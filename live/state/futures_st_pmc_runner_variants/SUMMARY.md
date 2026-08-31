# Futures ST+PMC runner variants (1m fill tape)

Markets: YM / MYM / NQ / MNQ. Same dual-runner rules as US30 runner hub.

> **2026-08 completed-hour causality fix.** The shared hourly resampler is left-labeled, so a bar timestamped 11:00 contains 11:00-11:59 data. This replay shifts signal bars to the completed-hour timestamp before the strategy can consume them, and fills only on the 1m tape.

## Fill timing

1h bars are **signal-only** (`broker_fills=False`); resting limits fill on the **1m** tape.

## Results

| market | variant | net | stress | N/S | units | WR% | max_open | EOY units | EOY by year |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| `mnq` | `sl50_tp150_3r_1mfill` | $1995 | $-4809 | 0.41 | 606 | 26.6 | 1 | 0 | {} |
| `mnq` | `sl50_tp150_runners_2r_10r` | $10938 | $-12752 | 0.86 | 1104 | 14.9 | 3 | 0 | {} |
| `mnq` | `sl50_tp150_runners_2r_indef` | $3170 | $-43787 | 0.07 | 1818 | 14.7 | 56 | 8 | {"2023": 2, "2024": 4, "2025": 2} |
| `mym` | `sl50_tp150_3r_1mfill` | $-1617 | $-2414 | -0.67 | 884 | 25.2 | 1 | 0 | {} |
| `mym` | `sl50_tp150_runners_2r_10r` | $1961 | $-4871 | 0.40 | 1812 | 14.8 | 3 | 0 | {} |
| `mym` | `sl50_tp150_runners_2r_indef` | $-445 | $-14955 | -0.03 | 2652 | 14.1 | 51 | 11 | {"2020": 1, "2023": 1, "2024": 5, "2025": 3, "2026": 1} |
| `nq` | `sl50_tp150_3r_1mfill` | $27572 | $-59228 | 0.47 | 1128 | 26.0 | 1 | 0 | {} |
| `nq` | `sl50_tp150_runners_2r_10r` | $259027 | $-154948 | 1.67 | 1509 | 14.9 | 3 | 0 | {} |
| `nq` | `sl50_tp150_runners_2r_indef` | $149663 | $-1313831 | 0.11 | 3468 | 16.2 | 190 | 51 | {"2011": 12, "2012": 3, "2014": 5, "2015": 3, "2017": 3, "2018": 3, "2019": 2, "2020": 4, "2021": 8, "2023": 2, "2024": 4, "2025": 2} |
| `ym` | `sl50_tp150_3r_1mfill` | $-33986 | $-44938 | -0.76 | 1762 | 24.0 | 1 | 0 | {} |
| `ym` | `sl50_tp150_runners_2r_10r` | $17436 | $-62550 | 0.28 | 3063 | 13.8 | 3 | 0 | {} |
| `ym` | `sl50_tp150_runners_2r_indef` | $-64974 | $-436359 | -0.15 | 5301 | 13.9 | 143 | 25 | {"2011": 4, "2012": 2, "2014": 3, "2016": 2, "2017": 2, "2020": 1, "2021": 1, "2023": 1, "2024": 7, "2025": 2} |

## Risk accounting

MTM / protected-floor / realized / giveback / open-exposure (runner vs base):
[`RUNNER_RISK_ACCOUNTING.md`](RUNNER_RISK_ACCOUNTING.md)

## Artifacts

- `summary.csv`
- `RUNNER_RISK_ACCOUNTING.md` / `.csv`
- Per market: `<market>/states/`, `<market>/audits/`
- Runner: `live/futures_st_pmc_runner_variants.py`

