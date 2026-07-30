"""US30 ST+PMC sl50_tp150_3r — baseline vs retest-add vs favourable BB-touch adds.

BB adds (1m Bollinger 20/2σ, matching win charts):
  - Main trade unchanged (SL 50 / TP 150).
  - While in position and already in favor (long above entry / short below),
    mid sloping favorably, touch lower BB (long) or upper BB (short).
  - Add SL = original entry; TP = inherited main target.
  - Max 3 BB adds.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import List

from .broker import DEFAULT_TICK_SIZE
from .fx_data import load_fx_1m_by_ny_date
from .hourly_st_pmc_loss_research import VariantConfig
from .hourly_st_pmc_strategyplugin_variants import run_variant
from .models import Bar
from .replay_audit import POINT_VALUES
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, resample_hourly

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "us30_st_pmc_retest_add_experiment"
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--only-bb",
        action="store_true",
        help="Only run the BB-add variant (reuse prior baseline/retest rows if present).",
    )
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

    variants = [
        VariantConfig(
            "sl50_tp150_3r_1mfill",
            stop_pts=50.0,
            tp1_pts=150.0,
            notes="baseline 1x on 1m fill tape (fair control for BB adds)",
        ),
        VariantConfig(
            "sl50_tp150_3r_bb_add_x3",
            stop_pts=50.0,
            tp1_pts=150.0,
            bb_add_enabled=True,
            bb_add_qty=1,
            max_bb_adds=3,
            bb_len=20,
            bb_std=2.0,
            notes="max 3 favourable 1m BB-touch adds; SL@entry; inherit TP",
        ),
    ]
    # Keep prior hourly-only rows for reference when present.
    rows = []
    prior_csv = OUT / "summary.csv"
    if prior_csv.exists():
        with prior_csv.open(newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                v = str(r.get("variant", ""))
                if v in {"sl50_tp150_3r", "sl50_tp150_3r_retest_add", "sl50_tp150_3r_retest_add_x5"}:
                    rows.append(r)

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
                "notes": cfg.notes,
            }
        )
        print(
            "  Net=$%.0f Stress=$%.0f N/S=%.2f units=%d WR=%.1f%% max_open=%d"
            % (a.net_usd, stress, ns, a.units, wr, a.max_open_units),
            flush=True,
        )

    # de-dupe by variant keeping last
    by_name = {}
    for r in rows:
        by_name[r["variant"]] = r
    rows = list(by_name.values())

    with (OUT / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    lines = [
        "# US30 ST+PMC 50/150 — retest / BB-add experiment",
        "",
        "Baseline vs classic retest-add vs **favourable 1m Bollinger-touch adds**.",
        "",
        "BB add rules: long touches lower band / short touches upper band; price already",
        "in favor; BB mid sloping favorably; add SL = original entry; inherit main TP;",
        "max 3 adds. Main trade stays SL50/TP150.",
        "",
        "| Variant | Units | Trades | Net $ | Stress | N/S | WR% | Max open |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            "| `%s` | %s | %s | %s | %s | %s | %s | %s |"
            % (
                r["variant"],
                r["units"],
                r["trades"],
                r["net_usd"],
                r["stress_dd_usd"],
                r["ns"],
                r["wr_pct"],
                r["max_open"],
            )
        )
    lines.extend(
        [
            "",
            "Live demos use **bb_add_enabled** (`max_bb_adds=3`, `max_contracts=4`).",
            "",
        ]
    )
    (OUT / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote %s" % (OUT / "SUMMARY.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
