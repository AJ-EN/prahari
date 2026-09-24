"""Shared helpers for the registry/API tests (kept out of conftest.py so other
components' tests are unaffected)."""
from __future__ import annotations

import sys
import uuid
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

warnings.filterwarnings("ignore", message=".*httpx2.*")

from fastapi.testclient import TestClient  # noqa: E402

from prahari.api.app import create_app  # noqa: E402

SHIELD = {"purpose": "unit test", "case_id": "TEST-CASE-1"}


def make_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("PRAHARI_DB", str(tmp_path / "registry.db"))
    client = TestClient(create_app())
    client.headers["X-Actor"] = "pytest"
    return client


def plate_event(camera_id: str, ts: float, raw: str, plate: str | None = None,
                **kw) -> dict:
    """A PlateEvent.to_dict()-shaped payload."""
    d = {"event_id": uuid.uuid4().hex, "camera_id": camera_id, "ts": ts, "pts_s": 1.0,
         "raw_text": raw, "plate": plate, "ocr_conf": 0.9, "det_conf": 0.95,
         "bbox": [10, 20, 120, 40], "valid": plate is not None and plate == raw,
         "candidates": [], "crop_path": None}
    d.update(kw)
    return d


def add_cameras(client: TestClient, cams: list[tuple[str, float, float]]) -> None:
    for cid, lat, lon in cams:
        r = client.post("/api/cameras", json={"id": cid, "name": f"cam {cid}",
                                              "department": "Police", "lat": lat, "lon": lon})
        assert r.status_code == 201, r.text
