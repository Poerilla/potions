# Q1 fakeout reversal satellite — broker-like replay

Strategy: on q1-OR-width days (trailing 250 sessions, causal in-plugin history), a morning touch break
(before 10:30) that closes back inside the OR on a 5m close within 2 candles is reversed at market;
stop = failed extreme +/- tick; TPs at opposite boundary / opposite 1R. Regime gate MA50>MA150,
hardened realism (1-tick slippage, $1.50/RT). All thresholds fixed a priori from the OR profile tables.

| Market | Variant | Trades | Units | Net | Closed DD | Stress DD | N/S | Win % | PF |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NQ | split | 447 | 894 | $9,874 | $-16,512 | $-16,792 | 0.59 | 32.44 | 1.089 |
| NQ | opp_boundary | 447 | 894 | $8,019 | $-14,843 | $-14,890 | 0.54 | 40.72 | 1.086 |
| MNQ | split | 159 | 318 | $-110 | $-2,096 | $-2,128 | -0.05 | 30.19 | 0.986 |
| MNQ | opp_boundary | 159 | 318 | $-904 | $-2,248 | $-2,250 | -0.4 | 35.85 | 0.874 |

Yearly breakdowns: `<market>_<variant>_yearly.csv`.
## Verdict (2026-08-02) — NOT promotable

The 0.86–0.93 flip cell is real but does not convert into a standalone trade: the tight stop at the
failed extreme is clipped long before the boundary-to-boundary traverse completes (32–41% win vs the
naive 0.92 flip probability), and the v2b `oco_then_reverse` reverse leg already harvests the same move
via its opposite-boundary stop with better geometry. NQ split nets only $9.9k over 16 years (PF 1.089,
N/S 0.59, 8 negative years); MNQ is flat/negative. DSR ledger: TRL-2026-00062..65 (COMPLETE).
Keep as a negative known-answer for the FX rollout plan (`live/specs/OR_PROFILE_NEXT_PLANS.md`, Plan C step 5).
