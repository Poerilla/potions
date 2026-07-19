"""EURUSD yearly-ORB bias → directional v2b S_1_1_3.

Rules:
- Jan–Mar defines the yearly opening range (YOR high/low).
- From Apr onward, each session uses the **prior daily close** vs YOR to set
  a yearly breakout bias.
- Default (follow): long YOR bias → long-only v2b; short → short-only.
- ``--invert-bias`` (fade): long YOR bias → short-only v2b; short → long-only.
- Inside YOR → no v2b. Jan–Mar sessions are flat (range still forming).
- v2b is tracker base S_1_1_3 (entry 5 = TP1 1 / TP2 1 / runner 3) with
  no reverse leg against the session trade side.
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
from .eurusd_overnight_sweep import FEE_PER_UNIT, INSTRUMENT, MARKET, TICK, _fx_spread, _has_full_rth_close
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
# Start early enough for a full Jan–Mar OR in 2004 (data begins mid-2003).
DEFAULT_START = date(2004, 1, 2)


def compute_yearly_orb_bias(
    daily: pd.DataFrame,
    *,
    invert: bool = False,
) -> Tuple[Dict[str, str], List[dict]]:
    """Map session ISO date → ``Long`` / ``Short`` from prior close vs YOR.

    Only Apr–Dec sessions after a completed Jan–Mar range are candidates.
    With ``invert=True``, trade against the yearly breakout (fade).
    """
    work = daily.copy()
    if "date" not in work.columns:
        # Platform daily may use ts/index — normalise.
        if isinstance(work.index, pd.DatetimeIndex):
            work = work.reset_index()
            work.rename(columns={work.columns[0]: "date"}, inplace=True)
        else:
            raise ValueError("daily frame needs a date column")
    work["date"] = pd.to_datetime(work["date"])
    work = work.sort_values("date").reset_index(drop=True)
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
        # Prior close starts as last OR close so Apr-1 can use Mar close.
        prior_close = float(or_bars.iloc[-1]["close"])
        trade_bars = g[g["month"] >= 4]
        for _, bar in trade_bars.iterrows():
            session = pd.Timestamp(bar["date"]).date().isoformat()
            side = ""
            if prior_close > yor_high:
                side = "Long"
            elif prior_close < yor_low:
                side = "Short"
            trade_side = side
            if side and invert:
                trade_side = "Short" if side == "Long" else "Long"
            if trade_side:
                bias[session] = trade_side
            rows.append(
                {
                    "session": session,
                    "year": int(year),
                    "prior_close": round(prior_close, 8),
                    "yor_high": round(yor_high, 8),
                    "yor_low": round(yor_low, 8),
                    "yor_bias": side or "none",
                    "trade_bias": trade_side or "none",
                }
            )
            prior_close = float(bar["close"])
    return bias, rows


def _load_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "date" in df.columns:
        return df
    if "ts" in df.columns:
        out = df.rename(columns={"ts": "date"})
        out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None)
        out["date"] = out["date"].dt.normalize()
        return out
    raise ValueError("Unsupported daily CSV columns in %s" % path)


def run(
    *,
    output_root: Path,
    start: date,
    force: bool,
    invert: bool = False,
    max_days: Optional[int] = None,
) -> dict:
    POINT_VALUES.setdefault(INSTRUMENT, 100000.0)
    DEFAULT_TICK_SIZE.setdefault(INSTRUMENT, TICK)
    one_m, daily_path = ensure_eurusd_platform_files(REPO, force=False)
    output_root.mkdir(parents=True, exist_ok=True)
    strategy_id = "eurusd_v2b_yearly_orb_%s_S_1_1_3" % ("fade" if invert else "bias")
    state_root = output_root / "states" / strategy_id
    if force and state_root.exists():
        shutil.rmtree(state_root)

    daily = _load_daily(daily_path)
    daily = daily[pd.to_datetime(daily["date"]).dt.date >= start].copy()
    bias_map, bias_rows = compute_yearly_orb_bias(daily, invert=invert)
    bias_csv = output_root / "yearly_orb_bias_by_session.csv"
    with bias_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["session", "year", "prior_close", "yor_high", "yor_low", "yor_bias", "trade_bias"],
        )
        writer.writeheader()
        writer.writerows(bias_rows)

    print(
        "Loading EURUSD 1m for yearly-ORB %s v2b..." % ("fade" if invert else "bias"),
        flush=True,
    )
    gby = load_fx_1m_by_ny_date(one_m, INSTRUMENT)
    # Eligible = sessions with Long/Short bias and a full RTH 1m grid.
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
        "  trade sessions: %d (Long=%d Short=%d)  mapped rows=%d invert=%s"
        % (len(eligible), long_days, short_days, len(bias_rows), invert),
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
        "invert_yearly_orb_bias": invert,
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
        "sizing": "S_1_1_3",
        "invert": invert,
        "bias_long_days": long_days,
        "bias_short_days": short_days,
        "sessions": len(eligible),
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
    title = "fade (trade against YOR breakout)" if invert else "follow (trade with YOR breakout)"
    lines = [
        "# EURUSD Yearly-ORB %s → v2b S_1_1_3" % ("fade" if invert else "bias"),
        "",
        "Prior daily close vs Jan–Mar yearly ORB sets the YOR bias. Mode: **%s**." % title,
        "Inside range → flat. No reverse leg against the session trade side.",
        "",
        "| Sizing | Sessions (L/S trade) | Trades | Units | Net | Closed DD | Stress DD | Net/Stress | Win% | PF |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        "| %s | %d (%d/%d) | %d | %d | $%.2f | $%.2f | $%.2f | %.2f | %.1f | %.3f |"
        % (
            result["sizing"],
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
        "- Invert YOR bias: **%s**" % invert,
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
            "driver": "eurusd_yearly_orb_bias_v2b",
            "entry_qty": 5,
            "tp1_qty": 1,
            "tp2_qty": 1,
            "use_session_direction_bias": True,
            "invert_yearly_orb_bias": invert,
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
            "invert": invert,
        },
    )
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Defaults to fade or bias state root based on --invert-bias.",
    )
    parser.add_argument("--start", default=DEFAULT_START.isoformat())
    parser.add_argument("--max-days", type=int, default=None)
    parser.add_argument(
        "--invert-bias",
        action="store_true",
        help="Fade YOR breakout: long YOR bias → short-only v2b, and vice versa.",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    if args.output_root is None:
        slug = "eurusd_v2b_yearly_orb_fade_S_1_1_3" if args.invert_bias else "eurusd_v2b_yearly_orb_bias_S_1_1_3"
        args.output_root = REPO / "live" / "state" / slug
    result = run(
        output_root=args.output_root,
        start=date.fromisoformat(args.start),
        force=args.force,
        invert=args.invert_bias,
        max_days=args.max_days,
    )
    print(
        "DONE Net=$%.2f Net/Stress=%.2f trades=%d sessions=%d invert=%s"
        % (result["net_usd"], result["net_over_stress"], result["trades"], result["sessions"], result["invert"]),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
