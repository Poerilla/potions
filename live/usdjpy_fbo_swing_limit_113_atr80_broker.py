"""USDJPY FBO 1/1/3 atr80 — swing-limit fade variant (broker-like).

Same book as promoted FBO atr80 (ignore first OR break, fade opposite,
1@0.25R / 1@1R / 3@2R absolute OR-boundary targets, BE after TP25, close-SL,
atr80 filter) but entry is a **limit at the confirmed 3-bar swing** created by
that first breakout (swing high after ORH break → short; swing low after ORL
break → long). Stop distance remains **1R** from the fill.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import traceback
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .broker_like_replays import BrokerReplaySpec, _runtime_config
from .engine import Engine, bars_from_csv
from .models import StrategyInstance, as_row
from .notify_email import send_email
from .replay_audit import POINT_VALUES, audit_units, read_bars, units_from_live_fills
from .replay_manifest import write_run_manifest
from .reporting import generate_market_close_report
from .run_ledger import begin_run, complete_run, fail_run
from .store import FlatFileStore


REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "usdjpy_fbo_swing_limit_113_atr80_broker"
INSTRUMENT = "USDJPY"
TICK = 0.001
FEE = 7.0
JPY_USD = 110.0
DSR_TRIAL = "TRL-2026-00151"


def _atr80_filter_csv() -> Path:
    path = OUT / "filters" / "usdjpy_atr80.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Reuse tracker filter if present.
    prior = (
        REPO
        / "live"
        / "state"
        / "fx_cross_pair_tracker_leaders"
        / "filters"
        / "usdjpy_atr80.csv"
    )
    if prior.exists():
        path.write_text(prior.read_text(encoding="utf-8"), encoding="utf-8")
        return path
    d = pd.read_csv(REPO / "fx" / "usdjpy_daily.csv", parse_dates=["date"])
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


def _spec(filt: Path) -> BrokerReplaySpec:
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
        "entry_mode": "first_break_opposite_swing_limit",
        "swing_limit_fbo_targets": True,
        "stop_mode": "close",
        "flip_after_stop": False,
        "eod_stop_to_or_mid": False,
        "record_levels": False,
        "entry_filter_csv": str(filt),
    }
    return BrokerReplaySpec(
        name="USDJPY FBO swing-limit 1/1/3 atr80",
        slug="fbo_swing_limit_1_1_3_atr80_usdjpy",
        strategy_type="monthly_orb_v2b_oco",
        max_contracts=5,
        config=cfg,
        notes="Ignore first break → 3-bar swing limit fade; FBO absolute targets; 1R stop from fill; atr80.",
    )


def run(output_root: Path, force: bool = False, do_email: bool = False) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    POINT_VALUES[INSTRUMENT] = 100000.0
    DEFAULT_TICK_SIZE[INSTRUMENT] = TICK
    filt = _atr80_filter_csv()
    spec = _spec(filt)
    daily_path = REPO / "fx" / "usdjpy_daily.csv"
    bars = bars_from_csv(daily_path, INSTRUMENT, "D", source=str(daily_path))
    sid = spec.slug
    state_root = output_root / "states" / sid
    rid = begin_run(
        run_class="broker_like",
        variant_slug=sid,
        instrument=INSTRUMENT,
        hub_path=str(output_root),
        dsr_trial_id=DSR_TRIAL,
        notes="swing-limit FBO 1/1/3 atr80",
        meta={"entry_mode": "first_break_opposite_swing_limit", "structure": "1/1/3"},
    )
    print("Loaded %d USDJPY daily bars" % len(bars), flush=True)
    try:
        if force and state_root.exists():
            shutil.rmtree(state_root)
        store = FlatFileStore(state_root, defer_table_writes=True)
        store.ensure()
        inst = StrategyInstance(
            strategy_id=sid,
            strategy_type=spec.strategy_type,
            version="v1",
            instrument=INSTRUMENT,
            broker_instrument=INSTRUMENT,
            account_mode="paper",
            enabled=True,
            timeframes="D",
            max_contracts=5,
            max_open_orders=64,
            config_json=json.dumps(_runtime_config(spec, bars), sort_keys=True),
        )
        store.upsert_row("strategy_instances", "strategy_id", as_row(inst))
        Engine(store=store, slippage_ticks=1.0, tick_size={INSTRUMENT: TICK}).replay_bars(bars)
        store.flush_tables()
        generate_market_close_report(store, bars[-1].ts[:10])
        rb = read_bars(state_root / "bars" / ("%s_D.csv" % INSTRUMENT), "ts")
        units = units_from_live_fills(state_root / "fills.csv", sid, rb[-1].ts, rb[-1].close)
        audit = audit_units(
            name=spec.name,
            slug=sid,
            source=state_root / "fills.csv",
            bar_source=state_root / "bars" / ("%s_D.csv" % INSTRUMENT),
            bars=rb,
            units=units,
            instrument=INSTRUMENT,
            notes=spec.notes,
            output_root=output_root / "audits",
            fee_per_unit=FEE,
        )
        ns = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
        net_usd = audit.net_usd / JPY_USD
        stress_usd = audit.intrabar_mtm_dd_usd / JPY_USD
        close_usd = audit.close_mtm_dd_usd / JPY_USD

        # Baseline comparison
        base = (
            REPO
            / "live"
            / "state"
            / "fx_cross_pair_tracker_leaders"
            / "summary.csv"
        )
        base_ns = base_net = None
        if base.exists():
            df = pd.read_csv(base)
            hit = df[(df.pair == "USDJPY") & (df.variant == "1_1_3_atr80")]
            if len(hit):
                base_ns = float(hit.iloc[0]["ns"])
                base_net = float(hit.iloc[0]["net_usd_approx"])

        row = {
            "variant": "swing_limit_1_1_3_atr80",
            "instrument": INSTRUMENT,
            "trades": audit.trades,
            "units": audit.units,
            "net_jpy": round(audit.net_usd, 2),
            "stress_jpy": round(audit.intrabar_mtm_dd_usd, 2),
            "ns": round(ns, 2),
            "net_usd_approx": round(net_usd, 2),
            "stress_usd_approx": round(stress_usd, 2),
            "baseline_fbo_atr80_net_usd": base_net,
            "baseline_fbo_atr80_ns": base_ns,
        }
        with (output_root / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(row.keys()))
            w.writeheader()
            w.writerow(row)

        stance = "research"
        if ns >= 4.0 and net_usd > 0:
            stance = "promote-candidate vs baseline"
        elif ns >= 1.0 and net_usd > 0:
            stance = "retain/research"
        elif net_usd > 0:
            stance = "weak — reject promote"
        else:
            stance = "reject"

        lines = [
            "# USDJPY FBO swing-limit 1/1/3 atr80 (broker-like)",
            "",
            "Ignore first OR break → wait for **confirmed 3-bar swing** (high after ORH break / "
            "low after ORL break) → **limit** fade at the pivot. Absolute FBO targets from OR "
            "boundary (0.25R / 1R / 2R); stop **1R** beyond fill; BE after TP25; atr80; fee $7.",
            "",
            "| Variant | Trades | Units | Net≈USD | Stress≈USD | N/S | Stance |",
            "|---|---:|---:|---:|---:|---:|---|",
            "| **swing-limit 1/1/3 atr80** | %d | %d | **$%.0f** | $%.0f | **%.2f** | %s |"
            % (audit.trades, audit.units, net_usd, stress_usd, ns, stance),
        ]
        if base_net is not None:
            lines.append(
                "| baseline stop@opposite OR 1/1/3 atr80 | — | — | $%.0f | — | %.2f | banked |"
                % (base_net, base_ns or 0.0)
            )
        lines.extend(
            [
                "",
                "Hub: `%s`" % output_root,
                "DSR: %s" % DSR_TRIAL,
                "",
            ]
        )
        summary = "\n".join(lines)
        (output_root / "SUMMARY.md").write_text(summary, encoding="utf-8")
        (output_root / "EMAIL.txt").write_text(summary, encoding="utf-8")
        write_run_manifest(
            output_root,
            data_inputs=[daily_path, filt],
            output_paths=[output_root / "summary.csv", output_root / "SUMMARY.md"],
            broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": FEE, "tick_size": TICK},
            causality_mode="audit",
            extra={"driver": "usdjpy_fbo_swing_limit_113_atr80_broker", "dsr": DSR_TRIAL},
        )
        complete_run(
            rid,
            net_usd=net_usd,
            stress_dd_usd=stress_usd,
            close_mtm_dd_usd=close_usd,
            ns=ns,
            trades=audit.trades,
            units=audit.units,
            replay_start=str(bars[0].ts)[:10],
            replay_end=str(bars[-1].ts)[:10],
        )
        print(summary, flush=True)
        if do_email:
            send_email(subject="potions: USDJPY FBO swing-limit 1/1/3 atr80 complete", body=summary)
        return output_root / "SUMMARY.md"
    except Exception as exc:
        fail_run(rid, notes=str(exc))
        tb = traceback.format_exc()
        print(tb, flush=True)
        if do_email:
            send_email(subject="potions: USDJPY FBO swing-limit FAILED", body=tb[-4000:])
        raise


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=OUT)
    p.add_argument("--force", action="store_true")
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    try:
        run(args.output_root, force=args.force, do_email=args.email)
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
