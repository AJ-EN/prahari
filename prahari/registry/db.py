"""
SQLite storage for the registry.

One file (`data/prahari.db` by default, override with env `PRAHARI_DB`), WAL
mode, schema created on first open. Every operation opens its own short-lived
connection, which is the simplest correct pattern for SQLite under a threaded
web server; WAL lets readers proceed while a writer holds the lock.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[2]
IST = timezone(timedelta(hours=5, minutes=30), "IST")

CAMERA_SOURCES = ("catalogue", "manual", "bulk", "api")
WATCHLIST_CATEGORIES = (
    "stolen_vehicle", "wanted_person", "missing_person", "blacklisted", "suspect",
)

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS cameras (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL DEFAULT '',
    department    TEXT NOT NULL DEFAULT '',
    lat           REAL,
    lon           REAL,
    codec         TEXT NOT NULL DEFAULT '',
    width         INTEGER,
    height        INTEGER,
    fps           REAL,
    live          INTEGER NOT NULL DEFAULT 1,
    rtsp_url      TEXT NOT NULL DEFAULT '',
    hls_url       TEXT NOT NULL DEFAULT '',
    whep_url      TEXT NOT NULL DEFAULT '',
    source        TEXT NOT NULL CHECK (source IN {CAMERA_SOURCES!r}),
    status        TEXT NOT NULL DEFAULT 'unknown',
    last_seen     REAL,
    capability    TEXT NOT NULL DEFAULT '{{}}',
    raw           TEXT NOT NULL DEFAULT '{{}}',
    catalogue_url TEXT,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_cameras_department ON cameras(department);
CREATE INDEX IF NOT EXISTS ix_cameras_status     ON cameras(status);

CREATE TABLE IF NOT EXISTS plate_events (
    event_id    TEXT PRIMARY KEY,
    camera_id   TEXT NOT NULL,
    ts          REAL NOT NULL,
    pts_s       REAL,
    raw_text    TEXT NOT NULL DEFAULT '',
    plate       TEXT,
    ocr_conf    REAL,
    det_conf    REAL,
    bbox        TEXT NOT NULL DEFAULT '[]',
    valid       INTEGER NOT NULL DEFAULT 0,
    candidates  TEXT NOT NULL DEFAULT '[]',
    crop_path   TEXT,
    received_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_events_plate     ON plate_events(plate);
CREATE INDEX IF NOT EXISTS ix_events_raw       ON plate_events(raw_text);
CREATE INDEX IF NOT EXISTS ix_events_camera_ts ON plate_events(camera_id, ts);
CREATE INDEX IF NOT EXISTS ix_events_ts        ON plate_events(ts);

CREATE TABLE IF NOT EXISTS watchlist (
    plate      TEXT PRIMARY KEY,
    category   TEXT NOT NULL CHECK (category IN {WATCHLIST_CATEGORIES!r}),
    details    TEXT NOT NULL DEFAULT '{{}}',
    source     TEXT NOT NULL DEFAULT 'manual',
    active     INTEGER NOT NULL DEFAULT 1,
    added_at   REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        TEXT NOT NULL,
    watchlist_plate TEXT NOT NULL,
    observed        TEXT NOT NULL,
    distance        REAL NOT NULL,
    score           REAL NOT NULL,
    via             TEXT NOT NULL DEFAULT '',
    kind            TEXT NOT NULL CHECK (kind IN ('alert', 'review')),
    status          TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'ack')),
    category        TEXT,
    camera_id       TEXT,
    ts              REAL,
    hits            INTEGER NOT NULL DEFAULT 1,
    last_ts         REAL,
    last_event_id   TEXT,
    created         REAL NOT NULL,
    acked_by        TEXT,
    acked_at        REAL,
    note            TEXT
);
CREATE INDEX IF NOT EXISTS ix_alerts_status ON alerts(status, kind);
CREATE INDEX IF NOT EXISTS ix_alerts_dedupe ON alerts(watchlist_plate, camera_id, kind, last_ts);

-- Every event folded into an alert (the first sighting and each deduplicated repeat).
CREATE TABLE IF NOT EXISTS alert_events (
    alert_id INTEGER NOT NULL,
    event_id TEXT NOT NULL,
    PRIMARY KEY (alert_id, event_id)
);
CREATE INDEX IF NOT EXISTS ix_alert_events_event ON alert_events(event_id);

CREATE TABLE IF NOT EXISTS audit_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    actor     TEXT NOT NULL,
    action    TEXT NOT NULL,
    purpose   TEXT,
    case_id   TEXT,
    params    TEXT NOT NULL DEFAULT '{{}}',
    prev_hash TEXT NOT NULL,
    hash      TEXT NOT NULL
);
-- Append-only at the database level. The hash chain is the second line of
-- defence: it still detects tampering by someone who drops these triggers.
CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
"""


def default_db_path() -> Path:
    env = os.environ.get("PRAHARI_DB")
    return Path(env) if env else ROOT / "data" / "prahari.db"


def now() -> float:
    return time.time()


def iso(ts: float | None) -> str | None:
    """Unix seconds -> ISO 8601 in IST (the operators' clock)."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, IST).isoformat(timespec="seconds")


def parse_time(value: str | float | int | None) -> float | None:
    """Accept unix seconds or ISO 8601 (naive ISO is taken as IST)."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    try:
        return float(s)
    except ValueError:
        pass
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.timestamp()


def jdump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True,
                      default=str)


def jload(s: str | None, default: Any = None) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return default


class Store:
    """Handle to the registry database. Cheap to create; holds only a path."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None,
                               check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """A write transaction. BEGIN IMMEDIATE takes the write lock up front,
        which is what keeps the audit hash chain linear under concurrency."""
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            conn.execute("COMMIT")
        finally:
            conn.close()

    def size_bytes(self) -> int:
        total = 0
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(self.path) + suffix)
            if p.exists():
                total += p.stat().st_size
        return total

    def counts(self) -> dict[str, int]:
        with self.read() as c:
            return {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    for t in ("cameras", "plate_events", "watchlist", "alerts", "audit_log")}
