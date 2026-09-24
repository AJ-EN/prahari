"""
Fuzzy plate search and cross-camera TRACE.

Lookups never use string equality. Every stored reading of an event (the
grammar-corrected `plate`, the `raw_text`, and each ANPR candidate) is compared
to the query under the OCR-confusion distance; the event's distance is the best
of those. Distances are computed once per DISTINCT string, which is what keeps
this fast: a busy grid produces many events but far fewer distinct readings.

Trace orders matched sightings by time, collapses consecutive reads at the same
camera into one visit, and checks every hop for physical plausibility using
the straight-line distance (a lower bound on road distance, so the implied
speed is a lower bound on real speed). Implausible hops are FLAGGED, not
dropped: they usually mean a misread, a clock problem, or a cloned plate —
all things an investigator needs to see.
"""
from __future__ import annotations

from typing import Any

from prahari.common import plate_grammar as g
from prahari.registry import cameras as cam_mod
from prahari.registry.db import Store, iso, jload
from prahari.registry.events import event_row
from prahari.registry.geo import haversine_km

TRACE_MAX_DISTANCE = 0.5          # generous: tracing is recall-oriented, distance is shown
SEARCH_MAX_DISTANCE = 0.5
MAX_PLAUSIBLE_KMH = 150.0
NEAR_MISS_CEILING = 3.0           # beyond this a "candidate" is noise


def _readings(row: dict) -> list[tuple[str, str]]:
    out = []
    if row.get("plate"):
        out.append(("plate", row["plate"]))
    if row.get("raw_text"):
        out.append(("raw_text", row["raw_text"]))
    for cand in jload(row.get("candidates"), []) or []:
        p = cand.get("plate") if isinstance(cand, dict) else cand
        if p:
            out.append(("candidate", g.normalise(str(p))))
    return out


def scan(store: Store, query: str, *, camera: str | None = None, t_from: float | None = None,
         t_to: float | None = None) -> tuple[list[dict], dict[str, float]]:
    """Every event in the window with its best distance to `query`.
    Returns (events, distance_by_distinct_string)."""
    q = g.normalise(query)
    sql, args = "SELECT * FROM plate_events WHERE 1=1", []
    if camera:
        sql += " AND camera_id = ?"; args.append(camera)
    if t_from is not None:
        sql += " AND ts >= ?"; args.append(t_from)
    if t_to is not None:
        sql += " AND ts <= ?"; args.append(t_to)
    sql += " ORDER BY ts"
    cache: dict[str, float] = {}
    out = []
    with store.read() as c:
        for r in c.execute(sql, args):
            row = dict(r)
            best = None
            for how, s in _readings(row):
                d = cache.get(s)
                if d is None:
                    d = cache[s] = g.confusion_distance(q, s)
                if best is None or d < best[0]:
                    best = (d, how, s)
            if best is None:
                continue
            row["match_distance"], row["matched_on"], row["matched_reading"] = best
            out.append(row)
    return out, cache


def near_misses(rows: list[dict], threshold: float, *, limit: int = 10) -> list[dict]:
    """Rank distinct readings outside the threshold: 'did you mean'. Readings
    within NEAR_MISS_CEILING come first; if there are none, the closest few
    readings are still returned, flagged `weak`, so the answer is never an
    unexplained empty list."""
    outside = [r for r in rows if r["match_distance"] > threshold]
    close = [r for r in outside if r["match_distance"] <= NEAR_MISS_CEILING]
    weak = not close
    if weak:
        dist_of = {r["matched_reading"]: r["match_distance"] for r in outside}
        keep = set(sorted(dist_of, key=lambda s: (dist_of[s], s))[:5])
        close = [r for r in outside if r["matched_reading"] in keep]
    groups: dict[str, dict] = {}
    for r in close:
        d = r["match_distance"]
        s = r["matched_reading"]
        grp = groups.setdefault(s, {"reading": s, "distance": round(d, 4),
                                    "similarity": round(g.similarity(s, r.get("_q", s)), 4),
                                    "events": 0, "cameras": set(), "first_ts": r["ts"],
                                    "last_ts": r["ts"], "example_event_id": r["event_id"]})
        grp["events"] += 1
        grp["cameras"].add(r["camera_id"])
        grp["last_ts"] = max(grp["last_ts"], r["ts"])
    out = sorted(groups.values(), key=lambda x: (x["distance"], -x["events"]))[:limit]
    for grp in out:
        grp["cameras"] = sorted(grp["cameras"])
        grp["first_ts_iso"], grp["last_ts_iso"] = iso(grp["first_ts"]), iso(grp["last_ts"])
        grp["grammar_valid"] = g.parse(grp["reading"]).valid
        grp["weak"] = weak
    return out


def _grammar(q: str) -> dict:
    pp = g.parse(q)
    info: dict[str, Any] = {"valid": pp.valid, "format": pp.format_name, "state": pp.state_name,
                            "district": pp.district_name, "reasons": list(pp.reasons)}
    if not pp.valid:
        info["did_you_mean"] = [{"plate": c.plate, "distance": c.distance,
                                 "edits": list(c.edits)} for c in g.constrained_decode(q)]
    return info


def _public_event(row: dict, cams: dict[str, dict]) -> dict:
    ev = event_row({k: v for k, v in row.items()
                    if k not in ("match_distance", "matched_on", "matched_reading", "_q")})
    cam = cams.get(row["camera_id"])
    ev["camera"] = ({"id": cam["id"], "name": cam["name"], "department": cam["department"],
                     "lat": cam["lat"], "lon": cam["lon"]} if cam else
                    {"id": row["camera_id"], "name": None, "department": None,
                     "lat": None, "lon": None})
    ev["match"] = {"distance": round(row["match_distance"], 4), "on": row["matched_on"],
                   "reading": row["matched_reading"],
                   "exact": row["match_distance"] == 0.0}
    return ev


def search(store: Store, *, plate: str | None = None, camera: str | None = None,
           t_from: float | None = None, t_to: float | None = None,
           max_distance: float = SEARCH_MAX_DISTANCE, limit: int = 200) -> dict:
    if not plate:
        sql, args = "SELECT * FROM plate_events WHERE 1=1", []
        if camera:
            sql += " AND camera_id = ?"; args.append(camera)
        if t_from is not None:
            sql += " AND ts >= ?"; args.append(t_from)
        if t_to is not None:
            sql += " AND ts <= ?"; args.append(t_to)
        sql += " ORDER BY ts DESC LIMIT ?"; args.append(limit)
        with store.read() as c:
            rows = [event_row(r) for r in c.execute(sql, args)]
        cams = cam_mod.lookup(store, [r["camera_id"] for r in rows])
        for r in rows:
            cam = cams.get(r["camera_id"])
            r["camera"] = {"id": r["camera_id"], "name": cam and cam["name"],
                           "lat": cam and cam["lat"], "lon": cam and cam["lon"]}
        return {"query": None, "count": len(rows), "events": rows}

    q = g.normalise(plate)
    rows, _ = scan(store, q, camera=camera, t_from=t_from, t_to=t_to)
    for r in rows:
        r["_q"] = q
    matched = [r for r in rows if r["match_distance"] <= max_distance]
    matched.sort(key=lambda r: (-r["ts"]))
    matched = matched[:limit]
    cams = cam_mod.lookup(store, [r["camera_id"] for r in matched])
    result = {"query": q, "max_distance": max_distance, "grammar": _grammar(q),
              "count": len(matched), "events": [_public_event(r, cams) for r in matched],
              "near_misses": near_misses(rows, max_distance)}
    if not matched:
        result["status"] = "no_confident_match"
        result["message"] = (f"No reading within confusion distance {max_distance} of {q}. "
                             "Ranked near-miss readings are listed instead."
                             if result["near_misses"] else
                             f"No readings in this window resemble {q}.")
    else:
        result["status"] = "matched"
    return result


def trace(store: Store, plate: str, *, t_from: float | None = None, t_to: float | None = None,
          max_distance: float = TRACE_MAX_DISTANCE, max_speed_kmh: float = MAX_PLAUSIBLE_KMH,
          collapse_s: float = 60.0) -> dict:
    q = g.normalise(plate)
    rows, _ = scan(store, q, t_from=t_from, t_to=t_to)
    for r in rows:
        r["_q"] = q
    matched = [r for r in rows if r["match_distance"] <= max_distance]
    cams = cam_mod.lookup(store, [r["camera_id"] for r in matched])

    # 1. collapse consecutive reads at one camera into a visit
    visits: list[dict] = []
    for r in matched:                                    # already ts-ordered
        v = visits[-1] if visits else None
        if v and v["camera_id"] == r["camera_id"] and r["ts"] - v["last_ts"] <= collapse_s:
            v["reads"].append(r)
            v["last_ts"] = r["ts"]
            continue
        visits.append({"camera_id": r["camera_id"], "first_ts": r["ts"], "last_ts": r["ts"],
                       "reads": [r]})

    # 2. describe each visit and the hop that led to it
    sightings, total_km, implausible = [], 0.0, 0
    prev = None
    for i, v in enumerate(visits):
        cam = cams.get(v["camera_id"])
        best = min(v["reads"], key=lambda r: (r["match_distance"], -(r["ocr_conf"] or 0)))
        s: dict[str, Any] = {
            "seq": i + 1,
            "camera": ({"id": cam["id"], "name": cam["name"], "department": cam["department"],
                        "lat": cam["lat"], "lon": cam["lon"]} if cam else
                       {"id": v["camera_id"], "name": None, "department": None,
                        "lat": None, "lon": None}),
            "ts": v["first_ts"], "ts_iso": iso(v["first_ts"]),
            "last_ts": v["last_ts"], "last_ts_iso": iso(v["last_ts"]),
            "dwell_s": round(v["last_ts"] - v["first_ts"], 3),
            "reads": len(v["reads"]),
            "event_ids": [r["event_id"] for r in v["reads"]],
            "observed": best["matched_reading"], "matched_on": best["matched_on"],
            "raw_text": best["raw_text"], "plate": best["plate"],
            "match_distance": round(best["match_distance"], 4),
            "similarity": round(g.similarity(q, best["matched_reading"]), 4),
            "confidence": {"ocr": max((r["ocr_conf"] or 0) for r in v["reads"]),
                           "det": max((r["det_conf"] or 0) for r in v["reads"])},
            "crop_path": best["crop_path"],
            "hop": None,
        }
        if prev is not None:
            gap = v["first_ts"] - prev["last_ts"]
            hop: dict[str, Any] = {"from_camera": prev["camera"]["id"], "gap_s": round(gap, 3),
                                   "distance_km": None, "speed_kmh": None,
                                   "plausible": True, "reason": None}
            a, b = prev["camera"], s["camera"]
            if None not in (a["lat"], a["lon"], b["lat"], b["lon"]):
                km = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
                hop["distance_km"] = round(km, 3)
                total_km += km
                if gap > 0:
                    kmh = km / (gap / 3600.0)
                    hop["speed_kmh"] = round(kmh, 1)
                    if kmh > max_speed_kmh:
                        hop["plausible"] = False
                        hop["reason"] = (f"implied straight-line speed {kmh:.0f} km/h exceeds "
                                         f"{max_speed_kmh:.0f} km/h: possible misread, clock "
                                         "skew, or cloned plate")
                elif km > 0.05:
                    hop["plausible"] = False
                    hop["reason"] = ("seen at two locations {:.2f} km apart with no time "
                                     "between them: possible cloned plate or clock skew"
                                     .format(km))
            else:
                hop["reason"] = "camera location unknown; plausibility not checked"
            if not hop["plausible"]:
                implausible += 1
            s["hop"] = hop
        sightings.append(s)
        prev = s

    coords = [[s["camera"]["lon"], s["camera"]["lat"]] for s in sightings
              if s["camera"]["lat"] is not None]
    features: list[dict] = []
    if len(coords) >= 2:
        features.append({"type": "Feature",
                         "geometry": {"type": "LineString", "coordinates": coords},
                         "properties": {"kind": "route", "plate": q,
                                        "sightings": len(sightings),
                                        "implausible_hops": implausible}})
    for s in sightings:
        if s["camera"]["lat"] is None:
            continue
        features.append({"type": "Feature",
                         "geometry": {"type": "Point",
                                      "coordinates": [s["camera"]["lon"], s["camera"]["lat"]]},
                         "properties": {"kind": "sighting", "seq": s["seq"],
                                        "camera_id": s["camera"]["id"],
                                        "camera_name": s["camera"]["name"],
                                        "ts_iso": s["ts_iso"],
                                        "match_distance": s["match_distance"],
                                        "plausible": (s["hop"] or {}).get("plausible", True)}})

    result: dict[str, Any] = {
        "query": q, "grammar": _grammar(q),
        "params": {"max_distance": max_distance, "max_speed_kmh": max_speed_kmh,
                   "collapse_s": collapse_s, "from": iso(t_from), "to": iso(t_to)},
        "summary": {
            "events_matched": len(matched), "sightings": len(sightings),
            "cameras": len({s["camera"]["id"] for s in sightings}),
            "first_seen": sightings[0]["ts_iso"] if sightings else None,
            "last_seen": sightings[-1]["ts_iso"] if sightings else None,
            "path_km": round(total_km, 3), "implausible_hops": implausible,
            "distinct_readings": sorted({s["observed"] for s in sightings}),
        },
        "sightings": sightings,
        "geojson": {"type": "FeatureCollection", "features": features},
        "near_misses": near_misses(rows, max_distance),
    }
    if sightings:
        result["status"] = "matched"
    else:
        result["status"] = "no_confident_match"
        result["message"] = (
            f"No sighting within confusion distance {max_distance} of {q}. The closest "
            "readings are ranked in near_misses (weak=true means even the best is far off); "
            "review them before concluding the vehicle was not seen."
            if result["near_misses"] else
            "No plate readings exist in this time window, so nothing can be traced.")
    return result
