"""
ANPR throughput benchmark on this machine.

    .venv/bin/python -m prahari.anpr.bench [--iters 60] [--providers cpu|coreml] [--threads 0]

For 640-, 960- and 1280-wide frames it times PlatePipeline.process() on
  * "empty" frames (no plate: detector cost only), and
  * "1 plate" frames (detector + OCR hypotheses + grammar for one plate),
reports median and p90 ms/frame, and derives streams per node:

    streams @ f fps = floor(1000 / (p90_ms * f))      (one worker, one pipeline)

p90 rather than median, so a node is not sized on its good frames. Frames
are synthetic but the cost does not depend on content beyond plate count;
a frame with k plates costs roughly det + k * ocr_per_plate.

This measures inference only. Decoding the camera stream (H.264/H.265 via
PyAV) is extra and belongs to the node's budget; so is JPEG evidence writing.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import random
import statistics
import time

from prahari.anpr.pipeline import PipelineConfig, PlatePipeline
from prahari.anpr.synth import make_scene, _background
from prahari.common.contracts import FrameSample


def _pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]


def run(iters: int = 60, providers: str = "coreml", threads: int = 0) -> dict:
    prov = ("CoreMLExecutionProvider", "CPUExecutionProvider") if providers == "coreml" \
        else ("CPUExecutionProvider",)
    pl = PlatePipeline(PipelineConfig(det_providers=prov, intra_op_threads=threads))
    rng = random.Random(3)
    res = {}
    for width in (640, 960, 1280):
        h = int(width * 9 / 16)
        empty = _background(width, h, rng)
        # A scene whose plate the detector actually finds, so OCR is timed too.
        for _ in range(50):
            with_plate = make_scene(rng, width=width, two_line=False,
                                    plate_px=int(40 * width / 960)).image
            if pl.process(FrameSample("bench", 0, 0.0, 0.0, with_plate, width, h)):
                break
        for label, img in (("empty", empty), ("1 plate", with_plate)):
            fs = FrameSample("bench", 0, 0.0, 0.0, img, width, h)
            for _ in range(5):
                pl.process(fs)
            ts, det, ocr, n = [], [], [], []
            for _ in range(iters):
                t = time.perf_counter()
                evs = pl.process(fs)
                ts.append((time.perf_counter() - t) * 1e3)
                det.append(pl.last_timing["det_ms"])
                ocr.append(pl.last_timing["ocr_ms"])
                n.append(len(evs))
            p90 = _pct(ts, 0.9)
            res[f"{width}/{label}"] = {
                "median_ms": round(statistics.median(ts), 1),
                "p90_ms": round(p90, 1),
                "det_ms": round(statistics.median(det), 1),
                "ocr_ms": round(statistics.median(ocr), 1),
                "plates": statistics.median(n),
                "streams_1fps": math.floor(1000 / p90),
                "streams_2fps": math.floor(1000 / (2 * p90)),
            }
    return {"machine": f"{platform.machine()} {platform.processor()} {platform.platform()}",
            "det_providers": list(prov), "ocr_providers": list(pl.cfg.ocr_providers), "intra_op_threads": threads or "default", "iters": iters,
            "results": res}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=60)
    ap.add_argument("--providers", choices=["cpu", "coreml"], default="coreml")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    r = run(a.iters, a.providers, a.threads)
    if a.json:
        print(json.dumps(r, indent=1))
        return
    print(f"{r['machine']} | detector={r['det_providers'][0]} ocr={r['ocr_providers'][0]} threads={r['intra_op_threads']} iters={r['iters']}")
    print(f"{'frame':<16}{'median':>8}{'p90':>8}{'det':>8}{'ocr':>8}{'@1fps':>8}{'@2fps':>8}   (ms; streams/node)")
    for k, v in r["results"].items():
        print(f"{k:<16}{v['median_ms']:>8}{v['p90_ms']:>8}{v['det_ms']:>8}{v['ocr_ms']:>8}"
              f"{v['streams_1fps']:>8}{v['streams_2fps']:>8}")


if __name__ == "__main__":
    main()
