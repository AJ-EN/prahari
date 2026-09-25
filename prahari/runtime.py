"""
The running system: cameras -> plate reader -> registry -> live alerts, in one
process alongside the API and console.

    NodeManager (one thread per camera, newest frame only)
        |  latest(camera_id)
        v
    ANPR scheduler thread  -- round-robin over cameras, one frame each --
        PlatePipeline -> CameraProfiler -> PlateDeduper
        |  PlateEvent
        v
    registry.events.ingest  -> watchlist match -> alert/review -> AlertBus (SSE)

Scheduling is capability-aware: a camera the profiler has measured as unable
to read plates (a corridor, a depot, plates too small) is still sampled, but
only one frame in ten, so the inference budget goes where plates are legible.

Health: every 10 s each camera's measured state (live / reconnecting / down,
measured fps, codec, resolution, reconnects, ANPR profile) is written to the
registry, which is what the console's wall, map and gap report show.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

import cv2

from prahari.common import diskguard
from prahari.common.contracts import CameraInfo, FrameSample, PlateEvent
from prahari.node.access import strip_credentials
from prahari.node.capture import CaptureConfig
from prahari.node.manager import NodeManager
from prahari.registry import cameras as cam_mod
from prahari.registry import events as ev_mod
from prahari.registry.db import Store
from prahari.settings import Settings

log = logging.getLogger("prahari.runtime")

STATE_TO_STATUS = {"live": "online", "connecting": "degraded", "backoff": "offline",
                   "stopped": "offline"}
UNVIABLE_EVERY = 10          # sample 1 in N frames on cameras measured ANPR-unviable
UNVIABLE_MIN_FRAMES = 60     # ...but only once there is enough evidence
OVERLAY_MAX_AGE_S = 1.5      # show the analysed frame (with its boxes) if this fresh


def camera_row(c: CameraInfo) -> dict:
    return {"id": c.id, "name": c.name or f"Camera {c.id}", "department": c.department,
            "lat": c.lat, "lon": c.lon, "codec": c.codec, "width": c.width, "height": c.height,
            "fps": c.fps, "live": c.live, "rtsp_url": strip_credentials(c.rtsp_url),
            "hls_url": strip_credentials(c.hls_url), "whep_url": strip_credentials(c.whep_url)}


class Runtime:
    def __init__(self, settings: Settings, store: Store, bus: Any):
        self.s = settings
        self.store = store
        self.bus = bus
        self.manager: NodeManager | None = None
        self.pipeline = None
        self.deduper = None
        self.profiler = None
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._analysed: dict[str, tuple] = {}    # camera -> (FrameSample, [(bbox, text)])
        self._snap_cache: dict[str, tuple] = {}  # camera -> ((epoch, pts), jpeg bytes)
        self._lock = threading.Lock()
        self.started_at = time.time()
        self.stats: dict[str, Any] = {
            "anpr_state": "off" if not settings.anpr else "loading",
            "anpr_error": "", "anpr_providers": [], "frames_processed": 0,
            "frames_skipped_unviable": 0, "ms_avg": None, "plates_read": 0,
            "events_emitted": 0, "alerts": 0, "reviews": 0, "dropped_disk": 0,
            "last_event_at": None, "catalogue_sync": None,
        }

    # ------------------------------------------------------------ lifecycle
    def start(self) -> None:
        cfg = CaptureConfig(keyframes_only=self.s.capture_mode == "keyframes",
                            target_fps=self.s.target_fps, max_width=self.s.max_width)
        self.manager = NodeManager(
            self.s.ingest_url, cfg, poll_s=self.s.catalogue_poll_s,
            on_discontinuity=self._on_discontinuity,
            max_cameras=self.s.max_cameras or None)
        self.manager.start()
        self._spawn(self._health_loop, "health")
        if self.s.anpr:
            self._spawn(self._anpr_loop, "anpr")

    def stop(self) -> None:
        self._stop.set()
        if self.manager:
            self.manager.stop(timeout=12)
        for t in self._threads:
            t.join(timeout=5)
        if self.deduper:
            for ev in self.deduper.flush():
                self._ingest(ev)

    def _spawn(self, fn, name: str) -> None:
        t = threading.Thread(target=fn, name=name, daemon=True)
        t.start()
        self._threads.append(t)

    # ------------------------------------------------------------ ANPR loop
    def _load_anpr(self) -> bool:
        try:
            from prahari.anpr.ccap import CameraProfiler
            from prahari.anpr.dedup import PlateDeduper
            from prahari.anpr.pipeline import PipelineConfig, PlatePipeline
            self.pipeline = PlatePipeline(PipelineConfig(save_evidence=self.s.save_evidence))
            self.deduper = PlateDeduper(window_s=6.0, mode=self.s.dedup_mode)
            self.profiler = CameraProfiler()
            self.stats["anpr_providers"] = list(self.pipeline.det_providers)
            self.stats["anpr_state"] = "running"
            return True
        except Exception as e:                      # models missing, onnxruntime absent...
            log.exception("plate reader failed to load")
            self.stats["anpr_state"] = "failed"
            self.stats["anpr_error"] = f"{type(e).__name__}: {e}"
            return False

    def _anpr_loop(self) -> None:
        if not self._load_anpr():
            return
        last: dict[str, tuple] = {}
        seen_since_skip: dict[str, int] = {}
        ms_ewma = None
        while not self._stop.is_set():
            ids = self.manager.camera_ids_running() if self.manager else []
            did = 0
            for cid in ids:
                if self._stop.is_set():
                    break
                s = self.manager.latest(cid)
                if s is None:
                    continue
                key = (s.epoch, s.pts_s)
                if last.get(cid) == key:
                    continue
                last[cid] = key
                prof = self.profiler.profile(cid)
                if prof["frames"] >= UNVIABLE_MIN_FRAMES and not prof["anpr_viable"]:
                    n = seen_since_skip.get(cid, 0) + 1
                    seen_since_skip[cid] = n
                    if n % UNVIABLE_EVERY:
                        self.stats["frames_skipped_unviable"] += 1
                        continue
                t0 = time.perf_counter()
                try:
                    evs = self.pipeline.process(s)
                except Exception as e:
                    log.warning("plate reader error on camera %s: %s", cid, e)
                    continue
                dt = (time.perf_counter() - t0) * 1000
                ms_ewma = dt if ms_ewma is None else 0.9 * ms_ewma + 0.1 * dt
                self.stats["ms_avg"] = round(ms_ewma, 1)
                self.stats["frames_processed"] += 1
                self.stats["plates_read"] += len(evs)
                self.profiler.update(cid, evs)
                with self._lock:
                    self._analysed[cid] = (s, [(ev.bbox, ev.plate or ev.raw_text) for ev in evs])
                out = self.deduper.push_many(evs, s.epoch) + self.deduper.tick(cid, s.ts)
                for ev in out:
                    self._ingest(ev)
                did += 1
            if not did:
                time.sleep(0.05)

    def _on_discontinuity(self, camera_id: str, epoch: int, reason: str) -> None:
        if self.deduper:
            for ev in self.deduper.flush(camera_id):
                self._ingest(ev)

    def _ingest(self, ev: PlateEvent) -> None:
        if not diskguard.can_write():
            self.stats["dropped_disk"] += 1
            return
        try:
            res = ev_mod.ingest(self.store, ev.to_dict())
        except Exception as e:
            log.warning("could not store plate event: %s", e)
            return
        self.stats["events_emitted"] += 1
        self.stats["last_event_at"] = time.time()
        for a in res.get("alerts", []):
            if a.get("kind") == "alert":
                self.stats["alerts"] += 1
            else:
                self.stats["reviews"] += 1
            self.bus.publish(a)

    # ------------------------------------------------------------ health loop
    def _health_loop(self) -> None:
        last_upsert = 0.0
        while not self._stop.wait(2.0 if not last_upsert else 10.0):
            if not self.manager:
                continue
            try:
                cams = self.manager.cameras()
                if cams and time.time() - last_upsert > self.s.catalogue_poll_s:
                    # The node's parse is the one that opens streams, so it is the
                    # source of truth for camera ids in the registry.
                    res = cam_mod.upsert(self.store, [camera_row(c) for c in cams],
                                         source="catalogue", catalogue_url=self.s.ingest_url)
                    self.stats["catalogue_sync"] = {"at": time.time(), "cameras": len(cams),
                                                    **{k: len(v) for k, v in res.items()
                                                       if isinstance(v, list)}}
                    last_upsert = time.time()
                snap = self.manager.snapshot()
                for c in snap["cameras"]:
                    cap = {"state": c["state"], "measured_fps": c["measured_fps"],
                           "codec": c["codec"], "size": c["size"],
                           "reconnects": c["reconnects"], "decode_warnings": c["warnings"],
                           "last_error": c["last_error"] or ""}
                    if self.profiler:
                        cap["anpr"] = self.profiler.profile(c["id"])
                    cam_mod.update_health(self.store, c["id"],
                                          status=STATE_TO_STATUS.get(c["state"], "unknown"),
                                          last_seen=c["last_frame_ts"], capability=cap)
            except Exception as e:
                log.warning("health update failed: %s", e)

    # ------------------------------------------------------------ for the API
    def snapshot_jpeg(self, camera_id: str, max_width: int = 640) -> bytes | None:
        if not self.manager:
            return None
        s: FrameSample | None = self.manager.latest(camera_id)
        if s is None:
            return None
        # Prefer the frame the plate reader actually analysed, so boxes line up
        # with what they were drawn from; fall back to the newest frame.
        with self._lock:
            analysed = self._analysed.get(camera_id)
        boxes: list = []
        if analysed and s.ts - analysed[0].ts <= OVERLAY_MAX_AGE_S:
            s, boxes = analysed
        key = (s.epoch, s.pts_s)
        cached = self._snap_cache.get(camera_id)
        if cached and cached[0] == key:
            return cached[1]
        img = s.image.copy()
        for (x, y, w, h), text in boxes:
            cv2.rectangle(img, (x, y), (x + w, y + h), (80, 220, 120), 3)
            cv2.putText(img, text, (x, max(18, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        (80, 220, 120), 2, cv2.LINE_AA)
        h, w = img.shape[:2]
        if w > max_width:
            img = cv2.resize(img, (max_width, int(h * max_width / w)), interpolation=cv2.INTER_AREA)
        ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ok:
            return None
        data = enc.tobytes()
        self._snap_cache[camera_id] = (key, data)
        return data

    def status(self) -> dict:
        snap = self.manager.snapshot() if self.manager else {"totals": {}, "catalogue": {}}
        return {
            "uptime_s": round(time.time() - self.started_at),
            "settings": {"ingest_url": self.s.ingest_url, "capture_mode": self.s.capture_mode,
                         "target_fps": self.s.target_fps, "max_width": self.s.max_width,
                         "max_cameras": self.s.max_cameras, "anpr": self.s.anpr,
                         "dedup_mode": self.s.dedup_mode},
            "cameras": snap.get("totals", {}),
            "catalogue": snap.get("catalogue", {}),
            "anpr": dict(self.stats),
            "disk": diskguard.report(),
        }


def attach(app, runtime: Runtime) -> None:
    """Add the live endpoints to the API, ahead of the console's catch-all mount."""
    from fastapi import HTTPException
    from fastapi.responses import FileResponse, Response

    def snapshot(camera_id: str):
        data = runtime.snapshot_jpeg(camera_id)
        if data is None:
            raise HTTPException(404, detail="no frame from this camera yet")
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    def status():
        return runtime.status()

    def evidence(camera_id: str, filename: str):
        root = (diskguard.DATA / "evidence").resolve()
        p = (root / camera_id / filename).resolve()
        if root not in p.parents or not p.is_file():
            raise HTTPException(404, detail="no such evidence file")
        return FileResponse(p, media_type="image/jpeg")

    before = len(app.router.routes)
    app.add_api_route("/api/cameras/{camera_id}/snapshot.jpg", snapshot, methods=["GET"],
                      tags=["live"], summary="Latest frame from a camera (JPEG, with plate boxes)")
    app.add_api_route("/api/runtime", status, methods=["GET"], tags=["live"],
                      summary="Live status: cameras, plate reader, throughput, disk")
    app.add_api_route("/api/evidence/{camera_id}/{filename}", evidence, methods=["GET"],
                      tags=["live"], summary="An evidence crop saved with a plate event")
    new = app.router.routes[before:]
    del app.router.routes[before:]
    app.router.routes[0:0] = new
