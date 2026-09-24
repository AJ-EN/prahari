"""
`python run.py doctor` — checks this computer and the camera link, and says in
plain words what is wrong and how to fix it. Safe to run any time; changes
nothing except downloading the plate-reading models (~11 MB) if missing.
"""
from __future__ import annotations

import importlib
import platform
import sys
import time

OK, WARN, FAIL = "  ✓", "  !", "  ✗"
_fails = 0


def say(mark: str, msg: str, fix: str = "") -> None:
    global _fails
    if mark == FAIL:
        _fails += 1
    print(f"{mark} {msg}")
    if fix:
        print(f"      → {fix}")


def section(title: str) -> None:
    print(f"\n{title}")


def check_python() -> None:
    section("1. This computer")
    v = sys.version_info
    say(OK if v >= (3, 10) else FAIL, f"Python {platform.python_version()} on {platform.system()} "
        f"{platform.machine()}", "" if v >= (3, 10) else "Install Python 3.12 from python.org")
    missing = []
    for mod, pkg in [("fastapi", "fastapi"), ("uvicorn", "uvicorn"), ("httpx", "httpx"),
                     ("numpy", "numpy"), ("cv2", "opencv-python-headless"), ("av", "av"),
                     ("onnxruntime", "onnxruntime"), ("fast_plate_ocr", "fast-alpr"),
                     ("PIL", "pillow")]:
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(pkg)
    if missing:
        say(FAIL, "Missing packages: " + ", ".join(missing),
            "pip install -r requirements.txt")
    else:
        say(OK, "All Python packages installed")
    try:
        import onnxruntime as ort
        prov = ort.get_available_providers()
        accel = [p for p in prov if p in ("CUDAExecutionProvider", "CoreMLExecutionProvider")]
        say(OK, "Plate reader will use: " + (", ".join(accel) + " + CPU" if accel else "CPU only"),
            "" if accel else "Fine for ~20 cameras at 1 frame/s. An NVIDIA GPU + "
                             "`pip install onnxruntime-gpu` handles many more.")
    except Exception:
        pass
    from prahari.common import diskguard
    free_gb = diskguard.free_bytes() / 1024 ** 3
    say(OK if diskguard.can_write() else FAIL, f"Free disk: {free_gb:.1f} GB",
        "" if diskguard.can_write() else "Free up space: PRAHARI stops saving below 3 GB.")


def check_models() -> None:
    section("2. Plate-reading models")
    try:
        from prahari.anpr import models
        paths = [models.detector_path(download=True), *models.ocr_paths(download=True)]
        size = sum(p.stat().st_size for p in paths if p.exists()) / 1024 ** 2
        say(OK, f"Models ready ({size:.0f} MB in models/)")
    except Exception as e:
        say(FAIL, f"Could not get the models: {e}",
            "Needs internet once, to download ~11 MB. Check your connection and rerun.")
        return
    try:
        import random

        from prahari.anpr.pipeline import PipelineConfig, PlatePipeline
        from prahari.anpr.synth import make_scene
        from prahari.common.contracts import FrameSample
        p = PlatePipeline(PipelineConfig(save_evidence=False))
        sc = make_scene(random.Random(3), width=1280, plate="GJ01AB1234", two_line=False,
                        plate_px=44)
        img = sc.image
        fs = FrameSample("doctor", 0, 0.0, time.time(), img, img.shape[1], img.shape[0])
        p.process(fs)
        t0 = time.perf_counter()
        evs = p.process(fs)
        ms = (time.perf_counter() - t0) * 1000
        got = [e.plate or e.raw_text for e in evs]
        if "GJ01AB1234" in got:
            say(OK, f"Test plate read correctly: GJ01AB1234 ({ms:.0f} ms per frame)")
        else:
            say(WARN, f"Test plate read as {got or 'nothing'} ({ms:.0f} ms per frame)",
                "The reader runs but misread a clean test plate; results on real cameras "
                "will be weaker. Report this.")
    except Exception as e:
        say(FAIL, f"Plate reader failed to run: {type(e).__name__}: {e}",
            "pip install -r requirements.txt, then rerun doctor")


def check_database() -> None:
    section("3. Database")
    try:
        from prahari.registry.db import Store
        from prahari.settings import Settings
        s = Settings.load()
        st = Store(s.db or None)
        c = st.counts()
        say(OK, f"Database OK at {st.path} — " + ", ".join(f"{k} {v}" for k, v in c.items()))
    except Exception as e:
        say(FAIL, f"Database problem: {e}", "Check the DB= line in prahari.env and folder permissions")


def check_cameras() -> None:
    section("4. Camera link")
    from prahari.settings import ENV_FILE, Settings
    s = Settings.load()
    if not ENV_FILE.exists():
        say(FAIL, "No prahari.env file yet",
            "Copy prahari.env.example to prahari.env and put the catalogue URL on INGEST_URL=")
        return
    if not s.ingest_url or "REPLACE-WITH-HOST" in s.ingest_url:
        say(FAIL, "INGEST_URL is not set in prahari.env",
            "Paste the portal's catalogue URL, e.g. INGEST_URL=http://<host>/api/ingest")
        return
    from prahari.node.catalogue import fetch_catalogue
    try:
        cams = fetch_catalogue(s.ingest_url)
    except Exception as e:
        say(FAIL, f"Can't read the catalogue at {s.ingest_url}: {type(e).__name__}: {e}",
            "Open that URL in a browser on this computer. If it asks for login, set "
            "INGEST_TOKEN. If it doesn't load, the network/VPN is the problem, not PRAHARI.")
        return
    if not cams:
        say(FAIL, "The catalogue loaded but listed no cameras",
            "Open the URL in a browser and send the JSON to the developers — the format may differ.")
        return
    live = [c for c in cams if c.live]
    with_url = [c for c in cams if c.rtsp_url or c.hls_url]
    no_loc = [c for c in cams if c.lat is None]
    say(OK, f"Catalogue OK: {len(cams)} cameras, {len(live)} marked live, "
        f"{len(with_url)} with a stream URL")
    if no_loc:
        say(WARN, f"{len(no_loc)} cameras have no location, so they won't appear on the map",
            "Add locations via Registry → Import CSV if you have them")
    for c in cams[:3]:
        print(f"      e.g. id={c.id!r} name={c.name!r} codec={c.codec or '?'} "
              f"url={(c.rtsp_url or c.hls_url)[:60]}")

    import av
    tried = 0
    for c in live:
        url = c.rtsp_url or c.hls_url
        if not url or tried >= 2:
            continue
        tried += 1
        opts = {"rtsp_transport": "tcp"} if url.startswith("rtsp") else {}
        t0 = time.time()
        try:
            with av.open(url, options=opts, timeout=(10, 10)) as ct:
                v = ct.streams.video[0]
                n, first, last = 0, None, None
                for fr in ct.decode(v):
                    if fr.pts is not None:
                        ts = float(fr.pts * v.time_base)
                        first = ts if first is None else first
                        last = ts
                    n += 1
                    if time.time() - t0 > 6:
                        break
                fps = (n - 1) / (last - first) if last and first is not None and last > first else 0
                say(OK, f"Camera {c.id}: opened, {v.codec_context.name} "
                        f"{v.codec_context.width}x{v.codec_context.height}, ~{fps:.1f} fps measured")
        except Exception as e:
            say(FAIL, f"Camera {c.id}: could not open the stream: {type(e).__name__}: {e}",
                "Port 8554 may be blocked on this network — try another network, or ask the "
                "organisers. PRAHARI forces RTSP over TCP, as their guide requires.")


def main() -> int:
    print("PRAHARI doctor — checking everything. This takes about 20 seconds.")
    check_python()
    check_models()
    check_database()
    check_cameras()
    print()
    if _fails:
        print(f"{_fails} problem(s) found. Fix the ✗ lines above (each has a → fix), then rerun.")
        return 1
    print("All good. Start with:  python run.py   (or practice first:  python run.py demo)")
    return 0
