# ST+PMC cross-market 1m fill tape - historical/stale hub

This folder is retained as a historical audit artifact only.

Do **not** rank YM / MYM / NQ / MNQ / NAS100 from the tables or state files in
this folder. The original cross-market run was affected by the HTF fill-ordering
bug where 1h signal bars were processed through `PaperBroker` before the 1m tape.
US30 was partially re-run here after the fix, but the non-US30 rows in this
folder were not regenerated in-place.

## Current corrected hubs

Use these post-fix hubs instead:

| Market group | Corrected output | Notes |
|---|---|---|
| Futures: YM / MYM / NQ / MNQ | [`../futures_st_pmc_runner_variants/SUMMARY.md`](../futures_st_pmc_runner_variants/SUMMARY.md) | 1h bars are signal-only with `broker_fills=False`; resting orders fill on 1m bars. Fair 3R and 2R->10R rows are rankable. |
| NAS100 / FX / metals | [`../fx_index_metals_st_pmc_runner_variants/SUMMARY.md`](../fx_index_metals_st_pmc_runner_variants/SUMMARY.md) | Lot-correct audit hub. Fair 3R and 2R->10R rows are rankable; indefinite runners are not rankable as standard strategy rows. |
| US30 | [`../us30_st_pmc_runner_variants/SUMMARY.md`](../us30_st_pmc_runner_variants/SUMMARY.md) | Dedicated corrected US30 runner hub. |

## Corrected futures fair 3R snapshot

From
[`../futures_st_pmc_runner_variants/summary.csv`](../futures_st_pmc_runner_variants/summary.csv):

| Market | Units | Net $ | Stress | N/S | WR% |
|---|---:|---:|---:|---:|---:|
| `nq` | 679 | 349516.91 | -17038.45 | **20.51** | 38.3 |
| `mnq` | 342 | 23170.75 | -1195.44 | **19.38** | 42.7 |
| `ym` | 985 | 106425.46 | -6025.72 | **17.66** | 36.8 |
| `mym` | 496 | 6515.86 | -1365.50 | **4.77** | 40.3 |

## Corrected index/FX fair 3R snapshot

From
[`../fx_index_metals_st_pmc_runner_variants/summary.csv`](../fx_index_metals_st_pmc_runner_variants/summary.csv):

| Market | Units | Net $ | Stress | N/S | WR% |
|---|---:|---:|---:|---:|---:|
| `nas100` | 477 | 15219 | -778 | **19.56** | 41.9 |
| `gbpusd` | 1026 | 108058 | -13310 | **8.12** | 30.6 |
| `eurusd` | 866 | 64449 | -21432 | **3.01** | 29.0 |
| `xauusd` | 169 | 77327 | -92932 | **0.83** | 28.4 |

## Bug-fix note

The 2026-08-07 fix made HTF bars signal-only:

- `Engine.process_bar(..., broker_fills=False)` for 1h signal bars.
- Fill replay resolves resting orders only on the 1m tape.
- Regression coverage was added for the no-lookahead HTF signal path.

The stale rows in this directory are useful only for comparing pre-fix vs
post-fix behavior. They should not feed rankings, pitch decks, Strategy Tracker
tables, or promotion decisions.

## Historical artifacts in this folder

- `summary.csv` - mixed/stale pre-fix cross-market snapshot.
- `charts/INDEX.md` - historical trade charts from the original run.
- Driver: `live/st_pmc_1mfill_cross_market.py`.
