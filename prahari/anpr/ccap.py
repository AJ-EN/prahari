"""
CCAP-lite: camera capability profile for ANPR.

Most city CCTV was not installed for ANPR: wrong angle, too wide a field of
view, plates a dozen pixels tall. Rather than pretend all ~50 cameras can
read plates, we measure it from the frames we actually process and say so.

Per camera we accumulate:
  frames           frames processed
  plates           plate detections (pre-dedup; one car = several)
  plate_px_median  median detected plate height in pixels (in the sampled frame)
  valid_rate       fraction of plate reads whose RAW OCR text is already a
                   grammar-valid Indian plate (no correction needed)
  corrected_rate   fraction that constrained_decode could repair into a
                   valid plate (includes the raw-valid ones)

anpr_viable heuristic (deliberately simple, all thresholds are constants
below so they can be tuned once real footage exists):
  1. enough evidence:  frames >= MIN_FRAMES and plates >= MIN_PLATES,
     otherwise viable=False with reason "insufficient data";
  2. resolution:       plate_px_median >= MIN_PLATE_PX (24). Measured on
     synthetic ground-truth crops (prahari/anpr/evaluate.py, part B),
     single-line exact-read rate vs plate height: 16px 3%, 20px 25%,
     24px 42%, 32px 97%, 48px 100%. Two-line plates need ~1.5x more:
     32px 25%, 48px 75%. Real footage will be worse, so 24px is the floor
     for "viable", not a promise of good reads;
  3. legibility:       valid_rate >= MIN_VALID_RATE. If fewer than a third of
     raw reads parse as Indian plates the camera is producing noise
     (glare, angle, motion blur, non-plate text).
Two-line plates are taller for the same character size, so the median mixes
layouts; this is a known approximation.

Notes: "plates" counts detections, not vehicles; a camera that never sees a
plate (e.g. a park) is "insufficient data", not "not viable".
"""
from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass, field

from prahari.common.contracts import PlateEvent

MIN_FRAMES = 30
MIN_PLATES = 5
MIN_PLATE_PX = 24
MIN_VALID_RATE = 0.33
_HEIGHTS_KEPT = 2000     # rolling window for the median


@dataclass
class _Stats:
    frames: int = 0
    plates: int = 0
    valid: int = 0
    corrected: int = 0
    heights: deque = field(default_factory=lambda: deque(maxlen=_HEIGHTS_KEPT))


class CameraProfiler:
    def __init__(self):
        self._s: dict[str, _Stats] = {}

    def update(self, camera_id: str, events: list[PlateEvent]) -> None:
        """Call once per processed frame with that frame's (pre-dedup) events."""
        s = self._s.setdefault(camera_id, _Stats())
        s.frames += 1
        for ev in events:
            s.plates += 1
            s.valid += 1 if ev.valid else 0
            s.corrected += 1 if ev.plate else 0
            s.heights.append(int(ev.bbox[3]))

    def profile(self, camera_id: str) -> dict:
        s = self._s.get(camera_id, _Stats())
        med = float(statistics.median(s.heights)) if s.heights else 0.0
        valid_rate = s.valid / s.plates if s.plates else 0.0
        corrected_rate = s.corrected / s.plates if s.plates else 0.0
        if s.frames < MIN_FRAMES or s.plates < MIN_PLATES:
            viable, reason = False, "insufficient data"
        elif med < MIN_PLATE_PX:
            viable, reason = False, f"plates too small ({med:.0f}px < {MIN_PLATE_PX}px)"
        elif valid_rate < MIN_VALID_RATE:
            viable, reason = False, f"reads illegible (valid_rate {valid_rate:.2f} < {MIN_VALID_RATE})"
        else:
            viable, reason = True, "ok"
        return {
            "camera_id": camera_id,
            "frames": s.frames,
            "plates": s.plates,
            "anpr_viable": viable,
            "plate_px_median": med,
            "valid_rate": round(valid_rate, 4),
            "corrected_rate": round(corrected_rate, 4),
            "reason": reason,
        }

    def profiles(self) -> list[dict]:
        return [self.profile(c) for c in sorted(self._s)]
