"""Request bodies. Responses are plain JSON documented in endpoint descriptions."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CameraIn(BaseModel):
    """A camera added by hand (the *manual* onboarding path)."""
    model_config = ConfigDict(json_schema_extra={"example": {
        "id": "AMC-NAV-014", "name": "Navrangpura crossroads (north)", "department": "Municipal",
        "lat": 23.0395, "lon": 72.5660, "codec": "h264", "width": 1920, "height": 1080,
        "fps": 25, "live": True, "rtsp_url": "rtsp://10.0.4.14:554/stream1"}})

    id: str = Field(..., min_length=1, description="Stable camera id")
    name: str = ""
    department: str = ""
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)
    codec: str = ""
    width: int | None = None
    height: int | None = None
    fps: float | None = Field(None, description="DECLARED fps; never used for timing")
    live: bool = True
    rtsp_url: str = ""
    hls_url: str = ""
    whep_url: str = ""
    capability: dict[str, Any] = Field(default_factory=dict)


class SyncIn(BaseModel):
    """Catalogue sync. Give a `url` to fetch, or an inline `payload` (for
    offline demos). The payload/URL response may be any reasonable shape."""
    model_config = ConfigDict(json_schema_extra={"example": {
        "url": "http://127.0.0.1:8090/api/ingest"}})

    url: str | None = None
    payload: Any = None
    headers: dict[str, str] | None = Field(
        None, description="Extra request headers, e.g. Authorization. Never logged.")


class HealthIn(BaseModel):
    """Heartbeat / measured-capability report from a node."""
    model_config = ConfigDict(json_schema_extra={"example": {
        "status": "online", "capability": {"measured_fps": 12.4, "anpr_viable": False,
                                           "anpr_reason": "plate < 60 px at 640x360"}}})

    status: Literal["online", "degraded", "offline", "unknown"] | None = None
    last_seen: float | None = Field(None, description="unix seconds; default now")
    capability: dict[str, Any] | None = Field(
        None, description="merged into the stored capability JSON; "
                          "`anpr_viable: false` marks the camera ANPR-unviable")


class WatchlistIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "plate": "GJ01AB1234", "category": "stolen_vehicle",
        "details": {"fir_no": "SAMPLE-FIR-0001/2026", "police_station": "Navrangpura PS",
                    "vehicle": "Maruti Swift, white"}}})

    plate: str = Field(..., min_length=1)
    category: str = Field(..., description="stolen_vehicle | wanted_person | missing_person"
                                           " | blacklisted | suspect (common synonyms accepted)")
    details: dict[str, Any] = Field(default_factory=dict)
    source: str = "manual"
    active: bool = True


class PlateEventIn(BaseModel):
    """`PlateEvent.to_dict()` from prahari.common.contracts."""
    model_config = ConfigDict(extra="allow", json_schema_extra={"example": {
        "event_id": "4f1c0a8e9b2d4c6e8a0b1c2d3e4f5a6b", "camera_id": "DEMO-04",
        "ts": 1790000000.0, "pts_s": 12.48, "raw_text": "GJ01AB1Z34", "plate": None,
        "ocr_conf": 0.71, "det_conf": 0.94, "bbox": [412, 380, 168, 44], "valid": False,
        "candidates": [{"plate": "GJ01AB1234", "distance": 0.18, "score": 0.98,
                        "edits": ["pos7 Z->2"]}], "crop_path": None}})

    event_id: str | None = None
    camera_id: str
    ts: float
    pts_s: float | None = None
    raw_text: str = ""
    plate: str | None = None
    ocr_conf: float = 0.0
    det_conf: float = 0.0
    bbox: list[int] = Field(default_factory=list)
    valid: bool | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    crop_path: str | None = None


class AckIn(BaseModel):
    note: str | None = Field(None, description="e.g. 'confirmed, PCR dispatched' or "
                                               "'false positive: GJ01AB1235'")
