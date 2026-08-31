# Quarterly ATR4 ladder — HA matched nulls

1.25× matched-added-exposure on top size-up candidates from the overlay.
Quarterly N is thin — treat VALIDATED claims cautiously.

| decision | book | condition=bucket | hp% | ΔN/S | Δnet | p_plac | p_shift | p_master |
|---|---|---|---:|---:|---:|---:|---:|---:|
| NOT VALIDATED | gbpusd_first_lower | Entry hour (NY)=12 | 18% | +0.97 | $+29652 | 1.000 | 0.908 | 0.569 |
| NOT VALIDATED | gbpusd_first_lower | Day of week=Monday | 29% | +0.93 | $+52293 | 1.000 | 0.951 | 0.539 |
| NOT VALIDATED | gbpusd_first_lower | Week of month=3 | 12% | +0.55 | $+16669 | 1.000 | 0.925 | 0.656 |
| NOT VALIDATED | eurusd_second_after_upper | Hourly RSI bucket=rsi_30_45 | 31% | +0.16 | $+9643 | 1.000 | 0.936 | nan |

Hub: `/home/tester/hsm/potions/live/state/quarterly_atr4_ha_conditions/nulls`
