"""
Local replica of the Sentinel camera grid.

The real sandbox is only reachable after login, and it cannot be made to fail on
demand. This replica mirrors the documented contract closely enough to build and
harden the ingest spine against it:

  * RTSP at  rtsp://<host>:8554/stream/<id>        (served by MediaMTX)
  * a catalogue at  http://<host>:<port>/api/ingest  listing every camera
  * mixed H.264 / H.265, mixed resolutions, mixed frame rates
  * feeds that loop (a hard cut at the loop point)

Usage:
  python sandbox/grid.py clips      # generate synthetic clips (once, ~30 MB)
  python sandbox/grid.py config     # write sandbox/mediamtx.yml
  python sandbox/grid.py catalogue  # serve /api/ingest on :8090
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLIPS = HERE / "clips"
N_CAMERAS = 12

# Deliberately heterogeneous, like the real grid. Departments mirror the five
# named in the official dataset description.
DEPTS = ["Police", "Health", "GSRTC", "Panchayat", "Municipal"]
PROFILES = [
    # (codec, width, height, fps)
    ("h264", 1280, 720, 25), ("h265", 960, 540, 15), ("h264", 640, 360, 12),
    ("h265", 1280, 720, 10), ("h264", 960, 540, 15), ("h265", 640, 360, 25),
]
# Rough points around Gandhinagar / Ahmedabad so the GIS layer has real geography.
POINTS = [
    (23.2156, 72.6369), (23.2237, 72.6500), (23.1991, 72.6305), (23.2310, 72.6200),
    (23.0225, 72.5714), (23.0395, 72.5660), (23.0120, 72.5870), (23.0600, 72.5800),
    (23.1650, 72.6100), (23.1300, 72.6000), (23.0900, 72.5950), (23.2450, 72.6700),
]


def cam(i: int) -> dict:
    codec, w, h, fps = PROFILES[i % len(PROFILES)]
    lat, lon = POINTS[i % len(POINTS)]
    return {"id": str(i + 1), "codec": codec, "width": w, "height": h, "fps": fps,
            "lat": lat, "lon": lon, "department": DEPTS[i % len(DEPTS)],
            "name": f"{DEPTS[i % len(DEPTS)]} camera {i + 1:02d}"}


def make_clips() -> None:
    CLIPS.mkdir(exist_ok=True)
    for i in range(N_CAMERAS):
        c = cam(i)
        out = CLIPS / f"cam{i + 1:02d}.mp4"
        if out.exists():
            continue
        enc = (["-c:v", "libx264", "-preset", "veryfast", "-crf", "32"] if c["codec"] == "h264"
               else ["-c:v", "libx265", "-preset", "veryfast", "-crf", "34", "-tag:v", "hvc1",
                     "-x265-params", "log-level=error"])
        # testsrc2 carries a moving pattern and a frame counter, so the loop
        # point is a visible hard cut. 40 s keeps the whole grid near 30 MB.
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
               "-i", f"testsrc2=size={c['width']}x{c['height']}:rate={c['fps']}:duration=40",
               *enc, "-g", str(c["fps"] * 2), "-pix_fmt", "yuv420p", str(out)]
        subprocess.run(cmd, check=True)
        print("made", out.name, c["codec"], f"{c['width']}x{c['height']}@{c['fps']}")


def write_config() -> None:
    lines = ["logLevel: warn", "rtspAddress: :8554", "rtmp: no", "srt: no",
             "hlsAddress: :8888", "webrtcAddress: :8889", "api: no", "paths:"]
    for i in range(N_CAMERAS):
        clip = CLIPS / f"cam{i + 1:02d}.mp4"
        lines += [
            f"  stream/{i + 1}:",
            # the repo path contains a space: quote it (MediaMTX runs this via /bin/sh)
            f"    runOnInit: ffmpeg -hide_banner -loglevel error -re -stream_loop -1 -i '{clip}' "
            f"-c copy -f rtsp -rtsp_transport tcp rtsp://127.0.0.1:8554/stream/{i + 1}",
            "    runOnInitRestart: yes",
        ]
    (HERE / "mediamtx.yml").write_text("\n".join(lines) + "\n")
    print("wrote", HERE / "mediamtx.yml")


def catalogue(host: str = "127.0.0.1") -> list[dict]:
    out = []
    for i in range(N_CAMERAS):
        c = cam(i)
        out.append({
            "id": c["id"], "name": c["name"], "department": c["department"],
            "location": {"lat": c["lat"], "lng": c["lon"]},
            "codec": c["codec"], "live": True,
            "stream": {"width": c["width"], "height": c["height"], "fps": c["fps"]},
            "urls": {
                "rtsp": f"rtsp://{host}:8554/stream/{c['id']}",
                "whep": f"http://{host}:8889/stream/{c['id']}/whep",
                "hls": f"http://{host}:8888/stream/{c['id']}/index.m3u8",
            },
        })
    return out


def serve_catalogue(port: int = 8090) -> None:
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.rstrip("/") != "/api/ingest":
                self.send_error(404); return
            body = json.dumps(catalogue()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers(); self.wfile.write(body)

        def log_message(self, *a):
            pass

    print(f"catalogue on http://127.0.0.1:{port}/api/ingest")
    HTTPServer(("127.0.0.1", port), H).serve_forever()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    {"clips": make_clips, "config": write_config, "catalogue": serve_catalogue}.get(
        cmd, lambda: print(__doc__))()
