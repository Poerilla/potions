from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[1]
MNQ_ROOT = REPO / "mnq"
V2D = MNQ_ROOT / "v2d"
CASE = MNQ_ROOT / "case_studies" / "midnight_open_hourly_charts"
SCRIPTS = REPO / "scripts"
DEFAULT_DBN = MNQ_ROOT / "raw" / "extracted_new" / "glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst"
SETUPS = MNQ_ROOT / "case_studies" / "daily_candlestick_theory" / "setups.csv"
HISTORY_START = date(2021, 3, 4)
POINT_VALUE = 2.0

sys.path[:0] = [str(MNQ_ROOT), str(SCRIPTS), str(V2D), str(CASE)]

from benchmark_v2b_scaleout_candidates import (  # noqa: E402
    causal_regime_v2b,
    load_c3_days,
    v2b_scaleout_session,
)
from mtm_v2b_scaleout import closed_dd, portfolio_mtm_dd_simple  # noqa: E402
from paper_replay_v2b_scaleout_ordering import (  # noqa: E402
    replay_long_then_short_strict,
    replay_oco_bracket_reverse,
)

import build_midnight_open_hourly_charts as mdata  # noqa: E402


@dataclass(frozen=True)
class VariantResult:
    name: str
    slug: str
    source: str
    timing: str
    trades: int
    units: int
    net_usd: float
    closed_dd_usd: float
    intrabar_stress_dd_usd: float
    max_open_units: int
    win_rate: float
    profit_factor: float
    notes: str

    @property
    def net_over_stress(self) -> float:
        return self.net_usd / abs(self.intrabar_stress_dd_usd) if self.intrabar_stress_dd_usd else 0.0


def money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return sign + f"{abs(value):,.2f}"


def profit_factor(values: Iterable[float]) -> float:
    arr = np.array(list(values), dtype=float)
    wins = float(arr[arr > 0].sum())
    losses = abs(float(arr[arr < 0].sum()))
    if losses <= 1e-9:
        return math.inf if wins > 0 else 0.0
    return wins / losses


def win_rate(values: Iterable[float]) -> float:
    arr = np.array(list(values), dtype=float)
    return 100.0 * float((arr > 0).mean()) if len(arr) else 0.0


def scaleout_variant(
    *,
    name: str,
    slug: str,
    gby: Dict[date, pd.DataFrame],
    regime: pd.Series,
    day_filter: Callable[[date], bool],
    replay_fn: Callable,
    notes: str,
) -> VariantResult:
    all_legs = []
    all_curves = []
    for session_day in sorted(gby.keys()):
        if session_day < HISTORY_START:
            continue
        if not day_filter(session_day):
            continue
        replayed = replay_fn(session_day, gby[session_day])
        legs, curves = replayed[0], replayed[1]
        if not legs:
            continue
        all_legs.extend(legs)
        all_curves.extend(curves)
    pnl = np.array([leg.net_usd for leg in all_legs], dtype=float)
    mtm_dd, _mtm_pct, net = portfolio_mtm_dd_simple(all_legs, all_curves)
    return VariantResult(
        name=name,
        slug=slug,
        source="fresh 1m DBN replay",
        timing="1m broker-like",
        trades=len(all_legs),
        units=len(all_legs) * 2,
        net_usd=net,
        closed_dd_usd=-closed_dd(pnl),
        intrabar_stress_dd_usd=-mtm_dd,
        max_open_units=2,
        win_rate=win_rate(pnl),
        profit_factor=profit_factor(pnl),
        notes=notes,
    )


def csv_clean_variant(path: Path, name: str, slug: str, qty_field: str = "qty_start") -> Optional[VariantResult]:
    if not path.exists():
        return None
    rows = read_csv(path)
    traded = [
        row
        for row in rows
        if as_float(row.get("entry")) or as_float(row.get(qty_field)) > 0 or row.get("result") not in {"No-Op", "Skipped", ""}
    ]
    if not traded:
        return None
    pnl = np.array([as_float(row.get("usd")) for row in traded], dtype=float)
    stress_samples: List[float] = []
    realized = 0.0
    peak = 0.0
    max_dd = 0.0
    max_open = 1
    for row, net in zip(traded, pnl):
        qty = int(as_float(row.get(qty_field)) or 1)
        max_open = max(max_open, qty)
        mae = abs(as_float(row.get("mae_pts")))
        stress = realized - mae * POINT_VALUE * max(qty, 1)
        peak = max(peak, realized)
        max_dd = max(max_dd, peak - stress)
        realized += net
        peak = max(peak, realized)
        max_dd = max(max_dd, peak - realized)
        stress_samples.append(stress)
    return VariantResult(
        name=name,
        slug=slug,
        source=str(path),
        timing="5m broker-like artifact",
        trades=len(traded),
        units=sum(int(as_float(row.get(qty_field)) or 1) for row in traded),
        net_usd=float(pnl.sum()),
        closed_dd_usd=-closed_dd(pnl),
        intrabar_stress_dd_usd=-max_dd,
        max_open_units=max_open,
        win_rate=win_rate(pnl),
        profit_factor=profit_factor(pnl),
        notes="Uses existing 5m-causal artifact rows; intrabar stress estimated from per-trade MAE fields.",
    )


def child_csv_variant(
    path: Path,
    name: str,
    slug: str,
    *,
    regime_filter: Optional[str] = None,
) -> Optional[VariantResult]:
    if not path.exists():
        return None
    rows = read_csv(path)
    if regime_filter is not None:
        rows = [row for row in rows if row.get("Regime") == regime_filter]
    if not rows:
        return None
    pnl = np.array([as_float(row.get("Net_$")) for row in rows], dtype=float)
    max_dd = aggregate_intrabar_stress_from_rows(rows)
    return VariantResult(
        name=name,
        slug=slug,
        source=str(path),
        timing="1m child artifact audit",
        trades=len(rows),
        units=sum(max(int(as_float(row.get("Contracts")) or 1), 1) for row in rows),
        net_usd=float(pnl.sum()),
        closed_dd_usd=-closed_dd(pnl),
        intrabar_stress_dd_usd=-max_dd,
        max_open_units=max(max(int(as_float(row.get("Contracts")) or 1), 1) for row in rows),
        win_rate=win_rate(pnl),
        profit_factor=profit_factor(pnl),
        notes="Uses child artifact rows. Stress is approximated from aggregate average entry, max contracts, and stop/target span because child-level unit exits are not expanded.",
    )


def aggregate_intrabar_stress_from_rows(rows: List[Dict[str, str]]) -> float:
    realized = 0.0
    peak = 0.0
    max_dd = 0.0
    for row in rows:
        direction = row.get("Trade_Direction", "Long")
        entry = as_float(row.get("Entry_Price") or row.get("Tier1_Entry"))
        stop = as_float(row.get("Stop_Price"))
        exit_px = as_float(row.get("Exit_Price"))
        contracts = max(int(as_float(row.get("Contracts")) or 1), 1)
        if entry and stop:
            adverse_pts = max(0.0, entry - stop) if direction == "Long" else max(0.0, stop - entry)
        else:
            adverse_pts = abs(entry - exit_px)
        peak = max(peak, realized)
        stress = realized - adverse_pts * POINT_VALUE * contracts
        max_dd = max(max_dd, peak - stress)
        realized += as_float(row.get("Net_$"))
        peak = max(peak, realized)
        max_dd = max(max_dd, peak - realized)
    return max_dd


def simple_csv_net_variant(path: Path, name: str, slug: str) -> Optional[VariantResult]:
    if not path.exists():
        return None
    rows = read_csv(path)
    if not rows or "Net_$" not in rows[0]:
        return None
    pnl = np.array([as_float(row.get("Net_$")) for row in rows], dtype=float)
    max_dd = aggregate_intrabar_stress_from_rows(rows)
    return VariantResult(
        name=name,
        slug=slug,
        source=str(path),
        timing="artifact audit",
        trades=len(rows),
        units=len(rows),
        net_usd=float(pnl.sum()),
        closed_dd_usd=-closed_dd(pnl),
        intrabar_stress_dd_usd=-max_dd,
        max_open_units=1,
        win_rate=win_rate(pnl),
        profit_factor=profit_factor(pnl),
        notes="Existing artifact audited with approximate intrabar stress from entry/stop span.",
    )


def as_float(value) -> float:
    if value is None or value == "":
        return 0.0
    try:
        if pd.isna(value):
            return 0.0
    except TypeError:
        pass
    return float(value)


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def result_row(result: VariantResult) -> Dict[str, str]:
    return {
        "candidate": result.name,
        "slug": result.slug,
        "source": result.source,
        "timing": result.timing,
        "trades": str(result.trades),
        "units": str(result.units),
        "net_usd": "%.2f" % result.net_usd,
        "closed_dd_usd": "%.2f" % result.closed_dd_usd,
        "intrabar_stress_dd_usd": "%.2f" % result.intrabar_stress_dd_usd,
        "max_open_units": str(result.max_open_units),
        "win_rate_pct": "%.2f" % result.win_rate,
        "profit_factor": "%.3f" % result.profit_factor if math.isfinite(result.profit_factor) else "inf",
        "net_over_stress_dd": "%.2f" % result.net_over_stress,
        "notes": result.notes,
    }


def write_markdown(path: Path, results: List[VariantResult]) -> None:
    ranked = sorted(results, key=lambda item: item.net_over_stress, reverse=True)
    lines = [
        "# V2B Family Broker-Like Replay Ranking",
        "",
        "Purpose: compare the v2b family on implementable timing assumptions. The strongest-confidence rows are `1m broker-like` because they were freshly replayed from completed 1-minute bars. `5m broker-like artifact` and `artifact audit` rows are useful triage, but should graduate to full StrategyPlugin/PaperBroker replay before promotion.",
        "",
        "| Rank | Candidate | Timing | Trades | Units | Net | Closed DD | Intrabar Stress DD | Max Units | Net / Stress | Win % | PF |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for idx, result in enumerate(ranked, start=1):
        pf = "%.2f" % result.profit_factor if math.isfinite(result.profit_factor) else "inf"
        lines.append(
            "| %d | %s | %s | %d | %d | $%s | $%s | $%s | %d | %.2f | %.1f%% | %s |"
            % (
                idx,
                result.name,
                result.timing,
                result.trades,
                result.units,
                money(result.net_usd),
                money(result.closed_dd_usd),
                money(result.intrabar_stress_dd_usd),
                result.max_open_units,
                result.net_over_stress,
                result.win_rate,
                pf,
            )
        )
    lines.extend(
        [
            "",
            "## Read",
            "",
            "- The main promotion test is `Net / Stress DD`, not net alone.",
            "- Any child or clean-break artifact that ranks high should be rebuilt as a real intraday `StrategyPlugin` before it competes with the daily broker-like candidates.",
            "- Rows with approximate stress use the best available artifact fields and are intentionally labeled that way.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def run(output_root: Path) -> List[VariantResult]:
    output_root.mkdir(parents=True, exist_ok=True)
    print("Loading MNQ 1m DBN for v2b family...", flush=True)
    gby = mdata.load_1m_by_ny_date(DEFAULT_DBN.resolve(), "mnq")
    regime = causal_regime_v2b()
    c3_days = load_c3_days(SETUPS) if SETUPS.exists() else set()

    def is_regime(day: date) -> bool:
        return day in regime.index and bool(regime.loc[day])

    results: List[VariantResult] = [
        scaleout_variant(
            name="v2b scaleout x2 MA50>MA150 long-priority",
            slug="mnq_v2b_scaleout_x2_ma50_150_long_priority",
            gby=gby,
            regime=regime,
            day_filter=is_regime,
            replay_fn=v2b_scaleout_session,
            notes="Fresh 1m replay. Long leg is scanned first; short leg can fire after leg 1 exits.",
        ),
        scaleout_variant(
            name="v2b scaleout x2 MA50>MA150 OCO then reverse",
            slug="mnq_v2b_scaleout_x2_ma50_150_oco_reverse",
            gby=gby,
            regime=regime,
            day_filter=is_regime,
            replay_fn=replay_oco_bracket_reverse,
            notes="Fresh 1m replay. Both sides are live after OR; first trigger wins, then opposite side may arm after exit.",
        ),
        scaleout_variant(
            name="v2b scaleout x2 MA50>MA150 strict long-then-short",
            slug="mnq_v2b_scaleout_x2_ma50_150_strict_long_then_short",
            gby=gby,
            regime=regime,
            day_filter=is_regime,
            replay_fn=replay_long_then_short_strict,
            notes="Fresh 1m replay. If long never fills, short is skipped.",
        ),
        scaleout_variant(
            name="v2b scaleout x2 C3 days only",
            slug="mnq_v2b_scaleout_x2_c3_only",
            gby=gby,
            regime=regime,
            day_filter=lambda day: day in c3_days,
            replay_fn=v2b_scaleout_session,
            notes="Diagnostic C3 calendar filter, no MA regime gate.",
        ),
        scaleout_variant(
            name="v2b scaleout x2 C3 + MA50>MA150",
            slug="mnq_v2b_scaleout_x2_c3_ma50_150",
            gby=gby,
            regime=regime,
            day_filter=lambda day: day in c3_days and is_regime(day),
            replay_fn=v2b_scaleout_session,
            notes="C3 calendar filter plus causal MA regime gate.",
        ),
    ]

    for maybe_result in [
        csv_clean_variant(MNQ_ROOT / "mnq_v2b_clean_break_bullish.csv", "v2b clean break bullish 2R", "mnq_v2b_clean_break_bullish_2r"),
        csv_clean_variant(
            MNQ_ROOT / "mnq_v2b_clean_break_4th_candle_boundary_stop.csv",
            "v2b 09:45 clean break boundary stop",
            "mnq_v2b_clean_break_4th_boundary_stop",
        ),
        csv_clean_variant(
            MNQ_ROOT / "mnq_v2b_clean_break_4th_candle_ladder3_runner.csv",
            "v2b 09:45 clean break ladder3 runner",
            "mnq_v2b_clean_break_4th_ladder3_runner",
        ),
        child_csv_variant(
            MNQ_ROOT / "case_studies" / "v2b_child" / "mnq_orb_open_limit_v2b_child.csv",
            "v2b child max 1 add",
            "mnq_v2b_child_1add",
        ),
        child_csv_variant(
            MNQ_ROOT / "case_studies" / "v2b_child" / "mnq_orb_open_limit_v2b_child_3max.csv",
            "v2b child max 2 adds",
            "mnq_v2b_child_2adds",
        ),
        child_csv_variant(
            V2D / "mnq_orb_results_adaptive_50_150_child_3max.csv",
            "adaptive child Regime=v2b only",
            "mnq_adaptive_child_regime_v2b",
            regime_filter="v2b",
        ),
        child_csv_variant(
            V2D / "mnq_orb_results_adaptive_50_150_inside_v2b_close_child_3max.csv",
            "adaptive inside-v2b close child Regime=v2b",
            "mnq_adaptive_inside_v2b_close_child_regime_v2b",
            regime_filter="v2b",
        ),
        simple_csv_net_variant(
            MNQ_ROOT / "case_studies" / "v2b_m" / "v2b_m_legs.csv",
            "v2b_m long-only monthly bias",
            "mnq_v2b_m_long_only",
        ),
    ]:
        if maybe_result is not None:
            results.append(maybe_result)

    ranked = sorted(results, key=lambda item: item.net_over_stress, reverse=True)
    write_csv(output_root / "v2b_family_broker_like_summary.csv", [result_row(result) for result in ranked])
    write_markdown(output_root / "V2B_FAMILY_BROKER_LIKE.md", ranked)
    return ranked


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run MNQ v2b family broker-like replay ranking.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("potions/live/state/broker_like_replays_monthly_boundary_stop_test/v2b_family"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    results = run(args.output_root)
    for result in results[:8]:
        print(
            "%s net=$%s stress=$%s ratio=%.2f"
            % (result.slug, money(result.net_usd), money(result.intrabar_stress_dd_usd), result.net_over_stress),
            flush=True,
        )
    print("Wrote %s" % args.output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
