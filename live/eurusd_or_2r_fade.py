"""EURUSD opening-range break → N×R fade (flat 1 by default).

Independent of monthly swing bias. Every full RTH session:

1. OR 09:30–09:45 NY
2. First break of OR high/low arms a fade **limit at ``--fade-r``** (default 2R)
3. On fill: SL = ``--stop-r`` beyond entry (default 1R); TP = OR boundary

Use ``--grid`` to compare entry∈{2,3}R × stop∈{1,2}R.

Uses PaperBroker + hardened FX realism (1-tick slip, half-pip spread, $7/unit).
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .bars import rth_bars
from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .eurusd_overnight_sweep import FEE_PER_UNIT, INSTRUMENT, MARKET, TICK, _fx_spread, _has_full_rth_close
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import MarketConfig, _regime_dates
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider


REPO = Path(__file__).resolve().parents[1]
DEFAULT_START = date(2004, 1, 2)


def run(
    *,
    output_root: Path,
    start: date,
    force: bool,
    entry_qty: int = 1,
    tp_mode: str = "or_boundary",
    fade_r_mult: float = 2.0,
    stop_r_mult: float = 1.0,
    max_days: Optional[int] = None,
) -> dict:
    POINT_VALUES.setdefault(INSTRUMENT, 100000.0)
    DEFAULT_TICK_SIZE.setdefault(INSTRUMENT, TICK)
    one_m, daily = ensure_eurusd_platform_files(REPO, force=False)
    strategy_id = "eurusd_or_fade_e%ss%sq%d_%s" % (
        _r_slug(fade_r_mult),
        _r_slug(stop_r_mult),
        entry_qty,
        tp_mode,
    )
    state_root = output_root / "states" / strategy_id
    if force and state_root.exists():
        shutil.rmtree(state_root)
    output_root.mkdir(parents=True, exist_ok=True)

    cfg = MarketConfig(
        market=MARKET,
        instrument=INSTRUMENT,
        daily_path=daily,
        dbn_path=one_m,
        start=start,
        fee_per_unit=FEE_PER_UNIT,
    )
    print(
        "Loading EURUSD 1m for OR fade entry=%sR stop=%sR (%s)..."
        % (_r_slug(fade_r_mult), _r_slug(stop_r_mult), strategy_id),
        flush=True,
    )
    gby = load_fx_1m_by_ny_date(one_m, INSTRUMENT)
    regime_dates = _regime_dates(cfg, gby, start=start)
    regime_dates = [d for d in regime_dates if _has_full_rth_close(gby.get(d), d)]
    if max_days is not None:
        regime_dates = regime_dates[:max_days]
    print("  regime sessions: %d" % len(regime_dates), flush=True)

    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {
        "market": MARKET,
        "entry_qty": entry_qty,
        "tp_mode": tp_mode,
        "fade_r_mult": float(fade_r_mult),
        "stop_r_mult": float(stop_r_mult),
        "tick_size": TICK,
        "use_regime_filter": True,
        "start": start.isoformat(),
        "regime_dates": [d.isoformat() for d in regime_dates],
        "record_levels": False,
        "suppress_alerts": True,
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="or_2r_fade",
                    version="v1",
                    instrument=INSTRUMENT,
                    broker_instrument=INSTRUMENT,
                    account_mode="paper",
                    enabled=True,
                    timeframes="1m",
                    max_contracts=max(1, entry_qty),
                    max_open_orders=64,
                    config_json=json.dumps(payload, sort_keys=True),
                )
            )
        ],
    )
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        tick_size={INSTRUMENT: TICK},
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
        **hardened_replay_engine_kwargs(slippage_ticks=1.0, spread_model=_fx_spread()),
    )

    audit_bars: List[AuditBar] = []
    for idx, day in enumerate(regime_dates, start=1):
        df = rth_bars(gby.get(day), day, dense=True)
        if df.empty:
            continue
        for ts, row in df.iterrows():
            ts_s = pd.Timestamp(ts).isoformat()
            bar = Bar(
                instrument=INSTRUMENT,
                timeframe="1m",
                ts=ts_s,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(one_m),
            )
            engine.process_bar(bar)
            audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
        if idx % 500 == 0:
            print("  %s %d/%d" % (strategy_id, idx, len(regime_dates)), flush=True)

    store.flush_tables()
    units = units_from_v2b_fills(state_root / "fills.csv", strategy_id)
    audit = fast_intraday_audit(
        strategy_id=strategy_id,
        state_root=state_root,
        bars=audit_bars,
        units=units,
        instrument=INSTRUMENT,
        fee_per_unit=FEE_PER_UNIT,
    )
    result = {
        "strategy_id": strategy_id,
        "entry_qty": entry_qty,
        "tp_mode": tp_mode,
        "fade_r_mult": float(fade_r_mult),
        "stop_r_mult": float(stop_r_mult),
        "sessions": len(regime_dates),
        "start": start.isoformat(),
        "units": len(units),
        "trades": len({u.trade_id for u in units}),
        "net_usd": float(audit["net_usd"]),
        "closed_dd_usd": float(audit["closed_dd_usd"]),
        "intrabar_stress_dd_usd": float(audit["intrabar_stress_dd_usd"]),
        "max_open_units": int(audit["max_open_units"]),
        "win_rate": float(audit["win_rate"]),
        "profit_factor": float(audit["profit_factor"]),
    }
    result["net_over_stress"] = (
        result["net_usd"] / abs(result["intrabar_stress_dd_usd"]) if result["intrabar_stress_dd_usd"] else 0.0
    )
    pd.DataFrame([result]).to_csv(output_root / "summary.csv", index=False)
    lines = [
        "# EURUSD OR → fade (entry %sR / stop %sR)" % (_r_slug(fade_r_mult), _r_slug(stop_r_mult)),
        "",
        "Opening range **09:30–09:45 NY**. First break arms a **fade limit at %sR**."
        % _r_slug(fade_r_mult),
        "Fill → SL **%sR** beyond entry; TP mode **%s** (qty=%d)."
        % (_r_slug(stop_r_mult), tp_mode, entry_qty),
        "",
        "| Sessions | Trades | Units | Net | Closed DD | Stress DD | Net/Stress | Win% | PF |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        "| %d | %d | %d | $%.2f | $%.2f | $%.2f | %.2f | %.1f | %.3f |"
        % (
            result["sessions"],
            result["trades"],
            result["units"],
            result["net_usd"],
            result["closed_dd_usd"],
            result["intrabar_stress_dd_usd"],
            result["net_over_stress"],
            result["win_rate"],
            result["profit_factor"],
        ),
        "",
        "- Start: **%s**" % start.isoformat(),
        "- Fills: `%s`" % (state_root / "fills.csv").as_posix(),
        "",
    ]
    (output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    write_run_manifest(
        output_root,
        data_inputs=[one_m, daily],
        output_paths=[output_root / "summary.csv", output_root / "INDEX.md", state_root / "fills.csv"],
        strategy_config={
            "driver": "eurusd_or_2r_fade",
            "entry_qty": entry_qty,
            "tp_mode": tp_mode,
            "fade_r_mult": float(fade_r_mult),
            "stop_r_mult": float(stop_r_mult),
            "start": start.isoformat(),
        },
        broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": FEE_PER_UNIT, "spread_model": "fx_half_pip"},
        causality_mode="audit",
        extra={
            "sessions": len(regime_dates),
            "trades": result["trades"],
            "net_usd": result["net_usd"],
            "net_over_stress": result["net_over_stress"],
        },
    )
    return result


def _r_slug(value: float) -> str:
    text = ("%g" % float(value)).replace(".", "p")
    return text


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DEFAULT_START.isoformat())
    parser.add_argument("--entry-qty", type=int, default=1)
    parser.add_argument(
        "--tp-mode",
        default="or_boundary",
        choices=["or_boundary", "one_r", "split"],
    )
    parser.add_argument("--fade-r", type=float, default=2.0, help="Entry extension in R (default 2)")
    parser.add_argument("--stop-r", type=float, default=1.0, help="Stop distance beyond entry in R (default 1)")
    parser.add_argument("--max-days", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--grid",
        action="store_true",
        help="Run entry∈{2,3}R × stop∈{1,2}R and write a compare table",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
    )
    args = parser.parse_args(argv)
    start = date.fromisoformat(args.start)

    if args.grid:
        compare_root = args.output_root or (REPO / "live" / "state" / "eurusd_or_fade_rr_compare")
        compare_root.mkdir(parents=True, exist_ok=True)
        results = []
        for fade_r, stop_r in ((2.0, 1.0), (2.0, 2.0), (3.0, 1.0), (3.0, 2.0)):
            out = compare_root / ("fade_%sR_sl_%sR" % (_r_slug(fade_r), _r_slug(stop_r)))
            result = run(
                output_root=out,
                start=start,
                force=args.force,
                entry_qty=args.entry_qty,
                tp_mode=args.tp_mode,
                fade_r_mult=fade_r,
                stop_r_mult=stop_r,
                max_days=args.max_days,
            )
            results.append(result)
            print(
                "DONE entry=%sR stop=%sR Net=$%.2f Net/Stress=%.2f trades=%d"
                % (
                    _r_slug(fade_r),
                    _r_slug(stop_r),
                    result["net_usd"],
                    result["net_over_stress"],
                    result["trades"],
                ),
                flush=True,
            )
        pd.DataFrame(results).to_csv(compare_root / "summary.csv", index=False)
        lines = [
            "# EURUSD OR fade — entry × stop R grid",
            "",
            "Flat qty=%d, TP=%s. Entry at N×R extension; SL = M×R beyond entry."
            % (args.entry_qty, args.tp_mode),
            "",
            "| Entry | SL | Trades | Units | Net | Stress DD | Net/Stress | Win% | PF |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for r in results:
            lines.append(
                "| %gR | %gR | %d | %d | $%.2f | $%.2f | %.2f | %.1f | %.3f |"
                % (
                    r["fade_r_mult"],
                    r["stop_r_mult"],
                    r["trades"],
                    r["units"],
                    r["net_usd"],
                    r["intrabar_stress_dd_usd"],
                    r["net_over_stress"],
                    r["win_rate"],
                    r["profit_factor"],
                )
            )
        (compare_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("Wrote %s" % (compare_root / "INDEX.md"), flush=True)
        return 0

    out = args.output_root or (
        REPO
        / "live"
        / "state"
        / ("eurusd_or_fade_e%sR_sl%sR" % (_r_slug(args.fade_r), _r_slug(args.stop_r)))
    )
    result = run(
        output_root=out,
        start=start,
        force=args.force,
        entry_qty=args.entry_qty,
        tp_mode=args.tp_mode,
        fade_r_mult=args.fade_r,
        stop_r_mult=args.stop_r,
        max_days=args.max_days,
    )
    print(
        "DONE Net=$%.2f Net/Stress=%.2f trades=%d sessions=%d"
        % (result["net_usd"], result["net_over_stress"], result["trades"], result["sessions"]),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
