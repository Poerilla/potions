"""Broker stress: first-break opposite with wick (strict 1R) stops.

Same entry / ladder family as the close-SL sweep, but ``stop_mode=wick``:
resting stop at opposite OR (= 1R from boundary entry). After TP1 → BE.
Wicks can stop out.
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
OUT = REPO / "live" / "state" / "eurusd_monthly_orb_fbo_wick_sl_sweep_broker"

# (label, entry_qty, tp1_qty, tp2_qty)
STRUCTURES: List[Tuple[str, int, int, int]] = [
    ("1_0_0", 1, 1, 0),  # 1 @ 0.25R
    ("0_1_0", 1, 0, 1),  # 1 @ 1R
    ("1_1_0", 2, 1, 1),  # 1 @ 0.25R + 1 @ 1R
    ("1_1_1", 3, 1, 1),  # + 1 runner
    ("1_1_2", 4, 1, 1),  # + 2 runners
    ("1_1_3", 5, 1, 1),  # + 3 runners
]


def _specs() -> List[BrokerReplaySpec]:
    out: List[BrokerReplaySpec] = []
    for label, entry, tp1, tp2 in STRUCTURES:
        cfg = {
            "allow_shorts": True,
            "or_sessions": 3,
            "max_trades_per_month": 2,
            "entry_qty": entry,
            "tp1_qty": tp1,
            "tp2_qty": tp2,
            "tp1_r": 0.25,
            "tp2_r": 1.0,
            "entry_mode": "first_break_opposite",
            "stop_mode": "wick",
            "flip_after_stop": False,
            "record_levels": False,
        }
        out.append(
            BrokerReplaySpec(
                name="FBO wick-SL %s" % label,
                slug="monthly_orb_fbo_wick_%s" % label,
                strategy_type="monthly_orb_v2b_oco",
                max_contracts=entry,
                config=cfg,
                notes="First-break opposite, wick stop at 1R (OR opposite), BE after TP1.",
            )
        )
    return out


SPECS = _specs()


def _campaign_wr(fills: pd.DataFrame) -> dict:
    if fills is None or len(fills) == 0:
        return {"campaigns": 0, "win_rate_pct": 0.0}
    fills = fills.copy()
    fills["ts"] = pd.to_datetime(fills["ts"])
    pnls = []
    for _, g in fills.groupby("trade_id"):
        g = g.sort_values("ts")
        e = g[g.reason == "entry"]
        if e.empty:
            continue
        e = e.iloc[0]
        pnl = -FEE_PER_UNIT * float(e.quantity)
        for _, r in g[g.reason != "entry"].iterrows():
            pts = (r.price - e.price) * r.quantity if e.side == "buy" else (e.price - r.price) * r.quantity
            pnl += pts * 100000.0 - FEE_PER_UNIT * float(r.quantity)
        pnls.append(pnl)
    if not pnls:
        return {"campaigns": 0, "win_rate_pct": 0.0}
    a = np.array(pnls, dtype=float)
    return {"campaigns": int(len(a)), "win_rate_pct": float(100.0 * (a > 0).mean())}


def run(output_root: Path, force: bool = False) -> None:
    POINT_VALUES.setdefault(INSTRUMENT, 100000.0)
    ensure_eurusd_platform_files(REPO, force=False)
    daily_path = REPO / "fx" / "eurusd_daily.csv"
    output_root.mkdir(parents=True, exist_ok=True)
    bars = bars_from_csv(daily_path, INSTRUMENT, "D", source=str(daily_path))
    print("Loaded %d EURUSD daily bars" % len(bars), flush=True)

    summary_rows = []
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
        row = {
            "structure": spec.slug.split("wick_")[-1],
            "slug": strategy_id,
            "entry_qty": str(spec.config["entry_qty"]),
            "campaigns": str(wr["campaigns"]),
            "win_rate_pct": "%.1f" % wr["win_rate_pct"],
            "trades": str(audit.trades),
            "units": str(audit.units),
            "net_usd": "%.2f" % audit.net_usd,
            "close_mtm_dd_usd": "%.2f" % audit.close_mtm_dd_usd,
            "intrabar_mtm_dd_usd": "%.2f" % audit.intrabar_mtm_dd_usd,
            "net_over_stress_dd": "%.2f" % ratio,
            "stop_fills": str(reasons.get("stop", 0) + reasons.get("runner_stop", 0)),
            "tp1_fills": str(reasons.get("tp1", 0)),
            "tp2_fills": str(reasons.get("tp2", 0)),
        }
        summary_rows.append(row)
        print(
            "DONE %s WR=%.1f%% Net=$%.2f StressDD=$%.2f Net/Stress=%.2f stops=%s"
            % (
                strategy_id,
                wr["win_rate_pct"],
                audit.net_usd,
                audit.intrabar_mtm_dd_usd,
                ratio,
                row["stop_fills"],
            ),
            flush=True,
        )

    with (output_root / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    # Close-SL reference from prior runs (approx)
    close_ref = {
        "1_0_0": (80.1, 4332, 0.22),
        "0_1_0": (54.9, -5690, -0.22),
        "1_1_0": (65.1, 19319, 0.60),
        "1_1_1": (57.2, 31395, 0.70),
        "1_1_2": (54.9, 44131, 0.78),
        "1_1_3": (50.3, 56867, 0.80),
    }
    lines = [
        "# EURUSD first-break opposite — wick SL (strict 1R) structure sweep",
        "",
        "Entry: ignore first OR break → arm opposite.",
        "Stop: **wick / resting** at opposite OR (= **1R** from boundary entry); BE after TP1.",
        "Ladder targets: TP1=0.25R, TP2=1R. Max 2/month, month-end flatten. Fee $%.2f/unit."
        % FEE_PER_UNIT,
        "",
        "| Structure | WR | Net | Stress DD | Net/Stress | Stop fills | vs close-SL Net |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        s = row["structure"]
        cref = close_ref.get(s)
        delta = ""
        if cref:
            delta = "$%+.0f" % (float(row["net_usd"]) - cref[1])
        lines.append(
            "| %s | %s%% | $%s | $%s | %s | %s | %s |"
            % (
                s.replace("_", "/"),
                row["win_rate_pct"],
                row["net_usd"],
                row["intrabar_mtm_dd_usd"],
                row["net_over_stress_dd"],
                row["stop_fills"],
                delta or "—",
            )
        )
    lines.extend(
        [
            "",
            "## Close-SL reference (prior)",
            "",
            "| Structure | WR | Net | Net/Stress |",
            "|---|---:|---:|---:|",
        ]
    )
    for s, (wr, net, ratio) in close_ref.items():
        lines.append("| %s | %.1f%% | $%+.0f | %.2f |" % (s.replace("_", "/"), wr, net, ratio))
    lines.append("")
    (output_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    write_run_manifest(
        output_root,
        data_inputs=[daily_path],
        output_paths=[output_root / "summary.csv", output_root / "SUMMARY.md"],
        broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": FEE_PER_UNIT, "tick_size": TICK},
        causality_mode="audit",
        extra={"driver": "eurusd_monthly_orb_fbo_wick_sl_sweep_broker", "variants": [s.slug for s in SPECS]},
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
