from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Sequence

import pandas as pd

from .nq_weekly_mid_ma500_bias_replay import plot_week, to_hourly_with_ma
from .nq_ma500_retest_weekly_replay import weekly_c3_info, weekly_ohlc
from .replay_audit import POINT_VALUES
from .v2b_strategy_cross_market_replay import MARKETS
from .ym_weekly_chart_context import compute_weekly_context


REPO = Path(__file__).resolve().parents[1]
FEE_PER_UNIT = 1.50


def read_bars(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert("America/New_York")
    df = df.set_index("ts").sort_index()
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"]).copy()
    df["ma500"] = df["close"].rolling(500).mean()
    return df


def read_units(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if df.empty:
        return df
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True).dt.tz_convert("America/New_York")
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True).dt.tz_convert("America/New_York")
    df["side"] = df["direction"].astype(str).str.lower()
    df["net"] = pd.to_numeric(df["usd"], errors="coerce").fillna(0.0) - FEE_PER_UNIT
    for col in ["entry_price", "exit_price"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    week_start = df["entry_ts"].dt.normalize() - pd.to_timedelta(df["entry_ts"].dt.weekday, unit="D")
    df["week_start"] = week_start.dt.date.astype(str)
    return df


def render_market(source_root: Path, output_root: Path, market: str, charts: int, force: bool) -> dict[str, object]:
    cfg = MARKETS[market]
    slug = "%s_weekly_mid_ma500_bias" % market
    state_root = source_root / "states" / slug
    audit_root = source_root / "audits" / slug
    out = output_root / market
    if out.exists() and force:
        shutil.rmtree(out)
    (out / "charts").mkdir(parents=True, exist_ok=True)

    bars = read_bars(state_root / "bars" / ("%s_15m.csv" % cfg.instrument))
    units = read_units(audit_root / "unit_fills.csv")
    chart_rows: list[dict[str, object]] = []
    if units.empty:
        (out / "INDEX.md").write_text("# %s Broker-Like Trade Charts\n\nNo trades.\n" % cfg.instrument, encoding="utf-8")
        return {"market": market, "charts": 0}

    ym_context = market == "ym"

    weeks = []
    for week_start_str, trades in units.groupby("week_start"):
        week_start = pd.Timestamp(week_start_str, tz="America/New_York")
        week_end = week_start + pd.Timedelta(days=7)
        week_15m = bars[(bars.index >= week_start) & (bars.index < week_end)].copy()
        if week_15m.empty:
            continue
        prev = weekly_ohlc(bars, week_start - pd.Timedelta(days=7), week_start)
        if not prev:
            continue
        week_1h = to_hourly_with_ma(week_15m, "ma500")
        if week_1h.empty:
            continue
        prev_levels = {
            "prev_high": float(prev["high"]),
            "prev_low": float(prev["low"]),
            "prev_mid": float(prev["low"]) + 0.5 * (float(prev["high"]) - float(prev["low"])),
            "prev_close": float(prev["close"]),
        }
        score = abs(float(trades["net"].sum())) + len(trades) * 200.0
        weeks.append((score, week_start, week_15m, week_1h, trades.copy(), prev_levels, weekly_c3_info(bars, week_start)))

    weeks.sort(key=lambda item: item[0], reverse=True)
    for idx, (_score, week_start, week_15m, week_1h, trades, prev_levels, c3_info) in enumerate(weeks[:charts], start=1):
        rel = Path("charts") / ("%03d_%s.png" % (idx, week_start.date().isoformat()))
        net = float(trades["net"].sum())
        title = "%s broker-like weekly 50%% MA500 - %s - net $%.0f - %d trades" % (
            cfg.instrument,
            week_start.date().isoformat(),
            net,
            len(trades),
        )
        weekly_context = compute_weekly_context(bars, week_start) if ym_context else None
        plot_week(
            out / rel,
            week_15m,
            week_1h,
            week_start,
            prev_levels,
            trades,
            pd.DataFrame(),
            c3_info,
            title,
            cfg.instrument,
            weekly_context=weekly_context,
        )
        row = {
            "idx": idx,
            "week_start": week_start.date().isoformat(),
            "weekly_c3": "" if not c3_info else "%s_%s" % (c3_info["direction"], "hit" if c3_info["hit"] else "miss"),
            "net": net,
            "trades": int(len(trades)),
            "chart": str(rel),
        }
        if weekly_context:
            row.update(
                {
                    "prev_doji": weekly_context["prev_doji"],
                    "prev_body_pct": round(100.0 * float(weekly_context["prev_body_pct"]), 1),
                    "weeks_since_ma10_cross": weekly_context["weeks_since_ma10_cross"],
                    "ma10_cross_direction": weekly_context["ma10_cross_direction"] or "",
                    "ma10_cross_week": weekly_context["ma10_cross_week"] or "",
                    "ma10_at_cross": weekly_context["ma10_at_cross"],
                }
            )
        chart_rows.append(row)

    pd.DataFrame(chart_rows).to_csv(out / "chart_index.csv", index=False)
    lines = [
        "# %s Broker-Like Weekly 50%% + MA500 Trade Charts" % cfg.instrument,
        "",
        "Charts are reconstructed from the actual StrategyPlugin/PaperBroker unit fills and persisted 15-minute replay bars.",
        "",
        "| # | Week | Weekly C3 | Net | Trades | Chart |",
        "|---:|---|---|---:|---:|---|",
    ]
    for row in chart_rows:
        lines.append(
            "| {idx} | {week_start} | {weekly_c3} | ${net:,.2f} | {trades} | [{chart}]({chart}) |".format(**row)
        )
    (out / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    return {"market": market, "charts": len(chart_rows), "index": out / "INDEX.md"}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chart actual broker-like weekly 50% + MA500 fills.")
    parser.add_argument("--source-root", type=Path, default=REPO / "live/state/weekly_mid_ma500_bias_broker_like_nq_ym_mnq")
    parser.add_argument("--output-root", type=Path, default=REPO / "live/state/weekly_mid_ma500_bias_broker_like_nq_ym_mnq/charts")
    parser.add_argument("--market", action="append", choices=sorted(MARKETS), default=None)
    parser.add_argument("--charts", type=int, default=80)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    markets = args.market or ["nq"]
    if args.output_root.exists() and not args.no_force and not args.market:
        shutil.rmtree(args.output_root)
    args.output_root.mkdir(parents=True, exist_ok=True)
    rows = [render_market(args.source_root, args.output_root, market, args.charts, force=not args.no_force) for market in markets]
    existing = []
    if (args.output_root / "INDEX.md").exists() and args.market:
        for line in (args.output_root / "INDEX.md").read_text(encoding="utf-8").splitlines():
            if line.startswith("| ") and not line.startswith("| Market") and not line.startswith("|---"):
                parts = [p.strip() for p in line.strip("|").split("|")]
                if parts and parts[0].upper() not in {m.upper() for m in markets}:
                    existing.append(line)
    lines = ["# Broker-Like Weekly 50% + MA500 Charts", "", "| Market | Charts | Report |", "|---|---:|---|"]
    for row in rows:
        rel = Path(row["market"]) / "INDEX.md"
        lines.append("| %s | %d | [%s](%s) |" % (str(row["market"]).upper(), int(row["charts"]), rel, rel))
    for line in existing:
        lines.append(line)
    (args.output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote %s" % (args.output_root / "INDEX.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
