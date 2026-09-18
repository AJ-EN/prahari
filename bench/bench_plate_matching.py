"""
Quantify what grammar-constrained decoding + confusion-space matching buys us.

This is the benchmark whose headline number goes in the submission deck:

    naive `WHERE plate = ?`   vs   PRAHARI matching

We synthesise realistic OCR corruption over valid Indian plates, then measure
how many watchlist vehicles each strategy actually finds. Ground truth is known
exactly because we generate the plates ourselves, so recall and false-positive
rate are both measurable without any hand labelling.

Corruption model: characters are flipped to their well-attested OCR confusions
(O/0, I/1, B/8, S/5, G/6, Z/2 ...) at a configurable rate. This is what real
ANPR output looks like on Indian plates at night, at angle, or through dust.

Run:  .venv/bin/python bench/bench_plate_matching.py
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from prahari.common import plate_grammar as g   # noqa: E402

# The confusions a real OCR engine actually makes, as a flip table.
FLIPS: dict[str, list[str]] = {
    "0": ["O", "D", "Q"], "O": ["0", "D", "Q"],
    "1": ["I", "L", "T"], "I": ["1", "L"], "L": ["1", "I"],
    "8": ["B"], "B": ["8"],
    "5": ["S"], "S": ["5", "6"],
    "6": ["G", "5"], "G": ["6", "C", "0"],
    "2": ["Z"], "Z": ["2"],
    "4": ["A"], "A": ["4"],
    "7": ["T", "1"], "T": ["7", "1"],
    "9": ["G", "6"], "3": ["8"],
    "M": ["N"], "N": ["M"], "U": ["V"], "V": ["U"],
    "C": ["G", "O", "0"], "D": ["0", "O"],
}


def random_plate(rng: random.Random) -> str:
    """Generate a grammatically valid Indian plate, Gujarat-weighted
    (this is a Gujarat deployment, so the traffic mix should be too)."""
    state = "GJ" if rng.random() < 0.7 else rng.choice(
        ["MH", "RJ", "MP", "DL", "UP", "KA", "TN", "AP"]
    )
    district = rng.randint(1, g.MAX_RTO_DISTRICT.get(state, 30))
    series_len = rng.choices([1, 2, 3], weights=[0.15, 0.7, 0.15])[0]
    series = "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(series_len))
    number = f"{rng.randint(1, 9999):04d}"
    return f"{state}{district:02d}{series}{number}"


ALL_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def corrupt(plate: str, rate: float, rng: random.Random) -> str:
    """Apply realistic OCR corruption.

    IMPORTANT (honesty note): if we only ever applied confusions drawn from the
    same table the matcher scores with, this benchmark would be circular and
    would flatter the result. Real ANPR output also drops characters, inserts
    spurious ones, and occasionally returns a character with no relationship to
    the truth at all (heavy blur, partial occlusion, mud).

    So corruption is a mixture:
      70%  well-attested confusion flip   (the matcher anticipates these)
      12%  character DROP                 (it does not)
      10%  arbitrary wrong character      (it does not)
       8%  spurious character INSERT      (it does not)
    """
    out: list[str] = []
    for ch in plate:
        if rng.random() >= rate:
            out.append(ch)
            continue
        roll = rng.random()
        if roll < 0.70 and ch in FLIPS:
            out.append(rng.choice(FLIPS[ch]))
        elif roll < 0.82:
            continue                                  # drop
        elif roll < 0.92:
            out.append(rng.choice(ALL_CHARS))         # arbitrary garbage
        else:
            out.append(ch)
            out.append(rng.choice(ALL_CHARS))         # spurious insert
    return "".join(out)


def run(n_watchlist: int = 200, n_obs: int = 600, seed: int = 7) -> None:
    rng = random.Random(seed)

    watchlist_plates = set()
    while len(watchlist_plates) < n_watchlist:
        p = random_plate(rng)
        if g.is_valid(p):
            watchlist_plates.add(p)
    watchlist = {p: {"type": "stolen_vehicle"} for p in sorted(watchlist_plates)}
    wl_list = sorted(watchlist_plates)

    print("=" * 78)
    print("PLATE MATCHING BENCHMARK — naive exact match vs PRAHARI")
    print(f"watchlist: {len(watchlist)} plates   observations per rate: {n_obs}")
    print("=" * 78)
    print(f"{'OCR err':>8} | {'naive recall':>13} | {'PRAHARI alert':>14} "
          f"| {'PRAHARI +review':>16} | {'false alerts':>13}")
    print("-" * 78)

    for rate in (0.00, 0.05, 0.10, 0.15, 0.20, 0.30):
        naive_hits = prahari_alert = prahari_any = 0
        false_alerts = 0
        n_on = n_off = 0

        for _ in range(n_obs):
            # Half the traffic is on the watchlist, half is not. The half that
            # is not is what measures false alerts — a system that alerts on
            # everything is worse than useless in a control room.
            on_list = rng.random() < 0.5
            truth = rng.choice(wl_list) if on_list else random_plate(rng)
            if not on_list and truth in watchlist:
                continue
            observed = corrupt(truth, rate, rng)

            if on_list:
                n_on += 1
                if observed == truth:
                    naive_hits += 1
                hits = g.match_watchlist(observed, watchlist, top_k=3)
                found = [h for h in hits if h.watchlist_plate == truth]
                if found:
                    prahari_any += 1
                    if g.should_alert(found[0]):
                        prahari_alert += 1
            else:
                n_off += 1
                hits = g.match_watchlist(observed, watchlist, top_k=3)
                if hits and g.should_alert(hits[0]):
                    false_alerts += 1

        n_on = max(n_on, 1)
        n_off = max(n_off, 1)
        print(f"{rate:>7.0%} | {naive_hits / n_on:>12.1%} | {prahari_alert / n_on:>13.1%} "
              f"| {prahari_any / n_on:>15.1%} | {false_alerts / n_off:>12.1%}")

    print("-" * 78)
    print("naive recall    = fraction of watchlist vehicles found by `WHERE plate = ?`")
    print("PRAHARI alert   = found AND confident enough to auto-alert")
    print("PRAHARI +review = found, including the operator 'near miss' review panel")
    print("false alerts    = auto-alerts raised on vehicles NOT on the watchlist")


if __name__ == "__main__":
    run()
