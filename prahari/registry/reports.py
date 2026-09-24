"""
Reports: coverage-gap analysis over the registry, and the plates CSV (a
required submission artifact: every detected plate with camera, location and
timestamp).
"""
from __future__ import annotations

import csv
import io
import math
from collections import defaultdict
from typing import Any, Iterator

import numpy as np

from prahari.common import plate_grammar as g
from prahari.registry import cameras as cam_mod
from prahari.registry.db import Store, iso, now
from prahari.registry.geo import EARTH_KM

KM_PER_DEG_LAT = 111.32
MAX_CELLS = 40_000


def _anpr_unviable(cap: dict) -> str | None:
    """Reason string if the camera's measured capability rules ANPR out."""
    if not cap:
        return None
    v = cap.get("anpr_viable", cap.get("anpr"))
    if v is False or (isinstance(v, str) and v.lower() in ("no", "false", "unviable",
                                                          "not_viable", "none")):
        return str(cap.get("anpr_reason") or cap.get("reason") or "capability: ANPR unviable")
    return None


def gap_analysis(store: Store, *, cell_km: float = 1.0, radius_km: float = 1.0,
                 stale_s: float = 600.0, list_limit: int = 500) -> dict:
    cams = cam_mod.list_cameras(store)
    t = now()
    located = [c for c in cams if c["lat"] is not None and c["lon"] is not None]

    # --- camera health -----------------------------------------------------
    offline, stale, never_seen, absent, unviable, no_stream = [], [], [], [], [], []
    for c in cams:
        brief = {"id": c["id"], "name": c["name"], "department": c["department"],
                 "status": c["status"], "last_seen": c["last_seen_iso"]}
        if c["status"] == "absent":
            absent.append(brief)
        elif c["status"] == "offline":
            offline.append(brief)
        elif c["last_seen"] is None:
            never_seen.append(brief)
        elif t - c["last_seen"] > stale_s:
            stale.append({**brief, "age_s": round(t - c["last_seen"])})
        if (reason := _anpr_unviable(c["capability"])):
            unviable.append({**brief, "reason": reason,
                             "capability": c["capability"]})
        if not (c["rtsp_url"] or c["hls_url"] or c["whep_url"]):
            no_stream.append(brief)
    down_ids = {x["id"] for x in offline + stale + never_seen + absent}

    by_dept: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for c in cams:
        d = by_dept[c["department"] or "(unassigned)"]
        d["total"] += 1
        d["located"] += int(c["lat"] is not None)
        d["healthy"] += int(c["id"] not in down_ids)
        d["offline_or_stale"] += int(c["id"] in down_ids)
        d["anpr_unviable"] += int(_anpr_unviable(c["capability"]) is not None)
        d[f"codec_{c['codec'] or 'unknown'}"] += 1

    # --- spatial coverage --------------------------------------------------
    grid: dict[str, Any] = {"cell_km": cell_km, "radius_km": radius_km, "cells": 0,
                            "covered": 0, "uncovered": 0, "coverage_pct": None,
                            "effective_coverage_pct": None, "bbox": None,
                            "uncovered_cells": [], "note": None}
    if located:
        lats = np.array([c["lat"] for c in located])
        lons = np.array([c["lon"] for c in located])
        healthy = np.array([c["id"] not in down_ids for c in located])
        min_lat, max_lat = lats.min(), lats.max()
        min_lon, max_lon = lons.min(), lons.max()
        mid = math.radians((min_lat + max_lat) / 2)
        eff_cell = cell_km
        while True:
            dlat = eff_cell / KM_PER_DEG_LAT
            dlon = eff_cell / (KM_PER_DEG_LAT * max(math.cos(mid), 0.01))
            ny = max(1, math.ceil((max_lat - min_lat) / dlat))
            nx = max(1, math.ceil((max_lon - min_lon) / dlon))
            if nx * ny <= MAX_CELLS:
                break
            eff_cell *= 1.5
        if eff_cell != cell_km:
            grid["note"] = (f"bounding box too large for {cell_km} km cells; "
                            f"coarsened to {eff_cell:.2f} km")
            grid["cell_km"] = round(eff_cell, 3)
        cy = min_lat + (np.arange(ny) + 0.5) * dlat
        cx = min_lon + (np.arange(nx) + 0.5) * dlon
        gy, gx = np.meshgrid(cy, cx, indexing="ij")
        gy, gx = gy.ravel(), gx.ravel()
        # haversine, cells x cameras
        p1, p2 = np.radians(gy)[:, None], np.radians(lats)[None, :]
        dphi = p2 - p1
        dl = np.radians(lons)[None, :] - np.radians(gx)[:, None]
        a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
        dist = 2 * EARTH_KM * np.arcsin(np.minimum(1.0, np.sqrt(a)))
        nearest = dist.min(axis=1)
        nearest_idx = dist.argmin(axis=1)
        covered = nearest <= radius_km
        if healthy.any():
            eff_covered = (np.where(healthy[None, :], dist, np.inf).min(axis=1) <= radius_km)
        else:
            eff_covered = np.zeros_like(covered)
        n = nearest.size
        grid.update({
            "bbox": [float(min_lon), float(min_lat), float(max_lon), float(max_lat)],
            "rows": int(ny), "cols": int(nx), "cells": int(n),
            "covered": int(covered.sum()), "uncovered": int((~covered).sum()),
            "coverage_pct": round(100 * covered.sum() / n, 1),
            "covered_only_by_unhealthy": int((covered & ~eff_covered).sum()),
            "effective_coverage_pct": round(100 * eff_covered.sum() / n, 1),
        })
        order = np.argsort(-nearest)                       # worst gaps first
        for i in order[: list_limit]:
            if covered[i]:
                break
            la, lo = float(gy[i]), float(gx[i])
            grid["uncovered_cells"].append({
                "center": [round(lo, 6), round(la, 6)],
                "nearest_camera_km": round(float(nearest[i]), 3),
                "nearest_camera": located[int(nearest_idx[i])]["id"],
                "polygon": [[round(lo - dlon / 2, 6), round(la - dlat / 2, 6)],
                            [round(lo + dlon / 2, 6), round(la - dlat / 2, 6)],
                            [round(lo + dlon / 2, 6), round(la + dlat / 2, 6)],
                            [round(lo - dlon / 2, 6), round(la + dlat / 2, 6)],
                            [round(lo - dlon / 2, 6), round(la - dlat / 2, 6)]],
            })
    else:
        grid["note"] = "no camera has a location; spatial coverage cannot be computed"

    return {
        "generated_at": iso(t),
        "params": {"cell_km": cell_km, "radius_km": radius_km, "stale_s": stale_s},
        "totals": {"cameras": len(cams), "located": len(located),
                   "without_location": len(cams) - len(located),
                   "healthy": len(cams) - len(down_ids), "offline": len(offline),
                   "stale": len(stale), "never_seen": len(never_seen), "absent": len(absent),
                   "anpr_unviable": len(unviable), "without_stream_url": len(no_stream)},
        "coverage": grid,
        "by_department": {k: dict(v) for k, v in sorted(by_dept.items())},
        "offline": offline, "stale": stale, "never_seen": never_seen, "absent": absent,
        "anpr_unviable": unviable,
        "without_location": [{"id": c["id"], "name": c["name"], "department": c["department"]}
                             for c in cams if c["lat"] is None],
        "without_stream_url": no_stream,
    }


def gap_markdown(r: dict) -> str:
    t, cov = r["totals"], r["coverage"]
    L = [f"# PRAHARI coverage gap report", "",
         f"Generated {r['generated_at']}. Grid cell {cov['cell_km']} km, "
         f"coverage radius {r['params']['radius_km']} km, stale after "
         f"{int(r['params']['stale_s'])} s without a heartbeat.", "",
         "## Summary", "",
         f"- Cameras registered: **{t['cameras']}** ({t['located']} with a location, "
         f"{t['without_location']} without)",
         f"- Healthy: **{t['healthy']}** · offline {t['offline']} · stale {t['stale']} · "
         f"never seen {t['never_seen']} · absent from catalogue {t['absent']}",
         f"- ANPR-unviable (by measured capability): **{t['anpr_unviable']}**",
         f"- Without any stream URL: {t['without_stream_url']}"]
    if cov["cells"]:
        L += [f"- Spatial coverage: **{cov['coverage_pct']}%** of {cov['cells']} cells have a "
              f"camera within {r['params']['radius_km']} km; **{cov['effective_coverage_pct']}%**"
              f" counting only healthy cameras ({cov['uncovered']} uncovered cells)"]
    if cov.get("note"):
        L += [f"- Note: {cov['note']}"]
    L += ["", "## By department", "",
          "| Department | Total | Healthy | Offline/stale | ANPR-unviable | Located |",
          "|---|---:|---:|---:|---:|---:|"]
    for dept, d in r["by_department"].items():
        L.append(f"| {dept} | {d.get('total', 0)} | {d.get('healthy', 0)} | "
                 f"{d.get('offline_or_stale', 0)} | {d.get('anpr_unviable', 0)} | "
                 f"{d.get('located', 0)} |")

    def section(title: str, rows: list[dict], extra: str | None = None) -> None:
        L.extend(["", f"## {title} ({len(rows)})", ""])
        if not rows:
            L.append("None.")
            return
        for x in rows[:50]:
            tail = f" — {x[extra]}" if extra and x.get(extra) else ""
            L.append(f"- `{x['id']}` {x.get('name') or ''} ({x.get('department') or 'n/a'})"
                     f"{tail}")
        if len(rows) > 50:
            L.append(f"- … and {len(rows) - 50} more")

    section("Offline", r["offline"], "last_seen")
    section("Stale (no heartbeat recently)", r["stale"], "last_seen")
    section("Never seen by a node", r["never_seen"])
    section("Absent from latest catalogue", r["absent"])
    section("ANPR-unviable", r["anpr_unviable"], "reason")
    section("Without location (invisible on the GIS)", r["without_location"])
    L.extend(["", f"## Worst coverage gaps (top {min(20, len(cov['uncovered_cells']))})", ""])
    if not cov["uncovered_cells"]:
        L.append("None within the cameras' bounding box.")
    else:
        L += ["| Cell centre (lat, lon) | Nearest camera | Distance km |", "|---|---|---:|"]
        for cell in cov["uncovered_cells"][:20]:
            lo, la = cell["center"]
            L.append(f"| {la:.4f}, {lo:.4f} | `{cell['nearest_camera']}` | "
                     f"{cell['nearest_camera_km']} |")
    return "\n".join(L) + "\n"


PLATES_CSV_COLUMNS = ["event_id", "timestamp_ist", "ts_unix", "camera_id", "camera_name",
                      "department", "lat", "lon", "plate", "raw_text", "grammar_valid",
                      "state", "rto_district", "ocr_conf", "det_conf", "watchlist_match",
                      "watchlist_category", "alert_kind", "crop_path"]


def plates_csv(store: Store, *, t_from: float | None = None, t_to: float | None = None,
               camera: str | None = None) -> Iterator[str]:
    """Stream the plates report as CSV lines."""
    sql = ("SELECT e.*, c.name AS camera_name, c.department, c.lat, c.lon,"
           " (SELECT a.watchlist_plate || '|' || COALESCE(a.category,'') || '|' || a.kind"
           "    FROM alert_events ae JOIN alerts a ON a.id = ae.alert_id"
           "    WHERE ae.event_id = e.event_id"
           "    ORDER BY a.kind = 'alert' DESC, a.distance LIMIT 1) AS hit"
           " FROM plate_events e LEFT JOIN cameras c ON c.id = e.camera_id WHERE 1=1")
    args: list[Any] = []
    if camera:
        sql += " AND e.camera_id = ?"; args.append(camera)
    if t_from is not None:
        sql += " AND e.ts >= ?"; args.append(t_from)
    if t_to is not None:
        sql += " AND e.ts <= ?"; args.append(t_to)
    sql += " ORDER BY e.ts, e.camera_id"

    buf = io.StringIO()
    w = csv.writer(buf)

    def flush() -> str:
        s = buf.getvalue()
        buf.seek(0); buf.truncate(0)
        return s

    w.writerow(PLATES_CSV_COLUMNS)
    yield flush()
    with store.read() as c:
        for n, r in enumerate(c.execute(sql, args), start=1):
            reading = r["plate"] or r["raw_text"]
            pp = g.parse(reading)
            hit = (r["hit"] or "").split("|") if r["hit"] else ["", "", ""]
            w.writerow([r["event_id"], iso(r["ts"]), f"{r['ts']:.3f}", r["camera_id"],
                        r["camera_name"] or "", r["department"] or "",
                        "" if r["lat"] is None else r["lat"],
                        "" if r["lon"] is None else r["lon"],
                        r["plate"] or "", r["raw_text"], int(pp.valid),
                        pp.state_name or "", pp.district_name or "",
                        f"{r['ocr_conf'] or 0:.3f}", f"{r['det_conf'] or 0:.3f}",
                        hit[0], hit[1], hit[2], r["crop_path"] or ""])
            if n % 500 == 0:
                yield flush()
    yield flush()
