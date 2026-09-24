"""
Practice grid for `python run.py demo`: eight cameras along one road in
Gandhinagar, with real-looking Indian number plates, so a new user sees the
whole system work end to end (plates read, watchlist alert, route traced)
before touching the real feeds.

The script: a stolen white Swift, GJ01AB1234 (on the sample watchlist), drives
past cameras 1 -> 2 -> 3 -> 4, about nine seconds apart. Cameras are ~150 m
apart, so that is ~60 km/h. A second listed vehicle, GJ18BD6612, passes
cameras 2 and 4. Other traffic is random. Camera 7 is a hospital corridor and
camera 8 a bus depot, so not every camera is a plate camera.

HONEST NOTE: this is synthetic video. Plates are clean and well lit; real
CCTV is much harder. It exists to prove the plumbing, not the accuracy.

Clips: 960x540, 10 fps, 40 s, loop forever. ~15 MB for all eight.
"""
from __future__ import annotations

import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2
import numpy as np

from prahari.anpr.synth import random_plate_text, render_plate

HERE = Path(__file__).resolve().parent
OUT = HERE / "demo"
W, H, FPS, SECONDS = 960, 540, 10, 40

# Along Ch-Road towards Sector 7, ~150 m apart.
BASE_LAT, BASE_LON, STEP = 23.2156, 72.6369, 0.00135
CAMERAS = [
    {"id": str(i + 1), "name": f"Ch-Road junction {i + 1}", "department": "Police",
     "lat": round(BASE_LAT + i * STEP, 6), "lon": round(BASE_LON + i * STEP * 0.6, 6),
     "kind": "road"} for i in range(6)
] + [
    {"id": "7", "name": "Civil Hospital OPD corridor", "department": "Health",
     "lat": 23.2201, "lon": 72.6352, "kind": "hall"},
    {"id": "8", "name": "GSRTC Gandhinagar depot", "department": "GSRTC",
     "lat": 23.2222, "lon": 72.6410, "kind": "depot"},
]

TARGET = "GJ01AB1234"
SECOND = "GJ18BD6612"
SCRIPT = {  # camera id -> [(plate, enter_second, colour BGR)]
    "1": [(TARGET, 4.0, (235, 235, 235))],
    "2": [(TARGET, 13.0, (235, 235, 235)), (SECOND, 27.0, (190, 190, 195))],
    "3": [(TARGET, 22.0, (235, 235, 235))],
    "4": [(TARGET, 31.0, (235, 235, 235)), (SECOND, 18.0, (190, 190, 195))],
}
COLOURS = [(40, 40, 170), (160, 90, 30), (30, 30, 30), (60, 130, 60), (200, 200, 200), (20, 90, 200)]
CROSS_S = 4.0          # seconds to cross the frame


def background(cam: dict) -> np.ndarray:
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = (120, 110, 100)
    if cam["kind"] == "road":
        img[: H // 3] = (170, 150, 120)                       # buildings/sky band
        for x in range(0, W, 90):
            cv2.rectangle(img, (x + 8, 40), (x + 70, H // 3), (140, 130, 115), -1)
        img[H // 3:] = (85, 85, 85)                            # road
        for x in range(0, W, 120):
            cv2.rectangle(img, (x, H // 3 + 150), (x + 60, H // 3 + 158), (220, 220, 220), -1)
    elif cam["kind"] == "hall":
        img[:] = (170, 175, 180)
        pts = np.array([[80, H], [W - 80, H], [W // 2 + 120, 180], [W // 2 - 120, 180]], np.int32)
        cv2.fillPoly(img, [pts], (120, 125, 130))
    else:
        img[:] = (95, 100, 105)
        cv2.rectangle(img, (0, H - 120), (W, H), (70, 70, 70), -1)
    cv2.putText(img, f"CAM {cam['id']}  {cam['name']}", (16, 30), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, (255, 255, 255), 2, cv2.LINE_AA)
    return img


def draw_car(frame: np.ndarray, x: int, y: int, colour, plate_img: np.ndarray) -> None:
    cw, ch = 300, 170
    cv2.rectangle(frame, (x, y), (x + cw, y + ch), colour, -1)
    cv2.rectangle(frame, (x + 40, y + 12), (x + cw - 40, y + 70), (60, 60, 60), -1)   # rear window
    cv2.rectangle(frame, (x + 10, y + 95), (x + 50, y + 115), (40, 40, 200), -1)       # tail lights
    cv2.rectangle(frame, (x + cw - 50, y + 95), (x + cw - 10, y + 115), (40, 40, 200), -1)
    ph, pw = plate_img.shape[:2]
    px, py = x + (cw - pw) // 2, y + ch - ph - 14
    x0, y0 = max(px, 0), max(py, 0)
    x1, y1 = min(px + pw, W), min(py + ph, H)
    if x1 > x0 and y1 > y0:
        frame[y0:y1, x0:x1] = plate_img[y0 - py:y1 - py, x0 - px:x1 - px]


def schedule(cam: dict, rng: random.Random) -> list[tuple[str, float, tuple]]:
    if cam["kind"] != "road":
        return []
    items = list(SCRIPT.get(cam["id"], []))
    t = 1.0
    while t < SECONDS - CROSS_S:
        if all(abs(t - s[1]) > CROSS_S + 0.5 for s in items):
            items.append((random_plate_text(rng), t, rng.choice(COLOURS)))
        t += rng.uniform(5.0, 8.0)
    return items


def render_clip(cam: dict, out: Path, seed: int) -> None:
    rng = random.Random(seed)
    bg = background(cam)
    cars = [(p, t0, c, render_plate(p, height=38, rng=random.Random(hash(p) & 0xFFFF)))
            for p, t0, c in schedule(cam, rng)]
    enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "26"] if int(cam["id"]) % 2 else \
          ["-c:v", "libx265", "-preset", "veryfast", "-crf", "28", "-tag:v", "hvc1",
           "-x265-params", "log-level=error"]
    ff = subprocess.Popen(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
                           "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           *enc, "-g", str(FPS * 2), "-pix_fmt", "yuv420p", str(out)],
                          stdin=subprocess.PIPE)
    for f in range(SECONDS * FPS):
        t = f / FPS
        frame = bg.copy()
        for plate, t0, colour, pimg in cars:
            if t0 <= t <= t0 + CROSS_S:
                x = int(-300 + (W + 300) * (t - t0) / CROSS_S)
                draw_car(frame, x, 300, colour, pimg)
        if cam["kind"] == "hall":                      # people walking
            for k in range(3):
                px = int((t * 40 + k * 300) % W)
                cv2.circle(frame, (px, 300), 14, (60, 50, 40), -1)
                cv2.rectangle(frame, (px - 12, 316), (px + 12, 390), (80, 60, 50), -1)
        elif cam["kind"] == "depot":
            cv2.rectangle(frame, (60, 250), (560, 420), (40, 120, 190), -1)
            for k in range(12):
                cv2.circle(frame, (620 + (k % 6) * 45, 330 + (k // 6) * 50 + int(8 * np.sin(t + k))),
                           10, (50, 40, 30), -1)
        ff.stdin.write(frame.tobytes())
    ff.stdin.close()
    ff.wait()


def build(force: bool = False) -> Path:
    OUT.mkdir(exist_ok=True)
    for i, cam in enumerate(CAMERAS):
        out = OUT / f"cam{int(cam['id']):02d}.mp4"
        if out.exists() and not force:
            continue
        render_clip(cam, out, seed=100 + i)
        print(f"  made {out.name}  ({out.stat().st_size // 1024} KB)  {cam['name']}")
    return OUT


def catalogue(host: str = "127.0.0.1", rtsp_port: int = 8554) -> list[dict]:
    return [{"id": c["id"], "name": c["name"], "department": c["department"],
             "location": {"lat": c["lat"], "lng": c["lon"]}, "codec": "h264" if int(c["id"]) % 2 else "h265",
             "live": True, "stream": {"width": W, "height": H, "fps": FPS},
             "urls": {"rtsp": f"rtsp://{host}:{rtsp_port}/stream/{c['id']}"}} for c in CAMERAS]


if __name__ == "__main__":
    build(force=True)
