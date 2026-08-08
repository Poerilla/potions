# Lot-correct accounting — futures_st_pmc_runner_variants

Replaces cross-trade FIFO nets for multi-lot books.

## Rankability

| Class | Status |
|---|---|
| Fair 3R / max 1 | **Rankable** (lot match still applied) |
| 2R→10R / max 3 | **Rankable** after reconciliation |
| Indefinite / large inventory | **Not rankable** on N/S until forced-flat + reachable stress reviewed as a separate sleeve |

## Definitions

- **Trade-matched realized** — closed lots paired within `trade_id`.
- **Continuous terminal equity** — realized + mark of still-open lots at final sample close.
- **Forced-flat equity** — continuous minus fee + 1-tick slip on liquidating open lots.
- **Reachable stress DD** — intrabar adverse clipped to live stop (BE after TP1 / hard SL); gap-open uses bar open.
- **Raw intrabar stress** — diagnostic unclipped mark (legacy contamination source for indef).

## Results

| market | variant | rankable | realized | continuous | forced-flat | friction | reachable stress | raw stress | N/S flat | open lots | max open |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `ym` | `sl50_tp150_runners_2r_indef` | **no** | $1001892 | $394159 | $393483 | $676 | $-260691 | $-715046 | 1.51 | 104 | 108 |
| `ym` | `sl50_tp150_3r_1mfill` | yes | $106425 | $106425 | $106425 | $0 | $-6026 | $-6026 | 17.66 | 0 | 1 |
| `ym` | `sl50_tp150_runners_2r_10r` | yes | $313302 | $313302 | $313302 | $0 | $-20589 | $-21424 | 15.22 | 0 | 3 |
| `mym` | `sl50_tp150_runners_2r_indef` | **no** | $24321 | $26055 | $25975 | $80 | $-11478 | $-31777 | 2.26 | 40 | 46 |
| `mym` | `sl50_tp150_3r_1mfill` | yes | $6516 | $6516 | $6516 | $0 | $-634 | $-1366 | 10.28 | 0 | 1 |
| `mym` | `sl50_tp150_runners_2r_10r` | yes | $20600 | $20600 | $20600 | $0 | $-2110 | $-4468 | 9.76 | 0 | 3 |
| `mnq` | `sl50_tp150_runners_2r_indef` | **no** | $74865 | $78408 | $78324 | $84 | $-31016 | $-52542 | 2.52 | 42 | 45 |
| `mnq` | `sl50_tp150_3r_1mfill` | yes | $23171 | $23171 | $23171 | $0 | $-1195 | $-1195 | 19.38 | 0 | 1 |
| `mnq` | `sl50_tp150_runners_2r_10r` | yes | $49899 | $49899 | $49899 | $0 | $-4498 | $-4953 | 11.09 | 0 | 3 |
| `nq` | `sl50_tp150_runners_2r_indef` | **no** | $2890794 | $1198780 | $1197844 | $936 | $-963157 | $-2003784 | 1.24 | 144 | 148 |
| `nq` | `sl50_tp150_3r_1mfill` | yes | $349517 | $349517 | $349517 | $0 | $-17038 | $-17038 | 20.51 | 0 | 1 |
| `nq` | `sl50_tp150_runners_2r_10r` | yes | $775763 | $775763 | $775763 | $0 | $-55268 | $-58524 | 14.04 | 0 | 3 |

## Indefinite sleeve (research only)

Do **not** compare indefinite N/S to 3R/10R until product decision.
Campaign economics remain TP1≈+150 vs losers≈−50; BE runners realize ~0 on stop,
while gross notional / margin / correlated inventory are the real burdens.


## Artifacts

- `LOT_CORRECT_ACCOUNTING.csv`
- `audits_lot_correct/` per strategy

