# NQ 5m large-candle HA (high-probability conditions)

Diagnostic only — not a promotion gate. HA here means **condition lift**, same mill as midnight-open / futures HP.

Universe: NQ RTH 09:30–16:00 5m, **p90 range** candles (causal expanding threshold).
Follow = candle direction from close, SL at open. Fade = opposite from close, SL = reflection of open across close (same body risk).
1R target = 1× body; 3R = 3× body. Non-overlapping. Flatten 16:00. $1.50 fee, $20/pt.

Prior-opposed overlay: NQ v2b resting-limit `nq_prior_opposed_rl` (432 campaigns). **during_po** = bar inside a live PO campaign. **after_po** = same session after that campaign's exit (outcome is then causal). Implied ST = opposite of PO side.

Fair WR with no edge ≈ **25% at 3R**, ≈ **50% at 1R**.

## Core books (all p90 large candles)

| Book | n | WR | avg | net | stress | N/S | PF |
|---|---:|---:|---:|---:|---:|---:|---:|
| follow 3R p90 | 25551 | 25.6% | $5 | $116518 | $86464 | 1.35 | 1.02 |
| fade 3R p90 | 26525 | 24.4% | $-18 | $-484088 | $485070 | -1.00 | 0.91 |
| follow 1R p90 | 41352 | 42.1% | $-16 | $-669173 | $708227 | -0.94 | 0.89 |
| fade 1R p90 | 41352 | 41.6% | $-19 | $-778533 | $778954 | -1.00 | 0.88 |

## HP regime sleeves (filtered signals, own non-overlap)

during fade-ST = during PO, large candle *with implied ST*, **fade** it (counter-trend with PO).
after follow-ST = after PO exit, large candle *with implied ST*, **follow** it (continuation).
after-loss follow-ST = same continuation, only when PO already lost (trend punched through the fade).
after-win fade-ST = after a PO win, fade remaining ST-direction candles (do not continue the old trend).

| Sleeve | n | WR | avg | net | stress | N/S | PF |
|---|---:|---:|---:|---:|---:|---:|---:|
| during fade-ST 3R | 1545 | 28.8% | $72 | $111838 | $20505 | 5.45 | 1.26 |
| during fade-ST 1R | 2085 | 43.9% | $8 | $16288 | $12854 | 1.27 | 1.04 |
| during any fade 1R | 3072 | 43.2% | $-12 | $-35978 | $46768 | -0.77 | 0.95 |
| after follow-ST 3R | 686 | 22.2% | $-43 | $-29799 | $34646 | -0.86 | 0.86 |
| after follow-ST 1R | 909 | 37.7% | $-49 | $-44378 | $50842 | -0.87 | 0.80 |
| after-loss follow-ST 1R | 572 | 37.8% | $-31 | $-17568 | $22933 | -0.77 | 0.86 |
| after-win fade-ST 1R | 337 | 47.5% | $31 | $10590 | $6439 | 1.64 | 1.15 |

## vs current NQ prior-opposed HP buckets

Same condition=bucket that we already use on the PO book. Lift is vs **that 5m book’s** baseline, not vs PO.

| 5m book | condition=bucket | n | WR | avg lift vs book | PO n | PO WR | PO avg lift |
|---|---|---:|---:|---:|---:|---:|---:|
| fade_1r | Week of month=2 | 10054 | 42.3% | $7 | 93 | 73% | $1247 |
| fade_1r | Opening 15m range vs ATR=or_norm | 10659 | 42.2% | $1 | 129 | 71% | $1430 |
| fade_1r | 5m MA vs trade=ma_aligned | 20573 | 41.9% | $2 | 274 | 66% | $-279 |
| fade_1r | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| fade_1r | Day of week=Friday | 8182 | 41.5% | $0 | 85 | 68% | $1623 |
| fade_1r | NQ-ES dispersion=disp_mid | 12834 | 41.4% | $1 | 138 | 69% | $429 |
| fade_1r | Hourly RSI vs trade=rsi_against_side | 14872 | 41.0% | $-1 | 248 | 71% | $1084 |
| fade_1r | ST-event age=st_age_30_90m | 8673 | 40.6% | $3 | 118 | 70% | $1179 |
| fade_3r | Opening 15m range vs ATR=or_norm | 6563 | 25.2% | $6 | 129 | 71% | $1430 |
| fade_3r | Week of month=2 | 6323 | 24.9% | $11 | 93 | 73% | $1247 |
| fade_3r | 5m MA vs trade=ma_aligned | 13190 | 24.5% | $4 | 274 | 66% | $-279 |
| fade_3r | Day of week=Friday | 5270 | 24.5% | $4 | 85 | 68% | $1623 |
| fade_3r | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| fade_3r | NQ-ES dispersion=disp_mid | 8410 | 24.0% | $-3 | 138 | 69% | $429 |
| fade_3r | Hourly RSI vs trade=rsi_against_side | 9666 | 23.9% | $0 | 248 | 71% | $1084 |
| fade_3r | ST-event age=st_age_30_90m | 5350 | 23.3% | $2 | 118 | 70% | $1179 |
| follow_1r | NQ-ES dispersion=disp_mid | 12834 | 42.9% | $2 | 138 | 69% | $429 |
| follow_1r | 5m MA vs trade=ma_aligned | 20768 | 42.5% | $2 | 274 | 66% | $-279 |
| follow_1r | Opening 15m range vs ATR=or_norm | 10659 | 42.4% | $2 | 129 | 71% | $1430 |
| follow_1r | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| follow_1r | ST-event age=st_age_30_90m | 8673 | 41.9% | $-5 | 118 | 70% | $1179 |
| follow_1r | Hourly RSI vs trade=rsi_against_side | 15517 | 41.8% | $1 | 248 | 71% | $1084 |
| follow_1r | Week of month=2 | 10054 | 41.4% | $-7 | 93 | 73% | $1247 |
| follow_1r | Day of week=Friday | 8182 | 41.3% | $-1 | 85 | 68% | $1623 |
| follow_3r | NQ-ES dispersion=disp_mid | 8037 | 26.4% | $8 | 138 | 69% | $429 |
| follow_3r | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| follow_3r | 5m MA vs trade=ma_aligned | 12814 | 25.5% | $-0 | 274 | 66% | $-279 |
| follow_3r | Hourly RSI vs trade=rsi_against_side | 9564 | 25.2% | $-1 | 248 | 71% | $1084 |
| follow_3r | Week of month=2 | 6381 | 24.9% | $-9 | 93 | 73% | $1247 |
| follow_3r | Day of week=Friday | 5081 | 24.8% | $-5 | 85 | 68% | $1623 |
| follow_3r | Opening 15m range vs ATR=or_norm | 6165 | 24.8% | $-14 | 129 | 71% | $1430 |
| follow_3r | ST-event age=st_age_30_90m | 5167 | 24.2% | $-15 | 118 | 70% | $1179 |

## Dual-lift notables (per 5m book)

### follow_3r

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| ATR14 quartile=atr_q1 | 6395 | +3.2 | $+2 | 5.25 | 3.42 |
| Day of week=Monday | 4361 | +1.9 | $+15 | 2.65 | 2.21 |
| ATR causal rolling percentile=atr_p0_25 | 3956 | +1.8 | $+13 | 2.42 | 1.81 |
| Prior-day range half=day_opposed | 13642 | +1.1 | $+2 | 2.28 | 1.86 |
| Hourly RSI bucket=rsi_gt70 | 1565 | +2.5 | $+35 | 2.21 | 5.59 |
| NQ-ES dispersion=disp_low | 7198 | +1.1 | $+6 | 1.89 | 2.19 |
| Week of month=3 | 5706 | +1.1 | $+10 | 1.74 | 2.34 |
| ST-event age=st_age_lt30m | 7163 | +1.0 | $+30 | 1.66 | 9.26 |
| ATR causal rolling percentile=atr_p25_50 | 4187 | +1.2 | $+10 | 1.65 | 1.46 |
| Entry hour (NY)=9 | 6450 | +1.0 | $+32 | 1.60 | 9.22 |
| Opening 15m range vs ATR=or_pre_open | 4696 | +1.1 | $+30 | 1.59 | 6.03 |
| Opening 15m direction vs trade=or_pre_open | 4696 | +1.1 | $+30 | 1.59 | 6.03 |

### fade_3r

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| Entry hour (NY)=15 | 2419 | +5.5 | $+8 | 5.98 | -0.54 |
| ST-event age=st_age_gt180m | 8947 | +2.6 | $+10 | 4.87 | -0.84 |
| Large-candle vs PO side=candle_against_po | 1140 | +5.3 | $+100 | 4.08 | 9.31 |
| Trade side vs PO side=trade_with_po | 1140 | +5.3 | $+100 | 4.08 | 9.31 |
| PO regime=during_counter_with_po | 769 | +5.2 | $+117 | 3.32 | 8.73 |
| Entry hour (NY)=14 | 2981 | +2.7 | $+16 | 3.22 | -0.25 |
| ATR14 quartile=atr_q1 | 6636 | +1.9 | $+12 | 3.16 | -0.94 |
| PO regime=after_still_fading | 371 | +5.5 | $+66 | 2.44 | 1.00 |
| PO v2b outcome (after exit)=po_loss | 469 | +4.8 | $+101 | 2.39 | 2.63 |
| Post-holiday session=post_holiday | 906 | +3.3 | $+28 | 2.25 | 0.39 |
| Opening 15m volume percentile=vol_mid | 6628 | +1.2 | $+12 | 2.11 | -0.69 |
| Opening 15m direction vs trade=or_aligned | 10850 | +1.0 | $+12 | 2.05 | -0.61 |

### follow_1r

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| ATR14 quartile=atr_q1 | 10363 | +4.1 | $+15 | 7.54 | -0.41 |
| ATR causal rolling percentile=atr_p0_25 | 6116 | +3.2 | $+14 | 4.75 | -0.21 |
| Prior-day range half=day_opposed | 21847 | +1.3 | $+3 | 3.17 | -0.91 |
| Hourly RSI bucket=rsi_gt70 | 2569 | +3.1 | $+17 | 3.09 | 0.07 |
| Opening 15m range vs ATR=or_narrow | 7654 | +1.8 | $+4 | 2.98 | -0.94 |
| NQ-ES dispersion=disp_low | 11349 | +1.3 | $+12 | 2.56 | -0.54 |
| ATR causal rolling percentile=atr_p25_50 | 6686 | +1.6 | $+7 | 2.50 | -0.84 |
| Hourly RSI bucket=rsi_55_70 | 11456 | +1.1 | $+11 | 2.14 | -0.51 |
| Day of week=Monday | 7098 | +1.3 | $+7 | 2.09 | -0.69 |
| Prior RTH range percentile=prior_range_comp | 11260 | +1.1 | $+3 | 2.07 | -0.97 |
| Overnight VWAP side=above_on_vwap | 18696 | +0.9 | $+5 | 2.06 | -0.76 |
| Overnight range third=on_upper | 15101 | +0.8 | $+4 | 1.76 | -0.75 |

### fade_1r

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| Overnight compression=on_comp | 9152 | +2.0 | $+4 | 3.58 | -0.96 |
| ATR14 quartile=atr_q1 | 10363 | +1.9 | $+10 | 3.43 | -1.00 |
| Month=7 | 2712 | +3.2 | $+14 | 3.31 | -0.59 |
| Opening 15m range vs ATR=or_narrow | 7654 | +2.0 | $+5 | 3.18 | -0.92 |
| ST-event age=st_age_gt180m | 15328 | +1.4 | $+5 | 2.91 | -0.99 |
| Opening 15m volume percentile=vol_low | 8600 | +1.6 | $+4 | 2.66 | -0.93 |
| Opening 15m direction vs trade=or_aligned | 18142 | +1.1 | $+6 | 2.56 | -1.00 |
| Entry hour (NY)=13 | 4460 | +1.9 | $+5 | 2.41 | -0.87 |
| PO regime=during_counter_with_po | 1282 | +3.2 | $+29 | 2.29 | 0.67 |
| Prior RTH range percentile=prior_range_norm | 11114 | +1.1 | $+1 | 2.16 | -1.00 |
| Cross-index direction agreement=mixed | 8460 | +1.2 | $+10 | 2.11 | -0.76 |
| Large-candle vs PO side=candle_against_po | 1863 | +2.3 | $+22 | 1.94 | 0.25 |

## Stance

Curious diagnostic only. 1R fade WR 42% vs follow 42% (fair ~50%); 3R fade N/S -1.00 vs follow 1.35 (fair WR ~25%); during-PO fade-ST 1R n=2085 WR=44% N/S=1.27; after-PO-loss continuation 1R n=572 WR=38% N/S=-0.77 Do not promote from this mill alone.

Hub: `/home/tester/hsm/potions/live/state/nq_5m_large_candle_ha`

