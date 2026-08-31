"""Broker-like: Monthly ORB OCO 2/1/2 with SL at opposite OR boundary.

Markets: MNQ (futures daily) and USDJPY (Histdata daily).

Rules
-----
- OR = first 3 daily sessions of the month
- ``entry_mode=oco``: after OR, OCO stops long @ ORH / short @ ORL
- Protective SL = opposite end of the OR (campaign_stop); ``stop_mode=close``
  (wicks allowed; flatten only when daily close is beyond stop)
- Structure **2/1/2** (entry 5): 2 @ TP1=1R, 1 @ TP2=2R, 2 runner (no runner TP)
- BE after TP1; max 2 fills/month; flatten month-end

Fees: MNQ $1.50/unit; USDJPY $7/unit (quote JPY; approx-USD at 110 JPY/USD).
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import traceback
from pathlib import Path
from typing import Dict, List, Optional

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
OUT = REPO / "live" / "state" / "monthly_orb_oco_212_mnq_usdjpy_broker"

JPY_USD = 110.0

MARKETS: List[Dict[str, object]] = [
    dict(
        market="mnq",
        instrument="MNQ",
        daily=REPO / "mnq" / "mnq_daily.csv",
        tick=0.25,
        fee=1.50,
        quote="USD",
        point_value=2.0,
    ),
    dict(
        market="usdjpy",
        instrument="USDJPY",
        daily=REPO / "fx" / "usdjpy_daily.csv",
        tick=0.001,
        fee=7.0,
        quote="JPY",
        point_value=100000.0,
    ),
]


def _spec() -> BrokerReplaySpec:
    cfg = {
        "allow_shorts": True,
        "or_sessions": 3,
        "max_trades_per_month": 2,
        "entry_qty": 5,
        "tp1_qty": 2,
        "tp2_qty": 1,
        "tp1_r": 1.0,
        "tp2_r": 2.0,
        "be_after": "tp1",
        "entry_mode": "oco",
        "stop_mode": "close",
        "flip_after_stop": False,
        "eod_stop_to_or_mid": False,
        "record_levels": False,
    }
    return BrokerReplaySpec(
        name="Monthly ORB OCO S_2_1_2 close-SL opposite-OR",
        slug="monthly_orb_v2b_oco_S_2_1_2",
        strategy_type="monthly_orb_v2b_oco",
        max_contracts=5,
        config=cfg,
        notes="OCO @ ORH/ORL; SL at opposite OR; 2@1R / 1@2R / 2 runner; BE after TP1; close-SL; month-end flatten.",
    )


def _progress(msg: str) -> None:
    print(msg, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def run(output_root: Path, force: bool = False, do_email: bool = False) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "PROGRESS.log").write_text("", encoding="utf-8")
    spec = _spec()
    rows: List[dict] = []
    run_ids: List[str] = []

    for meta in MARKETS:
        instrument = str(meta["instrument"])
        market = str(meta["market"])
        daily_path = Path(meta["daily"])  # type: ignore[arg-type]
        tick = float(meta["tick"])
        fee = float(meta["fee"])
        quote = str(meta["quote"])
        pv = float(meta["point_value"])
        POINT_VALUES[instrument] = pv
        DEFAULT_TICK_SIZE[instrument] = tick

        strategy_id = "%s_%s" % (market, spec.slug)
        state_root = output_root / "states" / strategy_id
        rid = begin_run(
            run_class="broker_like",
            variant_slug=strategy_id,
            instrument=instrument,
            hub_path=str(output_root),
            notes="monthly ORB OCO 2/1/2 opposite-OR SL",
            meta={"structure": "2/1/2", "entry_mode": "oco", "stop_mode": "close", "fee": fee},
        )
        run_ids.append(rid)
        _progress("START %s" % strategy_id)
        try:
            if not daily_path.exists():
                raise FileNotFoundError(daily_path)
            bars = bars_from_csv(daily_path, instrument, "D", source=str(daily_path))
            _progress("Loaded %d %s daily bars" % (len(bars), instrument))
            if force and state_root.exists():
                shutil.rmtree(state_root)
            store = FlatFileStore(state_root, defer_table_writes=True)
            store.ensure()
            instance = StrategyInstance(
                strategy_id=strategy_id,
                strategy_type=spec.strategy_type,
                version="v1",
                instrument=instrument,
                broker_instrument=instrument,
                account_mode="paper",
                enabled=True,
                timeframes="D",
                max_contracts=spec.max_contracts,
                max_open_orders=64,
                config_json=json.dumps(_runtime_config(spec, bars), sort_keys=True),
            )
            store.upsert_row("strategy_instances", "strategy_id", as_row(instance))
            Engine(store=store, slippage_ticks=1.0, tick_size={instrument: tick}).replay_bars(bars)
            store.flush_tables()
            generate_market_close_report(store, bars[-1].ts[:10])
            replay_bars = read_bars(state_root / "bars" / ("%s_D.csv" % instrument), "ts")
            units = units_from_live_fills(
                state_root / "fills.csv",
                strategy_id,
                replay_bars[-1].ts,
                replay_bars[-1].close,
            )
            audit = audit_units(
                name="%s %s" % (instrument, spec.name),
                slug=strategy_id,
                source=state_root / "fills.csv",
                bar_source=state_root / "bars" / ("%s_D.csv" % instrument),
                bars=replay_bars,
                units=units,
                instrument=instrument,
                notes=spec.notes + " fee=$%.2f/unit (%s)." % (fee, quote),
                output_root=output_root / "audits",
                fee_per_unit=fee,
            )
            ns = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
            fx = JPY_USD if quote == "JPY" else 1.0
            row = {
                "market": market,
                "instrument": instrument,
                "structure": "2_1_2",
                "quote": quote,
                "trades": audit.trades,
                "units": audit.units,
                "net_quote": round(audit.net_usd, 2),
                "close_dd_quote": round(audit.close_mtm_dd_usd, 2),
                "stress_dd_quote": round(audit.intrabar_mtm_dd_usd, 2),
                "ns": round(ns, 2),
                "net_usd_approx": round(audit.net_usd / fx, 2),
                "stress_usd_approx": round(audit.intrabar_mtm_dd_usd / fx, 2),
                "fee_per_unit": fee,
                "slug": strategy_id,
            }
            rows.append(row)
            complete_run(
                rid,
                net_usd=row["net_usd_approx"],
                stress_dd_usd=row["stress_usd_approx"],
                close_mtm_dd_usd=round(audit.close_mtm_dd_usd / fx, 2),
                ns=ns,
                trades=audit.trades,
                units=audit.units,
                replay_start=str(bars[0].ts)[:10] if bars else None,
                replay_end=str(bars[-1].ts)[:10] if bars else None,
            )
            _progress(
                "DONE %s trades=%d units=%d Net=%s%.2f Stress=%s%.2f N/S=%.2f (USD~%.0f / %.0f)"
                % (
                    strategy_id,
                    audit.trades,
                    audit.units,
                    quote,
                    audit.net_usd,
                    quote,
                    audit.intrabar_mtm_dd_usd,
                    ns,
                    row["net_usd_approx"],
                    row["stress_usd_approx"],
                )
            )
        except Exception as exc:
            fail_run(rid, notes=str(exc))
            _progress("FAIL %s: %s\n%s" % (strategy_id, exc, traceback.format_exc()))
            rows.append(
                {
                    "market": market,
                    "instrument": instrument,
                    "structure": "2_1_2",
                    "error": str(exc),
                    "slug": strategy_id,
                }
            )

    if not rows:
        raise RuntimeError("no market rows produced")

    fieldnames = sorted({k for r in rows for k in r.keys()})
    with (output_root / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# Monthly ORB OCO 2/1/2 — MNQ + USDJPY (broker-like)",
        "",
        "OCO stops @ ORH/ORL after 3-session OR; protective SL at **opposite OR boundary**; "
        "daily-close SL (wicks allowed). Ladder **2 @ 1R / 1 @ 2R / 2 runner**; BE after TP1; "
        "max 2/month; month-end flatten.",
        "",
        "| Market | Trades | Units | Net (quote) | Stress DD | N/S | Net≈USD | Stress≈USD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    stance_bits = []
    for r in rows:
        if "error" in r:
            lines.append("| %s | — | — | FAIL | — | — | — | — |" % r["instrument"])
            stance_bits.append("%s FAIL" % r["instrument"])
            continue
        lines.append(
            "| **%s** | %s | %s | %s %.0f | %s %.0f | **%.2f** | $%.0f | $%.0f |"
            % (
                r["instrument"],
                r["trades"],
                r["units"],
                r["quote"],
                r["net_quote"],
                r["quote"],
                r["stress_dd_quote"],
                r["ns"],
                r["net_usd_approx"],
                r["stress_usd_approx"],
            )
        )
        if r["ns"] >= 1.0 and r["net_usd_approx"] > 0:
            stance_bits.append("%s research/retain (N/S %.2f)" % (r["instrument"], r["ns"]))
        elif r["net_usd_approx"] > 0:
            stance_bits.append("%s weak positive (N/S %.2f) — reject promote" % (r["instrument"], r["ns"]))
        else:
            stance_bits.append("%s reject (net negative)" % r["instrument"])

    lines.extend(
        [
            "",
            "## Stance",
            "",
            "- " + "; ".join(stance_bits),
            "- Compare EURUSD OCO pack (1/1/2 etc. all failed broker stress) and promoted FX FBO 1/1/3.",
            "",
            "Fees: MNQ $1.50/unit; USDJPY $7/unit (JPY quote; ≈USD @ 110).",
            "Hub: `%s`" % output_root,
            "",
        ]
    )
    summary_md = "\n".join(lines)
    (output_root / "SUMMARY.md").write_text(summary_md, encoding="utf-8")
    (output_root / "EMAIL.txt").write_text(summary_md, encoding="utf-8")

    write_run_manifest(
        output_root,
        data_inputs=[Path(m["daily"]) for m in MARKETS],  # type: ignore[misc]
        output_paths=[output_root / "summary.csv", output_root / "SUMMARY.md"],
        broker_realism_config={
            "slippage_ticks": 1.0,
            "structure": "2/1/2",
            "entry_mode": "oco",
            "stop_mode": "close",
        },
        causality_mode="audit",
        extra={"driver": "monthly_orb_oco_212_mnq_usdjpy_broker", "run_ids": run_ids},
    )

    if do_email:
        send_email(subject="potions: monthly ORB OCO 2/1/2 MNQ+USDJPY complete", body=summary_md)
    return output_root / "SUMMARY.md"


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=OUT)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--email", action="store_true")
    args = parser.parse_args(argv)
    try:
        path = run(args.output_root, force=args.force, do_email=args.email)
        print("Wrote %s" % path, flush=True)
        return 0
    except Exception:
        tb = traceback.format_exc()
        print(tb, flush=True)
        if args.email:
            send_email(subject="potions: monthly ORB OCO 2/1/2 MNQ+USDJPY FAILED", body=tb[-4000:])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
