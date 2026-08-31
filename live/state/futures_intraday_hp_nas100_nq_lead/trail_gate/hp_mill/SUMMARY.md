# NAS100 FH follow 3R strong+sweep ST-trail HP mill

Diagnostic only — not a promotion gate. HA here means **condition lift**, same mill as midnight-open / futures HP.

Universe: broker-like `follow_3r_strong_sweep_st_trail` (n=56, WR=50.0%, net=$-41, N/S=-0.04). HP mill after trail improved the gated book.

Follow = candle direction from close, SL at open. Fade = opposite from close, SL = reflection of open across close (same body risk).
1R target = 1× body; 3R = 3× body. Non-overlapping. Flatten 16:00. $1.50 fee, $20/pt.

Prior-opposed overlay: NQ v2b resting-limit `nq_prior_opposed_rl` (432 campaigns). **during_po** = bar inside a live PO campaign. **after_po** = same session after that campaign's exit (outcome is then causal). Implied ST = opposite of PO side.

Fair WR with no edge ≈ **25% at 3R**, ≈ **50% at 1R**.

## Core books

| Book | n | WR | avg | net | stress | N/S | PF |
|---|---:|---:|---:|---:|---:|---:|---:|
| follow_3r_strong_sweep_st_trail | 56 | 50.0% | $-1 | $-41 | $958 | -0.04 | 0.00 |

## HP regime sleeves (filtered signals, own non-overlap)

during fade-ST = during PO, large/first-hour candle *with implied ST*, **fade** it (counter-trend with PO).
after follow-ST = after PO exit, candle *with implied ST*, **follow** it (continuation).
after-loss follow-ST = same continuation, only when PO already lost (trend punched through the fade).
after-win fade-ST = after a PO win, fade remaining ST-direction candles (do not continue the old trend).

| Sleeve | n | WR | avg | net | stress | N/S | PF |
|---|---:|---:|---:|---:|---:|---:|---:|

## vs current NQ prior-opposed HP buckets

Same condition=bucket that we already use on the PO book. Lift is vs **that candle book’s** baseline, not vs PO.

| book | condition=bucket | n | WR | avg lift vs book | PO n | PO WR | PO avg lift |
|---|---|---:|---:|---:|---:|---:|---:|
| follow_3r_strong_sweep_st_trail | Day of week=Friday | 12 | 66.7% | $54 | 85 | 68% | $1623 |
| follow_3r_strong_sweep_st_trail | Week of month=2 | 7 | 57.1% | $18 | 93 | 73% | $1247 |
| follow_3r_strong_sweep_st_trail | 5m MA vs trade=ma_aligned | 34 | 55.9% | $12 | 274 | 66% | $-279 |
| follow_3r_strong_sweep_st_trail | Opening 15m range vs ATR=or_norm | 0 | 0.0% | $0 | 129 | 71% | $1430 |
| follow_3r_strong_sweep_st_trail | ST-event age=st_age_30_90m | 0 | 0.0% | $0 | 118 | 70% | $1179 |
| follow_3r_strong_sweep_st_trail | NQ-ES dispersion=disp_mid | 22 | 50.0% | $-16 | 138 | 69% | $429 |
| follow_3r_strong_sweep_st_trail | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| follow_3r_strong_sweep_st_trail | Hourly RSI vs trade=rsi_against_side | 6 | 33.3% | $-68 | 248 | 71% | $1084 |

## Dual-lift notables (per book)

### follow_3r_strong_sweep_st_trail

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| Cross-index direction agreement=all_agree | 42 | +4.8 | $+18 | 0.47 | 1.65 |
| Contract-roll week=not_roll_week | 49 | +3.1 | $+4 | 0.31 | 0.16 |
| Prior-day range half=day_opposed | 51 | +2.9 | $+8 | 0.30 | 0.45 |
| Prior-week range half=week_opposed | 44 | +2.3 | $+7 | 0.23 | 0.36 |

## Notes

- Trail book only — gated strong + sweep_with_side entries, hourly ST trail exits.
- Diagnostic, not a promotion gate.

## Stance

Curious diagnostic only. See tables. Do not promote from this mill alone.

Hub: `/home/tester/hsm/potions/live/state/futures_intraday_hp_nas100_nq_lead/trail_gate/hp_mill`

