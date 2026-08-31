"""FX / index CFD / metals ST+PMC runner variants (1m fill tape).

Same dual-runner rules as US30 / futures hubs, with market-native stop/TP units:
  - NAS100 / metals: 50 / 150 price points
  - EURUSD / GBPUSD: 50 / 150 pips (0.0050 / 0.0150)
  - USDJPY / AUDJPY: 50 / 150 pips (0.50 / 1.50)

Lot-correct audit (trade_id match, reachable stop stress, forced-flat open mark)
comes from ``run_variant`` (2026-08-08). Completed-hour causality (2026-08):
left-labeled hourly bars are shifted to the hour-complete timestamp before the
strategy consumes them; fills only on the 1m tape.

SPX500 is skipped when ``fx/spx500_1m.csv`` is absent.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .fx_data import load_fx_1m_by_ny_date
from .hourly_st_pmc_loss_research import VariantConfig
from .hourly_st_pmc_strategyplugin_variants import TICK_SIZE, run_variant
from .models import Bar
from .replay_audit import POINT_VALUES
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, resample_hourly

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "fx_index_metals_st_pmc_runner_variants"


@dataclass(frozen=True)
class MarketSpec:
    key: str
    instrument: str
    one_m_path: Path
    daily_path: Path
    stop_pts: float
    target_pts: float
    tick: float
    notes: str = ""


def market_specs() -> List[MarketSpec]:
    def fx(key: str, instrument: str, stop: float, target: float, tick: float, notes: str = "") -> MarketSpec:
        return MarketSpec(
            key=key,
            instrument=instrument,
            one_m_path=REPO / "fx" / ("%s_1m.csv" % key),
            daily_path=REPO / "fx" / ("%s_daily.csv" % key),
            stop_pts=stop,
            target_pts=target,
            tick=tick,
            notes=notes,
        )

    out = [
        fx("nas100", "NAS100", 50.0, 150.0, 0.1, "index CFD points"),
        fx("eurusd", "EURUSD", 0.0050, 0.0150, 0.00001, "50/150 pips"),
        fx("gbpusd", "GBPUSD", 0.0050, 0.0150, 0.00001, "50/150 pips"),
        fx("usdjpy", "USDJPY", 0.50, 1.50, 0.001, "50/150 pips; PV in JPY"),
        fx("audjpy", "AUDJPY", 0.50, 1.50, 0.001, "50/150 pips; PV in JPY"),
        fx("xauusd", "XAUUSD", 50.0, 150.0, 0.01, "50/150 gold points"),
        fx("xagusd", "XAGUSD", 50.0, 150.0, 0.001, "50/150 silver points"),
    ]
    spx_1m = REPO / "fx" / "spx500_1m.csv"
    spx_daily = REPO / "fx" / "spx500_daily.csv"
    if spx_1m.exists() and spx_daily.exists():
        out.append(fx("spx500", "SPX500", 50.0, 150.0, 0.1, "index CFD points"))
    return out


def _variant_configs(stop: float, tp: float) -> List[VariantConfig]:
    return [
        VariantConfig(
            "sl50_tp150_3r_1mfill",
            stop_pts=stop,
            tp1_pts=tp,
            notes="fair control: 1 unit SL/TP on 1m fill tape",
        ),
        VariantConfig(
            "sl50_tp150_runners_2r_10r",
            stop_pts=stop,
            tp1_pts=tp,
            tp1_qty=1,
            runner_specs=((1, 2.0 * tp), (1, 10.0 * tp)),
            runner_stop_to_be_after_tp1=True,
            notes="3 units: TP1 + runner@2R + runner@10R; both runners SL→BE after TP1",
        ),
        VariantConfig(
            "sl50_tp150_runners_2r_indef",
            stop_pts=stop,
            tp1_pts=tp,
            tp1_qty=1,
            runner_specs=((1, 2.0 * tp), (1, None)),
            runner_stop_to_be_after_tp1=True,
            year_end_flatten_runners=True,
            runners_do_not_block_entries=True,
            notes=(
                "3 units: TP1 + runner@2R + indefinite; SL→BE after TP1; "
                "EOY flatten; indefinite runners do not block later campaigns"
            ),
        ),
    ]


def _load_market(spec: MarketSpec) -> Tuple[List[Bar], pd.DataFrame]:
    gby = load_fx_1m_by_ny_date(spec.one_m_path, spec.instrument)
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


def _year_end_stats(fills_path: Path) -> Dict[str, int]:
    out: Dict[str, int] = {}
    if not fills_path.exists():
        return out
    with fills_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if str(row.get("reason") or "") != "year_end_flatten":
                continue
            year = str(row.get("ts") or "")[:4]
            if not year.isdigit():
                continue
            out[year] = int(out.get(year) or 0) + abs(int(float(row.get("quantity") or 0)))
    return out


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


def _load_existing_summary() -> Dict[Tuple[str, str], Dict[str, object]]:
    csv_path = OUT / "summary.csv"
    out: Dict[Tuple[str, str], Dict[str, object]] = {}
    if not csv_path.exists():
        return out
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            m = str(row.get("market") or "")
            v = str(row.get("variant") or "")
            if m and v:
                out[(m, v)] = dict(row)
    return out


def write_summary(all_rows: Sequence[Dict[str, object]]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fields = [
        "market",
        "instrument",
        "variant",
        "units",
        "trades",
        "net_usd",
        "stress_dd_usd",
        "ns",
        "wr_pct",
        "max_open",
        "eoy_flatten_units",
        "eoy_flatten_by_year",
        "stop_pts",
        "target_pts",
        "notes",
    ]
    merged = _load_existing_summary()
    for r in all_rows:
        merged[(str(r["market"]), str(r["variant"]))] = dict(r)
    ordered = sorted(merged.values(), key=lambda r: (str(r.get("market")), str(r.get("variant"))))
    csv_path = OUT / "summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in ordered:
            w.writerow({k: r.get(k, "") for k in fields})

    lines = [
        "# FX / index / metals ST+PMC runner variants (1m fill tape)",
        "",
        "Lot-correct audit: trade_id match, reachable stop stress, forced-flat open mark.",
        "",
        "> **2026-08 completed-hour causality fix.** The shared hourly resampler "
        "is left-labeled, so a bar timestamped 11:00 contains 11:00-11:59 data. "
        "This replay shifts signal bars to the completed-hour timestamp before "
        "the strategy can consume them, and fills only on the 1m tape.",
        "",
        "## Rankability",
        "",
        "| Class | Status |",
        "|---|---|",
        "| Fair 3R / max 1 | **Rankable** |",
        "| 2R→10R / max 3 | **Rankable** |",
        "| Indefinite | **Not rankable** vs 3R/10R until lot-correct forced-flat reviewed as inventory sleeve |",
        "",
        "## Results",
        "",
        "| market | variant | net | stress | N/S | units | WR% | max_open | EOY | stop/tp |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in ordered:
        lines.append(
            "| `%s` | `%s` | $%.0f | $%.0f | %.2f | %s | %.1f | %s | %s | %s / %s |"
            % (
                r["market"],
                r["variant"],
                float(r["net_usd"]),
                float(r["stress_dd_usd"]),
                float(r["ns"]),
                r["units"],
                float(r["wr_pct"]),
                r["max_open"],
                r["eoy_flatten_units"],
                r.get("stop_pts", ""),
                r.get("target_pts", ""),
            )
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- **SPX500** skipped when `fx/spx500_1m.csv` is missing (live demo bars only).",
            "- USDJPY / AUDJPY nets use platform PV (JPY per price unit) — treat as native currency unless converted.",
            "- Post-process lot books: `python -m live.indefinite_lot_accounting --hubs fx`",
            "",
            "## Artifacts",
            "",
            "- `summary.csv`",
            "- Per market: `<market>/states/`, `<market>/audits/`",
            "- Runner: `live/fx_index_metals_st_pmc_runner_variants.py`",
            "",
        ]
    )
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote %s" % csv_path, flush=True)
    print("Wrote %s" % (OUT / "SUMMARY.md"), flush=True)


def run_market(spec: MarketSpec, *, force: bool, only: Optional[Sequence[str]]) -> List[Dict[str, object]]:
    if not spec.one_m_path.exists() or not spec.daily_path.exists():
        print("SKIP %s — missing 1m/daily" % spec.key, flush=True)
        return []
    inst = spec.instrument
    POINT_VALUES.setdefault(inst, POINT_VALUES.get(inst, 1.0))
    DEFAULT_TICK_SIZE[inst] = spec.tick
    TICK_SIZE[inst] = spec.tick

    print("Loading %s 1m → hourly…" % inst, flush=True)
    bars, one_m = _load_market(spec)
    print("  %s hourly=%d 1m=%d" % (inst, len(bars), len(one_m)), flush=True)

    variants = _variant_configs(spec.stop_pts, spec.target_pts)
    if only:
        want = set(only)
        variants = [v for v in variants if v.name in want]
    market_out = OUT / spec.key
    market_out.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, object]] = []
    for cfg in variants:
        print(
            "RUN %s/%s (max_contracts=%d stop=%g tp=%g)"
            % (spec.key, cfg.name, cfg.max_contracts, cfg.stop_pts, cfg.tp1_pts),
            flush=True,
        )
        result = run_variant(
            cfg=cfg,
            bars=bars,
            output_root=market_out,
            dbn=spec.one_m_path,
            daily_path=spec.daily_path,
            instrument=inst,
            market=spec.key,
            force=force,
            quiet=True,
            one_m=one_m,
        )
        a = result.audit
        stress = float(a.intrabar_mtm_dd_usd or a.close_mtm_dd_usd or 0.0)
        ns = (a.net_usd / abs(stress)) if stress else 0.0
        wr = (100.0 * float(a.win_units) / float(a.units)) if a.units else 0.0
        state = _read_strategy_state(result.state_root, result.strategy_id)
        eoy = _year_end_stats(result.state_root / "fills.csv")
        if not eoy and state.get("year_end_flatten_by_year"):
            eoy = {str(k): int(v) for k, v in (state.get("year_end_flatten_by_year") or {}).items()}
        row = {
            "market": spec.key,
            "instrument": inst,
            "variant": cfg.name,
            "units": a.units,
            "trades": a.trades,
            "net_usd": round(a.net_usd, 2),
            "stress_dd_usd": round(stress, 2),
            "ns": round(ns, 3),
            "wr_pct": round(wr, 1),
            "max_open": a.max_open_units,
            "eoy_flatten_units": int(sum(eoy.values())),
            "eoy_flatten_by_year": json.dumps(eoy, sort_keys=True),
            "stop_pts": spec.stop_pts,
            "target_pts": spec.target_pts,
            "notes": "%s | %s" % (spec.notes, cfg.notes),
        }
        rows.append(row)
        print(
            "  %s Net=$%.0f Stress=$%.0f N/S=%.2f units=%d WR=%.1f%% max_open=%d EOY=%d"
            % (inst, a.net_usd, stress, ns, a.units, wr, a.max_open_units, sum(eoy.values())),
            flush=True,
        )
    return rows


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    specs = market_specs()
    keys = [s.key for s in specs]
    ap.add_argument("--markets", nargs="*", default=keys, choices=sorted(set(keys + ["spx500"])))
    ap.add_argument("--only", nargs="*", default=None, help="Variant name filter(s)")
    ap.add_argument(
        "--snapshot",
        action="store_true",
        help="Refresh LATEST_SNAPSHOT / COMPLETION_EMAIL after summary write",
    )
    ap.add_argument(
        "--email",
        action="store_true",
        help="Refresh snapshot and email decision-oriented interim/completion body",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    want = {m.lower() for m in args.markets}
    selected = [s for s in specs if s.key in want]
    if "spx500" in want and not any(s.key == "spx500" for s in specs):
        print("NOTE: SPX500 skipped — no fx/spx500_1m.csv historical archive.", flush=True)
    if not selected:
        raise SystemExit("No markets selected / available")

    OUT.mkdir(parents=True, exist_ok=True)
    all_rows: List[Dict[str, object]] = []
    for spec in selected:
        all_rows.extend(run_market(spec, force=bool(args.force), only=args.only))
        write_summary(all_rows)
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
