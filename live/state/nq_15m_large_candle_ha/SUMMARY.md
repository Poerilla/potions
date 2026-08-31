# NQ 15m large-candle HA (high-probability conditions)

Diagnostic only — not a promotion gate. HA here means **condition lift**, same mill as midnight-open / futures HP.

Universe: NQ RTH 09:30–16:00 **15m**, **p90 range** candles (causal expanding threshold, resampled from 5m).

Follow = candle direction from close, SL at open. Fade = opposite from close, SL = reflection of open across close (same body risk).
1R target = 1× body; 3R = 3× body. Non-overlapping. Flatten 16:00. $1.50 fee, $20/pt.

Prior-opposed overlay: NQ v2b resting-limit `nq_prior_opposed_rl` (432 campaigns). **during_po** = bar inside a live PO campaign. **after_po** = same session after that campaign's exit (outcome is then causal). Implied ST = opposite of PO side.

Fair WR with no edge ≈ **25% at 3R**, ≈ **50% at 1R**.

## Core books

| Book | n | WR | avg | net | stress | N/S | PF |
|---|---:|---:|---:|---:|---:|---:|---:|
| follow 3R p90 | 9853 | 29.2% | $16 | $160246 | $54069 | 2.96 | 1.05 |
| fade 3R p90 | 10139 | 28.4% | $-9 | $-95894 | $120443 | -0.80 | 0.97 |
| follow 1R p90 | 13938 | 42.2% | $-26 | $-362582 | $388958 | -0.93 | 0.90 |
| fade 1R p90 | 13938 | 41.7% | $-29 | $-410372 | $412262 | -1.00 | 0.89 |

## HP regime sleeves (filtered signals, own non-overlap)

during fade-ST = during PO, large/first-hour candle *with implied ST*, **fade** it (counter-trend with PO).
after follow-ST = after PO exit, candle *with implied ST*, **follow** it (continuation).
after-loss follow-ST = same continuation, only when PO already lost (trend punched through the fade).
after-win fade-ST = after a PO win, fade remaining ST-direction candles (do not continue the old trend).

| Sleeve | n | WR | avg | net | stress | N/S | PF |
|---|---:|---:|---:|---:|---:|---:|---:|
| during fade-ST 3R | 574 | 34.1% | $205 | $117564 | $15870 | 7.41 | 1.51 |
| during fade-ST 1R | 701 | 46.2% | $59 | $41434 | $16639 | 2.49 | 1.19 |
| during any fade 1R | 1069 | 42.6% | $0 | $222 | $39634 | 0.01 | 1.00 |
| after follow-ST 3R | 235 | 26.4% | $-58 | $-13712 | $26388 | -0.52 | 0.88 |
| after follow-ST 1R | 271 | 39.5% | $-53 | $-14402 | $20834 | -0.69 | 0.86 |
| after-loss follow-ST 1R | 174 | 37.9% | $-56 | $-9711 | $14208 | -0.68 | 0.85 |
| after-win fade-ST 1R | 97 | 36.1% | $-31 | $-2990 | $7928 | -0.38 | 0.92 |

## vs current NQ prior-opposed HP buckets

Same condition=bucket that we already use on the PO book. Lift is vs **that candle book’s** baseline, not vs PO.

| book | condition=bucket | n | WR | avg lift vs book | PO n | PO WR | PO avg lift |
|---|---|---:|---:|---:|---:|---:|---:|
| fade_1r | Week of month=2 | 3429 | 42.1% | $-2 | 93 | 73% | $1247 |
| fade_1r | Opening 15m range vs ATR=or_norm | 3313 | 42.1% | $1 | 129 | 71% | $1430 |
| fade_1r | ST-event age=st_age_30_90m | 2515 | 41.8% | $14 | 118 | 70% | $1179 |
| fade_1r | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| fade_1r | 5m MA vs trade=ma_aligned | 6883 | 41.5% | $6 | 274 | 66% | $-279 |
| fade_1r | NQ-ES dispersion=disp_mid | 4355 | 40.9% | $-8 | 138 | 69% | $429 |
| fade_1r | Day of week=Friday | 2730 | 40.9% | $-3 | 85 | 68% | $1623 |
| fade_1r | Hourly RSI vs trade=rsi_against_side | 4894 | 40.2% | $-12 | 248 | 71% | $1084 |
| fade_3r | Day of week=Friday | 1959 | 29.0% | $-9 | 85 | 68% | $1623 |
| fade_3r | Week of month=2 | 2457 | 28.8% | $-0 | 93 | 73% | $1247 |
| fade_3r | Opening 15m range vs ATR=or_norm | 2265 | 28.7% | $6 | 129 | 71% | $1430 |
| fade_3r | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| fade_3r | 5m MA vs trade=ma_aligned | 5038 | 28.4% | $5 | 274 | 66% | $-279 |
| fade_3r | ST-event age=st_age_30_90m | 1738 | 28.3% | $36 | 118 | 70% | $1179 |
| fade_3r | NQ-ES dispersion=disp_mid | 3220 | 28.0% | $-24 | 138 | 69% | $429 |
| fade_3r | Hourly RSI vs trade=rsi_against_side | 3617 | 27.6% | $11 | 248 | 71% | $1084 |
| follow_1r | NQ-ES dispersion=disp_mid | 4355 | 43.2% | $10 | 138 | 69% | $429 |
| follow_1r | ST-event age=st_age_30_90m | 2515 | 42.9% | $-5 | 118 | 70% | $1179 |
| follow_1r | Opening 15m range vs ATR=or_norm | 3313 | 42.9% | $5 | 129 | 71% | $1430 |
| follow_1r | 5m MA vs trade=ma_aligned | 7049 | 42.7% | $9 | 274 | 66% | $-279 |
| follow_1r | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| follow_1r | Hourly RSI vs trade=rsi_against_side | 5192 | 41.6% | $-3 | 248 | 71% | $1084 |
| follow_1r | Day of week=Friday | 2730 | 41.1% | $-8 | 85 | 68% | $1623 |
| follow_1r | Week of month=2 | 3429 | 41.0% | $1 | 93 | 73% | $1247 |
| follow_3r | Opening 15m range vs ATR=or_norm | 2136 | 30.7% | $-19 | 129 | 71% | $1430 |
| follow_3r | Day of week=Friday | 1852 | 30.4% | $48 | 85 | 68% | $1623 |
| follow_3r | NQ-ES dispersion=disp_mid | 3083 | 29.8% | $11 | 138 | 69% | $429 |
| follow_3r | 5m MA vs trade=ma_aligned | 4975 | 29.5% | $20 | 274 | 66% | $-279 |
| follow_3r | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| follow_3r | ST-event age=st_age_30_90m | 1698 | 29.2% | $-2 | 118 | 70% | $1179 |
| follow_3r | Hourly RSI vs trade=rsi_against_side | 3623 | 28.4% | $1 | 248 | 71% | $1084 |
| follow_3r | Week of month=2 | 2470 | 28.2% | $-9 | 93 | 73% | $1247 |

## Dual-lift notables (per book)

### follow_3r

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| Entry hour (NY)=15 | 491 | +8.0 | $+46 | 3.81 | 2.74 |
| Hourly RSI bucket=rsi_gt70 | 544 | +6.4 | $+45 | 3.20 | 3.34 |
| Overnight range third=on_upper | 3649 | +2.7 | $+9 | 3.04 | 2.01 |
| RTH VWAP side=above_rth_vwap | 4677 | +2.2 | $+20 | 2.73 | 3.45 |
| Prior RTH range percentile=prior_range_norm | 2687 | +2.5 | $+33 | 2.56 | 4.71 |
| Hourly RSI bucket=rsi_55_70 | 2894 | +2.4 | $+48 | 2.53 | 7.62 |
| Prior-week range half=week_opposed | 5190 | +1.7 | $+22 | 2.12 | 6.17 |
| Overnight VWAP side=above_on_vwap | 4621 | +1.7 | $+7 | 2.04 | 1.96 |
| ST-event age=st_age_gt180m | 2428 | +2.1 | $+2 | 2.03 | 0.94 |
| Hourly RSI vs trade=rsi_with_side | 3384 | +1.6 | $+20 | 1.80 | 3.48 |
| ATR causal rolling percentile=atr_p0_25 | 1625 | +2.1 | $+17 | 1.75 | 2.64 |
| ATR causal rolling percentile=atr_p50_75 | 2515 | +1.8 | $+8 | 1.74 | 1.95 |

### fade_3r

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| Overnight compression=on_comp | 2414 | +3.7 | $+42 | 3.60 | 3.41 |
| ATR14 quartile=atr_q1 | 2536 | +3.0 | $+1 | 3.00 | -0.67 |
| Prior RTH range percentile=prior_range_comp | 2835 | +2.8 | $+45 | 2.95 | 3.17 |
| NQ-ES dispersion=disp_low | 2878 | +2.2 | $+8 | 2.30 | -0.07 |
| Post-holiday session=post_holiday | 318 | +5.5 | $+80 | 2.16 | 1.33 |
| Opening 15m range vs ATR=or_narrow | 1911 | +2.3 | $+3 | 2.08 | -0.36 |
| PO regime=during_counter_with_po | 260 | +5.8 | $+189 | 2.05 | 3.42 |
| Large-candle vs PO side=candle_against_po | 366 | +4.6 | $+123 | 1.93 | 3.41 |
| Trade side vs PO side=trade_with_po | 366 | +4.6 | $+123 | 1.93 | 3.41 |
| Month=6 | 712 | +3.3 | $+74 | 1.90 | 3.58 |
| Day of week=Monday | 1758 | +2.2 | $+43 | 1.87 | 2.55 |
| ATR causal rolling percentile=atr_p0_25 | 1674 | +2.2 | $+14 | 1.82 | 0.21 |

### follow_1r

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| ATR14 quartile=atr_q1 | 3486 | +4.2 | $+27 | 4.52 | 0.15 |
| ATR causal rolling percentile=atr_p25_50 | 2299 | +2.7 | $+28 | 2.43 | 0.21 |
| Opening 15m range vs ATR=or_narrow | 2511 | +2.5 | $+9 | 2.37 | -0.80 |
| Prior RTH range percentile=prior_range_norm | 3749 | +2.1 | $+13 | 2.27 | -0.71 |
| Hourly RSI bucket=rsi_55_70 | 3807 | +2.0 | $+21 | 2.24 | -0.28 |
| Overnight compression=on_norm | 4272 | +1.9 | $+17 | 2.22 | -0.54 |
| Hourly RSI bucket=rsi_gt70 | 818 | +3.9 | $+46 | 2.20 | 1.46 |
| Month=8 | 1239 | +2.8 | $+27 | 1.95 | 0.05 |
| Prior-day range half=day_opposed | 7757 | +1.3 | $+9 | 1.87 | -0.89 |
| Prior-week range half=week_opposed | 7360 | +1.2 | $+12 | 1.68 | -0.76 |
| PO regime=after_still_fading | 205 | +4.6 | $+61 | 1.34 | 0.68 |
| Hourly RSI vs trade=rsi_with_side | 4894 | +1.1 | $+11 | 1.30 | -0.76 |

### fade_1r

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| Large-candle vs PO side=candle_against_po | 562 | +5.7 | $+100 | 2.68 | 1.98 |
| Trade side vs PO side=trade_with_po | 562 | +5.7 | $+100 | 2.68 | 1.98 |
| PO regime=during_counter_with_po | 384 | +6.8 | $+122 | 2.66 | 4.17 |
| ATR14 quartile=atr_q1 | 3486 | +2.4 | $+16 | 2.55 | -0.90 |
| Prior RTH range percentile=prior_range_comp | 3839 | +2.1 | $+12 | 2.31 | -0.87 |
| Overnight compression=on_comp | 3171 | +2.2 | $+9 | 2.25 | -0.90 |
| ST-event age=st_age_90_180m | 2535 | +1.6 | $+12 | 1.52 | -0.70 |
| Gap direction=gap_flat | 86 | +7.2 | $+91 | 1.35 | 2.84 |
| PO v2b session state=during_po | 861 | +2.2 | $+41 | 1.30 | 0.27 |
| Month=6 | 990 | +2.0 | $+34 | 1.22 | 0.26 |
| Entry hour (NY)=14 | 1662 | +1.5 | $+21 | 1.16 | -0.25 |
| Week of month=5 | 1070 | +1.7 | $+32 | 1.09 | 0.12 |

## Stance

Curious diagnostic only. 1R fade WR 42% vs follow 42% (fair ~50%); 3R fade N/S -0.80 vs follow 2.96 (fair WR ~25%); during-PO fade-ST 1R n=701 WR=46% N/S=2.49; after-PO-loss continuation 1R n=174 WR=38% N/S=-0.68 Do not promote from this mill alone.

Hub: `/home/tester/hsm/potions/live/state/nq_15m_large_candle_ha`

