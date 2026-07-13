# V2B Hardened Replay Baseline

This directory captures outputs from the post-hardening V2B cross-market replay path.

## Realism stack

- Dense RTH 1m forward-fill (`live/bars.py`) — missing Databento minutes become flat bars with `volume=0`
- 1-tick adverse slippage on market/stop fills
- Synthetic half-spread overlay (`live/spread_model.py`) — RTH 0.5 tick minimum, wider at open and on low volume
- Stop-first OCO + directional adverse-path limit guards (`live/directional_path.py`)

Configuration is written to `realism_config.json`.

## Run (requires local DBN files)

```bash
PYTHONPATH=/home/tester/hsm python -m potions.live.replay_realism_baseline \
  --markets mnq,nq,es,ym,mym \
  --max-days 0 \
  --output-root live/state/v2b_hardened_replay_baseline
```

Use `--max-days 0` for full history or a small number for smoke tests.

## Compare to pre-hardening baseline

Compare `v2b_oco_cross_market_summary.csv` in this directory against:

- `live/state/v2b_oco_cross_market/v2b_oco_cross_market_summary.csv` (if present)
- Pre-realism snapshots referenced in `live/CHANGE_LOG.md`

Expect lower net and similar or slightly deeper intrabar stress DD under spread + dense grid normalization.

## Tick manifest audit

```bash
PYTHONPATH=/home/tester/hsm python -m potions.live.tick_replay_audit \
  --market nq \
  --manifest live/state/v2b_prior_opposed_execution_scrutiny/nq/tick_replay_manifest.csv \
  --output-dir live/state/tick_replay_audit/nq
```

## Live parity audit

After exporting Tradovate demo fills to `live/state/live_manual_journal/fills.csv`:

```bash
PYTHONPATH=/home/tester/hsm python -m potions.live.execution_parity_audit \
  --live-fills live/state/live_manual_journal/fills.csv \
  --sim-fills live/state/<replay_state>/fills.csv \
  --live-strategy-id manual_v2b_session \
  --sim-strategy-id nq_v2b_prior_opposed_stpmc_only_S_1_1_3 \
  --output-dir live/state/execution_parity
```
