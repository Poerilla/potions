# CHOP20 boundary60 — Causal entry variants + HP gates

Generated: 2026-08-28T16:53:54
Smoke: False
DSR: TRL-2026-00180

## Contract

- Daily CHOP20 + close breakout = **signal only**; `available_at` = last RTH 1m.
- **close_to_globex**: first 1m bar with `ts > available_at` (post-close / Globex).
- **close_to_next_rth**: first RTH minute of the next session.
- Fill = entry-bar **open** ±1 tick adverse; stop-first 1m management.
- Same stop/targets/age as boundary60 structure.
- HP gates filter at signal time (no size-up).

## Board

| market | entry_mode | hp | trades | net | MTM DD | N/S | WR | causal |
|---|---|---|---:|---:|---:|---:|---:|---:|
| MNQ | close_to_globex | baseline | 30 | $+26573 | $-6202 | 4.28 | 43% | 30/30 |
| MNQ | close_to_globex | hp_wom3 | 13 | $+18388 | $-15798 | 1.16 | 46% | 13/13 |
| MNQ | close_to_next_rth | baseline | 27 | $+19558 | $-11656 | 1.68 | 44% | 27/27 |
| MNQ | close_to_next_rth | hp_wom3 | 13 | $+19048 | $-17351 | 1.10 | 54% | 13/13 |
| NQ | close_to_globex | baseline | 79 | $+465567 | $-61887 | 7.52 | 43% | 79/79 |
| NQ | close_to_globex | hp_rsi_gt70 | 29 | $+535657 | $-49760 | 10.76 | 66% | 29/29 |
| NQ | close_to_globex | hp_rsi_with_side | 67 | $+458696 | $-67090 | 6.84 | 45% | 67/67 |
| NQ | close_to_next_rth | baseline | 67 | $+386398 | $-116686 | 3.31 | 43% | 67/67 |
| NQ | close_to_next_rth | hp_rsi_gt70 | 28 | $+532959 | $-56581 | 9.42 | 61% | 28/28 |
| NQ | close_to_next_rth | hp_rsi_with_side | 60 | $+391850 | $-133898 | 2.93 | 45% | 60/60 |

## Stance

- **Preferred causal entry: `close_to_globex`** (first 1m after RTH close; almost always 16:00 NY, rarely 18:00 after the halt).
  - NQ baseline: **+$466k / N/S 7.52 / n=79** — survives vs non-causal same-day (+$470k / 6.84 / 69).
  - MNQ baseline: **+$27k / N/S 4.28 / n=30** — in line with prior MNQ same-day (+$23k / 3.36 / 31).
- **`close_to_next_rth`**: weaker on both markets (NQ N/S 3.31, MNQ 1.68) — keep as locked alternate, do not cherry-pick.
- **HP gates (1m path re-sim, filter only):**
  - NQ `rsi_with_side`: **INVALIDATED** as an enhancer (ΔN/S −0.7 globex / −0.4 next-RTH).
  - NQ `rsi_gt70`: research-only lift (ΔN/S +3.2 / +6.1) but **n≈28–29** and prior nulls NOT VALIDATED — do **not** promote; no size-up.
  - MNQ `week_of_month=3`: **INVALIDATED** (ΔN/S −3.1 / −0.6; loses net vs baseline).
- **HA size-ups**: not run — descriptive research only; no live gate.
- **Same-day last-RTH fill**: retired for promotion (same-bar close decision+fill is not causal).
- **Next step**: port **close_to_globex** baseline (no HP gate) to StrategyPlugin + CausalityGuard snapshots.

Hub: `/home/tester/hsm/potions/live/state/chop20_dynamic_range_causal_entry_variants`
