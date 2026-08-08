# Demo status reference

## CLI `-status` (all current demos)

```bash
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"

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

## Tail logs

```bash
tail -f live/demo/us30_v2b_ungated_paper/PROGRESS.log
tail -40 live/demo/us30_v2b_ungated_oanda/run.log
rg "2026-07-31.*ERROR stage=stream_read" live/demo/*/run.log
```

## Open positions / resting orders

```bash
python3 - <<'PY'
import pandas as pd
from pathlib import Path
root = Path("live/demo/usdjpy_monday_or_ungated_paper/state")
pos = pd.read_csv(root / "positions.csv")
print(pos[pos["quantity"].astype(float) != 0])
orders = pd.read_csv(root / "orders.csv")
print(orders[orders["status"].isin(["working","submitted","accepted","pending","open"])]
      [["side","order_type","quantity","status","stop_price","limit_price","bracket_role"]])
PY
```

## Latest fills

```bash
column -s, -t < live/demo/us30_v2b_ungated_paper/state/fills.csv | tail -20
```

Fill reasons (v2b): `entry`, `tp1`, `tp2`, `wide_stop`, `runner_stop`, `eod_close`  
Monday OR: `entry`, `dd30` / `dd50`, `target`, week flatten

## Do not

- Print or commit `live/demo/.env` tokens
- Confuse research `live/PROGRESS.log` with per-demo `live/demo/<run>/PROGRESS.log`
- Treat overnight stream reconnects as fatal if heartbeats resumed
