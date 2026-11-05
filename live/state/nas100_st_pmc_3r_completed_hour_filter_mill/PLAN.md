# NAS100 fair-3R completed-hour filter mill — PLAN (no run yet)

**Status:** PLAN ONLY — do not treat as research result. Mill not executed.

**Goal:** Find a **causal sit-out filter** so that when completed-hour ST+PMC would arm,
we take only campaigns whose outcomes lift the book above the dead baseline.

**Not:** a new entry model, left-label revival, or re-demo of ~~N/S 19.56~~.

## Hard constraint

Existing condition profiles still score the **left-label** tape (`n=477`, net `+$15,219`,
N/S ~~19.56~~):

- `live/state/intraday_condition_profile/SUMMARY.md`
- `live/state/fx_metals_cfd_intraday_condition_profile/PROFILE.md`

Those “hour 11 / RSI-against / prior-quarter down” notables are **contaminated**. Do not reuse them.

**Tape for this study:** completed-hour fills only

`live/state/fx_index_metals_st_pmc_runner_variants/nas100/states/nas100_hourly_st_pmc_sl50_tp150_3r_1mfill/fills.csv`

| Baseline (completed-hour) | Value |
|---|---|
| Campaigns | ~856 |
| Net | +$1.4k |
| Stress | −$2.7k |
| **N/S** | **0.53** |

Same bug class as US30 fair-3R (29.39 → −0.21). Features must be **as-of completed hour close**
(or earlier). No same-hour NAS100 path.

US30 completed-hour 3R is also dead (N/S −0.21) — use it as a **cross-market feature source**,
not as a second “good” label. See `../us30_st_pmc_signal_hour_attribution/` and
`../fx_index_metals_st_pmc_runner_variants/INVALIDATED_LEFT_LABEL.md`.

## Prediction target

At the moment a completed-hour ST+PMC **would arm**, predict whether the next 3R campaign’s
net is favorable enough to take. Sit-out otherwise.

**Success (v1):** taken-book N/S and net beat **0.53 / +$1.4k** with coverage not tiny
(target **15–40%** of campaigns, **n≥80** taken).

This is **filter research**, not a new entry model.

```text
completed hour close → causal kitchen-sink features → heuristic score → take|sit
                                                              ↑
                                              completed-hour 3R outcome (label)
```

## Feature kitchen sink (all causal asof)

Reuse + extend:

- `live/fx_metals_cfd_intraday_condition_profile_lib.py`
- `live/intraday_condition_profile.py`

Hub for artifacts when run: this directory.

### Calendar

NY hour, DOW, week-of-month, month, quarter, year, session (RTH vs lunch),
days-to-FOMC/NFP/opex if a small calendar table exists, half-day / holiday-adjacent.

### NAS100 own tape (1m → 5m/1h/1d)

SMA/EMA 9/21/50/200 on 5m and 1h; MA state + cross vs trade side; RSI14 / Stoch / MACD hist;
OBV×MA; ATR14 quartile + ATR% of price; realized vol 1h/1d; range position in prior
day/week/month/quarter; prior bar body vs ATR; gap vs prior RTH close; trend age
(bars since last 1h EMA21 cross).

### Heikin-Ashi (new vs current mills)

1h and daily HA color, consecutive HA count, HA doji / small-body, HA vs real-close
disagreement, HA flip this hour vs prior.

### Structure / ST+PMC-native

Signal-hour range width vs ATR; PMC side; ST event age; failed-break / reclaim flags
(pattern from `../us30_pmc_failed_break_fade/`); post-close retest of signal-hour H/L
**only after** hour close (US30 attribution lesson — ~90% had a post-close retest).

### Cross-market

**US30 required.** SPX500 only if a daily series exists (`fx/spx500_1m.csv` is missing —
do **not** invent SPX 1m).

At NAS100 signal time:

- US30 1h RSI/HA/MA align vs NAS100 side
- US30−NAS100 1h return spread / rank-corr over last 6–24h
- both-up / both-down / diverge
- US30 completed-hour ST+PMC **would-have-armed** same hour (binary, no lookahead)
- YM/ES daily if 1m files already exist; else skip

### Regime

VIX-like proxy from NAS100 daily ATR z-score if no VIX file; prior-week trend;
monthly/yearly OR up/down/inside (already in the FX/CFD mill).

## Search protocol (anti p-hacking)

1. **Univariate buckets** on completed-hour tape (min n=40; report WR, avg, PF, N/S, coverage).
2. **Dual-lift shortlist:** WR and avg-net both beat baseline; coverage 8–35%.
3. **Cross-market repeats:** keep a NAS100 bucket only if the same family also lifts US30
   completed-hour 3R **or** is economically coherent (e.g. both-index HA align).
4. **Time holdout:** fit ≤2021, freeze, score 2022–2026. Reject if OOS N/S ≤ 0.53 or OOS net ≤ 0.
5. **Simple heuristic only for v1:** AND of ≤3 binary rules, or a 1–2 split tree. No ML on first pass.
6. **Nulls before any “maybe paper”:** matched sit-out / shuffled-label on ΔN/S (`p_master_ΔNS`),
   same bar as `live/state/intraday_hp_sizeup_nulls/`.
7. Stance: **hypothesis / RISK-THROTTLE** until nulls + OOS pass. Default: still dead.

## Deliverables when the mill is later executed

| Artifact | Role |
|---|---|
| `SUMMARY.md` | Baseline, top buckets, shortlist, OOS, stance |
| `campaigns_annotated.csv` | One row per completed-hour campaign + features |
| `buckets.csv` / `shortlist.csv` | Univariate + dual-lift |
| `heuristic_v1.json` | Frozen ≤3-rule AND (if any survives) |
| `EMAIL.txt` | Phone summary via `potions-job-email` |
| Ledger row | `run_class=ha` or `other` via `potions-run-ledger` |

## Explicit non-goals (this PLAN pass)

- Do not run the mill.
- Do not restart `demo-nas100-hourly-st-pmc-*` for alpha.
- Do not cite left-label N/S 19.56 / 8.12 / 3.01 as current alpha.

## Related

- Invalidation note: `../fx_index_metals_st_pmc_runner_variants/INVALIDATED_LEFT_LABEL.md`
- US30 lesson: `../us30_st_pmc_signal_hour_attribution/`
- Skills: `potions-intraday-condition-profile`, `potions-quick-backtest`, `potions-job-email`
