# NAS100 weekly OD half+EOW — HA mill

Source: `live/state/weekly_open_day_breakout_od_half_runner_bull_hivol` (NAS100 1@0.5×OD + 1@1×OD (BE) + 1 EOW bull×hivol (~$+12.8k / −$9.0k stress / N/S 1.43 / 202)).

Scale: **1@0.5×OD + 1@1×OD (BE) + 1 EOW** · bull×hivol · Engine+PaperBroker.
DSR: TRL-2026-00166 (parallel ledger while primary wipe pending).

```
Variant N/S reminder (weekly OD bull×hivol family, broker-like):

  This book (1m Engine+PaperBroker):
    1@0.5×OD + 1@1×OD (BE) + 1 EOW     N/S 1.43  (+$12.8k / 202)
  Same pack refs:
    half + 3×OD runner                 N/S 1.38  (+$12.3k / 202)
    OCO 1R                             N/S 1.15  (+$3.3k / 202)
    2/1/1 scale                        N/S 1.36  (+$15.1k / 198)
  Holiday/thin Monday filter on half+EOW: N/S 1.07 — do not promote.
```

## Profile

# NAS100 weekly OD half+EOW — HA condition profile

High-probability condition study on **Engine+PaperBroker** tape
(NAS100 1@0.5×OD + 1@1×OD (BE) + 1 EOW bull×hivol (~$+12.8k / −$9.0k stress / N/S 1.43 / 202)). Features: DOW / week-of-month / hour /
5m MA / hourly RSI+OBV / ATR quartile / prior range-half.
Diagnostic — not a promotion gate.

min_n=12.

## Book

- **NAS100 weekly OD half+EOW bull×hivol (broker)**: n=202 WR=59.4% avg=$64 net=$12831 N/S=1.46

## Notables (positive WR + avg lift)

| condition | bucket | n | WR | WRΔpp | avg | avgΔ | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|
| Week of month | 1 | 45 | 71% | +11.7 | $215 | $+151 | 1.45 |
| ATR14 quartile | atr_q3 | 50 | 68% | +8.6 | $168 | $+104 | 1.11 |
| ATR14 quartile | atr_q4 | 51 | 67% | +7.3 | $162 | $+99 | 0.94 |
| Hourly RSI bucket | rsi_55_70 | 74 | 70% | +10.9 | $143 | $+79 | 1.63 |
| Entry hour (NY) | 12 | 28 | 68% | +8.5 | $132 | $+69 | 0.85 |
| Day of week | Thursday | 30 | 63% | +3.9 | $127 | $+63 | 0.41 |
| Day of week | Wednesday | 42 | 62% | +2.5 | $120 | $+56 | 0.30 |

Hub: `/home/tester/hsm/potions/live/state/weekly_open_day_breakout_od_half_eow_ha_conditions/profile`


## Overlay

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


## Nulls

# NAS100 weekly OD half+EOW — HA matched nulls

1.25× matched-added-exposure on top size-up candidates from the overlay.
Weekly N is thin — treat VALIDATED claims cautiously.

| decision | condition=bucket | hp% | ΔN/S | p_plac | p_shift | p_master |
|---|---|---:|---:|---:|---:|---:|
| RISK THROTTLE | Week of month=1 | 22% | +0.21 | 0.002 | 0.017 | 0.875 |
| NOT VALIDATED | Hourly RSI bucket=rsi_55_70 | 37% | +0.14 | 0.006 | 0.057 | 0.948 |
| NOT VALIDATED | Entry hour (NY)=12 | 14% | +0.12 | 0.557 | 0.414 | 0.993 |
| NOT VALIDATED | Day of week=Thursday | 15% | +0.08 | 0.072 | 0.125 | 1.000 |
| NOT VALIDATED | Day of week=Wednesday | 21% | +0.05 | 0.063 | 0.146 | 0.998 |

Hub: `/home/tester/hsm/potions/live/state/weekly_open_day_breakout_od_half_eow_ha_conditions/nulls`

