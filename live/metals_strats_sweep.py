"""XAUUSD / XAGUSD sweep of top tracked strategies ("the gambit").

Stages per metal:
- daily: REPLAY_SPECS (yearly ORB x2, monthly scaleout3 x2, ATR supertrend x3)
- fbo:   monthly ORB FBO 1/1/3 runner@2R BE@TP25 close-SL, base + atr80 filter
- stpmc: hourly ST+PMC pip variants (50/150, 40/120, 25/75, 25/75+MA bull,
         40/120 directional) — pip = 0.1 (gold) / 0.01 (silver)
- v2b:   v2b OCO prior-opposed S_1_1_3 on 1m (2015+)

Units: gold 100 oz/lot (PV=$100 per 1.0), silver 5,000 oz/lot (PV=$5,000 per
1.0). Fee $7/lot round-turn leg, 1-tick slippage. P&L in USD.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import traceback
from datetime import date
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd

from .bars import rth_bars
from .broker import DEFAULT_TICK_SIZE
from .broker_like_replays import BrokerReplaySpec, REPLAY_SPECS, _runtime_config
from .engine import Engine, bars_from_csv
from .fx_data import load_fx_1m_by_ny_date
from .hourly_st_pmc_loss_research import VariantConfig
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .replay_audit import POINT_VALUES, audit_units, read_bars, units_from_live_fills
from .reporting import generate_market_close_report
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import MarketConfig, _regime_dates
from .verification import QuietPaperVerificationProvider
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, resample_hourly

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "metals_strats_sweep"
FEE = 7.0

METALS = {
    "XAUUSD": dict(pip=0.1, tick=0.01, pv=100.0),
    "XAGUSD": dict(pip=0.01, tick=0.001, pv=5000.0),
}


def _progress(msg: str) -> None:
    print(msg, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def _ensure_meta(sym: str) -> None:
    POINT_VALUES[sym] = METALS[sym]["pv"]
    DEFAULT_TICK_SIZE[sym] = METALS[sym]["tick"]


def _load_rows() -> List[dict]:
    path = OUT / "summary.csv"
    if path.exists():
        return pd.read_csv(path).to_dict("records")
    return []


def _write(rows: List[dict]) -> None:
    if not rows:
        return
    keys: List[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with (OUT / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def _record(rows: List[dict], sym: str, family: str, name: str, sid: str, audit, wr_pct: float, trades: int) -> None:
    ns = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
    rows = rows  # in-place append by caller
    rows.append(
        dict(
            pair=sym,
            family=family,
            name=name,
            strategy_id=sid,
            status="ok",
            trades=trades,
            net_usd=round(audit.net_usd),
            stress_usd=round(audit.intrabar_mtm_dd_usd),
            ns=round(ns, 2),
            wr=round(wr_pct, 1),
        )
    )


def _campaign_wr(fills: pd.DataFrame, pv: float) -> tuple:
    fills = fills.copy()
    fills["ts"] = pd.to_datetime(fills["ts"])
    pnls = []
    for _, g in fills.groupby("trade_id"):
        g = g.sort_values("ts")
        e = g[g.reason == "entry"]
        if e.empty:
            continue
        entry = float(e.price.iloc[0])
        side = e.side.iloc[0]
        pnl = -FEE * float(e.quantity.sum())
        for _, r in g[g.reason != "entry"].iterrows():
            pts = (r.price - entry) * r.quantity if side == "buy" else (entry - r.price) * r.quantity
            pnl += pts * pv - FEE * float(r.quantity)
        pnls.append(pnl)
    a = np.array(pnls, float)
    return len(a), (100.0 * (a > 0).mean() if len(a) else 0.0)


def _run_daily_spec(sym: str, spec: BrokerReplaySpec, sid: str, bars, force: bool):
    meta = METALS[sym]
    root = OUT / "states" / sid
    if force and root.exists():
        shutil.rmtree(root)
    store = FlatFileStore(root, defer_table_writes=True)
    store.ensure()
    inst = StrategyInstance(
        strategy_id=sid,
        strategy_type=spec.strategy_type,
        version="v1",
        instrument=sym,
        broker_instrument=sym,
        account_mode="paper",
        enabled=True,
        timeframes="D",
        max_contracts=spec.max_contracts,
        max_open_orders=64,
        config_json=json.dumps(_runtime_config(spec, bars), sort_keys=True),
    )
    store.upsert_row("strategy_instances", "strategy_id", as_row(inst))
    Engine(store=store, slippage_ticks=1.0, tick_size={sym: meta["tick"]}).replay_bars(bars)
    store.flush_tables()
    generate_market_close_report(store, bars[-1].ts[:10])
    rb = read_bars(root / "bars" / ("%s_D.csv" % sym), "ts")
    units = units_from_live_fills(root / "fills.csv", sid, rb[-1].ts, rb[-1].close)
    audit = audit_units(
        name="%s %s" % (sym, spec.name),
        slug=sid,
        source=root / "fills.csv",
        bar_source=root / "bars" / ("%s_D.csv" % sym),
        bars=rb,
        units=units,
        instrument=sym,
        notes=spec.notes,
        output_root=OUT / "audits",
        fee_per_unit=FEE,
    )
    return audit, root


def run_daily(sym: str, rows: List[dict], force: bool) -> None:
    _ensure_meta(sym)
    daily_path = REPO / "fx" / ("%s_daily.csv" % sym.lower())
    bars = bars_from_csv(daily_path, sym, "D", source=str(daily_path))
    _progress("%s daily bars: %d" % (sym, len(bars)))
    for spec in REPLAY_SPECS:
        sid = "%s_%s" % (sym.lower(), spec.slug)
        family = "yearly_orb" if "yearly" in spec.slug else ("atr_st" if "atr" in spec.slug else "monthly_orb")
        _progress("START daily %s" % sid)
        try:
            audit, root = _run_daily_spec(sym, spec, sid, bars, force)
            n, wr = _campaign_wr(pd.read_csv(root / "fills.csv"), METALS[sym]["pv"])
            _record(rows, sym, family, spec.name, sid, audit, wr, n)
            _progress("DONE %s Net=$%d N/S=%.2f" % (sid, audit.net_usd, rows[-1]["ns"]))
        except Exception as exc:
            _progress("FAIL %s: %s" % (sid, exc))
            rows.append(dict(pair=sym, family=family, name=spec.name, strategy_id=sid, status="error", error=str(exc)))
        _write(rows)


def _atr80_csv(sym: str) -> Path:
    path = OUT / "filters" / ("%s_atr80.csv" % sym.lower())
    path.parent.mkdir(parents=True, exist_ok=True)
    d = pd.read_csv(REPO / "fx" / ("%s_daily.csv" % sym.lower()), parse_dates=["date"]).sort_values("date")
    tr = np.maximum(d.high - d.low, np.maximum((d.high - d.close.shift()).abs(), (d.low - d.close.shift()).abs()))
    d["atr14"] = tr.rolling(14).mean()
    d["pctl"] = d.atr14.rolling(500, min_periods=100).rank(pct=True)
    recs = [
        dict(
            date=r.date.date().isoformat(),
            long_ok=(True if r.pctl != r.pctl else bool(r.pctl <= 0.80)),
            short_ok=(True if r.pctl != r.pctl else bool(r.pctl <= 0.80)),
        )
        for _, r in d.iterrows()
    ]
    pd.DataFrame(recs).to_csv(path, index=False)
    return path


def run_fbo(sym: str, rows: List[dict], force: bool) -> None:
    _ensure_meta(sym)
    daily_path = REPO / "fx" / ("%s_daily.csv" % sym.lower())
    bars = bars_from_csv(daily_path, sym, "D", source=str(daily_path))
    filt = _atr80_csv(sym)
    for flabel, fcsv in [("base", None), ("atr80", str(filt))]:
        cfg = {
            "allow_shorts": True,
            "or_sessions": 3,
            "max_trades_per_month": 2,
            "entry_qty": 5,
            "tp1_qty": 1,
            "tp2_qty": 1,
            "tp1_r": 0.25,
            "tp2_r": 1.0,
            "runner_r": 2.0,
            "be_after": "tp1",
            "entry_mode": "first_break_opposite",
            "stop_mode": "close",
            "flip_after_stop": False,
            "eod_stop_to_or_mid": False,
            "record_levels": False,
        }
        if fcsv:
            cfg["entry_filter_csv"] = fcsv
        spec = BrokerReplaySpec(
            name="Monthly ORB FBO 1/1/3 %s" % flabel,
            slug="fbo_113_%s" % flabel,
            strategy_type="monthly_orb_v2b_oco",
            max_contracts=5,
            config=cfg,
            notes="FBO 1/1/3 runner@2R BE@TP25 close-SL %s" % flabel,
        )
        sid = "%s_%s" % (sym.lower(), spec.slug)
        _progress("START fbo %s" % sid)
        try:
            audit, root = _run_daily_spec(sym, spec, sid, bars, force)
            n, wr = _campaign_wr(pd.read_csv(root / "fills.csv"), METALS[sym]["pv"])
            _record(rows, sym, "monthly_fbo", spec.name, sid, audit, wr, n)
            _progress("DONE %s Net=$%d N/S=%.2f" % (sid, audit.net_usd, rows[-1]["ns"]))
        except Exception as exc:
            _progress("FAIL %s: %s\n%s" % (sid, exc, traceback.format_exc()))
            rows.append(dict(pair=sym, family="monthly_fbo", name=spec.name, strategy_id=sid, status="error", error=str(exc)))
        _write(rows)


def _hourly_bars(sym: str) -> List[Bar]:
    one_m = REPO / "fx" / ("%s_1m.csv" % sym.lower())
    gby = load_fx_1m_by_ny_date(one_m, sym)
    hourly = resample_hourly(concat_all_1m(gby))
    return [
        Bar(
            instrument=sym,
            timeframe="1h",
            ts=ts.isoformat(),
            open=float(r["open"]),
            high=float(r["high"]),
            low=float(r["low"]),
            close=float(r["close"]),
            volume=float(r.get("volume", 0.0)),
            complete=True,
            source=str(one_m),
        )
        for ts, r in hourly.iterrows()
    ]


def run_stpmc(sym: str, rows: List[dict], force: bool) -> None:
    from . import hourly_st_pmc_strategyplugin_variants as hsv

    _ensure_meta(sym)
    meta = METALS[sym]
    hsv.TICK_SIZE[sym] = meta["tick"]
    pip = meta["pip"]
    variants = [
        VariantConfig("base_1x_50sl_150tp", stop_pts=50 * pip, tp1_pts=150 * pip, notes="50/150 pip base."),
        VariantConfig("sl40_tp120_3r", stop_pts=40 * pip, tp1_pts=120 * pip, notes="40/120 3R."),
        VariantConfig("sl25_tp75_3r", stop_pts=25 * pip, tp1_pts=75 * pip, notes="25/75 3R."),
        VariantConfig(
            "sl25_tp75_3r_ma_bull_prior",
            stop_pts=25 * pip,
            tp1_pts=75 * pip,
            ma_filter="bull_prior_only",
            notes="25/75 + prior MA50>MA150 gate.",
        ),
        VariantConfig(
            "sl40_tp120_3r_ma_directional_prior",
            stop_pts=40 * pip,
            tp1_pts=120 * pip,
            ma_filter="directional_prior",
            notes="40/120 directional prior.",
        ),
    ]
    bars = _hourly_bars(sym)
    _progress("%s hourly bars: %d" % (sym, len(bars)))
    for cfg in variants:
        sid = "%s_hourly_st_pmc_%s" % (sym.lower(), cfg.name)
        _progress("START stpmc %s" % sid)
        try:
            result = hsv.run_variant(
                cfg=cfg,
                bars=bars,
                output_root=OUT / "st_pmc" / sym.lower(),
                dbn=REPO / "fx" / ("%s_1m.csv" % sym.lower()),
                daily_path=REPO / "fx" / ("%s_daily.csv" % sym.lower()),
                instrument=sym,
                market=sym.lower(),
                force=force,
                quiet=True,
            )
            audit = result.audit
            wr = 100.0 * audit.win_units / audit.units if audit.units else 0.0
            _record(rows, sym, "hourly_st_pmc", "ST+PMC %s" % cfg.name, sid, audit, wr, audit.trades)
            _progress("DONE %s Net=$%d N/S=%.2f" % (sid, audit.net_usd, rows[-1]["ns"]))
        except Exception as exc:
            _progress("FAIL %s: %s\n%s" % (sid, exc, traceback.format_exc()))
            rows.append(dict(pair=sym, family="hourly_st_pmc", name="ST+PMC %s" % cfg.name, strategy_id=sid, status="error", error=str(exc)))
        _write(rows)


def _has_full_rth_close(raw_day: Optional[pd.DataFrame], session: date) -> bool:
    rth = rth_bars(raw_day, session, dense=True)
    if rth.empty:
        return False
    return bool((rth.index.time >= pd.Timestamp("15:55").time()).any())


def run_v2b(sym: str, rows: List[dict], force: bool, start: date) -> None:
    from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills

    _ensure_meta(sym)
    meta = METALS[sym]
    one_m = REPO / "fx" / ("%s_1m.csv" % sym.lower())
    daily_path = REPO / "fx" / ("%s_daily.csv" % sym.lower())
    cfg = MarketConfig(
        market=sym.lower(),
        instrument=sym,
        daily_path=daily_path,
        dbn_path=one_m,
        start=start,
        fee_per_unit=FEE,
    )
    _progress("%s loading 1m for v2b..." % sym)
    gby = load_fx_1m_by_ny_date(one_m, sym)
    regime = _regime_dates(cfg, gby, start=start)
    regime = [d for d in regime if _has_full_rth_close(gby.get(d), d)]
    _progress("%s v2b sessions: %d" % (sym, len(regime)))
    sid = "%s_v2b_oco_prior_opposed_S_1_1_3" % sym.lower()
    _progress("START v2b %s" % sid)
    try:
        root = OUT / "states" / sid
        if force and root.exists():
            shutil.rmtree(root)
        store = FlatFileStore(root, defer_table_writes=True)
        store.ensure()
        payload = {
            "market": sym.lower(),
            "tick_size": meta["tick"],
            "use_regime_filter": True,
            "start": start.isoformat(),
            "regime_dates": [d.isoformat() for d in regime],
            "record_levels": False,
            "mode": "oco_then_reverse",
            "entry_qty": 5,
            "tp1_qty": 1,
            "tp2_qty": 1,
            "prior_opposite_only": True,
        }
        inst = StrategyInstance(
            strategy_id=sid,
            strategy_type="v2b_scaleout",
            version="v1",
            instrument=sym,
            broker_instrument=sym,
            account_mode="paper",
            enabled=True,
            timeframes="1m",
            max_contracts=5,
            max_open_orders=64,
            config_json=json.dumps(payload, sort_keys=True),
        )
        store.write_table("strategy_instances", [as_row(inst)])
        engine = Engine(
            store=store,
            persist_bars=False,
            persist_health=False,
            slippage_ticks=1.0,
            tick_size={sym: meta["tick"]},
            notification_sink=NullNotificationSink(),
            verification_provider=QuietPaperVerificationProvider(),
            emit_order_alerts=False,
            broker_log_events=False,
            broker_persist_modifications=False,
        )
        for di, d in enumerate(regime, start=1):
            day = gby.get(d)
            if day is None or day.empty:
                continue
            for ts, r in day.iterrows():
                engine.process_bar(
                    Bar(
                        instrument=sym,
                        timeframe="1m",
                        ts=ts.isoformat(),
                        open=float(r["open"]),
                        high=float(r["high"]),
                        low=float(r["low"]),
                        close=float(r["close"]),
                        volume=float(r.get("volume", 0.0)),
                        complete=True,
                        source=str(one_m),
                    )
                )
            if di % 200 == 0:
                _progress("  %s v2b day %d/%d" % (sym, di, len(regime)))
        if hasattr(engine.broker, "flush_state"):
            engine.broker.flush_state()
        store.flush_tables()
        units = units_from_v2b_fills(root / "fills.csv", sid)
        audit_bars = [
            AuditBar(ts=ts.isoformat(), open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"]))
            for d in regime
            if gby.get(d) is not None
            for ts, r in gby[d].iterrows()
        ]
        audit = fast_intraday_audit(
            strategy_id=sid,
            state_root=root,
            bars=audit_bars,
            units=units,
            instrument=sym,
            fee_per_unit=FEE,
        )
        net = float(audit["net_usd"])
        stress = float(audit["intrabar_stress_dd_usd"])
        rows.append(
            dict(
                pair=sym,
                family="v2b_prior_opposed",
                name="v2b OCO prior-opposed S_1_1_3 (2015+)",
                strategy_id=sid,
                status="ok",
                trades=len(units),
                net_usd=round(net),
                stress_usd=round(stress),
                ns=round(net / abs(stress), 2) if stress else 0,
                wr=round(float(audit.get("win_rate") or 0.0), 1),
            )
        )
        _progress("DONE %s Net=$%d N/S=%.2f" % (sid, net, rows[-1]["ns"]))
    except Exception as exc:
        _progress("FAIL %s: %s\n%s" % (sid, exc, traceback.format_exc()))
        rows.append(dict(pair=sym, family="v2b_prior_opposed", name="v2b prior-opposed", strategy_id=sid, status="error", error=str(exc)))
    _write(rows)


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", choices=list(METALS) + ["all"], default="all")
    p.add_argument("--stage", choices=["daily", "fbo", "stpmc", "v2b", "all"], default="all")
    p.add_argument("--force", action="store_true")
    p.add_argument("--v2b-start", type=str, default="2015-01-02")
    args = p.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = _load_rows()
    syms = list(METALS) if args.symbol == "all" else [args.symbol]
    for sym in syms:
        if args.stage in ("daily", "all"):
            run_daily(sym, rows, args.force)
        if args.stage in ("fbo", "all"):
            run_fbo(sym, rows, args.force)
        if args.stage in ("stpmc", "all"):
            run_stpmc(sym, rows, args.force)
        if args.stage in ("v2b", "all"):
            y, m, d = (int(x) for x in args.v2b_start.split("-"))
            run_v2b(sym, rows, args.force, date(y, m, d))
    _write(rows)
    _progress("SWEEP DONE (%s / %s)" % (args.symbol, args.stage))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
