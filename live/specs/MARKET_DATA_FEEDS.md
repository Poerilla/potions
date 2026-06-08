# Market Data Feed Requirements

## Goal

Create a provider-neutral feed layer that can drive StrategyPlugin execution from completed bars while preserving enough raw data to audit mismatches between research, live feed, and broker fills.

This spec covers:

- Tradovate market-data WebSocket
- Databento live feed
- Any future direct feed such as Rithmic, CQG, IQFeed, broker-native websocket, or an exchange-normalized vendor

## Required Runtime Contract

Every feed adapter must produce normalized events:

```python
MarketDataStatus(
    provider: str,
    connected: bool,
    authenticated: bool,
    subscriptions: list[str],
    last_message_ts_utc: str,
    last_exchange_ts_utc: str,
    stale: bool,
    last_error: str,
)

MarketTick(
    provider: str,
    instrument: str,
    broker_instrument: str,
    ts_event_utc: str,
    ts_recv_utc: str,
    price: float,
    size: float,
    side: str,          # buy | sell | none when known
    source_seq: str,
    raw_ref: str,
)

CompletedBar(
    instrument: str,
    broker_instrument: str,
    timeframe: str,    # 1m | 5m | 15m | 4h | D
    ts: str,           # bar close timestamp, UTC or explicit offset
    open: float,
    high: float,
    low: float,
    close: float,
    volume: float,
    source: str,
    complete: True,
)
```

The existing `Bar` model can represent `CompletedBar`, but live mode also needs provider metadata in sidecar status/event files.

## Bar Construction Rules

All strategies must receive completed bars only.

Required behavior:

- Store raw feed messages before aggregation whenever practical.
- Build bars in `America/New_York` session logic for RTH intraday systems.
- Store bar timestamps consistently as bar-close timestamps.
- Emit a bar only after the interval has fully elapsed.
- De-duplicate bars by `(instrument, timeframe, ts, source)`.
- Rebuild 5m/15m/4h bars from 1m bars where possible instead of trusting multiple provider aggregations.
- Use the same bar builder for live feed, accelerated replay, and feed validation tests.

Required timeframes:

- `1m`: base for v2b and intraday validation.
- `5m`: v2b opening range and breakout logic.
- `15m`: optional ORB diagnostics.
- `4h`: monthly overlap/retest candidates.
- `D`: yearly/monthly ORB and ATR systems.

## Feed Health Requirements

The feed adapter must update `market_data_status.json` with:

- provider
- connection state
- authentication state
- subscribed symbols
- last raw message time
- last event/exchange time
- last completed 1m bar
- last completed 5m bar
- stale flag
- reconnect count
- dropped/gap count
- last error

Default blocking rules:

- Block new intraday entries if 1m data is stale for more than 10 seconds during RTH.
- Block new 5m-bar strategies if the latest expected 5m bar is missing.
- Do not block broker-side protective exits because of feed staleness.
- If feed is stale while a position is open, send warning alerts and rely on broker-side stops/brackets.

## Backfill And Reconnect

Every provider must support one of:

- native intraday replay/backfill, or
- a separate historical API, or
- a broker/chart fallback, or
- explicit "gap not recoverable" status that blocks new entries.

Required reconnect behavior:

- Record disconnect timestamp and last good event timestamp.
- On reconnect, backfill from last completed bar or last event if supported.
- Re-aggregate affected bars.
- If a completed strategy bar changes after backfill, flag it in `market_data_adjustments.jsonl`.
- Never silently overwrite bars that have already triggered orders.

## Broker Feed vs Non-Broker Feed Risks

Using a feed that is not the broker's feed is viable, but it creates real operational risk. The big one: **strategy decisions may be based on one representation of price while orders trigger, fill, and mark risk in another system.**

Primary risks:

- **Symbol mismatch**: Databento parent/continuous symbols may not match the exact Tradovate routable contract.
- **Roll mismatch**: research may use front-month or continuous logic while live orders must route to one concrete contract.
- **Bar mismatch**: provider-built bars can differ from broker chart bars due to session templates, settlement handling, late prints, corrections, filtering, or timestamp convention.
- **Trigger mismatch**: a stop entry may trigger at the broker even if the external feed's bar does not show the same high/low, or the external feed may show a breakout that the broker chart does not.
- **Latency mismatch**: faster direct feed can generate an entry before the broker platform visually confirms the same bar; slower feed can miss a valid setup.
- **Gap-through modeling mismatch**: broker fills stops at actual marketable prices; feed-only simulations can accidentally assume stop price fills.
- **Outage mismatch**: the data provider can be down while the broker is still routing orders, or the broker can be degraded while the feed looks healthy.
- **Entitlement/licensing mismatch**: exchange data agreements often distinguish display, non-display, API, professional, and redistribution use.
- **Volume mismatch**: vendor volume may aggregate differently from broker charts, which matters if volume becomes a false-breakout detector.
- **Clock mismatch**: local machine, provider event time, provider receive time, and broker order timestamps can drift.

Mitigations:

- Use exact tradable contracts in live configs; continuous contracts are research-only.
- Store `instrument` and `broker_instrument` on every tick, bar, order, fill, and report.
- Compare daily provider bars to broker chart/broker API bars during paper trading.
- Use broker order/fill/position state as account truth, not feed-derived position assumptions.
- Keep protective stops/brackets at the broker.
- Persist raw feed data and normalized bars for audit.
- Add a feed-vs-broker close/high/low report at market close.
- Require NTP/chrony or equivalent clock sync on the runtime host.
- Block new entries on feed staleness or unresolved contract mapping.
- Make feed provider a strategy config field so paper reports identify the source.

## Minimum Acceptance Tests

Each feed implementation needs these tests before paper trading:

- Can authenticate and subscribe to a known CME futures contract.
- Can write raw messages and completed 1m bars.
- Can derive 5m bars from 1m bars.
- Can replay a known RTH day and match existing broker-like replay order timing.
- Can reconnect and backfill or explicitly block new entries on unrecoverable gaps.
- Can detect duplicate messages and duplicate bars.
- Can detect stale feed and alert.
- Can run for a full RTH session without dropping expected 1m bars.
- Can produce a market-close feed audit report.

## Preferred Implementation Order

1. `CSVLiveFeedAdapter`: stream existing 1m files through the live event loop.
2. `BarBuilder`: one implementation shared by CSV, Tradovate, Databento.
3. `DatabentoLiveFeedAdapter` or `TradovateMarketDataFeedAdapter`.
4. Feed-vs-broker audit report.
5. Dual-feed observer mode, if we want redundancy.

