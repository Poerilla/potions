# Structure-program ST — broker-like replay

Plan **split15** risk=12 via StrategyPlugin `structure_program_st` + Engine/PaperBroker.

ES skipped (missing DBN). DSR TRL-2026-00072..074.

## Broker-like results

| market   | instrument   | plan    |   risk_pts | slug            |   sessions |   trades |   units |   net_usd |   win_rate_pct |   profit_factor |   st_flip_share_pct |
|:---------|:-------------|:--------|-----------:|:----------------|-----------:|---------:|--------:|----------:|---------------:|----------------:|--------------------:|
| nq       | NQ           | split15 |         12 | nq_split15_r12  |       2011 |      265 |    3970 |   -129680 |          38.54 |           0.659 |                80   |
| mnq      | MNQ          | split15 |         12 | mnq_split15_r12 |       1558 |      175 |    2620 |    -11905 |          32.82 |           0.618 |                80   |
| ym       | YM           | split15 |         12 | ym_split15_r12  |       1975 |      227 |    3400 |   -164200 |          32.5  |           0.327 |                81.1 |

## vs research (analytic)

| market   |   research_trades |   research_net_usd |   research_pf |   trades |   net_usd |   profit_factor |   st_flip_share_pct |
|:---------|------------------:|-------------------:|--------------:|---------:|----------:|----------------:|--------------------:|
| nq       |               355 |            1772175 |         7.244 |      265 |   -129680 |           0.659 |                80   |
| mnq      |               266 |             157787 |         7.648 |      175 |    -11905 |           0.618 |                80   |
| ym       |               318 |             607440 |        10.576 |      227 |   -164200 |           0.327 |                81.1 |

### Verdict

Analytic split15@12 edge **does not survive** broker-like replay (all three markets PF < 1, net negative). Dominant exit is next-bar / early `st_flip` (~80% of units). Do not promote on research-only numbers.
