"""London killzone sweep → reverse at opposite level — FX majors.

Same rules as ``eurusd_london_sweep_reversal`` (scaleout 1/1/1):
  - London H/L form **02:00–05:00** America/New_York
  - After **05:00**, first sweep sets bias (low→long / high→short)
  - Entry stop through opposite London level; initial SL at swept level
  - 3 units @ **1R / 2R / 3R**; after TP1, remaining stop → breakeven (next bar)
  - Flatten remainder at **16:00** NY; one campaign max per session

Default markets: EURUSD, GBPUSD, USDJPY. Hub → ``live/state/fx_london_sweep_reversal/``.
"""

from __future__ import annotations

import argparse
import csv
import json
import traceback
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

from .eurusd_london_sweep_reversal import run_backtest, summarize
from .fx_data import load_fx_1m_by_ny_date
from .fx_v2b_london_ungated import MARKETS, MarketSpec, REPO, _progress, _usd_norm

DEFAULT_OUT = REPO / "live" / "state" / "fx_london_sweep_reversal"
DEFAULT_MAJORS = ("EURUSD", "GBPUSD", "USDJPY")


def _point_value(market: MarketSpec) -> float:
    return float(market.point_value)


def run_one(
    *,
    output_root: Path,
    market: MarketSpec,
    start: date,
    force: bool,
    max_days: Optional[int],
    gby: Optional[Dict[date, pd.DataFrame]] = None,
) -> dict:
    strategy_id = "%s_london_sweep_1_1_1" % market.symbol.lower()
    state_root = output_root / "states" / strategy_id
    metrics_path = state_root / "metrics.json"
    one_m = REPO / "fx" / ("%s_1m.csv" % market.symbol.lower())

    if (not force) and metrics_path.exists():
        _progress(output_root, "CACHE %s" % strategy_id)
        return json.loads(metrics_path.read_text(encoding="utf-8"))

    if gby is None:
        gby = load_fx_1m_by_ny_date(one_m, market.symbol)

    # Patch module-level PnL constants for this market (sim uses globals).
    from . import eurusd_london_sweep_reversal as sweep_mod

    prev_pv = sweep_mod.POINT_VALUE
    prev_fee = sweep_mod.FEE_PER_UNIT
    prev_inst = sweep_mod.INSTRUMENT
    sweep_mod.POINT_VALUE = _point_value(market)
    sweep_mod.FEE_PER_UNIT = float(market.fee_per_unit)
    sweep_mod.INSTRUMENT = market.symbol
    try:
        sessions = sorted(d for d in gby if d >= start)
        if max_days is not None:
            sessions = sessions[:max_days]
        # run_backtest filters by start; pass truncated gby for max_days
        if max_days is not None:
            gby_run = {d: gby[d] for d in sessions}
            # include prior day bars for overnight merge in _session_frame
            for d in list(sessions):
                prev = date.fromordinal(d.toordinal() - 1)
                if prev in gby and prev not in gby_run:
                    gby_run[prev] = gby[prev]
        else:
            gby_run = gby
        _progress(output_root, "  %s sessions≈%d" % (market.symbol, len(sessions)))
        trades = run_backtest(gby_run, start)
    finally:
        sweep_mod.POINT_VALUE = prev_pv
        sweep_mod.FEE_PER_UNIT = prev_fee
        sweep_mod.INSTRUMENT = prev_inst

    stats = summarize(trades) if trades else {
        "trades": 0,
        "units": 0,
        "net_usd": 0.0,
        "wins": 0,
        "win_rate": 0.0,
        "avg_r": 0.0,
        "max_dd": 0.0,
        "longs": 0,
        "shorts": 0,
        "tp1": 0,
        "tp2": 0,
        "tp3": 0,
        "stops": 0,
        "be_stops": 0,
        "eod": 0,
    }
    net_native = float(stats["net_usd"])
    dd_native = float(stats["max_dd"])
    net_usd = _usd_norm(net_native, market.quote)
    dd_usd = _usd_norm(dd_native, market.quote)
    stress_proxy = abs(dd_usd) if dd_usd else 0.0

    state_root.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "session",
        "side",
        "london_high",
        "london_low",
        "sweep_ts",
        "entry_ts",
        "entry_price",
        "initial_stop",
        "tp1",
        "tp2",
        "tp3",
        "exit_ts",
        "exit_price",
        "exit_reason",
        "net_usd",
        "r_mult",
        "exits_json",
    ]
    with (state_root / "trades.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for t in trades:
            writer.writerow({k: getattr(t, k) for k in fieldnames})

    result = {
        "strategy_id": strategy_id,
        "symbol": market.symbol,
        "family": market.family,
        "quote": market.quote,
        "book": "S_1_1_1",
        "clock": "london_kz_02_05",
        "or_window": "02:00-05:00",
        "start": start.isoformat(),
        "sessions": len(sessions),
        "trades": int(stats["trades"]),
        "units": int(stats["units"]),
        "net_usd": net_usd,
        "net_native": net_native,
        "closed_dd_usd": dd_usd,
        "stress_dd_usd": stress_proxy,
        "net_over_stress": (net_usd / stress_proxy) if stress_proxy else 0.0,
        "win_rate": float(stats["win_rate"]),
        "avg_r": float(stats["avg_r"]),
        "longs": int(stats["longs"]),
        "shorts": int(stats["shorts"]),
        "tp1": int(stats["tp1"]),
        "tp2": int(stats["tp2"]),
        "tp3": int(stats["tp3"]),
        "stops": int(stats["stops"]),
        "be_stops": int(stats["be_stops"]),
        "eod": int(stats["eod"]),
        "state_root": str(state_root),
    }
    metrics_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    _progress(
        output_root,
        "DONE %s net_usd=%.2f N/S=%.2f trades=%d"
        % (strategy_id, result["net_usd"], result["net_over_stress"], result["trades"]),
    )
    return result


def write_summary(output_root: Path, rows: List[dict]) -> None:
    if not rows:
        return
    pd.DataFrame(rows).to_csv(output_root / "summary.csv", index=False)
    ranked = sorted(rows, key=lambda r: float(r.get("net_over_stress") or 0.0), reverse=True)
    lines = [
        "# FX majors — London sweep reversal (scaleout 1/1/1)",
        "",
        "London KZ **02:00–05:00** NY → first sweep bias → entry opposite level; "
        "TP 1R/2R/3R with BE after TP1; flatten **16:00**.",
        "",
        "| Rank | Symbol | Sessions | Trades | Net≈USD | DD≈USD | N/S | Win% | Avg R | L/S |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for i, r in enumerate(ranked, start=1):
        lines.append(
            "| %d | %s | %d | %d | $%.0f | $%.0f | %.2f | %.1f | %.2f | %d/%d |"
            % (
                i,
                r["symbol"],
                int(r.get("sessions") or 0),
                int(r["trades"]),
                float(r["net_usd"]),
                float(r["stress_dd_usd"]),
                float(r["net_over_stress"]),
                float(r["win_rate"]),
                float(r.get("avg_r") or 0.0),
                int(r.get("longs") or 0),
                int(r.get("shorts") or 0),
            )
        )
    lines.extend(["", "- Hub: `%s`" % output_root.as_posix(), ""])
    (output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    email = [
        "potions: fx_london_sweep_reversal complete",
        "",
        "London KZ 02:00–05:00 → sweep reverse 1/1/1; flatten 16:00. FX majors.",
        "",
        "Top by N/S:",
    ]
    for r in ranked[:12]:
        email.append(
            "  %s  N/S=%.2f  net≈$%.0f  trades=%d  win=%.1f%%"
            % (r["symbol"], float(r["net_over_stress"]), float(r["net_usd"]), int(r["trades"]), float(r["win_rate"]))
        )
    email.extend(["", "Hub: %s" % output_root])
    (output_root / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")


def run_batch(
    *,
    output_root: Path,
    markets: Sequence[str],
    start: date,
    force: bool,
    max_days: Optional[int],
    email: bool,
) -> List[dict]:
    output_root.mkdir(parents=True, exist_ok=True)
    rows: List[dict] = []
    summary_path = output_root / "summary.csv"
    if summary_path.exists() and not force:
        try:
            rows = pd.read_csv(summary_path).to_dict("records")
        except Exception:
            rows = []
    seen = {str(r.get("symbol")) for r in rows}
    _progress(output_root, "START london_sweep markets=%s" % ",".join(markets))
    errors: List[str] = []
    for name in markets:
        key = name.upper()
        market = MARKETS[key]
        if (not force) and key in seen:
            continue
        sid = "%s_london_sweep_1_1_1" % key.lower()
        mp = output_root / "states" / sid / "metrics.json"
        if (not force) and mp.exists() and key not in seen:
            rows.append(json.loads(mp.read_text(encoding="utf-8")))
            seen.add(key)
            write_summary(output_root, rows)
            continue
        try:
            _progress(output_root, "LOAD %s..." % key)
            gby = load_fx_1m_by_ny_date(REPO / "fx" / ("%s_1m.csv" % market.symbol.lower()), market.symbol)
            row = run_one(
                output_root=output_root,
                market=market,
                start=start,
                force=force,
                max_days=max_days,
                gby=gby,
            )
            rows = [r for r in rows if str(r.get("symbol")) != key]
            rows.append(row)
            seen.add(key)
            write_summary(output_root, rows)
        except Exception as exc:
            errors.append("%s: %s" % (key, exc))
            _progress(output_root, "ERROR %s: %s" % (key, exc))
            (output_root / ("ERROR_%s.txt" % key)).write_text(traceback.format_exc(), encoding="utf-8")
    write_summary(output_root, rows)
    if email:
        try:
            from .notify_email import send_email

            body = (output_root / "EMAIL.txt").read_text(encoding="utf-8")
            if errors:
                body += "\n\nErrors:\n" + "\n".join(errors)
            send_email(subject="potions: fx_london_sweep_reversal complete", body=body)
            _progress(output_root, "EMAIL sent")
        except Exception as exc:
            _progress(output_root, "EMAIL failed: %s" % exc)
            try:
                from .notify_email import send_email

                send_email(
                    subject="potions: fx_london_sweep_reversal EMAIL/ partial",
                    body="Hub: %s\nEmail issue: %s\nErrors: %s" % (output_root, exc, errors),
                )
            except Exception:
                pass
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--start", default="2015-01-02")
    p.add_argument("--markets", default=",".join(DEFAULT_MAJORS))
    p.add_argument("--max-days", type=int, default=None)
    p.add_argument("--no-force", action="store_true")
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    rows = run_batch(
        output_root=args.output_root,
        markets=[m.strip().upper() for m in args.markets.split(",") if m.strip()],
        start=date.fromisoformat(args.start),
        force=not args.no_force,
        max_days=args.max_days,
        email=args.email,
    )
    print("Wrote %s (%d rows)" % (args.output_root / "INDEX.md", len(rows)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
