#!/usr/bin/env python3
"""Build a one-page Nasdaq intraday mini vs QQQ pitch exhibit."""
from __future__ import annotations

import csv
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "live/state/nasdaq_intraday_mini_pitch"
START_CAPITAL = 30_000.0
STRATEGY_NAME = "Nasdaq Managed Intraday Mini Strategy"
BENCHMARK_NAME = "QQQ buy-and-hold"
CHART_FILE = "nasdaq_intraday_mini_vs_qqq_30k.png"
PDF_FILE = "ONE_PAGE_PITCH.pdf"
YEARLY = (
    ROOT
    / "live/state/mnq_v2b_prior_opposed_stpmc_broker_like/robustness_audit/yearly_breakdown.csv"
)
STRATEGY_EQUITY = (
    ROOT
    / "live/state/mnq_v2b_prior_opposed_stpmc_broker_like/states/"
    / "mnq_v2b_prior_opposed_stpmc_only_S_1_1_3/equity_curve.csv"
)
QQQ_DAILY = ROOT / "data/benchmarks/QQQ_2021-03-04_2026-03-06_yahoo_daily.csv"


def money(value: float) -> str:
    return f"${value:,.0f}"


def money2(value: float) -> str:
    return f"${value:,.2f}"


def pct(value: float) -> str:
    return f"{value:.1f}%"


def max_drawdown(series: pd.Series) -> float:
    return float((series - series.cummax()).min()) if not series.empty else 0.0


def build_strategy_rows() -> list[dict]:
    rows: list[dict] = []
    balance = START_CAPITAL

    with YEARLY.open() as f:
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
            balance = end

    return rows


def build_qqq_rows() -> tuple[list[dict], pd.DataFrame]:
    daily = pd.read_csv(QQQ_DAILY, parse_dates=["date"])
    daily = daily.sort_values("date")
    first_adj = float(daily.iloc[0]["adj_close"])
    daily["equity"] = START_CAPITAL * daily["adj_close"].astype(float) / first_adj

    rows: list[dict] = []
    prev_end = START_CAPITAL
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


def write_csv(strategy_rows: list[dict], qqq_rows: list[dict]) -> None:
    years = sorted({r["year"] for r in strategy_rows} | {r["year"] for r in qqq_rows})
    by_strategy = {r["year"]: r for r in strategy_rows}
    by_qqq = {r["year"]: r for r in qqq_rows}
    path = OUT_DIR / "annual_comparison.csv"
    with path.open("w", newline="") as f:
        fieldnames = [
            "year",
            "strategy_start",
            "strategy_net",
            "strategy_end",
            "strategy_return_pct",
            "strategy_closed_dd",
            "strategy_closed_dd_pct",
            "qqq_start",
            "qqq_net",
            "qqq_end",
            "qqq_return_pct",
            "qqq_max_daily_dd",
            "qqq_max_daily_dd_pct",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for year in years:
            s = by_strategy[year]
            q = by_qqq[year]
            writer.writerow(
                {
                    "year": year,
                    "strategy_start": f"{s['start']:.2f}",
                    "strategy_net": f"{s['net']:.2f}",
                    "strategy_end": f"{s['end']:.2f}",
                    "strategy_return_pct": f"{s['return_pct']:.4f}",
                    "strategy_closed_dd": f"{s['closed_dd']:.2f}",
                    "strategy_closed_dd_pct": f"{s['closed_dd_pct']:.4f}",
                    "qqq_start": f"{q['start']:.2f}",
                    "qqq_net": f"{q['net']:.2f}",
                    "qqq_end": f"{q['end']:.2f}",
                    "qqq_return_pct": f"{q['return_pct']:.4f}",
                    "qqq_max_daily_dd": f"{q['closed_dd']:.2f}",
                    "qqq_max_daily_dd_pct": f"{q['closed_dd_pct']:.4f}",
                }
            )


def write_equity_csv(qqq_equity: pd.DataFrame) -> None:
    strategy_daily = pd.read_csv(STRATEGY_EQUITY)
    strategy_daily["ts"] = pd.to_datetime(strategy_daily["ts"], utc=True)
    strategy_daily["date"] = strategy_daily["ts"].dt.date
    strategy_daily = strategy_daily.groupby("date", as_index=False).tail(1)
    strategy_daily["date"] = pd.to_datetime(strategy_daily["date"])
    strategy_daily["equity"] = START_CAPITAL + strategy_daily["close_equity_usd"].astype(float)
    out = pd.merge(
        strategy_daily[["date", "equity"]].rename(columns={"equity": "strategy_equity"}),
        qqq_equity.rename(columns={"equity": "qqq_equity"}),
        on="date",
        how="outer",
    ).sort_values("date")
    out.to_csv(OUT_DIR / "equity_curves.csv", index=False)


def write_chart() -> None:
    curves = pd.read_csv(OUT_DIR / "equity_curves.csv", parse_dates=["date"])
    curves = curves.sort_values("date").ffill()

    fig, (ax1, ax2) = plt.subplots(
        2,
        1,
        figsize=(10.5, 7.2),
        gridspec_kw={"height_ratios": [2.3, 1.0]},
        sharex=True,
    )
    ax1.plot(curves["date"], curves["strategy_equity"], label=STRATEGY_NAME, color="#0f766e", linewidth=2.3)
    ax1.plot(curves["date"], curves["qqq_equity"], label=BENCHMARK_NAME, color="#1d4ed8", linewidth=2.1)
    ax1.axhline(START_CAPITAL, color="#9ca3af", linewidth=1, linestyle="--")
    ax1.set_title(f"$30,000 Hypothetical Growth: {STRATEGY_NAME} vs QQQ")
    ax1.set_ylabel("Account value")
    ax1.grid(True, alpha=0.25)
    ax1.legend(loc="upper left")
    ax1.yaxis.set_major_formatter(lambda x, pos: f"${x/1000:.0f}k")

    strategy_dd = curves["strategy_equity"] - curves["strategy_equity"].cummax()
    qqq_dd = curves["qqq_equity"] - curves["qqq_equity"].cummax()
    ax2.fill_between(curves["date"], strategy_dd, 0, color="#0f766e", alpha=0.24, label="Strategy drawdown")
    ax2.fill_between(curves["date"], qqq_dd, 0, color="#1d4ed8", alpha=0.18, label="QQQ drawdown")
    ax2.set_ylabel("Drawdown")
    ax2.grid(True, alpha=0.25)
    ax2.yaxis.set_major_formatter(lambda x, pos: f"${x/1000:.0f}k")
    ax2.legend(loc="lower left", ncol=2)

    fig.tight_layout()
    fig.savefig(OUT_DIR / CHART_FILE, dpi=160)
    plt.close(fig)


def write_pdf(strategy_rows: list[dict], qqq_rows: list[dict]) -> None:
    strategy_end = strategy_rows[-1]["end"]
    qqq_end = qqq_rows[-1]["end"]
    strategy_net = strategy_end - START_CAPITAL
    qqq_net = qqq_end - START_CAPITAL
    strategy_total_return = strategy_net / START_CAPITAL * 100.0
    qqq_total_return = qqq_net / START_CAPITAL * 100.0
    strategy_worst_dd_pct = max(r["closed_dd_pct"] for r in strategy_rows)
    qqq_worst_dd_pct = max(r["closed_dd_pct"] for r in qqq_rows)
    by_qqq = {r["year"]: r for r in qqq_rows}

    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor("white")
    fig.text(0.06, 0.955, f"{STRATEGY_NAME} vs QQQ", fontsize=19, weight="bold", color="#111827")
    fig.text(
        0.06,
        0.923,
        "One-page hypothetical exhibit. $30,000 starting capital for both paths. QQQ uses adjusted-close buy-and-hold.",
        fontsize=9.5,
        color="#374151",
    )

    chart = plt.imread(OUT_DIR / CHART_FILE)
    ax_chart = fig.add_axes([0.055, 0.43, 0.89, 0.45])
    ax_chart.imshow(chart)
    ax_chart.axis("off")

    headline = (
        f"Strategy ending value: {money2(strategy_end)} | Net: {money2(strategy_net)} | Total return: {pct(strategy_total_return)}\n"
        f"QQQ ending value: {money2(qqq_end)} | Net: {money2(qqq_net)} | Total return: {pct(qqq_total_return)}\n"
        f"Worst annual strategy closed DD: {pct(strategy_worst_dd_pct)} of starting balance | "
        f"Worst annual QQQ daily DD: {pct(qqq_worst_dd_pct)}"
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
    for s in strategy_rows:
        q = by_qqq[s["year"]]
        table_rows.append(
            [
                str(s["year"]),
                money(s["start"]),
                money(s["net"]),
                pct(s["return_pct"]),
                pct(s["closed_dd_pct"]),
                money(q["net"]),
                pct(q["return_pct"]),
                pct(q["closed_dd_pct"]),
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
            "QQQ Net",
            "QQQ Ret.",
            "QQQ DD",
        ],
        loc="center",
        cellLoc="right",
        colLoc="right",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    table.scale(1, 1.22)
    for (row, _col), cell in table.get_celld().items():
        cell.set_edgecolor("#d1d5db")
        if row == 0:
            cell.set_facecolor("#e5e7eb")
            cell.set_text_props(weight="bold", color="#111827")

    caveat = (
        "This is hypothetical/backtested performance, not audited live performance. "
        "The strategy is intended as a small micro-futures diversifier, not a replacement for equity exposure. "
        "Live deployment still requires tick/order-sequence validation, broker-paper parity, and counsel-reviewed disclosures."
    )
    fig.text(0.06, 0.055, "\n".join(textwrap.wrap(caveat, width=150)), fontsize=8.8, color="#374151")
    fig.savefig(OUT_DIR / PDF_FILE, format="pdf", bbox_inches="tight")
    plt.close(fig)


def write_markdown(strategy_rows: list[dict], qqq_rows: list[dict]) -> None:
    strategy_end = strategy_rows[-1]["end"]
    qqq_end = qqq_rows[-1]["end"]
    strategy_net = strategy_end - START_CAPITAL
    qqq_net = qqq_end - START_CAPITAL
    strategy_total_return = strategy_net / START_CAPITAL * 100.0
    qqq_total_return = qqq_net / START_CAPITAL * 100.0
    strategy_worst_dd_pct = max(r["closed_dd_pct"] for r in strategy_rows)
    qqq_worst_dd_pct = max(r["closed_dd_pct"] for r in qqq_rows)

    by_qqq = {r["year"]: r for r in qqq_rows}
    lines = [
        f"# {STRATEGY_NAME} vs QQQ",
        "",
        "**One-page hypothetical exhibit.** Starting capital is **$30,000** for both paths. The managed intraday strategy uses a rules-based micro Nasdaq futures replay; QQQ uses adjusted-close buy-and-hold over the same available window.",
        "",
        f"![{STRATEGY_NAME} vs QQQ]({CHART_FILE})",
        "",
        "## Headline",
        "",
        f"- **{STRATEGY_NAME}:** {money2(strategy_end)} ending value, {money2(strategy_net)} net, **{pct(strategy_total_return)} total return**.",
        f"- **QQQ buy-and-hold:** {money2(qqq_end)} ending value, {money2(qqq_net)} net, **{pct(qqq_total_return)} total return**.",
        f"- Worst annual strategy closed DD as a share of that year's starting balance: **{pct(strategy_worst_dd_pct)}**.",
        f"- Worst annual QQQ daily drawdown as a share of that year's starting balance: **{pct(qqq_worst_dd_pct)}**.",
        "",
        "## Annual Table",
        "",
        "| Year | Strategy Start | Strategy Net | Strategy Return | Strategy Closed DD | Strategy DD % | QQQ Start | QQQ Net | QQQ Return | QQQ DD % |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in strategy_rows:
        q = by_qqq[s["year"]]
        lines.append(
            "| "
            f"{s['year']} | {money(s['start'])} | {money(s['net'])} | **{pct(s['return_pct'])}** | "
            f"{money(s['closed_dd'])} | {pct(s['closed_dd_pct'])} | "
            f"{money(q['start'])} | {money(q['net'])} | **{pct(q['return_pct'])}** | {pct(q['closed_dd_pct'])} |"
        )
    lines.extend(
        [
            "",
            "## Read",
            "",
            "This strategy path is not a replacement for QQQ exposure; it is a micro-futures sleeve designed to create a different return stream around Nasdaq intraday movement. The attractive part is that the tested path stayed positive in every calendar segment, including 2022 when QQQ was negative. The weak point is that 2022 compressed sharply for the strategy too, so the next live-testing phase still needs to prove execution quality and edge persistence.",
            "",
            "**Important caveat:** this remains hypothetical/backtested performance. The strategy still needs tick/order-sequence proof and broker-paper parity before live capital decisions.",
        ]
    )
    (OUT_DIR / "ONE_PAGE_PITCH.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    strategy_rows = build_strategy_rows()
    qqq_rows, qqq_equity = build_qqq_rows()
    write_csv(strategy_rows, qqq_rows)
    write_equity_csv(qqq_equity)
    write_chart()
    write_markdown(strategy_rows, qqq_rows)
    write_pdf(strategy_rows, qqq_rows)


if __name__ == "__main__":
    main()
