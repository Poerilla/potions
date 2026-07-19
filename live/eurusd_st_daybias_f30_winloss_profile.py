"""Profile f30-week day-bias winners vs losers + yearly daily charts.

- Weekday distribution of entry days (winners vs losers)
- Prior-week features: new high / new low vs prior 4 weeks; bias vs prior-week direction
- ≥5 yearly daily-candle charts: alternating week shading, green/red dots on entry days
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import PatchCollection

from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .ym_hourly_st_pmc_retest_replay import concat_all_1m


REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "eurusd_st_daybias_f30_winloss_profile"
NY = "America/New_York"
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _load_trades(path: Path) -> pd.DataFrame:
    t = pd.read_csv(path)
    t["entry_ts"] = pd.to_datetime(t["entry_ts"], utc=True)
    t["exit_ts"] = pd.to_datetime(t["exit_ts"], utc=True)
    t["entry_day"] = t["entry_ts"].dt.tz_convert(NY).dt.date
    t["weekday"] = t["entry_ts"].dt.tz_convert(NY).dt.dayofweek
    t["weekday_name"] = t["weekday"].map(lambda i: WEEKDAYS[int(i)])
    t["winner"] = t["usd"] > 0
    return t


def _daily_ohlc(one_m: pd.DataFrame) -> pd.DataFrame:
    d = one_m.copy()
    d["ny"] = d.index.tz_convert(NY).date
    daily = (
        d.groupby("ny")
        .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
        .sort_index()
    )
    daily.index = pd.to_datetime(daily.index)
    daily.index = daily.index.tz_localize(NY)
    # ISO week key (Mon-start)
    iso = daily.index.isocalendar()
    daily["iso_year"] = iso.year.astype(int)
    daily["iso_week"] = iso.week.astype(int)
    daily["week_key"] = daily["iso_year"].astype(str) + "-W" + daily["iso_week"].astype(str).str.zfill(2)
    daily["weekday"] = daily.index.dayofweek
    return daily


def _prior_week_features(daily: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    """Attach prior-week structure features to each trade (by entry_day)."""
    weekly = daily.groupby("week_key", sort=True).agg(
        w_open=("open", "first"),
        w_high=("high", "max"),
        w_low=("low", "min"),
        w_close=("close", "last"),
    )
    week_starts = daily.groupby("week_key").apply(lambda g: g.index.min())
    weekly["start"] = week_starts
    weekly = weekly.sort_values("start")
    keys = list(weekly.index)
    prev_key = {keys[i]: keys[i - 1] for i in range(1, len(keys))}
    day_to_week = {ts.date(): wk for ts, wk in zip(daily.index, daily["week_key"])}

    rows = []
    for _, t in trades.iterrows():
        d = t["entry_day"]
        wk = day_to_week.get(d)
        if wk is None or wk not in prev_key:
            rows.append(
                {
                    "entry_week": wk,
                    "prior_week": None,
                    "prior_week_dir": None,
                    "prior_week_new_high": False,
                    "prior_week_new_low": False,
                    "prior_week_inline": False,
                    "prior_week_opposed": False,
                }
            )
            continue
        pwk = prev_key[wk]
        pw = weekly.loc[pwk]
        # prior week new high/low vs the 4 weeks before that prior week
        lookback = [k for k in keys if weekly.loc[k, "start"] < pw["start"]][-4:]
        if lookback:
            prior_max = float(weekly.loc[lookback, "w_high"].max())
            prior_min = float(weekly.loc[lookback, "w_low"].min())
        else:
            prior_max = np.nan
            prior_min = np.nan
        pw_high = float(pw["w_high"])
        pw_low = float(pw["w_low"])
        pw_dir = "bull" if float(pw["w_close"]) > float(pw["w_open"]) else "bear"
        bias_dir = "bull" if str(t["side"]) == "long" else "bear"
        rows.append(
            {
                "entry_week": wk,
                "prior_week": pwk,
                "prior_week_dir": pw_dir,
                "prior_week_new_high": bool(np.isfinite(prior_max) and pw_high > prior_max),
                "prior_week_new_low": bool(np.isfinite(prior_min) and pw_low < prior_min),
                "prior_week_inline": pw_dir == bias_dir,
                "prior_week_opposed": pw_dir != bias_dir,
            }
        )
    feat = pd.DataFrame(rows)
    return pd.concat([trades.reset_index(drop=True), feat], axis=1)


def _weekday_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for wd in range(5):  # trading week Mon-Fri
        sub = df[df["weekday"] == wd]
        w = sub[sub["winner"]]
        l = sub[~sub["winner"]]
        rows.append(
            {
                "weekday": WEEKDAYS[wd],
                "n": len(sub),
                "n_win": len(w),
                "n_loss": len(l),
                "win_rate_pct": round(100.0 * len(w) / len(sub), 1) if len(sub) else 0.0,
                "usd_sum": round(float(sub["usd"].sum()), 2),
                "usd_winners": round(float(w["usd"].sum()), 2) if len(w) else 0.0,
                "usd_losers": round(float(l["usd"].sum()), 2) if len(l) else 0.0,
                "pct_of_all_wins": 0.0,
                "pct_of_all_losses": 0.0,
            }
        )
    out = pd.DataFrame(rows)
    n_w = int(df["winner"].sum())
    n_l = int((~df["winner"]).sum())
    if n_w:
        out["pct_of_all_wins"] = (out["n_win"] / n_w * 100).round(1)
    if n_l:
        out["pct_of_all_losses"] = (out["n_loss"] / n_l * 100).round(1)
    return out


def _feature_table(df: pd.DataFrame) -> pd.DataFrame:
    feats = [
        ("prior_week_new_high", "Prior week new high (vs prior 4w)"),
        ("prior_week_new_low", "Prior week new low (vs prior 4w)"),
        ("prior_week_inline", "Prior week dir INLINE with bias"),
        ("prior_week_opposed", "Prior week dir OPPOSED to bias"),
    ]
    rows = []
    for col, label in feats:
        if col not in df.columns:
            continue
        for flag, subset_name in [(True, "yes"), (False, "no")]:
            sub = df[df[col] == flag]
            if sub.empty:
                continue
            w = sub[sub["winner"]]
            rows.append(
                {
                    "feature": label,
                    "value": subset_name,
                    "n": len(sub),
                    "n_win": len(w),
                    "win_rate_pct": round(100.0 * len(w) / len(sub), 1),
                    "usd_sum": round(float(sub["usd"].sum()), 2),
                    "avg_usd": round(float(sub["usd"].mean()), 2),
                }
            )
    # Cross: new high/low × inline/opposed among winners only share
    w = df[df["winner"]]
    l = df[~df["winner"]]
    for name, sub in [("winners", w), ("losers", l)]:
        if sub.empty:
            continue
        rows.append(
            {
                "feature": f"[{name}] new_high & inline",
                "value": "rate",
                "n": len(sub),
                "n_win": int(sub["winner"].sum()) if name == "winners" else 0,
                "win_rate_pct": round(
                    100.0
                    * ((sub["prior_week_new_high"] & sub["prior_week_inline"]).mean()),
                    1,
                ),
                "usd_sum": round(float(sub["usd"].sum()), 2),
                "avg_usd": round(float(sub["usd"].mean()), 2),
            }
        )
        rows.append(
            {
                "feature": f"[{name}] new_low & opposed",
                "value": "rate",
                "n": len(sub),
                "n_win": int(sub["winner"].sum()) if name == "winners" else 0,
                "win_rate_pct": round(
                    100.0
                    * ((sub["prior_week_new_low"] & sub["prior_week_opposed"]).mean()),
                    1,
                ),
                "usd_sum": round(float(sub["usd"].sum()), 2),
                "avg_usd": round(float(sub["usd"].mean()), 2),
            }
        )
    return pd.DataFrame(rows)


def _plot_year(
    daily: pd.DataFrame,
    entries: pd.DataFrame,
    year: int,
    out_path: Path,
) -> None:
    # Select calendar year in NY
    mask = daily.index.year == year
    d = daily.loc[mask].copy()
    if len(d) < 10:
        return
    # Entry dots for this year
    e = entries[entries["entry_ts"].dt.tz_convert(NY).dt.year == year].copy()

    fig, ax = plt.subplots(figsize=(14, 6))

    # Alternating week shading
    weeks = list(d.groupby("week_key", sort=True))
    for i, (wk, g) in enumerate(weeks):
        if i % 2 == 0:
            continue
        x0 = mdates.date2num(g.index.min().to_pydatetime())
        x1 = mdates.date2num(g.index.max().to_pydatetime()) + 0.9
        ax.axvspan(x0, x1, color="#dfe6e9", alpha=0.55, zorder=0)

    # Daily candles
    for ts, row in d.iterrows():
        x = mdates.date2num(ts.to_pydatetime())
        o, h, l, c = float(row.open), float(row.high), float(row.low), float(row.close)
        color = "#1e8449" if c >= o else "#922b21"
        ax.vlines(x, l, h, color=color, lw=0.8, zorder=2)
        body_lo, body_hi = min(o, c), max(o, c)
        if abs(body_hi - body_lo) < 1e-6:
            body_hi = body_lo + 1e-5
        ax.add_patch(
            mpatches.Rectangle(
                (x - 0.3, body_lo),
                0.6,
                body_hi - body_lo,
                facecolor=color,
                edgecolor=color,
                lw=0.5,
                zorder=3,
            )
        )

    # Entry dots at day's mid (close)
    if not e.empty:
        # map entry_day -> close for y
        close_map = {ts.date(): float(c) for ts, c in zip(d.index, d["close"])}
        for _, t in e.iterrows():
            day = t["entry_day"]
            if day not in close_map:
                continue
            x = mdates.date2num(pd.Timestamp(day, tz=NY).to_pydatetime())
            y = close_map[day]
            col = "#27ae60" if t["winner"] else "#e74c3c"
            ax.scatter([x], [y], s=28, c=col, zorder=5, edgecolors="white", linewidths=0.4)

    ax.set_xlim(
        mdates.date2num(d.index.min().to_pydatetime()) - 1,
        mdates.date2num(d.index.max().to_pydatetime()) + 1,
    )
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.set_title("EURUSD daily — %d  |  green=winning entry day  red=losing entry day  |  alt week shade" % year)
    ax.set_ylabel("Price")
    win_p = mpatches.Patch(color="#27ae60", label="Winning entry")
    loss_p = mpatches.Patch(color="#e74c3c", label="Losing entry")
    shade_p = mpatches.Patch(color="#dfe6e9", label="Alt. ISO week")
    ax.legend(handles=[win_p, loss_p, shade_p], loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--trades",
        type=Path,
        default=REPO / "live" / "state" / "eurusd_hourly_st_daybias_dca" / "trades_st_daybias_dca_f30_week.csv",
    )
    parser.add_argument("--output-root", type=Path, default=OUT)
    parser.add_argument(
        "--years",
        default="2016,2018,2020,2022,2024",
        help="Comma list of calendar years for daily charts (need ≥5)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)
    charts_dir = out / "charts_yearly_daily"
    charts_dir.mkdir(parents=True, exist_ok=True)

    print("Loading trades + daily...", flush=True)
    trades = _load_trades(args.trades)
    one_m_path, _ = ensure_eurusd_platform_files(REPO)
    one_m = concat_all_1m(load_fx_1m_by_ny_date(one_m_path, "EURUSD")).sort_index()
    one_m = one_m[(one_m.index >= "2015-01-01") & (one_m.index < "2026-04-01")]
    daily = _daily_ohlc(one_m)
    # fix: daily index name
    daily = daily.copy()
    enriched = _prior_week_features(daily, trades)
    enriched.to_csv(out / "trades_enriched.csv", index=False)

    wd = _weekday_table(enriched)
    wd.to_csv(out / "weekday_profile.csv", index=False)
    feat = _feature_table(enriched)
    feat.to_csv(out / "prior_week_features.csv", index=False)

    n_w = int(enriched["winner"].sum())
    n_l = int((~enriched["winner"]).sum())
    print("trades=%d winners=%d losers=%d net=$%.0f" % (len(enriched), n_w, n_l, enriched["usd"].sum()), flush=True)
    print("\nWeekday profile:", flush=True)
    print(wd.to_string(index=False), flush=True)
    print("\nPrior-week features:", flush=True)
    print(feat.to_string(index=False), flush=True)

    # Winner commonality summary rates
    w = enriched[enriched["winner"]]
    l = enriched[~enriched["winner"]]
    def rate(df, col):
        return 100.0 * float(df[col].mean()) if len(df) and col in df.columns else 0.0

    years = [int(x.strip()) for x in args.years.split(",") if x.strip()]
    # ensure ≥5
    if len(years) < 5:
        years = sorted(set(years) | {2016, 2018, 2020, 2022, 2024})[:5]

    index_lines = [
        "# EURUSD daily — f30 week entry win/loss markers",
        "",
        "Daily candles, alternating ISO-week shading, green/red dots = entry days.",
        "Source trades: honest break-fixed f30 week (`trades_st_daybias_dca_f30_week.csv`).",
        "",
        "| Year | Chart |",
        "|---|---|",
    ]
    for y in years:
        fname = "eurusd_daily_%d.png" % y
        print("Charting", y, "...", flush=True)
        _plot_year(daily, enriched, y, charts_dir / fname)
        if (charts_dir / fname).exists():
            index_lines.append("| %d | [%s](%s) |" % (y, fname, fname))

    (charts_dir / "INDEX.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")

    # SUMMARY
    lines = [
        "# f30 week — winner / loser profile",
        "",
        "Honest (break-fixed) f30-week research trades. n=%d · wins=%d · losses=%d · net=$%s."
        % (len(enriched), n_w, n_l, f"{enriched['usd'].sum():,.0f}"),
        "",
        "## Entry weekday",
        "",
        "| Weekday | n | Wins | Losses | WR | % of all wins | % of all losses | Net $ |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in wd.iterrows():
        lines.append(
            "| %s | %d | %d | %d | %.1f%% | %.1f%% | %.1f%% | $%s |"
            % (
                r["weekday"],
                r["n"],
                r["n_win"],
                r["n_loss"],
                r["win_rate_pct"],
                r["pct_of_all_wins"],
                r["pct_of_all_losses"],
                f"{r['usd_sum']:,.0f}",
            )
        )

    lines.extend(
        [
            "",
            "## Do winners share prior-week structure?",
            "",
            "| Feature | Among winners | Among losers |",
            "|---|---:|---:|",
            "| Prior week **new high** (vs prior 4w) | %.1f%% | %.1f%% |"
            % (rate(w, "prior_week_new_high"), rate(l, "prior_week_new_high")),
            "| Prior week **new low** (vs prior 4w) | %.1f%% | %.1f%% |"
            % (rate(w, "prior_week_new_low"), rate(l, "prior_week_new_low")),
            "| Prior week **inline** with bias | %.1f%% | %.1f%% |"
            % (rate(w, "prior_week_inline"), rate(l, "prior_week_inline")),
            "| Prior week **opposed** to bias | %.1f%% | %.1f%% |"
            % (rate(w, "prior_week_opposed"), rate(l, "prior_week_opposed")),
            "",
            "### Conditional win rates",
            "",
            "| Slice | n | WR | Net $ |",
            "|---|---:|---:|---:|",
        ]
    )
    for _, r in feat.iterrows():
        if r["value"] not in {"yes", "no"}:
            continue
        lines.append(
            "| %s = %s | %d | %.1f%% | $%s |"
            % (r["feature"], r["value"], r["n"], r["win_rate_pct"], f"{r['usd_sum']:,.0f}")
        )

    lines.extend(
        [
            "",
            "## Yearly daily charts",
            "",
            f"See [`charts_yearly_daily/INDEX.md`](charts_yearly_daily/INDEX.md) ({len(years)} years).",
            "",
            "CSV: `weekday_profile.csv`, `prior_week_features.csv`, `trades_enriched.csv`",
            "",
        ]
    )
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote", out / "SUMMARY.md", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
