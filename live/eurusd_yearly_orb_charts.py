"""Build Yearly ORB detail charts for the EURUSD overnight sweep."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Optional

from .build_broker_like_replay_detail_charts import build_detail_charts


REPO = Path(__file__).resolve().parents[1]


COMPAT_SUMMARY = """candidate,slug,instrument,units,trades,net_usd,close_mtm_dd_usd,intrabar_mtm_dd_usd,max_open_units,net_over_stress_dd
EURUSD Yearly ORB scaleout3,eurusd_yearly_orb_scaleout3,EURUSD,276,92,165865.00,-19434.00,-19965.00,3,8.31
EURUSD Yearly ORB scaleout3 20% range-close,eurusd_yearly_orb_scaleout3_range_close_20pct,EURUSD,183,61,124518.75,-45705.75,-47959.25,3,2.60
"""


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="EURUSD yearly ORB broker-like detail charts.")
    parser.add_argument(
        "--replay-root",
        type=Path,
        default=REPO / "live" / "state" / "eurusd_overnight_sweep",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live" / "state" / "eurusd_overnight_sweep" / "charts" / "yearly_orb",
    )
    args = parser.parse_args(argv)

    # Detail-chart builder expects broker_like summary columns.
    compat = args.replay_root / "summary_charts_compat.csv"
    compat.write_text(COMPAT_SUMMARY, encoding="utf-8")
    # Temporarily swap: build_detail_charts reads summary.csv; keep original and restore.
    original = args.replay_root / "summary.csv"
    backup = args.replay_root / "summary_overnight_backup.csv"
    if original.exists() and not backup.exists():
        backup.write_text(original.read_text(encoding="utf-8"), encoding="utf-8")
    # Write a chart-compatible summary beside overnight ranking by merging required columns.
    overnight_rows = list(csv.DictReader(backup.open(encoding="utf-8"))) if backup.exists() else []
    # Prefer dedicated compat file renamed as summary for the chart pass.
    original.write_text(COMPAT_SUMMARY, encoding="utf-8")
    try:
        built = build_detail_charts(
            replay_root=args.replay_root,
            output_root=args.output_root,
            include_all=False,
            include_slugs=[
                "eurusd_yearly_orb_scaleout3",
                "eurusd_yearly_orb_scaleout3_range_close_20pct",
            ],
            exact=True,
        )
    finally:
        if backup.exists():
            original.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
    print("Wrote %d yearly ORB charts under %s" % (len(built), args.output_root), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
