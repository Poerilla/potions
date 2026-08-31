# Completed-hour ST+PMC → live/demo + prior-opposed impact

Date: 2026-08-23

## What changed in research ST+PMC

Left-labeled hourly bars (`ts=HH:00` spans HH:00–HH:59) are now shifted to the
**hour-complete** timestamp before the strategy consumes them
(`_replay_hourly_with_1m`). Fills only on the 1m tape.

## Live / demo ST+PMC

| Book | Impact |
|------|--------|
| US30 / NAS100 / EURUSD ST+PMC paper+OANDA | **Structurally causal already.** `HourlyBarAggregator` emits only at minute `:59` after the 1m bar is processed, then 1h is signal-only (`broker_fills=False`). Fill opportunity starts on the next hour's 1m tape. Ranking notes on US30 already cite completed-hour causal N/S. |
| Optional parity gap | Live still stamps `bar.ts` / `live_after_ts` at the left label. Research now stamps hour-complete. Does not create intrabar lookahead in the live loop, but research seed + gate math must not double-add +1h. |
| US30 London prior-opposed demo | **Research seed fixed** (`st_signal_stamp=completed_hour`) so completed-hour US30 ST orders do not get `live_after+1h` twice. Live sibling ST fill feed unchanged (wall-clock fill ts). |
| NAS100/SPX500 ungated v2b | **Unaffected** (no ST+PMC gate). |

No ST+PMC daemon restart required for the causal emission path.

## Prior-opposed v2b (research)

Prior-opposed **gates on ST+PMC entry limits**. Legacy gate tapes under
`hourly_st_pmc_strategyplugin_variants_cross_market/` were built with
hourly-only (non completed-hour / non-1m-fill) ST replay.

| Market | Prior-opposed status | Action |
|--------|----------------------|--------|
| **NQ** | Promotion resting-limit baseline | Regenerate ST `sl25_tp75_3r` completed-hour → rerun resting_limit with `--st-signal-stamp completed_hour` |
| **YM** | Resting-limit hub present | Same |
| **ES** | Legacy broker_like only; resting-limit blocked | **Blocked** — `es/raw/...ohlcv-1m.dbn.zst` missing |
| **MES** | Not in `PRIOR_OPPOSED_MARKETS`; no hub | **Blocked** — `mes_1min_raw.csv` missing; not wired in driver |

Gate math: with completed-hour ST, `resting_limit` must use
`--st-signal-stamp completed_hour` (availability = `live_after_ts`, no second +1h).

## Artifacts

- ST gate tapes: `live/state/hourly_st_pmc_sl25_completed_hour/{nq,ym}/`
- Prior-opposed: `live/state/{nq,ym}_v2b_prior_opposed_stpmc_resting_limit/`
- Progress: `STATUS.txt` / `chain.log`
