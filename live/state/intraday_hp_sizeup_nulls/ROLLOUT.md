# HP size-up rollout (strict master-null tiers)

Hub: `live/state/intraday_hp_sizeup_nulls/`  
Classifier: `live/intraday_hp_sizeup_nulls.py` (`SIZE-UP VALIDATED` / `BORDERLINE PAPER` / `RISK-BUDGET PROFILE`)

## Immutable decision rule

```text
SIZE-UP VALIDATED:
  p_placebo ≤ 0.05 AND p_shift ≤ 0.05 AND p_master ≤ 0.05
  AND walk-forward gate passes AND stress ≤ 1.35× baseline
  AND causal live-ready AND HP coverage < 35%.

BORDERLINE PAPER:
  All validated gates pass except 0.05 < p_master ≤ 0.10.
  Allowed: shadow / controlled paper only.
  Not allowed: historical promotion claim.

RISK-BUDGET / SENSITIVITY:
  p_master > 0.10, or walk-forward stability fails (or coverage too broad).
  Allowed: monitor and stress research.
  Not allowed: HP-size deployment.
```

## Authorized rollout (2026-08-12)

| Book | Condition | Mult | Status | Action |
|---|---|---:|---|---|
| EURUSD ST+PMC 3R | Thursday | **1.25×** | SIZE-UP VALIDATED | **Primary** shadow → controlled paper |
| US30 Monday OR | NY hour 11 | **1.25×** | SIZE-UP VALIDATED | **Primary** shadow → controlled paper |
| EURUSD ST+PMC 3R | Thursday | 1.5× | BORDERLINE PAPER | Optional exploratory parallel paper only |
| US30 Monday OR | NY hour 11 | 1.5× | BORDERLINE PAPER | Optional exploratory parallel paper only |
| EURUSD ST+PMC 3R | Thursday | 2.0× | RISK-BUDGET | Do **not** deploy as validated HP mult |
| US30 Monday OR | NY hour 11 | 2.0× | RISK-BUDGET | Do **not** deploy as validated HP mult |

Do not stack HP multipliers. Cap: one HP boost rule per book.

## Expected N/S impact (historical, linear sleeve @ 1.25×)

Incremental sleeve N/S is **scale-invariant** under linear replay
(\(k\Delta\mathrm{net}/k\Delta\mathrm{stress}\)); the book-level lift is what matters for
expectation setting:

| Book | HP | Inc N/S | Baseline book N/S | Sized book N/S @1.25× | Δ book N/S | Stress× |
|---|---:|---:|---:|---:|---:|---:|
| EURUSD ST+PMC Thu | 20% | **8.39** | 3.18 | **3.52** | **+0.34** | 1.025 |
| US30 Monday OR h11 | 9.5% | **6.69** | 1.96 | **2.16** | **+0.20** | 1.025 |

Read: if live HP incidence and fill quality match research, expect roughly
**+0.34 N/S** on the EURUSD 3R book and **+0.20 N/S** on the US30 Monday OR
half book from the 1.25× HP sleeve alone — not from changing the baseline
sleeve mix.

At 1.5× / 2×, **inc N/S stays 8.39 / 6.69**; only full-book path risk and
`p_master` degrade (hence borderline / risk-budget labels).

## Live/demo start (shadow first)

Paper demos already running (baseline size):

- `live/demo/eurusd_hourly_st_pmc_sl50_tp150_3r_paper`
- `live/demo/us30_monday_or_m3_s3_r2_half_paper`

**Phase 0 (now):** shadow annotate entry fills with `hp_flag` /
`would_size_mult=1.25` (no order-size change). Integer `quantity` on these
books is 1 — true 1.25× needs a later base-lot rescale (e.g. 4→5) or
fractional qty; do not fake validation by jumping to 2× lots.

Annotator: `python -m live.hp_size_shadow --once` (writes
`state/hp_shadow.csv` under each demo).

**Phase 1:** after ~1–2 weeks / first handful of HP hits logged, wire
controlled paper size only if lot geometry supports 1.25× cleanly.

**Not authorized:** 2× as a statistically validated HP multiplier; live
escalation from borderline 1.5× backtest evidence alone.

## Artifacts

- `SUMMARY.md` / `pair_decisions.csv` / `pairs/*/RESULT.json`
- `EMAIL.txt`
- Overlay plan (broader Tier A): `../intraday_condition_overlay/LIVE_PLAN.md`
