"""US30 ST+PMC runner variants on 1m fill tape (fair vs 2R+10R vs 2R+indefinite).

Campaign sizing (all share SL50 / TP1=150):
  - 1 unit at regular TP (150)
  - Runner A exits at 2× regular target (300); SL→BE after TP1
  - Runner B either exits at 10× regular target (1500) or runs indefinite
    (no TP; year-end flatten; does not block later campaigns)

Charts: draw stop + regular TP only (no 10R / indefinite TP lines).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .broker import DEFAULT_TICK_SIZE
from .fx_data import load_fx_1m_by_ny_date
from .hourly_st_pmc_loss_research import VariantConfig
from .hourly_st_pmc_strategyplugin_variants import run_variant
from .models import Bar
from .replay_audit import POINT_VALUES
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, resample_hourly

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "us30_st_pmc_runner_variants"
SYM = "US30"
TICK = 0.1


def _hourly_bars():
    one_m = REPO / "fx" / "us30_1m.csv"
    gby = load_fx_1m_by_ny_date(one_m, SYM)
    one_m_df = concat_all_1m(gby)
    hourly = resample_hourly(one_m_df)
    out: List[Bar] = []
    for ts, row in hourly.iterrows():
        out.append(
            Bar(
                instrument=SYM,
                timeframe="1h",
                ts=ts.isoformat(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(one_m),
            )
        )
    return out, one_m_df


def _read_strategy_state(state_root: Path, strategy_id: str) -> Dict[str, Any]:
    path = state_root / "strategy_state.csv"
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if str(row.get("strategy_id") or "") != strategy_id:
                continue
            raw = row.get("state_json") or row.get("state") or "{}"
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {}
    return {}


def _year_end_stats(fills_path: Path) -> Dict[str, int]:
    """Units closed via year_end_flatten, keyed by calendar year of the fill."""
    out: Dict[str, int] = {}
    if not fills_path.exists():
        return out
    with fills_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if str(row.get("reason") or "") != "year_end_flatten":
                continue
            ts = str(row.get("ts") or "")
            year = ts[:4]
            if not year.isdigit():
                continue
            qty = abs(int(float(row.get("quantity") or 0)))
            out[year] = int(out.get(year) or 0) + qty
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="Optional variant name filter(s).",
    )
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args()

    POINT_VALUES[SYM] = 1.0
    DEFAULT_TICK_SIZE[SYM] = TICK
    OUT.mkdir(parents=True, exist_ok=True)

    one_m_path = REPO / "fx" / "us30_1m.csv"
    daily = REPO / "fx" / "us30_daily.csv"
    print("Loading US30 1m → hourly…", flush=True)
    bars, one_m_df = _hourly_bars()
    print("Hourly bars: %d  1m bars: %d" % (len(bars), len(one_m_df)), flush=True)

    from . import hourly_st_pmc_strategyplugin_variants as hsv

    hsv.TICK_SIZE[SYM] = TICK

    tp = 150.0
    variants = [
        VariantConfig(
            "sl50_tp150_3r_1mfill",
            stop_pts=50.0,
            tp1_pts=tp,
            notes="fair control: 1 unit SL50 / TP150 on 1m fill tape",
        ),
        VariantConfig(
            "sl50_tp150_runners_2r_10r",
            stop_pts=50.0,
            tp1_pts=tp,
            tp1_qty=1,
            runner_specs=((1, 2.0 * tp), (1, 10.0 * tp)),
            runner_stop_to_be_after_tp1=True,
            notes="3 units: TP150 + runner@300 + runner@1500; both runners SL→BE after TP1",
        ),
        VariantConfig(
            "sl50_tp150_runners_2r_indef",
            stop_pts=50.0,
            tp1_pts=tp,
            tp1_qty=1,
            runner_specs=((1, 2.0 * tp), (1, None)),
            runner_stop_to_be_after_tp1=True,
            year_end_flatten_runners=True,
            runners_do_not_block_entries=True,
            notes=(
                "3 units: TP150 + runner@300 + indefinite; SL→BE after TP1; "
                "EOY flatten; indefinite runners do not block later campaigns"
            ),
        ),
    ]
    if args.only:
        want = set(args.only)
        variants = [v for v in variants if v.name in want]
        if not variants:
            raise SystemExit("No variants matched --only %s" % sorted(want))

    rows: List[Dict[str, object]] = []
    for cfg in variants:
        print("RUN %s (max_contracts=%d)" % (cfg.name, cfg.max_contracts), flush=True)
        result = run_variant(
            cfg=cfg,
            bars=bars,
            output_root=OUT,
            dbn=one_m_path,
            daily_path=daily,
            instrument=SYM,
            market="us30",
            force=bool(args.force),
            quiet=True,
            one_m=one_m_df,
        )
        a = result.audit
        stress = float(a.intrabar_mtm_dd_usd or a.close_mtm_dd_usd or 0.0)
        ns = (a.net_usd / abs(stress)) if stress else 0.0
        wr = (100.0 * float(a.win_units) / float(a.units)) if a.units else 0.0
        state = _read_strategy_state(result.state_root, result.strategy_id)
        eoy_by_year = _year_end_stats(result.state_root / "fills.csv")
        if not eoy_by_year and state.get("year_end_flatten_by_year"):
            raw = state.get("year_end_flatten_by_year") or {}
            eoy_by_year = {str(k): int(v) for k, v in raw.items()}
        eoy_total = int(sum(eoy_by_year.values()))
        eoy_events = int(state.get("year_end_flatten_events") or len(eoy_by_year))
        rows.append(
            {
                "variant": cfg.name,
                "units": a.units,
                "trades": a.trades,
                "net_usd": round(a.net_usd, 2),
                "stress_dd_usd": round(stress, 2),
                "ns": round(ns, 3),
                "wr_pct": round(wr, 1),
                "max_open": a.max_open_units,
                "eoy_flatten_events": eoy_events,
                "eoy_flatten_units": eoy_total,
                "eoy_flatten_by_year": json.dumps(eoy_by_year, sort_keys=True),
                "notes": cfg.notes,
            }
        )
        print(
            "  Net=$%.0f Stress=$%.0f N/S=%.2f units=%d WR=%.1f%% max_open=%d "
            "EOY_events=%d EOY_units=%d by_year=%s"
            % (
                a.net_usd,
                stress,
                ns,
                a.units,
                wr,
                a.max_open_units,
                eoy_events,
                eoy_total,
                json.dumps(eoy_by_year, sort_keys=True),
            ),
            flush=True,
        )

    csv_path = OUT / "summary.csv"
    fields = [
        "variant",
        "units",
        "trades",
        "net_usd",
        "stress_dd_usd",
        "ns",
        "wr_pct",
        "max_open",
        "eoy_flatten_events",
        "eoy_flatten_units",
        "eoy_flatten_by_year",
        "notes",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    lines = [
        "# US30 ST+PMC runner variants (1m fill tape)",
        "",
        "Fair control vs dual-runner scaleouts on the same US30 1m path as "
        "`sl50_tp150_3r_1mfill`.",
        "",
        "## Rules",
        "",
        "- Stop 50 / regular TP 150 (TP1).",
        "- Dual-runner campaigns enter **3 units**: TP1 + 2R runner + far runner.",
        "- Both runners: stop → breakeven when TP1 fills.",
        "- `2r_10r`: far runner target = **10× regular TP distance** (1500 pts).",
        "- `2r_indef`: far runner has **no TP**; flatten at calendar year change; "
        "indefinite inventory does **not** block later campaigns.",
        "- Charts draw stop + regular TP only (no 10R / indefinite TP lines).",
        "",
        "## Results",
        "",
        "| variant | net | stress | N/S | units | WR% | max_open | EOY flatten units | EOY by year |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            "| `%s` | $%.0f | $%.0f | %.2f | %s | %.1f | %s | %s | %s |"
            % (
                r["variant"],
                float(r["net_usd"]),
                float(r["stress_dd_usd"]),
                float(r["ns"]),
                r["units"],
                float(r["wr_pct"]),
                r["max_open"],
                r["eoy_flatten_units"],
                r["eoy_flatten_by_year"],
            )
        )
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "- Summary CSV: `summary.csv`",
            "- States: `states/us30_hourly_st_pmc_<variant>/`",
            "- Audits: `audits/`",
            "- Runner: `live/us30_st_pmc_runner_variants.py`",
            "",
        ]
    )
    (OUT / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote %s" % csv_path, flush=True)
    print("Wrote %s" % (OUT / "SUMMARY.md"), flush=True)
    if args.snapshot or args.email:
        from .refresh_hub_snapshot import refresh_hub_snapshot

        snap = refresh_hub_snapshot(OUT, email=bool(args.email))
        print(
            "snapshot status=%s complete=%s" % (snap.get("status"), snap.get("complete")),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
