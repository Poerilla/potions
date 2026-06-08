#!/usr/bin/env python3
"""Backtest WO gap reversal with scale-out exits (2023+)."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from build_nq_wo_gap_reversal_sample import (  # noqa: E402
    MAX_FILL_WAIT_BARS,
    MAX_TRADES_WEEK,
    NY,
    STOP_PTS,
    TARGET_PTS,
    bearish_breakout_candle,
    blocking_swing_before_bar,
    build_daily_atr,
    build_weekly_table,
    bullish_breakout_candle,
    concat_1m,
    first_pre_gap_bar,
    load_1m_by_ny_date,
    resample_1h,
    week_context,
    week_hourly_slice,
)

ExitMode = Literal['single', 'scale_50_300', 'scale_50_600', 'scale_50_300_600']
TP1_PTS = 50.0
RUNNER_600 = 600.0
TP2_PTS = 300.0
CONTRACTS_3 = 3


def _find_entry(
    bars: pd.DataFrame,
    side: Literal['long', 'short'],
    gap_idx: int,
    wo: float,
) -> tuple[int | None, str | None]:
    fill_end = min(gap_idx + 1 + MAX_FILL_WAIT_BARS, len(bars))
    for j in range(gap_idx + 1, fill_end):
        swing_i = blocking_swing_before_bar(bars, side, gap_idx, j)
        if swing_i is not None:
            kind = 'swing high' if side == 'long' else 'swing low'
            return None, f'{kind} @ bar {swing_i} before WO retest'
        row = bars.iloc[j]
        if float(row['low']) <= wo <= float(row['high']):
            return j, None
    return None, f'no WO retest within {MAX_FILL_WAIT_BARS} bars after gap'


def _exit_single(
    bars: pd.DataFrame,
    side: Literal['long', 'short'],
    entry_idx: int,
    wo: float,
) -> tuple[float, str, int, bool]:
    stop = wo - STOP_PTS if side == 'long' else wo + STOP_PTS
    target = wo + TARGET_PTS if side == 'long' else wo - TARGET_PTS
    exit_idx = entry_idx
    for j in range(entry_idx, len(bars)):
        row = bars.iloc[j]
        h, l = float(row['high']), float(row['low'])
        if side == 'long':
            if l <= stop:
                return -STOP_PTS, 'stop', j, False
            if h >= target:
                return TARGET_PTS, 'target', j, True
        else:
            if h >= stop:
                return -STOP_PTS, 'stop', j, False
            if l <= target:
                return TARGET_PTS, 'target', j, True
        exit_idx = j
    close = float(bars.iloc[exit_idx]['close'])
    pts = (close - wo) if side == 'long' else (wo - close)
    return pts, 'eod', exit_idx, pts > 0


def _exit_scale(
    bars: pd.DataFrame,
    side: Literal['long', 'short'],
    entry_idx: int,
    wo: float,
    runner_pts: float,
) -> tuple[float, str, int, bool]:
    stop = wo - STOP_PTS if side == 'long' else wo + STOP_PTS
    tp1 = wo + TP1_PTS if side == 'long' else wo - TP1_PTS
    runner_tgt = wo + runner_pts if side == 'long' else wo - runner_pts

    tp1_hit = False
    exit_idx = entry_idx
    leg2_pts = 0.0
    runner_result = 'open'

    for j in range(entry_idx, len(bars)):
        row = bars.iloc[j]
        h, l = float(row['high']), float(row['low'])

        if not tp1_hit:
            if side == 'long':
                if l <= stop:
                    return -STOP_PTS * 2, 'stop_both', j, False
                if h >= tp1:
                    tp1_hit = True
                    exit_idx = j
            else:
                if h >= stop:
                    return -STOP_PTS * 2, 'stop_both', j, False
                if l <= tp1:
                    tp1_hit = True
                    exit_idx = j
        else:
            if side == 'long':
                if l <= wo:
                    return TP1_PTS, 'tp1+be', j, True
                if h >= runner_tgt:
                    return TP1_PTS + runner_pts, 'tp1+target', j, True
            else:
                if h >= wo:
                    return TP1_PTS, 'tp1+be', j, True
                if l <= runner_tgt:
                    return TP1_PTS + runner_pts, 'tp1+target', j, True
            exit_idx = j

    if not tp1_hit:
        close = float(bars.iloc[exit_idx]['close'])
        pts = ((close - wo) if side == 'long' else (wo - close)) * 2
        return pts, 'eod_both', exit_idx, False

    close = float(bars.iloc[exit_idx]['close'])
    leg2_pts = (close - wo) if side == 'long' else (wo - close)
    return TP1_PTS + leg2_pts, f'tp1+eod', exit_idx, True


def _exit_scale_3leg(
    bars: pd.DataFrame,
    side: Literal['long', 'short'],
    entry_idx: int,
    wo: float,
) -> tuple[float, str, int, bool]:
    """3 contracts: +50, then +300, then +600; BE on remainder after +50."""
    stop = wo - STOP_PTS if side == 'long' else wo + STOP_PTS
    tp50 = wo + TP1_PTS if side == 'long' else wo - TP1_PTS
    tp300 = wo + TP2_PTS if side == 'long' else wo - TP2_PTS
    tp600 = wo + RUNNER_600 if side == 'long' else wo - RUNNER_600

    tp50_done = tp300_done = tp600_done = False
    pts = 0.0
    exit_idx = entry_idx

    def remaining() -> int:
        return CONTRACTS_3 - int(tp50_done) - int(tp300_done) - int(tp600_done)

    def result_tag() -> str:
        parts = []
        if tp50_done:
            parts.append('50')
        if tp300_done:
            parts.append('300')
        if tp600_done:
            parts.append('600')
        return '+'.join(parts) if parts else 'open'

    for j in range(entry_idx, len(bars)):
        row = bars.iloc[j]
        h, l = float(row['high']), float(row['low'])

        if not tp50_done:
            if side == 'long':
                if l <= stop:
                    return -STOP_PTS * CONTRACTS_3, 'stop_all', j, False
                if h >= tp50:
                    tp50_done = True
                    pts += TP1_PTS
            else:
                if h >= stop:
                    return -STOP_PTS * CONTRACTS_3, 'stop_all', j, False
                if l <= tp50:
                    tp50_done = True
                    pts += TP1_PTS
            exit_idx = j
            if not tp50_done:
                continue

        rem = remaining()
        if rem <= 0:
            break

        if side == 'long':
            if l <= wo:
                return pts, f'{result_tag()}+be', j, True
            if not tp300_done and h >= tp300:
                tp300_done = True
                pts += TP2_PTS
            if not tp600_done and h >= tp600:
                if not tp300_done:
                    tp300_done = True
                    pts += TP2_PTS
                tp600_done = True
                pts += RUNNER_600
        else:
            if h >= wo:
                return pts, f'{result_tag()}+be', j, True
            if not tp300_done and l <= tp300:
                tp300_done = True
                pts += TP2_PTS
            if not tp600_done and l <= tp600:
                if not tp300_done:
                    tp300_done = True
                    pts += TP2_PTS
                tp600_done = True
                pts += RUNNER_600
        exit_idx = j
        if remaining() == 0:
            break

    if not tp50_done:
        close = float(bars.iloc[exit_idx]['close'])
        leg = (close - wo) if side == 'long' else (wo - close)
        return leg * CONTRACTS_3, 'eod_all', exit_idx, False

    rem = remaining()
    if rem > 0:
        close = float(bars.iloc[exit_idx]['close'])
        leg = (close - wo) if side == 'long' else (wo - close)
        pts += leg * rem
        tag = result_tag()
        return pts, f'{tag}+eod' if tag else 'tp50+eod', exit_idx, True

    return pts, result_tag(), exit_idx, True


def simulate_week_trades(
    bars: pd.DataFrame,
    wo: float,
    week_key: str,
    *,
    short_only: bool,
    mode: ExitMode,
) -> list[dict]:
    n = len(bars)
    out: list[dict] = []
    trades_taken = 0
    had_win = False
    long_used = short_used = False

    for i in range(n):
        if trades_taken >= MAX_TRADES_WEEK or had_win:
            break

        side: Literal['long', 'short'] | None = None
        if not short_only and not long_used and bullish_breakout_candle(bars.iloc[i], wo):
            side = 'long'
        elif not short_used and bearish_breakout_candle(bars.iloc[i], wo):
            side = 'short'
        if side is None:
            continue

        if first_pre_gap_bar(bars, wo, i, side) is None:
            if side == 'long':
                long_used = True
            else:
                short_used = True
            continue

        entry_idx, block = _find_entry(bars, side, i, wo)
        if entry_idx is None:
            if side == 'long':
                long_used = True
            else:
                short_used = True
            continue

        if mode == 'single':
            pts, result, exit_idx, _ = _exit_single(bars, side, entry_idx, wo)
            tp1_hit = result == 'target'
            had_win = result == 'target'
        elif mode == 'scale_50_300':
            pts, result, exit_idx, won = _exit_scale(bars, side, entry_idx, wo, TARGET_PTS)
            tp1_hit = result.startswith('tp1')
            had_win = won
        elif mode == 'scale_50_600':
            pts, result, exit_idx, won = _exit_scale(bars, side, entry_idx, wo, RUNNER_600)
            tp1_hit = result.startswith('tp1')
            had_win = won
        else:
            pts, result, exit_idx, won = _exit_scale_3leg(bars, side, entry_idx, wo)
            tp1_hit = result != 'stop_all' and ('50' in result or result.startswith('tp'))
            had_win = won

        out.append(
            {
                'week': week_key,
                'side': side,
                'gap_idx': i,
                'entry_idx': entry_idx,
                'exit_idx': exit_idx,
                'pts': pts,
                'result': result,
                'tp1_hit': tp1_hit,
            }
        )
        trades_taken += 1
        if side == 'long':
            long_used = True
        else:
            short_used = True

    return out


def metrics(tdf: pd.DataFrame, label: str) -> dict:
    if tdf.empty:
        return {'label': label, 'n': 0}
    pts = tdf['pts'].values
    eq = np.cumsum(pts)
    max_dd = (eq - np.maximum.accumulate(eq)).min()
    streaks: list[int] = []
    cur = 0
    for x in pts < 0:
        if x:
            cur += 1
        else:
            if cur:
                streaks.append(cur)
            cur = 0
    if cur:
        streaks.append(cur)
    gross_loss = abs(pts[pts < 0].sum())
    return {
        'label': label,
        'n': len(tdf),
        'net': float(pts.sum()),
        'win_rate': float((pts > 0).mean() * 100),
        'pf': float(pts[pts > 0].sum() / gross_loss) if gross_loss else float('inf'),
        'avg': float(pts.mean()),
        'max_dd': float(max_dd),
        'max_loss_streak': max(streaks) if streaks else 0,
        'tp1_rate': float(tdf['tp1_hit'].mean() * 100) if 'tp1_hit' in tdf.columns else None,
    }


def main() -> int:
    start = '2023-01-01'
    dbn = HERE.parent / 'raw' / 'glbx-mdp3-20100606-20260308.ohlcv-1m.dbn.zst'
    print('Loading NQ 1m ...', flush=True)
    gby = load_1m_by_ny_date(dbn, 'nq')
    one_min = concat_1m(gby)
    one_min = one_min[one_min.index >= pd.Timestamp(start, tz=NY)]
    hourly = resample_1h(one_min)
    weekly = build_weekly_table(hourly, build_daily_atr(hourly))

    out = HERE / 'nq_weekly_wo_gap_reversal_sample'
    lines = [
        '# WO gap reversal — scale-out exit comparison (2023+)',
        '',
        'Entry rules unchanged.',
        '- **2ct modes:** +50 on leg 1 → BE on runner; runner @ 300 or 600.',
        f'- **3ct mode:** +50 / +300 / +600 ladder; BE on remainder after +50.',
        f'- Initial stop: **{STOP_PTS:.0f} pts** on all open contracts (stop-first intrabar).',
        '- Week rule: no 2nd trade after +50 hit or full target (same as a win).',
        '',
    ]

    for book in ('short_only', 'both'):
        short_only = book == 'short_only'
        results = []
        for mode, title in [
            ('single', f'Baseline 1ct → {TARGET_PTS:.0f}'),
            ('scale_50_300', f'2ct: +{TP1_PTS:.0f} / runner {TARGET_PTS:.0f}'),
            ('scale_50_600', f'2ct: +{TP1_PTS:.0f} / runner {RUNNER_600:.0f}'),
            ('scale_50_300_600', f'3ct: +{TP1_PTS:.0f} / +{TP2_PTS:.0f} / +{RUNNER_600:.0f}'),
        ]:
            rows: list[dict] = []
            for week in weekly.index:
                ctx = week_context(weekly, week)
                if ctx is None:
                    continue
                ws = weekly.loc[week, 'week_start']
                if ws < pd.Timestamp(start, tz=NY):
                    continue
                bars = week_hourly_slice(hourly, ws)
                if len(bars) < 20:
                    continue
                wo = float(ctx['WO'])
                wk = ws.date().isoformat()
                rows.extend(
                    simulate_week_trades(bars, wo, wk, short_only=short_only, mode=mode)
                )
            tdf = pd.DataFrame(rows)
            tdf.to_csv(out / f'scaleout_{book}_{mode}_2023plus.csv', index=False)
            results.append(metrics(tdf, title))

        lines.append(f'## {book.replace("_", " ").title()}')
        lines.append('')
        lines.append(
            '| Mode | Trades | Net pts | Win% | PF | Avg/trade | Max DD | Max loss streak |'
        )
        lines.append('|---|---:|---:|---:|---:|---:|---:|---:|')
        base = results[0]
        for m in results:
            dd_d = m['max_dd'] - base['max_dd'] if m['n'] and base['n'] else 0
            lines.append(
                f'| {m["label"]} | {m["n"]} | {m["net"]:+.1f} | {m["win_rate"]:.1f} | '
                f'{m["pf"]:.2f} | {m["avg"]:+.1f} | {m["max_dd"]:.0f} | {m["max_loss_streak"]} |'
            )
        lines.append('')
        if len(results) >= 2:
            for m in results[1:]:
                lines.append(
                    f'- **{m["label"]}** vs baseline: net {m["net"] - base["net"]:+.1f} pts, '
                    f'max DD {m["max_dd"] - base["max_dd"]:+.0f} pts, '
                    f'loss streak {m["max_loss_streak"] - base["max_loss_streak"]:+d}.'
                )
            lines.append('')

    (out / 'SCALEOUT_COMPARISON.md').write_text('\n'.join(lines), encoding='utf-8')
    print((out / 'SCALEOUT_COMPARISON.md').read_text())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
