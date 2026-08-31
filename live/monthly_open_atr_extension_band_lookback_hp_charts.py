"""4h charts for NQ lookback-HP months + first-2-day liquidity-run box.

Selects months from ``lookback_filter/months_features_nq.csv`` (OR of causal HP
predictors). On each chart:

- First **2 full NY trading days** after month open
- Biggest absolute extension from month open = **run on liquidity**
- Box ``(t_open, t_liq, p_open, p_liq)`` on that side
- Profile: reclaim open from liq swing vs further expansion past liq swing
  vs opposite-side (trade-direction) expansion

Hub: ``live/state/monthly_open_atr_extension_band/lookback_hp_month_charts_4h/``
"""

from __future__ import annotations

import argparse
import json
import traceback
from dataclasses import asdict, dataclass
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
from .monthly_open_atr_extension_band_trade_charts import _resample_ohlc
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS

REPO = Path(__file__).resolve().parents[1]
FEATURES_CSV = (
    REPO
    / "live"
    / "state"
    / "monthly_open_atr_extension_band"
    / "lookback_filter"
    / "months_features_nq.csv"
)
DEFAULT_OUT = (
    REPO
    / "live"
    / "state"
    / "monthly_open_atr_extension_band"
    / "lookback_hp_month_charts_4h"
)

MONTH_OPEN_COLOR = "#1565c0"
LIQ_UP_COLOR = "#c62828"
LIQ_DN_COLOR = "#2e7d32"
PNG_BATCH_BYTES = 18 * 1024 * 1024
PNG_MAX_PER_EMAIL = 18

CONDITIONS: Sequence[Tuple[str, str]] = (
    ("swept_swing_low_6m", "swept_swing_low_6m"),
    ("swept_swing_high_6m", "swept_swing_high_6m"),
    ("prior_bear", "prior_bear"),
    ("cal_month=7", "cal_month"),
    ("prior_engulf_bear", "prior_engulf_bear"),
)


@dataclass
class LiquidityRun:
    year: int
    month: int
    month_open: float
    t_open: pd.Timestamp
    t_liq: pd.Timestamp
    p_liq: float
    side: str  # "up" | "down"
    ext_pts: float
    day1: str
    day2: str
    # Rest-of-month profile (after t_liq)
    hit_open: bool
    trade_dir_ext_pts: float
    past_liq_ext_pts: float
    trade_dir_gt_past_liq: bool


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _truthy(val) -> bool:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return False
    try:
        return int(float(val)) == 1
    except (TypeError, ValueError):
        return False


def conditions_met(row: pd.Series) -> List[str]:
    met: List[str] = []
    for label, col in CONDITIONS:
        if col == "cal_month":
            try:
                if int(row.get("cal_month") or row.get("month") or 0) == 7:
                    met.append(label)
            except (TypeError, ValueError):
                pass
            continue
        if _truthy(row.get(col)):
            met.append(label)
    return met


def select_months(features: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in features.iterrows():
        met = conditions_met(row)
        if not met:
            continue
        rows.append(
            {
                "year": int(row["year"]),
                "month": int(row["month"]),
                "month_name": str(row.get("month_name") or ""),
                "month_open": float(row["month_open"]),
                "atr14": float(row.get("atr14") or 0.0),
                "conditions": "+".join(met),
                "n_conditions": len(met),
                "swept_swing_low_6m": int(_truthy(row.get("swept_swing_low_6m"))),
                "swept_swing_high_6m": int(_truthy(row.get("swept_swing_high_6m"))),
                "prior_bear": int(_truthy(row.get("prior_bear"))),
                "cal_month_7": int(int(row.get("cal_month") or row.get("month") or 0) == 7),
                "prior_engulf_bear": int(_truthy(row.get("prior_engulf_bear"))),
            }
        )
    return pd.DataFrame(rows)


def _ny_ts(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return t.tz_convert(NY)


def first_n_trading_days(bars: pd.DataFrame, t0: pd.Timestamp, t1: pd.Timestamp, n: int = 2) -> List:
    """Unique NY calendar dates with bars inside [t0, t1), first n."""
    window = bars[(bars.index >= t0) & (bars.index < t1)]
    if window.empty:
        return []
    days = []
    seen = set()
    for ts in window.index:
        d = _ny_ts(ts).date()
        if d in seen:
            continue
        seen.add(d)
        days.append(d)
        if len(days) >= n:
            break
    return days


def detect_liquidity_run(
    *,
    bars_1h: pd.DataFrame,
    year: int,
    month: int,
    month_open: float,
    t0: pd.Timestamp,
    t1: pd.Timestamp,
    n_days: int = 2,
) -> Optional[LiquidityRun]:
    """Biggest |extension| from month open over first ``n_days`` full NY trading days."""
    n = max(1, int(n_days))
    days = first_n_trading_days(bars_1h, t0, t1, n=n)
    if len(days) < n:
        return None
    day_set = set(days)
    # Bars on those calendar days (NY)
    mask_days = bars_1h.index.map(lambda ts: _ny_ts(ts).date() in day_set)
    seg = bars_1h.loc[mask_days]
    seg = seg[(seg.index >= t0) & (seg.index < t1)]
    if seg.empty:
        return None

    t_open = _ny_ts(seg.index[0])
    hi = float(seg["high"].max())
    lo = float(seg["low"].min())
    up_ext = hi - float(month_open)
    dn_ext = float(month_open) - lo

    if up_ext >= dn_ext and up_ext > 0:
        side = "up"
        p_liq = hi
        ext = up_ext
        # first bar that prints the high
        hit = seg[seg["high"] >= hi - 1e-9].iloc[0]
        t_liq = _ny_ts(hit.name)
    elif dn_ext > 0:
        side = "down"
        p_liq = lo
        ext = dn_ext
        hit = seg[seg["low"] <= lo + 1e-9].iloc[0]
        t_liq = _ny_ts(hit.name)
    else:
        return None

    # Rest of month after liquidity extreme
    after = bars_1h[(bars_1h.index > hit.name) & (bars_1h.index < t1)]
    hit_open = False
    trade_ext = 0.0
    past_liq = 0.0
    if not after.empty:
        if side == "up":
            # reclaim open from above: price trades back to/through open
            hit_open = bool((after["low"] <= float(month_open)).any())
            trade_ext = float(max(0.0, float(month_open) - float(after["low"].min())))
            past_liq = float(max(0.0, float(after["high"].max()) - p_liq))
        else:
            hit_open = bool((after["high"] >= float(month_open)).any())
            trade_ext = float(max(0.0, float(after["high"].max()) - float(month_open)))
            past_liq = float(max(0.0, p_liq - float(after["low"].min())))

    return LiquidityRun(
        year=year,
        month=month,
        month_open=float(month_open),
        t_open=t_open,
        t_liq=t_liq,
        p_liq=float(p_liq),
        side=side,
        ext_pts=float(ext),
        day1=str(days[0]),
        day2=str(days[-1]),
        hit_open=bool(hit_open),
        trade_dir_ext_pts=float(trade_ext),
        past_liq_ext_pts=float(past_liq),
        trade_dir_gt_past_liq=bool(trade_ext > past_liq),
    )


def plot_month_4h(
    *,
    bars_4h: pd.DataFrame,
    year: int,
    month: int,
    month_open: float,
    conditions: str,
    t0: pd.Timestamp,
    t1: pd.Timestamp,
    out_path: Path,
    liq: Optional[LiquidityRun] = None,
) -> None:
    window = bars_4h[(bars_4h.index >= t0) & (bars_4h.index < t1)].copy()
    fig, ax = plt.subplots(figsize=(20, 8.2))
    shade_weeks(ax, t0, t1)
    if not window.empty:
        plot_candles_4h(ax, window)
    ax.axhline(month_open, color=MONTH_OPEN_COLOR, lw=1.4, ls="--", alpha=0.9, label="month open")

    if liq is not None:
        color = LIQ_UP_COLOR if liq.side == "up" else LIQ_DN_COLOR
        x0 = mdates.date2num(liq.t_open.to_pydatetime())
        x1 = mdates.date2num(liq.t_liq.to_pydatetime())
        y0 = min(liq.month_open, liq.p_liq)
        y1 = max(liq.month_open, liq.p_liq)
        width = max(x1 - x0, 1e-4)
        height = max(y1 - y0, 1e-4)
        rect = Rectangle(
            (x0, y0),
            width,
            height,
            linewidth=2.0,
            edgecolor=color,
            facecolor=color,
            alpha=0.18,
            zorder=3,
            label="liq run (%s %.0fpt)" % (liq.side, liq.ext_pts),
        )
        ax.add_patch(rect)
        ax.axhline(liq.p_liq, color=color, lw=1.2, ls=":", alpha=0.85, label="liq swing")
        # annotate reclaim / expansion flags
        tag = "reclaim_open=%s | trade_ext=%.0f > past_liq=%.0f ? %s" % (
            "Y" if liq.hit_open else "N",
            liq.trade_dir_ext_pts,
            liq.past_liq_ext_pts,
            "Y" if liq.trade_dir_gt_past_liq else "N",
        )
        ax.text(
            0.01,
            0.02,
            tag,
            transform=ax.transAxes,
            fontsize=9,
            va="bottom",
            ha="left",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.85, edgecolor=color),
        )

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=2))
    ax.grid(True, alpha=0.25)
    title = "NQ %04d-%02d  |  4h  |  %s" % (year, month, conditions)
    if liq is not None:
        title += "  |  liq %s %.0fpt (d1-d2)" % (liq.side, liq.ext_pts)
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)
    ax.legend(loc="upper left", fontsize=9)
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def _profile_summary(runs: Sequence[LiquidityRun]) -> Dict[str, object]:
    n = len(runs)
    if n == 0:
        return {"n": 0}
    hit = sum(1 for r in runs if r.hit_open)
    trade_gt = sum(1 for r in runs if r.trade_dir_gt_past_liq)
    up = [r for r in runs if r.side == "up"]
    dn = [r for r in runs if r.side == "down"]
    return {
        "n_months": n,
        "liq_up_n": len(up),
        "liq_down_n": len(dn),
        "hit_open_n": hit,
        "hit_open_frac": hit / n,
        "trade_dir_gt_past_liq_n": trade_gt,
        "trade_dir_gt_past_liq_frac": trade_gt / n,
        "avg_liq_ext_pts": float(np.mean([r.ext_pts for r in runs])),
        "avg_trade_dir_ext_pts": float(np.mean([r.trade_dir_ext_pts for r in runs])),
        "avg_past_liq_ext_pts": float(np.mean([r.past_liq_ext_pts for r in runs])),
        "median_liq_ext_pts": float(np.median([r.ext_pts for r in runs])),
        "both_hit_open_and_trade_gt": sum(1 for r in runs if r.hit_open and r.trade_dir_gt_past_liq),
        "hit_open_but_past_liq_wins": sum(1 for r in runs if r.hit_open and not r.trade_dir_gt_past_liq),
        "no_reclaim_trade_gt": sum(1 for r in runs if (not r.hit_open) and r.trade_dir_gt_past_liq),
        "no_reclaim_past_liq_wins": sum(1 for r in runs if (not r.hit_open) and not r.trade_dir_gt_past_liq),
    }


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
        subj = "potions: NQ liq-run 4h charts (%d/%d)" % (i, len(batches))
        body = body_intro + "\nBatch %d/%d — %d PNGs\n" % (i, len(batches), len(batch))
        send_email(subject=subj, body=body, attachments=list(batch))
        _progress(output_root, "EMAIL batch %d/%d n=%d" % (i, len(batches), len(batch)))


def run(*, output_root: Path, email: bool = False, force: bool = True) -> int:
    if force and output_root.exists():
        import shutil

        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    charts_dir = output_root / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    if not FEATURES_CSV.exists():
        raise FileNotFoundError(
            "Missing %s — run live.monthly_open_atr_extension_band_lookback_filter first" % FEATURES_CSV
        )
    features = pd.read_csv(FEATURES_CSV)
    features = features[features["market"].astype(str).str.upper() == "NQ"].copy()
    selected = select_months(features)
    selected.to_csv(output_root / "months_selected.csv", index=False)
    _progress(
        output_root,
        "SELECTED n=%d / %d NQ months (OR of HP predictors)" % (len(selected), len(features)),
    )

    spec = MARKETS["NQ"]
    bars_1h = load_1h(spec)
    if bars_1h.index.tz is None:
        bars_1h.index = bars_1h.index.tz_localize("UTC")
    bars_1h_ny = bars_1h.tz_convert(NY)
    bars_4h = _resample_ohlc(bars_1h, "4h")

    win_by: Dict[Tuple[int, int], Tuple[pd.Timestamp, pd.Timestamp]] = {}
    for year, month, m0, m1 in month_windows(bars_1h, None, None):
        win_by[(int(year), int(month))] = (m0, m1)

    pngs: List[Path] = []
    index_rows: List[dict] = []
    runs: List[LiquidityRun] = []

    for row in selected.itertuples(index=False):
        key = (int(row.year), int(row.month))
        if key not in win_by:
            _progress(output_root, "SKIP no bars %04d-%02d" % key)
            continue
        t0, t1 = win_by[key]
        t0n = _ny_ts(t0)
        t1n = _ny_ts(t1)
        liq = detect_liquidity_run(
            bars_1h=bars_1h_ny,
            year=int(row.year),
            month=int(row.month),
            month_open=float(row.month_open),
            t0=t0n,
            t1=t1n,
        )
        slug = "%04d_%02d" % (row.year, row.month)
        out_path = charts_dir / ("%s.png" % slug)
        plot_month_4h(
            bars_4h=bars_4h,
            year=int(row.year),
            month=int(row.month),
            month_open=float(row.month_open),
            conditions=str(row.conditions),
            t0=t0n,
            t1=t1n,
            out_path=out_path,
            liq=liq,
        )
        pngs.append(out_path)
        rec = {
            "year": int(row.year),
            "month": int(row.month),
            "conditions": row.conditions,
            "n_conditions": int(row.n_conditions),
            "chart": str(out_path.relative_to(output_root)),
        }
        if liq is not None:
            runs.append(liq)
            rec.update(
                {
                    "liq_side": liq.side,
                    "liq_ext_pts": liq.ext_pts,
                    "p_liq": liq.p_liq,
                    "t_liq": liq.t_liq.isoformat(),
                    "day1": liq.day1,
                    "day2": liq.day2,
                    "hit_open": int(liq.hit_open),
                    "trade_dir_ext_pts": liq.trade_dir_ext_pts,
                    "past_liq_ext_pts": liq.past_liq_ext_pts,
                    "trade_dir_gt_past_liq": int(liq.trade_dir_gt_past_liq),
                }
            )
        index_rows.append(rec)
        _progress(
            output_root,
            "CHART %s | %s | liq=%s"
            % (slug, row.conditions, ("%s %.0fpt" % (liq.side, liq.ext_pts)) if liq else "none"),
        )

    idx = pd.DataFrame(index_rows)
    idx.to_csv(output_root / "INDEX.csv", index=False)
    runs_df = pd.DataFrame([asdict(r) for r in runs])
    if not runs_df.empty:
        # stringify timestamps for csv
        for c in ("t_open", "t_liq"):
            if c in runs_df.columns:
                runs_df[c] = runs_df[c].astype(str)
        runs_df.to_csv(output_root / "liquidity_runs.csv", index=False)

    profile = _profile_summary(runs)
    (output_root / "liquidity_profile.json").write_text(
        json.dumps(profile, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    n = int(profile.get("n_months") or 0)
    summary_lines = [
        "# NQ lookback HP 4h charts — liquidity-run overlay",
        "",
        "First **2 full NY trading days**: largest |move| from month open = run on liquidity.",
        "Box = `(t_open, t_liq, p_open, p_liq)`. Trade direction = opposite side of the run.",
        "",
        "## Selection",
        "",
        "Charts: **%d** (OR of causal HP predictors)." % len(pngs),
        "",
        "## Liquidity-run profile (n=%d)" % n,
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Liq run UP / DOWN | %d / %d |"
        % (int(profile.get("liq_up_n") or 0), int(profile.get("liq_down_n") or 0)),
        "| Avg / median liq extension (pts) | %.1f / %.1f |"
        % (float(profile.get("avg_liq_ext_pts") or 0), float(profile.get("median_liq_ext_pts") or 0)),
        "| **Hit month open** after liq swing | **%d / %d (%.1f%%)** |"
        % (
            int(profile.get("hit_open_n") or 0),
            n,
            100.0 * float(profile.get("hit_open_frac") or 0),
        ),
        "| **Trade-dir ext > past-liq ext** | **%d / %d (%.1f%%)** |"
        % (
            int(profile.get("trade_dir_gt_past_liq_n") or 0),
            n,
            100.0 * float(profile.get("trade_dir_gt_past_liq_frac") or 0),
        ),
        "| Avg trade-dir extension (pts) | %.1f |" % float(profile.get("avg_trade_dir_ext_pts") or 0),
        "| Avg past-liq extension (pts) | %.1f |" % float(profile.get("avg_past_liq_ext_pts") or 0),
        "",
        "### Joint",
        "",
        "| Cohort | N |",
        "|---|---:|",
        "| Reclaim open **and** trade-dir wins | %d |" % int(profile.get("both_hit_open_and_trade_gt") or 0),
        "| Reclaim open but past-liq wins | %d |" % int(profile.get("hit_open_but_past_liq_wins") or 0),
        "| No reclaim, trade-dir wins | %d |" % int(profile.get("no_reclaim_trade_gt") or 0),
        "| No reclaim, past-liq wins | %d |" % int(profile.get("no_reclaim_past_liq_wins") or 0),
        "",
        "Hub: `%s`" % output_root,
    ]
    summary = "\n".join(summary_lines) + "\n"
    (output_root / "SUMMARY.md").write_text(summary, encoding="utf-8")
    (output_root / "EMAIL.txt").write_text(summary, encoding="utf-8")

    lines = [
        "# NQ lookback HP months — 4h + liquidity-run box",
        "",
        "Charts: **%d**" % len(pngs),
        "",
        "| Year-Month | Conditions | Liq | Ext | Hit open | Trade>Past | Chart |",
        "|---|---|---|---:|---|---|---|",
    ]
    for r in index_rows:
        lines.append(
            "| %04d-%02d | `%s` | %s | %s | %s | %s | `%s` |"
            % (
                r["year"],
                r["month"],
                r["conditions"],
                r.get("liq_side", ""),
                ("%.0f" % r["liq_ext_pts"]) if "liq_ext_pts" in r else "",
                "Y" if r.get("hit_open") else ("N" if "hit_open" in r else ""),
                "Y" if r.get("trade_dir_gt_past_liq") else ("N" if "trade_dir_gt_past_liq" in r else ""),
                r["chart"],
            )
        )
    (output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    _progress(output_root, "DONE charts=%d profile=%s" % (len(pngs), json.dumps(profile)))
    if email:
        _email_batches(pngs, output_root, summary)
        send_email(subject="potions: NQ liq-run 4h charts + profile (%d)" % len(pngs), body=summary)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--email", action="store_true")
    p.add_argument("--force", action="store_true", default=True)
    p.add_argument("--no-force", action="store_false", dest="force")
    args = p.parse_args(argv)
    try:
        return run(output_root=args.output_root, email=args.email, force=args.force)
    except Exception:
        tb = traceback.format_exc()
        _progress(args.output_root, "FAILED\n" + tb)
        if args.email:
            send_email(subject="potions: NQ liq-run charts FAILED", body=tb[-4000:])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
