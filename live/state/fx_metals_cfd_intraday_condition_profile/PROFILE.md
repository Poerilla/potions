# FX / metals / CFD intraday condition profile (width-aware)

Study: `fx_metals_cfd_intraday_condition_profile_v1`

Phase **1** — diagnostic + shortlist for 1.25× HP nulls (Phase 2).
See [`PLAN.md`](PLAN.md) for full rollout including **quarterly breakout**.

## Books

| book | symbol | family | campaigns | baseline net | N/S |
|---|---|---|---:|---:|---:|
| eurusd_monday_or | EURUSD | monday_or | 2868 | +102368 | 1.90 |
| usdjpy_monday_or | USDJPY | monday_or | 1907 | +293966 | 14.47 |
| us30_monday_or | US30 | monday_or | 1121 | +31330 | 1.96 |
| gbpusd_monday_or | GBPUSD | monday_or | 2822 | +259305 | 2.99 |
| audjpy_monday_or | AUDJPY | monday_or | 2749 | +128457 | 2.38 |
| xauusd_monday_or | XAUUSD | monday_or | 3968 | +402718 | 1.94 |
| usdjpy_asia_range | USDJPY | asia_range | 861 | +178443 | 8.65 |
| eurusd_v2b_ungated | EURUSD | v2b | 2383 | -110259 | -0.95 |
| nas100_v2b_london | NAS100 | v2b | 1618 | -15399 | -0.82 |
| us30_london_prior_opposed | US30 | london_prior | 300 | +24370 | 7.90 |
| eurusd_st_pmc_3r | EURUSD | st_pmc | 865 | +64720 | 3.18 |
| gbpusd_st_pmc_3r | GBPUSD | st_pmc | 1025 | +108261 | 8.68 |
| usdjpy_st_pmc_3r | USDJPY | st_pmc | 869 | +36727 | 1.83 |
| audjpy_st_pmc_3r | AUDJPY | st_pmc | 850 | +83304 | 8.00 |
| nas100_st_pmc_3r | NAS100 | st_pmc | 477 | +15219 | 23.66 |
| us30_st_pmc_3r | US30 | st_pmc | 578 | +19028 | 44.20 |
| xauusd_st_pmc_3r | XAUUSD | st_pmc | 169 | +77327 | 0.91 |
| eurusd_quarterly_breakout | EURUSD | quarterly_breakout | 110 | +144535 | 0.85 |
| gbpusd_quarterly_breakout | GBPUSD | quarterly_breakout | 102 | +312052 | 1.78 |
| usdjpy_quarterly_breakout | USDJPY | quarterly_breakout | 111 | +20272 | 0.11 |
| audjpy_quarterly_breakout | AUDJPY | quarterly_breakout | 117 | -218823 | -0.66 |
| xauusd_quarterly_breakout | XAUUSD | quarterly_breakout | 113 | +1141869 | 3.71 |
| xagusd_quarterly_breakout | XAGUSD | quarterly_breakout | 108 | -182896 | -0.53 |
| us30_quarterly_breakout | US30 | quarterly_breakout | 48 | +74392 | 1.38 |
| nas100_quarterly_breakout | NAS100 | quarterly_breakout | 49 | +96731 | 5.98 |

## Shortlisted candidates (≤3/book, ≤1/family, cov 5–35%)

| book | condition=bucket | fam | cov | n | avg lift | inc N/S | z_WR |
|---|---|---|---:|---:|---:|---:|---:|
| audjpy_monday_or | Hourly RSI bucket=rsi_45_55 | momentum_rsi | 13% | 369 | +101 | 3.52 | 1.82 |
| audjpy_monday_or | 5m MA vs trade=ma_opposed | ma_opposition | 10% | 266 | +199 | 3.47 | 0.44 |
| audjpy_monday_or | Entry hour (NY)=7 | calendar | 5% | 143 | +163 | 3.14 | 1.39 |
| audjpy_st_pmc_3r | Month=11 | calendar | 8% | 68 | +185 | 8.87 | 1.80 |
| audjpy_st_pmc_3r | Hourly RSI vs trade=rsi_with_side | momentum_rsi | 20% | 173 | +106 | 8.50 | 1.48 |
| audjpy_st_pmc_3r | Prior quarter type=q_break_down | htf_quarter | 26% | 225 | +63 | 7.22 | 1.02 |
| eurusd_monday_or | 5m MA vs trade=ma_opposed | ma_opposition | 9% | 269 | +249 | 11.99 | 1.79 |
| eurusd_monday_or | Month=5 | calendar | 9% | 245 | +241 | 4.50 | 0.30 |
| eurusd_monday_or | Yearly ORB direction=yor_inside | htf_orb | 11% | 303 | +181 | 3.37 | 0.81 |
| eurusd_st_pmc_3r | Day of week=Thursday | calendar | 20% | 175 | +125 | 8.39 | 1.70 |
| eurusd_st_pmc_3r | Hourly RSI vs trade=rsi_against_side | momentum_rsi | 28% | 245 | +91 | 5.36 | 1.36 |
| eurusd_st_pmc_3r | Yearly ORB direction=yor_inside | htf_orb | 11% | 98 | +94 | 2.25 | 0.96 |
| gbpusd_monday_or | Hourly RSI bucket=rsi_45_55 | momentum_rsi | 14% | 398 | +280 | 8.05 | 1.09 |
| gbpusd_monday_or | Entry hour (NY)=12 | calendar | 6% | 179 | +196 | 4.53 | 1.17 |
| gbpusd_monday_or | Monthly OR direction=mor_up | htf_orb | 34% | 959 | +14 | 2.04 | 0.11 |
| gbpusd_st_pmc_3r | Entry hour (NY)=14 | calendar | 9% | 88 | +278 | 13.40 | 2.67 |
| gbpusd_st_pmc_3r | Hourly RSI bucket=rsi_30_45 | momentum_rsi | 23% | 237 | +89 | 9.72 | 1.32 |
| gbpusd_st_pmc_3r | Yearly ORB direction=yor_up | htf_orb | 30% | 308 | +30 | 5.92 | 0.50 |
| nas100_st_pmc_3r | Entry hour (NY)=11 | calendar | 9% | 43 | +28 | 16.69 | 1.77 |
| nas100_st_pmc_3r | Prior quarter type=q_break_down | htf_quarter | 14% | 66 | +17 | 15.49 | 1.25 |
| nas100_st_pmc_3r | Hourly RSI vs trade=rsi_against_side | momentum_rsi | 20% | 94 | +19 | 15.17 | 1.83 |
| us30_london_prior_opposed | Entry hour (NY)=3 | calendar | 35% | 104 | +87 | 16.08 | 2.29 |
| us30_london_prior_opposed | Hourly RSI bucket=rsi_30_45 | momentum_rsi | 28% | 85 | +90 | 7.08 | 0.56 |
| us30_london_prior_opposed | 5m MA vs trade=ma_opposed | ma_opposition | 34% | 103 | +35 | 5.24 | 1.02 |
| us30_monday_or | Monthly OR direction=mor_both | htf_orb | 7% | 83 | +154 | 7.93 | 2.75 |
| us30_monday_or | Entry hour (NY)=11 | calendar | 9% | 106 | +128 | 6.69 | 1.04 |
| us30_monday_or | Hourly RSI bucket=rsi_55_70 | momentum_rsi | 32% | 357 | +26 | 2.64 | 2.83 |
| us30_st_pmc_3r | Week of month=2 | calendar | 28% | 159 | +14 | 23.86 | 1.47 |
| us30_st_pmc_3r | Prior quarter type=q_break_down | htf_quarter | 11% | 64 | +15 | 13.43 | 1.14 |
| us30_st_pmc_3r | Yearly ORB direction=yor_down | htf_orb | 13% | 73 | +12 | 12.56 | 1.10 |
| usdjpy_asia_range | Entry hour (NY)=4 | calendar | 14% | 120 | +527 | 6.91 | 1.80 |
| usdjpy_asia_range | Hourly RSI bucket=rsi_gt70 | momentum_rsi | 5% | 47 | +1019 | 6.74 | 0.94 |
| usdjpy_asia_range | Monthly OR direction=mor_both | htf_orb | 9% | 76 | +268 | 6.33 | 1.25 |
| usdjpy_monday_or | Week of month=2 | calendar | 22% | 418 | +131 | 9.61 | 1.31 |
| usdjpy_monday_or | Monthly OR direction=mor_inside | htf_orb | 10% | 189 | +170 | 5.93 | 0.26 |
| usdjpy_monday_or | Hourly RSI bucket=rsi_gt70 | momentum_rsi | 8% | 149 | +217 | 5.77 | 2.45 |
| usdjpy_st_pmc_3r | Yearly ORB direction=yor_up | htf_orb | 35% | 304 | +81 | 5.77 | 1.48 |
| usdjpy_st_pmc_3r | Day of week=Wednesday | calendar | 21% | 185 | +100 | 4.35 | 1.51 |
| usdjpy_st_pmc_3r | Prior-week range half=week_aligned | prior_range | 24% | 209 | +57 | 3.04 | 0.91 |
| xauusd_monday_or | Hourly RSI bucket=rsi_55_70 | momentum_rsi | 32% | 1267 | +280 | 5.71 | 2.06 |
| xauusd_monday_or | Month=3 | calendar | 6% | 252 | +627 | 4.65 | 0.85 |
| xauusd_monday_or | 5m MA vs trade=ma_opposed | ma_opposition | 24% | 946 | +103 | 2.60 | 0.82 |
| xauusd_st_pmc_3r | Hourly RSI bucket=rsi_55_70 | momentum_rsi | 31% | 52 | +694 | 1.99 | 0.33 |
| xauusd_st_pmc_3r | Week of month=1 | calendar | 24% | 40 | +1040 | 1.20 | 0.52 |

## Width / HTF notables (positive dual-lift)

- **xauusd_quarterly_breakout** `Prior quarter type=q_break_up` n=62 WR lift +4.2pp avg lift $+10542 inc N/S=4.16
- **xauusd_quarterly_breakout** `Yearly ORB direction=yor_up` n=48 WR lift +0.6pp avg lift $+9913 inc N/S=5.86
- **xauusd_quarterly_breakout** `ATR causal rolling percentile=atr_pctl_q2` n=26 WR lift +7.3pp avg lift $+7427 inc N/S=3.83
- **xauusd_quarterly_breakout** `Prior-quarter range width=pqw_q2` n=26 WR lift +7.3pp avg lift $+6494 inc N/S=2.86
- **audjpy_quarterly_breakout** `Prior-day range percentile=prior_range_exp` n=48 WR lift +7.4pp avg lift $+5806 inc N/S=1.72
- **eurusd_quarterly_breakout** `ATR causal rolling percentile=atr_pctl_q2` n=22 WR lift +11.8pp avg lift $+5687 inc N/S=1.89
- **audjpy_quarterly_breakout** `ATR causal rolling percentile=atr_pctl_q4` n=34 WR lift +2.9pp avg lift $+5104 inc N/S=1.14
- **usdjpy_quarterly_breakout** `ATR causal rolling percentile=atr_pctl_q4` n=37 WR lift +9.0pp avg lift $+5041 inc N/S=2.22
- **audjpy_quarterly_breakout** `ATR causal rolling percentile=atr_pctl_q2` n=25 WR lift +7.0pp avg lift $+4644 inc N/S=1.11
- **gbpusd_quarterly_breakout** `Yearly ORB direction=yor_down` n=36 WR lift +2.3pp avg lift $+4397 inc N/S=2.48
- **xauusd_quarterly_breakout** `Weekly ATR trend vs trade=w_atr_aligned` n=86 WR lift +0.8pp avg lift $+4183 inc N/S=4.00
- **eurusd_quarterly_breakout** `Prior-day range percentile=prior_range_comp` n=38 WR lift +3.4pp avg lift $+4051 inc N/S=2.89
- **xagusd_quarterly_breakout** `Yearly ORB direction=yor_down` n=24 WR lift +6.0pp avg lift $+4006 inc N/S=1.59
- **gbpusd_quarterly_breakout** `ATR causal rolling percentile=atr_pctl_q1` n=42 WR lift +5.5pp avg lift $+3981 inc N/S=2.22
- **usdjpy_quarterly_breakout** `Weekly ATR trend vs trade=w_atr_opposed` n=31 WR lift +8.7pp avg lift $+3582 inc N/S=1.70
- **audjpy_quarterly_breakout** `Prior-quarter range width=pqw_q1` n=40 WR lift +2.0pp avg lift $+3542 inc N/S=1.14
- **eurusd_quarterly_breakout** `Prior quarter type=q_break_up` n=42 WR lift +7.7pp avg lift $+3444 inc N/S=2.44
- **xagusd_quarterly_breakout** `Prior quarter type=q_break_down` n=26 WR lift +8.9pp avg lift $+3369 inc N/S=1.32
- **gbpusd_quarterly_breakout** `Prior-day range percentile=prior_range_comp` n=29 WR lift +6.7pp avg lift $+3281 inc N/S=1.91
- **eurusd_quarterly_breakout** `Yearly ORB direction=yor_up` n=35 WR lift +8.2pp avg lift $+3237 inc N/S=2.55

## Next (Phase 2)

Run matched-added-exposure nulls on shortlist into `live/state/fx_metals_cfd_intraday_hp_sizeup_nulls/`.
Quarterly breakout books: prioritize `Prior-quarter range width` and HTF tags.

## Caveats

- Multiple comparisons — profile lift is hypothesis only.
- Quarterly breakout uses daily entries; min bucket N may be lower on thin books.
- ATR quartile in legacy profile is static; rolling `atr_pct_bucket` is preferred for HP.
