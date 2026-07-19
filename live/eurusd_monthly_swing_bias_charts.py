"""Sample EURUSD charts for monthly-swing → v2b (aligned / opposed).

Charts RTH 5m candles with:

- Opening range (09:30–09:45 NY) — entries are stops on this boundary
- NY 09:30 open + month open (the arm filter levels)
- Entry / TP / stop fills from the S_1_1_3 book

Even sample across the full campaign for each mode.
"""

from __future__ import annotations

import argparse
import shutil
from datetime import date, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytz

from .eurusd_prior_opposed_5m_charts import _resample_5m, _select_trades
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .nq_v2b_prior_opposed_15m_charts import (
    _draw_v2b_trade,
    _load_v2b_fill_groups,
    _load_v2b_trades,
    _plot_candles,
)


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
NY_TZ = pytz.timezone(NY)
INSTRUMENT = "EURUSD"
POINT_VALUE = 100000.0
FEE_PER_UNIT = 7.0
OR_START = time(9, 30)
OR_END = time(9, 45)
RTH_END = time(16, 0)


def _opening_range(df_1m: pd.DataFrame) -> Optional[Tuple[float, float, pd.Timestamp, pd.Timestamp]]:
    if df_1m.empty:
        return None
    opening = df_1m[(df_1m.index.time >= OR_START) & (df_1m.index.time < OR_END)]
    if opening.empty:
        return None
    return (
        float(opening["high"].max()),
        float(opening["low"].min()),
        opening.index[0],
        opening.index[-1] + pd.Timedelta(minutes=1),
    )


def _load_bias_lookup(bias_csv: Path) -> Dict[str, dict]:
    if not bias_csv.exists():
        return {}
    df = pd.read_csv(bias_csv)
    return {str(r["session"]): r.to_dict() for _, r in df.iterrows()}


def build_mode_charts(
    *,
    mode: str,
    output_root: Path,
    one_m: Path,
    fills: Path,
    bias_csv: Path,
    max_charts: int,
    force: bool,
) -> Path:
    import live.nq_v2b_prior_opposed_15m_charts as base

    base.POINT_VALUE = POINT_VALUE
    base.FEE_PER_UNIT = FEE_PER_UNIT

    mode_root = output_root / mode
    if force and mode_root.exists():
        shutil.rmtree(mode_root)
    charts_dir = mode_root / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    trades = sorted(_load_v2b_trades(fills), key=lambda item: item.entry_ts)
    if not trades:
        raise SystemExit("No trades in %s" % fills)
    selected = _select_trades(trades, max_charts)
    groups = _load_v2b_fill_groups(fills)
    bias = _load_bias_lookup(bias_csv)

    print(
        "Charting monthly-swing %s: %d / %d trades..." % (mode, len(selected), len(trades)),
        flush=True,
    )
    bars_by_day = load_fx_1m_by_ny_date(one_m, INSTRUMENT)

    rows: List[Dict[str, object]] = []
    for idx, trade in enumerate(selected, start=1):
        session = trade.entry_ts.date()
        session_s = session.isoformat()
        meta = bias.get(session_s, {})
        raw = bars_by_day.get(session)
        if raw is None or raw.empty:
            continue
        win_1m = raw[(raw.index.time >= OR_START) & (raw.index.time < RTH_END)].copy()
        if win_1m.empty:
            continue
        if "volume" not in win_1m.columns:
            win_1m["volume"] = 0.0
        candles = _resample_5m(win_1m)
        if candles.empty:
            continue
        or_levels = _opening_range(win_1m)
        r_open = meta.get("rth_open_0930", meta.get("yesterday_open", meta.get("day_open")))
        rth_open = float(r_open) if r_open not in (None, "") and r_open == r_open else None
        month_open = (
            float(meta["month_open"]) if meta.get("month_open") not in (None, "") and meta.get("month_open") == meta.get("month_open") else None
        )
        if rth_open is None and not win_1m.empty:
            rth_open = float(win_1m.iloc[0]["open"])
        if month_open is None:
            month_open = rth_open

        fills_g = groups[trade.trade_id]
        chart_start = candles.index[0]
        chart_end = NY_TZ.localize(pd.Timestamp(session).to_pydatetime().replace(hour=16, minute=0))

        fig, (ax, vol_ax) = plt.subplots(
            2,
            1,
            figsize=(16, 8.5),
            sharex=True,
            gridspec_kw={"height_ratios": [4, 1], "hspace": 0.04},
        )
        _plot_candles(ax, candles, width_days=(5 / (24 * 60)) * 0.7)

        if or_levels is not None:
            or_h, or_l, or_t0, or_t1 = or_levels
            ax.axhspan(or_l, or_h, color="#90caf9", alpha=0.22, zorder=1, label="Opening range")
            ax.axvspan(or_t0, or_t1, color="#90caf9", alpha=0.10, zorder=0)
            ax.hlines(or_h, chart_start, chart_end, colors="#1565c0", linestyles="-", linewidth=1.05, alpha=0.85)
            ax.hlines(or_l, chart_start, chart_end, colors="#1565c0", linestyles="-", linewidth=1.05, alpha=0.85)

        if month_open is not None:
            ax.hlines(
                month_open,
                chart_start,
                chart_end,
                colors="#6a1b9a",
                linestyles="--",
                linewidth=1.4,
                alpha=0.95,
                label="Month open %.5f" % month_open,
            )
        if rth_open is not None:
            ax.hlines(
                rth_open,
                chart_start,
                chart_end,
                colors="#00838f",
                linestyles=":",
                linewidth=1.5,
                alpha=0.95,
                label="NY 09:30 open %.5f" % rth_open,
            )

        _draw_v2b_trade(ax, trade, fills_g)

        marker = str(meta.get("marker_bias") or "?")
        trade_bias = str(meta.get("trade_bias") or trade.side)
        ax.set_title(
            "EURUSD monthly-swing %s S_1_1_3 — %s — %s — net $%.0f  (marker %s → trade %s)"
            % (mode, session_s, trade.side, trade.net_usd, marker, trade_bias)
        )
        ax.set_ylabel(INSTRUMENT)
        ax.grid(True, color="#dedede", linewidth=0.6, alpha=0.75)
        ax.legend(loc="upper left", fontsize=8)
        ax.set_xlim(chart_start, chart_end)

        colors = np.where(candles["close"] >= candles["open"], "#168a5a", "#c43d3d")
        vol_ax.bar(candles.index, candles["volume"], width=(5 / (24 * 60)) * 0.7, color=colors, alpha=0.45)
        vol_ax.set_ylabel("Vol")
        vol_ax.grid(True, axis="y", color="#e6e6e6", linewidth=0.5)
        vol_ax.xaxis.set_major_locator(mdates.HourLocator(interval=1, tz=candles.index.tz))
        vol_ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=candles.index.tz))
        vol_ax.set_xlabel("Time (America/New_York)")
        vol_ax.set_xlim(chart_start, chart_end)
        fig.autofmt_xdate()

        rel = Path("charts") / (
            "%03d_%s_%s_%s.png" % (idx, session_s, trade.side, "win" if trade.net_usd > 0 else "loss")
        )
        out = mode_root / rel
        fig.savefig(out, dpi=130, bbox_inches="tight")
        plt.close(fig)

        rows.append(
            {
                "idx": idx,
                "session": session_s,
                "side": trade.side,
                "net": trade.net_usd,
                "marker_bias": marker,
                "trade_bias": trade_bias,
                "rth_open_0930": rth_open if rth_open is not None else "",
                "month_open": month_open if month_open is not None else "",
                "chart": str(rel),
            }
        )
        if idx % 10 == 0:
            print("  %s charted %d/%d" % (mode, idx, len(selected)), flush=True)

    pd.DataFrame(rows).to_csv(mode_root / "chart_manifest.csv", index=False)
    lines = [
        "# EURUSD monthly-swing → v2b — **%s** sample charts" % mode,
        "",
        "Even sample of **%d** trades. RTH 5m with OR boundary entries, **NY 09:30 open**, month open, fills."
        % len(rows),
        "",
        "- Fills: `%s`" % fills.as_posix(),
        "- Bias ledger: `%s`" % bias_csv.as_posix(),
        "",
        "| # | Session | Side | Marker | Trade | Net | 09:30 open | Month open | Chart |",
        "|---:|---|---|---|---|---:|---:|---:|---|",
    ]
    for item in rows:
        lines.append(
            "| {idx} | {session} | {side} | {marker_bias} | {trade_bias} | ${net:,.2f} | {rth_open_0930} | {month_open} | [{chart}]({chart}) |".format(
                **{
                    **item,
                    "rth_open_0930": ("%.5f" % item["rth_open_0930"]) if item["rth_open_0930"] != "" else "",
                    "month_open": ("%.5f" % item["month_open"]) if item["month_open"] != "" else "",
                }
            )
        )
    (mode_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return mode_root


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live/state/eurusd_v2b_monthly_swing_compare/charts",
    )
    parser.add_argument("--max-charts", type=int, default=25, help="Charts per mode (default 25)")
    parser.add_argument("--modes", nargs="+", default=["aligned", "opposed"], choices=["aligned", "opposed"])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    one_m, _ = ensure_eurusd_platform_files(REPO, force=False)
    args.output_root.mkdir(parents=True, exist_ok=True)
    written = []
    for mode in args.modes:
        state = REPO / "live/state" / ("eurusd_v2b_monthly_swing_%s_S_1_1_3" % mode)
        fills = state / "states" / ("eurusd_v2b_monthly_swing_%s_S_1_1_3" % mode) / "fills.csv"
        bias_csv = state / "monthly_swing_bias_by_session.csv"
        if not fills.exists():
            raise SystemExit("Missing fills for %s: %s" % (mode, fills))
        out = build_mode_charts(
            mode=mode,
            output_root=args.output_root,
            one_m=one_m,
            fills=fills,
            bias_csv=bias_csv,
            max_charts=args.max_charts,
            force=args.force,
        )
        written.append(out)
        print("Wrote %s" % (out / "INDEX.md"), flush=True)

    lines = [
        "# EURUSD monthly-swing → v2b sample charts",
        "",
        "Aligned (follow marker) and opposed (fade marker). Filter = NY 09:30 open + month open; entries on OR boundary.",
        "",
    ]
    for out in written:
        lines.append("- [`%s`](%s/INDEX.md)" % (out.name, out.name))
    (args.output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote %s" % (args.output_root / "INDEX.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
