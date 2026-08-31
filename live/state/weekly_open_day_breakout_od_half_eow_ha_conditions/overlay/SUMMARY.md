# NAS100 weekly OD half+EOW — HA overlays

Filter / 1.25× / 1.5× on profile notables vs baseline broker tape.

## Full-tape ranked by ΔN/S

| condition | bucket | policy | hp% | Δnet | ΔN/S | net | N/S | causal |
|---|---|---|---:|---:|---:|---:|---:|---|
| Week of month | 1 | filter | 22% | $-3162 | +4.06 | $9669 | 5.51 | live_ready |
| ATR14 quartile | atr_q3 | filter | 25% | $-4437 | +2.62 | $8394 | 4.08 | needs_rolling_proxy |
| Day of week | Thursday | filter | 15% | $-9024 | +2.61 | $3807 | 4.06 | live_ready |
| Hourly RSI bucket | rsi_55_70 | filter | 37% | $-2263 | +1.09 | $10568 | 2.55 | live_ready |
| Day of week | Wednesday | filter | 21% | $-7795 | +0.72 | $5036 | 2.17 | live_ready |
| ATR14 quartile | atr_q4 | filter | 25% | $-4565 | +0.60 | $8266 | 2.06 | needs_rolling_proxy |
| ATR14 quartile | atr_q3 | size_1.5 | 25% | $+4197 | +0.48 | $17028 | 1.93 | needs_rolling_proxy |
| Week of month | 1 | size_1.5 | 22% | $+4834 | +0.40 | $17665 | 1.86 | live_ready |
| Hourly RSI bucket | rsi_55_70 | size_1.5 | 37% | $+5284 | +0.27 | $18115 | 1.72 | live_ready |
| Entry hour (NY) | 12 | size_1.5 | 14% | $+1849 | +0.25 | $14680 | 1.70 | live_ready |
| ATR14 quartile | atr_q3 | size_1.25 | 25% | $+2098 | +0.24 | $14929 | 1.69 | needs_rolling_proxy |
| Week of month | 1 | size_1.25 | 22% | $+2417 | +0.21 | $15248 | 1.66 | live_ready |
| Day of week | Thursday | size_1.5 | 15% | $+1903 | +0.17 | $14734 | 1.62 | live_ready |
| Hourly RSI bucket | rsi_55_70 | size_1.25 | 37% | $+2642 | +0.14 | $15473 | 1.60 | live_ready |
| Entry hour (NY) | 12 | size_1.25 | 14% | $+925 | +0.12 | $13756 | 1.58 | live_ready |
| Day of week | Wednesday | size_1.5 | 21% | $+2518 | +0.09 | $15349 | 1.55 | live_ready |
| Day of week | Thursday | size_1.25 | 15% | $+952 | +0.08 | $13783 | 1.54 | live_ready |
| Day of week | Wednesday | size_1.25 | 21% | $+1259 | +0.05 | $14090 | 1.51 | live_ready |
| ATR14 quartile | atr_q4 | size_1.5 | 25% | $+4133 | +0.05 | $16964 | 1.50 | needs_rolling_proxy |
| Entry hour (NY) | 12 | filter | 14% | $-9132 | +0.03 | $3699 | 1.49 | live_ready |
| ATR14 quartile | atr_q4 | size_1.25 | 25% | $+2066 | +0.03 | $14897 | 1.48 | needs_rolling_proxy |

Hub: `/home/tester/hsm/potions/live/state/weekly_open_day_breakout_od_half_eow_ha_conditions/overlay`
