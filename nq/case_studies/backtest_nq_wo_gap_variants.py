#!/usr/bin/env python3
"""Compare WO gap reversal rule variants vs baseline (2ct +50 / runner 300)."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import time
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from backtest_nq_wo_gap_scaleout import (  # noqa: E402
    TP1_PTS,
    _exit_scale,
    metrics,
)
from build_nq_wo_gap_reversal_sample import (  # noqa: E402
    MAX_FILL_WAIT_BARS,
    NY,
    STOP_PTS,
    TARGET_PTS,
    blocking_swing_before_bar,
    build_daily_atr,
    build_weekly_table,
    candle_fully_above_wo,
    candle_fully_below_wo,
    concat_1m,
    first_pre_gap_bar,
    load_1m_by_ny_date,
    resample_1h,
    week_context,
    week_hourly_slice,
)

RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)


@dataclass(frozen=True)
class VariantRules:
    key: str
    label: str
    gap_pct: float = 0.55
    use_swing_filter: bool = True
    max_trades_week: int | None = 2
    stop_after_win: bool = True
    rth_entries_only: bool = False


VARIANTS: tuple[VariantRules, ...] = (
    VariantRules('baseline', 'Baseline (55% gap · swing filter · 2 trades/wk)'),
    VariantRules('no_swing', '1 — no swing filter before WO retest'),
    VariantRules('gap_45', '2a — 45% gap candle', gap_pct=0.45),
    VariantRules('gap_50', '2b — 50% gap candle', gap_pct=0.50),
    VariantRules('max_3', '3 — max 3 trades/week', max_trades_week=3),
    VariantRules('unlimited', '4 — unlimited trades/week', max_trades_week=None, stop_after_win=False),
    VariantRules('rth_entry', '5 — RTH-only entries (09:30–16:00)', rth_entries_only=True),
)


def bullish_breakout_candle(row: pd.Series, wo: float, gap_pct: float) -> bool:
    o, c = float(row['open']), float(row['close'])
    if not (c > wo > o):
        return False
    body = c - o
    if body <= 0:
        return False
    above = c - wo
    below = wo - o
    if above <= below:
        return False
    return (above / body) >= gap_pct


def bearish_breakout_candle(row: pd.Series, wo: float, gap_pct: float) -> bool:
    o, c = float(row['open']), float(row['close'])
    if not (o > wo > c):
        return False
    body = o - c
    if body <= 0:
        return False
    below = wo - c
    above = o - wo
    if below <= above:
        return False
    return (below / body) >= gap_pct


def bar_overlaps_rth(ts: pd.Timestamp) -> bool:
    """1h bar end timestamp; bar window is (ts - 1h, ts]."""
    if ts.weekday() >= 5:
        return False
    bar_start = ts - pd.Timedelta(hours=1)
    day = ts.normalize()
    rth0 = day + pd.Timedelta(hours=9, minutes=30)
    rth1 = day + pd.Timedelta(hours=16)
    return bar_start < rth1 and ts > rth0


def _find_entry(
    bars: pd.DataFrame,
    side: Literal['long', 'short'],
    gap_idx: int,
    wo: float,
    rules: VariantRules,
) -> tuple[int | None, str | None]:
    fill_end = min(gap_idx + 1 + MAX_FILL_WAIT_BARS, len(bars))
    for j in range(gap_idx + 1, fill_end):
        if rules.use_swing_filter:
            swing_i = blocking_swing_before_bar(bars, side, gap_idx, j)
            if swing_i is not None:
                kind = 'swing high' if side == 'long' else 'swing low'
                return None, f'{kind} @ bar {swing_i} before WO retest'
        row = bars.iloc[j]
        if float(row['low']) <= wo <= float(row['high']):
            ts = pd.Timestamp(bars.index[j])
            if rules.rth_entries_only and not bar_overlaps_rth(ts):
                continue
            return j, None
    if rules.rth_entries_only:
        return None, 'no RTH WO retest within fill window'
    return None, f'no WO retest within {MAX_FILL_WAIT_BARS} bars after gap'


def simulate_week_trades(
    bars: pd.DataFrame,
    wo: float,
    week_key: str,
    *,
    short_only: bool,
    rules: VariantRules,
) -> list[dict]:
    n = len(bars)
    out: list[dict] = []
    trades_taken = 0
    had_win = False
    long_used = short_used = False
    cap = rules.max_trades_week

    for i in range(n):
        if cap is not None and trades_taken >= cap:
            break
        if rules.stop_after_win and had_win:
            break

        side: Literal['long', 'short'] | None = None
        row = bars.iloc[i]
        if not short_only and not long_used and bullish_breakout_candle(row, wo, rules.gap_pct):
            side = 'long'
        elif not short_used and bearish_breakout_candle(row, wo, rules.gap_pct):
            side = 'short'
        if side is None:
            continue

        if first_pre_gap_bar(bars, wo, i, side) is None:
            if side == 'long':
                long_used = True
            else:
                short_used = True
            continue

        entry_idx, block = _find_entry(bars, side, i, wo, rules)
        if entry_idx is None:
            if side == 'long':
                long_used = True
            else:
                short_used = True
            continue

        pts, result, exit_idx, won = _exit_scale(bars, side, entry_idx, wo, TARGET_PTS)
        tp1_hit = result.startswith('tp1')
        if rules.stop_after_win and won:
            had_win = True

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


def run_book(
    hourly: pd.DataFrame,
    weekly: pd.DataFrame,
    start: pd.Timestamp,
    *,
    short_only: bool,
    rules: VariantRules,
) -> pd.DataFrame:
    rows: list[dict] = []
    for week in weekly.index:
        ctx = week_context(weekly, week)
        if ctx is None:
            continue
        ws = weekly.loc[week, 'week_start']
        if ws < start:
            continue
        bars = week_hourly_slice(hourly, ws)
        if len(bars) < 20:
            continue
        wo = float(ctx['WO'])
        wk = ws.date().isoformat()
        rows.extend(simulate_week_trades(bars, wo, wk, short_only=short_only, rules=rules))
    return pd.DataFrame(rows)


def fmt_row(m: dict, base: dict) -> str:
    if not m.get('n'):
        return f'| {m["label"]} | 0 | — | — | — | — | — | — | — |'
    d_net = m['net'] - base['net'] if base.get('n') else 0.0
    d_n = m['n'] - base['n'] if base.get('n') else m['n']
    return (
        f'| {m["label"]} | {m["n"]} | {m["net"]:+.1f} | {d_net:+.1f} | '
        f'{m["win_rate"]:.1f} | {m["pf"]:.2f} | {m["avg"]:+.1f} | '
        f'{m["max_dd"]:.0f} | {m["max_loss_streak"]} | {d_n:+d} |'
    )


def main() -> int:
    start = pd.Timestamp('2010-06-06', tz=NY)
    dbn = HERE.parent / 'raw' / 'glbx-mdp3-20100606-20260308.ohlcv-1m.dbn.zst'
    out = HERE / 'nq_weekly_wo_gap_reversal_sample'
    out.mkdir(parents=True, exist_ok=True)

    print('Loading NQ 1m ...', flush=True)
    gby = load_1m_by_ny_date(dbn, 'nq')
    one_min = concat_1m(gby)
    one_min = one_min[one_min.index >= start]
    hourly = resample_1h(one_min)
    weekly = build_weekly_table(hourly, build_daily_atr(hourly))

    lines = [
        '# WO gap reversal — rule variant comparison',
        '',
        f'Full history from **{start.date()}** · exit **2ct +{TP1_PTS:.0f} / runner {TARGET_PTS:.0f}** · SL **{STOP_PTS:.0f} pts**.',
        'Baseline matches the chart study except where a variant overrides one rule.',
        '',
        '### Baseline rules (unchanged across variants unless noted)',
        '- Pre-gap: ≥1 prior 1h bar fully O+C on exit side of WO',
        '- Gap candle: ≥55% of O–C on exit side crossing WO',
        '- Entry: limit @ WO from next bar; 6-bar fill window',
        '- Post-gap swing filter: skip if 3-bar swing before retest (unless gap in swing)',
        '- Max **2** trades/week; stop new trades after +50 / target win',
        '- One gap signal per direction per week',
        '',
    ]

    for book in ('both', 'short_only'):
        short_only = book == 'short_only'
        title = 'Both sides' if book == 'both' else 'Short only'
        results: list[dict] = []
        frames: dict[str, pd.DataFrame] = {}

        for rules in VARIANTS:
            tdf = run_book(hourly, weekly, start, short_only=short_only, rules=rules)
            frames[rules.key] = tdf
            tdf.to_csv(out / f'variants_{book}_{rules.key}.csv', index=False)
            results.append(metrics(tdf, rules.label))

        base = results[0]
        lines.append(f'## {title}')
        lines.append('')
        lines.append(
            '| Variant | Trades | Net pts | Δ net vs base | Win% | PF | Avg/trade | Max DD | Max loss streak | Δ trades |'
        )
        lines.append('|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|')
        for m in results:
            lines.append(fmt_row(m, base))
        lines.append('')

        for m in results[1:]:
            if not m.get('n') or not base.get('n'):
                continue
            lines.append(
                f'- **{m["label"]}**: net {m["net"] - base["net"]:+.1f} pts vs baseline, '
                f'{m["n"] - base["n"]:+d} trades, max DD {m["max_dd"] - base["max_dd"]:+.0f} pts.'
            )
        lines.append('')

    (out / 'VARIANT_COMPARISON.md').write_text('\n'.join(lines), encoding='utf-8')
    print((out / 'VARIANT_COMPARISON.md').read_text())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
