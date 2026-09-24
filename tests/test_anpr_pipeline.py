"""PlatePipeline end to end on synthetic frames: contract, accuracy floor, evidence crops."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

from prahari.anpr import models
from prahari.anpr.dedup import PlateDeduper
from prahari.anpr.pipeline import PlatePipeline, PipelineConfig, encode_jpeg_capped
from prahari.anpr.synth import available_fonts, make_scene
from prahari.common import diskguard
from prahari.common.contracts import FrameSample, PlateEvent

pytestmark = pytest.mark.skipif(not available_fonts(), reason="no macOS system fonts")


@pytest.fixture(scope="module")
def pl():
    if not models.available():
        pytest.skip("models not downloaded (python -m prahari.anpr.models)")
    # CPU for the detector in tests: deterministic, and avoids an intermittent
    # CoreML-EP crash at interpreter exit (see pipeline.py).
    return PlatePipeline(PipelineConfig(det_providers=("CPUExecutionProvider",),
                                        download_models=False))


def frame(img, cam="cam-01", ts=1_700_000_000.0, epoch=0):
    return FrameSample(camera_id=cam, epoch=epoch, pts_s=12.5, ts=ts, image=img,
                       width=img.shape[1], height=img.shape[0])


def test_empty_and_blank_frames(pl):
    assert pl.process(frame(np.zeros((540, 960, 3), np.uint8))) == []
    assert pl.process(FrameSample("c", 0, 0, 0, None, 0, 0)) == []


def test_event_contract(pl):
    rng = random.Random(3)
    for _ in range(10):
        s = make_scene(rng, width=1280, two_line=False, plate_px=44)
        evs = pl.process(frame(s.image))
        if evs:
            break
    assert evs, "detector found nothing in 10 synthetic frames"
    e = evs[0]
    assert isinstance(e, PlateEvent) and len(e.event_id) == 32
    assert e.camera_id == "cam-01" and e.ts == 1_700_000_000.0 and e.pts_s == 12.5
    assert e.raw_text == e.raw_text.upper() and e.raw_text.isalnum()
    assert 0.0 <= e.ocr_conf <= 1.0 and 0.0 <= e.det_conf <= 1.0
    x, y, w, h = e.bbox
    assert all(isinstance(v, int) for v in e.bbox) and w > 0 and h > 0
    assert x + w <= 1280 and y + h <= 720
    if e.plate:
        assert e.candidates and e.candidates[0]["plate"] == e.plate
        assert set(e.candidates[0]) == {"plate", "distance", "score", "edits"}
    d = e.to_dict()
    assert isinstance(d["bbox"], list) and d["crop_path"] is None


def test_synthetic_accuracy_floor(pl):
    """Guard against regressions. Single-line plates, 1280-wide frames,
    realistic-ish 28-48 px plates. Measured ~95% at time of writing; the
    floor is set well below to allow model/provider jitter."""
    rng = random.Random(11)
    n, hit, ok = 30, 0, 0
    for _ in range(n):
        s = make_scene(rng, width=1280, two_line=False, plate_px=rng.randint(28, 48))
        evs = pl.process(frame(s.image))
        if evs:
            hit += 1
            ok += any(e.plate == s.plate for e in evs)
    assert hit / n >= 0.8, hit
    assert ok / n >= 0.75, ok


def test_evidence_crop_written_small(pl, tmp_path):
    cfg = PipelineConfig(det_providers=("CPUExecutionProvider",), download_models=False,
                         save_evidence=True, evidence_root=tmp_path / "evidence")
    p2 = PlatePipeline(cfg)
    rng = random.Random(5)
    evs = []
    for _ in range(10):
        s = make_scene(rng, width=1280, two_line=False, plate_px=44)
        evs = p2.process(frame(s.image, cam="cam/../07 west"))
        if evs:
            break
    assert evs
    p = Path(evs[0].crop_path)
    assert p.exists() and p.suffix == ".jpg"
    assert p.parent.parent == tmp_path / "evidence"     # camera id sanitised, no traversal
    assert p.stat().st_size <= 30_000


def test_evidence_skipped_when_disk_low(pl, tmp_path, monkeypatch):
    cfg = PipelineConfig(det_providers=("CPUExecutionProvider",), download_models=False,
                         save_evidence=True, evidence_root=tmp_path / "ev")
    p2 = PlatePipeline(cfg)
    monkeypatch.setattr(diskguard, "can_write", lambda *a, **k: False)
    rng = random.Random(5)
    for _ in range(10):
        s = make_scene(rng, width=1280, two_line=False, plate_px=44)
        evs = p2.process(frame(s.image))
        if evs:
            break
    assert evs and all(e.crop_path is None for e in evs)
    assert not (tmp_path / "ev").exists()


def test_jpeg_cap_on_large_noisy_image():
    img = np.random.default_rng(0).integers(0, 255, (900, 1600, 3), dtype=np.uint8)
    data = encode_jpeg_capped(img, 30_000, 360)
    assert data is not None and len(data) <= 30_000


def test_ind_prefix_and_seam_duplicate_repaired():
    r = PlatePipeline._score("full", "INDGJ01AB12", [0.9] * 11)
    assert r.raw == "INDGJ01AB12" and not r.valid        # raw_text preserved verbatim
    r = PlatePipeline._score("split", "KAA33QV7580", [0.9] * 11)   # duplicated char at the seam
    assert r.cands and r.cands[0].plate == "KA33QV7580"
    r = PlatePipeline._score("full", "GJ01AB1234", [0.9] * 10)
    assert r.valid and r.cands[0].plate == "GJ01AB1234" and r.quality == pytest.approx(0.9)


def test_multi_frame_pass_dedups_to_one(pl):
    """Same car in 6 consecutive frames (slightly different renders) -> 1 event."""
    rng = random.Random(21)
    s0 = make_scene(rng, width=1280, two_line=False, plate_px=44)
    d = PlateDeduper(window_s=5)
    out = []
    for i in range(6):
        s = make_scene(random.Random(100 + i), width=1280, plate=s0.plate, two_line=False,
                       plate_px=44 + i)
        out += d.push_many(pl.process(frame(s.image, ts=1000.0 + i * 0.5)), epoch=0)
    out += d.flush()
    assert len([e for e in out if e.plate == s0.plate]) == 1
