"""EURUSD inside-YOR + daily ATR Supertrend → directional v2b S_1_1_3.

Rules:
- Jan–Mar defines the yearly opening range (YOR).
- Apr–Dec only: trade when **prior daily close is inside** the YOR
  (``yor_low < prior_close < yor_high``). Breakouts → flat.
- Bias from the **prior completed** daily ATR Supertrend (default 14×3):
  - ``aligned``: ST bullish → long-only v2b; bearish → short-only
  - ``opposed``: ST bullish → short-only v2b; bearish → long-only
- v2b tracker base S_1_1_3 (entry 5 = TP1 1 / TP2 1 / runner 3); no reverse
  leg against the session trade side.
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
from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .engine import Engine
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


def compute_inside_yor_st_bias(
    daily: pd.DataFrame,
    *,
    mode: str,
    atr_len: int = 14,
    atr_mult: float = 3.0,
) -> Tuple[Dict[str, str], List[dict]]:
    """Map session → Long/Short when inside YOR and daily ST bias applies.

    ``mode`` is ``aligned`` or ``opposed``. Supertrend is causal: session D uses
    the ST state as of the prior completed daily bar.
    """
    if mode not in {"aligned", "opposed"}:
        raise ValueError("mode must be aligned or opposed")

    work = daily.copy()
    work["date"] = pd.to_datetime(work["date"])
    work = work.sort_values("date").reset_index(drop=True)
    st = compute_supertrend(
        work.set_index("date")[["open", "high", "low", "close", "volume"]],
        atr_len=atr_len,
        multiplier=atr_mult,
    )
    # Prior completed ST for the next session.
    prior_trend = st["supertrend_trend"].shift(1)
    work = work.join(prior_trend.rename("prior_st_trend"), on="date")
    work["year"] = work["date"].dt.year
    work["month"] = work["date"].dt.month

    bias: Dict[str, str] = {}
    rows: List[dict] = []
    for year, group in work.groupby("year", sort=True):
        g = group.reset_index(drop=True)
        or_bars = g[g["month"] <= 3]
        if or_bars.empty:
            continue
        yor_high = float(or_bars["high"].max())
        yor_low = float(or_bars["low"].min())
        if yor_high <= yor_low:
            continue
        prior_close = float(or_bars.iloc[-1]["close"])
        # ST available after the last OR bar for Apr-1.
        for _, bar in g[g["month"] >= 4].iterrows():
            session = pd.Timestamp(bar["date"]).date().isoformat()
            inside = yor_low < prior_close < yor_high
            st_trend = bar.get("prior_st_trend")
            st_side = ""
            if pd.notna(st_trend):
                st_side = "Long" if int(st_trend) == 1 else "Short" if int(st_trend) == -1 else ""
            trade_side = ""
            if inside and st_side:
                if mode == "aligned":
                    trade_side = st_side
                else:
                    trade_side = "Short" if st_side == "Long" else "Long"
            if trade_side:
                bias[session] = trade_side
            rows.append(
                {
                    "session": session,
                    "year": int(year),
                    "prior_close": round(prior_close, 8),
                    "yor_high": round(yor_high, 8),
                    "yor_low": round(yor_low, 8),
                    "inside_yor": bool(inside),
                    "prior_st": st_side or "none",
                    "trade_bias": trade_side or "none",
                    "mode": mode,
                }
            )
            prior_close = float(bar["close"])
    return bias, rows


def run_variant(
    *,
    mode: str,
    output_root: Path,
    start: date,
    force: bool,
    atr_len: int,
    atr_mult: float,
    max_days: Optional[int] = None,
) -> dict:
    POINT_VALUES.setdefault(INSTRUMENT, 100000.0)
    DEFAULT_TICK_SIZE.setdefault(INSTRUMENT, TICK)
    one_m, daily_path = ensure_eurusd_platform_files(REPO, force=False)
    output_root.mkdir(parents=True, exist_ok=True)
    strategy_id = "eurusd_v2b_inside_yor_daily_st_%s_S_1_1_3" % mode
    state_root = output_root / "states" / strategy_id
    if force and state_root.exists():
        shutil.rmtree(state_root)

    daily = _load_daily(daily_path)
    daily = daily[pd.to_datetime(daily["date"]).dt.date >= start].copy()
    # Need history before start for ST warmup — reload full daily then filter bias.
    daily_full = _load_daily(daily_path)
    bias_map, bias_rows = compute_inside_yor_st_bias(
        daily_full,
        mode=mode,
        atr_len=atr_len,
        atr_mult=atr_mult,
    )
    bias_rows = [r for r in bias_rows if date.fromisoformat(r["session"]) >= start]
    bias_csv = output_root / "inside_yor_st_bias_by_session.csv"
    with bias_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "session",
                "year",
                "prior_close",
                "yor_high",
                "yor_low",
                "inside_yor",
                "prior_st",
                "trade_bias",
                "mode",
            ],
        )
        writer.writeheader()
        writer.writerows(bias_rows)

    print("Loading EURUSD 1m for inside-YOR daily-ST %s v2b..." % mode, flush=True)
    gby = load_fx_1m_by_ny_date(one_m, INSTRUMENT)
    eligible = sorted(
        d
        for d_s, side in bias_map.items()
        for d in [date.fromisoformat(d_s)]
        if d >= start and _has_full_rth_close(gby.get(d), d)
    )
    if max_days is not None:
        eligible = eligible[:max_days]
    long_days = sum(1 for d in eligible if bias_map[d.isoformat()] == "Long")
    short_days = sum(1 for d in eligible if bias_map[d.isoformat()] == "Short")
    print(
        "  %s sessions: %d (Long=%d Short=%d) atr=%d x %g"
        % (mode, len(eligible), long_days, short_days, atr_len, atr_mult),
        flush=True,
    )

    session_bias = {d.isoformat(): bias_map[d.isoformat()] for d in eligible}
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
        "regime_dates": [d.isoformat() for d in eligible],
        "start": start.isoformat(),
        "gate": "inside_yor_daily_st",
        "st_mode": mode,
        "atr_len": atr_len,
        "atr_mult": atr_mult,
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
        "atr": "%d x %g" % (atr_len, atr_mult),
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
        "# EURUSD inside-YOR + daily ST (%s) → v2b S_1_1_3" % mode,
        "",
        "Trade only while **prior close is inside** Jan–Mar YOR. Direction from prior daily "
        "ATR Supertrend **%s** (ATR %d × %g)." % (mode, atr_len, atr_mult),
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
            "driver": "eurusd_yor_inside_daily_st_v2b",
            "mode": mode,
            "atr_len": atr_len,
            "atr_mult": atr_mult,
            "entry_qty": 5,
            "tp1_qty": 1,
            "tp2_qty": 1,
            "start": start.isoformat(),
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
    parser.add_argument("--atr-len", type=int, default=14)
    parser.add_argument("--atr-mult", type=float, default=3.0)
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
        out = REPO / "live" / "state" / ("eurusd_v2b_inside_yor_daily_st_%s_S_1_1_3" % mode)
        result = run_variant(
            mode=mode,
            output_root=out,
            start=start,
            force=args.force,
            atr_len=args.atr_len,
            atr_mult=args.atr_mult,
            max_days=args.max_days,
        )
        results.append(result)
        print(
            "DONE %s Net=$%.2f Net/Stress=%.2f trades=%d sessions=%d"
            % (mode, result["net_usd"], result["net_over_stress"], result["trades"], result["sessions"]),
            flush=True,
        )

    # Combined comparison at parent-style root.
    compare_root = REPO / "live" / "state" / "eurusd_v2b_inside_yor_daily_st_compare"
    compare_root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(results).to_csv(compare_root / "summary.csv", index=False)
    lines = [
        "# EURUSD inside-YOR + daily ST → v2b compare",
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
