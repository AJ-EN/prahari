"""
Stability harness for the ingest spine.

    python -m prahari.node.stability --catalogue URL --seconds N [--keyframes-only]

Runs every live catalogue camera through NodeManager, prints a compact table every
--interval seconds, writes a small summary to data/stability-<timestamp>-<mode>-<pid>.json and
exits non-zero if any selected camera never went live. Frames are dropped on the
floor (only counted); nothing but the summary JSON touches the disk.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import resource
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from prahari.node.capture import CaptureConfig
from prahari.node.manager import NodeManager

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"


def rss_mb(pid: int | None = None) -> float | None:
    try:
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid or os.getpid())],
                             capture_output=True, text=True, timeout=5).stdout.strip()
        return round(int(out) / 1024, 1) if out else None
    except Exception:
        return None


def cpu_seconds() -> float:
    r = resource.getrusage(resource.RUSAGE_SELF)
    return r.ru_utime + r.ru_stime


def fmt(v, w: int, nd: int = 1) -> str:
    if v is None:
        s = "-"
    elif isinstance(v, float):
        s = f"{v:.{nd}f}"
    else:
        s = str(v)
    return s[:w].rjust(w)


def table(snap: dict, elapsed: float, cpu_pct: float | None, rss: float | None) -> str:
    t = snap["totals"]
    lines = [f"--- t={elapsed:6.0f}s  live {t['live']}/{t['running']}  cpu {fmt(cpu_pct, 5)}%  rss {fmt(rss, 6)} MB  "
             f"reconn {t['reconnects']}  disc {t['discontinuities']}  warn {t['warnings']}  "
             f"catalogue ok/fail {snap['catalogue']['ok']}/{snap['catalogue']['failures']}",
             f"{'cam':>6} {'state':>10} {'codec':>5} {'size':>9} {'decl':>5} {'meas':>6} "
             f"{'dec':>7} {'emit':>6} {'reconn':>6} {'disc':>5} {'warn':>5} {'err':>4} {'age':>5}  last_error"]
    for c in sorted(snap["cameras"], key=lambda c: (len(c["id"]), c["id"])):
        size = f"{c['size'][0]}x{c['size'][1]}" if c["size"] else "-"
        lines.append(
            f"{fmt(c['id'], 6)} {fmt(c['state'], 10)} {fmt(c['codec'], 5)} {fmt(size, 9)} "
            f"{fmt(c['declared_fps'], 5, 0)} {fmt(c['measured_fps'], 6, 2)} {fmt(c['frames_decoded'], 7)} "
            f"{fmt(c['frames_emitted'], 6)} {fmt(c['reconnects'], 6)} {fmt(c['discontinuities'], 5)} "
            f"{fmt(c['warnings'], 5)} {fmt(c['decode_errors'], 4)} {fmt(c['last_frame_age_s'], 5)}  "
            f"{'' if c['state'] == 'live' else (c['last_error'] or '')[:50]}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalogue", default=os.environ.get("PRAHARI_INGEST_URL", "http://127.0.0.1:8090/api/ingest"))
    ap.add_argument("--seconds", type=float, default=180)
    ap.add_argument("--keyframes-only", action="store_true")
    ap.add_argument("--target-fps", type=float, default=5.0)
    ap.add_argument("--max-width", type=int, default=960)
    ap.add_argument("--interval", type=float, default=10.0)
    ap.add_argument("--poll", type=float, default=60.0, help="catalogue poll period, s")
    ap.add_argument("--cameras", default="", help="comma-separated allowlist of camera ids")
    ap.add_argument("--max-cameras", type=int, default=None)
    ap.add_argument("--decoder-threads", type=int, default=1)
    ap.add_argument("--out", default=str(DATA), help="directory for the summary JSON")
    ap.add_argument("--quiet-events", action="store_true", help="do not print epoch events")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = CaptureConfig(keyframes_only=a.keyframes_only, target_fps=a.target_fps,
                        max_width=a.max_width, decoder_threads=a.decoder_threads)

    events: list[dict] = []
    ev_lock = threading.Lock()
    t0 = time.time()

    def on_disc(cam_id: str, epoch: int, reason: str) -> None:
        with ev_lock:
            if len(events) < 2000:
                events.append({"t": round(time.time() - t0, 2), "camera": cam_id, "epoch": epoch, "reason": reason})
        if not a.quiet_events:
            print(f"  [event t={time.time() - t0:6.1f}s] camera {cam_id}: {reason} -> epoch {epoch}", flush=True)

    mgr = NodeManager(a.catalogue, cfg, poll_s=a.poll, on_discontinuity=on_disc,
                      camera_ids=[c.strip() for c in a.cameras.split(",") if c.strip()] or None,
                      max_cameras=a.max_cameras)
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    print(f"stability: catalogue={a.catalogue} seconds={a.seconds:.0f} mode="
          f"{'keyframes-only' if a.keyframes_only else f'full@{a.target_fps}fps'} max_width={a.max_width} "
          f"pid={os.getpid()}", flush=True)
    mgr.start()
    samples: list[dict] = []
    prev_cpu, prev_wall = cpu_seconds(), time.time()
    rss_peak = 0.0
    snap = mgr.snapshot()
    deadline = t0 + a.seconds
    while not stop.is_set() and time.time() < deadline:
        stop.wait(min(a.interval, max(0.0, deadline - time.time())))
        now, cpu = time.time(), cpu_seconds()
        cpu_pct = 100.0 * (cpu - prev_cpu) / max(1e-6, now - prev_wall)
        prev_cpu, prev_wall = cpu, now
        rss = rss_mb()
        rss_peak = max(rss_peak, rss or 0.0)
        snap = mgr.snapshot()
        samples.append({"t": round(now - t0, 1), "cpu_pct": round(cpu_pct, 1), "rss_mb": rss,
                        "live": snap["totals"]["live"], "running": snap["totals"]["running"]})
        print(table(snap, now - t0, cpu_pct, rss), flush=True)

    elapsed = time.time() - t0
    total_cpu = cpu_seconds()
    snap = mgr.snapshot()
    mgr.stop()

    cams = []
    for c in snap["cameras"]:
        cams.append({k: c[k] for k in ("id", "state", "ever_live", "codec", "size", "declared_fps", "measured_fps",
                                       "frames_decoded", "frames_emitted", "reconnects", "discontinuities",
                                       "warnings", "warning_top", "transport_logs", "transport_top", "decode_errors", "callback_errors",
                                       "last_error", "epoch")}
                    | {"emit_rate": round(c["frames_emitted"] / max(1.0, elapsed), 2)})
    never_live = [c["id"] for c in cams if not c["ever_live"]]
    steady = [s for s in samples if s["t"] > 20] or samples
    summary = {
        "started_at": t0, "seconds": round(elapsed, 1),
        "mode": "keyframes-only" if a.keyframes_only else "full", "target_fps": a.target_fps,
        "max_width": a.max_width, "catalogue": snap["catalogue"],
        "process": {
            "cpu_pct_avg": round(100.0 * total_cpu / max(1e-6, elapsed), 1),
            "cpu_pct_steady_avg": round(sum(s["cpu_pct"] for s in steady) / max(1, len(steady)), 1),
            "rss_mb_last": samples[-1]["rss_mb"] if samples else rss_mb(),
            "rss_mb_peak": rss_peak or rss_mb(),
            "ncpu": os.cpu_count(),
        },
        "totals": snap["totals"],
        "never_live": never_live,
        "cameras": cams,
        "events": events[:500],
        "samples": samples[-60:],
    }
    out_dir = Path(a.out)
    path = None
    try:
        from prahari.common.diskguard import can_write
        ok_to_write = can_write(out_dir if out_dir.exists() else ROOT)
    except Exception:
        ok_to_write = True
    if ok_to_write:
        out_dir.mkdir(parents=True, exist_ok=True)
        mode = "kf" if a.keyframes_only else f"full{a.target_fps:g}"
        path = out_dir / f"stability-{time.strftime('%Y%m%d-%H%M%S', time.localtime(t0))}-{mode}-{os.getpid()}.json"
        path.write_text(json.dumps(summary, indent=1, default=str))
    else:
        print("disk below safety floor: summary not written", file=sys.stderr)

    p = summary["process"]
    print(f"\nsummary: {len(cams)} cameras, never live: {never_live or 'none'}; cpu avg {p['cpu_pct_avg']}% "
          f"(steady {p['cpu_pct_steady_avg']}%, {p['ncpu']} cores = {100 * p['ncpu']}%), rss last "
          f"{p['rss_mb_last']} MB peak {p['rss_mb_peak']} MB; reconnects {snap['totals']['reconnects']}, "
          f"discontinuities {snap['totals']['discontinuities']}, warnings {snap['totals']['warnings']}"
          + (f"\nwrote {path}" if path else ""), flush=True)
    if not cams:
        print("no cameras were started (catalogue empty or unreachable)", file=sys.stderr)
        return 2
    return 1 if never_live else 0


if __name__ == "__main__":
    sys.exit(main())
