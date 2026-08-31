# NQ Quarterly Extreme Playbook Backtest

First daily touch of prior-quarter high/low → **one primary trade per quarter** (plus optional one-shot `failure_fade_reclaim` after a failed fade).

- Daily: `/home/tester/hsm/potions/nq/nq_daily.csv`
- Quarter rows (primary): **63**
- Filled legs: **67**
- No touch: **5**
- Limit unfilled: **3**
- Reclaim unfilled: **6**

## Rules

1. **failure_fade** — wick through, close back in range → market fade @ close; SL = touch adverse extreme; 5 @ 15% into range; BE on first week-close in range; 5 @ 62%.
   - **Reclaim (once, only if fade exits `stop`/`be_stop`):** significant level = original SL (sweep H/L). Wait close through then close back → market same direction. SL = prior entry ± 2× prior risk. Same 10/5/5 exits; TP1 = new entry ± 14% of prior width; TP2 kept from the failed fade. Sequence ends after this leg.
2. **on_level_cont** — close on extreme (±0.5% of prior width, min 1pt) → limit @ close; 5 @ 14% ext / 5 @ 62% ext.
3. **close_through_cont** — close beyond extreme → limit @ extreme; 5 @ 30% / 5 @ 62% ext.

Costs: 1-tick adverse slip on market/stop; $1.50/unit; NQ $20/pt. Stop before targets same bar.

## Overall (filled legs)

- N: **67**
- Net: **$284,890.50**
- Win%: **25.4%**
- Avg/trade: **$4,252.10**
- PF: **1.45**
- Max DD (trade equity): **$-178,130.00**
- Net/|DD|: **1.60**

## By setup

| Setup | N | Net $ | Win% | Avg $ | PF | MaxDD $ | Net/|DD| |
|---|---:|---:|---:|---:|---:|---:|---:|
| failure_fade | 22 | 59461.50 | 27.3 | 2702.80 | 1.39 | -58445.00 | 1.02 |
| failure_fade_reclaim | 12 | 183888.50 | 41.7 | 15324.04 | 3.02 | -41965.00 | 4.38 |
| on_level_cont | 7 | 5048.50 | 28.6 | 721.21 | 1.16 | -20880.00 | 0.24 |
| close_through_cont | 26 | 36492.00 | 15.4 | 1403.54 | 1.10 | -300845.00 | 0.12 |

## failure_fade sequence (primary ± reclaim, by quarter)

- Sequences with any filled fade leg: **22**
- Combined net: **$243,350.00**
- Win% (sequence): **40.9%**
- PF: **2.76**
- Max DD: **$-87,390.00**
- Net/|DD|: **2.78**
- Quarters that filled a reclaim: **12**

## By side

| Side | N | Net $ | Win% | PF |
|---|---:|---:|---:|---:|
| long | 45 | 8161.50 | 26.7 | 1.02 |
| short | 22 | 276729.00 | 22.7 | 3.16 |

## Exit mix

- `stop`: **45**
- `be_stop`: **12**
- `tp2`: **8**
- `quarter_eod`: **2**

## By year (next quarter)

| Year | N | Net $ | Win% |
|---:|---:|---:|---:|
| 2010 | 2 | -4680.00 | 0.0 |
| 2011 | 3 | -1355.00 | 33.3 |
| 2012 | 4 | 19996.75 | 25.0 |
| 2013 | 4 | 9339.25 | 50.0 |
| 2014 | 5 | -3180.50 | 20.0 |
| 2015 | 5 | -7761.50 | 20.0 |
| 2016 | 4 | -7143.00 | 25.0 |
| 2017 | 4 | 74476.00 | 50.0 |
| 2018 | 4 | 9321.50 | 25.0 |
| 2019 | 3 | -18395.00 | 0.0 |
| 2020 | 5 | -78275.00 | 0.0 |
| 2021 | 6 | 7533.75 | 16.7 |
| 2022 | 5 | 92844.00 | 40.0 |
| 2023 | 5 | 30191.25 | 40.0 |
| 2024 | 3 | -121195.00 | 0.0 |
| 2025 | 5 | 283173.00 | 40.0 |

## Files

- `trades.csv`
- `trades_all_quarters.csv`
