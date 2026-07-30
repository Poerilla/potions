# US30 — StrategyPlugin gambit sweep

Engine + PaperBroker on MT5 US30 CFD 1m/daily (`fx/us30_*.csv`, labeled extract
from `fx/raw/us30.zip`). Tick **0.1**, PV **$1/pt**, fee **$1.50**/unit.
ST+PMC stops in **index points** (NAS100/NQ convention). Same plugin families
as AUDJPY / metals / EURUSD overnight (daily ORB/ATR, hourly ST+PMC, v2b prior-opposed).

| Rank | Family | Strategy | Trades | Net $ | Stress DD | **N/S** | Unit WR |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | hourly_st_pmc | ST+PMC sl50_tp150_3r | 1074.0 | **12145.85** | -3108.6 | **3.91** | 31.8% |
| 2 | yearly_orb | Yearly ORB scaleout3 | 34.0 | **25597.0** | -7186.8 | **3.56** | 73.5% |
| 3 | hourly_st_pmc | ST+PMC sl40_tp120_3r | 1155.0 | **9587.8** | -3088.6 | **3.1** | 31.6% |
| 4 | yearly_orb | Yearly ORB scaleout3 20% range-close | 18.0 | **24309.83** | -10908.35 | **2.23** | 55.6% |
| 5 | atr_st | ATR daily 3-initial 10-max | 77.0 | **47889.7** | -32235.3 | **1.49** | 32.0% |
| 6 | hourly_st_pmc | ST+PMC sl25_tp75_3r | 1320.0 | **4044.85** | -3058.6 | **1.32** | 30.4% |
| 7 | hourly_st_pmc | ST+PMC sl25_tp75_3r_ma_directional_prior | 1021.0 | **3707.59** | -3058.6 | **1.21** | 30.8% |
| 8 | atr_st | ATR weekly 2-initial / 3-add / 6-max | 36.0 | **35620.1** | -36618.0 | **0.97** | 11.4% |
| 9 | monthly_orb | Monthly ORB restricted scaleout3 | 123.0 | **19586.1** | -21032.6 | **0.93** | 58.3% |
| 10 | v2b_prior_opposed | v2b OCO prior-opposed S_1_1_3 | 309 | **6322.9** | -10677.0 | **0.59** | 35.0% |
| 11 | atr_st | ATR daily ladder 1/1/2/2/2 10-max | 77.0 | **26142.0** | -47631.4 | **0.55** | 34.0% |
| 12 | monthly_orb | Monthly ORB restricted scaleout3 boundary-stop entry | 233.0 | **7430.73** | -17150.65 | **0.43** | 39.9% |

## Most promising: **ST+PMC sl50_tp150_3r** (`us30_hourly_st_pmc_sl50_tp150_3r`)

- Family: `hourly_st_pmc`
- Net / Stress: **12145.85** / -3108.6 → N/S **3.91** (hourly fill resolution)
- Trades / unit WR: 1074.0 / 31.8%

### Follow-up (2026-07-30): 1m fill tape causality

Hourly OHLC can fill entry+target on the same bar when H/L both touch levels even
if the high occurred **before** a causal limit fill. With StrategyPlugin + 1m
fill tape (`sl50_tp150_3r_1mfill`): **+$20.4k / −$2.0k / N/S 10.34** — see
[`../us30_st_pmc_retest_add_experiment/SUMMARY.md`](../us30_st_pmc_retest_add_experiment/SUMMARY.md).
Live paper/OANDA demos now use that fair-control config (no BB/retest pyramid).


## Monday OR (added)

Baseline `M1_S1_R1` (battle test): N/S **0.53** · net $+14910 · stress $-28124 · 2784 units.

Phase 1 sizing sweep (27 cells, `live/state/monday_or_sizing_sweep_broker_us30/`):

| Rank | Tag | ≈USD Net | ≈USD Stress | **N/S** | Units |
|---:|---|---:|---:|---:|---:|
| 1 | `M3_S3_R3` | $+29891 | $-15899 | **1.88** | 3742 |
| 2 | `M3_S3_R2` | $+31330 | $-16941 | **1.85** | 2624 |
| 3 | `M3_S1_R3` | $+22325 | $-14511 | **1.54** | 3546 |
| 4 | `M3_S3_R1` | $+25418 | $-17045 | **1.49** | 2224 |
| 5 | `M1_S3_R3` | $+28246 | $-19625 | **1.44** | 5221 |

**Best Monday OR tag:** `M3_S3_R3` — N/S **1.88** (still below gambit leaders ST+PMC 50/150 at 3.91 and Yearly ORB at 3.56).

Driver: `live/fx_monday_or_breakout_broker.py --pairs US30` + `live/monday_or_sizing_sweep_broker.py --pairs US30 --phase 1`.

Driver: `live/us30_futures_strats_sweep.py` (stages: daily / stpmc / v2b).
State: `live/state/us30_futures_strats_sweep/`.
