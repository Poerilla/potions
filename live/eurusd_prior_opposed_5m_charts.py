"""Build ~100 EURUSD prior-opposed v2b charts on 5-minute RTH candles."""

from __future__ import annotations

import argparse
import shutil
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .bars import rth_bars
from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .fx_data import load_fx_1m_by_ny_date
from .nq_v2b_prior_opposed_15m_charts import (
    FillTrade,
    _add_or_levels,
    _draw_st_trades,
    _draw_v2b_trade,
    _find_prior_opposite,
    _load_st_trades,
    _load_v2b_fill_groups,
    _load_v2b_trades,
    _plot_candles,
)


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
INSTRUMENT = "EURUSD"
POINT_VALUE = 100000.0
FEE_PER_UNIT = 7.0


def _resample_5m(rth: pd.DataFrame) -> pd.DataFrame:
    if rth.empty:
        return rth
    return (
        rth.resample("5min", label="right", closed="right")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open", "high", "low", "close"])
    )


def _select_trades(trades: List[FillTrade], max_charts: int) -> List[FillTrade]:
    if max_charts is None or len(trades) <= max_charts:
        return trades
    # Evenly spaced sample across the full campaign history.
    idx = np.linspace(0, len(trades) - 1, num=max_charts, dtype=int)
    seen = set()
    out: List[FillTrade] = []
    for i in idx:
        if int(i) in seen:
            continue
        seen.add(int(i))
        out.append(trades[int(i)])
    return out


def build_charts(
    *,
    output_root: Path,
    one_m: Path,
    v2b_fills: Path,
    st_fills: Path,
    st_strategy_id: str,
    max_charts: int,
    force: bool,
) -> None:
    import live.nq_v2b_prior_opposed_15m_charts as base

    base.POINT_VALUE = POINT_VALUE
    base.FEE_PER_UNIT = FEE_PER_UNIT

    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    v2b_trades = sorted(_load_v2b_trades(v2b_fills), key=lambda item: item.entry_ts)
    v2b_trades = _select_trades(v2b_trades, max_charts)
    v2b_groups = _load_v2b_fill_groups(v2b_fills)
    st_trades = _load_st_trades(st_fills, st_strategy_id)
    st_by_day: Dict[date, List[FillTrade]] = {}
    for trade in st_trades:
        st_by_day.setdefault(trade.entry_ts.date(), []).append(trade)

    print("Loading EURUSD 1m for 5m charts...", flush=True)
    bars_by_day = load_fx_1m_by_ny_date(one_m, INSTRUMENT)

    rows = []
    violations = 0
    for idx, trade in enumerate(v2b_trades, start=1):
        session = trade.entry_ts.date()
        rth = rth_bars(bars_by_day.get(session), session, dense=True)
        if rth.empty:
            continue
        candles = compute_supertrend(_resample_5m(rth), atr_len=14, multiplier=3.0)
        prior = _find_prior_opposite(trade, st_by_day)
        if prior is None:
            violations += 1
        session_st = [
            st
            for st in st_by_day.get(session, [])
            if st.entry_ts <= max(trade.exit_ts, trade.entry_ts) and st.exit_ts >= rth.index[0]
        ]
        fills = v2b_groups[trade.trade_id]

        fig, (ax, vol_ax) = plt.subplots(
            2,
            1,
            figsize=(17, 9),
            sharex=True,
            gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04},
        )
        _plot_candles(ax, candles, width_days=(5 / (24 * 60)) * 0.7)
        bull = candles["supertrend"].where(candles["supertrend_trend"] == 1)
        bear = candles["supertrend"].where(candles["supertrend_trend"] == -1)
        ax.plot(candles.index, bull, color="#009c5b", linewidth=1.2, label="5m ST bull")
        ax.plot(candles.index, bear, color="#d62728", linewidth=1.2, label="5m ST bear")
        _add_or_levels(ax, rth)
        _draw_st_trades(ax, session_st, prior)
        _draw_v2b_trade(ax, trade, fills)
        ax.set_title(
            "EURUSD prior-opposed ST+PMC -> v2b S_1_1_3 - %s - %s - net $%.0f"
            % (session.isoformat(), trade.side, trade.net_usd)
        )
        ax.set_ylabel(INSTRUMENT)
        ax.grid(True, color="#dedede", linewidth=0.6, alpha=0.75)
        ax.legend(loc="upper left", fontsize=8)

        colors = np.where(candles["close"] >= candles["open"], "#168a5a", "#c43d3d")
        vol_ax.bar(candles.index, candles["volume"], width=(5 / (24 * 60)) * 0.7, color=colors, alpha=0.45)
        vol_ax.set_ylabel("Vol")
        vol_ax.grid(True, axis="y", color="#e6e6e6", linewidth=0.5)
        vol_ax.xaxis.set_major_locator(mdates.HourLocator(interval=1, tz=candles.index.tz))
        vol_ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=candles.index.tz))
        vol_ax.set_xlabel("Time (America/New_York)")
        fig.autofmt_xdate()

        rel = Path("charts") / (
            "%03d_%s_%s_%s.png" % (idx, session.isoformat(), trade.side, "win" if trade.net_usd > 0 else "loss")
        )
        out = output_root / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=135, bbox_inches="tight")
        plt.close(fig)
        rows.append(
            {
                "idx": idx,
                "session": session.isoformat(),
                "side": trade.side,
                "net": trade.net_usd,
                "v2b_trade_id": trade.trade_id,
                "prior_st_trade_id": prior.trade_id if prior is not None else "",
                "prior_st_side": prior.side if prior is not None else "",
                "chart": str(rel),
            }
        )
        if idx % 25 == 0:
            print("  charted %d/%d" % (idx, len(v2b_trades)), flush=True)

    pd.DataFrame(rows).to_csv(output_root / "chart_manifest.csv", index=False)
    lines = [
        "# EURUSD v2b Prior-Opposed ST+PMC 5m Charts",
        "",
        "Evenly spaced sample across the full prior-opposed book. Each chart: 5m RTH candles, 5m Supertrend, OR levels, same-session ST+PMC, and the gated v2b campaign.",
        "",
        "- Source replay: `live/state/eurusd_v2b_prior_opposed_stpmc_broker_like/`",
        "- ST+PMC gate: `%s`" % st_strategy_id,
        "- Charts built: **%d**" % len(rows),
        "- Missing prior-opposite validations: **%d**" % violations,
        "",
        "| # | Session | Side | Net | Prior ST+PMC | Chart |",
        "|---:|---|---|---:|---|---|",
    ]
    for item in rows:
        lines.append(
            "| {idx} | {session} | {side} | ${net:,.2f} | {prior_st_side} | [{chart}]({chart}) |".format(**item)
        )
    (output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="EURUSD prior-opposed v2b 5m charts.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live/state/eurusd_v2b_prior_opposed_stpmc_broker_like/charts/prior_opposed_5m",
    )
    parser.add_argument("--one-m", type=Path, default=REPO / "fx" / "eurusd_1m.csv")
    parser.add_argument(
        "--v2b-fills",
        type=Path,
        default=REPO
        / "live/state/eurusd_v2b_prior_opposed_stpmc_broker_like/states/eurusd_v2b_prior_opposed_stpmc_only_S_1_1_3/fills.csv",
    )
    parser.add_argument(
        "--st-fills",
        type=Path,
        default=REPO
        / "live/state/eurusd_v2b_prior_opposed_stpmc_broker_like/st_pmc/states/eurusd_hourly_st_pmc_sl25_tp75_3r/fills.csv",
    )
    parser.add_argument("--st-strategy-id", default="eurusd_hourly_st_pmc_sl25_tp75_3r")
    parser.add_argument("--max-charts", type=int, default=100)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    build_charts(
        output_root=args.output_root,
        one_m=args.one_m,
        v2b_fills=args.v2b_fills,
        st_fills=args.st_fills,
        st_strategy_id=args.st_strategy_id,
        max_charts=args.max_charts,
        force=not args.no_force,
    )
    print("Wrote %s" % (args.output_root / "INDEX.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
