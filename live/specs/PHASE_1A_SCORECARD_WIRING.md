# Phase 1a — Scorecard + Null CSV Wiring (implementation spec)

**Status:** Ready to implement (blocked in plan-mode session; apply in agent mode)  
**Target:** [`scripts/generate_strategy_validation_scorecard.py`](../../scripts/generate_strategy_validation_scorecard.py)

## Goals

1. Primary null = **200-seed stratified gate replay** (not campaign sampling control).
2. **Campaign-level PSR/DSR** as headline inference; daily equity Sharpe secondary.
3. Regenerated `IMPLEMENTATION_STATUS.md` reflects gate null PASS.
4. Optional chart: `charts/gate_null_nq_net.png`.

## Constants (add after `PEER_PATH`)

```python
GATE_NULL_ROOT = ROOT / "live/state/v2b_prior_opposed_random_gate_replays/results"
PRIMARY_NULL_METHOD = "stratified_event_count"
GATE_NULL_MARKETS = ("nq", "mnq", "ym", "mym")
NQ_PRIOR_OPPOSED_UNIT_TRADES = ROOT / "live/state/nq_v2b_prior_opposed_stpmc_broker_like/states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3/unit_trades.csv"
COMMON_WINDOW_YEARS = 5.0
```

## New helpers

- `format_pvalue_disclosure(p_value, metric_name)`
- `campaign_pnl_series(path)` → `groupby trade_id sum net_usd`
- `campaign_sharpe_ratio(series, span_years=5.0)` → annualized via `sqrt(campaigns/year)`
- `@dataclass GateNullMarket` — per-market null stats from `summary_by_seed.csv` vs `summary.csv`
- `load_primary_gate_nulls()` — iterate `GATE_NULL_MARKETS`

Empirical p-value: `(sum(null_net >= real_net) + 1) / (n + 1)`.

## `main()` changes

```python
campaign_pnl = campaign_pnl_series(NQ_PRIOR_OPPOSED_UNIT_TRADES)
sr_campaign = campaign_sharpe_ratio(campaign_pnl)
dsr_campaign = compute_dsr(campaign_pnl, sr_campaign, n_eff)  # pass campaign P&L as series; use campaign sharpe
dsr_daily = compute_dsr(returns, float(nq["sharpe_daily"]), n_eff)  # secondary
gate_nulls = load_primary_gate_nulls()
chart_paths = save_charts(..., gate_nulls=gate_nulls)
write_outputs(..., dsr_primary=dsr_campaign, dsr_daily=dsr_daily, gate_nulls=gate_nulls, ...)
```

## `write_outputs()` changes

- **Random-Gate Control Status** section: table of NQ/MNQ/YM/MYM from `gate_nulls`; disclosure via `format_pvalue_disclosure`.
- Label family: **`stratified_fine_buckets`** (see AUDIT_TRACKER FD5).
- Move sampling control to **Secondary diagnostic** subsection.
- Headline DSR block: campaign observations count, campaign SR; footnote daily SR.
- `missing` table row "Random gate null": Implemented = stratified 200-seed; Left over = coarse buckets, 2000-seed, unconstrained/shuffled 200-seed.
- Regenerate `IMPLEMENTATION_STATUS.md` text accordingly.

## Null CSV (`v2b_prior_opposed_random_gate_replay.py`)

In `seed_result_row()` add:

```python
"counts_toward_permutation_test": "TRUE" if method in METHODS else "FALSE",
```

In `run_batch()` after universe freeze, write `run_metadata.json`:

```json
{
  "method": "stratified_event_count",
  "family_display_name": "stratified_fine_buckets",
  "time_buckets": ["09:30-09:45", "09:45-10:30", "10:30-12:00", "12:00-14:00", "14:00-15:30"],
  "seed_start": 1,
  "seed_end": 200,
  "seed_hash": "<hash of tuple(range(1,201))>"
}
```

## Verify

```bash
python scripts/generate_strategy_validation_scorecard.py
python -m py_compile scripts/generate_strategy_validation_scorecard.py
```

Check `live/state/strategy_validation_scorecard/SCORECARD_REPORT.md` shows gate null p=0.0050 and campaign-level DSR.
