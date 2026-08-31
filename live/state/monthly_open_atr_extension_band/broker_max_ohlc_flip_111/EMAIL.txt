# NQ monthly open — first-week 4h OHLC/OLHC flip fade

Engine + PaperBroker **1h** fills; pattern on **NY 4h** buckets.

- Entry trigger: ≥2 same-side 4h O&C (liquidity run) then opposite 4h close in **week 1**
- Direction: follow the flip (opposite of the liquidity run)
- Entry: **market** on confirming 4h close
- SL: **swing** of the liquidity run (BE only after main/band-max TP)
- Ladder **1/1/1**: band-med / band-max (trade direction) / runner → EOM
- Band: 6m rolling levels for TPs; slip 1 tick; fee $1.50/unit

## Results

| Trades | Units | Net $ | Stress DD $ | N/S | Sharpe | Sortino | Calmar |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 61 | 183 | -36161 | -149475 | -0.24 | -0.02 | -0.01 | -0.25 |

## Loss / runner profile

- Stop units: **118** (net $-303170)
- Med TP units: **29** (net $+78093)
- Open TP units: **16** (net $+97661)
- Runner/EOM units: **20** (net $+91530)
- Avg win / avg loss (units): $+4596 / $-2533

Vs reclaim baseline (`broker_max_plus_0p3_reclaim`): net +$517k, N/S 1.54 @ qty10 flat.

| Exit reason | N | Net $ | Avg $ |
|---|---:|---:|---:|
| flatten | 20 | +91530 | +4576 |
| stop | 118 | -303170 | -2569 |
| target | 16 | +97661 | +6104 |
| tp_med | 29 | +78093 | +2693 |

