"""
Indian number-plate grammar, constrained decoding, and confusion-space matching.

WHY THIS MODULE EXISTS
----------------------
Nearly every ANPR system built for an Indian deployment does this:

    SELECT * FROM watchlist WHERE plate = ocr_output

That is a broken primitive here. UK/EU plates are a single standardised,
reflective, machine-readable font, so exact matching works. Indian plates are
not one thing: two-line and stacked two-wheeler plates, hand-painted fonts,
HSRP hologram glare, BH-series, vanity plates, dust, damage, deliberate
obscuring. A single misread character turns a hit into a miss, silently.

This module replaces exact matching with three layers:

  1. GRAMMAR   An Indian plate is not an arbitrary string. It has a rigid
               structure and a closed vocabulary of state + RTO district
               codes. `GJ01AB1234` is valid; `6J01A81234` is not, because
               `6J` is not a state code and position 4 must be a digit.
               Structure is free accuracy.

  2. CORRECTION  Given a raw OCR read, search the neighbourhood of valid
               plates under an OCR-confusion-weighted edit distance and
               return ranked candidates with posteriors. `6J01A8I234`
               resolves to `GJ01AB1234` because 6->G, 8->B and I->1 are all
               cheap, well-attested OCR confusions and the result is the only
               grammatically valid string nearby.

  3. MATCHING  Watchlist lookup happens in confusion space, not string space,
               and always returns a ranked list. An operator seeing four
               ranked candidates with evidence crops has a working
               investigative tool. An operator seeing "no results" has
               nothing.

Everything here is pure-Python, dependency-free, and directly unit-testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

# ---------------------------------------------------------------------------
# 1. The closed vocabulary: state / UT codes
# ---------------------------------------------------------------------------

# Current codes. Historical codes that still appear on the road are included
# because a live camera will absolutely see them (OR, UA, AP-era TS plates).
STATE_CODES: dict[str, str] = {
    "AN": "Andaman & Nicobar Islands",
    "AP": "Andhra Pradesh",
    "AR": "Arunachal Pradesh",
    "AS": "Assam",
    "BR": "Bihar",
    "CG": "Chhattisgarh",
    "CH": "Chandigarh",
    "DD": "Dadra & Nagar Haveli and Daman & Diu",
    "DL": "Delhi",
    "GA": "Goa",
    "GJ": "Gujarat",
    "HP": "Himachal Pradesh",
    "HR": "Haryana",
    "JH": "Jharkhand",
    "JK": "Jammu & Kashmir",
    "KA": "Karnataka",
    "KL": "Kerala",
    "LA": "Ladakh",
    "LD": "Lakshadweep",
    "MH": "Maharashtra",
    "ML": "Meghalaya",
    "MN": "Manipur",
    "MP": "Madhya Pradesh",
    "MZ": "Mizoram",
    "NL": "Nagaland",
    "OD": "Odisha",
    "PB": "Punjab",
    "PY": "Puducherry",
    "RJ": "Rajasthan",
    "SK": "Sikkim",
    "TN": "Tamil Nadu",
    "TR": "Tripura",
    "TS": "Telangana",
    "UK": "Uttarakhand",
    "UP": "Uttar Pradesh",
    "WB": "West Bengal",
    # Historical, still on the road:
    "DN": "Dadra & Nagar Haveli (historical)",
    "OR": "Odisha (historical)",
    "UA": "Uttarakhand (historical)",
    "TG": "Telangana (alternate)",
}

# Highest RTO district number issued per state. A plate whose district code
# exceeds this is grammatically suspect, which is extra signal for correction.
# Gujarat is enumerated precisely because it is the deployment state; others
# are upper bounds sufficient for validation.
MAX_RTO_DISTRICT: dict[str, int] = {
    "GJ": 39,
    "MH": 52, "UP": 96, "TN": 99, "KA": 71, "AP": 40, "TS": 38,
    "RJ": 59, "MP": 70, "DL": 17, "HR": 99, "PB": 99, "KL": 99,
    "WB": 99, "BR": 56, "OD": 35, "OR": 35, "JH": 24, "CG": 30,
    "AS": 35, "HP": 99, "JK": 22, "UK": 20, "UA": 20, "GA": 12,
    "CH": 4, "PY": 5, "TR": 8, "ML": 14, "MN": 7, "MZ": 8,
    "NL": 10, "SK": 6, "AR": 26, "AN": 1, "LD": 9, "DD": 3,
    "DN": 9, "LA": 2, "TG": 38,
}

# Gujarat RTO district codes -> office, for registry enrichment and for making
# alerts legible to an operator ("GJ-18 = Gandhinagar").
GUJARAT_RTO: dict[int, str] = {
    1: "Ahmedabad", 2: "Mehsana", 3: "Rajkot", 4: "Bhavnagar", 5: "Surat",
    6: "Vadodara", 7: "Nadiad", 8: "Palanpur", 9: "Himmatnagar", 10: "Jamnagar",
    11: "Junagadh", 12: "Kutch/Bhuj", 13: "Surendranagar", 14: "Amreli",
    15: "Valsad", 16: "Bharuch", 17: "Godhra", 18: "Gandhinagar",
    19: "Bardoli", 20: "Dahod", 21: "Navsari", 22: "Rajpipla",
    23: "Anand", 24: "Patan", 25: "Porbandar", 26: "Vyara",
    27: "Ahmedabad East", 28: "Surat (Bardoli)", 29: "Vadodara Rural",
    30: "Modasa", 31: "Veraval", 32: "Ahmedabad Rural", 33: "Rajkot Rural",
    34: "Botad", 35: "Chhota Udepur", 36: "Mahisagar", 37: "Morbi",
    38: "Devbhoomi Dwarka", 39: "Gir Somnath",
}

# ---------------------------------------------------------------------------
# 2. Plate formats
# ---------------------------------------------------------------------------
#
# Each format is a positional template. Symbols:
#   S = state letter (constrained to STATE_CODES on the 2-letter prefix)
#   D = digit
#   A = alpha (series letters)
#   Literal characters match themselves.
#
# Templates are ordered by prevalence; the first match wins for classification.

FORMATS: list[tuple[str, str, str]] = [
    # (name, template, human description)
    ("standard_2l",  "SSDDAADDDD",  "GJ 01 AB 1234 — modern standard"),
    ("standard_1l",  "SSDDADDDD",   "GJ 01 A 1234"),
    ("standard_3l",  "SSDDAAADDDD", "GJ 01 ABC 1234"),
    ("standard_sd2", "SSDAADDDD",   "GJ 1 AB 1234 — single-digit district"),
    ("standard_sd1", "SSDADDDD",    "GJ 1 A 1234"),
    ("standard_sd3", "SSDAAADDDD",  "DL 3C BJ 5087 — Delhi-style category letter"),
    ("no_series",    "SSDDDDDD",    "GJ 01 1234 — older, no letter series"),
    ("bh_series",    "DDBHDDDDAA",  "22 BH 1234 AA — Bharat series"),
    ("bh_series_1",  "DDBHDDDDA",   "22 BH 1234 A — Bharat series"),
]

_CLASS_OF: dict[str, str] = {}
for _name, _tpl, _ in FORMATS:
    _CLASS_OF[_name] = _tpl

DIGITS = set("0123456789")
ALPHAS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def normalise(raw: str) -> str:
    """Strip everything that is not A-Z0-9 and upper-case. Plates are written
    with wildly inconsistent spacing, hyphens and decorative separators."""
    return re.sub(r"[^A-Z0-9]", "", (raw or "").upper())


def _fits_template(plate: str, template: str) -> bool:
    if len(plate) != len(template):
        return False
    for ch, slot in zip(plate, template):
        if slot == "D":
            if ch not in DIGITS:
                return False
        elif slot in ("A", "S"):
            if ch not in ALPHAS:
                return False
        else:  # literal
            if ch != slot:
                return False
    return True


@dataclass(frozen=True)
class PlateParse:
    """The structured reading of a plate string."""
    plate: str
    format_name: str
    valid: bool
    state_code: str | None = None
    state_name: str | None = None
    district: int | None = None
    district_name: str | None = None
    series: str | None = None
    number: str | None = None
    reasons: tuple[str, ...] = field(default_factory=tuple)


@lru_cache(maxsize=65536)
def parse(raw: str) -> PlateParse:
    """Parse a plate string under the Indian grammar.

    Returns a PlateParse with `valid=False` and human-readable `reasons` when
    the string cannot be a real Indian plate. Those reasons are what make an
    alert explainable to an operator (and defensible later).
    """
    p = normalise(raw)
    if not p:
        return PlateParse(p, "unknown", False, reasons=("empty",))

    for name, tpl, _desc in FORMATS:
        if not _fits_template(p, tpl):
            continue

        if name.startswith("bh_"):
            year = p[0:2]
            num = p[4:8]
            series = p[8:]
            return PlateParse(p, name, True, state_code="BH",
                              state_name="Bharat series", series=series,
                              number=num,
                              district_name=f"BH-{year}")

        state = p[0:2]
        reasons: list[str] = []
        if state not in STATE_CODES:
            reasons.append(f"'{state}' is not a valid state code")

        # District digits run until the first alpha (or the last 4 digits for
        # the no-series format).
        idx = 2
        while idx < len(p) and p[idx] in DIGITS and (len(p) - idx) > 4:
            idx += 1
        district_s = p[2:idx]
        district = int(district_s) if district_s else None

        rest = p[idx:]
        series = "".join(c for c in rest if c in ALPHAS)
        number = rest[len(series):]

        if district is not None and state in MAX_RTO_DISTRICT:
            if district < 1 or district > MAX_RTO_DISTRICT[state]:
                reasons.append(
                    f"district {district:02d} out of range for {state} "
                    f"(1-{MAX_RTO_DISTRICT[state]})"
                )

        district_name = None
        if state == "GJ" and district in GUJARAT_RTO:
            district_name = GUJARAT_RTO[district]

        return PlateParse(
            plate=p, format_name=name, valid=not reasons,
            state_code=state, state_name=STATE_CODES.get(state),
            district=district, district_name=district_name,
            series=series or None, number=number or None,
            reasons=tuple(reasons),
        )

    return PlateParse(p, "unknown", False,
                      reasons=("does not fit any known Indian plate format",))


def is_valid(raw: str) -> bool:
    return parse(raw).valid


# ---------------------------------------------------------------------------
# 3. The OCR confusion model
# ---------------------------------------------------------------------------
#
# Substitution costs in [0, 1]. Low cost == a confusion that real OCR engines
# make constantly on Indian plates. These are asymmetric in principle but we
# keep them symmetric here; the asymmetry that matters (digit-slot vs
# alpha-slot) is handled by the grammar, which is a stronger signal.
#
# Calibrate these against a measured confusion matrix once we have benchmark
# runs on the real grid — see docs/06-build-plan.md, Day 8.

_CONFUSION_PAIRS: dict[frozenset[str], float] = {
    frozenset("O0"): 0.08,
    frozenset("I1"): 0.08,
    frozenset("B8"): 0.12,
    frozenset("S5"): 0.12,
    frozenset("G6"): 0.18,
    frozenset("Z2"): 0.18,
    frozenset("D0"): 0.22,
    frozenset("Q0"): 0.25,
    frozenset("L1"): 0.25,
    frozenset("A4"): 0.30,
    frozenset("T7"): 0.30,
    frozenset("T1"): 0.35,
    frozenset("S6"): 0.40,
    frozenset("GC"): 0.35,
    frozenset("G0"): 0.35,
    frozenset("CO"): 0.40,
    frozenset("C0"): 0.40,
    frozenset("MN"): 0.35,
    frozenset("UV"): 0.35,
    frozenset("EF"): 0.40,
    frozenset("KX"): 0.40,
    frozenset("PR"): 0.40,
    frozenset("9G"): 0.45,
    frozenset("56"): 0.45,
    frozenset("38"): 0.30,
    frozenset("69"): 0.30,
    frozenset("17"): 0.35,
    frozenset("VY"): 0.45,
    frozenset("DO"): 0.20,
    frozenset("JI"): 0.40,
    frozenset("WN"): 0.40,
    frozenset("WM"): 0.35,
    frozenset("WV"): 0.40,
}

_SUB_COST: dict[tuple[str, str], float] = {}
for _pair, _cost in _CONFUSION_PAIRS.items():
    _chars = list(_pair)
    if len(_chars) == 2:
        a, b = _chars
        _SUB_COST[(a, b)] = _cost
        _SUB_COST[(b, a)] = _cost

UNRELATED_SUB_COST = 1.0
INDEL_COST = 1.0


def sub_cost(a: str, b: str) -> float:
    """Cost of substituting character `a` for `b` under the OCR confusion model."""
    if a == b:
        return 0.0
    return _SUB_COST.get((a, b), UNRELATED_SUB_COST)


def confusion_distance(a: str, b: str) -> float:
    """Confusion-weighted Levenshtein distance between two plate strings.

    This is the core primitive that replaces string equality. A distance of
    0.08 means "these differ by one character that OCR confuses constantly" —
    which should absolutely still fire a ranked alert. A distance of 1.0 means
    "these differ by a character no OCR engine would confuse" — which should
    not.
    """
    a, b = normalise(a), normalise(b)
    if a == b:
        return 0.0
    if not a:
        return len(b) * INDEL_COST
    if not b:
        return len(a) * INDEL_COST

    prev = [j * INDEL_COST for j in range(len(b) + 1)]
    for i, ca in enumerate(a, start=1):
        cur = [i * INDEL_COST]
        for j, cb in enumerate(b, start=1):
            cur.append(min(
                prev[j] + INDEL_COST,              # deletion
                cur[j - 1] + INDEL_COST,           # insertion
                prev[j - 1] + sub_cost(ca, cb),    # substitution
            ))
        prev = cur
    return prev[-1]


def similarity(a: str, b: str) -> float:
    """Confusion distance mapped to a 0..1 score. 1.0 == identical."""
    a, b = normalise(a), normalise(b)
    denom = max(len(a), len(b), 1)
    return max(0.0, 1.0 - confusion_distance(a, b) / denom)


# ---------------------------------------------------------------------------
# 4. Grammar-constrained correction
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Candidate:
    """A grammatically valid plate reachable from a raw OCR read."""
    plate: str
    distance: float          # confusion-weighted edit distance from the raw read
    score: float             # 0..1 posterior-ish confidence
    format_name: str
    edits: tuple[str, ...]   # human-readable, e.g. ("pos0 6->G",)
    state_name: str | None = None
    district_name: str | None = None

    def explain(self) -> str:
        if not self.edits:
            return "exact read, grammatically valid"
        return "corrected: " + ", ".join(self.edits)


def _alternatives(ch: str, want: str) -> list[tuple[str, float]]:
    """Characters of class `want` ('D' digit or 'A' alpha) reachable from `ch`,
    with their substitution costs. Always includes `ch` itself when it already
    belongs to the right class."""
    pool = DIGITS if want == "D" else ALPHAS
    out: list[tuple[str, float]] = []
    if ch in pool:
        out.append((ch, 0.0))
    for cand in pool:
        if cand == ch:
            continue
        c = sub_cost(ch, cand)
        if c < UNRELATED_SUB_COST:      # only plausible confusions
            out.append((cand, c))
    return sorted(out, key=lambda t: t[1])


def constrained_decode(
    raw: str,
    *,
    max_cost: float = 1.2,
    beam: int = 64,
    top_k: int = 5,
) -> list[Candidate]:
    """Correct a raw OCR read into ranked, grammatically VALID Indian plates.

    This is beam search over positions, where the beam is pruned by the plate
    grammar at every step: a character in a digit slot can only become a digit,
    a state prefix can only become a real state code, and a district code can
    only fall in that state's issued range.

    The grammar does most of the work. `6J01A8I234` has exactly one plausible
    valid neighbour, `GJ01AB1234`, because:
        pos0  '6' must be alpha -> G (cost 0.18)   [6J is not a state code; GJ is]
        pos5  '8' must be alpha -> B (cost 0.12)
        pos6  'I' must be digit -> 1 (cost 0.08)

    Returns [] if nothing valid is reachable within `max_cost`.
    """
    p = normalise(raw)
    if not p:
        return []

    results: dict[str, Candidate] = {}

    for fmt_name, tpl, _desc in FORMATS:
        if len(p) != len(tpl):
            continue

        # Beam entries: (partial_string, cost, edits)
        beams: list[tuple[str, float, tuple[str, ...]]] = [("", 0.0, ())]

        for pos, slot in enumerate(tpl):
            ch = p[pos]
            nxt: list[tuple[str, float, tuple[str, ...]]] = []

            if slot not in ("D", "A", "S"):          # literal, e.g. 'B','H'
                alts = [(slot, sub_cost(ch, slot))]
            else:
                alts = _alternatives(ch, "D" if slot == "D" else "A")

            for prefix, cost, edits in beams:
                for cand_ch, c in alts:
                    new_cost = cost + c
                    if new_cost > max_cost:
                        continue
                    new_prefix = prefix + cand_ch

                    # Grammar pruning ---------------------------------------
                    # State code must be real, checked the moment it is complete.
                    if slot == "S" and pos == 1 and not fmt_name.startswith("bh_"):
                        if new_prefix[:2] not in STATE_CODES:
                            continue

                    new_edits = edits if c == 0.0 else edits + (
                        f"pos{pos} {ch}->{cand_ch}",
                    )
                    nxt.append((new_prefix, new_cost, new_edits))

            nxt.sort(key=lambda t: t[1])
            beams = nxt[:beam]
            if not beams:
                break

        for cand_plate, cost, edits in beams:
            pp = parse(cand_plate)
            if not pp.valid:
                continue                              # district-range check etc.
            prior = results.get(cand_plate)
            if prior is None or cost < prior.distance:
                results[cand_plate] = Candidate(
                    plate=cand_plate,
                    distance=round(cost, 4),
                    score=round(max(0.0, 1.0 - cost / max(len(cand_plate), 1)), 4),
                    format_name=pp.format_name,
                    edits=edits,
                    state_name=pp.state_name,
                    district_name=pp.district_name,
                )

    return sorted(results.values(), key=lambda c: (c.distance, c.plate))[:top_k]


# ---------------------------------------------------------------------------
# 5. Watchlist matching in confusion space
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WatchlistHit:
    watchlist_plate: str
    observed_plate: str
    distance: float
    score: float
    exact: bool
    record: dict
    via: str                 # "exact" | "confusion" | "grammar+confusion"

    def explain(self) -> str:
        if self.exact:
            return "exact match"
        return f"{self.via} match, confusion distance {self.distance:.2f}"


# Default thresholds. `alert` fires an automatic alert; anything between
# `alert` and `review` lands in the operator "near miss" panel rather than
# being silently dropped. Never returning empty is a deliberate design rule:
# on stage, "no results" reads as failure, while four ranked candidates with
# evidence crops read as a working investigative tool.
ALERT_THRESHOLD = 0.30
REVIEW_THRESHOLD = 1.10


def match_watchlist(
    observed: str,
    watchlist: dict[str, dict] | list[str],
    *,
    alert_threshold: float = ALERT_THRESHOLD,
    review_threshold: float = REVIEW_THRESHOLD,
    use_grammar: bool = True,
    top_k: int = 5,
) -> list[WatchlistHit]:
    """Match an observed plate against a watchlist in CONFUSION SPACE.

    `watchlist` maps plate -> record (or is a bare list of plates).

    Strategy:
      1. exact hit                      -> distance 0
      2. direct confusion distance      -> catches single-character misreads
      3. grammar-corrected candidates   -> catches reads that are not even
                                           valid plates until repaired

    Always returns a RANKED list, never a bare hit/miss. Callers split on
    `alert_threshold` for automatic alerts vs the review panel.
    """
    if isinstance(watchlist, list):
        watchlist = {normalise(p): {} for p in watchlist}
    wl = {normalise(k): v for k, v in watchlist.items()}

    obs = normalise(observed)
    if not obs:
        return []

    best: dict[str, WatchlistHit] = {}

    def _offer(wl_plate: str, dist: float, via: str, seen: str) -> None:
        if dist > review_threshold:
            return
        prior = best.get(wl_plate)
        if prior is not None and prior.distance <= dist:
            return
        best[wl_plate] = WatchlistHit(
            watchlist_plate=wl_plate,
            observed_plate=seen,
            distance=round(dist, 4),
            score=round(max(0.0, 1.0 - dist / max(len(wl_plate), 1)), 4),
            exact=(dist == 0.0),
            record=wl.get(wl_plate, {}),
            via=via,
        )

    # 1 + 2: direct comparison against every watchlist entry.
    for wl_plate in wl:
        d = confusion_distance(obs, wl_plate)
        _offer(wl_plate, d, "exact" if d == 0.0 else "confusion", obs)

    # 3: repair the read first, then compare. This is what rescues reads that
    #    are not valid plates at all until the grammar fixes them.
    if use_grammar:
        for cand in constrained_decode(obs, max_cost=review_threshold):
            if cand.plate in wl:
                _offer(cand.plate, cand.distance, "grammar+confusion", obs)
            else:
                for wl_plate in wl:
                    d = cand.distance + confusion_distance(cand.plate, wl_plate)
                    _offer(wl_plate, d, "grammar+confusion", obs)

    hits = sorted(best.values(), key=lambda h: (h.distance, h.watchlist_plate))
    return hits[:top_k]


def should_alert(hit: WatchlistHit, *, alert_threshold: float = ALERT_THRESHOLD) -> bool:
    """True if this hit is confident enough to raise an automatic alert
    rather than land in the operator review panel."""
    return hit.distance <= alert_threshold
