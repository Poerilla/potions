# `live/demo` — Pilot A live demos

Continuous **paper** and **OANDA practice** runners. Artifacts live **here** (`live/demo/<run>/`), not under `live/state/`.

All commands below assume repo root `…/hsm/potions` (or set `PYTHONPATH` as shown).

```bash
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
# Creds: live/demo/.env  (gitignored) — OANDA_ENV / OANDA_ACCOUNT_ID / OANDA_TOKEN
# Or export the same vars in the shell before spawning daemons.
```

---

## Live status (how to check everything)

### 1) Daemon up / down (all 14)

```bash
python3 -m potions.live.cli demo-eurusd-v2b-paper-status
python3 -m potions.live.cli demo-nas100-v2b-paper-status
python3 -m potions.live.cli demo-spx500-v2b-paper-status
python3 -m potions.live.cli demo-us30-v2b-paper-status

python3 -m potions.live.cli demo-eurusd-v2b-oanda-status
python3 -m potions.live.cli demo-nas100-v2b-oanda-status
python3 -m potions.live.cli demo-spx500-v2b-oanda-status
python3 -m potions.live.cli demo-us30-v2b-oanda-status

python3 -m potions.live.cli demo-usdjpy-monday-or-paper-status
python3 -m potions.live.cli demo-usdjpy-monday-or-oanda-status

python3 -m potions.live.cli demo-us30-hourly-st-pmc-paper-status
python3 -m potions.live.cli demo-us30-hourly-st-pmc-oanda-status
python3 -m potions.live.cli demo-us30-hourly-st-pmc-2r10r-paper-status
python3 -m potions.live.cli demo-us30-hourly-st-pmc-2r10r-oanda-status
python3 -m potions.live.cli demo-nas100-hourly-st-pmc-paper-status
python3 -m potions.live.cli demo-nas100-hourly-st-pmc-oanda-status
python3 -m potions.live.cli demo-nas100-hourly-st-pmc-2r10r-paper-status
python3 -m potions.live.cli demo-nas100-hourly-st-pmc-2r10r-oanda-status
```

Each prints: `pid=… alive=True|False started_at=… state=…` (OANDA / Monday OR also show `routing=` / `tag=`).

**One-liner inventory** (pidfile + last heartbeat):

```bash
python3 - <<'PY'
from pathlib import Path
import os
ROOT = Path("live/demo")
for d in sorted(ROOT.iterdir()):
    if not (d / "pidfile").exists():
        continue
    pid = int((d / "pidfile").read_text().strip().splitlines()[0])
    try:
        os.kill(pid, 0); alive = True
    except Exception:
        alive = False
    prog = (d / "PROGRESS.log").read_text(errors="replace").strip().splitlines()
    print(f"{d.name:42} pid={pid} alive={alive}  {prog[-1][:100] if prog else ''}")
PY
```

### 1b) OANDA practice account vs local CSVs

```bash
python3 -m potions.live.cli oanda-practice-sync
python3 -m potions.live.cli oanda-practice-sync --repair-demo-positions
```

Snapshot + report: `live/demo/oanda_practice_snapshot/`. Agent skill: `.cursor/skills/potions-oanda-reconcile/`.

### 2) Fills (authoritative trade tape)

Per demo:

```text
live/demo/<run>/state/fills.csv
```

Columns that matter: `ts`, `side`, `quantity`, `price`, `reason`, `trade_id`, `mid_price`, `bid_price`, `ask_price`, `spread`.

```bash
# Latest fills for one demo
column -s, -t < live/demo/us30_v2b_ungated_paper/state/fills.csv | tail -20

# Reason mix
python3 - <<'PY'
import pandas as pd
df = pd.read_csv("live/demo/us30_v2b_ungated_paper/state/fills.csv")
print(df["reason"].value_counts())
print(df.tail(10)[["ts","side","quantity","price","reason"]])
PY
```

**v2b reasons:** `entry`, `tp1`, `tp2`, `wide_stop`, `runner_stop`, `eod_close`  
**Monday OR reasons:** `entry`, plus bracket exits (`dd30` / `dd50` stops, `target`, Friday flatten)

Mirror JSONL (same events): `state/events/fills.jsonl`.

### 3) Open position / trade status

```text
live/demo/<run>/state/positions.csv   # quantity != 0 → open
live/demo/<run>/state/orders.csv      # status working/submitted → resting brackets
live/demo/<run>/state/order_intents.csv
live/demo/<run>/state/strategy_state.csv   # plugin JSON state (OR levels, phase, etc.)
live/demo/<run>/state/health.json          # last bar / status
```

```bash
python3 - <<'PY'
import pandas as pd
from pathlib import Path
root = Path("live/demo/usdjpy_monday_or_ungated_paper/state")
pos = pd.read_csv(root / "positions.csv")
print("OPEN POSITIONS")
print(pos[pos["quantity"].astype(float) != 0])
orders = pd.read_csv(root / "orders.csv")
print("\nRESTING ORDERS")
print(orders[orders["status"].isin(["working","submitted","accepted","pending","open"])]
      [["side","order_type","quantity","status","stop_price","limit_price","bracket_role"]])
PY
```

### 4) PnL

**A. Session ledger (auto-written at NY RTH close)**

| Path | Contents |
|------|----------|
| `live/demo/ungated_paper_results.csv` | Paper v2b session FIFO USD + path summary |
| `live/demo/ungated_oanda_demo.csv` | OANDA practice v2b session FIFO USD |

Columns: `demo`, `session_date`, `path`, `usd` (includes a `TOTAL` row per date).

```bash
column -s, -t < live/demo/ungated_paper_results.csv
column -s, -t < live/demo/ungated_oanda_demo.csv
```

**B. Recompute FIFO PnL from fills for any NY session** (same helper daemons use):

```bash
python3 - <<'PY'
from datetime import date
from pathlib import Path
from potions.live.demo.session_pnl import load_session_fills, fifo_pnl_from_fills, summarize_fill_path

session = date(2026, 7, 27)  # NY calendar date
fills_path = Path("live/demo/nas100_v2b_ungated_paper/state/fills.csv")
fills = load_session_fills(fills_path, session)
raw, usd = fifo_pnl_from_fills(fills, "NAS100")
print(session, summarize_fill_path(fills), "usd=", usd)
PY
```

**C. Mark-to-market while a trade is open** — use `positions.csv` `avg_price` vs latest mid in `state/bars/<SYMBOL>_1m.csv` (or last RTH tick). Realized PnL only appears after exit fills; open qty shows `realized_pnl` column as broker-local (often 0 until flatten).

### 5) Heartbeats / logs

| File | Role |
|------|------|
| `live/demo/<run>/PROGRESS.log` | Heartbeats (~5m), session PnL lines, errors |
| `live/demo/<run>/run.log` | Daemon stdout/stderr |
| `live/demo/<run>/pidfile` | PID |
| `live/demo/<run>/RUN_META.json` | `started_at`, `state_root`, routing flags |

```bash
tail -f live/demo/us30_v2b_ungated_paper/PROGRESS.log
tail -40 live/demo/us30_v2b_ungated_oanda/run.log
```

---

## Inventory — what is in this folder

### Shared modules (root of `live/demo/`)

| File | Purpose |
|------|---------|
| `__init__.py` | `DEMO_ROOT`, `demo_run_root(name)` |
| `.env` | Practice creds (`OANDA_ENV`, `OANDA_ACCOUNT_ID`, `OANDA_TOKEN`) — **do not commit** |
| `oanda_v2b_ungated_common.py` | Shared OANDA practice v2b runner (stream, Account Changes, daemon helpers) |
| `session_pnl.py` | Session FIFO PnL + append to results CSVs |
| `eod_charts.py` | NY RTH close position charts → `charts/` |
| `size_report.py` | Friday EOW file-size lines → `PROGRESS.log` / `FILE_SIZES.log` |
| `practice_order_smoke.py` | Tiny practice market + reconcile + flatten (pre-flight) |
| `ungated_paper_results.csv` | Paper session PnL ledger |
| `ungated_oanda_demo.csv` | OANDA session PnL ledger |
| `FILE_SIZES_BASELINE_*.md` | Weekend size baseline snapshots |

### Paper v2b runners (prices from OANDA; **PaperBroker** fills)

| Module | Artifacts dir | CLI |
|--------|---------------|-----|
| `eurusd_v2b_ungated_paper.py` | `eurusd_v2b_ungated_paper/` | `demo-eurusd-v2b-paper` |
| `nas100_v2b_ungated_paper.py` | `nas100_v2b_ungated_paper/` | `demo-nas100-v2b-paper` |
| `spx500_v2b_ungated_paper.py` | `spx500_v2b_ungated_paper/` | `demo-spx500-v2b-paper` |
| `us30_v2b_ungated_paper.py` | `us30_v2b_ungated_paper/` | `demo-us30-v2b-paper` |

Each CLI has `-status` / `-stop` siblings (e.g. `demo-us30-v2b-paper-status`).

### OANDA practice v2b runners (real practice orders)

Thin wrappers around `oanda_v2b_ungated_common.py`:

| Module | Artifacts dir | CLI |
|--------|---------------|-----|
| `eurusd_v2b_ungated_oanda.py` | `eurusd_v2b_ungated_oanda/` | `demo-eurusd-v2b-oanda` |
| `nas100_v2b_ungated_oanda.py` | `nas100_v2b_ungated_oanda/` | `demo-nas100-v2b-oanda` |
| `spx500_v2b_ungated_oanda.py` | `spx500_v2b_ungated_oanda/` | `demo-spx500-v2b-oanda` |
| `us30_v2b_ungated_oanda.py` | `us30_v2b_ungated_oanda/` | `demo-us30-v2b-oanda` |

### Monday OR (USDJPY, Phase 2 `M2_S3_R1`)

| Module | Artifacts dir | CLI |
|--------|---------------|-----|
| `usdjpy_monday_or_ungated_paper.py` | `usdjpy_monday_or_ungated_paper/` | `demo-usdjpy-monday-or-paper` |
| `usdjpy_monday_or_ungated_oanda.py` | `usdjpy_monday_or_ungated_oanda/` | `demo-usdjpy-monday-or-oanda` |

Extra note in paper tree: `usdjpy_monday_or_ungated_paper/OR_SEED_NOTE.md` (how Monday OR was seeded after a paper stream bug).

### Hourly ST+PMC 1mfill (fair 3R + 2R→10R runners)

Plugin `hourly_st_pmc_retest`, stop 50 / target 150 index pts, **1m fill tape**
(no BB/retest adds). Lot-correct hubs (2026-08-08):
`live/state/us30_st_pmc_runner_variants/`,
`live/state/fx_index_metals_st_pmc_runner_variants/`.

| Book | US30 N/S | NAS100 N/S | max contracts | Rankable |
|------|---------:|-----------:|--------------:|----------|
| Fair 3R | **29.4** | **19.6** | 1 | yes |
| 2R→10R runners | **24.1** | **11.1** | 3 | yes |
| Indefinite runners | sleeve only | sleeve only | inventory | **no** (not demoed) |

| Module | Artifacts dir | CLI | Seed / inherit |
|--------|---------------|-----|----------------|
| `us30_hourly_st_pmc_paper.py` | `us30_hourly_st_pmc_sl50_tp150_3r_paper/` | `demo-us30-hourly-st-pmc-paper` | `fx/us30_1h.csv` (~300h) |
| `us30_hourly_st_pmc_oanda.py` | `us30_hourly_st_pmc_sl50_tp150_3r_oanda/` | `demo-us30-hourly-st-pmc-oanda` | same |
| `us30_hourly_st_pmc_runners_2r_10r_paper.py` | `us30_hourly_st_pmc_sl50_tp150_runners_2r_10r_paper/` | `demo-us30-hourly-st-pmc-2r10r-paper` | same |
| `us30_hourly_st_pmc_runners_2r_10r_oanda.py` | `us30_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda/` | `demo-us30-hourly-st-pmc-2r10r-oanda` | same |
| `nas100_hourly_st_pmc_paper.py` | `nas100_hourly_st_pmc_sl50_tp150_3r_paper/` | `demo-nas100-hourly-st-pmc-paper` | `fx/nas100_1h.csv` + inherit 1m from `nas100_v2b_*` |
| `nas100_hourly_st_pmc_oanda.py` | `nas100_hourly_st_pmc_sl50_tp150_3r_oanda/` | `demo-nas100-hourly-st-pmc-oanda` | same |
| `nas100_hourly_st_pmc_runners_2r_10r_paper.py` | `nas100_hourly_st_pmc_sl50_tp150_runners_2r_10r_paper/` | `demo-nas100-hourly-st-pmc-2r10r-paper` | same |
| `nas100_hourly_st_pmc_runners_2r_10r_oanda.py` | `nas100_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda/` | `demo-nas100-hourly-st-pmc-2r10r-oanda` | same |

### Per-run directory layout

```text
live/demo/<run>/
  pidfile
  PROGRESS.log
  run.log
  RUN_META.json
  FILE_SIZES.log          # after Friday EOW size dump
  charts/                 # EOD PNGs from eod_charts.py
  state/
    fills.csv
    positions.csv
    orders.csv
    order_intents.csv
    strategy_instances.csv
    strategy_state.csv
    health.json
    bars/<SYMBOL>_1m.csv          # (+ _15m.csv for Monday OR)
    events/
      fills.jsonl
      rth_ticks/YYYY-MM-DD.jsonl  # NY RTH only
      stream_errors.jsonl
      oanda_session_events.jsonl
      oanda_order_events.jsonl    # OANDA demos
      reconciliation_events.jsonl # OANDA demos
      ...
```

---

## Create / run / stop daemons

### Start (background)

```bash
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
# load .env or export OANDA_* first

python3 -m potions.live.cli demo-eurusd-v2b-paper --daemon
python3 -m potions.live.cli demo-nas100-v2b-paper --daemon
python3 -m potions.live.cli demo-spx500-v2b-paper --daemon
python3 -m potions.live.cli demo-us30-v2b-paper --daemon

python3 -m potions.live.cli demo-eurusd-v2b-oanda --daemon
python3 -m potions.live.cli demo-nas100-v2b-oanda --daemon
python3 -m potions.live.cli demo-spx500-v2b-oanda --daemon
python3 -m potions.live.cli demo-us30-v2b-oanda --daemon

python3 -m potions.live.cli demo-usdjpy-monday-or-paper --daemon
python3 -m potions.live.cli demo-usdjpy-monday-or-oanda --daemon

python3 -m potions.live.cli demo-us30-hourly-st-pmc-paper --daemon
python3 -m potions.live.cli demo-us30-hourly-st-pmc-oanda --daemon
python3 -m potions.live.cli demo-us30-hourly-st-pmc-2r10r-paper --daemon
python3 -m potions.live.cli demo-us30-hourly-st-pmc-2r10r-oanda --daemon
python3 -m potions.live.cli demo-nas100-hourly-st-pmc-paper --daemon
python3 -m potions.live.cli demo-nas100-hourly-st-pmc-oanda --daemon
python3 -m potions.live.cli demo-nas100-hourly-st-pmc-2r10r-paper --daemon
python3 -m potions.live.cli demo-nas100-hourly-st-pmc-2r10r-oanda --daemon
```

Foreground (debug): omit `--daemon`. Optional `--max-ticks N`, `--output-root PATH`, `--oanda-config PATH`.

### Stop

```bash
python3 -m potions.live.cli demo-us30-v2b-paper-stop
python3 -m potions.live.cli demo-us30-v2b-oanda-stop
# … same pattern for every demo
```

### Pre-flight (OANDA practice only)

```bash
python3 -m potions.live.cli --state-root /tmp/oanda_practice_smoke \
  oanda-practice-order-smoke --units 1
```

### Emergency flatten (practice account)

```bash
python3 -m potions.live.cli --state-root /tmp/oanda_flat \
  oanda-emergency-flatten --instruments EURUSD,NAS100,SPX500,US30,USDJPY
```

---

## Strategy notes (what these demos trade)

### Ungated v2b (`v2b_scaleout`)

- OCO scaleout, **ungated** (`prior_opposite_only=false`), sizing **S_1_1_1** (entry 3 / tp1 1 / tp2 1)
- Signals on **mid** OHLC; paper fills buy→ask / sell→bid
- Index CFD tick `0.1`; EURUSD tick `0.00001`
- NY RTH **09:30–16:00**: strategy + RTH tick logs; outside RTH stream stays up, bars persist, strategy idle
- OANDA demos: broker is truth; local CSVs mirrored via Account Changes
- Shared practice **margin** across all OANDA demos on one account

### USDJPY Monday OR (`monday_or_breakout`, tag `M2_S3_R1`)

- Quote stream → 1m → **15m** bars (research-compatible left label)
- Monday builds OR; breakouts Tue–Fri; flatten **Friday only @ NY 15:59**
- Core tune-up: sitout +3 pts **+ skip Aug/Sep** (broker N/S **10.60**); alt `M2_S3_R2` = skip-1-after-2W **+ skip Aug/Sep** (N/S **10.62**)
- Spec: `live/state/monday_or_phase2/SPEC_USDJPY_M2_S3_R1.md` · tracker: `CORE_WEEK_SITOUT.md`

---

## Adding a new demo strategy (checklist)

1. **Plugin** under `live/strategies/` + register in `live/registry.py`.
2. **Runner module** in `live/demo/` (copy a paper twin: e.g. `eurusd_v2b_ungated_paper.py`, or OANDA via `oanda_v2b_ungated_common.OandaDemoSpec`).
3. Implement / reuse: `default_output_root`, `spawn_daemon`, `status_daemon`, `stop_daemon`, `run_stream_loop`.
4. Artifacts under `live/demo/<your_run_name>/` via `demo_run_root("your_run_name")`.
5. Wire CLI in `live/cli.py`: start / `-status` / `-stop` parsers + `cmd_*` handlers.
6. For session PnL, call `session_pnl.append_session_result(...)` at NY RTH close (see paper runners).
7. Document the new CLI + artifact path in **this README**.

Paper vs OANDA:

- **Paper:** OANDA stream for prices only; `PaperBroker` for fills.
- **OANDA:** `OandaBroker` + Account Changes; keep `OANDA_ENV=practice` and `allow_live_routing=False`.

---

## Ops extras

```bash
# File growth / rotation planning (also auto on Friday EOW inside daemons)
python3 -m potions.live.demo.size_report

# EOD charts are written by the daemon; helper lives in eod_charts.py
```

Index CFDs (NAS100 / SPX500 / US30) are OANDA products used as NQ/ES/YM-style proxies — not CME futures.

---

## Snapshot (broker truth vs local)

**OANDA practice account** (`101-002-39860312-001`) as of 2026-07-28:

| Field | Value |
|------|-------|
| Open positions | **USDJPY long 3 only** (EURUSD / NAS / SPX / US30 flat) |
| Realized P/L | **2025.62** (`pl` ≈ 2025.6163) |
| Pending orders | 3 (USDJPY Monday OR brackets) |

Local `eurusd_v2b_ungated_oanda/state/positions.csv` had a **stale qty=1** from 2026-07-24 (entry fill mirrored, no exit fill written after flatten). Zeroed to match broker (`PROGRESS.log` has a `RECONCILE` line). Prefer account API / `positions` with `quantity!=0` on the broker over a single demo’s CSV when they disagree.

All **10** daemons were alive when last checked. Re-check with the status commands and `fills.csv` / `positions.csv` sections above.
