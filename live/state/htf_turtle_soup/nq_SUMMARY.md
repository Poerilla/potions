# HTF turtle soup — NQ

Failed break of prior HTF high/low (close5 OUT→IN), then turtle-soup the swing.
Risk/targets from **that day's OR**: stop = R/5, 5ct, scale 4 @ opposite OR, runner opp 1R + BE.

## Level definitions (causal)

- **daily_3**: prior 3 RTH sessions high/low
- **weekly_4**: prior 4 complete ISO weeks high/low
- **monthly_2**: prior 2 complete calendar months high/low

## Signal counts

| Family | Signals | Wick≥0.25R |
|---|---:|---:|
| daily_3 | 248 | 187 |
| weekly_4 | 103 | 74 |
| monthly_2 | 64 | 46 |

## Books

| variant | sessions | fills | fill_rate_pct | full_stop | scaled_4 | scale_rate_pct | win_pct | net_usd | usd_per_fill | profit_factor | avg_risk_usd | neg_years | n_years |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| nq_weekly_4_wick25 | 74 | 61 | 82.4 | 50 | 11 | 18.0 | 18.0 | 31472.5 | 515.94 | 2.243 | 580.57 | 10 | 17 |
| nq_weekly_4 | 103 | 83 | 80.6 | 66 | 17 | 20.5 | 20.5 | 23627.5 | 284.67 | 1.519 | 720.96 | 8 | 17 |
| nq_monthly_2_wick25 | 46 | 28 | 60.9 | 25 | 3 | 10.7 | 10.7 | -6330.0 | -226.07 | 0.645 | 800.54 | 10 | 12 |
| nq_all_families_wick25 | 307 | 218 | 71.0 | 180 | 32 | 14.7 | 16.5 | -18945.0 | -86.9 | 0.86 | 748.51 | 9 | 17 |
| nq_monthly_2 | 64 | 42 | 65.6 | 37 | 5 | 11.9 | 11.9 | -22745.0 | -541.55 | 0.372 | 1014.17 | 11 | 13 |
| nq_daily_3_wick25 | 187 | 129 | 69.0 | 105 | 18 | 14.0 | 17.1 | -44087.5 | -341.76 | 0.524 | 816.63 | 9 | 16 |
| nq_all_families | 415 | 299 | 72.0 | 246 | 47 | 15.7 | 17.1 | -55592.5 | -185.93 | 0.723 | 796.76 | 10 | 17 |
| nq_daily_3 | 248 | 174 | 70.2 | 143 | 25 | 14.4 | 16.7 | -56475.0 | -324.57 | 0.525 | 780.43 | 12 | 16 |

## Yearly nets (unfiltered)

### daily_3

| year | net | n | win% |
|---:|---:|---:|---:|
| 2010 | $-340 | 2 | 0.0 |
| 2011 | $262 | 11 | 27.3 |
| 2012 | $5248 | 17 | 41.2 |
| 2013 | $-45 | 14 | 21.4 |
| 2014 | $-5600 | 16 | 0.0 |
| 2015 | $-4840 | 12 | 0.0 |
| 2016 | $-1415 | 10 | 10.0 |
| 2017 | $148 | 11 | 27.3 |
| 2018 | $-1510 | 8 | 12.5 |
| 2019 | $-410 | 8 | 37.5 |
| 2020 | $-12465 | 14 | 14.3 |
| 2021 | $-10015 | 18 | 16.7 |
| 2023 | $-6980 | 10 | 10.0 |
| 2024 | $-8215 | 8 | 0.0 |
| 2025 | $2632 | 11 | 18.2 |
| 2026 | $-12930 | 4 | 0.0 |

### weekly_4

| year | net | n | win% |
|---:|---:|---:|---:|
| 2010 | $890 | 2 | 50.0 |
| 2011 | $592 | 1 | 100.0 |
| 2012 | $-578 | 7 | 14.3 |
| 2013 | $1860 | 4 | 50.0 |
| 2014 | $-3240 | 14 | 0.0 |
| 2015 | $2510 | 4 | 25.0 |
| 2016 | $-1212 | 3 | 0.0 |
| 2017 | $-1912 | 13 | 15.4 |
| 2018 | $5208 | 5 | 60.0 |
| 2019 | $-20 | 4 | 50.0 |
| 2020 | $-6812 | 5 | 0.0 |
| 2021 | $-6425 | 4 | 0.0 |
| 2022 | $-2052 | 1 | 0.0 |
| 2023 | $648 | 7 | 14.3 |
| 2024 | $2158 | 3 | 33.3 |
| 2025 | $1848 | 3 | 33.3 |
| 2026 | $30168 | 3 | 33.3 |

### monthly_2

| year | net | n | win% |
|---:|---:|---:|---:|
| 2010 | $-365 | 2 | 0.0 |
| 2011 | $-122 | 1 | 0.0 |
| 2012 | $-380 | 2 | 0.0 |
| 2013 | $-630 | 2 | 0.0 |
| 2014 | $-965 | 4 | 0.0 |
| 2015 | $-1208 | 3 | 0.0 |
| 2017 | $-1575 | 4 | 0.0 |
| 2018 | $-130 | 2 | 50.0 |
| 2020 | $6332 | 3 | 33.3 |
| 2021 | $-9750 | 8 | 12.5 |
| 2023 | $332 | 1 | 100.0 |
| 2024 | $-10168 | 7 | 14.3 |
| 2025 | $-4118 | 3 | 0.0 |
## Verdict (2026-08-02)

- **daily_3** and **monthly_2** fail hard (PF < 1, large negative nets). Nearby daily levels fake out too often into continuation; monthly levels are sparse and stop-heavy.
- **weekly_4** is the only green family: unfiltered +$23.6k / PF 1.52; with wick≥0.25R **+$31.5k / PF 2.24**. But yearly stability is weak (8–10 negative years of 17) — same regime-concentration pattern as OR close5 fade. **Park as a research note**, not a promotion candidate. Geometry (HTF fail → turtle-soup with OR risk) is reusable if a stabler level set appears.
