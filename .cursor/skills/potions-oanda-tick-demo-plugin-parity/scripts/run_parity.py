#!/usr/bin/env python3
"""Run OANDA-tick demo↔plugin parity drivers (NAS100 and/or USDJPY live books)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--book", choices=("both", "nas100", "usdjpy"), default="both")
    ap.add_argument("--usdjpy-book", choices=("both", "monday", "asia"), default="both")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--max-days", type=int, default=0)
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args()

    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    env.setdefault(
        "PYTHONPATH",
        "/home/tester/hsm:/home/tester/hsm/potions/v20-python/src",
    )
    env.setdefault(
        "POTIONS_RUN_LEDGER",
        str(REPO / "data" / "validation" / "broker_run_ledger.csv"),
    )

    cmds = []
    if args.book in ("both", "nas100"):
        cmd = [sys.executable, "-m", "live.nas100_clean_break_demo_plugin_tick_parity"]
        if args.email:
            cmd.append("--email")
        if args.smoke:
            cmd.append("--smoke")
        if args.max_days:
            cmd.extend(["--max-days", str(args.max_days)])
        cmds.append(cmd)
    if args.book in ("both", "usdjpy"):
        cmd = [sys.executable, "-m", "live.usdjpy_live_demo_plugin_tick_parity", "--book", args.usdjpy_book]
        if args.email:
            cmd.append("--email")
        if args.smoke:
            cmd.append("--smoke")
        if args.max_days:
            cmd.extend(["--max-days", str(args.max_days)])
        cmds.append(cmd)

    rc = 0
    for cmd in cmds:
        print("+", " ".join(cmd), flush=True)
        proc = subprocess.run(cmd, cwd=str(REPO), env=env)
        if proc.returncode != 0:
            rc = proc.returncode
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
