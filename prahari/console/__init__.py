"""
PRAHARI web console: a static single-page app (plain HTML/CSS/JS, no build step)
served by the registry API process.

    GET /            -> static/index.html
    GET /static/...  -> static/*  (app.js, views/*.js, vendored Leaflet)

The API stays under /api/... . The console is mounted WITHOUT a catch-all route,
so API routes added to the app later (e.g. /api/cameras/{id}/snapshot.jpg) are
never shadowed by it, whatever order they are registered in.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Revalidate on every load (ETag -> cheap 304), so an updated console is picked up
# on a plain browser refresh instead of running a stale cached module.
_NO_CACHE = {"Cache-Control": "no-cache"}


class _RevalidatingStatic(StaticFiles):
    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers.update(_NO_CACHE)
        return resp


def mount_console(app: FastAPI) -> None:
    """Serve the console at `/` and its assets at `/static`."""
    if not (STATIC_DIR / "index.html").is_file():      # console not shipped: API only
        return

    @app.get("/", include_in_schema=False)
    def console_index():
        return FileResponse(STATIC_DIR / "index.html", headers=_NO_CACHE)

    app.mount("/static", _RevalidatingStatic(directory=STATIC_DIR), name="console-static")
