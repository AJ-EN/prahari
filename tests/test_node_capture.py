"""Cheap unit tests for the capture spine: PTS clock, backoff, sizing, manager reconciliation."""
import random
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prahari.common.contracts import CameraInfo
from prahari.node import manager as manager_mod
from prahari.node.capture import CaptureConfig, PtsClock, backoff_delay, output_size, redact


def test_backoff_ladder_is_capped_jittered_and_never_tight():
    cfg = CaptureConfig()
    rng = random.Random(0)
    delays = [backoff_delay(i, cfg, rng) for i in range(10)]
    assert 1.5 <= delays[0] <= 2.5
    assert all(d >= 1.0 for d in delays)
    assert max(delays) <= cfg.backoff_max * (1 + cfg.backoff_jitter) + 1e-9
    assert delays[4] > delays[1]
    assert len({round(d, 6) for d in delays}) > 3        # jitter present


def test_output_size_preserves_aspect_and_even():
    assert output_size(1280, 720, 960) == (960, 540)
    assert output_size(640, 360, 960) == (640, 360)
    w, h = output_size(1921, 1081, 960)
    assert w == 960 and h % 2 == 0 and abs(h - 540) <= 2


def test_capture_ts_converges_on_minimum_offset():
    c = PtsClock(CaptureConfig())
    c.new_epoch()
    wall0 = 1000.0
    # replayed GOP: 2 s of PTS arrive in a 0.1 s burst, then real time
    burst = [(i * 0.1, wall0 + i * 0.005) for i in range(20)]
    live = [(2.0 + i * 0.1, wall0 + 0.1 + i * 0.1 + (0.03 if i % 3 else 0.0)) for i in range(50)]
    for pts, wall in burst + live:
        assert c.check(pts, wall) is None
        ts = c.capture_ts(pts, wall)
    # true offset is wall0 + 0.1 - 2.0 (live frames arrive with ~0 latency)
    assert abs(c.offset - (wall0 + 0.1 - 2.0)) < 1e-6
    assert abs(ts - (c.offset + live[-1][0])) < 1e-9


def test_discontinuity_backward_and_jump_but_not_gap():
    cfg = CaptureConfig(jump_tolerance_s=5.0)
    c = PtsClock(cfg)
    c.new_epoch()
    assert c.check(10.0, 100.0) is None
    assert c.check(10.04, 100.04) is None
    # a 20 s gap in both PTS and wall time is not a discontinuity
    assert c.check(30.04, 120.04) is None
    # PTS goes backwards: new epoch
    assert c.check(0.5, 120.1) == "pts_backward" and c.epoch == 2
    assert c.offset is None
    c.capture_ts(0.5, 120.1)
    # PTS leaps 3600 s ahead in 0.1 s of wall time: new epoch
    assert c.check(3600.6, 120.2) == "pts_jump" and c.epoch == 3


def test_measured_fps_from_pts_ignores_arrival_and_reorder():
    c = PtsClock(CaptureConfig())
    pts = [i / 12.0 for i in range(60)]
    for i in range(0, 60, 3):          # B-frame style reordering inside triples
        for p in (pts[i], pts[i + 2], pts[i + 1]) if i + 2 < 60 else pts[i:]:
            c.observe_packet(p)
    assert abs(c.measured_fps() - 12.0) < 0.3


def test_measured_fps_resets_on_pts_restart():
    c = PtsClock(CaptureConfig())
    for i in range(100):
        c.observe_packet(500 + i / 25.0)
    for i in range(50):
        c.observe_packet(i / 10.0)
    assert abs(c.measured_fps() - 10.0) < 0.5


def test_rate_limiter_hits_target_on_uneven_rates():
    for src_fps in (25.0, 15.0, 12.0, 10.0):
        c = PtsClock(CaptureConfig())
        c.new_epoch()
        emitted = 0
        n = int(src_fps * 60)
        for i in range(n):
            p = i / src_fps
            c.check(p, 1000 + p)
            if c.due(p, 5.0):
                emitted += 1
        rate = emitted / 60.0
        assert 4.5 <= rate <= 5.3, (src_fps, rate)


def test_rate_limiter_passes_everything_when_source_slower():
    c = PtsClock(CaptureConfig())
    c.new_epoch()
    out = [c.due(i * 0.5, 5.0) for i in range(10)]
    assert all(out)


def test_redact():
    assert redact("rtsp://user:pw@host:554/a") == "rtsp://host:554/a"
    assert redact("rtsp://host/a") == "rtsp://host/a"


class FakeWorker(threading.Thread):
    started = []

    def __init__(self, camera, cfg, on_sample=None, on_discontinuity=None, url=None):
        super().__init__(daemon=True)
        self.camera, self.url = camera, url
        self._ev = threading.Event()
        FakeWorker.started.append(camera.id)

    def run(self):
        self._ev.wait()

    def stop(self, join=True, timeout=1.0):
        self._ev.set()
        if join:
            self.join(timeout)

    def latest(self):
        return None

    def stats(self):
        return {"id": self.camera.id, "state": "live", "frames_emitted": 0, "reconnects": 0,
                "discontinuities": 0, "warnings": 0, "decode_errors": 0}


def test_manager_reconciles_catalogue_changes(monkeypatch):
    monkeypatch.setattr(manager_mod, "CameraWorker", FakeWorker)
    FakeWorker.started = []
    catalogue = {"v": [CameraInfo(id="1", rtsp_url="rtsp://h/1"), CameraInfo(id="2", rtsp_url="rtsp://h/2"),
                       CameraInfo(id="3", rtsp_url="rtsp://h/3", live=False), CameraInfo(id="4")]}
    fail = {"v": False}

    def fetch(url):
        if fail["v"]:
            raise ConnectionError("catalogue down")
        return list(catalogue["v"])

    m = manager_mod.NodeManager("http://x/api/ingest", fetch=fetch, allow_hls=True)
    m.refresh()
    assert sorted(m.camera_ids_running()) == ["1", "2"]            # 3 not live, 4 no url
    assert m.catalogue_stats["skipped_no_url"] == ["4"]
    # camera 2 removed, camera 5 added, camera 1 url changed
    catalogue["v"] = [CameraInfo(id="1", rtsp_url="rtsp://h/1b"), CameraInfo(id="5", rtsp_url="rtsp://h/5")]
    m.refresh()
    assert sorted(m.camera_ids_running()) == ["1", "5"]
    assert m.worker("1").url == "rtsp://h/1b"
    # catalogue outage keeps the current set
    fail["v"] = True
    m.refresh()
    assert sorted(m.camera_ids_running()) == ["1", "5"] and m.catalogue_stats["failures"] == 1
    fail["v"] = False
    # a single empty catalogue is ignored, a second one stops everything
    catalogue["v"] = []
    m.refresh()
    assert sorted(m.camera_ids_running()) == ["1", "5"]
    m.refresh()
    assert m.camera_ids_running() == []
    snap = m.snapshot()
    assert snap["totals"]["running"] == 0
    m.stop()


def test_manager_allowlist_and_cap(monkeypatch):
    monkeypatch.setattr(manager_mod, "CameraWorker", FakeWorker)
    cams = [CameraInfo(id=str(i), rtsp_url=f"rtsp://h/{i}") for i in range(10)]
    m = manager_mod.NodeManager("u", fetch=lambda u: cams, camera_ids=["2", "3", "7"], max_cameras=2)
    m.refresh()
    assert sorted(m.camera_ids_running()) == ["2", "3"]
    m.stop()
