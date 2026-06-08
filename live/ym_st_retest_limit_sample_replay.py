from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
MNQ_ROOT = REPO / "mnq"
CASE = MNQ_ROOT / "case_studies" / "midnight_open_hourly_charts"
SCRIPTS = REPO / "scripts"

sys.path[:0] = [str(REPO.parent), str(MNQ_ROOT), str(SCRIPTS), str(CASE)]

from potions.live.build_ym_1m_atr_supertrend_sample import (  # noqa: E402
    compute_supertrend,
    resample_ohlcv_by_rows,
    supertrend_overlay,
)
from potions.live.v2b_strategy_cross_market_replay import (  # noqa: E402
    _rth_bars,
    load_1m_by_ny_date_any,
)

POINT_VALUE = 5.0
FEE_PER_SIDE = 1.50
SLIPPAGE_TICKS = 1.0
TICK_SIZE = 1.0


@dataclass
class Trade:
    day: str
    side: str
    entry_ts: str
    exit_ts: str
    entry: float
    exit: float
    stop: float
    target: float
    pnl_pts: float
    pnl_usd: float
    result: str


def parse_index_days(index_path: Path) -> List[str]:
    text = index_path.read_text(encoding="utf-8")
    days = re.findall(r"^\|\s*\d+\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|", text, flags=re.MULTILINE)
    if not days:
        raise SystemExit(f"No session dates found in {index_path}")
    return days


def _fill_stop(side: str, stop: float, o: float, h: float, l: float) -> float:
    if side == "long":
        if l <= stop:
            return o if o < stop else stop - SLIPPAGE_TICKS * TICK_SIZE
    else:
        if h >= stop:
            return o if o > stop else stop + SLIPPAGE_TICKS * TICK_SIZE
    return stop


def _fill_target(side: str, target: float, h: float, l: float) -> float:
    return target


def simulate_session(
    day: str,
    df: pd.DataFrame,
    *,
    st_minutes: int,
    atr_len: int,
    atr_mult: float,
    stop_pts: float,
    target_pts: float,
) -> Tuple[List[Trade], dict]:
    overlay = supertrend_overlay(df, minutes=st_minutes, atr_len=atr_len, multiplier=atr_mult)
    plot = df.copy()
    plot["st"] = overlay["supertrend"]
    plot["trend"] = overlay["supertrend_trend"]

    trades: List[Trade] = []
    phase = "flat"  # flat | in
    side: Optional[str] = None
    entry_px = stop_px = target_px = 0.0
    entry_ts = ""
    open_trend: Optional[int] = None

    for ts, row in plot.iterrows():
        st = row["st"]
        trend = row["trend"]
        if pd.isna(st) or pd.isna(trend):
            continue
        if open_trend is None:
            open_trend = int(trend)

        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        ts_s = pd.Timestamp(ts).isoformat()

        if phase == "in":
            closed = False
            exit_px = 0.0
            result = ""
            if side == "long":
                stop_fill = _fill_stop("long", stop_px, o, h, l)
                if l <= stop_px:
                    exit_px = stop_fill
                    result = "loss"
                    closed = True
                elif h >= target_px:
                    exit_px = _fill_target("long", target_px, h, l)
                    result = "win"
                    closed = True
            else:
                stop_fill = _fill_stop("short", stop_px, o, h, l)
                if h >= stop_px:
                    exit_px = stop_fill
                    result = "loss"
                    closed = True
                elif l <= target_px:
                    exit_px = _fill_target("short", target_px, h, l)
                    result = "win"
                    closed = True

            if closed:
                pnl_pts = (exit_px - entry_px) if side == "long" else (entry_px - exit_px)
                pnl_usd = pnl_pts * POINT_VALUE - 2 * FEE_PER_SIDE
                trades.append(
                    Trade(
                        day=day,
                        side=side,
                        entry_ts=entry_ts,
                        exit_ts=ts_s,
                        entry=entry_px,
                        exit=exit_px,
                        stop=stop_px,
                        target=target_px,
                        pnl_pts=pnl_pts,
                        pnl_usd=pnl_usd,
                        result=result,
                    )
                )
                phase = "flat"
                side = None
            continue

        # Flat: maintain limit at current ST stop in the active trend direction.
        limit_side = "long" if int(trend) == 1 else "short"
        limit_px = float(st)

        filled = False
        if limit_side == "long" and l <= limit_px:
            entry_px = limit_px
            side = "long"
            filled = True
        elif limit_side == "short" and h >= limit_px:
            entry_px = limit_px
            side = "short"
            filled = True

        if filled:
            entry_ts = ts_s
            if side == "long":
                stop_px = entry_px - stop_pts
                target_px = entry_px + target_pts
            else:
                stop_px = entry_px + stop_pts
                target_px = entry_px - target_pts
            phase = "in"

    # Flatten any open position at session end.
    if phase == "in" and side is not None:
        last = plot.iloc[-1]
        exit_px = float(last["close"])
        ts_s = pd.Timestamp(plot.index[-1]).isoformat()
        pnl_pts = (exit_px - entry_px) if side == "long" else (entry_px - exit_px)
        pnl_usd = pnl_pts * POINT_VALUE - 2 * FEE_PER_SIDE
        trades.append(
            Trade(
                day=day,
                side=side,
                entry_ts=entry_ts,
                exit_ts=ts_s,
                entry=entry_px,
                exit=exit_px,
                stop=stop_px,
                target=target_px,
                pnl_pts=pnl_pts,
                pnl_usd=pnl_usd,
                result="eod",
            )
        )

    meta = {
        "open_trend": "bull" if open_trend == 1 else "bear" if open_trend == -1 else "unknown",
        "trades": len(trades),
        "net_usd": sum(t.pnl_usd for t in trades),
    }
    return trades, meta


def write_outputs(out_root: Path, trades: List[Trade], day_meta: List[dict], args) -> None:
    out_root.mkdir(parents=True, exist_ok=True)
    trade_rows = [
        {
            "day": t.day,
            "side": t.side,
            "entry_ts": t.entry_ts,
            "exit_ts": t.exit_ts,
            "entry": f"{t.entry:.2f}",
            "exit": f"{t.exit:.2f}",
            "stop": f"{t.stop:.2f}",
            "target": f"{t.target:.2f}",
            "pnl_pts": f"{t.pnl_pts:.2f}",
            "pnl_usd": f"{t.pnl_usd:.2f}",
            "result": t.result,
        }
        for t in trades
    ]
    trades_path = out_root / "trades.csv"
    if trade_rows:
        with trades_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(trade_rows[0].keys()))
            writer.writeheader()
            writer.writerows(trade_rows)
    else:
        trades_path.write_text("", encoding="utf-8")

    total_net = sum(t.pnl_usd for t in trades)
    wins = [t for t in trades if t.result == "win"]
    losses = [t for t in trades if t.result == "loss"]
    win_rate = 100.0 * len(wins) / len(trades) if trades else 0.0
    gross_win = sum(t.pnl_usd for t in wins)
    gross_loss = abs(sum(t.pnl_usd for t in losses))
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    days_with_trade = sum(1 for m in day_meta if m["trades"] > 0)
    avg_trades = sum(m["trades"] for m in day_meta) / len(day_meta) if day_meta else 0.0

    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        equity += t.pnl_usd
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)

    lines = [
        "# YM 2m ST Retest Limit Sample Replay",
        "",
        f"Sample: `{len(day_meta)}` sessions from `{args.index.name}`.",
        f"Signal: limit at `{args.st_minutes}m` ATR({args.atr_len}) x {args.atr_mult:g} Supertrend stop.",
        f"Direction: side follows current `{args.st_minutes}m` Supertrend (first reading at RTH open).",
        f"Bracket: `{args.stop_pts:g}` pt stop / `{args.target_pts:g}` pt target.",
        f"Rules: one trade at a time; limit re-armed when flat; RTH 09:30-16:00 only.",
        f"Costs: ${FEE_PER_SIDE:.2f}/side, {SLIPPAGE_TICKS:g} tick stop slippage.",
        "",
        "## Summary",
        "",
        f"- Sessions: **{len(day_meta)}**",
        f"- Sessions with at least one trade: **{days_with_trade}** ({100.0 * days_with_trade / len(day_meta):.1f}%)",
        f"- Total trades: **{len(trades)}** (avg {avg_trades:.2f}/session)",
        f"- Net P/L: **${total_net:,.2f}**",
        f"- Win rate: **{win_rate:.1f}%** ({len(wins)}W / {len(losses)}L)",
        f"- Profit factor: **{pf:.2f}**" if pf != float("inf") else "- Profit factor: **inf** (no losses)",
        f"- Max closed drawdown: **${max_dd:,.2f}**",
        f"- Net / |DD|: **{total_net / abs(max_dd):.2f}**" if max_dd < 0 else "- Net / |DD|: n/a",
        "",
        "## Per-session",
        "",
        "| Day | Open trend | Trades | Net USD |",
        "|---|---|---:|---:|",
    ]
    for m in day_meta:
        lines.append(f"| {m['day']} | {m['open_trend']} | {m['trades']} | ${m['net_usd']:,.2f} |")

    lines.extend(["", "## Trades", "", f"Full log: `{trades_path.name}`", ""])
    (out_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_root / 'SUMMARY.md'}", flush=True)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Replay ST retest limit strategy on YM sample days.")
    parser.add_argument(
        "--index",
        type=Path,
        default=REPO / "ym" / "case_studies" / "ym_1m_candles_2m_atr_supertrend_random_50" / "INDEX.md",
    )
    parser.add_argument(
        "--dbn",
        type=Path,
        default=REPO / "ym" / "raw" / "glbx-mdp3-20100606-20260506.ohlcv-1m.dbn.zst",
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        default=REPO / "ym" / "case_studies" / "ym_1m_candles_2m_atr_supertrend_random_50" / "st_retest_limit_replay",
    )
    parser.add_argument("--st-minutes", type=int, default=2)
    parser.add_argument("--atr-len", type=int, default=14)
    parser.add_argument("--atr-mult", type=float, default=3.0)
    parser.add_argument("--stop-pts", type=float, default=20.0)
    parser.add_argument("--target-pts", type=float, default=100.0)
    args = parser.parse_args(argv)

    days = parse_index_days(args.index)
    print(f"Loading YM 1m data for {len(days)} sample sessions...", flush=True)
    gby = load_1m_by_ny_date_any(args.dbn.resolve(), "ym")

    all_trades: List[Trade] = []
    day_meta: List[dict] = []
    for day_s in days:
        session_day = datetime.strptime(day_s, "%Y-%m-%d").date()
        rth = _rth_bars(gby.get(session_day), session_day)
        if rth.empty:
            day_meta.append({"day": day_s, "open_trend": "missing", "trades": 0, "net_usd": 0.0})
            continue
        trades, meta = simulate_session(
            day_s,
            rth,
            st_minutes=args.st_minutes,
            atr_len=args.atr_len,
            atr_mult=args.atr_mult,
            stop_pts=args.stop_pts,
            target_pts=args.target_pts,
        )
        all_trades.extend(trades)
        day_meta.append({"day": day_s, **meta})

    write_outputs(args.out_root, all_trades, day_meta, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
