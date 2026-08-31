# Quarterly ATR4 ladder — HA overlays

Filter / 1.25× / 1.5× on profile notables vs each book's baseline tape.

## Full-tape ranked by ΔN/S

| book | condition | bucket | policy | hp% | Δnet | ΔN/S | net | N/S | causal |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| nq_second_after_upper | Prior-month range half | month_aligned | filter | 62% | $+7399 | +593.32 | $314361 | 633.28 | live_ready |
| nq_second_after_upper | Prior-month range half | month_aligned | size_1.5 | 62% | $+157180 | +18.57 | $464142 | 58.54 | live_ready |
| nq_second_after_upper | Prior-month range half | month_aligned | size_1.25 | 62% | $+78590 | +9.43 | $385552 | 49.40 | live_ready |
| xauusd_first_only | ATR14 quartile | atr_q1 | filter | 27% | $-157858 | +7.69 | $93197 | 13.18 | needs_rolling_proxy |
| xauusd_first_only | Week of month | 2 | filter | 43% | $-51150 | +7.21 | $199904 | 12.70 | live_ready |
| eurusd_second_after_upper | Day of week | Monday | filter | 38% | $-6582 | +5.68 | $78045 | 9.54 | live_ready |
| eurusd_second_after_upper | 5m MA vs trade | ma_aligned | filter | 44% | $+14276 | +5.47 | $98902 | 9.32 | live_ready |
| gbpusd_first_lower | Entry hour (NY) | 12 | filter | 18% | $-285522 | +2.98 | $118608 | 16.20 | live_ready |
| gbpusd_first_lower | Day of week | Monday | filter | 29% | $-194957 | +2.86 | $209173 | 16.08 | live_ready |
| gbpusd_first_lower | Entry hour (NY) | 12 | size_1.5 | 18% | $+59304 | +1.94 | $463435 | 15.16 | live_ready |
| eurusd_second_after_upper | 5m MA vs trade | ma_aligned | size_1.5 | 44% | $+49451 | +1.83 | $134078 | 5.68 | live_ready |
| gbpusd_first_lower | Day of week | Monday | size_1.5 | 29% | $+104587 | +1.77 | $508717 | 14.99 | live_ready |
| eurusd_second_after_upper | Day of week | Monday | size_1.5 | 38% | $+39022 | +1.48 | $123649 | 5.34 | live_ready |
| xauusd_first_only | Week of month | 2 | size_1.5 | 43% | $+99952 | +1.35 | $351007 | 6.84 | live_ready |
| gbpusd_first_lower | Week of month | 3 | size_1.5 | 12% | $+33337 | +1.09 | $437467 | 14.31 | live_ready |
| xauusd_first_only | ATR14 quartile | atr_q1 | size_1.5 | 27% | $+46598 | +1.02 | $297653 | 6.51 | needs_rolling_proxy |
| gbpusd_first_lower | Entry hour (NY) | 12 | size_1.25 | 18% | $+29652 | +0.97 | $433782 | 14.19 | live_ready |
| eurusd_second_after_upper | 5m MA vs trade | ma_aligned | size_1.25 | 44% | $+24726 | +0.95 | $109352 | 4.80 | live_ready |
| gbpusd_first_lower | Day of week | Monday | size_1.25 | 29% | $+52293 | +0.93 | $456424 | 14.15 | live_ready |
| eurusd_second_after_upper | Day of week | Monday | size_1.25 | 38% | $+19511 | +0.76 | $104138 | 4.62 | live_ready |
| xauusd_first_only | Week of month | 2 | size_1.25 | 43% | $+49976 | +0.71 | $301031 | 6.20 | live_ready |
| gbpusd_first_lower | Week of month | 3 | size_1.25 | 12% | $+16669 | +0.55 | $420799 | 13.77 | live_ready |
| xauusd_first_only | ATR14 quartile | atr_q1 | size_1.25 | 27% | $+23299 | +0.51 | $274354 | 6.00 | needs_rolling_proxy |
| eurusd_second_after_upper | Hourly RSI bucket | rsi_30_45 | size_1.5 | 31% | $+19285 | +0.30 | $103912 | 4.16 | live_ready |
| eurusd_second_after_upper | Hourly RSI bucket | rsi_30_45 | size_1.25 | 31% | $+9643 | +0.16 | $94269 | 4.02 | live_ready |
| eurusd_second_after_upper | Hourly RSI bucket | rsi_30_45 | filter | 31% | $-46056 | +0.10 | $38571 | 3.96 | live_ready |
| xauusd_first_only | Hourly OBV vs trade | obv_aligned | size_1.25 | 20% | $+18860 | -0.24 | $269914 | 5.25 | live_ready |
| xauusd_first_only | ATR14 quartile | atr_q4 | size_1.25 | 27% | $+28157 | -0.35 | $279212 | 5.14 | needs_rolling_proxy |
| xauusd_first_only | Hourly OBV vs trade | obv_aligned | size_1.5 | 20% | $+37719 | -0.43 | $288774 | 5.06 | live_ready |
| xauusd_first_only | ATR14 quartile | atr_q4 | size_1.5 | 27% | $+56314 | -0.60 | $307369 | 4.89 | needs_rolling_proxy |
| gbpusd_first_lower | ATR14 quartile | atr_q4 | size_1.25 | 25% | $+47497 | -1.40 | $451628 | 11.82 | needs_rolling_proxy |
| xauusd_first_only | ATR14 quartile | atr_q4 | filter | 27% | $-138426 | -2.20 | $112628 | 3.29 | needs_rolling_proxy |
| gbpusd_first_lower | ATR14 quartile | atr_q4 | size_1.5 | 25% | $+94995 | -2.34 | $499125 | 10.89 | needs_rolling_proxy |
| xauusd_first_only | Hourly OBV vs trade | obv_aligned | filter | 20% | $-175616 | -3.22 | $75438 | 2.27 | live_ready |
| gbpusd_first_lower | ATR14 quartile | atr_q4 | filter | 25% | $-214141 | -7.01 | $189989 | 6.22 | needs_rolling_proxy |
| gbpusd_first_lower | Week of month | 3 | filter | 12% | $-337456 | -7.33 | $66674 | 5.89 | live_ready |

Hub: `/home/tester/hsm/potions/live/state/quarterly_atr4_ha_conditions/overlay`
