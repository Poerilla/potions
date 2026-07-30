#!/usr/bin/env python3
"""Timeframe study for trend_momentum (5m/15m/1h/4h/D × USDJPY, XAUUSD, US30, NQ)."""

from __future__ import annotations

import argparse
import traceback
from pathlib import Path

from .trend_momentum_common import (
    REPO,
    STUDY_INSTRUMENTS,
    TIMEFRAMES_STUDY,
    load_1m_frame,
    run_cell,
    write_summary,
)

OUT = REPO / "live" / "state" / "trend_momentum_tf_study"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--symbols", default="", help="Comma subset e.g. USDJPY,XAUUSD")
    ap.add_argument("--tfs", default="", help="Comma subset e.g. 15m,1h")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    log = OUT / "PROGRESS.log"
    symbols = {s.strip().upper() for s in args.symbols.split(",") if s.strip()} or None
    tfs = [t.strip() for t in args.tfs.split(",") if t.strip()] or list(TIMEFRAMES_STUDY)

    rows = []
    for spec in STUDY_INSTRUMENTS:
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

    write_summary(OUT, rows, "Trend momentum — timeframe study")
    # Recommend best intraday TF by mean N/S across study symbols
    from collections import defaultdict

    by_tf = defaultdict(list)
    for r in rows:
        if r["timeframe"] in {"5m", "15m", "1h"}:
            by_tf[r["timeframe"]].append(float(r["net_stress"]))
    ranked = sorted(
        ((tf, sum(v) / len(v)) for tf, v in by_tf.items() if v),
        key=lambda x: x[1],
        reverse=True,
    )
    rec = ranked[0][0] if ranked else "15m"
    (OUT / "RECOMMENDED_TF.txt").write_text(rec + "\n", encoding="utf-8")
    print("Recommended intraday TF: %s" % rec, flush=True)
    print("Wrote %s" % (OUT / "SUMMARY.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
