"""Two-line plate handling: blue-strip trim, line split, and OCR with/without split."""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pytest

from prahari.anpr import models
from prahari.anpr.pipeline import split_two_line, trim_blue_strip
from prahari.anpr.synth import available_fonts, make_scene, render_plate

pytestmark = pytest.mark.skipif(not available_fonts(), reason="no macOS system fonts")


def test_split_finds_gap_between_lines():
    rng = random.Random(1)
    for font in available_fonts():
        img = render_plate("GJ05C0987", True, font_path=font, height=120, rng=rng)
        top, bottom = split_two_line(img)
        assert top is not None and bottom is not None
        h = img.shape[0]
        # The gap is near the middle; halves overlap slightly, never clip a line.
        assert 0.35 * h < top.shape[0] < 0.7 * h
        assert 0.35 * h < bottom.shape[0] < 0.7 * h
        assert top.shape[0] + bottom.shape[0] >= h


def test_split_rejects_tiny_crops():
    assert split_two_line(np.full((8, 20, 3), 255, np.uint8)) == (None, None)


def test_trim_blue_strip_present_and_absent():
    img = render_plate("GJ01AB1234", False, height=80)
    t = trim_blue_strip(img)
    assert t is not None
    cut = img.shape[1] - t.shape[1]
    assert 0.05 * img.shape[1] < cut < 0.15 * img.shape[1]
    no_strip = img.copy()
    no_strip[:, : int(img.shape[1] * 0.2)] = 250           # paint the strip white
    assert trim_blue_strip(no_strip) is None


@pytest.fixture(scope="module")
def pipeline():
    if not models.available():
        pytest.skip("models not downloaded (python -m prahari.anpr.models)")
    from prahari.anpr.pipeline import PipelineConfig, PlatePipeline
    return PlatePipeline(PipelineConfig(det_providers=("CPUExecutionProvider",), download_models=False))


def test_two_line_reads_beat_full_crop_only(pipeline):
    """On 56 px two-line plates the pipeline (full / trim / split hypotheses,
    grammar-scored) must read at least as well as the full crop alone, and
    well in absolute terms. Measured at time of writing: 90% vs 60%."""
    from prahari.common.plate_grammar import constrained_decode
    rng = random.Random(42)
    ok_pipe = ok_full = 0
    n = 20
    for _ in range(n):
        s = make_scene(rng, width=1280, two_line=True, plate_px=56)
        x, y, w, h = s.bbox
        crop = pipeline._padded_crop(s.image, x, y, x + w, y + h)
        best = pipeline.read_plate(crop)
        ok_pipe += bool(best.cands) and best.cands[0].plate == s.plate
        full = pipeline._ocr_batch([crop])[0][0]
        fc = constrained_decode(full)
        ok_full += bool(fc) and fc[0].plate == s.plate
    assert ok_pipe >= ok_full
    assert ok_pipe / n >= 0.7, (ok_pipe, ok_full)


def test_single_line_reads(pipeline):
    rng = random.Random(7)
    n, ok = 20, 0
    for _ in range(n):
        s = make_scene(rng, width=1280, two_line=False, plate_px=40)
        x, y, w, h = s.bbox
        best = pipeline.read_plate(pipeline._padded_crop(s.image, x, y, x + w, y + h))
        ok += bool(best.cands) and best.cands[0].plate == s.plate
    assert ok / n >= 0.9, ok
