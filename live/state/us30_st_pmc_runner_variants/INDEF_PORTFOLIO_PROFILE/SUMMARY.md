# US30 ST+PMC indefinite runner — portfolio risk profile

Source: lot-correct forced-flat equity (`audits_lot_correct`). **Not rankable** vs 3R/10R on N/S.

## Equity path (close mark)

| Metric | Value |
|---|---:|
| Terminal equity | $80271 |
| Peak equity | $81364 |
| Max close DD | $-4438 (-5.5% of peak) |
| Time underwater | 97.5% |
| Avg DD | $-1377 |
| DD p50 / p90 / p99 | $-1235 / $-2702 / $-3559 |
| Longest underwater | 3705 hourly bars (~154 days) |
| Calmar-like (terminal/|DD|) | 18.09 |
| Approx daily Sharpe (Δequity) | 1.56 |

## Reachable stress path

| Metric | Value |
|---|---:|
| Max reachable stress DD | $-31164 |
| Stress Calmar-like | 2.55 |
| Stress time underwater | 97.7% |

## Open inventory burden

| Metric | Value |
|---|---:|
| Max open units | 68 |
| Mean / p50 / p90 / p99 open | 29.6 / 26.0 / 56.0 / 64.0 |
| Bars flat | 1.1% |
| Bars with ≥10 open | 90.8% |
| Bars with ≥30 open | 43.6% |

EOY flatten by year: `{"2017": 2, "2018": 3, "2020": 2, "2021": 3, "2024": 6, "2025": 4}`

## Worst close-DD episodes

| peak | trough | recover | DD $ | depth % |
|---|---|---|---:|---:|
| 2025-03-13T13:00 | 2025-03-26T10:00 | 2025-04-21T10:00 | $-4438 | -5.5 |
| 2024-12-20T05:00 | 2024-12-26T18:00 | 2025-01-21T12:00 | $-4295 | -5.8 |
| 2021-05-10T11:00 | 2021-06-07T12:00 | 2021-09-20T03:00 | $-3784 | -11.6 |
| 2017-03-01T14:00 | 2017-06-06T07:00 | 2017-08-06T20:00 | $-3592 | -46.9 |
| 2021-09-20T14:00 | 2021-09-27T09:00 | 2021-11-05T08:00 | $-3434 | -9.9 |
| 2019-06-03T03:00 | 2019-07-31T14:00 | 2019-12-23T07:00 | $-3421 | -14.1 |
| 2022-02-24T08:00 | 2022-06-22T10:00 | 2022-08-04T22:00 | $-3413 | -9.3 |
| 2018-05-21T10:00 | 2018-09-11T11:00 | 2018-10-26T10:00 | $-3277 | -20.2 |

## How to put this in a portfolio with defined risk

### 1. Choose the risk anchor

Use **reachable stress DD** ($31164 at 1×) as the sleeve’s risk unit — not raw open MTM, not legacy FIFO net.
Close DD ($4438) is the investor mark path; stress DD is the stop-aware capital-at-risk path.

### 2. Scale to a fund risk budget

For fund NAV \$1,000,000:

| Sleeve budget | Scale vs 1-lot book | Scaled terminal | Scaled stress DD | Scaled max open |
|---|---:|---:|---:|---:|
| 1% ($10000) | ×0.321 | $25757 | $-10000 | 21.8 |
| 2% ($20000) | ×0.642 | $51515 | $-20000 | 43.6 |
| 5% ($50000) | ×1.604 | $128787 | $-50000 | 109.1 |

Formula: `scale = (budget_pct × NAV) / |reachable_stress_dd|`.

### 3. Cap inventory separately from P&amp;L risk

Indef stacks BE runners: stop-defined loss per BE lot ≈ $0, but **margin / notional / gap risk** grow with open count.
Suggested hard caps (tune to broker): max open units **20**, margin proxy, and a kill-switch if open units or stress DD hit 1× profile extremes.

### 4. Sleeve role vs 3R / 2R→10R

| Book | Role |
|---|---|
| US30 3R (N/S ~29) | Core / rankable alpha, flat inventory |
| US30 2R→10R (N/S ~24) | Scaled participation, bounded 3 lots |
| US30 indef (this) | **Inventory sleeve** — harvest TP1 + optional trend residue; size on stress + concurrency, not on N/S leaderboard |

### 5. Portfolio assembly checklist

- Treat forced-flat reachable stress DD as the sleeve's 1× risk unit.
- Pick a fund risk budget (e.g. 2% NAV) and scale contracts = budget / |stress_dd|.
- Cap concurrency (open units / margin) independently — indef stacks inventory.
- BE runners add notional/margin but little stop-defined loss; size on margin + gap risk, not on open MTM.
- Do not co-rank this sleeve with flat 3R/10R on N/S; allocate as a separate inventory sleeve.
- Pair with negatively correlated / flatter books (e.g. US30 3R or 2R→10R, FX Monday OR) and enforce a portfolio stress sum cap.

## Artifacts

- `profile.json` — full machine-readable profile
- `equity_path.csv` — close / stress / open units path
- Equity source: `/home/tester/hsm/potions/live/state/us30_st_pmc_runner_variants/audits_lot_correct/us30_hourly_st_pmc_sl50_tp150_runners_2r_indef/us30_hourly_st_pmc_sl50_tp150_runners_2r_indef_lot_correct/equity_curve.csv`

