"""Run the tracked FX leaders on GBPUSD / USDJPY / AUDJPY.

Strategies (from STRATEGY_TRACKER Forex leaderboard):
1. Monthly ORB FBO 1/1/3 and 1/2/3 (runner@2R, BE@TP25, close-SL) — base and
   with the atr80 regime filter (daily ATR14 rolling-500 pctl <= 0.80).
2. Hourly ST+PMC sl25/tp75 3R with prior MA50>MA150 daily gate (promoted
   intraday sleeve), fee $1.50/unit convention.

JPY-quoted pairs (USDJPY, AUDJPY) report P&L in JPY (point value = 100,000
quote units); the summary adds an approx-USD column at 110 JPY/USD.
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
from .broker_like_replays import BrokerReplaySpec, _runtime_config
from .engine import Engine, bars_from_csv
from .hourly_st_pmc_loss_research import VariantConfig
from .models import Bar, StrategyInstance, as_row
from .replay_audit import POINT_VALUES, audit_units, read_bars, units_from_live_fills
from .reporting import generate_market_close_report
from .store import FlatFileStore
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, resample_hourly
from .fx_data import load_fx_1m_by_ny_date

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "fx_cross_pair_tracker_leaders"

MONTHLY_FEE = 7.0  # quote-ccy per unit (matches EURUSD monthly ORB pack)
JPY_USD = 110.0  # long-run average for approx-USD reporting

PAIRS: Dict[str, Dict[str, object]] = {
    "GBPUSD": dict(pip=0.0001, tick=0.00001, quote="USD"),
    "USDJPY": dict(pip=0.01, tick=0.001, quote="JPY"),
    "AUDJPY": dict(pip=0.01, tick=0.001, quote="JPY"),
}

FBO_STRUCTURES: List[Tuple[str, int, int, int]] = [("1_1_3", 5, 1, 1), ("1_2_3", 6, 1, 2)]


def _progress(msg: str) -> None:
    print(msg, flush=True)
    with (OUT / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def _atr80_filter_csv(sym: str) -> Path:
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


def _campaign_wr(fills: pd.DataFrame, pv: float, fee: float) -> Tuple[int, float]:
    fills = fills.copy()
    fills["ts"] = pd.to_datetime(fills["ts"])
    pnls = []
    for _, g in fills.groupby("trade_id"):
        g = g.sort_values("ts")
        e = g[g.reason == "entry"]
        if e.empty:
            continue
        e = e.iloc[0]
        pnl = -fee * float(e.quantity)
        for _, r in g[g.reason != "entry"].iterrows():
            pts = (r.price - e.price) * r.quantity if e.side == "buy" else (e.price - r.price) * r.quantity
            pnl += pts * pv - fee * float(r.quantity)
        pnls.append(pnl)
    a = np.array(pnls, float)
    return len(a), (100.0 * (a > 0).mean() if len(a) else 0.0)


def run_fbo(sym: str, rows: List[dict], force: bool) -> None:
    meta = PAIRS[sym]
    tick = float(meta["tick"])
    POINT_VALUES[sym] = 100000.0
    DEFAULT_TICK_SIZE[sym] = tick
    daily_path = REPO / "fx" / ("%s_daily.csv" % sym.lower())
    bars = bars_from_csv(daily_path, sym, "D", source=str(daily_path))
    filt_csv = _atr80_filter_csv(sym)
    for label, entry, tp1, tp2 in FBO_STRUCTURES:
        for flabel, fcsv in [("base", None), ("atr80", str(filt_csv))]:
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
            spec = BrokerReplaySpec(
                name="%s FBO %s %s" % (sym, label, flabel),
                slug="fbo_%s_%s_%s" % (label, flabel, sym.lower()),
                strategy_type="monthly_orb_v2b_oco",
                max_contracts=entry,
                config=cfg,
                notes="FBO %s runner@2R BE@TP25 close-SL %s" % (label, flabel),
            )
            sid = spec.slug
            _progress("START %s" % sid)
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
                    max_contracts=entry,
                    max_open_orders=64,
                    config_json=json.dumps(_runtime_config(spec, bars), sort_keys=True),
                )
                store.upsert_row("strategy_instances", "strategy_id", as_row(inst))
                Engine(store=store, slippage_ticks=1.0, tick_size={sym: tick}).replay_bars(bars)
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
                    fee_per_unit=MONTHLY_FEE,
                )
                n, wr = _campaign_wr(pd.read_csv(root / "fills.csv"), 100000.0, MONTHLY_FEE)
                ns = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
                fx = JPY_USD if meta["quote"] == "JPY" else 1.0
                rows.append(
                    dict(
                        pair=sym,
                        family="monthly_fbo",
                        variant="%s_%s" % (label, flabel),
                        n=n,
                        wr=round(wr, 1),
                        net_quote=round(audit.net_usd),
                        stress_quote=round(audit.intrabar_mtm_dd_usd),
                        ns=round(ns, 2),
                        net_usd_approx=round(audit.net_usd / fx),
                        stress_usd_approx=round(audit.intrabar_mtm_dd_usd / fx),
                        quote=meta["quote"],
                    )
                )
                _progress(
                    "DONE %s n=%d WR=%.1f Net=%s%d Stress=%s%d N/S=%.2f"
                    % (sid, n, wr, meta["quote"], audit.net_usd, meta["quote"], audit.intrabar_mtm_dd_usd, ns)
                )
            except Exception as exc:
                _progress("FAIL %s: %s\n%s" % (sid, exc, traceback.format_exc()))
                rows.append(dict(pair=sym, family="monthly_fbo", variant="%s_%s" % (label, flabel), error=str(exc)))
            _write(rows)


def _hourly_bars(sym: str) -> List[Bar]:
    one_m = REPO / "fx" / ("%s_1m.csv" % sym.lower())
    gby = load_fx_1m_by_ny_date(one_m, sym)
    hourly = resample_hourly(concat_all_1m(gby))
    bars: List[Bar] = []
    for ts, row in hourly.iterrows():
        bars.append(
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
    return bars


def run_st_pmc(sym: str, rows: List[dict], force: bool) -> None:
    from . import hourly_st_pmc_strategyplugin_variants as hsv

    meta = PAIRS[sym]
    pip = float(meta["pip"])
    tick = float(meta["tick"])
    POINT_VALUES[sym] = 100000.0
    DEFAULT_TICK_SIZE[sym] = tick
    hsv.TICK_SIZE[sym] = tick
    cfg = VariantConfig(
        "sl25_tp75_3r_ma_bull_prior",
        stop_pts=25 * pip,
        tp1_pts=75 * pip,
        ma_filter="bull_prior_only",
        notes="25/75 pip 3R with prior MA50>MA150 gate.",
    )
    _progress("START st_pmc %s (loading 1m→1h)" % sym)
    try:
        bars = _hourly_bars(sym)
        _progress("  %s hourly bars: %d" % (sym, len(bars)))
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
        ns = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
        fx = JPY_USD if meta["quote"] == "JPY" else 1.0
        rows.append(
            dict(
                pair=sym,
                family="hourly_st_pmc",
                variant="sl25_tp75_3r_ma_bull_prior",
                n=audit.trades,
                wr=round(100.0 * audit.win_units / audit.units if audit.units else 0.0, 1),
                net_quote=round(audit.net_usd),
                stress_quote=round(audit.intrabar_mtm_dd_usd),
                ns=round(ns, 2),
                net_usd_approx=round(audit.net_usd / fx),
                stress_usd_approx=round(audit.intrabar_mtm_dd_usd / fx),
                quote=meta["quote"],
            )
        )
        _progress("DONE st_pmc %s Net=%s%d N/S=%.2f" % (sym, meta["quote"], audit.net_usd, ns))
    except Exception as exc:
        _progress("FAIL st_pmc %s: %s\n%s" % (sym, exc, traceback.format_exc()))
        rows.append(dict(pair=sym, family="hourly_st_pmc", variant="sl25_tp75_3r_ma_bull_prior", error=str(exc)))
    _write(rows)


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


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--force", action="store_true")
    p.add_argument("--skip-intraday", action="store_true")
    args = p.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    rows: List[dict] = []
    for sym in PAIRS:
        run_fbo(sym, rows, args.force)
    if not args.skip_intraday:
        for sym in PAIRS:
            run_st_pmc(sym, rows, args.force)
    _write(rows)
    _progress("ALL DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
