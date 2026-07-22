# Pilot A — Index / FX v2b Ungated Demo Paper Runners

First paper pilot system (2026-07-22): paper-only continuous demos under `live/demo/` — **not** `live/state/`. OANDA practice stream feeds prices; **PaperBroker** simulates fills. No orders are sent to OANDA.

| Demo | OANDA instrument | Proxy | Artifacts | CLI |
|------|------------------|-------|-----------|-----|
| EURUSD | `EUR_USD` | — | `live/demo/eurusd_v2b_ungated_paper/` | `demo-eurusd-v2b-paper` |
| NAS100 | `NAS100_USD` (US Nas 100) | NQ-ish | `live/demo/nas100_v2b_ungated_paper/` | `demo-nas100-v2b-paper` |
| SPX500 | `SPX500_USD` (US SPX 500) | **ES** | `live/demo/spx500_v2b_ungated_paper/` | `demo-spx500-v2b-paper` |
| US30 | `US30_USD` (US Wall St 30) | **YM** | `live/demo/us30_v2b_ungated_paper/` | `demo-us30-v2b-paper` |

All can run **in parallel** (separate pidfiles / state roots / streams).

## Price schema (mid signals / bid-ask fills)

Each 1‑minute bar stores:

| Field | Role |
|-------|------|
| `open/high/low/close` | **Mid** OHLC — strategy signals, OR, filters |
| `bid_*` | Bid OHLC — sell fills / long exits |
| `ask_*` | Ask OHLC — buy fills / short exits |

Workflow:

1. Aggregate OANDA ticks into bid, ask, mid.
2. Build 1m OHLC for all three on the same `Bar`.
3. Run `v2b_scaleout` on **mid**.
4. Paper fills: **buy → ask**, **sell → bid** (no synthetic `SpreadModel` double-count).
5. Each fill records `mid_price`, `bid_price`, `ask_price`, `spread` for before/after-spread audit.

RTH ticks in `events/rth_ticks/` include `bid`, `ask`, `mid`, `spread`.

## Strategy

- `v2b_scaleout` OCO ungated (`prior_opposite_only=false`)
- Sizing `S_1_1_1` (entry 3 / tp1 1 / tp2 1)
- `use_regime_filter=false` so every NY RTH session can arm
- Index CFD tick size `0.1` (OANDA `displayPrecision=1`); EURUSD tick `0.00001`

## RTH behavior (America/New_York)

| Phase | Ticks | 1m bars | Strategy |
|-------|-------|---------|----------|
| Outside 09:30–16:00 | Stream alive; no tick JSONL | Persist OHLC (with quotes) to `state/bars/` only | Idle |
| NY RTH | Every tick → `events/rth_ticks/YYYY-MM-DD.jsonl` | Persist + `Engine.process_bar` | Paper intents / fills / positions |

## Run

```bash
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
export OANDA_ENV=practice OANDA_TOKEN=… OANDA_ACCOUNT_ID=101-002-39860312-001

python3 -m potions.live.cli demo-eurusd-v2b-paper --daemon
python3 -m potions.live.cli demo-nas100-v2b-paper --daemon
python3 -m potions.live.cli demo-spx500-v2b-paper --daemon
python3 -m potions.live.cli demo-us30-v2b-paper --daemon

python3 -m potions.live.cli demo-spx500-v2b-paper-status
python3 -m potions.live.cli demo-us30-v2b-paper-status
```

## Notes

- Process keeps running until `*-stop` / SIGTERM
- Reconnects on stream drop with backoff
- Session clocks / order expiry use America/New_York (see v2b `_parse_dt` / `_session_expiry`)
- At NY RTH close the daemon writes an EOD position chart via `live/demo/eod_charts.py` to `charts/{symbol}_v2b_position_YYYY-MM-DD.png`
- SPX500/US30/NAS100 are OANDA index CFDs, not CME futures — used here as ES/YM/NQ-style proxies only
