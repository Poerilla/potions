# USDJPY Asia-range London — filter nulls

Shadow tape: unfiltered `S_3_1_3` campaign nets (sizing hub), chronological,
one row per Asia-range campaign. Bars are **not** shuffled. Nulls destroy only
the mapping between gate timing and future outcomes (or search over that mapping).

Stress / max DD on this report are **closed-campaign equity drawdowns** on the
taken shadow tape (reachable-stress proxy). Broker-like intrabar stress for the
promoted filtered replay remains N/S **7.23** on the filters hub.

Frozen promote cell: `S_3_1_3` + January skip + roll50 WR40/PF1.
Seed: **20260811**. OOS cut: years > **2021**.

## Component scorecard (shadow tape vs unfiltered)

| Component | Taken | Skipped | Net≈USD | Stress | N/S | Max DD | Worst | PF | WR | OOS net | OOS N/S |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| unfiltered | 1673 | 0 | $+153741 | $-68391 | 2.25 | $-68391 | $-12473 | 1.143 | 49.2% | $+150267 | 5.35 |
| january_only | 1508 | 165 | $+182627 | $-53686 | 3.40 | $-53686 | $-12473 | 1.195 | 49.7% | $+169066 | 6.56 |
| wr_only | 1481 | 192 | $+144665 | $-53075 | 2.73 | $-53075 | $-12473 | 1.145 | 49.5% | $+135434 | 4.53 |
| pf_only | 992 | 681 | $+117945 | $-29674 | 3.97 | $-29674 | $-12473 | 1.158 | 49.5% | $+82973 | 2.80 |
| roll_wr_pf | 990 | 683 | $+116387 | $-29674 | 3.92 | $-29674 | $-12473 | 1.156 | 49.4% | $+81415 | 2.74 |
| combined | 879 | 794 | $+145792 | $-24017 | 6.07 | $-24017 | $-12473 | 1.229 | 49.6% | $+101690 | 4.23 |

Combined vs unfiltered: Δnet **$-7949** | stress -68391 → -24017 | N/S 2.25 → 6.07 | max DD -68391 → -24017.

Broker-like filtered hub (reference): trades=861 net≈$178141.92 stress≈$-24627.15 N/S=7.23

Attribution reminder (Δ taken net vs unfiltered): January +$28.9k; WR −$9.1k;
PF −$35.8k; rolling −$37.4k; combined −$7.9k — rolling is the sit-out engine;
January is the only positive-Δ lever on raw net.

## 1. January-skip month placebo

Real rule: skip January (+ roll50 WR40/PF1). Null: skip one other calendar month,
same roll gate. Exhaustive 12-way table.

| Month skipped | Taken | Net≈USD | Stress | N/S | Max DD | Δnet vs roll-only | Rank N/S |
|---|---:|---:|---:|---:|---:|---:|---:|
| **January** | 879 | $+145792 | $-24017 | 6.07 | $-24017 | $+29405 | 1 |
| February | 947 | $+118418 | $-29674 | 3.99 | $-29674 | $+2031 | 5 |
| March | 912 | $+94572 | $-36385 | 2.60 | $-36385 | $-21815 | 10 |
| April | 904 | $+86525 | $-29674 | 2.92 | $-29674 | $-29862 | 8 |
| May | 902 | $+135365 | $-29674 | 4.56 | $-29674 | $+18977 | 2 |
| June | 893 | $+116119 | $-29674 | 3.91 | $-29674 | $-269 | 6 |
| July | 917 | $+123148 | $-29674 | 4.15 | $-29674 | $+6761 | 4 |
| August | 924 | $+97115 | $-35996 | 2.70 | $-35996 | $-19272 | 9 |
| September | 907 | $+70351 | $-37139 | 1.89 | $-37139 | $-46037 | 12 |
| October | 924 | $+108266 | $-29674 | 3.65 | $-29674 | $-8122 | 7 |
| November | 907 | $+124162 | $-29674 | 4.18 | $-29674 | $+7775 | 3 |
| December | 874 | $+60427 | $-31833 | 1.90 | $-31833 | $-55960 | 11 |

January ranks: net **#1**/12, N/S **#1**/12, max-DD **#1**/12.
Among one-month omissions, empirical mass with Δnet/ΔN/S/ΔDD at least as extreme as January:
p(Δnet)=0.083, p(ΔN/S)=0.083, p(ΔDD)=0.083.

### Null study rows

| Test | Iters | Seed | Actual taken/skip | Actual net | Actual N/S | Actual max DD | Null med N/S | N/S 5–95%% | p(net) | p(N/S) | p(DD) | Verdict | Decision | Interpretation |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| january_month_placebo | 12 | 20260811 | 879/794 | $+145792 | 6.07 | $-24017 | 3.78 | 1.90–5.24 | 0.0833 | 0.0833 | 0.0833 | pass | PROMOTE FILTER AS ALPHA | alpha-selection evidence |
| matched_exposure_random_skip | 5000 | 20260811 | 879/794 | $+145792 | 6.07 | $-24017 | 8.25 | 5.89–10.57 | 0.9662 | 0.9332 | 0.7447 | fail | REJECT FILTER | no evidence |
| circular_shift_gate | 1654 | 20260811 | 879/794 | $+145792 | 6.07 | $-24017 | 1.64 | 0.19–5.46 | 0.0725 | 0.0356 | 0.0254 | pass | PROMOTE FILTER AS ALPHA | alpha-selection evidence |
| shadow_outcome_block_10 | 1000 | 20260911 | 879/794 | $+145792 | 6.07 | $-24017 | 2.76 | 0.90–6.75 | 0.1948 | 0.0819 | 0.0559 | fail | REJECT FILTER | no evidence |
| shadow_outcome_block_25 | 1000 | 20260912 | 879/794 | $+145792 | 6.07 | $-24017 | 2.84 | 1.11–6.48 | 0.2138 | 0.0679 | 0.0460 | inconclusive | RETAIN FILTER AS RISK THROTTLE | risk-throttle evidence |
| shadow_outcome_block_50 | 1000 | 20260913 | 879/794 | $+145792 | 6.07 | $-24017 | 2.78 | 0.91–6.75 | 0.1928 | 0.0749 | 0.0559 | fail | REJECT FILTER | no evidence |
| selection_aware_master | 300 | 20261810 | 879/794 | $+145792 | 6.07 | $-24017 | 8.03 | 7.18–9.61 | 0.2193 | 1.0000 | 0.8970 | fail | REJECT FILTER | no evidence |

## Decision rule (conservative)

- **PROMOTE FILTER AS ALPHA:** Actual Δnet and/or predictive selection statistic
  beats the selection-aware null at the predeclared confidence threshold (p≤0.05).
- **RETAIN FILTER AS RISK THROTTLE:** Actual Δnet is not significant, but the filter
  produces robust, OOS-confirmed stress/drawdown improvement beyond matched-exposure nulls.
- **REJECT FILTER:** Actual result does not beat matched-exposure, shifted-gate,
  or selection-aware nulls on either net or risk path.

## Overall stance

**RETAIN FILTER AS RISK THROTTLE** (timing-supported; not matched-exposure-confirmed)

Matched-exposure random masks are **not** beaten on net, N/S, or DD
(actual N/S 6.07 sits below the matched null median 8.25 — exposure reduction alone
can look better). Circular-shift still shows the live gate's **timing** beats
most scrambled gates with the same take count and clustering (p_ns=0.036, p_dd=0.025).
January ranks #1 among one-month omissions on net, N/S, and max DD.
Selection-aware best-null winners land at N/S ~8.0 median — the locked promote cell
does **not** clear White-style search (p_ns=1.0).
Do **not** promote as alpha; keep only as an operational risk throttle with the
understanding that year/month-matched random subsets can match or beat shadow N/S.

### Prior expectation check

- January seasonal lever: month placebo ranks and Δnet distribution (see §1).
- Rolling WR/PF as risk/exposure regulator: watch matched-exposure and shift p(DD)/p(stress)
  vs weak p(net).
- Combined N/S beauty from stress removal: compare actual N/S percentile under
  matched-exposure (same take count) vs circular-shift (same clustering).

### Artifacts

- `filter_nulls.csv` — one row per null study with p-values and decision fields
- `filter_nulls_month_placebo.csv` — 12 one-month omission rows
- `filter_nulls_components.csv` — component scorecard
- `filter_nulls_shadow_tape.csv` — campaign tape + live_gate_take
- `filter_nulls_*.parquet` / detail CSVs for iteration draws when written

Driver: `python -m live.fx_v2b_asia_range_london_usdjpy_filter_nulls --email`

