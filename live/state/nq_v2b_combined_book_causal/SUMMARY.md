# NQ combined book — causal Engine+PaperBroker replay

Window 2021-03-04 -> 2026-03-05. Core = prior-opposed resting-limit S_1_1_3 (promoted causal book, units from its own
Engine+PaperBroker fills). Satellite = all-days v2b S_1_1_3 replayed via Engine+PaperBroker with
`regime_dates` restricted to days where **no gate limit was resting at 09:45** (available_at_ts from the
core's dynamic_sizing_events; gates arming later in the day may causally overlap and are kept).
`skipflat` additionally drops flat-gap days (OR-profile P1, 09:45-knowable). All portfolios audited on one
union 1m bar tape with merged units; hardened realism (1-tick slippage, $1.50/RT).

| Portfolio | Legs | Units | Traded days | Net | Closed DD | Stress DD | N/S | Max open | Win % | PF |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B_only | B | 2160 | 419 | $1,330,920 | $-68,110 | $-68,610 | 19.4 | 5 | 51.11 | 2.326 |
| A_full_only | A_full | 6890 | 921 | $870,920 | $-116,718 | $-118,094 | 7.37 | 5 | 38.59 | 1.188 |
| B_plus_A_full_stack | B+A_full | 9050 | 937 | $2,201,840 | $-167,690 | $-168,190 | 13.09 | 10 | 41.58 | 1.391 |
| B_plus_A_complement | B+A_comp | 6665 | 920 | $1,930,612 | $-108,120 | $-108,844 | 17.74 | 10 | 43.15 | 1.501 |
| B_plus_A_complement_skipflat | B+A_comp_skipflat | 5805 | 831 | $1,921,202 | $-84,816 | $-85,341 | 22.51 | 10 | 44.03 | 1.585 |