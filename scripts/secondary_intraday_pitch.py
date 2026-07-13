#!/usr/bin/env python3
"""Build one-page PDFs for secondary intraday systems."""
from __future__ import annotations

import csv
import math
import textwrap
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class PitchConfig:
    out_dir: Path
    strategy_name: str
    read_label: str
    start_capital: float
    equity_path: Path
    unit_path: Path
    unit_usd_col: str
    unit_exit_col: str
    point_value: float | None
    benchmark_name: str
    benchmark_daily: Path
    chart_file: str
    source_summary: Path
    pitch_start: pd.Timestamp
    pitch_end: pd.Timestamp


CONFIGS = [
    PitchConfig(
        out_dir=ROOT / "live/state/unconstrained_nasdaq_managed_intraday_pitch",
        strategy_name="Unconstrained Nasdaq Managed Intraday Strategy",
        read_label="unconstrained intraday breakout sleeve",
        start_capital=355_000.0,
        equity_path=ROOT / "live/state/v2b_sizing_sweep/states/nq_v2b_sizing_S_1_1_3/equity_curve.csv",
        unit_path=ROOT / "live/state/v2b_sizing_sweep/states/nq_v2b_sizing_S_1_1_3/unit_trades.csv",
        unit_usd_col="net_usd",
        unit_exit_col="exit_ts",
        point_value=None,
        benchmark_name="QQQ",
        benchmark_daily=ROOT / "data/benchmarks/QQQ_2021-03-04_2026-03-06_yahoo_daily.csv",
        chart_file="unconstrained_nasdaq_intraday_vs_qqq_355k.png",
        source_summary=ROOT / "live/state/v2b_sizing_sweep/summary_partial.csv",
        pitch_start=pd.Timestamp("2021-03-04"),
        pitch_end=pd.Timestamp("2026-03-06"),
    ),
    PitchConfig(
        out_dir=ROOT / "live/state/nasdaq_managed_intraday_trend_follower_ii_pitch",
        strategy_name="Nasdaq Managed Intraday Trend Follower II",
        read_label="trend-following intraday sleeve",
        start_capital=75_000.0,
        equity_path=ROOT
        / "live/state/hourly_st_pmc_strategyplugin_variants_cross_market/nq/audits/"
        / "nq_hourly_st_pmc_sl25_tp75_3r/nq_hourly_st_pmc_sl25_tp75_3r/equity_curve.csv",
        unit_path=ROOT
        / "live/state/hourly_st_pmc_strategyplugin_variants_cross_market/nq/audits/"
        / "nq_hourly_st_pmc_sl25_tp75_3r/nq_hourly_st_pmc_sl25_tp75_3r/unit_fills.csv",
        unit_usd_col="usd",
        unit_exit_col="exit_ts",
        point_value=20.0,
        benchmark_name="QQQ",
        benchmark_daily=ROOT / "data/benchmarks/QQQ_2010-06-06_2026-03-08_yahoo_daily.csv",
        chart_file="nasdaq_trend_follower_ii_vs_qqq_75k_full_history.png",
        source_summary=ROOT / "live/state/hourly_st_pmc_strategyplugin_variants_cross_market/summary.csv",
        pitch_start=pd.Timestamp("2010-06-06"),
        pitch_end=pd.Timestamp("2026-03-08"),
    ),
    PitchConfig(
        out_dir=ROOT / "live/state/dow_managed_intraday_trend_follower_ii_pitch",
        strategy_name="Dow Managed Intraday Trend Follower II",
        read_label="Dow trend-following intraday sleeve",
        start_capital=50_000.0,
        equity_path=ROOT
        / "live/state/hourly_st_pmc_strategyplugin_variants/audits/"
        / "ym_hourly_st_pmc_sl40_tp120_3r/ym_hourly_st_pmc_sl40_tp120_3r/equity_curve.csv",
        unit_path=ROOT
        / "live/state/hourly_st_pmc_strategyplugin_variants/audits/"
        / "ym_hourly_st_pmc_sl40_tp120_3r/ym_hourly_st_pmc_sl40_tp120_3r/unit_fills.csv",
        unit_usd_col="usd",
        unit_exit_col="exit_ts",
        point_value=5.0,
        benchmark_name="DIA",
        benchmark_daily=ROOT / "data/benchmarks/DIA_2010-01-01_2026-06-03_daily.csv",
        chart_file="dow_trend_follower_ii_vs_dia_50k_full_history.png",
        source_summary=ROOT / "live/state/hourly_st_pmc_strategyplugin_variants/summary.csv",
        pitch_start=pd.Timestamp("2010-06-06"),
        pitch_end=pd.Timestamp("2026-05-06"),
    ),
]


def money(value: float) -> str:
    return f"${value:,.0f}"


def money2(value: float) -> str:
    return f"${value:,.2f}"


def pct(value: float) -> str:
    return f"{value:.1f}%"


def max_drawdown(series: pd.Series) -> float:
    return float((series - series.cummax()).min()) if not series.empty else 0.0


def drawdown_duration_days(series: pd.Series, dates: pd.Series) -> int:
    peak = -math.inf
    start = None
    max_days = 0
    for dt, value in zip(dates, series):
        if value >= peak:
            peak = float(value)
            start = None
            continue
        if start is None:
            start = dt
        max_days = max(max_days, int((dt - start).days))
    return max_days


def load_strategy_daily(config: PitchConfig) -> pd.DataFrame:
    raw = pd.read_csv(config.equity_path)
    raw["ts"] = pd.to_datetime(raw["ts"], utc=True)
    raw["date"] = pd.to_datetime(raw["ts"].dt.date)

    if "close_equity_usd" in raw.columns:
        prior = raw[raw["date"] < config.pitch_start]
        base = float(prior["close_equity_usd"].iloc[-1]) if not prior.empty else 0.0
        raw["strategy_net"] = raw["close_equity_usd"].astype(float) - base
        raw["stress_net"] = raw.get("intrabar_stress_equity_usd", raw["close_equity_usd"]).astype(float) - base
    else:
        if config.point_value is None:
            raise RuntimeError(f"point_value required for point equity curve: {config.equity_path}")
        prior = raw[raw["date"] < config.pitch_start]
        base = float(prior["close_equity_points"].iloc[-1]) if not prior.empty else 0.0
        raw["strategy_net"] = (raw["close_equity_points"].astype(float) - base) * config.point_value
        raw["stress_net"] = (raw.get("intrabar_stress_points", raw["close_equity_points"]).astype(float) - base) * config.point_value

    raw = raw[(raw["date"] >= config.pitch_start) & (raw["date"] <= config.pitch_end)].copy()
    if raw.empty:
        raise RuntimeError(f"No equity rows in pitch window: {config.equity_path}")

    daily = raw.groupby("date", as_index=False).tail(1)[["date", "strategy_net", "stress_net"]]
    daily["strategy_equity"] = config.start_capital + daily["strategy_net"]
    daily["strategy_stress_equity"] = config.start_capital + daily["stress_net"]
    return daily.reset_index(drop=True)


def load_benchmark_daily(config: PitchConfig, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    daily = pd.read_csv(config.benchmark_daily, parse_dates=["date"])
    daily = daily.sort_values("date")
    daily = daily[(daily["date"] >= start_date) & (daily["date"] <= end_date)].copy()
    if daily.empty:
        raise RuntimeError(f"No benchmark rows in pitch window: {config.benchmark_daily}")
    first_adj = float(daily.iloc[0]["adj_close"])
    daily["benchmark_equity"] = config.start_capital * daily["adj_close"].astype(float) / first_adj
    return daily[["date", "benchmark_equity"]].reset_index(drop=True)


def load_unit_campaigns(config: PitchConfig) -> pd.DataFrame:
    units = pd.read_csv(config.unit_path)
    units[config.unit_exit_col] = pd.to_datetime(units[config.unit_exit_col], utc=True)
    units["date"] = pd.to_datetime(units[config.unit_exit_col].dt.date)
    units = units[(units["date"] >= config.pitch_start) & (units["date"] <= config.pitch_end)].copy()
    if units.empty:
        return pd.DataFrame(columns=["trade_id", "date", "pnl"])
    grouped = units.groupby("trade_id", as_index=False).agg(
        date=("date", "max"),
        pnl=(config.unit_usd_col, "sum"),
    )
    return grouped


def build_annual_rows(curves: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    strategy_rows: list[dict] = []
    benchmark_rows: list[dict] = []
    prev_strategy = float(curves["strategy_equity"].iloc[0])
    prev_benchmark = float(curves["benchmark_equity"].iloc[0])

    for year, group in curves.groupby(curves["date"].dt.year):
        s_start = prev_strategy
        s_end = float(group["strategy_equity"].iloc[-1])
        s_net = s_end - s_start
        s_dd = max_drawdown(group["strategy_equity"])
        strategy_rows.append(
            {
                "year": int(year),
                "start": s_start,
                "net": s_net,
                "end": s_end,
                "return_pct": s_net / s_start * 100.0,
                "dd": s_dd,
                "dd_pct": abs(s_dd) / s_start * 100.0,
            }
        )
        prev_strategy = s_end

        b_start = prev_benchmark
        b_end = float(group["benchmark_equity"].iloc[-1])
        b_net = b_end - b_start
        b_dd = max_drawdown(group["benchmark_equity"])
        benchmark_rows.append(
            {
                "year": int(year),
                "start": b_start,
                "net": b_net,
                "end": b_end,
                "return_pct": b_net / b_start * 100.0,
                "dd": b_dd,
                "dd_pct": abs(b_dd) / b_start * 100.0,
            }
        )
        prev_benchmark = b_end
    return strategy_rows, benchmark_rows


def add_start_anchor(config: PitchConfig, curves: pd.DataFrame) -> pd.DataFrame:
    first_date = curves["date"].iloc[0]
    anchor = pd.DataFrame(
        [
            {
                "date": first_date - pd.Timedelta(days=1),
                "strategy_net": 0.0,
                "stress_net": 0.0,
                "strategy_equity": config.start_capital,
                "strategy_stress_equity": config.start_capital,
                "benchmark_equity": config.start_capital,
            }
        ]
    )
    return pd.concat([anchor, curves], ignore_index=True).sort_values("date").reset_index(drop=True)


def compute_metrics(config: PitchConfig, curves: pd.DataFrame, campaigns: pd.DataFrame) -> dict:
    strategy = curves["strategy_equity"].astype(float)
    benchmark = curves["benchmark_equity"].astype(float)
    strategy_ret = strategy.pct_change().dropna()
    benchmark_ret = benchmark.pct_change().dropna()
    years = (curves["date"].iloc[-1] - config.pitch_start).days / 365.25
    net = float(strategy.iloc[-1] - strategy.iloc[0])
    cagr = ((float(strategy.iloc[-1]) / float(strategy.iloc[0])) ** (1.0 / years) - 1.0) * 100.0
    dd = max_drawdown(strategy)
    dd_pct = abs(dd) / float(strategy.iloc[0]) * 100.0
    stress_dd = float((curves["strategy_stress_equity"] - curves["strategy_stress_equity"].cummax()).min())

    downside = strategy_ret[strategy_ret < 0]
    sharpe = float(strategy_ret.mean() / strategy_ret.std() * math.sqrt(252)) if strategy_ret.std() else 0.0
    sortino = float(strategy_ret.mean() / downside.std() * math.sqrt(252)) if downside.std() else 0.0
    corr = float(strategy_ret.corr(benchmark_ret)) if len(strategy_ret) and len(benchmark_ret) else 0.0
    down_bench = pd.DataFrame({"s": strategy_ret, "b": benchmark_ret}).dropna()
    down_bench = down_bench[down_bench["b"] < 0]
    down_capture = (
        float(down_bench["s"].mean() / down_bench["b"].mean())
        if not down_bench.empty and float(down_bench["b"].mean()) != 0.0
        else 0.0
    )

    if campaigns.empty:
        pf = 0.0
        win_rate = 0.0
        trades = 0
    else:
        wins = campaigns[campaigns["pnl"] > 0]["pnl"].sum()
        losses = campaigns[campaigns["pnl"] < 0]["pnl"].sum()
        pf = float(wins / abs(losses)) if losses else 0.0
        win_rate = float((campaigns["pnl"] > 0).mean() * 100.0)
        trades = int(campaigns["trade_id"].nunique())

    return {
        "window": f"{config.pitch_start.date()} to {curves['date'].iloc[-1].date()}",
        "net": net,
        "cagr": cagr,
        "max_dd": dd,
        "max_dd_pct": dd_pct,
        "stress_dd": stress_dd,
        "net_over_stress": net / abs(stress_dd) if stress_dd else 0.0,
        "calmar": cagr / dd_pct if dd_pct else 0.0,
        "sharpe": sharpe,
        "sortino": sortino,
        "daily_skew": float(strategy_ret.skew()) if len(strategy_ret) else 0.0,
        "dd_duration": drawdown_duration_days(strategy, curves["date"]),
        "benchmark_corr": corr,
        "benchmark_down_capture": down_capture,
        "profit_factor": pf,
        "win_rate": win_rate,
        "trades": trades,
    }


def write_csvs(config: PitchConfig, curves: pd.DataFrame, strategy_rows: list[dict], benchmark_rows: list[dict]) -> None:
    curves.to_csv(config.out_dir / "equity_curves.csv", index=False)
    with (config.out_dir / "annual_comparison.csv").open("w", newline="") as f:
        fields = [
            "year",
            "strategy_start",
            "strategy_net",
            "strategy_end",
            "strategy_return_pct",
            "strategy_drawdown",
            "strategy_drawdown_pct",
            "benchmark_start",
            "benchmark_net",
            "benchmark_end",
            "benchmark_return_pct",
            "benchmark_drawdown",
            "benchmark_drawdown_pct",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for strategy, benchmark in zip(strategy_rows, benchmark_rows):
            writer.writerow(
                {
                    "year": strategy["year"],
                    "strategy_start": f"{strategy['start']:.2f}",
                    "strategy_net": f"{strategy['net']:.2f}",
                    "strategy_end": f"{strategy['end']:.2f}",
                    "strategy_return_pct": f"{strategy['return_pct']:.4f}",
                    "strategy_drawdown": f"{strategy['dd']:.2f}",
                    "strategy_drawdown_pct": f"{strategy['dd_pct']:.4f}",
                    "benchmark_start": f"{benchmark['start']:.2f}",
                    "benchmark_net": f"{benchmark['net']:.2f}",
                    "benchmark_end": f"{benchmark['end']:.2f}",
                    "benchmark_return_pct": f"{benchmark['return_pct']:.4f}",
                    "benchmark_drawdown": f"{benchmark['dd']:.2f}",
                    "benchmark_drawdown_pct": f"{benchmark['dd_pct']:.4f}",
                }
            )


def write_chart(config: PitchConfig, curves: pd.DataFrame) -> None:
    fig, (ax1, ax2) = plt.subplots(
        2,
        1,
        figsize=(10.5, 7.2),
        gridspec_kw={"height_ratios": [2.3, 1.0]},
        sharex=True,
    )
    ax1.plot(curves["date"], curves["strategy_equity"], label=config.strategy_name, color="#0f766e", linewidth=2.3)
    ax1.plot(
        curves["date"],
        curves["benchmark_equity"],
        label=f"{config.benchmark_name} buy-and-hold",
        color="#1d4ed8",
        linewidth=2.1,
    )
    ax1.axhline(config.start_capital, color="#9ca3af", linewidth=1, linestyle="--")
    ax1.set_title(f"{money(config.start_capital)} Hypothetical Growth: {config.strategy_name} vs {config.benchmark_name}")
    ax1.set_ylabel("Account value")
    ax1.grid(True, alpha=0.25)
    ax1.legend(loc="upper left")
    ax1.yaxis.set_major_formatter(lambda x, pos: f"${x/1000:.0f}k")

    strategy_dd = curves["strategy_equity"] - curves["strategy_equity"].cummax()
    benchmark_dd = curves["benchmark_equity"] - curves["benchmark_equity"].cummax()
    ax2.fill_between(curves["date"], strategy_dd, 0, color="#0f766e", alpha=0.24, label="Strategy drawdown")
    ax2.fill_between(curves["date"], benchmark_dd, 0, color="#1d4ed8", alpha=0.18, label=f"{config.benchmark_name} drawdown")
    ax2.set_ylabel("Drawdown")
    ax2.grid(True, alpha=0.25)
    ax2.yaxis.set_major_formatter(lambda x, pos: f"${x/1000:.0f}k")
    ax2.legend(loc="lower left", ncol=2)

    fig.tight_layout()
    fig.savefig(config.out_dir / config.chart_file, dpi=160)
    plt.close(fig)


def write_pdf(config: PitchConfig, strategy_rows: list[dict], benchmark_rows: list[dict], metrics: dict) -> None:
    strategy_end = config.start_capital + metrics["net"]
    strategy_return = metrics["net"] / config.start_capital * 100.0
    benchmark_end = benchmark_rows[-1]["end"]
    benchmark_net = benchmark_end - config.start_capital
    benchmark_return = benchmark_net / config.start_capital * 100.0
    benchmark_worst_dd_pct = max(r["dd_pct"] for r in benchmark_rows)
    by_benchmark = {r["year"]: r for r in benchmark_rows}
    long_table = len(strategy_rows) > 8

    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor("white")
    fig.text(0.06, 0.955, f"{config.strategy_name} vs {config.benchmark_name}", fontsize=19, weight="bold", color="#111827")
    fig.text(
        0.06,
        0.923,
        f"One-page hypothetical exhibit. {money(config.start_capital)} starting capital for both paths. "
        f"{config.benchmark_name} uses adjusted-close buy-and-hold.",
        fontsize=9.5,
        color="#374151",
    )

    chart = plt.imread(config.out_dir / config.chart_file)
    ax_chart = fig.add_axes([0.055, 0.43, 0.89, 0.45])
    ax_chart.imshow(chart)
    ax_chart.axis("off")

    headline = (
        f"Strategy ending value: {money2(strategy_end)} | Net: {money2(metrics['net'])} | Total return: {pct(strategy_return)}\n"
        f"{config.benchmark_name} ending value: {money2(benchmark_end)} | Net: {money2(benchmark_net)} | Total return: {pct(benchmark_return)}\n"
        f"Strategy max daily DD: {pct(metrics['max_dd_pct'])} | "
        f"Worst annual {config.benchmark_name} daily DD: {pct(benchmark_worst_dd_pct)}\n"
        f"Sharpe/Sortino: {metrics['sharpe']:.2f}/{metrics['sortino']:.2f} | "
        f"CAGR: {pct(metrics['cagr'])} | Calmar: {metrics['calmar']:.2f} | "
        f"{config.benchmark_name} corr/downside capture: "
        f"{metrics['benchmark_corr']:.2f}/{metrics['benchmark_down_capture']:.2f} | PF: {metrics['profit_factor']:.2f}"
    )
    fig.text(
        0.06,
        0.385,
        headline,
        fontsize=10.5,
        color="#111827",
        bbox={"facecolor": "#f3f4f6", "edgecolor": "#d1d5db", "boxstyle": "round,pad=0.45"},
    )

    table_rows = []
    for strategy in strategy_rows:
        benchmark = by_benchmark[strategy["year"]]
        table_rows.append(
            [
                str(strategy["year"]),
                money(strategy["start"]),
                money(strategy["net"]),
                pct(strategy["return_pct"]),
                pct(strategy["dd_pct"]),
                money(benchmark["net"]),
                pct(benchmark["return_pct"]),
                pct(benchmark["dd_pct"]),
            ]
        )
    col_labels = [
        "Year",
        "Start",
        "Strategy Net",
        "Strategy Ret.",
        "Strategy DD",
        f"{config.benchmark_name} Net",
        f"{config.benchmark_name} Ret.",
        f"{config.benchmark_name} DD",
    ]

    if long_table:
        fig.text(
            0.06,
            0.205,
            "Full annual return table appears on page 2 so the full history remains readable.",
            fontsize=10.0,
            color="#374151",
            bbox={"facecolor": "#f9fafb", "edgecolor": "#d1d5db", "boxstyle": "round,pad=0.35"},
        )
    else:
        ax_table = fig.add_axes([0.055, 0.12, 0.89, 0.22])
        ax_table.axis("off")
        table = ax_table.table(
            cellText=table_rows,
            colLabels=col_labels,
            loc="center",
            cellLoc="right",
            colLoc="right",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(8.5)
        table.scale(1, 1.22)
        for (row, _), cell in table.get_celld().items():
            cell.set_edgecolor("#d1d5db")
            if row == 0:
                cell.set_facecolor("#e5e7eb")
                cell.set_text_props(weight="bold", color="#111827")

    caveat = (
        "This is hypothetical/backtested performance, not audited live performance. "
        "This sleeve is intended as a futures diversifier, not a replacement for equity exposure. "
        "Live deployment still requires tick/order-sequence validation, broker-paper parity, and counsel-reviewed disclosures."
    )
    fig.text(0.06, 0.055, "\n".join(textwrap.wrap(caveat, width=150)), fontsize=8.8, color="#374151")

    pdf_path = config.out_dir / "ONE_PAGE_PITCH.pdf"
    if not long_table:
        fig.savefig(pdf_path, format="pdf", bbox_inches="tight")
        plt.close(fig)
        return

    with PdfPages(pdf_path) as pdf:
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        fig2 = plt.figure(figsize=(11, 8.5))
        fig2.patch.set_facecolor("white")
        fig2.text(0.055, 0.955, f"{config.strategy_name} - Full Annual Table", fontsize=17, weight="bold", color="#111827")
        fig2.text(
            0.055,
            0.925,
            f"Hypothetical/backtested performance. {money(config.start_capital)} starting capital; "
            f"{config.benchmark_name} adjusted-close buy-and-hold.",
            fontsize=9.2,
            color="#374151",
        )
        ax_table = fig2.add_axes([0.035, 0.075, 0.93, 0.81])
        ax_table.axis("off")
        table = ax_table.table(
            cellText=table_rows,
            colLabels=col_labels,
            loc="center",
            cellLoc="right",
            colLoc="right",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(7.2)
        table.scale(1, 1.05)
        for (row, _), cell in table.get_celld().items():
            cell.set_edgecolor("#d1d5db")
            if row == 0:
                cell.set_facecolor("#e5e7eb")
                cell.set_text_props(weight="bold", color="#111827")
        pdf.savefig(fig2, bbox_inches="tight")
        plt.close(fig2)


def write_markdown(config: PitchConfig, strategy_rows: list[dict], benchmark_rows: list[dict], metrics: dict) -> None:
    strategy_end = config.start_capital + metrics["net"]
    strategy_return = metrics["net"] / config.start_capital * 100.0
    benchmark_end = benchmark_rows[-1]["end"]
    benchmark_net = benchmark_end - config.start_capital
    benchmark_return = benchmark_net / config.start_capital * 100.0
    benchmark_worst_dd_pct = max(r["dd_pct"] for r in benchmark_rows)
    by_benchmark = {r["year"]: r for r in benchmark_rows}

    lines = [
        f"# {config.strategy_name} vs {config.benchmark_name}",
        "",
        (
            f"**One-page hypothetical exhibit.** Starting capital is **{money(config.start_capital)}** for both paths. "
            f"The managed intraday sleeve uses a rules-based futures replay; {config.benchmark_name} uses adjusted-close "
            "buy-and-hold over the same available window."
        ),
        "",
        f"![{config.strategy_name} vs {config.benchmark_name}]({config.chart_file})",
        "",
        "## Headline",
        "",
        f"- **{config.strategy_name}:** {money2(strategy_end)} ending value, {money2(metrics['net'])} net, **{pct(strategy_return)} total return**.",
        f"- **{config.benchmark_name} buy-and-hold:** {money2(benchmark_end)} ending value, {money2(benchmark_net)} net, **{pct(benchmark_return)} total return**.",
        f"- Strategy max daily drawdown on this account path: **{pct(metrics['max_dd_pct'])}**.",
        f"- Worst annual {config.benchmark_name} daily drawdown as a share of that year's starting balance: **{pct(benchmark_worst_dd_pct)}**.",
        "",
        "## Institutional Metrics",
        "",
        "| Metric | Managed intraday sleeve |",
        "|---|---:|",
        f"| Pitch window | {metrics['window']} |",
        f"| Account-path CAGR | {pct(metrics['cagr'])} |",
        f"| Sharpe / Sortino | {metrics['sharpe']:.2f} / {metrics['sortino']:.2f} |",
        f"| Calmar on account drawdown | {metrics['calmar']:.2f} |",
        f"| Net / modeled stress DD | {metrics['net_over_stress']:.2f} |",
        f"| Max drawdown duration | {metrics['dd_duration']} days |",
        f"| Daily skew | {metrics['daily_skew']:.2f} |",
        f"| {config.benchmark_name} corr / downside capture | {metrics['benchmark_corr']:.2f} / {metrics['benchmark_down_capture']:.2f} |",
        f"| Profit factor / campaign win rate | {metrics['profit_factor']:.2f} / {metrics['win_rate']:.1f}% |",
        f"| Campaigns | {metrics['trades']:,} |",
        f"| Modeled stress DD | {money(metrics['stress_dd'])} |",
        "",
        "## Annual Table",
        "",
        (
            f"| Year | Strategy Start | Strategy Net | Strategy Return | Strategy DD % | "
            f"{config.benchmark_name} Start | {config.benchmark_name} Net | {config.benchmark_name} Return | "
            f"{config.benchmark_name} DD % |"
        ),
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for strategy in strategy_rows:
        benchmark = by_benchmark[strategy["year"]]
        lines.append(
            "| "
            f"{strategy['year']} | {money(strategy['start'])} | {money(strategy['net'])} | **{pct(strategy['return_pct'])}** | "
            f"{pct(strategy['dd_pct'])} | {money(benchmark['start'])} | {money(benchmark['net'])} | "
            f"**{pct(benchmark['return_pct'])}** | {pct(benchmark['dd_pct'])} |"
        )
    lines.extend(
        [
            "",
            "## Read",
            "",
            (
                f"This is positioned as a **{config.read_label}**. It is not the flagship gated product; "
                "it is a complementary sleeve that may be easier to explain once live broker-paper parity is proven."
            ),
            "",
            (
                "**Important caveat:** this remains hypothetical/backtested performance. The strategy still needs "
                "tick/order-sequence proof and broker-paper parity before live capital decisions."
            ),
            "",
            "## Internal Sources",
            "",
            f"- Equity curve: `{config.equity_path.relative_to(ROOT)}`",
            f"- Campaign fills: `{config.unit_path.relative_to(ROOT)}`",
            f"- Summary source: `{config.source_summary.relative_to(ROOT)}`",
        ]
    )
    (config.out_dir / "ONE_PAGE_PITCH.md").write_text("\n".join(lines) + "\n")


def build(config: PitchConfig) -> None:
    config.out_dir.mkdir(parents=True, exist_ok=True)
    strategy_daily = load_strategy_daily(config)
    benchmark_daily = load_benchmark_daily(config, strategy_daily["date"].iloc[0], strategy_daily["date"].iloc[-1])
    curves = pd.merge(strategy_daily, benchmark_daily, on="date", how="inner").sort_values("date").reset_index(drop=True)
    curves = add_start_anchor(config, curves)
    campaigns = load_unit_campaigns(config)
    strategy_rows, benchmark_rows = build_annual_rows(curves)
    metrics = compute_metrics(config, curves, campaigns)
    write_csvs(config, curves, strategy_rows, benchmark_rows)
    write_chart(config, curves)
    write_markdown(config, strategy_rows, benchmark_rows, metrics)
    write_pdf(config, strategy_rows, benchmark_rows, metrics)


def main() -> None:
    for config in CONFIGS:
        build(config)


if __name__ == "__main__":
    main()
