"""
All user-facing settings, from ONE file: `prahari.env` in the repo root.

A new user only ever needs to set INGEST_URL (and INGEST_TOKEN if the portal
requires one). Everything else has a sensible default. Environment variables
override the file. See `prahari.env.example` for every option, documented.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "prahari.env"


def _read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        out[k.strip()] = v
    return out


def _bool(v: str) -> bool:
    return v.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    ingest_url: str = ""            # catalogue: URL, or a saved JSON file (path)
    ingest_token: str = field(default="", repr=False)
    stream_user: str = ""           # Sentinel grid: registered email (RTSP/WebRTC login)
    stream_password: str = field(default="", repr=False)   # never stored or printed by PRAHARI
    ingest_cookie: str = field(default="", repr=False)     # optional session cookie for cameras.json / HLS
    rtsp_template: str = ""         # optional, e.g. rtsp://103.250.160.189:8554/stream/{id}
    host: str = "127.0.0.1"
    port: int = 8000
    db: str = ""                    # empty -> data/prahari.db
    max_cameras: int = 0            # 0 = every camera in the catalogue
    capture_mode: str = "full"      # "full" (decode, sample at TARGET_FPS) | "keyframes" (cheapest)
    target_fps: float = 2.0
    max_width: int = 1280           # plates need pixels; 1280 reads far better than 640
    anpr: bool = True
    save_evidence: bool = True
    catalogue_poll_s: float = 60.0
    dedup_mode: str = "best"        # "best" (best read per pass, ~6 s later) | "first" (instant)
    seed_sample_watchlist: bool = True
    source: str = field(default="defaults", repr=False)

    @classmethod
    def load(cls, env_file: Path = ENV_FILE) -> "Settings":
        raw = _read_env_file(env_file)
        for k in list(cls.__dataclass_fields__):
            ek = k.upper()
            if ek in os.environ:
                raw[ek] = os.environ[ek]
            elif f"PRAHARI_{ek}" in os.environ:
                raw[ek] = os.environ[f"PRAHARI_{ek}"]
        s = cls()
        for k, f in cls.__dataclass_fields__.items():
            if k == "source" or k.upper() not in raw:
                continue
            v = raw[k.upper()]
            cur = getattr(s, k)
            if isinstance(cur, bool):
                setattr(s, k, _bool(v))
            elif isinstance(cur, int):
                setattr(s, k, int(float(v)))
            elif isinstance(cur, float):
                setattr(s, k, float(v))
            else:
                setattr(s, k, v)
        # A catalogue saved as a file may be given relative to the PRAHARI folder.
        if s.ingest_url and "://" not in s.ingest_url and not os.path.isabs(s.ingest_url):
            s.ingest_url = str(ROOT / s.ingest_url)
        s.source = str(env_file) if env_file.exists() else "defaults (no prahari.env yet)"
        s.apply_to_environment()
        return s

    def apply_to_environment(self) -> None:
        """Components read a few settings from the environment; set them once here."""
        if self.ingest_token:
            os.environ["PRAHARI_INGEST_TOKEN"] = self.ingest_token
        for key, val in (("PRAHARI_STREAM_USER", self.stream_user),
                         ("PRAHARI_STREAM_PASSWORD", self.stream_password),
                         ("PRAHARI_INGEST_COOKIE", self.ingest_cookie),
                         ("PRAHARI_RTSP_TEMPLATE", self.rtsp_template)):
            if val:
                os.environ[key] = val
        if self.db:
            os.environ["PRAHARI_DB"] = self.db

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.ingest_token}"} if self.ingest_token else {}
