"""Futures ST+PMC runner variants on 1m fill tape (YM / MYM / NQ / MNQ).

Same rules as US30 ``us30_st_pmc_runner_variants``:
  - Fair control: 1× SL50 / TP150
  - Dual runners: TP150 + 2×TP (300) + 10×TP (1500) or indefinite
  - Both runners SL→BE after TP1; indefinite EOY flatten, non-blocking

Uses ``run_variant`` + ``_replay_hourly_with_1m`` with ``broker_fills=False`` on
1h signal bars (HTF lookahead fill fix, 2026-08-07).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from .broker import DEFAULT_TICK_SIZE
from .hourly_st_pmc_loss_research import VariantConfig
from .hourly_st_pmc_strategyplugin_variants import MARKET_CONFIGS, TICK_SIZE, run_variant
from .models import Bar
from .replay_audit import POINT_VALUES
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, load_1m_by_ny_date_any, resample_hourly

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "futures_st_pmc_runner_variants"
DEFAULT_MARKETS = ("ym", "mym", "nq", "mnq")


def _variant_configs(tp: float = 150.0) -> List[VariantConfig]:
    return [
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


def _load_market(market: str):
    cfg = MARKET_CONFIGS[market]
    instrument = str(cfg["instrument"])
    dbn = Path(cfg["dbn"])
    daily = Path(cfg["daily"])
    if not dbn.exists():
        raise FileNotFoundError("Missing 1m source for %s: %s" % (market, dbn))
    if not daily.exists():
        raise FileNotFoundError("Missing daily for %s: %s" % (market, daily))
    print("Loading %s 1m → hourly…" % instrument, flush=True)
    gby = load_1m_by_ny_date_any(dbn.resolve(), instrument.lower())
    one_m_df = concat_all_1m(gby)
    hourly = resample_hourly(one_m_df)
    bars: List[Bar] = []
    for ts, row in hourly.iterrows():
        bars.append(
            Bar(
                instrument=instrument,
                timeframe="1h",
                ts=ts.isoformat(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(dbn),
            )
        )
    print("  %s hourly=%d 1m=%d" % (instrument, len(bars), len(one_m_df)), flush=True)
    return instrument, dbn, daily, bars, one_m_df


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


def _year_end_stats_strict(fills_path: Path) -> Dict[str, int]:
    """Count year_end_flatten fills (reason or bracket_role)."""
    out: Dict[str, int] = {}
    if not fills_path.exists():
        return out
    with fills_path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            reason = str(row.get("reason") or "")
            role = str(row.get("bracket_role") or "")
            if reason != "year_end_flatten" and role != "year_end_flatten":
                continue
            ts = str(row.get("ts") or "")
            year = ts[:4]
            if not year.isdigit():
                continue
            qty = abs(int(float(row.get("quantity") or 0)))
            out[year] = int(out.get(year) or 0) + qty
    return out


def run_market(
    market: str,
    *,
    variants: Sequence[VariantConfig],
    force: bool,
) -> List[Dict[str, object]]:
    instrument, dbn, daily, bars, one_m_df = _load_market(market)
    tick = float(TICK_SIZE[instrument])
    DEFAULT_TICK_SIZE[instrument] = tick
    TICK_SIZE[instrument] = tick
    market_out = OUT / market
    market_out.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, object]] = []
    for cfg in variants:
        print("RUN %s/%s (max_contracts=%d)" % (market, cfg.name, cfg.max_contracts), flush=True)
        result = run_variant(
            cfg=cfg,
            bars=bars,
            output_root=market_out,
            dbn=dbn,
            daily_path=daily,
            instrument=instrument,
            market=market,
            force=force,
            quiet=True,
            one_m=one_m_df,
        )
        a = result.audit
        stress = float(a.intrabar_mtm_dd_usd or a.close_mtm_dd_usd or 0.0)
        ns = (a.net_usd / abs(stress)) if stress else 0.0
        wr = (100.0 * float(a.win_units) / float(a.units)) if a.units else 0.0
        state = _read_strategy_state(result.state_root, result.strategy_id)
        eoy_by_year = _year_end_stats_strict(result.state_root / "fills.csv")
        if not eoy_by_year and state.get("year_end_flatten_by_year"):
            raw = state.get("year_end_flatten_by_year") or {}
            eoy_by_year = {str(k): int(v) for k, v in raw.items()}
        eoy_total = int(sum(eoy_by_year.values()))
        eoy_events = int(state.get("year_end_flatten_events") or len(eoy_by_year))
        row = {
            "market": market,
            "instrument": instrument,
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
        rows.append(row)
        print(
            "  %s Net=$%.0f Stress=$%.0f N/S=%.2f units=%d WR=%.1f%% max_open=%d EOY_units=%d %s"
            % (
                instrument,
                a.net_usd,
                stress,
                ns,
                a.units,
                wr,
                a.max_open_units,
                eoy_total,
                json.dumps(eoy_by_year, sort_keys=True),
            ),
            flush=True,
        )
    return rows


def _load_existing_summary() -> Dict[Tuple[str, str], Dict[str, object]]:
    """Key=(market, variant) → row; used so --only / partial runs don't wipe peers."""
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
        "eoy_flatten_events",
        "eoy_flatten_units",
        "eoy_flatten_by_year",
        "notes",
    ]
    merged = _load_existing_summary()
    for r in all_rows:
        merged[(str(r["market"]), str(r["variant"]))] = dict(r)
    # Stable order: market then variant name
    ordered = sorted(merged.values(), key=lambda r: (str(r.get("market")), str(r.get("variant"))))
    csv_path = OUT / "summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in ordered:
            w.writerow({k: r.get(k, "") for k in fields})
    all_rows = ordered  # type: ignore[assignment]

    lines = [
        "# Futures ST+PMC runner variants (1m fill tape)",
        "",
        "Markets: YM / MYM / NQ / MNQ. Same dual-runner rules as US30 runner hub.",
        "",
        "## Fill timing",
        "",
        "1h bars are **signal-only** (`broker_fills=False`); resting limits fill on the **1m** tape.",
        "",
        "## Results",
        "",
        "| market | variant | net | stress | N/S | units | WR% | max_open | EOY units | EOY by year |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in all_rows:
        lines.append(
            "| `%s` | `%s` | $%.0f | $%.0f | %.2f | %s | %.1f | %s | %s | %s |"
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
                r["eoy_flatten_by_year"],
            )
        )
    lines.extend(
        [
            "",
            "## Risk accounting",
            "",
            "MTM / protected-floor / realized / giveback / open-exposure (runner vs base):",
            "[`RUNNER_RISK_ACCOUNTING.md`](RUNNER_RISK_ACCOUNTING.md)",
            "",
            "## Artifacts",
            "",
            "- `summary.csv`",
            "- `RUNNER_RISK_ACCOUNTING.md` / `.csv`",
            "- Per market: `<market>/states/`, `<market>/audits/`",
            "- Runner: `live/futures_st_pmc_runner_variants.py`",
            "",
        ]
    )
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote %s" % csv_path, flush=True)
    print("Wrote %s" % (OUT / "SUMMARY.md"), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true")
    ap.add_argument(
        "--markets",
        nargs="*",
        default=list(DEFAULT_MARKETS),
        choices=sorted(k for k in MARKET_CONFIGS if k in {"ym", "mym", "nq", "mnq", "mes", "es"}),
    )
    ap.add_argument("--only", nargs="*", default=None, help="Variant name filter(s).")
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args()

    variants = _variant_configs()
    if args.only:
        want = set(args.only)
        variants = [v for v in variants if v.name in want]
        if not variants:
            raise SystemExit("No variants matched --only %s" % sorted(want))

    OUT.mkdir(parents=True, exist_ok=True)
    all_rows: List[Dict[str, object]] = []
    for market in args.markets:
        if market == "mes" and not Path(MARKET_CONFIGS["mes"]["dbn"]).exists():
            print("SKIP mes — missing 1m archive", flush=True)
            continue
        all_rows.extend(run_market(market, variants=variants, force=bool(args.force)))
        # Persist incrementally so long NQ runs leave a partial summary.
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
