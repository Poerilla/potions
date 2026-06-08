#!/usr/bin/env python3
"""Simulate MNQ yearly-ORB scaleout3 sizing from $20k under half-profit-linked scaling.

Three regimes (each calendar year's realized sleeve P&L feeds a sizing budget;
bundles = floor(min(equity, sizing_budget) / (R * buffer))).

- Aggressive: 50% of year P&L to sizing budget plus 50% of long-run mean 1-bundle year
  (expected-profit kicker every year); buffer 1.0 * R; on a loss year also add 0.5 × mean
  for the loss-year floor (optimistic).
- Moderate: 50% of year P&L to sizing budget; buffer 1.1 * R.
- Conservative: 50% of positive P&L only; buffer 1.33 * R; losses reduce sizing
  budget by 25% of the loss.

R = 3 x |single-bundle full-sample open-heat stress DD| (same as yearly_orb_equity_scaling).

Outputs CSV + markdown under mnq/case_studies/profit_half_scaling_20k/.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from yearly_orb_equity_scaling import Market, base_stats, normalize_trades


ROOT = Path(__file__).resolve().parents[1]
MNQ = Market(
    "MNQ",
    ROOT / "mnq" / "mnq_yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close.csv",
    2.0,
)


@dataclass(frozen=True)
class Regime:
    name: str
    profit_to_sizing: float
    buffer_mult: float
    loss_sizing_frac: float
    use_expected_on_loss: bool
    expected_loss_weight: float
    expected_boost_frac: float  # add frac * mean_1b to sizing each year (aggressive)


def simulate_year_fixed_bundles(
    trades: pd.DataFrame,
    units: pd.DataFrame,
    year: int,
    bundles: int,
    capital_start: float,
) -> tuple[float, float, float, float]:
    """Return (end_capital, year_net, year_closed_dd, year_stress_dd)."""
    bundle_by_trade = {
        int(tid): bundles for tid in trades.loc[trades["Entry_Date"].dt.year.eq(year), "trade_id"]
    }
    capital = capital_start
    closed_high = capital
    stress_dd = 0.0
    closed_dd = 0.0
    last_date = max(pd.to_datetime(units["date"]).max(), trades["Final_Exit_Date"].max())
    year_days = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    year_days = year_days[year_days <= last_date]

    year_closed_high = capital
    year_stress_dd = 0.0
    year_closed_dd = 0.0

    for day in year_days:
        exits = units[pd.to_datetime(units["date"]).dt.date.eq(day.date())].copy()
        day_pnl = 0.0
        for _, unit in exits.iterrows():
            day_pnl += float(unit["usd"]) * bundle_by_trade.get(int(unit["trade_id"]), 0)
        capital += day_pnl
        closed_high = max(closed_high, capital)
        year_closed_high = max(year_closed_high, capital)
        closed_dd = min(closed_dd, capital - closed_high)
        year_closed_dd = min(year_closed_dd, capital - year_closed_high)
        active = trades[(trades["Entry_Date"] <= day) & (trades["Final_Exit_Date"] >= day)]
        heat = sum(
            float(row["mae_usd"]) * bundle_by_trade.get(int(row["trade_id"]), 0)
            for _, row in active.iterrows()
        )
        stress_equity = capital - heat
        stress_dd = min(stress_dd, stress_equity - closed_high)
        year_stress_dd = min(year_stress_dd, stress_equity - year_closed_high)

    year_net = capital - capital_start
    return capital, year_net, year_closed_dd, year_stress_dd


def one_bundle_year_nets(trades: pd.DataFrame, units: pd.DataFrame) -> dict[int, float]:
    """Isolated 1-bundle calendar-year net (PnL linear in starting equity for totals)."""
    out: dict[int, float] = {}
    first_year = int(trades["Entry_Date"].dt.year.min())
    last_date = max(pd.to_datetime(units["date"]).max(), trades["Final_Exit_Date"].max())
    last_year = int(last_date.year)
    for year in range(first_year, last_year + 1):
        _, yn, _, _ = simulate_year_fixed_bundles(trades, units, year, 1, 0.0)
        out[year] = yn
    return out


def rebuild_rows_with_sizing_start(
    trades: pd.DataFrame,
    units: pd.DataFrame,
    required_r: float,
    years: list[int],
    start_equity: float,
    regime: Regime,
    mean_1b: float,
    max_bundles: int = 250,
) -> pd.DataFrame:
    equity = float(start_equity)
    sizing = float(start_equity)
    rows = []
    peak_b = 0
    for year in years:
        sizing_start = sizing
        eff_r = required_r * regime.buffer_mult
        cap_room = min(equity, sizing)
        bundles = int(cap_room // eff_r) if eff_r > 0 else 0
        bundles = max(0, min(max_bundles, bundles))
        if bundles < 1 and cap_room >= eff_r:
            bundles = 1
        elif bundles < 1:
            bundles = 0
        peak_b = max(peak_b, bundles)
        eq_start = equity
        if bundles == 0:
            yn, ycd, ysd = 0.0, 0.0, 0.0
        else:
            equity, yn, ycd, ysd = simulate_year_fixed_bundles(trades, units, year, bundles, equity)
        p = yn
        boost = regime.expected_boost_frac * mean_1b
        if regime.use_expected_on_loss and p < 0:
            sizing = (
                sizing
                + regime.profit_to_sizing * p
                + regime.expected_loss_weight * mean_1b
                + boost
            )
        else:
            sizing = (
                sizing
                + regime.profit_to_sizing * max(p, 0.0)
                + regime.loss_sizing_frac * min(p, 0.0)
                + boost
            )
        sizing = min(max(sizing, 0.0), equity)
        rows.append(
            {
                "year": year,
                "start_equity": round(eq_start, 2),
                "sizing_budget_start": round(sizing_start, 2),
                "bundles": bundles,
                "contracts": bundles * 3,
                "eff_r_per_bundle": round(eff_r, 2),
                "year_net": round(yn, 2),
                "year_closed_dd": round(ycd, 2),
                "year_stress_dd": round(ysd, 2),
                "end_equity": round(equity, 2),
                "sizing_budget_end": round(sizing, 2),
            }
        )
    out_df = pd.DataFrame(rows)
    out_df.attrs["peak_bundles"] = peak_b
    return out_df


REGIMES = {
    "aggressive": Regime(
        name="aggressive",
        profit_to_sizing=0.5,
        buffer_mult=1.0,
        loss_sizing_frac=0.0,
        use_expected_on_loss=True,
        expected_loss_weight=0.5,
        expected_boost_frac=0.5,
    ),
    "moderate": Regime(
        name="moderate",
        profit_to_sizing=0.5,
        buffer_mult=1.1,
        loss_sizing_frac=0.0,
        use_expected_on_loss=False,
        expected_loss_weight=0.0,
        expected_boost_frac=0.0,
    ),
    "conservative": Regime(
        name="conservative",
        profit_to_sizing=0.5,
        buffer_mult=1.33,
        loss_sizing_frac=-0.25,
        use_expected_on_loss=False,
        expected_loss_weight=0.0,
        expected_boost_frac=0.0,
    ),
}


def simulate_synthetic_forward(
    regime: Regime,
    required_r: float,
    start_equity: float,
    mean_1b: float,
    std_1b: float,
    years: list[int],
    max_bundles: int = 250,
) -> pd.DataFrame:
    equity = float(start_equity)
    sizing = float(start_equity)
    rows = []
    note = f"synthetic year P&L = {mean_1b:.0f} * bundles (hist σ 1-bundle ≈ {std_1b:.0f})"
    for year in years:
        sizing_start = sizing
        eff_r = required_r * regime.buffer_mult
        cap_room = min(equity, sizing)
        bundles = int(cap_room // eff_r) if eff_r > 0 else 0
        bundles = max(0, min(max_bundles, bundles))
        if bundles < 1 and cap_room >= eff_r:
            bundles = 1
        elif bundles < 1:
            bundles = 0
        eq_start = equity
        yn = mean_1b * bundles if bundles else 0.0
        equity += yn
        p = yn
        boost = regime.expected_boost_frac * mean_1b
        if regime.use_expected_on_loss and p < 0:
            sizing = (
                sizing
                + regime.profit_to_sizing * p
                + regime.expected_loss_weight * mean_1b
                + boost
            )
        else:
            sizing = (
                sizing
                + regime.profit_to_sizing * max(p, 0.0)
                + regime.loss_sizing_frac * min(p, 0.0)
                + boost
            )
        sizing = min(max(sizing, 0.0), equity)
        rows.append(
            {
                "year": year,
                "start_equity": round(eq_start, 2),
                "sizing_budget_start": round(sizing_start, 2),
                "bundles": bundles,
                "contracts": bundles * 3,
                "eff_r_per_bundle": round(eff_r, 2),
                "year_net": round(yn, 2),
                "year_closed_dd": "",
                "year_stress_dd": "",
                "end_equity": round(equity, 2),
                "sizing_budget_end": round(sizing, 2),
                "projection_note": note,
            }
        )
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / "mnq" / "case_studies" / "profit_half_scaling_20k",
    )
    ap.add_argument("--start", type=float, default=20_000.0)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    trades, units = normalize_trades(MNQ)
    base = base_stats(trades, units)
    required_r = abs(base["stress_dd_usd"]) * 3.0

    nets_1b = one_bundle_year_nets(trades, units)
    mean_1b = float(sum(nets_1b.values()) / len(nets_1b))
    series = pd.Series(list(nets_1b.values()))
    std_1b = float(series.std(ddof=1)) if len(series) > 1 else 0.0

    first_year = int(trades["Entry_Date"].dt.year.min())
    last_date = max(pd.to_datetime(units["date"]).max(), trades["Final_Exit_Date"].max())
    hist_years = list(range(first_year, int(last_date.year) + 1))

    sections: list[str] = [
        "# MNQ yearly ORB — $20k half-profit-linked scaling",
        "",
        "Variant: yearly ORB scaleout3, inside-range swing stop, range-close exit (same CSV as equity scaling).",
        f"**R** = 3 × |full-sample open-heat stress DD| one bundle = **${required_r:,.0f}**.",
        "",
        "## Sizing rule",
        "",
        "- At each **1 Jan**: `bundles = floor(min(equity, sizing_budget) / (R × buffer))`, cap 250 bundles.",
        "- **Equity** compounds full realized P&L at that year’s bundle count.",
        "- **Sizing budget** is updated after each year from the regime’s profit rule (capped by equity).",
        "",
        "### Regimes",
        "",
        "| Track | Profit → sizing budget | Buffer × R | Loss handling |",
        "|---|---|---|---|",
        "| Aggressive | 50% of year net **+** 50% of mean 1-bundle year every year; extra 0.5× mean on loss years | 1.00 | sizes off profit *and* expected |",
        "| Moderate | 50% of year net | 1.10 | losses do not add to sizing budget |",
        "| Conservative | 50% of year net on gains; losses shrink sizing budget by 25% of loss | 1.33 | asymmetric |",
        "",
        f"**Mean 1-bundle calendar-year net** ({first_year}–{int(last_date.year)}): **${mean_1b:,.0f}** (sample σ ≈ **${std_1b:,.0f}**).",
        "",
        f"## A) Historical tape: **${args.start:,.0f}** start **{first_year}**",
        "",
    ]

    for key in ("aggressive", "moderate", "conservative"):
        regime = REGIMES[key]
        df = rebuild_rows_with_sizing_start(
            trades, units, required_r, hist_years, args.start, regime, mean_1b
        )
        df.to_csv(args.out / f"historical_{first_year}_{key}.csv", index=False)
        sections.append(f"### {key.title()}")
        sections.append("")
        sections.append(df.to_markdown(index=False))
        sections.append("")

    sections.extend(
        [
            "## B) Synthetic forward: **$20,000** on **2026-01-01** (5 years)",
            "",
            "No post-2025 trades in the CSV. Each year uses **deterministic** P&L = mean historical",
            f"1-bundle year net (${mean_1b:,.0f}) × bundle count. Stress/closed DD not extrapolated.",
            "",
        ]
    )
    fwd_years = list(range(2026, 2031))
    for key in ("aggressive", "moderate", "conservative"):
        regime = REGIMES[key]
        df = simulate_synthetic_forward(regime, required_r, args.start, mean_1b, std_1b, fwd_years)
        df.to_csv(args.out / f"forward_2026_5y_{key}.csv", index=False)
        sections.append(f"### {key.title()} (2026–2030)")
        sections.append("")
        show = df.drop(columns=["projection_note"], errors="ignore")
        sections.append(show.to_markdown(index=False))
        sections.append("")
        sections.append(f"_{df['projection_note'].iloc[0]}_")
        sections.append("")

    pd.DataFrame(
        [
            {
                "stress_dd_1bundle": base["stress_dd_usd"],
                "R_3x": required_r,
                "mean_1bundle_year_net": mean_1b,
                "std_1bundle_year_net": std_1b,
                "nets_1bundle_by_year": repr(nets_1b),
            }
        ]
    ).to_csv(args.out / "meta.csv", index=False)

    (args.out / "README.md").write_text("\n".join(sections), encoding="utf-8")
    print(f"Wrote {args.out / 'README.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
