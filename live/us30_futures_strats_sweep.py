"""US30 CFD sweep of StrategyPlugins used on FX/indices gambits.

Stages (same families as AUDJPY / metals / EURUSD overnight):
- daily: REPLAY_SPECS (yearly ORB x2, monthly scaleout3 x2, ATR supertrend x3)
- stpmc: hourly ST+PMC **index-point** variants (25/75, 40/120, 50/150, + MA gate)
- v2b: v2b OCO prior-opposed S_1_1_3 on 1m RTH

Economics: tick=0.1, point_value=$1/pt/unit, fee=$1.50/unit (NAS100/NQ pack).
Raw: ``fx/raw/us30.zip`` → ``fx/raw/us30_extracted/us30_*`` → ``fx/us30_{1m,daily}.csv``.
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
from .broker_like_replays import REPLAY_SPECS, _runtime_config
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
OUT = REPO / "live" / "state" / "us30_futures_strats_sweep"

SYM = "US30"
MARKET = "us30"
TICK = 0.1
POINT_VALUE = 1.0
FEE = 1.50

# Index-point ST+PMC (same absolute distances as NAS100 / NQ convention).
ST_VARIANTS = [
    VariantConfig("sl25_tp75_3r", stop_pts=25.0, tp1_pts=75.0, notes="25/75 index pts."),
    VariantConfig("sl40_tp120_3r", stop_pts=40.0, tp1_pts=120.0, notes="40/120 index pts."),
    VariantConfig("sl50_tp150_3r", stop_pts=50.0, tp1_pts=150.0, notes="50/150 index pts."),
    VariantConfig(
        "sl25_tp75_3r_ma_directional_prior",
        stop_pts=25.0,
        tp1_pts=75.0,
        ma_filter="directional_prior",
        notes="25/75 with directional prior MA filter.",
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


def _row_ok(
    *,
    family: str,
    name: str,
    strategy_id: str,
    audit,
) -> dict:
    ns = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
    return dict(
        family=family,
        name=name,
        strategy_id=strategy_id,
        status="ok",
        units=audit.units,
        trades=audit.trades,
        net_usd=round(audit.net_usd, 2),
        stress_dd_usd=round(audit.intrabar_mtm_dd_usd, 2),
        ns=round(ns, 2),
        wr_units=round(100.0 * audit.win_units / audit.units if audit.units else 0.0, 1),
    )


def run_daily(rows: List[dict], force: bool) -> None:
    _ensure_meta()
    daily_path = REPO / "fx" / "us30_daily.csv"
    bars = bars_from_csv(daily_path, SYM, "D", source=str(daily_path))
    _progress("daily bars: %d" % len(bars))
    for spec in REPLAY_SPECS:
        sid = "%s_%s" % (MARKET, spec.slug)
        family = "yearly_orb" if "yearly" in spec.slug else ("atr_st" if "atr" in spec.slug else "monthly_orb")
        if any(str(r.get("strategy_id")) == sid and r.get("status") == "ok" for r in rows) and not force:
            _progress("SKIP daily %s (already ok)" % sid)
            continue
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
                name="US30 %s" % spec.name,
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
            rows.append(_row_ok(family=family, name=spec.name, strategy_id=sid, audit=audit))
            _progress("DONE %s Net=$%.0f N/S=%.2f" % (sid, audit.net_usd, rows[-1]["ns"]))
        except Exception as exc:
            _progress("FAIL %s: %s" % (sid, exc))
            rows.append(dict(family=family, name=spec.name, strategy_id=sid, status="error", error=str(exc)))
        _write(rows)


def _hourly_bars() -> List[Bar]:
    one_m = REPO / "fx" / "us30_1m.csv"
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
        if any(str(r.get("strategy_id")) == sid and r.get("status") == "ok" for r in rows) and not force:
            _progress("SKIP stpmc %s (already ok)" % sid)
            continue
        _progress("START stpmc %s" % sid)
        try:
            result = hsv.run_variant(
                cfg=cfg,
                bars=bars,
                output_root=OUT / "st_pmc",
                dbn=REPO / "fx" / "us30_1m.csv",
                daily_path=REPO / "fx" / "us30_daily.csv",
                instrument=SYM,
                market=MARKET,
                force=force,
                quiet=True,
            )
            audit = result.audit
            rows.append(_row_ok(family="hourly_st_pmc", name="ST+PMC %s" % cfg.name, strategy_id=sid, audit=audit))
            _progress("DONE %s Net=$%.0f N/S=%.2f" % (sid, audit.net_usd, rows[-1]["ns"]))
        except Exception as exc:
            _progress("FAIL %s: %s\n%s" % (sid, exc, traceback.format_exc()))
            rows.append(
                dict(family="hourly_st_pmc", name="ST+PMC %s" % cfg.name, strategy_id=sid, status="error", error=str(exc))
            )
        _write(rows)


def _has_full_rth_close(raw_day: Optional[pd.DataFrame], session: date) -> bool:
    rth = rth_bars(raw_day, session, dense=True)
    if rth.empty:
        return False
    cutoff = pd.Timestamp("15:55").time()
    return bool((rth.index.time >= cutoff).any())


def run_v2b(rows: List[dict], force: bool, start: date, max_days: Optional[int]) -> None:
    from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills

    _ensure_meta()
    sid = "%s_v2b_oco_prior_opposed_S_1_1_3" % MARKET
    if any(str(r.get("strategy_id")) == sid and r.get("status") == "ok" for r in rows) and not force:
        _progress("SKIP v2b %s (already ok)" % sid)
        return

    one_m = REPO / "fx" / "us30_1m.csv"
    daily_path = REPO / "fx" / "us30_daily.csv"
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
    _progress("START v2b %s" % sid)
    try:
        root = OUT / "states" / sid
        fills_path = root / "fills.csv"
        replay_needed = force or not fills_path.exists() or fills_path.stat().st_size < 100
        if replay_needed:
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
        else:
            _progress("reusing existing fills at %s" % fills_path)

        units = units_from_v2b_fills(fills_path, sid)
        audit_bars = [
            AuditBar(
                ts=ts.isoformat(),
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
            )
            for d in regime_dates
            if gby.get(d) is not None
            for ts, r in gby[d].iterrows()
        ]
        audit = fast_intraday_audit(
            strategy_id=sid,
            state_root=root,
            bars=audit_bars,
            units=units,
            instrument=SYM,
            fee_per_unit=FEE,
        )
        net = float(audit["net_usd"])
        stress = float(audit["intrabar_stress_dd_usd"])
        ns = net / abs(stress) if stress else 0.0
        # drop prior error row for this sid
        rows[:] = [r for r in rows if str(r.get("strategy_id")) != sid]
        rows.append(
            dict(
                family="v2b_prior_opposed",
                name="v2b OCO prior-opposed S_1_1_3",
                strategy_id=sid,
                status="ok",
                units=len(units),
                trades=len({u.trade_id for u in units}),
                net_usd=round(net, 2),
                stress_dd_usd=round(stress, 2),
                ns=round(ns, 2),
                wr_units=round(float(audit.get("win_rate") or 0.0), 1),
            )
        )
        _progress("DONE %s Net=$%.0f N/S=%.2f" % (sid, net, ns))
    except Exception as exc:
        _progress("FAIL %s: %s\n%s" % (sid, exc, traceback.format_exc()))
        rows[:] = [r for r in rows if str(r.get("strategy_id")) != sid]
        rows.append(
            dict(
                family="v2b_prior_opposed",
                name="v2b OCO prior-opposed S_1_1_3",
                strategy_id=sid,
                status="error",
                error=str(exc),
            )
        )
    _write(rows)


def write_summary(rows: List[dict]) -> None:
    ok = [r for r in rows if r.get("status") == "ok"]
    ok_sorted = sorted(ok, key=lambda r: float(r.get("ns") or -999), reverse=True)
    lines = [
        "# US30 — StrategyPlugin gambit sweep",
        "",
        "Engine + PaperBroker on MT5 US30 CFD 1m/daily (`fx/us30_*.csv`, labeled extract",
        "from `fx/raw/us30.zip`). Tick **0.1**, PV **$1/pt**, fee **$1.50**/unit.",
        "ST+PMC stops in **index points** (NAS100/NQ convention). Same plugin families",
        "as AUDJPY / metals / EURUSD overnight (daily ORB/ATR, hourly ST+PMC, v2b prior-opposed).",
        "",
        "| Rank | Family | Strategy | Trades | Net $ | Stress DD | **N/S** | Unit WR |",
        "|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for i, r in enumerate(ok_sorted, 1):
        lines.append(
            "| %d | %s | %s | %s | **%s** | %s | **%s** | %s%% |"
            % (
                i,
                r.get("family"),
                r.get("name"),
                r.get("trades"),
                r.get("net_usd"),
                r.get("stress_dd_usd"),
                r.get("ns"),
                r.get("wr_units"),
            )
        )
    if ok_sorted:
        best = ok_sorted[0]
        lines.extend(
            [
                "",
                "## Most promising: **%s** (`%s`)" % (best.get("name"), best.get("strategy_id")),
                "",
                "- Family: `%s`" % best.get("family"),
                "- Net / Stress: **%s** / %s → N/S **%s**" % (best.get("net_usd"), best.get("stress_dd_usd"), best.get("ns")),
                "- Trades / unit WR: %s / %s%%" % (best.get("trades"), best.get("wr_units")),
                "",
            ]
        )
    errs = [r for r in rows if r.get("status") == "error"]
    if errs:
        lines.append("## Errors")
        lines.append("")
        for r in errs:
            lines.append("- `%s`: %s" % (r.get("strategy_id"), r.get("error")))
        lines.append("")
    lines.extend(
        [
            "Driver: `live/us30_futures_strats_sweep.py` (stages: daily / stpmc / v2b).",
            "State: `live/state/us30_futures_strats_sweep/`.",
            "",
        ]
    )
    (OUT / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    _progress("Wrote SUMMARY.md (%d ok, %d err)" % (len(ok), len(errs)))


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage", choices=["daily", "stpmc", "v2b", "all"], default="all")
    p.add_argument("--force", action="store_true")
    p.add_argument("--v2b-start", type=str, default="2017-01-03")
    p.add_argument("--v2b-max-days", type=int, default=None)
    args = p.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [] if args.force else _load_rows()
    if args.force:
        rows = []
    if args.stage in ("daily", "all"):
        run_daily(rows, args.force)
    if args.stage in ("stpmc", "all"):
        run_stpmc(rows, args.force)
    if args.stage in ("v2b", "all"):
        y, m, d = (int(x) for x in args.v2b_start.split("-"))
        run_v2b(rows, args.force, date(y, m, d), args.v2b_max_days)
    _write(rows)
    write_summary(rows)
    _progress("STAGE %s DONE" % args.stage)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
