"""
Synthetic accuracy evaluation for the ANPR pipeline.

    .venv/bin/python -m prahari.anpr.evaluate [--n 60] [--out data/anpr-test/eval.json]

Two measurements, kept separate on purpose:

  A. END-TO-END on synthetic scenes (detector + OCR + grammar), per frame
     width and layout. "det" = a detection overlapping the true plate box
     (IoU >= 0.3). "raw" = OCR string exactly equals the truth. "fixed" =
     best grammar-corrected plate equals the truth. "top5" = truth is among
     the ranked candidates. Rates are over ALL scenes (a missed detection
     counts as a wrong read).

  B. OCR-ONLY on ground-truth plate crops, per plate height, which isolates
     the recogniser + two-line handling + grammar from the detector. Also
     reports each read hypothesis alone (full crop / strip-trimmed / two-line
     split) so the value of the two-line split is visible.

Synthetic plates are far easier than real CCTV; see prahari/anpr/synth.py.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from prahari.anpr.pipeline import PipelineConfig, PlatePipeline, split_two_line, trim_blue_strip
from prahari.anpr.synth import make_scene
from prahari.common.contracts import FrameSample
from prahari.common.diskguard import DATA
from prahari.common.plate_grammar import constrained_decode


def _iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union else 0.0


def end_to_end(pl: PlatePipeline, n: int, seed: int = 101) -> dict:
    out = {}
    layouts = [("1L", False, "car"), ("2L-car", True, "car"), ("2L-bike", True, "bike")]
    for width in (640, 960, 1280):
        for name, two, veh in layouts:
            rng = random.Random(seed + width + len(name))
            c = defaultdict(int)
            for i in range(n):
                s = make_scene(rng, width=width, two_line=two, vehicle=veh)
                fs = FrameSample("synth", 0, i / 10, 1.7e9 + i / 10, s.image,
                                 s.image.shape[1], s.image.shape[0])
                evs = [e for e in pl.process(fs) if _iou(e.bbox, s.bbox) >= 0.3]
                c["n"] += 1
                if not evs:
                    continue
                e = max(evs, key=lambda e: e.det_conf)
                c["det"] += 1
                c["raw"] += e.raw_text == s.plate
                c["fixed"] += e.plate == s.plate
                c["top5"] += any(x["plate"] == s.plate for x in e.candidates)
            out[f"{width}/{name}"] = {k: (v / c["n"] if k != "n" else v) for k, v in c.items()} | {
                "n": c["n"]}
    return out


def ocr_only(pl: PlatePipeline, n: int, seed: int = 202) -> dict:
    out = {}
    for two in (False, True):
        for px in (12, 16, 20, 24, 32, 48, 64):
            rng = random.Random(seed + px + (1000 if two else 0))
            c = defaultdict(int)
            for _ in range(n):
                s = make_scene(rng, width=1280, two_line=two, plate_px=px)
                x, y, w, h = s.bbox
                crop = pl._padded_crop(s.image, x, y, x + w, y + h)
                best = pl.read_plate(crop)
                c["n"] += 1
                c["raw"] += best.raw == s.plate
                c["fixed"] += bool(best.cands) and best.cands[0].plate == s.plate
                c["top5"] += any(k.plate == s.plate for k in best.cands)
                # Each hypothesis alone.
                full = pl._ocr_batch([crop])[0][0]
                c["full_raw"] += full == s.plate
                fc = constrained_decode(full)
                c["full_fixed"] += bool(fc) and fc[0].plate == s.plate
                if two:
                    base = trim_blue_strip(crop)
                    base = crop if base is None else base
                    t, b = split_two_line(base)
                    if t is not None:
                        sp = "".join(r[0] for r in pl._ocr_batch([t, b]))
                        c["split_raw"] += sp == s.plate
                        sc = constrained_decode(sp)
                        c["split_fixed"] += bool(sc) and sc[0].plate == s.plate
                c[f"chose_{best.kind}"] += 1
            out[f"{'2L' if two else '1L'}/{px}px"] = {k: (v / c["n"] if k != "n" else v)
                                                      for k, v in c.items()}
    return out


def _table(title: str, res: dict, cols: list[str]) -> str:
    lines = [title, f"{'case':<18}" + "".join(f"{c:>12}" for c in cols)]
    for k, v in res.items():
        lines.append(f"{k:<18}" + "".join(
            f"{v.get(c, 0):>12.0%}" if c != "n" else f"{v.get(c, 0):>12d}" for c in cols))
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--ocr", default=None)
    ap.add_argument("--detector", default=None)
    ap.add_argument("--out", default=str(DATA / "anpr-test" / "eval.json"))
    a = ap.parse_args()
    cfg = PipelineConfig()
    if a.ocr:
        cfg.ocr = a.ocr
    if a.detector:
        cfg.detector = a.detector
    pl = PlatePipeline(cfg)
    e2e = end_to_end(pl, a.n)
    oo = ocr_only(pl, a.n)
    print(f"models: detector={cfg.detector} ocr={cfg.ocr}  n={a.n} per cell\n")
    print(_table("A. END-TO-END (synthetic scenes)", e2e, ["n", "det", "raw", "fixed", "top5"]))
    print()
    print(_table("B. OCR-ONLY on ground-truth crops (1280-wide scenes)", oo,
                 ["n", "raw", "fixed", "top5", "full_raw", "full_fixed", "split_raw", "split_fixed"]))
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps({"detector": cfg.detector, "ocr": cfg.ocr, "n": a.n,
                                       "end_to_end": e2e, "ocr_only": oo}, indent=1))
    print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
