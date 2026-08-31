"""4h charts for unlimited HP 1:1 re-entry fills (liq_run_fade_1r1_reentry).

Charts each HP month with ≥1 fill from the unlimited open-touch re-entry book.
Overlays liq-run box, month open / entry / stop, and each attempt entry→exit.
Legend placed **lower right**.

Hub: ``live/state/monthly_open_atr_extension_band/liq_run_fade_1r1_reentry_hp_charts/``
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
import numpy as np
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
TRADES_HP = (
    REPO
    / "live"
    / "state"
    / "monthly_open_atr_extension_band"
    / "liq_run_fade_1r1_reentry"
    / "trades_hp.csv"
)
DEFAULT_OUT = (
    REPO
    / "live"
    / "state"
    / "monthly_open_atr_extension_band"
    / "liq_run_fade_1r1_reentry_hp_charts"
)

ENTRY_COLOR = "#6a1b9a"
STOP_LVL_COLOR = "#c62828"
TARGET_COLOR = MONTH_OPEN_COLOR
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


def _exit_color(reason: str) -> str:
    r = str(reason).lower()
    if r == "target":
        return EXIT_TARGET
    if r == "stop":
        return EXIT_STOP
    return EXIT_EOM


def plot_month(
    *,
    bars_4h: pd.DataFrame,
    year: int,
    month: int,
    month_open: float,
    t0: pd.Timestamp,
    t1: pd.Timestamp,
    liq: Optional[LiquidityRun],
    trades: pd.DataFrame,
    out_path: Path,
) -> None:
    window = bars_4h[(bars_4h.index >= t0) & (bars_4h.index < t1)].copy()
    fig, ax = plt.subplots(figsize=(20, 8.2))
    shade_weeks(ax, t0, t1)
    if not window.empty:
        plot_candles_4h(ax, window)

    ax.axhline(month_open, color=MONTH_OPEN_COLOR, lw=1.4, ls="--", alpha=0.9, label="month open / target")

    if liq is not None:
        color = LIQ_UP_COLOR if liq.side == "up" else LIQ_DN_COLOR
        x0 = mdates.date2num(liq.t_open.to_pydatetime())
        x1 = mdates.date2num(liq.t_liq.to_pydatetime())
        y0 = min(liq.month_open, liq.p_liq)
        y1 = max(liq.month_open, liq.p_liq)
        rect = Rectangle(
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
        ax.add_patch(rect)
        ax.axhline(liq.p_liq, color=ENTRY_COLOR, lw=1.2, ls=":", alpha=0.9, label="entry / p_liq")
        ax.axhline(float(trades.iloc[0]["stop"]), color=STOP_LVL_COLOR, lw=1.0, ls="-.", alpha=0.75, label="stop (1R)")

    # Plot each attempt
    labeled_entry = False
    labeled_exit = {"target": False, "stop": False, "eom": False}
    month_net = float(trades["pnl_usd"].sum())
    for _, tr in trades.sort_values("attempt").iterrows():
        et = pd.Timestamp(tr["entry_ts"])
        xt = pd.Timestamp(tr["exit_ts"])
        if et.tzinfo is None:
            et = et.tz_localize(NY)
        else:
            et = et.tz_convert(NY)
        if xt.tzinfo is None:
            xt = xt.tz_localize(NY)
        else:
            xt = xt.tz_convert(NY)
        ep = float(tr["entry"])
        xp = float(tr["exit_px"])
        reason = str(tr["exit_reason"])
        att = int(tr["attempt"])
        re = int(tr["reentry"])
        ec = _exit_color(reason)

        ax.plot(
            [et.to_pydatetime(), xt.to_pydatetime()],
            [ep, xp],
            color=ec,
            lw=1.6,
            alpha=0.85,
            zorder=5,
        )
        ax.scatter(
            [et.to_pydatetime()],
            [ep],
            marker="^" if tr["side"] == "long" else "v",
            s=55,
            color=ENTRY_COLOR,
            zorder=6,
            label="entry" if not labeled_entry else None,
        )
        labeled_entry = True
        exit_label = None
        if reason in labeled_exit and not labeled_exit[reason]:
            exit_label = "exit %s" % reason
            labeled_exit[reason] = True
        ax.scatter(
            [xt.to_pydatetime()],
            [xp],
            marker="o",
            s=45,
            color=ec,
            zorder=6,
            label=exit_label,
        )
        ax.annotate(
            "a%d%s" % (att, "*" if re else ""),
            xy=(xt.to_pydatetime(), xp),
            xytext=(4, 6),
            textcoords="offset points",
            fontsize=8,
            color=ec,
        )

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
    ax.grid(True, alpha=0.25)
    n_att = len(trades)
    n_re = int(trades["reentry"].sum())
    title = "NQ %04d-%02d  |  4h  |  HP unlimited re-entry  |  fills=%d re=%d  net=$%+.0f" % (
        year,
        month,
        n_att,
        n_re,
        month_net,
    )
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
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
        subj = "potions: NQ HP reentry charts (%d/%d)" % (i, len(batches))
        body = body_intro + "\nBatch %d/%d — %d PNGs\n" % (i, len(batches), len(batch))
        send_email(subject=subj, body=body, attachments=list(batch))
        _progress(output_root, "EMAIL batch %d/%d n=%d" % (i, len(batches), len(batch)))


def run(*, output_root: Path, email: bool = False) -> int:
    if output_root.exists():
        import shutil

        shutil.rmtree(output_root)
    charts_dir = output_root / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    if not TRADES_HP.exists():
        raise FileNotFoundError(TRADES_HP)

    trades = pd.read_csv(TRADES_HP)
    fills = trades[trades["exit_reason"].astype(str) != "no_fill"].copy()
    _progress(output_root, "RUN fills=%d months=%d" % (len(fills), fills.groupby(["year", "month"]).ngroups))

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
    for (year, month), g in fills.groupby(["year", "month"], sort=True):
        year, month = int(year), int(month)
        if (year, month) not in win_by:
            continue
        t0, t1 = win_by[(year, month)]
        t0n, t1n = _ny_ts(t0), _ny_ts(t1)
        month_open = float(g.iloc[0]["month_open"])
        liq = detect_liquidity_run(
            bars_1h=bars_ny,
            year=year,
            month=month,
            month_open=month_open,
            t0=t0n,
            t1=t1n,
        )
        slug = "%04d_%02d" % (year, month)
        out_path = charts_dir / ("%s.png" % slug)
        plot_month(
            bars_4h=bars_4h,
            year=year,
            month=month,
            month_open=month_open,
            t0=t0n,
            t1=t1n,
            liq=liq,
            trades=g,
            out_path=out_path,
        )
        pngs.append(out_path)
        index_rows.append(
            {
                "year": year,
                "month": month,
                "n_fills": int(len(g)),
                "n_reentry": int(g["reentry"].sum()),
                "net_usd": float(g["pnl_usd"].sum()),
                "chart": str(out_path.relative_to(output_root)),
            }
        )
        if len(pngs) % 20 == 0:
            _progress(output_root, "CHARTS %d" % len(pngs))

    idx = pd.DataFrame(index_rows)
    idx.to_csv(output_root / "index.csv", index=False)
    summary = "\n".join(
        [
            "# NQ HP unlimited re-entry — 4h trade charts",
            "",
            "Source: `liq_run_fade_1r1_reentry/trades_hp.csv`",
            "Months with fills: **%d** | fills: **%d** | re-entries: **%d**" % (
                len(idx),
                int(fills.shape[0]),
                int(fills["reentry"].sum()),
            ),
            "Net (HP fills): **$%+.0f**" % float(fills["pnl_usd"].sum()),
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
        send_email(subject="potions: NQ HP reentry charts complete (%d)" % len(pngs), body=summary)
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
            send_email(subject="potions: HP reentry charts FAILED", body=tb[-4000:])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
