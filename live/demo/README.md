# Pilot A — Index / FX v2b Ungated Demo Runners

First paper pilot system (2026-07-22): continuous demos under `live/demo/` — **not** `live/state/`.

## Paper demos (prices only)

OANDA practice stream feeds prices; **PaperBroker** simulates fills. No orders are sent to OANDA.

| Demo | OANDA instrument | Proxy | Artifacts | CLI |
|------|------------------|-------|-----------|-----|
| EURUSD | `EUR_USD` | — | `live/demo/eurusd_v2b_ungated_paper/` | `demo-eurusd-v2b-paper` |
| NAS100 | `NAS100_USD` (US Nas 100) | NQ-ish | `live/demo/nas100_v2b_ungated_paper/` | `demo-nas100-v2b-paper` |
| SPX500 | `SPX500_USD` (US SPX 500) | **ES** | `live/demo/spx500_v2b_ungated_paper/` | `demo-spx500-v2b-paper` |
| US30 | `US30_USD` (US Wall St 30) | **YM** | `live/demo/us30_v2b_ungated_paper/` | `demo-us30-v2b-paper` |

All can run **in parallel** (separate pidfiles / state roots / streams).

## OANDA practice demos (real practice orders)

Same ungated `v2b_scaleout` / `S_1_1_1` as paper, but **`OandaBroker`** routes orders to the practice account. Local CSVs are an audit mirror via Account Changes (not PaperBroker bar fills). Paper daemons stay untouched under `*_paper/` roots.

| Demo | Artifacts | CLI |
|------|-----------|-----|
| EURUSD | `live/demo/eurusd_v2b_ungated_oanda/` | `demo-eurusd-v2b-oanda` |
| NAS100 | `live/demo/nas100_v2b_ungated_oanda/` | `demo-nas100-v2b-oanda` |
| SPX500 | `live/demo/spx500_v2b_ungated_oanda/` | `demo-spx500-v2b-oanda` |
| US30 | `live/demo/us30_v2b_ungated_oanda/` | `demo-us30-v2b-oanda` |

- **Practice only:** `OANDA_ENV=practice`; `allow_live_routing` stays false.
- **Per-daemon price streams** (one instrument each), same topology as paper.
- **Units:** strategy qty maps 1:1 to OANDA units (tiny practice size).
- **Shared margin:** all four share one practice account buying power.
- Session FIFO PnL appends to `ungated_oanda_demo.csv` at NY RTH close (see `session_pnl.py`). Paper session table: `ungated_paper_results.csv`.

```bash
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
export OANDA_ENV=practice OANDA_TOKEN=… OANDA_ACCOUNT_ID=101-002-39860312-001

# Smoke one tiny EURUSD market + reconcile + flatten before overnight
python3 -m potions.live.cli --state-root /tmp/oanda_practice_smoke oanda-practice-order-smoke --units 1

python3 -m potions.live.cli demo-eurusd-v2b-oanda --daemon
python3 -m potions.live.cli demo-nas100-v2b-oanda --daemon
python3 -m potions.live.cli demo-spx500-v2b-oanda --daemon
python3 -m potions.live.cli demo-us30-v2b-oanda --daemon

python3 -m potions.live.cli demo-eurusd-v2b-oanda-status
```

### USDJPY Monday OR (Phase 2 primary)

Tracker / broker Phase 1 #1: **`M2_S3_R1`** (`monday_or_breakout`, N/S ≈ 8.20). See `live/state/monday_or_phase2/SPEC_USDJPY_M2_S3_R1.md`.

| Field | Value |
|------|-------|
| Artifacts | `live/demo/usdjpy_monday_or_ungated_oanda/` |
| CLI | `demo-usdjpy-monday-or-oanda` (+ `-status` / `-stop`) |
| Bars | Quote stream → 1m → **15m** (left-labeled, same as research) |
| Sizing | Main 3=1@30%/2@50%; shifted 4; max 2 primaries/week |

```bash
python3 -m potions.live.cli demo-usdjpy-monday-or-oanda --daemon
python3 -m potions.live.cli demo-usdjpy-monday-or-oanda-status
```

Emergency flatten (practice):

```bash
python3 -m potions.live.cli --state-root /tmp/oanda_flat \
  oanda-emergency-flatten --instruments EURUSD,NAS100,SPX500,US30,USDJPY
```

## Price schema (mid signals / bid-ask fills)

Each 1‑minute bar stores:

| Field | Role |
|-------|------|
| `open/high/low/close` | **Mid** OHLC — strategy signals, OR, filters |
| `bid_*` | Bid OHLC — sell fills / long exits (paper) |
| `ask_*` | Ask OHLC — buy fills / short exits (paper) |

Workflow:

1. Aggregate OANDA ticks into bid, ask, mid.
2. Build 1m OHLC for all three on the same `Bar`.
3. Run `v2b_scaleout` on **mid**.
4. Paper fills: **buy → ask**, **sell → bid** (no synthetic `SpreadModel` double-count).
5. OANDA demos: fills from Account Changes (broker truth); local `fills.csv` is the mirror.
6. Each fill records `mid_price`, `bid_price`, `ask_price`, `spread` when available for before/after-spread audit.

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
| NY RTH | Every tick → `events/rth_ticks/YYYY-MM-DD.jsonl` | Persist + `Engine.process_bar` | Intents / fills / positions |

## Run (paper)

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
- **Friday RTH close (EOW):** each daemon echoes `FILE_SIZES` lines into `PROGRESS.log` and appends `FILE_SIZES.log` (price data + log sizes) for rotation planning — see `size_report.py`. Weekend baseline: `FILE_SIZES_BASELINE_YYYY-MM-DD.md`
- SPX500/US30/NAS100 are OANDA index CFDs, not CME futures — used here as ES/YM/NQ-style proxies only

## NQ-lead NAS100 synced follower (replay)

Research replay only: NAS100 rides NQ prior-opposed **campaign entries** when synced. NQ gates entry; NAS manages local `S_1_1_1` / EOD exits. Original NQ and standalone NAS100 prior-opposed paths are unchanged.

| Knob | Default |
|------|---------|
| `T_max` | 60s |
| `Δ_early` | 30s |
| Lead book | `live/state/nq_v2b_prior_opposed_stpmc_broker_like/` |
| Output | `live/state/nas100_v2b_nq_lead_synced_broker_like/` |
| Dollar standard | **×40** on native `$1`/pt (entry reading: **3 @ $40/pt** = $120/pt, or 120 @ $1/pt) |

```bash
PYTHONPATH=/home/tester/hsm python3 -m potions.live.nq_lead_nas100_prior_opposed_replay \
  --start 2021-03-04 \
  --t-max-seconds 60 \
  --nq-state-root potions/live/state/nq_v2b_prior_opposed_stpmc_broker_like
```

Strategy type: `v2b_nq_lead_nas100`. See output `sync_audit.csv` for entered vs skipped (`sync_window_expired`, `nq_already_scaled`, …).
