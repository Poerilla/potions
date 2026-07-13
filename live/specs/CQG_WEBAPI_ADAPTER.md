# CQG WebAPI Adapter

Status: deferred secondary adapter. A CQG implementation scaffold exists, but **Tradovate is now the first real broker/data adapter priority**. CQG production/live routing remains blocked until CQG protobuf transport, credentials, demo burn-in, and CQG conformance approval are complete.

## Provider Choice

If/when CQG is resumed, use **CQG WebAPI**, not FIX or the legacy COM Client API. CQG documents WebAPI as a protobuf-over-secure-WebSocket API with streaming market data, historical bars/ticks, order execution, account data, order history, and post-trade support. CQG also states that production API applications require formal conformance testing before live connection.

Demo defaults:

- `CQG_ENV=demo`
- `CQG_ENDPOINT=wss://demoapi.cqg.com`
- `CQG_PRIVATE_LABEL=WebAPITest`
- `CQG_CLIENT_ID=WebAPITest`
- `CQG_CLIENT_VERSION=potions-cqg-adapter-dev`

Secrets stay outside the repo:

- `CQG_USERNAME`
- `CQG_PASSWORD`
- `CQG_ACCOUNT_ID`
- `CQG_CONTRACT_MAP`, for example `MNQ=F.US.MNQM26,NQ=F.US.NQM26`

## Implemented Files

- `live/cqg.py`
  - `CqgWebApiConfig`
  - `CqgWebApiClient`
  - `JsonCqgProtocolCodec` for offline tests/replay
  - `CqgProtobufCodec` boundary for generated CQG `_pb2.py` files
  - `CqgMarketDataFeedAdapter`
  - `CqgBroker`
- `live/cli.py`
  - `cqg-smoke`
  - `cqg-feed-shadow`
  - `cqg-paper`
- `live/store.py`
  - nested event streams, e.g. `events/raw_market_data/cqg/YYYY-MM-DD.jsonl`

## Market Data Contract

CQG contract ids are treated as **session-only**. The adapter resolves and stores a `CqgContractRef` each session and never assumes a saved `contract_id` is valid after restart.

The feed adapter writes:

- `market_data_status.json`
- `events/raw_market_data/cqg/YYYY-MM-DD.jsonl`
- `events/cqg_session_events.jsonl`
- `feed_broker_bar_audit.csv`
- existing `bars/*.csv`

The adapter blocks new entries when:

- contract resolution is missing,
- CQG reports access denied,
- data is delayed,
- subscription level is downgraded/collapsed,
- the provider-neutral feed is stale,
- expected completed 1m/5m bars are missing or out of order.

Broker-side protective exits, reconciliation, and emergency flattening must not be blocked because the market-data stream is stale.

## Broker Contract

`CqgBroker` implements `BaseBroker` and keeps local CSV state as an audit mirror. CQG is intended to be the source of truth for orders, fills, positions, and account state once live demo credentials are enabled.

Order support scaffold:

- market
- limit
- stop
- cancel
- modify
- local audit mirror for order acknowledgments, fills, and positions
- emergency `go_flat`

CQG order docs require trade/order subscription for order status updates. The broker records this as a session event before order submission. Native CQG OCO/OPO/bracket support is represented as a switch, but remains disabled until demo validation proves CQG compound-order behavior matches post-session replay. Local-managed OCO is marked unsafe for live until validated.

## CLI Usage

Offline config smoke:

```bash
python -m potions.live.cli --state-root /tmp/cqg_state cqg-smoke --offline --instrument MNQ --contract-id demo_mnq
```

Replay saved CQG-like JSONL market data into bars:

```bash
python -m potions.live.cli --state-root /tmp/cqg_state cqg-feed-shadow --events cqg_events.jsonl
```

Bootstrap CQG broker/feed paper state and replay saved order/fill events:

```bash
python -m potions.live.cli --state-root /tmp/cqg_state cqg-paper --events cqg_events.jsonl
```

## Remaining Work Before Demo Orders

1. Generate or vendor CQG WebAPI protobuf `_pb2.py` files under `live/cqg_proto/`.
2. Implement the concrete `CqgProtobufCodec` field mappings.
3. Add real secure WebSocket transport and heartbeat/session-status loop.
4. Use CQG demo credentials to log on, resolve one MNQ/NQ contract, subscribe to trade/order updates, and request account data.
5. Run one full RTH session in feed shadow.
6. Route TP1-only v2b through CQG demo with order/fill/position reconciliation.
7. Restart during RTH and prove no duplicate entries or lost open-order state.
8. Complete CQG/StoneX conformance and entitlement approval before production.

## References

- CQG WebAPI overview: `https://help.cqg.com/apihelp/Documents/cqgwebapi.htm`
- CQG WebAPI orders: `https://help.cqg.com/apihelp/Documents/orders.htm`
- CQG market-data subscription: `https://help.cqg.com/apihelp/Documents/marketdatasubscription.htm`
- CQG API product overview: `https://www.cqg.com/products/cqg-apis/client-apis`
- CQG WebAPI samples: `https://github.com/cqg/WebAPIPythonSamples`
