# USDJPY Monthly ORB FBO 1/1/3 atr80 — HA overlays

Filter / 1.25× / 1.5× on profile notables vs baseline broker tape.

## Full-tape ranked by ΔN/S

| condition | bucket | policy | hp% | Δnet | ΔN/S | net | N/S | causal |
|---|---|---|---:|---:|---:|---:|---:|---|
| Hourly RSI vs trade | rsi_with_side | filter | 61% | $+32174 | +6.57 | $140064 | 12.06 | live_ready |
| Hourly RSI bucket | rsi_55_70 | filter | 24% | $-16164 | +2.70 | $91726 | 8.19 | live_ready |
| Hourly RSI vs trade | rsi_with_side | size_1.5 | 61% | $+70032 | +2.42 | $177923 | 7.90 | live_ready |
| Hourly RSI vs trade | rsi_with_side | size_1.25 | 61% | $+35016 | +1.66 | $142906 | 7.15 | live_ready |
| Day of week | Monday | size_1.5 | 19% | $+20294 | +1.50 | $128185 | 6.99 | live_ready |
| Day of week | Thursday | size_1.5 | 19% | $+25701 | +1.34 | $133591 | 6.83 | live_ready |
| Hourly RSI bucket | rsi_55_70 | size_1.5 | 24% | $+45863 | +1.12 | $153754 | 6.61 | live_ready |
| Prior-month range half | month_aligned | size_1.5 | 39% | $+32113 | +1.10 | $140003 | 6.58 | live_ready |
| Day of week | Thursday | size_1.25 | 19% | $+12850 | +0.97 | $120741 | 6.46 | live_ready |
| Day of week | Monday | size_1.25 | 19% | $+10147 | +0.89 | $118037 | 6.38 | live_ready |
| ATR14 quartile | atr_q3 | size_1.25 | 25% | $+20135 | +0.79 | $128025 | 6.27 | needs_rolling_proxy |
| Prior-month range half | month_aligned | size_1.25 | 39% | $+16056 | +0.69 | $123947 | 6.17 | live_ready |
| Hourly RSI bucket | rsi_55_70 | size_1.25 | 24% | $+22932 | +0.61 | $130822 | 6.09 | live_ready |
| ATR14 quartile | atr_q3 | size_1.5 | 25% | $+40270 | +0.55 | $148160 | 6.03 | needs_rolling_proxy |
| Day of week | Thursday | filter | 19% | $-56489 | +0.11 | $51402 | 5.60 | live_ready |
| Day of week | Sunday | size_1.25 | 14% | $+7082 | -0.28 | $114972 | 5.20 | live_ready |
| Day of week | Sunday | size_1.5 | 14% | $+14164 | -0.51 | $122054 | 4.98 | live_ready |
| Entry hour (NY) | 19 | size_1.25 | 34% | $+12767 | -0.62 | $120657 | 4.86 | live_ready |
| ATR14 quartile | atr_q3 | filter | 25% | $-27351 | -0.68 | $80540 | 4.80 | needs_rolling_proxy |
| Prior-month range half | month_aligned | filter | 39% | $-43665 | -0.96 | $64225 | 4.52 | live_ready |
| Entry hour (NY) | 19 | size_1.5 | 34% | $+25533 | -1.03 | $133424 | 4.46 | live_ready |
| Day of week | Sunday | filter | 14% | $-79563 | -1.58 | $28327 | 3.91 | live_ready |
| Day of week | Monday | filter | 19% | $-67302 | -2.08 | $40588 | 3.40 | live_ready |
| Entry hour (NY) | 19 | filter | 34% | $-56824 | -3.49 | $51067 | 2.00 | live_ready |

Hub: `/home/tester/hsm/potions/live/state/usdjpy_monthly_orb_fbo_ha_conditions/overlay`
