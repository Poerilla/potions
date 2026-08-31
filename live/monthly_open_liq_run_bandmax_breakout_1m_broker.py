"""HP research: band-max fade + envelope range-breakout sidecar (1m Engine).

Variant A — band-max fade (same plugin as ``monthly_open_liq_run_fade``):
  liq sets direction; limit @ dn-max (long) / up-max (short); target month open;
  SL distance = liq-run size; TP re-arms / stop waits open-touch.

Variant B — range breakout sidecar (``monthly_open_liq_range_breakout``):
  after ``t_liq``, envelope of chart lines = range; 4h close outside → limit at
  boundary; SL=2×liq; target=range size; max 2 attempts.

Hubs under ``live/state/monthly_open_atr_extension_band/``.
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
from .monthly_open_liq_run_bandmax_and_range_breakout import (
    build_enriched_hp_plans,
    write_causality_md,
)
from .monthly_open_liq_run_fade_1r1_reentry_1m_broker import _bars_for_plans, _spread
from .notify_email import send_email
from .replay_audit import POINT_VALUES, audit_units, units_from_live_fills
from .replay_realism import hardened_replay_engine_kwargs
from .run_ledger import log_run
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import MARKETS as V2B_MARKETS, load_1m_by_ny_date_any
from .verification import QuietPaperVerificationProvider

REPO = Path(__file__).resolve().parents[1]
BAND_ROOT = REPO / "live" / "state" / "monthly_open_atr_extension_band"
HUB_BANDMAX = BAND_ROOT / "liq_run_fade_bandmax_1r1_reentry_hp_1m_broker"
HUB_BREAKOUT = BAND_ROOT / "liq_run_range_breakout_hp_1m_broker"
FEE = 1.50
ENTRY_QTY = 10
DSR_BANDMAX = "TRL-2026-00145"
DSR_BREAKOUT = "TRL-2026-00146"


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _fade_plans(enriched: Dict[str, dict]) -> Dict[str, dict]:
    """Plugin-facing plans: entry/stop already band-max in enriched."""
    out: Dict[str, dict] = {}
    for k, p in enriched.items():
        out[k] = {
            "year": p["year"],
            "month": p["month"],
            "side": p["side"],
            "liq_side": p["liq_side"],
            "month_open": p["month_open"],
            "entry": p["entry"],
            "stop": p["stop"],
            "ext_pts": p["ext_pts"],
            "liq_days": p.get("liq_days", 2),
            "arm_after_ts": p["arm_after_ts"],
            "month_end_ts": p["month_end_ts"],
            "month_start_ts": p["month_start_ts"],
            "conditions": p.get("conditions", ""),
            "entry_mode": "band_max",
            "up_max": p["up_max"],
            "dn_max": p["dn_max"],
        }
    return out


def _breakout_plans(enriched: Dict[str, dict]) -> Dict[str, dict]:
    out: Dict[str, dict] = {}
    for k, p in enriched.items():
        out[k] = {
            "year": p["year"],
            "month": p["month"],
            "month_open": p["month_open"],
            "ext_pts": p["ext_pts"],
            "range_high": p["range_high"],
            "range_low": p["range_low"],
            "range_size": p["range_size"],
            "arm_after_ts": p["arm_after_ts"],
            "month_end_ts": p["month_end_ts"],
            "month_start_ts": p["month_start_ts"],
            "liq_side": p["liq_side"],
            "p_liq": p["p_liq"],
            "liq_stop": p["liq_stop"],
            "conditions": p.get("conditions", ""),
        }
    return out


def _run_engine(
    *,
    output_root: Path,
    sid: str,
    strategy_type: str,
    plans: Dict[str, dict],
    config_extra: Optional[dict] = None,
    smoke: int = 0,
    force: bool = True,
) -> dict:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    state_root = output_root / "states" / sid
    audits_root = output_root / "audits"

    use_plans = plans
    if smoke > 0:
        keys = sorted(plans.keys())[: int(smoke)]
        use_plans = {k: plans[k] for k in keys}

    (output_root / "month_plans.json").write_text(
        json.dumps(use_plans, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_causality_md(output_root / "CAUSALITY.md")
    _progress(output_root, "PLANS n=%d type=%s" % (len(use_plans), strategy_type))
    if not use_plans:
        raise RuntimeError("no plans")

    market = "NQ"
    tick = 0.25
    pv = 20.0
    POINT_VALUES[market] = pv
    DEFAULT_TICK_SIZE[market] = tick

    cfg = V2B_MARKETS["nq"]
    _progress(output_root, "LOAD 1m")
    gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    bars = _bars_for_plans(gby, use_plans, market, str(cfg.dbn_path))
    _progress(output_root, "BARS 1m=%d" % len(bars))

    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {
        "tick_size": tick,
        "entry_qty": ENTRY_QTY,
        "timeframe": "1m",
        "month_plans": use_plans,
        "suppress_alerts": True,
    }
    if config_extra:
        payload.update(config_extra)
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=sid,
                    strategy_type=strategy_type,
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
        name="NQ %s" % sid,
        slug=sid,
        source=fills_path,
        bar_source=Path(str(cfg.dbn_path)),
        bars=bars,
        units=units,
        instrument=market,
        notes=strategy_type,
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
    return {
        "strategy_id": sid,
        "strategy_type": strategy_type,
        "n_plans": float(len(use_plans)),
        "bars_1m": float(len(bars)),
        "units": float(audit.units),
        "trades": float(n_entries),
        "n_entries": float(n_entries),
        "net_usd": net,
        "stress_dd": float(audit.intrabar_mtm_dd_usd),
        "ns": ns,
        "win_units": float(audit.win_units),
        "loss_units": float(audit.loss_units),
        "equity_curve": str(eq_path),
        "state_root": str(state_root),
        "fills_path": str(fills_path),
        "eq_path": eq_path,
        "audits_root": str(audits_root),
    }


def _write_hub_summary(
    output_root: Path,
    metrics: dict,
    *,
    title: str,
    bullets: List[str],
    stance: str,
    dsr: str,
    notes: str,
) -> str:
    net = float(metrics["net_usd"])
    stress = abs(float(metrics["stress_dd"]))
    ns = float(metrics["ns"])
    n_entries = int(metrics["n_entries"])
    lines = [
        "# %s" % title,
        "",
        *["- %s" % b for b in bullets],
        "",
        "## Results",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Plans | %d |" % int(metrics["n_plans"]),
        "| Entries | %d |" % n_entries,
        "| Units | %d |" % int(metrics["units"]),
        "| Net $ | %+.0f |" % net,
        "| Stress DD $ | %.0f |" % stress,
        "| N/S | %.2f |" % ns,
        "",
        "Compare: base HP 1m liq@p_liq reentry ≈ +$552k / N/S 1.03 (183 entries).",
        "",
        "Hub: `%s`" % output_root,
        "",
        "Stance: %s" % stance,
        "",
        "See `CAUSALITY.md` for when bands / range / SL are live-known.",
        "",
    ]
    summary = "\n".join(lines)
    (output_root / "SUMMARY.md").write_text(summary, encoding="utf-8")
    (output_root / "EMAIL.txt").write_text(summary, encoding="utf-8")
    (output_root / "metrics.json").write_text(
        json.dumps({k: v for k, v in metrics.items() if k not in {"eq_path", "audits_root"}}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    (output_root / "RUN_COMPLETE.json").write_text(
        json.dumps({"ok": True, "metrics": {k: v for k, v in metrics.items() if not isinstance(v, Path)}}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    eq = metrics.get("eq_path")
    log_run(
        run_class="broker_like" if "fade" in str(metrics.get("strategy_type")) else "sidecar",
        variant_slug=str(metrics["strategy_id"]),
        instrument="NQ",
        hub_path=str(output_root.relative_to(REPO)),
        net_usd=net,
        stress_dd_usd=-stress,
        ns=ns,
        trades=n_entries,
        dsr_trial_id=dsr,
        equity_curve_path=eq if eq and Path(eq).exists() else None,
        meta={"qty": ENTRY_QTY, "timeframe": "1m", "universe": "hp"},
        notes=notes,
    )
    return summary


def run(
    *,
    which: str = "both",
    email: bool = False,
    smoke: int = 0,
    force: bool = True,
    liq_days: int = 2,
    sl_mode: str = "2x_liq",
) -> int:
    _progress(BAND_ROOT, "BUILD enriched plans smoke=%d liq_days=%d" % (smoke, liq_days))
    enriched = build_enriched_hp_plans(liq_days=liq_days, smoke=smoke)
    _progress(BAND_ROOT, "ENRICHED n=%d" % len(enriched))
    summaries: List[str] = []

    if which in {"both", "bandmax"}:
        hub = HUB_BANDMAX
        sid = "nq_liq_run_fade_bandmax_1r1_reentry_hp_1m"
        _progress(hub, "START bandmax fade")
        m = _run_engine(
            output_root=hub,
            sid=sid,
            strategy_type="monthly_open_liq_run_fade",
            plans=_fade_plans(enriched),
            config_extra={"max_reentries": 0, "entry_mode": "band_max"},
            smoke=0,  # already smoked in enriched
            force=force,
        )
        # Persist full enriched for charts
        (hub / "enriched_plans.json").write_text(
            json.dumps(enriched if smoke <= 0 else {k: enriched[k] for k in sorted(enriched)[:smoke]}, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        s = _write_hub_summary(
            hub,
            m,
            title="NQ HP band-max fade 1:1 reentry (1m broker)",
            bullets=[
                "Liq run sets **direction** only (first %d NY days)" % liq_days,
                "Limit @ **dn max** (long) / **up max** (short)",
                "Target = month open; SL distance = **liq-run size**",
                "Re-entry: TP re-arms; stop → wait open-touch",
                "Engine + PaperBroker 1m; slip 1 tick + spread",
            ],
            stance="research vs p_liq entry baseline",
            dsr=DSR_BANDMAX,
            notes="band-max fade HP 1m broker",
        )
        summaries.append(s)
        _progress(hub, "DONE bandmax %s" % json.dumps({k: m[k] for k in ("n_entries", "net_usd", "ns")}))

    if which in {"both", "breakout"}:
        hub = HUB_BREAKOUT
        sid = "nq_liq_range_breakout_hp_1m"
        _progress(hub, "START range breakout sidecar")
        m = _run_engine(
            output_root=hub,
            sid=sid,
            strategy_type="monthly_open_liq_range_breakout",
            plans=_breakout_plans(enriched),
            config_extra={"max_attempts": 2, "sl_mode": sl_mode},
            smoke=0,
            force=force,
        )
        (hub / "enriched_plans.json").write_text(
            json.dumps(enriched if smoke <= 0 else {k: enriched[k] for k in sorted(enriched)[:smoke]}, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        s = _write_hub_summary(
            hub,
            m,
            title="NQ HP envelope range breakout sidecar (1m broker)",
            bullets=[
                "Range = envelope of month open + up/dn bands + p_liq + 1R SL (known at t_liq)",
                "No signal during liq window; **4h close** outside → limit at boundary",
                "SL = **%s**; target = range size; max **2** attempts" % sl_mode,
                "Session-gap void: no fill if open gaps through/adverse (esp. near SL); retag required",
                "Engine + PaperBroker 1m; slip 1 tick + spread",
            ],
            stance="sidecar research (separate from fade book)",
            dsr=DSR_BREAKOUT,
            notes="range breakout sidecar HP 1m; sl_mode=%s" % sl_mode,
        )
        summaries.append(s)
        _progress(hub, "DONE breakout %s" % json.dumps({k: m[k] for k in ("n_entries", "net_usd", "ns")}))

    combined = "\n\n---\n\n".join(summaries) if summaries else "no runs"
    (BAND_ROOT / "BANDMAX_BREAKOUT_EMAIL.txt").write_text(combined, encoding="utf-8")
    if email and summaries:
        send_email(
            subject="potions: NQ HP bandmax fade + range breakout sidecar",
            body=combined,
        )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--which", choices=("both", "bandmax", "breakout"), default="both")
    p.add_argument("--email", action="store_true")
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--force", action="store_true", default=True)
    p.add_argument("--liq-days", type=int, default=2)
    p.add_argument("--sl-mode", choices=("2x_liq", "range"), default="2x_liq")
    args = p.parse_args(argv)
    try:
        return run(
            which=args.which,
            email=args.email,
            smoke=args.smoke,
            force=args.force,
            liq_days=args.liq_days,
            sl_mode=args.sl_mode,
        )
    except Exception:
        tb = traceback.format_exc()
        _progress(BAND_ROOT, "FAILED\n" + tb)
        if args.email:
            send_email(subject="potions: bandmax/breakout FAILED", body=tb[-4000:])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
