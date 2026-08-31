# US30 ladder: why path WR ~54% still lost money

## Short answer

The **58.6 pts (~0.32×ATR)** figure is real but **measures the wrong leg**. It is MAE on the
**first-path** fade (lower → upper4) for 2018 Q2 — the chronologically 2nd *first* win.
The ladder book trades the **reverse / second** fade (entry at opp ±4 after that first win).
On that leg, MAE is typically **~2–3×ATR**; a **0.5×ATR** stop dies on essentially every trade.

Path “Rev WR” (~53.8%) only means price eventually reaches the original ±4 before ±8 —
**without** a protective stop. Broker PnL WR (~8%) is after the tight stop.

## Evidence

| Item | Value |
|---|---|
| Path reverse opportunities (first win) | 13 |
| Path reverse wins / fails / unresolved | 7 / 4 / 2 → **53.8%** geometric WR |
| Broker second_only trades | 12 |
| Broker fill mix | 12 entries, **12 stops**, 3× tp1, 2× tp2 |
| Broker net / WR / PF | **−$6,588** / **8.3%** / **0.33** |

### Cited sample (58.6 pts)

- Market: US30 2018 Q2
- Leg: **first** fade from lower (long @ lower4 → upper4 resolve)
- MAE: **58.63 pts = 0.321×ATR** (ATR≈182.5)
- Reverse outcome after that first win: **unresolved** (never a reverse path win)

### Reverse-leg MAE (entry at opp ±4 → path resolve)

Detail: `us30_mae_diagnosis.csv`.

| Stat | MAE pts | MAE / ATR |
|---|---:|---:|
| Median (all 13 reverse entries) | 455 | **2.74×** |
| Mean | 582 | 3.14× |
| Max | 3032 | 5.80× |
| Survive **0.5×ATR** stop | **0 / 13 (0%)** | |
| Path wins that survive 0.5×ATR | **0 / 7** | |

Closest “path win” was 2021 Q3 at **0.55×ATR** MAE — still above the 0.5 stop.

## Implication

Risk sized from first-path MAE understates reverse-path adverse excursion by roughly an
order of magnitude. To keep path-like win rate in broker fills, reverse risk needs to be
on the order of **~2–3×ATR** (or a different stop model), not 0.5×ATR.

Promote stance: **reject** US30 second_only @ 0.5×ATR as currently configured.
