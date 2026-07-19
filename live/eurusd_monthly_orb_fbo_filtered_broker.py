"""Broker stress: FBO runner@2R BE@TP25 + HTF entry filters (A/B).

Promoted family (first-break opposite, close-SL, TP1=0.25R / TP2=1R / runner@2R,
BE after TP25) gated by a causal daily entry filter CSV:

- ``ema100_1h``: entry direction must agree with last 1H close vs EMA100(1H)
  as of the arming daily close (fill occurs next bar onward).
- ``ema100_1h_atr80``: additionally block entries when the daily ATR14
  rolling-500 percentile is above 0.80.

Variants: 1/1/3 and 1/2/3 for each filter.
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
OUT = REPO / "live" / "state" / "eurusd_monthly_orb_fbo_filtered_broker"
FILT = OUT / "filters"

# label, entry, tp1, tp2
STRUCTURES: List[Tuple[str, int, int, int]] = [
    ("1_1_3", 5, 1, 1),
    ("1_2_3", 6, 1, 2),
]
FILTERS = [
    ("ema100_1h", FILT / "ema100_1h.csv"),
    ("ema100_1h_atr80", FILT / "ema100_1h_atr80.csv"),
]


def _specs() -> List[BrokerReplaySpec]:
    out: List[BrokerReplaySpec] = []
    for flabel, fpath in FILTERS:
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
                "be_after": "tp1",
                "entry_mode": "first_break_opposite",
                "stop_mode": "close",
                "flip_after_stop": False,
                "eod_stop_to_or_mid": False,
                "record_levels": False,
                "entry_filter_csv": str(fpath),
            }
            out.append(
                BrokerReplaySpec(
                    name="FBO %s runner@2R BE@TP25 %s" % (label, flabel),
                    slug="monthly_orb_fbo_filt_%s_%s" % (flabel, label),
                    strategy_type="monthly_orb_v2b_oco",
                    max_contracts=entry,
                    config=cfg,
                    notes="1@0.25R / %d@1R / %d@2R; BE after TP25; close-SL; filter=%s." % (tp2, runner, flabel),
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
        variant = spec.slug.replace("monthly_orb_fbo_filt_", "")
        row = {
            "variant": variant,
            "slug": strategy_id,
            "campaigns": str(wr["campaigns"]),
            "win_rate_pct": "%.1f" % wr["win_rate_pct"],
            "pct_hit_1R": "%.1f" % wr["pct_tp2"],
            "pct_hit_2R": "%.1f" % wr["pct_tp3"],
            "net_usd": "%.2f" % audit.net_usd,
            "intrabar_mtm_dd_usd": "%.2f" % audit.intrabar_mtm_dd_usd,
            "net_over_stress_dd": "%.2f" % ratio,
            "units": str(audit.units),
        }
        rows.append(row)
        print(
            "DONE %s n=%s WR=%s%% Net=$%s Stress=$%s N/S=%s"
            % (
                strategy_id,
                row["campaigns"],
                row["win_rate_pct"],
                row["net_usd"],
                row["intrabar_mtm_dd_usd"],
                row["net_over_stress_dd"],
            ),
            flush=True,
        )

    with (output_root / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    lines = [
        "# EURUSD FBO runner@2R BE@TP25 — HTF entry filters (broker stress)",
        "",
        "First-break opposite, close-SL, TP 0.25R/1R/2R, BE after TP25. Fee $%.2f/unit." % FEE_PER_UNIT,
        "Filter applies at the arming daily close (signal causal; fill next bar+).",
        "",
        "| Variant | Campaigns | WR | Hit 1R | Hit 2R | Net | Stress DD | Net/Stress |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| %s | %s | %s%% | %s%% | %s%% | $%s | $%s | %s |"
            % (
                row["variant"],
                row["campaigns"],
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
            "Unfiltered baselines (same family):",
            "- 1/1/3: +$77,281 / -$74,027 / 1.04 (173 campaigns)",
            "- 1/2/3: +$90,640 / -$88,758 / 1.02",
            "",
            "Counterfactual expectation (drop-from-fills): 1/1/3 ema100 ~ +$127k / -$47k;",
            "ema100+atr80 ~ +$142k / -$34k. Broker rerun differs (freed monthly budget).",
            "",
        ]
    )
    (output_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    write_run_manifest(
        output_root,
        data_inputs=[daily_path, FILT / "ema100_1h.csv", FILT / "ema100_1h_atr80.csv"],
        output_paths=[output_root / "summary.csv", output_root / "SUMMARY.md"],
        broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": FEE_PER_UNIT, "tick_size": TICK},
        causality_mode="audit",
        extra={"driver": "eurusd_monthly_orb_fbo_filtered_broker"},
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
