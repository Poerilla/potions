"""Sample EURUSD charts for hourly-ST-sweep → v2b trades.

Evenly samples campaign trades (default 100) and charts each session as
NY RTH **1m** candles with:

- Opening range 09:30–09:45
- Hour-complete hourly ATR SuperTrend trail (bull/bear)
- Marker at the ST take that set the day direction + arm-after time
- v2b entry / TP / stop fills
"""

from __future__ import annotations

import argparse
import shutil
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytz

from .eurusd_prior_opposed_5m_charts import _select_trades
from .eurusd_v2b_hourly_st_sweep import build_hourly_st
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .nq_v2b_prior_opposed_15m_charts import (
    _draw_v2b_trade,
    _load_v2b_fill_groups,
    _load_v2b_trades,
    _plot_candles,
)
from .ym_hourly_st_pmc_retest_replay import concat_all_1m


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
NY_TZ = pytz.timezone(NY)
INSTRUMENT = "EURUSD"
POINT_VALUE = 100000.0
FEE_PER_UNIT = 7.0
OR_START = time(9, 30)
OR_END = time(9, 45)
RTH_END = time(16, 0)
ST_BULL = "#00897b"
ST_BEAR = "#c62828"
TAKE_COLOR = "#e65100"


def _opening_range(df_1m: pd.DataFrame):
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


def _load_take_lookup(path: Path) -> Dict[str, dict]:
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    out = {}
    for _, row in df.iterrows():
        out[str(row["session"])] = row.to_dict()
    return out


def build_charts(
    *,
    output_root: Path,
    one_m_path: Path,
    fills_path: Path,
    take_csv: Path,
    max_charts: int,
    force: bool,
    sizing_label: str,
) -> int:
    import live.nq_v2b_prior_opposed_15m_charts as base

    base.POINT_VALUE = POINT_VALUE
    base.FEE_PER_UNIT = FEE_PER_UNIT

    if force and output_root.exists():
        shutil.rmtree(output_root)
    charts_dir = output_root / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    trades = sorted(_load_v2b_trades(fills_path), key=lambda item: item.entry_ts)
    if not trades:
        raise SystemExit("No trades in %s" % fills_path)
    selected = _select_trades(trades, max_charts)
    groups = _load_v2b_fill_groups(fills_path)
    takes = _load_take_lookup(take_csv)

    print(
        "Loading EURUSD 1m for ST-sweep charts (%d / %d trades, sizing %s)..."
        % (len(selected), len(trades), sizing_label),
        flush=True,
    )
    bars_by_day = load_fx_1m_by_ny_date(one_m_path, INSTRUMENT)
    one_m = concat_all_1m(bars_by_day).sort_index()
    print("Computing hourly ST for overlays...", flush=True)
    hourly_st = build_hourly_st(one_m)

    rows: List[Dict[str, object]] = []
    for idx, trade in enumerate(selected, start=1):
        session = trade.entry_ts.date()
        session_s = session.isoformat()
        meta = takes.get(session_s, {})
        raw = bars_by_day.get(session)
        if raw is None or raw.empty:
            continue
        win_1m = raw[(raw.index.time >= OR_START) & (raw.index.time < RTH_END)].copy()
        if win_1m.empty:
            continue
        if "volume" not in win_1m.columns:
            win_1m["volume"] = 0.0

        or_levels = _opening_range(win_1m)
        session_start = pd.Timestamp(datetime.combine(session, OR_START), tz=NY)
        session_end = pd.Timestamp(datetime.combine(session, RTH_END), tz=NY)

        # Hourly ST available in/around the session (hour-complete series).
        st_win = hourly_st[
            (hourly_st["available_at"] >= session_start - pd.Timedelta(hours=6))
            & (hourly_st.index < session_end)
        ].copy()

        fig, ax = plt.subplots(1, 1, figsize=(17, 8.2))
        _plot_candles(ax, win_1m, width_days=(1.0 / (24 * 60)) * 0.7)

        if or_levels is not None:
            or_h, or_l, or_t0, or_t1 = or_levels
            ax.axhspan(or_l, or_h, color="#90caf9", alpha=0.22, zorder=1, label="Opening range")
            ax.axvspan(or_t0, or_t1, color="#bbdefb", alpha=0.16, zorder=0, label="OR window")
            ax.hlines(or_h, session_start, session_end, colors="#1565c0", linestyles="-", linewidth=1.05, alpha=0.9)
            ax.hlines(or_l, session_start, session_end, colors="#1565c0", linestyles="-", linewidth=1.05, alpha=0.9)

        if not st_win.empty:
            # Step the trail at availability time so the chart matches the gate.
            plot_ts = st_win["available_at"]
            bull = st_win["supertrend"].where(st_win["supertrend_trend"] == 1)
            bear = st_win["supertrend"].where(st_win["supertrend_trend"] == -1)
            ax.step(plot_ts, bull, where="post", color=ST_BULL, linewidth=1.35, alpha=0.95, label="Hourly ST bull")
            ax.step(plot_ts, bear, where="post", color=ST_BEAR, linewidth=1.35, alpha=0.95, label="Hourly ST bear")

        take_ts_raw = meta.get("take_ts") or ""
        arm_raw = meta.get("arm_after_ts") or ""
        st_level = meta.get("st_level")
        bias = str(meta.get("trade_bias") or trade.side)
        if take_ts_raw not in ("", None) and take_ts_raw == take_ts_raw:
            take_ts = pd.Timestamp(take_ts_raw)
            if take_ts.tzinfo is None:
                take_ts = take_ts.tz_localize(NY)
            else:
                take_ts = take_ts.tz_convert(NY)
            y = float(st_level) if st_level not in ("", None) and st_level == st_level else trade.entry_price
            marker = "^" if str(bias).lower().startswith("long") or bias == "Long" else "v"
            # Mapping: Long day came from bullish ST take; Short from bearish.
            if bias == "Long":
                marker = "v"  # took bullish trail below
                mcolor = ST_BULL
            else:
                marker = "^"  # took bearish trail above
                mcolor = ST_BEAR
            ax.axvline(take_ts, color=TAKE_COLOR, linewidth=1.2, alpha=0.85, zorder=6)
            ax.scatter([take_ts], [y], marker=marker, s=95, color=mcolor, zorder=9, label="ST take @ %s" % take_ts.strftime("%H:%M"))
            ax.annotate(
                "ST take\n%s" % take_ts.strftime("%H:%M"),
                xy=(take_ts, y),
                xytext=(8, 10),
                textcoords="offset points",
                fontsize=8,
                color=TAKE_COLOR,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.7, "pad": 1.5},
            )
        if arm_raw not in ("", None) and arm_raw == arm_raw:
            arm_ts = pd.Timestamp(arm_raw)
            if arm_ts.tzinfo is None:
                arm_ts = arm_ts.tz_localize(NY)
            else:
                arm_ts = arm_ts.tz_convert(NY)
            ax.axvline(arm_ts, color="#455a64", linewidth=1.0, linestyle=":", alpha=0.8, label="Arm after %s" % arm_ts.strftime("%H:%M"))

        fills_g = groups.get(trade.trade_id)
        if fills_g is not None and not fills_g.empty:
            _draw_v2b_trade(ax, trade, fills_g)

        ax.set_title(
            "EURUSD ST-sweep → v2b %s — %s — %s — net $%.0f  (bias %s)"
            % (sizing_label, session_s, trade.side, trade.net_usd, bias),
            fontsize=11,
        )
        ax.set_ylabel(INSTRUMENT)
        ax.set_xlabel("Time (America/New_York)")
        ax.set_xlim(session_start, session_end)
        ax.grid(True, color="#cfd8dc", linewidth=0.45, alpha=0.55)
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=1, tz=NY))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=NY))
        ax.legend(loc="upper left", fontsize=7, ncol=2)

        fname = "%03d_%s_%s_%s.png" % (
            idx,
            session_s,
            trade.side,
            "win" if trade.net_usd >= 0 else "loss",
        )
        out_path = charts_dir / fname
        fig.savefig(out_path, dpi=125, bbox_inches="tight")
        plt.close(fig)
        rows.append(
            {
                "idx": idx,
                "session": session_s,
                "side": trade.side,
                "bias": bias,
                "net_usd": round(float(trade.net_usd), 2),
                "take_ts": str(take_ts_raw or ""),
                "arm_after_ts": str(arm_raw or ""),
                "chart": "charts/%s" % fname,
            }
        )
        if idx % 20 == 0 or idx == len(selected):
            print("  %d / %d" % (idx, len(selected)), flush=True)

    pd.DataFrame(rows).to_csv(output_root / "chart_manifest.csv", index=False)
    lines = [
        "# EURUSD hourly-ST-sweep → v2b sample charts",
        "",
        "Even sample of **%d** trades from sizing **%s** (of %d campaign trades)."
        % (len(rows), sizing_label, len(trades)),
        "",
        "RTH 1m with OR, hour-complete hourly ST trail, ST-take marker, arm-after line, and v2b fills.",
        "",
        "| # | Session | Side | Bias | Net | Take | Arm after | Chart |",
        "|---:|---|---|---|---:|---|---|---|",
    ]
    for row in rows:
        take_hm = ""
        arm_hm = ""
        if row["take_ts"]:
            take_hm = pd.Timestamp(row["take_ts"]).tz_convert(NY).strftime("%H:%M")
        if row["arm_after_ts"]:
            arm_hm = pd.Timestamp(row["arm_after_ts"]).tz_convert(NY).strftime("%H:%M")
        lines.append(
            "| {idx} | {session} | {side} | {bias} | ${net_usd:,.0f} | {take} | {arm} | [{name}]({chart}) |".format(
                idx=row["idx"],
                session=row["session"],
                side=row["side"],
                bias=row["bias"],
                net_usd=float(row["net_usd"]),
                take=take_hm,
                arm=arm_hm,
                name=Path(str(row["chart"])).name,
                chart=row["chart"],
            )
        )
    lines.append("")
    (output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote %d charts → %s" % (len(rows), output_root), flush=True)
    return len(rows)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Sample charts for EURUSD ST-sweep v2b trades.")
    parser.add_argument(
        "--sizing",
        choices=("1_0_0", "1_1_1", "1_1_3"),
        default="1_0_0",
        help="Which replay book to chart (default 1_0_0).",
    )
    parser.add_argument("--max-charts", type=int, default=100)
    parser.add_argument("--force", action="store_true", default=True)
    parser.add_argument("--no-force", action="store_true")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
    )
    args = parser.parse_args(argv)

    one_m, _daily = ensure_eurusd_platform_files(REPO, force=False)
    replay_root = REPO / "live" / "state" / ("eurusd_v2b_hourly_st_sweep_%s" % args.sizing)
    if args.sizing == "1_0_0":
        sid = "eurusd_v2b_hourly_st_sweep_S_1_0_0"
    elif args.sizing == "1_1_1":
        sid = "eurusd_v2b_hourly_st_sweep_S_1_1_1"
    else:
        sid = "eurusd_v2b_hourly_st_sweep_S_1_1_3"
    fills = replay_root / "states" / sid / "fills.csv"
    take_csv = replay_root / "st_sweep_by_session.csv"
    if not fills.exists():
        raise SystemExit("Missing fills: %s" % fills)
    output_root = args.output_root or (
        REPO / "live" / "state" / ("eurusd_v2b_hourly_st_sweep_%s_charts" % args.sizing)
    )
    build_charts(
        output_root=output_root,
        one_m_path=one_m,
        fills_path=fills,
        take_csv=take_csv,
        max_charts=int(args.max_charts),
        force=not bool(args.no_force),
        sizing_label=args.sizing,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
