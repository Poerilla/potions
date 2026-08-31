# NQ failure_fade_reclaim as PRIMARY — MAE / MFE autopsy

Reclaim legs only (not gated behind fade PnL). Source tape: playbook `trades.csv`.

- N: **12**
- Net: **$183,888.50**
- Losers: **7** · Winners: **5**

## Failure modes

| Mode | N | Meaning |
|---|---:|---|
| stop_too_tight_big_winner | 5 | Stopped, then post-exit path still tagged TP2 or ≥2R from entry |
| stop_too_tight_recover | 0 | Stopped, then recovered ≥1R / TP1 |
| hard_loss | 2 | Stopped and did not recover |
| runner_left_on_table | 2 | Winner (often BE) that left ≥1R of hold-MFE |
| full_tp2 / quarter_hold / winner_ok | 3 | Captured intended runner |

Counts: `{'stop_too_tight_big_winner': 5, 'runner_left_on_table': 2, 'hard_loss': 2, 'quarter_hold': 1, 'full_tp2': 1, 'winner_ok': 1}`

## Could losers turn into large winners?

- Losers that later reached TP2 or ≥2R post-exit: **5 / 7**
- Losers that recovered ≥1R / TP1 post-exit (incl. big): **5 / 7**
- Reach TP2 if stop were **3R** (path MAE < 3R and TP2 tagged): **3 / 12**
- Reach TP2 if stop were **4R**: **3 / 12**

## Per-trade

| # | Q | Side | Exit | Net | MAE R | MFE R | Post MFE R | Left R | Mode | 3R→TP2 |
|---:|---|---|---|---:|---:|---:|---:|---:|---|---|
| 1 | 2012Q3 | short | stop | $-9,765 | 1.18 | 0.20 | 3.72 | 3.52 | stop_too_tight_big_winner |  |
| 2 | 2013Q2 | short | stop | $-7,615 | 1.06 | 0.07 | 1.86 | 1.79 | stop_too_tight_big_winner |  |
| 3 | 2014Q4 | long | stop | $-2,865 | 9.79 | 0.12 | 37.12 | 37.00 | stop_too_tight_big_winner |  |
| 4 | 2015Q4 | short | be_stop | $10,849 | 0.31 | 2.17 | 7.50 | 5.33 | runner_left_on_table | Y |
| 5 | 2016Q1 | long | be_stop | $8,752 | 0.27 | 1.66 | 5.75 | 4.09 | runner_left_on_table | Y |
| 6 | 2020Q4 | short | be_stop | $-11,065 | 0.89 | 0.69 | 0.00 | 0.00 | hard_loss |  |
| 7 | 2021Q1 | short | be_stop | $-65 | 0.41 | 0.61 | 2.23 | 1.62 | stop_too_tight_big_winner |  |
| 8 | 2021Q3 | short | stop | $-17,815 | 2.16 | 0.84 | 2.52 | 1.68 | stop_too_tight_big_winner |  |
| 9 | 2022Q1 | long | quarter_eod | $127,456 | 0.99 | 1.24 | 1.18 | 0.00 | quarter_hold |  |
| 10 | 2022Q2 | long | stop | $-41,965 | 1.60 | 0.03 | 0.62 | 0.58 | hard_loss |  |
| 11 | 2023Q4 | long | tp2 | $91,518 | 0.03 | 1.55 | 5.08 | 3.52 | full_tp2 | Y |
| 12 | 2025Q1 | long | be_stop | $36,468 | 0.93 | 1.44 | 2.36 | 0.92 | winner_ok |  |

## Charts

Annotated PNGs in `charts/` (MAE/MFE lines + failure-mode in title).

| # | Chart | Mode | Net |
|---:|---|---|---:|
| 1 | [01_2012Q3_short_stop_stop_too_tight_big_winner.png](charts/01_2012Q3_short_stop_stop_too_tight_big_winner.png) | stop_too_tight_big_winner | $-9,765 |
| 2 | [02_2013Q2_short_stop_stop_too_tight_big_winner.png](charts/02_2013Q2_short_stop_stop_too_tight_big_winner.png) | stop_too_tight_big_winner | $-7,615 |
| 3 | [03_2014Q4_long_stop_stop_too_tight_big_winner.png](charts/03_2014Q4_long_stop_stop_too_tight_big_winner.png) | stop_too_tight_big_winner | $-2,865 |
| 4 | [04_2015Q4_short_be_stop_runner_left_on_table.png](charts/04_2015Q4_short_be_stop_runner_left_on_table.png) | runner_left_on_table | $10,849 |
| 5 | [05_2016Q1_long_be_stop_runner_left_on_table.png](charts/05_2016Q1_long_be_stop_runner_left_on_table.png) | runner_left_on_table | $8,752 |
| 6 | [06_2020Q4_short_be_stop_hard_loss.png](charts/06_2020Q4_short_be_stop_hard_loss.png) | hard_loss | $-11,065 |
| 7 | [07_2021Q1_short_be_stop_stop_too_tight_big_winner.png](charts/07_2021Q1_short_be_stop_stop_too_tight_big_winner.png) | stop_too_tight_big_winner | $-65 |
| 8 | [08_2021Q3_short_stop_stop_too_tight_big_winner.png](charts/08_2021Q3_short_stop_stop_too_tight_big_winner.png) | stop_too_tight_big_winner | $-17,815 |
| 9 | [09_2022Q1_long_quarter_eod_quarter_hold.png](charts/09_2022Q1_long_quarter_eod_quarter_hold.png) | quarter_hold | $127,456 |
| 10 | [10_2022Q2_long_stop_hard_loss.png](charts/10_2022Q2_long_stop_hard_loss.png) | hard_loss | $-41,965 |
| 11 | [11_2023Q4_long_tp2_full_tp2.png](charts/11_2023Q4_long_tp2_full_tp2.png) | full_tp2 | $91,518 |
| 12 | [12_2025Q1_long_be_stop_winner_ok.png](charts/12_2025Q1_long_be_stop_winner_ok.png) | winner_ok | $36,468 |
