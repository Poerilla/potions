from __future__ import annotations

import math
import shutil
from pathlib import Path
from typing import Dict, Iterable, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from live.replay_manifest import write_run_manifest


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "live" / "state" / "ai_source_cta_package"
CHARTS = OUT / "charts"
EXHIBITS = OUT / "exhibits"

NQ_ROOT = ROOT / "live" / "state" / "nq_v2b_prior_opposed_stpmc_broker_like"
STRATEGY_ID = "nq_v2b_prior_opposed_stpmc_only_S_1_1_3"
STATE = NQ_ROOT / "states" / STRATEGY_ID
ROBUST = NQ_ROOT / "robustness_audit"
SCRUTINY = ROOT / "live" / "state" / "v2b_prior_opposed_execution_scrutiny"
BENCH = ROOT / "mnq" / "case_studies" / "fair_benchmark_comparison"

MODEL_CAPITAL = 1_000_000.0
PUBLIC_PROGRAM_NAME = "NQ Proprietary Intraday Futures Program"
PUBLIC_SLUG = "nq_intraday"
TEAR_SHEET_DOC = "NQ_INTRADAY_TEAR_SHEET.md"


def money(value: float, digits: int = 0) -> str:
    return f"${value:,.{digits}f}"


def pct(value: float, digits: int = 1) -> str:
    return f"{value:.{digits}f}%"


def ratio(value: float, digits: int = 2) -> str:
    if math.isinf(value):
        return "inf"
    return f"{value:.{digits}f}"


def md_table(rows: List[Dict[str, object]], columns: List[str]) -> str:
    if not rows:
        return ""
    out = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    return "\n".join(out)


def load_daily_equity() -> pd.DataFrame:
    eq = pd.read_csv(STATE / "equity_curve.csv")
    eq["ts"] = pd.to_datetime(eq["ts"], utc=True).dt.tz_convert("America/New_York")
    eq = eq.sort_values("ts")
    eq["date"] = eq["ts"].dt.date
    daily = eq.groupby("date").tail(1).copy()
    daily["date"] = pd.to_datetime(daily["date"])
    daily["model_equity"] = MODEL_CAPITAL + daily["close_equity_usd"].astype(float)
    daily["stress_equity"] = MODEL_CAPITAL + daily["intrabar_stress_equity_usd"].astype(float)
    daily["daily_return"] = daily["model_equity"].pct_change().fillna(
        daily["model_equity"].iloc[0] / MODEL_CAPITAL - 1.0
    )
    daily["close_drawdown_pct"] = daily["model_equity"] / daily["model_equity"].cummax() - 1.0
    daily["stress_drawdown_pct"] = daily["stress_equity"] / daily["model_equity"].cummax() - 1.0
    return daily


def max_drawdown_pct(series: pd.Series) -> float:
    return float((series / series.cummax() - 1.0).min())


def compute_metrics(daily: pd.DataFrame) -> Dict[str, float]:
    summary = pd.read_csv(NQ_ROOT / "summary.csv").iloc[0]
    campaigns = pd.read_csv(ROBUST / "campaigns_robustness.csv")
    start = daily["date"].iloc[0]
    end = daily["date"].iloc[-1]
    years = (end - start).days / 365.25
    ending_equity = float(daily["model_equity"].iloc[-1])
    cagr = (ending_equity / MODEL_CAPITAL) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    daily_returns = daily["daily_return"].astype(float)
    sharpe = math.sqrt(252) * daily_returns.mean() / daily_returns.std(ddof=1)
    downside = daily_returns[daily_returns < 0]
    sortino = math.sqrt(252) * daily_returns.mean() / downside.std(ddof=1)
    monthly = monthly_returns(daily)
    return {
        "start": start,
        "end": end,
        "years": years,
        "ending_equity": ending_equity,
        "net_usd": float(summary["net_usd"]),
        "closed_dd_usd": float(summary["closed_dd_usd"]),
        "stress_dd_usd": float(summary["intrabar_stress_dd_usd"]),
        "closed_dd_pct": max_drawdown_pct(daily["model_equity"]),
        "stress_dd_pct": float(daily["stress_drawdown_pct"].min()),
        "closed_dd_initial_pct": float(summary["closed_dd_usd"]) / MODEL_CAPITAL,
        "stress_dd_initial_pct": float(summary["intrabar_stress_dd_usd"]) / MODEL_CAPITAL,
        "return_pct": (ending_equity / MODEL_CAPITAL - 1.0) * 100.0,
        "cagr_pct": cagr * 100.0,
        "calmar_stress": cagr / abs(float(daily["stress_drawdown_pct"].min())),
        "sharpe": float(sharpe),
        "sortino": float(sortino),
        "trades": int(summary["trades"]),
        "units": int(summary["units"]),
        "win_rate_pct": float(summary["win_rate_pct"]),
        "profit_factor": float(summary["profit_factor"]),
        "net_over_stress": float(summary["net_over_stress"]),
        "avg_campaign": float(campaigns["net_usd"].mean()),
        "median_campaign": float(campaigns["net_usd"].median()),
        "max_win": float(campaigns["net_usd"].max()),
        "max_loss": float(campaigns["net_usd"].min()),
        "positive_months_pct": 100.0 * float((monthly["monthly_return_pct"] > 0).mean()),
        "best_month_pct": float(monthly["monthly_return_pct"].max()),
        "worst_month_pct": float(monthly["monthly_return_pct"].min()),
    }


def monthly_returns(daily: pd.DataFrame) -> pd.DataFrame:
    monthly = daily.set_index("date")["model_equity"].resample("M").last().dropna().to_frame("ending_equity")
    prior = monthly["ending_equity"].shift(1)
    if not monthly.empty:
        prior.iloc[0] = MODEL_CAPITAL
    monthly["monthly_return_pct"] = (monthly["ending_equity"] / prior - 1.0) * 100.0
    monthly["monthly_pnl_usd"] = monthly["ending_equity"].diff()
    if not monthly.empty:
        monthly.iloc[0, monthly.columns.get_loc("monthly_pnl_usd")] = monthly["ending_equity"].iloc[0] - MODEL_CAPITAL
    monthly = monthly.reset_index()
    monthly["year"] = monthly["date"].dt.year
    monthly["month"] = monthly["date"].dt.strftime("%b")
    return monthly


def yearly_model_returns(daily: pd.DataFrame) -> pd.DataFrame:
    annual = daily.set_index("date")["model_equity"].resample("Y").last().dropna().to_frame("ending_equity")
    prior = annual["ending_equity"].shift(1)
    if not annual.empty:
        prior.iloc[0] = MODEL_CAPITAL
    annual["return_pct"] = (annual["ending_equity"] / prior - 1.0) * 100.0
    annual["pnl_usd"] = annual["ending_equity"].diff()
    if not annual.empty:
        annual.iloc[0, annual.columns.get_loc("pnl_usd")] = annual["ending_equity"].iloc[0] - MODEL_CAPITAL
    annual = annual.reset_index()
    annual["year"] = annual["date"].dt.year
    return annual[["year", "ending_equity", "pnl_usd", "return_pct"]]


def write_charts(daily: pd.DataFrame, monthly: pd.DataFrame, yearly: pd.DataFrame) -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True, gridspec_kw={"height_ratios": [2.0, 1.0]})
    axes[0].plot(daily["date"], daily["model_equity"], color="#1f77b4", linewidth=1.8, label="Model equity")
    axes[0].set_title(f"{PUBLIC_PROGRAM_NAME}: Model Equity ($1M Reference)")
    axes[0].set_ylabel("Equity ($)")
    axes[0].grid(True, alpha=0.25)
    axes[0].legend(loc="upper left")
    axes[1].fill_between(daily["date"], daily["stress_drawdown_pct"] * 100.0, 0, color="#c44e52", alpha=0.45)
    axes[1].plot(daily["date"], daily["close_drawdown_pct"] * 100.0, color="#8c1d1d", linewidth=1.0, label="Close DD")
    axes[1].set_ylabel("Drawdown (%)")
    axes[1].grid(True, alpha=0.25)
    axes[1].legend(loc="lower left")
    fig.tight_layout()
    fig.savefig(CHARTS / f"{PUBLIC_SLUG}_equity_drawdown.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4.8))
    colors = np.where(yearly["pnl_usd"] >= 0, "#2ca02c", "#d62728")
    ax.bar(yearly["year"].astype(str), yearly["pnl_usd"], color=colors)
    ax.set_title("Annual Model P&L ($1M Reference)")
    ax.set_ylabel("P&L ($)")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(CHARTS / f"{PUBLIC_SLUG}_annual_pnl.png", dpi=160)
    plt.close(fig)

    heat = monthly.pivot(index="year", columns="month", values="monthly_return_pct")
    month_order = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    heat = heat.reindex(columns=month_order)
    fig, ax = plt.subplots(figsize=(12, 4.8))
    data = heat.to_numpy(dtype=float)
    finite = data[np.isfinite(data)]
    vmax = max(abs(float(np.nanmin(finite))), abs(float(np.nanmax(finite)))) if finite.size else 1.0
    im = ax.imshow(data, cmap="RdYlGn", vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(month_order)))
    ax.set_xticklabels(month_order)
    ax.set_yticks(range(len(heat.index)))
    ax.set_yticklabels(heat.index.astype(str))
    ax.set_title("Monthly Returns (%)")
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            if np.isfinite(data[i, j]):
                ax.text(j, i, f"{data[i, j]:.1f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    fig.tight_layout()
    fig.savefig(CHARTS / f"{PUBLIC_SLUG}_monthly_returns.png", dpi=160)
    plt.close(fig)

    ranking = pd.read_csv(BENCH / "top_strats_common_account_executable.csv").head(9)
    fig, ax = plt.subplots(figsize=(11, 5.2))
    labels = (
        ranking["strategy"]
        .str.replace("NQ v2b prior-opposed ST+PMC gate S_1_1_3", PUBLIC_PROGRAM_NAME, regex=False)
        .str.wrap(28)
    )
    ax.barh(range(len(ranking)), ranking["futures_return_pct"], color="#4c78a8")
    ax.set_yticks(range(len(ranking)))
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel("Return on $1M common account (%)")
    ax.set_title("Current Executable Strategy Ranking Context")
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(CHARTS / "common_account_ranking.png", dpi=160)
    plt.close(fig)


def write_exhibits(daily: pd.DataFrame, monthly: pd.DataFrame, yearly: pd.DataFrame, metrics: Dict[str, float]) -> None:
    EXHIBITS.mkdir(parents=True, exist_ok=True)
    daily_export = daily[
        ["date", "model_equity", "stress_equity", "daily_return", "close_drawdown_pct", "stress_drawdown_pct"]
    ].copy()
    daily_export["date"] = daily_export["date"].dt.date
    daily_export.to_csv(EXHIBITS / f"{PUBLIC_SLUG}_daily_equity.csv", index=False)
    monthly.to_csv(EXHIBITS / f"{PUBLIC_SLUG}_monthly_returns.csv", index=False)
    yearly.to_csv(EXHIBITS / f"{PUBLIC_SLUG}_yearly_model_returns.csv", index=False)
    pd.DataFrame([metrics]).to_csv(EXHIBITS / f"{PUBLIC_SLUG}_key_metrics.csv", index=False)

    context = pd.read_csv(BENCH / "top_strats_common_account_executable.csv").head(9)
    context["strategy"] = context["strategy"].replace(
        {"NQ v2b prior-opposed ST+PMC gate S_1_1_3": PUBLIC_PROGRAM_NAME}
    )
    context = context.drop(columns=["slug"], errors="ignore")
    context.to_csv(EXHIBITS / "top_strategy_common_account_context.csv", index=False)

    market_rows = []
    for market in ["nq", "mnq", "es", "ym", "mym"]:
        path = ROOT / "live" / "state" / f"{market}_v2b_prior_opposed_stpmc_broker_like" / "summary.csv"
        if path.exists():
            row = pd.read_csv(path).iloc[0].to_dict()
            market_rows.append(
                {
                    "market": market.upper(),
                    "campaigns": int(row["trades"]),
                    "unit_exits": int(row["units"]),
                    "net_usd": float(row["net_usd"]),
                    "closed_dd_usd": float(row["closed_dd_usd"]),
                    "intrabar_stress_dd_usd": float(row["intrabar_stress_dd_usd"]),
                    "win_rate_pct": float(row["win_rate_pct"]),
                    "profit_factor": float(row["profit_factor"]),
                    "net_over_stress": float(row["net_over_stress"]),
                    "causality_violations": int(row.get("causality_violations") or 0),
                }
            )
    pd.DataFrame(market_rows).to_csv(EXHIBITS / "cross_market_summary.csv", index=False)


def tear_sheet(metrics: Dict[str, float], monthly: pd.DataFrame, yearly: pd.DataFrame) -> str:
    yearly_robust = pd.read_csv(ROBUST / "yearly_breakdown.csv")
    filter_study = pd.read_csv(ROBUST / "filter_scenario_matrix.csv")
    event_study = pd.read_csv(ROBUST / "event_scenario_matrix.csv")
    scrutiny = pd.read_csv(EXHIBITS / "cross_market_summary.csv")

    key_rows = [
        {"Metric": "Program", "Value": PUBLIC_PROGRAM_NAME},
        {"Metric": "Performance type", "Value": "Simulated broker-like internal replay"},
        {"Metric": "Window", "Value": f"{metrics['start'].date()} to {metrics['end'].date()}"},
        {"Metric": "$1M model ending equity", "Value": money(metrics["ending_equity"], 0)},
        {"Metric": "$1M model net return", "Value": pct(metrics["return_pct"], 1)},
        {"Metric": "CAGR on $1M model", "Value": pct(metrics["cagr_pct"], 1)},
        {
            "Metric": "Max intrabar stress DD",
            "Value": (
                f"{money(metrics['stress_dd_usd'], 0)} / "
                f"{pct(metrics['stress_dd_initial_pct'] * 100.0, 1)} of initial / "
                f"{pct(metrics['stress_dd_pct'] * 100.0, 1)} peak-to-trough"
            ),
        },
        {
            "Metric": "Max closed DD",
            "Value": (
                f"{money(metrics['closed_dd_usd'], 0)} / "
                f"{pct(metrics['closed_dd_initial_pct'] * 100.0, 1)} of initial / "
                f"{pct(metrics['closed_dd_pct'] * 100.0, 1)} peak-to-trough"
            ),
        },
        {"Metric": "Profit factor", "Value": ratio(metrics["profit_factor"], 2)},
        {"Metric": "Campaign win rate", "Value": pct(metrics["win_rate_pct"], 1)},
        {"Metric": "Net / stress DD", "Value": ratio(metrics["net_over_stress"], 2)},
        {"Metric": "Sharpe / Sortino", "Value": f"{ratio(metrics['sharpe'], 2)} / {ratio(metrics['sortino'], 2)}"},
        {"Metric": "Campaigns / unit exits", "Value": f"{metrics['trades']:,} / {metrics['units']:,}"},
    ]

    annual_rows = []
    for row in yearly_robust.itertuples(index=False):
        annual_rows.append(
            {
                "Year": int(row.year),
                "Campaigns": int(row.trades),
                "Net": money(float(row.net_usd), 0),
                "Win %": pct(float(row.win_rate_pct), 1),
                "PF": ratio(float(row.profit_factor), 2),
                "Closed DD": money(float(row.closed_dd_usd), 0),
                "Net/DD": ratio(float(row.net_over_closed_dd), 2),
            }
        )

    cross_rows = []
    for row in scrutiny.sort_values("net_over_stress", ascending=False).itertuples(index=False):
        cross_rows.append(
            {
                "Market": row.market,
                "Campaigns": f"{int(row.campaigns):,}",
                "Net": money(float(row.net_usd), 0),
                "Stress DD": money(float(row.intrabar_stress_dd_usd), 0),
                "Win %": pct(float(row.win_rate_pct), 1),
                "PF": ratio(float(row.profit_factor), 2),
                "Net/Stress": ratio(float(row.net_over_stress), 2),
            }
        )

    best_filter = filter_study.iloc[0]
    base_event = event_study[event_study["scenario"] == "base_1_1_3"].iloc[0]

    return "\n".join(
        [
            f"# {PUBLIC_PROGRAM_NAME} - Performance Tear Sheet",
            "",
            "**Distribution status:** draft for diligence review. This document contains simulated/backtested performance, not audited live CTA performance.",
            "",
            "**Hypothetical performance notice:** Results shown are simulated or hypothetical and have material limitations. They do not represent actual client trading. They may not reflect all market-impact, liquidity, operational, psychological, or implementation risks. Compliance counsel should review this document and insert any required CFTC/NFA prescribed language before external distribution.",
            "",
            "## Executive Snapshot",
            "",
            md_table(key_rows, ["Metric", "Value"]),
            "",
            f"![Equity and drawdown](charts/{PUBLIC_SLUG}_equity_drawdown.png)",
            "",
            "## Strategy Description",
            "",
            "- Instrument: **NQ futures**.",
            "- Signal family: proprietary multi-timeframe intraday setup using a directional gate and later opposing price-confirmation trigger.",
            "- Entry logic: early-session range and momentum conditions are evaluated causally; orders are armed only after confirming data is available.",
            "- Position management: capped intraday exposure, predefined partial exits, protective stop management, and session-end flattening.",
            "- Replay engine: internal order-lifecycle replay; orders are active only after confirming bars close.",
            "- Realism baseline: 1-tick adverse slippage on market/stop fills, stop gap-through fills, stop-first same-bar ambiguity, and $1.50 fee per closed unit in the audit.",
            "- External diligence note: exact signal formulas, timing parameters, and sizing map are intentionally omitted from this draft and can be handled separately under diligence/NDA.",
            "",
            "## Annual Stability",
            "",
            md_table(annual_rows, ["Year", "Campaigns", "Net", "Win %", "PF", "Closed DD", "Net/DD"]),
            "",
            f"![Annual P&L](charts/{PUBLIC_SLUG}_annual_pnl.png)",
            "",
            f"![Monthly returns](charts/{PUBLIC_SLUG}_monthly_returns.png)",
            "",
            "## Robustness Read",
            "",
            f"- Weakest year: **2022**, with {money(13425, 0)} net and 1.17 PF. It remained positive but was not a strong year.",
            "- Rolling 50-campaign PF never dropped below 1.0 in the robustness audit.",
            "- Top 10 winners account for roughly 28% of total net; deleting the top 10 still left the strategy positive in the robustness pass.",
            f"- First risk-control lever: reduce size in the widest early-session range bucket; the internal reduced-size variant kept {money(float(best_filter['net_usd']), 0)} net and improved reconstructed Net/Stress to {ratio(float(best_filter['net_over_stress']), 2)}.",
            f"- CPI/FOMC skipping did **not** improve the base row; event study base remained {money(float(base_event['net_usd']), 0)} and {ratio(float(base_event['net_over_stress']), 2)} reconstructed Net/Stress.",
            "",
            "## Cross-Market Confirmation",
            "",
            md_table(cross_rows, ["Market", "Campaigns", "Net", "Stress DD", "Win %", "PF", "Net/Stress"]),
            "",
            "## Current Gating Risks",
            "",
            "- The fill-book causal audit passes: NQ has **352 / 352** qualifying campaign entries and **0** causal violations.",
            "- It is **not tick-proven yet**. NQ execution scrutiny marks 141 campaigns as bar-safe, 45 as same-minute ambiguous, and 166 as requiring deeper sequence review.",
            "- The coarse one-minute review is encouraging but incomplete: most non-bar-safe campaigns later revisit the relevant price zone, with one rough no-later-touch case.",
            "- The next diligence step is tick reconstruction and broker-paper shadow mode, not rule optimization.",
            "",
            "## Internal Support",
            "",
            "- Replay logs, chart packs, execution-scrutiny reports, and refresh scripts are archived internally.",
            "- External distribution should use this tear sheet plus compliance-reviewed exhibits, not raw strategy source paths.",
            "",
        ]
    )


def presentation(metrics: Dict[str, float]) -> str:
    ranking = pd.read_csv(BENCH / "top_strats_common_account_executable.csv").head(5)
    rank_rows = []
    for idx, row in ranking.iterrows():
        strategy_label = (
            PUBLIC_PROGRAM_NAME
            if row["strategy"] == "NQ v2b prior-opposed ST+PMC gate S_1_1_3"
            else row["strategy"]
        )
        rank_rows.append(
            {
                "Rank": idx + 1,
                "Strategy": strategy_label,
                "Books": int(row["integer_books"]),
                "Net": money(float(row["futures_net_usd"]), 0),
                "Return": pct(float(row["futures_return_pct"]), 1),
                "Stress DD": money(float(row["futures_stress_dd_usd"]), 0),
                "Net/DD": ratio(float(row["futures_net_over_stress"]), 2),
            }
        )

    return "\n".join(
        [
            "# Strategy Presentation Draft - aiSource CTA Diligence",
            "",
            "**Use:** Markdown slide draft. Convert to PDF/PowerPoint after compliance review.",
            "",
            "**Performance status:** simulated/backtested. No audited live CTA track record is presented in this draft.",
            "",
            "---",
            "",
            "## 1. Program Summary",
            "",
            f"- Primary program candidate: **{PUBLIC_PROGRAM_NAME}**.",
            "- Design goal: intraday, rule-based futures exposure with hard order lifecycle rules and daily flat behavior.",
            "- Core idea: a proprietary multi-timeframe condition identifies sessions where an initial directional impulse may set up a higher-quality opposing intraday opportunity.",
            "- Current status: strong broker-like replay, cross-market confirmation, execution scrutiny pending tick proof and broker-paper parity.",
            "",
            "---",
            "",
            "## 2. What The Strategy Trades",
            "",
            "- Market: **Nasdaq 100 futures (NQ)** as flagship; related index-futures markets confirm the pattern family.",
            "- Timeframes: multi-timeframe intraday gate plus lower-timeframe execution path.",
            "- Entry type: causal price-confirmation order after proprietary gate activation.",
            "- Exit type: predefined partial exits, protective stops, adaptive runner management, and session-end flattening.",
            "",
            "---",
            "",
            "## 3. Why This Is Different",
            "",
            "- The strategy does not blindly trade every intraday breakout.",
            "- It waits for a proprietary intraday gate before allowing a later opposing price-confirmation campaign.",
            "- The initial directional gate is not the main profit source; the edge is in the conditional follow-on campaign.",
            "- This delayed, causal arming path is different from filtering a completed trade tape after the fact.",
            "",
            "---",
            "",
            "## 4. Performance Snapshot",
            "",
            md_table(
                [
                    {"Metric": "Window", "Value": f"{metrics['start'].date()} to {metrics['end'].date()}"},
                    {"Metric": "Net, base book", "Value": money(metrics["net_usd"], 0)},
                    {"Metric": "$1M reference return", "Value": pct(metrics["return_pct"], 1)},
                    {"Metric": "CAGR, $1M reference", "Value": pct(metrics["cagr_pct"], 1)},
                    {"Metric": "Intrabar stress DD", "Value": money(metrics["stress_dd_usd"], 0)},
                    {"Metric": "Win rate / PF", "Value": f"{pct(metrics['win_rate_pct'], 1)} / {ratio(metrics['profit_factor'], 2)}"},
                    {"Metric": "Net / stress DD", "Value": ratio(metrics["net_over_stress"], 2)},
                ],
                ["Metric", "Value"],
            ),
            "",
            f"![Equity and drawdown](charts/{PUBLIC_SLUG}_equity_drawdown.png)",
            "",
            "---",
            "",
            "## 5. Current Ranking Context",
            "",
            "The common-account view gives each setup the same $1,000,000 account, uses integer base books only, and leaves idle cash idle.",
            "",
            md_table(rank_rows, ["Rank", "Strategy", "Books", "Net", "Return", "Stress DD", "Net/DD"]),
            "",
            "![Common account ranking](charts/common_account_ranking.png)",
            "",
            "---",
            "",
            "## 6. Robustness Findings",
            "",
            "- Positive yearly record in every tested year, but **2022 is weak** and should be discussed openly.",
            "- Wide early-session range days degrade most sharply; a reduced-size range-width rule improves reconstructed efficiency but is not yet part of the frozen strategy.",
            "- CPI/FOMC date skipping did not beat the base rule in the first official-date audit.",
            "- Top-winner deletion leaves the strategy profitable, but right-tail concentration is real.",
            "",
            "---",
            "",
            "## 7. Execution Readiness",
            "",
            "- Broker-like replay uses the same internal order-lifecycle framework intended for automation.",
            "- Causal gate check: **0 violations** across NQ, MNQ, ES, YM, and MYM.",
            "- Current blocker: same-minute ambiguous and sequence-sensitive campaigns need tick reconstruction.",
            "- Next stage: signal-only shadow mode, EOD replay parity, then small broker-paper sizing.",
            "",
            "---",
            "",
            "## 8. Risk Controls",
            "",
            "- Session-end flattening.",
            "- Bracketed campaign exits with protective stops, partial exits, and runner management.",
            "- Replay realism includes slippage, stop gap-through, and stop-first ambiguity.",
            "- Proposed live-readiness controls: stale-feed kill switch, duplicate/out-of-order bar detection, broker reconciliation, and no duplicate re-arming after restart.",
            "",
            "---",
            "",
            "## 9. Compliance Positioning",
            "",
            "- Present as **hypothetical/simulated performance** until actual managed-account performance exists.",
            "- Keep assumptions next to every performance table.",
            "- Add exact CFTC/NFA hypothetical-performance disclaimer language after counsel review.",
            "- Do not imply audited live performance, client results, or guaranteed capacity.",
            "",
            "---",
            "",
            "## 10. CTA Launch Roadmap",
            "",
            "1. Tick-reconstruct sequence-sensitive campaigns.",
            "2. Run signal-only live shadow mode and replay persisted feed at EOD.",
            "3. Paper trade with one-contract-equivalent sizing.",
            "4. Document brokerage, latency, error handling, and reconciliation.",
            "5. Only then produce an actual-performance supplement.",
            "",
        ]
    )


def compliance_notes() -> str:
    return "\n".join(
        [
            "# Compliance Notes For Performance Materials",
            "",
            "This is a working checklist, not legal advice.",
            "",
            "## Current Package Status",
            "",
            "- The package contains **simulated/backtested** strategy results.",
            "- It does not contain audited live CTA client performance.",
            "- The external version intentionally omits exact signal formulas, timestamps, and sizing parameters.",
            "- It should not be distributed externally until reviewed by qualified compliance counsel.",
            "- Any external version should place the required hypothetical-performance cautionary language immediately next to performance results, not only on a cover page.",
            "",
            "## Official References Checked",
            "",
            "- NFA Compliance Rule 2-29, promotional material and hypothetical performance: https://www.nfa.futures.org/rulebooksql/rules.aspx?RuleID=RULE+2-29&Section=4",
            "- CFTC discussion of Rule 4.41 and proximity of hypothetical-performance statements: https://www.cftc.gov/LawRegulation/FederalRegister/FinalRules/e7-3122.html",
            "- NFA promotional material guide: https://www.nfa.futures.org/members/member-resources/files/promo-material-guide.pdf",
            "",
            "## Assumptions To Keep With The Tear Sheet",
            "",
            "- Model account: $1,000,000 reference capital for return statistics.",
            "- Futures base book: capped NQ intraday campaign unit; exact sizing map retained internally.",
            "- Replay window: 2021-03-04 through 2026-03-06.",
            "- Execution engine: internal order-lifecycle replay.",
            "- Costs: 1-tick adverse slippage on market/stop fills and $1.50 per closed unit in audit.",
            "- Known unresolved issue: tick reconstruction is still required for same-minute and sequence-sensitive campaigns.",
            "",
        ]
    )


def readme(metrics: Dict[str, float]) -> str:
    return "\n".join(
        [
            "# aiSource CTA Diligence Package",
            "",
            "Draft performance and strategy materials for an aiSource CTA conversation.",
            "",
            "## Documents",
            "",
            f"- [{TEAR_SHEET_DOC}]({TEAR_SHEET_DOC})",
            "- [STRATEGY_PRESENTATION.md](STRATEGY_PRESENTATION.md)",
            "- [COMPLIANCE_NOTES.md](COMPLIANCE_NOTES.md)",
            "",
            "## Key Read",
            "",
            f"- Flagship simulated broker-like program: **{PUBLIC_PROGRAM_NAME}**.",
            f"- Base replay: **{money(metrics['net_usd'], 0)} net**, **{money(metrics['stress_dd_usd'], 0)} intrabar stress DD**, **{ratio(metrics['net_over_stress'], 2)} Net/Stress**, **{pct(metrics['win_rate_pct'], 1)} win**, **{ratio(metrics['profit_factor'], 2)} PF**.",
            f"- $1M reference account: **{pct(metrics['return_pct'], 1)} total return**, **{pct(metrics['cagr_pct'], 1)} CAGR**, **{pct(metrics['stress_dd_initial_pct'] * 100.0, 1)} stress DD vs initial capital**.",
            "- This is **not** audited live CTA performance.",
            "",
            "## Exhibits",
            "",
            f"- `exhibits/{PUBLIC_SLUG}_key_metrics.csv`",
            f"- `exhibits/{PUBLIC_SLUG}_monthly_returns.csv`",
            f"- `exhibits/{PUBLIC_SLUG}_yearly_model_returns.csv`",
            "- `exhibits/cross_market_summary.csv`",
            "- `exhibits/top_strategy_common_account_context.csv`",
            "",
            "## Charts",
            "",
            f"- `charts/{PUBLIC_SLUG}_equity_drawdown.png`",
            f"- `charts/{PUBLIC_SLUG}_annual_pnl.png`",
            f"- `charts/{PUBLIC_SLUG}_monthly_returns.png`",
            "- `charts/common_account_ranking.png`",
            "",
        ]
    )


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    CHARTS.mkdir(parents=True, exist_ok=True)
    EXHIBITS.mkdir(parents=True, exist_ok=True)

    daily = load_daily_equity()
    monthly = monthly_returns(daily)
    yearly = yearly_model_returns(daily)
    metrics = compute_metrics(daily)

    write_charts(daily, monthly, yearly)
    write_exhibits(daily, monthly, yearly, metrics)

    (OUT / "README.md").write_text(readme(metrics), encoding="utf-8")
    (OUT / TEAR_SHEET_DOC).write_text(tear_sheet(metrics, monthly, yearly), encoding="utf-8")
    (OUT / "STRATEGY_PRESENTATION.md").write_text(presentation(metrics), encoding="utf-8")
    (OUT / "COMPLIANCE_NOTES.md").write_text(compliance_notes(), encoding="utf-8")
    write_run_manifest(
        OUT,
        data_inputs=[STATE / "fills.csv", STATE / "orders.csv", ROBUST / "yearly_breakdown.csv"],
        output_paths=[
            OUT / "README.md",
            OUT / TEAR_SHEET_DOC,
            OUT / "STRATEGY_PRESENTATION.md",
            OUT / "COMPLIANCE_NOTES.md",
        ],
        strategy_config={"driver": "generate_ai_source_cta_package", "public_program_name": PUBLIC_PROGRAM_NAME},
        causality_mode="audit",
        repo_root=ROOT,
    )
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
