"""Broker stress: FBO with runner@2R and BE only after TP2 (1R).

Close-SL. First-break opposite.
Ladder: TP1=0.25R, TP2=1R, runner limit @ 2R.
BE moves only after TP2 fills (not after TP1).

Structures: 1/1/1, 1/1/3, 1/2/3.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from .broker_like_replays import BrokerReplaySpec, _runtime_config
from .engine import Engine, bars_from_csv
from .eurusd_overnight_sweep import FEE_PER_UNIT, INSTRUMENT, MARKET, TICK
from .fx_data import ensure_eurusd_platform_files
from .models import StrategyInstance, as_row
from .replay_audit import POINT_VALUES, audit_units, read_bars, units_from_live_fills
from .replay_manifest import write_run_manifest
from .reporting import generate_market_close_report
from .store import FlatFileStore


REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "eurusd_monthly_orb_fbo_runner2r_be_tp2_broker"

# label, entry, tp1, tp2  (runner = entry - tp1 - tp2)
STRUCTURES: List[Tuple[str, int, int, int]] = [
    ("1_1_1", 3, 1, 1),
    ("1_1_3", 5, 1, 1),
    ("1_2_3", 6, 1, 2),
]


def _specs() -> List[BrokerReplaySpec]:
    out: List[BrokerReplaySpec] = []
    for label, entry, tp1, tp2 in STRUCTURES:
        runner = entry - tp1 - tp2
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
            "be_after": "tp2",
            "entry_mode": "first_break_opposite",
            "stop_mode": "close",
            "flip_after_stop": False,
            "eod_stop_to_or_mid": False,
            "record_levels": False,
        }
        out.append(
            BrokerReplaySpec(
                name="FBO %s runner@2R BE@TP2" % label,
                slug="monthly_orb_fbo_r2r_be2_%s" % label,
                strategy_type="monthly_orb_v2b_oco",
                max_contracts=entry,
                config=cfg,
                notes="1@0.25R / %d@1R / %d@2R; BE after TP2; close-SL." % (tp2, runner),
            )
        )
    return out


SPECS = _specs()


def _campaign_wr(fills: pd.DataFrame) -> dict:
    fills = fills.copy()
    fills["ts"] = pd.to_datetime(fills["ts"])
    pnls = []
    hit_tp2 = hit_tp3 = 0
    for _, g in fills.groupby("trade_id"):
        g = g.sort_values("ts")
        e = g[g.reason == "entry"]
        if e.empty:
            continue
        e = e.iloc[0]
        pnl = -FEE_PER_UNIT * float(e.quantity)
        reasons = set(g[g.reason != "entry"].reason)
        if "tp2" in reasons:
            hit_tp2 += 1
        if "tp3" in reasons:
            hit_tp3 += 1
        for _, r in g[g.reason != "entry"].iterrows():
            pts = (r.price - e.price) * r.quantity if e.side == "buy" else (e.price - r.price) * r.quantity
            pnl += pts * 100000.0 - FEE_PER_UNIT * float(r.quantity)
        pnls.append(pnl)
    if not pnls:
        return {"campaigns": 0, "win_rate_pct": 0.0, "pct_tp2": 0.0, "pct_tp3": 0.0}
    a = np.array(pnls, dtype=float)
    n = len(a)
    return {
        "campaigns": n,
        "win_rate_pct": float(100.0 * (a > 0).mean()),
        "pct_tp2": float(100.0 * hit_tp2 / n),
        "pct_tp3": float(100.0 * hit_tp3 / n),
    }


def run(output_root: Path, force: bool = False) -> None:
    POINT_VALUES.setdefault(INSTRUMENT, 100000.0)
    ensure_eurusd_platform_files(REPO, force=False)
    daily_path = REPO / "fx" / "eurusd_daily.csv"
    output_root.mkdir(parents=True, exist_ok=True)
    bars = bars_from_csv(daily_path, INSTRUMENT, "D", source=str(daily_path))
    print("Loaded %d EURUSD daily bars" % len(bars), flush=True)

    rows = []
    for spec in SPECS:
        strategy_id = "%s_%s" % (MARKET, spec.slug)
        state_root = output_root / "states" / strategy_id
        print("START %s" % strategy_id, flush=True)
        if force and state_root.exists():
            shutil.rmtree(state_root)
        store = FlatFileStore(state_root, defer_table_writes=True)
        store.ensure()
        instance = StrategyInstance(
            strategy_id=strategy_id,
            strategy_type=spec.strategy_type,
            version="v1",
            instrument=INSTRUMENT,
            broker_instrument=INSTRUMENT,
            account_mode="paper",
            enabled=True,
            timeframes="D",
            max_contracts=spec.max_contracts,
            max_open_orders=64,
            config_json=json.dumps(_runtime_config(spec, bars), sort_keys=True),
        )
        store.upsert_row("strategy_instances", "strategy_id", as_row(instance))
        Engine(store=store, slippage_ticks=1.0, tick_size={INSTRUMENT: TICK}).replay_bars(bars)
        store.flush_tables()
        generate_market_close_report(store, bars[-1].ts[:10])
        replay_bars = read_bars(state_root / "bars" / ("%s_D.csv" % INSTRUMENT), "ts")
        units = units_from_live_fills(
            state_root / "fills.csv",
            strategy_id,
            replay_bars[-1].ts,
            replay_bars[-1].close,
        )
        audit = audit_units(
            name="EURUSD %s" % spec.name,
            slug=strategy_id,
            source=state_root / "fills.csv",
            bar_source=state_root / "bars" / ("%s_D.csv" % INSTRUMENT),
            bars=replay_bars,
            units=units,
            instrument=INSTRUMENT,
            notes=spec.notes + " fee=$%.2f/unit." % FEE_PER_UNIT,
            output_root=output_root / "audits",
            fee_per_unit=FEE_PER_UNIT,
        )
        ratio = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
        fills = pd.read_csv(state_root / "fills.csv")
        wr = _campaign_wr(fills)
        reasons = fills["reason"].value_counts().to_dict()
        struct = spec.slug.split("_")[-3] + "/" + spec.slug.split("_")[-2] + "/" + spec.slug.split("_")[-1]
        # slug ends with 1_1_1 etc
        struct = spec.slug.replace("monthly_orb_fbo_r2r_be2_", "").replace("_", "/")
        row = {
            "structure": struct,
            "slug": strategy_id,
            "campaigns": str(wr["campaigns"]),
            "win_rate_pct": "%.1f" % wr["win_rate_pct"],
            "pct_hit_1R": "%.1f" % wr["pct_tp2"],
            "pct_hit_2R": "%.1f" % wr["pct_tp3"],
            "net_usd": "%.2f" % audit.net_usd,
            "intrabar_mtm_dd_usd": "%.2f" % audit.intrabar_mtm_dd_usd,
            "net_over_stress_dd": "%.2f" % ratio,
            "tp3_fills": str(reasons.get("tp3", 0)),
            "units": str(audit.units),
        }
        rows.append(row)
        print(
            "DONE %s WR=%s%% Net=$%s Stress=$%s N/S=%s hit1R=%s%% hit2R=%s%%"
            % (
                strategy_id,
                row["win_rate_pct"],
                row["net_usd"],
                row["intrabar_mtm_dd_usd"],
                row["net_over_stress_dd"],
                row["pct_hit_1R"],
                row["pct_hit_2R"],
            ),
            flush=True,
        )

    with (output_root / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    lines = [
        "# EURUSD FBO — runner@2R, BE only after TP2 (1R)",
        "",
        "First-break opposite, close-SL.",
        "Targets: **0.25R / 1R / 2R**. Stop stays at OR opposite until **TP2 (1R)** → then BE.",
        "Fee $%.2f/unit." % FEE_PER_UNIT,
        "",
        "| Structure | WR | Hit 1R | Hit 2R | Net | Stress DD | Net/Stress |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| %s | %s%% | %s%% | %s%% | $%s | $%s | %s |"
            % (
                row["structure"],
                row["win_rate_pct"],
                row["pct_hit_1R"],
                row["pct_hit_2R"],
                row["net_usd"],
                row["intrabar_mtm_dd_usd"],
                row["net_over_stress_dd"],
            )
        )
    lines.extend(
        [
            "",
            "Prior close-SL reference (runner open-ended, BE after TP1):",
            "- 1/1/1: +$31.4k / 0.70 Net/Stress",
            "- 1/1/3: +$56.9k / 0.80 Net/Stress",
            "",
        ]
    )
    (output_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    write_run_manifest(
        output_root,
        data_inputs=[daily_path],
        output_paths=[output_root / "summary.csv", output_root / "SUMMARY.md"],
        broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": FEE_PER_UNIT, "tick_size": TICK},
        causality_mode="audit",
        extra={"driver": "eurusd_monthly_orb_fbo_runner2r_be_tp2_broker"},
    )
    print("Wrote %s" % (output_root / "SUMMARY.md"), flush=True)


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=OUT)
    p.add_argument("--force", action="store_true")
    args = p.parse_args(argv)
    run(args.output_root, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
