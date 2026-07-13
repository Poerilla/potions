# Tradovate Adapter

Status: implementation scaffold added for demo/sim validation. Production/live routing remains blocked until Tradovate demo burn-in, server-side OCO/OSO validation, account entitlement review, and operational reconciliation drills are complete.

## Provider Choice

Tradovate is now the **first real adapter** for the live runtime. CQG remains a deferred secondary provider.

The adapter is built from the checked-in OpenAPI file:

- `live/openapi.json`

The local spec currently identifies itself as **Tradovate API 1.0.0** and includes the demo server `https://demo.tradovateapi.com/v1`.

## Demo Defaults

Environment variables stay outside the repo:

- `TRADOVATE_ENV=demo`
- `TRADOVATE_REST_ENDPOINT=https://demo.tradovateapi.com/v1`
- `TRADOVATE_WS_ENDPOINT=wss://demo.tradovateapi.com/v1/websocket`
- `TRADOVATE_MD_WS_ENDPOINT=wss://demo.tradovateapi.com/v1/websocket`
- `TRADOVATE_USERNAME`
- `TRADOVATE_PASSWORD`
- `TRADOVATE_APP_ID`
- `TRADOVATE_APP_VERSION`
- `TRADOVATE_CID`
- `TRADOVATE_SECRET`
- `TRADOVATE_ACCOUNT_ID`
- `TRADOVATE_ACCOUNT_SPEC`
- `TRADOVATE_CONTRACT_MAP`, for example `MNQ=MNQM6,NQ=NQM6,MYM=MYMM6`
- `TRADOVATE_CONTRACT_ID_MAP`, optional numeric ids for flatten/liquidation, for example `MNQ=123456,NQ=123457,MYM=123458`

First supported instruments: **MNQ, NQ, and MYM**.

## Implemented Files

- `live/tradovate.py`
  - `TradovateConfig`
  - `TradovateOpenApiCatalog`
  - `TradovateWebApiClient`
  - `TradovateMarketDataFeedAdapter`
  - `TradovateBroker`
- `live/supervisor.py`
  - provider-neutral runtime freeze/reconcile/flatten state
- `live/cli.py`
  - `tradovate-smoke`
  - `tradovate-feed-shadow`
  - `tradovate-paper`
  - `tradovate-emergency-flatten`

## Required OpenAPI Routes

The adapter validates these routes at startup:

- `/auth/accesstokenrequest`
- `/auth/renewaccesstoken`
- `/account/list`
- `/contract/find`
- `/contract/suggest`
- `/contract/rollcontract`
- `/order/placeorder`
- `/order/placeoco`
- `/order/placeoso`
- `/order/cancelorder`
- `/order/modifyorder`
- `/order/liquidateposition`
- `/order/liquidatepositions`
- `/position/list`
- `/user/syncrequest`

## WebSocket Protocol

Tradovate WebSockets are parsed according to `live/openapi.json`:

- server frames: `o`, `h`, `a`, `c`
- client request frame: `endpoint\nrequest_id\nquery\nbody`
- socket authorization: `authorize`
- user/account/order synchronization: `user/syncrequest`
- client heartbeat: `[]`

The client heartbeat expectation from the spec is separate from the runtime freeze thresholds. The adapter sends protocol heartbeats around the 2.5 second cadence; the strategy runtime freezes new entries after a 1000 ms provider/fault threshold where configured.

## Market Data Contract

The feed adapter writes:

- `market_data_status.json`
- `events/raw_market_data/tradovate/YYYY-MM-DD.jsonl`
- `events/tradovate_session_events.jsonl`
- `feed_broker_bar_audit.csv`
- existing `bars/*.csv`

The adapter accepts Tradovate chart-style events and normalized trade/bar test events. It emits completed 1m bars and derives 5m bars for v2b.

The adapter blocks new entries when:

- contract resolution is missing,
- Tradovate reports access denied or delayed/downgraded data,
- the provider-neutral feed is stale,
- completed bars are missing, duplicate, or out of order.

Broker-side protective exits, reconciliation, and emergency flattening must not be blocked because market data is stale.

## Broker Contract

`TradovateBroker` implements `BaseBroker`. Tradovate is the order/fill/position/account source of truth when enabled; local CSVs are an audit mirror.

Order support scaffold:

- `placeorder`
- `placeoco`
- `placeoso`
- `cancelorder`
- `modifyorder`
- `liquidateposition`
- local audit mirror for acknowledgments, fills, positions, and broker events

All API-routed orders include `isAutomated: true`.

Live entries are blocked unless server-side OCO/OSO protective behavior has been validated in demo. Local-managed OCO is allowed only for paper/demo research and is marked unsafe for live.

## CLI Usage

Offline OpenAPI/config smoke:

```bash
PYTHONPATH=/home/tester/hsm python -m potions.live.cli --state-root /tmp/tradovate_state tradovate-smoke --offline
```

Replay saved Tradovate-like JSONL market data into bars:

```bash
PYTHONPATH=/home/tester/hsm python -m potions.live.cli --state-root /tmp/tradovate_state tradovate-feed-shadow --events tradovate_events.jsonl
```

Bootstrap Tradovate demo/sim broker/feed state and replay saved order/fill events:

```bash
PYTHONPATH=/home/tester/hsm python -m potions.live.cli --state-root /tmp/tradovate_state tradovate-paper --events tradovate_events.jsonl
```

Emergency flatten scaffold:

```bash
PYTHONPATH=/home/tester/hsm python -m potions.live.cli --state-root /tmp/tradovate_state tradovate-emergency-flatten
```

## Remaining Work Before Demo Orders

1. Add real credentialed demo smoke with `TRADOVATE_*` env vars.
2. Resolve current MNQ, NQ, and MYM contracts through Tradovate.
3. Subscribe to `user/syncrequest` and prove account/order/fill/position event flow.
4. Run one full RTH session in feed shadow.
5. Prove `placeoso`/`placeoco` server-side protective behavior in demo.
6. Route TP1-only v2b through Tradovate demo with reconciliation.
7. Restart during RTH and prove no duplicate entries or lost open-order state.
8. Complete compliance/account entitlement review before live use.
