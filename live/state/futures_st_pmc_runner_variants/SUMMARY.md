# Futures ST+PMC runner variants (1m fill tape)

Markets: YM / MYM / NQ / MNQ. Same dual-runner rules as US30 runner hub.

## Fill timing

1h bars are **signal-only** (`broker_fills=False`); resting limits fill on the **1m** tape.

## Results

| market | variant | net | stress | N/S | units | WR% | max_open | EOY units | EOY by year |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `mnq` | `sl50_tp150_3r_1mfill` | $23171 | $-1195 | 19.38 | 342 | 42.7 | 1 | 0 | {} |
| `mnq` | `sl50_tp150_runners_2r_10r` | $49899 | $-4953 | 10.07 | 627 | 24.2 | 3 | 0 | {} |
| `mnq` | `sl50_tp150_runners_2r_indef` | $96683 | $-52542 | 1.84 | 987 | 56.4 | 45 | 6 | {"2023": 1, "2024": 4, "2025": 1} |
| `mym` | `sl50_tp150_3r_1mfill` | $6516 | $-1366 | 4.77 | 496 | 40.3 | 1 | 0 | {} |
| `mym` | `sl50_tp150_runners_2r_10r` | $20600 | $-4468 | 4.61 | 1020 | 24.2 | 3 | 0 | {} |
| `mym` | `sl50_tp150_runners_2r_indef` | $53167 | $-31777 | 1.67 | 1448 | 59.0 | 46 | 13 | {"2020": 2, "2021": 2, "2024": 5, "2025": 3, "2026": 1} |
| `nq` | `sl50_tp150_3r_1mfill` | $349517 | $-17038 | 20.51 | 679 | 38.3 | 1 | 0 | {} |
| `nq` | `sl50_tp150_runners_2r_10r` | $775763 | $-58524 | 13.26 | 876 | 24.2 | 3 | 0 | {} |
| `nq` | `sl50_tp150_runners_2r_indef` | $4573429 | $-1948591 | 2.35 | 1929 | 61.3 | 137 | 41 | {"2011": 7, "2014": 6, "2015": 3, "2018": 3, "2019": 2, "2020": 6, "2021": 8, "2023": 1, "2024": 4, "2025": 1} |
| `ym` | `sl50_tp150_3r_1mfill` | $106425 | $-6026 | 17.66 | 985 | 36.8 | 1 | 0 | {} |
| `ym` | `sl50_tp150_runners_2r_10r` | $313302 | $-21424 | 14.62 | 1734 | 22.2 | 3 | 0 | {} |
| `ym` | `sl50_tp150_runners_2r_indef` | $970818 | $-715046 | 1.36 | 2857 | 59.0 | 108 | 28 | {"2011": 2, "2012": 2, "2014": 5, "2016": 2, "2017": 2, "2020": 2, "2021": 3, "2024": 8, "2025": 2} |


## Rankability (2026-08-08)

| Variant | Status |
|---|---|
| Fair 3R / max 1 | **Rankable** |
| 2R→10R / max 3 | **Rankable** |
| Indefinite (45–137 open) | **Not rankable** until lot-correct forced-flat — [`LOT_CORRECT_ACCOUNTING.md`](LOT_CORRECT_ACCOUNTING.md) |

NQ indefinite legacy +$4.57M / N/S 2.35 is **invalid** (cross-trade FIFO). 3R and 2R→10R remain the real candidates.

## Risk accounting

MTM / protected-floor / realized / giveback / open-exposure (runner vs base):
[`RUNNER_RISK_ACCOUNTING.md`](RUNNER_RISK_ACCOUNTING.md)

## Artifacts

- `summary.csv`
- `RUNNER_RISK_ACCOUNTING.md` / `.csv`
- Per market: `<market>/states/`, `<market>/audits/`
- Runner: `live/futures_st_pmc_runner_variants.py`

