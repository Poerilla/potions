# EURUSD — untried MNQ idea scout

Pandas/path scout (closed-equity DD). Unit = 1 lot, fee $1.50, ~0.5 pip half-spread.
ORB session: NY 09:30–09:45. Window 2015-01-01 → 2026-03-31.

Pass gate: `(net > 0 and Net/closed-DD ≥ 1.0)` or `net ≥ $23.5k with positive Net/DD`.

| Strategy | Net | Closed DD | Net/DD | Trades | WR | Gate |
|---|---:|---:|---:|---:|---:|:---:|
| B3_atr_fade_touch_ny | $-1,533 | $-3,181 | -0.48 | 25 | 56.0% | fail |
| B2_pm_sweep_daily | $-7,098 | $-27,320 | -0.26 | 217 | 41.5% | fail |
| B1_fib62_london_long | $-9,463 | $-11,470 | -0.82 | 651 | 40.2% | fail |
| A1_adaptive_v2b_only | $-11,201 | $-12,239 | -0.92 | 1352 | 52.1% | fail |
| B4_c3_hit_orb_fade | $-15,524 | $-16,994 | -0.91 | 947 | 47.0% | fail |
| A7_swept_orb | $-26,062 | $-26,054 | -1.00 | 1563 | 41.1% | fail |
| A3_clean_break | $-31,711 | $-32,052 | -0.99 | 2914 | 37.2% | fail |
| A2_adaptive_v2b_v2d | $-38,526 | $-39,130 | -0.98 | 2902 | 48.5% | fail |
| A5_orb_open_limit | $-49,112 | $-49,542 | -0.99 | 4763 | 41.2% | fail |
| A4_v1b_pullback | $-49,210 | $-49,856 | -0.99 | 5355 | 50.8% | fail |
| B5_daily_c3_breakout | $-68,400 | $-190,299 | -0.36 | 2368 | 40.5% | fail |
| A6_breakout_close_limit | $-106,986 | $-107,898 | -0.99 | 5827 | 52.7% | fail |
| B3_midnight_flip_ny | $-137,266 | $-153,604 | -0.89 | 9080 | 24.4% | fail |
| B3_midnight_flip_london | $-206,809 | $-212,860 | -0.97 | 10466 | 21.3% | fail |
| B5_monthly_c3_breakout | $-290,794 | $-357,266 | -0.81 | 88 | 30.7% | fail |

## Survivors for broker-like

None cleared the scout gate.

## Deferred Wave C (only if a parent cleared)

- v2b_child / open-limit child
- v2b_m monthly-break bias
- Monthly ORB overlap ST retest / stop-limit cycle
- adaptive_experiment 60% retrace / strict clean-break forks

## Already tried on FX (skipped)

Yearly ORB, Monthly ORB restricted/boundary, ATR DCA, Hourly ST+PMC, ungated v2b OCO,
prior-opposed / PMC / YORB / monthly-swing v2b gates, London sweep reversal, OR fade,
WO gap, weekly-mid, 15m ST DCA/fade.

CSV: `leaderboard.csv`
