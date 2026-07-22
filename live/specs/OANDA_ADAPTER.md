# OANDA Adapter

Status: **Pilot A active** — OANDA fxTrade **practice** pricing stream feeds four parallel `v2b_scaleout` paper demos; fills stay on local **PaperBroker**. Live (`fxtrade`) order routing remains blocked unless `allow_live_routing=True` after the practice order burn-in checklist below.

OANDA is the **FX / metals / index CFD** adapter path for this pilot. Tradovate remains the CME futures paper/live track; CQG stays deferred.

API reference: [OANDA_V20_REFERENCE.md](OANDA_V20_REFERENCE.md)  
Upstream SDK: [oanda/v20-python](https://github.com/oanda/v20-python) · vendored [`v20-python/`](../../v20-python/)  
Pilot operator docs: [live/demo/README.md](../demo/README.md)

## Provider Choice

Use OANDA when strategies need:

- Practice/live FX spot and metals (e.g. `EURUSD`, `XAUUSD`)
- Index CFDs as CME proxies (`NAS100_USD`, `SPX500_USD` / ES, `US30_USD` / YM)
- Account Details + Changes as broker truth (order-routing path; not used by Pilot A fills)
- Pricing stream / candles for completed bars

Do **not** route CME futures through this adapter.

## Practice Defaults

Environment variables stay outside the repo:

- `OANDA_ENV=practice` (or `live`)
- `OANDA_API_URL` — default `https://api-fxpractice.oanda.com` when practice
- `OANDA_STREAM_URL` — default `https://stream-fxpractice.oanda.com` when practice
- `OANDA_TOKEN` — personal access token (required for network smoke)
- `OANDA_ACCOUNT_ID` — default primary `101-002-39860312-001`
- `OANDA_INSTRUMENT_MAP` — e.g. `EURUSD=EUR_USD,NAS100=NAS100_USD,SPX500=SPX500_USD,US30=US30_USD`

Optional local JSON (not committed): `--oanda-config path.json` with the same keys (`env`, `api_url`, `stream_url`, `token`, `account_id`, `instrument_map`).

Secondary account `101-002-39860312-002` is documented for later multi-account work; v1 routes only the primary.

Pilot instruments: **EURUSD**, **NAS100**, **SPX500**, **US30** (plus **XAUUSD** mapped for adapter smoke).

### Units / lot sizing

OANDA order size is **signed units** (positive = buy/long, negative = sell/short).

| potions field | OANDA mapping |
|---------------|---------------|
| `OrderIntent.quantity` | Absolute units (integer) |
| `OrderIntent.side` `buy` / `sell` | Sign of `units` |
| Internal root `EURUSD` | Instrument `EUR_USD` |
| Internal root `XAUUSD` | Instrument `XAU_USD` |

Example: buy 1000 units of EURUSD → `units=1000`, instrument `EUR_USD`.  
Sell 10 units of XAUUSD → `units=-10`, instrument `XAU_USD`.

Prices on stop-loss / take-profit on fill must be strings with instrument precision or OANDA rejects with `PRECISION_EXCEEDED`.

## Importing the vendored SDK

```bash
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
# v20 dependencies (trusted-host if SSL verify fails on this host):
python3 -m pip install --user --trusted-host pypi.org --trusted-host files.pythonhosted.org requests ujson
```

`live/oanda.py` prepends `v20-python/src` on first Context create and shims stdlib `json` as `ujson` when `ujson` is not installed. `requests` is still required for network smoke.

## Implemented Files

- `live/oanda.py`
  - `OandaConfig`
  - `OandaApiClient` (thin `v20.Context` wrapper)
  - `OandaMarketDataFeedAdapter`
  - `OandaBroker`
  - `QuoteOneMinuteBarBuilder` (mid + bid/ask OHLC)
- `live/cli.py`
  - `oanda-smoke`, `oanda-stream-prices`, `oanda-feed-shadow`, `oanda-paper`, `oanda-emergency-flatten`
  - `demo-{eurusd,nas100,spx500,us30}-v2b-paper` (+ `-status` / `-stop`)
- `live/demo/*_v2b_ungated_paper.py` — Pilot A runners
- `live/tests/test_oanda_adapter.py`, `test_demo_eurusd_v2b_ungated_paper.py`
- `live/instruments.py` — FX + index CFD catalog entries

## Practice Burn-in Checklist

Complete before any `OANDA_ENV=live` or `allow_live_routing=True`:

1. Rotate any token that was pasted into chat/tickets; store only in env/local JSON. *(ops — treat pilot token as compromised if pasted)*
2. `oanda-smoke --offline` passes on a clean tree. **Done**
3. Credentialed practice: account details, instruments list, pricing snapshot (incl. `EUR_USD`, index CFDs). **Done (pilot)**
4. Account Details → store `lastTransactionID`; poll Account Changes for several minutes with no errors. *Open (order path)*
5. Pricing stream → completed 1m mid/bid/ask bars for RTH windows. **Done (Pilot A demos)**
6. Place one tiny practice **market** order; confirm fill via Changes/transactions; reconcile position. *Open*
7. Place limit + cancel; confirm order lifecycle in local audit + OANDA UI. *Open*
8. Attach SL/TP on fill; verify precision strings; no `PRECISION_EXCEEDED`. *Open*
9. Run `oanda-emergency-flatten` on practice with an open position; confirm flat. *Open*
10. Restart mid-session; prove no duplicate entries and open-order state recovers from Account Details. *Partial — PaperBroker restart/re-arm proven; OANDA order recovery open*
11. Only then consider live env with explicit `allow_live_routing=True` and reduced size.

## Remaining Work After Pilot A

1. Quote-side stop **triggers** (today: mid high/low trigger, ask/bid fill).
2. NY-aware `_parse_dt` / expiry on sibling strategies (`or_2r_fade`, `v2b_clean_break`).
3. OANDA practice order burn-in (checklist 4, 6–11) before any live routing.
4. Multi-account routing for the secondary practice account.
5. Engine split: sim `process_bar` vs external broker events (see live feed plan Phase 1).
6. Compliance review before funded live use.

## Market Data Contract

The feed adapter writes:

- `market_data_status.json`
- `events/raw_market_data/oanda/YYYY-MM-DD.jsonl`
- `events/oanda_session_events.jsonl`
- `feed_broker_bar_audit.csv`
- existing `bars/*.csv`

Accepted offline/event types:

- `instrument_resolution` — bind internal root → OANDA instrument
- `trade` / `price` — mid/trade ticks → 1m builders → derived 5m
- `bar` — completed vendor bars
- `candle` — OANDA candle-shaped payloads
- `market_data_status` — blocking statuses

Entry freeze when:

- instrument unresolved,
- status delayed / denied / stale,
- provider-neutral feed stale.

Broker protective exits, reconciliation, and emergency flatten must **not** be blocked by a stale feed.

## Broker Contract

`OandaBroker` implements `BaseBroker`. When enabled, OANDA is order/fill/position/account truth; local CSVs are an audit mirror.

Scaffold support:

- Market / Limit / Stop create via Order endpoints
- Cancel pending order
- Limit/Stop replace (modify)
- Stop-loss / take-profit **on fill** when intent brackets are set
- Account Details + Account Changes poll helpers
- Fill / order-status event handlers (transaction stream or offline JSONL)
- `go_flat` — cancel working orders + close positions for mapped instruments
- `process_bar` returns `[]` (fills come from account/transaction events)

Live gate: `OANDA_ENV != practice` requires `allow_live_routing=True`.

## CLI Usage

Offline config smoke:

```bash
PYTHONPATH=/home/tester/hsm:/home/tester/hsm/potions/v20-python/src \
  python -m potions.live.cli --state-root /tmp/oanda_state oanda-smoke --offline
```

Network practice smoke (needs `OANDA_TOKEN`):

```bash
export OANDA_ENV=practice
export OANDA_TOKEN=...
export OANDA_ACCOUNT_ID=101-002-39860312-001
PYTHONPATH=/home/tester/hsm:/home/tester/hsm/potions/v20-python/src \
  python3 -m potions.live.cli --state-root /tmp/oanda_state oanda-smoke
```

Stream live bid/ask to the console (Ctrl-C to stop):

```bash
PYTHONPATH=/home/tester/hsm:/home/tester/hsm/potions/v20-python/src \
  python3 -m potions.live.cli --state-root /tmp/oanda_state \
  oanda-stream-prices --instruments EURUSD,XAUUSD --max-ticks 20
```

EURUSD v2b ungated **paper demo** (OANDA prices → local PaperBroker; artifacts under `live/demo/`):

```bash
PYTHONPATH=/home/tester/hsm:/home/tester/hsm/potions/v20-python/src \
  python3 -m potions.live.cli demo-eurusd-v2b-paper --daemon
```

See [live/demo/README.md](../demo/README.md).

Replay saved OANDA-like JSONL into bars:

```bash
PYTHONPATH=/home/tester/hsm python -m potions.live.cli --state-root /tmp/oanda_state \
  oanda-feed-shadow --events oanda_events.jsonl
```

Paper scaffold (feed + broker event replay):

```bash
PYTHONPATH=/home/tester/hsm python -m potions.live.cli --state-root /tmp/oanda_state \
  oanda-paper --events oanda_events.jsonl
```

Emergency flatten scaffold:

```bash
PYTHONPATH=/home/tester/hsm python -m potions.live.cli --state-root /tmp/oanda_state \
  oanda-emergency-flatten --instruments EURUSD,XAUUSD
```
