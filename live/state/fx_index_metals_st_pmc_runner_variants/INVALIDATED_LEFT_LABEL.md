# Left-label ST+PMC 3R — do not cite as alpha

**Status (2026-09-08):** fair-3R books on this hub are **invalidated** under
completed-hour causality. Do **not** list NAS100 / GBPUSD (or EURUSD) 3R as
stranded-good or live-ready until a new **filter / revival** recovers real
post-close alpha.

## What died

The shared hourly resampler is **left-labeled**: a bar timestamped 11:00 contains
11:00–11:59 data. Pre-fix tapes armed on that bar and filled inside the same
hour (lookahead). After shifting signals to the **completed** hour, fair 3R
collapses — same class of bug as US30 (retired N/S 29.39 → **−0.21**).

| Market | Left-label N/S (do not cite) | Completed-hour 3R | Stance |
|---|---:|---:|---|
| **NAS100** fair 3R | ~~**19.56**~~ (+$15.2k / −$0.78k) | **0.53** (+$1.4k / −$2.7k) | **INVALIDATED** — hide from pickup lists |
| **GBPUSD** fair 3R | ~~**8.12**~~ | **−0.97** (−$131k / −$135k) | **INVALIDATED** — same cause, never live |
| EURUSD fair 3R | ~~3.01~~ | **−0.63** | same tape — do not cite 3.01 as promote |
| USDJPY fair 3R | (native JPY) | **−0.93** | same tape |

Source: this hub `SUMMARY.md` / `summary.csv` (completed-hour rerun). US30
attribution pattern: `../us30_st_pmc_signal_hour_attribution/`.

NAS100 **2R→10R** also haircuts (~~11.13~~ → **2.41**) — runner/tail, not a 3R
revive. Not a demo-promote.

## Revival (open)

The left-label tape’s edge was mostly **same-hour** target hits. Open question:
is there a **causal filter** (completed-hour only, post-close PMC retest,
hour-of-day, WR/PF sit-out, etc.) that recovers a fraction of that 19.56 / 8.12
without lookahead?

**Kitchen-sink protocol (PLAN only — mill not run):**  
[`../nas100_st_pmc_3r_completed_hour_filter_mill/PLAN.md`](../nas100_st_pmc_3r_completed_hour_filter_mill/PLAN.md)
— completed-hour tape only; calendar / MA / EMA / ATR / HA / US30 cross-market;
anti p-hacking holdout + nulls. Default stance remains **dead** until OOS + nulls pass.

Until that study produces a surviving heuristic: **stop showing these 3R rows as candidates.**

## Do not

- Quote canonical-board N/S 19.56 / 8.12 / 3.01 as current alpha
- Restart `demo-nas100-hourly-st-pmc-*` for alpha
- Treat GBPUSD 3R as “never picked up but still good”
