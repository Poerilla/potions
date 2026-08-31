# Intraday condition profile

Diagnostic profile of calendar / HTF / 5m conditions vs broker-like campaign outcomes
for research tapes aligned to **running intraday demos**. Not a promotion gate.

Features (causal asof): day-of-week, week-of-month, NY hour, 5m SMA9/21 state+cross,
hourly RSI14 + OBV×MA20, daily ATR14 quartiles, entry vs prior day/week/month range half
(aligned = long in lower half / short in upper half).

Significance heuristic: n≥40, positive WR and avg-net lift, and (|z_WR|≥1.64 or avg lift ≥35% of |baseline avg|).

## Books

- **EURUSD Monday OR M1_S2_R2 (Phase2)** (`eurusd_monday_or`): n=2868 WR=30.1% avg=$35.69 net=$102368
- **USDJPY Monday OR M2_S3_R1 skip Aug/Sep** (`usdjpy_monday_or`): n=1907 WR=31.9% avg=$154.15 net=$293966
- **US30 Monday OR M3_S3_R2** (`us30_monday_or`): n=1121 WR=29.2% avg=$27.95 net=$31330
- **USDJPY Asia-range London S_3_1_3 filtered** (`usdjpy_asia_range`): n=861 WR=50.4% avg=$207.25 net=$178443
- **EURUSD v2b ungated S_1_1_1** (`eurusd_v2b_ungated`): n=2383 WR=44.8% avg=$-46.27 net=$-110259
- **NAS100 v2b London ungated S_1_1_3 (index OR proxy)** (`nas100_v2b_london`): n=1618 WR=49.2% avg=$-9.52 net=$-15399
- **US30 London prior-opposed S_1_1_3** (`us30_london_prior_opposed`): n=300 WR=61.3% avg=$81.23 net=$24370
- **NAS100 hourly ST+PMC 50/150 3r** (`nas100_st_pmc_3r`): n=477 WR=41.9% avg=$31.91 net=$15219
- **US30 hourly ST+PMC 50/150 3r** (`us30_st_pmc_3r`): n=578 WR=42.6% avg=$32.92 net=$19028
- **EURUSD hourly ST+PMC 50/150 3r** (`eurusd_st_pmc_3r`): n=865 WR=29.0% avg=$74.82 net=$64720

## Cross-book notables (positive lift)

- **5m MA vs trade = ma_opposed** — 3 book(s): eurusd_monday_or, us30_london_prior_opposed, usdjpy_asia_range (median WR lift +5.2pp, median avg lift $+249.17)
- **ATR14 quartile = atr_q2** — 3 book(s): us30_london_prior_opposed, us30_monday_or, usdjpy_asia_range (median WR lift +6.7pp, median avg lift $+91.31)
- **ATR14 quartile = atr_q3** — 1 book(s): nas100_v2b_london (median WR lift +0.6pp, median avg lift $+3.73)
- **ATR14 quartile = atr_q4** — 4 book(s): eurusd_monday_or, eurusd_st_pmc_3r, eurusd_v2b_ungated, usdjpy_asia_range (median WR lift +3.1pp, median avg lift $+73.30)
- **Day of week = Friday** — 5 book(s): eurusd_monday_or, eurusd_st_pmc_3r, nas100_st_pmc_3r, us30_monday_or, us30_st_pmc_3r (median WR lift +7.5pp, median avg lift $+29.35)
- **Day of week = Monday** — 1 book(s): us30_london_prior_opposed (median WR lift +0.2pp, median avg lift $+63.80)
- **Day of week = Thursday** — 5 book(s): eurusd_monday_or, eurusd_st_pmc_3r, nas100_v2b_london, us30_st_pmc_3r, usdjpy_monday_or (median WR lift +5.5pp, median avg lift $+21.04)
- **Day of week = Tuesday** — 1 book(s): nas100_v2b_london (median WR lift +3.1pp, median avg lift $+6.98)
- **Entry hour (NY) = 1** — 1 book(s): usdjpy_monday_or (median WR lift +3.0pp, median avg lift $+199.97)
- **Entry hour (NY) = 10** — 2 book(s): eurusd_monday_or, us30_monday_or (median WR lift +2.2pp, median avg lift $+98.78)
- **Entry hour (NY) = 11** — 3 book(s): eurusd_v2b_ungated, nas100_st_pmc_3r, us30_monday_or (median WR lift +7.5pp, median avg lift $+31.06)
- **Entry hour (NY) = 12** — 2 book(s): eurusd_monday_or, us30_monday_or (median WR lift +2.2pp, median avg lift $+78.95)
- **Entry hour (NY) = 13** — 2 book(s): eurusd_monday_or, eurusd_st_pmc_3r (median WR lift +6.3pp, median avg lift $+106.94)
- **Entry hour (NY) = 14** — 1 book(s): eurusd_monday_or (median WR lift +10.1pp, median avg lift $+116.26)
- **Entry hour (NY) = 15** — 2 book(s): us30_monday_or, usdjpy_monday_or (median WR lift +2.8pp, median avg lift $+54.82)
- **Entry hour (NY) = 16** — 1 book(s): eurusd_monday_or (median WR lift +2.7pp, median avg lift $+99.04)
- **Entry hour (NY) = 18** — 1 book(s): eurusd_monday_or (median WR lift +1.7pp, median avg lift $+293.84)
- **Entry hour (NY) = 3** — 3 book(s): eurusd_monday_or, nas100_v2b_london, us30_london_prior_opposed (median WR lift +3.2pp, median avg lift $+87.24)
- **Entry hour (NY) = 4** — 3 book(s): eurusd_monday_or, usdjpy_asia_range, usdjpy_monday_or (median WR lift +7.2pp, median avg lift $+446.40)
- **Entry hour (NY) = 5** — 1 book(s): usdjpy_monday_or (median WR lift +9.0pp, median avg lift $+565.58)
- **Entry hour (NY) = 7** — 1 book(s): eurusd_monday_or (median WR lift +0.8pp, median avg lift $+45.14)
- **Entry hour (NY) = 8** — 2 book(s): eurusd_st_pmc_3r, us30_monday_or (median WR lift +2.8pp, median avg lift $+86.38)
- **Entry hour (NY) = 9** — 1 book(s): eurusd_monday_or (median WR lift +3.8pp, median avg lift $+17.55)
- **Hourly OBV vs trade = obv_opposed** — 2 book(s): eurusd_monday_or, eurusd_st_pmc_3r (median WR lift +2.8pp, median avg lift $+65.36)
- **Hourly RSI bucket = rsi_30_45** — 1 book(s): us30_london_prior_opposed (median WR lift +3.4pp, median avg lift $+89.55)
- **Hourly RSI bucket = rsi_45_55** — 2 book(s): eurusd_monday_or, usdjpy_monday_or (median WR lift +1.2pp, median avg lift $+63.32)
- **Hourly RSI bucket = rsi_55_70** — 3 book(s): eurusd_st_pmc_3r, us30_london_prior_opposed, us30_monday_or (median WR lift +2.4pp, median avg lift $+30.19)
- **Hourly RSI bucket = rsi_gt70** — 5 book(s): eurusd_monday_or, eurusd_v2b_ungated, nas100_v2b_london, usdjpy_asia_range, usdjpy_monday_or (median WR lift +2.6pp, median avg lift $+59.68)
- **Hourly RSI bucket = rsi_le30** — 2 book(s): eurusd_monday_or, eurusd_v2b_ungated (median WR lift +5.4pp, median avg lift $+19.69)
- **Hourly RSI vs trade = rsi_against_side** — 4 book(s): eurusd_monday_or, eurusd_st_pmc_3r, nas100_st_pmc_3r, us30_london_prior_opposed (median WR lift +7.3pp, median avg lift $+66.19)
- **Hourly RSI vs trade = rsi_neutral** — 2 book(s): eurusd_monday_or, usdjpy_monday_or (median WR lift +1.2pp, median avg lift $+63.32)
- **Hourly RSI vs trade = rsi_with_side** — 1 book(s): usdjpy_asia_range (median WR lift +3.2pp, median avg lift $+78.97)
- **Prior-day range half = day_aligned** — 1 book(s): eurusd_monday_or (median WR lift +9.2pp, median avg lift $+63.28)
- **Prior-month range half = month_opposed** — 2 book(s): eurusd_monday_or, us30_monday_or (median WR lift +2.4pp, median avg lift $+35.91)
- **Prior-week range half = week_opposed** — 4 book(s): eurusd_monday_or, eurusd_st_pmc_3r, us30_monday_or, usdjpy_monday_or (median WR lift +1.6pp, median avg lift $+24.02)
- **Week of month = 1** — 2 book(s): eurusd_monday_or, eurusd_st_pmc_3r (median WR lift +2.8pp, median avg lift $+70.70)
- **Week of month = 2** — 4 book(s): eurusd_st_pmc_3r, nas100_v2b_london, us30_st_pmc_3r, usdjpy_monday_or (median WR lift +2.5pp, median avg lift $+20.99)
- **Week of month = 4** — 5 book(s): eurusd_st_pmc_3r, nas100_v2b_london, us30_london_prior_opposed, us30_monday_or, usdjpy_monday_or (median WR lift +1.7pp, median avg lift $+35.71)
- **Week of month = 5** — 3 book(s): eurusd_st_pmc_3r, eurusd_v2b_ungated, nas100_v2b_london (median WR lift +2.7pp, median avg lift $+18.31)

## Per-book top positive buckets

### EURUSD Monday OR M1_S2_R2 (Phase2)
| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Hourly RSI vs trade | rsi_against_side | 106 | 43.4% | +13.3pp | 425.81 | +390.12 | 2.17 | +2.93 |
| Entry hour (NY) | 4 | 53 | 30.2% | +0.1pp | 406.89 | +371.19 | 1.51 | +0.02 |
| Entry hour (NY) | 18 | 85 | 31.8% | +1.7pp | 329.53 | +293.84 | 1.68 | +0.33 |
| 5m MA vs trade | ma_opposed | 269 | 35.3% | +5.2pp | 284.87 | +249.17 | 1.65 | +1.79 |
| Entry hour (NY) | 10 | 146 | 30.8% | +0.7pp | 185.91 | +150.22 | 1.34 | +0.19 |
| Entry hour (NY) | 14 | 219 | 40.2% | +10.1pp | 151.95 | +116.26 | 1.34 | +3.14 |
| Entry hour (NY) | 16 | 125 | 32.8% | +2.7pp | 134.73 | +99.04 | 1.26 | +0.65 |
| ATR14 quartile | atr_q4 | 717 | 33.2% | +3.1pp | 131.15 | +95.46 | 1.15 | +1.62 |
| Hourly OBV vs trade | obv_opposed | 421 | 34.0% | +3.9pp | 129.08 | +93.39 | 1.24 | +1.62 |
| Week of month | 1 | 667 | 33.1% | +3.0pp | 125.17 | +89.47 | 1.22 | +1.54 |
| Entry hour (NY) | 3 | 60 | 33.3% | +3.2pp | 124.17 | +88.47 | 1.19 | +0.54 |
| Entry hour (NY) | 12 | 222 | 34.2% | +4.1pp | 123.09 | +87.40 | 1.26 | +1.30 |

### USDJPY Monday OR M2_S3_R1 skip Aug/Sep
| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Entry hour (NY) | 5 | 66 | 40.9% | +9.0pp | 719.73 | +565.58 | 2.33 | +1.55 |
| Entry hour (NY) | 4 | 64 | 39.1% | +7.2pp | 600.55 | +446.40 | 2.19 | +1.21 |
| Hourly RSI bucket | rsi_gt70 | 149 | 41.6% | +9.7pp | 371.47 | +217.32 | 1.73 | +2.45 |
| Entry hour (NY) | 1 | 172 | 34.9% | +3.0pp | 354.12 | +199.97 | 1.65 | +0.81 |
| Week of month | 2 | 418 | 35.2% | +3.3pp | 285.25 | +131.10 | 1.53 | +1.31 |
| Entry hour (NY) | 15 | 131 | 37.4% | +5.5pp | 248.94 | +94.78 | 1.53 | +1.31 |
| Prior-week range half | week_opposed | 1343 | 34.0% | +2.1pp | 219.83 | +65.68 | 1.39 | +1.29 |
| Week of month | 4 | 430 | 34.0% | +2.1pp | 215.68 | +61.53 | 1.40 | +0.83 |
| Hourly RSI bucket | rsi_45_55 | 217 | 33.6% | +1.8pp | 210.72 | +56.57 | 1.46 | +0.53 |
| Hourly RSI vs trade | rsi_neutral | 217 | 33.6% | +1.8pp | 210.72 | +56.57 | 1.46 | +0.53 |
| Day of week | Wednesday | 466 | 33.9% | +2.0pp | 205.71 | +51.55 | 1.34 | +0.84 |
| Entry hour (NY) | 13 | 137 | 37.2% | +5.3pp | 204.61 | +50.46 | 1.40 | +1.30 |

### US30 Monday OR M3_S3_R2
| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Entry hour (NY) | 11 | 106 | 34.0% | +4.8pp | 155.66 | +127.72 | 2.11 | +1.04 |
| Entry hour (NY) | 8 | 54 | 31.5% | +2.3pp | 132.85 | +104.90 | 1.79 | +0.36 |
| Entry hour (NY) | 12 | 85 | 29.4% | +0.2pp | 98.44 | +70.50 | 1.57 | +0.05 |
| Entry hour (NY) | 10 | 149 | 32.9% | +3.7pp | 75.30 | +47.35 | 1.37 | +0.94 |
| Week of month | 4 | 255 | 30.6% | +1.4pp | 60.02 | +32.07 | 1.32 | +0.45 |
| Day of week | Friday | 125 | 48.8% | +19.6pp | 57.30 | +29.35 | 1.41 | +4.58 |
| Hourly RSI bucket | rsi_55_70 | 357 | 37.0% | +7.8pp | 54.07 | +26.12 | 1.27 | +2.83 |
| Prior-month range half | month_opposed | 637 | 32.7% | +3.5pp | 50.06 | +22.12 | 1.26 | +1.54 |
| Prior-week range half | week_opposed | 840 | 31.1% | +1.9pp | 48.97 | +21.02 | 1.26 | +0.92 |
| Entry hour (NY) | 15 | 75 | 29.3% | +0.2pp | 42.81 | +14.86 | 1.20 | +0.03 |
| ATR14 quartile | atr_q2 | 278 | 29.5% | +0.3pp | 37.89 | +9.94 | 1.25 | +0.11 |
| Hourly RSI vs trade | rsi_with_side | 862 | 30.2% | +1.0pp | 37.32 | +9.37 | 1.18 | +0.48 |

### USDJPY Asia-range London S_3_1_3 filtered
| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Hourly RSI bucket | rsi_gt70 | 47 | 57.4% | +7.0pp | 1226.35 | +1019.09 | 2.64 | +0.94 |
| Entry hour (NY) | 4 | 120 | 59.2% | +8.8pp | 734.72 | +527.47 | 2.23 | +1.80 |
| 5m MA vs trade | ma_opposed | 103 | 55.3% | +4.9pp | 678.55 | +471.30 | 2.10 | +0.95 |
| ATR14 quartile | atr_q2 | 215 | 57.7% | +7.3pp | 444.19 | +236.94 | 1.92 | +1.91 |
| ATR14 quartile | atr_q4 | 215 | 53.5% | +3.1pp | 334.92 | +127.67 | 1.32 | +0.81 |
| Hourly RSI vs trade | rsi_with_side | 431 | 53.6% | +3.2pp | 286.22 | +78.97 | 1.39 | +1.08 |
| Prior-month range half | month_opposed | 470 | 54.7% | +4.3pp | 278.84 | +71.59 | 1.43 | +1.49 |
| Week of month | 4 | 188 | 53.7% | +3.3pp | 276.21 | +68.96 | 1.46 | +0.82 |
| Week of month | 2 | 199 | 52.8% | +2.4pp | 270.88 | +63.63 | 1.43 | +0.60 |
| Prior-day range half | day_opposed | 566 | 53.0% | +2.6pp | 257.05 | +49.80 | 1.37 | +0.96 |
| Day of week | Wednesday | 170 | 50.6% | +0.2pp | 240.97 | +33.72 | 1.35 | +0.04 |
| 5m MA cross vs trade | cross_none | 827 | 50.8% | +0.4pp | 224.92 | +17.67 | 1.33 | +0.16 |

### EURUSD v2b ungated S_1_1_1
| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Hourly RSI bucket | rsi_gt70 | 125 | 47.2% | +2.4pp | -10.73 | +35.54 | 0.93 | +0.52 |
| Entry hour (NY) | 11 | 197 | 52.3% | +7.5pp | -15.21 | +31.06 | 0.89 | +2.03 |
| Hourly RSI bucket | rsi_le30 | 116 | 49.1% | +4.3pp | -19.28 | +26.99 | 0.86 | +0.91 |
| Week of month | 5 | 198 | 47.5% | +2.7pp | -27.96 | +18.31 | 0.80 | +0.72 |
| Day of week | Tuesday | 463 | 47.5% | +2.7pp | -30.16 | +16.11 | 0.78 | +1.07 |
| Entry hour (NY) | 9 | 1241 | 46.3% | +1.4pp | -32.69 | +13.58 | 0.76 | +0.82 |
| Hourly OBV vs trade | obv_aligned | 1142 | 46.4% | +1.6pp | -32.98 | +13.29 | 0.77 | +0.89 |
| 5m MA cross vs trade | cross_aligned | 104 | 48.1% | +3.3pp | -34.83 | +11.44 | 0.75 | +0.65 |
| ATR14 quartile | atr_q4 | 594 | 48.8% | +4.0pp | -36.78 | +9.49 | 0.78 | +1.76 |
| Week of month | 4 | 521 | 46.8% | +2.0pp | -37.42 | +8.85 | 0.74 | +0.84 |
| Hourly RSI bucket | rsi_45_55 | 770 | 45.6% | +0.8pp | -37.91 | +8.36 | 0.73 | +0.37 |
| Hourly RSI vs trade | rsi_neutral | 770 | 45.6% | +0.8pp | -37.91 | +8.36 | 0.73 | +0.37 |

### NAS100 v2b London ungated S_1_1_3 (index OR proxy)
| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Hourly RSI bucket | rsi_gt70 | 137 | 51.8% | +2.6pp | 5.40 | +14.91 | 1.12 | +0.59 |
| Entry hour (NY) | 3 | 1043 | 51.9% | +2.7pp | 1.05 | +10.56 | 1.02 | +1.35 |
| Week of month | 2 | 367 | 51.0% | +1.8pp | -2.09 | +7.43 | 0.97 | +0.61 |
| Day of week | Tuesday | 323 | 52.3% | +3.1pp | -2.54 | +6.98 | 0.96 | +1.03 |
| Week of month | 4 | 372 | 50.5% | +1.3pp | -2.97 | +6.55 | 0.96 | +0.47 |
| Week of month | 5 | 128 | 52.3% | +3.1pp | -4.47 | +5.05 | 0.93 | +0.69 |
| Day of week | Thursday | 319 | 53.9% | +4.7pp | -5.77 | +3.74 | 0.90 | +1.54 |
| ATR14 quartile | atr_q3 | 404 | 49.8% | +0.6pp | -5.79 | +3.73 | 0.92 | +0.20 |
| ATR14 quartile | atr_q2 | 404 | 49.8% | +0.6pp | -6.63 | +2.89 | 0.89 | +0.20 |
| 5m MA vs trade | ma_opposed | 684 | 49.4% | +0.2pp | -6.79 | +2.73 | 0.89 | +0.10 |
| 5m MA cross vs trade | cross_aligned | 77 | 49.4% | +0.2pp | -8.53 | +0.99 | 0.88 | +0.03 |
| 5m MA cross vs trade | cross_none | 1521 | 49.4% | +0.2pp | -8.64 | +0.88 | 0.87 | +0.10 |

### US30 London prior-opposed S_1_1_3
| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Week of month | 4 | 43 | 65.1% | +3.8pp | 178.21 | +96.98 | 3.45 | +0.48 |
| ATR14 quartile | atr_q2 | 75 | 68.0% | +6.7pp | 172.55 | +91.31 | 3.32 | +1.06 |
| Hourly RSI bucket | rsi_30_45 | 85 | 64.7% | +3.4pp | 170.78 | +89.55 | 2.73 | +0.56 |
| Entry hour (NY) | 3 | 104 | 74.0% | +12.7pp | 168.48 | +87.24 | 3.25 | +2.29 |
| Day of week | Monday | 52 | 61.5% | +0.2pp | 145.04 | +63.80 | 2.43 | +0.03 |
| Hourly RSI vs trade | rsi_against_side | 223 | 65.0% | +3.7pp | 122.49 | +41.26 | 2.40 | +0.86 |
| 5m MA vs trade | ma_opposed | 103 | 67.0% | +5.7pp | 115.98 | +34.74 | 2.23 | +1.02 |
| Hourly RSI bucket | rsi_55_70 | 113 | 63.7% | +2.4pp | 111.42 | +30.19 | 2.73 | +0.44 |
| Prior-day range half | day_aligned | 250 | 64.0% | +2.7pp | 102.27 | +21.04 | 2.15 | +0.64 |
| Prior-week range half | week_aligned | 245 | 62.9% | +1.5pp | 98.89 | +17.66 | 2.06 | +0.36 |
| Day of week | Thursday | 76 | 63.2% | +1.8pp | 86.56 | +5.33 | 1.82 | +0.29 |

### NAS100 hourly ST+PMC 50/150 3r
| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Entry hour (NY) | 11 | 43 | 55.8% | +13.9pp | 60.08 | +28.18 | 3.64 | +1.77 |
| Hourly RSI vs trade | rsi_against_side | 94 | 52.1% | +10.2pp | 50.97 | +19.06 | 2.93 | +1.83 |
| Day of week | Friday | 83 | 49.4% | +7.5pp | 46.96 | +15.05 | 2.78 | +1.27 |
| ATR14 quartile | atr_q4 | 119 | 47.9% | +6.0pp | 42.87 | +10.97 | 2.52 | +1.18 |
| Entry hour (NY) | 9 | 102 | 47.1% | +5.1pp | 42.33 | +10.42 | 2.54 | +0.95 |
| Hourly RSI bucket | rsi_55_70 | 158 | 46.2% | +4.3pp | 39.82 | +7.91 | 2.38 | +0.94 |
| ATR14 quartile | atr_q3 | 119 | 45.4% | +3.4pp | 39.20 | +7.30 | 2.39 | +0.68 |
| 5m MA vs trade | ma_aligned | 65 | 46.2% | +4.2pp | 38.24 | +6.33 | 2.26 | +0.65 |
| Hourly RSI bucket | rsi_30_45 | 81 | 44.4% | +2.5pp | 37.33 | +5.43 | 2.30 | +0.42 |
| Week of month | 4 | 99 | 44.4% | +2.5pp | 37.33 | +5.43 | 2.30 | +0.46 |
| Week of month | 2 | 119 | 44.5% | +2.6pp | 35.94 | +4.04 | 2.19 | +0.52 |
| Prior-week range half | week_opposed | 368 | 43.2% | +1.3pp | 34.79 | +2.88 | 2.18 | +0.37 |

### US30 hourly ST+PMC 50/150 3r
| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Day of week | Thursday | 119 | 50.4% | +7.9pp | 49.07 | +16.15 | 2.90 | +1.58 |
| Week of month | 2 | 159 | 49.1% | +6.5pp | 46.46 | +13.54 | 2.76 | +1.47 |
| Day of week | Friday | 103 | 49.5% | +7.0pp | 46.31 | +13.39 | 2.70 | +1.32 |
| 5m MA vs trade | ma_aligned | 71 | 47.9% | +5.3pp | 44.22 | +11.30 | 2.64 | +0.86 |
| Entry hour (NY) | 11 | 59 | 47.5% | +4.9pp | 43.36 | +10.44 | 2.60 | +0.72 |
| Entry hour (NY) | 9 | 112 | 47.3% | +4.8pp | 41.67 | +8.75 | 2.46 | +0.93 |
| Hourly RSI bucket | rsi_45_55 | 281 | 46.3% | +3.7pp | 40.23 | +7.31 | 2.41 | +1.03 |
| Hourly RSI vs trade | rsi_neutral | 281 | 46.3% | +3.7pp | 40.23 | +7.31 | 2.41 | +1.03 |
| Prior-day range half | day_opposed | 355 | 45.6% | +3.1pp | 38.83 | +5.91 | 2.34 | +0.92 |
| ATR14 quartile | atr_q2 | 144 | 45.1% | +2.6pp | 38.61 | +5.69 | 2.36 | +0.56 |
| ATR14 quartile | atr_q3 | 144 | 43.1% | +0.5pp | 34.54 | +1.62 | 2.18 | +0.11 |
| Prior-week range half | week_opposed | 444 | 43.2% | +0.7pp | 34.53 | +1.61 | 2.16 | +0.22 |

### EURUSD hourly ST+PMC 50/150 3r
| condition | bucket | n | WR | WR lift | avg $ | avg lift | PF | z_WR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Entry hour (NY) | 13 | 95 | 36.8% | +7.8pp | 234.28 | +159.46 | 1.74 | +1.60 |
| Day of week | Thursday | 175 | 35.4% | +6.4pp | 200.10 | +125.28 | 1.60 | +1.70 |
| Day of week | Friday | 168 | 35.1% | +6.1pp | 197.72 | +122.90 | 1.60 | +1.59 |
| Hourly RSI vs trade | rsi_against_side | 245 | 33.5% | +4.5pp | 165.93 | +91.11 | 1.49 | +1.36 |
| Entry hour (NY) | 8 | 62 | 32.3% | +3.2pp | 142.69 | +67.87 | 1.42 | +0.54 |
| Week of month | 1 | 219 | 31.5% | +2.5pp | 126.75 | +51.93 | 1.37 | +0.73 |
| ATR14 quartile | atr_q4 | 216 | 31.5% | +2.5pp | 125.96 | +51.14 | 1.36 | +0.71 |
| Hourly RSI bucket | rsi_55_70 | 203 | 31.0% | +2.0pp | 112.31 | +37.49 | 1.32 | +0.57 |
| Hourly OBV vs trade | obv_opposed | 600 | 30.8% | +1.8pp | 112.15 | +37.33 | 1.32 | +0.75 |
| Week of month | 4 | 179 | 30.7% | +1.7pp | 110.53 | +35.71 | 1.32 | +0.46 |
| Week of month | 5 | 67 | 31.3% | +2.3pp | 106.83 | +32.01 | 1.29 | +0.40 |
| Week of month | 2 | 191 | 30.4% | +1.3pp | 103.25 | +28.43 | 1.29 | +0.37 |

## Caveats

- Multiple comparisons: treat single-bucket spikes as hypotheses, not gates.
- Live demo tapes are too short; this uses research/broker-like fills.
- NAS100 live v2b ungated proxied by London ungated research tape.
- SPX500 omitted (no long 1m research series in `fx/`).
