# NQ first-hour follow 3R broker HA + gates

Diagnostic only — not a promotion gate. HA here means **condition lift**, same mill as midnight-open / futures HP.

Universe: **broker-like** NQ first-hour follow 3R (`nq_1h_first_hour_broker`, n=3943, WR=37.2%, net=$176743, N/S=5.86). Full HP mill + FH native + London/prior sweep fade-follow + composite gates.

Follow = candle direction from close, SL at open. Fade = opposite from close, SL = reflection of open across close (same body risk).
1R target = 1× body; 3R = 3× body. Non-overlapping. Flatten 16:00. $1.50 fee, $20/pt.

Prior-opposed overlay: NQ v2b resting-limit `nq_prior_opposed_rl` (432 campaigns). **during_po** = bar inside a live PO campaign. **after_po** = same session after that campaign's exit (outcome is then causal). Implied ST = opposite of PO side.

Fair WR with no edge ≈ **25% at 3R**, ≈ **50% at 1R**.

## Core books

| Book | n | WR | avg | net | stress | N/S | PF |
|---|---:|---:|---:|---:|---:|---:|---:|
| follow 3R all first-hour (broker) | 3943 | 37.2% | $45 | $176743 | $30172 | 5.86 | 0.00 |

## HP regime sleeves (filtered signals, own non-overlap)

during fade-ST = during PO, large/first-hour candle *with implied ST*, **fade** it (counter-trend with PO).
after follow-ST = after PO exit, candle *with implied ST*, **follow** it (continuation).
after-loss follow-ST = same continuation, only when PO already lost (trend punched through the fade).
after-win fade-ST = after a PO win, fade remaining ST-direction candles (do not continue the old trend).

| Sleeve | n | WR | avg | net | stress | N/S | PF |
|---|---:|---:|---:|---:|---:|---:|---:|
| follow 3R + 1h ST trail | 3943 | 37.5% | $53 | $208314 | $27690 | 7.52 | 1.16 |

## vs current NQ prior-opposed HP buckets

Same condition=bucket that we already use on the PO book. Lift is vs **that candle book’s** baseline, not vs PO.

| book | condition=bucket | n | WR | avg lift vs book | PO n | PO WR | PO avg lift |
|---|---|---:|---:|---:|---:|---:|---:|
| follow_3r_all | Day of week=Friday | 787 | 40.5% | $61 | 85 | 68% | $1623 |
| follow_3r_all | 5m MA vs trade=ma_aligned | 1948 | 38.3% | $-2 | 274 | 66% | $-279 |
| follow_3r_all | Opening 15m range vs ATR=or_norm | 0 | 0.0% | $0 | 129 | 71% | $1430 |
| follow_3r_all | ST-event age=st_age_30_90m | 0 | 0.0% | $0 | 118 | 70% | $1179 |
| follow_3r_all | ST-event direction vs trade=st_opposed_proxy | 0 | 0.0% | $0 | 248 | 71% | $1084 |
| follow_3r_all | NQ-ES dispersion=disp_mid | 1292 | 36.7% | $21 | 138 | 69% | $429 |
| follow_3r_all | Week of month=2 | 937 | 35.9% | $-33 | 93 | 73% | $1247 |
| follow_3r_all | Hourly RSI vs trade=rsi_against_side | 1457 | 35.3% | $6 | 248 | 71% | $1084 |

## Dual-lift notables (per book)

### follow_3r_all

| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |
|---|---:|---:|---:|---:|---:|
| First-hour body conviction=strong | 1099 | +14.1 | $+70 | 8.56 | 4.47 |
| Sweep fade side (short after hi / long after lo)=sweep_with_side | 1603 | +4.7 | $+44 | 3.25 | 5.97 |
| First-hour range size=fh_p95 | 632 | +6.0 | $+62 | 2.89 | 2.25 |
| First-hour range size=fh_p90 | 608 | +5.9 | $+81 | 2.80 | 5.06 |
| Prior-day range half=day_opposed | 2472 | +2.6 | $+6 | 2.10 | 4.47 |
| Gap vs first hour=gap_with | 1901 | +2.8 | $+12 | 2.09 | 4.47 |
| Prior-week range half=week_opposed | 2242 | +2.4 | $+14 | 1.91 | 4.04 |
| Day of week=Friday | 787 | +3.3 | $+61 | 1.76 | 2.75 |
| OR15 vs first hour=or15_agree | 2764 | +2.1 | $+18 | 1.74 | 7.02 |
| PO regime=during_counter_with_po | 116 | +7.6 | $+25 | 1.67 | 0.51 |
| First-hour vs prior day=above_pdh | 506 | +3.5 | $+16 | 1.54 | 2.12 |
| ATR14 quartile=atr_q4 | 983 | +2.6 | $+76 | 1.49 | 5.22 |

## Notes

- Tape: Engine+PaperBroker unit_trades from `/home/tester/hsm/potions/live/state/nq_1h_first_hour_broker`.
- London window: 03:00–09:29 NY (pre-RTH). Sweep = first hour takes that session extreme.
- sweep_fade_side=fade_follow_through → short after hi sweep or long after lo sweep.
- Composite gates: singles + pairwise AND of top N/S lifts (see composite_gates.csv).
- ST trail: hourly ATR SuperTrend 14×3 stop replaces fixed open stop after entry; 3R TP + EOD retained.

## Stance

Curious diagnostic only. See tables. Do not promote from this mill alone.

Hub: `/home/tester/hsm/potions/live/state/nq_1h_first_hour_broker_ha`


## Composite gates (broker tape)

| Gate | n | WR | avg | net | stress | N/S | cov |
|---|---:|---:|---:|---:|---:|---:|---:|
| sweep_fade_side=sweep_with_side | 1603 | 41.9% | $89 | $142076 | $23816 | 5.97 | 41% |
| fh_size=fh_p90 | 608 | 43.1% | $125 | $76273 | $15074 | 5.06 | 15% |
| fh_body=strong | 1099 | 51.3% | $115 | $126252 | $28232 | 4.47 | 28% |
| fh_body=strong | 1099 | 51.3% | $115 | $126252 | $28232 | 4.47 | 28% |
| gap_vs_fh=gap_with | 1901 | 40.0% | $57 | $107568 | $24066 | 4.47 | 48% |
| day_opposed | 2472 | 39.8% | $51 | $124846 | $27934 | 4.47 | 63% |
| day_half_align=day_opposed | 2472 | 39.8% | $51 | $124846 | $27934 | 4.47 | 63% |
| week_opposed | 2242 | 39.7% | $59 | $131470 | $32502 | 4.04 | 57% |
| week_half_align=week_opposed | 2242 | 39.7% | $59 | $131470 | $32502 | 4.04 | 57% |
| dow=Friday | 787 | 40.5% | $106 | $83553 | $30334 | 2.75 | 20% |
| fh_size=fh_p95 | 632 | 43.2% | $107 | $67342 | $29908 | 2.25 | 16% |
| sweep_fade_follow | 2282 | 34.2% | $15 | $34264 | $40436 | 0.85 | 58% |

## Exit variant: 1h ATR SuperTrend trail

| Book | n | WR | avg | net | stress | N/S |
|---|---:|---:|---:|---:|---:|---:|
| follow 3R + 1h ST trail | 3943 | 37.5% | $53 | $208314 | $27690 | 7.52 |
