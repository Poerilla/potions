# NAS100 misses of NQ winners — lookahead structure

Diagnostic only. The causal coupled book is unchanged: one NAS100 bar after the NQ entry bar completes, close must be through the ratio-mapped NQ opening range. This note looks past that bar on purpose.

Parent hub: `live/state/nas100_v2b_nq_lead_coupled_resting_limit/`. Lead book: hour-complete NQ resting-limit. Stance: **research only**.

## What the legal bar is doing

NQ fill stamps are the left-labeled minute. The follower may look on the next NAS bar after that minute completes, so the decision is about two minutes after the NQ print. Structure is the NAS **close** versus NQ's opening range scaled by the last NAS close already known at reveal. It is not NAS100's own 09:30–09:45 range.

Campaigns in the sync audit: **381**. Entered: **193**. `structure_failed`: **185**.

Classes on a structure miss:

- `close_gave_back` — a NAS close was already through the mapped level on the NQ fill minute or the completion minute, and the only legal bar (about two minutes after the fill) closed back inside.
- `wick_on_legal_bar` — that legal bar is the first trade through the level, and it closes back inside.
- `delayed_break` — no close has been through yet, and a later close the same session is.
- `never_breaks` — no NAS close through the mapped level for the rest of RTH.

### NQ winners skipped for structure (n=116)

| Class | N | Share |
|---|---:|---:|
| close_gave_back | 116 | 100.0% |

On the legal bar the close is back inside by a median **6.5** points (**0.092** mapped-OR widths). The same bar still wicks through the mapped level in **99.1%**. The first NAS close through that level is within two minutes of the NQ fill on **81.9%** of these rows (**12.1%** were already through more than 15 minutes earlier).

| Reclaim of the mapped close after the legal bar | N | Share |
|---|---:|---:|
| 1 min | 30 | 25.9% |
| 2–5 min | 44 | 37.9% |
| 6–15 min | 24 | 20.7% |
| 16–60 min | 16 | 13.8% |
| >60 min | 1 | 0.9% |
| never again that RTH | 1 | 0.9% |

When the close does come back through, the median wait is **3** minutes (p25 1, p75 8).

NAS's own 09:30–09:45 range is not a different box. Median mapped/native width ratio **1.010**. Median level gap **0.037** native widths (positive means the mapped NQ break is further out). The mapped level is more than 0.25 native widths further out on **19.0%** of rows. The legal close would still have cleared NAS's own range on **37.1%**. NAS's own range breaks within two minutes of the NQ fill on **76.7%**.

### NQ losers skipped for structure (n=69)

| Class | N | Share |
|---|---:|---:|
| close_gave_back | 69 | 100.0% |

On the legal bar the close is back inside by a median **5.4** points (**0.083** mapped-OR widths). The same bar still wicks through the mapped level in **98.6%**. The first NAS close through that level is within two minutes of the NQ fill on **63.8%** of these rows (**27.5%** were already through more than 15 minutes earlier).

| Reclaim of the mapped close after the legal bar | N | Share |
|---|---:|---:|
| 1 min | 16 | 23.2% |
| 2–5 min | 20 | 29.0% |
| 6–15 min | 7 | 10.1% |
| 16–60 min | 13 | 18.8% |
| >60 min | 5 | 7.2% |
| never again that RTH | 8 | 11.6% |

When the close does come back through, the median wait is **4** minutes (p25 1, p75 17).

NAS's own 09:30–09:45 range is not a different box. Median mapped/native width ratio **1.010**. Median level gap **-0.001** native widths (positive means the mapped NQ break is further out). The mapped level is more than 0.25 native widths further out on **5.8%** of rows. The legal close would still have cleared NAS's own range on **27.5%**. NAS's own range breaks within two minutes of the NQ fill on **66.7%**.

### Causal NAS entries (n=193)

| Class | N | Share |
|---|---:|---:|
| entered_on_legal_bar | 193 | 100.0% |

## Would-be NAS100 S_1_1_1 (lookahead)

If the first NAS close through the mapped range after the NQ bar completes is taken (fill on the next open, 1 tick adverse, fee $1.50 per unit per fill, stop before target), the campaign is a would-be NAS trade. The 60-second cap is removed. This is not the causal book.

| Slice | NQ campaigns | NAS trades | NAS win% | NAS net | NQ-win & NAS-win | NQ-win & NAS-loss | NQ-loss & NAS-win |
|---|---:|---:|---:|---:|---:|---:|---:|
| All campaigns | 381 | 370 | 63.2% | $17518 | 219 | 25 | 15 |
| Causal entries | 193 | 191 | 60.7% | $6954 | 112 | 16 | 4 |
| structure_failed | 185 | 176 | 65.9% | $10314 | 106 | 9 | 10 |
| NQ winners, structure_failed | 116 | 115 | 92.2% | $20384 | 106 | 9 | 0 |
| NQ losers, structure_failed | 69 | 61 | 16.4% | $-10070 | 0 | 0 | 10 |

Of **116** NQ-winner campaigns the causal book skipped for structure, lookahead NAS wins **106**, loses **9**, and never gets a mapped close-break **1**. The same exit proxy on the 193 causal entries nets about **$6954**, next to the broker book’s **$7,474**, so the skipped-winner dollars are on that scale and still use the later close.

## Read

NAS100 is not late to the break. On **88** of **116** skipped NQ winners the first close through the mapped range is the NQ fill minute (32) or the completion minute (56). The follower may only use the bar after that, and that close has already fallen back inside (median 6.5 points, 0.092 of the range) even though the bar still wicks the level on **99.1%** of them. The two opening ranges match: median width ratio 1.010, median level gap 0.037 native widths. Using NAS's own range would have passed the legal close on only 37% of these winner-misses. The close comes back through a median of 3 min later (**63.8%** within five minutes). A lookahead S_1_1_1 on that later close wins **106** of the 116. The same giveback hits NQ losers, so the one-bar close gate is not sorting winners from losers. One skipped NQ winner never reclaims the mapped close.

Files: `campaigns.csv`, `class_counts.csv`.
