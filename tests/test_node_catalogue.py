"""Catalogue parsing: the real /api/ingest schema is unseen, so many shapes must work."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest

from prahari.node.catalogue import auth_headers, fetch_catalogue, parse_catalogue

REPLICA_ENTRY = {
    "id": "1", "name": "Police camera 01", "department": "Police",
    "location": {"lat": 23.2156, "lng": 72.6369}, "codec": "h264", "live": True,
    "stream": {"width": 1280, "height": 720, "fps": 25},
    "urls": {"rtsp": "rtsp://127.0.0.1:8554/stream/1",
             "whep": "http://127.0.0.1:8889/stream/1/whep",
             "hls": "http://127.0.0.1:8888/stream/1/index.m3u8"},
}


def test_replica_bare_list():
    [c] = parse_catalogue([REPLICA_ENTRY])
    assert c.id == "1" and c.name == "Police camera 01" and c.department == "Police"
    assert (c.lat, c.lon) == (23.2156, 72.6369)
    assert (c.codec, c.width, c.height, c.fps, c.live) == ("h264", 1280, 720, 25.0, True)
    assert c.rtsp_url == "rtsp://127.0.0.1:8554/stream/1"
    assert c.hls_url.endswith("index.m3u8") and c.whep_url.endswith("/whep")
    assert c.raw == REPLICA_ENTRY


@pytest.mark.parametrize("key", ["cameras", "streams", "items", "data", "Cameras", "results"])
def test_wrapped_list(key):
    cams = parse_catalogue({key: [REPLICA_ENTRY], "count": 1, "ok": True})
    assert [c.id for c in cams] == ["1"]


def test_nested_wrapper_and_json_string():
    body = json.dumps({"status": "ok", "data": {"cameras": [REPLICA_ENTRY]}})
    assert [c.id for c in parse_catalogue(body)] == ["1"]
    assert [c.id for c in parse_catalogue(body.encode())] == ["1"]


def test_flat_aliases():
    e = {"camera_id": 42, "camera_name": "Sector 7 junction", "dept": "Municipal",
         "latitude": "23.02", "longitude": "72.57", "video_codec": "HEVC",
         "resolution": "1920x1080", "frame_rate": "25/1", "status": "ONLINE",
         "rtsp_url": "rtsp://gw.example:8554/live/42"}
    [c] = parse_catalogue([e])
    assert c.id == "42" and c.name == "Sector 7 junction" and c.department == "Municipal"
    assert (c.lat, c.lon) == (23.02, 72.57)
    assert (c.codec, c.width, c.height, c.fps, c.live) == ("h265", 1920, 1080, 25.0, True)


def test_stream_id_geo_nested_endpoints():
    e = {"stream_id": "cam-0007", "geo": {"latitude": 23.1, "lon": 72.6},
         "endpoints": {"rtsp": {"url": "rtsp://10.0.0.5/s/7"}, "hls": "https://gw/s/7/index.m3u8"},
         "online": False, "video": {"codec": "H.264", "resolution": "720p", "fps": 15}}
    [c] = parse_catalogue({"streams": [e]})
    assert c.id == "cam-0007" and (c.lat, c.lon) == (23.1, 72.6)
    assert c.rtsp_url == "rtsp://10.0.0.5/s/7" and c.hls_url == "https://gw/s/7/index.m3u8"
    assert c.live is False and c.codec == "h264" and (c.width, c.height) == (1280, 720) and c.fps == 15


def test_geojson_point_is_lon_lat():
    e = {"id": "g1", "geometry": {"type": "Point", "coordinates": [72.6369, 23.2156]},
         "url": "rtsp://h/g1"}
    [c] = parse_catalogue([e])
    assert (c.lat, c.lon) == (23.2156, 72.6369)


def test_location_list_and_string():
    [a] = parse_catalogue([{"id": "a", "location": [23.5, 72.5], "rtsp": "rtsp://h/a"}])
    [b] = parse_catalogue([{"id": "b", "location": "23.6, 72.4", "rtsp": "rtsp://h/b"}])
    assert (a.lat, a.lon) == (23.5, 72.5) and (b.lat, b.lon) == (23.6, 72.4)


def test_url_found_anywhere_and_id_from_url():
    e = {"meta": {"playback": ["http://x/y.m3u8", "rtsp://gw:8554/stream/99"]}}
    [c] = parse_catalogue([e])
    assert c.rtsp_url == "rtsp://gw:8554/stream/99" and c.id == "99"
    assert c.hls_url == "http://x/y.m3u8"


def test_dict_keyed_by_id():
    cams = parse_catalogue({"cam1": {"rtsp": "rtsp://h/1"}, "cam2": {"rtsp": "rtsp://h/2", "live": "offline"}})
    assert [(c.id, c.live) for c in cams] == [("cam1", True), ("cam2", False)]


@pytest.mark.parametrize("v,expected", [(True, True), (False, False), (1, True), (0, False), ("live", True),
                                        ("Offline", False), ("down", False), ("streaming", True),
                                        ({"online": False}, False), (None, True), ("weird", True)])
def test_live_values(v, expected):
    e = {"id": "x", "rtsp": "rtsp://h/x"}
    if v is not None:
        e["status"] = v
    assert parse_catalogue([e])[0].live is expected


def test_missing_optional_fields_and_bad_entries_are_skipped():
    cams = parse_catalogue([{"id": 5}, "junk", None, {"no": "id"}, {"id": 6, "rtsp": "rtsp://h/6"}])
    assert [c.id for c in cams] == ["5", "6"]
    c5 = cams[0]
    assert c5.rtsp_url == "" and c5.lat is None and c5.fps is None and c5.width is None and c5.live


def test_duplicate_ids_keep_first():
    cams = parse_catalogue([{"id": "1", "rtsp": "rtsp://a/1"}, {"id": "1", "rtsp": "rtsp://b/1"}])
    assert len(cams) == 1 and cams[0].rtsp_url == "rtsp://a/1"


def test_empty_shapes():
    assert parse_catalogue([]) == []
    assert parse_catalogue({"cameras": []}) == []
    assert parse_catalogue({}) == []


def test_resolution_forms():
    for res, wh in [({"w": 640, "h": 360}, (640, 360)), ([960, 540], (960, 540)), ("1280 X 720", (1280, 720))]:
        [c] = parse_catalogue([{"id": "r", "rtsp": "rtsp://h/r", "resolution": res}])
        assert (c.width, c.height) == wh


def test_auth_headers(monkeypatch):
    monkeypatch.delenv("PRAHARI_INGEST_TOKEN", raising=False)
    assert "Authorization" not in auth_headers()
    monkeypatch.setenv("PRAHARI_INGEST_TOKEN", "abc123")
    assert auth_headers()["Authorization"] == "Bearer abc123"
    assert auth_headers("Bearer xyz")["Authorization"] == "Bearer xyz"


def test_fetch_catalogue_with_mock_transport(monkeypatch):
    monkeypatch.setenv("PRAHARI_INGEST_TOKEN", "tok")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"cameras": [REPLICA_ENTRY]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        cams = fetch_catalogue("http://sandbox/api/ingest", client=client)
    assert [c.id for c in cams] == ["1"] and seen["auth"] == "Bearer tok"


def test_fetch_catalogue_raises_on_http_error():
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503))) as client:
        with pytest.raises(httpx.HTTPStatusError):
            fetch_catalogue("http://sandbox/api/ingest", client=client)
