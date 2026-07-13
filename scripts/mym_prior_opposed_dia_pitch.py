#!/usr/bin/env python3
"""Build a one-page Dow-managed intraday diversifier vs DIA pitch exhibit."""
from __future__ import annotations

import csv
import textwrap
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "live/state/dow_managed_intraday_diversifier_pitch"
START_CAPITAL = 20_000.0
STRATEGY_NAME = "Dow Managed Intraday Diversifier Strategy"
CHART_FILE = "dow_managed_intraday_diversifier_vs_dia_20k.png"
PDF_FILE = "ONE_PAGE_PITCH.pdf"
MYM_YEARLY = (
    ROOT
    / "live/state/mym_v2b_prior_opposed_stpmc_broker_like/robustness_audit/yearly_breakdown.csv"
)
DIA_DAILY = ROOT / "data/benchmarks/DIA_2021-03-04_2026-03-06_yahoo_daily.csv"
INSTITUTIONAL_METRICS = ROOT / "live/state/institutional_strategy_metrics/metrics.csv"


def money(value: float) -> str:
    return f"${value:,.0f}"


def money2(value: float) -> str:
    return f"${value:,.2f}"


def pct(value: float) -> str:
    return f"{value:.1f}%"


def max_drawdown(series: pd.Series) -> float:
    return float((series - series.cummax()).min()) if not series.empty else 0.0


def build_mym_rows() -> tuple[list[dict], pd.DataFrame]:
    rows: list[dict] = []
    equity_points = []
    balance = START_CAPITAL

    with MYM_YEARLY.open() as f:
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


def build_dia_rows() -> tuple[list[dict], pd.DataFrame]:
    daily = pd.read_csv(DIA_DAILY, parse_dates=["date"])
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


def write_csv(mym_rows: list[dict], dia_rows: list[dict]) -> None:
    years = sorted({r["year"] for r in mym_rows} | {r["year"] for r in dia_rows})
    by_mym = {r["year"]: r for r in mym_rows}
    by_dia = {r["year"]: r for r in dia_rows}
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
            "dia_start",
            "dia_net",
            "dia_end",
            "dia_return_pct",
            "dia_max_daily_dd",
            "dia_max_daily_dd_pct",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for year in years:
            m = by_mym[year]
            d = by_dia[year]
            writer.writerow(
                {
                    "year": year,
                    "strategy_start": f"{m['start']:.2f}",
                    "strategy_net": f"{m['net']:.2f}",
                    "strategy_end": f"{m['end']:.2f}",
                    "strategy_return_pct": f"{m['return_pct']:.4f}",
                    "strategy_closed_dd": f"{m['closed_dd']:.2f}",
                    "strategy_closed_dd_pct": f"{m['closed_dd_pct']:.4f}",
                    "dia_start": f"{d['start']:.2f}",
                    "dia_net": f"{d['net']:.2f}",
                    "dia_end": f"{d['end']:.2f}",
                    "dia_return_pct": f"{d['return_pct']:.4f}",
                    "dia_max_daily_dd": f"{d['closed_dd']:.2f}",
                    "dia_max_daily_dd_pct": f"{d['closed_dd_pct']:.4f}",
                }
            )


def write_equity_csv(mym_equity: pd.DataFrame, dia_equity: pd.DataFrame) -> None:
    mym_daily = pd.read_csv(
        ROOT
        / "live/state/mym_v2b_prior_opposed_stpmc_broker_like/states/"
        / "mym_v2b_prior_opposed_stpmc_only_S_1_1_3/equity_curve.csv"
    )
    mym_daily["ts"] = pd.to_datetime(mym_daily["ts"], utc=True)
    mym_daily["date"] = mym_daily["ts"].dt.date
    mym_daily = mym_daily.groupby("date", as_index=False).tail(1)
    mym_daily["date"] = pd.to_datetime(mym_daily["date"])
    mym_daily["equity"] = START_CAPITAL + mym_daily["close_equity_usd"].astype(float)
    out = pd.merge(
        mym_daily[["date", "equity"]].rename(columns={"equity": "strategy_equity"}),
        dia_equity.rename(columns={"equity": "dia_equity"}),
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
    ax1.plot(curves["date"], curves["dia_equity"], label="DIA buy-and-hold", color="#1d4ed8", linewidth=2.1)
    ax1.axhline(START_CAPITAL, color="#9ca3af", linewidth=1, linestyle="--")
    ax1.set_title(f"$20,000 Hypothetical Growth: {STRATEGY_NAME} vs DIA")
    ax1.set_ylabel("Account value")
    ax1.grid(True, alpha=0.25)
    ax1.legend(loc="upper left")
    ax1.yaxis.set_major_formatter(lambda x, pos: f"${x/1000:.0f}k")

    mym_dd = curves["strategy_equity"] - curves["strategy_equity"].cummax()
    dia_dd = curves["dia_equity"] - curves["dia_equity"].cummax()
    ax2.fill_between(curves["date"], mym_dd, 0, color="#0f766e", alpha=0.24, label="Strategy drawdown")
    ax2.fill_between(curves["date"], dia_dd, 0, color="#1d4ed8", alpha=0.18, label="DIA drawdown")
    ax2.set_ylabel("Drawdown")
    ax2.grid(True, alpha=0.25)
    ax2.yaxis.set_major_formatter(lambda x, pos: f"${x/1000:.0f}k")
    ax2.legend(loc="lower left", ncol=2)

    fig.tight_layout()
    fig.savefig(OUT_DIR / CHART_FILE, dpi=160)
    plt.close(fig)


def load_institutional_metrics() -> dict:
    metrics = {}
    if INSTITUTIONAL_METRICS.exists():
        df = pd.read_csv(INSTITUTIONAL_METRICS)
        rows = df[df["name"].astype(str).str.contains("MYM prior-opposed", regex=False)]
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

    curves_path = OUT_DIR / "equity_curves.csv"
    if curves_path.exists():
        curves = pd.read_csv(curves_path, parse_dates=["date"]).sort_values("date").ffill()
        if not curves.empty:
            start = float(curves["strategy_equity"].iloc[0])
            end = float(curves["strategy_equity"].iloc[-1])
            years = (curves["date"].iloc[-1] - curves["date"].iloc[0]).days / 365.25
            if start > 0 and years > 0:
                metrics["path_cagr"] = ((end / start) ** (1.0 / years) - 1.0) * 100.0
            curves["strategy_ret"] = curves["strategy_equity"].pct_change().fillna(0.0)
            curves["dia_ret"] = curves["dia_equity"].pct_change().fillna(0.0)
            metrics["dia_corr"] = float(curves["strategy_ret"].corr(curves["dia_ret"]))
            down = curves[curves["dia_ret"] < 0]
            if not down.empty and float(down["dia_ret"].mean()) != 0.0:
                metrics["dia_down_capture"] = float(down["strategy_ret"].mean() / down["dia_ret"].mean())
    return metrics


def write_pdf(mym_rows: list[dict], dia_rows: list[dict]) -> None:
    inst = load_institutional_metrics()
    mym_end = mym_rows[-1]["end"]
    dia_end = dia_rows[-1]["end"]
    mym_net = mym_end - START_CAPITAL
    dia_net = dia_end - START_CAPITAL
    mym_total_return = mym_net / START_CAPITAL * 100.0
    dia_total_return = dia_net / START_CAPITAL * 100.0
    mym_worst_dd_pct = max(r["closed_dd_pct"] for r in mym_rows)
    dia_worst_dd_pct = max(r["closed_dd_pct"] for r in dia_rows)
    by_dia = {r["year"]: r for r in dia_rows}

    fig = plt.figure(figsize=(11, 8.5))
    fig.patch.set_facecolor("white")
    fig.text(0.06, 0.955, f"{STRATEGY_NAME} vs DIA", fontsize=19, weight="bold", color="#111827")
    fig.text(
        0.06,
        0.923,
        "One-page hypothetical exhibit. $20,000 starting capital for both paths. DIA uses adjusted-close buy-and-hold.",
        fontsize=9.5,
        color="#374151",
    )

    chart = plt.imread(OUT_DIR / CHART_FILE)
    ax_chart = fig.add_axes([0.055, 0.43, 0.89, 0.45])
    ax_chart.imshow(chart)
    ax_chart.axis("off")

    headline = (
        f"Strategy ending value: {money2(mym_end)} | Net: {money2(mym_net)} | Total return: {pct(mym_total_return)}\n"
        f"DIA ending value: {money2(dia_end)} | Net: {money2(dia_net)} | Total return: {pct(dia_total_return)}\n"
        f"Worst annual strategy closed DD: {pct(mym_worst_dd_pct)} of starting balance | "
        f"Worst annual DIA daily DD: {pct(dia_worst_dd_pct)}\n"
        f"Sharpe/Sortino: {inst.get('sharpe', 0.0):.2f}/{inst.get('sortino', 0.0):.2f} | "
        f"$20k-path CAGR: {pct(inst.get('path_cagr', 0.0))} | "
        f"Calmar on modeled stress: {inst.get('calmar_stress', 0.0):.2f} | "
        f"DIA corr/downside capture: {inst.get('dia_corr', 0.0):.2f}/{inst.get('dia_down_capture', 0.0):.2f} | "
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
    for m in mym_rows:
        d = by_dia[m["year"]]
        table_rows.append(
            [
                str(m["year"]),
                money(m["start"]),
                money(m["net"]),
                pct(m["return_pct"]),
                pct(m["closed_dd_pct"]),
                money(d["net"]),
                pct(d["return_pct"]),
                pct(d["closed_dd_pct"]),
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
            "DIA Net",
            "DIA Ret.",
            "DIA DD",
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
        "The strategy is intended as a small futures diversifier, not a replacement for equity exposure. "
        "Live deployment still requires tick/order-sequence validation, broker-paper parity, and counsel-reviewed disclosures."
    )
    fig.text(0.06, 0.055, "\n".join(textwrap.wrap(caveat, width=150)), fontsize=8.8, color="#374151")
    fig.savefig(OUT_DIR / PDF_FILE, format="pdf", bbox_inches="tight")
    plt.close(fig)


def write_markdown(mym_rows: list[dict], dia_rows: list[dict]) -> None:
    inst = load_institutional_metrics()
    mym_end = mym_rows[-1]["end"]
    dia_end = dia_rows[-1]["end"]
    mym_net = mym_end - START_CAPITAL
    dia_net = dia_end - START_CAPITAL
    mym_total_return = mym_net / START_CAPITAL * 100.0
    dia_total_return = dia_net / START_CAPITAL * 100.0
    mym_worst_dd_pct = max(r["closed_dd_pct"] for r in mym_rows)
    dia_worst_dd_pct = max(r["closed_dd_pct"] for r in dia_rows)

    by_dia = {r["year"]: r for r in dia_rows}
    lines = [
        f"# {STRATEGY_NAME} vs DIA",
        "",
        "**One-page hypothetical exhibit.** Starting capital is **$20,000** for both paths. The managed intraday strategy uses a rules-based futures replay; DIA uses adjusted-close buy-and-hold over the same available window.",
        "",
        f"![{STRATEGY_NAME} vs DIA]({CHART_FILE})",
        "",
        "## Headline",
        "",
        f"- **{STRATEGY_NAME}:** {money2(mym_end)} ending value, {money2(mym_net)} net, **{pct(mym_total_return)} total return**.",
        f"- **DIA buy-and-hold:** {money2(dia_end)} ending value, {money2(dia_net)} net, **{pct(dia_total_return)} total return**.",
        f"- Worst annual strategy closed DD as a share of that year's starting balance: **{pct(mym_worst_dd_pct)}**.",
        f"- Worst annual DIA daily drawdown as a share of that year's starting balance: **{pct(dia_worst_dd_pct)}**.",
        "",
        "## Institutional Metrics",
        "",
        "The headline above uses the simple **$20,000 starting-account path**. The institutional statistics below use the same hypothetical replay's daily return path and stress accounting.",
        "",
        "| Metric | Managed intraday strategy |",
        "|---|---:|",
        f"| Backtest window | {inst.get('window', 'n/a')} |",
        f"| $20k-path CAGR | {pct(inst.get('path_cagr', 0.0))} |",
        f"| Sharpe / Sortino | {inst.get('sharpe', 0.0):.2f} / {inst.get('sortino', 0.0):.2f} |",
        f"| Calmar / MAR on modeled stress | {inst.get('calmar_stress', 0.0):.2f} |",
        f"| Calmar on worst annual closed DD | {mym_total_return and (inst.get('path_cagr', 0.0) / mym_worst_dd_pct):.2f} |",
        f"| Max drawdown duration | {inst.get('dd_duration', 0)} days |",
        f"| Daily skew | {inst.get('daily_skew', 0.0):.2f} |",
        f"| QQQ corr / downside capture | {inst.get('qqq_corr', 0.0):.2f} / {inst.get('qqq_down_capture', 0.0):.2f} |",
        f"| DIA corr / downside capture | {inst.get('dia_corr', 0.0):.2f} / {inst.get('dia_down_capture', 0.0):.2f} |",
        f"| Profit factor / win rate | {inst.get('profit_factor', 0.0):.2f} / {inst.get('win_rate', 0.0):.1f}% |",
        f"| Modeled intrabar stress / closed DD | {money(inst.get('stress_dd', 0.0))} / {money(inst.get('closed_dd', 0.0))} |",
        "",
        "## Annual Table",
        "",
        "| Year | Strategy Start | Strategy Net | Strategy Return | Strategy Closed DD | Strategy DD % | DIA Start | DIA Net | DIA Return | DIA DD % |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in mym_rows:
        d = by_dia[m["year"]]
        lines.append(
            "| "
            f"{m['year']} | {money(m['start'])} | {money(m['net'])} | **{pct(m['return_pct'])}** | "
            f"{money(m['closed_dd'])} | {pct(m['closed_dd_pct'])} | "
            f"{money(d['start'])} | {money(d['net'])} | **{pct(d['return_pct'])}** | {pct(d['closed_dd_pct'])} |"
        )
    lines.extend(
        [
            "",
            "## Read",
            "",
            "This strategy path is not a replacement for equity exposure; it is a small futures sleeve designed to behave differently from a passive Dow ETF. The attractive part is consistency: every tested calendar segment is positive, including 2022 when DIA was negative. The weak point is 2024, where the edge remained positive but compressed sharply.",
            "",
            "**Important caveat:** this remains hypothetical/backtested performance. The strategy still needs tick/order-sequence proof and broker-paper parity before live capital decisions.",
        ]
    )
    (OUT_DIR / "ONE_PAGE_PITCH.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mym_rows, mym_equity = build_mym_rows()
    dia_rows, dia_equity = build_dia_rows()
    write_csv(mym_rows, dia_rows)
    write_equity_csv(mym_equity, dia_equity)
    write_chart()
    write_markdown(mym_rows, dia_rows)
    write_pdf(mym_rows, dia_rows)


if __name__ == "__main__":
    main()
