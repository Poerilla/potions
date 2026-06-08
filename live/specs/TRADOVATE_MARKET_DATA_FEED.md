# Tradovate Market Data Feed Spec

## Purpose

Use Tradovate market data as a live/paper feed for strategies while using Tradovate broker/account APIs for order routing and reconciliation.

This is separate from `live/openapi.json`. The local OpenAPI file covers REST order/account/fill/position operations, but live market data is a WebSocket API.

## Current Public Endpoints

Production market-data WebSocket:

```text
wss://md.tradovateapi.com/v1/websocket
```

Production user/broker WebSockets:

```text
wss://demo.tradovateapi.com/v1/websocket
wss://live.tradovateapi.com/v1/websocket
```

REST base URLs:

```text
https://demo.tradovateapi.com/v1
https://live.tradovateapi.com/v1
```

Source notes:

- Tradovate Partner API cheat sheet lists the production market-data WebSocket and live/demo user WebSocket URLs.
- Tradovate Stage 5 Market Data Access describes market-data authorization, quote subscription, DOM, chart data, and tick chart processing.
- Tradovate support notes indicate market-data subscriptions are managed separately from order/API permissions. Do not assume order-routing permission implies live market-data entitlement.
- As checked on 2026-05-23, Tradovate support lists API access requirements as: live account greater than `$1,000`, CME Information License Agreement, and the API Access add-on. Their non-professional data page lists Level I top-of-book at `$4/month` per CME-group exchange or `$12/month` for the CME Group bundle. Confirm the API add-on price inside the Tradovate application before funding; the public support page confirms the add-on but does not show its live dollar amount in text.

## Required Capabilities

The Tradovate feed adapter must support:

- REST token acquisition through the existing Tradovate auth flow.
- Market-data WebSocket connect.
- WebSocket authorization with the access token.
- Heartbeat handling.
- Reconnect and reauthorization.
- Quote subscription for diagnostics.
- Chart/minute-bar subscription or chart request for 1m bars.
- Optional tick/DOM subscription if we later need true trade-based local bars.
- Stale-feed detection.
- Raw message persistence.
- Normalization into `MarketTick` and/or `CompletedBar`.

## Authorization Flow

1. Acquire an access token from REST auth.
2. Open the market-data WebSocket.
3. Send an authorization message.
4. Wait for successful auth response before subscribing.

Example wire shape from Tradovate docs:

```text
authorize
1

<accessToken>
```

Implementation note: Tradovate WebSocket examples show newline-delimited messages. Keep the exact encoding in a small protocol helper and cover it with tests, because examples across snippets sometimes differ on JSON string wrapping.

## Subscription Types

### Quote Diagnostics

Use quote subscriptions to verify that the contract is live and entitlement is correct.

```text
md/subscribeQuote
<request_id>

{"symbol":"MNQM6"}
```

The feed layer should not drive strategy bars from quote midpoints unless we explicitly choose quote-based bars. For v2b and ORB systems, trade/minute OHLC is preferred.

### Chart / Minute Bars

Use chart data for the first paper implementation if it provides stable completed minute bars.

Target:

```text
md/getChart
<request_id>

{
  "symbol": "MNQM6",
  "chartDescription": {
    "underlyingType": "MinuteBar",
    "elementSize": 1,
    "elementSizeUnit": "UnderlyingUnits",
    "withHistogram": false
  },
  "timeRange": {
    "asMuchAsElements": 200
  }
}
```

Requirements:

- Only emit a strategy `Bar` after the minute is complete.
- Convert Tradovate timestamps into canonical UTC and New York session labels.
- Verify whether chart bars are trade-based, bid/ask based, or platform-normalized.
- Verify whether chart bars include RTH-only filtering or full Globex unless specified.

## v2b Requirements

For v2b OCO paper trading:

- Need exact RTH 09:30-16:00 New York handling.
- Need 09:30-09:45 opening range from completed 1m bars, then 5m-derived logic.
- Need stop entry levels at range boundaries plus tick.
- Need same session cutoff / flatten rules as the plugin.
- Need no partial/incomplete 5m bars passed to the strategy.

## Yearly ORB Requirements

For yearly ORB:

- Daily bars must be consistent with the research/session definition.
- Jan-Mar range building must use completed daily bars only.
- Apr-Dec trade logic must run after completed daily close.
- If Tradovate chart daily bars differ from our research daily files, the report must show the difference.

## State Files

Add or populate:

- `market_data_status.json`
- `raw_market_data/tradovate/YYYY-MM-DD.jsonl`
- `bars/{instrument}_1m.csv`
- `bars/{instrument}_5m.csv`
- `bars/{instrument}_D.csv`
- `market_data_adjustments.jsonl`
- `feed_broker_bar_audit.csv`

## Failure Handling

Block new entries when:

- auth fails
- subscription rejected
- symbol unresolved
- feed stale
- current active contract cannot be mapped to broker tradable symbol
- expected 1m/5m bar is missing
- local clock drift exceeds tolerance

Do not block:

- broker-side protective stops
- broker-side emergency flatten
- position/order reconciliation

## Acceptance Checklist

- Connects to demo/paper environment with no live routing enabled.
- Subscribes to one MNQ contract and writes raw messages.
- Produces completed 1m bars for at least one full RTH session.
- Derives 5m bars and matches expected v2b OR construction.
- Alerts on disconnect/stale feed.
- Reconnects and backfills or blocks new entries when gap cannot be recovered.
- Market-close report compares Tradovate feed bars to stored research/data-provider bars.

## Open Questions

- Exact non-display/API market-data entitlement required for our account type.
- Whether Tradovate chart bars are stable enough for strategy logic or whether we should build bars from trade/tick messages.
- Whether demo market-data behavior matches live entitlement behavior.
- Whether the prop/paper account environment exposes the same feed paths as normal Tradovate demo/live.

## References

- `https://partner.tradovate.com/resources/reference/api-cheat-sheet`
- `https://partner.tradovate.com/overview/conformance-testing/stage-5-market-data-access`
- `https://tradovate.zendesk.com/hc/en-us/articles/205146178-How-Can-I-Subscribe-to-or-Change-My-Market-Data`
- `https://tradovate.zendesk.com/hc/en-us/articles/4403100181651-Do-I-Need-a-Market-Data-Subscription-Through-Tradovate-to-Perform-Trades`
