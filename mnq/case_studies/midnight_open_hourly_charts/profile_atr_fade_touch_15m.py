#!/usr/bin/env python3
"""
15-minute candle profiles for atr_fade_touch wins vs losses.

Outputs under ``profiles_atr_fade_touch_15m/``:
- Entry-time histogram (count + avg P&L by 15m slot)
- Entry 15m candle stats (range, body, wicks, direction)
- Post-entry MTM path (avg pts vs 15m bars from entry bar)

Example::

  python3 profile_atr_fade_touch_15m.py
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytz

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import build_midnight_open_hourly_charts as mdata  # noqa: E402
from backtest_midnight_open_flip import Trade  # noqa: E402

NY = pytz.timezone('America/New_York')
DEFAULT_CSV = HERE / 'backtest_midnight_open_flip_trades_mnq_atr_fade_touch.csv'
DEFAULT_DBN = mdata.DEFAULT_DBN
OUT_DIR = HERE / 'profiles_atr_fade_touch_15m'

# Session slots 00:00–15:45 in 15m steps (entry filter is 10:00+ but show full session context)
SLOT_TIMES = [time(h, m) for h in range(16) for m in (0, 15, 30, 45)]


@dataclass
class EntryCandleRow:
    range_pts: float
    body_pts: float
    body_pct_range: float
    upper_wick: float
    lower_wick: float
    bullish: bool  # close > open
    aligned: bool  # long+bullish or short+bearish


def load_trades(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df['entry_time'] = pd.to_datetime(df['entry_time'], utc=True).dt.tz_convert(NY)
    df['exit_time'] = pd.to_datetime(df['exit_time'], utc=True).dt.tz_convert(NY)
    df['pnl_usd'] = df['pnl_usd'].astype(float)
    df['win'] = df['pnl_usd'] > 0
    return df


def slot_label(t: time) -> str:
    return t.strftime('%H:%M')


def entry_time_profile(df: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    df = df.copy()
    df['slot'] = df['entry_time'].dt.floor('15min').dt.time
    rows = []
    for st in SLOT_TIMES:
        sub = df[df['slot'] == st]
        wins = sub[sub['win']]
        losses = sub[~sub['win']]
        rows.append(
            {
                'slot': slot_label(st),
                'n_total': len(sub),
                'n_wins': len(wins),
                'n_losses': len(losses),
                'win_rate_pct': 100.0 * len(wins) / len(sub) if len(sub) else float('nan'),
                'total_pnl': sub['pnl_usd'].sum(),
                'avg_pnl_win': wins['pnl_usd'].mean() if len(wins) else float('nan'),
                'avg_pnl_loss': losses['pnl_usd'].mean() if len(losses) else float('nan'),
            }
        )
    tab = pd.DataFrame(rows)
    tab.to_csv(out_dir / 'entry_time_by_15m.csv', index=False)

    # Plot counts
    x = np.arange(len(SLOT_TIMES))
    labels = [slot_label(t) for t in SLOT_TIMES]
    w_counts = tab['n_wins'].values
    l_counts = tab['n_losses'].values

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), facecolor='#0D1B2A', sharex=True)
    for ax in axes:
        ax.set_facecolor('#0D1B2A')
        ax.tick_params(colors='#CFD8DC')
        ax.grid(True, linestyle=':', alpha=0.25, color='#546E7A')
        for spine in ax.spines.values():
            spine.set_color('#37474F')

    axes[0].bar(x, w_counts, color='#66BB6A', alpha=0.9, label='Wins')
    axes[0].bar(x, l_counts, bottom=w_counts, color='#EF5350', alpha=0.9, label='Losses')
    axes[0].set_ylabel('Trade count', color='#ECEFF1')
    axes[0].set_title('atr_fade_touch — entries by 15m slot (NY)', color='white', fontsize=11)
    axes[0].legend(facecolor='#1B263B', labelcolor='#ECEFF1')

    pnl_w = []
    pnl_l = []
    for st in SLOT_TIMES:
        sub = df[df['slot'] == st]
        pnl_w.append(sub[sub['win']]['pnl_usd'].sum())
        pnl_l.append(sub[~sub['win']]['pnl_usd'].sum())
    axes[1].bar(x, pnl_w, color='#66BB6A', alpha=0.9, label='Win P&L')
    axes[1].bar(x, pnl_l, color='#EF5350', alpha=0.9, label='Loss P&L')
    axes[1].axhline(0, color='#90A4AE', linewidth=0.8)
    axes[1].set_ylabel('Total P&L (USD)', color='#ECEFF1')
    axes[1].set_xlabel('Entry 15m bar open (NY)', color='#B0BEC5')
    axes[1].legend(facecolor='#1B263B', labelcolor='#ECEFF1')

    axes[1].set_xticks(x[::2])
    axes[1].set_xticklabels([labels[i] for i in range(0, len(labels), 2)], rotation=45, ha='right', color='#CFD8DC')
    fig.tight_layout()
    fig.savefig(out_dir / 'entry_time_profile.png', dpi=140, facecolor='#0D1B2A')
    plt.close(fig)
    return tab


def entry_15m_candle_at(ts: pd.Timestamp, bars15: pd.DataFrame) -> pd.Series | None:
    if bars15.empty:
        return None
    t0 = pd.Timestamp(ts).floor('15min')
    if t0 not in bars15.index:
        # nearest bar at or before
        prior = bars15.index[bars15.index <= t0]
        if prior.empty:
            return None
        t0 = prior[-1]
    return bars15.loc[t0]


def candle_metrics(row: pd.Series, side: str) -> EntryCandleRow:
    o, h, l, c = map(float, (row['open'], row['high'], row['low'], row['close']))
    rng = max(h - l, 1e-9)
    body = abs(c - o)
    bull = c > o
    if c >= o:
        upper, lower = h - c, o - l
    else:
        upper, lower = h - o, c - l
    aligned = (side == 'long' and bull) or (side == 'short' and not bull)
    return EntryCandleRow(
        range_pts=rng,
        body_pts=body,
        body_pct_range=100.0 * body / rng,
        upper_wick=upper,
        lower_wick=lower,
        bullish=bull,
        aligned=aligned,
    )


def summarize_candles(rows: list[EntryCandleRow]) -> dict:
    if not rows:
        return {}
    r = np.array([x.range_pts for x in rows])
    b = np.array([x.body_pts for x in rows])
    bp = np.array([x.body_pct_range for x in rows])
    uw = np.array([x.upper_wick for x in rows])
    lw = np.array([x.lower_wick for x in rows])
    return {
        'n': len(rows),
        'range_mean': r.mean(),
        'range_med': np.median(r),
        'body_mean': b.mean(),
        'body_pct_mean': bp.mean(),
        'upper_wick_mean': uw.mean(),
        'lower_wick_mean': lw.mean(),
        'bullish_pct': 100.0 * sum(x.bullish for x in rows) / len(rows),
        'aligned_pct': 100.0 * sum(x.aligned for x in rows) / len(rows),
    }


def post_entry_path(
    side: str,
    entry_px: float,
    entry_ts: pd.Timestamp,
    exit_ts: pd.Timestamp,
    bars15: pd.DataFrame,
    max_bars: int = 24,
) -> list[float]:
    """MTM in points at each 15m bar close from entry bar through exit."""
    if bars15.empty:
        return []
    t0 = pd.Timestamp(entry_ts).floor('15min')
    path = bars15[(bars15.index >= t0) & (bars15.index <= exit_ts)]
    if path.empty:
        return []
    out: list[float] = []
    for _, bar in path.iterrows():
        cl = float(bar['close'])
        if side == 'long':
            out.append(cl - entry_px)
        else:
            out.append(entry_px - cl)
        if len(out) >= max_bars:
            break
    return out


def pad_paths(paths: list[list[float]], max_len: int) -> np.ndarray:
    """Shape (n_paths, max_len) with nan pad."""
    arr = np.full((len(paths), max_len), np.nan)
    for i, p in enumerate(paths):
        for j, v in enumerate(p[:max_len]):
            arr[i, j] = v
    return arr


def run_path_and_candle_profiles(df: pd.DataFrame, gby: dict, out_dir: Path) -> None:
    win_candles: list[EntryCandleRow] = []
    loss_candles: list[EntryCandleRow] = []
    win_paths: list[list[float]] = []
    loss_paths: list[list[float]] = []
    bars_cache: dict[date, pd.DataFrame] = {}

    for _, row in df.iterrows():
        d = date.fromisoformat(str(row['session']))
        raw = gby.get(d)
        if raw is None:
            continue
        if d not in bars_cache:
            bars_cache[d] = mdata._resample_session_ohlcv(
                mdata.slice_session_1m(raw, d), d, '15min'
            )
        b15 = bars_cache[d]
        et = row['entry_time']
        xt = row['exit_time']
        side = str(row['side'])
        entry_px = float(row['entry_px'])
        is_win = bool(row['win'])

        ec = entry_15m_candle_at(et, b15)
        if ec is not None:
            m = candle_metrics(ec, side)
            (win_candles if is_win else loss_candles).append(m)

        p = post_entry_path(side, entry_px, et, xt, b15)
        if p:
            (win_paths if is_win else loss_paths).append(p)

    max_len = 24
    w_arr = pad_paths(win_paths, max_len)
    l_arr = pad_paths(loss_paths, max_len)
    w_mean = np.nanmean(w_arr, axis=0)
    l_mean = np.nanmean(l_arr, axis=0)
    w_p25 = np.nanpercentile(w_arr, 25, axis=0)
    w_p75 = np.nanpercentile(w_arr, 75, axis=0)
    l_p25 = np.nanpercentile(l_arr, 25, axis=0)
    l_p75 = np.nanpercentile(l_arr, 75, axis=0)
    xs = np.arange(max_len)

    fig, ax = plt.subplots(figsize=(12, 6), facecolor='#0D1B2A')
    ax.set_facecolor('#0D1B2A')
    ax.fill_between(xs, w_p25, w_p75, color='#66BB6A', alpha=0.25)
    ax.fill_between(xs, l_p25, l_p75, color='#EF5350', alpha=0.25)
    ax.plot(xs, w_mean, color='#66BB6A', linewidth=2, label=f'Wins (n={len(win_paths)})')
    ax.plot(xs, l_mean, color='#EF5350', linewidth=2, label=f'Losses (n={len(loss_paths)})')
    ax.axhline(0, color='#90A4AE', linewidth=0.8)
    ax.set_xlabel('15m bars from entry bar (0 = entry period)', color='#B0BEC5')
    ax.set_ylabel('MTM at 15m close (pts)', color='#B0BEC5')
    ax.set_title('atr_fade_touch — avg favorable MTM path (15m)', color='white', fontsize=11)
    ax.tick_params(colors='#CFD8DC')
    ax.grid(True, linestyle=':', alpha=0.25)
    ax.legend(facecolor='#1B263B', labelcolor='#ECEFF1')
    for spine in ax.spines.values():
        spine.set_color('#37474F')
    fig.tight_layout()
    fig.savefig(out_dir / 'post_entry_15m_mtm_profile.png', dpi=140, facecolor='#0D1B2A')
    plt.close(fig)

    # Entry candle comparison chart
    labels = ['range', 'body', 'body_%', 'upper_wick', 'lower_wick']
    ws = summarize_candles(win_candles)
    ls = summarize_candles(loss_candles)
    if ws and ls:
        wv = [ws['range_mean'], ws['body_mean'], ws['body_pct_mean'], ws['upper_wick_mean'], ws['lower_wick_mean']]
        lv = [ls['range_mean'], ls['body_mean'], ls['body_pct_mean'], ls['upper_wick_mean'], ls['lower_wick_mean']]
        x = np.arange(len(labels))
        fig, ax = plt.subplots(figsize=(10, 5), facecolor='#0D1B2A')
        ax.set_facecolor('#0D1B2A')
        ax.bar(x - 0.2, wv, 0.4, color='#66BB6A', label='Wins')
        ax.bar(x + 0.2, lv, 0.4, color='#EF5350', label='Losses')
        ax.set_xticks(x)
        ax.set_xticklabels(labels, color='#CFD8DC')
        ax.set_ylabel('Points (body_% in percent)', color='#B0BEC5')
        ax.set_title('Entry 15m candle — mean size (pts)', color='white', fontsize=11)
        ax.legend(facecolor='#1B263B', labelcolor='#ECEFF1')
        ax.tick_params(colors='#CFD8DC')
        ax.grid(True, linestyle=':', alpha=0.25, axis='y')
        fig.tight_layout()
        fig.savefig(out_dir / 'entry_15m_candle_size.png', dpi=140, facecolor='#0D1B2A')
        plt.close(fig)

    lines = [
        '# atr_fade_touch — 15m candle profile (wins vs losses)',
        '',
        f'- **Wins:** {len(win_paths)} trades with path data',
        f'- **Losses:** {len(loss_paths)} trades with path data',
        '',
        '## Entry 15m candle (bar containing entry)',
        '',
        '| Metric | Wins | Losses |',
        '|---|---:|---:|',
    ]
    keys = [
        ('Count', 'n', '{:.0f}'),
        ('Range mean (pts)', 'range_mean', '{:.1f}'),
        ('Range median (pts)', 'range_med', '{:.1f}'),
        ('Body mean (pts)', 'body_mean', '{:.1f}'),
        ('Body % of range', 'body_pct_mean', '{:.1f}'),
        ('Upper wick mean', 'upper_wick_mean', '{:.1f}'),
        ('Lower wick mean', 'lower_wick_mean', '{:.1f}'),
        ('Bullish close %', 'bullish_pct', '{:.1f}'),
        ('Aligned w/ trade %', 'aligned_pct', '{:.1f}'),
    ]
    for name, key, fmt in keys:
        wv = ws.get(key, float('nan')) if ws else float('nan')
        lv = ls.get(key, float('nan')) if ls else float('nan')
        lines.append(f'| {name} | {fmt.format(wv)} | {fmt.format(lv)} |')

    lines += [
        '',
        '## Files',
        '',
        '- `entry_time_profile.png` — count & P&L by entry 15m slot',
        '- `entry_time_by_15m.csv` — table',
        '- `post_entry_15m_mtm_profile.png` — avg MTM vs bars after entry',
        '- `entry_15m_candle_size.png` — entry bar range/body/wicks',
        '',
    ]
    (out_dir / 'README.md').write_text('\n'.join(lines), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--trades-csv', type=Path, default=DEFAULT_CSV)
    ap.add_argument('--dbn', type=Path, default=DEFAULT_DBN)
    ap.add_argument('--out-dir', type=Path, default=OUT_DIR)
    args = ap.parse_args()

    if not args.trades_csv.is_file():
        print(f'Missing {args.trades_csv}', file=sys.stderr)
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    df = load_trades(args.trades_csv)
    print(f'Trades: {len(df)} ({df["win"].sum()} wins, {(~df["win"]).sum()} losses)', flush=True)

    entry_time_profile(df, args.out_dir)
    print(f'Wrote entry time profile → {args.out_dir}', flush=True)

    if not args.dbn.is_file():
        print('Skipping candle/path profiles (no DBN)', flush=True)
        return 0

    gby = mdata.load_1m_by_ny_date(args.dbn.resolve(), 'mnq')
    run_path_and_candle_profiles(df, gby, args.out_dir)
    print(f'Wrote 15m candle profiles → {args.out_dir}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
