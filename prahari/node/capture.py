"""
One capture thread per camera: RTSP (TCP) -> PyAV demux/decode -> FrameSample.

Rules this module is built around (from the organisers' sandbox notes):

  * RTSP is always forced over TCP.
  * All timing comes from PTS, never from arrival time. The gateway replays a
    buffered GOP on connect, so the first 1-2 s arrive faster than real time.
    Capture time is estimated as `ts = offset + pts_s`, where `offset` is the
    running minimum of (arrival_wall - pts_s) within the current epoch: late
    (replayed) frames give larger values, so the minimum converges on the true
    offset.
  * Declared fps is never trusted; the real rate is measured from PTS.
  * Frame intervals are not uniform and a gap is not a disconnect. Only a read
    timeout / EOF / error ends a session.
  * Reconnects use exponential backoff (2 s doubling to 30 s, with jitter).
  * Decoder warnings at join (H.265 "Could not find ref with POC", "Error
    constructing the frame RPS") are counted, never fatal. Bad packets are
    counted, never fatal.
  * PTS going backwards, or jumping forward far more than wall time did, is a
    discontinuity: `epoch` increments and `on_discontinuity` fires so trackers
    downstream can reset. Every new session is also a new epoch.
  * Latest-frame semantics: a 1-slot mailbox plus an optional callback. Nothing
    queues without bound; frames live in memory only.
"""
from __future__ import annotations

import collections
import logging
import random
import threading
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit, urlunsplit

import av
import av.logging

from prahari.node import access
from prahari.common.contracts import CameraInfo, FrameSample

log = logging.getLogger("prahari.node.capture")

STATES = ("idle", "connecting", "live", "backoff", "stopped")

_logging_lock = threading.Lock()
_logging_ready = False


def _ensure_libav_logging() -> None:
    """Route libav WARNING+ logs through PyAV so each worker thread can capture and
    count its own decoder warnings (av.logging.Capture(local=True)). Uncaptured
    logs (e.g. from other components) go to the 'libav' logger at ERROR only."""
    global _logging_ready
    with _logging_lock:
        if _logging_ready:
            return
        av.logging.set_level(av.logging.WARNING)
        av.logging.set_skip_repeated(False)       # repeat-skipping is global across threads
        logging.getLogger("libav").setLevel(logging.ERROR)
        _logging_ready = True


def redact(url: str) -> str:
    """Strip credentials from a URL for logs/stats."""
    try:
        p = urlsplit(url)
        if p.username or p.password:
            host = p.hostname or ""
            if p.port:
                host += f":{p.port}"
            return urlunsplit((p.scheme, host, p.path, p.query, p.fragment))
    except Exception:
        pass
    return url


@dataclass
class CaptureConfig:
    keyframes_only: bool = False     # skip_frame=NONKEY: near-zero CPU, ~0.5-1 fps
    target_fps: float = 5.0          # full-decode mode: emit at most this rate (by PTS)
    max_width: int = 960             # downscale on output, aspect preserved
    open_timeout: float = 10.0
    read_timeout: float = 10.0
    backoff_initial: float = 2.0
    backoff_max: float = 30.0
    backoff_jitter: float = 0.25     # +/- fraction
    stable_after_s: float = 20.0     # a session live this long resets the backoff
    jump_tolerance_s: float = 5.0    # PTS may lead wall time by this much before it is a jump
    backward_tolerance_s: float = 0.001
    fps_window_s: float = 10.0       # PTS span used for measured fps
    decoder_threads: int = 1         # 1 keeps decoder logs on the worker thread (countable)
    analyzeduration_us: int = 2_000_000
    probesize: int = 2_000_000
    extra_options: dict | None = None


def backoff_delay(attempt: int, cfg: CaptureConfig, rng: random.Random | None = None) -> float:
    """attempt 0 -> ~initial, doubling, capped, with +/- jitter. Never below 1 s."""
    base = min(cfg.backoff_max, cfg.backoff_initial * (2 ** max(0, attempt)))
    j = (rng or random).uniform(-cfg.backoff_jitter, cfg.backoff_jitter)
    return max(1.0, base * (1.0 + j))


def output_size(w: int, h: int, max_width: int) -> tuple[int, int]:
    if not max_width or w <= max_width:
        return w, h
    nh = max(2, int(round(h * max_width / w / 2.0)) * 2)
    return max_width, nh


class PtsClock:
    """PTS bookkeeping for one camera: epochs, discontinuities, capture-time offset,
    measured fps and the output rate limiter. Pure (no I/O) so it is unit-testable."""

    def __init__(self, cfg: CaptureConfig):
        self.cfg = cfg
        self.epoch = 0
        self.offset: float | None = None
        self.last_pts: float | None = None
        self.last_wall: float | None = None
        self.next_due: float | None = None
        self.frame_dt = 0.0
        self._win: collections.deque[float] = collections.deque()
        self._win_max = float("-inf")

    def new_epoch(self) -> int:
        self.epoch += 1
        self.offset = None
        self.last_pts = None
        self.last_wall = None
        self.next_due = None
        self._win.clear()
        self._win_max = float("-inf")
        return self.epoch

    def check(self, pts_s: float, wall: float) -> str | None:
        """Returns a discontinuity reason (and starts a new epoch) or None."""
        reason = None
        if self.last_pts is not None:
            d = pts_s - self.last_pts
            w = max(0.0, wall - (self.last_wall or wall))
            if d < -self.cfg.backward_tolerance_s:
                reason = "pts_backward"
            elif d > w + self.cfg.jump_tolerance_s:
                reason = "pts_jump"
        if reason:
            self.new_epoch()
        if self.last_pts is not None and pts_s > self.last_pts:
            dt = pts_s - self.last_pts
            self.frame_dt = dt if self.frame_dt == 0 else 0.9 * self.frame_dt + 0.1 * dt
        self.last_pts, self.last_wall = pts_s, wall
        return reason

    def capture_ts(self, pts_s: float, wall: float) -> float:
        sample = wall - pts_s
        if self.offset is None or sample < self.offset:
            self.offset = sample
        return self.offset + pts_s

    def observe_packet(self, pts_s: float) -> None:
        """Feed every packet's PTS (decode order is fine) for rate measurement."""
        if self._win and (pts_s < self._win_max - 2.0 or pts_s > self._win_max + self.cfg.jump_tolerance_s):
            self._win.clear()
            self._win_max = float("-inf")
        self._win.append(pts_s)
        if pts_s > self._win_max:
            self._win_max = pts_s
        while len(self._win) > 2 and self._win_max - self._win[0] > self.cfg.fps_window_s:
            self._win.popleft()
        if len(self._win) > 4096:
            self._win.popleft()

    def measured_fps(self) -> float | None:
        if len(self._win) < 3:
            return None
        span = self._win_max - min(self._win)
        if span < 0.5:
            return None
        return (len(self._win) - 1) / span

    def due(self, pts_s: float, target_fps: float) -> bool:
        """PTS-driven rate limiter: emit at most target_fps on average."""
        if not target_fps or target_fps <= 0:
            return True
        period = 1.0 / target_fps
        slack = 0.5 * self.frame_dt if self.frame_dt else 0.0
        if self.next_due is None or pts_s >= self.next_due - slack:
            nd = (self.next_due if self.next_due is not None else pts_s) + period
            # after a long gap, re-anchor instead of emitting a burst
            self.next_due = nd if nd > pts_s else pts_s + period
            return True
        return False


class CameraWorker(threading.Thread):
    """Capture loop for one camera. Thread-safe getters: latest(), stats()."""

    def __init__(self, camera: CameraInfo, cfg: CaptureConfig | None = None,
                 on_sample: Callable[[FrameSample], None] | None = None,
                 on_discontinuity: Callable[[str, int, str], None] | None = None,
                 url: str | None = None):
        super().__init__(name=f"cam-{camera.id}", daemon=True)
        _ensure_libav_logging()
        self.camera = camera
        self.cfg = cfg or CaptureConfig()
        # Always credential-free; access.with_credentials() adds them only when opening.
        self.url = access.strip_credentials(url or camera.rtsp_url or camera.hls_url)
        self.on_sample = on_sample
        self.on_discontinuity = on_discontinuity
        self._stop_ev = threading.Event()
        self._lock = threading.Lock()
        self._latest: FrameSample | None = None
        self.clock = PtsClock(self.cfg)
        self._rng = random.Random(hash(camera.id) ^ int(time.time()))
        # stats
        self.state = "idle"
        self.ever_live = False
        self.connect_attempts = 0
        self.sessions_ok = 0
        self.discontinuities = 0
        self.frames_decoded = 0
        self.frames_emitted = 0
        self.packets = 0
        self.decode_errors = 0
        self.warnings = 0
        self.warning_kinds: collections.Counter[str] = collections.Counter()
        self.transport_logs = 0
        self.transport_kinds: collections.Counter[str] = collections.Counter()
        self._decoder_names = {"h264", "hevc", "h265", "mpeg4", "mjpeg", "vp8", "vp9", "av1"}
        self.callback_errors = 0
        self.last_error = ""
        self.last_error_at: float | None = None
        self.last_frame_ts: float | None = None
        self.last_frame_wall: float | None = None
        self.last_pts: float | None = None
        self.next_retry_in: float | None = None
        self.stream_codec = ""
        self.stream_size: tuple[int, int] | None = None
        self.started_at = time.time()
        self.live_since: float | None = None

    # ---- public -------------------------------------------------------------
    def latest(self) -> FrameSample | None:
        with self._lock:
            return self._latest

    def stop(self, join: bool = True, timeout: float = 15.0) -> None:
        self._stop_ev.set()
        if join and self.is_alive() and threading.current_thread() is not self:
            self.join(timeout)

    @property
    def stopping(self) -> bool:
        return self._stop_ev.is_set()

    def stats(self) -> dict:
        now = time.time()
        with self._lock:
            mfps = self.clock.measured_fps()
            return {
                "id": self.camera.id,
                "state": self.state,
                "ever_live": self.ever_live,
                "url": redact(self.url),
                "codec": self.stream_codec or self.camera.codec,
                "size": list(self.stream_size) if self.stream_size else None,
                "declared_fps": self.camera.fps,
                "measured_fps": round(mfps, 2) if mfps else None,
                "epoch": self.clock.epoch,
                "frames_decoded": self.frames_decoded,
                "frames_emitted": self.frames_emitted,
                "packets": self.packets,
                "connect_attempts": self.connect_attempts,
                "reconnects": max(0, self.connect_attempts - 1),
                "discontinuities": self.discontinuities,
                "decode_errors": self.decode_errors,
                "warnings": self.warnings,
                "warning_top": [[k, n] for k, n in self.warning_kinds.most_common(3)],
                "transport_logs": self.transport_logs,
                "transport_top": [[k, n] for k, n in self.transport_kinds.most_common(3)],
                "callback_errors": self.callback_errors,
                "last_error": self.last_error,
                "last_error_age_s": round(now - self.last_error_at, 1) if self.last_error_at else None,
                "last_frame_ts": self.last_frame_ts,
                "last_frame_age_s": round(now - self.last_frame_wall, 2) if self.last_frame_wall else None,
                "next_retry_in_s": round(self.next_retry_in, 1) if self.state == "backoff" and self.next_retry_in else None,
                "keyframes_only": self.cfg.keyframes_only,
            }

    # ---- thread -------------------------------------------------------------
    def run(self) -> None:
        attempt = 0
        try:
            while not self._stop_ev.is_set():
                self._set_state("connecting")
                self.connect_attempts += 1
                self.live_since = None
                try:
                    self._session()
                    if not self._stop_ev.is_set():
                        self._error("stream ended")
                except Exception as e:  # never let one camera kill the thread
                    if not self._stop_ev.is_set():
                        self._error(f"{type(e).__name__}: {e}")
                if self._stop_ev.is_set():
                    break
                if self.live_since is not None and time.monotonic() - self.live_since >= self.cfg.stable_after_s:
                    attempt = 0     # that session was healthy: start the backoff ladder again
                delay = backoff_delay(attempt, self.cfg, self._rng)
                attempt += 1
                self.next_retry_in = delay
                self._set_state("backoff")
                self._stop_ev.wait(delay)
        finally:
            self._set_state("stopped")

    # ---- internals ----------------------------------------------------------
    def _set_state(self, s: str) -> None:
        with self._lock:
            self.state = s

    def _error(self, msg: str) -> None:
        msg = access.scrub(msg)   # libav echoes the URL, password included
        with self._lock:
            self.last_error = msg[:300]
            self.last_error_at = time.time()
        log.info("camera %s: %s", self.camera.id, msg)

    def _options(self) -> dict:
        opts = {
            "rtsp_transport": "tcp",
            "analyzeduration": str(self.cfg.analyzeduration_us),
            "probesize": str(self.cfg.probesize),
        }
        if not self.url.lower().startswith(("rtsp://", "rtsps://")):
            opts.pop("rtsp_transport")
        opts.update(access.ffmpeg_options_for(self.url))   # session cookie for HLS
        if self.cfg.extra_options:
            opts.update({k: str(v) for k, v in self.cfg.extra_options.items()})
        return opts

    def _drain_logs(self, logs: list) -> None:
        if not logs:
            return
        with self._lock:
            for level, name, msg in logs:
                msg = access.scrub(msg)
                if level > av.logging.WARNING:
                    continue
                key = msg.strip()[:60]
                if name in self._decoder_names:      # decoder (h264/hevc ...) warnings
                    self.warnings += 1
                    if len(self.warning_kinds) < 32 or key in self.warning_kinds:
                        self.warning_kinds[key] += 1
                else:                                # rtsp / tcp / demuxer messages
                    self.transport_logs += 1
                    if len(self.transport_kinds) < 32 or key in self.transport_kinds:
                        self.transport_kinds[key] += 1
        logs.clear()

    def _session(self) -> None:
        container = None
        with av.logging.Capture(local=True) as logs:
            try:
                container = av.open(access.with_credentials(self.url), options=self._options(),
                                    timeout=(self.cfg.open_timeout, self.cfg.read_timeout))
                self._drain_logs(logs)
                if not container.streams.video:
                    raise RuntimeError("no video stream")
                stream = container.streams.video[0]
                ctx = stream.codec_context
                try:
                    ctx.thread_count = max(1, int(self.cfg.decoder_threads))
                    if self.cfg.decoder_threads <= 1:
                        ctx.thread_type = "SLICE"
                except Exception:
                    pass
                if self.cfg.keyframes_only:
                    ctx.skip_frame = "NONKEY"
                tb = stream.time_base
                with self._lock:
                    self._decoder_names.add(ctx.name)
                    self.stream_codec = {"hevc": "h265"}.get(ctx.name, ctx.name)
                    if ctx.width and ctx.height:
                        self.stream_size = (ctx.width, ctx.height)
                    epoch = self.clock.new_epoch()      # new session: new epoch
                    self.sessions_ok += 1
                self._notify(epoch, "connect" if self.sessions_ok == 1 else "reconnect")
                for packet in container.demux(stream):
                    if self._stop_ev.is_set():
                        break
                    arrival = time.time()
                    if packet.size == 0 and packet.pts is None:
                        continue
                    self.packets += 1
                    if packet.pts is not None and tb is not None:
                        pts_s = float(packet.pts * tb)
                        with self._lock:
                            self.clock.observe_packet(pts_s)
                    try:
                        is_key = bool(packet.is_keyframe)
                        frames = ctx.decode(packet)
                        if self.cfg.keyframes_only and is_key:
                            # Skipped non-key frames never push a keyframe out of the
                            # decoder's reorder buffer, which would add a whole GOP of
                            # latency. Keyframes decode independently: drain and reset.
                            frames += ctx.decode(None)
                            ctx.flush_buffers()
                    except av.error.FFmpegError as e:    # bad packet: count, carry on
                        with self._lock:
                            self.decode_errors += 1
                        self._drain_logs(logs)
                        if self.decode_errors % 200 == 1:
                            log.debug("camera %s decode error: %s", self.camera.id, e)
                        continue
                    self._drain_logs(logs)
                    for frame in frames:
                        self._on_frame(frame, tb, arrival)
            finally:
                self._drain_logs(logs)
                if container is not None:
                    try:
                        container.close()
                    except Exception:
                        pass

    def _notify(self, epoch: int, reason: str) -> None:
        if self.on_discontinuity:
            try:
                self.on_discontinuity(self.camera.id, epoch, reason)
            except Exception:
                with self._lock:
                    self.callback_errors += 1

    def _on_frame(self, frame, tb, arrival: float) -> None:
        pts = frame.pts if frame.pts is not None else frame.dts
        ftb = frame.time_base or tb
        if pts is None or ftb is None:
            return
        pts_s = float(pts * ftb)
        with self._lock:
            reason = self.clock.check(pts_s, arrival)
            if reason:
                self.discontinuities += 1
            epoch = self.clock.epoch
            ts = self.clock.capture_ts(pts_s, arrival)
            self.frames_decoded += 1
            self.last_pts = pts_s
            if not self.ever_live or self.state != "live":
                self.state = "live"
                self.ever_live = True
                self.live_since = time.monotonic()
            emit = self.cfg.keyframes_only or self.clock.due(pts_s, self.cfg.target_fps)
            if frame.width and frame.height:
                self.stream_size = (frame.width, frame.height)
        if reason:
            log.info("camera %s: %s at pts %.3f -> epoch %d", self.camera.id, reason, pts_s, epoch)
            self._notify(epoch, reason)
        if not emit:
            return
        w, h = output_size(frame.width, frame.height, self.cfg.max_width)
        img = frame.reformat(width=w, height=h, format="bgr24").to_ndarray()
        sample = FrameSample(camera_id=self.camera.id, epoch=epoch, pts_s=pts_s, ts=ts,
                             image=img, width=w, height=h)
        with self._lock:
            self._latest = sample
            self.frames_emitted += 1
            self.last_frame_ts = ts
            self.last_frame_wall = arrival
        if self.on_sample:
            try:
                self.on_sample(sample)
            except Exception:
                with self._lock:
                    self.callback_errors += 1
