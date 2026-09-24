"""Shield-lite: purpose binding and the hash-chained audit log."""
from __future__ import annotations

import sqlite3

import pytest

from _registry_helpers import SHIELD, make_client
from prahari.registry import audit
from prahari.registry.db import Store


@pytest.fixture
def client(tmp_path, monkeypatch):
    return make_client(tmp_path, monkeypatch)


@pytest.mark.parametrize("path, params", [
    ("/api/trace/GJ01AB1234", {}),
    ("/api/watchlist/search", {"plate": "GJ01AB1234"}),
    ("/api/events", {"plate": "GJ01AB1234"}),
])
def test_purpose_and_case_id_required(client, path, params):
    r = client.get(path, params=params)
    assert r.status_code == 400
    assert set(r.json()["detail"]["missing"]) == {"purpose", "case_id"}
    r = client.get(path, params={**params, "purpose": "theft", "case_id": "  "})
    assert r.status_code == 400 and r.json()["detail"]["missing"] == ["case_id"]
    assert client.get(path, params={**params, **SHIELD}).status_code == 200


def test_sensitive_queries_are_audited(client):
    client.get("/api/trace/GJ01AB1234", params=SHIELD, headers={"X-Actor": "PI Desai"})
    client.get("/api/events", params={"plate": "GJ01AB1234", **SHIELD})
    client.get("/api/watchlist/search", params={"plate": "GJ01AB1234", **SHIELD})
    client.get("/api/trace/GJ01AB1234")                         # refused: not logged
    entries = client.get("/api/audit").json()["entries"]
    actions = [e["action"] for e in entries]
    assert actions == ["watchlist.search", "events.search", "trace"]
    trace = entries[-1]
    assert trace["actor"] == "PI Desai" and trace["purpose"] == "unit test"
    assert trace["case_id"] == "TEST-CASE-1" and trace["params"]["plate"] == "GJ01AB1234"
    assert client.get("/api/audit", params={"case_id": "TEST-CASE-1"}).json()["entries"]


def test_chain_verifies_and_links(client):
    for i in range(5):
        client.get("/api/trace/GJ01AB1234", params={**SHIELD, "case_id": f"C{i}"})
    v = client.get("/api/audit/verify").json()
    assert v["intact"] and v["entries"] == 5 and len(v["head_hash"]) == 64
    entries = sorted(client.get("/api/audit").json()["entries"], key=lambda e: e["id"])
    assert entries[0]["prev_hash"] == audit.GENESIS
    assert all(b["prev_hash"] == a["hash"] for a, b in zip(entries, entries[1:]))


def _raw(store: Store) -> sqlite3.Connection:
    c = sqlite3.connect(store.path, isolation_level=None)
    return c


def test_append_only_trigger(tmp_path):
    store = Store(tmp_path / "a.db")
    audit.append(store, actor="x", action="trace", purpose="p", case_id="c")
    c = _raw(store)
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        c.execute("UPDATE audit_log SET case_id = 'other'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        c.execute("DELETE FROM audit_log")


def test_tamper_detection_edit(tmp_path):
    store = Store(tmp_path / "a.db")
    for i in range(4):
        audit.append(store, actor="op", action="trace", purpose="p", case_id=f"C{i}",
                     params={"plate": "GJ01AB1234"})
    assert audit.verify(store)["intact"]
    # An attacker with raw file access drops the trigger and edits entry 2.
    c = _raw(store)
    c.execute("DROP TRIGGER audit_log_no_update")
    c.execute("UPDATE audit_log SET case_id = 'NOTHING-TO-SEE' WHERE id = 2")
    v = audit.verify(store)
    assert v["intact"] is False and v["first_broken_id"] == 2 and "edited" in v["reason"]


def test_tamper_detection_delete(tmp_path):
    store = Store(tmp_path / "a.db")
    for i in range(4):
        audit.append(store, actor="op", action="trace", purpose="p", case_id=f"C{i}")
    c = _raw(store)
    c.execute("DROP TRIGGER audit_log_no_delete")
    c.execute("DELETE FROM audit_log WHERE id = 2")
    v = audit.verify(store)
    assert v["intact"] is False and v["first_broken_id"] == 3 and "deleted" in v["reason"]


def test_tamper_detection_rehash_single_entry(tmp_path):
    """Recomputing one entry's own hash after editing it still breaks the NEXT link."""
    store = Store(tmp_path / "a.db")
    for i in range(3):
        audit.append(store, actor="op", action="trace", purpose="p", case_id=f"C{i}")
    c = _raw(store)
    c.execute("DROP TRIGGER audit_log_no_update")
    row = c.execute("SELECT ts, actor, action, purpose, params, prev_hash FROM audit_log"
                    " WHERE id = 1").fetchone()
    forged = audit.entry_hash(row[0], row[1], row[2], row[3], "FORGED", row[4], row[5])
    c.execute("UPDATE audit_log SET case_id = 'FORGED', hash = ? WHERE id = 1", (forged,))
    v = audit.verify(store)
    assert v["intact"] is False and v["first_broken_id"] == 2


def test_verify_endpoint_reports_tampering(client, tmp_path):
    client.get("/api/trace/GJ01AB1234", params=SHIELD)
    client.get("/api/trace/GJ01AB1234", params=SHIELD)
    c = sqlite3.connect(tmp_path / "registry.db", isolation_level=None)
    c.execute("DROP TRIGGER audit_log_no_update")
    c.execute("UPDATE audit_log SET actor = 'someone else' WHERE id = 1")
    v = client.get("/api/audit/verify").json()
    assert v["intact"] is False and v["first_broken_id"] == 1


def test_secrets_are_redacted(tmp_path):
    store = Store(tmp_path / "a.db")
    audit.append(store, actor="op", action="sync", params={"url": "u", "headers": {"A": "B"}})
    assert audit.recent(store)[0]["params"]["headers"] == "<redacted>"


def test_writes_are_audited_too(client):
    client.post("/api/watchlist", json={"plate": "GJ01AB1234", "category": "stolen_vehicle"})
    client.post("/api/cameras", json={"id": "X"})
    actions = {e["action"] for e in client.get("/api/audit").json()["entries"]}
    assert {"watchlist.add", "camera.manual_add"} <= actions
    assert client.get("/api/audit/verify").json()["intact"]


def test_health_and_docs(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and "counts" in h
    spec = client.get("/openapi.json").json()
    for p in ("/api/cameras/sync", "/api/cameras/import", "/api/trace/{plate}",
              "/api/reports/plates.csv", "/api/alerts/stream", "/api/audit/verify"):
        assert p in spec["paths"]
    assert client.get("/docs").status_code == 200
