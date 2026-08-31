# Structure-program ST — broker-like `scale_run` (NQ)

Plan **scale_run** risk=8 via StrategyPlugin `structure_program_st` + Engine/PaperBroker.
ST-flip mode: **fav_be** (favourable → BE hold; adverse → flatten). No EOD flatten.
Ladder: 5 @ +22 · 5 @ +50 · 5 @ +200. DSR **TRL-2026-00079**.

## Verdict

**FAILS broker gate.** Analytic +$2.03M / PF 9.6 → PaperBroker **−$102.6k / PF 0.70**.
Slightly less bad than split15-always (−$130k) but not promotable.

| metric | analytic `structure_sl_scale_run` | broker `scale_run` |
|---|---:|---:|
| trades | 325 | 228 |
| net $ | +2,032,875 | −102,568 |
| PF | 9.61 | 0.70 |
| win% | 49.8 | 7.9 (unit) |
| 200-pt runners | 64 trades | 20 units (`runner_tp`) |

## Unit exit PnL

| exit_reason   |   count |       sum |      mean |
|:--------------|--------:|----------:|----------:|
| st_flip       |    1365 | -198548   | -145.456  |
| risk_stop     |     585 | -106552   | -182.141  |
| be_stop       |    1200 |  -39800   |  -33.1667 |
| scale_22      |     155 |   67717.5 |  436.887  |
| runner_tp     |      20 |   79945   | 3997.25   |
| scale_50      |      95 |   94670   |  996.526  |

`st_flip` here is **adverse** flatten under fav_be (−$199k). Scale legs profitable but
swamped. Few runners survive broker friction / stop geometry.

## Artifacts

- `summary.csv`, `nq_scale_run_r8_metrics.csv`
- `states/nq_scale_run_r8/`
- Research path: `../structure_program_st/RESEARCH_PATH.md`
- Analytic hub: `../structure_program_st/structure_sl_scale_run/`

## Loss focus

Worst-100 charts + attribution: [`loss_charts/LOSS_FOCUS.md`](loss_charts/LOSS_FOCUS.md) · [`charts/`](loss_charts/charts/).
