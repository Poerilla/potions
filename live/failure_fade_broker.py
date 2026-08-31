"""Broker-like Engine+PaperBroker: NQ daily failure_fade + reclaim.

Primary fade on first prior-quarter extreme touch (wick through, close back in
range). Optional one-shot reclaim after stop/BE-stop. Market entries use
``live_after_ts`` (fill next daily open).

Hub: ``live/state/nq_failure_fade_broker/``
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine, bars_from_csv
from .models import StrategyInstance, as_row
from .notify_email import send_email
from .replay_audit import POINT_VALUES, audit_units, read_bars, units_from_live_fills
from .replay_manifest import write_run_manifest
from .reporting import generate_market_close_report
from .store import FlatFileStore

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "nq_failure_fade_broker"
DEFAULT_DAILY = REPO / "nq" / "nq_daily.csv"

TICK = 0.25
FEE = 1.50
ENTRY_QTY = 10
TP1_QTY = 5


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def run_book(
    *,
    output_root: Path,
    daily_path: Path,
    enable_reclaim: bool,
    force: bool,
    slippage_ticks: float,
) -> Dict[str, float]:
    slug = "nq_failure_fade_reclaim" if enable_reclaim else "nq_failure_fade_primary"
    strategy_id = slug
    state_root = output_root / "states" / strategy_id
    audits_root = output_root / "audits"
    if force and state_root.exists():
        shutil.rmtree(state_root)

    POINT_VALUES["NQ"] = 20.0
    DEFAULT_TICK_SIZE["NQ"] = TICK

    bars = bars_from_csv(daily_path, "NQ", "D", source=str(daily_path))
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {
        "tick_size": TICK,
        "entry_qty": ENTRY_QTY,
        "tp1_qty": TP1_QTY,
        "tp1_pct": 0.15,
        "tp2_pct": 0.62,
        "reclaim_tp1_pct": 0.14,
        "enable_reclaim": bool(enable_reclaim),
        "timeframe": "D",
        "suppress_alerts": True,
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="failure_fade",
                    version="v1",
                    instrument="NQ",
                    broker_instrument="NQ",
                    account_mode="paper",
                    enabled=True,
                    timeframes="D",
                    max_contracts=ENTRY_QTY,
                    max_open_orders=32,
                    config_json=json.dumps(payload, sort_keys=True),
                )
            )
        ],
    )
    engine = Engine(
        store=store,
        slippage_ticks=slippage_ticks,
        persist_health=False,
        tick_size={"NQ": TICK},
    )
    _progress(output_root, "RUN %s bars=%d reclaim=%s" % (strategy_id, len(bars), enable_reclaim))
    engine.replay_bars(bars)
    store.flush_tables()
    if bars:
        generate_market_close_report(store, bars[-1].ts[:10])

    bar_path = state_root / "bars" / "NQ_D.csv"
    replay_bars = read_bars(bar_path, "ts")
    units = units_from_live_fills(
        state_root / "fills.csv",
        strategy_id,
        replay_bars[-1].ts if replay_bars else "",
        replay_bars[-1].close if replay_bars else None,
    )
    audit = audit_units(
        name="NQ failure_fade%s" % ("+reclaim" if enable_reclaim else " primary"),
        slug=strategy_id,
        source=state_root / "fills.csv",
        bar_source=bar_path,
        bars=replay_bars,
        units=units,
        instrument="NQ",
        notes=(
            "Quarterly prior-extreme failure_fade on daily. "
            "enable_reclaim=%s. Realism: slip=%g tick fee=$%.2f/unit."
            % (enable_reclaim, slippage_ticks, FEE)
        ),
        output_root=audits_root,
        fee_per_unit=FEE,
    )
    return {
        "slug": strategy_id,
        "enable_reclaim": float(1 if enable_reclaim else 0),
        "bars": float(len(replay_bars)),
        "units": float(audit.units),
        "trades": float(audit.trades),
        "net_usd": float(audit.net_usd),
        "closed_dd": float(audit.close_mtm_dd_usd),
        "stress_dd": float(audit.intrabar_mtm_dd_usd),
        "win_units": float(audit.win_units),
        "loss_units": float(audit.loss_units),
        "ns": (
            float(audit.net_usd) / abs(float(audit.intrabar_mtm_dd_usd))
            if abs(float(audit.intrabar_mtm_dd_usd)) > 1e-9
            else 0.0
        ),
    }


def write_reports(output_root: Path, rows: Sequence[Dict[str, float]], slippage_ticks: float) -> None:
    lines = [
        "# NQ failure_fade broker-like replay",
        "",
        "Engine + PaperBroker on **NQ daily**. Market entries fill next open (`live_after_ts`).",
        "",
        f"- Slippage: **{slippage_ticks:g}** tick · fee **${FEE:.2f}**/unit · NQ $20/pt",
        f"- Sizing: **{ENTRY_QTY}** entry / **{TP1_QTY}** @ TP1 / remainder @ TP2",
        "",
        "| Book | Trades | Units | Net $ | Stress DD $ | N/S | Win units |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    email = [
        "NQ failure_fade broker-like replay complete.",
        "",
        "Hub: %s" % output_root,
        "",
    ]
    for r in rows:
        label = "fade+reclaim" if r["enable_reclaim"] else "primary only"
        lines.append(
            "| %s (`%s`) | %d | %d | %.2f | %.2f | %.2f | %d |"
            % (
                label,
                r["slug"],
                int(r["trades"]),
                int(r["units"]),
                r["net_usd"],
                r["stress_dd"],
                r["ns"],
                int(r["win_units"]),
            )
        )
        email.append(
            "%s: trades=%d units=%d net=$%.2f stress=$%.2f N/S=%.2f"
            % (label, int(r["trades"]), int(r["units"]), r["net_usd"], r["stress_dd"], r["ns"])
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Primary-only book disables reclaim (`enable_reclaim=false`).",
            "- Fade+reclaim is the full sequence plugin.",
            "- Expect PnL deltas vs pandas playbook (close fill vs next-open + resting OCO).",
            "",
            "## Files",
            "",
            "- `states/<slug>/fills.csv`",
            "- `audits/`",
            "",
        ]
    )
    (output_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    email.append("")
    email.append("SUMMARY: %s" % (output_root / "SUMMARY.md"))
    (output_root / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")
    # summary.csv
    import csv

    with (output_root / "summary.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            w.writeheader()
            for r in rows:
                w.writerow(r)


def run(
    *,
    output_root: Path,
    daily_path: Path,
    force: bool = True,
    slippage_ticks: float = 1.0,
    email: bool = False,
) -> int:
    if force and output_root.exists():
        # Keep sibling chart hubs elsewhere; only wipe this broker hub.
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    write_run_manifest(
        output_root,
        data_inputs=[daily_path],
        strategy_config={
            "strategy_type": "failure_fade",
            "enable_reclaim_books": [False, True],
            "entry_qty": ENTRY_QTY,
            "tp1_qty": TP1_QTY,
        },
        broker_realism_config={"slippage_ticks": slippage_ticks, "fee_per_unit": FEE},
        extra={"notes": "failure_fade primary + reclaim Engine+PaperBroker on NQ daily"},
    )
    rows: List[Dict[str, float]] = []
    try:
        for enable_reclaim in (False, True):
            rows.append(
                run_book(
                    output_root=output_root,
                    daily_path=daily_path,
                    enable_reclaim=enable_reclaim,
                    force=True,
                    slippage_ticks=slippage_ticks,
                )
            )
        write_reports(output_root, rows, slippage_ticks)
        _progress(output_root, "DONE wrote SUMMARY.md")
        try:
            from .run_ledger import log_from_hub

            log_from_hub(
                output_root,
                run_class="broker_like",
                variant_slug=str(output_root.name),
                instrument="NQ",
                notes="failure_fade_broker",
                meta={"slippage_ticks": slippage_ticks, "books": len(rows)},
            )
        except Exception as exc:
            _progress(output_root, "run_ledger skip: %s" % exc)
        if email:
            send_email(
                subject="potions: NQ failure_fade broker-like complete",
                body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        return 0
    except Exception as exc:
        _progress(output_root, "FAILED: %s" % exc)
        tb = traceback.format_exc()
        (output_root / "FAILED.txt").write_text(tb, encoding="utf-8")
        if email:
            try:
                send_email(
                    subject="potions: NQ failure_fade broker-like FAILED",
                    body="Hub: %s\n\n%s\n" % (output_root, tb[-4000:]),
                )
            except Exception:
                pass
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--daily", type=Path, default=DEFAULT_DAILY)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--slippage-ticks", type=float, default=1.0)
    p.add_argument("--force", action="store_true", default=True)
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    return run(
        output_root=args.output_root,
        daily_path=args.daily,
        force=bool(args.force),
        slippage_ticks=float(args.slippage_ticks),
        email=bool(args.email),
    )


if __name__ == "__main__":
    raise SystemExit(main())
