"""CCAP-lite camera capability profiles."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prahari.anpr import ccap
from prahari.anpr.ccap import CameraProfiler
from prahari.common.contracts import PlateEvent


def ev(h, valid=True, plate="GJ01AB1234"):
    return PlateEvent(event_id="x", camera_id="c", ts=0, pts_s=0, raw_text=plate if valid else "XX",
                      plate=plate, ocr_conf=0.9, det_conf=0.9, bbox=(0, 0, 4 * h, h), valid=valid)


def feed(p, cam, n_frames, events_per_frame):
    for i in range(n_frames):
        p.update(cam, events_per_frame(i))


def test_output_keys():
    p = CameraProfiler()
    feed(p, "c", 3, lambda i: [])
    out = p.profile("c")
    for k in ("camera_id", "frames", "plates", "anpr_viable", "plate_px_median", "valid_rate"):
        assert k in out
    assert out["frames"] == 3 and out["plates"] == 0 and out["anpr_viable"] is False
    assert out["reason"] == "insufficient data"


def test_good_camera_is_viable():
    p = CameraProfiler()
    feed(p, "c", 60, lambda i: [ev(40)] if i % 3 == 0 else [])
    out = p.profile("c")
    assert out["anpr_viable"] and out["plate_px_median"] == 40 and out["valid_rate"] == 1.0


def test_small_plates_not_viable():
    p = CameraProfiler()
    feed(p, "c", 60, lambda i: [ev(12)])
    out = p.profile("c")
    assert not out["anpr_viable"] and "too small" in out["reason"]


def test_illegible_reads_not_viable():
    p = CameraProfiler()
    feed(p, "c", 60, lambda i: [ev(40, valid=(i % 5 == 0), plate=None if i % 5 else "GJ01AB1234")])
    out = p.profile("c")
    assert out["valid_rate"] < ccap.MIN_VALID_RATE and not out["anpr_viable"]
    assert "illegible" in out["reason"]


def test_unknown_camera_and_profiles_list():
    p = CameraProfiler()
    assert p.profile("nope")["frames"] == 0
    p.update("b", [])
    p.update("a", [])
    assert [x["camera_id"] for x in p.profiles()] == ["a", "b"]
