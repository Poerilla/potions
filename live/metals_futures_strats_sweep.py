"""Metals (XAUUSD / XAGUSD) gambit: futures-style strats + FBO atr80.

Daily: REPLAY_SPECS (yearly ORB, monthly scaleout3, ATR ST).
Hourly: ST+PMC pip variants.
Monthly FBO: 1/1/3 base + atr80.
v2b: prior-opposed S_1_1_3 gated by same-session ST+PMC 25/75 (2015+).

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
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .bars import rth_bars
from .broker import DEFAULT_TICK_SIZE
from .broker_like_replays import BrokerReplaySpec, REPLAY_SPECS, _runtime_config
from .engine import Engine, bars_from_csv
from .fx_data import load_fx_1m_by_ny_date
from .hourly_st_pmc_loss_research import VariantConfig
from .models import Bar, StrategyInstance, as_row
from .nq_v2b_prior_opposed_replay import load_st_events, summarize_units
from .replay_audit import POINT_VALUES, audit_units, read_bars, units_from_live_fills
from .replay_realism import hardened_replay_engine_kwargs
from .reporting import generate_market_close_report
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import MarketConfig, _regime_dates
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


def _has_full_rth_close(raw_day: Optional[pd.DataFrame], session: date) -> bool:
    rth = rth_bars(raw_day, session, dense=True)
    if rth.empty:
        return False
    cutoff = pd.Timestamp("15:55").time()
    return bool((rth.index.time >= cutoff).any())


def _drop_family(rows: List[dict], pair: str, family: str) -> List[dict]:
    return [r for r in rows if not (str(r.get("pair")) == pair and str(r.get("family")) == family)]


def run_v2b(sym: str, rows: List[dict], force: bool, start: date, max_days: Optional[int]) -> None:
    """v2b OCO prior-opposed S_1_1_3 gated by base ST+PMC 25/75 fills (AUDJPY parity)."""
    from .v2b_strategy_replay import AuditBar

    meta = METALS[sym]
    POINT_VALUES[sym] = meta["pv"]
    DEFAULT_TICK_SIZE[sym] = meta["tick"]
    market = sym.lower()
    one_m = REPO / "fx" / ("%s_1m.csv" % market)
    daily_path = REPO / "fx" / ("%s_daily.csv" % market)
    st_sid = "%s_hourly_st_pmc_sl25_tp75_3r" % market
    st_fills = OUT / "st_pmc" / market / "states" / st_sid / "fills.csv"
    if not st_fills.exists():
        raise FileNotFoundError("Need ST+PMC gate fills at %s — run --stage stpmc first" % st_fills)

    sid = "%s_v2b_prior_opposed_stpmc_only_S_1_1_3" % market
    _progress("START v2b %s" % sid)
    try:
        rows[:] = _drop_family(rows, sym, "v2b_prior_opposed")
        root = OUT / "states" / sid
        if force and root.exists():
            shutil.rmtree(root)

        cfg = MarketConfig(
            market=market,
            instrument=sym,
            daily_path=daily_path,
            dbn_path=one_m,
            start=start,
            fee_per_unit=FEE,
        )
        _progress("loading %s 1m for v2b prior-opposed..." % sym)
        gby = load_fx_1m_by_ny_date(one_m, sym)
        st_orders = st_fills.parent / "orders.csv"
        st_events = load_st_events(
            st_fills,
            st_sid,
            orders_path=st_orders if st_orders.exists() else None,
            bars_by_ny_date=gby,
        )
        regime_dates = _regime_dates(cfg, gby, start=start)
        regime_dates = [d for d in regime_dates if _has_full_rth_close(gby.get(d), d)]
        if max_days is not None:
            regime_dates = regime_dates[:max_days]
        _progress("  %s v2b regime sessions: %d | ST gate events days: %d" % (sym, len(regime_dates), len(st_events)))

        store = FlatFileStore(root, defer_table_writes=True)
        store.ensure()
        payload = {
            "market": market,
            "mode": "oco_then_reverse",
            "entry_qty": 5,
            "tp1_qty": 1,
            "tp2_qty": 1,
            "tick_size": meta["tick"],
            "use_regime_filter": True,
            "start": start.isoformat(),
            "regime_dates": [d.isoformat() for d in regime_dates],
            "record_levels": False,
            "dynamic_sizing_events": st_events,
            "prior_opposite_only": True,
            "prior_opposite_entry_qty": 5,
            "prior_opposite_tp1_qty": 1,
            "prior_opposite_tp2_qty": 1,
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
            tick_size={sym: meta["tick"]},
            **hardened_replay_engine_kwargs(slippage_ticks=1.0),
        )

        audit_bars: List[AuditBar] = []
        n_days = len(regime_dates)
        for di, d in enumerate(regime_dates, start=1):
            day = rth_bars(gby.get(d), d, dense=True)
            if day is None or day.empty:
                continue
            for ts, row in day.iterrows():
                ts_s = pd.Timestamp(ts).isoformat()
                bar = Bar(
                    instrument=sym,
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
            if di % 100 == 0:
                _progress("  v2b %s day %d/%d" % (sym, di, n_days))
        if hasattr(engine.broker, "flush_state"):
            engine.broker.flush_state()
        store.flush_tables()

        result = summarize_units(
            sid,
            root,
            audit_bars,
            sym,
            FEE,
            market=market,
            regime_days=len(regime_dates),
            st_events=st_events,
            start_date=start,
        )
        # also bank a short audit note under audits/
        audit_dir = OUT / "audits" / sid
        audit_dir.mkdir(parents=True, exist_ok=True)
        (audit_dir / "reports").mkdir(exist_ok=True)
        (audit_dir / "reports" / "MTM_AUDIT.md").write_text(
            "\n".join(
                [
                    "# %s v2b prior-opposed S_1_1_3" % sym,
                    "",
                    "| Metric | Value |",
                    "|---|---:|",
                    "| Trades | %d |" % result.trades,
                    "| Units | %d |" % result.units,
                    "| Net | $%s |" % f"{result.net_usd:,.0f}",
                    "| Stress DD | $%s |" % f"{result.stress_dd_usd:,.0f}",
                    "| Net/Stress | %.2f |" % result.net_stress,
                    "| Unit WR | %.1f%% |" % result.win_rate_pct,
                    "| Regime days | %d |" % result.regime_days,
                    "| Prior-opposite entries | %d |" % result.prior_opposite_entries,
                    "",
                    "Gate: `%s`. Fee $%.2f/unit." % (st_sid, FEE),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        rows.append(
            dict(
                pair=sym,
                family="v2b_prior_opposed",
                name="v2b OCO prior-opposed S_1_1_3 (ST+PMC gate)",
                strategy_id=sid,
                status="ok",
                units=result.units,
                trades=result.trades,
                net_usd=round(result.net_usd),
                stress_usd=round(result.stress_dd_usd),
                ns=round(result.net_stress, 2),
                wr_units=round(result.win_rate_pct, 1),
            )
        )
        _progress(
            "DONE %s Net=$%d N/S=%.2f trades=%d"
            % (sid, result.net_usd, result.net_stress, result.trades)
        )
    except Exception as exc:
        _progress("FAIL %s: %s\n%s" % (sid, exc, traceback.format_exc()))
        rows.append(
            dict(
                pair=sym,
                family="v2b_prior_opposed",
                name="v2b OCO prior-opposed S_1_1_3 (ST+PMC gate)",
                strategy_id=sid,
                status="error",
                error=str(exc),
            )
        )
    _write(rows)


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage", choices=["daily", "stpmc", "fbo", "v2b", "all"], default="all")
    p.add_argument("--force", action="store_true")
    p.add_argument("--symbols", nargs="+", default=list(METALS.keys()))
    p.add_argument("--v2b-start", type=str, default="2015-01-02")
    p.add_argument("--v2b-max-days", type=int, default=None)
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
        if args.stage in ("v2b", "all"):
            y, m, d = (int(x) for x in args.v2b_start.split("-"))
            run_v2b(sym, rows, args.force, date(y, m, d), args.v2b_max_days)
    _write(rows)
    _progress("STAGE %s DONE" % args.stage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
