"""
Watchlist storage. Plates are stored normalised (A-Z0-9). Matching is NEVER
by string equality: every lookup goes through `plate_grammar.match_watchlist`,
which works in OCR-confusion space and returns ranked hits.
"""
from __future__ import annotations

import csv
import io

from prahari.common import plate_grammar as g
from prahari.registry.db import WATCHLIST_CATEGORIES, Store, iso, jdump, jload, now

CATEGORY_ALIASES = {
    "stolen": "stolen_vehicle", "stolen_vehicle": "stolen_vehicle", "theft": "stolen_vehicle",
    "vehicle_theft": "stolen_vehicle", "stolen vehicle": "stolen_vehicle",
    "wanted": "wanted_person", "wanted_person": "wanted_person", "wanted person": "wanted_person",
    "absconder": "wanted_person",
    "missing": "missing_person", "missing_person": "missing_person",
    "missing person": "missing_person", "kidnap": "missing_person",
    "blacklist": "blacklisted", "blacklisted": "blacklisted", "banned": "blacklisted",
    "suspect": "suspect", "suspicious": "suspect", "bolo": "suspect",
}


def normalise_category(cat: str | None) -> str:
    key = (cat or "").strip().lower().replace("-", "_")
    out = CATEGORY_ALIASES.get(key) or CATEGORY_ALIASES.get(key.replace("_", " "))
    if out is None:
        raise ValueError(f"unknown category {cat!r}; expected one of {WATCHLIST_CATEGORIES}")
    return out


def _row(r) -> dict:
    d = dict(r)
    d["details"] = jload(d["details"], {})
    d["active"] = bool(d["active"])
    d["added_at_iso"] = iso(d["added_at"])
    pp = g.parse(d["plate"])
    d["grammar"] = {"valid": pp.valid, "format": pp.format_name, "state": pp.state_name,
                    "district": pp.district_name, "reasons": list(pp.reasons)}
    return d


def add(store: Store, plate: str, category: str, *, details: dict | None = None,
        source: str = "manual", active: bool = True) -> dict:
    p = g.normalise(plate)
    if not p:
        raise ValueError("plate is empty after normalisation")
    cat = normalise_category(category)
    t = now()
    with store.tx() as c:
        c.execute(
            "INSERT INTO watchlist(plate, category, details, source, active, added_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)"
            " ON CONFLICT(plate) DO UPDATE SET category = excluded.category,"
            " details = excluded.details, source = excluded.source, active = excluded.active,"
            " updated_at = excluded.updated_at",
            (p, cat, jdump(details or {}), source, int(active), t, t))
    return get(store, p)


def get(store: Store, plate: str) -> dict | None:
    with store.read() as c:
        r = c.execute("SELECT * FROM watchlist WHERE plate = ?", (g.normalise(plate),)).fetchone()
    return _row(r) if r else None


def list_entries(store: Store, *, category: str | None = None,
                 active: bool | None = True) -> list[dict]:
    sql, args = "SELECT * FROM watchlist WHERE 1=1", []
    if category:
        sql += " AND category = ?"; args.append(normalise_category(category))
    if active is not None:
        sql += " AND active = ?"; args.append(int(active))
    sql += " ORDER BY category, plate"
    with store.read() as c:
        return [_row(r) for r in c.execute(sql, args)]


def deactivate(store: Store, plate: str) -> bool:
    """Soft delete: the entry stays for the audit trail and past alerts."""
    with store.tx() as c:
        return c.execute("UPDATE watchlist SET active = 0, updated_at = ? WHERE plate = ?",
                         (now(), g.normalise(plate))).rowcount > 0


def active_dict(store: Store) -> dict[str, dict]:
    """plate -> record, the shape `match_watchlist` takes."""
    with store.read() as c:
        return {r["plate"]: {"category": r["category"], "details": jload(r["details"], {}),
                             "source": r["source"]}
                for r in c.execute("SELECT plate, category, details, source FROM watchlist"
                                   " WHERE active = 1")}


def search(store: Store, observed: str, *, top_k: int = 10) -> dict:
    """Rank watchlist entries against an observed (possibly misread) plate."""
    wl = active_dict(store)
    hits = g.match_watchlist(observed, wl, top_k=top_k)
    pp = g.parse(observed)
    return {
        "observed": g.normalise(observed),
        "grammar": {"valid": pp.valid, "reasons": list(pp.reasons),
                    "state": pp.state_name, "district": pp.district_name},
        "corrections": [{"plate": cnd.plate, "distance": cnd.distance, "edits": list(cnd.edits)}
                        for cnd in g.constrained_decode(observed)] if not pp.valid else [],
        "hits": [{"watchlist_plate": h.watchlist_plate, "distance": h.distance,
                  "score": h.score, "exact": h.exact, "via": h.via, "explain": h.explain(),
                  "decision": "alert" if g.should_alert(h) else "review",
                  "category": h.record.get("category"), "details": h.record.get("details")}
                 for h in hits],
        "watchlist_size": len(wl),
    }


def import_csv(store: Store, text: str, *, source: str = "csv") -> dict:
    """Columns: plate, category, then anything else (fir_no, police_station,
    vehicle, notes, ...) which goes into `details`. A `details` column holding
    JSON is merged in too."""
    text = text.lstrip("﻿")
    reader = csv.DictReader(io.StringIO(text))
    added, errors = [], []
    for line, row in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items() if k}
        plate = row.pop("plate", "") or row.pop("vehicle_no", "") or row.pop("registration", "")
        category = row.pop("category", "") or row.pop("type", "")
        active = row.pop("active", "1").lower() not in ("0", "false", "no")
        details: dict = {}
        raw_details = row.pop("details", "")
        if raw_details:
            parsed = jload(raw_details, None)
            details.update(parsed if isinstance(parsed, dict) else {"notes": raw_details})
        details.update({k: v for k, v in row.items() if v})
        try:
            e = add(store, plate, category, details=details, source=source, active=active)
            added.append(e["plate"])
        except ValueError as ex:
            errors.append({"line": line, "error": str(ex)})
    return {"imported": len(added), "plates": added, "errors": errors}
