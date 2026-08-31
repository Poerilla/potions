# NQ first-hour 1h follow / fade HA (p99 / p95)

Diagnostic only — not a promotion gate. HA here means **condition lift**, same mill as midnight-open / futures HP.

Universe: NQ RTH **first hour only** (09:30–10:30 ET), one 1h candle per session. Entry at 10:30 close; remaining session walked on 5m. All first hours **and** causal expanding **p99** first-hour range (fallback **p95** if too rare: hi days too rare (5.9% < 8%)). Charts: 15m RTH, gold = first hour, sleeve = **follow 3R p95** (154 charts).

Follow = candle direction from close, SL at open. Fade = opposite from close, SL = reflection of open across close (same body risk).
1R target = 1× body; 3R = 3× body. Non-overlapping. Flatten 16:00. $1.50 fee, $20/pt.

Prior-opposed overlay: NQ v2b resting-limit `nq_prior_opposed_rl` (432 campaigns). **during_po** = bar inside a live PO campaign. **after_po** = same session after that campaign's exit (outcome is then causal). Implied ST = opposite of PO side.

Fair WR with no edge ≈ **25% at 3R**, ≈ **50% at 1R**.

## Core books

| Book | n | WR | avg | net | stress | N/S | PF |
|---|---:|---:|---:|---:|---:|---:|---:|
| follow 3R all first-hour | 3968 | 38.2% | $61 | $243008 | $26076 | 9.32 | 1.19 |
| fade 3R all first-hour | 3968 | 32.7% | $-48 | $-191912 | $208782 | -0.92 | 0.87 |
| follow 1R all first-hour | 3968 | 49.9% | $44 | $176438 | $23168 | 7.62 | 1.16 |
| fade 1R all first-hour | 3968 | 43.5% | $-56 | $-222012 | $240214 | -0.92 | 0.83 |
| follow 3R p99 first-hour | 238 | 43.7% | $31 | $7438 | $37675 | 0.20 | 1.03 |
| fade 3R p99 first-hour | 238 | 37.4% | $-198 | $-47222 | $76062 | -0.62 | 0.81 |
| follow 1R p99 first-hour | 238 | 48.3% | $17 | $3933 | $34895 | 0.11 | 1.02 |
| fade 1R p99 first-hour | 238 | 49.6% | $-24 | $-5647 | $45346 | -0.12 | 0.97 |
| follow 3R p95 first-hour | 879 | 43.8% | $99 | $86796 | $33968 | 2.56 | 1.14 |
| fade 3R p95 first-hour | 879 | 36.4% | $-56 | $-49368 | $69660 | -0.71 | 0.93 |
| follow 1R p95 first-hour | 879 | 51.8% | $69 | $60342 | $27722 | 2.18 | 1.11 |
| fade 1R p95 first-hour | 879 | 44.8% | $-80 | $-70758 | $97072 | -0.73 | 0.89 |

## HP regime sleeves (filtered signals, own non-overlap)

during fade-ST = during PO, large/first-hour candle *with implied ST*, **fade** it (counter-trend with PO).
after follow-ST = after PO exit, candle *with implied ST*, **follow** it (continuation).
after-loss follow-ST = same continuation, only when PO already lost (trend punched through the fade).
after-win fade-ST = after a PO win, fade remaining ST-direction candles (do not continue the old trend).

| Sleeve | n | WR | avg | net | stress | N/S | PF |
|---|---:|---:|---:|---:|---:|---:|---:|
| during fade-ST 3R (p95) | 4 | 25.0% | $-505 | $-2021 | $4670 | -0.43 | 0.57 |
| during fade-ST 1R (p95) | 4 | 75.0% | $898 | $3594 | $1196 | 3.00 | 4.00 |
| during fade-ST 3R (all) | 26 | 23.1% | $236 | $6126 | $3694 | 1.66 | 1.79 |
| during fade-ST 1R (all) | 26 | 42.3% | $250 | $6491 | $2064 | 3.14 | 3.05 |
| after follow-ST 3R (p95) | 3 | 33.3% | $-972 | $-2914 | $5133 | -0.57 | 0.43 |
| after follow-ST 1R (p95) | 3 | 33.3% | $-1356 | $-4070 | $5133 | -0.79 | 0.21 |
| after-loss follow-ST 1R (all) | 20 | 50.0% | $-20 | $-395 | $5449 | -0.07 | 0.96 |
| after-win fade-ST 1R (p95) | 0 | — | — | — | — | — | — |

## vs current NQ prior-opposed HP buckets

Same condition=bucket that we already use on the PO book. Lift is vs **that candle book’s** baseline, not vs PO.

| book | condition=bucket | n | WR | avg lift vs book | PO n | PO WR | PO avg lift |
|---|---|---:|---:|---:|---:|---:|---:|
| fade_1r_all | Hourly RSI vs trade=rsi_against_side | 2047 | 44.7% | $7 | 248 | 71% | $1084 |
| fade_1r_all | Opening 15m range vs ATR=or_norm | 1248 | 44.6% | $-18 | 129 | 71% | $1430 |
| fade_1r_all | Week of month=2 | 922 | 44.4% | $28 | 93 | 73% | $1247 |
| fade_1r_all | ST-event age=st_age_30_90m | 3968 | 43.5% | $0 | 118 | 70% | $1179 |
| fade_1r_all | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| fade_1r_all | NQ-ES dispersion=disp_mid | 1299 | 43.3% | $-25 | 138 | 69% | $429 |
| fade_1r_all | Day of week=Friday | 788 | 41.6% | $-25 | 85 | 68% | $1623 |
| fade_1r_all | 5m MA vs trade=ma_aligned | 615 | 37.2% | $8 | 274 | 66% | $-279 |
| fade_3r_all | Hourly RSI vs trade=rsi_against_side | 2047 | 34.5% | $7 | 248 | 71% | $1084 |
| fade_3r_all | Opening 15m range vs ATR=or_norm | 1248 | 33.8% | $-19 | 129 | 71% | $1430 |
| fade_3r_all | Week of month=2 | 922 | 32.9% | $38 | 93 | 73% | $1247 |
| fade_3r_all | ST-event age=st_age_30_90m | 3968 | 32.7% | $0 | 118 | 70% | $1179 |
| fade_3r_all | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| fade_3r_all | NQ-ES dispersion=disp_mid | 1299 | 31.9% | $-10 | 138 | 69% | $429 |
| fade_3r_all | Day of week=Friday | 788 | 31.2% | $-51 | 85 | 68% | $1623 |
| fade_3r_all | 5m MA vs trade=ma_aligned | 615 | 22.9% | $22 | 274 | 66% | $-279 |
| fade_3r_hi | Opening 15m range vs ATR=or_norm | 27 | 40.7% | $-188 | 129 | 71% | $1430 |
| fade_3r_hi | Hourly RSI vs trade=rsi_against_side | 126 | 40.5% | $149 | 248 | 71% | $1084 |
| fade_3r_hi | Week of month=2 | 52 | 40.4% | $484 | 93 | 73% | $1247 |
| fade_3r_hi | NQ-ES dispersion=disp_mid | 61 | 37.7% | $180 | 138 | 69% | $429 |
| fade_3r_hi | ST-event age=st_age_30_90m | 238 | 37.4% | $0 | 118 | 70% | $1179 |
| fade_3r_hi | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| fade_3r_hi | Day of week=Friday | 56 | 28.6% | $-280 | 85 | 68% | $1623 |
| fade_3r_hi | 5m MA vs trade=ma_aligned | 26 | 26.9% | $517 | 274 | 66% | $-279 |
| fade_3r_lo | Hourly RSI vs trade=rsi_against_side | 478 | 39.1% | $40 | 248 | 71% | $1084 |
| fade_3r_lo | NQ-ES dispersion=disp_mid | 249 | 36.5% | $46 | 138 | 69% | $429 |
| fade_3r_lo | ST-event age=st_age_30_90m | 879 | 36.4% | $0 | 118 | 70% | $1179 |
| fade_3r_lo | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| fade_3r_lo | Day of week=Friday | 178 | 36.0% | $-105 | 85 | 68% | $1623 |
| fade_3r_lo | Opening 15m range vs ATR=or_norm | 204 | 35.3% | $-162 | 129 | 71% | $1430 |
| fade_3r_lo | Week of month=2 | 195 | 33.8% | $-26 | 93 | 73% | $1247 |
| fade_3r_lo | 5m MA vs trade=ma_aligned | 85 | 24.7% | $7 | 274 | 66% | $-279 |
| follow_1r_all | 5m MA vs trade=ma_aligned | 3353 | 51.4% | $5 | 274 | 66% | $-279 |
| follow_1r_all | Day of week=Friday | 788 | 51.0% | $22 | 85 | 68% | $1623 |
| follow_1r_all | NQ-ES dispersion=disp_mid | 1299 | 49.9% | $26 | 138 | 69% | $429 |
| follow_1r_all | ST-event age=st_age_30_90m | 3968 | 49.9% | $0 | 118 | 70% | $1179 |
| follow_1r_all | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| follow_1r_all | Week of month=2 | 922 | 49.6% | $-27 | 93 | 73% | $1247 |
| follow_1r_all | Opening 15m range vs ATR=or_norm | 1248 | 49.3% | $17 | 129 | 71% | $1430 |
| follow_1r_all | Hourly RSI vs trade=rsi_against_side | 874 | 47.7% | $-2 | 248 | 71% | $1084 |
| follow_3r_all | Day of week=Friday | 788 | 41.6% | $64 | 85 | 68% | $1623 |
| follow_3r_all | 5m MA vs trade=ma_aligned | 3353 | 40.4% | $10 | 274 | 66% | $-279 |
| follow_3r_all | ST-event age=st_age_30_90m | 3968 | 38.2% | $0 | 118 | 70% | $1179 |
| follow_3r_all | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| follow_3r_all | Opening 15m range vs ATR=or_norm | 1248 | 37.7% | $35 | 129 | 71% | $1430 |
| follow_3r_all | NQ-ES dispersion=disp_mid | 1299 | 37.0% | $21 | 138 | 69% | $429 |
| follow_3r_all | Week of month=2 | 922 | 36.8% | $-34 | 93 | 73% | $1247 |
| follow_3r_all | Hourly RSI vs trade=rsi_against_side | 874 | 31.2% | $-37 | 248 | 71% | $1084 |
| follow_3r_hi | Opening 15m range vs ATR=or_norm | 27 | 55.6% | $454 | 129 | 71% | $1430 |
| follow_3r_hi | Day of week=Friday | 56 | 53.6% | $136 | 85 | 68% | $1623 |
| follow_3r_hi | 5m MA vs trade=ma_aligned | 212 | 46.7% | $58 | 274 | 66% | $-279 |
| follow_3r_hi | NQ-ES dispersion=disp_mid | 61 | 44.3% | $4 | 138 | 69% | $429 |
| follow_3r_hi | ST-event age=st_age_30_90m | 238 | 43.7% | $0 | 118 | 70% | $1179 |
| follow_3r_hi | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| follow_3r_hi | Hourly RSI vs trade=rsi_against_side | 43 | 37.2% | $-148 | 248 | 71% | $1084 |
| follow_3r_hi | Week of month=2 | 52 | 32.7% | $-632 | 93 | 73% | $1247 |
| follow_3r_lo | Day of week=Friday | 178 | 46.1% | $62 | 85 | 68% | $1623 |
| follow_3r_lo | 5m MA vs trade=ma_aligned | 794 | 45.7% | $18 | 274 | 66% | $-279 |
| follow_3r_lo | NQ-ES dispersion=disp_mid | 249 | 44.2% | $10 | 138 | 69% | $429 |
| follow_3r_lo | Opening 15m range vs ATR=or_norm | 204 | 44.1% | $134 | 129 | 71% | $1430 |
| follow_3r_lo | ST-event age=st_age_30_90m | 879 | 43.8% | $0 | 118 | 70% | $1179 |
| follow_3r_lo | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| follow_3r_lo | Week of month=2 | 195 | 42.6% | $47 | 93 | 73% | $1247 |
| follow_3r_lo | Hourly RSI vs trade=rsi_against_side | 172 | 34.9% | $-94 | 248 | 71% | $1084 |

## Dual-lift notables (per book)

### follow_3r_all

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| First-hour body conviction=strong | 1125 | +14.4 | $+72 | 8.75 | 6.11 |
| Large-candle vs PO side=candle_with_po | 244 | +11.0 | $+273 | 3.43 | 4.50 |
| Trade side vs PO side=trade_with_po | 244 | +11.0 | $+273 | 3.43 | 4.50 |
| PO regime=during_counter_with_po | 227 | +11.2 | $+246 | 3.37 | 3.39 |
| First-hour range size=fh_p95 | 641 | +5.7 | $+63 | 2.74 | 2.69 |
| Hourly RSI bucket=rsi_gt70 | 401 | +7.0 | $+11 | 2.73 | 2.62 |
| Hourly RSI vs trade=rsi_with_side | 2047 | +3.6 | $+16 | 2.71 | 9.21 |
| First-hour range size=fh_p90 | 616 | +5.2 | $+79 | 2.45 | 5.95 |
| PO v2b session state=during_po | 253 | +7.3 | $+170 | 2.31 | 2.57 |
| Prior-day range half=day_opposed | 2478 | +2.7 | $+7 | 2.17 | 5.93 |
| Prior-week range half=week_opposed | 2248 | +2.7 | $+17 | 2.14 | 6.27 |
| Opening 15m direction vs trade=or_aligned | 2803 | +2.4 | $+18 | 2.02 | 10.97 |

### fade_3r_all

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| First-hour close location=lower | 1246 | +3.8 | $+12 | 2.50 | -0.59 |
| Overnight range third=on_lower | 1385 | +3.6 | $+22 | 2.46 | -0.61 |
| First-hour body conviction=mid | 1486 | +2.8 | $+32 | 1.93 | -0.31 |
| ATR14 quartile=atr_q1 | 992 | +3.0 | $+51 | 1.79 | 0.28 |
| NQ-ES dispersion=disp_low | 1371 | +2.5 | $+34 | 1.71 | -0.34 |
| First-hour range size=fh_p95 | 641 | +3.3 | $+45 | 1.67 | -0.07 |
| Week of month=5 | 317 | +4.5 | $+84 | 1.65 | 0.75 |
| Opening 15m range vs ATR=or_wide | 1453 | +2.0 | $+27 | 1.42 | -0.36 |
| Post-holiday session=post_holiday | 145 | +4.5 | $+103 | 1.14 | 0.40 |
| Day of week=Tuesday | 801 | +1.4 | $+37 | 0.75 | -0.15 |
| Opening 15m volume percentile=vol_high | 1468 | +1.1 | $+40 | 0.75 | -0.16 |
| Cross-index direction agreement=mixed | 867 | +1.2 | $+24 | 0.68 | -0.45 |

### follow_1r_all

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| First-hour body conviction=strong | 1125 | +6.1 | $+85 | 3.63 | 6.65 |
| Large-candle vs PO side=candle_with_po | 244 | +7.5 | $+189 | 2.28 | 3.88 |
| Trade side vs PO side=trade_with_po | 244 | +7.5 | $+189 | 2.28 | 3.88 |
| PO regime=during_counter_with_po | 227 | +7.4 | $+181 | 2.17 | 3.30 |
| Prior RTH range percentile=prior_range_norm | 1229 | +2.6 | $+42 | 1.60 | 5.97 |
| Month=4 | 309 | +4.5 | $+138 | 1.52 | 4.06 |
| First-hour range size=fh_p95 | 641 | +3.2 | $+44 | 1.49 | 2.08 |
| First-hour range size=fh_p90 | 616 | +3.2 | $+65 | 1.48 | 4.79 |
| PO v2b session state=during_po | 253 | +4.3 | $+127 | 1.32 | 2.85 |
| Opening 15m volume percentile=vol_mid | 1237 | +2.0 | $+54 | 1.24 | 10.73 |
| PO v2b session state=after_po | 40 | +7.6 | $+142 | 0.96 | 1.85 |
| ATR14 quartile=atr_q4 | 992 | +1.2 | $+41 | 0.70 | 5.11 |

### fade_1r_all

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| First-hour body conviction=mid | 1486 | +4.5 | $+45 | 3.00 | -0.39 |
| ATR14 quartile=atr_q1 | 992 | +3.3 | $+52 | 1.85 | -0.41 |
| First-hour range size=fh_p99 | 238 | +6.1 | $+32 | 1.83 | -0.12 |
| Week of month=5 | 317 | +4.7 | $+78 | 1.64 | 0.72 |
| Opening 15m volume percentile=vol_high | 1468 | +2.0 | $+41 | 1.31 | -0.38 |
| Post-holiday session=post_holiday | 145 | +4.1 | $+100 | 0.97 | 0.43 |
| Month=3 | 329 | +2.7 | $+79 | 0.94 | 0.71 |
| Opening 15m range vs ATR=or_wide | 1453 | +1.3 | $+26 | 0.84 | -0.70 |
| Overnight compression=on_comp | 1294 | +1.0 | $+21 | 0.62 | -0.89 |
| Hourly RSI bucket=rsi_30_45 | 930 | +1.1 | $+30 | 0.61 | -0.56 |
| First-hour range size=fh_lt_p80 | 1704 | +0.7 | $+40 | 0.46 | -0.95 |
| Week of month=2 | 922 | +0.8 | $+28 | 0.46 | -0.80 |

### follow_3r_hi

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| Prior RTH range percentile=prior_range_norm | 40 | +21.3 | $+552 | 2.51 | 3.45 |
| Opening 15m volume percentile=vol_mid | 49 | +15.5 | $+455 | 1.99 | 2.39 |
| First-hour body conviction=strong | 102 | +10.2 | $+123 | 1.74 | 0.64 |
| Overnight compression=on_norm | 48 | +12.6 | $+410 | 1.60 | 1.84 |
| ATR causal rolling percentile=atr_p50_75 | 56 | +11.7 | $+188 | 1.58 | 0.69 |
| Day of week=Friday | 56 | +9.9 | $+136 | 1.34 | 0.38 |
| NQ-ES dispersion=disp_low | 52 | +8.2 | $+389 | 1.08 | 1.47 |
| Week of month=1 | 79 | +6.9 | $+369 | 1.08 | 2.36 |
| First-hour close location=lower | 107 | +5.8 | $+18 | 1.01 | 0.17 |
| OR15 vs first hour=or15_agree | 177 | +4.9 | $+97 | 0.99 | 0.78 |
| Opening 15m direction vs trade=or_aligned | 178 | +4.6 | $+85 | 0.94 | 0.71 |
| RTH VWAP side=below_rth_vwap | 122 | +3.8 | $+78 | 0.70 | 0.41 |

### fade_3r_hi

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| Cross-index direction agreement=mixed | 43 | +13.8 | $+743 | 1.72 | 2.19 |
| First-hour body conviction=strong | 102 | +7.7 | $+75 | 1.35 | -0.33 |
| Month=2 | 42 | +10.2 | $+339 | 1.26 | 0.30 |
| Day of week=Tuesday | 45 | +9.3 | $+685 | 1.18 | 2.24 |
| Prior-week range half=week_aligned | 143 | +3.9 | $+250 | 0.75 | 0.35 |
| First-hour close location=lower | 107 | +3.7 | $+203 | 0.66 | 0.02 |
| Day of week=Wednesday | 40 | +5.1 | $+380 | 0.62 | 0.47 |
| Hourly RSI vs trade=rsi_against_side | 126 | +3.1 | $+149 | 0.58 | -0.14 |
| Prior RTH close location=prior_close_high_third | 77 | +2.9 | $+270 | 0.45 | 0.31 |
| Week of month=2 | 52 | +3.0 | $+484 | 0.40 | 1.20 |
| Opening 15m volume percentile=vol_high | 160 | +2.0 | $+117 | 0.40 | -0.35 |
| ATR14 quartile=atr_q1 | 60 | +2.6 | $+154 | 0.37 | -0.30 |

### follow_3r_lo

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| First-hour body conviction=strong | 364 | +12.0 | $+120 | 3.87 | 2.90 |
| Large-candle vs PO side=candle_with_po | 86 | +12.0 | $+148 | 2.14 | 0.98 |
| Trade side vs PO side=trade_with_po | 86 | +12.0 | $+148 | 2.14 | 0.98 |
| PO regime=during_counter_with_po | 83 | +11.6 | $+153 | 2.04 | 0.97 |
| Prior RTH range percentile=prior_range_norm | 216 | +7.6 | $+111 | 2.01 | 2.08 |
| Opening 15m range vs ATR=or_narrow | 68 | +12.1 | $+267 | 1.93 | 3.16 |
| Opening 15m volume percentile=vol_mid | 232 | +6.6 | $+143 | 1.81 | 3.13 |
| PO v2b session state=during_po | 87 | +9.1 | $+73 | 1.63 | 0.65 |
| Month=6 | 53 | +10.9 | $+158 | 1.56 | 1.88 |
| Overnight compression=on_norm | 257 | +5.2 | $+267 | 1.49 | 4.74 |
| Hourly RSI vs trade=rsi_with_side | 478 | +3.7 | $+55 | 1.31 | 3.49 |
| Week of month=1 | 248 | +4.6 | $+95 | 1.29 | 2.45 |

### fade_3r_lo

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| Month=9 | 69 | +10.0 | $+368 | 1.66 | 3.31 |
| ATR14 quartile=atr_q1 | 220 | +5.4 | $+52 | 1.49 | -0.13 |
| Month=11 | 69 | +8.5 | $+421 | 1.42 | 1.99 |
| Prior RTH range percentile=prior_range_comp | 199 | +5.3 | $+58 | 1.40 | 0.01 |
| First-hour close location=lower | 366 | +3.8 | $+52 | 1.26 | -0.03 |
| Hourly RSI vs trade=rsi_against_side | 478 | +2.7 | $+40 | 0.99 | -0.19 |
| Opening 15m volume percentile=vol_high | 515 | +2.0 | $+83 | 0.76 | 0.29 |
| Hourly RSI bucket=rsi_30_45 | 283 | +2.5 | $+149 | 0.75 | 0.67 |
| Week of month=5 | 66 | +4.5 | $+296 | 0.73 | 2.83 |
| Overnight range third=on_lower | 424 | +2.0 | $+35 | 0.72 | -0.18 |
| Day of week=Tuesday | 176 | +2.8 | $+179 | 0.70 | 0.62 |
| RTH VWAP side=below_rth_vwap | 441 | +1.9 | $+22 | 0.68 | -0.27 |

## Notes

- First-hour-native conditions: range size (p99/p95/p90/p80), body conviction, close third, vs prior day, OR15 agree/oppose, gap vs first-hour direction.
- After-PO sleeves are expected to be thin — most prior-opposed campaigns are still live at 10:30.
- Chart index: [`charts/INDEX.md`](charts/INDEX.md).

## Stance

Curious diagnostic only. 1R fade WR 44% vs follow 50% (fair ~50%); 3R fade N/S -0.92 vs follow 9.32 (fair WR ~25%); after-PO-loss continuation 1R n=20 WR=50% N/S=-0.07 Do not promote from this mill alone.

Hub: `/home/tester/hsm/potions/live/state/nq_1h_first_hour_ha_p99`

