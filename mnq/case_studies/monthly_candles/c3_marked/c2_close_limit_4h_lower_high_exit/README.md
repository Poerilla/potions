# MNQ Monthly C3: C2-Close Limit Long / Daily Lower-High Exit

Long-only replacement study after discarding the 5-minute ATR drill-down.

## Rules

- Use every monthly C3 setup.
- During the C3 month, arm a buy limit at the C2 monthly close after a confirmed 4-hour close above C2 close.
- Fill is modeled on a later 4-hour bar touch at the C2 close.
- Exit if a 4-hour candle closes `50` points below the C2 close.
- Exit when the daily chart confirms a lower high, filled at the next 4-hour bar open.
- Unlimited re-entry attempts are allowed while still inside the C3 month.
- Entries stop after the C3 month, but an open trade can continue until an exit signal appears.
- Position size is 1 MNQ contract.

## Summary

| bucket                                     |   setups |   filled_setups |   trades |   wins |   win_rate |   net_pts |   net_usd |   max_closed_dd_usd |   profit_factor |   avg_trade_usd |   avg_mae_pts |   worst_mae_pts |   avg_mfe_pts |
|:-------------------------------------------|---------:|----------------:|---------:|-------:|-----------:|----------:|----------:|--------------------:|----------------:|----------------:|--------------:|----------------:|--------------:|
| all                                        |       46 |              39 |      125 |     57 |      45.6  |   2865.5  |    5731   |             -3168   |           1.386 |           45.85 |       -105.07 |         -541.5  |        201.62 |
| c3_bearish                                 |       46 |              10 |       32 |      9 |      28.12 |   -173.5  |    -347   |             -3240.5 |           0.938 |          -10.84 |       -140.01 |         -541.5  |        265.9  |
| c3_bullish                                 |       46 |              29 |       93 |     48 |      51.61 |   3039    |    6078   |             -2524   |           1.658 |           65.35 |        -93.05 |         -446    |        179.5  |
| c3_hit_False                               |       46 |               7 |       13 |      6 |      46.15 |   1316    |    2632   |              -689.5 |           3.385 |          202.46 |        -72.98 |         -161.25 |        243.81 |
| c3_hit_True                                |       46 |              32 |      112 |     51 |      45.54 |   1549.5  |    3099   |             -2583.5 |           1.226 |           27.67 |       -108.8  |         -541.5  |        196.72 |
| exit_4h_close_50pt_below_c2_close          |       46 |              20 |       31 |      0 |       0    |  -4081    |   -8162   |             -8162   |           0     |         -263.29 |       -178.16 |         -541.5  |        205.31 |
| exit_daily_lower_high_next_4h_open         |       46 |              30 |       68 |     57 |      83.82 |  10037.8  |   20075.5 |              -191   |          42.393 |          295.23 |        -49.96 |         -256.75 |        239.38 |
| exit_same_bar_4h_close_50pt_below_c2_close |       46 |              17 |       26 |      0 |       0    |  -3091.25 |   -6182.5 |             -6182.5 |           0     |         -237.79 |       -162.08 |         -430    |         98.45 |

## Setup Notes

- C3 setups reviewed: `46`
- Setups with at least one fill: `39`
- Maximum hold window after C3 month end: `90` days.

## Files

- [trades.csv](trades.csv)
- [setup_summary.csv](setup_summary.csv)
- [summary.csv](summary.csv)

## Chart Sets

- [All chart collections](charts/INDEX.md)
- [Daily lower-high winners](charts/daily_lower_high_exits/winners/INDEX.md)
- [Daily lower-high losers](charts/daily_lower_high_exits/losers/INDEX.md)
- [All losers](charts/all_losers/INDEX.md)

## Stop-Condition Notes

The current 50-point 4-hour close stop is the main weak point. The daily lower-high exit group is strong on its own, but the stop failures produce large givebacks:

- Daily lower-high exits: `68` trades, `57` winners, `83.82%` win rate, `+$20,075.50`.
- 4-hour close-stop exits: `57` trades, `0` winners, `-$14,344.50`.
- The worst stop loss still had large favorable excursion before failing, which suggests the problem is not only stop width; it is also trade management after a failed retest.

Quick stop-width sweep:

| 4h Close Stop | Trades | Win Rate | Net USD | Max Closed DD | Profit Factor |
|---:|---:|---:|---:|---:|---:|
| 25 pts | 129 | 41.86% | $4,713 | -$2,767 | 1.33 |
| 50 pts | 125 | 45.60% | $5,731 | -$3,168 | 1.39 |
| 75 pts | 121 | 47.93% | $5,344 | -$3,362 | 1.34 |
| 100 pts | 120 | 48.33% | $3,749 | -$3,912 | 1.22 |
| 125 pts | 118 | 49.15% | $1,928 | -$5,180 | 1.10 |
| 150 pts | 116 | 50.86% | $1,096 | -$6,490 | 1.05 |
| 200 pts | 115 | 51.30% | $188 | -$6,418 | 1.01 |

That sweep says a wider stop does not improve the system. The next useful tests are likely:

- Keep the hard 4-hour close stop near `25-50` points, but make re-entry stricter after a stop, such as requiring a fresh daily close back above C2 close or waiting one full session before arming again.
- Add a partial or scratch rule when the trade gets meaningful MFE but later returns to C2 close.
- Require the fill candle to close back above C2 close; otherwise reject same-bar retests that immediately close below the stop.
- Test a volatility-scaled stop, such as `max(50 pts, 0.5x daily ATR)`, only if it also includes a profit-protection rule after favorable movement.
- Prefer bullish C3 contexts first, since bearish C3 contexts were roughly flat to negative in this long-only version.

## Causality Notes

- The C2 close is known before the C3 month begins.
- The 4-hour close stop is modeled at the confirming 4-hour close.
- A daily lower high is only known after that daily candle completes, so the model exits at the next 4-hour bar open.
- Same-bar limit-fill then 4-hour close-stop is allowed because the close-stop information is only known at that bar close.
