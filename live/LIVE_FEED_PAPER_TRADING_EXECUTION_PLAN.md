# Live Feed Paper Trading Execution Plan

Goal: move the current `potions/live/` runtime from broker-like replay into a real-time paper-trading harness that can run strategies such as **v2b OCO scaleout** and **Yearly ORB scaleout3** against a Tradovate demo/paper account, while keeping the same `StrategyPlugin -> RiskManager -> Broker` path used by replays.

This plan is intentionally paper-first. Real-money routing should stay disabled until the paper path survives multiple weeks of feed, order, fill, reconciliation, restart, and report checks.

## Current Readiness

The runtime is currently a strong replay engine, not a complete live-feed engine.

What already exists:

- `Engine` can accept completed `Bar` objects and run strategy callbacks.
- `StrategyManager` loads enabled `StrategyPlugin`s from flat files and applies order/cancel/modify actions.
- `PaperBroker` simulates fills against completed OHLC bars and persists orders, fills, positions, events, and health.
- `RiskManager` blocks over-sizing and now collapses OCO peers in exposure projection.
- `SpoofVerificationProvider` auto-approves paper entries and blocks unapproved live entries.
- Health endpoint and flat-file reports exist.
- `V2BScaleoutStrategy` exists and supports `oco_then_reverse`, custom `entry_qty`, `tp1_qty`, and `tp2_qty`.
- `YearlyOrbScaleout3Strategy` exists for daily-bar yearly ORB variants.

What is missing before Tradovate paper trading:

- No live market-data adapter.
- No 1m/5m real-time bar builder.
- No idempotent bar upsert / duplicate-bar protection.
- No real Tradovate broker implementation. `TradovateBroker` is still an inert shell.
- Engine still assumes a broker can be asked to `process_bar()`, which is a simulation method, not a live-broker method.
- Live jobs such as `market_data_refresh`, `reconcile_orders`, `reconcile_positions`, and `send_alerts` are currently noops.
- No startup reconciliation loop that trusts broker state over local state.
- No durable mapping between local `intent_id` / `broker_order_id` and Tradovate `orderId` / `ocoId` / `osoId`.
- No production-grade notification sink yet.

## Tradovate OpenAPI Capability Check

Source inspected: `live/openapi.json`

Spec metadata:

- OpenAPI: `3.0.0`
- Title: `Tradovate API`
- Version: `1.0.0`
- Server in spec: `https://demo.tradovateapi.com/v1`
- Paths: `341`

### REST Endpoints That Support Our Needs

| Need | OpenAPI support | Relevant endpoints | Read |
|---|---|---|---|
| Username/password auth | Yes | `POST /auth/accesstokenrequest` | Usable for demo/paper auth. Requires `name`, `password`; supports app/device/client fields. |
| Token renewal | Yes | `GET /auth/renewaccesstoken` | Required for long-running engine. |
| Current user | Yes | `GET /auth/me` | Useful for sanity checks and account ownership. |
| Account discovery | Yes | `GET /account/list`, `GET /account/find`, `GET /account/item` | Usable for selecting the paper/demo account. |
| Cash / net liquidation | Yes | `POST /cashBalance/getcashbalancesnapshot` | Usable for daily reports and risk checks. |
| Margin snapshots | Yes | `GET /marginSnapshot/list` | Useful, but should be validated against demo account behavior. |
| Contract lookup | Yes | `GET /contract/find`, `GET /contract/suggest`, `GET /contract/item`, `GET /contract/list` | Usable for active contract resolution if we provide the symbol. Roll logic still needs our own resolver. |
| Place standalone order | Yes | `POST /order/placeorder` | Supports `Market`, `Limit`, `Stop`, `StopLimit`, trailing variants. Required fields include `action`, `symbol`, `orderQty`, `orderType`. |
| Place OCO order | Yes | `POST /order/placeoco` | Important for v2b entry pairs and protective OCO exits. Returns `orderId` and `ocoId`. |
| Place OSO / bracket order | Yes | `POST /order/placeoso` | Important for parent + bracket style workflows. Returns parent and child ids. Must be tested with desired v2b scaleout shape. |
| Start broker order strategy | Yes | `POST /orderStrategy/startorderstrategy` | Possibly useful for bracket/ATM behavior, but requires strategy type ids and params. Treat as optional later phase. |
| Modify order | Yes | `POST /order/modifyorder` | Needed for runner stop movement and order maintenance. |
| Cancel order | Yes | `POST /order/cancelorder` | Needed for OCO cleanup, EOD cleanup, stale order cleanup. |
| Liquidate one position | Yes | `POST /order/liquidateposition` | Needed for kill switch and emergency flatten. |
| Liquidate multiple positions | Yes | `POST /order/liquidatepositions` | Useful for global emergency flatten. |
| Cancel everything | Yes | `POST /user/canceleverything` | Broad hammer. Must be treated as emergency-only. |
| Orders / versions / commands | Yes | `/order/*`, `/orderVersion/*`, `/command/*`, `/commandReport/*` | Needed for reconciliation and broker state recovery. |
| Execution reports | Yes | `GET /executionReport/list`, `/executionReport/item`, `/executionReport/find` | Needed to detect broker-side fills/rejections. |
| Fills | Yes | `GET /fill/list`, `/fill/item`, `/fill/items` | Needed to persist fills and rebuild positions. |
| Positions | Yes | `GET /position/list`, `/position/find`, `/position/item` | Needed for startup and continuous reconciliation. |

### Gaps In This OpenAPI File

This `openapi.json` does **not** appear to include usable market-data bar, quote, chart, or websocket endpoints. Searches for `chart`, `quote`, `md`, `depth`, and historical bar paths did not reveal bar-feed endpoints. It contains market-data subscription/account-management endpoints, but not the actual live data stream.

Practical implication:

- The REST spec is sufficient to scaffold the **broker/order/account/fill adapter**.
- We still need a **separate market-data adapter** for live 1m/5m/daily bars.
- That feed can be Tradovate’s market-data websocket if available outside this OpenAPI file, Databento live, or another broker/data provider.

## Target Architecture

The live runtime should be split into two event streams:

1. Market-data events:
   - tick/quote/trade input
   - bar aggregation
   - completed bar event
   - `Engine.process_completed_bar(bar)`

2. Broker events:
   - order accepted/rejected
   - order working/canceled/expired
   - fill / partial fill
   - position changed
   - account/cash/margin changed
   - `StrategyManager.on_fills(fills)`
   - local state reconciliation

The current replay path combines those through `PaperBroker.process_bar()`. Live mode must not.

## Phase 1 - Runtime Interface Cleanup

Objective: make the same engine support simulated bars and real broker events without confusing replay fills with broker fills.

Tasks:

- Add a broker capability flag or separate classes:
  - `SimBroker` / current `PaperBroker`
  - `ExternalBroker` / real Tradovate adapter
- Change `Engine.process_bar()` into two clearer paths:
  - `process_completed_bar(bar)` for strategy evaluation
  - `process_simulated_bar(bar)` for PaperBroker replay fills + strategy evaluation
- Keep current replay behavior intact by wrapping it in `ReplayEngine` or a mode flag.
- Add `BrokerEvent` models:
  - `OrderAccepted`
  - `OrderRejected`
  - `OrderCanceled`
  - `OrderModified`
  - `FillReceived`
  - `PositionSnapshot`
  - `AccountSnapshot`
- Add idempotency keys to prevent duplicate fill/order processing.
- Add tests showing replay mode still matches current broker-like outputs for a small fixture.

Acceptance:

- Existing replay tests still pass.
- A fake external broker can inject a fill and strategy state updates correctly.
- Engine no longer requires external brokers to implement `process_bar()`.

## Phase 2 - Flat-File State Hardening

Objective: make flat files reliable enough for live paper trading.

Tasks:

- Add idempotent bar storage keyed by `(instrument, timeframe, ts)`.
- Add `broker_order_mappings.csv`:
  - `intent_id`
  - `local_broker_order_id`
  - `broker`
  - `broker_account_id`
  - `broker_order_id`
  - `broker_oco_id`
  - `broker_oso_id`
  - `cl_ord_id`
  - `status`
  - `created_at`
  - `updated_at`
- Add `broker_events.csv` or JSONL:
  - source event id
  - broker timestamp
  - normalized event type
  - raw payload path/hash
- Add `market_data_status.json`:
  - last tick time
  - last completed 1m bar
  - last completed 5m bar
  - feed stale flag
- Add `runtime_locks/` or lock-file behavior to avoid running two engines on the same state root.
- Add tests for duplicate bars, duplicate fills, restart reload, and broker mapping recovery.

Acceptance:

- Replaying the same completed bar twice does not double-trigger strategy orders.
- Replaying the same fill twice does not double-change position.
- Restart reconstructs pending orders, mappings, positions, and strategy state.

## Phase 3 - Market Data Adapter And Bar Builder

Objective: get trustworthy completed 1m/5m/daily bars into the engine.

Tasks:

- Define `MarketDataAdapter`:
  - `connect()`
  - `subscribe(contract)`
  - `on_trade_or_quote(callback)`
  - `get_status()`
  - `disconnect()`
- Define `BarBuilder`:
  - input: tick/trade or quote events
  - output: completed `Bar`
  - timeframes: `1m`, `5m`, `15m`, `4H`, `D`
  - timezone: `America/New_York`
  - session filters: RTH for v2b, daily settlement handling for ORB systems
- Add `BarCompletenessGuard`:
  - bars only emitted after timestamp has fully elapsed
  - no partial bars passed to strategies
  - reconnect can backfill missing bars
- Add a provider implementation:
  - Preferred: Tradovate market-data websocket if we document and test it.
  - Acceptable first paper path: Databento live feed if easier and already familiar.
- Add a small `CSVLiveFeedAdapter` for rehearsal:
  - streams historical 1m bars in real time or accelerated time
  - exercises the same live event loop without broker risk.

Acceptance:

- A one-day accelerated `CSVLiveFeedAdapter` run produces the same bars/orders as the existing v2b replay for that day.
- Real or demo feed can run during RTH and write completed 1m bars to `bars/MNQ_1m.csv`.
- Feed stale condition creates a warning alert and blocks new entries after a configured timeout.

## Phase 4 - Tradovate REST Broker Adapter

Objective: implement paper-account order routing, reconciliation, and emergency control using `live/openapi.json`.

Core class:

```python
class TradovateBroker(BaseBroker):
    def __init__(self, config, store, http_client, account_mode="paper"):
        ...
```

Config file fields:

- `base_url`: default from spec is `https://demo.tradovateapi.com/v1`
- `username`
- `password`
- `app_id`
- `app_version`
- `device_id`
- `cid`
- `secret`
- `account_spec`
- `account_id`
- `default_is_automated`
- `paper_only`

Required endpoint mappings:

| BaseBroker method | Tradovate endpoint(s) |
|---|---|
| `authenticate()` | `POST /auth/accesstokenrequest` |
| `renew_token()` | `GET /auth/renewaccesstoken` |
| `get_accounts()` | `GET /account/list` |
| `get_active_contract()` | `GET /contract/suggest`, `GET /contract/find` plus our own roll resolver |
| `submit_order_intent()` | `POST /order/placeorder`, `/order/placeoco`, or `/order/placeoso` |
| `modify_order()` | `POST /order/modifyorder` |
| `cancel_order()` | `POST /order/cancelorder` |
| `reconcile_orders()` | `GET /order/list`, `/orderVersion/list`, `/commandReport/list` |
| `reconcile_positions()` | `GET /position/list` |
| `load_fills()` | `GET /fill/list`, `GET /executionReport/list` |
| `flatten_position()` | `POST /order/liquidateposition` |
| `kill_switch()` | `POST /order/liquidatepositions`, optionally `/user/canceleverything` |
| `account_snapshot()` | `POST /cashBalance/getcashbalancesnapshot`, `GET /marginSnapshot/list` |

Implementation notes:

- Use `clOrdId` as our idempotency bridge. Suggested format:
  - `potions-{strategy_id}-{intent_id[:8]}-{seq}`
- Always persist raw response payloads before mutating local status.
- Do not rely only on submit response. Confirm with order/command report polling.
- All fills must be reconstructed from broker fill/execution report records, not guessed from local orders.
- Parent/child/OCO relationships must be stored in `broker_order_mappings.csv`.

Acceptance:

- Can authenticate to demo and list accounts.
- Can find/suggest active MNQ/NQ contract.
- Can submit a 1-lot paper stop order, cancel it, and reconcile status.
- Can submit a paper OCO pair, manually trigger/cancel one side, and reconcile peer cancellation.
- Can submit a paper OSO/bracket if Tradovate supports the exact parent/child shape we need.
- Can liquidate one paper position and confirm local state returns flat.

## Phase 5 - V2B OCO Paper Harness

Objective: run `v2b_scaleout` against a Tradovate paper account with custom sizing.

Example strategy instance:

```json
{
  "strategy_id": "mnq_v2b_oco_paper_custom",
  "strategy_type": "v2b_scaleout",
  "version": "v1",
  "instrument": "MNQ",
  "broker_instrument": "MNQM6",
  "account_mode": "paper",
  "enabled": true,
  "timeframes": "1m",
  "max_contracts": 4,
  "max_open_orders": 24,
  "config_json": {
    "mode": "oco_then_reverse",
    "entry_qty": 4,
    "tp1_qty": 2,
    "tp2_qty": 1,
    "tick_size": 0.25,
    "rth_start": "09:30",
    "or_end": "09:45",
    "eod_cutoff": "15:59",
    "use_regime_filter": true,
    "record_levels": true
  }
}
```

Important: `regime_dates` should not be manually static in live operation. Instead, a daily updater should write the current `regime_ok` decision to state before RTH, based on prior completed daily close:

- `MA50 > MA150` shifted one completed daily bar.
- If false, no v2b entries are armed.
- If data is stale or unavailable, skip the session.

Execution behavior required:

- 09:30-09:45 ET: build OR from completed 1m bars.
- After 09:44/09:45 close confirms OR complete: submit OCO stop pair.
- On first entry fill:
  - cancel peer OCO automatically or confirm broker OCO did so.
  - place protective stop for full quantity.
  - place TP1 and TP2 limits according to custom buckets.
- On TP1 fill:
  - cancel wide stop / stale TP2 as needed.
  - move remaining stack to runner stop at boundary.
  - restore TP2 limit for TP2 bucket.
- At EOD cutoff:
  - cancel all open strategy orders.
  - flatten any open position.
  - verify flat with broker position snapshot.

Acceptance:

- Five paper sessions run with zero duplicate bars, zero orphan orders, zero unexplained position drift.
- Every local fill matches a Tradovate fill id and price.
- Every local open order maps to a Tradovate order id.
- EOD flat is confirmed by broker.
- Daily report contains strategy state, OR levels, orders, fills, positions, P/L, warnings, and next expected action.

## Phase 6 - Yearly ORB Paper Harness

Objective: run the lower-frequency `yearly_orb_scaleout3` through the same external-broker path.

Additional requirements:

- Daily bar source must be settlement-aware and consistent with research assumptions.
- Contract roll resolver matters more because trades can remain open for days/weeks.
- Order expiry must map to broker-supported `GTC` / `GTD` behavior.
- Retest limit orders should be checked daily for validity and canceled/reset on year change.
- Range-close or 20% range-close exits should route as market or market-close style orders at the next configured tradable time.

Acceptance:

- One historical accelerated daily replay still matches plugin replay.
- Demo account can place, cancel, and reconcile one yearly ORB retest limit.
- Demo account can attach/maintain protective exits.
- Restart with open retest orders recovers broker order ids and strategy state.

## Phase 7 - Monitoring, Reporting, And Operator Controls

Objective: make paper trading observable and safe.

Tasks:

- Extend health endpoint:
  - `/feed`
  - `/broker`
  - `/orders`
  - `/positions`
  - `/strategy/{id}`
  - `/risk`
- Add operator commands:
  - `status`
  - `pause-strategy`
  - `resume-strategy`
  - `cancel-strategy-orders`
  - `flatten-strategy`
  - `kill-switch`
- Add notification sinks:
  - disk JSONL remains default
  - email stub -> real SMTP or provider
  - SMS stub -> real provider
- Add report fields:
  - feed freshness
  - broker token expiry
  - account id/spec
  - active contract
  - pending verification
  - working orders with broker ids
  - protective bracket coverage
  - expected next action
  - reconciliation differences

Acceptance:

- Any feed stale, broker auth failure, unbracketed position, or state mismatch produces warning or engine-error alert.
- Kill switch can flatten paper account and persist the result.

## Phase 8 - Paper Promotion Checklist

Before live-money consideration:

- At least 20 RTH paper sessions for v2b OCO.
- At least one contract roll simulation and one real roll week in paper.
- No unexplained local-vs-broker position mismatch.
- No missed EOD flatten.
- No duplicate order submission after restart.
- No unprotected open position after an entry fill.
- Slippage/commission report compared against broker actual fills.
- Manual operator runbook written and followed.
- Real 2FA / approval flow implemented for live entries.
- `paper_only` hard guard removed only in a deliberate code change.

## Recommended Implementation Order

1. Refactor Engine into replay-vs-external broker paths.
2. Add idempotent bar/fill/order storage.
3. Build `CSVLiveFeedAdapter` and prove one-day v2b parity.
4. Implement Tradovate auth/account/contract/order/cancel/reconcile REST subset.
5. Paper test standalone order/cancel/reconcile.
6. Paper test OCO order/cancel/reconcile.
7. Paper test OSO/bracket behavior. If OSO cannot express our scaleout shape cleanly, use explicit child orders after parent fill.
8. Add market-data adapter and 1m bar builder.
9. Run v2b custom sizing in Tradovate demo with no live-money path.
10. Add Yearly ORB after v2b event loop is stable.

## Open Questions

- Which live market-data source should be primary: Tradovate websocket, Databento live, or another feed?
- Does Tradovate `placeoso` support the exact multi-target scaleout shape we need, or should we always place child exits after parent fill?
- Does demo/paper support all order types and OCO/OSO behavior exactly like live?
- How should we select active contracts and roll dates for intraday vs yearly systems?
- Should `market_close` exits be true broker market orders at 15:59, or simulated MOC-like orders at a scheduled time?
- What minimum live approval workflow do we want after paper: local CLI approval, SMS/email approval, or broker-native controls?

