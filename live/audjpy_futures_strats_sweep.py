"""AUDJPY sweep of top tracked futures strategies.

Stages:
- daily: REPLAY_SPECS (yearly ORB x2, monthly scaleout3 x2, ATR supertrend x3)
- stpmc: hourly ST+PMC pip variants (50/150, 40/120, 25/75, directional)
- v2b: v2b OCO prior-opposed S_1_1_3 on 1m (2015+)

P&L in JPY (point value 100,000 quote units); fee ¥7/unit to match the FX pack
convention (understated ~1%: see fx_cross_pair_tracker_leaders SUMMARY).
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
OUT = REPO / "live" / "state" / "audjpy_futures_strats_sweep"

SYM = "AUDJPY"
MARKET = "audjpy"
PIP = 0.01
TICK = 0.001
POINT_VALUE = 100000.0
FEE = 7.0

ST_VARIANTS = [
    VariantConfig("base_1x_50sl_150tp", stop_pts=50 * PIP, tp1_pts=150 * PIP, notes="50/150 pip base."),
    VariantConfig("sl40_tp120_3r", stop_pts=40 * PIP, tp1_pts=120 * PIP, notes="40/120 3R in pips."),
    VariantConfig("sl25_tp75_3r", stop_pts=25 * PIP, tp1_pts=75 * PIP, notes="25/75 3R in pips."),
    VariantConfig(
        "sl40_tp120_3r_ma_directional_prior",
        stop_pts=40 * PIP,
        tp1_pts=120 * PIP,
        ma_filter="directional_prior",
        notes="40/120 with directional prior MA filter.",
    ),
]


def _progress(msg: str) -> None:
    print(msg, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def _ensure_meta() -> None:
    POINT_VALUES[SYM] = POINT_VALUE
    DEFAULT_TICK_SIZE[SYM] = TICK


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


def run_daily(rows: List[dict], force: bool) -> None:
    _ensure_meta()
    daily_path = REPO / "fx" / "audjpy_daily.csv"
    bars = bars_from_csv(daily_path, SYM, "D", source=str(daily_path))
    _progress("daily bars: %d" % len(bars))
    for spec in REPLAY_SPECS:
        sid = "%s_%s" % (MARKET, spec.slug)
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
                instrument=SYM,
                broker_instrument=SYM,
                account_mode="paper",
                enabled=True,
                timeframes="D",
                max_contracts=spec.max_contracts,
                max_open_orders=64,
                config_json=json.dumps(_runtime_config(spec, bars), sort_keys=True),
            )
            store.upsert_row("strategy_instances", "strategy_id", as_row(inst))
            Engine(store=store, slippage_ticks=1.0, tick_size={SYM: TICK}).replay_bars(bars)
            store.flush_tables()
            generate_market_close_report(store, bars[-1].ts[:10])
            rb = read_bars(root / "bars" / ("%s_D.csv" % SYM), "ts")
            units = units_from_live_fills(root / "fills.csv", sid, rb[-1].ts, rb[-1].close)
            audit = audit_units(
                name="AUDJPY %s" % spec.name,
                slug=sid,
                source=root / "fills.csv",
                bar_source=root / "bars" / ("%s_D.csv" % SYM),
                bars=rb,
                units=units,
                instrument=SYM,
                notes=spec.notes,
                output_root=OUT / "audits",
                fee_per_unit=FEE,
            )
            ns = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
            rows.append(
                dict(
                    family=family,
                    name=spec.name,
                    strategy_id=sid,
                    status="ok",
                    units=audit.units,
                    trades=audit.trades,
                    net_jpy=round(audit.net_usd),
                    stress_jpy=round(audit.intrabar_mtm_dd_usd),
                    ns=round(ns, 2),
                    wr_units=round(100.0 * audit.win_units / audit.units if audit.units else 0.0, 1),
                    net_usd_approx=round(audit.net_usd / 110.0),
                )
            )
            _progress("DONE %s Net=JPY%d N/S=%.2f" % (sid, audit.net_usd, ns))
        except Exception as exc:
            _progress("FAIL %s: %s" % (sid, exc))
            rows.append(dict(family=family, name=spec.name, strategy_id=sid, status="error", error=str(exc)))
        _write(rows)


def _hourly_bars() -> List[Bar]:
    one_m = REPO / "fx" / "audjpy_1m.csv"
    gby = load_fx_1m_by_ny_date(one_m, SYM)
    hourly = resample_hourly(concat_all_1m(gby))
    out: List[Bar] = []
    for ts, row in hourly.iterrows():
        out.append(
            Bar(
                instrument=SYM,
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


def run_stpmc(rows: List[dict], force: bool) -> None:
    from . import hourly_st_pmc_strategyplugin_variants as hsv

    _ensure_meta()
    hsv.TICK_SIZE[SYM] = TICK
    bars = _hourly_bars()
    _progress("hourly bars: %d" % len(bars))
    for cfg in ST_VARIANTS:
        sid = "%s_hourly_st_pmc_%s" % (MARKET, cfg.name)
        _progress("START stpmc %s" % sid)
        try:
            result = hsv.run_variant(
                cfg=cfg,
                bars=bars,
                output_root=OUT / "st_pmc",
                dbn=REPO / "fx" / "audjpy_1m.csv",
                daily_path=REPO / "fx" / "audjpy_daily.csv",
                instrument=SYM,
                market=MARKET,
                force=force,
                quiet=True,
            )
            audit = result.audit
            ns = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
            rows.append(
                dict(
                    family="hourly_st_pmc",
                    name="ST+PMC %s" % cfg.name,
                    strategy_id=sid,
                    status="ok",
                    units=audit.units,
                    trades=audit.trades,
                    net_jpy=round(audit.net_usd),
                    stress_jpy=round(audit.intrabar_mtm_dd_usd),
                    ns=round(ns, 2),
                    wr_units=round(100.0 * audit.win_units / audit.units if audit.units else 0.0, 1),
                    net_usd_approx=round(audit.net_usd / 110.0),
                )
            )
            _progress("DONE %s Net=JPY%d N/S=%.2f" % (sid, audit.net_usd, ns))
        except Exception as exc:
            _progress("FAIL %s: %s\n%s" % (sid, exc, traceback.format_exc()))
            rows.append(dict(family="hourly_st_pmc", name="ST+PMC %s" % cfg.name, strategy_id=sid, status="error", error=str(exc)))
        _write(rows)


def _has_full_rth_close(raw_day: Optional[pd.DataFrame], session: date) -> bool:
    rth = rth_bars(raw_day, session, dense=True)
    if rth.empty:
        return False
    cutoff = pd.Timestamp("15:55").time()
    return bool((rth.index.time >= cutoff).any())


def run_v2b(rows: List[dict], force: bool, start: date, max_days: Optional[int]) -> None:
    from .v2b_strategy_replay import fast_intraday_audit, units_from_v2b_fills, AuditBar

    _ensure_meta()
    one_m = REPO / "fx" / "audjpy_1m.csv"
    daily_path = REPO / "fx" / "audjpy_daily.csv"
    cfg = MarketConfig(
        market=MARKET,
        instrument=SYM,
        daily_path=daily_path,
        dbn_path=one_m,
        start=start,
        fee_per_unit=FEE,
    )
    _progress("loading 1m for v2b prior-opposed...")
    gby = load_fx_1m_by_ny_date(one_m, SYM)
    regime_dates = _regime_dates(cfg, gby, start=start)
    regime_dates = [d for d in regime_dates if _has_full_rth_close(gby.get(d), d)]
    if max_days is not None:
        regime_dates = regime_dates[:max_days]
    _progress("v2b regime sessions: %d" % len(regime_dates))

    slug = "v2b_oco_prior_opposed_S_1_1_3"
    sid = "%s_%s" % (MARKET, slug)
    _progress("START v2b %s" % sid)
    try:
        root = OUT / "states" / sid
        if force and root.exists():
            shutil.rmtree(root)
        store = FlatFileStore(root, defer_table_writes=True)
        store.ensure()
        payload = {
            "market": MARKET,
            "tick_size": TICK,
            "use_regime_filter": True,
            "start": start.isoformat(),
            "regime_dates": [d.isoformat() for d in regime_dates],
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
            instrument=SYM,
            broker_instrument=SYM,
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
            tick_size={SYM: TICK},
            notification_sink=NullNotificationSink(),
            verification_provider=QuietPaperVerificationProvider(),
            emit_order_alerts=False,
            broker_log_events=False,
            broker_persist_modifications=False,
        )
        n_days = len(regime_dates)
        for di, d in enumerate(regime_dates, start=1):
            day = gby.get(d)
            if day is None or day.empty:
                continue
            for ts, row in day.iterrows():
                engine.process_bar(
                    Bar(
                        instrument=SYM,
                        timeframe="1m",
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
            if di % 100 == 0:
                _progress("  v2b day %d/%d" % (di, n_days))
        if hasattr(engine.broker, "flush_state"):
            engine.broker.flush_state()
        store.flush_tables()
        fills_path = root / "fills.csv"
        units = units_from_live_fills(fills_path, sid)
        audit_bars = [
            AuditBar(ts=ts.isoformat(), open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"]))
            for d in regime_dates
            if gby.get(d) is not None
            for ts, r in gby[d].iterrows()
        ]
        audit = fast_intraday_audit(
            name="AUDJPY v2b prior-opposed S_1_1_3",
            slug=sid,
            source=fills_path,
            units=units,
            bars=audit_bars,
            instrument=SYM,
            notes="v2b OCO prior-opposed 1/1/3, 1m replay, fee=JPY%.2f" % FEE,
            output_root=OUT / "audits",
            fee_per_unit=FEE,
        )
        ns = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
        rows.append(
            dict(
                family="v2b_prior_opposed",
                name="v2b OCO prior-opposed S_1_1_3",
                strategy_id=sid,
                status="ok",
                units=audit.units,
                trades=audit.trades,
                net_jpy=round(audit.net_usd),
                stress_jpy=round(audit.intrabar_mtm_dd_usd),
                ns=round(ns, 2),
                wr_units=round(100.0 * audit.win_units / audit.units if audit.units else 0.0, 1),
                net_usd_approx=round(audit.net_usd / 110.0),
            )
        )
        _progress("DONE %s Net=JPY%d N/S=%.2f" % (sid, audit.net_usd, ns))
    except Exception as exc:
        _progress("FAIL %s: %s\n%s" % (sid, exc, traceback.format_exc()))
        rows.append(dict(family="v2b_prior_opposed", name="v2b OCO prior-opposed S_1_1_3", strategy_id=sid, status="error", error=str(exc)))
    _write(rows)


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage", choices=["daily", "stpmc", "v2b", "all"], default="all")
    p.add_argument("--force", action="store_true")
    p.add_argument("--v2b-start", type=str, default="2015-01-02")
    p.add_argument("--v2b-max-days", type=int, default=None)
    args = p.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = _load_rows()
    if args.stage in ("daily", "all"):
        run_daily(rows, args.force)
    if args.stage in ("stpmc", "all"):
        run_stpmc(rows, args.force)
    if args.stage in ("v2b", "all"):
        y, m, d = (int(x) for x in args.v2b_start.split("-"))
        run_v2b(rows, args.force, date(y, m, d), args.v2b_max_days)
    _write(rows)
    _progress("STAGE %s DONE" % args.stage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
