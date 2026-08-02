"""Broker-like Engine+PaperBroker replay of the q1 fakeout reversal satellite.

Feeds every 1m RTH session (dense grid) so the plugin's trailing OR-width
history matches the OR profile engine's all-sessions quartile definition;
the MA50>MA150 regime gate is applied inside the plugin via ``regime_dates``
(same gate as the v2b S_1_1_3 family for apples-to-apples).

Variants (all thresholds fixed a priori from the OR profile tables):
  - split        : entry 2, 1 unit TP at opposite boundary, 1 at opposite 1R
  - opp_boundary : entry 2, both units TP at the opposite boundary

Usage (from repo root):
  python -m live.q1_fakeout_satellite_replay --markets nq mnq
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Sequence

import pandas as pd

from .bars import rth_bars
from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import MARKETS, _regime_dates, load_1m_by_ny_date_any
from .v2b_strategy_replay import (
    AuditBar,
    DEFAULT_SLIPPAGE_TICKS,
    fast_intraday_audit,
    units_from_v2b_fills,
)
from .replay_audit import POINT_VALUES

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "q1_fakeout_satellite"

VARIANTS = {
    "split": {"tp_mode": "split", "entry_qty": 2},
    "opp_boundary": {"tp_mode": "opp_boundary", "entry_qty": 2},
}


def run_market(market: str, out_root: Path, max_days: int = 0) -> List[Dict[str, object]]:
    cfg = MARKETS[market]
    print("Loading %s 1m for q1 fakeout replays..." % cfg.instrument, flush=True)
    gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    all_days = sorted(gby)
    regime = _regime_dates(cfg, gby)
    if max_days:
        all_days = all_days[:max_days]
    regime_iso = [d.isoformat() for d in regime]
    print("  %s: %d sessions to feed, %d regime-eligible" % (cfg.instrument, len(all_days), len(regime)), flush=True)

    rows: List[Dict[str, object]] = []
    for variant, vcfg in VARIANTS.items():
        slug = "%s_q1_fakeout_%s" % (market, variant)
        state_root = out_root / "states" / slug
        if state_root.exists():
            shutil.rmtree(state_root)
        store = FlatFileStore(state_root, defer_table_writes=True)
        store.ensure()
        config = {
            "market": market,
            "tick_size": 0.25,
            "entry_qty": int(vcfg["entry_qty"]),
            "tp_mode": vcfg["tp_mode"],
            "use_regime_filter": True,
            "require_regime_dates": True,
            "regime_dates": regime_iso,
            "record_levels": False,
        }
        instance = StrategyInstance(
            strategy_id=slug,
            strategy_type="q1_fakeout_reversal",
            version="v1",
            instrument=cfg.instrument,
            broker_instrument=cfg.instrument,
            account_mode="paper",
            enabled=True,
            timeframes="1m",
            max_contracts=int(vcfg["entry_qty"]),
            max_open_orders=16,
            config_json=json.dumps(config, sort_keys=True),
        )
        store.write_table("strategy_instances", [as_row(instance)])
        engine = Engine(store=store, persist_bars=False, persist_health=False, slippage_ticks=DEFAULT_SLIPPAGE_TICKS)
        audit_bars: List[AuditBar] = []
        for idx, day in enumerate(all_days, start=1):
            df = rth_bars(gby.get(day), day, dense=True)
            if df.empty:
                continue
            for ts, row in df.iterrows():
                ts_s = pd.Timestamp(ts).isoformat()
                bar = Bar(
                    instrument=cfg.instrument,
                    timeframe="1m",
                    ts=ts_s,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0.0)),
                    complete=True,
                    source=str(cfg.dbn_path),
                )
                engine.process_bar(bar)
                audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
            if idx % 1000 == 0:
                print("  %s %s: %d/%d sessions" % (cfg.instrument, variant, idx, len(all_days)), flush=True)
        store.flush_tables()
        units = units_from_v2b_fills(state_root / "fills.csv", slug)
        audit = fast_intraday_audit(
            strategy_id=slug,
            state_root=state_root,
            bars=audit_bars,
            units=units,
            instrument=cfg.instrument,
            fee_per_unit=cfg.fee_per_unit,
        )
        net = float(audit["net_usd"])
        stress = float(audit["intrabar_stress_dd_usd"])
        rows.append(
            {
                "market": market,
                "variant": variant,
                "sessions_fed": len(all_days),
                "trades": len({u.trade_id for u in units}),
                "units": len(units),
                "net_usd": round(net, 2),
                "closed_dd_usd": round(float(audit["closed_dd_usd"]), 2),
                "intrabar_stress_dd_usd": round(stress, 2),
                "net_over_stress": round(net / abs(stress), 2) if stress else "",
                "win_rate_pct": round(float(audit["win_rate"]), 2),
                "profit_factor": round(float(audit["profit_factor"]), 3)
                if math.isfinite(float(audit["profit_factor"]))
                else "inf",
            }
        )
        print(
            "  %s %s: %d trades, net $%.2f, stress $%.2f"
            % (market, variant, rows[-1]["trades"], net, stress),
            flush=True,
        )

        # yearly breakdown from units
        point_value = POINT_VALUES[cfg.instrument]
        yearly: Dict[int, Dict[str, float]] = defaultdict(lambda: {"net": 0.0, "units": 0})
        for u in units:
            y = datetime.fromisoformat(u.entry_ts).year
            yearly[y]["net"] += u.points * point_value - cfg.fee_per_unit
            yearly[y]["units"] += 1
        ydf = pd.DataFrame(
            [{"year": y, "net_usd": round(v["net"], 2), "units": int(v["units"])} for y, v in sorted(yearly.items())]
        )
        ydf.to_csv(out_root / ("%s_%s_yearly.csv" % (market, variant)), index=False)
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="q1 fakeout reversal satellite broker-like replay")
    ap.add_argument("--markets", nargs="+", default=["nq", "mnq"])
    ap.add_argument("--max-days", type=int, default=0)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    all_rows: List[Dict[str, object]] = []
    for market in args.markets:
        all_rows.extend(run_market(market.lower(), args.out, max_days=args.max_days))
        pd.DataFrame(all_rows).to_csv(args.out / "summary.csv", index=False)

    df = pd.DataFrame(all_rows)
    lines = [
        "# Q1 fakeout reversal satellite — broker-like replay",
        "",
        "Strategy: on q1-OR-width days (trailing 250 sessions, causal in-plugin history), a morning touch break",
        "(before 10:30) that closes back inside the OR on a 5m close within 2 candles is reversed at market;",
        "stop = failed extreme +/- tick; TPs at opposite boundary / opposite 1R. Regime gate MA50>MA150,",
        "hardened realism (1-tick slippage, $1.50/RT). All thresholds fixed a priori from the OR profile tables.",
        "",
        "| Market | Variant | Trades | Units | Net | Closed DD | Stress DD | N/S | Win % | PF |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in df.iterrows():
        lines.append(
            "| %s | %s | %d | %d | $%s | $%s | $%s | %s | %s | %s |"
            % (
                str(r["market"]).upper(),
                r["variant"],
                r["trades"],
                r["units"],
                f"{r['net_usd']:,.0f}",
                f"{r['closed_dd_usd']:,.0f}",
                f"{r['intrabar_stress_dd_usd']:,.0f}",
                r["net_over_stress"],
                r["win_rate_pct"],
                r["profit_factor"],
            )
        )
    lines.append("")
    lines.append("Yearly breakdowns: `<market>_<variant>_yearly.csv`.")
    (args.out / "SUMMARY.md").write_text("\n".join(lines))
    print("Outputs -> %s" % args.out, flush=True)


if __name__ == "__main__":
    main()
