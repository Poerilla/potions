from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
MNQ_ROOT = REPO / "mnq"
CASE = MNQ_ROOT / "case_studies" / "midnight_open_hourly_charts"
SCRIPTS = REPO / "scripts"

sys.path[:0] = [str(REPO.parent), str(MNQ_ROOT), str(SCRIPTS), str(CASE)]

from potions.live.build_ym_1m_atr_supertrend_sample import compute_supertrend  # noqa: E402
from potions.live.v2b_strategy_cross_market_replay import load_1m_by_ny_date_any  # noqa: E402

POINT_VALUE = 5.0
FEE_PER_SIDE = 1.50
SLIPPAGE_TICKS = 1.0
TICK_SIZE = 1.0


@dataclass
class Trade:
    side: str
    entry_ts: str
    exit_ts: str
    entry: float
    exit: float
    stop: float
    target: float
    prev_month_close: float
    pnl_pts: float
    pnl_usd: float
    result: str


def load_prev_month_close_map(daily_path: Path) -> Dict[Tuple[int, int], float]:
    daily = pd.read_csv(daily_path, parse_dates=["date"]).sort_values("date")
    daily["year"] = daily["date"].dt.year
    daily["month"] = daily["date"].dt.month
    last = daily.groupby(["year", "month"], as_index=False).tail(1)
    closes = { (int(r.year), int(r.month)): float(r.close) for r in last.itertuples() }

    out: Dict[Tuple[int, int], float] = {}
    for (y, m), _ in closes.items():
        py, pm = (y, m - 1) if m > 1 else (y - 1, 12)
        if (py, pm) in closes:
            out[(y, m)] = closes[(py, pm)]
    return out


def concat_all_1m(gby: Dict[date, pd.DataFrame]) -> pd.DataFrame:
    parts = [df.sort_index() for df in gby.values() if df is not None and not df.empty]
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts).sort_index()


def resample_hourly(df_1m: pd.DataFrame) -> pd.DataFrame:
    return (
        df_1m.resample("1h", label="left", closed="left")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open"])
    )


def _fill_stop(side: str, stop: float, o: float, h: float, l: float) -> float:
    if side == "long":
        if l <= stop:
            return o if o < stop else stop - SLIPPAGE_TICKS * TICK_SIZE
    else:
        if h >= stop:
            return o if o > stop else stop + SLIPPAGE_TICKS * TICK_SIZE
    return stop


def simulate(
    hourly: pd.DataFrame,
    pmc_map: Dict[Tuple[int, int], float],
    *,
    stop_pts: float,
    target_pts: float,
) -> List[Trade]:
    trades: List[Trade] = []
    phase = "flat"
    side: Optional[str] = None
    entry_px = stop_px = target_px = pmc_at_entry = 0.0
    entry_ts = ""

    for ts, row in hourly.iterrows():
        st = row["supertrend"]
        trend = row["supertrend_trend"]
        if pd.isna(st) or pd.isna(trend):
            continue

        y, m = int(ts.year), int(ts.month)
        pmc = pmc_map.get((y, m))
        if pmc is None or not np.isfinite(pmc):
            continue

        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        ts_s = pd.Timestamp(ts).isoformat()

        if phase == "in":
            closed = False
            exit_px = 0.0
            result = ""
            if side == "long":
                if l <= stop_px:
                    exit_px = _fill_stop("long", stop_px, o, h, l)
                    result = "loss"
                    closed = True
                elif h >= target_px:
                    exit_px = target_px
                    result = "win"
                    closed = True
            else:
                if h >= stop_px:
                    exit_px = _fill_stop("short", stop_px, o, h, l)
                    result = "loss"
                    closed = True
                elif l <= target_px:
                    exit_px = target_px
                    result = "win"
                    closed = True

            if closed:
                pnl_pts = (exit_px - entry_px) if side == "long" else (entry_px - exit_px)
                trades.append(
                    Trade(
                        side=side or "",
                        entry_ts=entry_ts,
                        exit_ts=ts_s,
                        entry=entry_px,
                        exit=exit_px,
                        stop=stop_px,
                        target=target_px,
                        prev_month_close=pmc_at_entry,
                        pnl_pts=pnl_pts,
                        pnl_usd=pnl_pts * POINT_VALUE - 2 * FEE_PER_SIDE,
                        result=result,
                    )
                )
                phase = "flat"
                side = None
            continue

        # Flat: limit at hourly ST stop, side filtered by prior-month close.
        limit_px = float(st)
        if c > pmc and int(trend) == 1:
            if l <= limit_px:
                side = "long"
                entry_px = limit_px
                entry_ts = ts_s
                pmc_at_entry = pmc
                stop_px = entry_px - stop_pts
                target_px = entry_px + target_pts
                phase = "in"
        elif c < pmc and int(trend) == -1:
            if h >= limit_px:
                side = "short"
                entry_px = limit_px
                entry_ts = ts_s
                pmc_at_entry = pmc
                stop_px = entry_px + stop_pts
                target_px = entry_px - target_pts
                phase = "in"

    return trades


def summarize(trades: List[Trade]) -> dict:
    if not trades:
        return {"trades": 0}
    wins = [t for t in trades if t.result == "win"]
    losses = [t for t in trades if t.result == "loss"]
    net = sum(t.pnl_usd for t in trades)
    gross_win = sum(t.pnl_usd for t in wins)
    gross_loss = abs(sum(t.pnl_usd for t in losses))
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        equity += t.pnl_usd
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    longs = [t for t in trades if t.side == "long"]
    shorts = [t for t in trades if t.side == "short"]
    return {
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": 100.0 * len(wins) / len(trades),
        "net_usd": net,
        "profit_factor": pf,
        "max_dd_usd": max_dd,
        "net_over_dd": net / abs(max_dd) if max_dd < 0 else float("nan"),
        "long_trades": len(longs),
        "short_trades": len(shorts),
        "long_net": sum(t.pnl_usd for t in longs),
        "short_net": sum(t.pnl_usd for t in shorts),
        "avg_win_usd": gross_win / len(wins) if wins else 0.0,
        "avg_loss_usd": -gross_loss / len(losses) if losses else 0.0,
    }


def write_outputs(out_root: Path, trades: List[Trade], stats: dict, args) -> None:
    out_root.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "side": t.side,
            "entry_ts": t.entry_ts,
            "exit_ts": t.exit_ts,
            "entry": f"{t.entry:.2f}",
            "exit": f"{t.exit:.2f}",
            "stop": f"{t.stop:.2f}",
            "target": f"{t.target:.2f}",
            "prev_month_close": f"{t.prev_month_close:.2f}",
            "pnl_pts": f"{t.pnl_pts:.2f}",
            "pnl_usd": f"{t.pnl_usd:.2f}",
            "result": t.result,
        }
        for t in trades
    ]
    trades_path = out_root / "trades.csv"
    if rows:
        with trades_path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    pf = stats.get("profit_factor", 0.0)
    pf_s = f"{pf:.2f}" if pf != float("inf") else "inf"
    lines = [
        "# YM Hourly ST + Prior Month Close Retest Replay",
        "",
        "Strategy rules:",
        "- Hourly `ATR(14) x 3` Supertrend on all available 1m sessions.",
        "- If price is **above** prior calendar month close → long limit at bullish ST stop.",
        "- If price is **below** prior calendar month close → short limit at bearish ST stop.",
        "- Bracket: `{:.0f}` pt stop / `{:.0f}` pt target (3R). One trade at a time; limit re-armed when flat.".format(
            args.stop_pts, args.target_pts
        ),
        f"- Costs: ${FEE_PER_SIDE:.2f}/side, {SLIPPAGE_TICKS:g} tick stop slippage.",
        "",
        "## Summary",
        "",
        f"- Trades: **{stats.get('trades', 0):,}**",
        f"- Win rate: **{stats.get('win_rate_pct', 0):.1f}%** ({stats.get('wins', 0)}W / {stats.get('losses', 0)}L)",
        f"- Net P/L: **${stats.get('net_usd', 0):,.2f}**",
        f"- Profit factor: **{pf_s}**",
        f"- Max closed drawdown: **${stats.get('max_dd_usd', 0):,.2f}**",
        f"- Net / |DD|: **{stats.get('net_over_dd', float('nan')):.2f}**",
        "",
        "## By side",
        "",
        f"- Longs: {stats.get('long_trades', 0):,} trades, ${stats.get('long_net', 0):,.2f} net",
        f"- Shorts: {stats.get('short_trades', 0):,} trades, ${stats.get('short_net', 0):,.2f} net",
        f"- Avg win: ${stats.get('avg_win_usd', 0):,.2f} | Avg loss: ${stats.get('avg_loss_usd', 0):,.2f}",
        "",
        f"Full log: `{trades_path.name}`",
        "",
    ]
    (out_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Replay YM hourly ST + prior month close limit strategy.")
    parser.add_argument(
        "--dbn",
        type=Path,
        default=REPO / "ym" / "raw" / "glbx-mdp3-20100606-20260506.ohlcv-1m.dbn.zst",
    )
    parser.add_argument("--daily", type=Path, default=REPO / "ym" / "ym_daily.csv")
    parser.add_argument(
        "--out-root",
        type=Path,
        default=REPO / "ym" / "case_studies" / "ym_hourly_st_pmc_retest_replay",
    )
    parser.add_argument("--atr-len", type=int, default=14)
    parser.add_argument("--atr-mult", type=float, default=3.0)
    parser.add_argument("--stop-pts", type=float, default=50.0)
    parser.add_argument("--target-pts", type=float, default=150.0)
    args = parser.parse_args(argv)

    print("Loading YM 1m DBN...", flush=True)
    gby = load_1m_by_ny_date_any(args.dbn.resolve(), "ym")
    print("Building hourly series...", flush=True)
    one_m = concat_all_1m(gby)
    hourly = resample_hourly(one_m)
    hourly = compute_supertrend(hourly, atr_len=args.atr_len, multiplier=args.atr_mult)
    pmc_map = load_prev_month_close_map(args.daily)
    print(f"  {len(hourly):,} hourly bars", flush=True)

    trades = simulate(hourly, pmc_map, stop_pts=args.stop_pts, target_pts=args.target_pts)
    stats = summarize(trades)
    write_outputs(args.out_root, trades, stats, args)
    print(f"Trades: {stats.get('trades', 0)} | Net: ${stats.get('net_usd', 0):,.2f}", flush=True)
    print(f"Wrote {args.out_root / 'SUMMARY.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
