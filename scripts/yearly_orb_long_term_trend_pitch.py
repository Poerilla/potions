#!/usr/bin/env python3
"""Build one-page long-term trend PDFs for the top yearly ORB futures rows."""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "live/state/yearly_orb_long_term_trend_pitch"
SUMMARY_PATH = ROOT / "live/state/broker_like_replays/summary.csv"


POINT_VALUES = {
    "ES": 50.0,
    "NQ": 20.0,
    "YM": 5.0,
}

ETF_BY_INSTRUMENT = {
    "ES": ("SPY", ROOT / "data/benchmarks/SPY_2010-06-06_2026-03-08_yahoo_daily.csv"),
    "NQ": ("QQQ", ROOT / "data/benchmarks/QQQ_2010-06-06_2026-03-08_yahoo_daily.csv"),
    "YM": ("DIA", ROOT / "data/benchmarks/DIA_2010-01-01_2026-06-03_daily.csv"),
}

PROGRAM_NAME = {
    "ES": "S&P Long-Term Trend Program",
    "NQ": "Nasdaq Long-Term Trend Program",
    "YM": "Dow Long-Term Trend Program",
}


@dataclass(frozen=True)
class PitchSource:
    instrument: str
    slug: str
    etf: str
    etf_path: Path
    equity_path: Path
    units_path: Path
    point_value: float
    net_usd: float
    stress_dd_usd: float
    close_dd_usd: float
    trades: int
    units: int
    max_open_units: int
    net_over_stress: float
    start_capital: float


def money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.0f}"


def pct(value: float) -> str:
    return f"{value:.1f}%"


def max_drawdown(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    return float((series - series.cummax()).min())


def drawdown_duration_days(series: pd.Series, dates: pd.Series) -> int:
    peak = -math.inf
    underwater_start = None
    longest = 0
    for dt, value in zip(dates, series):
        if value >= peak:
            peak = float(value)
            underwater_start = None
            continue
        if underwater_start is None:
            underwater_start = dt
        longest = max(longest, int((dt - underwater_start).days))
    return longest


def annualized_return(start: float, end: float, days: int) -> float:
    if start <= 0 or end <= 0 or days <= 0:
        return 0.0
    return (end / start) ** (365.25 / days) - 1.0


def sharpe(returns: pd.Series) -> float:
    returns = returns.dropna()
    if len(returns) < 2 or returns.std(ddof=1) == 0:
        return 0.0
    return float(returns.mean() / returns.std(ddof=1) * math.sqrt(252))


def sortino(returns: pd.Series) -> float:
    returns = returns.dropna()
    downside = returns[returns < 0]
    if len(returns) < 2 or len(downside) < 2 or downside.std(ddof=1) == 0:
        return 0.0
    return float(returns.mean() / downside.std(ddof=1) * math.sqrt(252))


def load_top_three() -> list[PitchSource]:
    summary = pd.read_csv(SUMMARY_PATH)
    mask = summary["slug"].str.contains("yearly_orb_scaleout3", na=False)
    mask &= ~summary["slug"].str.contains("range_close", na=False)
    mask &= summary["instrument"].isin(["ES", "NQ", "YM"])
    top = summary[mask].sort_values("net_over_stress_dd", ascending=False).head(3)
    sources: list[PitchSource] = []
    for _, row in top.iterrows():
        instrument = str(row["instrument"])
        etf, etf_path = ETF_BY_INSTRUMENT[instrument]
        stress = abs(float(row["intrabar_mtm_dd_usd"]))
        # 3x stress rounded up to the nearest $5k, matching the platform's sizing language.
        start_capital = math.ceil((stress * 3.0) / 5_000.0) * 5_000.0
        slug = str(row["slug"])
        sources.append(
            PitchSource(
                instrument=instrument,
                slug=slug,
                etf=etf,
                etf_path=etf_path,
                equity_path=ROOT / f"live/state/broker_like_replays/audits/{slug}/equity_curve.csv",
                units_path=ROOT / f"live/state/broker_like_replays/audits/{slug}/unit_fills.csv",
                point_value=POINT_VALUES[instrument],
                net_usd=float(row["net_usd"]),
                stress_dd_usd=float(row["intrabar_mtm_dd_usd"]),
                close_dd_usd=float(row["close_mtm_dd_usd"]),
                trades=int(row["trades"]),
                units=int(row["units"]),
                max_open_units=int(row["max_open_units"]),
                net_over_stress=float(row["net_over_stress_dd"]),
                start_capital=start_capital,
            )
        )
    return sources


def load_strategy_curve(src: PitchSource) -> pd.DataFrame:
    curve = pd.read_csv(src.equity_path)
    curve["date"] = pd.to_datetime(curve["ts"]).dt.tz_localize(None).dt.normalize()
    curve = curve.groupby("date", as_index=False).tail(1)
    curve["net_usd"] = curve["close_equity_points"].astype(float) * src.point_value
    curve["stress_net_usd"] = curve["intrabar_stress_points"].astype(float) * src.point_value
    curve["program_equity"] = src.start_capital + curve["net_usd"]
    curve["program_stress_equity"] = src.start_capital + curve["stress_net_usd"]
    return curve[["date", "net_usd", "stress_net_usd", "program_equity", "program_stress_equity"]].reset_index(drop=True)


def load_etf_curve(src: PitchSource, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    bench = pd.read_csv(src.etf_path, parse_dates=["date"])
    bench = bench.sort_values("date")
    bench = bench[(bench["date"] >= start) & (bench["date"] <= end)].copy()
    if bench.empty:
        raise RuntimeError(f"No ETF benchmark rows for {src.etf} in {start.date()} to {end.date()}")
    first = float(bench["adj_close"].iloc[0])
    bench["etf_equity"] = src.start_capital * bench["adj_close"].astype(float) / first
    return bench[["date", "etf_equity"]].reset_index(drop=True)


def load_campaigns(src: PitchSource) -> pd.DataFrame:
    units = pd.read_csv(src.units_path)
    units["exit_date"] = pd.to_datetime(units["exit_ts"]).dt.tz_localize(None).dt.normalize()
    return (
        units.groupby("trade_id", as_index=False)
        .agg(exit_date=("exit_date", "max"), pnl=("usd", "sum"))
        .sort_values("exit_date")
    )


def build_curves(src: PitchSource) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    strategy = load_strategy_curve(src)
    start = strategy["date"].min()
    end = strategy["date"].max()
    etf = load_etf_curve(src, start, end)
    curves = pd.merge(strategy, etf, on="date", how="outer").sort_values("date")
    curves["program_equity"] = curves["program_equity"].ffill()
    curves["program_stress_equity"] = curves["program_stress_equity"].ffill()
    curves["etf_equity"] = curves["etf_equity"].ffill()
    curves = curves.dropna(subset=["program_equity", "etf_equity"]).reset_index(drop=True)
    campaigns = load_campaigns(src)
    return curves, strategy, campaigns


def annual_rows(curves: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    prior_program = float(curves["program_equity"].iloc[0])
    prior_etf = float(curves["etf_equity"].iloc[0])
    for year, group in curves.groupby(curves["date"].dt.year):
        program_end = float(group["program_equity"].iloc[-1])
        etf_end = float(group["etf_equity"].iloc[-1])
        program_net = program_end - prior_program
        etf_net = etf_end - prior_etf
        program_dd = max_drawdown(group["program_equity"])
        rows.append(
            {
                "Year": int(year),
                "Program %": program_net / prior_program * 100.0,
                "ETF %": etf_net / prior_etf * 100.0,
                "Program net": program_net,
                "Program DD %": abs(program_dd) / prior_program * 100.0,
            }
        )
        prior_program = program_end
        prior_etf = etf_end
    return pd.DataFrame(rows)


def metric_summary(src: PitchSource, curves: pd.DataFrame, campaigns: pd.DataFrame) -> dict[str, float]:
    daily = curves[["date", "program_equity", "etf_equity"]].dropna().copy()
    program_returns = daily["program_equity"].pct_change()
    etf_returns = daily["etf_equity"].pct_change()
    days = int((daily["date"].iloc[-1] - daily["date"].iloc[0]).days)
    start = float(daily["program_equity"].iloc[0])
    end = float(daily["program_equity"].iloc[-1])
    etf_end = float(daily["etf_equity"].iloc[-1])
    close_dd = max_drawdown(daily["program_equity"])
    stress_dd = min(float(src.stress_dd_usd), float((daily["program_stress_equity"] - daily["program_equity"].cummax()).min())) if "program_stress_equity" in daily else src.stress_dd_usd
    gross_profit = float(campaigns[campaigns["pnl"] > 0]["pnl"].sum())
    gross_loss = abs(float(campaigns[campaigns["pnl"] < 0]["pnl"].sum()))
    pf = gross_profit / gross_loss if gross_loss else 0.0
    win_rate = float((campaigns["pnl"] > 0).mean() * 100.0) if not campaigns.empty else 0.0
    corr = float(program_returns.corr(etf_returns)) if len(daily) > 2 else 0.0
    downside = etf_returns < 0
    downside_capture = 0.0
    if downside.sum() > 1 and etf_returns[downside].sum() != 0:
        downside_capture = float(program_returns[downside].sum() / etf_returns[downside].sum())
    return {
        "net": end - start,
        "end": end,
        "etf_end": etf_end,
        "return_pct": (end - start) / start * 100.0,
        "etf_return_pct": (etf_end - start) / start * 100.0,
        "cagr": annualized_return(start, end, days) * 100.0,
        "etf_cagr": annualized_return(start, etf_end, days) * 100.0,
        "close_dd": close_dd,
        "stress_dd": src.stress_dd_usd,
        "calmar": (annualized_return(start, end, days) / (abs(src.stress_dd_usd) / start)) if src.stress_dd_usd else 0.0,
        "sharpe": sharpe(program_returns),
        "sortino": sortino(program_returns),
        "corr": corr,
        "downside_capture": downside_capture,
        "pf": pf,
        "win_rate": win_rate,
        "dd_duration": drawdown_duration_days(daily["program_equity"], daily["date"]),
    }


def make_chart(src: PitchSource, curves: pd.DataFrame, chart_path: Path) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(9.0, 4.0))
    ax.plot(curves["date"], curves["program_equity"], color="#1b5e20", lw=2.4, label=PROGRAM_NAME[src.instrument])
    ax.plot(curves["date"], curves["etf_equity"], color="#37474f", lw=1.8, label=f"{src.etf} fully invested")
    ax.fill_between(
        curves["date"],
        curves["program_equity"],
        curves["program_equity"].cummax(),
        where=curves["program_equity"] < curves["program_equity"].cummax(),
        color="#c62828",
        alpha=0.10,
        linewidth=0,
    )
    ax.set_title(f"{PROGRAM_NAME[src.instrument]} vs {src.etf}", loc="left", fontsize=13, fontweight="bold")
    ax.set_ylabel("Account equity ($)")
    ax.yaxis.set_major_formatter(lambda x, _: f"${x/1000:,.0f}k")
    ax.legend(loc="upper left", frameon=False)
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(chart_path, dpi=180)
    plt.close(fig)


def write_markdown(src: PitchSource, metrics: dict[str, float], annual: pd.DataFrame, chart_path: Path, pdf_path: Path) -> Path:
    md_path = OUT_DIR / f"LONG_TERM_TREND_{src.instrument}_{src.etf}.md"
    lines = [
        f"# {PROGRAM_NAME[src.instrument]}",
        "",
        "**Status:** hypothetical/backtested broker-like replay. Not audited live performance.",
        "",
        f"![Equity chart]({chart_path.name})",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Starting account anchor | {money(src.start_capital)} |",
        f"| Net profit | {money(metrics['net'])} |",
        f"| Total return | {pct(metrics['return_pct'])} |",
        f"| CAGR | {pct(metrics['cagr'])} |",
        f"| Intrabar stress DD | {money(src.stress_dd_usd)} |",
        f"| Net / stress DD | {src.net_over_stress:.2f} |",
        f"| Sharpe / Sortino | {metrics['sharpe']:.2f} / {metrics['sortino']:.2f} |",
        f"| Calmar | {metrics['calmar']:.2f} |",
        f"| Correlation to {src.etf} | {metrics['corr']:.2f} |",
        f"| Profit factor / win rate | {metrics['pf']:.2f} / {pct(metrics['win_rate'])} |",
        "",
        "## Annual Table",
        "",
        annual.to_markdown(index=False, floatfmt=".1f"),
        "",
        f"PDF: `{pdf_path.name}`",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path


def draw_pdf(src: PitchSource, curves: pd.DataFrame, metrics: dict[str, float], annual: pd.DataFrame, chart_path: Path, pdf_path: Path) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")
    with PdfPages(pdf_path) as pdf:
        fig = plt.figure(figsize=(11.0, 8.5))
        fig.patch.set_facecolor("white")
        ax_bg = fig.add_axes([0, 0, 1, 1])
        ax_bg.axis("off")

        ax_bg.text(0.055, 0.955, PROGRAM_NAME[src.instrument], fontsize=20, fontweight="bold", color="#102027")
        ax_bg.text(
            0.055,
            0.925,
            f"Broker-like yearly opening-range trend replay vs {src.etf}, sized at 3x historical intrabar stress.",
            fontsize=9.5,
            color="#455a64",
        )
        ax_bg.text(
            0.055,
            0.902,
            "Hypothetical/backtested results only. Performance includes broker-realism defaults used by the live replay stack.",
            fontsize=8.5,
            color="#7b1fa2",
        )

        chart_ax = fig.add_axes([0.38, 0.52, 0.57, 0.34])
        chart_ax.plot(curves["date"], curves["program_equity"], color="#1b5e20", lw=2.2, label="Program")
        chart_ax.plot(curves["date"], curves["etf_equity"], color="#37474f", lw=1.6, label=src.etf)
        chart_ax.set_title(f"Equity Growth: Program vs {src.etf}", loc="left", fontsize=11, fontweight="bold")
        chart_ax.yaxis.set_major_formatter(lambda x, _: f"${x/1000:,.0f}k")
        chart_ax.tick_params(axis="both", labelsize=8)
        chart_ax.legend(loc="upper left", frameon=False, fontsize=8)
        chart_ax.grid(True, alpha=0.22)

        metric_items = [
            ("Start anchor", money(src.start_capital)),
            ("Program net", money(metrics["net"])),
            ("Program return", pct(metrics["return_pct"])),
            (f"{src.etf} return", pct(metrics["etf_return_pct"])),
            ("CAGR", pct(metrics["cagr"])),
            ("Stress DD", money(src.stress_dd_usd)),
            ("Net / DD", f"{src.net_over_stress:.2f}"),
            ("Sharpe / Sortino", f"{metrics['sharpe']:.2f} / {metrics['sortino']:.2f}"),
            ("Calmar", f"{metrics['calmar']:.2f}"),
            (f"Corr to {src.etf}", f"{metrics['corr']:.2f}"),
            ("PF / win", f"{metrics['pf']:.2f} / {pct(metrics['win_rate'])}"),
            ("Trades / units", f"{src.trades} / {src.units}"),
        ]

        x0, y0 = 0.055, 0.842
        box_w, box_h = 0.145, 0.057
        for idx, (label, value) in enumerate(metric_items):
            col = idx % 2
            row = idx // 2
            x = x0 + col * (box_w + 0.018)
            y = y0 - row * (box_h + 0.012)
            rect = plt.Rectangle((x, y - box_h), box_w, box_h, facecolor="#f6f8fa", edgecolor="#cfd8dc", lw=0.8)
            ax_bg.add_patch(rect)
            ax_bg.text(x + 0.008, y - 0.020, label, fontsize=7.2, color="#607d8b")
            ax_bg.text(x + 0.008, y - 0.043, value, fontsize=10.0, fontweight="bold", color="#102027")

        ax_bg.text(0.055, 0.405, "Annual Results", fontsize=12, fontweight="bold", color="#102027")
        ax_bg.text(
            0.055,
            0.386,
            "Program returns use each year's starting balance; ETF is fully invested over the same dates.",
            fontsize=8,
            color="#455a64",
        )

        table_ax = fig.add_axes([0.055, 0.082, 0.89, 0.288])
        table_ax.axis("off")
        display = annual.copy()
        display["Program %"] = display["Program %"].map(lambda x: f"{x:.1f}%")
        display["ETF %"] = display["ETF %"].map(lambda x: f"{x:.1f}%")
        display["Program net"] = display["Program net"].map(money)
        display["Program DD %"] = display["Program DD %"].map(lambda x: f"{x:.1f}%")
        table = table_ax.table(
            cellText=display.values,
            colLabels=display.columns,
            cellLoc="right",
            colLoc="right",
            bbox=[0, 0, 1, 1],
            colWidths=[0.10, 0.16, 0.14, 0.18, 0.16],
        )
        table.auto_set_font_size(False)
        table.set_fontsize(6.4)
        for (r, c), cell in table.get_celld().items():
            cell.set_edgecolor("#eceff1")
            if r == 0:
                cell.set_facecolor("#263238")
                cell.set_text_props(color="white", weight="bold")
            elif r % 2 == 0:
                cell.set_facecolor("#f7f9fb")
            else:
                cell.set_facecolor("white")

        foot = (
            f"Source: {src.slug} broker-like replay; equity curve {src.equity_path.relative_to(ROOT)}; "
            f"matched ETF file {src.etf_path.relative_to(ROOT)}. One base book, max {src.max_open_units} open units. "
            "No live track record is implied."
        )
        ax_bg.text(0.055, 0.055, foot, fontsize=6.7, color="#607d8b", wrap=True)
        pdf.savefig(fig)
        plt.close(fig)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index_lines = [
        "# Yearly ORB Long-Term Trend Pitch PDFs",
        "",
        "Generated from broker-like replay audit curves and matched ETF benchmark files.",
        "",
        "| Instrument | ETF | PDF | Markdown |",
        "|---|---|---|---|",
    ]
    for src in load_top_three():
        curves, _, campaigns = build_curves(src)
        metrics = metric_summary(src, curves, campaigns)
        annual = annual_rows(curves)
        chart_path = OUT_DIR / f"LONG_TERM_TREND_{src.instrument}_{src.etf}.png"
        pdf_path = OUT_DIR / f"LONG_TERM_TREND_{src.instrument}_{src.etf}.pdf"
        make_chart(src, curves, chart_path)
        draw_pdf(src, curves, metrics, annual, chart_path, pdf_path)
        md_path = write_markdown(src, metrics, annual, chart_path, pdf_path)
        index_lines.append(
            f"| {src.instrument} | {src.etf} | [{pdf_path.name}]({pdf_path.name}) | [{md_path.name}]({md_path.name}) |"
        )
        annual_out = OUT_DIR / f"LONG_TERM_TREND_{src.instrument}_{src.etf}_annual.csv"
        annual.to_csv(annual_out, index=False)
        curves.to_csv(OUT_DIR / f"LONG_TERM_TREND_{src.instrument}_{src.etf}_equity.csv", index=False)
        print(f"Wrote {pdf_path}")
    (OUT_DIR / "INDEX.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
