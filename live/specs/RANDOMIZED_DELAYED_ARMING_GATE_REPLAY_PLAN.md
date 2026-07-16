# Randomized Delayed-Arming Gate Replay Plan

## Purpose

Test whether the prior-opposed ST+PMC gate is genuinely adding information, or whether the strong NQ/MNQ/ES/YM/MYM prior-opposed v2b results could be reproduced by any random delayed arming event with similar timing and trade frequency.

This must be a **true StrategyPlugin replay**, not a completed-trade resampling shortcut. The only thing that changes is the source of `dynamic_sizing_events`; the v2b strategy, order lifecycle, `Engine`, `PaperBroker`, slippage, fees, stop gap-through behavior, OCO handling, RTH filters, and `S_1_1_3` sizing must remain identical to the strict prior-opposed replay.

**2026-07-16:** existing null-control “real” nets compare against the **legacy hourly fill-stamp** NQ book (**$1,184,585**, timestamp-inflated). Re-run null families against **resting-limit hour-complete** (**$1,330,920**) before treating p-values as promotion evidence. Left-label resting-limit (**$1,321,745**) is diagnostic only.

## Implementation / First-Run Status

Implemented runner: [`../v2b_prior_opposed_random_gate_replay.py`](../v2b_prior_opposed_random_gate_replay.py).

The primary `stratified_event_count` allocator null has now been run at **200
true broker-like seeds** on every available 1m market: NQ, MNQ, YM, and MYM.
NQ used the restored long NQ 1m source,
`nq/raw/glbx-mdp3-20100606-20260616.ohlcv-1m.dbn.zst`, while retaining the same
2021-03-04 common-window regime support used by the banked strict replay. MNQ
used the local 2021-start 1m CSV fallback. YM and MYM used their available 1m
DBNs. ES is blocked until
`es/raw/glbx-mdp3-20100606-20260425.ohlcv-1m.dbn.zst` is restored.

Output: [`../state/v2b_prior_opposed_random_gate_replays/INDEX.md`](../state/v2b_prior_opposed_random_gate_replays/INDEX.md).

Primary result:

| Market | Null method | Seeds | Gate events | Median net | P95 net | Best net | Median fills | Real strict net | Real fills | p(null >= real) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NQ | `stratified_event_count` | 200 | 332 | $11,756.25 | $184,135.62 | $308,293.75 | 171 | $1,184,585.00 | 352 | 0.0050 |
| MNQ | `stratified_event_count` | 200 | 331 | -$231.25 | $16,137.88 | $31,681.50 | 172 | $113,547.50 | 353 | 0.0050 |
| YM | `stratified_event_count` | 200 | 375 | -$42,777.50 | $24,352.81 | $95,548.75 | 191 | $320,190.00 | 347 | 0.0050 |
| MYM | `stratified_event_count` | 200 | 368 | -$5,878.19 | $713.76 | $3,180.25 | 188 | $26,053.62 | 333 | 0.0050 |

Read: the primary stratified random delayed-gate null does **not** reproduce the
real strict prior-opposed edge in any available market. Across NQ, MNQ, YM, and
MYM, no seed matched or exceeded the real strict replay; causality violations
were **0** in every null summary. Secondary 200-seed runs for
`unconstrained_event_count` and `shuffled_stpmc_side` remain pending, except
for the initial NQ smoke rows.

## Core Principle

The randomized gate should enter the existing v2b plugin through the exact same contract as the real gate:

```json
{
  "dynamic_sizing_events": {
    "YYYY-MM-DD": [
      {"ts": "YYYY-MM-DDTHH:MM:SS-05:00", "side": "long"}
    ]
  },
  "prior_opposite_only": true,
  "prior_opposite_entry_qty": 5,
  "prior_opposite_tp1_qty": 1,
  "prior_opposite_tp2_qty": 1
}
```

Side semantics are already tested in `live/tests/test_v2b_prior_opposed_execution_scrutiny.py`: a random event with `side = "short"` can arm a later **Long** v2b entry; a random event with `side = "long"` can arm a later **Short** v2b entry.

## Existing Code To Reuse

- Strict replay driver: `live/nq_v2b_prior_opposed_replay.py`
- v2b plugin gate contract: `live/strategies/v2b_scaleout.py`
- Market/bar loading: `live/v2b_strategy_cross_market_replay.py`
- Existing strict outputs:
  - `live/state/nq_v2b_prior_opposed_stpmc_broker_like/`
  - `live/state/mnq_v2b_prior_opposed_stpmc_broker_like/`
  - `live/state/es_v2b_prior_opposed_stpmc_broker_like/`
  - `live/state/ym_v2b_prior_opposed_stpmc_broker_like/`
  - `live/state/mym_v2b_prior_opposed_stpmc_broker_like/`
- Execution scrutiny helpers: `live/v2b_prior_opposed_execution_scrutiny.py`
- Robustness campaign files: `live/state/*_v2b_prior_opposed_stpmc_broker_like/robustness_audit/campaigns_robustness.csv`
- Scorecard output to update after nulls: `live/state/strategy_validation_scorecard/`

## Non-Negotiable Anti-Leakage Rules

1. Random gates must be generated from timestamps and features known **before** the random event timestamp.
2. Random event construction must not inspect future v2b trade outcome, campaign net, MFE, MAE, TP/stop outcome, or EOD result.
3. Seed lists must be fixed before looking at null results.
4. The real strategy and every null run must use the same broker realism defaults.
5. Primary nulls should match **gate-event count**, not filled-campaign count. Filled-campaign-count matching is allowed only as a secondary diagnostic because it conditions on whether the random gate caused a fill.
6. Null rows are `CONTROL_NULL` in the DSR ledger and do not count toward strategy-search `N_eff`.

## Null Families

### 1. Unconstrained Random Delayed Gate

Goal: answer, "Does any random causal same-session arming event work?"

Construction:

- Build an eligible event universe from each market's 1m RTH bars.
- Include sessions that pass the same regime date and full-RTH-session filters as the strict replay.
- Candidate timestamps: completed 1m bar close times from RTH open through a conservative late-entry cutoff, e.g. `09:30` to `15:30` New York time. Starting at `09:30` is intentional because the real ST+PMC gate can be known before v2b becomes order-active; the unchanged v2b plugin still controls when an entry order can actually arm and fill.
- Candidate sides: `long` and `short`, with side sampled to match the real gate-side distribution for that market.
- For each seed, sample the same number of gate events as the real strict replay's gate events.
- Replay the unchanged v2b plugin using these random events.

Primary comparison:

- Real strict replay vs distribution of random-event-count replays.

### 2. Stratified Random Delayed Gate

Goal: answer, "Does the real gate still beat random timing after matching the obvious timing and volatility structure?"

Strata:

- `year`
- intended v2b side, not gate side
- time-of-day bucket
- OR-width quartile

Recommended initial time buckets:

- `09:45-10:30`
- `10:30-12:00`
- `12:00-14:00`
- `14:00-15:30`

Construction:

- Derive the real gate profile from actual strict campaigns and their matched prior gate events.
- For each stratum, draw the same number of random gate events from the eligible universe.
- If a stratum has insufficient candidates, sample with replacement and emit `STRATIFIED_WITH_REPLACEMENT_WARNING`.
- If a stratum has zero candidates, merge the nearest time bucket in the same year / side / OR-width quartile and emit `STRATUM_MERGE_WARNING`.

Primary comparison:

- Real strict replay vs stratified null distribution for net, Sharpe, Sortino, Calmar, PF, stress DD, win rate, and downside capture.

### 3. Shuffled ST+PMC Side Labels

Goal: isolate whether the **opposite-side relationship** matters more than merely having an ST+PMC event.

Construction:

- Keep the real ST+PMC event timestamps.
- Randomly permute or flip event sides within year and time bucket.
- Replay the unchanged v2b plugin.

Interpretation:

- If shuffled labels perform close to real, the side/opposition logic is suspect.
- If real strongly beats shuffled, the direction relationship has evidence.

### 4. Calendar / Simple-Signal Benchmarks

These are not nulls; they are simple unrelated gates.

Examples:

- Prior-day return sign quota gate.
- Opening gap sign quota gate.
- Day-of-week / time-bucket quota gate.
- Randomized fixed-time gates, e.g. one gate at a sampled time bucket per eligible day.

Interpretation:

- These answer whether a very simple, non-ST+PMC timing rule captures the same effect.

### 5. Fill-Count-Matched Diagnostic

Goal: answer the user's specific "same amount of trades" question while being honest about conditioning.

Construction:

- Generate random event streams, replay them, and keep only seeds whose filled campaign count is within tolerance of the real campaign count, e.g. `real_count +/- 2%`.
- Do **not** filter by PnL, PF, drawdown, win rate, or any outcome metric other than fill count.

Interpretation:

- Useful for trade-frequency-normalized comparison.
- Secondary only, because fill-count matching is partly post-signal conditioning.

## Implementation Plan

### Phase 0 - Refactor Strict Replay For Reuse

Add a new module:

- `live/v2b_prior_opposed_random_gate_replay.py`

Refactor or wrap `live/nq_v2b_prior_opposed_replay.py` so we can call:

```python
run_v2b_delayed_gate_replay(
    market="nq",
    output_root=...,
    strategy_id=...,
    dynamic_sizing_events=random_events,
    start=date(2021, 3, 4),
    dbn_path=None,
    keep_state=False,
)
```

Requirements:

- Real replay behavior remains unchanged.
- Existing CLI output for `nq_v2b_prior_opposed_replay.py` remains stable.
- The wrapper returns the same summary fields as the strict replay.
- For random batches, preserve run manifests and event files even if state folders are deleted to save disk.

### Phase 1 - Build Eligible Event Universe

Output:

- `live/state/v2b_prior_opposed_random_gate_replays/event_universe/{market}_eligible_events.csv`

Columns:

- `market`
- `instrument`
- `session`
- `year`
- `ts`
- `time_bucket`
- `candidate_gate_side`
- `intended_v2b_side`
- `or_width_pts`
- `or_width_quartile`
- `atr14` where available
- `atr14_quartile` where available
- `is_full_rth_session`
- `regime_ok`

Rules:

- Use the same `_regime_dates` and `_has_full_rth_close` logic as the strict replay.
- Compute OR width from the same first-15-minute 1m bars used by the plugin.
- Candidate `ts` values must be completed 1m bars.
- Candidate event side is opposite the intended v2b side.

### Phase 2 - Build Real Gate Profile

Output:

- `live/state/v2b_prior_opposed_random_gate_replays/real_gate_profile/{market}_real_gate_profile.csv`

Columns:

- `market`
- `campaign_id`
- `session`
- `year`
- `v2b_side`
- `gate_side`
- `gate_ts`
- `v2b_order_active_ts`
- `v2b_entry_ts`
- `time_bucket`
- `or_width_pts`
- `or_width_quartile`
- `net_usd`

Primary anti-leakage profile: use the **full same-session ST+PMC event tape** that falls inside the eligible random-gate universe, not only ST+PMC events that later produced filled v2b campaigns. This matches the information available to the live gate before knowing whether a v2b fill will occur.

Secondary campaign-matched profile: use existing actual strict fills plus ST+PMC fills. The matching rule is the same as execution scrutiny: latest same-session opposite ST+PMC event strictly before v2b order active time. This profile is useful for explanation and fill-count diagnostics, but it is not the primary null because it conditions on a realized campaign.

### Phase 3 - Seeded Event Generation

Output:

- `live/state/v2b_prior_opposed_random_gate_replays/generated_events/{market}/{method}/seed_000001_events.json`
- `live/state/v2b_prior_opposed_random_gate_replays/generated_events/{market}/{method}/seed_000001_events.csv`

Methods:

- `unconstrained_event_count`
- `stratified_event_count`
- `shuffled_stpmc_side`
- `simple_gap_sign`
- `simple_prior_day_return`
- `fill_count_matched_diagnostic`

All generators must accept:

- `--seed`
- `--market`
- `--start`
- `--iterations`
- `--method`
- `--target-profile`

### Phase 4 - Batch Replay

Run order:

1. Smoke: `NQ`, `unconstrained_event_count`, 5 seeds.
2. Smoke: `NQ`, `stratified_event_count`, 5 seeds.
3. NQ common-window: 200 seeds per primary method.
4. MNQ common-window: 200 seeds per primary method.
5. ES/YM/MYM common-window: 200 seeds per primary method.
6. Final allocator run: 2,000 seeds per market/method.
7. Optional long-history NQ run after common-window results are stable.

Output:

- `live/state/v2b_prior_opposed_random_gate_replays/results/{market}/{method}/run_manifest.csv`
- `live/state/v2b_prior_opposed_random_gate_replays/results/{market}/{method}/summary_by_seed.csv`
- `live/state/v2b_prior_opposed_random_gate_replays/results/{market}/{method}/null_distribution.csv`

`summary_by_seed.csv` columns:

- `seed`
- `method`
- `market`
- `gate_events`
- `filled_campaigns`
- `units`
- `net_usd`
- `closed_dd_usd`
- `intrabar_stress_dd_usd`
- `win_rate_pct`
- `profit_factor`
- `net_over_stress`
- `sharpe`
- `sortino`
- `calmar`
- `qqq_corr`
- `qqq_downside_capture`
- `bar_safe_count`
- `same_1m_ambiguous_count`
- `pre_arm_touch_count`
- `no_later_touch_count`
- `state_retained`
- `events_path`

State retention:

- Keep full state for real replay, smoke runs, and the top/bottom 5 seeds by net/PF/drawdown.
- For all other random seeds, delete bulky state folders after extracting summaries.

### Phase 5 - Statistical Report

Output:

- `live/state/v2b_prior_opposed_random_gate_replays/INDEX.md`
- `live/state/v2b_prior_opposed_random_gate_replays/{market}/INDEX.md`
- `live/state/v2b_prior_opposed_random_gate_replays/{market}/{method}/REPORT.md`
- charts:
  - net distribution vs real
  - Sharpe distribution vs real
  - PF distribution vs real
  - stress DD distribution vs real
  - filled-campaign count distribution
  - event-to-fill efficiency
  - latency-risk distribution

Metrics:

- One-sided p-value: `P(null_metric >= real_metric)` for net, PF, Sharpe, Sortino, Calmar.
- One-sided p-value: `P(null_drawdown <= real_drawdown)` for drawdown efficiency if using absolute drawdown.
- Percentile rank of real inside the null distribution.
- Median / P5 / P95 for each null metric.
- Effect size: `(real - null_median) / null_iqr`.

Use +1 p-value smoothing:

```text
p = (count(null >= real) + 1) / (iterations + 1)
```

## Pass / Fail Interpretation

This is not a single binary test, but the following thresholds are useful:

- **Strong gate evidence:** real result is above the 95th percentile on net and Sharpe/Sortino across both unconstrained and stratified nulls, with p <= 0.05 and no hidden increase in stress.
- **Moderate evidence:** real beats unconstrained nulls but only partially beats stratified nulls; gate may be exploiting time/volatility structure more than ST+PMC content.
- **Weak evidence:** real sits inside the 25th-75th percentile of stratified random nulls.
- **Failure / overfit concern:** random stratified gates match or exceed real on net and risk-adjusted metrics, or shuffled ST+PMC side labels perform similarly to the real opposition logic.

## DSR / Scorecard Integration

After the run:

- Add each random-gate method as `CONTROL_NULL` rows in `data/validation/dsr_trial_ledger.csv`.
- Keep `counts_toward_dsr = FALSE` and `dsr_exclusion_reason = CONTROL_NULL`.
- Update `live/state/strategy_validation_scorecard/SCORECARD_REPORT.md` with real-vs-null p-values.
- Replace the current sampling-control note in `mnq/case_studies/STRATEGY_TRACKER.md` with true delayed-arming null results.

## Tests

Unit tests:

- Generated events are reproducible for a fixed seed.
- Event timestamps are in RTH, after OR completion, before the late-entry cutoff, and on regime/full-RTH sessions.
- Event side correctly maps to intended v2b side.
- `stratified_event_count` matches real counts by year / side / time bucket / OR-width quartile where candidates exist.
- Stratum replacement and merge warnings are emitted deterministically.
- The replay wrapper produces identical results to the existing strict replay when passed the real ST+PMC events.
- No random generator reads `net_usd`, `exit_reasons`, `campaign_mae_usd`, `campaign_mfe_usd`, `hit_tp1`, `hit_tp2`, `runner_stop`, or `wide_stop`.

Integration tests:

- NQ 5-seed smoke produces all expected output files.
- `summary_by_seed.csv` can regenerate the same event files and replay summaries from seed.
- State retention policy keeps smoke/top/bottom states and deletes non-retained bulk states.
- Scorecard generator ingests the null output and displays p-values.

## First Commands To Target

Smoke:

```bash
python -m live.v2b_prior_opposed_random_gate_replay \
  --market nq \
  --method unconstrained_event_count \
  --iterations 5 \
  --output-root live/state/v2b_prior_opposed_random_gate_replays
```

NQ common-window primary:

```bash
python -m live.v2b_prior_opposed_random_gate_replay \
  --market nq \
  --method stratified_event_count \
  --iterations 200 \
  --output-root live/state/v2b_prior_opposed_random_gate_replays \
  --resume \
  --prune-state \
  --workers 4
```

Primary all-market stratified batch:

```bash
python -m live.v2b_prior_opposed_random_gate_replay \
  --markets nq,mnq,ym,mym,es \
  --methods stratified_event_count \
  --iterations 200 \
  --output-root live/state/v2b_prior_opposed_random_gate_replays \
  --resume \
  --prune-state \
  --skip-missing \
  --workers 4
```

Secondary all-market batch:

```bash
python -m live.v2b_prior_opposed_random_gate_replay \
  --markets nq,mnq,ym,mym,es \
  --methods unconstrained_event_count,shuffled_stpmc_side \
  --iterations 200 \
  --output-root live/state/v2b_prior_opposed_random_gate_replays \
  --resume \
  --prune-state \
  --skip-missing \
  --workers 4
```

## Expected Outcome

The current sampling control is already supportive, but it is not enough. This plan upgrades the evidence from "completed-campaign sampling says the result is unusual" to "the same live-orderable StrategyPlugin cannot be reproduced by causal random delayed gates under identical broker realism." That is the version an allocator can scrutinize without immediately dismissing it as post-hoc tape selection.
