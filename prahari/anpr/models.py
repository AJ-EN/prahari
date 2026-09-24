"""
Model registry for the ANPR pipeline. All weights live under <repo>/models/
(gitignored). Nothing is fetched to ~/.cache.

Stack: the open-source `fast-alpr` family, used at the component level
  * detector  open-image-models YOLOv9-tiny plate detector, ONNX, end-to-end NMS
  * OCR       fast-plate-ocr CCT ("compact convolutional transformer") global
              model, ONNX, 128x64 RGB input, 10 fixed character slots,
              alphabet 0-9A-Z. Trained on 65+ countries; India is NOT in its
              region list, so everything Indian-specific (two-line split,
              grammar repair) is done by us on top of it.

Sizes measured on disk (bytes):
  yolo-v9-t-384-license-plates-end2end.onnx   7,771,218
  yolo-v9-t-640-license-plates-end2end.onnx   (same weights, 640 input)
  cct_xs_v2_global.onnx                        3,344,292
  cct_s_v2_global.onnx                         5,262,230

Download:  .venv/bin/python -m prahari.anpr.models
"""
from __future__ import annotations

import shutil
import sys
import urllib.request
from pathlib import Path

from prahari.common.diskguard import ROOT

MODELS_DIR = ROOT / "models"

_DET = "https://github.com/ankandrew/open-image-models/releases/download/assets"
_OCR = "https://github.com/ankandrew/cnn-ocr-lp/releases/download/arg-plates"

# name -> list of (filename, url)
DETECTORS: dict[str, list[tuple[str, str]]] = {
    "yolo-v9-t-384": [("yolo-v9-t-384-license-plates-end2end.onnx",
                       f"{_DET}/yolo-v9-t-384-license-plates-end2end.onnx")],
    "yolo-v9-t-512": [("yolo-v9-t-512-license-plates-end2end.onnx",
                       f"{_DET}/yolo-v9-t-512-license-plates-end2end.onnx")],
    "yolo-v9-t-640": [("yolo-v9-t-640-license-plates-end2end.onnx",
                       f"{_DET}/yolo-v9-t-640-license-plates-end2end.onnx")],
}
OCRS: dict[str, list[tuple[str, str]]] = {
    "cct-xs-v2-global": [("cct_xs_v2_global.onnx", f"{_OCR}/cct_xs_v2_global.onnx"),
                         ("cct_xs_v2_global_plate_config.yaml",
                          f"{_OCR}/cct_xs_v2_global_plate_config.yaml")],
    "cct-s-v2-global": [("cct_s_v2_global.onnx", f"{_OCR}/cct_s_v2_global.onnx"),
                        ("cct_s_v2_global_plate_config.yaml",
                         f"{_OCR}/cct_s_v2_global_plate_config.yaml")],
}

DEFAULT_DETECTOR = "yolo-v9-t-384"
DEFAULT_OCR = "cct-xs-v2-global"

MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024   # project rule: stop and ask above ~100 MB


def _download(url: str, dest: Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as r:
        size = int(r.headers.get("Content-Length", 0))
        if size > MAX_DOWNLOAD_BYTES:
            raise RuntimeError(f"{url} is {size / 1e6:.0f} MB, over the download limit")
        with open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
    tmp.rename(dest)


def ensure(files: list[tuple[str, str]], download: bool = True) -> list[Path]:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for fname, url in files:
        p = MODELS_DIR / fname
        if not p.exists():
            if not download:
                raise FileNotFoundError(f"{p} missing; run: .venv/bin/python -m prahari.anpr.models")
            print(f"downloading {fname} ...", file=sys.stderr)
            _download(url, p)
        out.append(p)
    return out


def detector_path(name: str = DEFAULT_DETECTOR, download: bool = True) -> Path:
    return ensure(DETECTORS[name], download)[0]


def ocr_paths(name: str = DEFAULT_OCR, download: bool = True) -> tuple[Path, Path]:
    onnx, cfg = ensure(OCRS[name], download)
    return onnx, cfg


def available() -> bool:
    try:
        detector_path(download=False)
        ocr_paths(download=False)
        return True
    except FileNotFoundError:
        return False


if __name__ == "__main__":
    detector_path()
    ocr_paths()
    for p in sorted(MODELS_DIR.iterdir()):
        print(f"{p.stat().st_size:>12,d}  {p.name}")
