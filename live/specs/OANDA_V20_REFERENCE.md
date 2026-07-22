# OANDA v20 API Reference

Durable notes for wiring OANDA as a potions live **market-data feed** and **broker**. Secrets (personal access tokens) stay in environment variables or local JSON config — **never** commit tokens to this repo.

Upstream SDK: [oanda/v20-python](https://github.com/oanda/v20-python)  
Local vendored tree: [`v20-python/`](../../v20-python/) (import via `PYTHONPATH=v20-python/src` or editable install).

Related implementation contract: [OANDA_ADAPTER.md](OANDA_ADAPTER.md).

## Environments

### REST API

| Environment | URL | Auth |
|-------------|-----|------|
| fxTrade Practice | `https://api-fxpractice.oanda.com` | Bearer personal access token |
| fxTrade (live) | `https://api-fxtrade.oanda.com` | Bearer personal access token |

### Streaming API

| Environment | URL | Auth |
|-------------|-----|------|
| fxTrade Practice | `https://stream-fxpractice.oanda.com/` | Bearer personal access token |
| fxTrade (live) | `https://stream-fxtrade.oanda.com/` | Bearer personal access token |

Documentation examples use the live hostname; for practice, replace the host with the practice URLs above.

## Authentication

Personal traders generate a token from the OANDA account profile: **My Account → My Services → Manage API Access**.

Send the token as a Bearer header:

```http
Authorization: Bearer <personal_access_token>
```

Example:

```bash
curl -H "Authorization: Bearer <token>" \
  https://api-fxpractice.oanda.com/v3/accounts
```

OANDA does not retain the token string after generation; revoke and recreate if lost. Treat a token pasted into chat or tickets as compromised and rotate it.

## Request / response conventions

- Request bodies: `Content-Type: application/json` unless otherwise specified.
- Responses: `Content-Type: application/json` unless otherwise specified.
- DateTime fields follow OANDA’s DateTime definition (RFC3339 in the Python bindings by default).

## Rate and connection limits

| Limit | Value | Notes |
|-------|-------|-------|
| REST requests | 120 / second | Excess → HTTP 429; applied per requesting IP |
| Active streams | 20 | Excess rejected; per IP |
| New connections | ≤ 2 / second | Prefer persistent HTTP keep-alive |

Best practice: reuse one persistent connection; keep established-connection traffic under ~100 req/s.

## Account state loop (recommended)

1. **Startup:** `GET /v3/accounts/{accountID}` (Account Details). Store the full Account snapshot and `lastTransactionID`.
2. **Update:** Poll Account Changes with that `lastTransactionID`.
   - **AccountChanges** — infrequent entity updates (orders, trades, positions, balance). Merge into the snapshot.
   - **AccountState** — frequent price-dependent fields (unrealized PL, NAV, trailing stops). Replace those fields on the snapshot.
3. Advance `lastTransactionID` from each successful poll.

This keeps a consistent account view without re-fetching the entire account on every tick.

## Trading and prices

| Need | Endpoint family |
|------|-----------------|
| Place / cancel / replace orders | Order |
| Real-time quotes | Pricing (REST poll or stream) |
| Historical / candle bars | Instrument candles |
| Fills / account events | Transaction stream or Account Changes |
| Close exposure | Trade close / Position close |

## Practice accounts (this workspace)

| Role | Account ID |
|------|------------|
| Primary (default routing) | `101-002-39860312-001` |
| Secondary (documented only in v1) | `101-002-39860312-002` |

Token: set `OANDA_TOKEN` in the environment (or a local JSON config file outside git). Do not write the token into this document.

## Common HTTP errors

| Status | Typical cause |
|--------|---------------|
| 400 Bad Request | Missing/invalid params; invalid instrument; price precision exceeded |
| 401 Unauthorized | Missing/invalid Bearer token; wrong account ID often surfaces as forbidden |
| 403 Forbidden | Token lacks permission; account not tradable |
| 404 Not Found | Unknown trade / order / transaction ID |
| 405 Method Not Allowed | Wrong HTTP method for the route |
| 429 Too Many Requests | Rate limit |

Notable reject reasons:

- `Invalid value specified for 'instrument'` — use OANDA form (`EUR_USD`, `XAU_USD`), not `EURUSD`.
- `STOP_LOSS_ON_FILL_PRICE_PRECISION_EXCEEDED` — send prices as strings with allowed precision.

## Configure curl examples (OANDA docs UI)

In the OANDA developer docs “Examples” panel:

1. Open Settings next to Request.
2. Set URL to practice or live API host.
3. Set Account and Token (local only).
4. Save — curl snippets update for copy/paste.

## Sample SDK entry points (vendored / upstream)

The [v20-python samples](https://github.com/oanda/v20-python-samples) illustrate account details/changes, candles, pricing stream, market/limit/stop orders, trades, and positions. Prefer potions’ [`live/oanda.py`](../oanda.py) wrapper over calling `v20` directly from strategies.
