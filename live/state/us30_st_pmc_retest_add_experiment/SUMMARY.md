# US30 ST+PMC 50/150 — retest / BB-add experiment

Baseline vs classic retest-add vs **favourable 1m Bollinger-touch adds**.

BB add rules: long touches lower band / short touches upper band; price already
in favor; BB mid sloping favorably; add SL = original entry; inherit main TP;
max 3 adds. Main trade stays SL50/TP150.

`sl50_tp150_3r_1mfill` is the fair control (same 1m fill tape as BB adds).

| Variant | Units | Trades | Net $ | Stress | N/S | WR% | Max open |
|---|---:|---:|---:|---:|---:|---:|---:|
| `sl50_tp150_3r` | 1074 | 1074 | 12145.85 | -3108.6 | 3.907 | 31.8 | 1 |
| `sl50_tp150_3r_retest_add` | 1369 | 1369 | 12708.58 | -3108.6 | 4.088 | 30.8 | 2 |
| `sl50_tp150_3r_retest_add_x5` | 1546 | 1546 | 12546.74 | -3653.0 | 3.435 | 30.1 | 6 |
| `sl50_tp150_3r_1mfill` | 1197 | 1197 | 20383.83 | -1970.88 | 10.343 | 34.6 | 1 |
| `sl50_tp150_3r_bb_add_x3` | 1872 | 1872 | 15720.81 | -2544.3 | 6.179 | 31.5 | 4 |

**Read (2026-07-30):** BB-add improves on hourly-only (N/S 6.18 vs 3.91) but
**hurts vs the fair 1m-fill control** (10.34). Live demos now run the fair
control: `fill_tape=1m`, no BB/retest adds, `max_contracts=1`.
Cross-market 1mfill: [`../st_pmc_1mfill_cross_market/SUMMARY.md`](../st_pmc_1mfill_cross_market/SUMMARY.md).
