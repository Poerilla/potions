from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "nq" / "case_studies" / "futures_dca_vs_qqq"
CONTRIBUTION = 1_000.0


def load_price(path: Path, price_col: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    return df[["date", price_col]].rename(columns={price_col: "price"})


def dca_on_common_period_dates(futures: pd.DataFrame, qqq: pd.DataFrame, period_freq: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    common = futures.merge(qqq, on="date", suffixes=("_futures", "_qqq"), how="inner").sort_values("date")
    common["period"] = common["date"].dt.to_period(period_freq).astype(str)
    buy_rows = common.groupby("period", as_index=False).first()
    buy_rows["contribution"] = CONTRIBUTION
    buy_rows["futures_units_bought"] = buy_rows["contribution"] / buy_rows["price_futures"]
    buy_rows["qqq_shares_bought"] = buy_rows["contribution"] / buy_rows["price_qqq"]
    buy_rows["cum_futures_units"] = buy_rows["futures_units_bought"].cumsum()
    buy_rows["cum_qqq_shares"] = buy_rows["qqq_shares_bought"].cumsum()
    buy_rows["cum_invested"] = buy_rows["contribution"].cumsum()

    daily = common.merge(
        buy_rows[["date", "contribution", "futures_units_bought", "qqq_shares_bought"]],
        on="date",
        how="left",
    )
    daily[["contribution", "futures_units_bought", "qqq_shares_bought"]] = daily[
        ["contribution", "futures_units_bought", "qqq_shares_bought"]
    ].fillna(0.0)
    daily["cum_futures_units"] = daily["futures_units_bought"].cumsum()
    daily["cum_qqq_shares"] = daily["qqq_shares_bought"].cumsum()
    daily["cum_invested"] = daily["contribution"].cumsum()
    daily["futures_equity"] = daily["cum_futures_units"] * daily["price_futures"]
    daily["qqq_equity"] = daily["cum_qqq_shares"] * daily["price_qqq"]
    daily["futures_drawdown"] = daily["futures_equity"] - daily["futures_equity"].cummax()
    daily["qqq_drawdown"] = daily["qqq_equity"] - daily["qqq_equity"].cummax()
    return daily, buy_rows


def summarize(label: str, cadence: str, daily: pd.DataFrame, buys: pd.DataFrame) -> dict[str, object]:
    end = daily.iloc[-1]
    invested = float(buys["contribution"].sum())
    futures_end = float(end["futures_equity"])
    qqq_end = float(end["qqq_equity"])
    return {
        "study": label,
        "cadence": cadence,
        "start": daily["date"].min().date().isoformat(),
        "end": daily["date"].max().date().isoformat(),
        "purchases": int(len(buys)),
        "contribution_per_purchase": CONTRIBUTION,
        "total_invested": invested,
        "futures_end_value": futures_end,
        "futures_net": futures_end - invested,
        "futures_return_on_invested_pct": (futures_end / invested - 1.0) * 100.0,
        "futures_max_drawdown": float(daily["futures_drawdown"].min()),
        "qqq_end_value": qqq_end,
        "qqq_net": qqq_end - invested,
        "qqq_return_on_invested_pct": (qqq_end / invested - 1.0) * 100.0,
        "qqq_max_drawdown": float(daily["qqq_drawdown"].min()),
        "futures_minus_qqq_end_value": futures_end - qqq_end,
    }


def money(v: float) -> str:
    return f"${v:,.0f}"


def pct(v: float) -> str:
    return f"{v:,.1f}%"


def md_table(rows: list[dict[str, object]], cols: list[str]) -> str:
    out = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")
    return "\n".join(out)


def plot_equity(label: str, cadence: str, daily: pd.DataFrame, filename: str) -> None:
    fig, ax = plt.subplots(figsize=(11, 5.4))
    ax.plot(daily["date"], daily["futures_equity"], label=label, linewidth=1.8)
    ax.plot(daily["date"], daily["qqq_equity"], label="QQQ", linewidth=1.5, linestyle="--")
    ax.plot(daily["date"], daily["cum_invested"], label="Contributed capital", color="#666666", linewidth=1.0, alpha=0.7)
    ax.set_title(f"{cadence.title()} $1,000 DCA: {label} vs QQQ")
    ax.set_ylabel("Account value")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"${x/1000:,.0f}k"))
    ax.grid(alpha=0.25)
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(OUT / filename, dpi=170)
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    qqq = load_price(ROOT / "data/benchmarks/QQQ_2000-01-01_2026-06-03_daily.csv", "adj_close")
    nq = load_price(ROOT / "nq/nq_daily.csv", "close")
    mnq = load_price(ROOT / "mnq/mnq_daily.csv", "close")

    studies = []
    for cadence, period_freq in [("monthly", "M"), ("quarterly", "Q")]:
        for label, futures, slug in [
            ("NQ synthetic fractional exposure", nq, "nq"),
            ("MNQ synthetic fractional exposure", mnq, "mnq"),
        ]:
            daily, buys = dca_on_common_period_dates(futures, qqq, period_freq)
            daily.to_csv(OUT / f"{slug}_{cadence}_dca_vs_qqq_daily.csv", index=False)
            buys.to_csv(OUT / f"{slug}_{cadence}_dca_vs_qqq_buys.csv", index=False)
            plot_equity(label, cadence, daily, f"{slug}_{cadence}_dca_vs_qqq_equity.png")
            studies.append(summarize(label, cadence, daily, buys))

    pd.DataFrame(studies).to_csv(OUT / "summary.csv", index=False)
    pretty_rows = []
    for row in studies:
        pretty_rows.append(
            {
                "Study": row["study"],
                "Cadence": row["cadence"],
                "Window": f"{row['start']} to {row['end']}",
                "Buys": row["purchases"],
                "Invested": money(float(row["total_invested"])),
                "Futures End": money(float(row["futures_end_value"])),
                "Futures Return": pct(float(row["futures_return_on_invested_pct"])),
                "QQQ End": money(float(row["qqq_end_value"])),
                "QQQ Return": pct(float(row["qqq_return_on_invested_pct"])),
                "Fut - QQQ": money(float(row["futures_minus_qqq_end_value"])),
            }
        )

    readme = "\n".join(
        [
            "# Futures DCA vs QQQ",
            "",
            "Synthetic benchmark: invest **$1,000** on the first common trading day of each calendar month or quarter into the futures close series and into QQQ adjusted close over the exact same dates.",
            "",
            "Important caveat: this is **fractional index exposure math**, not an executable NQ/MNQ contract strategy. It ignores futures margin, contract granularity, financing, tax, commissions, slippage, and roll/continuous-contract construction effects. QQQ uses adjusted close, so dividends are included in the ETF benchmark.",
            "",
            md_table(
                pretty_rows,
                ["Study", "Cadence", "Window", "Buys", "Invested", "Futures End", "Futures Return", "QQQ End", "QQQ Return", "Fut - QQQ"],
            ),
            "",
            "## Charts",
            "",
            "![NQ monthly DCA vs QQQ](nq_monthly_dca_vs_qqq_equity.png)",
            "",
            "![MNQ monthly DCA vs QQQ](mnq_monthly_dca_vs_qqq_equity.png)",
            "",
            "![NQ quarterly DCA vs QQQ](nq_quarterly_dca_vs_qqq_equity.png)",
            "",
            "![MNQ quarterly DCA vs QQQ](mnq_quarterly_dca_vs_qqq_equity.png)",
            "",
            "## Output Files",
            "",
            "- `summary.csv`",
            "- `nq_monthly_dca_vs_qqq_daily.csv`",
            "- `nq_monthly_dca_vs_qqq_buys.csv`",
            "- `nq_quarterly_dca_vs_qqq_daily.csv`",
            "- `nq_quarterly_dca_vs_qqq_buys.csv`",
            "- `mnq_monthly_dca_vs_qqq_daily.csv`",
            "- `mnq_monthly_dca_vs_qqq_buys.csv`",
            "- `mnq_quarterly_dca_vs_qqq_daily.csv`",
            "- `mnq_quarterly_dca_vs_qqq_buys.csv`",
        ]
    )
    (OUT / "INDEX.md").write_text(readme, encoding="utf-8")
    print(f"Wrote {OUT}")
    print(pd.DataFrame(studies).to_string(index=False))


if __name__ == "__main__":
    main()
