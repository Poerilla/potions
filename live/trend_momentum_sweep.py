#!/usr/bin/env python3
"""Full multi-market trend_momentum sweep on recommended TF(s)."""

from __future__ import annotations

import argparse
import traceback
from pathlib import Path

from .trend_momentum_common import (
    REPO,
    SWEEP_INSTRUMENTS,
    load_1m_frame,
    run_cell,
    write_summary,
)

OUT = REPO / "live" / "state" / "trend_momentum_sweep"
TF_STUDY = REPO / "live" / "state" / "trend_momentum_tf_study" / "RECOMMENDED_TF.txt"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--tfs",
        default="",
        help="Comma TFs (default: recommended from TF study + 15m)",
    )
    ap.add_argument("--symbols", default="", help="Comma subset")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    log = OUT / "PROGRESS.log"

    if args.tfs.strip():
        tfs = [t.strip() for t in args.tfs.split(",") if t.strip()]
    else:
        rec = "15m"
        if TF_STUDY.exists():
            rec = TF_STUDY.read_text(encoding="utf-8").strip() or "15m"
        tfs = [rec]
        if "15m" not in tfs:
            tfs.append("15m")

    symbols = {s.strip().upper() for s in args.symbols.split(",") if s.strip()} or None
    rows = []
    for spec in SWEEP_INSTRUMENTS:
        if symbols and spec.symbol not in symbols:
            continue
        print("[%s] caching 1m..." % spec.symbol, flush=True)
        try:
            df1 = load_1m_frame(spec)
        except Exception as exc:
            msg = "[FAIL] %s load_1m: %s\n%s" % (spec.symbol, exc, traceback.format_exc())
            print(msg, flush=True)
            with log.open("a", encoding="utf-8") as fh:
                fh.write(msg + "\n")
            continue
        for tf in tfs:
            try:
                row = run_cell(
                    out_root=OUT, spec=spec, timeframe=tf, force=args.force, df1_cache=df1
                )
                rows.append(row)
                with log.open("a", encoding="utf-8") as fh:
                    fh.write(
                        "%s %s net=%.0f ns=%.2f\n"
                        % (spec.symbol, tf, float(row["net_usd_approx"]), float(row["net_stress"]))
                    )
            except Exception as exc:
                msg = "[FAIL] %s %s: %s\n%s" % (spec.symbol, tf, exc, traceback.format_exc())
                print(msg, flush=True)
                with log.open("a", encoding="utf-8") as fh:
                    fh.write(msg + "\n")
        del df1

    write_summary(OUT, rows, "Trend momentum — multi-market sweep")
    print("Wrote %s" % (OUT / "SUMMARY.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
