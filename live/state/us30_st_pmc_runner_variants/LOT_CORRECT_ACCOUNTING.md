# Lot-correct accounting — us30_st_pmc_runner_variants

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
| `us30` | `sl50_tp150_runners_2r_indef` | **no** | $58718 | $80271 | $80169 | $102 | $-32060 | $-89374 | 2.50 | 64 | 68 |
| `us30` | `sl50_tp150_3r_1mfill` | yes | $19028 | $19028 | $19028 | $0 | $-647 | $-907 | 29.39 | 0 | 1 |
| `us30` | `sl50_tp150_runners_2r_10r` | yes | $56111 | $56111 | $56111 | $0 | $-2333 | $-2867 | 24.05 | 0 | 3 |

## Indefinite sleeve (research only)

Do **not** compare indefinite N/S to 3R/10R until product decision.
Campaign economics remain TP1≈+150 vs losers≈−50; BE runners realize ~0 on stop,
while gross notional / margin / correlated inventory are the real burdens.


## Artifacts

- `LOT_CORRECT_ACCOUNTING.csv`
- `audits_lot_correct/` per strategy

