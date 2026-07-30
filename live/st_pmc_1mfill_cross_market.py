"""Cross-market ST+PMC sl50_tp150_3r with StrategyPlugin + 1m fill tape.

Same path as US30 ``sl50_tp150_3r_1mfill``: Engine + PaperBroker +
``hourly_st_pmc_retest``, hourly ST+PMC signals, 1m bars for fill resolution.

Stop/target:
  - Index / equity futures: 50 / 150 points
  - EURUSD: 50 / 150 pips (0.0050 / 0.0150)
  - USDJPY: 50 / 150 pips (0.50 / 1.50)

SPX500 is skipped when no historical 1m archive is present.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .fx_data import load_fx_1m_by_ny_date
from .hourly_st_pmc_loss_research import VariantConfig
from .hourly_st_pmc_strategyplugin_variants import MARKET_CONFIGS, TICK_SIZE, run_variant
from .models import Bar
from .replay_audit import POINT_VALUES
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, load_1m_by_ny_date_any, resample_hourly

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "st_pmc_1mfill_cross_market"


@dataclass(frozen=True)
class MarketSpec:
    key: str
    instrument: str
    one_m_path: Path
    daily_path: Path
    stop_pts: float
    target_pts: float
    tick: float
    source: str  # futures | fx
    notes: str = ""


def _fx_spec(key: str, instrument: str, stop: float, target: float, tick: float) -> MarketSpec:
    return MarketSpec(
        key=key,
        instrument=instrument,
        one_m_path=REPO / "fx" / ("%s_1m.csv" % key),
        daily_path=REPO / "fx" / ("%s_daily.csv" % key),
        stop_pts=stop,
        target_pts=target,
        tick=tick,
        source="fx",
    )


def market_specs() -> List[MarketSpec]:
    out: List[MarketSpec] = []
    for key in ("ym", "mym", "nq", "mnq", "mes"):
        cfg = MARKET_CONFIGS[key]
        inst = str(cfg["instrument"])
        out.append(
            MarketSpec(
                key=key,
                instrument=inst,
                one_m_path=Path(cfg["dbn"]),
                daily_path=Path(cfg["daily"]),
                stop_pts=50.0,
                target_pts=150.0,
                tick=float(TICK_SIZE[inst]),
                source="futures",
            )
        )
    out.extend(
        [
            _fx_spec("nas100", "NAS100", 50.0, 150.0, 0.1),
            _fx_spec("us30", "US30", 50.0, 150.0, 0.1),
            _fx_spec("eurusd", "EURUSD", 0.0050, 0.0150, 0.00001),
            _fx_spec("usdjpy", "USDJPY", 0.50, 1.50, 0.001),
            # Metals: same 50/150 price points as index CFDs (PV 100 / 1000)
            _fx_spec("xauusd", "XAUUSD", 50.0, 150.0, 0.01),
            _fx_spec("xagusd", "XAGUSD", 50.0, 150.0, 0.001),
        ]
    )
    spx_1m = REPO / "fx" / "spx500_1m.csv"
    spx_daily = REPO / "fx" / "spx500_daily.csv"
    if spx_1m.exists() and spx_daily.exists():
        out.append(_fx_spec("spx500", "SPX500", 50.0, 150.0, 0.1))
    return out


def _load_frames(spec: MarketSpec) -> Tuple[List[Bar], pd.DataFrame]:
    if spec.source == "fx":
        gby = load_fx_1m_by_ny_date(spec.one_m_path, spec.instrument)
    else:
        gby = load_1m_by_ny_date_any(spec.one_m_path.resolve(), spec.instrument.lower())
    one_m = concat_all_1m(gby)
    hourly = resample_hourly(one_m)
    bars: List[Bar] = []
    for ts, row in hourly.iterrows():
        bars.append(
            Bar(
                instrument=spec.instrument,
                timeframe="1h",
                ts=ts.isoformat(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(spec.one_m_path),
            )
        )
    return bars, one_m


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--markets",
        nargs="*",
        default=[],
        help="Subset of market keys (default: all available except missing SPX).",
    )
    ap.add_argument("--skip-us30", action="store_true", help="Skip US30 (already measured).")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    specs = market_specs()
    if args.markets:
        want = {m.lower() for m in args.markets}
        specs = [s for s in specs if s.key in want]
    if args.skip_us30:
        specs = [s for s in specs if s.key != "us30"]

    print("Markets:", ", ".join(s.key for s in specs), flush=True)
    if not (REPO / "fx" / "spx500_1m.csv").exists():
        print("NOTE: SPX500 skipped — no fx/spx500_1m.csv historical archive.", flush=True)

    rows: List[Dict[str, object]] = []
    for spec in specs:
        print("=" * 60, flush=True)
        print(
            "LOAD %s (%s) stop=%g target=%g tick=%g" % (spec.key, spec.instrument, spec.stop_pts, spec.target_pts, spec.tick),
            flush=True,
        )
        if not spec.one_m_path.exists() or not spec.daily_path.exists():
            print("  SKIP missing data: %s / %s" % (spec.one_m_path, spec.daily_path), flush=True)
            rows.append(
                {
                    "market": spec.key,
                    "instrument": spec.instrument,
                    "variant": "sl50_tp150_3r_1mfill",
                    "units": 0,
                    "trades": 0,
                    "net_usd": "",
                    "stress_dd_usd": "",
                    "ns": "",
                    "wr_pct": "",
                    "max_open": "",
                    "stop_pts": spec.stop_pts,
                    "target_pts": spec.target_pts,
                    "notes": "missing data",
                }
            )
            continue

        DEFAULT_TICK_SIZE[spec.instrument] = spec.tick
        TICK_SIZE[spec.instrument] = spec.tick
        # Ensure audit PV known
        if spec.instrument not in POINT_VALUES:
            POINT_VALUES[spec.instrument] = 1.0

        bars, one_m = _load_frames(spec)
        print("  hourly=%d  1m=%d" % (len(bars), len(one_m)), flush=True)

        cfg = VariantConfig(
            "sl50_tp150_3r_1mfill",
            stop_pts=float(spec.stop_pts),
            tp1_pts=float(spec.target_pts),
            notes="1m fill tape; StrategyPlugin PaperBroker",
        )
        print("RUN %s_%s" % (spec.key, cfg.name), flush=True)
        result = run_variant(
            cfg=cfg,
            bars=bars,
            output_root=OUT / spec.key,
            dbn=spec.one_m_path,
            daily_path=spec.daily_path,
            instrument=spec.instrument,
            market=spec.key,
            force=bool(args.force),
            quiet=True,
            one_m=one_m,
        )
        a = result.audit
        stress = float(a.intrabar_mtm_dd_usd or a.close_mtm_dd_usd or 0.0)
        ns = (a.net_usd / abs(stress)) if stress else 0.0
        wr = (100.0 * float(a.win_units) / float(a.units)) if a.units else 0.0
        row = {
            "market": spec.key,
            "instrument": spec.instrument,
            "variant": cfg.name,
            "units": a.units,
            "trades": a.trades,
            "net_usd": round(a.net_usd, 2),
            "stress_dd_usd": round(stress, 2),
            "ns": round(ns, 3),
            "wr_pct": round(wr, 1),
            "max_open": a.max_open_units,
            "stop_pts": spec.stop_pts,
            "target_pts": spec.target_pts,
            "notes": "Engine+PaperBroker+StrategyPlugin; 1m fills",
        }
        rows.append(row)
        print(
            "  Net=$%.0f Stress=$%.0f N/S=%.2f units=%d WR=%.1f%%"
            % (a.net_usd, stress, ns, a.units, wr),
            flush=True,
        )

    # Merge with any prior summary so subset --markets runs do not wipe peers.
    by_market: Dict[str, Dict[str, object]] = {}
    prev_path = OUT / "summary.csv"
    if prev_path.exists() and rows:
        with prev_path.open(newline="", encoding="utf-8") as fh:
            for old in csv.DictReader(fh):
                by_market[str(old.get("market") or "")] = dict(old)
    for r in rows:
        by_market[str(r["market"])] = r
    # Prefer known market order, then leftovers.
    order = [s.key for s in market_specs()] + ["us30"]
    seen = set()
    merged: List[Dict[str, object]] = []
    for key in order:
        if key in by_market and key not in seen:
            merged.append(by_market[key])
            seen.add(key)
    for key, r in by_market.items():
        if key and key not in seen:
            merged.append(r)
            seen.add(key)
    if not merged:
        merged = list(rows)

    fieldnames = list(merged[0].keys())
    with (OUT / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(merged)

    lines = [
        "# ST+PMC sl50_tp150_3r — cross-market 1m fill tape",
        "",
        "StrategyPlugin (`hourly_st_pmc_retest`) + Engine + PaperBroker.",
        "Hourly ST+PMC signals; **1m bars resolve fills** (same method as US30 fair control).",
        "",
        "| Market | Instrument | Units | Net $ | Stress | N/S | WR% | Stop/TP |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in merged:
        lines.append(
            "| `%s` | %s | %s | %s | %s | %s | %s | %s / %s |"
            % (
                r["market"],
                r["instrument"],
                r["units"],
                r["net_usd"],
                r["stress_dd_usd"],
                r["ns"],
                r["wr_pct"],
                r["stop_pts"],
                r["target_pts"],
            )
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- FX stops are **50/150 pips** (EURUSD 0.0050/0.0150, USDJPY 0.50/1.50).",
            "- Metals use **50/150 price points** (XAUUSD PV 100, XAGUSD PV 1000).",
            "- USDJPY audit uses `POINT_VALUES=100000` (JPY notional); raw $ are not USD-comparable — use N/S.",
            "- **MES** skipped — no 1m archive. **SPX500** skipped — no `fx/spx500_1m.csv`.",
            "- US30 fair-control prior: N/S **10.34** (`live/state/us30_st_pmc_retest_add_experiment`).",
            "- Runner: `live/st_pmc_1mfill_cross_market.py`.",
            "",
        ]
    )
    (OUT / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote %s" % (OUT / "SUMMARY.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
