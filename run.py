#!/usr/bin/env python3
"""
PRAHARI — one command to run everything.

    python run.py            start with the camera link in prahari.env
    python run.py demo       practice mode: a built-in fake camera grid with plates
    python run.py doctor     check this computer and the camera link, in plain words
    python run.py seed       load the SAMPLE watchlist into the database

Then open the address it prints (default http://127.0.0.1:8000).
Stop with Ctrl+C.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

if sys.version_info < (3, 10):
    sys.exit("PRAHARI needs Python 3.10 or newer (3.12 recommended). "
             f"This is Python {sys.version.split()[0]}.")


def banner(lines: list[str]) -> None:
    w = max(len(x) for x in lines) + 4
    print("\n" + "=" * w)
    for x in lines:
        print(f"  {x}")
    print("=" * w + "\n", flush=True)


def port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        return s.connect_ex((host, port)) != 0


def free_port(start: int) -> int:
    p = start
    while not port_free(p):
        p += 1
    return p


def serve(settings, *, extra_lines: list[str] | None = None, before_stop=None) -> None:
    import uvicorn

    from prahari.api.app import create_app
    from prahari.registry import watchlist as wl_mod
    from prahari.registry.seed import seed_watchlist
    from prahari.runtime import Runtime, attach

    if not port_free(settings.port, "127.0.0.1"):
        sys.exit(f"Port {settings.port} is already in use. Set PORT=... in prahari.env, "
                 f"or stop the other program.")
    app = create_app(settings.db or None)
    store = app.state.get_store()
    if settings.seed_sample_watchlist and not wl_mod.list_entries(store):
        n = seed_watchlist(store)
        print(f"Loaded {n} SAMPLE watchlist entries (clearly marked SAMPLE). "
              f"Import your own from the Watchlist page.")
    rt = Runtime(settings, store, app.state.bus)
    attach(app, rt)
    rt.start()

    shown = "127.0.0.1" if settings.host in ("0.0.0.0", "") else settings.host
    banner([f"PRAHARI is running.  Open:  http://{shown}:{settings.port}",
            f"Cameras from: {settings.ingest_url}",
            f"Database:     {store.path}",
            *(extra_lines or []),
            "Stop with Ctrl+C."])
    try:
        uvicorn.run(app, host=settings.host, port=settings.port, log_level="warning",
                    timeout_graceful_shutdown=2)
    finally:
        print("Stopping cameras...", flush=True)
        if before_stop:
            before_stop()
        rt.stop()


def cmd_start() -> None:
    from prahari.settings import ENV_FILE, Settings
    s = Settings.load()
    where = ENV_FILE if ENV_FILE.exists() else "prahari.env (copy it from prahari.env.example)"
    if not s.ingest_url or "REPLACE" in s.ingest_url:
        sys.exit(f"\nNo camera list set yet. Set INGEST_URL in {where}.\n"
                 f"  Or try practice mode first:  python run.py demo\n")
    if "://" not in s.ingest_url and not Path(s.ingest_url).exists():
        sys.exit(f"\nCamera list file not found: {s.ingest_url}\n"
                 f"  Open https://cctv.corp8.cloud/cameras.json in your logged-in browser,\n"
                 f"  save it into the PRAHARI folder under that name, then run again.\n"
                 f"  Check everything first with:  python run.py doctor\n")
    serve(s)


def cmd_demo() -> None:
    """Practice mode: built-in RTSP grid + catalogue, separate database."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from prahari.settings import Settings
    sys.path.insert(0, str(ROOT / "sandbox"))
    import demo_grid

    clips = ROOT / "sandbox" / "demo"
    if not list(clips.glob("cam*.mp4")):
        print("Building practice videos (one time, ~10 s)...")
        demo_grid.build()

    rtsp_port = free_port(8554)
    srv = subprocess.Popen([sys.executable, str(ROOT / "sandbox" / "rtsp_server.py"),
                            "--clips", str(clips), "--port", str(rtsp_port)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def stop_video_server() -> None:
        if srv.poll() is None:
            srv.terminate()
            try:
                srv.wait(timeout=5)
            except subprocess.TimeoutExpired:
                srv.kill()

    atexit.register(stop_video_server)          # never leave it running behind us
    cat_port = free_port(8091)
    body = json.dumps(demo_grid.catalogue(rtsp_port=rtsp_port)).encode()

    class Cat(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?")[0].rstrip("/") != "/api/ingest":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", cat_port), Cat)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    for _ in range(50):                      # wait for the RTSP server to listen
        if not port_free(rtsp_port):
            break
        if srv.poll() is not None:
            sys.exit("The practice video server failed to start:\n" +
                     (srv.stderr.read().decode(errors="replace") if srv.stderr else ""))
        time.sleep(0.1)

    s = Settings.load()
    s.ingest_url = f"http://127.0.0.1:{cat_port}/api/ingest"
    s.ingest_token = ""
    s.max_cameras = 0
    s.db = s.db or str(ROOT / "data" / "demo.db")   # never mix practice data with real data
    s.catalogue_poll_s = 30
    s.apply_to_environment()
    try:
        serve(s, before_stop=stop_video_server, extra_lines=[
            "PRACTICE MODE — synthetic cameras, separate database (data/demo.db).",
            "Watch: a stolen white Swift GJ01AB1234 drives past cameras 1 -> 2 -> 3 -> 4.",
            "Try:  Alerts page, then Trace -> GJ01AB1234."])
    finally:
        httpd.shutdown()
        stop_video_server()


def cmd_doctor() -> None:
    from prahari.doctor import main as doctor_main
    sys.exit(doctor_main())


def cmd_seed() -> None:
    from prahari.registry.db import Store
    from prahari.registry.seed import seed_watchlist
    from prahari.settings import Settings
    s = Settings.load()
    store = Store(s.db or None)
    print(f"{seed_watchlist(store)} SAMPLE watchlist entries in {store.path}")


def main() -> None:
    logging.basicConfig(level=os.environ.get("PRAHARI_LOG", "WARNING"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"
    cmds = {"start": cmd_start, "demo": cmd_demo, "doctor": cmd_doctor, "seed": cmd_seed}
    if cmd in ("-h", "--help", "help") or cmd not in cmds:
        print(__doc__)
        sys.exit(0 if cmd in ("-h", "--help", "help") else 2)
    try:
        cmds[cmd]()
    except KeyboardInterrupt:
        pass
    except ModuleNotFoundError as e:
        sys.exit(f"\nMissing Python package: {e.name}\n"
                 f"  Install everything with:  pip install -r requirements.txt\n"
                 f"  Then check with:          python run.py doctor\n")


if __name__ == "__main__":
    main()
