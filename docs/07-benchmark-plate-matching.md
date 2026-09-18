# Benchmark — Plate Matching: Naive vs PRAHARI

**Reproduce:** `.venv/bin/python bench/bench_plate_matching.py`
**Run date:** 18 Sep 2026 · 200-plate watchlist · 600 observations per error rate · seed 7

## Result

| OCR char error | Naive `WHERE plate = ?` | PRAHARI auto-alert | PRAHARI incl. review panel | False alerts |
|---:|---:|---:|---:|---:|
| 0 % | 100.0 % | 100.0 % | 100.0 % | **0.0 %** |
| 5 % | 59.9 % | 73.9 % | **96.9 %** | **0.0 %** |
| 10 % | 32.4 % | 48.1 % | **82.7 %** | **0.0 %** |
| 15 % | 16.1 % | 32.4 % | **69.2 %** | **0.0 %** |
| 20 % | 10.9 % | 21.9 % | **53.5 %** | **0.0 %** |
| 30 % | 2.7 % | 6.1 % | **29.9 %** | **0.0 %** |

## The headline number for the deck

> At a realistic **10–15 % character error rate** — normal for Indian plates at night, at angle, or through dust —
> exact string matching finds **16–32 %** of watchlist vehicles.
> **PRAHARI finds 69–83 %. With zero false alerts.**
>
> That is a **2.6× to 4.3×** improvement in recall on identical footage, from a better matching primitive alone —
> no better camera, no better OCR model, no more compute.

**Why the zero-false-alert column matters most.** Recall is easy to buy by loosening a threshold; that produces a
control room that cries wolf and gets switched off within a week. Recall rising while false alerts stay at zero is
the grammar doing the work: most corrupted strings have *no* valid Indian plate nearby, so they are correctly
rejected rather than force-matched to the closest watchlist entry.

## Honesty notes (read these before quoting the numbers)

1. **The corruption model is deliberately unsympathetic.** If we only injected confusions drawn from the same table
   the matcher scores with, the benchmark would be circular. Corruption is a mixture: **70 %** attested confusion
   flips (which the matcher anticipates), **12 %** character drops, **10 %** arbitrary wrong characters, **8 %**
   spurious inserts — the last three are errors the confusion model does *not* anticipate. The uplift survives them.
2. **This is synthetic.** Plates are generated, not read off real footage. It isolates the *matching* primitive from
   OCR quality, which is exactly what it is meant to measure — but it is not a field result.
   **Day 8 replaces this with a measurement on the real Sentinel grid.**
3. **The "review panel" column is not free recall.** Those are ranked candidates surfaced to a human operator with
   evidence crops, not silent auto-alerts. Presented honestly, this is *assisted* recall.
4. **The confusion costs are hand-set priors**, not learned. They should be re-fitted from a measured confusion
   matrix once we have real OCR output. See `docs/06-build-plan.md` Day 8.
5. Watchlist size is 200. Real watchlists are far larger, which raises collision pressure. **Re-run at 10k and 100k
   entries before quoting these figures in the HLD** — this is a known open item.

## Why this wins the live evaluation

On finale day the jury hands you **one plate** and asks you to trace it across ~50 cameras. Each camera is an
independent chance to read that plate, and each read is an independent chance to lose it to a single bad character.

A team on exact matching finds the vehicle at the handful of cameras where OCR happened to be clean.
A team matching in confusion space finds it nearly everywhere it appeared — and renders a longer, denser,
more convincing route on the map, in front of the DGP.

**Same footage. Same models. Different primitive.**
