# US30 ST+PMC runner variants (1m fill tape)

Fair control vs dual-runner scaleouts on the same US30 1m path as `sl50_tp150_3r_1mfill`.

## Rules

- Stop 50 / regular TP 150 (TP1).
- Dual-runner campaigns enter **3 units**: TP1 + 2R runner + far runner.
- Both runners: stop → breakeven when TP1 fills.
- `2r_10r`: far runner target = **10× regular TP distance** (1500 pts).
- `2r_indef`: far runner has **no TP**; flatten at calendar year change; indefinite inventory does **not** block later campaigns.
- Charts draw stop + regular TP only (no 10R / indefinite TP lines); entry/exit markers only (no vertical lines).

## Fill-tape fix (2026-08-07)

Prior 1mfill replays incorrectly matched resting orders against **hourly** OHLC at the hour timestamp (lookahead within the hour). Replayed with `Engine.process_bar(1h, broker_fills=False)` so fills occur on true 1m touches.

## Results

| variant | net | stress | N/S | units | WR% | max_open | EOY flatten units | EOY by year |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `sl50_tp150_3r_1mfill` | $19028 | $-907 | 20.97 | 578 | 42.6 | 1 | 0 | {} |
| `sl50_tp150_runners_2r_10r` | $56111 | $-2867 | 19.57 | 1086 | 25.0 | 3 | 0 | {} |
| `sl50_tp150_runners_2r_indef` | $191517 | $-73531 | 2.60 | 1670 | 60.9 | 65 | 20 | {"2017": 2, "2018": 3, "2020": 2, "2021": 3, "2024": 6, "2025": 4} |

### Indefinite year-end inventory

EOY flatten closed **20** stacked runner units across **6** year-ends (peak **2024 = 6**). Max open during the run was **65**.



## Rankability (2026-08-08)

| Variant | Status |
|---|---|
| Fair 3R / max 1 | **Rankable** |
| 2R→10R / max 3 | **Rankable** |
| Indefinite | **Not rankable** on legacy FIFO net/stress — see [`LOT_CORRECT_ACCOUNTING.md`](LOT_CORRECT_ACCOUNTING.md) |

Legacy indefinite headline net/stress were contaminated by cross-trade FIFO while 65+ same-direction lots were open. Use lot-correct forced-flat + reachable stress only.

## Risk accounting (runner vs base)

Full MTM / protected-floor / realized / giveback / open-exposure:
[`RUNNER_RISK_ACCOUNTING.md`](RUNNER_RISK_ACCOUNTING.md) · [`RUNNER_RISK_ACCOUNTING.csv`](RUNNER_RISK_ACCOUNTING.csv)

| runner | Δ net vs base | base N/S | runner N/S (MTM) | N/S (floor) | Δ max units |
|---|---:|---:|---:|---:|---:|
| `2r_10r` | +$37.1k | 20.97 | 19.57 | 27.28 | +2 |
| `2r_indef` | +$172.5k | 20.97 | 2.60 | 2.19 | +64 |

## Artifacts

- Summary CSV: `summary.csv`
- States: `states/us30_hourly_st_pmc_<variant>/`
- Audits: `audits/`
- Charts: `live/state/st_pmc_1mfill_cross_market/charts/us30_runners_2r_10r/` and `…/us30_runners_2r_indef/`
- Runner: `live/us30_st_pmc_runner_variants.py`
