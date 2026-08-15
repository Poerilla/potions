"""Broker-like Engine+PaperBroker replay for structure_program_st.

Best research plan: split15 @ risk 12. Futures + top FX by research net/stress.

Usage:
  python -m live.structure_program_st_replay --markets nq mnq ym
  python -m live.structure_program_st_replay --markets nas100 us30 usdjpy_ny eurusd_ny
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from datetime import date, time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .bars import rth_bars
from .engine import Engine
from .fx_or_markets import FX_MARKETS, load_market_gby, session_bars
from .models import Bar, StrategyInstance, as_row
from .replay_audit import POINT_VALUES
from .replay_realism import hardened_replay_engine_kwargs
from .spread_model import SpreadModel
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any
from .v2b_strategy_replay import (
    AuditBar,
    DEFAULT_SLIPPAGE_TICKS,
    fast_intraday_audit,
    units_from_v2b_fills,
)

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "structure_program_st_broker"

FUT_TICK = {
    "nq": 0.25,
    "mnq": 0.25,
    "es": 0.25,
    "mes": 0.25,
    "ym": 1.0,
    "mym": 1.0,
}

# Research point values (FX_MARKETS) — prefer these over replay_audit defaults for FX CFDs
FX_POINT_VALUES = {
    "US30": 1.0,
    "NAS100": 1.0,
    "EURUSD": 100000.0,
    "USDJPY": 1000.0,  # USD per 1.0 price move (matches research batch)
    "XAUUSD": 1.0,
}


def _fx_risk_price(market_key: str, risk_pts: float) -> float:
    fx = FX_MARKETS[market_key]
    if fx.symbol in {"EURUSD", "GBPUSD", "USDJPY", "AUDJPY"} or fx.tick <= 0.0001:
        pip = 0.0001 if fx.tick <= 0.0001 else 0.01
        if fx.symbol == "USDJPY":
            pip = 0.01
        return float(risk_pts) * pip
    return float(risk_pts)


def _session_cfg(market: str) -> Dict[str, str]:
    if market in FX_MARKETS:
        clock = FX_MARKETS[market].clock
        eod = clock.eod
        return {
            "session_open": "%02d:%02d" % (clock.or_start.hour, clock.or_start.minute),
            "session_close": "%02d:%02d" % (clock.session_end.hour, clock.session_end.minute),
            "eod_time": "%02d:%02d" % (eod.hour, eod.minute),
        }
    return {"session_open": "09:30", "session_close": "16:00", "eod_time": "15:59"}


def _manual_net(units, instrument: str, fee_per_unit: float) -> Dict[str, float]:
    pv = float(FX_POINT_VALUES.get(instrument) or POINT_VALUES.get(instrument) or 20.0)
    nets = []
    for u in units:
        if u.entry_price != u.entry_price or u.exit_price != u.exit_price:
            continue
        nets.append(u.points * pv - fee_per_unit)
    if not nets:
        return {
            "net_usd": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "units": 0,
            "closed_dd_usd": 0.0,
        }
    import numpy as np

    arr = np.asarray(nets, dtype=float)
    eq = np.cumsum(arr)
    peak = np.maximum.accumulate(eq)
    dd = float((eq - peak).min())
    wins = float(arr[arr > 0].sum())
    losses = float(arr[arr <= 0].sum())
    pf = wins / abs(losses) if losses else float("inf")
    return {
        "net_usd": float(arr.sum()),
        "win_rate_pct": 100.0 * float((arr > 0).mean()),
        "profit_factor": float(pf) if math.isfinite(pf) else float("inf"),
        "units": int(len(arr)),
        "closed_dd_usd": dd,
    }


def run_futures_market(
    market: str,
    *,
    out_root: Path,
    plan: str,
    risk_pts: float,
    max_days: int = 0,
    start: Optional[date] = None,
    st_flip_mode: str = "adverse",
    st_flip_min_bars: int = 0,
    entry_mode: str = "touch",
    signal_source: str = "internal",
    external_signals_csv: str = "",
) -> Dict[str, object]:
    cfg = MARKETS[market]
    if not cfg.dbn_path.exists():
        print("SKIP %s: missing %s" % (market, cfg.dbn_path), flush=True)
        return {"market": market, "skipped": True, "reason": "missing_dbn"}

    print("Loading %s 1m…" % cfg.instrument, flush=True)
    gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    all_days = sorted(gby)
    if start:
        all_days = [d for d in all_days if d >= start]
    if max_days:
        all_days = all_days[:max_days]

    return _run_days(
        market=market,
        instrument=cfg.instrument,
        gby=gby,
        all_days=all_days,
        out_root=out_root,
        plan=plan,
        risk_pts=risk_pts,
        risk_price=float(risk_pts),
        tick_size=FUT_TICK.get(market, 0.25),
        fee_per_unit=float(cfg.fee_per_unit),
        session_cfg=_session_cfg(market),
        bar_fn=lambda day, df: rth_bars(df, day, dense=True),
        source=str(cfg.dbn_path),
        slippage_ticks=DEFAULT_SLIPPAGE_TICKS,
        spread_model=None,
        point_instrument=cfg.instrument,
        st_flip_mode=st_flip_mode,
        st_flip_min_bars=st_flip_min_bars,
        entry_mode=entry_mode,
        signal_source=signal_source,
        external_signals_csv=external_signals_csv,
    )


def run_fx_market(
    market: str,
    *,
    out_root: Path,
    plan: str,
    risk_pts: float,
    max_days: int = 0,
    start: Optional[date] = None,
    st_flip_mode: str = "adverse",
    st_flip_min_bars: int = 0,
    entry_mode: str = "touch",
    signal_source: str = "internal",
    external_signals_csv: str = "",
) -> Dict[str, object]:
    fx = FX_MARKETS[market]
    if not fx.path.exists():
        print("SKIP %s: missing %s" % (market, fx.path), flush=True)
        return {"market": market, "skipped": True, "reason": "missing_csv"}

    print("Loading FX %s…" % fx.symbol, flush=True)
    gby = load_market_gby(fx)
    all_days = sorted(gby)
    if start:
        all_days = [d for d in all_days if d >= start]
    if max_days:
        all_days = all_days[:max_days]

    rp = _fx_risk_price(market, risk_pts)
    fx_spread = SpreadModel(
        rth_half_spread_ticks=5.0 if fx.symbol in {"EURUSD", "USDJPY"} else 1.0,
        eth_half_spread_ticks=10.0 if fx.symbol in {"EURUSD", "USDJPY"} else 2.0,
        open_widen_half_spread_ticks=10.0 if fx.symbol in {"EURUSD", "USDJPY"} else 2.0,
        low_volume_threshold=1.0,
        low_volume_multiplier=1.5,
        tick_size=fx.tick,
    )
    return _run_days(
        market=market,
        instrument=fx.symbol,
        gby=gby,
        all_days=all_days,
        out_root=out_root,
        plan=plan,
        risk_pts=risk_pts,
        risk_price=rp,
        tick_size=fx.tick,
        fee_per_unit=float(fx.fee_per_unit),
        session_cfg=_session_cfg(market),
        bar_fn=lambda day, df: session_bars(df, day, fx.clock, dense=True),
        source=str(fx.path),
        slippage_ticks=1.0,
        spread_model=fx_spread,
        point_instrument=fx.symbol,
        st_flip_mode=st_flip_mode,
        st_flip_min_bars=st_flip_min_bars,
        entry_mode=entry_mode,
        signal_source=signal_source,
        external_signals_csv=external_signals_csv,
    )


def _run_days(
    *,
    market: str,
    instrument: str,
    gby: Dict,
    all_days: List[date],
    out_root: Path,
    plan: str,
    risk_pts: float,
    risk_price: float,
    tick_size: float,
    fee_per_unit: float,
    session_cfg: Dict[str, str],
    bar_fn,
    source: str,
    slippage_ticks: float,
    spread_model: Optional[SpreadModel],
    point_instrument: str,
    st_flip_mode: str = "adverse",
    st_flip_min_bars: int = 0,
    entry_mode: str = "touch",
    signal_source: str = "internal",
    external_signals_csv: str = "",
) -> Dict[str, object]:
    slug = "%s_%s_r%.0f" % (market, plan, risk_pts)
    if signal_source == "external":
        slug += "_ext"
    elif signal_source == "structure_only":
        slug += "_struct"
    if entry_mode and entry_mode != "touch":
        slug += "_%s" % entry_mode
    state_root = out_root / "states" / slug
    if state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()

    if plan == "scale4":
        entry_qty = 4
    else:
        entry_qty = 15
    config = {
        "plan": plan,
        "risk_pts": risk_price,  # absolute price distance (pips converted for FX pairs)
        "tick_size": tick_size,
        "entry_qty": entry_qty,
        "rth_only": True,
        "atr_len": 14,
        "atr_mult": 3.0,
        "st_flip_exit": st_flip_mode != "off",
        "st_flip_mode": st_flip_mode,
        "st_flip_min_bars": int(st_flip_min_bars),
        "entry_mode": entry_mode,
        "signal_source": signal_source,
        "external_signals_csv": external_signals_csv,
        **session_cfg,
    }
    if signal_source == "structure_only":
        # Resting structure limits may wait many sessions for a touch.
        config["pending_max_closes"] = 60
        config["entry_mode"] = "resting"
    if plan == "split15":
        config.update(
            {
                "scale_qty": 5,
                "eod_qty": 5,
                "runner_qty": 5,
                "runner_r": 6.0,
                "st_flip_after_scale": False,
                "eod_flatten": True,
            }
        )
    elif plan == "scale_run":
        # Absolute-pt ladder from structure_sl_scale_run research; fav ST→BE.
        config.update(
            {
                "scale_qty": 5,
                "scale2_qty": 5,
                "eod_qty": 0,
                "runner_qty": 5,
                "tp1_pts": 22.0,
                "tp2_pts": 50.0,
                "tp3_pts": 200.0,
                "runner_r": 0.0,
                "st_flip_after_scale": True,
                "st_flip_mode": "fav_be" if st_flip_mode == "adverse" else st_flip_mode,
                "eod_flatten": False,
            }
        )
        if st_flip_mode == "off":
            config["st_flip_exit"] = False
            config["st_flip_mode"] = "off"
        elif st_flip_mode in {"always", "adverse", "after_n", "adverse_after_n"}:
            # default scale_run behavior is fav_be; allow explicit overrides
            if st_flip_mode == "adverse":
                config["st_flip_mode"] = "fav_be"
            else:
                config["st_flip_mode"] = st_flip_mode
    elif plan == "touch_st_align":
        config.update(
            {
                "scale_qty": 5,
                "scale2_qty": 5,
                "eod_qty": 0,
                "runner_qty": 5,
                "tp1_pts": 25.0,
                "tp2_pts": 50.0,
                "tp3_pts": 200.0,
                "tight_sl_pts": 12.0,
                "runner_r": 0.0,
                "st_flip_after_scale": True,
                "st_flip_mode": "fav_be" if st_flip_mode in {"adverse", "fav_be"} else st_flip_mode,
                "eod_flatten": False,
                "pending_max_closes": 3,
                "fade_after_through_mins": 0,
            }
        )
        if st_flip_mode == "off":
            config["st_flip_exit"] = False
            config["st_flip_mode"] = "off"
    elif plan == "touch_st_align_fade20":
        config.update(
            {
                "scale_qty": 5,
                "scale2_qty": 5,
                "eod_qty": 0,
                "runner_qty": 5,
                "tp1_pts": 25.0,
                "tp2_pts": 50.0,
                "tp3_pts": 200.0,
                "tight_sl_pts": 12.0,
                "runner_r": 0.0,
                "st_flip_after_scale": True,
                "st_flip_mode": "fav_be" if st_flip_mode in {"adverse", "fav_be"} else st_flip_mode,
                "eod_flatten": False,
                "pending_max_closes": 3,
                "fade_after_through_mins": 20,
            }
        )
        if st_flip_mode == "off":
            config["st_flip_exit"] = False
            config["st_flip_mode"] = "off"
    elif plan == "vwap_scalein":
        config.update(
            {
                "slice_qty": 3,
                "n_slices": 5,
                "scale_qty": 5,
                "scale2_qty": 5,
                "eod_qty": 0,
                "runner_qty": 5,
                "tp1_pts": 25.0,
                "tp2_pts": 50.0,
                "tp3_pts": 200.0,
                "tight_sl_pts": 12.0,
                "st_flip_after_scale": True,
                "st_flip_mode": "fav_be" if st_flip_mode in {"adverse", "fav_be"} else st_flip_mode,
                "eod_flatten": True,
                "pending_max_closes": 60,
            }
        )
        if st_flip_mode == "off":
            config["st_flip_exit"] = False
            config["st_flip_mode"] = "off"
    else:
        config.update(
            {
                "scale_qty": 2,
                "eod_qty": 0,
                "runner_qty": 2,
                "runner_r": 3.0,
                "st_flip_after_scale": True,
                "eod_flatten": True,
            }
        )

    instance = StrategyInstance(
        strategy_id=slug,
        strategy_type="structure_program_st",
        version="v1",
        instrument=instrument,
        broker_instrument=instrument,
        account_mode="paper",
        enabled=True,
        timeframes="1m",
        max_contracts=entry_qty,
        max_open_orders=32,
        config_json=json.dumps(config, sort_keys=True),
    )
    store.write_table("strategy_instances", [as_row(instance)])
    engine_kwargs = hardened_replay_engine_kwargs(
        slippage_ticks=slippage_ticks, spread_model=spread_model
    )
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        tick_size={instrument: tick_size},
        **engine_kwargs,
    )
    audit_bars: List[AuditBar] = []

    for idx, day in enumerate(all_days, start=1):
        df = bar_fn(day, gby.get(day))
        if df is None or df.empty:
            continue
        for ts, row in df.iterrows():
            o = float(row["open"]) if pd.notna(row["open"]) else float("nan")
            h = float(row["high"]) if pd.notna(row["high"]) else float("nan")
            l = float(row["low"]) if pd.notna(row["low"]) else float("nan")
            c = float(row["close"]) if pd.notna(row["close"]) else float("nan")
            ts_s = pd.Timestamp(ts).isoformat()
            bar = Bar(
                instrument=instrument,
                timeframe="1m",
                ts=ts_s,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=float(row["volume"]) if "volume" in row and pd.notna(row["volume"]) else 0.0,
                complete=True,
                source=source,
            )
            engine.process_bar(bar)
            if o == o:
                audit_bars.append(AuditBar(ts_s, o, h, l, c))
        if idx % 250 == 0 or idx == len(all_days):
            print("  %s %d/%d" % (instrument, idx, len(all_days)), flush=True)

    store.flush_tables()
    fills_path = state_root / "fills.csv"
    units = units_from_v2b_fills(fills_path, slug) if fills_path.exists() else []
    # Prefer research-consistent point values for FX
    manual = _manual_net(units, point_instrument, fee_per_unit)
    try:
        audit = fast_intraday_audit(
            strategy_id=slug,
            state_root=state_root,
            bars=audit_bars,
            units=units,
            instrument=point_instrument if point_instrument in POINT_VALUES else "NQ",
            fee_per_unit=fee_per_unit,
        )
        stress = float(audit.get("intrabar_stress_dd_usd") or manual["closed_dd_usd"])
    except Exception:
        stress = manual["closed_dd_usd"]

    net = manual["net_usd"]
    pf = manual["profit_factor"]
    row = {
        "market": market,
        "instrument": instrument,
        "plan": plan,
        "risk_pts": risk_pts,
        "risk_price": risk_price,
        "slug": slug,
        "sessions": len(all_days),
        "trades": len({u.trade_id for u in units}),
        "units": manual["units"],
        "net_usd": round(net, 2),
        "closed_dd_usd": round(manual["closed_dd_usd"], 2),
        "intrabar_stress_dd_usd": round(stress, 2),
        "net_over_stress": round(net / abs(stress), 2) if stress else "",
        "win_rate_pct": round(manual["win_rate_pct"], 2),
        "profit_factor": round(pf, 3) if math.isfinite(pf) else "inf",
    }
    pd.DataFrame([row]).to_csv(out_root / ("%s_metrics.csv" % slug), index=False)
    print(
        "  %s trades=%s units=%s net=$%.0f PF=%s N/S=%s"
        % (slug, row["trades"], row["units"], row["net_usd"], row["profit_factor"], row["net_over_stress"]),
        flush=True,
    )
    return row


def run_market(market: str, **kwargs) -> Dict[str, object]:
    m = market.lower()
    if m in FX_MARKETS:
        return run_fx_market(m, **kwargs)
    if m in MARKETS:
        return run_futures_market(m, **kwargs)
    print("SKIP unknown market %s" % market, flush=True)
    return {"market": market, "skipped": True, "reason": "unknown"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--markets",
        nargs="+",
        default=["nq"],
        help="Futures keys (nq/mnq/ym) and/or FX keys (nas100/us30/usdjpy_ny/eurusd_ny/...)",
    )
    ap.add_argument(
        "--plan",
        default="split15",
        choices=["split15", "scale4", "scale_run", "touch_st_align", "touch_st_align_fade20", "vwap_scalein"],
    )
    ap.add_argument("--risk-pts", type=float, default=12.0)
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--max-days", type=int, default=0)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument(
        "--st-flip-mode",
        default="adverse",
        choices=["off", "always", "adverse", "after_n", "adverse_after_n", "fav_be"],
        help="For scale_run, default adverse maps to fav_be (fav→BE hold, adverse flatten).",
    )
    ap.add_argument("--st-flip-min-bars", type=int, default=0)
    ap.add_argument(
        "--entry-mode",
        default="touch",
        choices=["touch", "sweep_reclaim", "resting"],
        help="touch=research; sweep_reclaim=SL then reclaim; resting=submit limit on arm",
    )
    ap.add_argument(
        "--signal-source",
        default="internal",
        choices=["internal", "external", "structure_only"],
        help="structure_only=program+structure key resting (no ST break); external=CSV arms",
    )
    ap.add_argument(
        "--signals-csv",
        default="",
        help="CSV with signal_ts,side,limit_px,stop (analytic trades.csv works)",
    )
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    start = date.fromisoformat(args.start) if args.start else None
    rows = []
    for m in args.markets:
        rows.append(
            run_market(
                m.lower(),
                out_root=out,
                plan=args.plan,
                risk_pts=args.risk_pts,
                max_days=args.max_days,
                start=start,
                st_flip_mode=args.st_flip_mode,
                st_flip_min_bars=args.st_flip_min_bars,
                entry_mode=args.entry_mode,
                signal_source=args.signal_source,
                external_signals_csv=args.signals_csv,
            )
        )
    # merge with any prior summary rows for other markets
    summary_path = out / "summary.csv"
    df = pd.DataFrame(rows)
    if summary_path.exists():
        old = pd.read_csv(summary_path)
        keep = old[~old["market"].isin(df["market"])] if "market" in old.columns else old
        df = pd.concat([keep, df], ignore_index=True)
    df.to_csv(summary_path, index=False)
    try:
        body = df.to_markdown(index=False)
    except Exception:
        body = df.to_string(index=False)
    (out / "SUMMARY.md").write_text(
        "# Structure-program ST — broker-like replay\n\n"
        "Plan **%s** risk=%.0f via StrategyPlugin `structure_program_st` + Engine/PaperBroker.\n\n"
        "ST-flip mode: **%s** (min_bars=%d) · entry_mode: **%s** · signals: **%s**\n\n"
        "%s\n"
        % (
            args.plan,
            args.risk_pts,
            args.st_flip_mode,
            args.st_flip_min_bars,
            args.entry_mode,
            args.signal_source,
            body,
        )
    )
    print("→ %s" % (out / "SUMMARY.md"), flush=True)


if __name__ == "__main__":
    main()
