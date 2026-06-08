# V2B Family Broker-Like Replay Ranking

Purpose: compare the v2b family on implementable timing assumptions. The strongest-confidence rows are `1m StrategyPlugin` because they run through the same flat-file `Engine` + `PaperBroker` path intended for live automation. `1m scanner`, `5m broker-like artifact`, and `artifact audit` rows are useful triage, but should not outrank true StrategyPlugin rows for live execution.

| Rank | Candidate | Timing | Trades | Units | Net | Closed DD | Intrabar Stress DD | Max Units | Net / Stress | Win % | PF |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | v2b scaleout x2 MA50>MA150 long-priority | 1m scanner diagnostic | 1302 | 2604 | $83,245.00 | $-2,729.50 | $-3,130.00 | 2 | 26.60 | 59.7% | 1.60 |
| 2 | v2b scaleout x2 C3 days only | 1m scanner diagnostic | 954 | 1908 | $57,395.50 | $-3,887.50 | $-4,412.50 | 2 | 13.01 | 58.2% | 1.49 |
| 3 | v2b scaleout x2 C3 + MA50>MA150 | 1m scanner diagnostic | 681 | 1362 | $41,844.50 | $-3,887.50 | $-4,412.50 | 2 | 9.48 | 59.2% | 1.56 |
| 4 | v2b scaleout x2 MA50>MA150 OCO then reverse | 1m StrategyPlugin | 1406 | 2806 | $34,444.50 | $-5,841.50 | $-5,869.50 | 2 | 5.87 | 46.2% | 1.19 |
| 5 | v2b clean break bullish 2R | 5m StrategyPlugin | 675 | 675 | $9,498.50 | $-1,886.50 | $-1,950.00 | 1 | 4.87 | 28.9% | 1.25 |
| 6 | adaptive inside-v2b close child Regime=v2b | 1m child artifact audit | 771 | 1208 | $12,187.50 | $-2,893.00 | $-3,505.50 | 3 | 3.48 | 32.9% | 1.30 |
| 7 | v2b child max 1 add | 1m child artifact audit | 1992 | 3144 | $20,602.50 | $-5,609.50 | $-6,080.50 | 2 | 3.39 | 51.3% | 1.12 |
| 8 | v2b_m long-only monthly bias | artifact audit | 363 | 363 | $3,936.00 | $-1,106.00 | $-1,254.50 | 1 | 3.14 | 54.5% | 1.18 |
| 9 | v2b scaleout x2 MA50>MA150 strict long-then-short | 1m StrategyPlugin | 1052 | 2102 | $18,926.50 | $-6,153.00 | $-6,163.00 | 2 | 3.07 | 46.1% | 1.14 |
| 10 | v2b child max 2 adds | 1m child artifact audit | 1992 | 3857 | $22,608.00 | $-6,742.00 | $-7,476.50 | 3 | 3.02 | 48.4% | 1.12 |
| 11 | adaptive child Regime=v2b only | 1m child artifact audit | 1437 | 2792 | $19,063.00 | $-5,442.00 | $-6,369.00 | 3 | 2.99 | 49.1% | 1.16 |
| 12 | v2b 09:45 clean break, old RL stop baseline | 5m StrategyPlugin | 436 | 436 | $5,110.50 | $-3,256.00 | $-3,280.50 | 1 | 1.56 | 28.9% | 1.20 |
| 13 | v2b 09:45 clean break boundary stop | 5m StrategyPlugin | 439 | 439 | $1,553.50 | $-1,023.50 | $-1,053.50 | 1 | 1.47 | 8.2% | 1.19 |
| 14 | v2b 09:45 clean break ladder3 runner | 5m StrategyPlugin | 439 | 1317 | $2,363.00 | $-3,012.50 | $-3,123.00 | 3 | 0.76 | 9.6% | 1.10 |

## Read

- The main promotion test is `Net / Stress DD`, not net alone.
- The `$83k` row is preserved because it is reproducible, but it is a scanner: it can select a later Long while ignoring an earlier Short. Use the `1m StrategyPlugin` OCO row for live-orderable planning.
- Clean-break variants now have real 5m `StrategyPlugin` replays. The broad bullish clean-break survives, but does not beat the hardened OCO-then-reverse row on MNQ. Child variants still need plugin promotion before they compete with daily broker-like candidates.
- Rows with approximate stress use the best available artifact fields and are intentionally labeled that way.

## Clean-Break StrategyPlugin Replays

Full output: [`../../v2b_clean_break_broker_like/V2B_CLEAN_BREAK_BROKER_LIKE.md`](../../v2b_clean_break_broker_like/V2B_CLEAN_BREAK_BROKER_LIKE.md). These rows use completed 5-minute RTH bars. Entry stops can fill during the breakout candle, but clean-close validation happens only after that candle closes; protective exits become active from the next 5-minute bar.

| Rank | Market | Variant | Trades | Units | Net | Intrabar Stress DD | Net / Stress | Win % | PF |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | NQ | Bullish clean break, 2R target, RL stop | 2039 | 2039 | $112,026.50 | $-19,115.00 | 5.86 | 28.2% | 1.20 |
| 2 | MNQ | Bullish clean break, 2R target, RL stop | 675 | 675 | $9,498.50 | $-1,950.00 | 4.87 | 28.9% | 1.25 |
| 3 | NQ | 09:45 clean break, 2R target, boundary stop | 1161 | 1161 | $31,333.50 | $-9,513.00 | 3.29 | 8.0% | 1.29 |
| 4 | NQ | 09:45 clean break, 2R target, RL stop baseline | 1157 | 1157 | $85,804.50 | $-32,059.50 | 2.68 | 28.0% | 1.25 |
| 5 | NQ | 09:45 clean break, 3-lot ladder runner | 1161 | 3483 | $62,205.50 | $-27,315.50 | 2.28 | 9.5% | 1.20 |
| 6 | MNQ | 09:45 clean break, 2R target, RL stop baseline | 436 | 436 | $5,110.50 | $-3,280.50 | 1.56 | 28.9% | 1.20 |
| 7 | MNQ | 09:45 clean break, 2R target, boundary stop | 439 | 439 | $1,553.50 | $-1,053.50 | 1.47 | 8.2% | 1.19 |
| 8 | MNQ | 09:45 clean break, 3-lot ladder runner | 439 | 1317 | $2,363.00 | $-3,123.00 | 0.76 | 9.6% | 1.10 |

Read: clean breaks are real, but the broad version is the only one with enough occurrence density to matter on MNQ. The 09:45 boundary-stop variant cuts stress but also strips too many eventual winners; the 3-lot runner adds exposure faster than it adds edge.

## Cross-Market OCO Then Reverse

Common-start replay: `2021-03-04` onward, using the hardened `v2b_scaleout` StrategyPlugin path with OCO breakout stops, TP1 + runner, and reverse side allowed only after the first campaign closes. Full report: [`../../v2b_strategy_plugin_cross_market_requested/V2B_OCO_CROSS_MARKET_COMMON_WINDOW.md`](../../v2b_strategy_plugin_cross_market_requested/V2B_OCO_CROSS_MARKET_COMMON_WINDOW.md).

| Rank | Market | Net | Intrabar Stress DD | Net / Stress | Win % | PF | Read |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | NQ | $389,026.50 | $-58,840.00 | 6.61 | 46.4% | 1.21 | Best hardened V2B market on this pass. |
| 2 | MNQ | $34,444.50 | $-5,869.50 | 5.87 | 46.2% | 1.19 | Still the best low-capital expression. |
| 3 | YM | $76,271.25 | $-51,933.25 | 1.47 | 45.4% | 1.10 | Positive but much weaker stress-adjusted edge. |
| 4 | ES | $63,239.50 | $-73,105.00 | 0.87 | 42.2% | 1.06 | Positive net, weak efficiency. |
| 5 | MYM | $4,092.25 | $-6,805.62 | 0.60 | 44.7% | 1.05 | Barely positive. |
| 6 | MES | $1,466.75 | $-5,517.75 | 0.27 | 42.8% | 1.04 | Partial CSV coverage only; DBN is corrupted locally. |

NQ chart pack: [`../../v2b_strategy_plugin_cross_market_requested/charts/nq_v2b_scaleout_oco_then_reverse/INDEX.md`](../../v2b_strategy_plugin_cross_market_requested/charts/nq_v2b_scaleout_oco_then_reverse/INDEX.md).
