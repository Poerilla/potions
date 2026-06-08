# NQ adaptive 50/150 v2b-only scaleout

Longer-sample NQ confirmation for the MNQ leader candidate.

## Rules

- Compute daily MA50 and MA150 from NQ front-month daily closes.
- At each RTH session, use only information known before the open: prior daily MA50 > prior daily MA150 allows v2b; otherwise the day is skipped.
- No v2d fade arm is traded in this candidate.
- Opening range is 09:30-09:45 New York.
- Parent entry is v2b breakout: Long at `RH + 0.25`, Short at `RL - 0.25`.
- Initial stop is the opposite opening-range boundary.
- Trade 2 NQ contracts: 1 exits at TP1 (`RH + Range` / `RL - Range`), then the runner stop moves to entry.
- Runner exits at TP2 (`RH + 2*Range` / `RL - 2*Range`), runner stop, or end of session.
- Intrabar ordering is pessimistic: stop before target while fully loaded, and runner stop before TP2 when both touch.
- Fill model matches the MNQ scaleout research path: no extra entry slippage beyond the boundary tick, $1.50 round-trip fee per contract, and end-of-session flatten before 16:00.

## Headline

- Adaptive 50/150 v2b-only scaleout: 4,739 legs, $414,773.00, DD $-100,010.00, PF 1.13.
- All v2b days scaleout reference: 6,098 legs, $443,816.00, DD $-102,565.00, PF 1.10.

## Metrics

| Segment | Legs | Days | Net | Gross pts | Net pt equiv | Trade DD | Daily DD | Win rate | PF | TP1 | TP2 | Avg/trade |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| adaptive 50/150 v2b-only scaleout | 4739 | 3149 | $414,773.00 | 21,449.50 | 20,738.65 | $-100,010.00 | $-99,274.00 | 51.89% | 1.13 | 44.17% | 18.55% | $87.52 |
| all v2b days scaleout | 6098 | 4039 | $443,816.00 | 23,105.50 | 22,190.80 | $-102,565.00 | $-102,565.00 | 51.77% | 1.10 | 44.36% | 18.48% | $72.78 |

## Outputs

- Legs: [nq_adaptive_50_150_v2b_scaleout.csv](nq_adaptive_50_150_v2b_scaleout.csv)
- Summary CSV: [nq_adaptive_50_150_v2b_scaleout.summary.csv](nq_adaptive_50_150_v2b_scaleout.summary.csv)
- Skip audit: [nq_adaptive_50_150_v2b_scaleout.skips.csv](nq_adaptive_50_150_v2b_scaleout.skips.csv)
