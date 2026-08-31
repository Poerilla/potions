# Broker scale_run — where losses concentrate

PaperBroker NQ `nq_scale_run_r8` campaign + unit attribution.

## Headline

- Campaigns: **228** (losers 199) · net **$-102568**
- Unit PnL: `st_flip` (adverse) **$-198548** · `risk_stop` **$-106552** · `be_stop` **$-39800**
- Charts: worst **100** selected → **96** rendered in `charts/` (sum $-296200; a few skipped if session window missing)

## By year (campaign net)

|   year |   count |      sum |       mean |
|-------:|--------:|---------:|-----------:|
|   2020 |      45 | -18987.5 |  -421.944  |
|   2021 |      43 | -32155   |  -747.791  |
|   2022 |      29 |   5572.5 |   192.155  |
|   2023 |      34 | -32365   |  -951.912  |
|   2024 |      39 | -16302.5 |  -418.013  |
|   2025 |      29 |   1722.5 |    59.3966 |
|   2026 |       9 | -10052.5 | -1116.94   |

## Unit $ by year × exit_reason

|   year |   be_stop |   risk_stop |   runner_tp |   scale_22 |   scale_50 |   st_flip |
|-------:|----------:|------------:|------------:|-----------:|-----------:|----------:|
|   2020 |   -2050   |    -18532.5 |     19992.5 |    10912.5 |       9960 |  -39270   |
|   2021 |   -1457.5 |    -31995   |     19980   |     4385   |       9985 |  -33052.5 |
|   2022 |   -2160   |    -15435   |     19980   |    10912.5 |       9960 |  -17685   |
|   2023 |   -1180   |    -10890   |         0   |     8745   |       9960 |  -39000   |
|   2024 |  -18787.5 |    -14265   |         0   |    17490   |      29905 |  -30645   |
|   2025 |  -13732.5 |    -12862.5 |     19992.5 |    13080   |      24900 |  -29655   |
|   2026 |    -432.5 |     -2572.5 |         0   |     2192.5 |          0 |   -9240   |

## Loser campaigns by worst_reason

| worst_reason   |   count |       sum |      mean |
|:---------------|--------:|----------:|----------:|
| st_flip        |      91 | -198548   | -2181.84  |
| risk_stop      |      39 | -106552   | -2732.12  |
| be_stop        |      69 |  -23927.5 |  -346.775 |

## Takeaway

Most dollar damage is **adverse ST-flip flattens** (fav_be mode still exits when close is through entry), then **full risk_stop** on the 15-lot. Scale/runner legs are profitable but too rare under broker fills to offset.
