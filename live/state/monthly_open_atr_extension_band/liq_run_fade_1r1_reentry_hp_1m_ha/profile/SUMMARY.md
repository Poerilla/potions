# NQ liq-run fade HP 1m — HA condition profile

High-probability condition study on **1m Engine+PaperBroker** tape
(+$552k / N/S 1.03 / 183 entries). Features: DOW / week-of-month / hour /
5m MA / hourly RSI+OBV / ATR quartile / prior range-half.
Diagnostic — not a promotion gate.

min_n=12.

## Book

- **NQ liq-run fade 1:1 reentry HP (1m broker)**: n=178 WR=47.2% avg=$2143 net=$381368

## Notables (positive WR + avg lift)

| condition | bucket | n | WR | WRΔpp | avg | avgΔ | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|
| ATR14 quartile | atr_q4 | 45 | 51% | +3.9 | $15986 | $+13844 | 0.47 |
| Hourly RSI bucket | rsi_gt70 | 16 | 56% | +9.1 | $15871 | $+13728 | 0.70 |
| Day of week | Monday | 27 | 74% | +26.9 | $9357 | $+7215 | 2.61 |
| Hourly RSI bucket | rsi_30_45 | 48 | 56% | +9.1 | $6369 | $+4226 | 1.12 |
| Day of week | Tuesday | 47 | 53% | +6.0 | $5594 | $+3452 | 0.73 |
| Prior-week range half | week_aligned | 147 | 50% | +2.5 | $4315 | $+2173 | 0.44 |
| Prior-month range half | month_opposed | 57 | 47% | +0.2 | $4240 | $+2097 | 0.02 |
| Week of month | 1 | 97 | 53% | +5.4 | $3814 | $+1671 | 0.85 |
| Hourly RSI vs trade | rsi_against_side | 145 | 48% | +1.1 | $3692 | $+1549 | 0.19 |
| 5m MA vs trade | ma_opposed | 157 | 49% | +1.9 | $3138 | $+995 | 0.34 |

Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/liq_run_fade_1r1_reentry_hp_1m_ha/profile`
