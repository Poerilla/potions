# NQ first-hour 1h follow / fade HA (high-probability conditions)

Diagnostic only — not a promotion gate. HA here means **condition lift**, same mill as midnight-open / futures HP.

Universe: NQ RTH **first hour only** (09:30–10:30 ET), one 1h candle per session. Entry at 10:30 close; remaining session walked on 5m. All first hours **and** causal expanding p90 first-hour range sleeves. Charts: 15m RTH, gold = first hour, sleeve = **follow 3R** (151 charts).

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
| follow 3R p90 first-hour | 1495 | 43.6% | $116 | $173118 | $26076 | 6.64 | 1.20 |
| fade 3R p90 first-hour | 1495 | 35.1% | $-77 | $-115762 | $133281 | -0.87 | 0.89 |
| follow 1R p90 first-hour | 1495 | 52.3% | $86 | $127858 | $20907 | 6.12 | 1.17 |
| fade 1R p90 first-hour | 1495 | 43.7% | $-99 | $-147392 | $166718 | -0.88 | 0.84 |

## HP regime sleeves (filtered signals, own non-overlap)

during fade-ST = during PO, large/first-hour candle *with implied ST*, **fade** it (counter-trend with PO).
after follow-ST = after PO exit, candle *with implied ST*, **follow** it (continuation).
after-loss follow-ST = same continuation, only when PO already lost (trend punched through the fade).
after-win fade-ST = after a PO win, fade remaining ST-direction candles (do not continue the old trend).

| Sleeve | n | WR | avg | net | stress | N/S | PF |
|---|---:|---:|---:|---:|---:|---:|---:|
| during fade-ST 3R (p90) | 8 | 37.5% | $292 | $2333 | $4670 | 0.50 | 1.47 |
| during fade-ST 1R (p90) | 8 | 75.0% | $682 | $5458 | $1196 | 4.56 | 5.50 |
| during fade-ST 3R (all) | 26 | 23.1% | $236 | $6126 | $3694 | 1.66 | 1.79 |
| during fade-ST 1R (all) | 26 | 42.3% | $250 | $6491 | $2064 | 3.14 | 3.05 |
| after follow-ST 3R (p90) | 9 | 44.4% | $202 | $1816 | $5534 | 0.33 | 1.26 |
| after follow-ST 1R (p90) | 9 | 44.4% | $-235 | $-2114 | $5534 | -0.38 | 0.70 |
| after-loss follow-ST 1R (all) | 20 | 50.0% | $-20 | $-395 | $5449 | -0.07 | 0.96 |
| after-win fade-ST 1R (p90) | 1 | 0.0% | $-906 | $-906 | $0 | 0.00 | 0.00 |

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
| fade_3r_p90 | Hourly RSI vs trade=rsi_against_side | 806 | 36.4% | $18 | 248 | 71% | $1084 |
| fade_3r_p90 | Week of month=2 | 331 | 35.3% | $88 | 93 | 73% | $1247 |
| fade_3r_p90 | ST-event age=st_age_30_90m | 1495 | 35.1% | $0 | 118 | 70% | $1179 |
| fade_3r_p90 | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| fade_3r_p90 | NQ-ES dispersion=disp_mid | 446 | 33.2% | $-56 | 138 | 69% | $429 |
| fade_3r_p90 | Day of week=Friday | 306 | 32.4% | $-92 | 85 | 68% | $1623 |
| fade_3r_p90 | Opening 15m range vs ATR=or_norm | 399 | 32.3% | $-111 | 129 | 71% | $1430 |
| fade_3r_p90 | 5m MA vs trade=ma_aligned | 161 | 23.6% | $36 | 274 | 66% | $-279 |
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
| follow_3r_p90 | Opening 15m range vs ATR=or_norm | 399 | 46.9% | $100 | 129 | 71% | $1430 |
| follow_3r_p90 | Day of week=Friday | 306 | 46.7% | $75 | 85 | 68% | $1623 |
| follow_3r_p90 | 5m MA vs trade=ma_aligned | 1334 | 45.7% | $17 | 274 | 66% | $-279 |
| follow_3r_p90 | NQ-ES dispersion=disp_mid | 446 | 45.3% | $66 | 138 | 69% | $429 |
| follow_3r_p90 | ST-event age=st_age_30_90m | 1495 | 43.6% | $0 | 118 | 70% | $1179 |
| follow_3r_p90 | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| follow_3r_p90 | Week of month=2 | 331 | 42.0% | $-45 | 93 | 73% | $1247 |
| follow_3r_p90 | Hourly RSI vs trade=rsi_against_side | 287 | 35.9% | $-112 | 248 | 71% | $1084 |

## Dual-lift notables (per book)

### follow_3r_all

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| First-hour body conviction=strong | 1125 | +14.4 | $+72 | 8.75 | 6.11 |
| First-hour range size=fh_p90 | 1495 | +5.4 | $+55 | 3.68 | 6.64 |
| Large-candle vs PO side=candle_with_po | 244 | +11.0 | $+273 | 3.43 | 4.50 |
| Trade side vs PO side=trade_with_po | 244 | +11.0 | $+273 | 3.43 | 4.50 |
| PO regime=during_counter_with_po | 227 | +11.2 | $+246 | 3.37 | 3.39 |
| Hourly RSI bucket=rsi_gt70 | 401 | +7.0 | $+11 | 2.73 | 2.62 |
| Hourly RSI vs trade=rsi_with_side | 2047 | +3.6 | $+16 | 2.71 | 9.21 |
| PO v2b session state=during_po | 253 | +7.3 | $+170 | 2.31 | 2.57 |
| Prior-day range half=day_opposed | 2478 | +2.7 | $+7 | 2.17 | 5.93 |
| Prior-week range half=week_opposed | 2248 | +2.7 | $+17 | 2.14 | 6.27 |
| Opening 15m direction vs trade=or_aligned | 2803 | +2.4 | $+18 | 2.02 | 10.97 |
| OR15 vs first hour=or15_agree | 2790 | +2.4 | $+19 | 1.99 | 11.02 |

### fade_3r_all

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| First-hour close location=lower | 1246 | +3.8 | $+12 | 2.50 | -0.59 |
| Overnight range third=on_lower | 1385 | +3.6 | $+22 | 2.46 | -0.61 |
| First-hour body conviction=mid | 1486 | +2.8 | $+32 | 1.93 | -0.31 |
| ATR14 quartile=atr_q1 | 992 | +3.0 | $+51 | 1.79 | 0.28 |
| NQ-ES dispersion=disp_low | 1371 | +2.5 | $+34 | 1.71 | -0.34 |
| Week of month=5 | 317 | +4.5 | $+84 | 1.65 | 0.75 |
| Opening 15m range vs ATR=or_wide | 1453 | +2.0 | $+27 | 1.42 | -0.36 |
| Post-holiday session=post_holiday | 145 | +4.5 | $+103 | 1.14 | 0.40 |
| Day of week=Tuesday | 801 | +1.4 | $+37 | 0.75 | -0.15 |
| Opening 15m volume percentile=vol_high | 1468 | +1.1 | $+40 | 0.75 | -0.16 |
| Cross-index direction agreement=mixed | 867 | +1.2 | $+24 | 0.68 | -0.45 |
| Hourly RSI bucket=rsi_30_45 | 930 | +1.2 | $+39 | 0.68 | -0.13 |

### follow_1r_all

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| First-hour body conviction=strong | 1125 | +6.1 | $+85 | 3.63 | 6.65 |
| Large-candle vs PO side=candle_with_po | 244 | +7.5 | $+189 | 2.28 | 3.88 |
| Trade side vs PO side=trade_with_po | 244 | +7.5 | $+189 | 2.28 | 3.88 |
| PO regime=during_counter_with_po | 227 | +7.4 | $+181 | 2.17 | 3.30 |
| First-hour range size=fh_p90 | 1495 | +2.4 | $+41 | 1.60 | 6.12 |
| Prior RTH range percentile=prior_range_norm | 1229 | +2.6 | $+42 | 1.60 | 5.97 |
| Month=4 | 309 | +4.5 | $+138 | 1.52 | 4.06 |
| PO v2b session state=during_po | 253 | +4.3 | $+127 | 1.32 | 2.85 |
| Opening 15m volume percentile=vol_mid | 1237 | +2.0 | $+54 | 1.24 | 10.73 |
| PO v2b session state=after_po | 40 | +7.6 | $+142 | 0.96 | 1.85 |
| ATR14 quartile=atr_q4 | 992 | +1.2 | $+41 | 0.70 | 5.11 |
| First-hour close location=lower | 1246 | +1.1 | $+31 | 0.67 | 4.61 |

### fade_1r_all

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| First-hour body conviction=mid | 1486 | +4.5 | $+45 | 3.00 | -0.39 |
| ATR14 quartile=atr_q1 | 992 | +3.3 | $+52 | 1.85 | -0.41 |
| Week of month=5 | 317 | +4.7 | $+78 | 1.64 | 0.72 |
| Opening 15m volume percentile=vol_high | 1468 | +2.0 | $+41 | 1.31 | -0.38 |
| Post-holiday session=post_holiday | 145 | +4.1 | $+100 | 0.97 | 0.43 |
| Month=3 | 329 | +2.7 | $+79 | 0.94 | 0.71 |
| Opening 15m range vs ATR=or_wide | 1453 | +1.3 | $+26 | 0.84 | -0.70 |
| Overnight compression=on_comp | 1294 | +1.0 | $+21 | 0.62 | -0.89 |
| Hourly RSI bucket=rsi_30_45 | 930 | +1.1 | $+30 | 0.61 | -0.56 |
| First-hour range size=fh_lt_p80 | 1704 | +0.7 | $+40 | 0.46 | -0.95 |
| Week of month=2 | 922 | +0.8 | $+28 | 0.46 | -0.80 |
| Month=2 | 319 | +1.3 | $+68 | 0.45 | 0.23 |

### follow_3r_p90

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| First-hour body conviction=strong | 580 | +12.4 | $+99 | 5.12 | 4.47 |
| Large-candle vs PO side=candle_with_po | 139 | +12.5 | $+321 | 2.84 | 4.15 |
| Trade side vs PO side=trade_with_po | 139 | +12.5 | $+321 | 2.84 | 4.15 |
| PO regime=during_counter_with_po | 132 | +12.4 | $+296 | 2.76 | 3.32 |
| Opening 15m volume percentile=vol_mid | 429 | +6.0 | $+117 | 2.22 | 6.50 |
| PO v2b session state=during_po | 140 | +9.2 | $+216 | 2.11 | 2.51 |
| Hourly RSI vs trade=rsi_with_side | 806 | +4.2 | $+36 | 1.92 | 6.54 |
| First-hour vs prior day=above_pdh | 120 | +8.1 | $+10 | 1.71 | 1.45 |
| OR15 vs first hour=or15_agree | 1075 | +3.3 | $+53 | 1.65 | 6.67 |
| Prior RTH range percentile=prior_range_norm | 390 | +4.6 | $+58 | 1.63 | 2.56 |
| Opening 15m direction vs trade=or_aligned | 1076 | +3.2 | $+51 | 1.63 | 6.60 |
| Month=4 | 137 | +6.0 | $+380 | 1.36 | 5.39 |

### fade_3r_p90

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| First-hour close location=lower | 560 | +4.9 | $+55 | 2.09 | -0.22 |
| ATR14 quartile=atr_q1 | 374 | +5.3 | $+77 | 1.93 | -0.01 |
| Month=11 | 109 | +9.0 | $+320 | 1.90 | 2.09 |
| Overnight range third=on_lower | 641 | +3.3 | $+35 | 1.48 | -0.49 |
| First-hour body conviction=mid | 574 | +2.9 | $+87 | 1.25 | 0.13 |
| Overnight compression=on_comp | 270 | +3.5 | $+58 | 1.10 | -0.24 |
| Post-holiday session=post_holiday | 57 | +7.1 | $+113 | 1.10 | 0.11 |
| Week of month=5 | 120 | +4.9 | $+241 | 1.09 | 1.74 |
| Month=6 | 101 | +4.6 | $+67 | 0.93 | -0.07 |
| Hourly RSI bucket=rsi_30_45 | 430 | +2.4 | $+108 | 0.92 | 0.28 |
| NQ-ES dispersion=disp_low | 409 | +2.4 | $+36 | 0.89 | -0.42 |
| Month=12 | 129 | +3.7 | $+32 | 0.85 | -0.26 |

## Notes

- First-hour-native conditions: range size (p90/p80), body conviction, close third, vs prior day, OR15 agree/oppose, gap vs first-hour direction.
- After-PO sleeves are expected to be thin — most prior-opposed campaigns are still live at 10:30.
- Chart index: [`charts/INDEX.md`](charts/INDEX.md).

## Stance

Curious diagnostic only. 1R fade WR 44% vs follow 50% (fair ~50%); 3R fade N/S -0.92 vs follow 9.32 (fair WR ~25%); after-PO-loss continuation 1R n=20 WR=50% N/S=-0.07 Do not promote from this mill alone.

Hub: `/home/tester/hsm/potions/live/state/nq_1h_first_hour_ha`

