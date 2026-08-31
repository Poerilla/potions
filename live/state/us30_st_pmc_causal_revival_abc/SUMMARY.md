# US30 ST+PMC causal revival — paths A / B / C

Fresh strategies under completed-hour causality. **No inheritance** of retired fair-3R N/S 29.39. Locked 1m broker-realistic path; no exit/threshold sweep.

Control (reference only): completed-hour ST-limit sl50_tp150_runners_2r_10r from live/state/us30_st_pmc_runner_variants (N/S 1.47) — locked control, not re-run

## Results

| cell | path | net | stress | N/S | units | WR% | causal_ok | notes |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `path_a_prepost_pmc_3r` | A | $-6441 | $-6744 | -0.95 | 602 | 21.1 | yes | Path A: pre-posted PMC limit; fair 3R |
| `path_b_post_hour_pmc_retest_3r` | B | $-4994 | $-5356 | -0.93 | 578 | 21.8 | yes | Path B: post-hour PMC one-shot retest; expiry 240m; fair 3R |
| `path_c_continuation_break_3r` | C | $7302 | $-4261 | 1.71 | 5310 | 26.8 | yes | Path C: post-hour H/L break → next 1m market; fair 3R |
| `path_c_continuation_break_2r_10r` | C | $25371 | $-13783 | 1.84 | 5207 | 14.7 | yes | Path C + locked 2R→10R runner management cell |

| control_completed_hour_st_2r10r | ctrl | — | — | **1.47** | — | — | yes | completed-hour ST-limit sl50_tp150_runners_2r_10r from live/state/us30_st_pmc_runner_variants (N/S 1.47) — locked control, not re-run |

## Stance

- Research retain candidate(s): **path_c_continuation_break_2r_10r** (N/S 1.84). Still below demo bar unless forward evidence confirms; do not promote on this board alone.

- Demo decision for legacy book: see `live/state/us30_st_pmc_signal_hour_attribution/DEMO_DECISION.md` (alpha_status: invalidated).

Hub: `/home/tester/hsm/potions/live/state/us30_st_pmc_causal_revival_abc`

