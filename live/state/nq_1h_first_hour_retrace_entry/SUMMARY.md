# NQ first-hour follow — MAE + retracement entries

Diagnostic only (5m walk). Not a promotion gate.

Universe: NQ RTH first hour 09:30–10:30; follow candle direction.
Base: entry at FH **close**, SL at FH **open**, TP = 3× body, flatten 16:00.
Retrace books: limit at `close − ret×body` (long) / `close + ret×body` (short);
SL = candle **low/high**; R = |entry−SL|; TP = 3R. Miss if limit never tagged (or SL swept first).

## Base close-entry MAE (path until exit)

| Metric | Value |
|---|---:|
| n | 3968 |
| mae_px_median | 12.750 |
| mae_px_p75 | 32.812 |
| mae_px_p90 | 70.975 |
| mae_body_median | 1.000 |
| mae_body_p75 | 1.224 |
| mae_body_p90 | 1.816 |
| mae_range_median | 0.320 |
| mae_range_p75 | 0.533 |
| mae_range_p90 | 0.731 |
| frac_mae_ge_032 | 0.805 |
| frac_mae_ge_050 | 0.720 |
| frac_mae_ge_072 | 0.633 |
| frac_tagged_open | 0.543 |
| frac_tagged_extreme | 0.089 |
| wins_mae_body_median | 0.328 |
| losses_mae_body_median | 1.147 |

Read: `frac_mae_ge_032` = share of base trades whose adverse path ≥ 32% of body
(i.e. price *would have* tagged a 32% retrace limit).

## Books

| Book | n | fill% | WR | avg $ | net | stress | N/S | PF | avg R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| close entry 3×body (base) | 3968 | — | 38.2% | $61 | $243,008 | $26,076 | 9.32 | 1.19 | nan |
| retrace body 32% → SL extreme → 3R | 3204 | 81% | 41.0% | $41 | $131,196 | $74,606 | 1.76 | 1.10 | 0.05 |
| retrace body 50% → SL extreme → 3R | 2878 | 73% | 38.8% | $35 | $101,120 | $65,512 | 1.54 | 1.10 | 0.05 |
| retrace body 72% → SL extreme → 3R | 2522 | 64% | 36.4% | $44 | $110,780 | $49,914 | 2.22 | 1.14 | 0.07 |
| retrace range 32% → SL extreme → 3R | 3360 | 85% | 39.6% | $-23 | $-77,768 | $169,097 | -0.46 | 0.95 | -0.07 |
| retrace range 50% → SL extreme → 3R | 2852 | 72% | 36.3% | $14 | $40,127 | $101,532 | 0.40 | 1.04 | -0.03 |
| retrace range 72% → SL extreme → 3R | 2189 | 55% | 32.3% | $35 | $75,646 | $28,604 | 2.64 | 1.14 | 0.06 |

## Stance

Research / diagnostic. Promote only after broker-like Engine+PaperBroker rebuild.

Hub: `/home/tester/hsm/potions/live/state/nq_1h_first_hour_retrace_entry`
