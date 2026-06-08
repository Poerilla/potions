#!/usr/bin/env python3
"""QQQ monthly DCA plus extra buys on sliding-low signals."""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from qqq_market_structure_dca_study import first_trading_day_each_month, money, monthly_dca_open, summarize_curve
from qqq_sliding_3m_low_limit_dca_study import DEFAULT_START, EVENT_MODES, max_drawdown
from qqq_yearly_orb_study import ROOT, default_completed_end, load_adjusted_daily


def monthly_dca_custom(daily: pd.DataFrame, monthly_amount: float, variant: str) -> pd.DataFrame:
    out = monthly_dca_open(daily, monthly_amount).copy()
    out["variant"] = variant
    return out


def simulate_extra_overlay(
    daily: pd.DataFrame,
    signals: pd.DataFrame,
    event_mode: str,
    monthly_amount: float,
    extra_amount: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    invest_dates = first_trading_day_each_month(daily)
    sig = signals[signals["event_mode"].eq(event_mode)].copy()
    sig["date"] = pd.to_datetime(sig["date"])
    by_date = {pd.Timestamp(row["date"]): row for _, row in sig.iterrows()}

    shares = 0.0
    total_contributed = 0.0
    rows = []
    events = []
    for _, bar in daily.sort_values("date").iterrows():
        date = pd.Timestamp(bar["date"])
        monthly_contribution = 0.0
        monthly_buy = 0.0
        extra_contribution = 0.0
        extra_buy = 0.0
        extra_price = math.nan
        signal = by_date.get(date)

        if date in invest_dates:
            monthly_contribution = monthly_amount
            monthly_buy = monthly_amount
            total_contributed += monthly_amount
            shares += monthly_amount / float(bar["open"])

        if signal is not None:
            extra_contribution = extra_amount
            extra_buy = extra_amount
            extra_price = float(signal["buy_price"])
            total_contributed += extra_amount
            shares += extra_amount / extra_price
            events.append(
                {
                    "date": date,
                    "event_mode": event_mode,
                    "event_type": "extra_buy_on_sliding_low",
                    "extra_amount": extra_amount,
                    "buy_price": extra_price,
                    "shares_bought": extra_amount / extra_price,
                    "rolling_low": float(signal["rolling_low"]),
                    "rolling_low_date": pd.Timestamp(signal["rolling_low_date"]),
                    "window_start": pd.Timestamp(signal["window_start"]),
                    "daily_low": float(signal["daily_low"]),
                    "daily_open": float(signal["daily_open"]),
                    "daily_close": float(signal["daily_close"]),
                }
            )

        invested = shares * float(bar["close"])
        rows.append(
            {
                "date": date,
                "variant": "monthly_dca_plus_%s_extra_%s" % (event_mode, int(extra_amount)),
                "event_mode": event_mode,
                "monthly_contribution": monthly_contribution,
                "extra_contribution": extra_contribution,
                "contribution": monthly_contribution + extra_contribution,
                "monthly_buy_amount": monthly_buy,
                "extra_buy_amount": extra_buy,
                "buy_amount": monthly_buy + extra_buy,
                "extra_buy_price": extra_price,
                "shares": shares,
                "cash": 0.0,
                "invested_value": invested,
                "equity": invested,
                "total_contributed": total_contributed,
                "exposure_frac": 1.0 if invested else 0.0,
            }
        )
    return pd.DataFrame(rows), pd.DataFrame(events)


def summarize_overlay(curve: pd.DataFrame, event_mode: str, base_summary: dict, equal_monthly_summary: dict, signal_count: int, years: float, extra_amount: float) -> dict:
    equity = pd.to_numeric(curve["equity"], errors="coerce")
    total = float(curve.iloc[-1]["total_contributed"]) if not curve.empty else 0.0
    ending = float(equity.iloc[-1]) if not curve.empty else 0.0
    net = ending - total
    dd = max_drawdown(equity)
    extra_contributed = float(pd.to_numeric(curve["extra_contribution"], errors="coerce").sum()) if not curve.empty else 0.0
    return {
        "variant": str(curve.iloc[0]["variant"]),
        "event_mode": event_mode,
        "signals": signal_count,
        "signals_per_year": signal_count / years if years else math.nan,
        "extra_amount": extra_amount,
        "base_monthly_contributed": float(base_summary["total_contributed"]),
        "extra_contributed": extra_contributed,
        "total_contributed": total,
        "ending_equity": ending,
        "net": net,
        "return_on_contributions_pct": net / total * 100.0 if total else math.nan,
        "max_dd": dd,
        "net_over_dd": net / abs(dd) if dd < 0 else math.inf,
        "ending_vs_base_monthly": ending - float(base_summary["ending_equity"]),
        "net_vs_base_monthly": net - float(base_summary["net"]),
        "ending_vs_equal_monthly": ending - float(equal_monthly_summary["ending_equity"]),
        "equal_monthly_amount": float(equal_monthly_summary["monthly_amount"]),
        "equal_monthly_ending_equity": float(equal_monthly_summary["ending_equity"]),
        "incremental_ending_per_extra_dollar": (ending - float(base_summary["ending_equity"])) / extra_contributed if extra_contributed else math.nan,
    }


def plot_overlay(base: pd.DataFrame, equal_monthly: pd.DataFrame, overlays: pd.DataFrame, out: Path, lookback_months: int) -> None:
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(base["date"], base["equity"], color="#111827", linewidth=1.6, label="$1k/month DCA")
    ax.plot(equal_monthly["date"], equal_monthly["equity"], color="#6b7280", linewidth=1.2, label="best same-total monthly DCA")
    colors = {"all_touches": "#7c3aed", "new_touch_cluster": "#0f766e", "first_touch_per_month": "#2563eb"}
    for mode, group in overlays.groupby("event_mode", sort=False):
        ax.plot(group["date"], group["equity"], color=colors.get(mode), linewidth=1.25, label="extra $500 " + mode)
    ax.set_title("QQQ $1k/month DCA plus extra $500 on %d-month sliding-low signals" % lookback_months)
    ax.set_ylabel("Equity ($)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=8)
    ax.xaxis.set_major_locator(mdates.YearLocator(base=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def write_report(
    out_dir: Path,
    lookback_months: int,
    base_summary: dict,
    best_equal_monthly_summary: dict,
    summary: pd.DataFrame,
    extra_amount: float,
) -> None:
    ranked = summary.sort_values("ending_equity", ascending=False).reset_index(drop=True)
    best = ranked.iloc[0]
    lines = [
        "# QQQ Sliding %d-Month Low Extra-$%d Overlay" % (lookback_months, int(extra_amount)),
        "",
        "Rule: keep regular QQQ DCA at **$1,000/month**, then contribute and buy an additional **$%d** whenever the selected sliding-low signal fires." % int(extra_amount),
        "",
        "The extra buy uses the trailing-low limit price from the sliding-low study. This is more capital than base DCA, so the table includes a same-total monthly-DCA comparison.",
        "",
        "Base monthly DCA: **%s contributed**, **%s ending equity**, **%s net**, **%s max DD**, **%.2f Net/DD**."
        % (
            money(float(base_summary["total_contributed"])),
            money(float(base_summary["ending_equity"])),
            money(float(base_summary["net"])),
            money(float(base_summary["max_dd"])),
            float(base_summary["net_over_dd"]),
        ),
        "",
        "## Leaderboard",
        "",
        "| Rank | Signal | Signals | Extra Contrib | Total Contrib | End Equity | More Than Base | Net | Max DD | Net/DD | Same-Total Monthly | vs Same-Total Monthly |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, (_, row) in enumerate(ranked.iterrows(), start=1):
        lines.append(
            "| %d | %s | %d | %s | %s | %s | %s | %s | %s | %.2f | %s/mo -> %s | %s |"
            % (
                rank,
                row["event_mode"],
                int(row["signals"]),
                money(float(row["extra_contributed"])),
                money(float(row["total_contributed"])),
                money(float(row["ending_equity"])),
                money(float(row["ending_vs_base_monthly"])),
                money(float(row["net"])),
                money(float(row["max_dd"])),
                float(row["net_over_dd"]),
                money(float(row["equal_monthly_amount"])),
                money(float(row["equal_monthly_ending_equity"])),
                money(float(row["ending_vs_equal_monthly"])),
            )
        )
    lines.extend(
        [
            "",
            "## Read",
            "",
            "- Best ending-equity overlay is **%s**, ending at **%s** after adding **%s** of extra contributions. That is **%s** more ending equity than the base `$1,000/month` DCA."
            % (
                best["event_mode"],
                money(float(best["ending_equity"])),
                money(float(best["extra_contributed"])),
                money(float(best["ending_vs_base_monthly"])),
            ),
            "- Against same-total monthly DCA, that best overlay is **%s**."
            % money(float(best["ending_vs_equal_monthly"])),
            "",
            "## Charts",
            "",
            "- Overlay equity comparison: [`charts/extra_500_overlay_equity.png`](charts/extra_500_overlay_equity.png)",
            "",
            "## Files",
            "",
            "- `extra_500_overlay_summary.csv`",
            "- `extra_500_overlay_curves.csv`",
            "- `extra_500_overlay_events.csv`",
        ]
    )
    (out_dir / "EXTRA_500_OVERLAY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run monthly DCA plus extra sliding-low buys.")
    parser.add_argument("--lookback-months", type=int, default=2)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=default_completed_end())
    parser.add_argument("--monthly-amount", type=float, default=1_000.0)
    parser.add_argument("--extra-amount", type=float, default=500.0)
    parser.add_argument("--study-root", type=Path, default=None)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    study_root = args.study_root or ROOT / "nq" / "case_studies" / ("qqq_sliding_%dm_low_limit_dca_study" % args.lookback_months)
    signals_path = study_root / "signals.csv"
    if not signals_path.exists():
        raise FileNotFoundError("Missing %s; run the sliding-low study first" % signals_path)

    daily = load_adjusted_daily("QQQ", args.start, args.end, ROOT / "data" / "benchmarks", refresh=args.refresh).sort_values("date").reset_index(drop=True)
    daily["date"] = pd.to_datetime(daily["date"])
    signals = pd.read_csv(signals_path, parse_dates=["date", "rolling_low_date", "window_start"])
    base = monthly_dca_open(daily, args.monthly_amount)
    base_summary = summarize_curve(base, "monthly_dca_open", 0, math.nan, 0.0)
    years = max((pd.Timestamp(daily.iloc[-1]["date"]) - pd.Timestamp(daily.iloc[0]["date"])).days / 365.25, 1e-9)

    overlay_parts = []
    event_parts = []
    summary_rows = []
    equal_monthly_summaries = {}
    for mode, _ in EVENT_MODES:
        signal_count = int(len(signals[signals["event_mode"].eq(mode)]))
        extra_contrib = signal_count * args.extra_amount
        total_contrib = float(base_summary["total_contributed"]) + extra_contrib
        month_count = int(pd.to_numeric(base["contribution"], errors="coerce").gt(0).sum())
        equal_monthly_amount = total_contrib / month_count if month_count else args.monthly_amount
        equal_monthly = monthly_dca_custom(daily, equal_monthly_amount, "same_total_monthly_dca_for_%s" % mode)
        equal_summary = summarize_curve(equal_monthly, "same_total_monthly_dca_for_%s" % mode, signal_count, signal_count / years, 0.0)
        equal_summary["monthly_amount"] = equal_monthly_amount
        equal_monthly_summaries[mode] = (equal_monthly, equal_summary)

        curve, events = simulate_extra_overlay(daily, signals, mode, args.monthly_amount, args.extra_amount)
        overlay_parts.append(curve)
        event_parts.append(events)
        summary_rows.append(summarize_overlay(curve, mode, base_summary, equal_summary, signal_count, years, args.extra_amount))

    overlays = pd.concat(overlay_parts, ignore_index=True)
    events = pd.concat(event_parts, ignore_index=True)
    summary = pd.DataFrame(summary_rows)
    best_equal_mode = summary.sort_values("ending_equity", ascending=False).iloc[0]["event_mode"]
    best_equal_monthly, best_equal_summary = equal_monthly_summaries[str(best_equal_mode)]

    summary.to_csv(study_root / "extra_500_overlay_summary.csv", index=False)
    overlays.to_csv(study_root / "extra_500_overlay_curves.csv", index=False)
    events.to_csv(study_root / "extra_500_overlay_events.csv", index=False)
    plot_overlay(base, best_equal_monthly, overlays, study_root / "charts" / "extra_500_overlay_equity.png", args.lookback_months)
    write_report(study_root, args.lookback_months, base_summary, best_equal_summary, summary, args.extra_amount)
    print("Wrote %s" % (study_root / "EXTRA_500_OVERLAY.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
