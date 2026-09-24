"""Watchlist CRUD/import, event ingestion, alert-vs-review decisions, live SSE, ack."""
from __future__ import annotations

import json
import threading
import time

import pytest

from _registry_helpers import SHIELD, add_cameras, make_client, plate_event
from prahari.registry import seed
from prahari.registry.db import Store


@pytest.fixture
def client(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    add_cameras(c, [("C1", 23.2156, 72.6369), ("C2", 23.1650, 72.6100)])
    r = c.post("/api/watchlist", json={"plate": "GJ-01-AB-1234", "category": "stolen",
                                       "details": {"fir_no": "SAMPLE-1"}})
    assert r.status_code == 201
    return c


def test_watchlist_crud(client):
    e = client.get("/api/watchlist/gj01ab1234").json()
    assert e["plate"] == "GJ01AB1234" and e["category"] == "stolen_vehicle"
    assert e["grammar"]["valid"] and e["grammar"]["district"] == "Ahmedabad"
    assert client.post("/api/watchlist", json={"plate": "GJ18BK4521",
                                               "category": "nonsense"}).status_code == 400
    odd = client.post("/api/watchlist", json={"plate": "VIP 1", "category": "suspect"}).json()
    assert odd["grammar"]["valid"] is False and odd["grammar"]["reasons"]
    assert client.get("/api/watchlist").json()["count"] == 2
    assert client.delete("/api/watchlist/VIP1").status_code == 200
    assert client.get("/api/watchlist").json()["count"] == 1
    assert client.get("/api/watchlist", params={"active": False}).json()["count"] == 1
    assert client.delete("/api/watchlist/NOPE").status_code == 404


def test_watchlist_csv_import(client):
    csv_body = ("plate,category,fir_no,police_station\n"
                "GJ05JT3309,stolen_vehicle,SAMPLE-2,Adajan\n"
                "GJ18BK4521,wanted,SAMPLE-3,Infocity\n"
                ",suspect,,\n"
                "GJ06FH2290,unknown_cat,,\n")
    r = client.post("/api/watchlist/import", content=csv_body,
                    headers={"Content-Type": "text/csv"}).json()
    assert r["imported"] == 2 and len(r["errors"]) == 2
    e = client.get("/api/watchlist/GJ18BK4521").json()
    assert e["category"] == "wanted_person"
    assert e["details"] == {"fir_no": "SAMPLE-3", "police_station": "Infocity"}


def test_misread_alerts_on_watchlisted_plate(client):
    """The headline case: OCR read GJ01AB1Z34 must ALERT on watchlisted GJ01AB1234."""
    r = client.post("/api/events/plate",
                    json=plate_event("C1", time.time(), "GJ01AB1Z34", None)).json()
    assert r["stored"] and len(r["alerts"]) == 1
    a = r["alerts"][0]
    assert a["kind"] == "alert" and a["watchlist_plate"] == "GJ01AB1234"
    assert a["distance"] <= 0.30 and a["observed"] == "GJ01AB1Z34"
    assert a["camera"]["id"] == "C1" and a["camera"]["lat"] == 23.2156
    assert a["watchlist"]["category"] == "stolen_vehicle"


@pytest.mark.parametrize("raw", ["GJ01AB1234", "6J01AB1234", "GJ01A81234", "gj 01 ab 1234"])
def test_other_confusable_reads_alert(client, raw):
    r = client.post("/api/events/plate", json=plate_event("C1", time.time(), raw)).json()
    assert [a["kind"] for a in r["alerts"]] == ["alert"]


def test_different_vehicle_goes_to_review_not_alert(client):
    # 4 -> 5 is not an OCR confusion: a different real vehicle, one char apart.
    r = client.post("/api/events/plate",
                    json=plate_event("C1", time.time(), "GJ01AB1235", "GJ01AB1235")).json()
    assert [a["kind"] for a in r["alerts"]] == ["review"]
    assert r["alerts"][0]["distance"] > 0.30


def test_unrelated_plate_creates_nothing(client):
    r = client.post("/api/events/plate",
                    json=plate_event("C1", time.time(), "MH12XY9876", "MH12XY9876")).json()
    assert r["stored"] and r["alerts"] == [] and r["hits"] == []


def test_idempotent_event_id_and_dedupe(client):
    t = time.time()
    ev = plate_event("C1", t, "GJ01AB1234", "GJ01AB1234")
    first = client.post("/api/events/plate", json=ev).json()
    again = client.post("/api/events/plate", json=ev).json()
    assert first["stored"] and again["duplicate"] and again["alerts"] == []
    # Same plate, same camera, 2 s later: folded into the same alert.
    r = client.post("/api/events/plate",
                    json=plate_event("C1", t + 2, "GJ01AB1234", "GJ01AB1234")).json()
    assert r["alerts"] == [] and r["updated_alerts"][0]["hits"] == 2
    # Different camera: a new alert.
    r = client.post("/api/events/plate",
                    json=plate_event("C2", t + 300, "GJ01AB1234", "GJ01AB1234")).json()
    assert len(r["alerts"]) == 1
    assert client.get("/api/alerts").json()["count"] == 2


def test_event_validation_and_unknown_camera(client):
    assert client.post("/api/events/plate", json={"camera_id": "C1"}).status_code == 422
    assert client.post("/api/events/plate", json={"camera_id": "C1", "ts": 1.0,
                                                  "raw_text": ""}).status_code == 400
    r = client.post("/api/events/plate",
                    json=plate_event("GHOST", time.time(), "GJ01AB1234")).json()
    assert r["stored"] and r["camera_known"] is False and r["alerts"]


def test_batch_ingest(client):
    t = time.time()
    evs = [plate_event("C1", t, "GJ01AB1234"), plate_event("C2", t + 600, "KA01AA0001")]
    r = client.post("/api/events/batch", json=evs + [evs[0]]).json()
    assert (r["received"], r["stored"], r["duplicates"]) == (3, 2, 1)
    assert len(r["alerts"]) == 1


def test_list_and_ack_alerts(client):
    client.post("/api/events/plate", json=plate_event("C1", time.time(), "GJ01AB1Z34"))
    alerts = client.get("/api/alerts", params={"status": "open", "kind": "alert"}).json()
    assert alerts["count"] == 1
    a = alerts["alerts"][0]
    assert a["event"]["raw_text"] == "GJ01AB1Z34" and a["watchlist"]["details"]["fir_no"]
    acked = client.post(f"/api/alerts/{a['id']}/ack", json={"note": "PCR dispatched"}).json()
    assert acked["status"] == "ack" and acked["acked_by"] == "pytest"
    assert client.get("/api/alerts", params={"status": "open"}).json()["count"] == 0
    assert client.post("/api/alerts/9999/ack", json={}).status_code == 404


def test_camera_marked_alive_by_events(client):
    client.post("/api/events/plate", json=plate_event("C2", time.time(), "KA01AA0001"))
    cam = client.get("/api/cameras/C2").json()
    assert cam["status"] == "online" and cam["last_seen"] is not None


def _read_sse(client, params, out: list, n: int):
    with client.stream("GET", "/api/alerts/stream", params=params) as resp:
        for line in resp.iter_lines():
            if line.startswith("data: "):
                out.append(json.loads(line[6:]))
                if len(out) >= n:
                    return


def test_sse_replay(client):
    client.post("/api/events/plate", json=plate_event("C1", time.time(), "GJ01AB1Z34"))
    got: list = []
    _read_sse(client, {"replay": 5, "limit": 1}, got, 1)
    assert got[0]["watchlist_plate"] == "GJ01AB1234" and got[0]["kind"] == "alert"


def test_sse_live_push(client):
    got: list = []
    th = threading.Thread(target=_read_sse, args=(client, {"limit": 1}, got, 1), daemon=True)
    th.start()
    app_bus = client.app.state.bus
    deadline = time.time() + 5
    while app_bus.subscribers == 0 and time.time() < deadline:
        time.sleep(0.02)
    assert app_bus.subscribers == 1
    client.post("/api/events/plate", json=plate_event("C2", time.time(), "6J01AB1234"))
    th.join(timeout=5)
    assert got and got[0]["camera"]["id"] == "C2" and got[0]["kind"] == "alert"


def test_watchlist_search_is_ranked_and_purpose_bound(client):
    assert client.get("/api/watchlist/search", params={"plate": "GJ01AB1Z34"}).status_code == 400
    r = client.get("/api/watchlist/search", params={"plate": "GJ01AB1Z34", **SHIELD}).json()
    assert r["hits"][0]["watchlist_plate"] == "GJ01AB1234"
    assert r["hits"][0]["decision"] == "alert" and "confusion" in r["hits"][0]["explain"]
    assert r["corrections"] and r["corrections"][0]["plate"] == "GJ01AB1234"


def test_seed_watchlist(tmp_path):
    store = Store(tmp_path / "seed.db")
    n = seed.seed_watchlist(store)
    assert 35 <= n <= 50
    with store.read() as c:
        cats = {r[0] for r in c.execute("SELECT DISTINCT category FROM watchlist")}
        sample_flags = [json.loads(r[0])["sample"] for r in c.execute("SELECT details FROM watchlist")]
    assert cats == {"stolen_vehicle", "wanted_person", "missing_person", "blacklisted", "suspect"}
    assert all(sample_flags)
    assert seed.seed_watchlist(store) == n                     # idempotent
    assert store.counts()["watchlist"] == n
