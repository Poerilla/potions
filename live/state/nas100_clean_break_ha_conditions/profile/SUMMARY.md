# NAS100 clean-break — HA condition profile

High-probability condition study on **Engine+PaperBroker 1m-fill** tape
(NAS100 clean-break trail06_m4_e2_out_be 1m-fill unit book (~$+12.3k / N/S 6.23 / 1166; live/public default = ×10)).
Features: DOW / week-of-month / Entry month / hour / 5m MA /
hourly RSI+OBV / ATR quartile / prior range-half.
Diagnostic — not a promotion gate.

min_n=40.

## Book

- **NAS100 clean-break trail06_m4_e2_out_be (1m-fill unit)**: n=1166 WR=12.9% avg=$11 net=$12253 N/S=6.57

## Notables (positive WR + avg lift)

| condition | bucket | n | WR | WRΔpp | avg | avgΔ | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|
| Entry month | April | 86 | 22% | +9.2 | $53 | $+42 | 2.47 |
| Entry month | January | 96 | 19% | +5.9 | $30 | $+19 | 1.66 |
| Day of week | Monday | 261 | 16% | +3.6 | $26 | $+15 | 1.57 |
| Week of month | 4 | 267 | 14% | +1.4 | $21 | $+10 | 0.60 |
| Entry month | August | 105 | 18% | +5.2 | $20 | $+9 | 1.53 |
| Prior-month range half | month_aligned | 301 | 17% | +4.1 | $19 | $+8 | 1.88 |
| ATR14 quartile | atr_q4 | 290 | 14% | +0.9 | $19 | $+8 | 0.42 |
| Week of month | 5 | 89 | 15% | +1.7 | $19 | $+8 | 0.47 |
| 5m MA cross vs trade | cross_aligned | 66 | 14% | +0.8 | $18 | $+8 | 0.18 |
| 5m MA vs trade | ma_aligned | 710 | 13% | +0.5 | $17 | $+7 | 0.32 |
| Week of month | 1 | 269 | 15% | +2.0 | $17 | $+6 | 0.89 |
| Entry month | March | 88 | 15% | +1.9 | $16 | $+5 | 0.52 |
| Hourly RSI bucket | rsi_55_70 | 392 | 13% | +0.4 | $14 | $+4 | 0.21 |
| Entry month | October | 93 | 15% | +2.2 | $14 | $+4 | 0.61 |
| ATR14 quartile | atr_q2 | 290 | 15% | +2.0 | $14 | $+4 | 0.89 |

## Entry month board (appendix)

| month | n | WR | WRΔpp | avg | avgΔ | net | years green |
|---|---:|---:|---:|---:|---:|---:|---:|
| January | 96 | 19% | +5.9 | $30 | $+19 | $+2836 | 8/9 |
| February | 99 | 3% | -9.8 | $-25 | $-35 | $-2426 | 0/9 |
| March | 88 | 15% | +1.9 | $16 | $+5 | $+1369 | 6/9 |
| April | 86 | 22% | +9.2 | $53 | $+42 | $+4536 | 7/9 |
| May | 103 | 10% | -3.2 | $9 | $-2 | $+905 | 4/9 |
| June | 109 | 13% | -0.0 | $13 | $+2 | $+1364 | 4/9 |
| July | 98 | 12% | -0.6 | $13 | $+2 | $+1255 | 6/9 |
| August | 105 | 18% | +5.2 | $20 | $+9 | $+2061 | 7/9 |
| September | 101 | 10% | -3.0 | $-12 | $-23 | $-1260 | 2/9 |
| October | 93 | 15% | +2.2 | $14 | $+4 | $+1340 | 4/8 |
| November | 93 | 11% | -2.1 | $2 | $-9 | $+154 | 4/9 |
| December | 95 | 8% | -4.4 | $1 | $-9 | $+118 | 3/9 |

Hub: `/home/tester/hsm/potions/live/state/nas100_clean_break_ha_conditions/profile`
