from __future__ import annotations

import argparse
import math
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .replay_audit import POINT_VALUES
from .v2b_strategy_cross_market_replay import MARKETS, _rth_bars, load_1m_by_ny_date_any


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
FEE_PER_UNIT = 1.50
PRIOR_OPPOSED_MARKETS = ["nq", "mnq", "es", "ym", "mym"]


@dataclass(frozen=True)
class Paths:
    market: str
    instrument: str
    point_value: float
    output_root: Path
    state_root: Path
    fills: Path
    orders: Path
    unit_trades: Path
    equity_curve: Path
    daily: Path


def money(value: float) -> str:
    return "$%s%.2f" % ("-" if value < 0 else "", abs(value))


def max_drawdown(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    peak = values.cummax()
    return float((values - peak).min())


def profit_factor(pnls: pd.Series) -> float:
    gains = float(pnls[pnls > 0].sum())
    losses = abs(float(pnls[pnls < 0].sum()))
    if losses == 0:
        return math.inf if gains > 0 else 0.0
    return gains / losses


def load_campaigns(fills_path: Path, point_value: float) -> pd.DataFrame:
    fills = pd.read_csv(fills_path)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1).astype(int)

    rows = []
    for trade_id, group in fills.sort_values("ts").groupby("trade_id"):
        entries = group[group["reason"].astype(str) == "entry"]
        exits = group[group["reason"].astype(str) != "entry"]
        if entries.empty or exits.empty:
            continue
        entry = entries.iloc[0]
        side = "long" if str(entry["side"]).lower() == "buy" else "short"
        entry_px = float(entry["price"])
        net = 0.0
        exit_reasons = []
        for _idx, exit_row in exits.iterrows():
            qty = int(exit_row["quantity"])
            px = float(exit_row["price"])
            pts = px - entry_px if side == "long" else entry_px - px
            net += pts * point_value * qty - FEE_PER_UNIT * qty
            exit_reasons.append(str(exit_row["reason"]))
        rows.append(
            {
                "trade_id": str(trade_id),
                "session": pd.Timestamp(entry["ts"]).date().isoformat(),
                "year": pd.Timestamp(entry["ts"]).year,
                "side": side,
                "entry_ts": pd.Timestamp(entry["ts"]),
                "exit_ts": pd.Timestamp(exits["ts"].max()),
                "entry_price": entry_px,
                "entry_qty": int(entry["quantity"]),
                "net_usd": net,
                "exit_reasons": ",".join(sorted(set(exit_reasons))),
                "hit_tp1": "tp1" in exit_reasons,
                "hit_tp2": "tp2" in exit_reasons,
                "runner_stop": "runner_stop" in exit_reasons,
                "wide_stop": "wide_stop" in exit_reasons,
                "eod_close": "eod_close" in exit_reasons,
            }
        )
    return pd.DataFrame(rows).sort_values("entry_ts").reset_index(drop=True)


def add_daily_regimes(campaigns: pd.DataFrame, daily_path: Path) -> pd.DataFrame:
    daily = pd.read_csv(daily_path, parse_dates=["date"]).sort_values("date")
    for col in ["open", "high", "low", "close"]:
        daily[col] = pd.to_numeric(daily[col], errors="coerce")
    prev_close = daily["close"].shift(1)
    tr = pd.concat(
        [
            daily["high"] - daily["low"],
            (daily["high"] - prev_close).abs(),
            (daily["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    daily["atr14"] = tr.rolling(14).mean().shift(1)
    daily["gap_pts"] = (daily["open"] - prev_close).abs()
    daily["session"] = daily["date"].dt.date.astype(str)
    out = campaigns.merge(daily[["session", "atr14", "gap_pts"]], on="session", how="left")
    return out


def add_intraday_regimes(campaigns: pd.DataFrame, market: str, instrument: str, point_value: float) -> pd.DataFrame:
    cfg = MARKETS[market]
    print("Loading %s 1m bars for robustness audit..." % instrument, flush=True)
    bars_by_day = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), market)
    rows = []
    for row in campaigns.itertuples(index=False):
        session = date.fromisoformat(str(row.session))
        rth = _rth_bars(bars_by_day.get(session), session)
        or_width = np.nan
        mae_usd = np.nan
        mfe_usd = np.nan
        if not rth.empty:
            opening = rth[
                (rth.index.time >= pd.Timestamp("09:30").time())
                & (rth.index.time < pd.Timestamp("09:45").time())
            ]
            if not opening.empty:
                or_width = float(opening["high"].max() - opening["low"].min())
            window = rth[(rth.index >= row.entry_ts) & (rth.index <= row.exit_ts)]
            if not window.empty:
                entry = float(row.entry_price)
                qty = int(row.entry_qty)
                if row.side == "long":
                    adverse_pts = min(0.0, float(window["low"].min()) - entry)
                    favorable_pts = max(0.0, float(window["high"].max()) - entry)
                else:
                    adverse_pts = min(0.0, entry - float(window["high"].max()))
                    favorable_pts = max(0.0, entry - float(window["low"].min()))
                mae_usd = adverse_pts * point_value * qty
                mfe_usd = favorable_pts * point_value * qty
        rows.append({"trade_id": row.trade_id, "or_width_pts": or_width, "campaign_mae_usd": mae_usd, "campaign_mfe_usd": mfe_usd})
    return campaigns.merge(pd.DataFrame(rows), on="trade_id", how="left")


def add_quartiles(df: pd.DataFrame, col: str, out_col: str) -> None:
    valid = pd.to_numeric(df[col], errors="coerce")
    try:
        df[out_col] = pd.qcut(valid, 4, labels=["Q1 low", "Q2", "Q3", "Q4 high"], duplicates="drop")
    except ValueError:
        df[out_col] = ""


def summarize_group(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    rows = []
    for key, g in df.groupby(group_col, dropna=False, observed=False):
        pnl = g["net_usd"]
        rows.append(
            {
                group_col: str(key),
                "trades": len(g),
                "net_usd": pnl.sum(),
                "win_rate_pct": 100.0 * float((pnl > 0).mean()) if len(g) else 0.0,
                "profit_factor": profit_factor(pnl),
                "avg_trade": pnl.mean() if len(g) else 0.0,
                "closed_dd_usd": max_drawdown(pnl.cumsum()),
                "avg_mae_usd": g["campaign_mae_usd"].mean(),
                "worst_mae_usd": g["campaign_mae_usd"].min(),
            }
        )
    out = pd.DataFrame(rows)
    if not out.empty:
        out["net_over_closed_dd"] = out.apply(
            lambda r: r["net_usd"] / abs(r["closed_dd_usd"]) if r["closed_dd_usd"] else 0.0, axis=1
        )
    return out


def rolling_metrics(campaigns: pd.DataFrame, window: int = 50) -> pd.DataFrame:
    rows = []
    for i in range(window, len(campaigns) + 1):
        g = campaigns.iloc[i - window : i]
        pnl = g["net_usd"]
        dd = max_drawdown(pnl.cumsum())
        rows.append(
            {
                "end_entry_ts": g.iloc[-1]["entry_ts"],
                "end_trade_id": g.iloc[-1]["trade_id"],
                "window": window,
                "trades": len(g),
                "net_usd": pnl.sum(),
                "win_rate_pct": 100.0 * float((pnl > 0).mean()),
                "profit_factor": profit_factor(pnl),
                "closed_dd_usd": dd,
                "net_over_closed_dd": pnl.sum() / abs(dd) if dd else 0.0,
            }
        )
    return pd.DataFrame(rows)


def stop_slippage_audit(fills_path: Path, orders_path: Path, point_value: float, tick_size: float = 0.25) -> pd.DataFrame:
    fills = pd.read_csv(fills_path)
    orders = pd.read_csv(orders_path)
    merged = fills.merge(
        orders[["broker_order_id", "trade_id", "side", "order_type", "quantity", "stop_price", "bracket_role"]],
        on="broker_order_id",
        how="left",
        suffixes=("_fill", "_order"),
    )
    merged = merged[merged["order_type"].astype(str) == "stop"].copy()
    if merged.empty:
        return merged
    merged["price"] = pd.to_numeric(merged["price"], errors="coerce")
    merged["stop_price"] = pd.to_numeric(merged["stop_price"], errors="coerce")
    merged["quantity_fill"] = pd.to_numeric(merged["quantity_fill"], errors="coerce").fillna(0)
    sell = merged["side_fill"].astype(str).str.lower().eq("sell")
    buy = merged["side_fill"].astype(str).str.lower().eq("buy")
    merged["adverse_slip_pts"] = 0.0
    merged.loc[sell, "adverse_slip_pts"] = (merged.loc[sell, "stop_price"] - merged.loc[sell, "price"]).clip(lower=0)
    merged.loc[buy, "adverse_slip_pts"] = (merged.loc[buy, "price"] - merged.loc[buy, "stop_price"]).clip(lower=0)
    merged["gap_beyond_1tick_pts"] = (merged["adverse_slip_pts"] - float(tick_size)).clip(lower=0)
    merged["adverse_slip_usd"] = merged["adverse_slip_pts"] * point_value * merged["quantity_fill"]
    merged["gap_beyond_1tick_usd"] = merged["gap_beyond_1tick_pts"] * point_value * merged["quantity_fill"]
    return merged


def recovery_stats(equity_path: Path) -> Dict[str, float]:
    eq = pd.read_csv(equity_path)
    eq["ts"] = pd.to_datetime(eq["ts"], utc=True).dt.tz_convert(NY)
    eq["close_equity_usd"] = pd.to_numeric(eq["close_equity_usd"], errors="coerce").fillna(0.0)
    peak = -math.inf
    peak_ts: Optional[pd.Timestamp] = None
    current_start: Optional[pd.Timestamp] = None
    max_recovery_bars = 0
    max_recovery_days = 0
    unresolved_days = 0
    bars_in_dd = 0
    for row in eq.itertuples(index=False):
        value = float(row.close_equity_usd)
        ts = pd.Timestamp(row.ts)
        if value >= peak:
            if current_start is not None:
                max_recovery_bars = max(max_recovery_bars, bars_in_dd)
                max_recovery_days = max(max_recovery_days, (ts.date() - current_start.date()).days)
            peak = value
            peak_ts = ts
            current_start = None
            bars_in_dd = 0
        else:
            if current_start is None:
                current_start = peak_ts
                bars_in_dd = 0
            bars_in_dd += 1
    if current_start is not None and not eq.empty:
        unresolved_days = (pd.Timestamp(eq.iloc[-1]["ts"]).date() - current_start.date()).days
        max_recovery_bars = max(max_recovery_bars, bars_in_dd)
        max_recovery_days = max(max_recovery_days, unresolved_days)
    return {
        "max_recovery_bars": float(max_recovery_bars),
        "max_recovery_calendar_days": float(max_recovery_days),
        "unresolved_recovery_calendar_days": float(unresolved_days),
        "bars_in_drawdown_pct": 100.0 * float((eq["close_equity_usd"] < eq["close_equity_usd"].cummax()).mean()) if not eq.empty else 0.0,
    }


def write_plot(output_root: Path, campaigns: pd.DataFrame, rolling: pd.DataFrame, instrument: str) -> None:
    chart_dir = output_root / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)

    fig, (ax, dd_ax) = plt.subplots(2, 1, figsize=(14, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    x = campaigns["entry_ts"]
    equity = campaigns["net_usd"].cumsum()
    ax.plot(x, equity, color="#0f766e", linewidth=1.6, label="Campaign close equity")
    ax.set_title("%s prior-opposed v2b campaign equity" % instrument)
    ax.grid(True, alpha=0.3)
    ax.legend()
    dd = equity - equity.cummax()
    dd_ax.fill_between(x, dd, 0, color="#dc2626", alpha=0.35)
    dd_ax.set_ylabel("DD")
    dd_ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.savefig(chart_dir / "campaign_equity_dd.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    if not rolling.empty:
        fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
        axes[0].plot(rolling["end_entry_ts"], rolling["profit_factor"], color="#2563eb")
        axes[0].axhline(1.0, color="#777", linestyle="--", linewidth=0.8)
        axes[0].set_title("Rolling 50-campaign PF")
        axes[1].plot(rolling["end_entry_ts"], rolling["win_rate_pct"], color="#16a34a")
        axes[1].set_title("Rolling 50-campaign win rate")
        axes[2].plot(rolling["end_entry_ts"], rolling["net_over_closed_dd"], color="#9333ea")
        axes[2].set_title("Rolling 50-campaign Net / closed-DD")
        for ax in axes:
            ax.grid(True, alpha=0.3)
        fig.autofmt_xdate()
        fig.savefig(chart_dir / "rolling_50_metrics.png", dpi=140, bbox_inches="tight")
        plt.close(fig)


def write_report(
    output_root: Path,
    instrument: str,
    campaigns: pd.DataFrame,
    yearly: pd.DataFrame,
    quartiles: Dict[str, pd.DataFrame],
    rolling: pd.DataFrame,
    unit_contrib: pd.DataFrame,
    stop_audit: pd.DataFrame,
    recovery: Dict[str, float],
) -> None:
    total_net = float(campaigns["net_usd"].sum())
    top10 = campaigns.nlargest(10, "net_usd")
    worst10 = campaigns.nsmallest(10, "net_usd")
    top10_net = float(top10["net_usd"].sum())
    worst10_net = float(worst10["net_usd"].sum())
    rolling_bad = rolling[rolling["profit_factor"] < 1.0] if not rolling.empty else pd.DataFrame()
    stop_gap = float(stop_audit["gap_beyond_1tick_usd"].sum()) if not stop_audit.empty else 0.0
    stop_slip = float(stop_audit["adverse_slip_usd"].sum()) if not stop_audit.empty else 0.0
    max_loss_streak = max_losing_streak(campaigns["net_usd"])
    max_win_streak = max_losing_streak(-campaigns["net_usd"])

    lines = [
        "# %s Prior-Opposed v2b Robustness Audit" % instrument,
        "",
        "Purpose: aggressively poke holes in the confirmed broker-like %s prior-opposed ST+PMC -> v2b `S_1_1_3` result." % instrument,
        "",
        "## Headline",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Campaigns | {len(campaigns)} |",
        f"| Net | {money(total_net)} |",
        f"| Campaign closed DD | {money(max_drawdown(campaigns['net_usd'].cumsum()))} |",
        f"| Win rate | {100.0 * float((campaigns['net_usd'] > 0).mean()):.2f}% |",
        f"| Profit factor | {profit_factor(campaigns['net_usd']):.3f} |",
        f"| Avg trade | {money(float(campaigns['net_usd'].mean()))} |",
        f"| Median trade | {money(float(campaigns['net_usd'].median()))} |",
        f"| Skew | {float(campaigns['net_usd'].skew()):.3f} |",
        f"| Max losing streak | {max_loss_streak} |",
        f"| Max winning streak | {max_win_streak} |",
        "",
        "## Main Ways This Could Be Fragile",
        "",
    ]
    concerns = []
    if top10_net / total_net > 0.45:
        concerns.append("Top-10 winners contribute more than 45% of total net; check monster-runner dependency.")
    if not rolling_bad.empty:
        concerns.append(f"{len(rolling_bad)} rolling 50-campaign windows have PF < 1.0.")
    if yearly["net_usd"].min() < 0:
        concerns.append("At least one calendar year is net-negative.")
    if not yearly.empty and yearly["net_over_closed_dd"].min() < 1.0:
        weak = yearly.sort_values("net_over_closed_dd").iloc[0]
        concerns.append(
            "Weakest year is %s: %s net, %.2f PF, %.2f Net/closed-DD."
            % (str(weak["year"]), money(float(weak["net_usd"])), float(weak["profit_factor"]), float(weak["net_over_closed_dd"]))
        )
    if stop_gap > total_net * 0.10:
        concerns.append("Gap-through stop damage is more than 10% of net.")
    if max_loss_streak >= 5:
        concerns.append("Loss streak reaches 5+ campaigns; sizing must tolerate clustering.")
    gap_table = quartiles.get("Opening gap quartile")
    if gap_table is not None and not gap_table.empty:
        worst_gap = gap_table.sort_values("net_over_closed_dd").iloc[0]
        if float(worst_gap["net_over_closed_dd"]) < 4.0:
            concerns.append(
                "Opening-gap fragility: %s has %.2f Net/closed-DD and %.2f PF."
                % (str(worst_gap["gap_quartile"]), float(worst_gap["net_over_closed_dd"]), float(worst_gap["profit_factor"]))
            )
    or_table = quartiles.get("Opening range width quartile")
    if or_table is not None and not or_table.empty:
        worst_or = or_table.sort_values("net_over_closed_dd").iloc[0]
        if float(worst_or["net_over_closed_dd"]) < 4.0:
            concerns.append(
                "Opening-range-width fragility: %s has %.2f Net/closed-DD and %.2f PF."
                % (str(worst_or["or_width_quartile"]), float(worst_or["net_over_closed_dd"]), float(worst_or["profit_factor"]))
            )
    if not concerns:
        concerns.append(
            "No single audit bucket broke the model, but the sample is still only %d campaigns and should be paper-parity tested."
            % len(campaigns)
        )
    for item in concerns:
        lines.append(f"- {item}")

    lines += [
        "",
        "## Concentration",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Top 10 winners net | {money(top10_net)} |",
        f"| Top 10 winners share of total net | {100.0 * top10_net / total_net:.2f}% |",
        f"| Worst 10 losers net | {money(worst10_net)} |",
        f"| Worst 10 losers share of total net | {100.0 * abs(worst10_net) / total_net:.2f}% |",
        f"| Positive campaign share | {100.0 * float((campaigns['net_usd'] > 0).mean()):.2f}% |",
        "",
        "Top winner and loser tables are in `top_10_winners.csv` and `worst_10_losers.csv`.",
        "",
        "## Execution Fragility",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Stop adverse fill cost vs stop price | {money(stop_slip)} |",
        f"| Gap-through cost beyond the baseline 1 tick | {money(stop_gap)} |",
        f"| Filled stop count | {len(stop_audit)} |",
        "",
        "Stop slippage includes the normal 1-tick adverse stop fill. Gap-through isolates the amount beyond that baseline.",
        "",
        "## Recovery / Exposure",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Max recovery bars | {recovery['max_recovery_bars']:.0f} |",
        f"| Max recovery calendar days | {recovery['max_recovery_calendar_days']:.0f} |",
        f"| Unresolved recovery days at end | {recovery['unresolved_recovery_calendar_days']:.0f} |",
        f"| Bars in close-equity drawdown | {recovery['bars_in_drawdown_pct']:.2f}% |",
        "",
        "## Yearly Stability",
        "",
        yearly.to_markdown(index=False, floatfmt=".2f"),
        "",
        "## Rolling Stability",
        "",
        f"- Rolling windows: {len(rolling)} using 50 campaigns.",
        f"- Worst rolling PF: {rolling['profit_factor'].min():.3f}" if not rolling.empty else "- No rolling windows.",
        f"- Worst rolling Net/closed-DD: {rolling['net_over_closed_dd'].min():.2f}" if not rolling.empty else "",
        f"- Rolling PF < 1.0 count: {len(rolling_bad)}" if not rolling.empty else "",
        "",
        "Charts: [`charts/campaign_equity_dd.png`](charts/campaign_equity_dd.png), [`charts/rolling_50_metrics.png`](charts/rolling_50_metrics.png).",
        "",
        "## Runner / Exit Dependency",
        "",
        unit_contrib.to_markdown(index=False, floatfmt=".2f"),
        "",
        "## Cross-Regime Quartiles",
        "",
    ]
    for name, table in quartiles.items():
        lines += [f"### {name}", "", table.to_markdown(index=False, floatfmt=".2f"), ""]

    lines += [
        "## Known Gaps",
        "",
        "- CPI/FOMC exclusion is not included yet because no local event calendar was found in the workspace. Add a dated event-calendar CSV and rerun this audit to quantify those exclusions.",
        "- Replay/live parity still needs an online dry-run harness: restart mid-session, replay from persisted state, compare expected order book to broker-paper order book, and verify no duplicate re-arming.",
        "- This audit estimates per-campaign intrabar heat from 1m bars; the headline replay `intrabar_stress_dd` remains the authoritative portfolio-level stress number.",
        "",
        "## Files",
        "",
        "- `campaigns_robustness.csv`",
        "- `yearly_breakdown.csv`",
        "- `rolling_50.csv`",
        "- `exit_reason_contribution.csv`",
        "- `stop_slippage_audit.csv`",
        "- `top_10_winners.csv`",
        "- `worst_10_losers.csv`",
    ]
    (output_root / "ROBUSTNESS_AUDIT.md").write_text("\n".join([line for line in lines if line is not None]))


def max_losing_streak(pnls: pd.Series) -> int:
    best = 0
    current = 0
    for value in pnls:
        if value < 0:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def run(paths: Paths, force: bool) -> None:
    if force and paths.output_root.exists():
        shutil.rmtree(paths.output_root)
    paths.output_root.mkdir(parents=True, exist_ok=True)

    campaigns = load_campaigns(paths.fills, paths.point_value)
    campaigns = add_daily_regimes(campaigns, paths.daily)
    campaigns = add_intraday_regimes(campaigns, paths.market, paths.instrument, paths.point_value)
    add_quartiles(campaigns, "atr14", "atr14_quartile")
    add_quartiles(campaigns, "gap_pts", "gap_quartile")
    add_quartiles(campaigns, "or_width_pts", "or_width_quartile")

    yearly = summarize_group(campaigns, "year")
    rolling = rolling_metrics(campaigns, 50)
    unit_trades = pd.read_csv(paths.unit_trades)
    unit_trades["net_usd"] = pd.to_numeric(unit_trades["net_usd"], errors="coerce").fillna(0.0)
    unit_contrib = (
        unit_trades.groupby("exit_reason", dropna=False)["net_usd"]
        .agg(units="count", net_usd="sum", avg_unit="mean")
        .reset_index()
        .sort_values("net_usd", ascending=False)
    )
    stop_audit = stop_slippage_audit(
        paths.fills,
        paths.orders,
        paths.point_value,
        DEFAULT_TICK_SIZE.get(paths.instrument.upper(), 0.25),
    )
    recovery = recovery_stats(paths.equity_curve)
    quartiles = {
        "ATR14 quartile": summarize_group(campaigns, "atr14_quartile"),
        "Opening gap quartile": summarize_group(campaigns, "gap_quartile"),
        "Opening range width quartile": summarize_group(campaigns, "or_width_quartile"),
    }

    campaigns.to_csv(paths.output_root / "campaigns_robustness.csv", index=False)
    yearly.to_csv(paths.output_root / "yearly_breakdown.csv", index=False)
    rolling.to_csv(paths.output_root / "rolling_50.csv", index=False)
    unit_contrib.to_csv(paths.output_root / "exit_reason_contribution.csv", index=False)
    stop_audit.to_csv(paths.output_root / "stop_slippage_audit.csv", index=False)
    campaigns.nlargest(10, "net_usd").to_csv(paths.output_root / "top_10_winners.csv", index=False)
    campaigns.nsmallest(10, "net_usd").to_csv(paths.output_root / "worst_10_losers.csv", index=False)
    for name, table in quartiles.items():
        table.to_csv(paths.output_root / ("%s.csv" % name.lower().replace(" ", "_")), index=False)

    write_plot(paths.output_root, campaigns, rolling, paths.instrument)
    write_report(paths.output_root, paths.instrument, campaigns, yearly, quartiles, rolling, unit_contrib, stop_audit, recovery)
    print("Wrote %s" % (paths.output_root / "ROBUSTNESS_AUDIT.md"))


def _default_state_root(market: str) -> Path:
    return REPO / f"live/state/{market}_v2b_prior_opposed_stpmc_broker_like/states/{market}_v2b_prior_opposed_stpmc_only_S_1_1_3"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Poke holes in a prior-opposed ST+PMC v2b replay.")
    parser.add_argument("--market", choices=PRIOR_OPPOSED_MARKETS, default="nq")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=None,
    )
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    market = args.market.lower()
    cfg = MARKETS[market]
    state = args.state_root or _default_state_root(market)
    output_root = args.output_root or (REPO / f"live/state/{market}_v2b_prior_opposed_stpmc_broker_like/robustness_audit")
    paths = Paths(
        market=market,
        instrument=cfg.instrument,
        point_value=POINT_VALUES[cfg.instrument],
        output_root=output_root,
        state_root=state,
        fills=state / "fills.csv",
        orders=state / "orders.csv",
        unit_trades=state / "unit_trades.csv",
        equity_curve=state / "equity_curve.csv",
        daily=cfg.daily_path,
    )
    run(paths, force=not args.no_force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
