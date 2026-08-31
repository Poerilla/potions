# V2B Clean-Break Pyramid Outside OR (max 8)

STATUS: RESEARCH TRIAL (Engine + PaperBroker, 5m RTH)

## Rules
- Base: bullish v2b clean break (OR 09:30–09:45, stop @ OR high + 2 ticks, clean close).
- After clean: +1 contract each 5m candle whose **low** stays above OR high (max 8).
- Exit all when 5m **close** <= OR high (`close_back_into_range`); EOD 15:55 still flattens.
- No 2R target / RL stop brackets in this size model.

## Results

| Market | Sessions | Trades | Units | Net | Stress DD | MaxU | N/S | Win% | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NQ | 4046 | 2042 | 5763 | $646,265.50 | $-139,398.50 | 8 | 4.64 | 30.7% | 1.43 |
| MNQ | 1325 | 679 | 1974 | $36,426.50 | $-14,395.50 | 8 | 2.53 | 33.4% | 1.34 |

| Combined net | $+682692 |
| Worst-market stress | $-139398 |
| Combined N/S (vs worst stress) | 4.90 |

**Stance:** research — interesting vs baseline single-lot clean break; needs OOS / causality note

Hub: `/home/tester/hsm/potions/live/state/v2b_clean_break_pyramid_outside_v1`
DSR: `TRL-2026-00193`
smoke=False

Baseline reference (single-lot bullish 2R/RL): NQ ~$93k / 3.79 N/S; MNQ ~$8.9k / 4.40 N/S.
