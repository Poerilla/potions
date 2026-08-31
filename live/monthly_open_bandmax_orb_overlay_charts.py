"""Band-max +0.5 · open TP + 2R runner charts with monthly ORB overlay.

For every filled month in ``broker_max_plus_0p5_runner2r[_<mkt>]/all_weeks``:

- 4h candles, extension band (max entry / plus_0.5 SL / month-open TP / runner 2R)
- Monthly ORB from first **3** daily sessions: RH/RL box, form vertical,
  long/short 1R measured-move targets

Also writes path hit-rate for monthly ORB restricted scaleout3 when that
sim CSV exists (NQ / MNQ).

Hub: ``live/state/monthly_open_atr_extension_band/broker_max_plus_0p5_runner2r[_<mkt>]/orb_overlay_charts/``
"""

from __future__ import annotations

import argparse
import csv
import json
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

from .gbpusd_quarterly_4h_charts import NY, plot_candles as plot_candles_4h, shade_weeks, slug
from .instrument_deep_check import _resolve_paths, load_campaigns
from .monthly_atr4_helpers import load_1h, month_windows
from .monthly_open_atr_extension_band_broker import (
    DEFAULT_ROLLING_BAND_MONTHS,
    _band_from_working,
    _entry_stop_atr,
    collect_path_stats,
    rolling_band_from_paths,
)
from .monthly_open_atr_extension_band_max_runner_broker import default_hub_for_market
from .monthly_open_atr_extension_band_trade_charts import _resample_ohlc
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS
from .run_ledger import log_run

REPO = Path(__file__).resolve().parents[1]
BAND_ROOT = REPO / "live" / "state" / "monthly_open_atr_extension_band"


def daily_path_for(market: str) -> Path:
    m = market.upper()
    cands = [
        REPO / m.lower() / ("%s_daily.csv" % m.lower()),
        REPO / "fx" / ("%s_daily.csv" % m.lower()),
        REPO / "nq" / "nq_daily.csv" if m == "NQ" else None,
        REPO / "mnq" / "mnq_daily.csv" if m == "MNQ" else None,
    ]
    for p in cands:
        if p is not None and p.exists():
            return p
    raise FileNotFoundError("No daily CSV for %s" % market)


def so3_path_for(market: str) -> Optional[Path]:
    m = market.upper()
    cands = [
        REPO / m.lower() / ("%s_monthly_orb_restricted_scaleout3.csv" % m.lower()),
        REPO / "fx" / ("%s_monthly_orb_restricted_scaleout3.csv" % m.lower()),
    ]
    for p in cands:
        if p.exists():
            return p
    return None


def default_state_root(market: str) -> Path:
    hub = default_hub_for_market(market)
    m = market.upper()
    sid = "%s_mo_ext_max_plus_0p5_r2r_allw_L0_5_5_r%dm" % (
        m.lower(),
        DEFAULT_ROLLING_BAND_MONTHS,
    )
    return hub / "all_weeks" / "states" / sid


def default_chart_out(market: str) -> Path:
    return default_hub_for_market(market) / "orb_overlay_charts"


MONTH_OPEN_COLOR = "#1565c0"
BAND_FILL = "#fff3e0"
BAND_EDGE = "#ef6c00"
BAND_MED = "#ff9800"
ENTRY_COLOR = "#6a1b9a"
STOP_COLOR = "#c62828"
TARGET_OPEN = "#1565c0"
RUNNER_TP = "#00838f"
ORB_HI = "#6a1b9a"
ORB_LO = "#6a1b9a"
ORB_FILL = "#e1bee7"
ORB_FORM = "#4a148c"
ORB_TGT_LONG = "#2e7d32"
ORB_TGT_SHORT = "#c62828"
EXIT_TARGET = "#2e7d32"
EXIT_STOP = "#b71c1c"
EXIT_EOM = "#ef6c00"
PNG_BATCH_BYTES = 18 * 1024 * 1024
PNG_MAX_PER_EMAIL = 16
ENTRY_MODE = "max"
SL_MODE = "plus_0.5"
RUNNER_R_MULT = 2.0


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


@dataclass
class MonthlyOrb:
    year: int
    month: int
    range_high: float
    range_low: float
    range_pts: float
    form_ts: pd.Timestamp  # end of 3rd daily session (NY)
    long_target: float  # RH + range
    short_target: float  # RL - range
    range_day_dates: List[pd.Timestamp]


def load_monthly_orbs(daily_path: Path) -> Dict[Tuple[int, int], MonthlyOrb]:
    df = pd.read_csv(daily_path)
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(NY)
    out: Dict[Tuple[int, int], MonthlyOrb] = {}
    for (y, m), g in df.groupby([df["date"].dt.year, df["date"].dt.month], sort=True):
        g = g.sort_values("date")
        if len(g) < 4:
            continue
        range_bars = g.iloc[:3]
        rh = float(range_bars["high"].max())
        rl = float(range_bars["low"].min())
        rng = rh - rl
        if not np.isfinite(rng) or rng <= 0:
            continue
        # OR forms at the close of day 3 → mark at that session's date 16:00 NY
        d3 = pd.Timestamp(range_bars.iloc[2]["date"])
        form_ts = d3.replace(hour=16, minute=0, second=0, microsecond=0)
        if form_ts.tzinfo is None:
            form_ts = form_ts.tz_localize(NY)
        else:
            form_ts = form_ts.tz_convert(NY)
        out[(int(y), int(m))] = MonthlyOrb(
            year=int(y),
            month=int(m),
            range_high=rh,
            range_low=rl,
            range_pts=rng,
            form_ts=form_ts,
            long_target=rh + rng,
            short_target=rl - rng,
            range_day_dates=[pd.Timestamp(x) for x in range_bars["date"].tolist()],
        )
    return out


def path_hitrate(
    daily_path: Path,
    trades_path: Path,
    label: str,
) -> Dict[str, object]:
    """After entry, does price touch 1R TP before opposite OR boundary?

    Same-bar ordering: opposite stop before target (conservative).
    Ignores range-close (pure geometric race).
    """
    daily = pd.read_csv(daily_path)
    daily["date"] = pd.to_datetime(daily["date"]).dt.normalize()
    trades = pd.read_csv(trades_path)
    trades = trades[trades["Result"] != "No-Op"].copy()
    rows = []
    for _, t in trades.iterrows():
        entry_d = pd.Timestamp(t["Entry_Date"]).normalize()
        y, m = map(int, str(t["Period"]).split("-"))
        month_end = pd.Timestamp(year=y, month=m, day=1) + pd.offsets.MonthEnd(0)
        bars = daily[(daily["date"] >= entry_d) & (daily["date"] <= month_end)]
        direction = str(t["Trade_Direction"])
        target = float(t["TP_Price"])
        stop = float(t["Initial_Stop_Price"])
        tp25 = float(t["TP25_Price"])
        hit_1r = "neither"
        hit_25 = "neither"
        for _, b in bars.iterrows():
            h, l = float(b["high"]), float(b["low"])
            if direction == "Long":
                if l <= stop:
                    hit_1r = "opposite"
                    break
                if h >= target:
                    hit_1r = "target_1r"
                    break
            else:
                if h >= stop:
                    hit_1r = "opposite"
                    break
                if l <= target:
                    hit_1r = "target_1r"
                    break
        for _, b in bars.iterrows():
            h, l = float(b["high"]), float(b["low"])
            if direction == "Long":
                if l <= stop:
                    hit_25 = "opposite"
                    break
                if h >= tp25:
                    hit_25 = "tp25"
                    break
            else:
                if h >= stop:
                    hit_25 = "opposite"
                    break
                if l <= tp25:
                    hit_25 = "tp25"
                    break
        rows.append(
            {
                "period": t["Period"],
                "direction": direction,
                "path_1r": hit_1r,
                "path_tp25": hit_25,
                "unit2_exit": t.get("Unit2_Exit_Reason"),
                "final_reason": t.get("Final_Reason"),
            }
        )
    rdf = pd.DataFrame(rows)
    n = len(rdf)
    c1 = rdf["path_1r"].value_counts().to_dict()
    c25 = rdf["path_tp25"].value_counts().to_dict()
    resolved = rdf[rdf["path_1r"].isin(["target_1r", "opposite"])]
    resolved25 = rdf[rdf["path_tp25"].isin(["tp25", "opposite"])]
    cond_1r = float((resolved["path_1r"] == "target_1r").mean()) if len(resolved) else float("nan")
    cond_25 = float((resolved25["path_tp25"] == "tp25").mean()) if len(resolved25) else float("nan")
    # Sim exit: full TP fill rate (Unit2)
    u2_tp = float((trades["Unit2_Exit_Reason"] == "TP").mean()) if n else float("nan")
    boundary = float(
        trades["Final_Reason"].astype(str).str.contains("Boundary-Stop").mean()
    ) if n else float("nan")
    return {
        "label": label,
        "n": n,
        "path_1r_counts": c1,
        "path_tp25_counts": c25,
        "hitrate_1r_unconditional": float(c1.get("target_1r", 0) / n) if n else float("nan"),
        "hitrate_1r_vs_opposite": cond_1r,
        "n_resolved_1r": int(len(resolved)),
        "hitrate_tp25_vs_opposite": cond_25,
        "n_resolved_tp25": int(len(resolved25)),
        "sim_unit2_tp_rate": u2_tp,
        "sim_boundary_stop_rate": boundary,
        "rows": rows,
    }


def _broker_trades_enriched(state_root: Path, market: str) -> pd.DataFrame:
    """One row per campaign with all exit legs + plan levels."""
    paths = _resolve_paths(state_root, None, None)
    campaigns = load_campaigns(paths)
    fills = pd.read_csv(paths.fills)
    orders = pd.read_csv(state_root / "orders.csv") if (state_root / "orders.csv").exists() else pd.DataFrame()
    plans_path = state_root.parent.parent / "month_plans.json"
    if not plans_path.exists():
        # all_weeks/states/... → all_weeks/month_plans.json
        plans_path = state_root.parent.parent / "month_plans.json"
    plans: Dict[str, dict] = {}
    if plans_path.exists():
        raw = json.loads(plans_path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            for p in raw:
                plans["%04d-%02d" % (int(p["year"]), int(p["month"]))] = p
        elif isinstance(raw, dict):
            plans = {str(k): v for k, v in raw.items()}

    rows: List[dict] = []
    for camp in campaigns.itertuples(index=False):
        trade_id = str(camp.trade_id)
        tf = fills[fills["trade_id"].astype(str) == trade_id].sort_values("ts")
        if tf.empty:
            continue
        entry_fill = tf[tf["reason"].astype(str) == "entry"]
        if entry_fill.empty:
            continue
        entry_fill = entry_fill.iloc[0]
        entry_ts = pd.Timestamp(entry_fill["ts"])
        if entry_ts.tzinfo is None:
            entry_ts = entry_ts.tz_localize("UTC")
        entry_ts_ny = entry_ts.tz_convert(NY)
        side = str(camp.side).lower()
        entry_px = float(entry_fill["price"])
        exits = []
        for _, ef in tf[tf["reason"].astype(str) != "entry"].iterrows():
            exits.append(
                {
                    "ts": pd.Timestamp(ef["ts"]),
                    "px": float(ef["price"]),
                    "reason": str(ef["reason"]),
                    "qty": float(ef["quantity"]),
                }
            )
        stop_px = float("nan")
        target_px = float("nan")
        if not orders.empty and "trade_id" in orders.columns:
            to = orders[orders["trade_id"].astype(str) == trade_id]
            stop_rows = to[to["bracket_role"].astype(str) == "stop"]
            tgt_rows = to[to["bracket_role"].astype(str) == "target"]
            if not stop_rows.empty and pd.notna(stop_rows.iloc[0].get("stop_price")):
                stop_px = float(stop_rows.iloc[0]["stop_price"])
            if not tgt_rows.empty and pd.notna(tgt_rows.iloc[0].get("limit_price")):
                target_px = float(tgt_rows.iloc[0]["limit_price"])
        y, m = int(entry_ts_ny.year), int(entry_ts_ny.month)
        key = "%04d-%02d" % (y, m)
        plan = plans.get(key) or {}
        month_open = float(plan.get("month_open") or float("nan"))
        leg = (plan.get("long") if side == "long" else plan.get("short")) or {}
        if not np.isfinite(stop_px) and leg.get("stop") is not None:
            stop_px = float(leg["stop"])
        if not np.isfinite(target_px) and leg.get("target") is not None:
            target_px = float(leg["target"])
        if not np.isfinite(month_open) and leg.get("target") is not None:
            month_open = float(leg["target"])
        if not np.isfinite(entry_px) and leg.get("entry") is not None:
            entry_px = float(leg["entry"])
        initial_r = abs(entry_px - stop_px) if np.isfinite(stop_px) else float("nan")
        if side == "long":
            runner_tp = (month_open + RUNNER_R_MULT * initial_r) if np.isfinite(month_open) and np.isfinite(initial_r) else float("nan")
        else:
            runner_tp = (month_open - RUNNER_R_MULT * initial_r) if np.isfinite(month_open) and np.isfinite(initial_r) else float("nan")
        last_exit = exits[-1] if exits else None
        rows.append(
            {
                "market": market.upper(),
                "trade_id": trade_id,
                "year": y,
                "month": m,
                "side": side,
                "entry_ts": entry_ts_ny,
                "entry_px": entry_px,
                "stop_px": stop_px,
                "target_px": target_px if np.isfinite(target_px) else month_open,
                "month_open": month_open,
                "runner_tp": runner_tp,
                "initial_r": initial_r,
                "exits": exits,
                "exit_ts": last_exit["ts"].tz_convert(NY) if last_exit and last_exit["ts"].tzinfo else (pd.Timestamp(last_exit["ts"]).tz_localize("UTC").tz_convert(NY) if last_exit else entry_ts_ny),
                "exit_px": last_exit["px"] if last_exit else entry_px,
                "exit_reason": last_exit["reason"] if last_exit else "open",
                "pnl_usd": float(camp.net_usd),
            }
        )
    return pd.DataFrame(rows).sort_values(["year", "month", "entry_ts"]).reset_index(drop=True)


def _hline(ax, y, t0, t1, color, style, lw, label, labeled: set) -> None:
    lab = label if label not in labeled else None
    ax.hlines(y, t0, t1, colors=color, linestyles=style, linewidth=lw, alpha=0.95, zorder=5, label=lab)
    if lab:
        labeled.add(label)


def plot_overlay(
    *,
    bars_4h: pd.DataFrame,
    trade: pd.Series,
    band,
    path_stats,
    orb: Optional[MonthlyOrb],
    t0: pd.Timestamp,
    t1: pd.Timestamp,
    out_path: Path,
    market: str = "NQ",
) -> None:
    mkt = str(market).upper()
    fig, ax = plt.subplots(figsize=(20, 8.4))
    shade_weeks(ax, t0, t1)
    window = bars_4h[(bars_4h.index >= t0) & (bars_4h.index < t1)].copy()
    plot_candles_4h(ax, window)

    month_open = float(trade["month_open"]) if np.isfinite(trade["month_open"]) else float(path_stats.month_open)
    atr14 = float(path_stats.atr14)
    up_min, up_med, up_max, dn_min, dn_med, dn_max = _band_from_working(band)
    side = str(trade["side"])
    labeled: set = set()
    extras: List[float] = [month_open]

    if side == "long":
        entry_atr, stop_atr = _entry_stop_atr(dn_min, dn_med, dn_max, entry_mode=ENTRY_MODE, sl_mode=SL_MODE)
        inner = month_open - dn_min * atr14
        outer = month_open - dn_max * atr14
        med = month_open - dn_med * atr14
        lo, hi = sorted((inner, outer))
        ax.axhspan(lo, hi, color=BAND_FILL, alpha=0.32, zorder=1, label="dn band")
        labeled.add("dn band")
    else:
        entry_atr, stop_atr = _entry_stop_atr(up_min, up_med, up_max, entry_mode=ENTRY_MODE, sl_mode=SL_MODE)
        inner = month_open + up_min * atr14
        outer = month_open + up_max * atr14
        med = month_open + up_med * atr14
        lo, hi = sorted((inner, outer))
        ax.axhspan(lo, hi, color=BAND_FILL, alpha=0.32, zorder=1, label="up band")
        labeled.add("up band")

    for val, name, color, style, lw in [
        (inner, "band min", BAND_EDGE, ":", 1.0),
        (med, "band med", BAND_MED, "--", 1.0),
        (outer, "band max", BAND_EDGE, ":", 1.1),
        (float(trade["entry_px"]), "band-max entry", ENTRY_COLOR, "-", 1.5),
        (float(trade["stop_px"]), "SL max+0.5", STOP_COLOR, "-", 1.5),
        (month_open, "month open / open TP", TARGET_OPEN, "-", 1.6),
        (float(trade["runner_tp"]), "runner TP (open±2R)", RUNNER_TP, "-.", 1.5),
    ]:
        if not np.isfinite(val):
            continue
        _hline(ax, val, t0, t1, color, style, lw, name, labeled)
        extras.append(val)

    # --- Monthly ORB overlay ---
    if orb is not None:
        form = orb.form_ts
        # Shade OR formation window (first 3 sessions)
        orb_t0 = orb.range_day_dates[0].replace(hour=9, minute=30)
        if orb_t0.tzinfo is None:
            orb_t0 = orb_t0.tz_localize(NY)
        ax.axvspan(
            max(orb_t0, t0),
            min(form, t1),
            color=ORB_FILL,
            alpha=0.22,
            zorder=0,
            label="monthly OR forming (D1–D3)",
        )
        labeled.add("monthly OR forming (D1–D3)")
        if t0 <= form <= t1:
            ax.axvline(
                form,
                color=ORB_FORM,
                lw=1.8,
                ls="-",
                alpha=0.95,
                zorder=7,
                label="monthly OR formed",
            )
            labeled.add("monthly OR formed")
            ax.annotate(
                "OR formed",
                xy=(form.to_pydatetime(), orb.range_high),
                xytext=(8, 12),
                textcoords="offset points",
                fontsize=8,
                color=ORB_FORM,
                fontweight="bold",
            )
        # OR levels from form → month end
        orb_from = max(form, t0)
        for val, name, color, style in [
            (orb.range_high, "OR high", ORB_HI, "--"),
            (orb.range_low, "OR low", ORB_LO, "--"),
            (orb.long_target, "OR 1R long tgt", ORB_TGT_LONG, ":"),
            (orb.short_target, "OR 1R short tgt", ORB_TGT_SHORT, ":"),
        ]:
            _hline(ax, val, orb_from, t1, color, style, 1.35, name, labeled)
            extras.append(val)
        # OR box height marker
        ax.add_patch(
            Rectangle(
                (mdates.date2num(orb_from.to_pydatetime()), orb.range_low),
                mdates.date2num(t1.to_pydatetime()) - mdates.date2num(orb_from.to_pydatetime()),
                orb.range_pts,
                fill=False,
                edgecolor=ORB_FORM,
                linewidth=1.2,
                linestyle="--",
                alpha=0.7,
                zorder=4,
            )
        )

    # Fill markers
    entry_ts = pd.Timestamp(trade["entry_ts"])
    marker = "^" if side == "long" else "v"
    ax.scatter(
        [entry_ts.to_pydatetime()],
        [float(trade["entry_px"])],
        marker=marker,
        s=170,
        color=ENTRY_COLOR,
        edgecolors="white",
        linewidths=0.8,
        zorder=10,
        label="entry",
    )
    for ex in trade["exits"] or []:
        ts = ex["ts"]
        if getattr(ts, "tzinfo", None) is None:
            ts = pd.Timestamp(ts).tz_localize("UTC")
        ts = ts.tz_convert(NY)
        reason = str(ex["reason"])
        color = {
            "target": EXIT_TARGET,
            "stop": EXIT_STOP,
            "flatten": EXIT_EOM,
        }.get(reason, EXIT_EOM)
        lab = "exit %s" % reason
        if lab in labeled:
            lab = None
        else:
            labeled.add("exit %s" % reason)
        ax.scatter(
            [ts.to_pydatetime()],
            [float(ex["px"])],
            marker="x",
            s=120,
            color=color,
            linewidths=2.0,
            zorder=11,
            label=lab,
        )

    if not window.empty:
        y_lo = float(window["low"].min())
        y_hi = float(window["high"].max())
        for v in extras:
            if v is not None and np.isfinite(v):
                y_lo = min(y_lo, float(v))
                y_hi = max(y_hi, float(v))
        pad = max((y_hi - y_lo) * 0.06, 1.0)
        ax.set_ylim(y_lo - pad, y_hi + pad)

    ax.set_xlim(t0, t1)
    orb_bits = ""
    if orb is not None:
        orb_bits = " · OR %.0f–%.0f (%.0f pts) formed %s" % (
            orb.range_low,
            orb.range_high,
            orb.range_pts,
            orb.form_ts.strftime("%m-%d"),
        )
    ax.set_title(
        "%s 4h · Band-max +0.5 · open TP + 2R  ·  %04d-%02d %s  ·  last=%s  ·  pnl $%s%s"
        % (
            mkt,
            int(trade["year"]),
            int(trade["month"]),
            side,
            trade["exit_reason"],
            "{:,.0f}".format(float(trade["pnl_usd"])),
            orb_bits,
        ),
        fontsize=12,
        pad=10,
    )
    ax.set_ylabel(mkt)
    ax.grid(True, color="#dedede", linewidth=0.55, alpha=0.75)
    ax.legend(loc="lower right", fontsize=7.5, ncol=2, framealpha=0.92)
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO, tz=NY))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d", tz=NY))
    ax.set_xlabel("America/New_York")
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=115, bbox_inches="tight")
    plt.close(fig)


def _pack_batches(paths: List[Path]) -> List[List[Path]]:
    batches: List[List[Path]] = []
    cur: List[Path] = []
    cur_bytes = 0
    for p in paths:
        if not p.exists():
            continue
        sz = p.stat().st_size
        if cur and (len(cur) >= PNG_MAX_PER_EMAIL or cur_bytes + sz > PNG_BATCH_BYTES):
            batches.append(cur)
            cur, cur_bytes = [], 0
        cur.append(p)
        cur_bytes += sz
    if cur:
        batches.append(cur)
    return batches


def write_hitrate_report(output_root: Path, results: Sequence[Dict[str, object]]) -> str:
    lines = [
        "# Monthly ORB restricted scaleout3 — target before opposite OR",
        "",
        "Path race after breakout entry on **daily** OHLC (stop before target same bar).",
        "Ignores range-close exits — pure geometry: does price touch **1R TP**",
        "(`entry ± OR width`) before the **opposite OR boundary**?",
        "",
    ]
    for r in results:
        n = int(r["n"])
        c1 = r["path_1r_counts"]
        lines += [
            "## %s (n=%d bundles)" % (r["label"], n),
            "",
            "| Outcome | Count | Rate |",
            "|---|---:|---:|",
            "| 1R target first | %d | %.1f%% |"
            % (int(c1.get("target_1r", 0)), 100.0 * float(r["hitrate_1r_unconditional"])),
            "| Opposite OR first | %d | %.1f%% |"
            % (int(c1.get("opposite", 0)), 100.0 * c1.get("opposite", 0) / n if n else 0),
            "| Neither by month-end | %d | %.1f%% |"
            % (int(c1.get("neither", 0)), 100.0 * c1.get("neither", 0) / n if n else 0),
            "",
            "- **Conditional hitrate** (1R before opposite | either touched): "
            "**%.1f%%** (n=%d resolved)"
            % (100.0 * float(r["hitrate_1r_vs_opposite"]), int(r["n_resolved_1r"])),
            "- TP25 before opposite (conditional): **%.1f%%** (n=%d)"
            % (100.0 * float(r["hitrate_tp25_vs_opposite"]), int(r["n_resolved_tp25"])),
            "- Sim Unit2 full-TP fill rate (range-close can exit first): %.1f%%"
            % (100.0 * float(r["sim_unit2_tp_rate"])),
            "- Sim Boundary-Stop rate: %.1f%%" % (100.0 * float(r["sim_boundary_stop_rate"])),
            "",
        ]
    lines += [
        "## Read for Band-max overlay",
        "",
        "Monthly ORB 1R target is hit before the opposite boundary on ~**70%** of",
        "resolved NQ paths. Opposite-boundary stopouts are uncommon in the",
        "*restricted* sim because range-close often exits earlier — but the raw",
        "path race is the relevant figure for using OR levels as a management overlay.",
        "",
    ]
    text = "\n".join(lines)
    (output_root / "HITRATE.md").write_text(text + "\n", encoding="utf-8")
    # CSV detail
    for r in results:
        slug_lab = slug(str(r["label"]))
        with (output_root / ("hitrate_%s.csv" % slug_lab)).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(
                fh,
                fieldnames=["period", "direction", "path_1r", "path_tp25", "unit2_exit", "final_reason"],
            )
            w.writeheader()
            for row in r["rows"]:  # type: ignore[index]
                w.writerow(row)
    return text


def build(
    *,
    market: str,
    state_root: Path,
    output_root: Path,
    email: bool,
    force: bool,
    limit: Optional[int],
    attach_charts: bool = True,
) -> None:
    mkt = str(market).upper()
    if mkt not in MARKETS:
        raise SystemExit("Unknown market %s (want %s)" % (mkt, ",".join(sorted(MARKETS))))
    output_root.mkdir(parents=True, exist_ok=True)
    charts_dir = output_root / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    daily = daily_path_for(mkt)
    so3 = so3_path_for(mkt)
    hit_results: List[Dict[str, object]] = []
    primary_hit: Optional[Dict[str, object]] = None
    _progress(output_root, "HITRATE compute market=%s daily=%s" % (mkt, daily))
    if so3 is not None:
        primary_hit = path_hitrate(daily, so3, "%s restricted scaleout3" % mkt)
        hit_results.append(primary_hit)
        _progress(
            output_root,
            "HITRATE %s 1R-before-opp=%.1f%% (cond) uncond=%.1f%%"
            % (
                mkt,
                100.0 * float(primary_hit["hitrate_1r_vs_opposite"]),
                100.0 * float(primary_hit["hitrate_1r_unconditional"]),
            ),
        )
    # Always include NQ/MNQ reference hitrates when available (and not this market).
    for ref, lab in (("NQ", "NQ restricted scaleout3"), ("MNQ", "MNQ restricted scaleout3")):
        if ref == mkt:
            continue
        try:
            ref_daily = daily_path_for(ref)
            ref_so3 = so3_path_for(ref)
        except FileNotFoundError:
            continue
        if ref_so3 is None:
            continue
        hit_results.append(path_hitrate(ref_daily, ref_so3, lab))
    hit_md = write_hitrate_report(output_root, hit_results) if hit_results else ""

    orbs = load_monthly_orbs(daily)
    trades = _broker_trades_enriched(state_root, mkt)
    if limit is not None and limit > 0:
        trades = trades.head(int(limit))
    _progress(output_root, "TRADES n=%d state=%s" % (len(trades), state_root))

    spec = MARKETS[mkt]
    bars_1h = load_1h(spec)
    bars_4h = _resample_ohlc(bars_1h, "4h")
    paths = collect_path_stats(spec)
    paths_by_key = {(p.year, p.month): p for p in paths}

    chart_rows: List[dict] = []
    for _, trade in trades.iterrows():
        y, m = int(trade["year"]), int(trade["month"])
        path = paths_by_key.get((y, m))
        if path is None:
            _progress(output_root, "skip %04d-%02d no path" % (y, m))
            continue
        band = rolling_band_from_paths(
            list(paths_by_key.values()),
            mkt,
            y,
            m,
            window=DEFAULT_ROLLING_BAND_MONTHS,
        )
        if band is None:
            _progress(output_root, "skip %04d-%02d no band" % (y, m))
            continue
        wins = [w for w in month_windows(bars_1h, None, None) if w[0] == y and w[1] == m]
        if not wins:
            continue
        _, _, m0, m1 = wins[0]
        fname = "%04d_%02d_%s_%s.png" % (y, m, trade["side"], slug(str(trade["exit_reason"])))
        out_path = charts_dir / fname
        if out_path.exists() and not force:
            orb = orbs.get((y, m))
            chart_rows.append(
                {
                    "year": y,
                    "month": m,
                    "side": trade["side"],
                    "exit_reason": trade["exit_reason"],
                    "pnl_usd": float(trade["pnl_usd"]),
                    "chart": "charts/%s" % fname,
                    "orb_formed": orb.form_ts.isoformat() if orb else "",
                    "orb_hi": orb.range_high if orb else "",
                    "orb_lo": orb.range_low if orb else "",
                    "orb_long_tgt": orb.long_target if orb else "",
                    "orb_short_tgt": orb.short_target if orb else "",
                }
            )
            continue
        plot_overlay(
            bars_4h=bars_4h,
            trade=trade,
            band=band,
            path_stats=path,
            orb=orbs.get((y, m)),
            t0=m0,
            t1=m1,
            out_path=out_path,
            market=mkt,
        )
        orb = orbs.get((y, m))
        chart_rows.append(
            {
                "year": y,
                "month": m,
                "side": trade["side"],
                "exit_reason": trade["exit_reason"],
                "pnl_usd": float(trade["pnl_usd"]),
                "chart": "charts/%s" % fname,
                "orb_formed": orb.form_ts.isoformat() if orb else "",
                "orb_hi": orb.range_high if orb else "",
                "orb_lo": orb.range_low if orb else "",
                "orb_long_tgt": orb.long_target if orb else "",
                "orb_short_tgt": orb.short_target if orb else "",
            }
        )
        _progress(output_root, "CHART %s" % fname)

    idx = pd.DataFrame(chart_rows)
    idx.to_csv(output_root / "INDEX.csv", index=False)
    md = [
        "# %s Band-max +0.5 · open TP + 2R — monthly ORB overlay charts" % mkt,
        "",
        "Source: `%s`" % state_root,
        "",
        "Each chart: extension band + band-max entry / max+0.5 SL / month-open TP /",
        "runner open±2R, plus **monthly OR** (first 3 daily sessions) — purple form",
        "window + vertical at OR formed, OR high/low, long & short 1R targets.",
        "",
    ]
    if primary_hit is not None:
        md += [
            "## Hitrate (see HITRATE.md)",
            "",
            "- %s 1R before opposite (conditional): **%.1f%%**"
            % (mkt, 100.0 * float(primary_hit["hitrate_1r_vs_opposite"])),
            "- %s 1R first (unconditional of %d): **%.1f%%**"
            % (mkt, int(primary_hit["n"]), 100.0 * float(primary_hit["hitrate_1r_unconditional"])),
            "",
        ]
    elif hit_md:
        md += ["## Hitrate", "", "See HITRATE.md (reference books; no restricted scaleout3 for %s)." % mkt, ""]
    md += [
        "## Charts (%d)" % len(chart_rows),
        "",
        "| # | month | side | exit | pnl | OR formed | chart |",
        "|---:|---|---|---|---:|---|---|",
    ]
    for i, r in enumerate(chart_rows, start=1):
        formed = str(r.get("orb_formed") or "")[:16]
        md.append(
            "| %d | %04d-%02d | %s | %s | %+.0f | %s | [%s](%s) |"
            % (
                i,
                r["year"],
                r["month"],
                r["side"],
                r["exit_reason"],
                r["pnl_usd"],
                formed,
                Path(r["chart"]).name,
                r["chart"],
            )
        )
    summary = "\n".join(md) + "\n"
    (output_root / "SUMMARY.md").write_text(summary, encoding="utf-8")
    (output_root / "INDEX.md").write_text(summary, encoding="utf-8")

    email_lines = [
        "potions: %s Band-max +0.5 · open TP + 2R + monthly ORB overlay" % mkt,
        "",
        "Hub: %s" % output_root,
        "Charts: %d" % len(chart_rows),
        "",
    ]
    if primary_hit is not None:
        email_lines += [
            "Monthly ORB restricted scaleout3 hitrate (%s path race):" % mkt,
            "  1R before opposite (conditional): %.1f%%"
            % (100.0 * float(primary_hit["hitrate_1r_vs_opposite"])),
            "  1R first unconditional: %.1f%% of %d"
            % (100.0 * float(primary_hit["hitrate_1r_unconditional"]), int(primary_hit["n"])),
            "",
        ]
    email_lines += [
        "Stance: research overlay — use OR formed + 1R tgt as management levels on band-max fades.",
        "",
    ]
    if hit_md:
        email_lines.append(hit_md.split("## Read for Band-max overlay")[0].strip())
    email_body = "\n".join(email_lines)
    (output_root / "EMAIL.txt").write_text(email_body + "\n", encoding="utf-8")
    meta = {"charts": len(chart_rows), "market": mkt, "hub": str(output_root)}
    if primary_hit is not None:
        meta["hitrate_1r_conditional"] = float(primary_hit["hitrate_1r_vs_opposite"])
        meta["hitrate_1r_unconditional"] = float(primary_hit["hitrate_1r_unconditional"])
    (output_root / "RUN_COMPLETE.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    try:
        hub_rel = str(output_root.relative_to(REPO))
    except ValueError:
        hub_rel = str(output_root)
    log_run(
        run_class="pandas",
        variant_slug="%s_bandmax_0p5_runner2r_orb_overlay" % mkt.lower(),
        instrument=mkt,
        hub_path=hub_rel,
        trades=len(chart_rows),
        meta=meta,
        notes="band-max +0.5 runner2r charts + monthly ORB overlay",
    )

    if email:
        pngs = sorted(charts_dir.glob("*.png")) if attach_charts else []
        batches = _pack_batches(pngs) if attach_charts else []
        if not batches:
            send_email(
                subject="potions: %s band-max ORB overlay complete" % mkt,
                body=email_body,
            )
        else:
            for i, batch in enumerate(batches, start=1):
                body = email_body + "\nBatch %d/%d — %d PNGs\n" % (i, len(batches), len(batch))
                send_email(
                    subject="potions: %s band-max +0.5 ORB overlay charts (%d/%d)"
                    % (mkt, i, len(batches)),
                    body=body,
                    attachments=batch,
                )
                _progress(output_root, "EMAIL batch %d/%d n=%d" % (i, len(batches), len(batch)))
    _progress(output_root, "DONE charts=%d" % len(chart_rows))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", default="NQ")
    ap.add_argument("--state-root", type=Path, default=None)
    ap.add_argument("--output-root", type=Path, default=None)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-attach-charts", action="store_true", help="Email summary only (no PNG batches)")
    ap.add_argument("--limit", type=int, default=None, help="Chart only first N trades (smoke)")
    args = ap.parse_args()
    market = str(args.market).upper()
    state_root = args.state_root or default_state_root(market)
    output_root = args.output_root or default_chart_out(market)
    try:
        build(
            market=market,
            state_root=state_root,
            output_root=output_root,
            email=bool(args.email),
            force=bool(args.force),
            limit=args.limit,
            attach_charts=not bool(args.no_attach_charts),
        )
        return 0
    except Exception:
        err = traceback.format_exc()
        output_root.mkdir(parents=True, exist_ok=True)
        (output_root / "PROGRESS.log").open("a").write("FAIL\n%s\n" % err)
        try:
            send_email(
                subject="potions: %s band-max ORB overlay FAILED" % market,
                body="Hub: %s\n\n%s\n" % (output_root, err[-2500:]),
            )
        except Exception:
            pass
        raise



if __name__ == "__main__":
    raise SystemExit(main())
