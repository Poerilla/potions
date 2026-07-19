# Stress-reduction study — promoted 1/1/3 runner@2R

Goal: cut the ~−$71k intrabar stress DD without gutting the +$71k net (fills-ledger basis; audit ref +$77.3k / −$74.0k — small definitional gaps, same shape).

Method: rebuilt the intrabar MTM equity curve from `fills.csv` + daily bars (validated vs audit), built per-campaign features, then swept filters and measured **real stress DD** per counterfactual (not just closed equity).

## What did NOT work

- **Timing:** losers are NOT late-month. It's the opposite — late entries (entry ≥ half-month) and second-trades-of-month are the *profitable* ones (late bucket +$50k avg $1.2k; second trade avg $1,685 vs $100). "Skip late" destroys the book (+$9k / 0.15 N/S).
- **Daily supertrend (10,3)/(14,2):** alignment filter is a coin flip (0.47 aligned / 0.83 counter). Same for 1H/4H supertrends — at OR-break moments all ST configs agree with break direction, no discrimination.
- **SMA20 daily:** perverse — counter-SMA20 is the good side (fade-flavored entries win). Inconsistent across other lookbacks; treated as noise.
- **OR width vs ATR:** no clean edge either side of median.

## What worked

### 1) Entry aligned with 1H EMA100 (≈ 4 trading days) — the standout

Take the FBO entry only if the prior-day 1H close is on the entry side of its **EMA100(1H)** (long: close > EMA; short: close < EMA). Causal (signal frozen a day before entry).

| | Baseline | 1h EMA100 aligned |
|---|---:|---:|
| Campaigns | 173 | 141 (drops 32) |
| Net | +$71.2k | **+$127.5k** |
| Stress DD | −$71.0k | **−$46.9k** |
| Net/Stress | 1.00 | **2.72** |
| WR | 50.3% | 53.9% (dropped set: 34.4%) |

Per-era kept net: 03-08 +$34.8k · 09-14 +$21.4k · 15-20 +$22.9k · 21-26 +$48.4k — positive in **all four eras** (baseline was −$15.8k in 15-20). Dropped 32 trades sum to **−$56k**.

### 2) Add ATR regime: skip entries when daily ATR14 percentile > 0.80

| | 1h EMA100 & ATR≤80 |
|---|---:|
| Campaigns | 114 |
| Net | **+$142.0k** |
| Stress DD | **−$33.9k** |
| Net/Stress | **4.19** |

Also all-era positive. High-ATR months (panic regimes) were where the counter-trend disasters clustered in 03-08/09-14.

## Caveats

- These are **counterfactual drops on the existing fills** — a broker rerun with the filter in the strategy will differ slightly (skipping trade 1 frees the 2-fills/month budget for a different trade 2).
- 1h EMA100 was picked from a sweep (~30 variants) → selection bias risk. Mitigation: edge is monotone-ish in neighborhood (EMA50 +, EMA200 weaker but +), WR gap is large (54% vs 34%), and all four eras agree. Still worth an out-of-family sanity check (e.g. GBPUSD).
- ATR>0.8 cut only removes 27 more trades; the pctl window (rolling 500d rank) must be reproduced causally in the plugin.

## Plan

1. Add optional `entry_filter` to `monthly_orb_v2b_oco`: `htf_ema` (tf=1h, span=100, prior-day close) + optional `atr_pctl_max`.
2. Broker rerun 1/1/3 with (a) EMA100 filter, (b) EMA100+ATR≤80; compare audit stress vs −$74k baseline.
3. Cross-check the same filter on 1/2/3 and on GBPUSD daily if data available.

Artifacts: `campaign_features.csv`, `filter_sweep.csv`, `htf_filter_sweep.csv`, `htf_alignment.csv`, `final_candidates.csv`, HTF bars `eurusd_1h.csv` / `eurusd_4h.csv`.
