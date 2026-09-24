"""
PRAHARI ANPR pipeline:  FrameSample -> [PlateEvent]

    frame --(YOLOv9-t plate detector, ONNX)--> plate boxes
          --crop + pad--> plate crop
          --build read hypotheses-->   full crop
                                       blue IND strip trimmed
                                       two-line: top/bottom split, concatenated
          --(CCT OCR, ONNX, one batch per plate)--> raw strings + per-char probs
          --normalise + constrained_decode (plate_grammar)--> ranked valid plates
          --pick the best hypothesis--> PlateEvent (+ optional evidence JPEG)

Load once, then call `process()` from ONE worker thread. A lock makes
concurrent calls safe but serialised; for parallelism run one PlatePipeline
per worker (each holds its own ONNX sessions, ~15 MB of weights).
"""
from __future__ import annotations

import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np

from prahari.anpr import models as model_registry
from prahari.common import diskguard
from prahari.common.contracts import FrameSample, PlateEvent
from prahari.common.plate_grammar import constrained_decode, is_valid, normalise


@dataclass
class PipelineConfig:
    detector: str = model_registry.DEFAULT_DETECTOR
    ocr: str = model_registry.DEFAULT_OCR
    det_conf: float = 0.30
    # ONNX Runtime providers. Measured on the M1 (bench.py): the detector is
    # ~5x faster on CoreML (3.6 ms vs 17-19 ms per frame, identical boxes),
    # while the tiny OCR model is as fast or faster on CPU. "auto" = CoreML
    # for the detector when available (disable: PRAHARI_ANPR_COREML=0).
    det_providers: Sequence[str] | str = "auto"
    ocr_providers: Sequence[str] = ("CPUExecutionProvider",)
    intra_op_threads: int = 0            # 0 = ORT default (all cores)
    pad_frac: float = 0.06               # grow the detector box before OCR
    min_plate_px: int = 6                # skip degenerate boxes
    two_line_max_aspect: float = 2.6     # w/h below this -> also try a two-line split
    try_strip_trim: bool = True
    save_evidence: bool = False
    evidence_root: Path = field(default_factory=lambda: diskguard.DATA / "evidence")
    evidence_max_bytes: int = 30_000
    evidence_max_width: int = 360
    cap_check_every: int = 100           # enforce_cap() every N writes (it walks the dir)
    download_models: bool = True


@dataclass
class _Read:
    kind: str                      # "full" | "trim" | "split"
    raw: str                       # normalised A-Z0-9
    probs: list[float]
    conf: float
    valid: bool
    cands: list
    quality: float


_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


class PlatePipeline:
    def __init__(self, config: PipelineConfig | None = None):
        import onnxruntime as ort
        from fast_plate_ocr import LicensePlateRecognizer

        self.cfg = cfg = config or PipelineConfig()
        so = ort.SessionOptions()
        if cfg.intra_op_threads:
            so.intra_op_num_threads = cfg.intra_op_threads
        so.log_severity_level = 4          # CoreML empty-output errors are expected
        det_path = model_registry.detector_path(cfg.detector, cfg.download_models)
        ocr_onnx, ocr_cfg = model_registry.ocr_paths(cfg.ocr, cfg.download_models)
        det_prov = list(_resolve_det_providers(cfg.det_providers, ort))
        self.detector = _PlateDetector(det_path, cfg.det_conf, det_prov, so)
        self.det_providers = det_prov
        so2 = ort.SessionOptions()
        if cfg.intra_op_threads:
            so2.intra_op_num_threads = cfg.intra_op_threads
        so2.log_severity_level = 3
        self.ocr = LicensePlateRecognizer(onnx_model_path=ocr_onnx, plate_config_path=ocr_cfg,
                                          providers=list(cfg.ocr_providers), sess_options=so2)
        self._ocr_rgb = self.ocr.config.image_color_mode == "rgb"
        self._pad = self.ocr.config.pad_char
        self._lock = threading.Lock()
        self._writes = 0
        self.last_timing: dict[str, float] = {}

    # ------------------------------------------------------------------ API

    def process(self, sample: FrameSample) -> list[PlateEvent]:
        img = sample.image
        if img is None or getattr(img, "size", 0) == 0:
            return []
        with self._lock:
            t0 = time.perf_counter()
            dets = self.detector.predict(img)
            t1 = time.perf_counter()
            events = []
            H, W = img.shape[:2]
            for d in dets:
                bb = d.bounding_box
                x1, y1 = max(0, int(bb.x1)), max(0, int(bb.y1))
                x2, y2 = min(W, int(bb.x2)), min(H, int(bb.y2))
                if (y2 - y1) < self.cfg.min_plate_px or (x2 - x1) < self.cfg.min_plate_px:
                    continue
                crop = self._padded_crop(img, x1, y1, x2, y2)
                best = self.read_plate(crop)
                ev = PlateEvent(
                    event_id=uuid.uuid4().hex,
                    camera_id=sample.camera_id,
                    ts=float(sample.ts),
                    pts_s=float(sample.pts_s),
                    raw_text=best.raw,
                    plate=best.cands[0].plate if best.cands else None,
                    ocr_conf=round(best.conf, 4),
                    det_conf=round(float(d.confidence), 4),
                    bbox=(x1, y1, x2 - x1, y2 - y1),
                    valid=best.valid,
                    candidates=[{"plate": c.plate, "distance": c.distance, "score": c.score,
                                 "edits": list(c.edits)} for c in best.cands],
                )
                if self.cfg.save_evidence:
                    ev.crop_path = self._save_evidence(img, ev)
                events.append(ev)
            t2 = time.perf_counter()
            self.last_timing = {"det_ms": (t1 - t0) * 1e3, "ocr_ms": (t2 - t1) * 1e3,
                                "total_ms": (t2 - t0) * 1e3, "n_plates": float(len(events))}
            return events

    def read_plate(self, crop_bgr: np.ndarray) -> _Read:
        """OCR one plate crop (BGR). Tries every applicable hypothesis in a
        single OCR batch and returns the best under grammar + confidence."""
        hyps: list[tuple[str, list[np.ndarray]]] = [("full", [crop_bgr])]
        trimmed = trim_blue_strip(crop_bgr) if self.cfg.try_strip_trim else None
        base = trimmed if trimmed is not None else crop_bgr
        if trimmed is not None:
            hyps.append(("trim", [trimmed]))
        h, w = base.shape[:2]
        if h > 0 and w / h < self.cfg.two_line_max_aspect:
            top, bottom = split_two_line(base)
            if top is not None:
                hyps.append(("split", [top, bottom]))

        flat = [im for _, ims in hyps for im in ims]
        preds = self._ocr_batch(flat)
        reads: list[_Read] = []
        i = 0
        for kind, ims in hyps:
            parts = preds[i:i + len(ims)]
            i += len(ims)
            raw = "".join(p[0] for p in parts)
            probs = [q for p in parts for q in p[1]]
            reads.append(self._score(kind, raw, probs))
        # Highest quality wins; ties go to the earlier (simpler) hypothesis.
        return max(reads, key=lambda r: (r.quality, -["full", "trim", "split"].index(r.kind)))

    # -------------------------------------------------------------- helpers

    def _padded_crop(self, img, x1, y1, x2, y2):
        H, W = img.shape[:2]
        px = int((x2 - x1) * self.cfg.pad_frac)
        py = int((y2 - y1) * self.cfg.pad_frac)
        return img[max(0, y1 - py):min(H, y2 + py), max(0, x1 - px):min(W, x2 + px)]

    def _ocr_batch(self, crops_bgr: list[np.ndarray]) -> list[tuple[str, list[float]]]:
        conv = cv2.COLOR_BGR2RGB if self._ocr_rgb else cv2.COLOR_BGR2GRAY
        ims = [cv2.cvtColor(c, conv) for c in crops_bgr]
        preds = self.ocr.run(ims, return_confidence=True, remove_pad_char=False)
        out = []
        for p in preds:
            text = p.plate
            probs = [float(x) for x in (p.char_probs if p.char_probs is not None else [])]
            keep = [(ch, pr) for ch, pr in zip(text, probs) if ch != self._pad]
            out.append((normalise("".join(ch for ch, _ in keep)), [pr for _, pr in keep]))
        return out

    @staticmethod
    def _score(kind: str, raw: str, probs: list[float]) -> _Read:
        """Grammar-aware quality of one read hypothesis.

        `raw` stays exactly what the OCR produced (-> PlateEvent.raw_text,
        and `valid` refers to it). Candidates may come from a cleaned
        variant of it:
          * a stray leading I/IN/IND picked up from the blue HSRP strip;
          * one-character deletions when the read is longer than 10 chars,
            which only happens when a two-line split duplicates a character
            at the seam (the OCR emits at most 10 per crop).
        plate_grammar.constrained_decode only substitutes, so these indel
        variants are handled here without touching the shared grammar.
        """
        conf = float(np.mean(probs)) if probs else 0.0
        variants: list[tuple[str, float]] = [(raw, 1.0)]
        for k in (3, 2, 1):
            if raw.startswith("IND"[:k]) and len(raw) - k >= 8:
                variants.append((raw[k:], 0.97))
        if len(raw) > 10:
            seen = set()
            for i in range(len(raw)):
                v = raw[:i] + raw[i + 1:]
                if v not in seen:
                    seen.add(v)
                    variants.append((v, 0.92))
        valid = is_valid(raw)
        best_q, best_cands = -1.0, []
        for text, pen in variants:
            if not text:
                continue
            cands = constrained_decode(text)
            if text == raw and valid:
                q = conf
            elif cands:
                q = conf * cands[0].score * 0.95 * pen
            else:
                q = conf * 0.2 * pen
            if q > best_q:
                best_q, best_cands = q, cands
        return _Read(kind, raw, probs, conf, valid, best_cands, max(best_q, 0.0))

    def _save_evidence(self, img: np.ndarray, ev: PlateEvent) -> str | None:
        root = Path(self.cfg.evidence_root)
        if not diskguard.can_write():
            return None
        x, y, w, h = ev.bbox
        H, W = img.shape[:2]
        cx1, cx2 = max(0, x - w), min(W, x + 2 * w)
        cy1, cy2 = max(0, y - int(2.5 * h)), min(H, y + 2 * h)
        ctx = img[cy1:cy2, cx1:cx2]
        # Mark the plate in the context crop.
        ctx = ctx.copy()
        cv2.rectangle(ctx, (x - cx1, y - cy1), (x - cx1 + w, y - cy1 + h), (0, 0, 255), 1)
        data = encode_jpeg_capped(ctx, self.cfg.evidence_max_bytes, self.cfg.evidence_max_width)
        if data is None:
            return None
        d = root / (_SAFE.sub("_", ev.camera_id).strip(".") or "unknown")
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{int(ev.ts * 1000)}_{ev.event_id[:12]}.jpg"
        p.write_bytes(data)
        self._writes += 1
        if self._writes % self.cfg.cap_check_every == 0:
            diskguard.enforce_cap(root)
        return str(p)


class _PlateDetector:
    """Thin YOLOv9 end-to-end ONNX runner using open-image-models' own pre/
    post-processing. Exists because the library swallows EVERY inference
    exception and logs a warning per frame; with the CoreML EP an empty
    detection set raises ("runtime shape has zero elements"), which on CCTV
    (mostly empty frames) floods logs. Here that one case means "no plates"
    and anything else is raised.

    CoreML caveats (measured): boxes match CPU on 59/60 synthetic frames (the
    odd one a borderline-confidence box); ORT's CoreML EP has crashed at
    interpreter exit ("recursive_mutex lock failed") in 1 of ~8 runs. Harmless
    for a long-running node, but tests pin the detector to CPU."""

    def __init__(self, path: Path, conf: float, providers, so):
        import onnxruntime as ort
        from open_image_models.detection.core.base import inspect_model_input_shape
        from open_image_models.detection.core.yolo_v9.postprocess import convert_to_detection_result
        from open_image_models.detection.core.yolo_v9.preprocess import preprocess

        self._pre, self._post = preprocess, convert_to_detection_result
        self.sess = ort.InferenceSession(str(path), providers=list(providers), sess_options=so)
        self.inp = self.sess.get_inputs()[0].name
        self.out = self.sess.get_outputs()[0].name
        self.img_size = inspect_model_input_shape(self.sess.get_inputs()[0].shape).image_size
        self.conf = conf
        self.empty_errors = 0

    def predict(self, img: np.ndarray) -> list:
        x, ratio, pad = self._pre(img, self.img_size)
        try:
            pred = self.sess.run([self.out], {self.inp: x})[0]
        except Exception as e:  # noqa: BLE001
            if "zero elements" in str(e):
                self.empty_errors += 1
                return []
            raise
        pred = np.asarray(pred)
        if pred.ndim == 3:
            pred = pred[0]
        return self._post(predictions=pred, class_labels={0: "License Plate"}, ratio=ratio,
                          padding=pad, score_threshold=self.conf)


def _resolve_det_providers(p, ort) -> Sequence[str]:
    if p != "auto":
        return p
    avail = ort.get_available_providers()
    # NVIDIA GPU (requires the onnxruntime-gpu package instead of onnxruntime).
    if "CUDAExecutionProvider" in avail and os.environ.get("PRAHARI_ANPR_CUDA", "1") != "0":
        return ("CUDAExecutionProvider", "CPUExecutionProvider")
    if os.environ.get("PRAHARI_ANPR_COREML", "1") != "0" and \
            "CoreMLExecutionProvider" in ort.get_available_providers():
        return ("CoreMLExecutionProvider", "CPUExecutionProvider")
    return ("CPUExecutionProvider",)


# ---------------------------------------------------------------- image ops

def encode_jpeg_capped(img: np.ndarray, max_bytes: int = 30_000, max_width: int = 360) -> bytes | None:
    """JPEG-encode, shrinking quality then size until it fits under max_bytes."""
    if img is None or img.size == 0:
        return None
    h, w = img.shape[:2]
    if w > max_width:
        img = cv2.resize(img, (max_width, max(1, int(h * max_width / w))), interpolation=cv2.INTER_AREA)
    for _ in range(4):
        for q in (80, 65, 50, 35):
            ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])
            if ok and len(enc) <= max_bytes:
                return enc.tobytes()
        h, w = img.shape[:2]
        img = cv2.resize(img, (max(1, int(w * 0.7)), max(1, int(h * 0.7))), interpolation=cv2.INTER_AREA)
    return None


def trim_blue_strip(crop_bgr: np.ndarray) -> np.ndarray | None:
    """Cut off the blue 'IND' strip at the left of an HSRP plate, if present.

    Looks at the left 20% of the crop for columns that are mostly saturated
    blue (HSV hue ~100-130 in OpenCV's 0-180 scale). Returns None when no
    strip is found, so callers can skip that hypothesis."""
    h, w = crop_bgr.shape[:2]
    if w < 16 or h < 6:
        return None
    zone = crop_bgr[:, : max(2, int(w * 0.2))]
    hsv = cv2.cvtColor(zone, cv2.COLOR_BGR2HSV)
    blue = (hsv[..., 0] >= 95) & (hsv[..., 0] <= 135) & (hsv[..., 1] >= 90) & (hsv[..., 2] >= 50)
    col_frac = blue.mean(axis=0)
    cols = np.where(col_frac > 0.45)[0]
    if len(cols) < max(2, int(w * 0.025)):
        return None
    cut = int(cols.max()) + 1 + max(1, int(w * 0.01))
    if cut >= w * 0.25:
        return None
    return crop_bgr[:, cut:]


def split_two_line(crop_bgr: np.ndarray) -> tuple[np.ndarray | None, np.ndarray | None]:
    """Split a two-line plate into (top, bottom) at the inter-line gap.

    The gap is the row, within the middle 30-70% band, with the least dark
    ink (after Otsu binarisation). The two halves overlap by a few percent so
    a slightly-off split does not clip characters."""
    h, w = crop_bgr.shape[:2]
    if h < 12:
        return None, None
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    _, binv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    # Ignore the outer 10% columns (border, IND strip) when profiling.
    x0, x1 = int(w * 0.1), int(w * 0.95)
    prof = binv[:, x0:x1].mean(axis=1)
    prof = np.convolve(prof, np.ones(3) / 3, mode="same")
    lo, hi = int(h * 0.3), int(h * 0.7)
    split = lo + int(np.argmin(prof[lo:hi])) if hi > lo else h // 2
    ov = max(1, int(h * 0.04))
    top = crop_bgr[: min(h, split + ov)]
    bottom = crop_bgr[max(0, split - ov):]
    if top.shape[0] < 5 or bottom.shape[0] < 5:
        return None, None
    return top, bottom
