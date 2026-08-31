# OANDA Account `-004` Rotation — 2026-08-24

## Decision

Replace the dedicated-account `-004` NAS100 ST+PMC 2R->10R practice sleeve with
the USDJPY Asia-range London filtered `S_3_1_3` sleeve.

## New Active Mapping

| Account | Alias target | Demo dir | CLI | Config |
|---|---|---|---|---|
| `101-002-39860312-004` | `USDJPY Asia Range S313` | `usdjpy_asia_range_london_oanda` | `demo-usdjpy-asia-range-oanda` | `usdjpy_asia_range_004.json` |

Start command:

```bash
CFG=/home/tester/hsm/potions/live/demo/oanda_account_configs
python3 -m potions.live.cli demo-usdjpy-asia-range-oanda --daemon \
  --oanda-config "$CFG/usdjpy_asia_range_004.json"
```

## Replaced Mapping

| Old sleeve | Old config | Action |
|---|---|---|
| NAS100 ST+PMC 2R->10R | `nas100_2r10r_st_pmc_004.json` | Removed from active account-config directory |

Historical NAS100 ST+PMC scripts and logs remain in the repository for audit,
but they are no longer part of the active top-3 dedicated-account runbook.

## Causality Evidence For Replacement

Source: `live/state/usdjpy_causality_review_2026_08/CAUSALITY_REVIEW.md`.

| Check | Result |
|---|---:|
| StrategyPlugin | `v2b_scaleout` |
| Broker-style performance | `$178,142 / -$24,627 / 7.23 N/S` |
| Feature snapshots | `3,772` |
| Causality violations | `0` |
| Entry fills at/before activation | `0` |
| Earliest entry fill | `1m` after the 03:00 London arm |

Status: **PASS at 1m bar resolution**. Residual limitation remains that this
is a 1m OHLC broker replay, not a tick-queue proof.

## OANDA Alias

Target alias: `USDJPY Asia Range S313`.

Result: **updated successfully** via OANDA practice REST account configuration
on 2026-08-24. Response status: `200`.

## Smoke Test

Command class:

```bash
demo-usdjpy-asia-range-oanda --max-ticks 3 \
  --oanda-config /home/tester/hsm/potions/live/demo/oanda_account_configs/usdjpy_asia_range_004.json
```

Result: **PASS** on 2026-08-24.

- Reconciled account `101-002-39860312-004`: open orders `0`, positions `0`.
- Opened OANDA practice pricing stream for `USD_JPY`: HTTP `200`.
- Strategy metadata: `strategy_type=v2b_scaleout`, `book=S_3_1_3`, routing `True`.
- Stopped because `--max-ticks=3` was reached; no live trade/order was submitted.

The detached daemon was attempted once and connected, but the shell environment
did not keep the child process alive. Leave the account in smoke-verified
stopped state unless an operator starts it from the normal daemon supervisor.
