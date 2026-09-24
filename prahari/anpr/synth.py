"""
Synthetic Indian number plates and scenes, for testing without real footage.

HONESTY NOTE: these are much easier than real CCTV. The plates are clean,
fronto-parallel-ish, perfectly printed in a known font, with no HSRP glare,
no dirt, no hand-painted lettering, no motion blur from a 1/50 s shutter, no
H.264 macroblocking and no night-time IR bloom. Numbers measured on this set
are an upper bound on what the pipeline does in the field, and are useful
mainly to catch regressions and to test the plumbing (two-line split,
grammar correction, dedup, evidence crops).

Layouts rendered
----------------
  single line  "GJ 01 AB 1234"            ~500x120 mm, aspect ~4.2
  two line     "GJ 01" / "AB 1234"        ~285x200 mm (two-wheeler), aspect ~1.4-1.8

Both carry the blue "IND" strip on the left, as on HSRP plates.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from prahari.common.plate_grammar import MAX_RTO_DISTRICT

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf",
    "/System/Library/Fonts/Supplemental/DIN Condensed Bold.ttf",
    "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]

# Series letters: Indian RTOs avoid I and O in series to limit confusion.
SERIES_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"

# Deployment-weighted state mix: mostly Gujarat, some neighbours.
STATE_MIX = ["GJ"] * 12 + ["MH", "RJ", "MP", "DL", "KA", "UP", "HR", "TN"]


def available_fonts() -> list[str]:
    return [f for f in FONT_CANDIDATES if Path(f).exists()]


@lru_cache(maxsize=64)
def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def random_plate_text(rng: random.Random) -> str:
    """A grammatically valid plate string, e.g. GJ01AB1234 / GJ05C0987."""
    state = rng.choice(STATE_MIX)
    district = rng.randint(1, min(MAX_RTO_DISTRICT.get(state, 20), 39))
    series = "".join(rng.choice(SERIES_ALPHABET) for _ in range(rng.choice([1, 2, 2, 2])))
    number = f"{rng.randint(1, 9999):04d}"
    return f"{state}{district:02d}{series}{number}"


def _split_text(plate: str) -> tuple[str, str, str, str]:
    state, district = plate[:2], plate[2:4]
    rest = plate[4:]
    series = "".join(c for c in rest if c.isalpha())
    number = rest[len(series):]
    return state, district, series, number


def _fit_font(draw: ImageDraw.ImageDraw, text: str, font_path: str,
              max_w: int, max_h: int) -> ImageFont.FreeTypeFont:
    size = max_h
    while size > 6:
        f = _font(font_path, size)
        l, t, r, b = draw.textbbox((0, 0), text, font=f)
        if (r - l) <= max_w and (b - t) <= max_h:
            return f
        size -= 2
    return _font(font_path, 6)


def _draw_centered(draw, box, text, font, fill=(0, 0, 0)):
    x0, y0, x1, y1 = box
    l, t, r, b = draw.textbbox((0, 0), text, font=font)
    x = x0 + (x1 - x0 - (r - l)) / 2 - l
    y = y0 + (y1 - y0 - (b - t)) / 2 - t
    draw.text((x, y), text, font=font, fill=fill)


def render_plate(plate: str, two_line: bool = False, *, font_path: str | None = None,
                 height: int = 120, rng: random.Random | None = None) -> np.ndarray:
    """Render a plate as a BGR uint8 image. `height` is the plate height in px.

    Rendered at a fixed high resolution and then downsampled, which is closer
    to what a camera does than rasterising a tiny font directly."""
    rng = rng or random.Random(0)
    font_path = font_path or available_fonts()[0]
    aspect = rng.uniform(1.45, 1.75) if two_line else rng.uniform(4.0, 4.4)
    H = 200
    W = int(round(H * aspect))
    img = Image.new("RGB", (W, H), (250, 250, 250))
    d = ImageDraw.Draw(img)
    bw = max(1, H // 40)
    d.rectangle([bw, bw, W - 1 - bw, H - 1 - bw], outline=(10, 10, 10), width=max(1, bw))

    # Blue IND strip on the left.
    strip_w = int(W * (0.10 if two_line else 0.07))
    d.rectangle([2 * bw, 2 * bw, 2 * bw + strip_w, H - 1 - 2 * bw], fill=(20, 60, 170))
    ind_font = _fit_font(d, "IND", font_path, strip_w - 2, max(6, H // (4 if two_line else 5)))
    ind_box = (2 * bw, int(H * 0.6), 2 * bw + strip_w, H - 3 * bw)
    _draw_centered(d, ind_box, "IND", ind_font, fill=(240, 240, 240))

    state, district, series, number = _split_text(plate)
    x0 = 2 * bw + strip_w + max(2, W // 60)
    x1 = W - 3 * bw - max(2, W // 60)
    if two_line:
        top = f"{state} {district}"
        bot = f"{series} {number}"
        pad = int(H * 0.06)
        mid = H // 2
        ft = _fit_font(d, bot, font_path, x1 - x0, mid - 2 * pad)
        _draw_centered(d, (x0, pad, x1, mid - pad // 2), top, ft)
        _draw_centered(d, (x0, mid + pad // 2, x1, H - pad), bot, ft)
    else:
        text = f"{state} {district} {series} {number}"
        pad = int(H * 0.14)
        f = _fit_font(d, text, font_path, x1 - x0, H - 2 * pad)
        _draw_centered(d, (x0, pad, x1, H - pad), text, f)

    out = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
    th = max(8, int(height))
    tw = max(8, int(round(th * aspect)))
    interp = cv2.INTER_AREA if th < H else cv2.INTER_LINEAR
    return cv2.resize(out, (tw, th), interpolation=interp)


@dataclass
class SceneSample:
    image: np.ndarray                    # BGR
    plate: str                           # ground truth
    two_line: bool
    bbox: tuple[int, int, int, int]      # x, y, w, h of the plate in the scene
    plate_px: int                        # rendered plate height in px
    vehicle: str = "car"                 # "car" | "bike" context drawn around it


def _background(w: int, h: int, rng: random.Random) -> np.ndarray:
    """Road-ish backdrop: vertical gradient plus a few low-contrast blocks."""
    base = rng.randint(70, 150)
    grad = np.linspace(0.75, 1.15, h, dtype=np.float32)[:, None, None]
    bg = np.clip(base * grad * np.ones((h, w, 3), np.float32), 0, 255).astype(np.uint8)
    for _ in range(rng.randint(2, 6)):
        c = tuple(int(np.clip(base + rng.randint(-40, 40), 0, 255)) for _ in range(3))
        x, y = rng.randint(0, w - 1), rng.randint(0, h - 1)
        cv2.rectangle(bg, (x, y), (x + rng.randint(20, w // 4), y + rng.randint(10, h // 5)), c, -1)
    for _ in range(rng.randint(0, 2)):   # lane markings
        cv2.line(bg, (rng.randint(0, w), h), (rng.randint(0, w), rng.randint(h // 2, h)),
                 (210, 210, 210), rng.randint(2, 5))
    return bg


def _draw_vehicle(img: np.ndarray, px: int, py: int, pw: int, ph: int,
                  bike: bool, rng: random.Random) -> None:
    """Crude rear of a car / two-wheeler around the plate location: body,
    tail lights, dark bumper band and a dark plate holder. Plate detectors
    lean on this context; without it they under-fire badly (measured)."""
    H, W = img.shape[:2]
    body = tuple(rng.randint(20, 230) for _ in range(3))
    if bike:       # narrow two-wheeler rear: mudguard + tail light above plate
        bx1, bx2 = px - pw // 2, px + pw + pw // 2
        by1, by2 = py - 3 * ph, py + ph + ph // 2
        cv2.rectangle(img, (max(0, bx1), max(0, by1)), (min(W, bx2), min(H, by2)), body, -1)
        cv2.circle(img, (px + pw // 2, max(0, py - ph // 2)), max(3, ph // 4), (30, 30, 210), -1)
        cv2.rectangle(img, (px + pw // 4, min(H - 1, by2)), (px + 3 * pw // 4, H - 1), (25, 25, 25), -1)
    else:          # car rear: wide body, two tail lights, bumper band below
        bx1, bx2 = px - int(pw * 1.3), px + pw + int(pw * 1.3)
        by1, by2 = py - 4 * ph, py + 2 * ph
        cv2.rectangle(img, (max(0, bx1), max(0, by1)), (min(W, bx2), min(H, by2)), body, -1)
        cv2.rectangle(img, (max(0, bx1 + pw // 4), max(0, by1 + ph // 2)),
                      (min(W, bx2 - pw // 4), max(0, by1 + 2 * ph)), (45, 45, 50), -1)   # rear glass
        for lx in (bx1 + pw // 5, bx2 - pw // 5 - pw // 3):
            cv2.rectangle(img, (max(0, lx), max(0, py - ph)), (min(W, lx + pw // 3), max(0, py)),
                          (30, 30, 200), -1)
        cv2.rectangle(img, (max(0, bx1), min(H - 1, py + ph + ph // 3)), (min(W, bx2), min(H, by2)),
                      (28, 28, 28), -1)
    b = max(2, ph // 10)
    cv2.rectangle(img, (max(0, px - b), max(0, py - b)), (min(W, px + pw + b), min(H, py + ph + b)),
                  (22, 22, 22), -1)


def make_scene(rng: random.Random, *, width: int = 960, plate: str | None = None,
               two_line: bool | None = None, plate_px: int | None = None,
               blur: bool = True, noise: bool = True, perspective: bool = True,
               jpeg_quality: int | None = 80, vehicle: str | None = None) -> SceneSample:
    """A 16:9 scene with one vehicle carrying one plate.

    Two-line plates go on a two-wheeler rear or (autos, commercial vehicles)
    a wide car-like rear, 50/50 unless `vehicle` is given.

    Default plate heights are chosen to resemble a well-placed ANPR-ish
    city camera: single-line 18-48 px and two-line 26-56 px at 960 wide,
    scaled with frame width."""
    h = int(width * 9 / 16)
    plate = plate or random_plate_text(rng)
    if two_line is None:
        two_line = rng.random() < 0.4
    if plate_px is None:
        k = width / 960
        lo, hi = (26, 56) if two_line else (18, 48)
        plate_px = int(rng.randint(lo, hi) * k)
    fonts = available_fonts()
    pimg = render_plate(plate, two_line, font_path=rng.choice(fonts), height=plate_px, rng=rng)
    ph, pw = pimg.shape[:2]

    img = _background(width, h, rng)
    margin_x, margin_y = int(pw * 1.6) + 2, 4 * ph + 2
    px = rng.randint(min(margin_x, width - pw - 1), max(min(margin_x, width - pw - 1), width - pw - margin_x))
    py = rng.randint(min(margin_y, h - ph - 1), max(min(margin_y, h - ph - 1), h - 2 * ph - 2))
    px = int(np.clip(px, 0, width - pw))
    py = int(np.clip(py, 0, h - ph))
    if vehicle is None:
        vehicle = ("bike" if rng.random() < 0.5 else "car") if two_line else "car"
    _draw_vehicle(img, px, py, pw, ph, vehicle == "bike", rng)

    if perspective:
        # Mild keystone/shear, as from a pole-mounted camera looking down.
        j = 0.06
        src = np.float32([[0, 0], [pw, 0], [pw, ph], [0, ph]])
        dst = np.float32([[rng.uniform(0, j) * pw, rng.uniform(0, j) * ph],
                          [pw - rng.uniform(0, j) * pw, rng.uniform(0, j) * ph],
                          [pw - rng.uniform(0, j) * pw, ph - rng.uniform(0, j) * ph],
                          [rng.uniform(0, j) * pw, ph - rng.uniform(0, j) * ph]])
        M = cv2.getPerspectiveTransform(src, dst)
        warped = cv2.warpPerspective(pimg, M, (pw, ph), borderValue=(0, 0, 0))
        mask = cv2.warpPerspective(np.full((ph, pw), 255, np.uint8), M, (pw, ph))
        roi = img[py:py + ph, px:px + pw]
        roi[mask > 0] = warped[mask > 0]
    else:
        img[py:py + ph, px:px + pw] = pimg

    if blur:
        k = rng.choice([3, 3, 5])
        img = cv2.GaussianBlur(img, (k, k), rng.uniform(0.5, 1.2))
    if noise:
        n = np.random.default_rng(rng.randint(0, 1 << 30)).normal(0, rng.uniform(2, 7), img.shape)
        img = np.clip(img.astype(np.float32) + n, 0, 255).astype(np.uint8)
    if jpeg_quality:
        ok, enc = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
        img = cv2.imdecode(enc, cv2.IMREAD_COLOR)

    return SceneSample(image=img, plate=plate, two_line=two_line,
                       bbox=(px, py, pw, ph), plate_px=ph, vehicle=vehicle)


def make_set(n: int, seed: int = 7, **kw) -> list[SceneSample]:
    rng = random.Random(seed)
    return [make_scene(rng, **kw) for _ in range(n)]


def save_samples(out_dir: Path, n: int = 8, seed: int = 11) -> list[Path]:
    """Write a few small sample JPEGs for human inspection (data/anpr-test)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, s in enumerate(make_set(n, seed=seed, width=960)):
        p = out_dir / f"synth_{i:02d}_{'2L' if s.two_line else '1L'}_{s.plate}.jpg"
        cv2.imwrite(str(p), s.image, [cv2.IMWRITE_JPEG_QUALITY, 80])
        paths.append(p)
    return paths


if __name__ == "__main__":
    from prahari.common.diskguard import DATA
    for p in save_samples(DATA / "anpr-test"):
        print(p)
