# USDJPY Monthly ORB FBO 1/1/3 atr80 — HA mill

Source: `fx_cross_pair_tracker_leaders/states/fbo_1_1_3_atr80_usdjpy`
(USDJPY FBO 1/1/3 atr80 broker (~+$108k / N/S 4.25 / 156)).

## Profile

# USDJPY Monthly ORB FBO 1/1/3 atr80 — HA condition profile

High-probability condition study on **Engine+PaperBroker** tape
(USDJPY FBO 1/1/3 atr80 broker (~+$108k / N/S 4.25 / 156)). Features: DOW / week-of-month / hour /
5m MA / hourly RSI+OBV / ATR quartile / prior range-half.
Diagnostic — not a promotion gate.

min_n=12. Nets USD-normalized (JPY/110).

## Book

- **USDJPY Monthly ORB FBO 1/1/3 atr80 (broker)**: n=156 WR=50.6% avg=$692 net=$107890 N/S=5.48

## Notables (positive WR + avg lift)

| condition | bucket | n | WR | WRΔpp | avg | avgΔ | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|
| Hourly RSI bucket | rsi_55_70 | 38 | 68% | +17.8 | $2414 | $+1722 | 1.97 |
| ATR14 quartile | atr_q3 | 39 | 56% | +5.8 | $2065 | $+1374 | 0.64 |
| Day of week | Thursday | 29 | 59% | +8.0 | $1772 | $+1081 | 0.79 |
| Hourly RSI vs trade | rsi_with_side | 95 | 56% | +5.1 | $1474 | $+783 | 0.79 |
| Day of week | Monday | 30 | 53% | +2.7 | $1353 | $+661 | 0.27 |
| Day of week | Sunday | 22 | 55% | +3.9 | $1288 | $+596 | 0.34 |
| Prior-month range half | month_aligned | 61 | 52% | +1.8 | $1053 | $+361 | 0.24 |
| Entry hour (NY) | 19 | 53 | 51% | +0.3 | $964 | $+272 | 0.04 |

Hub: `/home/tester/hsm/potions/live/state/usdjpy_monthly_orb_fbo_ha_conditions/profile`


## Overlay

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


## Nulls

# USDJPY Monthly ORB FBO 1/1/3 atr80 — HA matched nulls

1.25× matched-added-exposure on top size-up candidates from the overlay.
Monthly N is thin — treat VALIDATED claims cautiously.

| decision | condition=bucket | hp% | ΔN/S | p_plac | p_shift | p_master |
|---|---|---:|---:|---:|---:|---:|
| NOT VALIDATED | Day of week=Monday | 19% | +0.89 | 0.703 | 0.581 | 0.125 |
| NOT VALIDATED | Day of week=Thursday | 19% | +0.97 | 0.514 | 0.388 | 0.077 |
| NOT VALIDATED | Hourly RSI bucket=rsi_55_70 | 24% | +0.61 | 0.925 | 0.733 | 0.384 |
| NOT VALIDATED | Prior-month range half=month_aligned | 39% | +0.69 | 0.875 | 0.655 | 0.292 |

Hub: `/home/tester/hsm/potions/live/state/usdjpy_monthly_orb_fbo_ha_conditions/nulls`

