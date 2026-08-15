# FX / index / metals ST+PMC runner variants (1m fill tape)

Lot-correct audit: trade_id match, reachable stop stress, forced-flat open mark.

## Rankability

| Class | Status |
|---|---|
| Fair 3R / max 1 | **Rankable** |
| 2R→10R / max 3 | **Rankable** |
| Indefinite | **Not rankable** vs 3R/10R until lot-correct forced-flat reviewed as inventory sleeve |

## Results

| market | variant | net | stress | N/S | units | WR% | max_open | EOY | stop/tp |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `audjpy` | `sl50_tp150_3r_1mfill` | $9171241 | $-1162978 | 7.89 | 851 | 30.8 | 1 | 0 | 0.5 / 1.5 |
| `audjpy` | `sl50_tp150_runners_2r_10r` | $9825893 | $-4798864 | 2.05 | 942 | 16.8 | 3 | 0 | 0.5 / 1.5 |
| `audjpy` | `sl50_tp150_runners_2r_indef` | $16400247 | $-24697107 | 0.66 | 2577 | 19.4 | 178 | 61 | 0.5 / 1.5 |
| `eurusd` | `sl50_tp150_3r_1mfill` | $64449 | $-21432 | 3.01 | 866 | 29.0 | 1 | 0 | 0.005 / 0.015 |
| `eurusd` | `sl50_tp150_runners_2r_10r` | $121157 | $-67308 | 1.80 | 855 | 17.1 | 3 | 0 | 0.005 / 0.015 |
| `eurusd` | `sl50_tp150_runners_2r_indef` | $339774 | $-228429 | 1.49 | 2589 | 20.0 | 239 | 48 | 0.005 / 0.015 |
| `gbpusd` | `sl50_tp150_3r_1mfill` | $108058 | $-13310 | 8.12 | 1026 | 30.6 | 1 | 0 | 0.005 / 0.015 |
| `gbpusd` | `sl50_tp150_runners_2r_10r` | $101445 | $-41066 | 2.47 | 1110 | 16.5 | 3 | 0 | 0.005 / 0.015 |
| `gbpusd` | `sl50_tp150_runners_2r_indef` | $220821 | $-267644 | 0.82 | 3072 | 18.7 | 212 | 21 | 0.005 / 0.015 |
| `nas100` | `sl50_tp150_3r_1mfill` | $15219 | $-778 | 19.56 | 477 | 41.9 | 1 | 0 | 50.0 / 150.0 |
| `nas100` | `sl50_tp150_runners_2r_10r` | $34065 | $-3059 | 11.13 | 762 | 26.2 | 3 | 0 | 50.0 / 150.0 |
| `nas100` | `sl50_tp150_runners_2r_indef` | $54331 | $-22598 | 2.40 | 1449 | 24.9 | 74 | 23 | 50.0 / 150.0 |
| `usdjpy` | `sl50_tp150_3r_1mfill` | $4040012 | $-2282415 | 1.77 | 869 | 27.5 | 1 | 0 | 0.5 / 1.5 |
| `usdjpy` | `sl50_tp150_runners_2r_10r` | $2801336 | $-6519902 | 0.43 | 870 | 14.5 | 3 | 0 | 0.5 / 1.5 |
| `usdjpy` | `sl50_tp150_runners_2r_indef` | $14374713 | $-42280000 | 0.34 | 2544 | 18.5 | 199 | 50 | 0.5 / 1.5 |
| `xagusd` | `sl50_tp150_3r_1mfill` | $68739 | $-58600 | 1.17 | 1 | 100.0 | 1 | 0 | 50.0 / 150.0 |
| `xagusd` | `sl50_tp150_runners_2r_10r` | $206218 | $-175800 | 1.17 | 3 | 100.0 | 3 | 0 | 50.0 / 150.0 |
| `xagusd` | `sl50_tp150_runners_2r_indef` | $15132 | $-175800 | 0.09 | 69 | 43.5 | 3 | 66 | 50.0 / 150.0 |
| `xauusd` | `sl50_tp150_3r_1mfill` | $77327 | $-92932 | 0.83 | 169 | 28.4 | 1 | 0 | 50.0 / 150.0 |
| `xauusd` | `sl50_tp150_runners_2r_10r` | $278071 | $-167944 | 1.66 | 96 | 17.7 | 3 | 0 | 50.0 / 150.0 |
| `xauusd` | `sl50_tp150_runners_2r_indef` | $995971 | $-2006322 | 0.50 | 573 | 29.7 | 103 | 66 | 50.0 / 150.0 |

## Notes

- **SPX500** skipped when `fx/spx500_1m.csv` is missing (live demo bars only).
- USDJPY / AUDJPY nets use platform PV (JPY per price unit) — treat as native currency unless converted.
- Post-process lot books: `python -m live.indefinite_lot_accounting --hubs fx`

## Artifacts

- `summary.csv`
- Per market: `<market>/states/`, `<market>/audits/`
- Runner: `live/fx_index_metals_st_pmc_runner_variants.py`

