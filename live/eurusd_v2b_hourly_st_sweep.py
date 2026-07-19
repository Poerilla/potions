"""EURUSD v2b gated by hourly SuperTrend trailing-stop sweep.

Rule
----
1. Compute hourly ATR SuperTrend (14×3), available at **hour complete**
   (left-labeled hour H known at H+1h).
2. On each NY calendar day, find the **first** 1m bar that takes the resting
   trail:
   - Bullish ST (trend=+1, trail below) taken when ``low <= ST`` → **Long** day
   - Bearish ST (trend=-1, trail above) taken when ``high >= ST`` → **Short** day
3. If no take by RTH end → **no trade** that day.
4. Dedicated direction only (no reverse leg). Arm OR-boundary v2b stops only
   after ``max(take_ts, 09:45 NY)`` so a pre-OR take arms at 09:45 exactly,
   and a later take delays arming until that bar.

Sizing knobs match tracker notation ``tp1/tp2/runner`` with
``entry = tp1+tp2+runner``.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .bars import rth_bars
from .broker import DEFAULT_TICK_SIZE
from .build_ym_1m_atr_supertrend_sample import compute_supertrend
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
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, resample_hourly


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
DEFAULT_START = date(2003, 6, 2)
OR_END = time(9, 45)
EOD = time(15, 55)
ATR_LEN = 14
ATR_MULT = 3.0


def build_hourly_st(one_m: pd.DataFrame) -> pd.DataFrame:
    hourly = resample_hourly(one_m)
    st = compute_supertrend(hourly, atr_len=ATR_LEN, multiplier=ATR_MULT)
    st = st.dropna(subset=["supertrend"]).copy()
    st["available_at"] = st.index + pd.Timedelta(hours=1)
    return st[["open", "high", "low", "close", "supertrend", "supertrend_trend", "available_at"]]


def detect_session_st_takes(
    one_m: pd.DataFrame,
    hourly_st: pd.DataFrame,
    sessions: List[date],
) -> Tuple[Dict[str, str], Dict[str, str], List[dict]]:
    """Return bias map, arm_after map, and audit rows for first ST take per day."""
    if hourly_st.empty or one_m.empty:
        return {}, {}, []

    session_set = set(sessions)
    events = (
        hourly_st.reset_index(drop=True)[["available_at", "supertrend", "supertrend_trend"]]
        .rename(columns={"available_at": "ts"})
        .sort_values("ts")
    )
    bars = one_m.copy()
    bars = bars.assign(ts=bars.index).reset_index(drop=True)
    bars["ts"] = pd.to_datetime(bars["ts"])
    events["ts"] = pd.to_datetime(events["ts"])
    if getattr(bars["ts"].dt, "tz", None) is None:
        bars["ts"] = bars["ts"].dt.tz_localize(NY)
    else:
        bars["ts"] = bars["ts"].dt.tz_convert(NY)
    if getattr(events["ts"].dt, "tz", None) is None:
        events["ts"] = events["ts"].dt.tz_localize(NY)
    else:
        events["ts"] = events["ts"].dt.tz_convert(NY)
    bars = bars.sort_values("ts")
    events = events.sort_values("ts")
    merged = pd.merge_asof(
        bars,
        events,
        on="ts",
        direction="backward",
    )
    merged = merged[merged["supertrend"].notna()].copy()
    if merged.empty:
        return {}, {}, []

    bull_take = (merged["supertrend_trend"] == 1) & (merged["low"] <= merged["supertrend"])
    bear_take = (merged["supertrend_trend"] == -1) & (merged["high"] >= merged["supertrend"])
    merged["take_side"] = np.where(bull_take, "Long", np.where(bear_take, "Short", ""))
    merged["session"] = merged["ts"].dt.tz_convert(NY).dt.date
    # Restrict to requested sessions and before EOD cutoff.
    eod_ok = merged["ts"].dt.tz_convert(NY).dt.time <= EOD
    hits = merged[(merged["take_side"] != "") & eod_ok & merged["session"].isin(session_set)]
    if hits.empty:
        return {}, {}, []
    first = hits.groupby("session", sort=True).head(1)

    bias: Dict[str, str] = {}
    arm_after: Dict[str, str] = {}
    rows: List[dict] = []
    first_by_session = {row.session: row for row in first.itertuples(index=False)}
    for session in sessions:
        session_s = session.isoformat()
        row = first_by_session.get(session)
        if row is None:
            rows.append(
                {
                    "session": session_s,
                    "trade_bias": "none",
                    "take_ts": "",
                    "arm_after_ts": "",
                    "st_level": "",
                    "st_trend": "",
                }
            )
            continue
        take_ts = pd.Timestamp(row.ts)
        take_side = str(row.take_side)
        or_end_ts = pd.Timestamp(datetime.combine(session, OR_END), tz=NY)
        arm_ts = take_ts if take_ts >= or_end_ts else or_end_ts
        bias[session_s] = take_side
        arm_after[session_s] = arm_ts.isoformat()
        rows.append(
            {
                "session": session_s,
                "trade_bias": take_side,
                "take_ts": take_ts.isoformat(),
                "arm_after_ts": arm_ts.isoformat(),
                "st_level": round(float(row.supertrend), 8),
                "st_trend": int(row.supertrend_trend),
            }
        )
    return bias, arm_after, rows


def run(
    *,
    output_root: Path,
    start: date,
    force: bool,
    entry_qty: int,
    tp1_qty: int,
    tp2_qty: int,
    max_days: Optional[int] = None,
) -> dict:
    POINT_VALUES.setdefault(INSTRUMENT, 100000.0)
    DEFAULT_TICK_SIZE.setdefault(INSTRUMENT, TICK)
    one_m_path, daily = ensure_eurusd_platform_files(REPO, force=False)
    runner = max(0, entry_qty - tp1_qty - tp2_qty)
    sizing_label = "%d_%d_%d" % (tp1_qty, tp2_qty, runner)
    # Prefer human "1/0/0" style when flat single lot (tp1=tp2=0, entry=1).
    if entry_qty == 1 and tp1_qty == 0 and tp2_qty == 0:
        sizing_label = "1_0_0"
    strategy_id = "eurusd_v2b_hourly_st_sweep_S_%s" % sizing_label
    state_root = output_root / "states" / strategy_id
    if force and state_root.exists():
        shutil.rmtree(state_root)
    if force and (output_root / "summary.csv").exists():
        # Keep output_root but clear prior summary artifacts for this sizing run.
        pass
    output_root.mkdir(parents=True, exist_ok=True)

    cfg = MarketConfig(
        market=MARKET,
        instrument=INSTRUMENT,
        daily_path=daily,
        dbn_path=one_m_path,
        start=start,
        fee_per_unit=FEE_PER_UNIT,
    )
    print("Loading EURUSD 1m for hourly-ST-sweep v2b %s..." % strategy_id, flush=True)
    gby = load_fx_1m_by_ny_date(one_m_path, INSTRUMENT)
    one_m = concat_all_1m(gby).sort_index()
    print("Computing hourly ATR SuperTrend %d×%g (hour-complete)..." % (ATR_LEN, ATR_MULT), flush=True)
    hourly_st = build_hourly_st(one_m)

    regime_dates = _regime_dates(cfg, gby, start=start)
    regime_dates = [d for d in regime_dates if _has_full_rth_close(gby.get(d), d)]
    if max_days is not None:
        # Detect takes on a slightly wider window then truncate eligible.
        detect_sessions = regime_dates[: max(max_days * 3, max_days)]
    else:
        detect_sessions = regime_dates

    bias_map, arm_after_map, take_rows = detect_session_st_takes(one_m, hourly_st, detect_sessions)
    eligible = [d for d in regime_dates if d.isoformat() in bias_map]
    if max_days is not None:
        eligible = eligible[:max_days]
    long_n = sum(1 for d in eligible if bias_map[d.isoformat()] == "Long")
    short_n = sum(1 for d in eligible if bias_map[d.isoformat()] == "Short")
    print(
        "  eligible trade sessions: %d (Long=%d Short=%d)  scanned=%d"
        % (len(eligible), long_n, short_n, len(detect_sessions)),
        flush=True,
    )

    pd.DataFrame(take_rows).to_csv(output_root / "st_sweep_by_session.csv", index=False)

    session_bias = {d.isoformat(): bias_map[d.isoformat()] for d in eligible}
    session_arm_after = {d.isoformat(): arm_after_map[d.isoformat()] for d in eligible}
    payload = {
        "market": MARKET,
        "mode": "oco_then_reverse",
        "entry_qty": entry_qty,
        "tp1_qty": tp1_qty,
        "tp2_qty": tp2_qty,
        "tick_size": TICK,
        "use_regime_filter": True,
        "prior_opposite_only": False,
        "use_session_direction_bias": True,
        "session_direction_bias": session_bias,
        "session_arm_after_ts": session_arm_after,
        "regime_dates": [d.isoformat() for d in eligible],
        "start": start.isoformat(),
        "st_atr_len": ATR_LEN,
        "st_atr_mult": ATR_MULT,
        "st_availability": "hour_complete",
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
                    max_contracts=entry_qty,
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
                source=str(one_m_path),
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
    sizing = sizing_label if entry_qty == 1 and tp1_qty == 0 and tp2_qty == 0 else "S_%d_%d_%d" % (tp1_qty, tp2_qty, runner)
    if not sizing.startswith("S_") and "_" in sizing:
        sizing = "S_%s" % sizing
    result = {
        "strategy_id": strategy_id,
        "sizing": sizing,
        "entry_qty": entry_qty,
        "tp1_qty": tp1_qty,
        "tp2_qty": tp2_qty,
        "runner_qty": runner,
        "eligible_sessions": len(eligible),
        "long_sessions": long_n if max_days is None else sum(1 for d in eligible if bias_map[d.isoformat()] == "Long"),
        "short_sessions": short_n if max_days is None else sum(1 for d in eligible if bias_map[d.isoformat()] == "Short"),
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
    result["output_slug"] = output_root.name
    pd.DataFrame([result]).to_csv(output_root / "summary.csv", index=False)

    lines = [
        "# EURUSD hourly-ST-sweep → v2b %s" % sizing,
        "",
        "First **hour-complete** hourly ATR SuperTrend (14×3) trail take of the NY day sets the "
        "dedicated OR direction; v2b arms only after ``max(take, 09:45)``.",
        "",
        "- Bullish ST taken (`low ≤ ST`) → **Long** OR break",
        "- Bearish ST taken (`high ≥ ST`) → **Short** OR break",
        "- No take → no trade",
        "- No reverse leg against the session direction",
        "",
        "| Sizing | Eligible days | Trades | Units | Net | Closed DD | Stress DD | Net/Stress | Win% | PF |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        "| %s | %d | %d | %d | $%.2f | $%.2f | $%.2f | %.2f | %.1f | %.3f |"
        % (
            sizing,
            result["eligible_sessions"],
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
        "- Entry / TP1 / TP2 / runner: **%d / %d / %d / %d**" % (entry_qty, tp1_qty, tp2_qty, runner),
        "- Long / Short eligible days: **%d / %d**" % (result["long_sessions"], result["short_sessions"]),
        "- Take ledger: [`st_sweep_by_session.csv`](st_sweep_by_session.csv)",
        "",
    ]
    (output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_run_manifest(
        output_root,
        data_inputs=[one_m_path, daily],
        output_paths=[
            output_root / "summary.csv",
            output_root / "INDEX.md",
            output_root / "st_sweep_by_session.csv",
            state_root / "fills.csv",
        ],
        strategy_config={
            k: v
            for k, v in payload.items()
            if k not in {"session_direction_bias", "session_arm_after_ts", "regime_dates"}
        },
        broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": FEE_PER_UNIT, "spread_model": "fx_half_pip"},
        causality_mode="audit",
        extra={
            "driver": "eurusd_v2b_hourly_st_sweep",
            "st_availability": "hour_complete",
            "sizing": sizing,
        },
    )
    return result


def write_compare(compare_root: Path, results: List[dict]) -> None:
    compare_root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(compare_root / "summary.csv", index=False)
    lines = [
        "# EURUSD hourly-ST-sweep → v2b sizing compare",
        "",
        "First hour-complete hourly ST trail take sets Long/Short; arm after max(take, 09:45).",
        "",
        "| Sizing | Eligible | Trades | Units | Net | Stress DD | Net/Stress | Win% | PF | Path |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in results:
        slug = str(r.get("output_slug") or r["strategy_id"])
        lines.append(
            "| %s | %d | %d | %d | $%.2f | $%.2f | %.2f | %.1f | %.3f | [`%s`](../%s/INDEX.md) |"
            % (
                r["sizing"],
                r["eligible_sessions"],
                r["trades"],
                r["units"],
                r["net_usd"],
                r["intrabar_stress_dd_usd"],
                r["net_over_stress"],
                r["win_rate"],
                r["profit_factor"],
                slug,
                slug,
            )
        )
    lines.append("")
    (compare_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="EURUSD v2b gated by hourly ST trail sweep.")
    parser.add_argument("--start", default=DEFAULT_START.isoformat())
    parser.add_argument("--max-days", type=int, default=None)
    parser.add_argument("--no-force", action="store_true")
    parser.add_argument(
        "--only",
        choices=("1_0_0", "1_1_1", "1_1_3", "all"),
        default="all",
        help="Which sizing to run (default all three).",
    )
    args = parser.parse_args(argv)
    start = date.fromisoformat(args.start)
    force = not args.no_force

    specs = [
        ("1_0_0", 1, 0, 0),
        ("1_1_1", 3, 1, 1),
        ("1_1_3", 5, 1, 1),
    ]
    if args.only != "all":
        specs = [s for s in specs if s[0] == args.only]

    results = []
    for label, entry, tp1, tp2 in specs:
        out = REPO / "live" / "state" / ("eurusd_v2b_hourly_st_sweep_%s" % label)
        print("=== Running %s (entry=%d tp1=%d tp2=%d) ===" % (label, entry, tp1, tp2), flush=True)
        result = run(
            output_root=out,
            start=start,
            force=force,
            entry_qty=entry,
            tp1_qty=tp1,
            tp2_qty=tp2,
            max_days=args.max_days,
        )
        results.append(result)
        print(
            "  Net=$%.2f Net/Stress=%.2f trades=%d"
            % (result["net_usd"], result["net_over_stress"], result["trades"]),
            flush=True,
        )

    if len(results) > 1:
        compare_root = REPO / "live" / "state" / "eurusd_v2b_hourly_st_sweep_compare"
        write_compare(compare_root, results)
        print("Wrote compare → %s" % (compare_root / "INDEX.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
