"""Broker-like trial: v2b clean-break + pyramid outside OR (max 8).

Entry / clean validation unchanged from bullish clean-break
(`required_break_num=0`, stop @ OR high + 2 ticks, clean close required).

After clean validation:
  - No 2R / RL brackets.
  - Each subsequent 5m candle whose *low* stays strictly above OR high → +1
    market add (max 8 total).
  - If 5m *close* <= OR high → flatten everything (`close_back_into_range`).
  - EOD flatten still applies at 15:55.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.v2b_clean_break_pyramid_outside_v1 --email
  python -m live.v2b_clean_break_pyramid_outside_v1 --email --smoke
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .notify_email import send_email
from .run_ledger import begin_run, complete_run, fail_run
from .v2b_clean_break_replays import (
    FEE_PER_UNIT,
    MARKETS,
    MarketConfig,
    load_5m_bars,
    run_one as _run_one_base,
)
from .v2b_clean_break_replays import VariantConfig
from .v2b_strategy_replay import money

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "v2b_clean_break_pyramid_outside_v1"
STUDY_ID = "v2b_clean_break_pyramid_outside_v1"
DSR = "TRL-2026-00193"

VARIANT = VariantConfig(
    name="bullish_pyramid_outside_max8",
    label="Bullish clean break, +1/5m outside OR (max 8), exit close-into-range",
    config={
        "variant": "bullish_pyramid_outside_max8",
        "entry_qty": 1,
        "required_break_num": 0,
        "stop_mode": "opposite",
        "size_model": "pyramid_outside_max8",
        "max_pyramid_qty": 8,
        "entry_offset_ticks": 2,
    },
)


def _progress(msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _append_dsr() -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    lines = path.read_text().splitlines()
    if any(ln.startswith(DSR + ",") for ln in lines):
        return
    header = next(ln for ln in lines if ln.startswith("trial_id,"))
    fields = header.split(",")
    row = {k: "" for k in fields}
    row.update(
        {
            "trial_id": DSR,
            "entry_date": date.today().isoformat(),
            "analyst": "cursor",
            "trial_class": "EXECUTION_VARIANT",
            "trial_subclass": "v2b_clean_break_pyramid_outside",
            "is_independent": "TRUE",
            "market": "NQ,MNQ",
            "replay_type": "FULL_HISTORY",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {
                    "base": "bullish_2r_rl_stop clean break",
                    "size_model": "pyramid_outside_max8",
                    "max_qty": 8,
                    "add": "5m_low_above_or_high",
                    "exit": "5m_close_le_or_high",
                }
            ),
            "fixed_parameters_ref": "live/v2b_clean_break_pyramid_outside_v1.py",
            "num_params_varied": "1",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "1.00",
            "status": "PENDING",
            "notes": "Clean-break entry; pyramid +1 per outside 5m candle max 8; flatten on close into OR",
            "disclosure_review": "FALSE",
        }
    )
    with path.open("a", newline="") as fh:
        csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore").writerow(row)


def _mark_dsr(status: str) -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    out = []
    for ln in path.read_text().splitlines():
        if ln.startswith(DSR + ","):
            for old in ("PENDING", "RUNNING", "COMPLETE", "FAILED"):
                tok = ",%s," % old
                if tok in ln:
                    ln = ln.replace(tok, ",%s," % status, 1)
                    break
        out.append(ln)
    path.write_text("\n".join(out) + "\n")


def run_one(*, output_root: Path, market: MarketConfig, bars) -> Any:
    """Thin wrapper so instance max_contracts matches pyramid cap."""
    # Patch via local copy of run_one logic with max_contracts=8
    from .engine import Engine
    from .models import Bar, StrategyInstance, as_row
    from .store import FlatFileStore
    from .v2b_clean_break_replays import DEFAULT_SLIPPAGE_TICKS
    from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills

    variant = VARIANT
    strategy_id = "%s_v2b_clean_break_%s" % (market.market, variant.name)
    state_root = output_root / "states" / strategy_id
    if state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()

    config = dict(variant.config)
    config.update({"market": market.market, "record_levels": False})
    max_qty = int(config.get("max_pyramid_qty") or 8)
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type="v2b_clean_break",
        version="v1",
        instrument=market.instrument,
        broker_instrument=market.instrument,
        account_mode="paper",
        enabled=True,
        timeframes="5m",
        max_contracts=max_qty,
        max_open_orders=16,
        config_json=json.dumps(config, sort_keys=True),
    )
    store.write_table("strategy_instances", [as_row(instance)])
    engine = Engine(store=store, persist_bars=False, persist_health=False, slippage_ticks=DEFAULT_SLIPPAGE_TICKS)

    audit_bars: List[AuditBar] = []
    _progress("replay %s / %s" % (market.instrument, variant.name))
    sessions = 0
    for _session_day, session_bars in bars.groupby("session_day", sort=True):
        sessions += 1
        for _, row in session_bars.iterrows():
            import pandas as pd

            ts_s = pd.Timestamp(row["ts"]).isoformat()
            bar = Bar(
                instrument=market.instrument,
                timeframe="5m",
                ts=ts_s,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(market.bars_path),
            )
            engine.process_bar(bar)
            audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
        if sessions % 500 == 0:
            _progress("%s: %d sessions" % (market.instrument, sessions))

    store.flush_tables()
    units = units_from_v2b_fills(state_root / "fills.csv", strategy_id)
    audit = fast_intraday_audit(
        strategy_id=strategy_id,
        state_root=state_root,
        bars=audit_bars,
        units=units,
        instrument=market.instrument,
        fee_per_unit=FEE_PER_UNIT,
    )
    from .v2b_clean_break_replays import ReplayResult

    return ReplayResult(
        market=market.market,
        instrument=market.instrument,
        variant=variant.name,
        label=variant.label,
        strategy_id=strategy_id,
        state_root=state_root,
        sessions=sessions,
        units=len(units),
        trades=len({u.trade_id for u in units}),
        net_usd=audit["net_usd"],
        closed_dd_usd=audit["closed_dd_usd"],
        intrabar_stress_dd_usd=audit["intrabar_stress_dd_usd"],
        max_open_units=audit["max_open_units"],
        win_rate=audit["win_rate"],
        profit_factor=audit["profit_factor"],
    )


def run(*, email: bool, smoke: bool, markets: Sequence[str], max_sessions: Optional[int]) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    _append_dsr()
    rid = begin_run(
        run_class="broker_like",
        variant_slug=STUDY_ID,
        instrument=",".join(m.upper() for m in markets),
        hub_path=str(HUB.relative_to(REPO)),
        dsr_trial_id=DSR,
        meta={"size_model": "pyramid_outside_max8", "max_qty": 8, "smoke": smoke},
    )
    try:
        results = []
        for name in markets:
            market = MARKETS[name]
            bars = load_5m_bars(market.bars_path, market.instrument)
            if max_sessions is not None:
                keep = sorted(bars["session_day"].unique())[:max_sessions]
                bars = bars[bars["session_day"].isin(keep)].copy()
            _progress("%s sessions=%d" % (market.instrument, bars["session_day"].nunique()))
            results.append(run_one(output_root=HUB, market=market, bars=bars))

        rows = []
        for r in results:
            rows.append(
                {
                    "market": r.market,
                    "instrument": r.instrument,
                    "variant": r.variant,
                    "label": r.label,
                    "sessions": r.sessions,
                    "trades": r.trades,
                    "units": r.units,
                    "net_usd": r.net_usd,
                    "closed_dd_usd": r.closed_dd_usd,
                    "intrabar_stress_dd_usd": r.intrabar_stress_dd_usd,
                    "max_open_units": r.max_open_units,
                    "win_rate": r.win_rate,
                    "profit_factor": r.profit_factor,
                    "ns": r.net_over_stress,
                }
            )
        import pandas as pd

        summary = pd.DataFrame(rows)
        summary.to_csv(HUB / "summary.csv", index=False)

        total_net = float(summary["net_usd"].sum())
        # Portfolio DD approx: worst single-market stress (conservative) + sum nets
        worst_stress = float(summary["intrabar_stress_dd_usd"].min()) if len(summary) else 0.0
        ns = total_net / abs(worst_stress) if worst_stress else 0.0

        stance = "research"
        if total_net > 0 and ns >= 1.0:
            stance = "research — interesting vs baseline single-lot clean break; needs OOS / causality note"
        elif total_net <= 0:
            stance = "reject / weak on this rule set"

        lines = [
            "# V2B Clean-Break Pyramid Outside OR (max 8)",
            "",
            "STATUS: RESEARCH TRIAL (Engine + PaperBroker, 5m RTH)",
            "",
            "## Rules",
            "- Base: bullish v2b clean break (OR 09:30–09:45, stop @ OR high + 2 ticks, clean close).",
            "- After clean: +1 contract each 5m candle whose **low** stays above OR high (max 8).",
            "- Exit all when 5m **close** <= OR high (`close_back_into_range`); EOD 15:55 still flattens.",
            "- No 2R target / RL stop brackets in this size model.",
            "",
            "## Results",
            "",
            "| Market | Sessions | Trades | Units | Net | Stress DD | MaxU | N/S | Win% | PF |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for r in results:
            pf = "%.2f" % r.profit_factor if math.isfinite(r.profit_factor) else "inf"
            lines.append(
                "| %s | %d | %d | %d | $%s | $%s | %d | %.2f | %.1f%% | %s |"
                % (
                    r.instrument,
                    r.sessions,
                    r.trades,
                    r.units,
                    money(r.net_usd),
                    money(r.intrabar_stress_dd_usd),
                    r.max_open_units,
                    r.net_over_stress,
                    r.win_rate,
                    pf,
                )
            )
        lines += [
            "",
            "| Combined net | $%+.0f |" % total_net,
            "| Worst-market stress | $%+.0f |" % worst_stress,
            "| Combined N/S (vs worst stress) | %.2f |" % ns,
            "",
            "**Stance:** %s" % stance,
            "",
            "Hub: `%s`" % HUB,
            "DSR: `%s`" % DSR,
            "smoke=%s" % smoke,
            "",
            "Baseline reference (single-lot bullish 2R/RL): NQ ~$93k / 3.79 N/S; MNQ ~$8.9k / 4.40 N/S.",
            "",
        ]
        body = "\n".join(lines)
        (HUB / "SUMMARY.md").write_text(body, encoding="utf-8")
        (HUB / "EMAIL.txt").write_text("potions: %s\n\n%s\n" % (STUDY_ID, body), encoding="utf-8")
        (HUB / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "study_id": STUDY_ID,
                    "total_net": total_net,
                    "worst_stress": worst_stress,
                    "ns": ns,
                    "stance": stance,
                    "smoke": smoke,
                    "markets": rows,
                },
                indent=2,
            )
            + "\n"
        )

        complete_run(
            rid,
            net_usd=total_net,
            stress_dd_usd=worst_stress,
            close_mtm_dd_usd=worst_stress,
            ns=ns,
            trades=int(summary["trades"].sum()),
            notes=stance,
            meta={"rows": rows},
        )
        _mark_dsr("COMPLETE")
        if email:
            send_email(subject="potions: %s complete" % STUDY_ID, body=(HUB / "EMAIL.txt").read_text())
        _progress("DONE net=$%+.0f N/S=%.2f stance=%s" % (total_net, ns, stance))
    except Exception:
        err = traceback.format_exc()
        fail_run(rid, notes=err[-2000:])
        _mark_dsr("FAILED")
        if email:
            send_email(subject="potions: %s FAILED" % STUDY_ID, body=err[-4000:])
        raise


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--max-sessions", type=int, default=None)
    ap.add_argument("--market", action="append", choices=sorted(MARKETS), default=None)
    args = ap.parse_args()
    max_sessions = args.max_sessions
    if args.smoke and max_sessions is None:
        max_sessions = 40
    markets = args.market or ["nq", "mnq"]
    run(email=bool(args.email), smoke=bool(args.smoke), markets=markets, max_sessions=max_sessions)


if __name__ == "__main__":
    main()
