# Live Runtime Specs

Persistent implementation specs for moving `potions/live/` from broker-like replay into paper/live automation.

## Specs

- [Market Data Feed Requirements](MARKET_DATA_FEEDS.md)
- [Tradovate Market Data Feed](TRADOVATE_MARKET_DATA_FEED.md)
- [Tradovate Adapter](TRADOVATE_ADAPTER.md)
- [Operational Fault Protocol](OPERATIONAL_FAULT_PROTOCOL.md)
- [Platform Hardening Upgrades](PLATFORM_HARDENING_UPGRADES.md)
- [KDB+ Migration Plan](KDB_MIGRATION_PLAN.md)
- [Databento Market Data Feed](DATABENTO_MARKET_DATA_FEED.md)
- [CQG WebAPI Adapter](CQG_WEBAPI_ADAPTER.md)
- [OANDA v20 API Reference](OANDA_V20_REFERENCE.md)
- [OANDA Adapter](OANDA_ADAPTER.md)
- [Start-Small Broker Execution Plan](START_SMALL_BROKER_EXECUTION_PLAN.md)
- [Start-Small Cloud Bootstrap](START_SMALL_CLOUD_BOOTSTRAP.md)

## Current Read

The runtime should support two independent but reconciled streams:

1. **Market data stream**: produces completed bars for strategies.
2. **Broker stream**: owns order state, fills, positions, margin, and account truth.

**Pilot A (2026-07-22, active):** OANDA practice **pricing** → 1m mid/bid/ask bars → `v2b_scaleout` → local **PaperBroker**. Parallel demos: EURUSD, NAS100, SPX500 (ES proxy), US30 (YM proxy). See [live/demo/README.md](../demo/README.md) and the status section in [LIVE_FEED_PAPER_TRADING_EXECUTION_PLAN.md](../LIVE_FEED_PAPER_TRADING_EXECUTION_PLAN.md).

Longer-term safest paper routes:

- Use **one feed provider** to build completed 1m/5m/daily bars.
- Use **Tradovate demo/sim** for CME futures order routing, fills, position reconciliation, and emergency flattening.
- Use **OANDA practice** for FX/metals/index CFD feed; complete order burn-in before any OANDA live routing.
- Keep CQG as a deferred secondary futures adapter path.
- Keep broker-side protective orders active after entry so feed outages cannot leave the account naked.

## Source Notes

As of 2026-05-22:

- Tradovate order/account endpoints and WebSocket protocol notes are covered by `live/openapi.json`.
- Tradovate market data uses the WebSocket/chart flow described in that same checked-in spec.
- Databento live data uses its Python/Raw Live API, with `GLBX.MDP3` as the relevant CME Globex dataset family for NQ/MNQ/ES/MES/YM/MYM-style futures work.

As of 2026-07-22:

- OANDA v20 practice/live REST and streaming hosts, auth, and account-changes loop are summarized in `OANDA_V20_REFERENCE.md`.
- Local SDK clone lives at `v20-python/`; potions wraps it in `live/oanda.py`.
- First paper pilot pack runs under `live/demo/` with NY-aware session/expiry on the v2b + PaperBroker path.
Primary references checked:

- Tradovate Partner API cheat sheet: `https://partner.tradovate.com/resources/reference/api-cheat-sheet`
- Tradovate market-data conformance guide: `https://partner.tradovate.com/overview/conformance-testing/stage-5-market-data-access`
- Tradovate market-data subscription note: `https://tradovate.zendesk.com/hc/en-us/articles/205146178-How-Can-I-Subscribe-to-or-Change-My-Market-Data`
- Tradovate order-without-market-data note: `https://tradovate.zendesk.com/hc/en-us/articles/4403100181651-Do-I-Need-a-Market-Data-Subscription-Through-Tradovate-to-Perform-Trades`
- Databento Live API subscribe docs: `https://databento.com/docs/api-reference-live/client/subscribe`
