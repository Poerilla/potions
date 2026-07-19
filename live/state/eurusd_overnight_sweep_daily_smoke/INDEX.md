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
| 3 | monthly_orb | Monthly ORB restricted scaleout3 | 321 | 963 | $21,841.25 | $-48,307.50 | 0.45 | 55.5 | ok |
| 4 | atr | ATR daily ladder 1/1/2/2/2 10-max | 224 | 438 | $-14,505.00 | $-137,313.00 | -0.11 | 24.9 | ok |
| 5 | atr | ATR daily 3-initial 10-max | 224 | 819 | $-42,242.00 | $-204,371.00 | -0.21 | 19.7 | ok |
| 6 | v2b_prior_opposed | v2b prior-opposed ST+PMC S_1_1_3 | 370 | 1850 | $-9,475.00 | $-21,021.00 | -0.45 | 38.4 | ok |
| 7 | atr | ATR weekly 2-initial / 3-add / 6-max | 83 | 257 | $-153,556.00 | $-290,014.00 | -0.53 | 9.7 | ok |
| 8 | monthly_orb | Monthly ORB restricted scaleout3 boundary-stop entry | 653 | 1959 | $-143,265.25 | $-154,605.25 | -0.93 | 37.8 | ok |

Progress log: `PROGRESS.log`
CSV: `summary.csv`
