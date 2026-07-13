#!/usr/bin/env python3
"""Build one-page ES and NQ managed intraday pitch exhibits."""
from __future__ import annotations

import csv
import textwrap
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
METRICS_PATH = ROOT / "live/state/institutional_strategy_metrics/metrics.csv"


@dataclass(frozen=True)
class PitchConfig:
    out_dir: Path
    strategy_name: str
    instrument: str
    start_capital: float
    yearly_path: Path
    equity_path: Path
    benchmark_name: str
    benchmark_daily: Path
    chart_file: str
    pdf_file: str = "ONE_PAGE_PITCH.pdf"


CONFIGS = [
    PitchConfig(
        out_dir=ROOT / "live/state/sp_managed_intraday_diversifier_pitch",
        strategy_name="S&P Managed Intraday Diversifier Strategy",
        instrument="ES",
        start_capital=100_000.0,
        yearly_path=ROOT
        / "live/state/es_v2b_prior_opposed_stpmc_broker_like/robustness_audit/yearly_breakdown.csv",
        equity_path=ROOT
        / "live/state/es_v2b_prior_opposed_stpmc_broker_like/states/"
        / "es_v2b_prior_opposed_stpmc_only_S_1_1_3/equity_curve.csv",
        benchmark_name="SPY",
        benchmark_daily=ROOT / "data/benchmarks/SPY_2021-03-04_2026-03-06_yahoo_daily.csv",
        chart_file="sp_managed_intraday_diversifier_vs_spy_100k.png",
    ),
    PitchConfig(
        out_dir=ROOT / "live/state/nasdaq_managed_intraday_pitch",
        strategy_name="Nasdaq Managed Intraday Strategy",
        instrument="NQ",
        start_capital=250_000.0,
        yearly_path=ROOT
        / "live/state/nq_v2b_prior_opposed_stpmc_broker_like/robustness_audit/yearly_breakdown.csv",
        equity_path=ROOT
        / "live/state/nq_v2b_prior_opposed_stpmc_broker_like/states/"
        / "nq_v2b_prior_opposed_stpmc_only_S_1_1_3/equity_curve.csv",
        benchmark_name="QQQ",
        benchmark_daily=ROOT / "data/benchmarks/QQQ_2021-03-04_2026-03-06_yahoo_daily.csv",
        chart_file="nasdaq_managed_intraday_vs_qqq_250k.png",
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


def build_strategy_rows(config: PitchConfig) -> tuple[list[dict], pd.DataFrame]:
    rows: list[dict] = []
    equity_points = []
    balance = config.start_capital

    with config.yearly_path.open() as f:
        for row in csv.DictReader(f):
            year = int(row["year"])
            start = balance
            net = float(row["net_usd"])
            closed_dd = float(row["closed_dd_usd"])
            end = start + net
            rows.append(
                {
                    "year": year,
                    "start": start,
                    "net": net,
                    "end": end,
                    "return_pct": net / start * 100.0,
                    "closed_dd": closed_dd,
                    "closed_dd_pct": abs(closed_dd) / start * 100.0,
                    "trades": int(row["trades"]),
                    "win_rate_pct": float(row["win_rate_pct"]),
                    "profit_factor": float(row["profit_factor"]),
                }
            )
            equity_points.append({"date": f"{year}-12-31", "equity": end})
            balance = end

    equity = pd.DataFrame(equity_points)
    equity["date"] = pd.to_datetime(equity["date"])
    return rows, equity


def build_benchmark_rows(config: PitchConfig) -> tuple[list[dict], pd.DataFrame]:
    daily = pd.read_csv(config.benchmark_daily, parse_dates=["date"])
    daily = daily.sort_values("date")
    first_adj = float(daily.iloc[0]["adj_close"])
    daily["equity"] = config.start_capital * daily["adj_close"].astype(float) / first_adj

    rows: list[dict] = []
    prev_end = config.start_capital
    for year, group in daily.groupby(daily["date"].dt.year):
        start = prev_end
        end = float(group.iloc[-1]["equity"])
        net = end - start
        dd = max_drawdown(group["equity"])
        rows.append(
            {
                "year": int(year),
                "start": start,
                "net": net,
                "end": end,
                "return_pct": net / start * 100.0,
                "closed_dd": dd,
                "closed_dd_pct": abs(dd) / start * 100.0,
            }
        )
        prev_end = end

    return rows, daily[["date", "equity"]].copy()


def write_csv(config: PitchConfig, strategy_rows: list[dict], benchmark_rows: list[dict]) -> None:
    years = sorted({r["year"] for r in strategy_rows} | {r["year"] for r in benchmark_rows})
    by_strategy = {r["year"]: r for r in strategy_rows}
    by_benchmark = {r["year"]: r for r in benchmark_rows}
    path = config.out_dir / "annual_comparison.csv"
    with path.open("w", newline="") as f:
        fieldnames = [
            "year",
            "strategy_start",
            "strategy_net",
            "strategy_end",
            "strategy_return_pct",
            "strategy_closed_dd",
            "strategy_closed_dd_pct",
            "benchmark_start",
            "benchmark_net",
            "benchmark_end",
            "benchmark_return_pct",
            "benchmark_max_daily_dd",
            "benchmark_max_daily_dd_pct",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for year in years:
            s = by_strategy[year]
            b = by_benchmark[year]
            writer.writerow(
                {
                    "year": year,
                    "strategy_start": f"{s['start']:.2f}",
                    "strategy_net": f"{s['net']:.2f}",
                    "strategy_end": f"{s['end']:.2f}",
                    "strategy_return_pct": f"{s['return_pct']:.4f}",
                    "strategy_closed_dd": f"{s['closed_dd']:.2f}",
                    "strategy_closed_dd_pct": f"{s['closed_dd_pct']:.4f}",
                    "benchmark_start": f"{b['start']:.2f}",
                    "benchmark_net": f"{b['net']:.2f}",
                    "benchmark_end": f"{b['end']:.2f}",
                    "benchmark_return_pct": f"{b['return_pct']:.4f}",
                    "benchmark_max_daily_dd": f"{b['closed_dd']:.2f}",
                    "benchmark_max_daily_dd_pct": f"{b['closed_dd_pct']:.4f}",
                }
            )


def write_equity_csv(config: PitchConfig, benchmark_equity: pd.DataFrame) -> None:
    strategy_daily = pd.read_csv(config.equity_path)
    strategy_daily["ts"] = pd.to_datetime(strategy_daily["ts"], utc=True)
    strategy_daily["date"] = strategy_daily["ts"].dt.date
    strategy_daily = strategy_daily.groupby("date", as_index=False).tail(1)
    strategy_daily["date"] = pd.to_datetime(strategy_daily["date"])
    strategy_daily["equity"] = config.start_capital + strategy_daily["close_equity_usd"].astype(float)

    out = pd.merge(
        strategy_daily[["date", "equity"]].rename(columns={"equity": "strategy_equity"}),
        benchmark_equity.rename(columns={"equity": "benchmark_equity"}),
        on="date",
        how="outer",
    ).sort_values("date")
    out.to_csv(config.out_dir / "equity_curves.csv", index=False)


def write_chart(config: PitchConfig) -> None:
    curves = pd.read_csv(config.out_dir / "equity_curves.csv", parse_dates=["date"])
    curves = curves.sort_values("date").ffill()

    fig, (ax1, ax2) = plt.subplots(
        2,
        1,
        figsize=(10.5, 7.2),
        gridspec_kw={"height_ratios": [2.3, 1.0]},
        sharex=True,
    )
    ax1.plot(
        curves["date"],
        curves["strategy_equity"],
        label=config.strategy_name,
        color="#0f766e",
        linewidth=2.3,
    )
    ax1.plot(
        curves["date"],
        curves["benchmark_equity"],
        label=f"{config.benchmark_name} buy-and-hold",
        color="#1d4ed8",
        linewidth=2.1,
    )
    ax1.axhline(config.start_capital, color="#9ca3af", linewidth=1, linestyle="--")
    ax1.set_title(
        f"{money(config.start_capital)} Hypothetical Growth: "
        f"{config.strategy_name} vs {config.benchmark_name}"
    )
    ax1.set_ylabel("Account value")
    ax1.grid(True, alpha=0.25)
    ax1.legend(loc="upper left")
    ax1.yaxis.set_major_formatter(lambda x, pos: f"${x/1000:.0f}k")

    strategy_dd = curves["strategy_equity"] - curves["strategy_equity"].cummax()
    benchmark_dd = curves["benchmark_equity"] - curves["benchmark_equity"].cummax()
    ax2.fill_between(curves["date"], strategy_dd, 0, color="#0f766e", alpha=0.24, label="Strategy drawdown")
    ax2.fill_between(
        curves["date"],
        benchmark_dd,
        0,
        color="#1d4ed8",
        alpha=0.18,
        label=f"{config.benchmark_name} drawdown",
    )
    ax2.set_ylabel("Drawdown")
    ax2.grid(True, alpha=0.25)
    ax2.yaxis.set_major_formatter(lambda x, pos: f"${x/1000:.0f}k")
    ax2.legend(loc="lower left", ncol=2)

    fig.tight_layout()
    fig.savefig(config.out_dir / config.chart_file, dpi=160)
    plt.close(fig)


def load_institutional_metrics(config: PitchConfig) -> dict:
    metrics = {}
    if METRICS_PATH.exists():
        df = pd.read_csv(METRICS_PATH)
        rows = df[df["name"].astype(str).str.contains(f"{config.instrument} prior-opposed", regex=False)]
        if not rows.empty:
            row = rows.iloc[0]
            metrics.update(
                {
                    "window": f"{row['start']} to {row['end']}",
                    "sharpe": float(row["sharpe_daily"]),
                    "sortino": float(row["sortino_daily"]),
                    "calmar_stress": float(row["calmar_mar"]),
                    "dd_duration": int(float(row["max_drawdown_duration_days"])),
                    "daily_skew": float(row["daily_skew"]),
                    "qqq_corr": float(row["qqq_daily_corr"]),
                    "qqq_down_capture": float(row["qqq_downside_capture"]),
                    "profit_factor": float(row["profit_factor"]),
                    "win_rate": float(row["win_rate_pct"]),
                    "stress_dd": float(row["intrabar_stress_dd_usd"]),
                    "closed_dd": float(row["closed_dd_usd"]),
                }
            )

    curves_path = config.out_dir / "equity_curves.csv"
    if curves_path.exists():
        curves = pd.read_csv(curves_path, parse_dates=["date"]).sort_values("date").ffill()
        if not curves.empty:
            start = float(curves["strategy_equity"].iloc[0])
            end = float(curves["strategy_equity"].iloc[-1])
            years = (curves["date"].iloc[-1] - curves["date"].iloc[0]).days / 365.25
            if start > 0 and years > 0:
                metrics["path_cagr"] = ((end / start) ** (1.0 / years) - 1.0) * 100.0
            curves["strategy_ret"] = curves["strategy_equity"].pct_change().fillna(0.0)
            curves["benchmark_ret"] = curves["benchmark_equity"].pct_change().fillna(0.0)
            metrics["benchmark_corr"] = float(curves["strategy_ret"].corr(curves["benchmark_ret"]))
            down = curves[curves["benchmark_ret"] < 0]
            if not down.empty and float(down["benchmark_ret"].mean()) != 0.0:
                metrics["benchmark_down_capture"] = float(
                    down["strategy_ret"].mean() / down["benchmark_ret"].mean()
                )
    return metrics


def benchmark_corr_text(config: PitchConfig, inst: dict) -> str:
    if config.benchmark_name.upper() == "QQQ":
        return f"{inst.get('qqq_corr', 0.0):.2f}/{inst.get('qqq_down_capture', 0.0):.2f}"
    return f"{inst.get('benchmark_corr', 0.0):.2f}/{inst.get('benchmark_down_capture', 0.0):.2f}"


def write_pdf(config: PitchConfig, strategy_rows: list[dict], benchmark_rows: list[dict]) -> None:
    inst = load_institutional_metrics(config)
    strategy_end = strategy_rows[-1]["end"]
    benchmark_end = benchmark_rows[-1]["end"]
    strategy_net = strategy_end - config.start_capital
    benchmark_net = benchmark_end - config.start_capital
    strategy_total_return = strategy_net / config.start_capital * 100.0
    benchmark_total_return = benchmark_net / config.start_capital * 100.0
    strategy_worst_dd_pct = max(r["closed_dd_pct"] for r in strategy_rows)
    benchmark_worst_dd_pct = max(r["closed_dd_pct"] for r in benchmark_rows)
    by_benchmark = {r["year"]: r for r in benchmark_rows}

    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor("white")
    fig.text(
        0.06,
        0.955,
        f"{config.strategy_name} vs {config.benchmark_name}",
        fontsize=19,
        weight="bold",
        color="#111827",
    )
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
        f"Strategy ending value: {money2(strategy_end)} | Net: {money2(strategy_net)} | "
        f"Total return: {pct(strategy_total_return)}\n"
        f"{config.benchmark_name} ending value: {money2(benchmark_end)} | Net: {money2(benchmark_net)} | "
        f"Total return: {pct(benchmark_total_return)}\n"
        f"Worst annual strategy closed DD: {pct(strategy_worst_dd_pct)} of starting balance | "
        f"Worst annual {config.benchmark_name} daily DD: {pct(benchmark_worst_dd_pct)}\n"
        f"Sharpe/Sortino: {inst.get('sharpe', 0.0):.2f}/{inst.get('sortino', 0.0):.2f} | "
        f"{money(config.start_capital)}-path CAGR: {pct(inst.get('path_cagr', 0.0))} | "
        f"Calmar on modeled stress: {inst.get('calmar_stress', 0.0):.2f} | "
        f"{config.benchmark_name} corr/downside capture: {benchmark_corr_text(config, inst)} | "
        f"PF: {inst.get('profit_factor', 0.0):.2f}"
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
                pct(strategy["closed_dd_pct"]),
                money(benchmark["net"]),
                pct(benchmark["return_pct"]),
                pct(benchmark["closed_dd_pct"]),
            ]
        )
    ax_table = fig.add_axes([0.055, 0.12, 0.89, 0.22])
    ax_table.axis("off")
    table = ax_table.table(
        cellText=table_rows,
        colLabels=[
            "Year",
            "Start",
            "Strategy Net",
            "Strategy Ret.",
            "Strategy DD",
            f"{config.benchmark_name} Net",
            f"{config.benchmark_name} Ret.",
            f"{config.benchmark_name} DD",
        ],
        loc="center",
        cellLoc="right",
        colLoc="right",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    table.scale(1, 1.22)
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor("#d1d5db")
        if row == 0:
            cell.set_facecolor("#e5e7eb")
            cell.set_text_props(weight="bold", color="#111827")

    caveat = (
        "This is hypothetical/backtested performance, not audited live performance. "
        "The strategy is intended as a futures diversifier, not a replacement for equity exposure. "
        "Live deployment still requires tick/order-sequence validation, broker-paper parity, and counsel-reviewed disclosures."
    )
    fig.text(0.06, 0.055, "\n".join(textwrap.wrap(caveat, width=150)), fontsize=8.8, color="#374151")
    fig.savefig(config.out_dir / config.pdf_file, format="pdf", bbox_inches="tight")
    plt.close(fig)


def write_markdown(config: PitchConfig, strategy_rows: list[dict], benchmark_rows: list[dict]) -> None:
    inst = load_institutional_metrics(config)
    strategy_end = strategy_rows[-1]["end"]
    benchmark_end = benchmark_rows[-1]["end"]
    strategy_net = strategy_end - config.start_capital
    benchmark_net = benchmark_end - config.start_capital
    strategy_total_return = strategy_net / config.start_capital * 100.0
    benchmark_total_return = benchmark_net / config.start_capital * 100.0
    strategy_worst_dd_pct = max(r["closed_dd_pct"] for r in strategy_rows)
    benchmark_worst_dd_pct = max(r["closed_dd_pct"] for r in benchmark_rows)
    by_benchmark = {r["year"]: r for r in benchmark_rows}
    calmar_closed = inst.get("path_cagr", 0.0) / strategy_worst_dd_pct if strategy_worst_dd_pct else 0.0

    lines = [
        f"# {config.strategy_name} vs {config.benchmark_name}",
        "",
        (
            f"**One-page hypothetical exhibit.** Starting capital is **{money(config.start_capital)}** for both "
            f"paths. The managed intraday strategy uses a rules-based futures replay; "
            f"{config.benchmark_name} uses adjusted-close buy-and-hold over the same available window."
        ),
        "",
        f"![{config.strategy_name} vs {config.benchmark_name}]({config.chart_file})",
        "",
        "## Headline",
        "",
        (
            f"- **{config.strategy_name}:** {money2(strategy_end)} ending value, {money2(strategy_net)} net, "
            f"**{pct(strategy_total_return)} total return**."
        ),
        (
            f"- **{config.benchmark_name} buy-and-hold:** {money2(benchmark_end)} ending value, "
            f"{money2(benchmark_net)} net, **{pct(benchmark_total_return)} total return**."
        ),
        f"- Worst annual strategy closed DD as a share of that year's starting balance: **{pct(strategy_worst_dd_pct)}**.",
        (
            f"- Worst annual {config.benchmark_name} daily drawdown as a share of that year's starting balance: "
            f"**{pct(benchmark_worst_dd_pct)}**."
        ),
        "",
        "## Institutional Metrics",
        "",
        (
            f"The headline above uses the simple **{money(config.start_capital)} starting-account path**. "
            "The institutional statistics below use the same hypothetical replay's daily return path and stress accounting."
        ),
        "",
        "| Metric | Managed intraday strategy |",
        "|---|---:|",
        f"| Backtest window | {inst.get('window', 'n/a')} |",
        f"| {money(config.start_capital)}-path CAGR | {pct(inst.get('path_cagr', 0.0))} |",
        f"| Sharpe / Sortino | {inst.get('sharpe', 0.0):.2f} / {inst.get('sortino', 0.0):.2f} |",
        f"| Calmar / MAR on modeled stress | {inst.get('calmar_stress', 0.0):.2f} |",
        f"| Calmar on worst annual closed DD | {calmar_closed:.2f} |",
        f"| Max drawdown duration | {inst.get('dd_duration', 0)} days |",
        f"| Daily skew | {inst.get('daily_skew', 0.0):.2f} |",
        f"| QQQ corr / downside capture | {inst.get('qqq_corr', 0.0):.2f} / {inst.get('qqq_down_capture', 0.0):.2f} |",
        f"| Profit factor / win rate | {inst.get('profit_factor', 0.0):.2f} / {inst.get('win_rate', 0.0):.1f}% |",
        (
            f"| Modeled intrabar stress / closed DD | {money(inst.get('stress_dd', 0.0))} / "
            f"{money(inst.get('closed_dd', 0.0))} |"
        ),
        "",
        "## Annual Table",
        "",
        (
            f"| Year | Strategy Start | Strategy Net | Strategy Return | Strategy Closed DD | Strategy DD % | "
            f"{config.benchmark_name} Start | {config.benchmark_name} Net | {config.benchmark_name} Return | "
            f"{config.benchmark_name} DD % |"
        ),
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    if config.benchmark_name.upper() != "QQQ":
        insertion_idx = lines.index(
            f"| Profit factor / win rate | {inst.get('profit_factor', 0.0):.2f} / {inst.get('win_rate', 0.0):.1f}% |"
        )
        lines.insert(
            insertion_idx,
            (
                f"| {config.benchmark_name} corr / downside capture | "
                f"{inst.get('benchmark_corr', 0.0):.2f} / {inst.get('benchmark_down_capture', 0.0):.2f} |"
            ),
        )
    for strategy in strategy_rows:
        benchmark = by_benchmark[strategy["year"]]
        lines.append(
            "| "
            f"{strategy['year']} | {money(strategy['start'])} | {money(strategy['net'])} | "
            f"**{pct(strategy['return_pct'])}** | {money(strategy['closed_dd'])} | "
            f"{pct(strategy['closed_dd_pct'])} | {money(benchmark['start'])} | "
            f"{money(benchmark['net'])} | **{pct(benchmark['return_pct'])}** | "
            f"{pct(benchmark['closed_dd_pct'])} |"
        )

    lines.extend(
        [
            "",
            "## Read",
            "",
            (
                f"This strategy path is not a replacement for passive {config.benchmark_name} exposure; "
                "it is a futures sleeve designed to behave differently from a buy-and-hold equity index ETF. "
                "The useful diligence question is whether the live implementation can preserve enough of the "
                "replay's return distribution after real broker routing, sequence checks, fees, and slippage."
            ),
            "",
            (
                "**Important caveat:** this remains hypothetical/backtested performance. The strategy still needs "
                "tick/order-sequence proof and broker-paper parity before live capital decisions."
            ),
        ]
    )
    (config.out_dir / "ONE_PAGE_PITCH.md").write_text("\n".join(lines) + "\n")


def build(config: PitchConfig) -> None:
    config.out_dir.mkdir(parents=True, exist_ok=True)
    strategy_rows, _ = build_strategy_rows(config)
    benchmark_rows, benchmark_equity = build_benchmark_rows(config)
    write_csv(config, strategy_rows, benchmark_rows)
    write_equity_csv(config, benchmark_equity)
    write_chart(config)
    write_markdown(config, strategy_rows, benchmark_rows)
    write_pdf(config, strategy_rows, benchmark_rows)


def main() -> None:
    for config in CONFIGS:
        build(config)


if __name__ == "__main__":
    main()
