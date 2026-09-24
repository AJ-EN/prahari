"""PlateDeduper: per-camera, per-epoch suppression of repeated plate reads."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from prahari.anpr.dedup import PlateDeduper
from prahari.common.contracts import PlateEvent


def ev(plate, ts, cam="c1", conf=0.9, raw=None, det=0.9):
    raw = raw or plate or ""
    return PlateEvent(event_id=f"{cam}-{ts}-{raw}", camera_id=cam, ts=ts, pts_s=ts, raw_text=raw,
                      plate=plate, ocr_conf=conf, det_conf=det, bbox=(0, 0, 100, 25),
                      valid=plate == raw)


def test_repeats_collapse_to_best_read():
    d = PlateDeduper(window_s=5, mode="best")
    out = []
    out += d.push(ev("GJ01AB1234", 0.0, conf=0.7), 0)
    out += d.push(ev("GJ01AB1234", 0.5, conf=0.95), 0)
    out += d.push(ev("GJ01AB1284", 1.0, conf=0.6), 0)   # 1 misread char, same car
    assert out == []                                     # still open
    out += d.tick("c1", 7.0)                             # quiet > window
    assert len(out) == 1 and out[0].ocr_conf == 0.95 and out[0].plate == "GJ01AB1234"


def test_confusable_misreads_join_cluster():
    d = PlateDeduper(window_s=5)
    d.push(ev("GJ01AB1234", 0.0), 0)
    d.push(ev(None, 0.4, raw="6J01A8I234", conf=0.99), 0)   # uncorrected raw, confusion-close
    assert d.open_clusters("c1") == 1
    out = d.flush()
    assert len(out) == 1 and out[0].plate == "GJ01AB1234"   # grammar-valid read preferred


def test_different_plates_stay_separate():
    d = PlateDeduper(window_s=5)
    d.push(ev("GJ01AB1234", 0.0), 0)
    d.push(ev("MH12XY9876", 0.2), 0)
    assert d.open_clusters("c1") == 2
    assert {e.plate for e in d.flush()} == {"GJ01AB1234", "MH12XY9876"}


def test_same_plate_after_window_is_new_sighting():
    d = PlateDeduper(window_s=5)
    out = d.push(ev("GJ01AB1234", 0.0), 0)
    out += d.push(ev("GJ01AB1234", 20.0), 0)   # closes the first, opens a second
    out += d.flush()
    assert [e.ts for e in out] == [0.0, 20.0]


def test_window_measured_from_last_seen_not_first():
    d = PlateDeduper(window_s=5)
    out = []
    for t in (0, 4, 8, 12):                      # a slow car, always within 5 s of last read
        out += d.push(ev("GJ01AB1234", float(t)), 0)
    out += d.flush()
    assert len(out) == 1


def test_epoch_change_flushes_and_resets():
    d = PlateDeduper(window_s=60)
    d.push(ev("GJ01AB1234", 100.0, conf=0.8), 0)
    out = d.push(ev("GJ01AB1234", 101.0), 1)     # reconnect: epoch 1
    assert len(out) == 1 and out[0].ts == 100.0  # pending best of epoch 0 emitted
    assert d.open_clusters("c1") == 1            # new epoch starts its own cluster
    assert len(d.flush()) == 1


def test_cameras_are_independent():
    d = PlateDeduper(window_s=5)
    d.push(ev("GJ01AB1234", 0.0, cam="a"), 0)
    d.push(ev("GJ01AB1234", 0.1, cam="b"), 0)
    assert d.open_clusters("a") == 1 and d.open_clusters("b") == 1
    assert len(d.flush()) == 2


def test_first_mode_emits_immediately_once():
    d = PlateDeduper(window_s=5, mode="first")
    assert len(d.push(ev("GJ01AB1234", 0.0), 0)) == 1
    assert d.push(ev("GJ01AB1234", 1.0, conf=0.99), 0) == []
    assert d.tick("c1", 10.0) == [] and d.flush() == []


def test_bad_mode_rejected():
    with pytest.raises(ValueError):
        PlateDeduper(mode="latest")
