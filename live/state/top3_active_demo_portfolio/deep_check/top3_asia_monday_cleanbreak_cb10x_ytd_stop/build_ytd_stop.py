"""Year-target stop on the TOP3 Asia + Monday OR + Clean Break x10 account.

The stored campaign tape has 1,262 rows whose exit timestamp is earlier than the
entry timestamp (Monday OR and Asia Range fill clocks). The daily equity curve
does not depend on that ordering: every bar is a flat book (open units 0) and
close equity equals realized PnL. The stop is applied to that path.

Rule: paper equity starts at $100,000 and compounds by calendar-year realized
PnL. After the first daily close whose year-to-date PnL is at least the hurdle
(10, 15, or 20 percent of that year's starting equity), the rest of the
calendar year is flat. The crossing day is kept in full. This is an end-of-day
lock on the stored curve, not a new Engine replay and not an intraday fill at
the exact percentage.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from live.instrument_deep_check import NY, START_EQUITY, max_drawdown

STATE = Path(
    "/home/tester/hsm/potions/live/state/top3_active_demo_portfolio/states/top3_asia_monday_cleanbreak_cb10x"
)
PUBLISHED = (
    STATE.parent.parent
    / "deep_check"
    / "top3_asia_monday_cleanbreak_cb10x"
    / "yearly_breakdown.csv"
)
OUT = Path(
    "/home/tester/hsm/potions/live/state/top3_active_demo_portfolio/deep_check/top3_asia_monday_cleanbreak_cb10x_ytd_stop"
)
TARGETS = (0.20, 0.15, 0.10)


def _money(value: float) -> str:
    return "$%s%.2f" % ("-" if value < 0 else "", abs(value))


def _pct(value: float) -> str:
    return "%+.2f%%" % (100.0 * value)


def load_equity() -> pd.DataFrame:
    eq = pd.read_csv(STATE / "equity_curve.csv")
    eq["ts"] = pd.to_datetime(eq["ts"], utc=True).dt.tz_convert(NY)
    eq = eq.sort_values("ts").reset_index(drop=True)
    eq["date"] = eq["ts"].dt.date
    eq["year"] = eq["ts"].dt.year.astype(int)
    eq["close"] = pd.to_numeric(eq["close_equity_usd"])
    eq["stress"] = pd.to_numeric(eq["intrabar_stress_equity_usd"])
    eq["delta"] = eq["close"].diff()
    eq.loc[0, "delta"] = eq.loc[0, "close"]
    if not (eq["open_units"] == 0).all():
        raise SystemExit("equity curve has open units; daily close is not flat realized")
    if float((eq["close"] - pd.to_numeric(eq["realized_usd"])).abs().max()) > 1e-6:
        raise SystemExit("close equity is not realized PnL")
    return eq


def load_trades() -> pd.DataFrame:
    tr = pd.read_csv(STATE / "trades.csv")
    tr["session"] = pd.to_datetime(tr["session"]).dt.date
    tr["year"] = pd.to_datetime(tr["session"]).dt.year.astype(int)
    tr["net_usd"] = pd.to_numeric(tr["net_usd"])
    return tr


def _stress(window: pd.DataFrame) -> float:
    if window.empty:
        return 0.0
    return float(max_drawdown(window["stress"]))


def simulate(eq: pd.DataFrame, trades: pd.DataFrame, target: float | None) -> pd.DataFrame:
    paper = float(START_EQUITY)
    rows = []
    for year, g in eq.groupby("year", sort=True):
        start = paper
        hurdle = None if target is None else float(target) * start
        ytd = 0.0
        peak = 0.0
        peak_date = None
        lock_date = None
        lock_ytd = None
        for rec in g.itertuples(index=False):
            ytd += float(rec.delta)
            if ytd > peak:
                peak = ytd
                peak_date = rec.date
            if hurdle is not None and lock_ytd is None and ytd >= hurdle:
                lock_ytd = ytd
                lock_date = rec.date
        final = float(g["delta"].sum())
        net = final if lock_ytd is None else float(lock_ytd)
        window = g if lock_date is None else g[g["date"] <= lock_date]
        stress = _stress(window)
        end = start + net
        year_trades = trades[trades["year"] == int(year)]
        if lock_date is None:
            kept = year_trades
            skipped = year_trades.iloc[0:0]
        else:
            kept = year_trades[year_trades["session"] <= lock_date]
            skipped = year_trades[year_trades["session"] > lock_date]
        rows.append(
            {
                "year": int(year),
                "days": int(len(window)),
                "days_skipped": int(len(g) - len(window)),
                "trades": int(len(kept)),
                "skipped_trades": int(len(skipped)),
                "skipped_trade_net_usd": float(skipped["net_usd"].sum()) if len(skipped) else 0.0,
                "net_usd": net,
                "final_net_usd": final,
                "tail_net_usd": final - net,
                "peak_net_usd": peak,
                "peak_return": peak / start if start else 0.0,
                "peak_date": "" if peak_date is None else str(peak_date),
                "stress_dd_usd": stress,
                "net_over_stress": (net / abs(stress)) if stress else 0.0,
                "start_equity_100k": start,
                "end_equity_100k": end,
                "return_on_start_equity": (net / start) if start else 0.0,
                "final_return": (final / start) if start else 0.0,
                "stopped": lock_date is not None,
                "stop_date": "" if lock_date is None else str(lock_date),
            }
        )
        paper = end
    return pd.DataFrame(rows)


def sleeve_after_stop(trades: pd.DataFrame, board: pd.DataFrame) -> pd.DataFrame:
    parts = []
    for row in board.itertuples(index=False):
        if not row.stopped:
            continue
        stop = pd.to_datetime(row.stop_date).date()
        skipped = trades[(trades["year"] == row.year) & (trades["session"] > stop)]
        if len(skipped):
            parts.append(skipped[["sleeve", "net_usd"]])
    if not parts:
        return pd.DataFrame(columns=["sleeve", "trades", "net_usd"])
    raw = pd.concat(parts, ignore_index=True)
    return (
        raw.groupby("sleeve", dropna=False)
        .agg(trades=("net_usd", "size"), net_usd=("net_usd", "sum"))
        .reset_index()
        .sort_values("net_usd")
    )


def write_chart(boards: dict[str, pd.DataFrame]) -> Path:
    fig, ax = plt.subplots(figsize=(10.5, 5.2))
    for name, board in boards.items():
        ax.plot(board["year"], board["end_equity_100k"], marker="o", ms=3.5, label=name)
    ax.set_yscale("log")
    ax.set_xlabel("Year")
    ax.set_ylabel("Compounded equity (log, start $100k)")
    ax.set_title("TOP3 x10 — flat after the first daily close through the year hurdle")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    path = OUT / "charts" / "compound_equity.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def md_table(board: pd.DataFrame) -> str:
    header = (
        "| year | trades | skipped | net | tail | stress | N/S | return | start | end | stop |"
    )
    sep = "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---|"
    lines = [header, sep]
    for row in board.itertuples(index=False):
        lines.append(
            "| %d | %d | %d | %s | %s | %s | %.2f | %s | %s | %s | %s |"
            % (
                row.year,
                row.trades,
                row.skipped_trades,
                _money(row.net_usd),
                _money(row.tail_net_usd),
                _money(row.stress_dd_usd),
                row.net_over_stress,
                _pct(row.return_on_start_equity),
                _money(row.start_equity_100k),
                _money(row.end_equity_100k),
                row.stop_date,
            )
        )
    return "\n".join(lines)


def summary_stats(board: pd.DataFrame) -> dict:
    rets = board["return_on_start_equity"]
    end = float(board["end_equity_100k"].iloc[-1])
    n = len(board)
    cagr = (end / START_EQUITY) ** (1.0 / n) - 1.0 if end > 0 else float("nan")
    return {
        "end_equity": end,
        "net": end - START_EQUITY,
        "cagr": float(cagr),
        "years_stopped": int(board["stopped"].sum()),
        "trades": int(board["trades"].sum()),
        "skipped_trades": int(board["skipped_trades"].sum()),
        "tail_net": float(board["tail_net_usd"].sum()),
        "worst_return": float(rets.min()),
        "best_return": float(rets.max()),
        "losing_years": int((rets < 0).sum()),
        "avg_return": float(rets.mean()),
        "worst_ns": float(board["net_over_stress"].min()),
        "avg_ns": float(board["net_over_stress"].mean()),
        "worst_stress": float(board["stress_dd_usd"].min()),
        "n_years": n,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    eq = load_equity()
    trades = load_trades()
    published = pd.read_csv(PUBLISHED)
    baseline = simulate(eq, trades, None)
    merged = baseline.merge(published, on="year", suffixes=("_cal", "_pub"))
    net_gap = float((merged["net_usd_cal"] - merged["net_usd_pub"]).abs().max())
    stress_gap = float((merged["stress_dd_usd_cal"] - merged["stress_dd_usd_pub"]).abs().max())
    if stress_gap > 0.05:
        raise SystemExit("baseline stress drifted from published yearly board by %.4f" % stress_gap)
    if abs(float(baseline["net_usd"].sum()) - float(published["net_usd"].sum())) > 0.05:
        raise SystemExit("calendar net does not match published total")

    boards = {"baseline": baseline}
    sleeves = {}
    for target in TARGETS:
        key = "stop_%d" % int(round(target * 100))
        boards[key] = simulate(eq, trades, target)
        sleeves[key] = sleeve_after_stop(trades, boards[key])
        boards[key].to_csv(OUT / ("yearly_%s.csv" % key), index=False)
        sleeves[key].to_csv(OUT / ("skipped_by_sleeve_%s.csv" % key), index=False)
    baseline.to_csv(OUT / "yearly_baseline.csv", index=False)

    # Peak vs final on the unfiltered calendar path (baseline hurdles).
    path = baseline[
        [
            "year",
            "trades",
            "final_net_usd",
            "final_return",
            "peak_net_usd",
            "peak_return",
            "peak_date",
            "start_equity_100k",
        ]
    ].copy()
    path["giveback_usd"] = (path["peak_net_usd"] - path["final_net_usd"]).clip(lower=0)
    path["giveback_pp"] = path["giveback_usd"] / path["start_equity_100k"]
    for target in TARGETS:
        key = int(round(target * 100))
        stopped = boards["stop_%d" % key]
        # First-passage dates on the BASELINE equity path, not the recompounded one.
        # Recompute quickly from baseline deltas so a prior stop cannot move the date.
        path["first_%d" % key] = ""
        path["tail_%d" % key] = 0.0
    # Fill first-passage from a single baseline walk (start equity is baseline).
    paper = float(START_EQUITY)
    first_rows = []
    for year, g in eq.groupby("year", sort=True):
        start = paper
        ytd = 0.0
        final = float(g["delta"].sum())
        stamps = {t: "" for t in TARGETS}
        locks = {t: None for t in TARGETS}
        for rec in g.itertuples(index=False):
            ytd += float(rec.delta)
            for target in TARGETS:
                if locks[target] is None and ytd >= target * start:
                    locks[target] = ytd
                    stamps[target] = str(rec.date)
        row = {"year": int(year)}
        for target in TARGETS:
            key = int(round(target * 100))
            row["first_%d" % key] = stamps[target]
            row["tail_%d" % key] = 0.0 if locks[target] is None else final - float(locks[target])
        first_rows.append(row)
        paper += final
    path = path.drop(columns=[c for c in path.columns if c.startswith("first_") or c.startswith("tail_")])
    path = path.merge(pd.DataFrame(first_rows), on="year", how="left")
    pub_ret = published[["year", "return_on_start_equity"]].rename(
        columns={"return_on_start_equity": "published_entry_year_return"}
    )
    path = path.merge(pub_ret, on="year", how="left")
    path.to_csv(OUT / "baseline_peak_vs_final.csv", index=False)

    stats = {name: summary_stats(board) for name, board in boards.items()}
    pd.DataFrame([{"book": name, **row} for name, row in stats.items()]).to_csv(
        OUT / "comparison.csv", index=False
    )
    chart = write_chart(boards)

    touched = []
    for target in TARGETS:
        key = int(round(target * 100))
        hit = path[path["first_%d" % key].astype(str).str.len() > 0]
        touched.append(
            {
                "target": target,
                "years_touched": int(len(hit)),
                "tail_net": float(hit["tail_%d" % key].sum()) if len(hit) else 0.0,
                "years_tail_negative": int((hit["tail_%d" % key] < -1.0).sum()) if len(hit) else 0,
                "years_tail_positive": int((hit["tail_%d" % key] > 1.0).sum()) if len(hit) else 0,
            }
        )

    lines = []
    lines.append("# TOP3 x10 year-target stop")
    lines.append("")
    lines.append("Book: Asia Range + Monday OR + NAS100 Clean Break x10.")
    lines.append("State: `%s`" % STATE)
    lines.append(
        "Parent deep-check: `live/state/top3_active_demo_portfolio/deep_check/top3_asia_monday_cleanbreak_cb10x`"
    )
    lines.append("")
    lines.append("## Rule")
    lines.append("")
    lines.append(
        "Paper equity starts at $100,000 and compounds by calendar-year realized PnL on "
        "`equity_curve.csv`. A year stops after the first daily close that is already through "
        "10, 15, or 20 percent of that year's starting equity. That day's PnL is kept. Later "
        "days in the calendar year are flat. The hurdle is rebuilt from the stopped equity, so "
        "a lock changes the next year's dollar target."
    )
    lines.append("")
    lines.append(
        "This is an end-of-day lock. It does not assume an intraday flatten exactly at the "
        "percentage. Stress is the published year-local intrabar peak-to-trough, cut off after "
        "the lock session. Years that never print the hurdle keep the published stress."
    )
    lines.append("")
    lines.append(
        "Calendar-year net matches the published entry-year net except where a trade's session "
        "and its realized mark fall in different years. Max |year net| gap vs the published "
        "board is %s. Total net matches. Max |stress| gap is %.4f."
        % (_money(net_gap), stress_gap)
    )
    lines.append("")
    lines.append("## Did a 20 percent year get traded back down?")
    lines.append("")
    lines.append(
        "Peak is the highest daily realized year-to-date PnL, divided by baseline start equity. "
        "Tail is the PnL from the day after the first print through year-end, on the baseline "
        "hurdles (not re-compounded)."
    )
    lines.append("")
    lines.append("| target | years that printed it | tail after the print | years tail lost | years tail made |")
    lines.append("|---:|---:|---:|---:|---:|")
    for row in touched:
        lines.append(
            "| %.0f%% | %d | %s | %d | %d |"
            % (
                100 * row["target"],
                row["years_touched"],
                _money(row["tail_net"]),
                row["years_tail_negative"],
                row["years_tail_positive"],
            )
        )
    lines.append("")
    lines.append("| year | published | calendar final | peak | giveback | first 20 | tail 20 | first 15 | tail 15 | first 10 | tail 10 |")
    lines.append("|---:|---:|---:|---:|---:|:---|---:|:---|---:|:---|---:|")
    for row in path.itertuples(index=False):
        lines.append(
            "| %d | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                row.year,
                _pct(row.published_entry_year_return),
                _pct(row.final_return),
                _pct(row.peak_return),
                _pct(row.giveback_pp),
                row.first_20,
                _money(row.tail_20),
                row.first_15,
                _money(row.tail_15),
                row.first_10,
                _money(row.tail_10),
            )
        )
    lines.append("")
    lines.append("## Re-compounded books")
    lines.append("")
    lines.append("| book | end equity | net | compound / year-row | years stopped | worst year | losing years | avg N/S | worst stress | tail given up |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for name, row in stats.items():
        lines.append(
            "| %s | %s | %s | %s | %d | %s | %d | %.2f | %s | %s |"
            % (
                name,
                _money(row["end_equity"]),
                _money(row["net"]),
                _pct(row["cagr"]),
                row["years_stopped"],
                _pct(row["worst_return"]),
                row["losing_years"],
                row["avg_ns"],
                _money(row["worst_stress"]),
                _money(row["tail_net"]),
            )
        )
    lines.append("")
    for name, board in boards.items():
        if name == "baseline":
            continue
        lines.append("### %s" % name)
        lines.append("")
        lines.append(md_table(board))
        lines.append("")
        sl = sleeves[name]
        if len(sl):
            lines.append("Trades with a session date after the lock (sleeve net is the campaign net, which can differ from the equity-curve tail when a session straddles the daily mark):")
            lines.append("")
            lines.append("| sleeve | trades | net |")
            lines.append("|---|---:|---:|")
            for row in sl.itertuples(index=False):
                lines.append("| %s | %d | %s |" % (row.sleeve, int(row.trades), _money(row.net_usd)))
            lines.append("")
    lines.append("Chart: `%s`" % chart)
    text = "\n".join(lines) + "\n"
    (OUT / "SUMMARY.md").write_text(text, encoding="utf-8")
    (OUT / "run_meta.json").write_text(
        json.dumps(
            {
                "state": str(STATE),
                "targets": list(TARGETS),
                "net_gap_vs_published_year": net_gap,
                "stress_gap_vs_published_year": stress_gap,
                "stats": stats,
                "touched": touched,
                "rule": "eod lock on daily realized equity after ytd return >= target",
            },
            indent=2,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )
    print(text)


if __name__ == "__main__":
    main()
