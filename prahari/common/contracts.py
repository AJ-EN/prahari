"""
The data contract between PRAHARI's components. Every component builds to these
shapes and nothing else, so they can be developed in parallel and wired later.

    catalogue (/api/ingest) --> CameraInfo
    node (capture)          --> FrameSample      (in memory only, never stored)
    anpr (pipeline)         --> PlateEvent       (small, serialisable)
    registry/api            <-- PlateEvent       (stored, matched, alerted, traced)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class CameraInfo:
    id: str
    name: str = ""
    department: str = ""
    lat: float | None = None
    lon: float | None = None
    codec: str = ""                 # "h264" | "h265" | ""
    width: int | None = None
    height: int | None = None
    fps: float | None = None        # DECLARED fps. Never use for timing.
    live: bool = True
    rtsp_url: str = ""
    hls_url: str = ""
    whep_url: str = ""
    raw: dict[str, Any] = field(default_factory=dict)   # the catalogue entry, verbatim


@dataclass
class FrameSample:
    camera_id: str
    epoch: int              # increments on every reconnect / detected discontinuity
    pts_s: float            # presentation timestamp in seconds, from the stream
    ts: float               # estimated capture time, unix seconds (NOT arrival time)
    image: Any              # numpy.ndarray, BGR, uint8
    width: int
    height: int


@dataclass
class PlateEvent:
    event_id: str           # uuid4 hex
    camera_id: str
    ts: float               # unix seconds, from FrameSample.ts
    pts_s: float
    raw_text: str           # what OCR produced, normalised A-Z0-9
    plate: str | None       # best grammar-corrected plate, or None if none valid
    ocr_conf: float         # 0..1
    det_conf: float         # 0..1
    bbox: tuple[int, int, int, int]      # x, y, w, h in the sampled frame
    valid: bool             # raw_text already a valid Indian plate
    candidates: list[dict] = field(default_factory=list)  # [{plate, distance, score, edits}]
    crop_path: str | None = None   # evidence crop under data/evidence, if written

    def to_dict(self) -> dict:
        d = asdict(self)
        d["bbox"] = list(self.bbox)
        return d
