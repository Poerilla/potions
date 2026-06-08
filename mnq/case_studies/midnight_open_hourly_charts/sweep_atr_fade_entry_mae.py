#!/usr/bin/env python3
"""
Sweep atr_fade_touch entry distance = historical MAE stats (fixed pts from M).

SL/TP/filters unchanged (3×ATR stop, 2×ATR opposite target, 10:00+, one trade/day).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_midnight_open_hourly_charts as mdata  # noqa: E402
from backtest_midnight_open_flip import (  # noqa: E402
    ATR_FADE_ENTRY_MULT,
    Trade,
    build_hourly_with_warmup,
    simulate_session_atr_fade_touch,
)

DEFAULT_DBN = mdata.DEFAULT_DBN

# From analyze_atr_fade_touch_excursions.py on 2×ATR-entry baseline
MAE_ENTRY_OFFSETS = {
    'baseline_2xATR': None,  # use ATR mult
    'mae_mean_48.2': 48.2,
    'mae_median_45.0': 45.0,
    'mae_p90_88.3': 88.3,
    'mae_p95_105.6': 105.6,
}


def summarize(label: str, trades: list[Trade]) -> dict:
    if not trades:
        return {'label': label, 'n': 0, 'pnl': 0.0, 'win_pct': 0.0, 'med': 0.0}
    pnl = np.array([t.pnl_usd for t in trades], dtype=float)
    reasons = {}
    for t in trades:
        reasons[t.reason_exit] = reasons.get(t.reason_exit, 0) + 1
    top = ', '.join(f'{k}={v}' for k, v in sorted(reasons.items(), key=lambda x: -x[1])[:3])
    return {
        'label': label,
        'n': len(trades),
        'pnl': float(pnl.sum()),
        'avg': float(pnl.mean()),
        'med': float(np.median(pnl)),
        'win_pct': float(100.0 * (pnl > 0).mean()),
        'best': float(pnl.max()),
        'worst': float(pnl.min()),
        'exits': top,
    }


def run_variant(
    sessions: list[tuple],
    label: str,
    entry_pts: float | None,
) -> list[Trade]:
    trades: list[Trade] = []
    kw: dict = (
        {'entry_offset_pts': entry_pts} if entry_pts is not None else {'entry_atr_mult': ATR_FADE_ENTRY_MULT}
    )
    for d, M, sess, hw in sessions:
        trades.extend(simulate_session_atr_fade_touch(d, M, sess, hw, 2.0, **kw))
    return trades


def build_sessions(gby, session_days: list) -> list[tuple]:
    out: list[tuple] = []
    for d in session_days:
        if d.weekday() >= 5:
            continue
        raw = gby.get(d)
        if raw is None:
            continue
        sess = mdata.slice_session_1m(raw, d)
        if sess.empty:
            continue
        M = mdata.ny_midnight_open_px(sess)
        if not np.isfinite(M):
            continue
        hw = build_hourly_with_warmup(gby, d)
        out.append((d, M, sess, hw))
    return out


def main() -> int:
    print('Loading DBN ...', flush=True)
    gby = mdata.load_1m_by_ny_date(DEFAULT_DBN.resolve(), 'mnq')
    print('Building session cache (warmup once per day) ...', flush=True)
    sessions = build_sessions(gby, sorted(gby.keys()))
    print(f'  {len(sessions)} weekday sessions', flush=True)
    rows: list[dict] = []

    for label, pts in MAE_ENTRY_OFFSETS.items():
        print(f'Running {label} ...', flush=True)
        trades = run_variant(sessions, label, pts)
        rows.append(summarize(label, trades))

    print('\n## Entry sweep — fixed pts from M (MAE stats) vs baseline 2×ATR\n', flush=True)
    print(
        '| Variant | Trades | Total P&L | Avg | Median | Win% | Best | Worst | Top exits |',
        flush=True,
    )
    print('|---|---:|---:|---:|---:|---:|---:|---:|---|', flush=True)
    for r in rows:
        print(
            f"| {r['label']} | {r['n']} | ${r['pnl']:,.0f} | ${r['avg']:,.0f} | ${r['med']:,.0f} | "
            f"{r['win_pct']:.1f}% | ${r['best']:,.0f} | ${r['worst']:,.0f} | {r.get('exits', '')} |",
            flush=True,
        )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
