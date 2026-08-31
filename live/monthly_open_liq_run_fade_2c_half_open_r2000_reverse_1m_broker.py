"""1m Engine+PaperBroker: HP 2c half+open @ $2k risk + reverse after full stop.

Hub: ``…/liq_run_fade_2c_half_open_r2000_reverse_hp_1m_broker/``
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .models import StrategyInstance, as_row
from .monthly_open_liq_run_fade_1r1_reentry_1m_broker import (
    _bars_for_plans,
    _spread,
    _utc_z,
    build_hp_month_plans,
)
from .notify_email import send_email
from .replay_audit import POINT_VALUES, audit_units, units_from_live_fills
from .replay_realism import hardened_replay_engine_kwargs
from .run_ledger import log_run
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import MARKETS as V2B_MARKETS, load_1m_by_ny_date_any
from .verification import QuietPaperVerificationProvider

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = (
    REPO
    / "live"
    / "state"
    / "monthly_open_atr_extension_band"
    / "liq_run_fade_2c_half_open_r1k_rev2k_hp_1m_broker"
)
FEE = 1.50
ENTRY_QTY = 2
PRIMARY_RISK_USD = 1000.0
REVERSE_RISK_USD = 2000.0
PV = 20.0
PRIMARY_STOP_PTS = PRIMARY_RISK_USD / (ENTRY_QTY * PV)  # 25
REVERSE_STOP_PTS = REVERSE_RISK_USD / (ENTRY_QTY * PV)  # 50
DSR = "TRL-2026-00150"
STRATEGY_ID = "nq_liq_2c_half_open_r1k_rev2k_hp_1m"


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def run(
    *,
    output_root: Path,
    email: bool = False,
    smoke: int = 0,
    force: bool = True,
    enable_reverse: bool = True,
    primary_risk_usd: float = PRIMARY_RISK_USD,
    reverse_risk_usd: float = REVERSE_RISK_USD,
) -> int:
    output_root = Path(output_root).resolve()
    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    dsr_path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    if dsr_path.exists():
        with dsr_path.open("a", encoding="utf-8") as fh:
            fh.write(
                "%s,2026-08-26,cursor,STRATEGY_PLUGIN,nq_liq_2c_half_open_r1k_rev2k_1m,,True,NQ,"
                "2010-06-06,2026-06-16,FULL_SAMPLE,False,,,\"{\\\"primary_risk_usd\\\":%.0f,\\\"reverse_risk_usd\\\":%.0f,\\\"enable_reverse\\\":%s}\","
                "%s/,1,,,,,,,,,,,TRUE,False,1.00,,RUNNING,,,\"1m broker 2c half+open primary $1k + reverse $2k after full stop.\",False\n"
                % (
                    DSR,
                    primary_risk_usd,
                    reverse_risk_usd,
                    str(bool(enable_reverse)).lower(),
                    output_root.relative_to(REPO),
                )
            )

    primary_stop_pts = float(primary_risk_usd) / (ENTRY_QTY * PV)
    reverse_stop_pts = float(reverse_risk_usd) / (ENTRY_QTY * PV)
    _progress(
        output_root,
        "BUILD plans smoke=%d primary=$%.0f (%.1fpt) reverse=$%.0f (%.1fpt) rev=%s"
        % (
            smoke,
            primary_risk_usd,
            primary_stop_pts,
            reverse_risk_usd,
            reverse_stop_pts,
            enable_reverse,
        ),
    )
    plans = build_hp_month_plans(smoke=smoke, liq_days=2)
    for p in plans.values():
        p["primary_stop_pts"] = primary_stop_pts
        p["reverse_stop_pts"] = reverse_stop_pts
        p["primary_risk_usd"] = float(primary_risk_usd)
        p["reverse_risk_usd"] = float(reverse_risk_usd)
        p["stop_pts"] = primary_stop_pts  # legacy
        if p["side"] == "long":
            p["stop"] = float(p["entry"]) - primary_stop_pts
        else:
            p["stop"] = float(p["entry"]) + primary_stop_pts
    (output_root / "month_plans.json").write_text(
        json.dumps(plans, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _progress(output_root, "PLANS n=%d" % len(plans))
    if not plans:
        raise RuntimeError("no HP plans")

    market = "NQ"
    tick = 0.25
    POINT_VALUES[market] = PV
    DEFAULT_TICK_SIZE[market] = tick
    sid = STRATEGY_ID
    state_root = output_root / "states" / sid
    audits_root = output_root / "audits"

    cfg = V2B_MARKETS["nq"]
    _progress(output_root, "LOAD 1m")
    gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    bars = _bars_for_plans(gby, plans, market, str(cfg.dbn_path))
    _progress(output_root, "BARS 1m=%d" % len(bars))

    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {
        "tick_size": tick,
        "entry_qty": ENTRY_QTY,
        "qty_half": 1,
        "qty_open": 1,
        "timeframe": "1m",
        "month_plans": plans,
        "risk_usd": float(primary_risk_usd),
        "primary_risk_usd": float(primary_risk_usd),
        "reverse_risk_usd": float(reverse_risk_usd),
        "point_value": PV,
        "enable_reverse": bool(enable_reverse),
        "suppress_alerts": True,
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=sid,
                    strategy_type="monthly_open_liq_run_fade_2c_half_open",
                    version="v2",
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
        fills_path, sid, last.ts if last else "", last.close if last else None
    )
    audit = audit_units(
        name="NQ 2c half+open $%.0f + rev $%.0f 1m" % (primary_risk_usd, reverse_risk_usd),
        slug=sid,
        source=fills_path,
        bar_source=Path(str(cfg.dbn_path)),
        bars=bars,
        units=units,
        instrument=market,
        notes="2c half+open primary $1k; reverse $2k after full stop; target |entry-open|",
        output_root=audits_root,
        fee_per_unit=FEE,
    )
    eq_path = audits_root / sid / "equity_curve.csv"
    stress = abs(float(audit.intrabar_mtm_dd_usd))
    net = float(audit.net_usd)
    ns = (net / stress) if stress > 1e-9 else 0.0

    n_entries = n_rev_entries = n_stop = n_half = n_open = 0
    if fills_path.exists():
        fdf = pd.read_csv(fills_path)
        reasons = fdf["reason"].astype(str)
        n_entries = int((reasons == "entry").sum())
        n_targets = int((reasons == "target").sum())
        n_half = int((reasons == "target_half").sum()) + n_targets // 2
        n_open = int((reasons == "target_open").sum()) + max(0, n_targets - n_half)
        n_stop = int((reasons == "stop").sum())
        # reverse entries: trade_ids with _tN where N is even-ish / count entries per month >1
        # Prefer trade_id suffix: primary usually t1, reverse t2+
        rev_ids = set()
        for tid, g in fdf.groupby("trade_id"):
            g = g.sort_values("ts")
            if (g["reason"].astype(str) == "entry").any():
                # if this trade's first exit isn't half/open-only primary path and entry
                # follows a stop in same calendar month from another trade — count by seq
                pass
        # Count trade_ids whose entry is the 2nd+ entry in that YYYYMM from strategy_id pattern
        by_month = {}
        for tid, g in fdf.groupby("trade_id"):
            ent = g[g["reason"].astype(str) == "entry"]
            if ent.empty:
                continue
            ts = str(ent.iloc[0]["ts"])
            mk = ts[:7]  # YYYY-MM
            by_month.setdefault(mk, []).append((ts, tid))
        for mk, items in by_month.items():
            items.sort()
            for i, (_, tid) in enumerate(items):
                if i >= 1:
                    rev_ids.add(tid)
        n_rev_entries = len(rev_ids)

    metrics = {
        "strategy_id": sid,
        "primary_risk_usd": float(primary_risk_usd),
        "reverse_risk_usd": float(reverse_risk_usd),
        "primary_stop_pts": primary_stop_pts,
        "reverse_stop_pts": reverse_stop_pts,
        "enable_reverse": bool(enable_reverse),
        "n_plans": float(len(plans)),
        "bars_1m": float(len(bars)),
        "n_entries": float(n_entries),
        "n_rev_entries": float(n_rev_entries),
        "n_half": float(n_half),
        "n_open": float(n_open),
        "n_stop": float(n_stop),
        "units": float(audit.units),
        "net_usd": net,
        "stress_dd": float(audit.intrabar_mtm_dd_usd),
        "ns": ns,
        "win_units": float(audit.win_units),
        "loss_units": float(audit.loss_units),
        "equity_curve": str(eq_path),
    }
    (output_root / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = "\n".join(
        [
            "# NQ HP 2c half+open primary $%.0f + reverse $%.0f — **1m broker**"
            % (primary_risk_usd, reverse_risk_usd),
            "",
            "- Primary: 2 @ p_liq; 1@half 1@open; SL = **%.1f pts** ($%.0f)"
            % (primary_stop_pts, primary_risk_usd),
            "- Reverse after **full initial stop** only: opposite limit @ stop; target |entry−open|; SL = **%.1f pts** ($%.0f)"
            % (reverse_stop_pts, reverse_risk_usd),
            "- enable_reverse = **%s**" % enable_reverse,
            "",
            "## Results",
            "",
            "| Metric | Value |",
            "|---|---:|",
            "| Plans | %d |" % len(plans),
            "| Entries (all) | %d |" % n_entries,
            "| Reverse entries | %d |" % n_rev_entries,
            "| Half / Open / Stop fills | %d / %d / %d |" % (n_half, n_open, n_stop),
            "| Net $ | %+.0f |" % net,
            "| Stress DD $ | %.0f |" % stress,
            "| N/S | %.2f |" % ns,
            "",
            "Hub: `%s`" % output_root,
            "",
            "Stance: 1m broker primary $1k + reverse $2k after full stop.",
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
        dsr_trial_id=DSR,
        equity_curve_path=eq_path if eq_path.exists() else None,
        meta={
            "qty": ENTRY_QTY,
            "primary_risk_usd": primary_risk_usd,
            "reverse_risk_usd": reverse_risk_usd,
            "enable_reverse": enable_reverse,
            "timeframe": "1m",
            "n_rev_entries": n_rev_entries,
        },
        notes="1m 2c half+open primary $1k reverse $2k after full stop",
    )
    if email:
        send_email(subject="potions: NQ 2c primary $1k + reverse $2k 1m broker", body=summary)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--email", action="store_true")
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--no-reverse", action="store_true")
    p.add_argument("--primary-risk-usd", type=float, default=PRIMARY_RISK_USD)
    p.add_argument("--reverse-risk-usd", type=float, default=REVERSE_RISK_USD)
    args = p.parse_args(argv)
    try:
        return run(
            output_root=args.output_root,
            email=args.email,
            smoke=args.smoke,
            enable_reverse=not args.no_reverse,
            primary_risk_usd=args.primary_risk_usd,
            reverse_risk_usd=args.reverse_risk_usd,
        )
    except Exception:
        tb = traceback.format_exc()
        _progress(args.output_root, "FAILED\n" + tb)
        if args.email:
            send_email(subject="potions: 2c r1k/rev2k 1m FAILED", body=tb[-4000:])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
