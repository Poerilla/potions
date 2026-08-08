# FX / index / metals ST+PMC runner variants (1m fill tape)

Lot-correct audit: trade_id match, reachable stop stress, forced-flat open mark.

## Run status (2026-08-08 ~14:35Z)

| Market | Status |
|---|---|
| **NAS100** | **Done** (3R / 2R→10R / indef) |
| EURUSD | In progress — fair 3R ~50% (~75k/143k hours) |
| GBPUSD | In progress — fair 3R ~50% (~70k/143k hours) |
| USDJPY | In progress — fair 3R ~50% (~70k/143k hours) |
| AUDJPY / XAUUSD / XAGUSD | Queued after batch 1 |
| SPX500 | Skipped — no `fx/spx500_1m.csv` |

Parallel driver + orchestrator → lot-correct post (`python -m live.indefinite_lot_accounting --hubs fx`) when all markets finish.

## Rankability

| Class | Status |
|---|---|
| Fair 3R / max 1 | **Rankable** |
| 2R→10R / max 3 | **Rankable** |
| Indefinite | **Not rankable** vs 3R/10R (inventory sleeve) |

## Results (complete so far)

| market | variant | net | stress | N/S | units | WR% | max_open | EOY | stop/tp |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `nas100` | `sl50_tp150_3r_1mfill` | $15219 | $-778 | 19.56 | 477 | 41.9 | 1 | 0 | 50.0 / 150.0 |
| `nas100` | `sl50_tp150_runners_2r_10r` | $34065 | $-3059 | 11.13 | 762 | 26.2 | 3 | 0 | 50.0 / 150.0 |
| `nas100` | `sl50_tp150_runners_2r_indef` | $54331 | $-22598 | 2.40 | 1449 | 24.9 | 74 | 23 | 50.0 / 150.0 |

## Notes

- **SPX500** skipped when `fx/spx500_1m.csv` is missing (live demo bars only).
- USDJPY / AUDJPY nets use platform PV (JPY per price unit) — treat as native currency unless converted.
- Post-process lot books: `python -m live.indefinite_lot_accounting --hubs fx`

## Artifacts

- `summary.csv`
- Per market: `<market>/states/`, `<market>/audits/`
- Runner: `live/fx_index_metals_st_pmc_runner_variants.py`

