"""
NodeManager: keeps one CameraWorker per live catalogue camera.

  * polls the catalogue (default every 60 s); starts workers for new live cameras,
    stops workers for cameras that disappeared or went not-live, restarts a worker
    whose stream URL changed
  * a failed catalogue fetch keeps the current camera set (a catalogue blip must not
    take every camera down); an empty catalogue must be seen twice in a row before
    all cameras are stopped
  * opens only the cameras being processed: optional allowlist / predicate / cap
  * memory is bounded: one decoder + one latest FrameSample per camera, nothing queued
  * snapshot() is JSON-serialisable; latest(camera_id) returns the newest FrameSample
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Iterable

from prahari.common.contracts import CameraInfo, FrameSample
from prahari.node.capture import CameraWorker, CaptureConfig
from prahari.node.catalogue import fetch_catalogue

log = logging.getLogger("prahari.node.manager")


class NodeManager:
    def __init__(self, catalogue_url: str, config: CaptureConfig | None = None, poll_s: float = 60.0,
                 on_sample: Callable[[FrameSample], None] | None = None,
                 on_discontinuity: Callable[[str, int, str], None] | None = None,
                 camera_ids: Iterable[str] | None = None,
                 camera_filter: Callable[[CameraInfo], bool] | None = None,
                 max_cameras: int | None = None,
                 allow_hls: bool = True,
                 fetch: Callable[[str], list[CameraInfo]] = fetch_catalogue):
        self.catalogue_url = catalogue_url
        self.config = config or CaptureConfig()
        self.poll_s = poll_s
        self.on_sample = on_sample
        self.on_discontinuity = on_discontinuity
        self.camera_ids = {str(c) for c in camera_ids} if camera_ids else None
        self.camera_filter = camera_filter
        self.max_cameras = max_cameras
        self.allow_hls = allow_hls
        self._fetch = fetch
        self._lock = threading.RLock()
        self._workers: dict[str, CameraWorker] = {}
        self._retired: list[CameraWorker] = []
        self._cameras: dict[str, CameraInfo] = {}
        self._stop_ev = threading.Event()
        self._thread: threading.Thread | None = None
        self._empty_polls = 0
        self.catalogue_stats = {"url": catalogue_url, "polls": 0, "ok": 0, "failures": 0,
                                "last_ok_at": None, "last_error": "", "listed": 0, "live_listed": 0,
                                "selected": 0, "skipped_no_url": []}

    # ---- lifecycle ----------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_ev.clear()
        self._thread = threading.Thread(target=self._poll_loop, name="catalogue-poller", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 15.0) -> None:
        self._stop_ev.set()
        with self._lock:
            workers = list(self._workers.values()) + self._retired
            self._workers.clear()
            self._retired.clear()
        for w in workers:
            w.stop(join=False)
        deadline = time.monotonic() + timeout
        for w in workers:
            w.join(max(0.0, deadline - time.monotonic()))
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)

    def _poll_loop(self) -> None:
        while not self._stop_ev.is_set():
            try:
                self.refresh()
            except Exception as e:     # never let the poller die
                log.exception("catalogue refresh crashed: %s", e)
            self._stop_ev.wait(self.poll_s)

    # ---- catalogue reconciliation --------------------------------------------
    def _url_for(self, cam: CameraInfo) -> str:
        if cam.rtsp_url:
            return cam.rtsp_url
        return cam.hls_url if self.allow_hls else ""

    def _select(self, cams: list[CameraInfo]) -> list[CameraInfo]:
        out = []
        for c in cams:
            if not c.live:
                continue
            if self.camera_ids is not None and c.id not in self.camera_ids:
                continue
            if self.camera_filter is not None and not self.camera_filter(c):
                continue
            out.append(c)
        if self.max_cameras is not None:
            out = out[: self.max_cameras]
        return out

    def refresh(self) -> None:
        cs = self.catalogue_stats
        cs["polls"] += 1
        try:
            cams = self._fetch(self.catalogue_url)
        except Exception as e:
            cs["failures"] += 1
            cs["last_error"] = f"{type(e).__name__}: {e}"[:300]
            log.warning("catalogue fetch failed, keeping %d cameras: %s", len(self._workers), cs["last_error"])
            return
        cs["ok"] += 1
        cs["last_ok_at"] = time.time()
        cs["last_error"] = ""
        if not cams and self._workers:
            self._empty_polls += 1
            if self._empty_polls < 2:
                log.warning("catalogue returned no cameras; keeping current set until it happens twice")
                return
        else:
            self._empty_polls = 0
        cs["listed"] = len(cams)
        cs["live_listed"] = sum(1 for c in cams if c.live)
        selected = self._select(cams)
        no_url = [c.id for c in selected if not self._url_for(c)]
        cs["skipped_no_url"] = no_url[:50]
        selected = [c for c in selected if self._url_for(c)]
        cs["selected"] = len(selected)
        want = {c.id: c for c in selected}
        with self._lock:
            self._cameras = {c.id: c for c in cams}
            for cid in list(self._workers):
                w = self._workers[cid]
                if cid not in want or self._url_for(want[cid]) != w.url or not w.is_alive():
                    reason = ("removed" if cid not in want else
                              "url changed" if self._url_for(want[cid]) != w.url else "thread died")
                    log.info("stopping camera %s (%s)", cid, reason)
                    w.stop(join=False)
                    self._retired.append(w)
                    del self._workers[cid]
            for cid, cam in want.items():
                if cid in self._workers:
                    self._workers[cid].camera = cam     # refresh metadata (name, declared fps ...)
                    continue
                w = CameraWorker(cam, self.config, on_sample=self.on_sample,
                                 on_discontinuity=self.on_discontinuity, url=self._url_for(cam))
                self._workers[cid] = w
                w.start()
                log.info("started camera %s -> %s", cid, w.url)
            self._retired = [w for w in self._retired if w.is_alive()]

    # ---- queries --------------------------------------------------------------
    def latest(self, camera_id: str) -> FrameSample | None:
        with self._lock:
            w = self._workers.get(str(camera_id))
        return w.latest() if w else None

    def camera_ids_running(self) -> list[str]:
        with self._lock:
            return list(self._workers)

    def cameras(self) -> list[CameraInfo]:
        with self._lock:
            return list(self._cameras.values())

    def worker(self, camera_id: str) -> CameraWorker | None:
        with self._lock:
            return self._workers.get(str(camera_id))

    def snapshot(self) -> dict:
        with self._lock:
            workers = list(self._workers.values())
            retired_alive = sum(1 for w in self._retired if w.is_alive())
        cams = [w.stats() for w in workers]
        states: dict[str, int] = {}
        for c in cams:
            states[c["state"]] = states.get(c["state"], 0) + 1
        return {
            "at": time.time(),
            "catalogue": dict(self.catalogue_stats),
            "totals": {
                "running": len(cams),
                "states": states,
                "live": states.get("live", 0),
                "stopping": retired_alive,
                "frames_emitted": sum(c["frames_emitted"] for c in cams),
                "reconnects": sum(c["reconnects"] for c in cams),
                "discontinuities": sum(c["discontinuities"] for c in cams),
                "warnings": sum(c["warnings"] for c in cams),
                "transport_logs": sum(c.get("transport_logs", 0) for c in cams),
                "decode_errors": sum(c["decode_errors"] for c in cams),
            },
            "cameras": cams,
        }
