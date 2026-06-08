from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import pandas as pd

from .v2b_st_pmc_alignment_study import REPO, Trade, load_strategy_trades, load_v2b_trades


NY = "America/New_York"


@dataclass(frozen=True)
class TimingRow:
    subject: Trade
    prior: Optional[Trade]
    bucket: str


def summarize_trades(label: str, trades: Sequence[Trade]) -> Dict[str, str]:
    trades = list(trades)
    net = sum(t.pnl_usd for t in trades)
    wins = sum(1 for t in trades if t.pnl_usd > 0)
    losses = len(trades) - wins
    gross_win = sum(t.pnl_usd for t in trades if t.pnl_usd > 0)
    gross_loss = abs(sum(t.pnl_usd for t in trades if t.pnl_usd <= 0))
    return {
        "bucket": label,
        "trades": str(len(trades)),
        "wins": str(wins),
        "losses": str(losses),
        "win_rate_pct": "%.2f" % (100.0 * wins / len(trades) if trades else 0.0),
        "net_usd": "%.2f" % net,
        "avg_usd": "%.2f" % (net / len(trades) if trades else 0.0),
        "profit_factor": "%.3f" % (gross_win / gross_loss if gross_loss else math.inf),
    }


def flatten(by_session: Dict[str, List[Trade]]) -> List[Trade]:
    out: List[Trade] = []
    for trades in by_session.values():
        out.extend(trades)
    return sorted(out, key=lambda t: (t.entry_ts, t.trade_id))


def by_session(trades: Iterable[Trade]) -> Dict[str, List[Trade]]:
    out: Dict[str, List[Trade]] = {}
    for trade in trades:
        out.setdefault(trade.session, []).append(trade)
    for session in out:
        out[session] = sorted(out[session], key=lambda t: (t.entry_ts, t.trade_id))
    return out


def find_prior_same_day(
    trade: Trade,
    candidates_by_session: Dict[str, List[Trade]],
    *,
    side: Optional[str],
) -> Optional[Trade]:
    candidates = candidates_by_session.get(trade.session, [])
    usable = [
        t
        for t in candidates
        if t.entry_ts < trade.entry_ts and (side is None or t.side == side)
    ]
    if not usable:
        return None
    return max(usable, key=lambda t: (t.entry_ts, t.trade_id))


def classify_subjects(
    subjects: Sequence[Trade],
    priors_by_session: Dict[str, List[Trade]],
) -> List[TimingRow]:
    rows: List[TimingRow] = []
    for trade in subjects:
        prior_aligned = find_prior_same_day(trade, priors_by_session, side=trade.side)
        if prior_aligned is not None:
            rows.append(TimingRow(trade, prior_aligned, "prior_aligned"))
            continue
        prior_any = find_prior_same_day(trade, priors_by_session, side=None)
        if prior_any is None:
            rows.append(TimingRow(trade, None, "no_prior_signal"))
        else:
            rows.append(TimingRow(trade, prior_any, "prior_opposed"))
    return rows


def write_csv(path: Path, rows: Sequence[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_timing_rows(path: Path, rows: Sequence[TimingRow], *, subject_prefix: str, prior_prefix: str) -> None:
    out = []
    for row in rows:
        subject = row.subject
        prior = row.prior
        out.append(
            {
                "session": subject.session,
                "bucket": row.bucket,
                f"{subject_prefix}_trade_id": subject.trade_id,
                f"{subject_prefix}_side": subject.side,
                f"{subject_prefix}_entry_ts": subject.entry_ts.isoformat(),
                f"{subject_prefix}_exit_ts": subject.exit_ts.isoformat(),
                f"{subject_prefix}_pnl_usd": "%.2f" % subject.pnl_usd,
                f"{prior_prefix}_trade_id": prior.trade_id if prior else "",
                f"{prior_prefix}_side": prior.side if prior else "",
                f"{prior_prefix}_entry_ts": prior.entry_ts.isoformat() if prior else "",
                f"{prior_prefix}_exit_ts": prior.exit_ts.isoformat() if prior else "",
                f"{prior_prefix}_pnl_usd": "%.2f" % prior.pnl_usd if prior else "",
            }
        )
    write_csv(path, out)


def markdown_table(rows: Sequence[Dict[str, str]]) -> str:
    if not rows:
        return ""
    fields = list(rows[0].keys())
    lines = [
        "| " + " | ".join(fields) + " |",
        "| " + " | ".join(["---"] * len(fields)) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row.get(f, "") for f in fields) + " |")
    return "\n".join(lines)


def build_report(
    *,
    output_root: Path,
    st_fills: Path,
    st_strategy_id: str,
    v2b_fills: Path,
    start_date: date,
    point_value: float,
    fee_per_unit: float,
) -> None:
    output_root.mkdir(parents=True, exist_ok=True)

    st_trades = [
        t
        for t in load_strategy_trades(
            st_fills,
            strategy_id=st_strategy_id,
            point_value=point_value,
            fee_per_unit=fee_per_unit,
        )
        if t.entry_ts.date() >= start_date
    ]
    st_trades = sorted(st_trades, key=lambda t: (t.entry_ts, t.trade_id))
    v2b_by_session = load_v2b_trades(v2b_fills, point_value=point_value, fee_per_unit=fee_per_unit)
    v2b_trades = [t for t in flatten(v2b_by_session) if t.entry_ts.date() >= start_date]

    st_by_session = by_session(st_trades)
    v2b_by_session = by_session(v2b_trades)

    v2b_timing = classify_subjects(v2b_trades, st_by_session)
    st_timing = classify_subjects(st_trades, v2b_by_session)

    v2b_summary = [summarize_trades("v2b_base_all", v2b_trades)]
    for bucket in ["prior_aligned", "prior_opposed", "no_prior_signal"]:
        v2b_summary.append(summarize_trades("v2b_" + bucket, [r.subject for r in v2b_timing if r.bucket == bucket]))

    st_summary = [summarize_trades("st_pmc_base_all", st_trades)]
    for bucket in ["prior_aligned", "prior_opposed", "no_prior_signal"]:
        st_summary.append(summarize_trades("st_pmc_" + bucket, [r.subject for r in st_timing if r.bucket == bucket]))

    write_csv(output_root / "v2b_timing_summary.csv", v2b_summary)
    write_csv(output_root / "st_pmc_timing_summary.csv", st_summary)
    write_timing_rows(output_root / "v2b_trade_timing.csv", v2b_timing, subject_prefix="v2b", prior_prefix="st_pmc")
    write_timing_rows(output_root / "st_pmc_trade_timing.csv", st_timing, subject_prefix="st_pmc", prior_prefix="v2b")

    v2b_base = v2b_summary[0]
    v2b_aligned = v2b_summary[1]
    v2b_opposed = v2b_summary[2]
    st_base = st_summary[0]
    st_aligned = st_summary[1]
    st_opposed = st_summary[2]

    def f(row: Dict[str, str], key: str) -> float:
        return float(row[key])

    v2b_aligned_wr_delta = f(v2b_aligned, "win_rate_pct") - f(v2b_base, "win_rate_pct")
    v2b_opposed_wr_delta = f(v2b_opposed, "win_rate_pct") - f(v2b_base, "win_rate_pct")
    st_aligned_wr_delta = f(st_aligned, "win_rate_pct") - f(st_base, "win_rate_pct")
    st_opposed_wr_delta = f(st_opposed, "win_rate_pct") - f(st_base, "win_rate_pct")

    index = f"""# MNQ v2b / ST+PMC Causal Timing Study

This report asks two separate causal questions:

1. **v2b second:** when MNQ hourly ST+PMC has already fired earlier in the session, how does a later same-direction MNQ v2b trade behave versus base v2b?
2. **ST+PMC second:** when MNQ v2b has already fired earlier in the session, how does a later same-direction MNQ hourly ST+PMC trade behave versus base ST+PMC?

Definitions:

- `prior_aligned`: the other strategy already had a same-session entry in the same direction before the subject trade entry.
- `prior_opposed`: the other strategy already had a same-session entry, but only in the opposite direction before the subject trade entry.
- `no_prior_signal`: no earlier same-session entry from the other strategy.
- Same-timestamp entries are not treated as prior information.

## v2b As The Second Signal

{markdown_table(v2b_summary)}

## ST+PMC As The Second Signal

{markdown_table(st_summary)}

## Read

- **v2b after same-direction ST+PMC is not better than base v2b** in this pass: win rate changes by {v2b_aligned_wr_delta:+.2f} pct points, PF drops from {v2b_base["profit_factor"]} to {v2b_aligned["profit_factor"]}, and average trade drops from ${v2b_base["avg_usd"]} to ${v2b_aligned["avg_usd"]}.
- **v2b after opposite-direction ST+PMC is the strongest v2b timing bucket**: win rate changes by {v2b_opposed_wr_delta:+.2f} pct points, PF improves to {v2b_opposed["profit_factor"]}, and average trade rises to ${v2b_opposed["avg_usd"]}. This looks more like a failed hourly ST+PMC / intraday reversal gate than an alignment gate.
- **ST+PMC after same-direction v2b improves modestly versus base ST+PMC**: win rate changes by {st_aligned_wr_delta:+.2f} pct points, PF improves from {st_base["profit_factor"]} to {st_aligned["profit_factor"]}, and average trade rises from ${st_base["avg_usd"]} to ${st_aligned["avg_usd"]}.
- **ST+PMC after opposite-direction v2b is weaker**: win rate changes by {st_opposed_wr_delta:+.2f} pct points and PF drops to {st_opposed["profit_factor"]}.

Practical first model idea: use **v2b as a potential confirmation gate for later ST+PMC**, but do not use same-direction ST+PMC as a v2b size-up gate yet. For v2b, the stronger research branch is the opposite-direction prior ST+PMC bucket, which needs chart review before treating it as a live sizing signal.

## Files

- `v2b_timing_summary.csv`
- `st_pmc_timing_summary.csv`
- `v2b_trade_timing.csv`
- `st_pmc_trade_timing.csv`
"""
    (output_root / "INDEX.md").write_text(index)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Causal timing study for MNQ v2b and MNQ hourly ST+PMC.")
    parser.add_argument("--output-root", type=Path, default=REPO / "live/state/mnq_v2b_st_pmc_timing_study")
    parser.add_argument(
        "--st-fills",
        type=Path,
        default=REPO / "live/state/hourly_st_pmc_strategyplugin_variants_cross_market/mnq/combined_state/fills.csv",
    )
    parser.add_argument("--st-strategy-id", default="mnq_hourly_st_pmc_sl25_tp75_3r")
    parser.add_argument(
        "--v2b-fills",
        type=Path,
        default=REPO / "live/state/v2b_sizing_sweep/states/mnq_v2b_sizing_S_1_1_3/fills.csv",
    )
    parser.add_argument("--start-date", default="2021-03-04")
    parser.add_argument("--point-value", type=float, default=2.0)
    parser.add_argument("--fee-per-unit", type=float, default=1.50)
    args = parser.parse_args(argv)
    build_report(
        output_root=args.output_root,
        st_fills=args.st_fills,
        st_strategy_id=args.st_strategy_id,
        v2b_fills=args.v2b_fills,
        start_date=date.fromisoformat(args.start_date),
        point_value=args.point_value,
        fee_per_unit=args.fee_per_unit,
    )
    print("Wrote %s" % (args.output_root / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
