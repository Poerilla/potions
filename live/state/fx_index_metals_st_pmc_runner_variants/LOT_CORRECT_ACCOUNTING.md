# Lot-correct accounting — fx_index_metals_st_pmc_runner_variants

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

| market | variant | rankable | realized | continuous | forced-flat | friction | reachable stress | raw stress | N/S flat | open lots | max open | hold med h | hold p90 h |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `nas100` | `sl50_tp150_runners_2r_indef` | **no** | $91836 | $54436 | $54324 | $112 | $-22598 | $-49198 | 2.40 | 70 | 74 | 7 | 143 |
| `nas100` | `sl50_tp150_3r_1mfill` | yes | $15219 | $15219 | $15219 | $0 | $-778 | $-1008 | 19.56 | 0 | 1 | 4 | 92 |
| `nas100` | `sl50_tp150_runners_2r_10r` | yes | $33210 | $34067 | $34065 | $2 | $-3059 | $-3805 | 11.13 | 1 | 3 | 5 | 123 |
| `eurusd` | `sl50_tp150_runners_2r_indef` | **no** | $-120591 | $340131 | $339536 | $595 | $-228429 | $-234831 | 1.49 | 238 | 239 | 47 | 269 |
| `eurusd` | `sl50_tp150_3r_1mfill` | yes | $64720 | $64450 | $64448 | $2 | $-21432 | $-21432 | 3.01 | 1 | 1 | 43 | 192 |
| `eurusd` | `sl50_tp150_runners_2r_10r` | yes | $113232 | $121159 | $121156 | $2 | $-67308 | $-69158 | 1.80 | 1 | 3 | 49 | 336 |
| `gbpusd` | `sl50_tp150_runners_2r_indef` | **no** | $-287668 | $221139 | $220609 | $530 | $-267644 | $-529065 | 0.82 | 212 | 212 | 29 | 192 |
| `gbpusd` | `sl50_tp150_3r_1mfill` | yes | $108261 | $108059 | $108057 | $2 | $-13310 | $-13516 | 8.12 | 1 | 1 | 25 | 138 |
| `gbpusd` | `sl50_tp150_runners_2r_10r` | yes | $99742 | $101448 | $101443 | $5 | $-41066 | $-41145 | 2.47 | 2 | 3 | 25 | 216 |
| `usdjpy` | `sl50_tp150_runners_2r_indef` | **no** | $-26836242 | $14375006 | $14355213 | $19792 | $-42280000 | $-42838900 | 0.34 | 195 | 199 | 48 | 275 |
| `usdjpy` | `sl50_tp150_3r_1mfill` | yes | $4040012 | $4040012 | $4040012 | $0 | $-2282415 | $-2283008 | 1.77 | 0 | 1 | 39 | 190 |
| `usdjpy` | `sl50_tp150_runners_2r_10r` | yes | $1971276 | $2801337 | $2801236 | $102 | $-6519902 | $-6519902 | 0.43 | 1 | 3 | 48 | 356 |
| `audjpy` | `sl50_tp150_runners_2r_indef` | **no** | $-5647034 | $16400513 | $16382547 | $17966 | $-24697107 | $-34334305 | 0.66 | 177 | 178 | 48 | 311 |
| `audjpy` | `sl50_tp150_3r_1mfill` | yes | $9163436 | $9171243 | $9171141 | $102 | $-1162978 | $-1162978 | 7.89 | 1 | 1 | 36 | 195 |
| `audjpy` | `sl50_tp150_runners_2r_10r` | yes | $9802477 | $9825898 | $9825593 | $304 | $-4798864 | $-4798864 | 2.05 | 3 | 3 | 36 | 339 |
| `xauusd` | `sl50_tp150_runners_2r_indef` | **no** | $1256404 | $996112 | $995877 | $235 | $-2006322 | $-2006322 | 0.50 | 94 | 103 | 373 | 2628 |
| `xauusd` | `sl50_tp150_3r_1mfill` | yes | $77327 | $77327 | $77327 | $0 | $-92932 | $-92932 | 0.83 | 0 | 1 | 428 | 2687 |
| `xauusd` | `sl50_tp150_runners_2r_10r` | yes | $278071 | $278071 | $278071 | $0 | $-167944 | $-167944 | 1.66 | 0 | 3 | 284 | 5035 |
| `xagusd` | `sl50_tp150_runners_2r_indef` | **no** | $6188 | $15136 | $15129 | $8 | $-175800 | $-175800 | 0.09 | 3 | 3 | 8655 | 8722 |
| `xagusd` | `sl50_tp150_3r_1mfill` | yes | $0 | $68741 | $68738 | $2 | $-58600 | $-58600 | 1.17 | 1 | 1 | 0 | 0 |
| `xagusd` | `sl50_tp150_runners_2r_10r` | yes | $0 | $206223 | $206215 | $8 | $-175800 | $-175800 | 1.17 | 3 | 3 | 0 | 0 |

## Indefinite sleeve (research only)

Do **not** compare indefinite N/S to 3R/10R until product decision.
Campaign economics remain TP1≈+150 vs losers≈−50; BE runners realize ~0 on stop,
while gross notional / margin / correlated inventory are the real burdens.


## Artifacts

- `LOT_CORRECT_ACCOUNTING.csv`
- `audits_lot_correct/` per strategy

