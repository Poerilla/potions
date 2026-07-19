"""Broker-like EURUSD 15m SuperTrend DCA replay (Engine + PaperBroker).

Each integer unit = 0.5 standard lot (point value $50,000; fee $0.75/unit)
to match the research add size of 0.5 lots × up to 5.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .engine import Engine
from .eurusd_overnight_sweep import _fx_spread
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .hourly_st_pmc_retest_replay import read_bars_from_engine_bars
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .replay_audit import POINT_VALUES, audit_units, units_from_live_fills
from .store import FlatFileStore
from .verification import QuietPaperVerificationProvider
from .ym_hourly_st_pmc_retest_replay import concat_all_1m


REPO = Path(__file__).resolve().parents[1]
INSTRUMENT = "EURUSD"
STRATEGY_ID = "eurusd_intraday_st_dca_15m_0p5x5_close"
HALF_LOT_POINT_VALUE = 50_000.0
FEE_PER_HALF_LOT = 0.75
TICK = 1e-5
NY = "America/New_York"


def _resample_15m(df_1m: pd.DataFrame) -> pd.DataFrame:
    return (
        df_1m.resample("15min", label="right", closed="right")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open"])
    )


def load_15m_bars(one_m_path: Path, start: str, end: str) -> List[Bar]:
    gby = load_fx_1m_by_ny_date(one_m_path, INSTRUMENT)
    one_m = concat_all_1m(gby).sort_index()
    start_ts = pd.Timestamp(start, tz=NY)
    end_ts = pd.Timestamp(end, tz=NY)
    one_m = one_m[(one_m.index >= start_ts) & (one_m.index <= end_ts)]
    m15 = _resample_15m(one_m)
    bars: List[Bar] = []
    for ts, row in m15.iterrows():
        bars.append(
            Bar(
                instrument=INSTRUMENT,
                timeframe="15m",
                ts=ts.isoformat(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(one_m_path),
            )
        )
    return bars


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="EURUSD 15m ST DCA broker-like replay")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2026-03-31")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live" / "state" / "eurusd_intraday_st_dca_broker",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--exit-mode",
        choices=("close", "wick"),
        default="close",
        help="close = exit only if bar closes beyond trail; wick = resting stop",
    )
    args = parser.parse_args(argv)

    strategy_id = STRATEGY_ID if args.exit_mode == "close" else "eurusd_intraday_st_dca_15m_0p5x5_wick"
    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)
    state_root = out / "states" / strategy_id
    if args.force and state_root.exists():
        shutil.rmtree(state_root)

    one_m_path, _daily = ensure_eurusd_platform_files(REPO)
    print(
        "Loading 15m bars %s → %s (exit_mode=%s) ..."
        % (args.start, args.end, args.exit_mode),
        flush=True,
    )
    bars = load_15m_bars(one_m_path, args.start, args.end)
    print("  %d bars" % len(bars), flush=True)

    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type="intraday_st_dca",
        version="v1",
        instrument=INSTRUMENT,
        broker_instrument=INSTRUMENT,
        account_mode="paper",
        enabled=True,
        timeframes="15m",
        max_contracts=5,
        max_open_orders=32,
        config_json=json.dumps(
            {
                "timeframe": "15m",
                "atr_len": 14,
                "atr_mult": 3.0,
                "add_qty": 1,
                "max_adds": 5,
                "tick_size": TICK,
                "session_gate": True,
                "exit_mode": args.exit_mode,
            },
            sort_keys=True,
        ),
    )
    store.write_table("strategy_instances", [as_row(instance)])

    prev_pv = POINT_VALUES.get(INSTRUMENT)
    POINT_VALUES[INSTRUMENT] = HALF_LOT_POINT_VALUE

    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        slippage_ticks=1.0,
        tick_size={INSTRUMENT: TICK},
        spread_model=_fx_spread(),
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
    )

    for idx, bar in enumerate(bars, start=1):
        engine.process_bar(bar)
        if idx % 20000 == 0:
            print("  replayed %d/%d" % (idx, len(bars)), flush=True)
    if hasattr(engine.broker, "flush_state"):
        engine.broker.flush_state()
    store.flush_tables()

    fills_path = state_root / "fills.csv"
    if not fills_path.exists():
        raise SystemExit("No fills written at %s" % fills_path)
    units = units_from_live_fills(fills_path, strategy_id)
    audit = audit_units(
        name="EURUSD 15m ST DCA 0.5×5 exit=%s" % args.exit_mode,
        slug=strategy_id,
        source=fills_path,
        bar_source=one_m_path,
        bars=read_bars_from_engine_bars(bars),
        units=units,
        instrument=INSTRUMENT,
        notes=(
            "Engine + PaperBroker intraday_st_dca. London→NY session. "
            "exit_mode=%s. Each unit=0.5 lot (PV=$50k). ATR ST 14×3. "
            "add_qty=1 max_adds=5. slippage=1 tick; fee=$%.2f/unit."
            % (args.exit_mode, FEE_PER_HALF_LOT)
        ),
        output_root=out / "audits" / strategy_id,
        fee_per_unit=FEE_PER_HALF_LOT,
    )
    if prev_pv is not None:
        POINT_VALUES[INSTRUMENT] = prev_pv

    ratio = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
    summary = {
        "strategy_id": strategy_id,
        "exit_mode": args.exit_mode,
        "trades": audit.trades,
        "units": audit.units,
        "net_usd": round(audit.net_usd, 2),
        "closed_dd_usd": round(audit.close_mtm_dd_usd, 2),
        "stress_dd_usd": round(audit.intrabar_mtm_dd_usd, 2),
        "net_over_stress": round(ratio, 3),
        "win_units": audit.win_units,
        "win_rate_pct": round(100.0 * audit.win_units / audit.units, 2) if audit.units else 0.0,
        "max_open_units": audit.max_open_units,
        "window": "%s → %s" % (args.start, args.end),
        "unit_definition": "1 unit = 0.5 standard lot",
        "state_root": str(state_root),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "SUMMARY.md").write_text(
        "\n".join(
            [
                "# EURUSD 15m ST DCA — close-beyond-trail exit",
                "",
                "Exit only when the 15m bar **closes** beyond the SuperTrend trail (wicks ignored).",
                "",
                "| Metric | Value |",
                "|---|---:|",
                "| Exit mode | %s |" % args.exit_mode,
                "| Net | $%s |" % f"{audit.net_usd:,.2f}",
                "| Intrabar stress DD | $%s |" % f"{audit.intrabar_mtm_dd_usd:,.2f}",
                "| Closed DD | $%s |" % f"{audit.close_mtm_dd_usd:,.2f}",
                "| Net / Stress | %.3f |" % ratio,
                "| Trades / Units | %d / %d |" % (audit.trades, audit.units),
                "| Win units %% | %.1f |"
                % (100.0 * audit.win_units / audit.units if audit.units else 0.0),
                "| Max open units | %d |" % audit.max_open_units,
                "",
                "Window: %s → %s. Session: London 08:00 → NY 16:00." % (args.start, args.end),
                "Unit = 0.5 lot (PV $50,000). Fee $%.2f/unit. Slippage 1 tick + FX half-spread."
                % FEE_PER_HALF_LOT,
                "",
                "Prior wick-stop broker result: −$516.5k / −$517.8k stress (Net/Stress −1.0).",
                "",
                "States: `%s`" % state_root,
                "Audit: `%s`" % (out / "audits" / strategy_id),
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2), flush=True)
    print("Wrote", out / "SUMMARY.md", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
