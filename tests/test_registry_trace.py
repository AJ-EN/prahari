"""Fuzzy search, cross-camera trace, near-miss fallback, and the plates CSV report."""
from __future__ import annotations

import csv
import io

import pytest

from _registry_helpers import SHIELD, add_cameras, make_client, plate_event

T0 = 1_790_000_000.0

# A Gandhinagar -> Ahmedabad corridor, plus Surat (~210 km away).
CAMS = [("GN1", 23.2156, 72.6369), ("GN2", 23.1650, 72.6100), ("AH1", 23.0395, 72.5660),
        ("SU1", 21.1702, 72.8311)]


@pytest.fixture
def client(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    add_cameras(c, CAMS)
    return c


def post(client, *events):
    for e in events:
        assert client.post("/api/events/plate", json=e).status_code == 200


def test_trace_orders_and_flags_implausible_hop(client):
    # Posted OUT of order on purpose; one misread; two frames at GN1; a Surat read
    # 10 minutes after Ahmedabad (impossible: ~210 km).
    post(client,
         plate_event("AH1", T0 + 1200, "GJ01AB1234", "GJ01AB1234"),
         plate_event("GN1", T0, "GJ01AB1234", "GJ01AB1234"),
         plate_event("GN1", T0 + 1.5, "GJ01AB1234", "GJ01AB1234", ocr_conf=0.7),
         plate_event("GN2", T0 + 420, "GJ01AB1Z34", None, ocr_conf=0.6),
         plate_event("SU1", T0 + 1800, "GJ01AB1234", "GJ01AB1234"),
         plate_event("GN2", T0 + 500, "MH12XY9876", "MH12XY9876"))      # another vehicle
    r = client.get("/api/trace/GJ01AB1234", params=SHIELD)
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["status"] == "matched"
    cams = [s["camera"]["id"] for s in t["sightings"]]
    assert cams == ["GN1", "GN2", "AH1", "SU1"]
    ts = [s["ts"] for s in t["sightings"]]
    assert ts == sorted(ts)

    gn1, gn2, ah1, su1 = t["sightings"]
    assert gn1["reads"] == 2 and gn1["hop"] is None and gn1["confidence"]["ocr"] == 0.9
    assert gn2["observed"] == "GJ01AB1Z34" and 0 < gn2["match_distance"] <= 0.30
    assert gn2["camera"]["name"] == "cam GN2" and gn2["camera"]["lat"] == 23.1650
    hop = gn2["hop"]
    assert hop["from_camera"] == "GN1" and hop["gap_s"] == pytest.approx(418.5)
    assert 5 < hop["distance_km"] < 7 and hop["speed_kmh"] < 150 and hop["plausible"]
    assert ah1["hop"]["plausible"]
    assert su1["hop"]["plausible"] is False and su1["hop"]["speed_kmh"] > 1000
    assert "cloned plate" in su1["hop"]["reason"]
    assert t["summary"]["implausible_hops"] == 1 and t["summary"]["cameras"] == 4

    line = t["geojson"]["features"][0]
    assert line["geometry"]["type"] == "LineString"
    assert line["geometry"]["coordinates"][0] == [72.6369, 23.2156]
    assert len(line["geometry"]["coordinates"]) == 4

    gj = client.get("/api/trace/GJ01AB1234", params={**SHIELD, "format": "geojson"})
    assert gj.headers["content-type"].startswith("application/geo+json")
    assert gj.json()["type"] == "FeatureCollection"


def test_trace_time_window_and_collapse_off(client):
    post(client, plate_event("GN1", T0, "GJ01AB1234"), plate_event("GN1", T0 + 2, "GJ01AB1234"),
         plate_event("AH1", T0 + 1200, "GJ01AB1234"))
    t = client.get("/api/trace/GJ01AB1234",
                   params={**SHIELD, "from": T0 + 100, "to": T0 + 5000}).json()
    assert [s["camera"]["id"] for s in t["sightings"]] == ["AH1"]
    t = client.get("/api/trace/GJ01AB1234", params={**SHIELD, "collapse_s": 0}).json()
    assert t["summary"]["sightings"] == 3
    assert t["sightings"][1]["hop"]["speed_kmh"] == 0.0          # same camera
    iso_from = "2026-09-21T19:23:20+05:30"                         # == T0 in IST
    t = client.get("/api/trace/GJ01AB1234", params={**SHIELD, "from": iso_from}).json()
    assert t["summary"]["events_matched"] == 3


def test_simultaneous_sightings_far_apart_are_flagged(client):
    post(client, plate_event("GN1", T0, "GJ01AB1234"), plate_event("SU1", T0, "GJ01AB1234"))
    t = client.get("/api/trace/GJ01AB1234", params=SHIELD).json()
    hop = t["sightings"][1]["hop"]
    assert hop["plausible"] is False and hop["speed_kmh"] is None


def test_trace_matches_via_candidates(client):
    post(client, plate_event("GN1", T0, "XXGARBLED", None,
                             candidates=[{"plate": "GJ01AB1234", "distance": 0.4}]))
    t = client.get("/api/trace/GJ01AB1234", params=SHIELD).json()
    assert t["sightings"][0]["matched_on"] == "candidate"


def test_trace_near_miss_fallback_never_silent(client):
    post(client, plate_event("GN1", T0, "GJ01AB1238", "GJ01AB1238"),     # 1 unrelated char
         plate_event("GN2", T0 + 60, "GJ01AB1238", "GJ01AB1238"),
         plate_event("AH1", T0 + 90, "KA05MN0001", "KA05MN0001"))
    t = client.get("/api/trace/GJ01AB1234", params=SHIELD).json()
    assert t["status"] == "no_confident_match" and t["sightings"] == []
    assert t["message"]
    nm = t["near_misses"]
    assert nm[0]["reading"] == "GJ01AB1238" and nm[0]["events"] == 2
    assert nm[0]["cameras"] == ["GN1", "GN2"] and nm[0]["weak"] is False

    # Nothing even close: still ranked, marked weak.
    t = client.get("/api/trace/DL01ZZ9999", params=SHIELD).json()
    assert t["near_misses"] and all(x["weak"] for x in t["near_misses"])


def test_trace_empty_database_explains(client):
    t = client.get("/api/trace/GJ01AB1234", params=SHIELD).json()
    assert t["status"] == "no_confident_match" and "No plate readings" in t["message"]


def test_trace_invalid_query_gets_grammar_help(client):
    post(client, plate_event("GN1", T0, "GJ01AB1234"))
    t = client.get("/api/trace/6J01A8I234", params=SHIELD).json()
    assert t["grammar"]["valid"] is False
    assert t["grammar"]["did_you_mean"][0]["plate"] == "GJ01AB1234"
    assert t["status"] == "matched"                   # 0.18 + 0.12 + 0.08 <= 0.5


def test_fuzzy_event_search(client):
    post(client, plate_event("GN1", T0, "GJ01AB1Z34"), plate_event("GN2", T0 + 60, "GJ01AB1234"),
         plate_event("AH1", T0 + 90, "MH12XY9876"))
    r = client.get("/api/events", params={"plate": "GJ01AB1234", **SHIELD}).json()
    assert r["count"] == 2 and r["status"] == "matched"
    assert [e["camera"]["id"] for e in r["events"]] == ["GN2", "GN1"]      # newest first
    assert r["events"][1]["match"]["distance"] > 0
    r = client.get("/api/events", params={"plate": "GJ01AB1234", "camera": "GN1",
                                          **SHIELD}).json()
    assert r["count"] == 1
    # no plate filter: plain listing, not purpose-bound
    r = client.get("/api/events", params={"camera": "AH1"}).json()
    assert r["count"] == 1 and r["events"][0]["camera"]["name"] == "cam AH1"
    assert client.get("/api/events", params={"from": "yesterday"}).status_code == 400


def test_plates_csv_report(client):
    client.post("/api/watchlist", json={"plate": "GJ01AB1234", "category": "stolen_vehicle"})
    post(client, plate_event("GN1", T0, "GJ01AB1Z34"), plate_event("GN1", T0 + 1, "GJ01AB1Z34"),
         plate_event("AH1", T0 + 90, "MH12XY9876", "MH12XY9876"),
         plate_event("SU1", T0 + 99999, "KA05MN0001", "KA05MN0001"))
    r = client.get("/api/reports/plates.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 4
    first = rows[0]
    assert first["camera_id"] == "GN1" and first["camera_name"] == "cam GN1"
    assert float(first["lat"]) == 23.2156 and first["timestamp_ist"].endswith("+05:30")
    assert first["watchlist_match"] == "GJ01AB1234" and first["alert_kind"] == "alert"
    assert rows[1]["watchlist_match"] == "GJ01AB1234"          # the deduplicated repeat too
    assert rows[2]["state"] == "Maharashtra" and rows[2]["watchlist_match"] == ""

    r = client.get("/api/reports/plates.csv", params={"from": T0 + 50, "to": T0 + 1000})
    assert len(list(csv.DictReader(io.StringIO(r.text)))) == 1
    r = client.get("/api/reports/plates.csv", params={"camera": "GN1"})
    assert len(list(csv.DictReader(io.StringIO(r.text)))) == 2
