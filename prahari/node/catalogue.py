"""
Camera catalogue: `GET /api/ingest` -> list[CameraInfo].

The catalogue is the contract; camera ids, the camera set and URLs all come from
here and nothing is hardcoded. We have not seen the real sandbox's JSON yet, so
the parser is deliberately tolerant:

  * a bare list, or an object wrapping it (cameras / streams / items / data /
    results / feeds / devices ...), or an object keyed by camera id
  * field aliases (id / camera_id / stream_id ..., lat / latitude, lon / lng /
    longitude, possibly nested under location / geo / position / coordinates;
    GeoJSON Point [lon, lat] is understood)
  * stream URLs under any key or nesting; as a last resort any string value in
    the entry that looks like an rtsp:// / .m3u8 / .../whep URL is used
  * live / status / online as bools, numbers or words
  * resolution as width+height, "1280x720", "720p", [w, h] or {w, h}
  * fps / frame_rate as numbers or "25/1"

The whole entry is kept verbatim in CameraInfo.raw.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Iterable
from urllib.parse import urlparse

import httpx

from prahari.common.contracts import CameraInfo

log = logging.getLogger("prahari.node.catalogue")

TOKEN_ENV = "PRAHARI_INGEST_TOKEN"

LIST_KEYS = ("cameras", "camera", "streams", "items", "data", "results", "feeds",
             "devices", "sources", "channels", "records", "list", "entries", "rows")

ID_KEYS = ("id", "camera_id", "cameraid", "cam_id", "camid", "stream_id", "streamid",
           "device_id", "deviceid", "channel_id", "uid", "uuid", "code", "key")
NAME_KEYS = ("name", "camera_name", "title", "label", "display_name", "description", "location_name")
DEPT_KEYS = ("department", "dept", "agency", "owner", "organisation", "organization", "org", "source_department")
LAT_KEYS = ("lat", "latitude")
LON_KEYS = ("lon", "lng", "long", "longitude")
LIVE_KEYS = ("live", "is_live", "online", "is_online", "status", "state", "active", "enabled", "available", "health")
CODEC_KEYS = ("codec", "video_codec", "vcodec", "encoding", "compression", "codec_name")
WIDTH_KEYS = ("width", "w", "resolution_width", "frame_width")
HEIGHT_KEYS = ("height", "h", "resolution_height", "frame_height")
RES_KEYS = ("resolution", "res", "size", "dimensions", "frame_size")
FPS_KEYS = ("fps", "frame_rate", "framerate", "rate", "frames_per_second", "r_frame_rate", "avg_frame_rate")
RTSP_KEYS = ("rtsp", "rtsp_url", "rtspurl", "rtsp_uri", "rtsp_stream", "rtsp_link")
HLS_KEYS = ("hls", "hls_url", "hlsurl", "m3u8", "hls_uri", "playlist")
WHEP_KEYS = ("whep", "whep_url", "whepurl", "webrtc", "webrtc_url")
GENERIC_URL_KEYS = ("url", "uri", "src", "source", "stream_url", "streamurl", "link", "href", "endpoint")

# nested containers searched (breadth-first) after the entry's top level
NESTS = ("location", "geo", "position", "coordinates", "coords", "gps", "geometry", "loc", "point",
         "urls", "endpoints", "stream", "streams", "links", "sources", "source", "video", "media",
         "meta", "metadata", "properties", "info", "details", "config", "attributes", "camera", "spec")

LIVE_TRUE = {"live", "online", "active", "up", "ok", "running", "streaming", "ready", "true", "yes",
             "on", "healthy", "available", "connected", "enabled", "1", "good", "normal"}
LIVE_FALSE = {"offline", "down", "inactive", "error", "stopped", "disabled", "dead", "unavailable",
              "false", "no", "off", "failed", "failure", "disconnected", "maintenance", "0", "unhealthy",
              "not_live", "notlive", "paused", "fault", "broken", "unknown_offline"}


def _norm(k: str) -> str:
    return re.sub(r"[\s_\-\.]", "", str(k)).lower()


def _walk(entry: dict, max_depth: int = 3) -> list[dict]:
    """The entry followed by its nested dicts, breadth-first; well-known nests first."""
    out, frontier = [entry], [entry]
    nest_rank = {_norm(n): i for i, n in enumerate(NESTS)}
    for _ in range(max_depth):
        nxt = []
        for d in frontier:
            kids = [(k, v) for k, v in d.items() if isinstance(v, dict)]
            kids.sort(key=lambda kv: nest_rank.get(_norm(kv[0]), len(nest_rank)))
            for _, v in kids:
                nxt.append(v)
        out += nxt
        frontier = nxt
    return out


def _find(entry: dict, keys: Iterable[str], depth: int = 3, skip_containers: bool = True) -> Any:
    want = [_norm(k) for k in keys]
    for d in _walk(entry, depth):
        nd = {_norm(k): v for k, v in d.items()}
        for w in want:
            if w in nd and nd[w] is not None and nd[w] != "":
                v = nd[w]
                if skip_containers and isinstance(v, dict):
                    continue
                return v
    return None


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    m = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)\s*", s)
    if m:
        den = float(m.group(2))
        return float(m.group(1)) / den if den else None
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def _int(v: Any) -> int | None:
    n = _num(v)
    return int(round(n)) if n is not None and n > 0 else None


def _codec(v: Any) -> str:
    if not v:
        return ""
    s = _norm(v)
    if s in ("h264", "avc", "avc1", "x264", "mpeg4avc", "mpeg4part10") or "264" in s or s.startswith("avc"):
        return "h264"
    if s in ("h265", "hevc", "hvc1", "hev1", "x265") or "265" in s or "hevc" in s:
        return "h265"
    return str(v).strip().lower()


def _live(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, dict):
        return _live(_find(v, ("live", "online", "status", "state", "value")))
    s = _norm(v)
    if s in LIVE_TRUE:
        return True
    if s in LIVE_FALSE:
        return False
    return True   # unknown words: assume live, the worker will find out


def _coords(entry: dict) -> tuple[float | None, float | None]:
    lat, lon = _num(_find(entry, LAT_KEYS)), _num(_find(entry, LON_KEYS))
    if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
        return lat, lon
    # list / string / GeoJSON forms
    for d in _walk(entry):
        for k, v in d.items():
            nk = _norm(k)
            if nk not in {_norm(n) for n in ("location", "geo", "position", "coordinates", "coords", "gps",
                                             "latlng", "latlon", "lnglat", "point", "geometry", "loc")}:
                continue
            geojson = isinstance(d.get("type"), str) and d.get("type", "").lower() == "point" and nk == "coordinates"
            if isinstance(v, dict) and str(v.get("type", "")).lower() == "point" and isinstance(v.get("coordinates"), list):
                v, geojson = v["coordinates"], True
            if isinstance(v, str) and "," in v:
                v = [p for p in v.split(",")]
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                a, b = _num(v[0]), _num(v[1])
                if a is None or b is None:
                    continue
                if geojson or nk == "lnglat":
                    a, b = b, a
                if -90 <= a <= 90 and -180 <= b <= 180:
                    return a, b
    return None, None


def _resolution(entry: dict) -> tuple[int | None, int | None]:
    w, h = _int(_find(entry, WIDTH_KEYS)), _int(_find(entry, HEIGHT_KEYS))
    if w and h:
        return w, h
    r = _find(entry, RES_KEYS, skip_containers=False)
    if isinstance(r, dict):
        return _int(_find(r, WIDTH_KEYS)), _int(_find(r, HEIGHT_KEYS))
    if isinstance(r, (list, tuple)) and len(r) >= 2:
        return _int(r[0]), _int(r[1])
    if isinstance(r, str):
        m = re.search(r"(\d{2,5})\s*[x×X\*,]\s*(\d{2,5})", r)
        if m:
            return int(m.group(1)), int(m.group(2))
        m = re.fullmatch(r"\s*(\d{3,4})\s*[pP]\s*", r)
        if m:
            hh = int(m.group(1))
            return int(round(hh * 16 / 9 / 2) * 2), hh
    return w, h


def _all_strings(obj: Any, depth: int = 5) -> Iterable[str]:
    if depth < 0:
        return
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _all_strings(v, depth - 1)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _all_strings(v, depth - 1)


def _urls(entry: dict) -> tuple[str, str, str]:
    def s(v: Any) -> str:
        if isinstance(v, dict):
            v = _find(v, GENERIC_URL_KEYS)
        return v.strip() if isinstance(v, str) else ""

    rtsp, hls, whep = s(_find(entry, RTSP_KEYS, skip_containers=False)), \
        s(_find(entry, HLS_KEYS, skip_containers=False)), s(_find(entry, WHEP_KEYS, skip_containers=False))
    # generic url fields, then any string anywhere in the entry, classified by shape
    candidates = [s(_find(entry, GENERIC_URL_KEYS))] + list(_all_strings(entry))
    for c in candidates:
        if not isinstance(c, str) or "://" not in c:
            continue
        lc = c.lower()
        if not rtsp and lc.startswith(("rtsp://", "rtsps://")):
            rtsp = c.strip()
        elif not hls and (".m3u8" in lc) and lc.startswith("http"):
            hls = c.strip()
        elif not whep and "whep" in lc and lc.startswith("http"):
            whep = c.strip()
    return rtsp, hls, whep


def _entries(obj: Any, depth: int = 0) -> list[tuple[str | None, dict]]:
    """Locate the list of camera entries. Returns (key_id, entry) pairs."""
    if isinstance(obj, (str, bytes, bytearray)):
        obj = json.loads(obj)
    if isinstance(obj, list):
        return [(None, e) for e in obj if isinstance(e, dict)]
    if not isinstance(obj, dict) or depth > 3:
        return []
    nk = {_norm(k): k for k in obj}
    for key in LIST_KEYS:
        k = nk.get(_norm(key))
        if k is None:
            continue
        v = obj[k]
        if isinstance(v, list):
            return [(None, e) for e in v if isinstance(e, dict)]
        if isinstance(v, dict):
            inner = _entries(v, depth + 1)
            if inner:
                return inner
    # any list of dicts that look like cameras
    for k, v in obj.items():
        if isinstance(v, list) and v and all(isinstance(e, dict) for e in v) and \
                any(_urls(e)[0] or _find(e, ID_KEYS, depth=0) is not None for e in v):
            return [(None, e) for e in v]
    # a dict keyed by camera id: {"cam1": {...}, "cam2": {...}}
    vals = list(obj.values())
    if vals and all(isinstance(v, dict) for v in vals) and any(any(_urls(v)) for v in vals):
        return [(str(k), v) for k, v in obj.items()]
    # a single camera object
    if any(_urls(obj)):
        return [(None, obj)]
    return []


def parse_entry(entry: dict, key_id: str | None = None) -> CameraInfo | None:
    rtsp, hls, whep = _urls(entry)
    cid = _find(entry, ID_KEYS, depth=1)
    if cid is None or isinstance(cid, (list, dict)):
        cid = key_id
    if cid is None and rtsp:
        cid = urlparse(rtsp).path.rstrip("/").split("/")[-1] or None
    if cid is None:
        name = _find(entry, NAME_KEYS, depth=0)
        cid = name if isinstance(name, str) else None
    if cid is None:
        return None
    if isinstance(cid, float) and cid.is_integer():
        cid = int(cid)
    lat, lon = _coords(entry)
    w, h = _resolution(entry)
    fps = _num(_find(entry, FPS_KEYS))
    name = _find(entry, NAME_KEYS)
    dept = _find(entry, DEPT_KEYS)
    live_v = _find(entry, LIVE_KEYS, skip_containers=False)
    return CameraInfo(
        id=str(cid).strip(),
        name=str(name) if isinstance(name, (str, int, float)) else "",
        department=str(dept) if isinstance(dept, (str, int, float)) else "",
        lat=lat, lon=lon,
        codec=_codec(_find(entry, CODEC_KEYS)),
        width=w, height=h,
        fps=fps if fps and fps > 0 else None,
        live=_live(live_v),
        rtsp_url=rtsp, hls_url=hls, whep_url=whep,
        raw=entry,
    )


def parse_catalogue(obj: Any) -> list[CameraInfo]:
    """Pure: catalogue JSON (already decoded, or str/bytes) -> cameras. Never raises on
    odd entries; skips what it cannot identify. Duplicate ids keep the first entry."""
    out: list[CameraInfo] = []
    seen: set[str] = set()
    for key_id, entry in _entries(obj):
        try:
            cam = parse_entry(entry, key_id)
        except Exception as e:   # one bad entry must not lose the whole catalogue
            log.warning("catalogue: skipping unparseable entry (%s): %.200r", e, entry)
            continue
        if cam is None:
            log.warning("catalogue: skipping entry without an id or url: %.200r", entry)
            continue
        if cam.id in seen:
            log.warning("catalogue: duplicate camera id %r, keeping the first", cam.id)
            continue
        seen.add(cam.id)
        out.append(cam)
    return out


def auth_headers(token: str | None = None) -> dict[str, str]:
    token = token if token is not None else os.environ.get(TOKEN_ENV, "")
    h = {"Accept": "application/json"}
    if token:
        h["Authorization"] = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    return h


def fetch_catalogue(url: str, token: str | None = None, timeout: float = 10.0,
                    client: httpx.Client | None = None) -> list[CameraInfo]:
    """GET the catalogue and parse it. Raises on HTTP / network / JSON errors so the
    caller can decide to keep its current camera set."""
    headers = auth_headers(token)
    if client is None:
        with httpx.Client(timeout=timeout, follow_redirects=True) as c:
            r = c.get(url, headers=headers)
    else:
        r = client.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return parse_catalogue(r.json())
