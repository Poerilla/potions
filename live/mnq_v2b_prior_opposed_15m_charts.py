from __future__ import annotations

import argparse
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .v2b_st_pmc_alignment_study import REPO, Trade, load_strategy_trades
from .v2b_strategy_cross_market_replay import _rth_bars, load_1m_by_ny_date_any


NY = "America/New_York"


def plot_candles(ax, df: pd.DataFrame, *, width_days: float) -> None:
    if df.empty:
        return
    x = mdates.date2num(df.index.to_pydatetime())
    colors = np.where(df["close"] >= df["open"], "#168a5a", "#c43d3d")
    ax.vlines(x, df["low"], df["high"], color=colors, linewidth=1.0, alpha=0.9, zorder=3)
    for xi, o, c, color in zip(x, df["open"], df["close"], colors):
        bottom = min(o, c)
        height = max(abs(c - o), 0.01)
        ax.add_patch(
            plt.Rectangle(
                (xi - width_days / 2.0, bottom),
                width_days,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.5,
                alpha=0.82,
                zorder=4,
            )
        )


def resample_15m(rth: pd.DataFrame) -> pd.DataFrame:
    if rth.empty:
        return rth
    return rth.resample("15min", label="right", closed="right").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna(subset=["open", "high", "low", "close"])


def load_unit_campaigns(unit_trades: Path) -> Dict[str, pd.DataFrame]:
    df = pd.read_csv(unit_trades)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True).dt.tz_convert(NY)
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True).dt.tz_convert(NY)
    df["entry_price"] = pd.to_numeric(df["entry_price"], errors="coerce")
    df["exit_price"] = pd.to_numeric(df["exit_price"], errors="coerce")
    df["net_usd"] = pd.to_numeric(df["net_usd"], errors="coerce").fillna(0.0)
    return {str(k): g.copy() for k, g in df.groupby("trade_id")}


def trade_by_id(trades: List[Trade]) -> Dict[str, Trade]:
    return {t.trade_id: t for t in trades}


def draw_trade_markers(ax, *, campaign: pd.DataFrame, prior: Optional[Trade]) -> None:
    entry = campaign.iloc[0]
    side = str(entry["direction"]).lower()
    entry_ts = pd.Timestamp(entry["entry_ts"])
    entry_px = float(entry["entry_price"])
    exit_ts = pd.Timestamp(campaign["exit_ts"].max())
    net = float(campaign["net_usd"].sum())
    color = "#006dce" if side == "long" else "#7b3fb2"
    ax.scatter([entry_ts], [entry_px], s=90, color=color, marker="^" if side == "long" else "v", zorder=8, label="v2b entry")
    ax.axvline(entry_ts, color=color, linewidth=1.4, alpha=0.85)
    ax.axvline(exit_ts, color=color, linewidth=1.0, alpha=0.7, linestyle="--")
    for _idx, row in campaign.iterrows():
        reason = str(row["exit_reason"])
        marker = "o" if reason in {"tp1", "tp2"} else "x"
        ax.scatter([pd.Timestamp(row["exit_ts"])], [float(row["exit_price"])], s=50, color=color, marker=marker, zorder=8)
    ax.text(
        entry_ts,
        entry_px,
        " v2b %s $%.0f" % (side, net),
        color=color,
        fontsize=8,
        va="bottom",
        zorder=9,
    )
    if prior is not None:
        st_color = "#d1495b" if prior.side == "short" else "#1b998b"
        ax.scatter([prior.entry_ts], [prior.entry], s=75, color=st_color, marker="s", zorder=8, label="prior ST+PMC")
        ax.axvline(prior.entry_ts, color=st_color, linewidth=1.0, alpha=0.75)
        ax.text(
            prior.entry_ts,
            prior.entry,
            " ST+PMC %s" % prior.side,
            color=st_color,
            fontsize=8,
            va="top",
            zorder=9,
        )


def add_or_levels(ax, rth: pd.DataFrame) -> None:
    opening = rth[
        (rth.index.time >= pd.Timestamp("09:30").time())
        & (rth.index.time < pd.Timestamp("09:45").time())
    ]
    if opening.empty:
        return
    rh = float(opening["high"].max())
    rl = float(opening["low"].min())
    rng = rh - rl
    for value, label, color, style in [
        (rh, "OR high", "#455a64", "-"),
        (rl, "OR low", "#455a64", "-"),
        (rh + rng, "+1R", "#2e7d32", "--"),
        (rl - rng, "-1R", "#c62828", "--"),
        (rh + 2 * rng, "+2R", "#2e7d32", ":"),
        (rl - 2 * rng, "-2R", "#c62828", ":"),
    ]:
        ax.axhline(value, color=color, linestyle=style, linewidth=0.9, alpha=0.65)
        ax.text(rth.index[0], value, " " + label, color=color, fontsize=7, va="bottom")


def build_charts(
    *,
    output_root: Path,
    campaign_regimes: Path,
    unit_trades: Path,
    st_fills: Path,
    st_strategy_id: str,
    dbn: Path,
    max_charts: Optional[int],
    force: bool,
) -> None:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    regimes = pd.read_csv(campaign_regimes)
    regimes = regimes[regimes["regime"].astype(str) == "not_aligned_prior_opposed"].copy()
    regimes["base_1_1_3_net"] = pd.to_numeric(regimes["base_1_1_3_net"], errors="coerce").fillna(0.0)
    regimes = regimes.sort_values(["session", "entry_ts", "trade_id"])
    if max_charts is not None:
        regimes = regimes.head(max_charts)

    campaigns = load_unit_campaigns(unit_trades)
    st_trades = load_strategy_trades(st_fills, strategy_id=st_strategy_id, point_value=2.0, fee_per_unit=1.50)
    st_by_id = trade_by_id(st_trades)

    print("Loading MNQ 1m bars...", flush=True)
    bars_by_day = load_1m_by_ny_date_any(dbn.resolve(), "mnq")

    rows = []
    for idx, row in enumerate(regimes.itertuples(index=False), start=1):
        session = date.fromisoformat(str(row.session))
        campaign = campaigns.get(str(row.trade_id))
        if campaign is None or campaign.empty:
            continue
        rth = _rth_bars(bars_by_day.get(session), session)
        if rth.empty:
            continue
        candles = resample_15m(rth)
        candles = compute_supertrend(candles, atr_len=14, multiplier=3.0)
        prior = st_by_id.get(str(row.prior_st_trade_id))

        fig, (ax, vol_ax) = plt.subplots(
            2,
            1,
            figsize=(17, 9),
            sharex=True,
            gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04},
        )
        plot_candles(ax, candles, width_days=(15 / (24 * 60)) * 0.7)
        bull = candles["supertrend"].where(candles["supertrend_trend"] == 1)
        bear = candles["supertrend"].where(candles["supertrend_trend"] == -1)
        ax.plot(candles.index, bull, color="#009c5b", linewidth=1.5, label="15m ST bull")
        ax.plot(candles.index, bear, color="#d62728", linewidth=1.5, label="15m ST bear")
        add_or_levels(ax, rth)
        draw_trade_markers(ax, campaign=campaign, prior=prior)
        ax.set_title(
            "MNQ v2b prior-opposed ST+PMC branch - %s - %s - net $%.0f"
            % (row.session, row.side, float(row.base_1_1_3_net))
        )
        ax.set_ylabel("MNQ")
        ax.grid(True, color="#dedede", linewidth=0.6, alpha=0.75)
        ax.legend(loc="upper left", fontsize=8)

        colors = np.where(candles["close"] >= candles["open"], "#168a5a", "#c43d3d")
        vol_ax.bar(candles.index, candles["volume"], width=(15 / (24 * 60)) * 0.7, color=colors, alpha=0.45)
        vol_ax.set_ylabel("Vol")
        vol_ax.grid(True, axis="y", color="#e6e6e6", linewidth=0.5)
        vol_ax.xaxis.set_major_locator(mdates.HourLocator(interval=1, tz=candles.index.tz))
        vol_ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=candles.index.tz))
        vol_ax.set_xlabel("Time (America/New_York)")
        fig.autofmt_xdate()

        rel = Path("charts") / ("%03d_%s_%s_%s.png" % (idx, row.session, row.side, "win" if float(row.base_1_1_3_net) > 0 else "loss"))
        out = output_root / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=135, bbox_inches="tight")
        plt.close(fig)
        rows.append(
            {
                "idx": idx,
                "session": str(row.session),
                "side": str(row.side),
                "v2b_trade_id": str(row.trade_id),
                "prior_st_trade_id": str(row.prior_st_trade_id),
                "net": float(row.base_1_1_3_net),
                "chart": str(rel),
            }
        )
        if idx % 50 == 0:
            print("  charted %d/%d" % (idx, len(regimes)), flush=True)

    lines = [
        "# MNQ v2b Prior-Opposed ST+PMC 15m Charts",
        "",
        "Subset: v2b `S_1_1_3` campaigns where MNQ hourly ST+PMC had already fired in the opposite direction earlier in the same session.",
        "",
        "This is the strongest timing/regime branch from the weighting study and is best read as a possible failed-ST / intraday reversal structure.",
        "",
        "| # | Session | Side | Net | Chart |",
        "|---:|---|---|---:|---|",
    ]
    for item in rows:
        lines.append(
            "| {idx} | {session} | {side} | ${net:,.2f} | [{chart}]({chart}) |".format(**item)
        )
    (output_root / "INDEX.md").write_text("\n".join(lines))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build 15m charts for the MNQ v2b prior-opposed ST+PMC branch.")
    parser.add_argument("--output-root", type=Path, default=REPO / "live/state/mnq_v2b_regime_weighting_research/charts/prior_opposed_15m")
    parser.add_argument("--campaign-regimes", type=Path, default=REPO / "live/state/mnq_v2b_regime_weighting_research/campaign_regimes.csv")
    parser.add_argument("--unit-trades", type=Path, default=REPO / "live/state/v2b_sizing_sweep/states/mnq_v2b_sizing_S_1_1_3/unit_trades.csv")
    parser.add_argument("--st-fills", type=Path, default=REPO / "live/state/hourly_st_pmc_strategyplugin_variants_cross_market/mnq/combined_state/fills.csv")
    parser.add_argument("--st-strategy-id", default="mnq_hourly_st_pmc_sl25_tp75_3r")
    parser.add_argument("--dbn", type=Path, default=REPO / "mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst")
    parser.add_argument("--max-charts", type=int, default=None)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    build_charts(
        output_root=args.output_root,
        campaign_regimes=args.campaign_regimes,
        unit_trades=args.unit_trades,
        st_fills=args.st_fills,
        st_strategy_id=args.st_strategy_id,
        dbn=args.dbn,
        max_charts=args.max_charts,
        force=not args.no_force,
    )
    print("Wrote %s" % (args.output_root / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
