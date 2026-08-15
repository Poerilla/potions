# US30 ST+PMC 50/150 — retest / BB-add experiment

Baseline vs classic retest-add vs **favourable 1m Bollinger-touch adds**.

BB add rules: long touches lower band / short touches upper band; price already
in favor; BB mid sloping favorably; add SL = original entry; inherit main TP;
max 3 adds. Main trade stays SL50/TP150.

| Variant | Units | Trades | Net $ | Stress | N/S | WR% | Max open |
|---|---:|---:|---:|---:|---:|---:|---:|
| `sl50_tp150_3r` | 1074 | 1074 | 12145.85 | -3108.6 | 3.907 | 31.8 | 1 |
| `sl50_tp150_3r_retest_add` | 1369 | 1369 | 12708.58 | -3108.6 | 4.088 | 30.8 | 2 |
| `sl50_tp150_3r_retest_add_x5` | 1546 | 1546 | 12546.74 | -3653.0 | 3.435 | 30.1 | 6 |
| `sl50_tp150_3r_1mfill` | 578 | 578 | 19027.57 | -907.27 | 20.972 | 42.6 | 1 |
| `sl50_tp150_3r_bb_add_x3` | 1101 | 1101 | 23177.02 | -1569.94 | 14.763 | 39.9 | 4 |

Live demos run **fair-control** (`bb_add_enabled=False`, `max_contracts=1`) —
same 50/150 1mfill path; BB-add is research-only (hurts N/S vs control).

**2026-08-07 fill-tape fix:** 1mfill rows above were regenerated with HTF
`broker_fills=False` (no hourly OHLC lookahead). Prior 1mfill N/S≈10.3 / 1197
units was inflated by same-hour premature fills; corrected fair control is
**578 units, N/S≈20.97**.
