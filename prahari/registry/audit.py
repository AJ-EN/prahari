"""
Shield-lite: an append-only, SHA-256 hash-chained audit log.

Each entry's hash covers its own fields AND the previous entry's hash, so
editing, deleting or reordering any past entry breaks every hash after it.
`verify()` recomputes the whole chain from the genesis value and reports the
first entry that does not check out.

Known limit (stated, not hidden): truncating the newest entries leaves a
shorter chain that is still internally consistent. Anchoring the head hash
externally (printing it into a report, or countersigning it) closes that gap;
`verify()` returns `head_hash` for exactly that purpose.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from prahari.registry.db import Store, jdump

GENESIS = "0" * 64
SENSITIVE_KEYS = {"authorization", "token", "password", "headers", "api_key", "secret"}


def _redact(params: dict[str, Any]) -> dict[str, Any]:
    return {k: ("<redacted>" if k.lower() in SENSITIVE_KEYS else v)
            for k, v in params.items()}


def entry_hash(ts: str, actor: str, action: str, purpose: str | None,
               case_id: str | None, params: str, prev_hash: str) -> str:
    material = json.dumps([ts, actor, action, purpose, case_id, params, prev_hash],
                          ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def append(store: Store, *, actor: str, action: str, purpose: str | None = None,
           case_id: str | None = None, params: dict[str, Any] | None = None) -> dict:
    ts = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    p = jdump(_redact(params or {}))
    with store.tx() as c:
        row = c.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        prev = row["hash"] if row else GENESIS
        h = entry_hash(ts, actor, action, purpose, case_id, p, prev)
        cur = c.execute(
            "INSERT INTO audit_log(ts, actor, action, purpose, case_id, params, prev_hash, hash)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (ts, actor, action, purpose, case_id, p, prev, h))
        return {"id": cur.lastrowid, "ts": ts, "hash": h, "prev_hash": prev}


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["params"] = json.loads(d["params"]) if d["params"] else {}
    return d


def recent(store: Store, *, limit: int = 100, action: str | None = None,
           case_id: str | None = None) -> list[dict]:
    q, args = "SELECT * FROM audit_log WHERE 1=1", []
    if action:
        q += " AND action = ?"; args.append(action)
    if case_id:
        q += " AND case_id = ?"; args.append(case_id)
    q += " ORDER BY id DESC LIMIT ?"; args.append(limit)
    with store.read() as c:
        return [_row(r) for r in c.execute(q, args)]


def verify(store: Store) -> dict:
    """Recompute the chain. Intact iff every entry links to its predecessor
    and every stored hash equals the recomputed one."""
    prev = GENESIS
    n = 0
    with store.read() as c:
        for r in c.execute("SELECT * FROM audit_log ORDER BY id"):
            n += 1
            if r["prev_hash"] != prev:
                return {"intact": False, "entries": n, "first_broken_id": r["id"],
                        "reason": "prev_hash does not match the preceding entry "
                                  "(an entry was deleted, inserted or reordered)",
                        "head_hash": None}
            expect = entry_hash(r["ts"], r["actor"], r["action"], r["purpose"],
                                r["case_id"], r["params"], r["prev_hash"])
            if expect != r["hash"]:
                return {"intact": False, "entries": n, "first_broken_id": r["id"],
                        "reason": "entry contents do not match its hash (entry was edited)",
                        "head_hash": None}
            prev = r["hash"]
    return {"intact": True, "entries": n, "first_broken_id": None, "reason": None,
            "head_hash": prev if n else GENESIS}
