"""
Vercel serverless entrypoint for PRAHARI.
Exports FastAPI `app` instance from `prahari.api.app`.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is on sys.path when invoked in serverless environments
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from prahari.api.app import app  # noqa: E402

__all__ = ["app"]
