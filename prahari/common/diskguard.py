"""
Disk budget for everything PRAHARI writes.

The dev machine has single-digit gigabytes free, so nothing in this project is
allowed to grow without a ceiling:

  * No raw video is ever stored. Frames live in memory only.
  * Evidence crops (small JPEGs) go under data/evidence with a hard size cap;
    the oldest are deleted first when the cap is reached.
  * All writers call `can_write()` first and stop writing, loudly, when free
    space on the volume drops below FLOOR_BYTES.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"

FLOOR_BYTES = int(os.environ.get("PRAHARI_DISK_FLOOR_MB", "3072")) * 1024 * 1024
EVIDENCE_CAP_BYTES = int(os.environ.get("PRAHARI_EVIDENCE_CAP_MB", "300")) * 1024 * 1024


def free_bytes(path: Path = ROOT) -> int:
    return shutil.disk_usage(path).free


def can_write(path: Path = ROOT) -> bool:
    """False when the volume is below the safety floor. Callers must skip the write."""
    return free_bytes(path) > FLOOR_BYTES


def dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def enforce_cap(path: Path, cap_bytes: int = EVIDENCE_CAP_BYTES) -> int:
    """Delete oldest files under `path` until it fits under `cap_bytes`.
    Returns the number of files removed."""
    if not path.exists():
        return 0
    files = sorted((f for f in path.rglob("*") if f.is_file()), key=lambda f: f.stat().st_mtime)
    total = sum(f.stat().st_size for f in files)
    removed = 0
    for f in files:
        if total <= cap_bytes:
            break
        total -= f.stat().st_size
        f.unlink(missing_ok=True)
        removed += 1
    return removed


def report() -> str:
    gb = 1024 ** 3
    return (f"free {free_bytes() / gb:.1f} GB (floor {FLOOR_BYTES / gb:.1f} GB) | "
            f"project data {dir_size(DATA) / 1024**2:.0f} MB "
            f"(evidence cap {EVIDENCE_CAP_BYTES / 1024**2:.0f} MB)")


if __name__ == "__main__":
    print(report())
