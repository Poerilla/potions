# CHOP20 post-entry peer confirmation (SMT-style)

Generated: 2026-08-28T23:01:13
DSR: TRL-2026-00185
Driver: `live/chop20_post_entry_smt_study.py`

## Contract

- Post-entry layer only (not an entry filter).
- Primary campaigns: CHOP20 boundary60 `close_to_globex` baselines.
- Peer level family: prior-day CHOP20 rolling `range_high_20` / `range_low_20` (frozen at signal `available_at`).
- Confirmation clock `t0` = primary **entry fill** (locked windows 0–5 / 6–30 / max 60m or exit).
- State from completed 1m bars; counterfactual actions fill on the next minute.
- Pairs: NAS100→SPX500 (phase 1–4) and SPX500→NAS100 (phase 5). US30 deferred.

## Verdict

**Do not promote peer non-confirmation as an invalidation / add-suppression rule on this book.**

On NAS100 primary / SPX500 peer, `NO_CONFIRM` campaigns have **higher** mean R, **lower** stop rate, and **higher** 4R hit rate than `ALREADY_CONFIRMED`. Causal forward tables at +5/+15/+30m among still-open trades agree: unconfirmed peers show better forward mean R and lower forward stop rate. Suppressing adds after 30m no-confirm **destroys** baseline net R (~+24.7 → ~+1.7).

`OPPOSITE_BREAK` is n=1 — no decision weight. `CONFIRMS_FAST` / `CONFIRMS_LATE` are effectively empty for this daily-range + globex-entry design (peer either already through the prior-day window by entry, or not within 60m).

## NAS100 → SPX500 outcomes by state

| state | n | share | mean R | stop | hit 0.5/1/4 | med MAE R | med MFE R | N/stress |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| NO_CONFIRM | 45 | 61% | +0.57 | 84% | 38/27/16 | -0.14 | 0.26 | 1.35 |
| ALREADY_CONFIRMED | 28 | 38% | -0.07 | 93% | 36/21/7 | -0.19 | 0.18 | -0.12 |
| OPPOSITE_BREAK | 1 | 1% | +1.16 | 100% | 100/100/0 | -0.34 | 1.25 | n/a |

### Long / short

| side | state | n | mean R | stop | hit4 |
|---|---|---:|---:|---:|---:|
| long | NO_CONFIRM | 31 | +0.77 | 84% | 16% |
| long | ALREADY_CONFIRMED | 19 | +0.04 | 95% | 5% |
| short | NO_CONFIRM | 14 | +0.13 | 86% | 14% |
| short | ALREADY_CONFIRMED | 9 | -0.32 | 89% | 11% |
| short | OPPOSITE_BREAK | 1 | +1.16 | 100% | 0% |

### Conditional forward (still open at decision)

| +mins | peer state | n | fwd stop | mean fwd R | med fwd MFE R |
|---:|---|---:|---:|---:|---:|
| 5 | ALREADY_CONFIRMED | 27 | 93% | -0.09 | 0.18 |
| 5 | OPPOSITE_BREAK | 1 | 100% | +1.00 | 1.19 |
| 5 | PENDING_UNCONFIRMED | 41 | 83% | +0.63 | 0.29 |
| 15 | ALREADY_CONFIRMED | 27 | 93% | -0.10 | 0.18 |
| 15 | OPPOSITE_BREAK | 1 | 100% | +0.98 | 1.18 |
| 15 | PENDING_UNCONFIRMED | 40 | 82% | +0.64 | 0.35 |
| 30 | ALREADY_CONFIRMED | 26 | 92% | -0.14 | 0.19 |
| 30 | NO_CONFIRM | 40 | 82% | +0.63 | 0.36 |
| 30 | OPPOSITE_BREAK | 1 | 100% | +0.77 | 1.11 |

### Counterfactual actions

| action | net R | mean R |
|---|---:|---:|
| baseline | +24.7 | +0.334 |
| suppress_adds_after_30m_no_confirm | +1.7 | +0.023 |
| flatten_after_opposite | +23.8 | +0.321 |
| tighten_stop_after_opposite | +23.6 | +0.319 |

## SPX500 → NAS100 (reverse)

| state | n | mean R | stop | hit4 |
|---|---:|---:|---:|---:|
| ALREADY_CONFIRMED | 24 | +0.06 | 83% | 17% |
| NO_CONFIRM | 19 | +0.58 | 84% | 11% |
| PEER_LEVEL_UNAVAILABLE | 13 | -0.07 | 92% | 8% |

Actions: baseline netR=+11.5, suppress_adds_after_30m_no_confirm netR=+2.5, flatten_after_opposite netR=+11.5, tighten_stop_after_opposite netR=+11.5

Reverse pair echoes the same qualitative result: `NO_CONFIRM` is not worse than sync confirmation; add-suppression after no-confirm hurts.

## Artifacts

- `nas100_vs_spx500/events.csv` — frozen event schema
- `*/outcome_by_state*.csv`, `confirmation_heatmap_hour.csv`, `leadlag_delay_distribution.csv`
- `*/transition_table.csv`, `conditional_risk*.csv`, `counterfactual_*.csv`
- `EMAIL.txt`

## Next (only if revisiting)

- Do **not** expand US30 until a different level family (e.g. RTH opening range) is predeclared — CHOP20 daily-range peer confirm is already decided against for invalidation.
- Optional second study: 30m RTH opening-range peer confirm on intraday books (ST+PMC / London), not this daily CHOP20 campaign tape.

Hub: `/home/tester/hsm/potions/live/state/chop20_post_entry_smt_nas100_spx500`
