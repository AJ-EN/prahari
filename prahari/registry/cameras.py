"""
Camera registry: onboarding (catalogue sync, bulk CSV, manual), listing,
GeoJSON and health.

The catalogue schema is NOT known in advance ("GET /api/ingest is the
contract, the URL pattern is not"), so parsing is deliberately tolerant:
a camera may arrive as a flat record, with nested `location`/`stream`/`urls`
objects, with GeoJSON coordinates, with a "1280x720" resolution string, or
with stream URLs we can only recognise by their scheme. Every entry is kept
verbatim in `raw`, so nothing the catalogue said is ever lost.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from typing import Any, Iterable

from prahari.registry.db import CAMERA_SOURCES, Store, iso, jdump, jload, now
from prahari.registry.geo import valid_coord

# ---------------------------------------------------------------------------
# Tolerant parsing
# ---------------------------------------------------------------------------

LIST_KEYS = ("cameras", "streams", "items", "data", "results", "feeds", "devices",
             "camera_list", "cameraList", "records", "features")

ID_KEYS = ("id", "camera_id", "cameraId", "cam_id", "camId", "uid", "uuid", "code",
           "stream_id", "streamId", "key", "slug")
NAME_KEYS = ("name", "title", "label", "camera_name", "cameraName", "display_name",
             "displayName", "description")
DEPT_KEYS = ("department", "dept", "department_name", "departmentName", "agency",
             "owner", "org", "organisation", "organization", "authority")
LAT_KEYS = ("lat", "latitude", "Lat", "Latitude", "LAT")
LON_KEYS = ("lon", "lng", "long", "longitude", "Lon", "Lng", "Longitude", "LON", "LNG")
CODEC_KEYS = ("codec", "video_codec", "videoCodec", "encoding", "compression", "vcodec")
WIDTH_KEYS = ("width", "w", "frame_width", "frameWidth")
HEIGHT_KEYS = ("height", "h", "frame_height", "frameHeight")
RES_KEYS = ("resolution", "res", "size", "frame_size")
FPS_KEYS = ("fps", "framerate", "frame_rate", "frameRate", "frames_per_second")
LIVE_KEYS = ("live", "is_live", "isLive", "online", "active", "enabled")
RTSP_KEYS = ("rtsp_url", "rtsp", "rtspUrl", "rtsp_uri")
HLS_KEYS = ("hls_url", "hls", "hlsUrl", "m3u8")
WHEP_KEYS = ("whep_url", "whep", "whepUrl", "webrtc", "webrtc_url", "webrtcUrl")
GENERIC_URL_KEYS = ("url", "stream_url", "streamUrl", "uri", "src", "source_url")

NESTED_LOC = ("location", "loc", "geo", "position", "coordinates", "coords", "gps",
              "geometry", "point", "latlng", "latLng")
NESTED_STREAM = ("stream", "video", "media", "specs", "properties", "meta", "metadata",
                 "config", "profile")
NESTED_URLS = ("urls", "streams", "endpoints", "links", "stream_urls", "streamUrls",
               "sources")

_RES_RE = re.compile(r"(\d{2,5})\s*[x×X*]\s*(\d{2,5})")
_TRUE = {"1", "true", "yes", "y", "on", "live", "online", "active", "enabled", "up"}
_FALSE = {"0", "false", "no", "n", "off", "offline", "inactive", "disabled", "down", "dead"}


def extract_camera_list(payload: Any) -> list[dict]:
    """Find the list of camera records in an arbitrary catalogue payload."""
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for k in LIST_KEYS:
        v = payload.get(k)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
        if isinstance(v, dict):
            inner = extract_camera_list(v)
            if inner:
                return inner
    # A single camera record?
    if any(k in payload for k in ID_KEYS) and (
            any(k in payload for k in RTSP_KEYS + NAME_KEYS + LAT_KEYS)):
        return [payload]
    # A mapping id -> record, e.g. {"cam1": {...}, "cam2": {...}}
    if payload and all(isinstance(v, dict) for v in payload.values()):
        out = []
        for k, v in payload.items():
            rec = dict(v)
            if not any(key in rec for key in ID_KEYS):
                rec["id"] = k
            out.append(rec)
        return out
    return []


def _first(d: dict, keys: Iterable[str]) -> Any:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def _sub(d: dict, keys: Iterable[str]) -> list[dict]:
    out = []
    for k in keys:
        v = d.get(k)
        if isinstance(v, dict):
            out.append(v)
            # GeoJSON-ish nesting: properties/geometry inside a nested object
            for kk in ("properties", "geometry"):
                if isinstance(v.get(kk), dict):
                    out.append(v[kk])
    return out


def _num(v: Any, cast=float) -> Any:
    if v is None or v == "":
        return None
    try:
        return cast(float(v)) if cast is int else cast(v)
    except (TypeError, ValueError):
        m = re.search(r"-?\d+(\.\d+)?", str(v))
        if m:
            return cast(float(m.group(0))) if cast is int else cast(m.group(0))
        return None


def _bool(v: Any, default: bool = True) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    s = str(v).strip().lower()
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    return default


def normalise_codec(v: Any) -> str:
    s = re.sub(r"[^a-z0-9]", "", str(v or "").lower())
    if not s:
        return ""
    if s in ("h264", "avc", "avc1", "x264", "mpeg4avc") or "264" in s:
        return "h264"
    if s in ("h265", "hevc", "hvc1", "hev1", "x265") or "265" in s or "hevc" in s:
        return "h265"
    return s


def _classify_url(u: str) -> str | None:
    lu = u.lower()
    if lu.startswith(("rtsp://", "rtsps://")):
        return "rtsp"
    if ".m3u8" in lu or "/hls" in lu:
        return "hls"
    if "whep" in lu or lu.startswith(("webrtc://",)):
        return "whep"
    return None


def _scan_urls(obj: Any, found: dict[str, str], depth: int = 0) -> None:
    """Last-resort: recognise stream URLs anywhere in the record by scheme."""
    if depth > 4:
        return
    if isinstance(obj, str):
        kind = _classify_url(obj)
        if kind and kind not in found:
            found[kind] = obj
    elif isinstance(obj, dict):
        for v in obj.values():
            _scan_urls(v, found, depth + 1)
    elif isinstance(obj, list):
        for v in obj:
            _scan_urls(v, found, depth + 1)


def _coords(rec: dict) -> tuple[float | None, float | None]:
    lat = _num(_first(rec, LAT_KEYS))
    lon = _num(_first(rec, LON_KEYS))
    if lat is not None and lon is not None:
        return lat, lon
    for k in NESTED_LOC:
        v = rec.get(k)
        if isinstance(v, dict):
            if isinstance(v.get("coordinates"), list):       # GeoJSON Point
                c = v["coordinates"]
                if len(c) >= 2:
                    return _num(c[1]), _num(c[0])
            la, lo = _num(_first(v, LAT_KEYS)), _num(_first(v, LON_KEYS))
            if la is not None and lo is not None:
                return la, lo
        elif isinstance(v, (list, tuple)) and len(v) >= 2:
            a, b = _num(v[0]), _num(v[1])
            if a is not None and b is not None:
                # Ambiguous order. GeoJSON is [lon, lat]; "coordinates" and
                # "geometry" keys follow it. Otherwise assume [lat, lon]. For
                # India (lat 6-37, lon 68-98) the ranges disambiguate anyway.
                if k in ("coordinates", "geometry") or (abs(a) > 60 and abs(b) <= 60):
                    return b, a
                return a, b
        elif isinstance(v, str) and "," in v:
            parts = v.split(",")
            a, b = _num(parts[0]), _num(parts[1])
            if a is not None and b is not None:
                return (b, a) if abs(a) > 60 and abs(b) <= 60 else (a, b)
    return lat, lon


def parse_camera(rec: dict) -> dict | None:
    """Map one arbitrary catalogue record onto the CameraInfo shape.
    Returns None only when the record carries neither an id nor any way to
    derive a stable one (no name, no stream URL)."""
    if not isinstance(rec, dict):
        return None
    streams = _sub(rec, NESTED_STREAM)
    urlsets = _sub(rec, NESTED_URLS)
    layers = [rec] + streams

    def pick(keys):
        for layer in layers:
            v = _first(layer, keys)
            if v is not None:
                return v
        return None

    rtsp = pick(RTSP_KEYS)
    hls = pick(HLS_KEYS)
    whep = pick(WHEP_KEYS)
    for u in urlsets:
        rtsp = rtsp or _first(u, RTSP_KEYS)
        hls = hls or _first(u, HLS_KEYS)
        whep = whep or _first(u, WHEP_KEYS)
    generic = pick(GENERIC_URL_KEYS)
    if isinstance(generic, str):
        kind = _classify_url(generic)
        if kind == "rtsp" and not rtsp:
            rtsp = generic
        elif kind == "hls" and not hls:
            hls = generic
        elif kind == "whep" and not whep:
            whep = generic
    if not (rtsp and hls and whep):
        found: dict[str, str] = {}
        _scan_urls(rec, found)
        rtsp = rtsp or found.get("rtsp")
        hls = hls or found.get("hls")
        whep = whep or found.get("whep")

    width = _num(pick(WIDTH_KEYS), int)
    height = _num(pick(HEIGHT_KEYS), int)
    if width is None or height is None:
        res = pick(RES_KEYS)
        if isinstance(res, str) and (m := _RES_RE.search(res)):
            width, height = int(m.group(1)), int(m.group(2))
        elif isinstance(res, dict):
            width = width or _num(_first(res, WIDTH_KEYS), int)
            height = height or _num(_first(res, HEIGHT_KEYS), int)
        elif isinstance(res, (list, tuple)) and len(res) == 2:
            width, height = _num(res[0], int), _num(res[1], int)

    lat, lon = _coords(rec)
    if lat is None or lon is None:
        for s in streams:
            lat, lon = _coords(s)
            if lat is not None and lon is not None:
                break

    live_v = pick(LIVE_KEYS)
    if live_v is None and isinstance(rec.get("status"), str):
        live_v = rec["status"]
    name = pick(NAME_KEYS)
    cid = pick(ID_KEYS)
    if cid is None:
        basis = rtsp or hls or whep or name
        if not basis:
            return None
        cid = "cam-" + hashlib.sha1(str(basis).encode()).hexdigest()[:10]

    return {
        "id": str(cid).strip(),
        "name": str(name).strip() if name is not None else "",
        "department": str(pick(DEPT_KEYS) or "").strip(),
        "lat": lat if valid_coord(lat, lon) else None,
        "lon": lon if valid_coord(lat, lon) else None,
        "codec": normalise_codec(pick(CODEC_KEYS)),
        "width": width,
        "height": height,
        "fps": _num(pick(FPS_KEYS)),
        "live": _bool(live_v, True),
        "rtsp_url": str(rtsp or ""),
        "hls_url": str(hls or ""),
        "whep_url": str(whep or ""),
        "raw": rec,
    }


def parse_catalogue(payload: Any) -> tuple[list[dict], list[dict]]:
    """-> (cameras, skipped). Duplicate ids keep the last record."""
    cams: dict[str, dict] = {}
    skipped: list[dict] = []
    for i, rec in enumerate(extract_camera_list(payload)):
        cam = parse_camera(rec)
        if cam is None or not cam["id"]:
            skipped.append({"index": i, "reason": "no id, name or stream URL", "record": rec})
            continue
        cams[cam["id"]] = cam
    return list(cams.values()), skipped


def parse_csv(text: str) -> tuple[list[dict], list[dict]]:
    """Bulk CSV import: any header naming; the same aliases as the catalogue
    parser (id/camera_id, lat/latitude, lng/lon, rtsp/rtsp_url, resolution ...)."""
    text = text.lstrip("﻿")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    cams, skipped = [], []
    for i, row in enumerate(reader, start=2):              # line 1 is the header
        row = {(k or "").strip(): (v.strip() if isinstance(v, str) else v)
               for k, v in row.items() if k}
        if not any(row.values()):
            continue
        cam = parse_camera(row)
        if cam is None:
            skipped.append({"line": i, "reason": "no id, name or stream URL", "record": row})
        else:
            cams.append(cam)
    return cams, skipped


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_FIELDS = ("name", "department", "lat", "lon", "codec", "width", "height", "fps",
           "live", "rtsp_url", "hls_url", "whep_url")


def _row_to_dict(r) -> dict:
    d = dict(r)
    d["live"] = bool(d["live"])
    d["capability"] = jload(d.get("capability"), {})
    d["raw"] = jload(d.get("raw"), {})
    d["last_seen_iso"] = iso(d.get("last_seen"))
    return d


def upsert(store: Store, cams: list[dict], *, source: str,
           catalogue_url: str | None = None) -> dict:
    """Insert or update cameras. Descriptive fields come from the source;
    operational state (status, last_seen, capability) is never overwritten by
    an onboarding path — only by health updates."""
    if source not in CAMERA_SOURCES:
        raise ValueError(f"source must be one of {CAMERA_SOURCES}")
    added, updated, unchanged = [], [], []
    t = now()
    with store.tx() as c:
        for cam in cams:
            prior = c.execute("SELECT * FROM cameras WHERE id = ?", (cam["id"],)).fetchone()
            vals = {f: cam.get(f) for f in _FIELDS}
            vals["live"] = int(bool(vals["live"] if vals["live"] is not None else True))
            for f in ("name", "department", "codec", "rtsp_url", "hls_url", "whep_url"):
                vals[f] = vals[f] or ""
            raw = jdump(cam.get("raw") or {})
            if prior is None:
                c.execute(
                    "INSERT INTO cameras(id, name, department, lat, lon, codec, width, height,"
                    " fps, live, rtsp_url, hls_url, whep_url, source, status, capability, raw,"
                    " catalogue_url, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (cam["id"], *[vals[f] for f in _FIELDS], source,
                     cam.get("status") or "unknown", jdump(cam.get("capability") or {}),
                     raw, catalogue_url, t, t))
                added.append(cam["id"])
                continue
            changed = any(prior[f] != vals[f] for f in _FIELDS) or prior["raw"] != raw
            status = prior["status"]
            if status == "absent":                     # reappeared in the catalogue
                status, changed = "unknown", True
            if changed or prior["source"] != source:
                sets = ", ".join(f"{f} = ?" for f in _FIELDS)
                c.execute(
                    f"UPDATE cameras SET {sets}, source = ?, status = ?, raw = ?,"
                    " catalogue_url = COALESCE(?, catalogue_url), updated_at = ? WHERE id = ?",
                    (*[vals[f] for f in _FIELDS], source, status, raw, catalogue_url, t,
                     cam["id"]))
                updated.append(cam["id"])
            else:
                unchanged.append(cam["id"])
    return {"added": added, "updated": updated, "unchanged": unchanged}


def mark_absent(store: Store, present_ids: set[str], catalogue_url: str | None) -> list[str]:
    """The camera set can change between runs. Catalogue cameras that vanished
    are marked `absent` (not deleted: their history and events stay)."""
    with store.tx() as c:
        rows = c.execute("SELECT id FROM cameras WHERE source = 'catalogue' AND status != 'absent'"
                         " AND (catalogue_url IS ? OR catalogue_url = ?)",
                         (catalogue_url, catalogue_url)).fetchall()
        gone = [r["id"] for r in rows if r["id"] not in present_ids]
        for cid in gone:
            c.execute("UPDATE cameras SET status = 'absent', updated_at = ? WHERE id = ?",
                      (now(), cid))
    return gone


def fetch_catalogue(url: str, *, headers: dict[str, str] | None = None,
                    timeout: float = 15.0) -> Any:
    import httpx
    r = httpx.get(url, headers=headers or {}, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    try:
        return r.json()
    except ValueError:
        # Some catalogues are served as CSV; be tolerant here too.
        return {"__csv__": r.text}


def sync(store: Store, *, url: str | None = None, payload: Any = None,
         headers: dict[str, str] | None = None) -> dict:
    """Pull a catalogue (from `url`, or an inline `payload`) and upsert it."""
    if payload is None:
        if not url:
            raise ValueError("either url or payload is required")
        payload = fetch_catalogue(url, headers=headers)
    if isinstance(payload, dict) and "__csv__" in payload:
        cams, skipped = parse_csv(payload["__csv__"])
    else:
        cams, skipped = parse_catalogue(payload)
    result = upsert(store, cams, source="catalogue", catalogue_url=url)
    absent = mark_absent(store, {c["id"] for c in cams}, url) if cams else []
    return {"source": "catalogue", "url": url, "received": len(cams) + len(skipped),
            "parsed": len(cams), **result, "absent": absent,
            "skipped": skipped[:50], "without_location": [c["id"] for c in cams
                                                           if c["lat"] is None]}


def get(store: Store, camera_id: str) -> dict | None:
    with store.read() as c:
        r = c.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,)).fetchone()
    return _row_to_dict(r) if r else None


def lookup(store: Store, ids: Iterable[str]) -> dict[str, dict]:
    ids = list(set(ids))
    if not ids:
        return {}
    out = {}
    with store.read() as c:
        for i in range(0, len(ids), 500):
            chunk = ids[i:i + 500]
            q = f"SELECT * FROM cameras WHERE id IN ({','.join('?' * len(chunk))})"
            for r in c.execute(q, chunk):
                out[r["id"]] = _row_to_dict(r)
    return out


def list_cameras(store: Store, *, department: str | None = None, status: str | None = None,
                 codec: str | None = None, source: str | None = None, live: bool | None = None,
                 bbox: tuple[float, float, float, float] | None = None,
                 q: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM cameras WHERE 1=1", []
    if department:
        sql += " AND lower(department) = lower(?)"; args.append(department)
    if status:
        sql += " AND status = ?"; args.append(status)
    if codec:
        sql += " AND codec = ?"; args.append(normalise_codec(codec))
    if source:
        sql += " AND source = ?"; args.append(source)
    if live is not None:
        sql += " AND live = ?"; args.append(int(live))
    if bbox:
        min_lon, min_lat, max_lon, max_lat = bbox
        sql += " AND lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?"
        args += [min_lon, max_lon, min_lat, max_lat]
    if q:
        sql += " AND (id LIKE ? OR name LIKE ?)"; args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY department, id"
    with store.read() as c:
        return [_row_to_dict(r) for r in c.execute(sql, args)]


def delete(store: Store, camera_id: str) -> bool:
    with store.tx() as c:
        return c.execute("DELETE FROM cameras WHERE id = ?", (camera_id,)).rowcount > 0


def to_geojson(cams: list[dict]) -> dict:
    feats, skipped = [], []
    for cam in cams:
        if cam["lat"] is None or cam["lon"] is None:
            skipped.append(cam["id"])
            continue
        props = {k: cam[k] for k in ("id", "name", "department", "codec", "width", "height",
                                     "fps", "live", "status", "source", "last_seen_iso",
                                     "rtsp_url", "hls_url", "whep_url")}
        props["anpr_viable"] = cam["capability"].get("anpr_viable")
        feats.append({"type": "Feature", "id": cam["id"],
                      "geometry": {"type": "Point", "coordinates": [cam["lon"], cam["lat"]]},
                      "properties": props})
    return {"type": "FeatureCollection", "features": feats,
            "skipped_without_location": skipped}


HEALTH_STATUSES = ("online", "degraded", "offline", "unknown")


def update_health(store: Store, camera_id: str, *, status: str | None = None,
                  last_seen: float | None = None, capability: dict | None = None) -> dict | None:
    """Heartbeat / capability report from a node. Capability is MERGED, so a
    node can report measured fps now and ANPR viability later."""
    if status is not None and status not in HEALTH_STATUSES:
        raise ValueError(f"status must be one of {HEALTH_STATUSES}")
    with store.tx() as c:
        r = c.execute("SELECT status, capability FROM cameras WHERE id = ?",
                      (camera_id,)).fetchone()
        if r is None:
            return None
        cap = jload(r["capability"], {})
        if capability:
            cap.update(capability)
        c.execute("UPDATE cameras SET status = ?, last_seen = ?, capability = ?, updated_at = ?"
                  " WHERE id = ?",
                  (status or (r["status"] if r["status"] not in ("unknown", "absent")
                              else "online"),
                   last_seen if last_seen is not None else now(), jdump(cap), now(), camera_id))
    return get(store, camera_id)


def touch(store: Store, camera_id: str, ts: float) -> None:
    """An event arrived from this camera: it is demonstrably alive."""
    with store.tx() as c:
        c.execute("UPDATE cameras SET last_seen = MAX(COALESCE(last_seen, 0), ?),"
                  " status = CASE WHEN status IN ('unknown','offline') THEN 'online'"
                  " ELSE status END WHERE id = ?", (ts, camera_id))
