# CHOP20 boundary60 — HA matched nulls

1.25× matched-added-exposure. Thin campaign N — treat VALIDATED cautiously.

| decision | book | condition=bucket | ΔN/S | p_master |
|---|---|---|---:|---:|
| NOT VALIDATED | nq_chop20_boundary60_1m | Hourly RSI bucket=rsi_gt70 | +2.16 | 0.204 |
| RISK THROTTLE | nq_chop20_boundary60_1m | Week of month=3 | +1.60 | 0.549 |
| NOT VALIDATED | mnq_chop20_boundary60_1m | Week of month=3 | +1.38 | 0.040 |
| NOT VALIDATED | nq_chop20_boundary60_1m | Day of week=Thursday | +0.61 | 0.968 |
| NOT VALIDATED | nq_chop20_boundary60_1m | Day of week=Monday | +0.50 | 0.975 |
| NOT VALIDATED | ym_chop20_boundary60_1m | Hourly RSI bucket=rsi_55_70 | +0.23 | 0.591 |

Hub: `/home/tester/hsm/potions/live/state/chop20_dynamic_range_ha_conditions/nulls`
