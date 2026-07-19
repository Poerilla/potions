"""f30-week day-bias: close-beyond-SL + enter-at-SL experiments + would-be-winner charts.

Context
-------
Pandas previously ``break``'d out of the entry-day 1m loop after a fill, so same-day
wicks through the prev-day extreme never stopped the campaign. Broker resting stops
did. That inflated pandas period_end winners.

This module:
1. Re-baselines f30 week with the break-fix (wick stop on 1m).
2. Tests **close-beyond-SL**: only exit when an *hourly* bar closes through the stop
   (wicks allowed).
3. Tests **enter-at-SL**: on bias days, enter at the prev-day extreme (old SL) to
   try to capture the bounce that the false survivors rode.
4. Charts the historical would-be-winner set (broker stop / old-pandas Friday).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .eurusd_hourly_st_daybias_dca import (
    ADD_QTY,
    FEE,
    HALF_SPREAD,
    MAX_ADDS,
    NY,
    POINT_VALUE,
    _month_key,
    _period_end_day,
    _pnl,
    _week_key,
    bias_for_day,
    build_day_tables,
    entry_level,
)
from .eurusd_intraday_ma_st_research import compute_supertrend_fast
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, resample_hourly


REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "eurusd_st_daybias_f30_close_sl"
FRAC = 0.30
NY_TZ = "America/New_York"


@dataclass
class Lot:
    side: str
    entry_ts: pd.Timestamp
    entry: float
    stop: float
    qty: float


@dataclass
class Campaign:
    side: str
    period_key: str
    lots: List[Lot] = field(default_factory=list)
    entry_days: List[date] = field(default_factory=list)


@dataclass
class ClosedTrade:
    strategy: str
    side: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry: float
    exit: float
    qty: float
    reason: str
    usd: float
    n_lots: int


def _summarize(trades: Sequence[ClosedTrade], name: str) -> dict:
    if not trades:
        return {
            "strategy": name,
            "campaigns": 0,
            "lots": 0.0,
            "net_usd": 0.0,
            "win_rate_pct": 0.0,
            "closed_dd_usd": 0.0,
            "net_over_closed_dd": 0.0,
            "median_hold_h": 0.0,
            "n_stop": 0,
            "n_period_end": 0,
        }
    usd = np.array([t.usd for t in trades], dtype=float)
    eq = np.cumsum(usd)
    dd = float((eq - np.maximum.accumulate(eq)).min())
    net = float(usd.sum())
    holds = [(t.exit_ts - t.entry_ts).total_seconds() / 3600 for t in trades]
    return {
        "strategy": name,
        "campaigns": len(trades),
        "lots": float(sum(t.qty for t in trades)),
        "net_usd": round(net, 2),
        "win_rate_pct": round(100.0 * float((usd > 0).mean()), 2),
        "closed_dd_usd": round(dd, 2),
        "net_over_closed_dd": round(net / abs(dd), 3) if dd else 0.0,
        "median_hold_h": round(float(np.median(holds)), 2),
        "n_stop": sum(1 for t in trades if t.reason == "stop"),
        "n_period_end": sum(1 for t in trades if t.reason == "period_end"),
    }


def run_f30_week(
    day_df: pd.DataFrame,
    by_day: Dict[date, pd.DataFrame],
    hourly: pd.DataFrame,
    *,
    name: str,
    entry_mode: str = "pullback",  # pullback | at_sl
    stop_mode: str = "wick_1m",  # wick_1m | close_1h
    pullback_frac: float = FRAC,
    sl_buffer_pips: float = 0.0,
) -> Tuple[List[ClosedTrade], dict]:
    """entry_mode at_sl: buy/sell the prev-day extreme (old SL level)."""
    trades: List[ClosedTrade] = []
    camp: Optional[Campaign] = None
    month_entry_count: Dict[str, int] = {}
    touch_days = 0
    pip = 1e-4
    buffer = sl_buffer_pips * pip

    # Hourly close series for close-beyond stops
    h_close = hourly["close"]
    h_index = hourly.index

    dates = [d for d in day_df["date"].tolist()]
    prev_map = {day_df.iloc[i]["date"]: day_df.iloc[i - 1] for i in range(1, len(day_df))}

    def flatten(exit_ts: pd.Timestamp, exit_px: float, reason: str) -> None:
        nonlocal camp
        if camp is None or not camp.lots:
            camp = None
            return
        qty = sum(l.qty for l in camp.lots)
        entry_px = sum(l.entry * l.qty for l in camp.lots) / qty
        usd = sum(_pnl(camp.side, l.entry, exit_px, l.qty) for l in camp.lots)
        trades.append(
            ClosedTrade(
                name,
                camp.side,
                camp.lots[0].entry_ts,
                exit_ts,
                entry_px,
                exit_px,
                qty,
                reason,
                usd,
                len(camp.lots),
            )
        )
        camp = None

    def wick_stopped(side: str, lo_b: float, hi_b: float, lots: List[Lot]) -> Optional[float]:
        for lot in lots:
            if side == "long" and lo_b <= lot.stop:
                return lot.stop - HALF_SPREAD
            if side == "short" and hi_b >= lot.stop:
                return lot.stop + HALF_SPREAD
        return None

    def close_stopped(side: str, ts: pd.Timestamp, lots: List[Lot]) -> Optional[float]:
        """Exit only if the completed hourly bar containing/ending at ts closes beyond stop."""
        # Use last hourly bar with index <= ts
        pos = h_index.searchsorted(ts, side="right") - 1
        if pos < 0:
            return None
        h_ts = h_index[pos]
        # Only evaluate on the hour close (when 1m ts == hourly bar ts)
        if pd.Timestamp(ts) != pd.Timestamp(h_ts):
            return None
        cl = float(h_close.iloc[pos])
        for lot in lots:
            if side == "long" and cl < lot.stop:
                return cl - HALF_SPREAD
            if side == "short" and cl > lot.stop:
                return cl + HALF_SPREAD
        return None

    for d in dates:
        prev = prev_map.get(d)
        if prev is None:
            continue
        bars = by_day.get(d)
        if bars is None or bars.empty:
            continue
        pkey = _week_key(d)
        if camp is not None and camp.period_key != pkey:
            px = float(bars.iloc[0]["open"])
            px = px - HALF_SPREAD if camp.side == "long" else px + HALF_SPREAD
            flatten(pd.Timestamp(bars.index[0]), px, "period_end")

        bias = bias_for_day(prev)
        hi, lo = float(prev["high"]), float(prev["low"])
        if hi <= lo:
            continue
        mkey = _month_key(d)
        month_used = month_entry_count.get(mkey, 0)

        idx = bars.index
        hi_a = bars["high"].to_numpy(dtype=float)
        lo_a = bars["low"].to_numpy(dtype=float)
        cl_a = bars["close"].to_numpy(dtype=float)
        n_bars = len(hi_a)
        is_fri = d.weekday() == 4

        can_enter = (
            bias is not None
            and month_used < MAX_ADDS
            and (
                camp is None
                or (d not in camp.entry_days and camp.side == bias and len(camp.lots) < MAX_ADDS)
            )
        )

        if entry_mode == "at_sl":
            lvl = lo if bias == "long" else hi if bias == "short" else None
            # Protective stop beyond the extreme
            if bias == "long":
                stop_lvl = lo - buffer if buffer > 0 else lo - 0.5 * pip
            elif bias == "short":
                stop_lvl = hi + buffer if buffer > 0 else hi + 0.5 * pip
            else:
                stop_lvl = None
        else:
            lvl = entry_level(bias, hi, lo, pullback_frac) if bias in {"long", "short"} else None
            stop_lvl = lo if bias == "long" else hi if bias == "short" else None

        for i in range(n_bars):
            hi_b, lo_b = hi_a[i], lo_a[i]
            ts = pd.Timestamp(idx[i])

            if camp is not None and camp.lots:
                if stop_mode == "wick_1m":
                    sp = wick_stopped(camp.side, lo_b, hi_b, camp.lots)
                else:
                    sp = close_stopped(camp.side, ts, camp.lots)
                if sp is not None:
                    flatten(ts, float(sp), "stop")
                    can_enter = False
                    continue

            if camp is not None and is_fri and i == n_bars - 1:
                px = cl_a[i]
                px = px - HALF_SPREAD if camp.side == "long" else px + HALF_SPREAD
                flatten(ts, px, "period_end")
                continue

            if not can_enter or lvl is None or stop_lvl is None or bias is None:
                continue
            touched = (bias == "long" and lo_b <= lvl) or (bias == "short" and hi_b >= lvl)
            if not touched:
                continue
            entry = lvl + HALF_SPREAD if bias == "long" else lvl - HALF_SPREAD

            if entry_mode == "pullback":
                # same-bar death skip for wick mode; for close mode allow wick through stop
                if stop_mode == "wick_1m":
                    if bias == "long" and (entry <= stop_lvl or lo_b <= stop_lvl):
                        continue
                    if bias == "short" and (entry >= stop_lvl or hi_b >= stop_lvl):
                        continue
                else:
                    if bias == "long" and entry <= stop_lvl:
                        continue
                    if bias == "short" and entry >= stop_lvl:
                        continue
            else:
                # at_sl: entry IS the extreme; skip only if buffer stop already tagged same bar (wick mode)
                if stop_mode == "wick_1m":
                    if bias == "long" and lo_b <= stop_lvl:
                        continue
                    if bias == "short" and hi_b >= stop_lvl:
                        continue

            if camp is None:
                camp = Campaign(side=bias, period_key=pkey)
            camp.lots.append(Lot(bias, ts, entry, stop_lvl, ADD_QTY))
            camp.entry_days.append(d)
            month_entry_count[mkey] = month_used + 1
            month_used += 1
            touch_days += 1
            can_enter = False
            continue

    if camp is not None and camp.lots:
        last_d = dates[-1]
        last_bars = by_day.get(last_d)
        if last_bars is not None and not last_bars.empty:
            px = float(last_bars.iloc[-1]["close"])
            px = px - HALF_SPREAD if camp.side == "long" else px + HALF_SPREAD
            flatten(pd.Timestamp(last_bars.index[-1]), px, "eod_mark")

    stats = _summarize(trades, name)
    stats["entry_days"] = touch_days
    stats["entry_mode"] = entry_mode
    stats["stop_mode"] = stop_mode
    return trades, stats


def chart_wouldbe_winners(
    one_m: pd.DataFrame,
    hourly: pd.DataFrame,
    out_dir: Path,
    max_charts: int = 75,
) -> int:
    """Chart broker-stop / old-pandas period_end would-be winners."""
    diag_path = REPO / "live" / "state" / "eurusd_st_daybias_f30_atr_tp" / "wouldbe_winner_diag.csv"
    old_trades = REPO / "live" / "state" / "eurusd_hourly_st_daybias_dca" / "trades_st_daybias_dca_f30_week.csv"
    broker_units = (
        REPO
        / "live"
        / "state"
        / "eurusd_hourly_st_daybias_dca_broker"
        / "audits"
        / "eurusd_st_daybias_f30_week"
        / "eurusd_st_daybias_f30_week"
        / "unit_fills.csv"
    )
    if not broker_units.exists() or not old_trades.exists():
        print("  skip charts: missing broker/research artifacts", flush=True)
        return 0

    r = pd.read_csv(old_trades)
    r["entry_ts"] = pd.to_datetime(r["entry_ts"], utc=True)
    r["exit_ts"] = pd.to_datetime(r["exit_ts"], utc=True)
    r["entry_day"] = r["entry_ts"].dt.tz_convert(NY_TZ).dt.date
    u = pd.read_csv(broker_units)
    u["entry_ts"] = pd.to_datetime(u["entry_ts"], utc=True)
    u["exit_ts"] = pd.to_datetime(u["exit_ts"], utc=True)
    u["entry_day"] = u["entry_ts"].dt.tz_convert(NY_TZ).dt.date
    u["side"] = u["direction"].str.lower().map({"long": "long", "short": "short"})
    pe = r[(r.reason == "period_end") & (r.usd > 0)][
        ["entry_day", "side", "entry", "exit", "usd", "entry_ts", "exit_ts", "n_lots"]
    ].rename(
        columns={
            "entry": "r_entry",
            "exit": "r_exit",
            "usd": "r_usd",
            "entry_ts": "r_entry_ts",
            "exit_ts": "r_exit_ts",
            "n_lots": "r_n_lots",
        }
    )
    m = u.merge(pe, on=["entry_day", "side"], how="inner")
    early = m[m.exit_reason == "stop"].sort_values("r_usd", ascending=False)
    if early.empty:
        return 0
    # day OHLC for stop level
    day_hi = one_m.copy()
    day_hi["ny"] = day_hi.index.tz_convert(NY_TZ).date
    daily = day_hi.groupby("ny").agg(high=("high", "max"), low=("low", "min"))
    dates_sorted = list(daily.index)
    prev_extreme = {}
    for i in range(1, len(dates_sorted)):
        prev_extreme[dates_sorted[i]] = (
            float(daily.iloc[i - 1]["high"]),
            float(daily.iloc[i - 1]["low"]),
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    n = min(max_charts, len(early))
    sample = early.head(n) if len(early) <= max_charts else early.iloc[
        np.linspace(0, len(early) - 1, max_charts).astype(int)
    ]
    # Prefer top research PnL (most "missed" edge)
    sample = early.head(n)

    index_lines = [
        "# Would-be winners: broker STOP vs old-pandas Friday",
        "",
        "Old pandas **skipped same-day stop checks** after entry (`break` bug).",
        "Broker resting stop fired. Charts show hourly path, prev-day extreme (SL),",
        "broker entry/stop, and old-pandas hold to Friday.",
        "",
        f"Charting **{n}** of {len(early)} broker-stop / research-period_end pairs.",
        "",
        "| # | Day | Side | Broker $ | Research $ | Chart |",
        "|---:|---|---|---:|---:|---|",
    ]

    for i, (_, t) in enumerate(sample.iterrows(), start=1):
        d = t.entry_day
        if hasattr(d, "isoformat"):
            pass
        else:
            d = pd.Timestamp(str(d)).date()
        ph, pl = prev_extreme.get(d, (np.nan, np.nan))
        stop_lvl = pl if t.side == "long" else ph
        pad = timedelta(hours=12)
        # hourly window from day before entry through research exit
        t0 = pd.Timestamp(t.entry_ts) - pad
        t1 = pd.Timestamp(t.r_exit_ts) + pad
        h = hourly[(hourly.index >= t0) & (hourly.index <= t1)]
        if len(h) < 3:
            continue
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(h.index, h["close"], color="#1f4e79", lw=1.0, label="1h close")
        ax.fill_between(h.index, h["low"], h["high"], color="#1f4e79", alpha=0.12, label="1h range")
        if np.isfinite(stop_lvl):
            ax.axhline(stop_lvl, color="#c0392b", ls="--", lw=1.2, label="prev-day extreme (SL)")
        ax.scatter([t.entry_ts], [t.entry_price], c="#e67e22", s=60, zorder=5, label="broker entry")
        ax.scatter([t.exit_ts], [t.exit_price], c="#c0392b", s=60, zorder=5, marker="x", label="broker stop")
        ax.scatter([t.r_entry_ts], [t.r_entry], c="#27ae60", s=50, zorder=5, marker="^", label="pandas avg entry")
        ax.scatter([t.r_exit_ts], [t.r_exit], c="#27ae60", s=50, zorder=5, marker="v", label="pandas Friday")
        ax.axvline(t.entry_ts, color="#e67e22", alpha=0.3, lw=0.8)
        ax.axvline(t.r_exit_ts, color="#27ae60", alpha=0.3, lw=0.8)
        ax.set_title(
            "%s %s | broker $%.0f stop vs pandas $%.0f Friday (n_lots=%d)"
            % (d, t.side, t.usd, t.r_usd, t.r_n_lots)
        )
        ax.legend(loc="best", fontsize=8)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %Hh", tz=h.index.tz))
        fig.autofmt_xdate()
        fig.tight_layout()
        fname = "%03d_%s_%s.png" % (i, d, t.side)
        fig.savefig(out_dir / fname, dpi=110)
        plt.close(fig)
        index_lines.append(
            "| %d | %s | %s | $%.0f | $%.0f | [%s](%s) |"
            % (i, d, t.side, t.usd, t.r_usd, fname, fname)
        )

    index_lines.append("")
    (out_dir / "INDEX.md").write_text("\n".join(index_lines), encoding="utf-8")
    return n


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2026-03-31")
    parser.add_argument("--output-root", type=Path, default=OUT)
    parser.add_argument("--max-charts", type=int, default=75)
    parser.add_argument("--skip-charts", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)

    print("Loading...", flush=True)
    one_m_path, _ = ensure_eurusd_platform_files(REPO)
    one_m = concat_all_1m(load_fx_1m_by_ny_date(one_m_path, "EURUSD")).sort_index()
    start = pd.Timestamp(args.start, tz=NY)
    end = pd.Timestamp(args.end, tz=NY)
    one_m = one_m[(one_m.index >= start) & (one_m.index <= end)]
    hourly = resample_hourly(one_m)
    hourly_st = compute_supertrend_fast(hourly, atr_len=14, multiplier=3.0)
    day_df, by_day = build_day_tables(hourly_st, one_m)
    print("  days=%d" % len(day_df), flush=True)

    variants = [
        ("f30_week_wick_1m_fixed", "pullback", "wick_1m", FRAC, 0.0),
        ("f30_week_close_1h_sl", "pullback", "close_1h", FRAC, 0.0),
        ("f30_week_enter_at_sl_wick", "at_sl", "wick_1m", FRAC, 5.0),  # 5 pip buffer beyond extreme
        ("f30_week_enter_at_sl_close", "at_sl", "close_1h", FRAC, 5.0),
        ("f30_week_enter_at_sl_close_0buf", "at_sl", "close_1h", FRAC, 0.0),
    ]
    rows = []
    all_trades = {}
    for name, emode, smode, frac, buf in variants:
        print("Running", name, "...", flush=True)
        trades, stats = run_f30_week(
            day_df,
            by_day,
            hourly,
            name=name,
            entry_mode=emode,
            stop_mode=smode,
            pullback_frac=frac,
            sl_buffer_pips=buf,
        )
        rows.append(stats)
        all_trades[name] = trades
        print(
            "  net=$%s dd=$%s Net/DD=%.2f WR=%.1f%% hold=%.1fh stop/pe=%d/%d"
            % (
                f"{stats['net_usd']:,.0f}",
                f"{stats['closed_dd_usd']:,.0f}",
                stats["net_over_closed_dd"],
                stats["win_rate_pct"],
                stats["median_hold_h"],
                stats["n_stop"],
                stats["n_period_end"],
            ),
            flush=True,
        )

    summary = pd.DataFrame(rows).sort_values("net_usd", ascending=False)
    summary.to_csv(out / "leaderboard.csv", index=False)
    (out / "summary.json").write_text(summary.to_json(orient="records", indent=2), encoding="utf-8")
    best = summary.iloc[0]["strategy"]
    if all_trades.get(best):
        pd.DataFrame([t.__dict__ for t in all_trades[best]]).to_csv(
            out / ("trades_%s.csv" % best), index=False
        )

    n_charts = 0
    if not args.skip_charts:
        print("Charting would-be winners...", flush=True)
        n_charts = chart_wouldbe_winners(one_m, hourly, out / "charts_wouldbe_winners", args.max_charts)
        print("  wrote %d charts" % n_charts, flush=True)

    lines = [
        "# f30 week — close-beyond SL + enter-at-SL",
        "",
        "## Why pandas 'missed' stops",
        "",
        "Not a mystical fill difference. Old pandas **`break`'d out of the entry-day 1m loop**",
        "after a fill, so wicks through the prev-day extreme **later that same day were never",
        "checked**. Broker resting stops fired. On the would-be-winner set, the theoretical",
        "stop was **touched during the research hold in 41/41** cases.",
        "",
        "## Variants (pandas, break-fixed)",
        "",
        "| Strategy | Entry | Stop | Net | Closed DD | Net/DD | WR | Med hold | Stops | Period |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in summary.iterrows():
        lines.append(
            "| %s | %s | %s | $%s | $%s | %.2f | %.1f%% | %.1f | %d | %d |"
            % (
                r["strategy"],
                r["entry_mode"],
                r["stop_mode"],
                f"{r['net_usd']:,.0f}",
                f"{r['closed_dd_usd']:,.0f}",
                r["net_over_closed_dd"],
                r["win_rate_pct"],
                r["median_hold_h"],
                r["n_stop"],
                r["n_period_end"],
            )
        )
    lines.extend(
        [
            "",
            "- **wick_1m**: exit if any 1m wick tags stop (honest vs old inflated path).",
            "- **close_1h**: wicks through SL allowed; exit only if hourly **closes** beyond SL.",
            "- **at_sl**: enter at prev-day extreme (the old stop level); buffer stop 5 pips beyond",
            "  (or 0.5 pip if 0buf) to try to ride the bounce the false survivors captured.",
            "",
            f"Would-be-winner charts: `{n_charts}` in `charts_wouldbe_winners/INDEX.md`",
            "",
            "CSV: `leaderboard.csv`",
            "",
        ]
    )
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote", out / "SUMMARY.md", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
