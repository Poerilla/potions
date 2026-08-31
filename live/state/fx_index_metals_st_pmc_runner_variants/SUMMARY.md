# FX / index / metals ST+PMC runner variants (1m fill tape)

Lot-correct audit: trade_id match, reachable stop stress, forced-flat open mark.

> **2026-08 completed-hour causality fix.** The shared hourly resampler is left-labeled, so a bar timestamped 11:00 contains 11:00-11:59 data. This replay shifts signal bars to the completed-hour timestamp before the strategy can consume them, and fills only on the 1m tape.

## Rankability

| Class | Status |
|---|---|
| Fair 3R / max 1 | **Rankable** |
| 2R→10R / max 3 | **Rankable** |
| Indefinite | **Not rankable** vs 3R/10R until lot-correct forced-flat reviewed as inventory sleeve |

## Results

| market | variant | net | stress | N/S | units | WR% | max_open | EOY | stop/tp |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `audjpy` | `sl50_tp150_3r_1mfill` | $647229 | $-2526181 | 0.26 | 1334 | 25.6 | 1 | 0 | 0.5 / 1.5 |
| `audjpy` | `sl50_tp150_runners_2r_10r` | $3395763 | $-8134309 | 0.42 | 1257 | 14.6 | 3 | 0 | 0.5 / 1.5 |
| `audjpy` | `sl50_tp150_runners_2r_indef` | $-2400317 | $-46100207 | -0.05 | 4020 | 16.1 | 233 | 72 | 0.5 / 1.5 |
| `eurusd` | `sl50_tp150_3r_1mfill` | $-29300 | $-46192 | -0.63 | 1402 | 24.2 | 1 | 0 | 0.005 / 0.015 |
| `eurusd` | `sl50_tp150_runners_2r_10r` | $96403 | $-64619 | 1.49 | 1041 | 14.7 | 3 | 0 | 0.005 / 0.015 |
| `eurusd` | `sl50_tp150_runners_2r_indef` | $-57946 | $-511962 | -0.11 | 4212 | 16.5 | 356 | 55 | 0.005 / 0.015 |
| `gbpusd` | `sl50_tp150_3r_1mfill` | $-130688 | $-135189 | -0.97 | 1754 | 24.5 | 1 | 0 | 0.005 / 0.015 |
| `gbpusd` | `sl50_tp150_runners_2r_10r` | $-356192 | $-381383 | -0.93 | 1722 | 12.3 | 3 | 0 | 0.005 / 0.015 |
| `gbpusd` | `sl50_tp150_runners_2r_indef` | $-424021 | $-763044 | -0.56 | 5136 | 15.5 | 324 | 45 | 0.005 / 0.015 |
| `nas100` | `sl50_tp150_3r_1mfill` | $1421 | $-2665 | 0.53 | 856 | 27.5 | 1 | 0 | 50.0 / 150.0 |
| `nas100` | `sl50_tp150_runners_2r_10r` | $11632 | $-4821 | 2.41 | 1347 | 15.9 | 3 | 0 | 50.0 / 150.0 |
| `nas100` | `sl50_tp150_runners_2r_indef` | $4564 | $-35165 | 0.13 | 2607 | 16.5 | 111 | 27 | 50.0 / 150.0 |
| `usdjpy` | `sl50_tp150_3r_1mfill` | $-7870666 | $-8471696 | -0.93 | 1372 | 22.4 | 1 | 0 | 0.5 / 1.5 |
| `usdjpy` | `sl50_tp150_runners_2r_10r` | $3265954 | $-6812715 | 0.48 | 1086 | 13.8 | 3 | 0 | 0.5 / 1.5 |
| `usdjpy` | `sl50_tp150_runners_2r_indef` | $-18402927 | $-79410594 | -0.23 | 4062 | 15.8 | 311 | 67 | 0.5 / 1.5 |
| `xagusd` | `sl50_tp150_3r_1mfill` | $68739 | $-58600 | 1.17 | 1 | 100.0 | 1 | 0 | 50.0 / 150.0 |
| `xagusd` | `sl50_tp150_runners_2r_10r` | $206218 | $-175800 | 1.17 | 3 | 100.0 | 3 | 0 | 50.0 / 150.0 |
| `xagusd` | `sl50_tp150_runners_2r_indef` | $155956 | $-175800 | 0.89 | 69 | 60.9 | 3 | 66 | 50.0 / 150.0 |
| `xauusd` | `sl50_tp150_3r_1mfill` | $17187 | $-179376 | 0.10 | 181 | 26.5 | 1 | 0 | 50.0 / 150.0 |
| `xauusd` | `sl50_tp150_runners_2r_10r` | $233508 | $-155551 | 1.50 | 129 | 17.1 | 3 | 0 | 50.0 / 150.0 |
| `xauusd` | `sl50_tp150_runners_2r_indef` | $1077520 | $-2132133 | 0.51 | 624 | 29.3 | 115 | 70 | 50.0 / 150.0 |

## Notes

- **SPX500** skipped when `fx/spx500_1m.csv` is missing (live demo bars only).
- USDJPY / AUDJPY nets use platform PV (JPY per price unit) — treat as native currency unless converted.
- Post-process lot books: `python -m live.indefinite_lot_accounting --hubs fx`

## Artifacts

- `summary.csv`
- Per market: `<market>/states/`, `<market>/audits/`
- Runner: `live/fx_index_metals_st_pmc_runner_variants.py`

