"""
PRAHARI Registry — the mandatory Model 1 centralised CCTV registry, plus the
watchlist, plate-event store, alerting, trace and the Shield-lite audit log.

Storage and logic only; no web code lives here (see `prahari.api`).
"""
from prahari.registry.db import Store, default_db_path

__all__ = ["Store", "default_db_path"]
