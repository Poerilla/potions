# USDJPY Monthly ORB FBO 1/1/3 atr80 — HA condition profile

High-probability condition study on **Engine+PaperBroker** tape
(USDJPY FBO 1/1/3 atr80 broker (~+$108k / N/S 4.25 / 156)). Features: DOW / week-of-month / hour /
5m MA / hourly RSI+OBV / ATR quartile / prior range-half.
Diagnostic — not a promotion gate.

min_n=12. Nets USD-normalized (JPY/110).

## Book

- **USDJPY Monthly ORB FBO 1/1/3 atr80 (broker)**: n=156 WR=50.6% avg=$692 net=$107890 N/S=5.48

## Notables (positive WR + avg lift)

| condition | bucket | n | WR | WRΔpp | avg | avgΔ | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|
| Hourly RSI bucket | rsi_55_70 | 38 | 68% | +17.8 | $2414 | $+1722 | 1.97 |
| ATR14 quartile | atr_q3 | 39 | 56% | +5.8 | $2065 | $+1374 | 0.64 |
| Day of week | Thursday | 29 | 59% | +8.0 | $1772 | $+1081 | 0.79 |
| Hourly RSI vs trade | rsi_with_side | 95 | 56% | +5.1 | $1474 | $+783 | 0.79 |
| Day of week | Monday | 30 | 53% | +2.7 | $1353 | $+661 | 0.27 |
| Day of week | Sunday | 22 | 55% | +3.9 | $1288 | $+596 | 0.34 |
| Prior-month range half | month_aligned | 61 | 52% | +1.8 | $1053 | $+361 | 0.24 |
| Entry hour (NY) | 19 | 53 | 51% | +0.3 | $964 | $+272 | 0.04 |

Hub: `/home/tester/hsm/potions/live/state/usdjpy_monthly_orb_fbo_ha_conditions/profile`
