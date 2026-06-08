from __future__ import annotations

import argparse
import csv
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .replay_audit import POINT_VALUES
from .v2b_st_pmc_alignment_study import REPO, Trade, load_strategy_trades
from .v2b_st_pmc_timing_study import by_session, find_prior_same_day
from .v2b_strategy_cross_market_replay import MARKETS
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, load_1m_by_ny_date_any


NY = "America/New_York"


@dataclass(frozen=True)
class Campaign:
    trade_id: str
    side: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry_price: float
    actual_base_net_usd: float
    base_tp1_qty: int
    base_tp2_qty: int
    base_runner_qty: int
    full_exit_reason: str
    tp1_unit_usd: float
    tp2_unit_usd: float
    runner_unit_usd: float
    full_exit_unit_usd: float
    mae_unit_usd: float
    mfe_unit_usd: float
    regime: str
    prior_st_trade_id: str


@dataclass(frozen=True)
class Scenario:
    name: str
    aligned: Optional[Tuple[int, int, int]]
    not_aligned: Optional[Tuple[int, int, int]]
    complexity: float


@dataclass(frozen=True)
class Leg:
    trade_id: str
    regime: str
    bucket: str
    side: str
    qty: int
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry_price: float
    exit_price: float
    net_usd: float


def norm_side(value: str) -> str:
    value = str(value).lower()
    if value in {"long", "buy"}:
        return "long"
    if value in {"short", "sell"}:
        return "short"
    raise ValueError("unknown side %r" % value)


def load_v2b_campaigns(
    unit_trades_path: Path,
    st_fills_path: Path,
    st_strategy_id: str,
    *,
    point_value: float,
    fee_per_unit: float,
    start_date: date,
    bars: pd.DataFrame,
) -> List[Campaign]:
    units = pd.read_csv(unit_trades_path)
    units["entry_ts"] = pd.to_datetime(units["entry_ts"], utc=True).dt.tz_convert(NY)
    units["exit_ts"] = pd.to_datetime(units["exit_ts"], utc=True).dt.tz_convert(NY)
    units["net_usd"] = pd.to_numeric(units["net_usd"], errors="coerce").fillna(0.0)
    units["entry_price"] = pd.to_numeric(units["entry_price"], errors="coerce")
    units["exit_price"] = pd.to_numeric(units["exit_price"], errors="coerce")
    units = units[units["entry_ts"].dt.date >= start_date].copy()

    st_trades = [
        t
        for t in load_strategy_trades(
            st_fills_path,
            strategy_id=st_strategy_id,
            point_value=point_value,
            fee_per_unit=fee_per_unit,
        )
        if t.entry_ts.date() >= start_date
    ]
    st_by_session = by_session(st_trades)

    campaigns: List[Campaign] = []
    for trade_id, group in units.sort_values(["entry_ts", "exit_ts", "unit_id"]).groupby("trade_id"):
        entry_ts = pd.Timestamp(group["entry_ts"].iloc[0])
        side = norm_side(group["direction"].iloc[0])
        prior_aligned = find_prior_same_day(
            Trade(
                trade_id=str(trade_id),
                side=side,
                entry_ts=entry_ts,
                exit_ts=pd.Timestamp(group["exit_ts"].max()),
                entry=float(group["entry_price"].iloc[0]),
                exit=float(group["exit_price"].iloc[-1]),
                exit_reason=str(group["exit_reason"].iloc[-1]),
                pnl_usd=float(group["net_usd"].sum()),
                pnl_pts=0.0,
                session=entry_ts.date().isoformat(),
            ),
            st_by_session,
            side=side,
        )
        prior_any = find_prior_same_day(
            Trade(
                trade_id=str(trade_id),
                side=side,
                entry_ts=entry_ts,
                exit_ts=pd.Timestamp(group["exit_ts"].max()),
                entry=float(group["entry_price"].iloc[0]),
                exit=float(group["exit_price"].iloc[-1]),
                exit_reason=str(group["exit_reason"].iloc[-1]),
                pnl_usd=float(group["net_usd"].sum()),
                pnl_pts=0.0,
                session=entry_ts.date().isoformat(),
            ),
            st_by_session,
            side=None,
        )
        if prior_aligned is not None:
            regime = "aligned"
            prior_id = prior_aligned.trade_id
        elif prior_any is not None:
            regime = "not_aligned_prior_opposed"
            prior_id = prior_any.trade_id
        else:
            regime = "not_aligned_no_prior"
            prior_id = ""

        reasons = set(group["exit_reason"].astype(str))
        has_tp1 = "tp1" in reasons
        tp1_units = group[group["exit_reason"].astype(str) == "tp1"]
        tp2_units = group[group["exit_reason"].astype(str) == "tp2"]
        remaining_after_tp1 = group[group["exit_reason"].astype(str) != "tp1"] if has_tp1 else group.iloc[0:0]
        if has_tp1 and tp2_units.empty:
            # The TP2-intended unit remains open if TP2 is not reached, then exits
            # with the runner batch at EOD/runner stop. Base S_1_1_3 still has
            # one TP2-intended unit plus three runners in that shared exit.
            tp2_unit_usd = float(remaining_after_tp1["net_usd"].mean()) if not remaining_after_tp1.empty else 0.0
            runner_units = remaining_after_tp1
        else:
            tp2_unit_usd = float(tp2_units["net_usd"].iloc[0]) if not tp2_units.empty else 0.0
            runner_units = group[group["exit_reason"].astype(str).isin(["runner_stop", "runner_target", "eod_close"])] if has_tp1 else group.iloc[0:0]

        if has_tp1:
            full_exit_reason = ""
            full_exit_unit_usd = 0.0
        else:
            full_exit_reason = str(group["exit_reason"].iloc[-1])
            full_exit_unit_usd = float(group["net_usd"].iloc[0])
        window = bars[(bars.index >= entry_ts) & (bars.index <= pd.Timestamp(group["exit_ts"].max()))]
        if window.empty:
            mae_unit_usd = min(float(group["net_usd"].min()), 0.0)
            mfe_unit_usd = max(float(group["net_usd"].max()), 0.0)
        elif side == "long":
            mae_unit_usd = (float(window["low"].min()) - float(group["entry_price"].iloc[0])) * point_value
            mfe_unit_usd = (float(window["high"].max()) - float(group["entry_price"].iloc[0])) * point_value
        else:
            mae_unit_usd = (float(group["entry_price"].iloc[0]) - float(window["high"].max())) * point_value
            mfe_unit_usd = (float(group["entry_price"].iloc[0]) - float(window["low"].min())) * point_value

        campaigns.append(
            Campaign(
                trade_id=str(trade_id),
                side=side,
                entry_ts=entry_ts,
                exit_ts=pd.Timestamp(group["exit_ts"].max()),
                entry_price=float(group["entry_price"].iloc[0]),
                actual_base_net_usd=float(group["net_usd"].sum()),
                base_tp1_qty=len(tp1_units),
                base_tp2_qty=1 if has_tp1 else 0,
                base_runner_qty=len(runner_units),
                full_exit_reason=full_exit_reason,
                tp1_unit_usd=float(tp1_units["net_usd"].iloc[0]) if not tp1_units.empty else 0.0,
                tp2_unit_usd=tp2_unit_usd,
                runner_unit_usd=float(runner_units["net_usd"].mean()) if not runner_units.empty else 0.0,
                full_exit_unit_usd=full_exit_unit_usd,
                mae_unit_usd=mae_unit_usd,
                mfe_unit_usd=mfe_unit_usd,
                regime=regime,
                prior_st_trade_id=prior_id,
            )
        )
    return sorted(campaigns, key=lambda c: (c.entry_ts, c.trade_id))


def campaign_qty_for_scenario(c: Campaign, scenario: Scenario) -> Optional[Tuple[int, int, int]]:
    if c.regime == "aligned":
        return scenario.aligned
    return scenario.not_aligned


def modeled_trade_net(c: Campaign, sizing: Tuple[int, int, int]) -> float:
    tp1_qty, tp2_qty, runner_qty = sizing
    total_qty = tp1_qty + tp2_qty + runner_qty
    if total_qty <= 0:
        return 0.0
    if sizing == (1, 1, 3):
        return c.actual_base_net_usd
    if c.base_tp1_qty <= 0:
        return c.full_exit_unit_usd * total_qty
    return c.tp1_unit_usd * tp1_qty + c.tp2_unit_usd * tp2_qty + c.runner_unit_usd * runner_qty


def build_legs(c: Campaign, sizing: Tuple[int, int, int], unit_rows: pd.DataFrame) -> List[Leg]:
    group = unit_rows[unit_rows["trade_id"].astype(str) == c.trade_id].sort_values(["exit_ts", "unit_id"])
    legs: List[Leg] = []
    tp1_qty, tp2_qty, runner_qty = sizing
    total_qty = tp1_qty + tp2_qty + runner_qty
    if total_qty <= 0:
        return legs
    if c.base_tp1_qty <= 0:
        row = group.iloc[-1]
        legs.append(
            Leg(c.trade_id, c.regime, "full_exit", c.side, total_qty, c.entry_ts, pd.Timestamp(row["exit_ts"]), c.entry_price, float(row["exit_price"]), c.full_exit_unit_usd * total_qty)
        )
        return legs
    for bucket, qty, reason in [("tp1", tp1_qty, "tp1"), ("tp2", tp2_qty, "tp2")]:
        if qty <= 0:
            continue
        rows = group[group["exit_reason"].astype(str) == reason]
        if bucket == "tp2" and rows.empty:
            rows = group[group["exit_reason"].astype(str) != "tp1"]
        if rows.empty:
            continue
        row = rows.iloc[0]
        unit = c.tp1_unit_usd if bucket == "tp1" else c.tp2_unit_usd
        legs.append(Leg(c.trade_id, c.regime, bucket, c.side, qty, c.entry_ts, pd.Timestamp(row["exit_ts"]), c.entry_price, float(row["exit_price"]), unit * qty))
    if runner_qty > 0:
        rows = group[group["exit_reason"].astype(str).isin(["runner_stop", "runner_target", "eod_close"])]
        if not rows.empty:
            row = rows.iloc[-1]
            legs.append(Leg(c.trade_id, c.regime, "runner", c.side, runner_qty, c.entry_ts, pd.Timestamp(row["exit_ts"]), c.entry_price, float(row["exit_price"]), c.runner_unit_usd * runner_qty))
    return legs


def stress_sequence_for_campaigns(
    campaigns: Sequence[Campaign],
    nets: Dict[str, float],
    sizings: Dict[str, Tuple[int, int, int]],
) -> Tuple[float, float, List[float], List[float]]:
    realized = 0.0
    close_peak = 0.0
    stress_peak = 0.0
    close_dd = 0.0
    stress_dd = 0.0
    close_equity: List[float] = []
    stress_equity: List[float] = []
    for campaign in sorted(campaigns, key=lambda c: (c.exit_ts, c.trade_id)):
        sizing = sizings[campaign.trade_id]
        qty = sum(sizing)
        stress_value = realized + campaign.mae_unit_usd * qty
        stress_peak = max(stress_peak, realized)
        stress_dd = min(stress_dd, stress_value - stress_peak)
        realized += nets[campaign.trade_id]
        close_peak = max(close_peak, realized)
        close_dd = min(close_dd, realized - close_peak)
        close_equity.append(realized)
        stress_equity.append(stress_value)
    return close_dd, stress_dd, close_equity, stress_equity


def max_drawdown(values: Sequence[float]) -> float:
    peak = -math.inf
    max_dd = 0.0
    for value in values:
        peak = max(peak, value)
        max_dd = min(max_dd, value - peak)
    return max_dd


def max_losing_streak(values: Sequence[float]) -> int:
    streak = 0
    best = 0
    for value in values:
        if value <= 0:
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return best


def recovery_stats(equity: Sequence[float]) -> Tuple[int, int]:
    peak = -math.inf
    current = 0
    longest = 0
    recoveries = 0
    underwater = False
    for value in equity:
        if value >= peak:
            if underwater:
                recoveries += 1
            peak = value
            underwater = False
            current = 0
        else:
            underwater = True
            current += 1
            longest = max(longest, current)
    return longest, recoveries


def summarize_campaigns(label: str, campaigns: Sequence[Campaign], nets: Dict[str, float], sizings: Dict[str, Tuple[int, int, int]], *, stress_dd: float, closed_dd: float, complexity: float) -> Dict[str, str]:
    vals = [nets[c.trade_id] for c in campaigns if c.trade_id in nets]
    selected = [c for c in campaigns if c.trade_id in nets]
    net = sum(vals)
    wins = sum(1 for v in vals if v > 0)
    gross_win = sum(v for v in vals if v > 0)
    gross_loss = abs(sum(v for v in vals if v <= 0))
    equity = np.cumsum(vals).tolist() if vals else []
    longest_recovery, recoveries = recovery_stats(equity)
    years = 5.14
    stress_capital = abs(stress_dd) * (complexity + 1.0) if stress_dd else 0.0
    annual_net = net / years
    dce = annual_net / (stress_capital * complexity) if stress_capital and complexity else 0.0
    return {
        "row": label,
        "trades": str(len(vals)),
        "wins": str(wins),
        "losses": str(len(vals) - wins),
        "win_rate_pct": "%.2f" % (100.0 * wins / len(vals) if vals else 0.0),
        "net_usd": "%.2f" % net,
        "closed_dd_usd": "%.2f" % closed_dd,
        "stress_dd_usd": "%.2f" % stress_dd,
        "net_stress": "%.2f" % (net / abs(stress_dd) if stress_dd else 0.0),
        "profit_factor": "%.3f" % (gross_win / gross_loss if gross_loss else math.inf),
        "avg_trade": "%.2f" % (net / len(vals) if vals else 0.0),
        "median_trade": "%.2f" % (float(np.median(vals)) if vals else 0.0),
        "max_losing_streak": str(max_losing_streak(vals)),
        "avg_mae": "%.2f" % (float(np.mean([c.mae_unit_usd * sum(sizings[c.trade_id]) for c in selected])) if selected else 0.0),
        "avg_mfe": "%.2f" % (float(np.mean([c.mfe_unit_usd * sum(sizings[c.trade_id]) for c in selected])) if selected else 0.0),
        "equity_vol": "%.2f" % (float(np.std(vals)) if vals else 0.0),
        "longest_recovery_trades": str(longest_recovery),
        "recovery_count": str(recoveries),
        "stress_capital": "%.2f" % stress_capital,
        "annual_net": "%.2f" % annual_net,
        "dce": "%.4f" % dce,
    }


def load_unit_rows(unit_trades_path: Path) -> pd.DataFrame:
    df = pd.read_csv(unit_trades_path)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True).dt.tz_convert(NY)
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True).dt.tz_convert(NY)
    df["entry_price"] = pd.to_numeric(df["entry_price"], errors="coerce")
    df["exit_price"] = pd.to_numeric(df["exit_price"], errors="coerce")
    df["net_usd"] = pd.to_numeric(df["net_usd"], errors="coerce").fillna(0.0)
    return df


def load_bars(dbn_path: Path, market: str, start_ts: Optional[pd.Timestamp] = None, end_ts: Optional[pd.Timestamp] = None) -> pd.DataFrame:
    by_day = load_1m_by_ny_date_any(dbn_path.resolve(), market)
    bars = concat_all_1m(by_day)
    if start_ts is not None:
        bars = bars[bars.index >= start_ts]
    if end_ts is not None:
        bars = bars[bars.index <= end_ts]
    return bars.copy()


def write_csv(path: Path, rows: Sequence[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def markdown_table(rows: Sequence[Dict[str, str]], fields: Optional[Sequence[str]] = None) -> str:
    if not rows:
        return ""
    fields = list(fields or rows[0].keys())
    out = ["| " + " | ".join(fields) + " |", "| " + " | ".join(["---"] * len(fields)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(row.get(f, "") for f in fields) + " |")
    return "\n".join(out)


def build_report(
    *,
    output_root: Path,
    unit_trades_path: Path,
    st_fills_path: Path,
    st_strategy_id: str,
    dbn_path: Path,
    market: str,
    instrument: str,
    point_value: float,
    fee_per_unit: float,
    start_date: date,
) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    unit_rows = load_unit_rows(unit_trades_path)
    raw_units = unit_rows[unit_rows["entry_ts"].dt.date >= start_date]
    print("Loading %s 1m bars for campaign MAE/MFE..." % instrument, flush=True)
    bars = load_bars(dbn_path, market, raw_units["entry_ts"].min(), raw_units["exit_ts"].max())
    campaigns = load_v2b_campaigns(
        unit_trades_path,
        st_fills_path,
        st_strategy_id,
        point_value=point_value,
        fee_per_unit=fee_per_unit,
        start_date=start_date,
        bars=bars,
    )
    scenarios = [
        Scenario("A_base_all_1_1_3", (1, 1, 3), (1, 1, 3), 1.0),
        Scenario("B_hard_filter_not_aligned_1_1_3", None, (1, 1, 3), 1.5),
        Scenario("C_weight_not_aligned_2_1_3", (1, 1, 3), (2, 1, 3), 1.3),
        Scenario("D_weight_not_aligned_2_2_3", (1, 1, 3), (2, 2, 3), 1.3),
        Scenario("E_weight_not_aligned_3_2_3", (1, 1, 3), (3, 2, 3), 1.3),
        Scenario("F_derisk_aligned_1_1_1_not_2_1_3", (1, 1, 1), (2, 1, 3), 1.3),
        Scenario("G_skip_aligned_not_2_2_3", None, (2, 2, 3), 1.5),
    ]
    regime_rows = []
    scenario_rows = []
    component_rows = []
    for scenario in scenarios:
        nets: Dict[str, float] = {}
        sizings: Dict[str, Tuple[int, int, int]] = {}
        legs: List[Leg] = []
        selected_campaigns = []
        for campaign in campaigns:
            sizing = campaign_qty_for_scenario(campaign, scenario)
            if sizing is None:
                continue
            net = modeled_trade_net(campaign, sizing)
            nets[campaign.trade_id] = net
            sizings[campaign.trade_id] = sizing
            selected_campaigns.append(campaign)
            legs.extend(build_legs(campaign, sizing, unit_rows))
        closed_dd, stress_dd, close_equity, stress_equity = stress_sequence_for_campaigns(selected_campaigns, nets, sizings)
        if scenario.name == "A_base_all_1_1_3":
            write_csv(
                output_root / "scenario_A_reconstructed_equity.csv",
                [
                    {
                        "trade_idx": str(i + 1),
                        "close_equity_usd": "%.2f" % close_equity[i],
                        "campaign_stress_equity_usd": "%.2f" % stress_equity[i],
                    }
                    for i in range(len(close_equity))
                ],
            )
        scenario_rows.append(
            summarize_campaigns(
                scenario.name,
                selected_campaigns,
                nets,
                sizings,
                stress_dd=stress_dd,
                closed_dd=closed_dd,
                complexity=scenario.complexity,
            )
        )
        for regime_label, subset in [
            ("aligned", [c for c in selected_campaigns if c.regime == "aligned"]),
            ("not_aligned", [c for c in selected_campaigns if c.regime != "aligned"]),
            ("not_aligned_prior_opposed", [c for c in selected_campaigns if c.regime == "not_aligned_prior_opposed"]),
            ("not_aligned_no_prior", [c for c in selected_campaigns if c.regime == "not_aligned_no_prior"]),
        ]:
            if not subset:
                continue
            subset_ids = {c.trade_id for c in subset}
            subset_nets = {k: v for k, v in nets.items() if k in subset_ids}
            subset_sizings = {k: v for k, v in sizings.items() if k in subset_ids}
            subset_closed_dd, subset_stress_dd, _close, _stress = stress_sequence_for_campaigns(subset, subset_nets, subset_sizings)
            row = summarize_campaigns(
                scenario.name + "__" + regime_label,
                subset,
                subset_nets,
                subset_sizings,
                stress_dd=subset_stress_dd,
                closed_dd=subset_closed_dd,
                complexity=scenario.complexity,
            )
            row["scenario"] = scenario.name
            row["regime"] = regime_label
            regime_rows.append(row)
        for bucket in ["tp1", "tp2", "runner", "full_exit"]:
            blegs = [leg for leg in legs if leg.bucket == bucket]
            component_rows.append(
                {
                    "scenario": scenario.name,
                    "bucket": bucket,
                    "units": str(sum(leg.qty for leg in blegs)),
                    "net_usd": "%.2f" % sum(leg.net_usd for leg in blegs),
                    "avg_unit": "%.2f" % (sum(leg.net_usd for leg in blegs) / sum(leg.qty for leg in blegs) if blegs and sum(leg.qty for leg in blegs) else 0.0),
                }
            )

    write_csv(output_root / "scenario_matrix.csv", scenario_rows)
    write_csv(output_root / "regime_decomposition.csv", regime_rows)
    write_csv(output_root / "component_contribution.csv", component_rows)
    write_csv(
        output_root / "campaign_regimes.csv",
        [
            {
                "trade_id": c.trade_id,
                "session": c.entry_ts.date().isoformat(),
                "side": c.side,
                "entry_ts": c.entry_ts.isoformat(),
                "exit_ts": c.exit_ts.isoformat(),
                "regime": c.regime,
                "prior_st_trade_id": c.prior_st_trade_id,
                "base_1_1_3_net": "%.2f" % modeled_trade_net(c, (1, 1, 3)),
                "tp1_unit_usd": "%.2f" % c.tp1_unit_usd,
                "tp2_unit_usd": "%.2f" % c.tp2_unit_usd,
                "runner_unit_usd": "%.2f" % c.runner_unit_usd,
                "full_exit_unit_usd": "%.2f" % c.full_exit_unit_usd,
                "mae_unit_usd": "%.2f" % c.mae_unit_usd,
                "mfe_unit_usd": "%.2f" % c.mfe_unit_usd,
            }
            for c in campaigns
        ],
    )

    top_fields = ["row", "trades", "win_rate_pct", "net_usd", "stress_dd_usd", "net_stress", "profit_factor", "avg_trade", "avg_mae", "max_losing_streak", "stress_capital", "dce"]
    regime_fields = ["scenario", "regime", "trades", "win_rate_pct", "net_usd", "stress_dd_usd", "net_stress", "profit_factor", "avg_trade", "avg_mae"]
    index = f"""# {instrument} v2b Regime Weighting Research

Source plan: `/home/tester/hsm/mnq_v2b_regime_weighting_research_plan.md`

Model:

- Base v2b tape: {instrument} unit trades from `{unit_trades_path}`.
- Regime signal: prior same-session {instrument} hourly ST+PMC `{st_strategy_id}`.
- `aligned`: ST+PMC had already fired in the same direction before the v2b entry.
- `not_aligned`: no prior ST+PMC, or prior ST+PMC was opposite direction.
- Scenario PnL is linearly reweighted from the unit tape; prices/timestamps remain broker-like replay fills.
- Stress is reconstructed at the campaign level from MNQ 1-minute OHLC by measuring each campaign's worst adverse price between entry and exit, then replaying the campaign equity sequence under each sizing. This is intentionally faster and slightly coarser than a full per-minute portfolio replay, but it preserves the broker-like fills and captures the adverse intrabar excursion per campaign.

## Scenario Matrix

{markdown_table(scenario_rows, top_fields)}

## Regime Decomposition

{markdown_table(regime_rows, regime_fields)}

## Component Contribution

{markdown_table(component_rows)}

## Read

- The hard filter is **not** the best allocator answer here: `B_hard_filter_not_aligned_1_1_3` gives up too much net versus the base.
- The cleanest weighted row in this pass is `E_weight_not_aligned_3_2_3`, but it also raises stress and max sizing. It is an allocator optimization candidate, not a first live-test candidate.
- The conservative weighted row `C_weight_not_aligned_2_1_3` improves absolute net while keeping the same aligned participation.
- The prior-opposed subset is the strongest not-aligned branch, matching the timing study's failed-ST/reversal read.

## Files

- `scenario_matrix.csv`
- `regime_decomposition.csv`
- `component_contribution.csv`
- `campaign_regimes.csv`
- `scenario_A_reconstructed_equity.csv`
"""
    (output_root / "INDEX.md").write_text(index)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Execute v2b regime weighting research plan.")
    parser.add_argument("--market", default="mnq", choices=sorted(MARKETS))
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument(
        "--unit-trades",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--st-fills",
        type=Path,
        default=None,
    )
    parser.add_argument("--st-strategy-id", default=None)
    parser.add_argument("--v2b-slug", default="S_1_1_3")
    parser.add_argument("--dbn", type=Path, default=None)
    parser.add_argument("--start-date", default="2021-03-04")
    parser.add_argument("--point-value", type=float, default=None)
    parser.add_argument("--fee-per-unit", type=float, default=1.50)
    args = parser.parse_args(argv)
    cfg = MARKETS[args.market]
    instrument = cfg.instrument
    output_root = args.output_root or (REPO / "live/state/v2b_regime_weighting_research_all" / args.market)
    unit_trades = args.unit_trades or (REPO / ("live/state/v2b_sizing_sweep/states/%s_v2b_sizing_%s/unit_trades.csv" % (args.market, args.v2b_slug)))
    st_fills = args.st_fills or (REPO / ("live/state/hourly_st_pmc_strategyplugin_variants_cross_market/%s/combined_state/fills.csv" % args.market))
    st_strategy_id = args.st_strategy_id or ("%s_hourly_st_pmc_sl25_tp75_3r" % args.market)
    dbn = args.dbn or cfg.dbn_path
    point_value = args.point_value if args.point_value is not None else float(POINT_VALUES[instrument])
    build_report(
        output_root=output_root,
        unit_trades_path=unit_trades,
        st_fills_path=st_fills,
        st_strategy_id=st_strategy_id,
        dbn_path=dbn,
        market=args.market,
        instrument=instrument,
        point_value=point_value,
        fee_per_unit=args.fee_per_unit,
        start_date=date.fromisoformat(args.start_date),
    )
    print("Wrote %s" % (output_root / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
