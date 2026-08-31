"""Broker-like Engine+PaperBroker 1m fill tape: HP liq-run fade 1:1 re-entry.

Replays the lookback-HP unlimited re-entry book through Engine on NQ **1m**
bars (resting limit @ p_liq, SL=1R, target=month open; re-arm after TP
immediately, after stop on open-touch).

Hub: ``live/state/monthly_open_atr_extension_band/liq_run_fade_1r1_reentry_hp_1m_broker/``
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .monthly_atr4_helpers import load_1h, month_windows
from .monthly_open_atr_extension_band_lookback_hp_charts import (
    FEATURES_CSV,
    _ny_ts,
    detect_liquidity_run,
    select_months,
)
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS
from .replay_audit import POINT_VALUES, audit_units, units_from_live_fills
from .replay_realism import hardened_replay_engine_kwargs
from .run_ledger import log_run
from .spread_model import SpreadModel
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import MARKETS as V2B_MARKETS, load_1m_by_ny_date_any
from .verification import QuietPaperVerificationProvider

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = (
    REPO
    / "live"
    / "state"
    / "monthly_open_atr_extension_band"
    / "liq_run_fade_1r1_reentry_hp_1m_broker"
)
NY = "America/New_York"
FEE = 1.50
ENTRY_QTY = 10
DSR = "TRL-2026-00143"
STRATEGY_ID = "nq_liq_run_fade_1r1_reentry_hp_1m"


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _utc_z(ts) -> str:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return t.tz_convert("UTC").isoformat().replace("+00:00", "Z")


def _spread(tick: float) -> SpreadModel:
    return SpreadModel(
        rth_half_spread_ticks=0.5,
        eth_half_spread_ticks=1.0,
        open_widen_half_spread_ticks=1.0,
        low_volume_threshold=50.0,
        low_volume_multiplier=1.5,
        tick_size=tick,
    )


def build_hp_month_plans(*, smoke: int = 0, liq_days: int = 2) -> Dict[str, dict]:
    spec = MARKETS["NQ"]
    bars = load_1h(spec)
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    bars_ny = bars.tz_convert(NY)

    win_by: Dict[Tuple[int, int], Tuple[pd.Timestamp, pd.Timestamp]] = {}
    for year, month, m0, m1 in month_windows(bars, None, None):
        win_by[(int(year), int(month))] = (m0, m1)

    feats = pd.read_csv(FEATURES_CSV)
    feats = feats[feats["market"].astype(str).str.upper() == "NQ"]
    sel = select_months(feats)
    if smoke > 0:
        sel = sel.head(smoke)

    plans: Dict[str, dict] = {}
    for r in sel.itertuples(index=False):
        year, month = int(r.year), int(r.month)
        if (year, month) not in win_by:
            continue
        t0, t1 = win_by[(year, month)]
        t0n, t1n = _ny_ts(t0), _ny_ts(t1)
        mo = float(r.month_open)
        liq = detect_liquidity_run(
            bars_1h=bars_ny,
            year=year,
            month=month,
            month_open=mo,
            t0=t0n,
            t1=t1n,
            n_days=int(liq_days),
        )
        if liq is None:
            continue
        if liq.side == "up":
            side = "short"
            entry = float(liq.p_liq)
            stop = float(liq.p_liq) + float(liq.ext_pts)
        else:
            side = "long"
            entry = float(liq.p_liq)
            stop = float(liq.p_liq) - float(liq.ext_pts)
        key = "%04d-%02d" % (year, month)
        plans[key] = {
            "year": year,
            "month": month,
            "side": side,
            "liq_side": liq.side,
            "month_open": mo,
            "entry": entry,
            "stop": stop,
            "ext_pts": float(liq.ext_pts),
            "liq_days": int(liq_days),
            "arm_after_ts": _utc_z(liq.t_liq),
            "month_end_ts": _utc_z(t1n),
            "month_start_ts": _utc_z(t0n),
            "conditions": str(getattr(r, "conditions", "") or ""),
        }
    return plans


def _bars_for_plans(
    gby: Dict[date, pd.DataFrame],
    plans: Dict[str, dict],
    instrument: str,
    source: str,
) -> List[Bar]:
    """Concatenate 1m bars for each plan month (full NY session days in month)."""
    out: List[Bar] = []
    for key in sorted(plans.keys()):
        plan = plans[key]
        t0 = pd.Timestamp(plan["month_start_ts"])
        t1 = pd.Timestamp(plan["month_end_ts"])
        if t0.tzinfo is None:
            t0 = t0.tz_localize("UTC")
        if t1.tzinfo is None:
            t1 = t1.tz_localize("UTC")
        t0n = t0.tz_convert(NY)
        t1n = t1.tz_convert(NY)
        # days spanning the month window
        d0 = t0n.date()
        d1 = t1n.date()
        days = sorted(d for d in gby.keys() if d0 <= d <= d1)
        for day in days:
            df = gby.get(day)
            if df is None or df.empty:
                continue
            for ts, row in df.iterrows():
                ts_ny = pd.Timestamp(ts)
                if ts_ny.tzinfo is None:
                    ts_ny = ts_ny.tz_localize(NY)
                else:
                    ts_ny = ts_ny.tz_convert(NY)
                if ts_ny < t0n or ts_ny >= t1n:
                    continue
                o = float(row["open"])
                h = float(row["high"])
                l = float(row["low"])
                c = float(row["close"])
                if min(o, h, l, c) <= 0:
                    continue
                out.append(
                    Bar(
                        instrument=instrument,
                        timeframe="1m",
                        ts=_utc_z(ts_ny),
                        open=o,
                        high=h,
                        low=l,
                        close=c,
                        volume=float(row.get("volume", 0.0) or 0.0),
                        complete=True,
                        source=source,
                    )
                )
    # Engine expects chronological; months are sorted but ensure
    out.sort(key=lambda b: b.ts)
    return out


def run(
    *,
    output_root: Path,
    email: bool = False,
    smoke: int = 0,
    force: bool = True,
    liq_days: int = 2,
    strategy_id: Optional[str] = None,
    dsr_trial_id: str = DSR,
) -> int:
    output_root = Path(output_root).resolve()
    liq_days = int(liq_days)
    sid = strategy_id or (
        "nq_liq_run_fade_1r1_reentry_hp_1m"
        if liq_days == 2
        else "nq_liq_run_fade_1r1_reentry_hp_d%d_1m" % liq_days
    )
    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    state_root = output_root / "states" / sid
    audits_root = output_root / "audits"

    _progress(output_root, "BUILD plans smoke=%d liq_days=%d" % (smoke, liq_days))
    plans = build_hp_month_plans(smoke=smoke, liq_days=liq_days)
    (output_root / "month_plans.json").write_text(
        json.dumps(plans, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _progress(output_root, "PLANS n=%d" % len(plans))
    if not plans:
        raise RuntimeError("no HP month plans")

    market = "NQ"
    tick = 0.25
    pv = 20.0
    POINT_VALUES[market] = pv
    DEFAULT_TICK_SIZE[market] = tick

    cfg = V2B_MARKETS["nq"]
    _progress(output_root, "LOAD 1m %s" % cfg.dbn_path)
    gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    bars = _bars_for_plans(gby, plans, market, str(cfg.dbn_path))
    _progress(output_root, "BARS 1m=%d" % len(bars))

    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {
        "tick_size": tick,
        "entry_qty": ENTRY_QTY,
        "timeframe": "1m",
        "month_plans": plans,
        "max_reentries": 0,
        "liq_days": liq_days,
        "suppress_alerts": True,
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=sid,
                    strategy_type="monthly_open_liq_run_fade",
                    version="v1",
                    instrument=market,
                    broker_instrument=market,
                    account_mode="paper",
                    enabled=True,
                    timeframes="1m",
                    max_contracts=ENTRY_QTY,
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
        tick_size={market: tick},
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
        **hardened_replay_engine_kwargs(
            slippage_ticks=1.0,
            spread_model=_spread(tick),
        ),
    )
    _progress(output_root, "REPLAY start")
    n = len(bars)
    for i, bar in enumerate(bars, start=1):
        engine.process_bar(bar)
        if i % 200000 == 0 or i == n:
            _progress(output_root, "REPLAY %d/%d" % (i, n))
    store.flush_tables()

    fills_path = state_root / "fills.csv"
    last = bars[-1] if bars else None
    units = units_from_live_fills(
        fills_path,
        sid,
        last.ts if last else "",
        last.close if last else None,
    )
    audit = audit_units(
        name="NQ liq-run fade 1:1 HP reentry 1m broker d%d" % liq_days,
        slug=sid,
        source=fills_path,
        bar_source=Path(str(cfg.dbn_path)),
        bars=bars,
        units=units,
        instrument=market,
        notes=(
            "Engine+PaperBroker 1m; HP lookback OR; liq first %d NY days; "
            "unlimited reentry (TP re-arms; stop waits open)." % liq_days
        ),
        output_root=audits_root,
        fee_per_unit=FEE,
    )
    eq_path = audits_root / sid / "equity_curve.csv"
    stress = abs(float(audit.intrabar_mtm_dd_usd))
    net = float(audit.net_usd)
    ns = (net / stress) if stress > 1e-9 else 0.0
    n_entries = 0
    if fills_path.exists():
        try:
            fdf = pd.read_csv(fills_path)
            n_entries = int((fdf["reason"].astype(str) == "entry").sum())
        except Exception:
            n_entries = int(audit.trades)
    else:
        n_entries = int(audit.trades)
    metrics = {
        "strategy_id": sid,
        "liq_days": float(liq_days),
        "n_plans": float(len(plans)),
        "bars_1m": float(len(bars)),
        "units": float(audit.units),
        "trades": float(n_entries),
        "n_entries": float(n_entries),
        "audit_trades": float(audit.trades),
        "net_usd": net,
        "stress_dd": float(audit.intrabar_mtm_dd_usd),
        "ns": ns,
        "win_units": float(audit.win_units),
        "loss_units": float(audit.loss_units),
        "equity_curve": str(eq_path),
        "state_root": str(state_root),
    }
    (output_root / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    path_tip = "2d 1m broker HP: +$552k / N/S 1.03 (183 entries)."
    summary = "\n".join(
        [
            "# NQ liq-run fade 1:1 HP — broker-like **1m** (liq first **%d** days)" % liq_days,
            "",
            "- Engine + PaperBroker; slip 1 tick + spread model",
            "- Universe: lookback HP OR months (**%d** plans)" % len(plans),
            "- Liq run: largest |ext| from month open over first **%d** NY trading days" % liq_days,
            "- Structure: limit @ p_liq, SL=1R, target=month open, qty **%d**" % ENTRY_QTY,
            "- Re-entry: **TP re-arms immediately**; stop → wait open-touch",
            "",
            "## Results",
            "",
            "| Metric | Value |",
            "|---|---:|",
            "| Entries | %d |" % n_entries,
            "| Units | %d |" % int(audit.units),
            "| Net $ | %+.0f |" % net,
            "| Stress DD $ | %.0f |" % stress,
            "| N/S | %.2f |" % ns,
            "",
            path_tip,
            "",
            "Hub: `%s`" % output_root,
            "",
            "Stance: broker-like 1m (liq-days sensitivity).",
            "",
        ]
    )
    (output_root / "SUMMARY.md").write_text(summary, encoding="utf-8")
    (output_root / "EMAIL.txt").write_text(summary, encoding="utf-8")
    (output_root / "RUN_COMPLETE.json").write_text(
        json.dumps({"ok": True, "metrics": metrics}, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _progress(output_root, "DONE %s" % json.dumps(metrics))

    log_run(
        run_class="broker_like",
        variant_slug=sid,
        instrument="NQ",
        hub_path=str(output_root.relative_to(REPO)),
        net_usd=net,
        stress_dd_usd=-stress,
        ns=ns,
        trades=int(n_entries),
        dsr_trial_id=dsr_trial_id,
        equity_curve_path=eq_path if eq_path.exists() else None,
        meta={
            "qty": ENTRY_QTY,
            "timeframe": "1m",
            "universe": "hp",
            "liq_days": liq_days,
            "reentry": "tp_rearm_stop_open",
        },
        notes="1m Engine HP liq-run fade 1:1 reentry; liq_days=%d" % liq_days,
    )
    if email:
        send_email(
            subject="potions: NQ liq-run fade HP 1m broker d%d" % liq_days,
            body=summary,
        )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--email", action="store_true")
    p.add_argument("--smoke", type=int, default=0, help="Only first N HP months")
    p.add_argument("--force", action="store_true", default=True)
    p.add_argument("--liq-days", type=int, default=2, help="First N NY trading days for liq run")
    p.add_argument("--dsr", type=str, default=DSR)
    args = p.parse_args(argv)
    try:
        return run(
            output_root=args.output_root,
            email=args.email,
            smoke=args.smoke,
            force=args.force,
            liq_days=args.liq_days,
            dsr_trial_id=args.dsr,
        )
    except Exception:
        tb = traceback.format_exc()
        _progress(args.output_root, "FAILED\n" + tb)
        if args.email:
            send_email(subject="potions: liq-run HP 1m broker FAILED", body=tb[-4000:])
        raise


if __name__ == "__main__":
    raise SystemExit(main())