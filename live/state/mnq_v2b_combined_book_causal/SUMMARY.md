# MNQ combined book — causal Engine+PaperBroker replay

Window 2021-03-04 -> 2026-03-03. Core = prior-opposed resting-limit S_1_1_3 (promoted causal book, units from its own
Engine+PaperBroker fills). Satellite = all-days v2b S_1_1_3 replayed via Engine+PaperBroker with
`regime_dates` restricted to days where **no gate limit was resting at 09:45** (available_at_ts from the
core's dynamic_sizing_events; gates arming later in the day may causally overlap and are kept).
`skipflat` additionally drops flat-gap days (OR-profile P1, 09:45-knowable). All portfolios audited on one
union 1m bar tape with merged units; hardened realism (1-tick slippage, $1.50/RT).

| Portfolio | Legs | Units | Traded days | Net | Closed DD | Stress DD | N/S | Max open | Win % | PF |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| B_only | B | 2140 | 416 | $128,360 | $-6,905 | $-6,960 | 18.44 | 5 | 51.03 | 2.257 |
| A_full_only | A_full | 6856 | 918 | $76,148 | $-12,234 | $-12,372 | 6.15 | 5 | 38.39 | 1.163 |
| B_plus_A_full_stack | B+A_full | 8996 | 934 | $204,508 | $-17,111 | $-17,156 | 11.92 | 10 | 41.4 | 1.36 |
| B_plus_A_complement | B+A_comp | 6635 | 919 | $178,441 | $-10,986 | $-11,053 | 16.14 | 10 | 42.91 | 1.457 |
| B_plus_A_complement_skipflat | B+A_comp_skipflat | 5770 | 828 | $182,965 | $-8,316 | $-8,606 | 21.26 | 10 | 44.06 | 1.554 |