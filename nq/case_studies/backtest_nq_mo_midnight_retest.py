#!/usr/bin/env python3
"""
Backtest MO-bias midnight-close retest on 15m bars (00:00–16:00 NY).

Bias (causal): prior session daily **close** vs current-month **MO**.
- bull → long setups only
- bear → short setups only

Setup (long example):
1. Price trades **below** first-15m **close** (midnight close) on an earlier bar.
2. Later 15m bar **opens below** and **closes above** midnight close (breakout).
3. **Limit entry** @ midnight close on a subsequent bar (retest); max 6 bars to fill.

Exit: TP +200 pts / SL −{30|50|100} pts, or session close (16:00).
Max **2 trades/day**, max **3 wins per bias streak** (resets on MO-side flip).

Usage::

  python3 nq/case_studies/backtest_nq_mo_midnight_retest.py
  python3 nq/case_studies/backtest_nq_mo_midnight_retest.py --chart-sample 100 --force
"""
from __future__ import annotations

import argparse
import random
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Literal

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
POTIONS_ROOT = HERE.parents[1]
MNQ_CS = POTIONS_ROOT / 'mnq' / 'case_studies' / 'midnight_open_hourly_charts'
sys.path.insert(0, str(MNQ_CS))

from build_midnight_open_hourly_charts import (  # noqa: E402
    DEFAULT_DBN_NQ,
    NY,
    load_1m_by_ny_date,
    resample_15m_midnight_to_1600,
)
from build_nq_yearly_daily_levels_study import BG, GREEN_CANDLE, RED_CANDLE, load_daily  # noqa: E402

TARGET_PTS = 200.0
MAX_TRADES_DAY = 2
MAX_WINS_STREAK = 3
MAX_FILL_WAIT_BARS = 6
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
RTH_FILL = '#243B55'
ETH_FILL = '#111D2C'
BULL_COLOR = '#76FF03'
BEAR_COLOR = '#EF5350'
MC_COLOR = '#FFD54F'
MO_COLOR = '#26C6DA'

Side = Literal['long', 'short']


@dataclass
class TradeRecord:
    session: date
    side: Side
    bias: str
    streak_id: str
    midnight_close: float
    mo: float
    breakout_ts: pd.Timestamp
    entry_ts: pd.Timestamp
    entry: float
    exit_ts: pd.Timestamp
    exit: float
    pts: float
    result: str
    stop_pts: float
    attempt: int


@dataclass
class DayState:
    bias: str
    streak_id: str
    streak_wins: int
    trades_taken: int = 0
    stopped_today: bool = False


def build_monthly_mo(daily: pd.DataFrame) -> dict[tuple[int, int], float]:
    work = daily.copy()
    work['ym'] = list(zip(work['date'].dt.year, work['date'].dt.month))
    out: dict[tuple[int, int], float] = {}
    for ym, g in work.groupby('ym', sort=True):
        g = g.sort_values('date')
        out[(int(ym[0]), int(ym[1]))] = float(g['open'].iloc[0])
    return out


def causal_bias(session: date, daily: pd.DataFrame, mo_map: dict[tuple[int, int], float]) -> tuple[str, float] | None:
    ym = (session.year, session.month)
    mo = mo_map.get(ym)
    if mo is None:
        return None
    prior = daily[daily['date'].dt.date < session].sort_values('date')
    if prior.empty:
        return None
    close = float(prior.iloc[-1]['close'])
    bias = 'bull' if close >= mo else 'bear'
    return bias, mo


def bullish_breakout(row: pd.Series, level: float) -> bool:
    o, c = float(row['open']), float(row['close'])
    return o < level < c


def bearish_breakout(row: pd.Series, level: float) -> bool:
    o, c = float(row['open']), float(row['close'])
    return o > level > c


def had_dip_below(bars: pd.DataFrame, level: float, before_idx: int) -> bool:
    for i in range(1, before_idx):
        if float(bars.iloc[i]['low']) < level:
            return True
    return False


def had_rally_above(bars: pd.DataFrame, level: float, before_idx: int) -> bool:
    for i in range(1, before_idx):
        if float(bars.iloc[i]['high']) > level:
            return True
    return False


def find_retest_entry(
    bars: pd.DataFrame,
    side: Side,
    breakout_idx: int,
    level: float,
) -> int | None:
    end = min(breakout_idx + 1 + MAX_FILL_WAIT_BARS, len(bars))
    for j in range(breakout_idx + 1, end):
        row = bars.iloc[j]
        if float(row['low']) <= level <= float(row['high']):
            return j
    return None


def simulate_exit(
    bars: pd.DataFrame,
    side: Side,
    entry_idx: int,
    entry: float,
    stop_pts: float,
) -> tuple[float, str, int]:
    stop = entry - stop_pts if side == 'long' else entry + stop_pts
    target = entry + TARGET_PTS if side == 'long' else entry - TARGET_PTS
    for j in range(entry_idx, len(bars)):
        row = bars.iloc[j]
        h, l = float(row['high']), float(row['low'])
        if side == 'long':
            if l <= stop:
                return -stop_pts, 'stop', j
            if h >= target:
                return TARGET_PTS, 'target', j
        else:
            if h >= stop:
                return -stop_pts, 'stop', j
            if l <= target:
                return TARGET_PTS, 'target', j
    last = bars.iloc[-1]
    exit_px = float(last['close'])
    pts = exit_px - entry if side == 'long' else entry - exit_px
    return pts, 'session_close', len(bars) - 1


def scan_day_setups(
    bars: pd.DataFrame,
    side: Side,
    mc: float,
    start_idx: int = 1,
) -> list[tuple[int, int]]:
    """Return list of (breakout_idx, entry_idx) from ``start_idx`` onward."""
    out: list[tuple[int, int]] = []
    n = len(bars)
    i = max(start_idx, 1)
    while i < n:
        row = bars.iloc[i]
        ok = False
        if side == 'long' and had_dip_below(bars, mc, i) and bullish_breakout(row, mc):
            ok = True
        elif side == 'short' and had_rally_above(bars, mc, i) and bearish_breakout(row, mc):
            ok = True
        if ok:
            ej = find_retest_entry(bars, side, i, mc)
            if ej is not None:
                out.append((i, ej))
                i = ej + 1
                continue
        i += 1
    return out


def simulate_session(
    session: date,
    bars15: pd.DataFrame,
    state: DayState,
    stop_pts: float,
) -> tuple[list[TradeRecord], DayState]:
    if len(bars15) < 3:
        return [], state
    mc = float(bars15.iloc[0]['close'])
    side: Side = 'long' if state.bias == 'bull' else 'short'
    setups = scan_day_setups(bars15, side, mc)
    if not setups:
        return [], state

    trades: list[TradeRecord] = []
    next_setup = 0
    attempt = 0

    while state.trades_taken < MAX_TRADES_DAY and state.streak_wins < MAX_WINS_STREAK:
        if next_setup >= len(setups):
            break
        bo_idx, en_idx = setups[next_setup]
        next_setup += 1
        attempt += 1
        entry_ts = pd.Timestamp(bars15.index[en_idx])
        entry = mc
        pts, result, exit_idx = simulate_exit(bars15, side, en_idx, entry, stop_pts)
        exit_ts = pd.Timestamp(bars15.index[exit_idx])
        won = result == 'target'

        trades.append(
            TradeRecord(
                session=session,
                side=side,
                bias=state.bias,
                streak_id=state.streak_id,
                midnight_close=mc,
                mo=0.0,  # filled by caller
                breakout_ts=pd.Timestamp(bars15.index[bo_idx]),
                entry_ts=entry_ts,
                entry=entry,
                exit_ts=exit_ts,
                exit=float(bars15.iloc[exit_idx]['close']) if result == 'session_close' else (
                    entry + TARGET_PTS if (side == 'long' and result == 'target') else
                    entry - TARGET_PTS if (side == 'short' and result == 'target') else
                    entry - stop_pts if side == 'long' else entry + stop_pts
                ),
                pts=pts,
                result=result,
                stop_pts=stop_pts,
                attempt=attempt,
            )
        )
        state.trades_taken += 1
        if won:
            state.streak_wins += 1
            if state.streak_wins >= MAX_WINS_STREAK or state.trades_taken >= MAX_TRADES_DAY:
                break
            continue
        # stop loss — one retry if daily cap allows
        if result == 'stop' and state.trades_taken < MAX_TRADES_DAY:
            continue
        break

    return trades, state


def build_bias_streaks(daily: pd.DataFrame, mo_map: dict[tuple[int, int], float]) -> dict[date, tuple[str, str]]:
    """Map session date → (bias, streak_id)."""
    dates = sorted(daily['date'].dt.date.unique())
    out: dict[date, tuple[str, str]] = {}
    prev_bias: str | None = None
    streak_start: date | None = None
    for d in dates:
        b = causal_bias(d, daily, mo_map)
        if b is None:
            continue
        bias, _mo = b
        if bias != prev_bias:
            streak_start = d
            prev_bias = bias
        out[d] = (bias, f'{streak_start}_{bias}')
    return out


def run_backtest(
    daily: pd.DataFrame,
    gby_1m: dict[date, pd.DataFrame],
    mo_map: dict[tuple[int, int], float],
    stop_pts: float,
) -> list[TradeRecord]:
    streak_map = build_bias_streaks(daily, mo_map)
    streak_wins: dict[str, int] = {}
    all_trades: list[TradeRecord] = []

    for session in sorted(gby_1m.keys()):
        if session not in streak_map:
            continue
        bias, streak_id = streak_map[session]
        if streak_wins.get(streak_id, 0) >= MAX_WINS_STREAK:
            continue
        b = causal_bias(session, daily, mo_map)
        if b is None:
            continue
        _, mo = b
        day_1m = gby_1m.get(session)
        bars15 = resample_15m_midnight_to_1600(day_1m, session) if day_1m is not None else pd.DataFrame()
        if bars15.empty or len(bars15) < 3:
            continue

        state = DayState(
            bias=bias,
            streak_id=streak_id,
            streak_wins=streak_wins.get(streak_id, 0),
        )
        day_trades, state = simulate_session(session, bars15, state, stop_pts)
        streak_wins[streak_id] = state.streak_wins
        for t in day_trades:
            t.mo = mo
            all_trades.append(t)
    return all_trades


def metrics(trades: list[TradeRecord]) -> dict:
    if not trades:
        return {'n': 0, 'wins': 0, 'losses': 0, 'win_rate': 0.0, 'total_pts': 0.0, 'avg_pts': 0.0}
    pts = [t.pts for t in trades]
    wins = sum(1 for t in trades if t.pts > 0)
    return {
        'n': len(trades),
        'wins': wins,
        'losses': len(trades) - wins,
        'win_rate': wins / len(trades),
        'total_pts': sum(pts),
        'avg_pts': sum(pts) / len(trades),
        'targets': sum(1 for t in trades if t.result == 'target'),
        'stops': sum(1 for t in trades if t.result == 'stop'),
        'session_close': sum(1 for t in trades if t.result == 'session_close'),
    }


def trades_to_df(trades: list[TradeRecord]) -> pd.DataFrame:
    rows = []
    for i, t in enumerate(trades):
        rows.append(
            {
                'trade_id': i,
                'session': t.session.isoformat(),
                'side': t.side,
                'bias': t.bias,
                'streak_id': t.streak_id,
                'midnight_close': t.midnight_close,
                'mo': t.mo,
                'breakout_ts': t.breakout_ts.isoformat(),
                'entry_ts': t.entry_ts.isoformat(),
                'entry': t.entry,
                'exit_ts': t.exit_ts.isoformat(),
                'exit': t.exit,
                'pts': t.pts,
                'result': t.result,
                'stop_pts': t.stop_pts,
                'attempt': t.attempt,
            }
        )
    return pd.DataFrame(rows)


def shade_rth(ax, bars: pd.DataFrame) -> None:
    if bars.empty:
        return
    t0, t1 = bars.index[0], bars.index[-1]
    ax.axvspan(mdates.date2num(t0), mdates.date2num(t1), facecolor=ETH_FILL, alpha=0.5, zorder=0)
    day = bars.index[0].normalize()
    if day.weekday() < 5:
        rth0 = NY.localize(datetime.combine(day.date(), RTH_OPEN))
        rth1 = NY.localize(datetime.combine(day.date(), RTH_CLOSE))
        ax.axvspan(
            mdates.date2num(max(rth0, t0)),
            mdates.date2num(min(rth1, t1)),
            facecolor=RTH_FILL,
            alpha=0.65,
            zorder=1,
        )


def plot_trade_chart(
    out_path: Path,
    trade: TradeRecord,
    bars15: pd.DataFrame,
) -> None:
    fig, ax = plt.subplots(figsize=(14, 7), facecolor=BG)
    ax.set_facecolor(BG)
    shade_rth(ax, bars15)

    xs = mdates.date2num(list(bars15.index.to_pydatetime()))
    width = (15 / (24 * 60)) * 0.72 if len(xs) > 1 else 0.01
    for x, (_, row) in zip(xs, bars15.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        col = GREEN_CANDLE if c >= o else RED_CANDLE
        ax.vlines(x, l, h, color=col, linewidth=0.85, zorder=3)
        body_lo = min(o, c)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, body_lo),
                width,
                max(abs(c - o), 0.08),
                facecolor=col,
                edgecolor=col,
                alpha=0.92,
                zorder=3,
            )
        )

    x0, x1 = xs[0], xs[-1]
    mc = trade.midnight_close
    ax.plot([x0, x1], [mc, mc], color=MC_COLOR, linewidth=1.5, zorder=4, label=f'MC {mc:.1f}')
    ax.plot([x0, x1], [trade.mo, trade.mo], color=MO_COLOR, linewidth=1.2, linestyle=':', zorder=4, label=f'MO {trade.mo:.1f}')

    stop = trade.entry - trade.stop_pts if trade.side == 'long' else trade.entry + trade.stop_pts
    target = trade.entry + TARGET_PTS if trade.side == 'long' else trade.entry - TARGET_PTS
    ax.axhline(stop, color=BEAR_COLOR, linestyle='--', linewidth=1.0, alpha=0.8)
    ax.axhline(target, color=BULL_COLOR, linestyle='--', linewidth=1.0, alpha=0.8)
    ax.axhline(trade.entry, color='white', linestyle='-', linewidth=0.8, alpha=0.6)

    x_bo = mdates.date2num(trade.breakout_ts.to_pydatetime())
    x_en = mdates.date2num(trade.entry_ts.to_pydatetime())
    x_ex = mdates.date2num(trade.exit_ts.to_pydatetime())
    ax.axvline(x_bo, color='#FFB74D', linestyle=':', linewidth=1.2, alpha=0.9)
    ax.scatter([x_en], [trade.entry], color='white', s=40, zorder=9, marker='^' if trade.side == 'long' else 'v')
    ax.scatter([x_ex], [trade.exit], color=BEAR_COLOR if trade.pts < 0 else BULL_COLOR, s=50, zorder=9, marker='x')

    bias_c = BULL_COLOR if trade.bias == 'bull' else BEAR_COLOR
    ax.set_title(
        f'NQ 15m MO midnight retest · {trade.session} · {trade.side.upper()} · SL {trade.stop_pts:.0f} · '
        f'{trade.result} {trade.pts:+.1f} pts',
        color=bias_c,
        fontsize=9,
        fontweight='bold',
        loc='left',
        pad=8,
    )
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.tick_params(colors='#9FB3C8', labelsize=7)
    for s in ax.spines.values():
        s.set_color('#3A506B')
    ax.grid(True, alpha=0.1, color='#9FB3C8')
    ax.legend(loc='upper right', fontsize=7, facecolor='#1B263B', labelcolor='white')
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, facecolor=BG)
    plt.close(fig)


def sample_trades(trades: list[TradeRecord], n: int, seed: int) -> list[TradeRecord]:
    if len(trades) <= n:
        return trades
    rng = random.Random(seed)
    by_result: dict[str, list[TradeRecord]] = {}
    for t in trades:
        by_result.setdefault(t.result, []).append(t)
    picked: list[TradeRecord] = []
    per = max(1, n // max(len(by_result), 1))
    for bucket in by_result.values():
        rng.shuffle(bucket)
        picked.extend(bucket[:per])
    if len(picked) < n:
        rest = [t for t in trades if t not in picked]
        rng.shuffle(rest)
        picked.extend(rest[: n - len(picked)])
    return picked[:n]


def write_summary(output_root: Path, summaries: dict[float, dict]) -> None:
    lines = [
        '# NQ MO bias · midnight-close retest backtest',
        '',
        'Bias: prior daily **close** vs month **MO** (causal). Trade direction with bias only.',
        '',
        'Setup: dip through midnight close → 15m breakout → limit retest @ midnight close.',
        '',
        f'Exit: **+{TARGET_PTS:.0f}** target · max **{MAX_TRADES_DAY}** trades/day · **{MAX_WINS_STREAK}** wins/bias streak.',
        '',
        '| SL (pts) | Trades | Win% | Total pts | Avg/trade | Targets | Stops | EOD |',
        '|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for sl in sorted(summaries.keys()):
        m = summaries[sl]
        lines.append(
            f"| {sl:.0f} | {m['n']} | {m['win_rate']*100:.1f}% | {m['total_pts']:+.1f} | {m['avg_pts']:+.2f} | "
            f"{m['targets']} | {m['stops']} | {m['session_close']} |"
        )
    lines.extend(['', 'Sample charts use **SL 30** variant.', ''])
    (output_root / 'SUMMARY.md').write_text('\n'.join(lines), encoding='utf-8')


def build(
    output_root: Path,
    daily_path: Path,
    dbn_path: Path,
    chart_sample: int,
    seed: int,
    force: bool,
) -> None:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    daily = load_daily(daily_path).sort_values('date')
    mo_map = build_monthly_mo(daily)

    print(f'Loading 1m {dbn_path.name} ...', flush=True)
    gby_1m = load_1m_by_ny_date(dbn_path, 'nq')

    stop_list = [30.0, 50.0, 100.0]
    summaries: dict[float, dict] = {}
    trades_sl30: list[TradeRecord] = []

    for sl in stop_list:
        print(f'Backtest SL={sl:.0f} ...', flush=True)
        trades = run_backtest(daily, gby_1m, mo_map, sl)
        summaries[sl] = metrics(trades)
        df = trades_to_df(trades)
        df.to_csv(output_root / f'trades_sl{int(sl)}.csv', index=False)
        if sl == 30.0:
            trades_sl30 = trades
        m = summaries[sl]
        print(
            f"  n={m['n']} win={m['win_rate']*100:.1f}% total={m['total_pts']:+.1f} avg={m['avg_pts']:+.2f}",
            flush=True,
        )

    write_summary(output_root, summaries)

    if chart_sample > 0 and trades_sl30:
        sample = sample_trades(trades_sl30, chart_sample, seed)
        chart_dir = output_root / 'charts'
        manifest: list[dict] = []
        print(f'Charting {len(sample)} sample trades ...', flush=True)
        for i, t in enumerate(sample):
            day_1m = gby_1m.get(t.session)
            bars15 = resample_15m_midnight_to_1600(day_1m, t.session) if day_1m is not None else pd.DataFrame()
            if bars15.empty:
                continue
            rel = f'charts/{t.session.isoformat()}_{t.side}_sl30_{i:03d}.png'
            plot_trade_chart(output_root / rel, t, bars15)
            manifest.append({'chart': rel, 'session': t.session.isoformat(), 'pts': t.pts, 'result': t.result})
        pd.DataFrame(manifest).to_csv(output_root / 'chart_manifest.csv', index=False)

    print(f'Done → {output_root / "SUMMARY.md"}', flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--output-root', type=Path, default=HERE / 'nq_mo_midnight_retest')
    ap.add_argument('--daily', type=Path, default=POTIONS_ROOT / 'nq' / 'nq_daily.csv')
    ap.add_argument('--dbn', type=Path, default=DEFAULT_DBN_NQ)
    ap.add_argument('--chart-sample', type=int, default=100)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()
    build(args.output_root, args.daily, args.dbn, args.chart_sample, args.seed, args.force)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
