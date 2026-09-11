"""Export sanitized public tear-sheet JSON (no instruments / fills / SPY / size-ups).

Tabs:
- FX Momentum
- FX Intraday Trend
- Index Momentum

Usage:
  PYTHONPATH=... python -m live.public_track_record.export_all \\
    --out-dir /path/to/fx-momentum-track/docs/data
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import common as C

REPO = C.REPO

ASIA_UNIT = (
    REPO
    / "live/state/fx_v2b_asia_range_london_usdjpy_filters/states"
    / "usdjpy_v2b_asia_range_london_S_3_1_3_flt/unit_trades.csv"
)
ASIA_DEMO = REPO / "live/demo/usdjpy_asia_range_london_oanda/state/fills.csv"

MOR_FILLS = (
    REPO
    / "live/state/monday_or_sizing_sweep_broker_usdjpy/states/usdjpy_m2_s3_r1/fills.csv"
)
MOR_DEMO = REPO / "live/demo/usdjpy_monday_or_ungated_oanda/state/fills.csv"

CB_UNIT = (
    REPO
    / "live/state/nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill_validation/states"
    / "nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill/unit_trades.csv"
)
CB_DEMO = (
    REPO
    / "live/demo/nas100_v2b_clean_break_trail06_m4_e2_out_be_oanda/state/fills.csv"
)

RETIRED_PUBLIC_FILES = (
    "fx_breakout.json",
    "index_breakout.json",
)

TABS: List[Dict[str, str]] = [
    {"id": "fx_momentum", "name": "FX Momentum", "file": "fx_momentum.json"},
    {"id": "fx_intraday_trend", "name": "FX Intraday Trend", "file": "fx_intraday_trend.json"},
    {"id": "index_momentum", "name": "Index Momentum", "file": "index_momentum.json"},
]


def _leak_check(payload: Dict[str, Any]) -> None:
    blob = json.dumps(payload).lower()
    banned = (
        "usdjpy",
        "usd_jpy",
        "nas100",
        "asia-range",
        "asia_range",
        "monday or",
        "monday_or",
        "s_3_1_3",
        "m2_s3_r1",
        "trail06",
        "oanda",
        "101-002",
        "potions",
        "breakout",
        "pyramid",
        "clean-break",
        "clean_break",
        "size-normalized",
        "size normalized",
        "live size",
        "multi-lot",
        "micro-size",
        "micro fills",
        "lot-cash",
        "size-up",
        "size up",
        "scale-out",
        "point value",
        "spy",
        "n/s",
        "net/stress",
        "net-stress",
    )
    for b in banned:
        if b in blob:
            raise ValueError(f"public payload leak: {b!r}")


def build_fx_momentum() -> Dict[str, Any]:
    camps = C.campaigns_from_unit_trades_fx(ASIA_UNIT)
    demo = C.campaigns_from_fills_fx(ASIA_DEMO, point_value=1.0, normalize_qty=True)
    return C.build_track_payload(
        product_name="FX Momentum",
        tab_id="fx_momentum",
        camps=camps,
        demo=demo,
        overview={
            "style": "Systematic",
            "asset_class": "FX",
            "holding_period": "Intraday",
            "edge": "Rules-based momentum / session continuation in liquid FX.",
            "overnight": "Positions are not intended to be held multi-day.",
        },
    )


def build_fx_intraday_trend() -> Dict[str, Any]:
    camps = C.campaigns_from_fills_fx(MOR_FILLS, point_value=100_000.0, normalize_qty=False)
    demo = C.campaigns_from_fills_fx(MOR_DEMO, point_value=1.0, normalize_qty=True)
    return C.build_track_payload(
        product_name="FX Intraday Trend",
        tab_id="fx_intraday_trend",
        camps=camps,
        demo=demo,
        overview={
            "style": "Systematic",
            "asset_class": "FX",
            "holding_period": "Intraday",
            "edge": "Rules-based intraday trend capture in liquid FX.",
            "overnight": "Positions are not intended to be held multi-day.",
        },
    )


def build_index_momentum() -> Dict[str, Any]:
    camps = C.campaigns_from_unit_trades_usd(CB_UNIT)
    demo = C.campaigns_from_fills_index(CB_DEMO, normalize_qty=False)
    return C.build_track_payload(
        product_name="Index Momentum",
        tab_id="index_momentum",
        camps=camps,
        demo=demo,
        overview={
            "style": "Systematic",
            "asset_class": "Equity index (CFD)",
            "holding_period": "Intraday",
            "edge": "Rules-based momentum around the cash-session open.",
            "overnight": "Positions are not intended to be held multi-day.",
        },
    )


BUILDERS = {
    "fx_momentum": build_fx_momentum,
    "fx_intraday_trend": build_fx_intraday_trend,
    "index_momentum": build_index_momentum,
}


def export_all(out_dir: Path) -> List[Dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in RETIRED_PUBLIC_FILES:
        p = out_dir / old
        if p.exists():
            p.unlink()
            print("removed retired", p)
    summaries: List[Dict[str, Any]] = []
    for tab in TABS:
        payload = BUILDERS[tab["id"]]()
        _leak_check(payload)
        path = out_dir / tab["file"]
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(
            "wrote",
            path,
            "practice_n=%s practice_net=%.2f bt_end=%.2f"
            % (
                (payload.get("live") or {}).get("kpis", {}).get("n_campaigns")
                or (payload.get("practice_kpis") or {}).get("n_campaigns"),
                payload.get("practice_net_check_usd") or 0.0,
                ((payload.get("backtest") or {}).get("kpis") or payload.get("kpis") or {}).get(
                    "end_equity"
                ),
            ),
        )
        summaries.append(
            {
                "id": tab["id"],
                "name": tab["name"],
                "file": tab["file"],
                "as_of": payload.get("as_of"),
            }
        )
    catalog = {
        "schema_version": 2,
        "title": "Strategy Tear Sheets",
        "as_of": summaries[0]["as_of"] if summaries else None,
        "tabs": [{"id": t["id"], "name": t["name"], "data": f"data/{t['file']}"} for t in TABS],
        "disclaimer": (
            "LIVE/SIM (top) is unaudited practice. BACKTEST (bottom) is hypothetical — "
            "not an offer to invest."
        ),
    }
    cat_path = out_dir / "catalog.json"
    cat_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    print("wrote", cat_path)
    return summaries


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=REPO / "live" / "public_track_record",
        help="Directory for sanitized JSON + catalog.json",
    )
    args = ap.parse_args(argv)
    export_all(args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
