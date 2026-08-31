# Structure-program ST sweep

ES skipped (missing DBN). NQ risk/plan sweep + cross-market split15@12.

| market    | plan    |   risk_pts |   trades |          net_usd |   win_pct |   profit_factor |   avg_usd |   mae_med |   scaled_pct |
|:----------|:--------|-----------:|---------:|-----------------:|----------:|----------------:|----------:|----------:|-------------:|
| nq        | split15 |         12 |      355 |      1.77218e+06 |      69   |           7.244 |    4992   |      3.5  |           44 |
| nq        | split15 |          8 |      324 |      1.729e+06   |      69.8 |           9.612 |    5336.4 |      3    |           55 |
| nq        | split15 |         10 |      349 |      1.7266e+06  |      69.1 |           7.704 |    4947.3 |      3.5  |           50 |
| nq        | split15 |         20 |      378 |      1.63219e+06 |      66.1 |           4.924 |    4318   |      4.25 |           29 |
| nq        | split15 |         16 |      372 |      1.53146e+06 |      67.5 |           5.072 |    4116.8 |      4    |           33 |
| ym        | split15 |         12 |      318 | 607440           |      73.9 |          10.576 |    1910.2 |      4    |           63 |
| usdjpy_ny | split15 |         12 |      783 | 503055           |      72.5 |           5.203 |     642.5 |      0    |           12 |
| eurusd_ny | split15 |         12 |      842 | 450660           |      71.3 |           5.475 |     535.2 |      0    |            8 |
| nq        | scale4  |         20 |      396 | 176478           |      64.9 |           2.422 |     445.7 |      3.5  |           28 |
| mnq       | split15 |         12 |      266 | 157787           |      65.8 |           7.648 |     593.2 |      3.38 |           46 |
| nq        | scale4  |         16 |      387 | 133926           |      65.9 |           2.188 |     346.1 |      3.25 |           33 |
| nq        | scale4  |         12 |      369 | 119332           |      67.8 |           2.405 |     323.4 |      2    |           43 |
| nq        | scale4  |         10 |      377 | 115416           |      68.2 |           2.466 |     306.1 |      1.75 |           50 |
| us30      | split15 |         12 |      271 | 105176           |      71.6 |          10.043 |     388.1 |      3    |           58 |
| nas100    | split15 |         12 |      351 |  84090           |      64.7 |           7.253 |     239.6 |      3.1  |           40 |
| xauusd_ny | split15 |         12 |      863 |  13563           |      68.4 |           3.009 |      15.7 |      0    |            3 |

**Best research row:** market=nq plan=split15 risk=12.0 net=$1772175 PF=7.244 WR=69.0% (n=355)

Broker-like gates (all NQ fails):
- split15 r12 → `live/state/structure_program_st_broker/` (TRL-2026-00072) and ST-flip variants
- scale_run r8 fav_be → `live/state/structure_program_st_broker_scale_run/` (TRL-2026-00079) **−$103k PF 0.70**
- Path: [RESEARCH_PATH.md](RESEARCH_PATH.md)

## Broker-like verdict (TRL-2026-00072)

| market   |   trades |   net_usd |   profit_factor |   st_flip_share_pct |
|:---------|---------:|----------:|----------------:|--------------------:|
| nq       |      265 |   -129680 |           0.659 |                80   |
| mnq      |      175 |    -11905 |           0.618 |                80   |
| ym       |      227 |   -164200 |           0.327 |                81.1 |

Analytic best (NQ split15 r12 +$1.77M PF 7.2) **fails** PaperBroker gate. Details: `live/state/structure_program_st_broker/SUMMARY.md`.
