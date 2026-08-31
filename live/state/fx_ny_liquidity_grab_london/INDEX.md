# NY liquidity grab — London session (FX + metals)

Plugin `ny_liquidity_grab`: after London open, arm OCO at prior NY RTH H/L once price trades into that range; 1 lot; risk=NY range; TP=1R opposite.
Arm 03:00 window → flatten 11:59 America/New_York.

| Rank | Symbol | Sessions | Trades | Net≈USD | Stress≈USD | N/S | Win% | PF |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | AUDJPY | 1430 | 907 | $-13823 | $-19184 | -0.72 | 46.1 | 0.845 |
| 2 | USDJPY | 1681 | 994 | $-48398 | $-52658 | -0.92 | 43.0 | 0.599 |
| 3 | XAUUSD | 1929 | 1108 | $-115725 | $-120833 | -0.96 | 49.3 | 0.723 |
| 4 | GBPUSD | 1436 | 1009 | $-37129 | $-38633 | -0.96 | 46.6 | 0.761 |
| 5 | EURUSD | 1355 | 897 | $-34560 | $-35669 | -0.97 | 40.8 | 0.653 |
| 6 | XAGUSD | 1573 | 885 | $-55274 | $-56497 | -0.98 | 40.5 | 0.545 |

- Hub: `live/state/fx_ny_liquidity_grab_london`

