# Live Deploy Bootstrap

This folder is the small-cloud starting point for paper execution. It is
intentionally boring: one container, one `engine.conf`, one strategy, local
flat-file state.

## First Target

- Strategy: `v2b_scaleout`
- Market: `MNQ`
- Size: `1` contract
- Buckets: `1/0/0` (`tp1_qty=1`, `tp2_qty=0`, no runner)
- Broker mode: local `PaperBroker`
- Feed mode: flat-file/live-bar adapter placeholder
- Regime safety: empty `regime_dates` means no entries until the daily
  MA50>MA150 updater is wired or the dates are explicitly populated.

This gets the runtime shape right before Tradovate paper routing is added:

```text
completed bars -> StrategyPlugin -> OrderIntent -> Engine -> PaperBroker -> fills/reports
```

## Local Smoke Run

Create the active config from the example:

```bash
cp potions/live/deploy/engine.conf.example.json potions/live/deploy/engine.conf.json
python -m potions.live.config_runner --config potions/live/deploy/engine.conf.json check
python -m potions.live.config_runner --config potions/live/deploy/engine.conf.json init
```

Run the container:

```bash
cd potions/live/deploy
docker compose up -d --build
curl http://127.0.0.1:8765/healthz
```

State lands in:

```text
potions/live/deploy/state/mnq_v2b_1_0_0_demo/
```

## What Is Not Wired Yet

- Tradovate broker-paper order routing.
- Tradovate live/paper feed adapter.
- Databento live feed adapter.
- Contract roll resolver from `MNQ` to the active Tradovate-routable contract.
- Secrets management.

The config schema already separates those knobs so they can be implemented
without changing strategy code.

## Promotion Order

1. Run local paper loop with replayed/completed bars.
2. Add a CSV live-feed adapter that drips completed 1m bars into jobs.
3. Add Tradovate broker-paper adapter behind the same `OrderIntent` contract.
4. Add Databento or Tradovate market-data feed.
5. Only then enable `broker-live`, with `allow_live_routing` still requiring an
   explicit config change and operator checklist.
