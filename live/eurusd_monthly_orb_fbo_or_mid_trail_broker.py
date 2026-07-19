"""Broker stress: first-break opposite 1/1/3 with EOD stop → OR mid.

Close-SL kept (wicks ignored; exit only if daily close beyond stop).
After each day in a trade, ratchet stop to OR midpoint (tighten only).
BE after TP1 still applies and wins if tighter than mid.
Structure: 1 @ 0.25R / 1 @ 1R / 3 runner.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path
from typing import List, Optional

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
OUT = REPO / "live" / "state" / "eurusd_monthly_orb_fbo_or_mid_trail_broker"


def _specs() -> List[BrokerReplaySpec]:
    base = {
        "allow_shorts": True,
        "or_sessions": 3,
        "max_trades_per_month": 2,
        "entry_qty": 5,
        "tp1_qty": 1,
        "tp2_qty": 1,
        "tp1_r": 0.25,
        "tp2_r": 1.0,
        "entry_mode": "first_break_opposite",
        "stop_mode": "close",
        "flip_after_stop": False,
        "record_levels": False,
    }
    return [
        BrokerReplaySpec(
            name="FBO 1/1/3 close-SL baseline",
            slug="monthly_orb_fbo_1_1_3_close",
            strategy_type="monthly_orb_v2b_oco",
            max_contracts=5,
            config={**base, "eod_stop_to_or_mid": False},
            notes="Baseline 1/1/3 close-SL, init SL=OR opposite, BE after TP1.",
        ),
        BrokerReplaySpec(
            name="FBO 1/1/3 close-SL EOD→OR mid",
            slug="monthly_orb_fbo_1_1_3_close_or_mid",
            strategy_type="monthly_orb_v2b_oco",
            max_contracts=5,
            config={**base, "eod_stop_to_or_mid": True},
            notes="Close-SL; each EOD ratchet stop to OR mid (tighten only); BE after TP1.",
        ),
    ]


SPECS = _specs()


def _campaign_wr(fills: pd.DataFrame) -> dict:
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
        row = {
            "variant": "or_mid_trail" if spec.config.get("eod_stop_to_or_mid") else "baseline",
            "slug": strategy_id,
            "campaigns": str(wr["campaigns"]),
            "win_rate_pct": "%.1f" % wr["win_rate_pct"],
            "trades": str(audit.trades),
            "units": str(audit.units),
            "net_usd": "%.2f" % audit.net_usd,
            "close_mtm_dd_usd": "%.2f" % audit.close_mtm_dd_usd,
            "intrabar_mtm_dd_usd": "%.2f" % audit.intrabar_mtm_dd_usd,
            "net_over_stress_dd": "%.2f" % ratio,
        }
        rows.append(row)
        print(
            "DONE %s WR=%s%% Net=$%s StressDD=$%s Net/Stress=%s"
            % (strategy_id, row["win_rate_pct"], row["net_usd"], row["intrabar_mtm_dd_usd"], row["net_over_stress_dd"]),
            flush=True,
        )

    with (output_root / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    lines = [
        "# EURUSD first-break opposite 1/1/3 — EOD stop → OR mid",
        "",
        "Close-SL (wicks ignored). Structure **1 @ 0.25R / 1 @ 1R / 3 runner**.",
        "Trail variant: after each daily close, ratchet stop to **OR midpoint** (tighten only).",
        "BE after TP1 still applies. Fee $%.2f/unit." % FEE_PER_UNIT,
        "",
        "| Variant | Campaigns | WR | Net | Stress DD | Net/Stress |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| %s | %s | %s%% | $%s | $%s | %s |"
            % (
                row["variant"],
                row["campaigns"],
                row["win_rate_pct"],
                row["net_usd"],
                row["intrabar_mtm_dd_usd"],
                row["net_over_stress_dd"],
            )
        )
    if len(rows) == 2:
        d_net = float(rows[1]["net_usd"]) - float(rows[0]["net_usd"])
        d_ratio = float(rows[1]["net_over_stress_dd"]) - float(rows[0]["net_over_stress_dd"])
        lines.extend(
            [
                "",
                "Δ (OR-mid trail vs baseline): Net $%+.0f, Net/Stress %+.2f" % (d_net, d_ratio),
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
        extra={"driver": "eurusd_monthly_orb_fbo_or_mid_trail_broker"},
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
