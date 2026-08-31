---
name: potions-run-ledger
description: >-
  Logs every potions broker-like Engine replay, pandas walkthrough, deep-check,
  sweep, and audit into data/validation/broker_run_ledger.csv (id, timestamp,
  instrument, Sharpe/Parmar/N/S, MTM DD, net, avg yearly net/stress, variant
  slug, meta). Use when starting or finishing any research/replay/job, or when
  the user asks for the run catalog / ledger.
---

# Potions run ledger (always log)

**Rule:** Every broker-like Engine+PaperBroker replay, pandas study/walkthrough,
instrument deep-check, sweep, sidecar book, causality audit, and **HA
(high-probability conditions) mill** (profile / overlay / nulls) **must** append
(or complete) a row in [`data/validation/broker_run_ledger.csv`](../../../data/validation/broker_run_ledger.csv).
Do **not** wait for the user to ask.

This is separate from the DSR peek ledger
([`data/validation/dsr_trial_ledger.csv`](../../../data/validation/dsr_trial_ledger.csv)):

| Ledger | Purpose |
|--------|---------|
| `broker_run_ledger.csv` | **All** finished runs + metrics catalog |
| `dsr_trial_ledger.csv` | Multiple-testing / disclosure (append **before** peek) |

## API

```python
from live.run_ledger import begin_run, complete_run, fail_run, log_run, log_from_hub

# Long job
rid = begin_run(
    run_class="broker_like",  # broker_like|pandas|deep_check|walk_forward|sweep|audit|sidecar|ha|other
    variant_slug="nq_quarterly_range_breakout",
    instrument="NQ",
    hub_path="live/state/nq_quarterly_range_breakout_v2_honest_chk",
    dsr_trial_id="TRL-2026-00117",  # optional link
    meta={"allowed_sides": ["long", "short"]},
)
# ... work ...
complete_run(
    rid,
    net_usd=...,
    stress_dd_usd=...,          # intrabar MTM DD (negative)
    close_mtm_dd_usd=...,
    ns=...,
    trades=...,
    equity_curve_path=hub / "audits" / "..." / "equity_curve.csv",  # fills Sharpe/Sortino/Calmar=Parmar
    yearly_csv_path=hub / "deep_check" / "..." / "yearly_breakdown.csv",  # avg yearly *
)

# One-shot after hub exists
log_from_hub(Path("live/state/<slug>"), run_class="broker_like", instrument="NQ")

# Pandas walkthrough (even without Engine)
log_run(
    run_class="pandas",
    variant_slug="nq_prior_width_study",
    instrument="NQ",
    hub_path="live/state/.../prior_width_study",
    net_usd=...,
    stress_dd_usd=...,
    ns=...,
    meta={"study": "prior_width_vs_losses"},
    notes="pandas walkthrough",
)
```

CLI:

```bash
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
python -m live.run_ledger log-hub --hub live/state/<slug> --instrument NQ
python -m live.run_ledger tail -n 20
```

## Required fields (fill what you can)

- `run_id`, `ts_start` / `ts_end`, `status`, `run_class`, **`variant_slug`**, **`instrument`**, `hub_path`
- **`net_usd`**, **`stress_dd_usd`** (MTM / intrabar), **`close_mtm_dd_usd`**, **`ns`**
- **`sharpe`**, **`sortino`**, **`calmar`**, **`parmar`** (Parmar = Calmar-like from equity when available)
- **`avg_yearly_net`**, **`avg_yearly_stress`**, **`avg_yearly_ns`**, `n_years` (deep-check / yearly board)
- `trades`, `units`, `replay_start` / `replay_end`, `meta_json`, `dsr_trial_id`, `notes`

## Already wired

Drivers that auto-log on success:

- `live.quarterly_range_breakout_broker`
- `live.failure_fade_broker`
- `live.instrument_deep_check` (**always**, including when used by this skill)
- `live.usdjpy_monthly_orb_fbo_ha_conditions` (`run_class=ha`)
- `live.monthly_open_liq_run_fade_ha_conditions` (`run_class=ha`)
- `live.quarterly_atr4_ha_conditions` (`run_class=ha`)

For other family drivers / pandas scripts: call `log_run` / `log_from_hub` before exit
(and `fail_run` on crash). Prefer `--email` via `potions-job-email` as well.

## HA (high-probability conditions)

Use `run_class=ha` for condition-profile / overlay / null mills. Example:

```python
log_run(
    run_class="ha",
    variant_slug="usdjpy_fbo_1_1_3_atr80_ha",
    instrument="USDJPY",
    hub_path="live/state/usdjpy_monthly_orb_fbo_ha_conditions",
    notes="HA condition mill profile+overlay+nulls",
    meta={"source": "fbo_1_1_3_atr80_usdjpy"},
    net_usd=...,
    ns=...,
    trades=...,
)
```

## Deep-check

When running `potions-instrument-deep-check`, the module writes the deep_check hub
**and** a `run_class=deep_check` ledger row with yearly averages. If you only have
an older deep_check folder, backfill:

```bash
python -m live.run_ledger log-hub --hub live/state/<hub>/deep_check/<id> \
  --run-class deep_check --instrument <SYM>
```

## Related

- `live/run_ledger.py` — implementation
- `potions-job-email` — Resend on finish (still required)
- `potions-causality-audit` / `potions-strategy-plugin` — still append DSR **before** peek
- `potions-quick-backtest` — call ledger after replay
