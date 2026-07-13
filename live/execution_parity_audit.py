from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .broker import DEFAULT_TICK_SIZE
from .manual_journal import validate_manual_journal
from .replay_audit import POINT_VALUES, Unit, units_from_live_fills

DEFAULT_ENTRY_SLIPPAGE_TICKS = 2.0
DEFAULT_EXIT_SLIPPAGE_TICKS = 2.0


@dataclass(frozen=True)
class MatchedTrade:
    live: Unit
    sim: Unit
    entry_delta: float
    exit_delta: float
    entry_delta_ticks: float
    exit_delta_ticks: float
    net_delta_usd: float


@dataclass(frozen=True)
class ParityAuditResult:
    ok: bool
    matched: int
    unmatched_live: int
    unmatched_sim: int
    median_entry_delta: float
    median_exit_delta: float
    pct_entry_within_slippage: float
    pct_exit_within_slippage: float
    sim_better_entry_count: int
    sim_better_exit_count: int
    messages: List[str]


def _entry_minute(ts: str) -> str:
    text = str(ts)
    if "T" in text:
        date_part, time_part = text.split("T", 1)
        minute = time_part[:5]
        return "%sT%s" % (date_part, minute)
    return text[:16]


def _session_date(ts: str) -> str:
    return str(ts)[:10]


def match_units(
    live_units: Sequence[Unit],
    sim_units: Sequence[Unit],
) -> Tuple[List[MatchedTrade], List[Unit], List[Unit]]:
    sim_pool = list(sim_units)
    matched: List[MatchedTrade] = []
    unmatched_live: List[Unit] = []
    for live in live_units:
        key = (_session_date(live.entry_ts), live.direction.lower(), _entry_minute(live.entry_ts))
        hit_idx = None
        for idx, sim in enumerate(sim_pool):
            sim_key = (_session_date(sim.entry_ts), sim.direction.lower(), _entry_minute(sim.entry_ts))
            if sim_key == key:
                hit_idx = idx
                break
        if hit_idx is None:
            unmatched_live.append(live)
            continue
        sim = sim_pool.pop(hit_idx)
        instrument = live.candidate or sim.candidate or "MNQ"
        tick = DEFAULT_TICK_SIZE.get(instrument.upper(), 0.25)
        entry_delta = live.entry_price - sim.entry_price
        exit_delta = live.exit_price - sim.exit_price
        point_value = POINT_VALUES.get(instrument.upper(), 2.0)
        live_net = live.points * point_value
        sim_net = sim.points * point_value
        matched.append(
            MatchedTrade(
                live=live,
                sim=sim,
                entry_delta=entry_delta,
                exit_delta=exit_delta,
                entry_delta_ticks=entry_delta / tick if tick else 0.0,
                exit_delta_ticks=exit_delta / tick if tick else 0.0,
                net_delta_usd=live_net - sim_net,
            )
        )
    return matched, unmatched_live, sim_pool


def audit_execution_parity(
    *,
    live_fills: Path,
    sim_fills: Path,
    live_strategy_id: str,
    sim_strategy_id: str,
    instrument: str = "MNQ",
    entry_slippage_ticks: float = DEFAULT_ENTRY_SLIPPAGE_TICKS,
    exit_slippage_ticks: float = DEFAULT_EXIT_SLIPPAGE_TICKS,
    min_match_pct: float = 0.95,
) -> ParityAuditResult:
    journal = validate_manual_journal(live_fills)
    messages: List[str] = []
    if not journal.ok:
        messages.extend(journal.errors[:10])
    live_units = units_from_live_fills(live_fills, live_strategy_id)
    sim_units = units_from_live_fills(sim_fills, sim_strategy_id)
    matched, unmatched_live, unmatched_sim = match_units(live_units, sim_units)
    if not matched:
        return ParityAuditResult(
            ok=False,
            matched=0,
            unmatched_live=len(unmatched_live),
            unmatched_sim=len(unmatched_sim),
            median_entry_delta=0.0,
            median_exit_delta=0.0,
            pct_entry_within_slippage=0.0,
            pct_exit_within_slippage=0.0,
            sim_better_entry_count=0,
            sim_better_exit_count=0,
            messages=messages + ["no matched trades"],
        )

    entry_deltas = sorted(m.entry_delta for m in matched)
    exit_deltas = sorted(m.exit_delta for m in matched)
    median_entry = entry_deltas[len(entry_deltas) // 2]
    median_exit = exit_deltas[len(exit_deltas) // 2]
    entry_within = sum(1 for m in matched if abs(m.entry_delta_ticks) <= entry_slippage_ticks) / len(matched)
    exit_within = sum(1 for m in matched if abs(m.exit_delta_ticks) <= exit_slippage_ticks) / len(matched)
    sim_better_entry = sum(1 for m in matched if m.entry_delta < 0)
    sim_better_exit = sum(1 for m in matched if m.exit_delta < 0)
    ok = True
    if median_entry < 0:
        ok = False
        messages.append("median entry delta < 0 (sim fills better than live on average)")
    if median_exit < 0:
        ok = False
        messages.append("median exit delta < 0 (sim fills better than live on average)")
    if entry_within < min_match_pct:
        ok = False
        messages.append("entry slippage within tolerance for only %.1f%% of matches" % (100 * entry_within))
    if exit_within < min_match_pct:
        ok = False
        messages.append("exit slippage within tolerance for only %.1f%% of matches" % (100 * exit_within))
    if sim_better_entry > len(matched) * 0.25:
        ok = False
        messages.append("sim entry fills better than live on %d/%d trades" % (sim_better_entry, len(matched)))
    if sim_better_exit > len(matched) * 0.25:
        ok = False
        messages.append("sim exit fills better than live on %d/%d trades" % (sim_better_exit, len(matched)))
    if unmatched_live:
        messages.append("%d live units unmatched" % len(unmatched_live))
    if unmatched_sim:
        messages.append("%d sim units unmatched" % len(unmatched_sim))
    return ParityAuditResult(
        ok=ok and journal.ok,
        matched=len(matched),
        unmatched_live=len(unmatched_live),
        unmatched_sim=len(unmatched_sim),
        median_entry_delta=median_entry,
        median_exit_delta=median_exit,
        pct_entry_within_slippage=entry_within,
        pct_exit_within_slippage=exit_within,
        sim_better_entry_count=sim_better_entry,
        sim_better_exit_count=sim_better_exit,
        messages=messages,
    )


def write_parity_report(
    output_dir: Path,
    result: ParityAuditResult,
    matched: Sequence[MatchedTrade],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in matched:
        rows.append(
            {
                "trade_id": item.live.trade_id,
                "direction": item.live.direction,
                "live_entry_ts": item.live.entry_ts,
                "sim_entry_ts": item.sim.entry_ts,
                "live_entry_price": "%.2f" % item.live.entry_price,
                "sim_entry_price": "%.2f" % item.sim.entry_price,
                "entry_delta": "%.4f" % item.entry_delta,
                "entry_delta_ticks": "%.2f" % item.entry_delta_ticks,
                "live_exit_price": "%.2f" % item.live.exit_price,
                "sim_exit_price": "%.2f" % item.sim.exit_price,
                "exit_delta": "%.4f" % item.exit_delta,
                "exit_delta_ticks": "%.2f" % item.exit_delta_ticks,
                "net_delta_usd": "%.2f" % item.net_delta_usd,
            }
        )
    with (output_dir / "matched_trades.csv").open("w", newline="", encoding="utf-8") as fh:
        if rows:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    summary = asdict(result)
    summary["messages"] = result.messages
    (output_dir / "parity_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    lines = [
        "# Execution Parity Audit",
        "",
        "| Metric | Value |",
        "|---|---|",
        "| Pass | %s |" % ("yes" if result.ok else "no"),
        "| Matched trades | %d |" % result.matched,
        "| Median entry delta (live - sim) | %.4f |" % result.median_entry_delta,
        "| Median exit delta (live - sim) | %.4f |" % result.median_exit_delta,
        "| Entry within slippage | %.1f%% |" % (100 * result.pct_entry_within_slippage),
        "| Exit within slippage | %.1f%% |" % (100 * result.pct_exit_within_slippage),
        "",
        "## Messages",
        "",
    ]
    if result.messages:
        lines.extend("- %s" % msg for msg in result.messages)
    else:
        lines.append("- none")
    (output_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_audit_cli(args: argparse.Namespace) -> int:
    live_units = units_from_live_fills(Path(args.live_fills), args.live_strategy_id)
    sim_units = units_from_live_fills(Path(args.sim_fills), args.sim_strategy_id)
    matched, _, _ = match_units(live_units, sim_units)
    result = audit_execution_parity(
        live_fills=Path(args.live_fills),
        sim_fills=Path(args.sim_fills),
        live_strategy_id=args.live_strategy_id,
        sim_strategy_id=args.sim_strategy_id,
        instrument=args.instrument,
        entry_slippage_ticks=args.entry_slippage_ticks,
        exit_slippage_ticks=args.exit_slippage_ticks,
    )
    write_parity_report(Path(args.output_dir), result, matched)
    print(json.dumps(asdict(result), indent=2))
    return 0 if result.ok else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compare live manual fills to replay fills")
    parser.add_argument("--live-fills", required=True)
    parser.add_argument("--sim-fills", required=True)
    parser.add_argument("--live-strategy-id", required=True)
    parser.add_argument("--sim-strategy-id", required=True)
    parser.add_argument("--instrument", default="MNQ")
    parser.add_argument("--output-dir", default="live/state/execution_parity")
    parser.add_argument("--entry-slippage-ticks", type=float, default=DEFAULT_ENTRY_SLIPPAGE_TICKS)
    parser.add_argument("--exit-slippage-ticks", type=float, default=DEFAULT_EXIT_SLIPPAGE_TICKS)
    args = parser.parse_args(argv)
    return run_audit_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
