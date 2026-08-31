# NQ 15m large-candle HA (high-probability conditions, p99/p95)

Diagnostic only — not a promotion gate. HA here means **condition lift**, same mill as midnight-open / futures HP.

Universe: NQ RTH 09:30–16:00 **15m**, **p99 range** candles (causal expanding threshold, resampled from 5m). Fallback **p95** if p99 is too rare (hi).

Follow = candle direction from close, SL at open. Fade = opposite from close, SL = reflection of open across close (same body risk).
1R target = 1× body; 3R = 3× body. Non-overlapping. Flatten 16:00. $1.50 fee, $20/pt.

Prior-opposed overlay: NQ v2b resting-limit `nq_prior_opposed_rl` (432 campaigns). **during_po** = bar inside a live PO campaign. **after_po** = same session after that campaign's exit (outcome is then causal). Implied ST = opposite of PO side.

Fair WR with no edge ≈ **25% at 3R**, ≈ **50% at 1R**.

## Core books

| Book | n | WR | avg | net | stress | N/S | PF |
|---|---:|---:|---:|---:|---:|---:|---:|
| follow 3R p99 | 2290 | 34.5% | $39 | $89540 | $58887 | 1.52 | 1.07 |
| fade 3R p99 | 2338 | 30.9% | $-34 | $-78997 | $123216 | -0.64 | 0.95 |
| follow 1R p99 | 2798 | 46.5% | $-13 | $-37167 | $107970 | -0.34 | 0.97 |
| fade 1R p99 | 2798 | 43.7% | $-50 | $-140587 | $143022 | -0.98 | 0.90 |
| follow 3R p95 | 6738 | 31.1% | $30 | $200863 | $45014 | 4.46 | 1.08 |
| fade 3R p95 | 6913 | 29.9% | $-15 | $-101904 | $141228 | -0.72 | 0.96 |

## HP regime sleeves (filtered signals, own non-overlap)

during fade-ST = during PO, large/first-hour candle *with implied ST*, **fade** it (counter-trend with PO).
after follow-ST = after PO exit, candle *with implied ST*, **follow** it (continuation).
after-loss follow-ST = same continuation, only when PO already lost (trend punched through the fade).
after-win fade-ST = after a PO win, fade remaining ST-direction candles (do not continue the old trend).

| Sleeve | n | WR | avg | net | stress | N/S | PF |
|---|---:|---:|---:|---:|---:|---:|---:|
| during fade-ST 3R | 71 | 52.1% | $853 | $60564 | $12958 | 4.67 | 2.21 |
| during fade-ST 1R | 73 | 57.5% | $276 | $20130 | $11870 | 1.70 | 1.43 |
| during any fade 1R | 152 | 51.3% | $188 | $28507 | $13912 | 2.05 | 1.27 |
| after follow-ST 3R | 34 | 38.2% | $67 | $2269 | $7961 | 0.29 | 1.08 |
| after follow-ST 1R | 36 | 44.4% | $-84 | $-3039 | $6956 | -0.44 | 0.88 |
| after-loss follow-ST 1R | 27 | 44.4% | $-120 | $-3240 | $6930 | -0.47 | 0.83 |
| after-win fade-ST 1R | 9 | 33.3% | $-125 | $-1128 | $5782 | -0.20 | 0.83 |

## vs current NQ prior-opposed HP buckets

Same condition=bucket that we already use on the PO book. Lift is vs **that candle book’s** baseline, not vs PO.

| book | condition=bucket | n | WR | avg lift vs book | PO n | PO WR | PO avg lift |
|---|---|---:|---:|---:|---:|---:|---:|
| fade_1r | Opening 15m range vs ATR=or_norm | 482 | 49.2% | $62 | 129 | 71% | $1430 |
| fade_1r | Week of month=2 | 702 | 45.3% | $-6 | 93 | 73% | $1247 |
| fade_1r | NQ-ES dispersion=disp_mid | 801 | 43.8% | $-3 | 138 | 69% | $429 |
| fade_1r | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| fade_1r | Day of week=Friday | 545 | 43.1% | $-4 | 85 | 68% | $1623 |
| fade_1r | ST-event age=st_age_30_90m | 471 | 43.1% | $-31 | 118 | 70% | $1179 |
| fade_1r | 5m MA vs trade=ma_aligned | 1414 | 42.6% | $14 | 274 | 66% | $-279 |
| fade_1r | Hourly RSI vs trade=rsi_against_side | 896 | 41.5% | $-29 | 248 | 71% | $1084 |
| fade_3r | Opening 15m range vs ATR=or_norm | 423 | 36.2% | $-11 | 129 | 71% | $1430 |
| fade_3r | ST-event age=st_age_30_90m | 350 | 32.0% | $36 | 118 | 70% | $1179 |
| fade_3r | Day of week=Friday | 442 | 31.7% | $-50 | 85 | 68% | $1623 |
| fade_3r | Hourly RSI vs trade=rsi_against_side | 756 | 31.1% | $67 | 248 | 71% | $1084 |
| fade_3r | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| fade_3r | 5m MA vs trade=ma_aligned | 1178 | 30.3% | $19 | 274 | 66% | $-279 |
| fade_3r | NQ-ES dispersion=disp_mid | 669 | 30.2% | $-66 | 138 | 69% | $429 |
| fade_3r | Week of month=2 | 587 | 29.5% | $-71 | 93 | 73% | $1247 |
| fade_3r_lo | Opening 15m range vs ATR=or_norm | 1430 | 31.8% | $-5 | 129 | 71% | $1430 |
| fade_3r_lo | Day of week=Friday | 1312 | 31.4% | $-10 | 85 | 68% | $1623 |
| fade_3r_lo | Week of month=2 | 1666 | 31.2% | $16 | 93 | 73% | $1247 |
| fade_3r_lo | ST-event age=st_age_30_90m | 1147 | 30.3% | $8 | 118 | 70% | $1179 |
| fade_3r_lo | 5m MA vs trade=ma_aligned | 3443 | 30.3% | $15 | 274 | 66% | $-279 |
| fade_3r_lo | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| fade_3r_lo | NQ-ES dispersion=disp_mid | 2175 | 29.5% | $-26 | 138 | 69% | $429 |
| fade_3r_lo | Hourly RSI vs trade=rsi_against_side | 2425 | 28.9% | $10 | 248 | 71% | $1084 |
| follow_1r | ST-event age=st_age_30_90m | 471 | 47.6% | $55 | 118 | 70% | $1179 |
| follow_1r | NQ-ES dispersion=disp_mid | 801 | 47.2% | $10 | 138 | 69% | $429 |
| follow_1r | 5m MA vs trade=ma_aligned | 1381 | 46.6% | $22 | 274 | 66% | $-279 |
| follow_1r | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| follow_1r | Week of month=2 | 702 | 45.7% | $6 | 93 | 73% | $1247 |
| follow_1r | Day of week=Friday | 545 | 45.7% | $-13 | 85 | 68% | $1623 |
| follow_1r | Opening 15m range vs ATR=or_norm | 482 | 45.6% | $-32 | 129 | 71% | $1430 |
| follow_1r | Hourly RSI vs trade=rsi_against_side | 1104 | 45.3% | $-1 | 248 | 71% | $1084 |
| follow_3r | Day of week=Friday | 429 | 36.4% | $118 | 85 | 68% | $1623 |
| follow_3r | 5m MA vs trade=ma_aligned | 1110 | 35.7% | $74 | 274 | 66% | $-279 |
| follow_3r | NQ-ES dispersion=disp_mid | 667 | 34.9% | $11 | 138 | 69% | $429 |
| follow_3r | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| follow_3r | Opening 15m range vs ATR=or_norm | 401 | 33.9% | $-128 | 129 | 71% | $1430 |
| follow_3r | ST-event age=st_age_30_90m | 346 | 33.8% | $72 | 118 | 70% | $1179 |
| follow_3r | Week of month=2 | 574 | 33.1% | $-16 | 93 | 73% | $1247 |
| follow_3r | Hourly RSI vs trade=rsi_against_side | 912 | 31.6% | $-24 | 248 | 71% | $1084 |
| follow_3r_lo | NQ-ES dispersion=disp_mid | 2092 | 32.9% | $32 | 138 | 69% | $429 |
| follow_3r_lo | Day of week=Friday | 1270 | 32.2% | $82 | 85 | 68% | $1623 |
| follow_3r_lo | 5m MA vs trade=ma_aligned | 3358 | 31.7% | $29 | 274 | 66% | $-279 |
| follow_3r_lo | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| follow_3r_lo | Opening 15m range vs ATR=or_norm | 1378 | 30.8% | $-55 | 129 | 71% | $1430 |
| follow_3r_lo | Hourly RSI vs trade=rsi_against_side | 2521 | 30.4% | $-7 | 248 | 71% | $1084 |
| follow_3r_lo | ST-event age=st_age_30_90m | 1130 | 30.3% | $34 | 118 | 70% | $1179 |
| follow_3r_lo | Week of month=2 | 1685 | 28.9% | $-37 | 93 | 73% | $1247 |

## Dual-lift notables (per book)

### follow_3r

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| Entry hour (NY)=15 | 86 | +16.7 | $+335 | 3.20 | 7.60 |
| ST-event age=st_age_gt180m | 482 | +7.0 | $+127 | 2.96 | 3.08 |
| Opening 15m range vs ATR=or_narrow | 214 | +9.0 | $+101 | 2.65 | 1.42 |
| ATR causal rolling percentile=atr_p25_50 | 246 | +6.2 | $+82 | 1.94 | 1.78 |
| ATR14 quartile=atr_q1 | 573 | +4.3 | $+20 | 1.93 | 4.07 |
| Entry hour (NY)=13 | 129 | +8.2 | $+214 | 1.90 | 2.55 |
| Week of month=1 | 574 | +3.4 | $+53 | 1.51 | 1.37 |
| Prior-day range half=day_opposed | 1275 | +2.3 | $+18 | 1.40 | 2.00 |
| Hourly RSI vs trade=rsi_with_side | 704 | +2.8 | $+66 | 1.35 | 2.07 |
| Opening 15m volume percentile=vol_mid | 421 | +2.8 | $+55 | 1.13 | 1.35 |
| PO regime=during_counter_with_po | 50 | +7.5 | $+142 | 1.11 | 0.95 |
| Month=2 | 215 | +3.7 | $+166 | 1.09 | 1.64 |

### fade_3r

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| Large-candle vs PO side=candle_against_po | 53 | +20.1 | $+613 | 3.13 | 3.64 |
| Trade side vs PO side=trade_with_po | 53 | +20.1 | $+613 | 3.13 | 3.64 |
| Prior RTH range percentile=prior_range_comp | 452 | +7.0 | $+234 | 2.93 | 3.96 |
| Week of month=5 | 154 | +10.7 | $+227 | 2.78 | 2.16 |
| Overnight compression=on_comp | 311 | +7.4 | $+18 | 2.65 | -0.18 |
| Post-holiday session=post_holiday | 73 | +14.3 | $+139 | 2.61 | 0.55 |
| ATR causal rolling percentile=atr_p0_25 | 203 | +8.5 | $+54 | 2.52 | 0.26 |
| ATR causal rolling percentile=atr_p50_75 | 544 | +5.3 | $+93 | 2.42 | 1.56 |
| PO v2b session state=during_po | 96 | +10.8 | $+101 | 2.24 | 0.30 |
| Entry hour (NY)=14 | 243 | +5.7 | $+135 | 1.84 | 1.43 |
| ATR causal rolling percentile=atr_p25_50 | 254 | +5.3 | $+80 | 1.75 | 0.61 |
| Month=6 | 122 | +6.8 | $+220 | 1.59 | 2.36 |

### follow_1r

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| Entry hour (NY)=13 | 198 | +8.5 | $+297 | 2.32 | 11.35 |
| ATR14 quartile=atr_q1 | 700 | +4.6 | $+45 | 2.19 | 2.82 |
| Entry hour (NY)=12 | 207 | +4.7 | $+95 | 1.30 | 1.34 |
| PO regime=during_counter_with_po | 72 | +7.6 | $+193 | 1.28 | 1.15 |
| Prior RTH close location=prior_close_low_third | 1015 | +2.2 | $+16 | 1.22 | 0.05 |
| Gap direction=gap_up | 1250 | +1.9 | $+47 | 1.15 | 1.15 |
| Month=12 | 230 | +3.9 | $+85 | 1.14 | 1.42 |
| Opening 15m range vs ATR=or_narrow | 249 | +3.7 | $+41 | 1.11 | 0.40 |
| Month=9 | 208 | +3.9 | $+18 | 1.10 | 0.06 |
| Week of month=1 | 722 | +2.2 | $+31 | 1.07 | 0.27 |
| Month=5 | 188 | +4.0 | $+145 | 1.06 | 2.22 |
| Hourly RSI bucket=rsi_gt70 | 89 | +5.2 | $+54 | 0.96 | 0.47 |

### fade_1r

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| PO regime=during_counter_with_po | 43 | +21.4 | $+652 | 2.81 | 4.88 |
| Large-candle vs PO side=candle_against_po | 70 | +16.3 | $+492 | 2.72 | 4.87 |
| Trade side vs PO side=trade_with_po | 70 | +16.3 | $+492 | 2.72 | 4.87 |
| Prior RTH range percentile=prior_range_comp | 518 | +6.1 | $+108 | 2.59 | 1.44 |
| Week of month=5 | 176 | +9.2 | $+212 | 2.38 | 3.18 |
| Post-holiday session=post_holiday | 85 | +12.8 | $+62 | 2.34 | 0.10 |
| Opening 15m range vs ATR=or_norm | 482 | +5.5 | $+62 | 2.25 | 0.22 |
| ATR causal rolling percentile=atr_p50_75 | 609 | +3.0 | $+46 | 1.33 | -0.11 |
| PO v2b session state=during_po | 115 | +5.9 | $+140 | 1.25 | 0.59 |
| Prior RTH close location=prior_close_mid_third | 747 | +2.5 | $+43 | 1.23 | -0.12 |
| ATR causal rolling percentile=atr_p0_25 | 215 | +4.2 | $+53 | 1.21 | 0.04 |
| Month=7 | 137 | +5.2 | $+126 | 1.21 | 0.95 |

### follow_3r_lo

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| Entry hour (NY)=15 | 289 | +9.4 | $+48 | 3.37 | 1.96 |
| Hourly RSI bucket=rsi_gt70 | 327 | +7.1 | $+5 | 2.71 | 0.79 |
| Opening 15m range vs ATR=or_narrow | 1016 | +3.8 | $+28 | 2.45 | 2.32 |
| ATR causal rolling percentile=atr_p25_50 | 1043 | +3.7 | $+83 | 2.39 | 8.55 |
| Hourly RSI bucket=rsi_55_70 | 1903 | +2.6 | $+57 | 2.13 | 7.30 |
| ATR14 quartile=atr_q3 | 1684 | +2.3 | $+99 | 1.83 | 9.90 |
| PO v2b outcome (after exit)=po_win | 45 | +11.1 | $+264 | 1.60 | 2.24 |
| RTH VWAP side=above_rth_vwap | 3071 | +1.6 | $+17 | 1.59 | 3.80 |
| Prior-day range half=day_opposed | 3789 | +1.5 | $+13 | 1.57 | 4.89 |
| NQ-ES dispersion=disp_mid | 2092 | +1.8 | $+32 | 1.52 | 4.90 |
| Prior RTH range percentile=prior_range_norm | 1748 | +1.8 | $+31 | 1.47 | 4.36 |
| Month=7 | 435 | +3.4 | $+55 | 1.47 | 2.41 |

### fade_3r_lo

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| Overnight compression=on_comp | 1403 | +4.9 | $+40 | 3.67 | 1.31 |
| Entry hour (NY)=14 | 657 | +6.6 | $+86 | 3.53 | 2.70 |
| ST-event age=st_age_gt180m | 1602 | +4.3 | $+40 | 3.37 | 1.92 |
| ATR14 quartile=atr_q1 | 1730 | +3.3 | $+3 | 2.69 | -0.89 |
| Entry hour (NY)=15 | 324 | +6.8 | $+34 | 2.61 | 0.30 |
| ATR causal rolling percentile=atr_p0_25 | 977 | +4.1 | $+11 | 2.59 | -0.09 |
| Post-holiday session=post_holiday | 210 | +7.7 | $+144 | 2.40 | 1.68 |
| Prior RTH range percentile=prior_range_comp | 1773 | +2.7 | $+42 | 2.24 | 1.07 |
| PO v2b session state=after_po | 137 | +8.8 | $+104 | 2.22 | 0.78 |
| Opening 15m volume percentile=vol_low | 1182 | +3.2 | $+10 | 2.19 | -0.14 |
| Large-candle vs PO side=candle_against_po | 223 | +6.4 | $+202 | 2.05 | 3.44 |
| Trade side vs PO side=trade_with_po | 223 | +6.4 | $+202 | 2.05 | 3.44 |

## Stance

Curious diagnostic only. 1R fade WR 44% vs follow 47% (fair ~50%); 3R fade N/S -0.64 vs follow 1.52 (fair WR ~25%); during-PO fade-ST 1R n=73 WR=58% N/S=1.70; after-PO-loss continuation 1R n=27 WR=44% N/S=-0.47 Do not promote from this mill alone.

Hub: `/home/tester/hsm/potions/live/state/nq_15m_large_candle_ha_p99`

