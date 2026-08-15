# Turtle soup of the failed-break swing (close5-confirmed)

Universe: same close5 OUT→IN q1-regime signals as A1 (203 sessions).
Entry = limit at the **failed extreme** (the swing the fakeout made).
Stop = that swing ± **R/5**. Size **5**: scale **4** at opposite OR boundary, **1 runner**.

## Book stats (NQ, 1-tick analytic, $1.50/RT/unit)

| variant | sessions | fills | fill_rate_pct | full_stop | scaled_4 | runner_tp | runner_sl | runner_eod | scale_rate_of_fills_pct | net_usd | usd_per_fill | profit_factor | avg_risk_pts | avg_risk_usd_5ct |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TS_opp1r | 203 | 143 | 70.4 | 109 | 31 | 9 | 11 | 14 | 21.7 | 41830.5 | 292.52 | 1.869 | 4.33 | 433.36 |
| TS_opp1r_be | 203 | 143 | 70.4 | 109 | 31 | 9 | 12 | 13 | 21.7 | 42637.5 | 298.16 | 1.886 | 4.33 | 433.36 |
| TS_eod | 203 | 143 | 70.4 | 109 | 31 | 0 | 12 | 22 | 21.7 | 43519.5 | 304.33 | 1.905 | 4.33 | 433.36 |
| TS_eod_be | 203 | 143 | 70.4 | 109 | 31 | 0 | 13 | 21 | 21.7 | 44362.5 | 310.23 | 1.922 | 4.33 | 433.36 |

## Yearly (`TS_opp1r_be`)

| year | net | n | wins | win% |
|---:|---:|---:|---:|---:|
| 2010 | $252 | 3 | 1 | 33.3 |
| 2011 | $-175 | 12 | 2 | 16.7 |
| 2012 | $-615 | 6 | 0 | 0.0 |
| 2013 | $-638 | 11 | 1 | 9.1 |
| 2014 | $55 | 6 | 1 | 16.7 |
| 2015 | $1158 | 3 | 1 | 33.3 |
| 2016 | $9808 | 17 | 9 | 52.9 |
| 2017 | $1250 | 12 | 3 | 25.0 |
| 2018 | $-162 | 1 | 0 | 0.0 |
| 2019 | $2132 | 17 | 4 | 23.5 |
| 2020 | $-935 | 2 | 0 | 0.0 |
| 2021 | $10045 | 12 | 3 | 25.0 |
| 2022 | $10772 | 3 | 2 | 66.7 |
| 2023 | $23010 | 16 | 6 | 37.5 |
| 2024 | $-1808 | 11 | 1 | 9.1 |
| 2025 | $-11512 | 11 | 0 | 0.0 |

Negative years: 7 / 16. Charts: `charts/turtle_soup/`.
## Read (2026-08-02)

This is the first structure that looks *asymmetric the right way* on this signal:

- **Expectancy ≈ +0.64R** per fill (risk ≈ R/5 per contract × 5 = ~$433 avg risk).
- **Win rate only 24%**, but median win $1,610 vs median loss $238 — the classic turtle-soup payoff.
- **Scale rate 22%** (31/143): most fills never reach the opposite OR; they die at the tight swing stop. When they *do* scale, mean PnL is ~$2.8k.
- **Fill rate 70%**: after close5 IN, price retests the failed extreme often enough to arm the soup.
- **Stability still uneven**: 9/16 years green; 2010–2020 nets **+$12.1k** (unlike A1 which was flat that decade — a real improvement), but 2023 alone is +$23k and **2025 is −$11.5k / 0 wins**. Fails the ≥70%-of-years bar as a promotion candidate, but the geometry is worth keeping and refining (stop buffer vs R/5 floor in ticks, runner rule, q1+gap filters).

Charts: `live/state/q1_fakeout_satellite/charts/turtle_soup/` (5 winners / 5 losers, gates labeled).
