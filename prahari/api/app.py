"""
PRAHARI Registry API.

    .venv/bin/python -m uvicorn prahari.api.app:app --port 8000
    open http://127.0.0.1:8000/docs

The database path comes from env `PRAHARI_DB` (default data/prahari.db).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from prahari.api.bus import AlertBus
from prahari.api.models import AckIn, CameraIn, HealthIn, PlateEventIn, SyncIn, WatchlistIn
from prahari.common import diskguard
from prahari.registry import audit
from prahari.registry import cameras as cam_mod
from prahari.registry import events as ev_mod
from prahari.registry import reports
from prahari.registry import trace as trace_mod
from prahari.registry import watchlist as wl_mod
from prahari.registry.db import Store, iso, now, parse_time
from prahari.registry.geo import parse_bbox

VERSION = "0.1.0"

DESCRIPTION = """
**PRAHARI** (પ્રહરી, *sentinel*) — the centralised CCTV registry (Model 1) with GIS,
plus watchlist screening, live alerts, cross-camera trace and a tamper-evident audit log.

### Camera onboarding — three paths
1. **Catalogue sync** — `POST /api/cameras/sync` pulls a catalogue URL (e.g. the sandbox
   `GET /api/ingest`). Parsing is tolerant: a list, or `{cameras|streams|items|data: [...]}`,
   flat or nested fields (`location.lat/lng`, `stream.width`, `urls.rtsp/hls/whep`, GeoJSON
   coordinates, `"1280x720"` resolutions, URLs recognised by scheme). Cameras that vanish
   from the catalogue are marked `absent`, never silently deleted.
2. **Bulk import** — `POST /api/cameras/import` with a CSV body (`Content-Type: text/csv`);
   same column aliases as the catalogue.
3. **Manual** — `POST /api/cameras` with one camera as JSON.

### Matching principle
Plates are **never** compared by string equality. Watchlist screening, search and trace all
use the OCR-confusion distance from `prahari.common.plate_grammar` (e.g. `GJ01AB1Z34`
matches `GJ01AB1234` at distance 0.18 because Z/2 is a common OCR confusion). Hits at
distance ≤ 0.30 raise an **alert**; weaker hits (≤ 1.10) go to operator **review**.
Nothing returns empty silently: when there is no confident match, ranked near-misses are
returned.

### Shield-lite (privacy / auditability)
`GET /api/trace/{plate}`, `GET /api/watchlist/search` and plate searches on `GET /api/events`
**require** `purpose` and `case_id` query parameters (HTTP 400 without them). Every such
query, and every watchlist/registry change, is written to an append-only SHA-256
hash-chained audit log; `GET /api/audit/verify` recomputes the chain. Send the operator's
identity in the `X-Actor` header.

### Live alerts
`GET /api/alerts/stream` is a Server-Sent Events stream; each message's `data` is one alert
JSON object (`kind` is `alert` or `review`).

Times: inputs accept unix seconds or ISO 8601 (naive = IST); outputs carry unix `ts` and
`*_iso` in IST (+05:30).
"""

TAGS = [
    {"name": "cameras", "description": "The CCTV registry: onboarding, listing, GIS, health."},
    {"name": "watchlist", "description": "Watchlist CRUD, CSV import and confusion-space search."},
    {"name": "events", "description": "Plate-event ingestion (from ANPR nodes) and fuzzy search."},
    {"name": "alerts", "description": "Watchlist alerts and review items; live SSE stream."},
    {"name": "trace", "description": "Cross-camera route reconstruction for one vehicle."},
    {"name": "reports", "description": "Coverage-gap analysis and the plates CSV report."},
    {"name": "audit", "description": "Hash-chained audit log (Shield-lite)."},
    {"name": "system", "description": "Health."},
]


class Shield:
    """Purpose binding: sensitive queries must say why, and for which case."""

    def __init__(self, purpose: str | None, case_id: str | None, actor: str):
        self.purpose, self.case_id, self.actor = purpose, case_id, actor

    def require(self) -> "Shield":
        missing = [n for n, v in (("purpose", self.purpose), ("case_id", self.case_id))
                   if not (v and v.strip())]
        if missing:
            raise HTTPException(400, detail={
                "error": "purpose_binding_required",
                "missing": missing,
                "message": "This query touches personal movement data. State a purpose and a "
                           "case_id (e.g. ?purpose=stolen+vehicle+recovery&case_id=FIR-123/2026)"
                           ". The query will be recorded in the audit log."})
        return self


def _shield_params(
    purpose: str | None = Query(None, description="Why this query is being run (required)"),
    case_id: str | None = Query(None, description="Case / FIR / diary reference (required)"),
    x_actor: str | None = Header(None, description="Operator identity for the audit log"),
) -> Shield:
    return Shield(purpose, case_id, x_actor or "anonymous")


def require_shield(s: Shield = Depends(_shield_params)) -> Shield:
    return s.require()


def actor_of(x_actor: str | None = Header(None, description="Operator identity for the audit log")
             ) -> str:
    return x_actor or "anonymous"


def _time(v: str | None, name: str) -> float | None:
    try:
        return parse_time(v)
    except ValueError:
        raise HTTPException(400, detail=f"{name}: expected unix seconds or ISO 8601, got {v!r}")


def create_app(db_path: str | Path | None = None) -> FastAPI:
    app = FastAPI(title="PRAHARI Registry API", version=VERSION, description=DESCRIPTION,
                  openapi_tags=TAGS)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"])
    bus = AlertBus()
    state: dict[str, Any] = {}

    def store() -> Store:
        if "store" not in state:
            state["store"] = Store(db_path)
        return state["store"]

    app.state.bus = bus
    app.state.get_store = store

    @app.exception_handler(ValueError)
    async def _value_error(_: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    def log(actor: str, action: str, params: dict | None = None, shield: Shield | None = None):
        audit.append(store(), actor=actor, action=action,
                     purpose=shield.purpose if shield else None,
                     case_id=shield.case_id if shield else None, params=params or {})

    # ------------------------------------------------------------------ system
    @app.get("/api/health", tags=["system"], summary="Service health and database stats")
    def health():
        s = store()
        return {"status": "ok", "version": VERSION, "time": iso(now()), "db": str(s.path),
                "db_bytes": s.size_bytes(), "counts": s.counts(),
                "disk_free_mb": diskguard.free_bytes() // (1024 * 1024),
                "disk_ok": diskguard.can_write(), "live_subscribers": bus.subscribers}

    # ----------------------------------------------------------------- cameras
    @app.get("/api/cameras", tags=["cameras"], summary="List / filter cameras")
    def list_cameras(
        department: str | None = Query(None, description="case-insensitive exact match"),
        status: str | None = Query(None, description="online | degraded | offline | unknown | absent"),
        codec: str | None = Query(None, description="h264 | h265 (aliases like hevc accepted)"),
        source: str | None = Query(None, description="catalogue | manual | bulk | api"),
        live: bool | None = None,
        bbox: str | None = Query(None, description="minLon,minLat,maxLon,maxLat"),
        q: str | None = Query(None, description="substring of id or name"),
    ):
        """Every registered camera with location, stream URLs, onboarding source, health
        status, last heartbeat and measured capability JSON."""
        box = parse_bbox(bbox) if bbox else None
        cams = cam_mod.list_cameras(store(), department=department, status=status, codec=codec,
                                    source=source, live=live, bbox=box, q=q)
        return {"count": len(cams), "cameras": cams}

    @app.get("/api/cameras.geojson", tags=["cameras"], summary="Cameras as GeoJSON (GIS layer)",
             response_class=JSONResponse)
    def cameras_geojson(department: str | None = None, status: str | None = None,
                        codec: str | None = None, bbox: str | None = None):
        """RFC 7946 FeatureCollection of camera Points (`[lon, lat]`) for MapLibre/Leaflet/QGIS.
        Cameras without a location are listed in `skipped_without_location`."""
        box = parse_bbox(bbox) if bbox else None
        cams = cam_mod.list_cameras(store(), department=department, status=status,
                                    codec=codec, bbox=box)
        return JSONResponse(cam_mod.to_geojson(cams), media_type="application/geo+json")

    @app.post("/api/cameras", tags=["cameras"], status_code=201,
              summary="Onboarding path 3: add or update one camera manually")
    def add_camera(cam: CameraIn, actor: str = Depends(actor_of)):
        d = cam.model_dump()
        cap = d.pop("capability")
        d["raw"] = cam.model_dump(exclude={"capability"})
        res = cam_mod.upsert(store(), [d], source="manual")
        if cap:
            cam_mod.update_health(store(), cam.id, capability=cap,
                                  status=None, last_seen=None)
        log(actor, "camera.manual_add", {"id": cam.id})
        return {**res, "camera": cam_mod.get(store(), cam.id)}

    @app.post("/api/cameras/sync", tags=["cameras"],
              summary="Onboarding path 1: sync from a catalogue URL")
    def sync_catalogue(body: SyncIn, actor: str = Depends(actor_of)):
        """Fetches `url` (or uses inline `payload`), parses it tolerantly and upserts every
        camera with `source=catalogue`. Returns added / updated / unchanged ids, records that
        could not be parsed (`skipped`, with the reason), cameras without a location, and
        catalogue cameras no longer present (`absent`)."""
        if not body.url and body.payload is None:
            raise HTTPException(400, detail="give either url or payload")
        try:
            res = cam_mod.sync(store(), url=body.url, payload=body.payload, headers=body.headers)
        except httpx.HTTPError as ex:
            raise HTTPException(502, detail=f"catalogue fetch failed: {ex!r}")
        log(actor, "camera.catalogue_sync", {"url": body.url, "parsed": res["parsed"],
                                             "added": len(res["added"])})
        return res

    @app.post("/api/cameras/import", tags=["cameras"],
              summary="Onboarding path 2: bulk import (CSV body)",
              openapi_extra={"requestBody": {"required": True, "content": {
                  "text/csv": {"schema": {"type": "string"}, "example":
                               "camera_id,name,department,latitude,longitude,codec,resolution,"
                               "fps,rtsp\nPS-01,Sector 7 gate,Police,23.2156,72.6369,H.264,"
                               "1280x720,25,rtsp://10.1.1.5:554/live\n"},
                  "application/json": {"schema": {"type": "array", "items": {"type": "object"}}}}}})
    async def import_cameras(request: Request, actor: str = Depends(actor_of)):
        """Send the CSV as the raw request body (`Content-Type: text/csv`; `python-multipart`
        is not installed, so multipart upload is not supported). Headers are matched with the
        same aliases as catalogue sync (`id`/`camera_id`, `lat`/`latitude`, `lng`/`lon`,
        `rtsp`/`rtsp_url`, `resolution` like `1280x720`, ...). A JSON array body also works.
        Example: `curl -X POST --data-binary @cams.csv -H 'Content-Type: text/csv' .../api/cameras/import`"""
        body = (await request.body()).decode("utf-8-sig", errors="replace")
        ctype = request.headers.get("content-type", "")
        if "json" in ctype:
            cams, skipped = cam_mod.parse_catalogue(json.loads(body))
        else:
            cams, skipped = cam_mod.parse_csv(body)
        res = await run_in_threadpool(cam_mod.upsert, store(), cams, source="bulk")
        await run_in_threadpool(log, actor, "camera.bulk_import",
                                {"rows": len(cams), "added": len(res["added"])})
        return {"source": "bulk", "parsed": len(cams), **res, "skipped": skipped,
                "without_location": [c["id"] for c in cams if c["lat"] is None]}

    @app.get("/api/cameras/{camera_id}", tags=["cameras"], summary="One camera")
    def get_camera(camera_id: str):
        cam = cam_mod.get(store(), camera_id)
        if not cam:
            raise HTTPException(404, detail="camera not found")
        return cam

    @app.delete("/api/cameras/{camera_id}", tags=["cameras"], summary="Remove a camera")
    def delete_camera(camera_id: str, actor: str = Depends(actor_of)):
        """Removes the registry entry. Its plate events are kept (evidence)."""
        if not cam_mod.delete(store(), camera_id):
            raise HTTPException(404, detail="camera not found")
        log(actor, "camera.delete", {"id": camera_id})
        return {"deleted": camera_id}

    @app.post("/api/cameras/{camera_id}/health", tags=["cameras"],
              summary="Heartbeat / measured capability from a node")
    def camera_health(camera_id: str, body: HealthIn):
        """Updates status and `last_seen` (default: now) and MERGES `capability`. Nodes report
        measured facts here (real fps, plate pixel width, `anpr_viable`), which drive the gap
        report."""
        cam = cam_mod.update_health(store(), camera_id, status=body.status,
                                    last_seen=body.last_seen, capability=body.capability)
        if not cam:
            raise HTTPException(404, detail="camera not found")
        return cam

    # --------------------------------------------------------------- watchlist
    @app.get("/api/watchlist", tags=["watchlist"], summary="List watchlist entries")
    def list_watchlist(category: str | None = None,
                       active: bool | None = Query(True, description="omit filter with active=")):
        rows = wl_mod.list_entries(store(), category=category, active=active)
        return {"count": len(rows), "entries": rows}

    @app.post("/api/watchlist", tags=["watchlist"], status_code=201,
              summary="Add or update a watchlist entry")
    def add_watchlist(body: WatchlistIn, actor: str = Depends(actor_of)):
        """The plate is normalised (`GJ-01-AB-1234` → `GJ01AB1234`). Plates that fail the Indian
        plate grammar are still accepted (vanity / foreign / damaged plates exist) and the
        response's `grammar.reasons` says why."""
        e = wl_mod.add(store(), body.plate, body.category, details=body.details,
                       source=body.source, active=body.active)
        log(actor, "watchlist.add", {"plate": e["plate"], "category": e["category"]})
        return e

    @app.post("/api/watchlist/import", tags=["watchlist"], summary="Bulk import (CSV body)",
              openapi_extra={"requestBody": {"required": True, "content": {"text/csv": {
                  "schema": {"type": "string"},
                  "example": "plate,category,fir_no,police_station,vehicle\n"
                             "GJ01AB1234,stolen_vehicle,SAMPLE-1/2026,Navrangpura,Swift white\n"}}}})
    async def import_watchlist(request: Request, actor: str = Depends(actor_of)):
        """Columns `plate` and `category` are required; every other column is kept in
        `details`. Send as the raw body with `Content-Type: text/csv`."""
        body = (await request.body()).decode("utf-8-sig", errors="replace")
        res = await run_in_threadpool(wl_mod.import_csv, store(), body)
        await run_in_threadpool(log, actor, "watchlist.import", {"imported": res["imported"]})
        return res

    @app.get("/api/watchlist/search", tags=["watchlist"],
             summary="Rank watchlist entries against an observed plate (purpose-bound)")
    def search_watchlist(plate: str = Query(..., description="observed / partial / misread plate"),
                         top_k: int = Query(10, ge=1, le=100),
                         shield: Shield = Depends(require_shield)):
        """Confusion-space lookup: returns ranked hits with distance, `decision`
        (`alert`/`review`), the explanation, and grammar repairs for invalid reads."""
        res = wl_mod.search(store(), plate, top_k=top_k)
        log(shield.actor, "watchlist.search", {"plate": plate, "hits": len(res["hits"])}, shield)
        return res

    @app.get("/api/watchlist/{plate}", tags=["watchlist"], summary="One watchlist entry")
    def get_watchlist(plate: str):
        e = wl_mod.get(store(), plate)
        if not e:
            raise HTTPException(404, detail="not on the watchlist")
        return e

    @app.delete("/api/watchlist/{plate}", tags=["watchlist"], summary="Deactivate an entry")
    def delete_watchlist(plate: str, actor: str = Depends(actor_of)):
        """Soft delete (`active=false`): the entry and its past alerts remain for audit."""
        if not wl_mod.deactivate(store(), plate):
            raise HTTPException(404, detail="not on the watchlist")
        log(actor, "watchlist.deactivate", {"plate": plate})
        return {"deactivated": plate}

    # ------------------------------------------------------------------ events
    def _ingest(ev: dict) -> dict:
        if not diskguard.can_write():
            raise HTTPException(507, detail="disk below safety floor; event not stored")
        res = ev_mod.ingest(store(), ev)
        for a in res["alerts"]:
            bus.publish(a)
        return res

    @app.post("/api/events/plate", tags=["events"], summary="Ingest one PlateEvent")
    def ingest_plate(ev: PlateEventIn):
        """Body is `PlateEvent.to_dict()`. The event is stored (idempotent on `event_id`),
        screened against the active watchlist on both `plate` and `raw_text`, and any hit
        becomes an `alert` (distance ≤ 0.30) or a `review` item, pushed live to
        `/api/alerts/stream`. Repeat sightings at the same camera within 120 s update the
        existing alert (`hits`) instead of creating new ones."""
        return _ingest(ev.model_dump())

    @app.post("/api/events/batch", tags=["events"], summary="Ingest a batch of PlateEvents")
    def ingest_batch(evs: list[PlateEventIn]):
        """For store-and-forward flushes from a node. Same semantics as `/api/events/plate`."""
        out = [_ingest(e.model_dump()) for e in evs]
        return {"received": len(evs), "stored": sum(r["stored"] for r in out),
                "duplicates": sum(r["duplicate"] for r in out),
                "alerts": [a for r in out for a in r["alerts"]]}

    @app.get("/api/events", tags=["events"], summary="Search plate events (fuzzy)")
    def search_events(
        plate: str | None = Query(None, description="fuzzy: confusion distance, not equality"),
        camera: str | None = None,
        from_: str | None = Query(None, alias="from", description="unix s or ISO 8601"),
        to: str | None = Query(None, description="unix s or ISO 8601"),
        max_distance: float = Query(trace_mod.SEARCH_MAX_DISTANCE, ge=0, le=3),
        limit: int = Query(200, ge=1, le=5000),
        shield: Shield = Depends(_shield_params),
    ):
        """Without `plate`: latest events (optionally by camera / time). With `plate`: the
        query is **purpose-bound** (`purpose` + `case_id` required, audited) and returns events
        whose plate, raw OCR text or ANPR candidates lie within `max_distance`, each with its
        match distance, plus ranked `near_misses` so an empty result is never silent."""
        t_from, t_to = _time(from_, "from"), _time(to, "to")
        if plate:
            shield.require()
        res = trace_mod.search(store(), plate=plate, camera=camera, t_from=t_from, t_to=t_to,
                               max_distance=max_distance, limit=limit)
        if plate:
            log(shield.actor, "events.search", {"plate": plate, "camera": camera,
                                                "from": from_, "to": to,
                                                "results": res["count"]}, shield)
        return res

    # ------------------------------------------------------------------ alerts
    @app.get("/api/alerts", tags=["alerts"], summary="List alerts and review items")
    def list_alerts(status: str | None = Query(None, description="open | ack"),
                    kind: str | None = Query(None, description="alert | review"),
                    since: str | None = Query(None, description="unix s or ISO 8601"),
                    limit: int = Query(100, ge=1, le=1000)):
        rows = ev_mod.list_alerts(store(), status=status, kind=kind,
                                  since=_time(since, "since"), limit=limit)
        return {"count": len(rows), "alerts": rows}

    @app.post("/api/alerts/{alert_id}/ack", tags=["alerts"], summary="Acknowledge an alert")
    def ack_alert(alert_id: int, body: AckIn | None = None, actor: str = Depends(actor_of)):
        a = ev_mod.ack(store(), alert_id, by=actor, note=body.note if body else None)
        if not a:
            raise HTTPException(404, detail="alert not found")
        log(actor, "alert.ack", {"id": alert_id, "note": body.note if body else None})
        return a

    @app.get("/api/alerts/stream", tags=["alerts"], summary="Live alerts (Server-Sent Events)",
             response_class=StreamingResponse,
             responses={200: {"content": {"text/event-stream": {}}}})
    async def alert_stream(request: Request,
                           replay: int = Query(0, ge=0, le=100,
                                               description="first send the N latest open alerts"),
                           limit: int | None = Query(None, ge=1,
                                                     description="close after N messages")):
        """`const es = new EventSource('/api/alerts/stream'); es.onmessage = e =>
        JSON.parse(e.data)`. Each message is one alert object; comment keep-alives every 15 s."""
        q = bus.subscribe()
        backlog = (await run_in_threadpool(ev_mod.list_alerts, store(), status="open",
                                           limit=replay)) if replay else []

        async def gen():
            sent = 0
            try:
                yield "retry: 3000\n\n"
                for a in reversed(backlog):
                    yield f"id: {a['id']}\ndata: {json.dumps(a, default=str)}\n\n"
                    sent += 1
                    if limit and sent >= limit:
                        return
                while True:
                    try:
                        a = await asyncio.wait_for(q.get(), timeout=15)
                    except asyncio.TimeoutError:
                        if await request.is_disconnected():
                            return
                        yield ": keep-alive\n\n"
                        continue
                    yield f"id: {a['id']}\ndata: {json.dumps(a, default=str)}\n\n"
                    sent += 1
                    if limit and sent >= limit:
                        return
            finally:
                bus.unsubscribe(q)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    # ------------------------------------------------------------------- trace
    @app.get("/api/trace/{plate}", tags=["trace"],
             summary="Reconstruct a vehicle's route across cameras (purpose-bound)")
    def trace(plate: str,
              from_: str | None = Query(None, alias="from", description="unix s or ISO 8601"),
              to: str | None = Query(None, description="unix s or ISO 8601"),
              max_distance: float = Query(trace_mod.TRACE_MAX_DISTANCE, ge=0, le=3,
                                          description="confusion-distance cut-off"),
              max_speed_kmh: float = Query(trace_mod.MAX_PLAUSIBLE_KMH, gt=0),
              collapse_s: float = Query(60, ge=0, description="merge reads at one camera "
                                                              "closer than this"),
              format: str = Query("json", pattern="^(json|geojson)$"),
              shield: Shield = Depends(require_shield)):
        """Sightings of the plate (fuzzy: plate, raw OCR and candidates), ordered by time, with
        camera name/lat/lon, match distance, confidence, and for every hop the time gap,
        straight-line distance and implied speed. Hops faster than `max_speed_kmh` are
        **flagged** (`hop.plausible=false`, with a reason — misread, clock skew or cloned plate)
        and kept. `geojson` holds the route LineString and sighting Points (`format=geojson`
        returns only that). With no confident match, `status=no_confident_match` and
        `near_misses` ranks the closest readings."""
        res = trace_mod.trace(store(), plate, t_from=_time(from_, "from"), t_to=_time(to, "to"),
                              max_distance=max_distance, max_speed_kmh=max_speed_kmh,
                              collapse_s=collapse_s)
        log(shield.actor, "trace", {"plate": plate, "from": from_, "to": to,
                                    "sightings": res["summary"]["sightings"]}, shield)
        if format == "geojson":
            return JSONResponse(res["geojson"], media_type="application/geo+json")
        return res

    # ----------------------------------------------------------------- reports
    @app.get("/api/reports/gap", tags=["reports"], summary="Coverage-gap analysis",
             responses={200: {"content": {"application/json": {}, "text/markdown": {}}}})
    def gap_report(cell_km: float = Query(1.0, gt=0.05, le=50),
                   radius_km: float = Query(1.0, gt=0, le=50),
                   stale_s: float = Query(600, gt=0, description="no heartbeat for this long = stale"),
                   format: str = Query("json", pattern="^(json|md|markdown)$")):
        """Grid of ~`cell_km` cells over the cameras' bounding box: cells with no camera within
        `radius_km` (worst first, with polygons for the map), coverage % overall and counting
        only healthy cameras; offline / stale / never-seen / absent cameras; counts by
        department; cameras whose measured capability says ANPR is unviable; cameras without a
        location or stream URL. `format=md` returns a human-readable Markdown report."""
        r = reports.gap_analysis(store(), cell_km=cell_km, radius_km=radius_km, stale_s=stale_s)
        if format in ("md", "markdown"):
            return PlainTextResponse(reports.gap_markdown(r), media_type="text/markdown")
        return r

    @app.get("/api/reports/plates.csv", tags=["reports"],
             summary="Every detected plate with camera, location and timestamp (CSV)",
             response_class=StreamingResponse, responses={200: {"content": {"text/csv": {}}}})
    def plates_csv(from_: str | None = Query(None, alias="from"), to: str | None = None,
                   camera: str | None = None, actor: str = Depends(actor_of),
                   purpose: str | None = None, case_id: str | None = None):
        """Columns: event_id, timestamp_ist, ts_unix, camera_id, camera_name, department, lat,
        lon, plate, raw_text, grammar_valid, state, rto_district, ocr_conf, det_conf,
        watchlist_match, watchlist_category, alert_kind, crop_path. Export is audited."""
        t_from, t_to = _time(from_, "from"), _time(to, "to")
        audit.append(store(), actor=actor, action="report.plates_csv",
                     purpose=purpose or "report export", case_id=case_id,
                     params={"from": from_, "to": to, "camera": camera})
        return StreamingResponse(reports.plates_csv(store(), t_from=t_from, t_to=t_to,
                                                    camera=camera),
                                 media_type="text/csv",
                                 headers={"Content-Disposition":
                                          'attachment; filename="prahari_plates.csv"'})

    # ------------------------------------------------------------------- audit
    @app.get("/api/audit", tags=["audit"], summary="Recent audit entries")
    def audit_list(limit: int = Query(100, ge=1, le=5000), action: str | None = None,
                   case_id: str | None = None):
        return {"entries": audit.recent(store(), limit=limit, action=action, case_id=case_id)}

    @app.get("/api/audit/verify", tags=["audit"], summary="Recompute and verify the hash chain")
    def audit_verify():
        """`intact=false` names the first entry whose hash or link does not check out. Publish
        `head_hash` somewhere external (a report, a signed email) to also detect truncation."""
        return audit.verify(store())

    # --- web console: static UI at "/" and "/static/..." (prahari/console). No catch-all,
    # so it never shadows /api routes, including ones registered after this line.
    from prahari.console import mount_console
    mount_console(app)

    return app


app = create_app()
