"""4h charts for small-SL 2c fade ($1k risk, half + open).

Charts every filled month from ``liq_run_fade_2c_half_open_r1000/trades_all.csv``.
Overlays liq box, entry / $1k stop / half target / month open, and scale-out path.
Legend **lower right**.

Hub: ``…/liq_run_fade_2c_half_open_r1000_charts/``
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import pandas as pd

from .gbpusd_quarterly_4h_charts import NY, plot_candles as plot_candles_4h, shade_weeks
from .monthly_atr4_helpers import load_1h, month_windows
from .monthly_open_atr_extension_band_lookback_hp_charts import (
    LIQ_DN_COLOR,
    LIQ_UP_COLOR,
    MONTH_OPEN_COLOR,
    LiquidityRun,
    detect_liquidity_run,
    _ny_ts,
)
from .monthly_open_atr_extension_band_trade_charts import _resample_ohlc
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS

REPO = Path(__file__).resolve().parents[1]
TRADES_ALL = (
    REPO
    / "live"
    / "state"
    / "monthly_open_atr_extension_band"
    / "liq_run_fade_2c_half_open_r1000"
    / "trades_all.csv"
)
DEFAULT_OUT = (
    REPO
    / "live"
    / "state"
    / "monthly_open_atr_extension_band"
    / "liq_run_fade_2c_half_open_r1000_charts"
)

ENTRY_COLOR = "#6a1b9a"
STOP_LVL_COLOR = "#c62828"
HALF_COLOR = "#00838f"
EXIT_TARGET = "#2e7d32"
EXIT_STOP = "#b71c1c"
EXIT_EOM = "#ef6c00"
PNG_BATCH_BYTES = 18 * 1024 * 1024
PNG_MAX_PER_EMAIL = 18


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _parse_ts(val: object) -> pd.Timestamp:
    ts = pd.Timestamp(val)
    if ts.tzinfo is None:
        return ts.tz_localize(NY)
    return ts.tz_convert(NY)


def _leg_events(
    *,
    bars_1h: pd.DataFrame,
    side: str,
    entry_ts: pd.Timestamp,
    exit_ts: pd.Timestamp,
    t1: pd.Timestamp,
    target_half: float,
    target_open: float,
    stop: float,
    tp_half: int,
    tp_open: int,
    exit_reason: str,
) -> List[Tuple[pd.Timestamp, float, str]]:
    """Recover half/open/stop timestamps from 1h path (same priority as sim)."""
    events: List[Tuple[pd.Timestamp, float, str]] = []
    after = bars_1h[(bars_1h.index >= entry_ts) & (bars_1h.index < t1)]
    half_done = False
    for ts, row in after.iterrows():
        hi = float(row["high"])
        lo = float(row["low"])
        if not half_done:
            if (side == "short" and hi >= stop) or (side == "long" and lo <= stop):
                events.append((ts, stop, "stop"))
                return events
            if (side == "short" and lo <= target_half) or (side == "long" and hi >= target_half):
                if tp_half:
                    events.append((ts, target_half, "half"))
                half_done = True
                if tp_open and (
                    (side == "short" and lo <= target_open) or (side == "long" and hi >= target_open)
                ):
                    events.append((ts, target_open, "open"))
                    return events
                continue
        else:
            if (side == "short" and hi >= stop) or (side == "long" and lo <= stop):
                events.append((ts, stop, "stop"))
                return events
            if tp_open and (
                (side == "short" and lo <= target_open) or (side == "long" and hi >= target_open)
            ):
                events.append((ts, target_open, "open"))
                return events
    # EOM / recorded exit
    events.append((_parse_ts(exit_ts), float("nan"), str(exit_reason)))
    return events


def plot_month(
    *,
    bars_4h: pd.DataFrame,
    bars_1h: pd.DataFrame,
    year: int,
    month: int,
    t0: pd.Timestamp,
    t1: pd.Timestamp,
    liq: Optional[LiquidityRun],
    trade: pd.Series,
    out_path: Path,
) -> None:
    window = bars_4h[(bars_4h.index >= t0) & (bars_4h.index < t1)].copy()
    fig, ax = plt.subplots(figsize=(20, 8.2))
    shade_weeks(ax, t0, t1)
    if not window.empty:
        plot_candles_4h(ax, window)

    month_open = float(trade["month_open"])
    entry = float(trade["entry"])
    stop = float(trade["stop"])
    target_half = float(trade["target_half"])
    target_open = float(trade["target_open"])
    side = str(trade["side"])
    entry_ts = _parse_ts(trade["entry_ts"])
    exit_ts = _parse_ts(trade["exit_ts"])
    reason = str(trade["exit_reason"])
    pnl = float(trade["pnl_usd"])

    ax.axhline(month_open, color=MONTH_OPEN_COLOR, lw=1.4, ls="--", alpha=0.9, label="month open")
    ax.axhline(entry, color=ENTRY_COLOR, lw=1.2, ls=":", alpha=0.9, label="entry")
    ax.axhline(stop, color=STOP_LVL_COLOR, lw=1.1, ls="-.", alpha=0.85, label="stop ($1k / 25pt)")
    ax.axhline(target_half, color=HALF_COLOR, lw=1.2, ls="--", alpha=0.9, label="half target")

    if liq is not None:
        color = LIQ_UP_COLOR if liq.side == "up" else LIQ_DN_COLOR
        x0 = mdates.date2num(liq.t_open.to_pydatetime())
        x1 = mdates.date2num(liq.t_liq.to_pydatetime())
        y0 = min(liq.month_open, liq.p_liq)
        y1 = max(liq.month_open, liq.p_liq)
        ax.add_patch(
            Rectangle(
                (x0, y0),
                max(x1 - x0, 1e-4),
                max(y1 - y0, 1e-4),
                linewidth=2.0,
                edgecolor=color,
                facecolor=color,
                alpha=0.18,
                zorder=3,
                label="liq run (%s %.0fpt)" % (liq.side, liq.ext_pts),
            )
        )

    ax.scatter(
        [entry_ts.to_pydatetime()],
        [entry],
        marker="^" if side == "long" else "v",
        s=70,
        color=ENTRY_COLOR,
        zorder=6,
        label="fill",
    )

    events = _leg_events(
        bars_1h=bars_1h,
        side=side,
        entry_ts=entry_ts,
        exit_ts=exit_ts,
        t1=t1,
        target_half=target_half,
        target_open=target_open,
        stop=stop,
        tp_half=int(trade["tp_half"]),
        tp_open=int(trade["tp_open"]),
        exit_reason=reason,
    )
    prev_t, prev_px = entry_ts, entry
    labeled = {"half": False, "open": False, "stop": False, "eom": False}
    for ts, px, kind in events:
        if pd.isna(px):
            px = float(trade["entry"])  # fallback; prefer close path
            # use recorded exit from legs if possible
            px = float(trade.get("target_open") if "open" in reason else stop) if "stop" in reason else float(
                trade["target_open"] if int(trade["tp_open"]) else trade["target_half"]
            )
            if "eom" in reason:
                seg = bars_1h[(bars_1h.index >= exit_ts) & (bars_1h.index <= exit_ts)]
                px = float(seg["close"].iloc[0]) if not seg.empty else float(trade["target_half"])
        color = {
            "half": HALF_COLOR,
            "open": EXIT_TARGET,
            "stop": EXIT_STOP,
        }.get(kind, EXIT_EOM)
        lab = None
        if kind in labeled and not labeled[kind]:
            lab = "exit %s" % kind
            labeled[kind] = True
        ax.plot(
            [prev_t.to_pydatetime(), ts.to_pydatetime()],
            [prev_px, px],
            color=color,
            lw=1.7,
            alpha=0.9,
            zorder=5,
        )
        ax.scatter([ts.to_pydatetime()], [px], marker="o", s=50, color=color, zorder=6, label=lab)
        ax.annotate(kind, xy=(ts.to_pydatetime(), px), xytext=(4, 6), textcoords="offset points", fontsize=8, color=color)
        prev_t, prev_px = ts, px

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
    ax.grid(True, alpha=0.25)
    ax.set_title(
        "NQ %04d-%02d  |  4h  |  2c $1k SL  half+open  |  %s  net=$%+.0f"
        % (year, month, reason, pnl),
        fontsize=12,
        fontweight="bold",
        pad=10,
    )
    ax.legend(loc="lower right", fontsize=9, framealpha=0.92)
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def _email_batches(pngs: Sequence[Path], output_root: Path, body_intro: str) -> None:
    if not pngs:
        return
    batches: List[List[Path]] = []
    cur: List[Path] = []
    cur_bytes = 0
    for p in pngs:
        sz = p.stat().st_size if p.exists() else 0
        if cur and (len(cur) >= PNG_MAX_PER_EMAIL or cur_bytes + sz > PNG_BATCH_BYTES):
            batches.append(cur)
            cur, cur_bytes = [], 0
        cur.append(p)
        cur_bytes += sz
    if cur:
        batches.append(cur)
    for i, batch in enumerate(batches, start=1):
        subj = "potions: NQ 2c $1k SL charts (%d/%d)" % (i, len(batches))
        body = body_intro + "\nBatch %d/%d — %d PNGs\n" % (i, len(batches), len(batch))
        send_email(subject=subj, body=body, attachments=list(batch))
        _progress(output_root, "EMAIL batch %d/%d n=%d" % (i, len(batches), len(batch)))


def run(*, output_root: Path, email: bool = False) -> int:
    if output_root.exists():
        import shutil

        shutil.rmtree(output_root)
    charts_dir = output_root / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    trades = pd.read_csv(TRADES_ALL)
    fills = trades[trades["exit_reason"].astype(str) != "no_fill"].copy()
    _progress(output_root, "RUN fills=%d" % len(fills))

    spec = MARKETS["NQ"]
    bars = load_1h(spec)
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    bars_ny = bars.tz_convert(NY)
    bars_4h = _resample_ohlc(bars_ny, "4h")

    win_by: Dict[Tuple[int, int], Tuple[pd.Timestamp, pd.Timestamp]] = {}
    for year, month, m0, m1 in month_windows(bars, None, None):
        win_by[(int(year), int(month))] = (m0, m1)

    pngs: List[Path] = []
    index_rows: List[dict] = []
    for _, tr in fills.sort_values(["year", "month"]).iterrows():
        year, month = int(tr["year"]), int(tr["month"])
        if (year, month) not in win_by:
            continue
        t0, t1 = win_by[(year, month)]
        t0n, t1n = _ny_ts(t0), _ny_ts(t1)
        month_open = float(tr["month_open"])
        liq = detect_liquidity_run(
            bars_1h=bars_ny,
            year=year,
            month=month,
            month_open=month_open,
            t0=t0n,
            t1=t1n,
        )
        out_path = charts_dir / ("%04d_%02d.png" % (year, month))
        plot_month(
            bars_4h=bars_4h,
            bars_1h=bars_ny,
            year=year,
            month=month,
            t0=t0n,
            t1=t1n,
            liq=liq,
            trade=tr,
            out_path=out_path,
        )
        pngs.append(out_path)
        index_rows.append(
            {
                "year": year,
                "month": month,
                "exit_reason": str(tr["exit_reason"]),
                "pnl_usd": float(tr["pnl_usd"]),
                "tp_half": int(tr["tp_half"]),
                "tp_open": int(tr["tp_open"]),
                "chart": str(out_path.relative_to(output_root)),
            }
        )
        if len(pngs) % 25 == 0:
            _progress(output_root, "CHARTS %d" % len(pngs))

    pd.DataFrame(index_rows).to_csv(output_root / "index.csv", index=False)
    summary = "\n".join(
        [
            "# NQ 2c $1k SL half+open — 4h trade charts",
            "",
            "Source: `liq_run_fade_2c_half_open_r1000/trades_all.csv`",
            "Charts: **%d** (all fills)" % len(pngs),
            "Net: **$%+.0f**" % float(fills["pnl_usd"].sum()),
            "Legend: **lower right**",
            "",
            "Hub: `%s`" % output_root,
            "",
        ]
    )
    (output_root / "SUMMARY.md").write_text(summary, encoding="utf-8")
    (output_root / "EMAIL.txt").write_text(summary, encoding="utf-8")
    (output_root / "RUN_COMPLETE.json").write_text(
        json.dumps({"ok": True, "n_charts": len(pngs)}, indent=2) + "\n", encoding="utf-8"
    )
    _progress(output_root, "DONE charts=%d" % len(pngs))
    if email:
        send_email(subject="potions: NQ 2c $1k SL charts complete (%d)" % len(pngs), body=summary)
        _email_batches(pngs, output_root, summary)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    try:
        return run(output_root=args.output_root, email=args.email)
    except Exception:
        tb = traceback.format_exc()
        _progress(args.output_root, "FAILED\n" + tb)
        if args.email:
            send_email(subject="potions: 2c $1k SL charts FAILED", body=tb[-4000:])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
