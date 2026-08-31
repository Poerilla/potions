"""4h charts for HP 1m-broker liq-run fade fills + extension bands.

Overlays:
  - liq-run box (first N NY trading days)
  - rolling extension **up + dn min / med / max** bands
  - month open, plan entry/stop
  - each entry→exit path from 1m broker fills

Legend **lower right**.
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
    LiquidityRun,
    detect_liquidity_run,
    _ny_ts,
)
from .monthly_open_atr_extension_band_trade_charts import _resample_ohlc
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS

REPO = Path(__file__).resolve().parents[1]
DEFAULT_HUB = (
    REPO
    / "live"
    / "state"
    / "monthly_open_atr_extension_band"
    / "liq_run_fade_1r1_reentry_hp_1m_broker"
)
FILLS = (
    DEFAULT_HUB
    / "states"
    / "nq_liq_run_fade_1r1_reentry_hp_1m"
    / "fills.csv"
)
PLANS = DEFAULT_HUB / "month_plans.json"
DEFAULT_OUT = DEFAULT_HUB / "trade_charts_4h"

BAND_FILL_UP = "#ffebee"
BAND_FILL_DN = "#e8f5e9"
BAND_MIN_UP = "#ef5350"
BAND_MED_UP = "#e53935"
BAND_MAX_UP = "#b71c1c"
BAND_MIN_DN = "#66bb6a"
BAND_MED_DN = "#43a047"
BAND_MAX_DN = "#1b5e20"
ENTRY_COLOR = "#6a1b9a"
STOP_COLOR = "#c62828"
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


def _ts(val: object) -> pd.Timestamp:
    t = pd.Timestamp(val)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return t.tz_convert(NY)


def _find_fills(hub: Path) -> Path:
    direct = hub / "states" / "nq_liq_run_fade_1r1_reentry_hp_1m" / "fills.csv"
    if direct.exists():
        return direct
    matches = sorted(hub.glob("states/*/fills.csv"))
    if not matches:
        raise FileNotFoundError("no fills.csv under %s/states" % hub)
    return matches[-1]


def _campaigns(fills: pd.DataFrame) -> pd.DataFrame:
    """One row per trade_id: entry + exit."""
    rows: List[dict] = []
    for tid, g in fills.groupby("trade_id"):
        g = g.sort_values("ts")
        ent = g[g["reason"].astype(str) == "entry"]
        if ent.empty:
            continue
        e = ent.iloc[0]
        ex = g[g["reason"].astype(str) != "entry"]
        if ex.empty:
            continue
        x = ex.iloc[-1]
        et = _ts(e["ts"])
        rows.append(
            {
                "trade_id": str(tid),
                "year": int(et.year),
                "month": int(et.month),
                "side": "short" if str(e["side"]).lower() == "sell" else "long",
                "entry_ts": et,
                "entry_px": float(e["price"]),
                "exit_ts": _ts(x["ts"]),
                "exit_px": float(x["price"]),
                "exit_reason": str(x["reason"]),
                "qty": int(e["quantity"]),
            }
        )
    return pd.DataFrame(rows).sort_values(["year", "month", "entry_ts"]).reset_index(drop=True)


def _draw_bands_both(
    ax,
    *,
    month_open: float,
    atr14: float,
    up_min: float,
    up_med: float,
    up_max: float,
    dn_min: float,
    dn_med: float,
    dn_max: float,
) -> None:
    # Up band (above open)
    u_lo = month_open + up_min * atr14
    u_med = month_open + up_med * atr14
    u_hi = month_open + up_max * atr14
    ax.axhspan(min(u_lo, u_hi), max(u_lo, u_hi), color=BAND_FILL_UP, alpha=0.28, zorder=1, label="up band")
    ax.axhline(u_lo, color=BAND_MIN_UP, lw=1.1, ls=":", alpha=0.9, label="up min")
    ax.axhline(u_med, color=BAND_MED_UP, lw=1.3, ls="--", alpha=0.95, label="up med")
    ax.axhline(u_hi, color=BAND_MAX_UP, lw=1.1, ls=":", alpha=0.9, label="up max")
    # Down band (below open)
    d_hi = month_open - dn_min * atr14
    d_med = month_open - dn_med * atr14
    d_lo = month_open - dn_max * atr14
    ax.axhspan(min(d_lo, d_hi), max(d_lo, d_hi), color=BAND_FILL_DN, alpha=0.28, zorder=1, label="dn band")
    ax.axhline(d_hi, color=BAND_MIN_DN, lw=1.1, ls=":", alpha=0.9, label="dn min")
    ax.axhline(d_med, color=BAND_MED_DN, lw=1.3, ls="--", alpha=0.95, label="dn med")
    ax.axhline(d_lo, color=BAND_MAX_DN, lw=1.1, ls=":", alpha=0.9, label="dn max")


def plot_month(
    *,
    bars_4h: pd.DataFrame,
    year: int,
    month: int,
    t0: pd.Timestamp,
    t1: pd.Timestamp,
    plan: dict,
    liq: Optional[LiquidityRun],
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
    entry = float(plan["entry"])
    stop = float(plan["stop"])

    ax.axhline(month_open, color=MONTH_OPEN_COLOR, lw=1.4, ls="--", alpha=0.9, label="month open")
    ax.axhline(entry, color=ENTRY_COLOR, lw=1.2, ls=":", alpha=0.9, label="entry / p_liq")
    ax.axhline(stop, color=STOP_COLOR, lw=1.1, ls="-.", alpha=0.85, label="stop (1R)")

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

    labeled = {"entry": False, "target": False, "stop": False, "flatten": False}
    month_pts = 0.0
    for _, tr in camps.sort_values("entry_ts").iterrows():
        et, xt = tr["entry_ts"], tr["exit_ts"]
        ep, xp = float(tr["entry_px"]), float(tr["exit_px"])
        reason = str(tr["exit_reason"])
        pts = (ep - xp) if tr["side"] == "short" else (xp - ep)
        month_pts += pts * float(tr["qty"])
        ec = {"target": EXIT_TARGET, "stop": EXIT_STOP}.get(reason, EXIT_EOM)
        ax.plot(
            [et.to_pydatetime(), xt.to_pydatetime()],
            [ep, xp],
            color=ec,
            lw=1.6,
            alpha=0.9,
            zorder=5,
        )
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
        lab = None
        if reason in labeled and not labeled[reason]:
            lab = "exit %s" % reason
            labeled[reason] = True
        ax.scatter([xt.to_pydatetime()], [xp], marker="o", s=45, color=ec, zorder=6, label=lab)
        ax.annotate(
            reason[:3],
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
        "NQ %04d-%02d  |  4h  |  1m broker HP reentry liq%d  |  fills=%d  ~net=$%+.0f"
        % (year, month, liq_days, len(camps), net_usd),
        fontsize=12,
        fontweight="bold",
        pad=10,
    )
    ax.legend(loc="lower right", fontsize=7.5, framealpha=0.92, ncol=2)
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def _email_batches(pngs: Sequence[Path], output_root: Path, body_intro: str, *, subject_prefix: str) -> None:
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
        subj = "%s (%d/%d)" % (subject_prefix, i, len(batches))
        body = body_intro + "\nBatch %d/%d — %d PNGs\n" % (i, len(batches), len(batch))
        send_email(subject=subj, body=body, attachments=list(batch))
        _progress(output_root, "EMAIL batch %d/%d n=%d" % (i, len(batches), len(batch)))


def run(
    *,
    hub: Path,
    output_root: Path,
    email: bool = False,
    liq_days: int = 2,
) -> int:
    hub = Path(hub).resolve()
    output_root = Path(output_root).resolve()
    liq_days = int(liq_days)
    if output_root.exists():
        import shutil

        shutil.rmtree(output_root)
    charts_dir = output_root / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    fills_path = _find_fills(hub)
    plans_path = hub / "month_plans.json"
    if not plans_path.exists():
        raise FileNotFoundError(plans_path)
    plans = json.loads(plans_path.read_text(encoding="utf-8"))
    # prefer plan-stored liq_days when present
    sample = next(iter(plans.values()), {})
    if sample.get("liq_days"):
        liq_days = int(sample["liq_days"])

    fills = pd.read_csv(fills_path)
    camps = _campaigns(fills)
    _progress(
        output_root,
        "RUN hub=%s liq_days=%d months=%d campaigns=%d"
        % (hub.name, liq_days, camps.groupby(["year", "month"]).ngroups, len(camps)),
    )

    spec = MARKETS["NQ"]
    bars = load_1h(spec)
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    bars_ny = bars.tz_convert(NY)
    bars_4h = _resample_ohlc(bars_ny, "4h")
    paths = collect_path_stats(spec)
    path_by = {(p.year, p.month): p for p in paths}

    win_by: Dict[Tuple[int, int], Tuple[pd.Timestamp, pd.Timestamp]] = {}
    for year, month, m0, m1 in month_windows(bars, None, None):
        win_by[(int(year), int(month))] = (m0, m1)

    pngs: List[Path] = []
    index_rows: List[dict] = []
    for (year, month), g in camps.groupby(["year", "month"], sort=True):
        year, month = int(year), int(month)
        key = "%04d-%02d" % (year, month)
        plan = plans.get(key)
        if not plan or (year, month) not in win_by:
            continue
        t0, t1 = win_by[(year, month)]
        t0n, t1n = _ny_ts(t0), _ny_ts(t1)
        month_open = float(plan["month_open"])
        liq = detect_liquidity_run(
            bars_1h=bars_ny,
            year=year,
            month=month,
            month_open=month_open,
            t0=t0n,
            t1=t1n,
            n_days=liq_days,
        )
        wb = rolling_band_from_paths(
            paths,
            "NQ",
            year,
            month,
            window=DEFAULT_ROLLING_BAND_MONTHS,
        )
        band_tuple = _band_from_working(wb) if wb is not None else None
        path = path_by.get((year, month))
        atr14 = float(path.atr14) if path is not None else float("nan")
        if not np.isfinite(atr14) or atr14 <= 0:
            atr14 = float("nan")
            band_tuple = None

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
        index_rows.append(
            {
                "year": year,
                "month": month,
                "n_fills": int(len(g)),
                "chart": str(out_path.relative_to(output_root)),
            }
        )
        if len(pngs) % 20 == 0:
            _progress(output_root, "CHARTS %d" % len(pngs))

    pd.DataFrame(index_rows).to_csv(output_root / "index.csv", index=False)
    summary = "\n".join(
        [
            "# NQ HP 1m broker reentry — 4h charts (liq %d days, both bands)" % liq_days,
            "",
            "Source hub: `%s`" % hub,
            "Months: **%d** | campaigns: **%d**" % (len(pngs), len(camps)),
            "Overlays: liq-run box (d1–d%d); rolling **up+dn min/med/max**; entry/stop/open" % liq_days,
            "Legend: **lower right**",
            "",
            "Hub: `%s`" % output_root,
            "",
        ]
    )
    (output_root / "SUMMARY.md").write_text(summary, encoding="utf-8")
    (output_root / "EMAIL.txt").write_text(summary, encoding="utf-8")
    (output_root / "RUN_COMPLETE.json").write_text(
        json.dumps({"ok": True, "n_charts": len(pngs), "liq_days": liq_days}, indent=2) + "\n",
        encoding="utf-8",
    )
    _progress(output_root, "DONE charts=%d" % len(pngs))
    if email:
        send_email(
            subject="potions: NQ HP 1m broker charts liq%d (%d)" % (liq_days, len(pngs)),
            body=summary,
        )
        _email_batches(
            pngs,
            output_root,
            summary,
            subject_prefix="potions: NQ HP 1m charts liq%d" % liq_days,
        )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hub", type=Path, default=DEFAULT_HUB)
    p.add_argument("--output-root", type=Path, default=None)
    p.add_argument("--liq-days", type=int, default=2)
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    out = args.output_root
    if out is None:
        out = Path(args.hub).resolve() / "trade_charts_4h"
    try:
        return run(hub=args.hub, output_root=out, email=args.email, liq_days=args.liq_days)
    except Exception:
        tb = traceback.format_exc()
        _progress(out, "FAILED\n" + tb)
        if args.email:
            send_email(subject="potions: HP 1m broker charts FAILED", body=tb[-4000:])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
