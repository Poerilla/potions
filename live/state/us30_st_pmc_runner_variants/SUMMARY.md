# US30 ST+PMC runner variants (1m fill tape)

Fair control vs dual-runner scaleouts on the same US30 1m path as `sl50_tp150_3r_1mfill`.

> **2026-08 completed-hour causality fix.** The shared hourly resampler is left-labeled, so a bar timestamped 11:00 contains 11:00-11:59 data. This replay now shifts signal bars to the completed-hour timestamp before the strategy can consume them, and fills only on the 1m tape. The old positive 3R baseline is superseded by the table below.

## Rules

- Stop 50 / regular TP 150 (TP1).
- Dual-runner campaigns enter **3 units**: TP1 + 2R runner + far runner.
- Both runners: stop → breakeven when TP1 fills.
- `2r_10r`: far runner target = **10× regular TP distance** (1500 pts).
- `2r_indef`: far runner has **no TP**; flatten at calendar year change; indefinite inventory does **not** block later campaigns.
- Charts draw stop + regular TP only (no 10R / indefinite TP lines).

## Results

| variant | net | stress | N/S | units | WR% | max_open | EOY flatten units | EOY by year |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `sl50_tp150_3r_1mfill` | $-982 | $-4599 | -0.21 | 1017 | 25.7 | 1 | 0 | {} |
| `sl50_tp150_runners_2r_10r` | $13340 | $-9066 | 1.47 | 1908 | 14.6 | 3 | 0 | {} |
| `sl50_tp150_runners_2r_indef` | $9171 | $-34332 | 0.27 | 3051 | 15.0 | 77 | 16 | {"2017": 2, "2020": 1, "2021": 2, "2023": 1, "2024": 5, "2025": 5} |

## Artifacts

- Summary CSV: `summary.csv`
- Causality/fill audit: `CAUSALITY_AUDIT.md` and `causality_fill_audit.csv`
- States: `states/us30_hourly_st_pmc_<variant>/`
- Audits: `audits/`
- Runner: `live/us30_st_pmc_runner_variants.py`
