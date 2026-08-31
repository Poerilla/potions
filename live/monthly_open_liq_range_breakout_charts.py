"""4h charts for envelope range-breakout sidecar fills.

Overlays month open, up/dn bands, range_high/low envelope, liq box, fills.
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

from .gbpusd_quarterly_4h_charts import NY, plot_candles as plot_candles_4h, shade_weeks
from .monthly_atr4_helpers import load_1h, month_windows
from .monthly_open_atr_extension_band_broker import (
    DEFAULT_ROLLING_BAND_MONTHS,
    _band_from_working,
    collect_path_stats,
    rolling_band_from_paths,
)
from .monthly_open_atr_extension_band_lookback_hp_charts import (
    LIQ_DN_COLOR,
    LIQ_UP_COLOR,
    MONTH_OPEN_COLOR,
    detect_liquidity_run,
    _ny_ts,
)
from .monthly_open_atr_extension_band_trade_charts import _resample_ohlc
from .monthly_open_liq_run_fade_1r1_reentry_1m_broker_charts import (
    BAND_FILL_DN,
    BAND_FILL_UP,
    BAND_MAX_DN,
    BAND_MAX_UP,
    BAND_MED_DN,
    BAND_MED_UP,
    BAND_MIN_DN,
    BAND_MIN_UP,
    ENTRY_COLOR,
    EXIT_EOM,
    EXIT_STOP,
    EXIT_TARGET,
    STOP_COLOR,
    _campaigns,
    _draw_bands_both,
    _email_batches,
    _find_fills,
    _progress,
    _ts,
)
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS

REPO = Path(__file__).resolve().parents[1]
DEFAULT_HUB = (
    REPO
    / "live"
    / "state"
    / "monthly_open_atr_extension_band"
    / "liq_run_range_breakout_hp_1m_broker"
)
RANGE_COLOR = "#1565c0"


def plot_month(
    *,
    bars_4h: pd.DataFrame,
    year: int,
    month: int,
    t0: pd.Timestamp,
    t1: pd.Timestamp,
    plan: dict,
    liq,
    band_tuple: Optional[Tuple[float, float, float, float, float, float]],
    atr14: float,
    camps: pd.DataFrame,
    out_path: Path,
    liq_days: int,
) -> None:
    window = bars_4h[(bars_4h.index >= t0) & (bars_4h.index < t1)].copy()
    fig, ax = plt.subplots(figsize=(20, 8.2))
    shade_weeks(ax, t0, t1)
    if not window.empty:
        plot_candles_4h(ax, window)

    month_open = float(plan["month_open"])
    rh = float(plan["range_high"])
    rl = float(plan["range_low"])

    ax.axhline(month_open, color=MONTH_OPEN_COLOR, lw=1.4, ls="--", alpha=0.9, label="month open")
    ax.axhspan(rl, rh, color="#bbdefb", alpha=0.22, zorder=1, label="envelope range")
    ax.axhline(rh, color=RANGE_COLOR, lw=1.5, ls="-", alpha=0.95, label="range high")
    ax.axhline(rl, color=RANGE_COLOR, lw=1.5, ls="-", alpha=0.95, label="range low")

    if band_tuple is not None and atr14 > 0:
        up_min, up_med, up_max, dn_min, dn_med, dn_max = band_tuple
        _draw_bands_both(
            ax,
            month_open=month_open,
            atr14=atr14,
            up_min=up_min,
            up_med=up_med,
            up_max=up_max,
            dn_min=dn_min,
            dn_med=dn_med,
            dn_max=dn_max,
        )

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
                label="liq run d1-d%d (%s %.0fpt)" % (liq_days, liq.side, liq.ext_pts),
            )
        )

    labeled = {"entry": False}
    month_pts = 0.0
    for _, tr in camps.sort_values("entry_ts").iterrows():
        et, xt = tr["entry_ts"], tr["exit_ts"]
        ep, xp = float(tr["entry_px"]), float(tr["exit_px"])
        reason = str(tr["exit_reason"])
        pts = (ep - xp) if tr["side"] == "short" else (xp - ep)
        month_pts += pts * float(tr["qty"])
        ec = {"target": EXIT_TARGET, "target_range": EXIT_TARGET, "stop": EXIT_STOP}.get(reason, EXIT_EOM)
        ax.plot([et.to_pydatetime(), xt.to_pydatetime()], [ep, xp], color=ec, lw=1.6, alpha=0.9, zorder=5)
        ax.scatter(
            [et.to_pydatetime()],
            [ep],
            marker="^" if tr["side"] == "long" else "v",
            s=55,
            color=ENTRY_COLOR,
            zorder=6,
            label="fill" if not labeled["entry"] else None,
        )
        labeled["entry"] = True
        ax.scatter([xt.to_pydatetime()], [xp], marker="o", s=45, color=ec, zorder=6)
        ax.annotate(
            reason[:6],
            xy=(xt.to_pydatetime(), xp),
            xytext=(4, 6),
            textcoords="offset points",
            fontsize=8,
            color=ec,
        )

    net_usd = month_pts * 20.0
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
    ax.grid(True, alpha=0.25)
    ax.set_title(
        "NQ %04d-%02d  |  4h  |  range breakout sidecar  |  fills=%d  ~net=$%+.0f"
        % (year, month, len(camps), net_usd),
        fontsize=12,
        fontweight="bold",
        pad=10,
    )
    ax.legend(loc="lower right", fontsize=7.5, framealpha=0.92, ncol=2)
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def run(*, hub: Path, output_root: Path, email: bool = False, liq_days: int = 2) -> int:
    hub = Path(hub).resolve()
    output_root = Path(output_root).resolve()
    if output_root.exists():
        shutil.rmtree(output_root)
    charts_dir = output_root / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    fills_path = _find_fills(hub)
    plans_path = hub / "month_plans.json"
    plans = json.loads(plans_path.read_text(encoding="utf-8"))
    fills = pd.read_csv(fills_path)
    camps = _campaigns(fills)
    _progress(output_root, "RUN months=%d campaigns=%d" % (len(plans), len(camps)))

    spec = MARKETS["NQ"]
    bars = load_1h(spec)
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    bars_ny = bars.tz_convert(NY)
    bars_4h = _resample_ohlc(bars_ny, "4h")
    paths = collect_path_stats(spec)
    path_by = {(p.year, p.month): p for p in paths}
    win_by = {}
    for year, month, m0, m1 in month_windows(bars, None, None):
        win_by[(int(year), int(month))] = (m0, m1)

    pngs: List[Path] = []
    keys = sorted({(int(r.year), int(r.month)) for r in camps.itertuples(index=False)}) if len(camps) else []
    # also chart months with plans even if no fills? only fill months
    for year, month in keys:
        key = "%04d-%02d" % (year, month)
        plan = plans.get(key)
        if not plan or (year, month) not in win_by:
            continue
        t0, t1 = win_by[(year, month)]
        t0n, t1n = _ny_ts(t0), _ny_ts(t1)
        path = path_by.get((year, month))
        atr14 = float(path.atr14) if path is not None else float("nan")
        wb = rolling_band_from_paths(paths, "NQ", year, month, window=DEFAULT_ROLLING_BAND_MONTHS)
        band_tuple = _band_from_working(wb) if wb is not None else None
        liq = detect_liquidity_run(
            bars_1h=bars_ny,
            year=year,
            month=month,
            month_open=float(plan["month_open"]),
            t0=t0n,
            t1=t1n,
            n_days=liq_days,
        )
        g = camps[(camps["year"] == year) & (camps["month"] == month)]
        out_path = charts_dir / ("%04d_%02d.png" % (year, month))
        plot_month(
            bars_4h=bars_4h,
            year=year,
            month=month,
            t0=t0n,
            t1=t1n,
            plan=plan,
            liq=liq,
            band_tuple=band_tuple,
            atr14=atr14 if np.isfinite(atr14) else 0.0,
            camps=g,
            out_path=out_path,
            liq_days=liq_days,
        )
        pngs.append(out_path)

    summary = "\n".join(
        [
            "# NQ HP range-breakout sidecar — 4h charts",
            "",
            "Source hub: `%s`" % hub,
            "Months with fills: **%d** | campaigns: **%d**" % (len(pngs), len(camps)),
            "Overlays: envelope range, bands, liq box, breakout fills",
            "Gap rule: session open must not gap through/adverse entry (esp. near SL)",
            "",
            "Hub: `%s`" % output_root,
            "",
        ]
    )
    (output_root / "SUMMARY.md").write_text(summary, encoding="utf-8")
    (output_root / "EMAIL.txt").write_text(summary, encoding="utf-8")
    _progress(output_root, "DONE charts=%d" % len(pngs))
    if email:
        send_email(subject="potions: NQ range breakout charts (%d)" % len(pngs), body=summary)
        _email_batches(pngs, output_root, summary, subject_prefix="potions: NQ range BO charts")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hub", type=Path, default=DEFAULT_HUB)
    p.add_argument("--output-root", type=Path, default=None)
    p.add_argument("--liq-days", type=int, default=2)
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    out = args.output_root or (Path(args.hub).resolve() / "trade_charts_4h")
    try:
        return run(hub=args.hub, output_root=out, email=args.email, liq_days=args.liq_days)
    except Exception:
        tb = traceback.format_exc()
        _progress(out, "FAILED\n" + tb)
        if args.email:
            send_email(subject="potions: range BO charts FAILED", body=tb[-4000:])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
