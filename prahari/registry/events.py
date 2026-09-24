"""
Plate-event ingestion, watchlist screening and alerts.

    PlateEvent --store--> plate_events
               --screen--> match_watchlist(plate) ∪ match_watchlist(raw_text)
               --decide--> should_alert ? kind="alert" : kind="review"
               --publish--> live subscribers (SSE)

Ingestion is idempotent on `event_id`, because the node's store-and-forward
delivers at least once. Repeated sightings of the same watchlisted plate at
the same camera within `dedupe_s` update one alert (`hits`, `last_ts`)
instead of flooding the operator with one alert per sampled frame.
"""
from __future__ import annotations

import os
import uuid
from typing import Any

from prahari.common import plate_grammar as g
from prahari.registry import cameras as cam_mod
from prahari.registry import watchlist as wl_mod
from prahari.registry.db import Store, iso, jdump, jload, now

DEDUPE_S = float(os.environ.get("PRAHARI_ALERT_DEDUPE_S", "120"))
MAX_REVIEWS_PER_EVENT = 3


def normalise_event(ev: dict[str, Any]) -> dict[str, Any]:
    """Coerce a PlateEvent dict (see prahari.common.contracts) for storage."""
    if not ev.get("camera_id"):
        raise ValueError("camera_id is required")
    if ev.get("ts") is None:
        raise ValueError("ts is required")
    raw = g.normalise(ev.get("raw_text") or "")
    plate = g.normalise(ev.get("plate") or "") or None
    if not raw and not plate:
        raise ValueError("at least one of plate / raw_text is required")
    bbox = ev.get("bbox") or []
    return {
        "event_id": str(ev.get("event_id") or uuid.uuid4().hex),
        "camera_id": str(ev["camera_id"]),
        "ts": float(ev["ts"]),
        "pts_s": float(ev["pts_s"]) if ev.get("pts_s") is not None else None,
        "raw_text": raw,
        "plate": plate,
        "ocr_conf": float(ev.get("ocr_conf") or 0.0),
        "det_conf": float(ev.get("det_conf") or 0.0),
        "bbox": [int(x) for x in bbox][:4],
        "valid": (bool(ev["valid"]) if ev.get("valid") is not None
                  else (g.is_valid(raw) if raw else False)),
        "candidates": list(ev.get("candidates") or []),
        "crop_path": ev.get("crop_path"),
    }


def event_row(r) -> dict:
    d = dict(r)
    d["bbox"] = jload(d.get("bbox"), [])
    d["candidates"] = jload(d.get("candidates"), [])
    d["valid"] = bool(d["valid"])
    d["ts_iso"] = iso(d["ts"])
    return d


def screen(observations: list[str], watchlist: dict[str, dict]) -> list[g.WatchlistHit]:
    """Best hit per watchlist plate across every reading of the event."""
    best: dict[str, g.WatchlistHit] = {}
    for obs in observations:
        for h in g.match_watchlist(obs, watchlist):
            prior = best.get(h.watchlist_plate)
            if prior is None or h.distance < prior.distance:
                best[h.watchlist_plate] = h
    return sorted(best.values(), key=lambda h: (h.distance, h.watchlist_plate))


def ingest(store: Store, ev: dict[str, Any], *, dedupe_s: float = DEDUPE_S) -> dict:
    e = normalise_event(ev)
    with store.tx() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO plate_events(event_id, camera_id, ts, pts_s, raw_text, plate,"
            " ocr_conf, det_conf, bbox, valid, candidates, crop_path, received_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (e["event_id"], e["camera_id"], e["ts"], e["pts_s"], e["raw_text"], e["plate"],
             e["ocr_conf"], e["det_conf"], jdump(e["bbox"]), int(e["valid"]),
             jdump(e["candidates"]), e["crop_path"], now()))
        if cur.rowcount == 0:
            return {"event_id": e["event_id"], "stored": False, "duplicate": True,
                    "alerts": [], "camera_known": None}

    camera = cam_mod.get(store, e["camera_id"])
    if camera:
        cam_mod.touch(store, e["camera_id"], e["ts"])

    observations = [o for o in dict.fromkeys([e["plate"], e["raw_text"]]) if o]
    wl = wl_mod.active_dict(store)
    hits = screen(observations, wl) if wl else []
    alerting = [h for h in hits if g.should_alert(h)]
    chosen = alerting or [h for h in hits if not g.should_alert(h)][:MAX_REVIEWS_PER_EVENT]

    created, updated = [], []
    for h in chosen:
        kind = "alert" if g.should_alert(h) else "review"
        a, is_new = _record_alert(store, e, h, kind, dedupe_s)
        a = decorate(a, camera=camera, watch=h.record, event=e)
        a["explain"] = h.explain()
        (created if is_new else updated).append(a)
    return {"event_id": e["event_id"], "stored": True, "duplicate": False,
            "camera_known": camera is not None, "alerts": created, "updated_alerts": updated,
            "hits": [{"watchlist_plate": h.watchlist_plate, "distance": h.distance,
                      "decision": "alert" if g.should_alert(h) else "review"} for h in hits]}


def _record_alert(store: Store, e: dict, h: g.WatchlistHit, kind: str,
                  dedupe_s: float) -> tuple[dict, bool]:
    t = now()
    with store.tx() as c:
        prior = c.execute(
            "SELECT * FROM alerts WHERE watchlist_plate = ? AND camera_id = ? AND kind = ?"
            " AND status = 'open' AND last_ts >= ? ORDER BY id DESC LIMIT 1",
            (h.watchlist_plate, e["camera_id"], kind, e["ts"] - dedupe_s)).fetchone()
        if prior is not None and dedupe_s > 0:
            best = min(prior["distance"], h.distance)
            c.execute("UPDATE alerts SET hits = hits + 1, last_ts = MAX(last_ts, ?),"
                      " last_event_id = ?, distance = ?, score = MAX(score, ?) WHERE id = ?",
                      (e["ts"], e["event_id"], best, h.score, prior["id"]))
            c.execute("INSERT OR IGNORE INTO alert_events VALUES (?, ?)",
                      (prior["id"], e["event_id"]))
            row = c.execute("SELECT * FROM alerts WHERE id = ?", (prior["id"],)).fetchone()
            return dict(row), False
        cur = c.execute(
            "INSERT INTO alerts(event_id, watchlist_plate, observed, distance, score, via, kind,"
            " status, category, camera_id, ts, hits, last_ts, last_event_id, created)"
            " VALUES (?,?,?,?,?,?,?, 'open', ?,?,?, 1, ?,?,?)",
            (e["event_id"], h.watchlist_plate, h.observed_plate, h.distance, h.score, h.via,
             kind, h.record.get("category"), e["camera_id"], e["ts"], e["ts"], e["event_id"],
             t))
        c.execute("INSERT OR IGNORE INTO alert_events VALUES (?, ?)",
                  (cur.lastrowid, e["event_id"]))
        row = c.execute("SELECT * FROM alerts WHERE id = ?", (cur.lastrowid,)).fetchone()
        return dict(row), True


def decorate(a: dict, *, camera: dict | None = None, watch: dict | None = None,
             event: dict | None = None) -> dict:
    a = dict(a)
    a["ts_iso"] = iso(a.get("ts"))
    a["created_iso"] = iso(a.get("created"))
    a["camera"] = ({k: camera.get(k) for k in ("id", "name", "department", "lat", "lon")}
                   if camera else {"id": a.get("camera_id"), "name": None, "lat": None,
                                   "lon": None, "department": None})
    if watch is not None:
        a["watchlist"] = {"category": watch.get("category"), "details": watch.get("details")}
    if event is not None:
        a["event"] = {k: event.get(k) for k in ("raw_text", "plate", "ocr_conf", "det_conf",
                                                 "crop_path", "bbox")}
    return a


def list_alerts(store: Store, *, status: str | None = None, kind: str | None = None,
                since: float | None = None, alert_id: int | None = None,
                limit: int = 100) -> list[dict]:
    sql = ("SELECT a.*, w.details AS w_details, e.raw_text, e.plate AS e_plate, e.ocr_conf,"
           " e.det_conf, e.crop_path FROM alerts a"
           " LEFT JOIN watchlist w ON w.plate = a.watchlist_plate"
           " LEFT JOIN plate_events e ON e.event_id = a.event_id WHERE 1=1")
    args: list[Any] = []
    if status:
        sql += " AND a.status = ?"; args.append(status)
    if kind:
        sql += " AND a.kind = ?"; args.append(kind)
    if since is not None:
        sql += " AND a.ts >= ?"; args.append(since)
    if alert_id is not None:
        sql += " AND a.id = ?"; args.append(alert_id)
    sql += " ORDER BY a.id DESC LIMIT ?"; args.append(limit)
    with store.read() as c:
        rows = [dict(r) for r in c.execute(sql, args)]
    cams = cam_mod.lookup(store, [r["camera_id"] for r in rows if r["camera_id"]])
    out = []
    for r in rows:
        ev = {"raw_text": r.pop("raw_text"), "plate": r.pop("e_plate"),
              "ocr_conf": r.pop("ocr_conf"), "det_conf": r.pop("det_conf"),
              "crop_path": r.pop("crop_path")}
        details = jload(r.pop("w_details"), {})
        out.append(decorate(r, camera=cams.get(r["camera_id"]),
                            watch={"category": r.get("category"), "details": details},
                            event=ev))
    return out


def ack(store: Store, alert_id: int, *, by: str, note: str | None = None) -> dict | None:
    with store.tx() as c:
        n = c.execute("UPDATE alerts SET status = 'ack', acked_by = ?, acked_at = ?, note = ?"
                      " WHERE id = ?", (by, now(), note, alert_id)).rowcount
    if not n:
        return None
    rows = list_alerts(store, alert_id=alert_id, limit=1)
    return rows[0] if rows else None
