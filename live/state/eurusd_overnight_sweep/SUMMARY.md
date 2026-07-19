# EURUSD Overnight Broker-Like Sweep

Tracker-led candidates on Histdata EURUSD through `Engine + PaperBroker + StrategyPlugin`.

- Point value: **$100,000** / lot (standard).
- Tick: **0.00001**; ST stops/targets in **pips**.
- Fee proxy: **$7.00**/unit; 1m rows use ~0.5 pip half-spread.
- Daily families: Yearly ORB, Monthly ORB, ATR Supertrend.
- Hourly: ST+PMC pip variants; 1m: v2b OCO + imported prior-opposed.

| Rank | Family | Candidate | Trades | Units | Net | Stress DD | Net/Stress | Win% | Status |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | yearly_orb | Yearly ORB scaleout3 | 92 | 276 | $165,865.00 | $-19,965.00 | 8.31 | 90.9 | ok |
| 2 | yearly_orb | Yearly ORB scaleout3 20% range-close | 61 | 183 | $124,518.75 | $-47,959.25 | 2.60 | 38.3 | ok |
| 3 | hourly_st_pmc | Hourly ST+PMC sl25_tp75_3r | 2182 | 2182 | $28,388.52 | $-18,987.32 | 1.50 | 26.7 | ok |
| 4 | hourly_st_pmc | Hourly ST+PMC sl25_tp75_3r_ma_bull_prior | 1148 | 1148 | $23,533.68 | $-15,745.46 | 1.49 | 27.4 | ok |
| 5 | monthly_orb | Monthly ORB restricted scaleout3 | 321 | 963 | $21,841.25 | $-48,307.50 | 0.45 | 55.5 | ok |
| 6 | hourly_st_pmc | Hourly ST+PMC sl40_tp120_3r_ma_directional_prior | 1345 | 1345 | $3,905.89 | $-36,719.86 | 0.11 | 25.4 | ok |
| 7 | atr | ATR daily ladder 1/1/2/2/2 10-max | 224 | 438 | $-14,505.00 | $-137,313.00 | -0.11 | 24.9 | ok |
| 8 | atr | ATR daily 3-initial 10-max | 224 | 819 | $-42,242.00 | $-204,371.00 | -0.21 | 19.7 | ok |
| 9 | hourly_st_pmc | Hourly ST+PMC sl40_tp120_3r | 1681 | 1681 | $-18,540.29 | $-44,337.87 | -0.42 | 24.6 | ok |
| 10 | v2b_prior_opposed | v2b prior-opposed ST+PMC S_1_1_3 | 370 | 1850 | $-9,475.00 | $-21,021.00 | -0.45 | 38.4 | ok |
| 11 | atr | ATR weekly 2-initial / 3-add / 6-max | 83 | 257 | $-153,556.00 | $-290,014.00 | -0.53 | 9.7 | ok |
| 12 | hourly_st_pmc | Hourly ST+PMC base_1x_50sl_150tp | 1404 | 1404 | $-25,592.39 | $-44,665.65 | -0.57 | 24.3 | ok |
| 13 | monthly_orb | Monthly ORB restricted scaleout3 boundary-stop entry | 652 | 1956 | $-140,782.25 | $-158,514.50 | -0.89 | 38.1 | ok |
| 14 | v2b | v2b_oco_S_1_1_3 | 2383 | 11915 | $-240,006.00 | $-251,282.00 | -0.96 | 22.7 | ok |
| 15 | v2b | v2b_oco_1_0_0 | 2022 | 2022 | $-42,414.00 | $-42,818.00 | -0.99 | 49.0 | ok |

Progress log: `PROGRESS.log`
CSV: `summary.csv`

## Forex intraday baseline (promoted 2026-07-17)

**Hourly ST+PMC 25/75 + MA bull prior** (`eurusd_hourly_st_pmc_sl25_tp75_3r_ma_bull_prior`) is the promoted **EURUSD forex intraday** sleeve.

- Pack: [`../eurusd_forex_intraday_baseline/SUMMARY.md`](../eurusd_forex_intraday_baseline/SUMMARY.md)
- Pitch: [`../eurusd_forex_intraday_baseline/ONE_PAGE_PITCH.md`](../eurusd_forex_intraday_baseline/ONE_PAGE_PITCH.md)
- Causal: **PASS** — see [`../eurusd_forex_intraday_baseline/CAUSAL_CHECK.md`](../eurusd_forex_intraday_baseline/CAUSAL_CHECK.md)
