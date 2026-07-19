"""EURUSD monthly 3HL/3LH swing marker → directional v2b S_1_1_3.

After an alternating monthly swing marker completes on month M:

- Green ▲ (3 higher lows) → next calendar month biased **Long**
- Red ▼ (3 lower highs) → next calendar month biased **Short**

Aligned / opposed:

- ``aligned``: trade with the marker
- ``opposed``: fade the marker (flip Long↔Short)

Entry open filter (live in ``v2b_scaleout``):

- Entries arm as v2b stops on the **opening-range boundary** (OR high/low ± tick)
- Long only while bar close is **above the NY 09:30 open** and **above the month open**
- Short only while bar close is **below the NY 09:30 open** and **below the month open**

v2b tracker base S_1_1_3 (entry 5 = TP1 1 / TP2 1 / runner 3); no reverse leg
against the session trade side.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .bars import rth_bars
from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .eurusd_monthly_quarter_charts import detect_swing_streaks, load_monthly
from .eurusd_overnight_sweep import FEE_PER_UNIT, INSTRUMENT, MARKET, TICK, _fx_spread, _has_full_rth_close
from .eurusd_yearly_orb_bias_v2b import _load_daily
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .store import FlatFileStore
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider


REPO = Path(__file__).resolve().parents[1]
DEFAULT_START = date(2004, 1, 2)


def _next_month_period(period: pd.Period) -> pd.Period:
    return period + 1


def compute_monthly_swing_bias(
    daily: pd.DataFrame,
    *,
    mode: str,
    daily_path: Path,
) -> Tuple[Dict[str, str], Dict[str, float], List[dict]]:
    """Map sessions in month M+1 after a swing mark on month M.

    Returns bias map, month opens, and a ledger of sessions. The NY 09:30 open
    is filled later from 1m RTH bars (not available on the daily frame).
    """
    if mode not in {"aligned", "opposed"}:
        raise ValueError("mode must be aligned or opposed")

    work = daily.copy()
    work["date"] = pd.to_datetime(work["date"])
    work = work.sort_values("date").reset_index(drop=True)
    work["session"] = work["date"].dt.date
    work["month_period"] = work["date"].dt.to_period("M")

    monthly = detect_swing_streaks(load_monthly(daily_path))
    # Completing month (month-end index) → signal → trades next month.
    signal_by_next: Dict[pd.Period, str] = {}
    for ts, row in monthly.iterrows():
        period = pd.Timestamp(ts).to_period("M")
        marker = ""
        if bool(row.get("three_higher_lows")):
            marker = "Long"
        elif bool(row.get("three_lower_highs")):
            marker = "Short"
        if not marker:
            continue
        signal_by_next[_next_month_period(period)] = marker

    month_open_by_period: Dict[pd.Period, float] = {}
    for period, g in work.groupby("month_period", sort=True):
        month_open_by_period[period] = float(g.iloc[0]["open"])

    bias: Dict[str, str] = {}
    month_opens: Dict[str, float] = {}
    rows: List[dict] = []

    for _, bar in work.iterrows():
        session = bar["session"].isoformat()
        period = bar["month_period"]
        marker_side = signal_by_next.get(period, "")
        trade_side = ""
        if marker_side:
            if mode == "aligned":
                trade_side = marker_side
            else:
                trade_side = "Short" if marker_side == "Long" else "Long"
        month_open = float(month_open_by_period[period])
        if trade_side:
            bias[session] = trade_side
            month_opens[session] = month_open
        rows.append(
            {
                "session": session,
                "year": int(bar["date"].year),
                "month": int(bar["date"].month),
                "marker_bias": marker_side or "none",
                "trade_bias": trade_side or "none",
                "rth_open_0930": "",
                "month_open": round(month_open, 8),
                "mode": mode,
            }
        )
    return bias, month_opens, rows


def _ny_0930_open(day_df: Optional[pd.DataFrame], session: date) -> Optional[float]:
    """First dense RTH bar open (NY 09:30)."""
    rth = rth_bars(day_df, session, dense=True)
    if rth.empty:
        return None
    return float(rth.iloc[0]["open"])


def run_variant(
    *,
    mode: str,
    output_root: Path,
    start: date,
    force: bool,
    max_days: Optional[int] = None,
) -> dict:
    POINT_VALUES.setdefault(INSTRUMENT, 100000.0)
    DEFAULT_TICK_SIZE.setdefault(INSTRUMENT, TICK)
    one_m, daily_path = ensure_eurusd_platform_files(REPO, force=False)
    output_root.mkdir(parents=True, exist_ok=True)
    strategy_id = "eurusd_v2b_monthly_swing_%s_S_1_1_3" % mode
    state_root = output_root / "states" / strategy_id
    if force and state_root.exists():
        shutil.rmtree(state_root)

    daily_full = _load_daily(daily_path)
    bias_map, month_opens, bias_rows = compute_monthly_swing_bias(
        daily_full, mode=mode, daily_path=daily_path
    )
    bias_rows = [r for r in bias_rows if date.fromisoformat(r["session"]) >= start]

    print("Loading EURUSD 1m for monthly-swing %s v2b..." % mode, flush=True)
    gby = load_fx_1m_by_ny_date(one_m, INSTRUMENT)
    eligible = sorted(
        d
        for d_s, side in bias_map.items()
        for d in [date.fromisoformat(d_s)]
        if d >= start and _has_full_rth_close(gby.get(d), d)
    )
    if max_days is not None:
        eligible = eligible[:max_days]

    # NY 09:30 open from dense RTH 1m (plugin session_day_opens key).
    rth_opens: Dict[str, float] = {}
    row_by_session = {r["session"]: r for r in bias_rows}
    kept: List[date] = []
    for d in eligible:
        o = _ny_0930_open(gby.get(d), d)
        if o is None:
            continue
        key = d.isoformat()
        rth_opens[key] = o
        if key in row_by_session:
            row_by_session[key]["rth_open_0930"] = round(o, 8)
        kept.append(d)
    eligible = kept

    bias_csv = output_root / "monthly_swing_bias_by_session.csv"
    with bias_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "session",
                "year",
                "month",
                "marker_bias",
                "trade_bias",
                "rth_open_0930",
                "month_open",
                "mode",
            ],
        )
        writer.writeheader()
        writer.writerows(bias_rows)

    long_days = sum(1 for d in eligible if bias_map[d.isoformat()] == "Long")
    short_days = sum(1 for d in eligible if bias_map[d.isoformat()] == "Short")
    print(
        "  %s sessions: %d (Long=%d Short=%d)" % (mode, len(eligible), long_days, short_days),
        flush=True,
    )

    session_bias = {d.isoformat(): bias_map[d.isoformat()] for d in eligible}
    session_day_opens = {d.isoformat(): rth_opens[d.isoformat()] for d in eligible}
    session_month_opens = {d.isoformat(): month_opens[d.isoformat()] for d in eligible}
    payload = {
        "market": MARKET,
        "mode": "oco_then_reverse",
        "entry_qty": 5,
        "tp1_qty": 1,
        "tp2_qty": 1,
        "tick_size": TICK,
        "use_regime_filter": True,
        "prior_opposite_only": False,
        "use_session_direction_bias": True,
        "session_direction_bias": session_bias,
        "use_open_alignment_filter": True,
        "arm_open_filter_at_or_only": True,
        "open_ref": "ny_0930_open",
        "session_day_opens": session_day_opens,
        "session_month_opens": session_month_opens,
        "regime_dates": [d.isoformat() for d in eligible],
        "start": start.isoformat(),
        "gate": "monthly_swing_hl_lh",
        "st_mode": mode,
        "record_levels": False,
        "suppress_alerts": True,
    }

    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="v2b_scaleout",
                    version="v1",
                    instrument=INSTRUMENT,
                    broker_instrument=INSTRUMENT,
                    account_mode="paper",
                    enabled=True,
                    timeframes="1m",
                    max_contracts=5,
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
    for idx, day in enumerate(eligible, start=1):
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
        if idx % 250 == 0:
            print("  %s %d/%d" % (strategy_id, idx, len(eligible)), flush=True)

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
        "mode": mode,
        "sizing": "S_1_1_3",
        "sessions": len(eligible),
        "bias_long_days": long_days,
        "bias_short_days": short_days,
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
        "# EURUSD monthly swing (%s) → v2b S_1_1_3" % mode,
        "",
        "Bias from alternating **3 higher lows / 3 lower highs** monthly marker;",
        "trade the **next month**. Entries on OR boundary. Long only above **NY 09:30 + month**",
        "open; Short only below both. Mode: **%s**." % mode,
        "",
        "| Mode | Sessions (L/S) | Trades | Units | Net | Closed DD | Stress DD | Net/Stress | Win% | PF |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        "| %s | %d (%d/%d) | %d | %d | $%.2f | $%.2f | $%.2f | %.2f | %.1f | %.3f |"
        % (
            mode,
            result["sessions"],
            result["bias_long_days"],
            result["bias_short_days"],
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
        "- Bias ledger: `%s`" % bias_csv.as_posix(),
        "- Fills: `%s`" % (state_root / "fills.csv").as_posix(),
        "",
    ]
    (output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    write_run_manifest(
        output_root,
        data_inputs=[one_m, daily_path],
        output_paths=[output_root / "summary.csv", output_root / "INDEX.md", bias_csv, state_root / "fills.csv"],
        strategy_config={
            "driver": "eurusd_monthly_swing_bias_v2b",
            "mode": mode,
            "entry_qty": 5,
            "tp1_qty": 1,
            "tp2_qty": 1,
            "start": start.isoformat(),
            "use_open_alignment_filter": True,
        },
        broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": FEE_PER_UNIT, "spread_model": "fx_half_pip"},
        causality_mode="audit",
        extra={
            "sessions": len(eligible),
            "long_days": long_days,
            "short_days": short_days,
            "net_usd": result["net_usd"],
            "net_over_stress": result["net_over_stress"],
            "mode": mode,
        },
    )
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DEFAULT_START.isoformat())
    parser.add_argument("--max-days", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["aligned", "opposed"],
        choices=["aligned", "opposed"],
    )
    args = parser.parse_args(argv)
    start = date.fromisoformat(args.start)
    results = []
    for mode in args.modes:
        out = REPO / "live" / "state" / ("eurusd_v2b_monthly_swing_%s_S_1_1_3" % mode)
        result = run_variant(
            mode=mode,
            output_root=out,
            start=start,
            force=args.force,
            max_days=args.max_days,
        )
        results.append(result)
        print(
            "DONE %s Net=$%.2f Net/Stress=%.2f trades=%d sessions=%d"
            % (mode, result["net_usd"], result["net_over_stress"], result["trades"], result["sessions"]),
            flush=True,
        )

    compare_root = REPO / "live" / "state" / "eurusd_v2b_monthly_swing_compare"
    compare_root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(compare_root / "summary.csv", index=False)
    lines = [
        "# EURUSD monthly swing marker → v2b compare",
        "",
        "Alternating 3HL/3LH marker bias the **next** month; arm v2b OR-boundary stops only",
        "when price is on the correct side of the **NY 09:30 open** and **month open**.",
        "",
        "| Mode | Sessions (L/S) | Trades | Units | Net | Stress DD | Net/Stress | Win% |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        lines.append(
            "| %s | %d (%d/%d) | %d | %d | $%.2f | $%.2f | %.2f | %.1f |"
            % (
                r["mode"],
                r["sessions"],
                r["bias_long_days"],
                r["bias_short_days"],
                r["trades"],
                r["units"],
                r["net_usd"],
                r["intrabar_stress_dd_usd"],
                r["net_over_stress"],
                r["win_rate"],
            )
        )
    (compare_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote %s" % (compare_root / "INDEX.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
