"""Camera registry: the three onboarding paths, tolerant parsing, GIS, health, gap report."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from _registry_helpers import make_client
from prahari.registry import cameras as cm


@pytest.fixture
def client(tmp_path, monkeypatch):
    return make_client(tmp_path, monkeypatch)


# ---------------------------------------------------------------- tolerant parsing

SANDBOX_STYLE = [{
    "id": "1", "name": "Police camera 01", "department": "Police",
    "location": {"lat": 23.2156, "lng": 72.6369}, "codec": "h264", "live": True,
    "stream": {"width": 1280, "height": 720, "fps": 25},
    "urls": {"rtsp": "rtsp://127.0.0.1:8554/stream/1",
             "whep": "http://127.0.0.1:8889/stream/1/whep",
             "hls": "http://127.0.0.1:8888/stream/1/index.m3u8"},
}]


def test_parse_sandbox_shape_nested_fields():
    cams, skipped = cm.parse_catalogue(SANDBOX_STYLE)
    assert not skipped and len(cams) == 1
    c = cams[0]
    assert (c["id"], c["lat"], c["lon"]) == ("1", 23.2156, 72.6369)
    assert (c["width"], c["height"], c["fps"], c["codec"]) == (1280, 720, 25.0, "h264")
    assert c["rtsp_url"].startswith("rtsp://") and c["hls_url"].endswith(".m3u8")
    assert c["whep_url"].endswith("/whep")
    assert c["raw"] == SANDBOX_STYLE[0]                 # verbatim


@pytest.mark.parametrize("wrapper", ["cameras", "streams", "items", "data"])
def test_parse_wrapped_lists(wrapper):
    cams, _ = cm.parse_catalogue({wrapper: SANDBOX_STYLE, "total": 1})
    assert [c["id"] for c in cams] == ["1"]


def test_parse_doubly_wrapped_and_id_mapping():
    cams, _ = cm.parse_catalogue({"data": {"cameras": SANDBOX_STYLE}})
    assert [c["id"] for c in cams] == ["1"]
    cams, _ = cm.parse_catalogue({"camA": {"name": "A", "rtsp": "rtsp://x/a"},
                                  "camB": {"name": "B", "rtsp": "rtsp://x/b"}})
    assert sorted(c["id"] for c in cams) == ["camA", "camB"]


def test_parse_alias_zoo():
    rec = {"cameraId": 7, "title": "Bus stand", "agency": "GSRTC", "latitude": "23.01",
           "longitude": "72.58", "video_codec": "HEVC", "resolution": "960x540",
           "frameRate": "15", "status": "offline",
           "endpoints": {"webrtc": "http://h/7/whep"},
           "misc": ["rtsp://10.0.0.7:554/live", "http://h/7/index.m3u8"]}
    c = cm.parse_camera(rec)
    assert c["id"] == "7" and c["name"] == "Bus stand" and c["department"] == "GSRTC"
    assert (c["lat"], c["lon"]) == (23.01, 72.58)
    assert c["codec"] == "h265" and (c["width"], c["height"]) == (960, 540) and c["fps"] == 15
    assert c["live"] is False
    assert c["rtsp_url"] == "rtsp://10.0.0.7:554/live"          # found by scheme
    assert c["hls_url"].endswith(".m3u8") and c["whep_url"].endswith("/whep")


def test_parse_geojson_point_and_latlon_list():
    c = cm.parse_camera({"id": "g", "geometry": {"type": "Point",
                                                 "coordinates": [72.6, 23.2]}})
    assert (c["lat"], c["lon"]) == (23.2, 72.6)
    c = cm.parse_camera({"id": "l", "coordinates": [72.6, 23.2]})       # GeoJSON order
    assert (c["lat"], c["lon"]) == (23.2, 72.6)
    c = cm.parse_camera({"id": "s", "location": "23.2, 72.6"})
    assert (c["lat"], c["lon"]) == (23.2, 72.6)


def test_parse_skips_unidentifiable_and_derives_ids():
    cams, skipped = cm.parse_catalogue([{"foo": 1}, {"url": "rtsp://10.1.1.1/s"}])
    assert len(skipped) == 1 and len(cams) == 1
    assert cams[0]["id"].startswith("cam-") and cams[0]["rtsp_url"] == "rtsp://10.1.1.1/s"


def test_parse_rejects_null_island():
    c = cm.parse_camera({"id": "z", "lat": 0, "lon": 0})
    assert c["lat"] is None and c["lon"] is None


# ---------------------------------------------------------------- path 1: catalogue

@pytest.fixture
def catalogue_server():
    payload = {"payload": {"streams": SANDBOX_STYLE + [{
        "camera_id": "2", "name": "Health camera 02", "dept": "Health",
        "latitude": 23.2237, "longitude": 72.65, "codec": "H.265",
        "rtsp_url": "rtsp://127.0.0.1:8554/stream/2"}]}}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(payload["payload"]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/api/ingest", payload
    srv.shutdown()


def test_onboarding_catalogue_sync_over_http(client, catalogue_server):
    url, payload = catalogue_server
    r = client.post("/api/cameras/sync", json={"url": url})
    assert r.status_code == 200, r.text
    res = r.json()
    assert sorted(res["added"]) == ["1", "2"] and res["parsed"] == 2
    cam2 = client.get("/api/cameras/2").json()
    assert cam2["source"] == "catalogue" and cam2["codec"] == "h265"
    assert cam2["department"] == "Health"

    # Re-sync unchanged -> unchanged; then the catalogue drops camera 2 -> absent.
    assert sorted(client.post("/api/cameras/sync", json={"url": url}).json()["unchanged"]) \
        == ["1", "2"]
    payload["payload"] = {"streams": SANDBOX_STYLE}
    res = client.post("/api/cameras/sync", json={"url": url}).json()
    assert res["absent"] == ["2"]
    assert client.get("/api/cameras/2").json()["status"] == "absent"


def test_catalogue_sync_inline_payload_and_bad_url(client):
    r = client.post("/api/cameras/sync", json={"payload": {"items": SANDBOX_STYLE}})
    assert r.status_code == 200 and r.json()["added"] == ["1"]
    r = client.post("/api/cameras/sync", json={"url": "http://127.0.0.1:9/nothing"})
    assert r.status_code == 502
    assert client.post("/api/cameras/sync", json={}).status_code == 400


# ---------------------------------------------------------------- path 2: bulk CSV

CSV = """camera_id,name,department,latitude,longitude,codec,resolution,fps,rtsp
PS-01,Sector 7 gate,Police,23.2156,72.6369,H.264,1280x720,25,rtsp://10.1.1.5:554/live
PS-02,Infocity,Police,23.1650,72.6100,hevc,640x360,12,rtsp://10.1.1.6:554/live
MUN-01,No location camera,Municipal,,,h264,,,rtsp://10.1.1.7:554/live
,,,,,,,,
"""


def test_onboarding_bulk_csv(client):
    r = client.post("/api/cameras/import", content=CSV,
                    headers={"Content-Type": "text/csv"})
    assert r.status_code == 200, r.text
    res = r.json()
    assert sorted(res["added"]) == ["MUN-01", "PS-01", "PS-02"]
    assert res["without_location"] == ["MUN-01"]
    ps2 = client.get("/api/cameras/PS-02").json()
    assert ps2["source"] == "bulk" and ps2["codec"] == "h265"
    assert (ps2["width"], ps2["height"], ps2["fps"]) == (640, 360, 12.0)


def test_bulk_semicolon_csv_and_json_array(client):
    r = client.post("/api/cameras/import", content="id;lat;lng\nX1;23.1;72.5\n",
                    headers={"Content-Type": "text/csv"})
    assert r.json()["added"] == ["X1"]
    r = client.post("/api/cameras/import", json=[{"id": "J1", "lat": 23.0, "lon": 72.0}])
    assert r.json()["added"] == ["J1"]


# ---------------------------------------------------------------- path 3: manual

def test_onboarding_manual_and_filters_and_geojson(client):
    for cid, dept, lat, lon, codec in [("A", "Police", 23.20, 72.63, "h264"),
                                       ("B", "Health", 23.02, 72.57, "h265"),
                                       ("C", "Police", 21.17, 72.83, "h265")]:
        r = client.post("/api/cameras", json={"id": cid, "department": dept, "lat": lat,
                                              "lon": lon, "codec": codec})
        assert r.status_code == 201 and r.json()["camera"]["source"] == "manual"
    client.post("/api/cameras", json={"id": "D", "department": "Police"})     # no location

    assert client.get("/api/cameras", params={"department": "police"}).json()["count"] == 3
    assert {c["id"] for c in client.get("/api/cameras", params={"codec": "hevc"})
            .json()["cameras"]} == {"B", "C"}
    box = client.get("/api/cameras", params={"bbox": "72.5,22.9,72.7,23.3"}).json()
    assert {c["id"] for c in box["cameras"]} == {"A", "B"}
    assert client.get("/api/cameras", params={"bbox": "1,2,3"}).status_code == 400

    gj = client.get("/api/cameras.geojson")
    assert gj.headers["content-type"].startswith("application/geo+json")
    fc = gj.json()
    assert fc["type"] == "FeatureCollection" and len(fc["features"]) == 3
    assert fc["features"][0]["geometry"]["type"] == "Point"
    assert fc["skipped_without_location"] == ["D"]
    assert client.post("/api/cameras", json={"id": "bad", "lat": 123}).status_code == 422


def test_health_update_merges_capability(client):
    client.post("/api/cameras", json={"id": "H1", "lat": 23.2, "lon": 72.6})
    r = client.post("/api/cameras/H1/health", json={"capability": {"measured_fps": 11.8}})
    cam = r.json()
    assert cam["status"] == "online" and cam["last_seen"] is not None
    cam = client.post("/api/cameras/H1/health",
                      json={"status": "degraded", "capability": {"anpr_viable": False}}).json()
    assert cam["status"] == "degraded"
    assert cam["capability"] == {"measured_fps": 11.8, "anpr_viable": False}
    assert client.post("/api/cameras/nope/health", json={}).status_code == 404
    assert client.post("/api/cameras/H1/health", json={"status": "weird"}).status_code == 422


# ---------------------------------------------------------------- gap report

def test_gap_report(client):
    for cid, lat, lon in [("G1", 23.20, 72.60), ("G2", 23.25, 72.65), ("G3", 23.30, 72.70)]:
        client.post("/api/cameras", json={"id": cid, "department": "Police" if cid != "G3"
                                          else "Municipal", "lat": lat, "lon": lon})
    client.post("/api/cameras", json={"id": "G4", "department": "Health"})     # no location
    client.post("/api/cameras/G1/health", json={"status": "online"})
    client.post("/api/cameras/G2/health", json={"status": "offline"})
    client.post("/api/cameras/G3/health", json={"last_seen": time.time() - 7200,
                                                 "capability": {"anpr_viable": False,
                                                                "anpr_reason": "too small"}})
    r = client.get("/api/reports/gap", params={"cell_km": 1, "radius_km": 1}).json()
    t = r["totals"]
    assert (t["cameras"], t["offline"], t["stale"], t["never_seen"]) == (4, 1, 1, 1)
    assert t["anpr_unviable"] == 1 and r["anpr_unviable"][0]["reason"] == "too small"
    assert r["by_department"]["Police"]["total"] == 2
    cov = r["coverage"]
    assert cov["cells"] > 50 and cov["uncovered"] > 0
    assert cov["effective_coverage_pct"] < cov["coverage_pct"]       # unhealthy cams excluded
    worst = cov["uncovered_cells"][0]
    assert worst["nearest_camera_km"] > 1 and len(worst["polygon"]) == 5
    assert [c["id"] for c in r["without_location"]] == ["G4"]

    md = client.get("/api/reports/gap", params={"format": "md"})
    assert md.headers["content-type"].startswith("text/markdown")
    assert "# PRAHARI coverage gap report" in md.text and "| Police |" in md.text
    assert "too small" in md.text


def test_gap_report_empty_registry(client):
    r = client.get("/api/reports/gap").json()
    assert r["totals"]["cameras"] == 0 and r["coverage"]["note"]
