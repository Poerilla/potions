# V2B OCO Then Reverse Cross-Market Replay - Common Window

This compares the hardened live-orderable `v2b_scaleout` StrategyPlugin across markets on a shared start date: **2021-03-04**. The mechanics are the same as the MNQ hardening pass: prior-day MA50 > MA150, 09:30-09:45 RTH opening range, both OCO breakout stops armed after the OR completes, 2 contracts, TP1 plus runner to TP2, reverse side allowed after the first campaign closes, and PaperBroker pessimistic same-bar ordering.

| Rank | Market | Regime Days | Units | Trades | Net | Closed DD | Intrabar Stress DD | Net / Stress | Win % | PF | Coverage |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | NQ | 1164 | 2809 | 1407 | $389,026.50 | $-58,550.00 | $-58,840.00 | 6.61 | 46.4% | 1.21 | common start to local data end |
| 2 | MNQ | 1164 | 2806 | 1406 | $34,444.50 | $-5,841.50 | $-5,869.50 | 5.87 | 46.2% | 1.19 | common start to local data end |
| 3 | YM | 1182 | 2835 | 1425 | $76,271.25 | $-51,893.25 | $-51,933.25 | 1.47 | 45.4% | 1.10 | common start to local data end |
| 4 | ES | 1195 | 3082 | 1544 | $63,239.50 | $-72,905.00 | $-73,105.00 | 0.87 | 42.2% | 1.06 | common start to local data end |
| 5 | MYM | 1160 | 2777 | 1396 | $4,092.25 | $-6,801.62 | $-6,805.62 | 0.60 | 44.7% | 1.05 | common start to local data end |
| 6 | MES | 517 | 1338 | 670 | $1,466.75 | $-5,507.75 | $-5,517.75 | 0.27 | 42.8% | 1.04 | partial: CSV ends 2023-08-17 |

## Read

- **NQ is the best cross-market OCO-then-reverse V2B row** on this window: highest net and highest Net/Stress.
- **MNQ remains strong on capital efficiency**, but nominal net is one-tenth of NQ because of the point multiplier.
- YM, ES, MYM, and MES are positive but not attractive enough to outrank the NQ/MNQ pair under this exact V2B logic.
- MES used `mes/mes_1min_raw.csv` because the local MES DBN throws a zstd corruption error; treat the MES row as partial coverage only.

## Charts

- NQ chart pack: [`charts/nq_v2b_scaleout_oco_then_reverse/INDEX.md`](charts/nq_v2b_scaleout_oco_then_reverse/INDEX.md)
- MNQ chart pack from original hardening pass: [`../v2b_strategy_plugin_replay/charts/oco_then_reverse/INDEX.md`](../v2b_strategy_plugin_replay/charts/oco_then_reverse/INDEX.md)
