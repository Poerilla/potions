"""Metals (XAUUSD / XAGUSD) gambit: futures-style strats + FBO atr80.

Daily: REPLAY_SPECS (yearly ORB, monthly scaleout3, ATR ST).
Hourly: ST+PMC pip variants.
Monthly FBO: 1/1/3 base + atr80.

Contract sizing (USD P&L):
  XAUUSD: point_value=100 (100oz), tick=0.01, pip=$1 for ST variants
  XAGUSD: point_value=1000 (1000oz mini), tick=0.001, pip=$0.05
Fee $1.50/unit (futures-like).
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .broker_like_replays import BrokerReplaySpec, REPLAY_SPECS, _runtime_config
from .engine import Engine, bars_from_csv
from .fx_data import load_fx_1m_by_ny_date
from .hourly_st_pmc_loss_research import VariantConfig
from .models import Bar, StrategyInstance, as_row
from .replay_audit import POINT_VALUES, audit_units, read_bars, units_from_live_fills
from .reporting import generate_market_close_report
from .store import FlatFileStore
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, resample_hourly

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "metals_futures_strats_sweep"
FEE = 1.50

METALS: Dict[str, Dict[str, float]] = {
    "XAUUSD": dict(pv=100.0, tick=0.01, pip=1.0),
    "XAGUSD": dict(pv=1000.0, tick=0.001, pip=0.05),
}

FBO_STRUCTURES: List[Tuple[str, int, int, int]] = [("1_1_3", 5, 1, 1)]


def _progress(msg: str) -> None:
    print(msg, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


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


def _atr80_csv(sym: str) -> Path:
    path = OUT / "filters" / ("%s_atr80.csv" % sym.lower())
    path.parent.mkdir(parents=True, exist_ok=True)
    d = pd.read_csv(REPO / "fx" / ("%s_daily.csv" % sym.lower()), parse_dates=["date"])
    d = d.sort_values("date").reset_index(drop=True)
    tr = np.maximum(
        d.high - d.low,
        np.maximum((d.high - d.close.shift()).abs(), (d.low - d.close.shift()).abs()),
    )
    d["atr14"] = tr.rolling(14).mean()
    d["pctl"] = d.atr14.rolling(500, min_periods=100).rank(pct=True)
    rows = []
    for _, r in d.iterrows():
        ok = True if r.pctl != r.pctl else bool(r.pctl <= 0.80)
        rows.append(dict(date=r.date.date().isoformat(), long_ok=ok, short_ok=ok))
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def run_daily(sym: str, rows: List[dict], force: bool) -> None:
    meta = METALS[sym]
    POINT_VALUES[sym] = meta["pv"]
    DEFAULT_TICK_SIZE[sym] = meta["tick"]
    daily_path = REPO / "fx" / ("%s_daily.csv" % sym.lower())
    bars = bars_from_csv(daily_path, sym, "D", source=str(daily_path))
    market = sym.lower()
    for spec in REPLAY_SPECS:
        sid = "%s_%s" % (market, spec.slug)
        family = "yearly_orb" if "yearly" in spec.slug else ("atr_st" if "atr" in spec.slug else "monthly_orb")
        _progress("START daily %s" % sid)
        try:
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
            ns = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
            rows.append(
                dict(
                    pair=sym,
                    family=family,
                    name=spec.name,
                    strategy_id=sid,
                    status="ok",
                    units=audit.units,
                    trades=audit.trades,
                    net_usd=round(audit.net_usd),
                    stress_usd=round(audit.intrabar_mtm_dd_usd),
                    ns=round(ns, 2),
                    wr_units=round(100.0 * audit.win_units / audit.units if audit.units else 0.0, 1),
                )
            )
            _progress("DONE %s Net=$%d N/S=%.2f" % (sid, audit.net_usd, ns))
        except Exception as exc:
            _progress("FAIL %s: %s" % (sid, exc))
            rows.append(dict(pair=sym, family=family, name=spec.name, strategy_id=sid, status="error", error=str(exc)))
        _write(rows)


def _hourly_bars(sym: str) -> List[Bar]:
    one_m = REPO / "fx" / ("%s_1m.csv" % sym.lower())
    gby = load_fx_1m_by_ny_date(one_m, sym)
    hourly = resample_hourly(concat_all_1m(gby))
    out: List[Bar] = []
    for ts, row in hourly.iterrows():
        out.append(
            Bar(
                instrument=sym,
                timeframe="1h",
                ts=ts.isoformat(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(one_m),
            )
        )
    return out


def run_stpmc(sym: str, rows: List[dict], force: bool) -> None:
    from . import hourly_st_pmc_strategyplugin_variants as hsv

    meta = METALS[sym]
    POINT_VALUES[sym] = meta["pv"]
    DEFAULT_TICK_SIZE[sym] = meta["tick"]
    hsv.TICK_SIZE[sym] = meta["tick"]
    pip = meta["pip"]
    variants = [
        VariantConfig("sl25_tp75_3r", stop_pts=25 * pip, tp1_pts=75 * pip, notes="25/75 3R"),
        VariantConfig("sl40_tp120_3r", stop_pts=40 * pip, tp1_pts=120 * pip, notes="40/120 3R"),
        VariantConfig(
            "sl25_tp75_3r_ma_bull_prior",
            stop_pts=25 * pip,
            tp1_pts=75 * pip,
            ma_filter="bull_prior_only",
            notes="25/75 MA bull prior",
        ),
    ]
    bars = _hourly_bars(sym)
    _progress("%s hourly bars: %d" % (sym, len(bars)))
    market = sym.lower()
    for cfg in variants:
        sid = "%s_hourly_st_pmc_%s" % (market, cfg.name)
        _progress("START stpmc %s" % sid)
        try:
            result = hsv.run_variant(
                cfg=cfg,
                bars=bars,
                output_root=OUT / "st_pmc" / market,
                dbn=REPO / "fx" / ("%s_1m.csv" % market),
                daily_path=REPO / "fx" / ("%s_daily.csv" % market),
                instrument=sym,
                market=market,
                force=force,
                quiet=True,
            )
            audit = result.audit
            ns = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
            rows.append(
                dict(
                    pair=sym,
                    family="hourly_st_pmc",
                    name="ST+PMC %s" % cfg.name,
                    strategy_id=sid,
                    status="ok",
                    units=audit.units,
                    trades=audit.trades,
                    net_usd=round(audit.net_usd),
                    stress_usd=round(audit.intrabar_mtm_dd_usd),
                    ns=round(ns, 2),
                    wr_units=round(100.0 * audit.win_units / audit.units if audit.units else 0.0, 1),
                )
            )
            _progress("DONE %s Net=$%d N/S=%.2f" % (sid, audit.net_usd, ns))
        except Exception as exc:
            _progress("FAIL %s: %s\n%s" % (sid, exc, traceback.format_exc()))
            rows.append(dict(pair=sym, family="hourly_st_pmc", name="ST+PMC %s" % cfg.name, strategy_id=sid, status="error", error=str(exc)))
        _write(rows)


def run_fbo(sym: str, rows: List[dict], force: bool) -> None:
    meta = METALS[sym]
    POINT_VALUES[sym] = meta["pv"]
    DEFAULT_TICK_SIZE[sym] = meta["tick"]
    daily_path = REPO / "fx" / ("%s_daily.csv" % sym.lower())
    bars = bars_from_csv(daily_path, sym, "D", source=str(daily_path))
    filt = _atr80_csv(sym)
    market = sym.lower()
    for label, entry, tp1, tp2 in FBO_STRUCTURES:
        for flabel, fcsv in [("base", None), ("atr80", str(filt))]:
            cfg = {
                "allow_shorts": True,
                "or_sessions": 3,
                "max_trades_per_month": 2,
                "entry_qty": entry,
                "tp1_qty": tp1,
                "tp2_qty": tp2,
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
            sid = "%s_fbo_%s_%s" % (market, label, flabel)
            _progress("START fbo %s" % sid)
            try:
                root = OUT / "states" / sid
                if force and root.exists():
                    shutil.rmtree(root)
                store = FlatFileStore(root, defer_table_writes=True)
                store.ensure()
                spec = BrokerReplaySpec(
                    name="%s FBO %s %s" % (sym, label, flabel),
                    slug=sid,
                    strategy_type="monthly_orb_v2b_oco",
                    max_contracts=entry,
                    config=cfg,
                    notes="FBO %s" % flabel,
                )
                inst = StrategyInstance(
                    strategy_id=sid,
                    strategy_type=spec.strategy_type,
                    version="v1",
                    instrument=sym,
                    broker_instrument=sym,
                    account_mode="paper",
                    enabled=True,
                    timeframes="D",
                    max_contracts=entry,
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
                    name=spec.name,
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
                ns = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
                rows.append(
                    dict(
                        pair=sym,
                        family="monthly_fbo",
                        name="FBO %s %s" % (label, flabel),
                        strategy_id=sid,
                        status="ok",
                        units=audit.units,
                        trades=audit.trades,
                        net_usd=round(audit.net_usd),
                        stress_usd=round(audit.intrabar_mtm_dd_usd),
                        ns=round(ns, 2),
                        wr_units=round(100.0 * audit.win_units / audit.units if audit.units else 0.0, 1),
                    )
                )
                _progress("DONE %s Net=$%d N/S=%.2f" % (sid, audit.net_usd, ns))
            except Exception as exc:
                _progress("FAIL %s: %s" % (sid, exc))
                rows.append(dict(pair=sym, family="monthly_fbo", name="FBO %s %s" % (label, flabel), strategy_id=sid, status="error", error=str(exc)))
            _write(rows)


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage", choices=["daily", "stpmc", "fbo", "all"], default="all")
    p.add_argument("--force", action="store_true")
    p.add_argument("--symbols", nargs="+", default=list(METALS.keys()))
    args = p.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = _load_rows()
    for sym in args.symbols:
        if args.stage in ("daily", "all"):
            run_daily(sym, rows, args.force)
        if args.stage in ("stpmc", "all"):
            run_stpmc(sym, rows, args.force)
        if args.stage in ("fbo", "all"):
            run_fbo(sym, rows, args.force)
    _write(rows)
    _progress("STAGE %s DONE" % args.stage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
