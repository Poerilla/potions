# NQ liq-run fade 1:1 HP 1m — HA mill

Source book: `liq_run_fade_1r1_reentry_hp_1m_broker` (+$552k / N/S 1.03 / 183).

```
Variant N/S reminder (same liq-run fade family):

  Best N/S overall (path sim, HP lookback):
    2c half+open $1k SL     HP N/S 3.46  (+$32k)   — small-risk sleeve
  Best among full-size structural books (path sim, HP lookback):
    1:1 unlimited reentry   HP N/S 2.24  (+$618k)  — this book's 1h cousin
  This book (1m Engine+PaperBroker, HP):
    1:1 unlimited reentry   N/S 1.03     (+$552k / 183 entries)
  Other HP path-sim refs:
    win3 reentry cap        HP N/S 1.58
    2c BE+2R                HP N/S 1.02
    base once/month 1:1     HP N/S 0.64
    liq-days=4 1m broker    N/S -0.60
```

## Profile

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


## Overlay

# NQ liq-run fade HP 1m — HA overlays

Filter / 1.25× / 1.5× on profile notables vs baseline 1m broker tape.

## Full-tape ranked by ΔN/S

| condition | bucket | policy | hp% | Δnet | ΔN/S | net | N/S | causal |
|---|---|---|---:|---:|---:|---:|---:|---|
| Hourly RSI bucket | rsi_gt70 | filter | 9% | $-127432 | +3.78 | $253935 | 4.77 | live_ready |
| Day of week | Monday | filter | 15% | $-128722 | +1.33 | $252645 | 2.32 | live_ready |
| Prior-week range half | week_aligned | filter | 83% | $+252965 | +1.13 | $634332 | 2.12 | live_ready |
| ATR14 quartile | atr_q4 | filter | 25% | $+338008 | +1.12 | $719375 | 2.11 | needs_rolling_proxy |
| Hourly RSI vs trade | rsi_against_side | filter | 81% | $+153920 | +1.00 | $535288 | 1.99 | live_ready |
| Hourly RSI bucket | rsi_30_45 | filter | 27% | $-75662 | +0.52 | $305705 | 1.51 | live_ready |
| ATR14 quartile | atr_q4 | size_1.5 | 25% | $+359688 | +0.46 | $741055 | 1.45 | needs_rolling_proxy |
| 5m MA vs trade | ma_opposed | filter | 88% | $+111265 | +0.46 | $492632 | 1.45 | live_ready |
| Day of week | Monday | size_1.5 | 15% | $+126322 | +0.36 | $507690 | 1.35 | live_ready |
| Hourly RSI bucket | rsi_gt70 | size_1.5 | 9% | $+126968 | +0.36 | $508335 | 1.35 | live_ready |
| Hourly RSI vs trade | rsi_against_side | size_1.5 | 81% | $+267644 | +0.33 | $649011 | 1.32 | live_ready |
| Prior-week range half | week_aligned | size_1.5 | 83% | $+317166 | +0.32 | $698534 | 1.31 | live_ready |
| ATR14 quartile | atr_q4 | size_1.25 | 25% | $+179844 | +0.28 | $561211 | 1.27 | needs_rolling_proxy |
| Prior-month range half | month_opposed | filter | 32% | $-139698 | +0.25 | $241670 | 1.24 | live_ready |
| Prior-month range half | month_opposed | size_1.5 | 32% | $+120835 | +0.24 | $502202 | 1.23 | live_ready |
| 5m MA vs trade | ma_opposed | size_1.5 | 88% | $+246316 | +0.24 | $627684 | 1.23 | live_ready |
| Hourly RSI bucket | rsi_30_45 | size_1.5 | 27% | $+152852 | +0.22 | $534220 | 1.21 | live_ready |
| Day of week | Monday | size_1.25 | 15% | $+63161 | +0.22 | $444529 | 1.21 | live_ready |
| Prior-week range half | week_aligned | size_1.25 | 83% | $+158583 | +0.18 | $539951 | 1.17 | live_ready |
| Hourly RSI vs trade | rsi_against_side | size_1.25 | 81% | $+133822 | +0.18 | $515189 | 1.17 | live_ready |
| Hourly RSI bucket | rsi_gt70 | size_1.25 | 9% | $+63484 | +0.18 | $444851 | 1.17 | live_ready |
| Hourly RSI bucket | rsi_30_45 | size_1.25 | 27% | $+76426 | +0.18 | $457794 | 1.16 | live_ready |
| 5m MA vs trade | ma_opposed | size_1.25 | 88% | $+123158 | +0.14 | $504526 | 1.13 | live_ready |
| Prior-month range half | month_opposed | size_1.25 | 32% | $+60418 | +0.13 | $441785 | 1.12 | live_ready |
| Week of month | 1 | size_1.5 | 54% | $+184960 | +0.07 | $566328 | 1.06 | live_ready |
| Week of month | 1 | size_1.25 | 54% | $+92480 | +0.05 | $473848 | 1.04 | live_ready |
| Week of month | 1 | filter | 54% | $-11448 | +0.02 | $369920 | 1.01 | live_ready |
| Day of week | Tuesday | size_1.5 | 26% | $+131466 | +0.01 | $512834 | 1.00 | live_ready |
| Day of week | Tuesday | size_1.25 | 26% | $+65733 | +0.00 | $447101 | 0.99 | live_ready |
| Day of week | Tuesday | filter | 26% | $-118435 | -0.06 | $262932 | 0.93 | live_ready |

Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/liq_run_fade_1r1_reentry_hp_1m_ha/overlay`


## Nulls

# NQ liq-run fade HP 1m — HA matched nulls

1.25× matched-added-exposure on top size-up candidates from the overlay.

| decision | condition=bucket | hp% | ΔN/S | p_plac | p_shift | p_master |
|---|---|---:|---:|---:|---:|---:|
| NOT VALIDATED | Day of week=Monday | 15% | +0.22 | 0.304 | 0.273 | 0.711 |
| NOT VALIDATED | Hourly RSI bucket=rsi_gt70 | 9% | +0.18 | 0.199 | 0.191 | 0.840 |
| NOT VALIDATED | Prior-month range half=month_opposed | 32% | +0.13 | 1.000 | 0.824 | 0.955 |
| NOT VALIDATED | Hourly RSI bucket=rsi_30_45 | 27% | +0.18 | 0.001 | 0.077 | 0.838 |
| NOT VALIDATED | Day of week=Tuesday | 26% | +0.00 | 0.173 | 0.276 | 1.000 |

Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/liq_run_fade_1r1_reentry_hp_1m_ha/nulls`

