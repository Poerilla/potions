# Intraday condition overlay (filter vs size-up)

Broker-like campaign replay of condition-profile hits under **filter**,
**1.25× size-up**, and **1.5× size-up** vs each book's baseline tape.
Source: `live/state/intraday_condition_profile/all_campaigns.csv` (entry-asof features).

Splits: **full** tape, chronological **IS** (first 60%), **OOS** (last 40%).
Size-up scales campaign `net_usd` on HP rows only (PnL+fees linear in size).

## Causality

- Calendar / hour / MA / RSI / OBV / prior range-half: **pre-fill** (live-ready).
- ATR quartile here is a **static within-book** cut — live needs causal rolling percentile.
- No post-fill add-on size studied; all HP flags are knowable at entry.

## OOS keepers (heuristic)

| scope | book | condition | bucket | policy | stance | hp% | Δnet | ΔN/S | OOS net | OOS N/S | causal |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|
| cross_book | eurusd_v2b_ungated | Week of month | 5 | filter | retain_filter | 9% | +41848 | +0.08 | -6361 | -0.88 | live_ready |
| single_book | eurusd_v2b_ungated | ATR14 quartile | atr_q4 | filter | retain_filter | 19% | +36261 | +0.15 | -11949 | -0.82 | needs_rolling_proxy |
| cross_book | eurusd_v2b_ungated | ATR14 quartile | atr_q4 | filter | retain_filter | 19% | +36261 | +0.15 | -11949 | -0.82 | needs_rolling_proxy |
| cross_book | eurusd_monday_or | Entry hour (NY) | 3 | filter | retain_filter | 2% | +17952 | +0.17 | -1252 | -0.19 | live_ready |
| cross_book | nas100_v2b_london | Week of month | 5 | filter | retain_filter | 8% | +8116 | +0.17 | -874 | -0.50 | live_ready |
| cross_book | eurusd_monday_or | Prior-week range half | week_opposed | filter | retain_filter | 76% | +4110 | +0.05 | -15094 | -0.30 | live_ready |
| single_book | usdjpy_monday_or | Hourly RSI bucket | rsi_gt70 | size_1.25 | retain_size | 8% | +4770 | -0.06 | 100676 | 4.66 | live_ready |
| cross_book | usdjpy_monday_or | Hourly RSI bucket | rsi_gt70 | size_1.25 | retain_size | 8% | +4770 | -0.06 | 100676 | 4.66 | live_ready |
| single_book | usdjpy_monday_or | Entry hour (NY) | 4 | size_1.5 | retain_size | 3% | +3255 | +0.16 | 99161 | 4.88 | live_ready |
| cross_book | usdjpy_monday_or | Entry hour (NY) | 4 | size_1.5 | retain_size | 3% | +3255 | +0.16 | 99161 | 4.88 | live_ready |
| single_book | usdjpy_monday_or | Entry hour (NY) | 5 | size_1.25 | retain_size | 3% | +3232 | +0.26 | 99138 | 4.98 | live_ready |
| single_book | eurusd_monday_or | Hourly RSI vs trade | rsi_against_side | size_1.5 | retain_size | 3% | +2338 | +0.04 | -16866 | -0.31 | live_ready |
| cross_book | eurusd_monday_or | Hourly RSI vs trade | rsi_against_side | size_1.5 | retain_size | 3% | +2338 | +0.04 | -16866 | -0.31 | live_ready |
| single_book | eurusd_monday_or | 5m MA vs trade | ma_opposed | size_1.25 | retain_size | 9% | +1963 | +0.04 | -17241 | -0.32 | live_ready |
| cross_book | eurusd_monday_or | 5m MA vs trade | ma_opposed | size_1.25 | retain_size | 9% | +1963 | +0.04 | -17241 | -0.32 | live_ready |
| single_book | usdjpy_monday_or | Entry hour (NY) | 4 | size_1.25 | retain_size | 3% | +1628 | +0.08 | 97533 | 4.80 | live_ready |
| cross_book | usdjpy_monday_or | Entry hour (NY) | 4 | size_1.25 | retain_size | 3% | +1628 | +0.08 | 97533 | 4.80 | live_ready |
| single_book | eurusd_monday_or | Hourly RSI vs trade | rsi_against_side | size_1.25 | retain_size | 3% | +1169 | +0.02 | -18035 | -0.34 | live_ready |
| cross_book | eurusd_monday_or | Hourly RSI vs trade | rsi_against_side | size_1.25 | retain_size | 3% | +1169 | +0.02 | -18035 | -0.34 | live_ready |
| single_book | nas100_v2b_london | Hourly RSI bucket | rsi_gt70 | size_1.5 | retain_size | 9% | +754 | +0.01 | -8236 | -0.66 | live_ready |
| cross_book | nas100_v2b_london | Hourly RSI bucket | rsi_gt70 | size_1.5 | retain_size | 9% | +754 | +0.01 | -8236 | -0.66 | live_ready |
| single_book | eurusd_v2b_ungated | Hourly RSI bucket | rsi_le30 | size_1.5 | retain_size | 5% | +565 | +0.00 | -47644 | -0.96 | live_ready |
| single_book | nas100_v2b_london | Hourly RSI bucket | rsi_gt70 | size_1.25 | retain_size | 9% | +377 | +0.01 | -8613 | -0.66 | live_ready |
| cross_book | nas100_v2b_london | Hourly RSI bucket | rsi_gt70 | size_1.25 | retain_size | 9% | +377 | +0.01 | -8613 | -0.66 | live_ready |
| cross_book | eurusd_monday_or | Entry hour (NY) | 4 | size_1.5 | retain_size | 2% | +325 | +0.02 | -18879 | -0.34 | live_ready |
| single_book | eurusd_v2b_ungated | Hourly RSI bucket | rsi_le30 | size_1.25 | retain_size | 5% | +283 | +0.00 | -47926 | -0.96 | live_ready |
| cross_book | us30_london_prior_opposed | Week of month | 4 | size_1.25 | retain_size | 13% | +269 | -0.04 | 8110 | 2.51 | live_ready |
| cross_book | nas100_st_pmc_3r | Entry hour (NY) | 11 | size_1.25 | retain_size | 7% | +220 | +0.06 | 6609 | 15.08 | live_ready |
| cross_book | eurusd_monday_or | Entry hour (NY) | 4 | size_1.25 | retain_size | 2% | +163 | +0.01 | -19042 | -0.35 | live_ready |
| single_book | nas100_v2b_london | Entry hour (NY) | 3 | size_1.5 | retain_size | 65% | +18 | +0.13 | -8972 | -0.54 | live_ready |
| cross_book | nas100_v2b_london | Entry hour (NY) | 3 | size_1.5 | retain_size | 65% | +18 | +0.13 | -8972 | -0.54 | live_ready |
| single_book | nas100_v2b_london | Entry hour (NY) | 3 | size_1.25 | retain_size | 65% | +9 | +0.07 | -8981 | -0.60 | live_ready |
| cross_book | nas100_v2b_london | Entry hour (NY) | 3 | size_1.25 | retain_size | 65% | +9 | +0.07 | -8981 | -0.60 | live_ready |
| single_book | eurusd_v2b_ungated | Hourly RSI bucket | rsi_le30 | filter | worth_filter | 5% | +49340 | +1.50 | 1130 | 0.53 | live_ready |
| single_book | eurusd_v2b_ungated | Entry hour (NY) | 11 | filter | worth_filter | 10% | +47839 | +0.87 | -371 | -0.09 | live_ready |
| cross_book | eurusd_v2b_ungated | Entry hour (NY) | 11 | filter | worth_filter | 10% | +47839 | +0.87 | -371 | -0.09 | live_ready |
| single_book | eurusd_v2b_ungated | Hourly RSI bucket | rsi_gt70 | filter | worth_filter | 6% | +46219 | +0.28 | -1991 | -0.68 | live_ready |
| cross_book | eurusd_v2b_ungated | Hourly RSI bucket | rsi_gt70 | filter | worth_filter | 6% | +46219 | +0.28 | -1991 | -0.68 | live_ready |
| cross_book | eurusd_monday_or | ATR14 quartile | atr_q4 | filter | worth_filter | 3% | +36321 | +1.50 | 17117 | 1.14 | needs_rolling_proxy |
| single_book | eurusd_monday_or | Entry hour (NY) | 14 | filter | worth_filter | 8% | +35606 | +2.45 | 16401 | 2.10 | live_ready |
| cross_book | eurusd_monday_or | Day of week | Thursday | filter | worth_filter | 19% | +29791 | +1.20 | 10586 | 0.84 | live_ready |
| single_book | eurusd_monday_or | 5m MA vs trade | ma_opposed | filter | worth_filter | 9% | +27056 | +1.60 | 7852 | 1.25 | live_ready |
| cross_book | eurusd_monday_or | 5m MA vs trade | ma_opposed | filter | worth_filter | 9% | +27056 | +1.60 | 7852 | 1.25 | live_ready |
| single_book | eurusd_monday_or | Hourly RSI vs trade | rsi_against_side | filter | worth_filter | 3% | +23881 | +1.29 | 4676 | 0.93 | live_ready |
| cross_book | eurusd_monday_or | Hourly RSI vs trade | rsi_against_side | filter | worth_filter | 3% | +23881 | +1.29 | 4676 | 0.93 | live_ready |
| cross_book | eurusd_monday_or | Hourly RSI bucket | rsi_gt70 | filter | worth_filter | 9% | +19063 | +0.35 | -142 | -0.01 | live_ready |
| single_book | nas100_v2b_london | Hourly RSI bucket | rsi_gt70 | filter | worth_filter | 9% | +10497 | +1.99 | 1507 | 1.32 | live_ready |
| cross_book | nas100_v2b_london | Hourly RSI bucket | rsi_gt70 | filter | worth_filter | 9% | +10497 | +1.99 | 1507 | 1.32 | live_ready |
| cross_book | usdjpy_monday_or | Prior-week range half | week_opposed | filter | worth_filter | 70% | +10445 | +2.62 | 106350 | 7.35 | live_ready |
| single_book | nas100_v2b_london | Entry hour (NY) | 3 | filter | worth_filter | 65% | +9026 | +0.68 | 36 | 0.01 | live_ready |
| cross_book | nas100_v2b_london | Entry hour (NY) | 3 | filter | worth_filter | 65% | +9026 | +0.68 | 36 | 0.01 | live_ready |
| single_book | eurusd_st_pmc_3r | Day of week | Thursday | filter | worth_filter | 21% | +9013 | +3.59 | 15787 | 3.93 | live_ready |
| cross_book | eurusd_st_pmc_3r | Day of week | Thursday | filter | worth_filter | 21% | +9013 | +3.59 | 15787 | 3.93 | live_ready |
| single_book | nas100_v2b_london | Week of month | 2 | filter | worth_filter | 23% | +8097 | +0.32 | -893 | -0.35 | live_ready |
| cross_book | nas100_v2b_london | Week of month | 2 | filter | worth_filter | 23% | +8097 | +0.32 | -893 | -0.35 | live_ready |
| cross_book | nas100_v2b_london | Day of week | Thursday | filter | worth_filter | 20% | +7925 | +0.28 | -1064 | -0.38 | live_ready |
| single_book | eurusd_st_pmc_3r | Hourly RSI vs trade | rsi_against_side | filter | worth_filter | 23% | +7053 | +2.15 | 13827 | 2.48 | live_ready |
| cross_book | eurusd_st_pmc_3r | Hourly RSI vs trade | rsi_against_side | filter | worth_filter | 23% | +7053 | +2.15 | 13827 | 2.48 | live_ready |
| single_book | usdjpy_asia_range | ATR14 quartile | atr_q2 | filter | worth_filter | 31% | +3540 | +2.36 | 52742 | 4.75 | needs_rolling_proxy |
| cross_book | usdjpy_asia_range | ATR14 quartile | atr_q2 | filter | worth_filter | 31% | +3540 | +2.36 | 52742 | 4.75 | needs_rolling_proxy |
| cross_book | eurusd_st_pmc_3r | Week of month | 2 | filter | worth_filter | 22% | +3060 | +1.06 | 9834 | 1.39 | live_ready |
| cross_book | us30_monday_or | Prior-week range half | week_opposed | filter | worth_filter | 75% | +2156 | +0.49 | 16580 | 1.39 | live_ready |
| cross_book | us30_london_prior_opposed | Hourly RSI vs trade | rsi_against_side | filter | worth_filter | 72% | +929 | +1.41 | 8770 | 3.96 | live_ready |
| cross_book | usdjpy_monday_or | Prior-week range half | week_opposed | size_1.5 | worth_size | 70% | +53175 | +1.08 | 149081 | 5.80 | live_ready |
| cross_book | usdjpy_monday_or | Prior-week range half | week_opposed | size_1.25 | worth_size | 70% | +26588 | +0.67 | 122493 | 5.40 | live_ready |
| single_book | usdjpy_asia_range | ATR14 quartile | atr_q2 | size_1.5 | worth_size | 31% | +26371 | +0.96 | 75574 | 3.35 | needs_rolling_proxy |
| cross_book | usdjpy_asia_range | ATR14 quartile | atr_q2 | size_1.5 | worth_size | 31% | +26371 | +0.96 | 75574 | 3.35 | needs_rolling_proxy |
| single_book | usdjpy_asia_range | Entry hour (NY) | 4 | size_1.5 | worth_size | 14% | +23167 | +0.73 | 72370 | 3.11 | live_ready |
| cross_book | usdjpy_asia_range | Entry hour (NY) | 4 | size_1.5 | worth_size | 14% | +23167 | +0.73 | 72370 | 3.11 | live_ready |
| single_book | usdjpy_monday_or | Week of month | 2 | size_1.5 | worth_size | 21% | +21984 | +1.07 | 117889 | 5.79 | live_ready |
| cross_book | usdjpy_monday_or | Week of month | 2 | size_1.5 | worth_size | 21% | +21984 | +1.07 | 117889 | 5.79 | live_ready |
| single_book | usdjpy_asia_range | 5m MA vs trade | ma_opposed | size_1.5 | worth_size | 12% | +20672 | +0.87 | 69875 | 3.25 | live_ready |
| cross_book | usdjpy_asia_range | 5m MA vs trade | ma_opposed | size_1.5 | worth_size | 12% | +20672 | +0.87 | 69875 | 3.25 | live_ready |
| cross_book | usdjpy_asia_range | ATR14 quartile | atr_q4 | size_1.5 | worth_size | 25% | +15059 | -0.06 | 64262 | 2.32 | needs_rolling_proxy |
| cross_book | usdjpy_asia_range | Hourly RSI bucket | rsi_gt70 | size_1.5 | worth_size | 6% | +13893 | +0.62 | 63096 | 3.00 | live_ready |
| single_book | usdjpy_asia_range | ATR14 quartile | atr_q2 | size_1.25 | worth_size | 31% | +13186 | +0.50 | 62388 | 2.89 | needs_rolling_proxy |
| cross_book | usdjpy_asia_range | ATR14 quartile | atr_q2 | size_1.25 | worth_size | 31% | +13186 | +0.50 | 62388 | 2.89 | needs_rolling_proxy |
| single_book | usdjpy_monday_or | Day of week | Thursday | size_1.5 | worth_size | 14% | +12964 | +0.10 | 108869 | 4.82 | live_ready |
| cross_book | usdjpy_monday_or | Day of week | Thursday | size_1.5 | worth_size | 14% | +12964 | +0.10 | 108869 | 4.82 | live_ready |
| cross_book | usdjpy_monday_or | Week of month | 4 | size_1.5 | worth_size | 22% | +11855 | -0.12 | 107761 | 4.60 | live_ready |
| single_book | usdjpy_asia_range | Entry hour (NY) | 4 | size_1.25 | worth_size | 14% | +11584 | +0.50 | 60786 | 2.88 | live_ready |
| cross_book | usdjpy_asia_range | Entry hour (NY) | 4 | size_1.25 | worth_size | 14% | +11584 | +0.50 | 60786 | 2.88 | live_ready |
| single_book | usdjpy_monday_or | Week of month | 2 | size_1.25 | worth_size | 21% | +10992 | +0.54 | 106897 | 5.26 | live_ready |
| cross_book | usdjpy_monday_or | Week of month | 2 | size_1.25 | worth_size | 21% | +10992 | +0.54 | 106897 | 5.26 | live_ready |
| single_book | usdjpy_asia_range | 5m MA vs trade | ma_opposed | size_1.25 | worth_size | 12% | +10336 | +0.44 | 59539 | 2.83 | live_ready |
| cross_book | usdjpy_asia_range | 5m MA vs trade | ma_opposed | size_1.25 | worth_size | 12% | +10336 | +0.44 | 59539 | 2.83 | live_ready |
| single_book | usdjpy_monday_or | Hourly RSI bucket | rsi_gt70 | size_1.5 | worth_size | 8% | +9541 | -0.14 | 105446 | 4.58 | live_ready |
| cross_book | usdjpy_monday_or | Hourly RSI bucket | rsi_gt70 | size_1.5 | worth_size | 8% | +9541 | -0.14 | 105446 | 4.58 | live_ready |
| cross_book | eurusd_monday_or | ATR14 quartile | atr_q4 | size_1.5 | worth_size | 3% | +8558 | +0.17 | -10646 | -0.18 | needs_rolling_proxy |
| single_book | eurusd_monday_or | Entry hour (NY) | 14 | size_1.5 | worth_size | 8% | +8201 | +0.16 | -11004 | -0.20 | live_ready |
| single_book | eurusd_st_pmc_3r | Day of week | Thursday | size_1.5 | worth_size | 21% | +7894 | +0.35 | 14668 | 0.69 | live_ready |
| cross_book | eurusd_st_pmc_3r | Day of week | Thursday | size_1.5 | worth_size | 21% | +7894 | +0.35 | 14668 | 0.69 | live_ready |
| cross_book | usdjpy_asia_range | ATR14 quartile | atr_q4 | size_1.25 | worth_size | 25% | +7530 | +0.08 | 56732 | 2.46 | needs_rolling_proxy |
| cross_book | usdjpy_asia_range | Hourly RSI bucket | rsi_gt70 | size_1.25 | worth_size | 6% | +6947 | +0.31 | 56149 | 2.69 | live_ready |
| single_book | eurusd_st_pmc_3r | Hourly RSI vs trade | rsi_against_side | size_1.5 | worth_size | 23% | +6913 | +0.44 | 13688 | 0.78 | live_ready |
| cross_book | eurusd_st_pmc_3r | Hourly RSI vs trade | rsi_against_side | size_1.5 | worth_size | 23% | +6913 | +0.44 | 13688 | 0.78 | live_ready |
| single_book | usdjpy_monday_or | Day of week | Thursday | size_1.25 | worth_size | 14% | +6482 | +0.05 | 102387 | 4.77 | live_ready |
| cross_book | usdjpy_monday_or | Day of week | Thursday | size_1.25 | worth_size | 14% | +6482 | +0.05 | 102387 | 4.77 | live_ready |
| single_book | usdjpy_monday_or | Entry hour (NY) | 5 | size_1.5 | worth_size | 3% | +6464 | +0.48 | 102370 | 5.21 | live_ready |
| cross_book | usdjpy_monday_or | Week of month | 4 | size_1.25 | worth_size | 22% | +5928 | -0.02 | 101833 | 4.70 | live_ready |
| cross_book | eurusd_monday_or | Day of week | Thursday | size_1.5 | worth_size | 19% | +5293 | +0.11 | -13911 | -0.24 | live_ready |
| single_book | us30_monday_or | Entry hour (NY) | 11 | size_1.5 | worth_size | 9% | +5054 | +0.26 | 19479 | 1.16 | live_ready |
| cross_book | us30_monday_or | Entry hour (NY) | 11 | size_1.5 | worth_size | 9% | +5054 | +0.26 | 19479 | 1.16 | live_ready |
| cross_book | eurusd_st_pmc_3r | Week of month | 2 | size_1.5 | worth_size | 22% | +4917 | +0.17 | 11691 | 0.50 | live_ready |
| single_book | us30_monday_or | Entry hour (NY) | 10 | size_1.5 | worth_size | 15% | +4831 | +0.35 | 19255 | 1.26 | live_ready |
| cross_book | us30_london_prior_opposed | Hourly RSI vs trade | rsi_against_side | size_1.5 | worth_size | 72% | +4385 | +0.44 | 12227 | 2.98 | live_ready |
| cross_book | eurusd_monday_or | ATR14 quartile | atr_q4 | size_1.25 | worth_size | 3% | +4279 | +0.09 | -14925 | -0.27 | needs_rolling_proxy |
| single_book | us30_monday_or | Hourly RSI bucket | rsi_55_70 | size_1.5 | worth_size | 29% | +4241 | +0.16 | 18666 | 1.06 | live_ready |
| cross_book | us30_monday_or | Hourly RSI bucket | rsi_55_70 | size_1.5 | worth_size | 29% | +4241 | +0.16 | 18666 | 1.06 | live_ready |
| cross_book | us30_monday_or | Prior-week range half | week_opposed | size_1.25 | worth_size | 75% | +4145 | +0.08 | 18570 | 0.99 | live_ready |
| single_book | us30_monday_or | Day of week | Friday | size_1.5 | worth_size | 10% | +4140 | +0.30 | 18565 | 1.20 | live_ready |
| cross_book | us30_monday_or | Day of week | Friday | size_1.5 | worth_size | 10% | +4140 | +0.30 | 18565 | 1.20 | live_ready |
| single_book | eurusd_monday_or | Entry hour (NY) | 14 | size_1.25 | worth_size | 8% | +4100 | +0.08 | -15104 | -0.28 | live_ready |
| single_book | eurusd_st_pmc_3r | Day of week | Thursday | size_1.25 | worth_size | 21% | +3947 | +0.18 | 10721 | 0.51 | live_ready |
| cross_book | eurusd_st_pmc_3r | Day of week | Thursday | size_1.25 | worth_size | 21% | +3947 | +0.18 | 10721 | 0.51 | live_ready |
| single_book | eurusd_monday_or | 5m MA vs trade | ma_opposed | size_1.5 | worth_size | 9% | +3926 | +0.08 | -15278 | -0.28 | live_ready |
| cross_book | eurusd_monday_or | 5m MA vs trade | ma_opposed | size_1.5 | worth_size | 9% | +3926 | +0.08 | -15278 | -0.28 | live_ready |
| single_book | us30_london_prior_opposed | Entry hour (NY) | 3 | size_1.5 | worth_size | 33% | +3528 | +0.65 | 11369 | 3.19 | live_ready |
| cross_book | us30_london_prior_opposed | Entry hour (NY) | 3 | size_1.5 | worth_size | 33% | +3528 | +0.65 | 11369 | 3.19 | live_ready |
| cross_book | us30_london_prior_opposed | 5m MA vs trade | ma_opposed | size_1.5 | worth_size | 32% | +3479 | +0.51 | 11320 | 3.05 | live_ready |
| single_book | eurusd_st_pmc_3r | Hourly RSI vs trade | rsi_against_side | size_1.25 | worth_size | 23% | +3457 | +0.21 | 10231 | 0.54 | live_ready |
| cross_book | eurusd_st_pmc_3r | Hourly RSI vs trade | rsi_against_side | size_1.25 | worth_size | 23% | +3457 | +0.21 | 10231 | 0.54 | live_ready |
| single_book | eurusd_st_pmc_3r | Entry hour (NY) | 13 | size_1.5 | worth_size | 13% | +2952 | +0.11 | 9726 | 0.45 | live_ready |
| cross_book | eurusd_monday_or | Day of week | Thursday | size_1.25 | worth_size | 19% | +2647 | +0.06 | -16558 | -0.30 | live_ready |
| single_book | us30_monday_or | Entry hour (NY) | 11 | size_1.25 | worth_size | 9% | +2527 | +0.13 | 16952 | 1.03 | live_ready |
| cross_book | us30_monday_or | Entry hour (NY) | 11 | size_1.25 | worth_size | 9% | +2527 | +0.13 | 16952 | 1.03 | live_ready |
| cross_book | us30_monday_or | ATR14 quartile | atr_q2 | size_1.5 | worth_size | 27% | +2526 | +0.03 | 16951 | 0.94 | needs_rolling_proxy |
| cross_book | eurusd_st_pmc_3r | Week of month | 2 | size_1.25 | worth_size | 22% | +2458 | +0.09 | 9232 | 0.43 | live_ready |
| single_book | us30_london_prior_opposed | ATR14 quartile | atr_q2 | size_1.5 | worth_size | 31% | +2456 | +0.68 | 10297 | 3.22 | needs_rolling_proxy |
| cross_book | us30_london_prior_opposed | ATR14 quartile | atr_q2 | size_1.5 | worth_size | 31% | +2456 | +0.68 | 10297 | 3.22 | needs_rolling_proxy |
| single_book | us30_monday_or | Entry hour (NY) | 10 | size_1.25 | worth_size | 15% | +2415 | +0.17 | 16840 | 1.08 | live_ready |
| cross_book | us30_london_prior_opposed | Hourly RSI vs trade | rsi_against_side | size_1.25 | worth_size | 72% | +2193 | +0.26 | 10034 | 2.81 | live_ready |
| single_book | us30_london_prior_opposed | Hourly RSI bucket | rsi_30_45 | size_1.5 | worth_size | 28% | +2167 | +0.64 | 10009 | 3.19 | live_ready |
| single_book | us30_monday_or | Week of month | 4 | size_1.5 | worth_size | 22% | +2124 | +0.07 | 16549 | 0.97 | live_ready |
| cross_book | us30_monday_or | Week of month | 4 | size_1.5 | worth_size | 22% | +2124 | +0.07 | 16549 | 0.97 | live_ready |
| single_book | us30_monday_or | Hourly RSI bucket | rsi_55_70 | size_1.25 | worth_size | 29% | +2120 | +0.08 | 16545 | 0.99 | live_ready |
| cross_book | us30_monday_or | Hourly RSI bucket | rsi_55_70 | size_1.25 | worth_size | 29% | +2120 | +0.08 | 16545 | 0.99 | live_ready |
| single_book | us30_monday_or | Day of week | Friday | size_1.25 | worth_size | 10% | +2070 | +0.15 | 16495 | 1.05 | live_ready |
| cross_book | us30_monday_or | Day of week | Friday | size_1.25 | worth_size | 10% | +2070 | +0.15 | 16495 | 1.05 | live_ready |
| single_book | us30_st_pmc_3r | Week of month | 2 | size_1.5 | worth_size | 34% | +1790 | +1.01 | 11005 | 23.33 | live_ready |
| cross_book | us30_st_pmc_3r | Week of month | 2 | size_1.5 | worth_size | 34% | +1790 | +1.01 | 11005 | 23.33 | live_ready |
| cross_book | eurusd_st_pmc_3r | Hourly RSI bucket | rsi_55_70 | size_1.5 | worth_size | 22% | +1780 | +0.12 | 8554 | 0.45 | live_ready |
| single_book | us30_london_prior_opposed | Entry hour (NY) | 3 | size_1.25 | worth_size | 33% | +1764 | +0.36 | 9605 | 2.90 | live_ready |
| cross_book | us30_london_prior_opposed | Entry hour (NY) | 3 | size_1.25 | worth_size | 33% | +1764 | +0.36 | 9605 | 2.90 | live_ready |
| cross_book | us30_london_prior_opposed | 5m MA vs trade | ma_opposed | size_1.25 | worth_size | 32% | +1739 | +0.28 | 9581 | 2.83 | live_ready |
| cross_book | eurusd_st_pmc_3r | Prior-week range half | week_opposed | size_1.5 | worth_size | 75% | +1708 | +0.01 | 8482 | 0.34 | live_ready |
| cross_book | eurusd_st_pmc_3r | Week of month | 4 | size_1.5 | worth_size | 22% | +1529 | +0.04 | 8303 | 0.37 | live_ready |
| single_book | eurusd_st_pmc_3r | Entry hour (NY) | 13 | size_1.25 | worth_size | 13% | +1476 | +0.06 | 8250 | 0.39 | live_ready |
| single_book | eurusd_st_pmc_3r | Day of week | Friday | size_1.5 | worth_size | 21% | +1354 | +0.04 | 8128 | 0.37 | live_ready |
| cross_book | eurusd_st_pmc_3r | Day of week | Friday | size_1.5 | worth_size | 21% | +1354 | +0.04 | 8128 | 0.37 | live_ready |
| cross_book | us30_st_pmc_3r | Day of week | Friday | size_1.5 | worth_size | 23% | +1334 | +3.23 | 10549 | 25.56 | live_ready |
| single_book | us30_st_pmc_3r | Day of week | Thursday | size_1.5 | worth_size | 18% | +1318 | +1.69 | 10533 | 24.01 | live_ready |
| cross_book | us30_st_pmc_3r | Day of week | Thursday | size_1.5 | worth_size | 18% | +1318 | +1.69 | 10533 | 24.01 | live_ready |
| cross_book | us30_monday_or | ATR14 quartile | atr_q2 | size_1.25 | worth_size | 27% | +1263 | +0.02 | 15688 | 0.92 | needs_rolling_proxy |
| single_book | us30_london_prior_opposed | ATR14 quartile | atr_q2 | size_1.25 | worth_size | 31% | +1228 | +0.35 | 9070 | 2.89 | needs_rolling_proxy |
| cross_book | us30_london_prior_opposed | ATR14 quartile | atr_q2 | size_1.25 | worth_size | 31% | +1228 | +0.35 | 9070 | 2.89 | needs_rolling_proxy |
| cross_book | us30_london_prior_opposed | Hourly RSI bucket | rsi_55_70 | size_1.5 | worth_size | 36% | +1214 | -0.26 | 9056 | 2.29 | live_ready |
| single_book | us30_london_prior_opposed | Hourly RSI bucket | rsi_30_45 | size_1.25 | worth_size | 28% | +1084 | +0.33 | 8925 | 2.87 | live_ready |
| single_book | us30_monday_or | Week of month | 4 | size_1.25 | worth_size | 22% | +1062 | +0.04 | 15487 | 0.94 | live_ready |
| cross_book | us30_monday_or | Week of month | 4 | size_1.25 | worth_size | 22% | +1062 | +0.04 | 15487 | 0.94 | live_ready |
| single_book | nas100_st_pmc_3r | Hourly RSI vs trade | rsi_against_side | size_1.5 | worth_size | 20% | +1013 | +3.36 | 7402 | 18.38 | live_ready |
| cross_book | nas100_st_pmc_3r | Hourly RSI vs trade | rsi_against_side | size_1.5 | worth_size | 20% | +1013 | +3.36 | 7402 | 18.38 | live_ready |
| cross_book | nas100_st_pmc_3r | Day of week | Friday | size_1.5 | worth_size | 17% | +949 | +2.23 | 7339 | 17.25 | live_ready |
| single_book | us30_st_pmc_3r | Week of month | 2 | size_1.25 | worth_size | 34% | +895 | +0.73 | 10110 | 23.05 | live_ready |
| cross_book | us30_st_pmc_3r | Week of month | 2 | size_1.25 | worth_size | 34% | +895 | +0.73 | 10110 | 23.05 | live_ready |
| cross_book | eurusd_st_pmc_3r | Hourly RSI bucket | rsi_55_70 | size_1.25 | worth_size | 22% | +890 | +0.06 | 7664 | 0.39 | live_ready |
| cross_book | eurusd_st_pmc_3r | Prior-week range half | week_opposed | size_1.25 | worth_size | 75% | +854 | +0.01 | 7628 | 0.34 | live_ready |
| cross_book | eurusd_st_pmc_3r | Week of month | 4 | size_1.25 | worth_size | 22% | +764 | +0.02 | 7538 | 0.35 | live_ready |
| single_book | eurusd_st_pmc_3r | Day of week | Friday | size_1.25 | worth_size | 21% | +677 | +0.02 | 7451 | 0.36 | live_ready |
| cross_book | eurusd_st_pmc_3r | Day of week | Friday | size_1.25 | worth_size | 21% | +677 | +0.02 | 7451 | 0.36 | live_ready |
| cross_book | us30_st_pmc_3r | Day of week | Friday | size_1.25 | worth_size | 23% | +667 | +1.62 | 9882 | 23.94 | live_ready |
| single_book | us30_st_pmc_3r | Day of week | Thursday | size_1.25 | worth_size | 18% | +659 | +0.87 | 9874 | 23.19 | live_ready |
| cross_book | us30_st_pmc_3r | Day of week | Thursday | size_1.25 | worth_size | 18% | +659 | +0.87 | 9874 | 23.19 | live_ready |
| cross_book | us30_london_prior_opposed | Hourly RSI bucket | rsi_55_70 | size_1.25 | worth_size | 36% | +607 | -0.14 | 8449 | 2.40 | live_ready |
| cross_book | us30_london_prior_opposed | Week of month | 4 | size_1.5 | worth_size | 13% | +537 | -0.07 | 8379 | 2.47 | live_ready |
| single_book | nas100_st_pmc_3r | Hourly RSI vs trade | rsi_against_side | size_1.25 | worth_size | 20% | +507 | +1.63 | 6896 | 16.65 | live_ready |
| cross_book | nas100_st_pmc_3r | Hourly RSI vs trade | rsi_against_side | size_1.25 | worth_size | 20% | +507 | +1.63 | 6896 | 16.65 | live_ready |
| cross_book | nas100_st_pmc_3r | Day of week | Friday | size_1.25 | worth_size | 17% | +475 | +1.12 | 6864 | 16.13 | live_ready |
| cross_book | nas100_st_pmc_3r | Entry hour (NY) | 11 | size_1.5 | worth_size | 7% | +439 | +0.11 | 6828 | 15.13 | live_ready |

## Single-book candidates tested

- `eurusd_monday_or` · Hourly RSI vs trade=rsi_against_side · profile n=106 WR+13.3pp avg$+390 z=2.93
- `eurusd_monday_or` · 5m MA vs trade=ma_opposed · profile n=269 WR+5.2pp avg$+249 z=1.79
- `eurusd_monday_or` · Day of week=Friday · profile n=344 WR+15.3pp avg$+45 z=5.83
- `eurusd_monday_or` · Entry hour (NY)=14 · profile n=219 WR+10.1pp avg$+116 z=3.14
- `eurusd_monday_or` · Prior-day range half=day_aligned · profile n=107 WR+9.2pp avg$+63 z=2.03
- `eurusd_st_pmc_3r` · Day of week=Thursday · profile n=175 WR+6.4pp avg$+125 z=1.70
- `eurusd_st_pmc_3r` · Day of week=Friday · profile n=168 WR+6.1pp avg$+123 z=1.59
- `eurusd_st_pmc_3r` · Entry hour (NY)=13 · profile n=95 WR+7.8pp avg$+159 z=1.60
- `eurusd_st_pmc_3r` · Hourly RSI vs trade=rsi_against_side · profile n=245 WR+4.5pp avg$+91 z=1.36
- `eurusd_st_pmc_3r` · Week of month=1 · profile n=219 WR+2.5pp avg$+52 z=0.73
- `eurusd_v2b_ungated` · Entry hour (NY)=11 · profile n=197 WR+7.5pp avg$+31 z=2.03
- `eurusd_v2b_ungated` · ATR14 quartile=atr_q4 · profile n=594 WR+4.0pp avg$+9 z=1.76
- `eurusd_v2b_ungated` · Hourly RSI bucket=rsi_le30 · profile n=116 WR+4.3pp avg$+27 z=0.91
- `eurusd_v2b_ungated` · Hourly RSI bucket=rsi_gt70 · profile n=125 WR+2.4pp avg$+36 z=0.52
- `nas100_st_pmc_3r` · Hourly RSI vs trade=rsi_against_side · profile n=94 WR+10.2pp avg$+19 z=1.83
- `nas100_v2b_london` · Entry hour (NY)=3 · profile n=1043 WR+2.7pp avg$+11 z=1.35
- `nas100_v2b_london` · Day of week=Tuesday · profile n=323 WR+3.1pp avg$+7 z=1.03
- `nas100_v2b_london` · Hourly RSI bucket=rsi_gt70 · profile n=137 WR+2.6pp avg$+15 z=0.59
- `nas100_v2b_london` · Week of month=2 · profile n=367 WR+1.8pp avg$+7 z=0.61
- `us30_london_prior_opposed` · Entry hour (NY)=3 · profile n=104 WR+12.7pp avg$+87 z=2.29
- `us30_london_prior_opposed` · ATR14 quartile=atr_q2 · profile n=75 WR+6.7pp avg$+91 z=1.06
- `us30_london_prior_opposed` · Hourly RSI bucket=rsi_30_45 · profile n=85 WR+3.4pp avg$+90 z=0.56
- `us30_monday_or` · Day of week=Friday · profile n=125 WR+19.6pp avg$+29 z=4.58
- `us30_monday_or` · Hourly RSI bucket=rsi_55_70 · profile n=357 WR+7.8pp avg$+26 z=2.83
- `us30_monday_or` · Entry hour (NY)=11 · profile n=106 WR+4.8pp avg$+128 z=1.04
- `us30_monday_or` · Entry hour (NY)=10 · profile n=149 WR+3.7pp avg$+47 z=0.94
- `us30_monday_or` · Week of month=4 · profile n=255 WR+1.4pp avg$+32 z=0.45
- `us30_st_pmc_3r` · Day of week=Thursday · profile n=119 WR+7.9pp avg$+16 z=1.58
- `us30_st_pmc_3r` · Week of month=2 · profile n=159 WR+6.5pp avg$+14 z=1.47
- `usdjpy_asia_range` · Entry hour (NY)=4 · profile n=120 WR+8.8pp avg$+527 z=1.80
- `usdjpy_asia_range` · ATR14 quartile=atr_q2 · profile n=215 WR+7.3pp avg$+237 z=1.91
- `usdjpy_asia_range` · 5m MA vs trade=ma_opposed · profile n=103 WR+4.9pp avg$+471 z=0.95
- `usdjpy_monday_or` · Hourly RSI bucket=rsi_gt70 · profile n=149 WR+9.7pp avg$+217 z=2.45
- `usdjpy_monday_or` · Day of week=Thursday · profile n=297 WR+5.5pp avg$+21 z=1.89
- `usdjpy_monday_or` · Entry hour (NY)=5 · profile n=66 WR+9.0pp avg$+566 z=1.55
- `usdjpy_monday_or` · Entry hour (NY)=4 · profile n=64 WR+7.2pp avg$+446 z=1.21
- `usdjpy_monday_or` · Week of month=2 · profile n=418 WR+3.3pp avg$+131 z=1.31

## Cross-book candidates tested

- **Hourly RSI bucket=rsi_gt70** · 5 books (eurusd_monday_or,eurusd_v2b_ungated,nas100_v2b_london,usdjpy_asia_range,usdjpy_monday_or) · med WR+2.6pp med avg$+60
- **Week of month=4** · 5 books (eurusd_st_pmc_3r,nas100_v2b_london,us30_london_prior_opposed,us30_monday_or,usdjpy_monday_or) · med WR+1.7pp med avg$+36
- **Day of week=Friday** · 5 books (eurusd_monday_or,eurusd_st_pmc_3r,nas100_st_pmc_3r,us30_monday_or,us30_st_pmc_3r) · med WR+7.5pp med avg$+29
- **Day of week=Thursday** · 5 books (eurusd_monday_or,eurusd_st_pmc_3r,nas100_v2b_london,us30_st_pmc_3r,usdjpy_monday_or) · med WR+5.5pp med avg$+21
- **ATR14 quartile=atr_q4** · 4 books (eurusd_monday_or,eurusd_st_pmc_3r,eurusd_v2b_ungated,usdjpy_asia_range) · med WR+3.1pp med avg$+73
- **Hourly RSI vs trade=rsi_against_side** · 4 books (eurusd_monday_or,eurusd_st_pmc_3r,nas100_st_pmc_3r,us30_london_prior_opposed) · med WR+7.3pp med avg$+66
- **Prior-week range half=week_opposed** · 4 books (eurusd_monday_or,eurusd_st_pmc_3r,us30_monday_or,usdjpy_monday_or) · med WR+1.6pp med avg$+24
- **Week of month=2** · 4 books (eurusd_st_pmc_3r,nas100_v2b_london,us30_st_pmc_3r,usdjpy_monday_or) · med WR+2.5pp med avg$+21
- **Entry hour (NY)=4** · 3 books (eurusd_monday_or,usdjpy_asia_range,usdjpy_monday_or) · med WR+7.2pp med avg$+446
- **5m MA vs trade=ma_opposed** · 3 books (eurusd_monday_or,us30_london_prior_opposed,usdjpy_asia_range) · med WR+5.2pp med avg$+249
- **ATR14 quartile=atr_q2** · 3 books (us30_london_prior_opposed,us30_monday_or,usdjpy_asia_range) · med WR+6.7pp med avg$+91
- **Entry hour (NY)=3** · 3 books (eurusd_monday_or,nas100_v2b_london,us30_london_prior_opposed) · med WR+3.2pp med avg$+87
- **Entry hour (NY)=11** · 3 books (eurusd_v2b_ungated,nas100_st_pmc_3r,us30_monday_or) · med WR+7.5pp med avg$+31
- **Hourly RSI bucket=rsi_55_70** · 3 books (eurusd_st_pmc_3r,us30_london_prior_opposed,us30_monday_or) · med WR+2.4pp med avg$+30
- **Week of month=5** · 3 books (eurusd_st_pmc_3r,eurusd_v2b_ungated,nas100_v2b_london) · med WR+2.7pp med avg$+18

## Full-tape top Δnet overlays

| scope | book | condition=bucket | policy | hp% | base net | overlay net | Δnet | base N/S | N/S | stress× |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| cross_book | usdjpy_monday_or | Prior-week range half=week_opposed | size_1.5 | 70% | 293966 | 441583 | +147617 | 14.47 | 16.16 | 1.34 |
| cross_book | eurusd_v2b_ungated | Hourly RSI bucket=rsi_gt70 | filter | 5% | -110259 | -1342 | +108917 | -0.95 | -0.21 | 0.06 |
| single_book | eurusd_v2b_ungated | Hourly RSI bucket=rsi_gt70 | filter | 5% | -110259 | -1342 | +108917 | -0.95 | -0.21 | 0.06 |
| single_book | eurusd_v2b_ungated | Hourly RSI bucket=rsi_le30 | filter | 5% | -110259 | -2236 | +108023 | -0.95 | -0.42 | 0.05 |
| cross_book | eurusd_v2b_ungated | Entry hour (NY)=11 | filter | 8% | -110259 | -2996 | +107263 | -0.95 | -0.69 | 0.04 |
| single_book | eurusd_v2b_ungated | Entry hour (NY)=11 | filter | 8% | -110259 | -2996 | +107263 | -0.95 | -0.69 | 0.04 |
| cross_book | eurusd_v2b_ungated | Week of month=5 | filter | 8% | -110259 | -5536 | +104723 | -0.95 | -0.49 | 0.10 |
| cross_book | eurusd_v2b_ungated | ATR14 quartile=atr_q4 | filter | 25% | -110259 | -21846 | +88413 | -0.95 | -0.79 | 0.24 |
| single_book | eurusd_v2b_ungated | ATR14 quartile=atr_q4 | filter | 25% | -110259 | -21846 | +88413 | -0.95 | -0.79 | 0.24 |
| cross_book | usdjpy_monday_or | Prior-week range half=week_opposed | size_1.25 | 70% | 293966 | 367775 | +73808 | 14.47 | 15.79 | 1.15 |
| cross_book | usdjpy_monday_or | Week of month=2 | size_1.5 | 22% | 293966 | 353583 | +59617 | 14.47 | 16.57 | 1.05 |
| single_book | usdjpy_monday_or | Week of month=2 | size_1.5 | 22% | 293966 | 353583 | +59617 | 14.47 | 16.57 | 1.05 |
| cross_book | eurusd_monday_or | Prior-week range half=week_opposed | size_1.5 | 74% | 102368 | 156758 | +54391 | 1.90 | 2.14 | 1.36 |
| single_book | usdjpy_asia_range | ATR14 quartile=atr_q2 | size_1.5 | 25% | 178443 | 226194 | +47751 | 8.65 | 10.02 | 1.09 |
| cross_book | usdjpy_asia_range | ATR14 quartile=atr_q2 | size_1.5 | 25% | 178443 | 226194 | +47751 | 8.65 | 10.02 | 1.09 |
| cross_book | eurusd_monday_or | ATR14 quartile=atr_q4 | size_1.5 | 25% | 102368 | 149385 | +47017 | 1.90 | 2.55 | 1.09 |
| cross_book | usdjpy_monday_or | Week of month=4 | size_1.5 | 23% | 293966 | 340338 | +46372 | 14.47 | 14.54 | 1.15 |
| single_book | usdjpy_asia_range | Entry hour (NY)=4 | size_1.5 | 14% | 178443 | 222527 | +44083 | 8.65 | 9.58 | 1.13 |
| cross_book | usdjpy_asia_range | Entry hour (NY)=4 | size_1.5 | 14% | 178443 | 222527 | +44083 | 8.65 | 9.58 | 1.13 |
| cross_book | eurusd_monday_or | 5m MA vs trade=ma_opposed | size_1.5 | 9% | 102368 | 140682 | +38315 | 1.90 | 2.57 | 1.01 |
| single_book | eurusd_monday_or | 5m MA vs trade=ma_opposed | size_1.5 | 9% | 102368 | 140682 | +38315 | 1.90 | 2.57 | 1.01 |
| cross_book | usdjpy_asia_range | ATR14 quartile=atr_q4 | size_1.5 | 25% | 178443 | 214447 | +36004 | 8.65 | 7.15 | 1.45 |
| cross_book | usdjpy_asia_range | 5m MA vs trade=ma_opposed | size_1.5 | 12% | 178443 | 213389 | +34946 | 8.65 | 9.92 | 1.04 |
| single_book | usdjpy_asia_range | 5m MA vs trade=ma_opposed | size_1.5 | 12% | 178443 | 213389 | +34946 | 8.65 | 9.92 | 1.04 |
| cross_book | eurusd_st_pmc_3r | Prior-week range half=week_opposed | size_1.5 | 76% | 64720 | 98379 | +33659 | 3.18 | 3.98 | 1.21 |

## Verdict draft

**Size-up is worth it on already-good books; filters are secondary.**

Best OOS size overlays (live-ready, positive baseline book): USDJPY Monday OR
`week_opposed` / `week_of_month=2` / Thursday; USDJPY Asia-range `hour=4` /
`ma_opposed` / `rsi_gt70`; EURUSD ST+PMC Thursday + `rsi_against`; lighter lifts on
US30 Monday OR (Fri / hour 10–11) and London prior (hour 3 / ma_opposed). Prefer
**1.25×** for cross-book, **1.5×** only on A1/A2 single-book cells after shadow.

Hard filters help as sit-outs (esp. EURUSD ST+PMC Thursday) but EURUSD/NAS100 v2b
“filter Δnet” is mostly lose-less on a broken book — not a promote path.

ATR quartile: defer until causal rolling percentile. All scored features are
entry-asof (pre-fill). See `LIVE_PLAN.md` for staged live/demo rollout.
