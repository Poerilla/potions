# CHOP20 boundary60 — HA condition profile

Diagnostic HP conditions on 1m path-aware campaign tapes.
min_n=6.

## Baselines

- **nas100_chop20_causal_globex**: n=74 WR=27% net=$15460 N/S=3.90
- **usdjpy_chop20_causal_globex**: n=168 WR=27% net=$6081394 N/S=1.60
- **xauusd_chop20_causal_globex**: n=128 WR=30% net=$348849 N/S=4.59

## Notables (top 40)

| book | condition | bucket | n | WR | WRΔpp | avgΔ |
|---|---|---|---:|---:|---:|---:|
| usdjpy_chop20_causal_globex | Hourly RSI bucket | rsi_45_55 | 41 | 37% | +9.8 | $+175555 |
| usdjpy_chop20_causal_globex | Hourly RSI vs trade | rsi_neutral | 41 | 37% | +9.8 | $+175555 |
| usdjpy_chop20_causal_globex | Hourly RSI bucket | rsi_gt70 | 19 | 37% | +10.1 | $+87505 |
| usdjpy_chop20_causal_globex | Entry hour (NY) | 22 | 7 | 29% | +1.8 | $+77832 |
| usdjpy_chop20_causal_globex | Week of month | 2 | 36 | 36% | +9.3 | $+67656 |
| usdjpy_chop20_causal_globex | ATR14 quartile | atr_q4 | 42 | 29% | +1.8 | $+63985 |
| usdjpy_chop20_causal_globex | Hourly OBV vs trade | obv_opposed | 59 | 31% | +3.7 | $+56730 |
| usdjpy_chop20_causal_globex | Day of week | Friday | 34 | 35% | +8.5 | $+55544 |
| usdjpy_chop20_causal_globex | Prior-week range half | week_aligned | 36 | 33% | +6.5 | $+40869 |
| usdjpy_chop20_causal_globex | Day of week | Sunday | 35 | 34% | +7.5 | $+32245 |
| usdjpy_chop20_causal_globex | 5m MA vs trade | ma_opposed | 80 | 30% | +3.2 | $+25112 |
| usdjpy_chop20_causal_globex | Entry hour (NY) | 21 | 28 | 36% | +8.9 | $+20849 |
| xauusd_chop20_causal_globex | Hourly RSI vs trade | rsi_against_side | 8 | 62% | +32.0 | $+9133 |
| xauusd_chop20_causal_globex | Prior-day range half | day_aligned | 21 | 48% | +17.2 | $+4535 |
| xauusd_chop20_causal_globex | Hourly RSI bucket | rsi_gt70 | 14 | 36% | +5.2 | $+2478 |
| xauusd_chop20_causal_globex | ATR14 quartile | atr_q3 | 32 | 34% | +3.9 | $+2344 |
| xauusd_chop20_causal_globex | 5m MA cross vs trade | cross_opposed | 6 | 50% | +19.5 | $+1890 |
| xauusd_chop20_causal_globex | Week of month | 1 | 32 | 34% | +3.9 | $+1597 |
| xauusd_chop20_causal_globex | 5m MA vs trade | ma_aligned | 60 | 37% | +6.2 | $+1237 |
| xauusd_chop20_causal_globex | Week of month | 2 | 31 | 42% | +11.5 | $+1025 |
| nas100_chop20_causal_globex | Day of week | Wednesday | 11 | 36% | +9.3 | $+399 |
| nas100_chop20_causal_globex | Week of month | 3 | 14 | 43% | +15.8 | $+311 |
| nas100_chop20_causal_globex | Hourly RSI bucket | rsi_gt70 | 12 | 42% | +14.6 | $+298 |
| nas100_chop20_causal_globex | ATR14 quartile | atr_q4 | 19 | 42% | +15.1 | $+290 |
| nas100_chop20_causal_globex | Day of week | Thursday | 16 | 31% | +4.2 | $+181 |
| nas100_chop20_causal_globex | 5m MA vs trade | ma_aligned | 39 | 28% | +1.2 | $+128 |

Hub: `/home/tester/hsm/potions/live/state/chop20_dynamic_range_ha_conditions_fx_metals/profile`
