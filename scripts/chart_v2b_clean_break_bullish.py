#!/usr/bin/env python3
"""Chart target winners from the bullish v2b clean-break study."""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
NY_TZ = 'America/New_York'


MARKETS = {
    'mnq': {
        'bars': ROOT / 'mnq' / 'mnq_5min_rth.csv',
        'trades': ROOT / 'mnq' / 'mnq_v2b_clean_break_bullish.csv',
        'out': ROOT / 'mnq' / 'case_studies' / 'v2b_clean_break_bullish' / 'charts' / 'mnq_winners',
    },
    'nq': {
        'bars': ROOT / 'nq' / 'nq_5min_rth.csv',
        'trades': ROOT / 'nq' / 'nq_v2b_clean_break_bullish.csv',
        'out': ROOT / 'mnq' / 'case_studies' / 'v2b_clean_break_bullish' / 'charts' / 'nq_winners',
    },
}


def load_bars(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df['ts'] = pd.to_datetime(df['ts_event'], utc=True).dt.tz_convert(NY_TZ)
    df['session_day'] = df['ts'].dt.date.astype(str)
    return df.sort_values('ts').reset_index(drop=True)


def parse_time(value: object) -> pd.Timestamp | None:
    if pd.isna(value) or not str(value):
        return None
    return pd.to_datetime(value, utc=True).tz_convert(NY_TZ)


def draw_candles(ax: plt.Axes, bars: pd.DataFrame) -> None:
    xs = mdates.date2num(bars['ts'].dt.tz_localize(None))
    if len(xs) > 1:
        width = (xs[1] - xs[0]) * 0.72
    else:
        width = 0.002
    for x, (_, row) in zip(xs, bars.iterrows()):
        o, h, l, c = float(row['open']), float(row['high']), float(row['low']), float(row['close'])
        color = '#089981' if c >= o else '#f23645'
        ax.vlines(x, l, h, color=color, linewidth=0.85, alpha=0.9, zorder=3)
        body_low = min(o, c)
        body_height = max(abs(c - o), 0.01)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, body_low),
                width,
                body_height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.6,
                alpha=0.88,
                zorder=4,
            )
        )


def nearest_bar_x(bars: pd.DataFrame, ts: pd.Timestamp | None) -> float | None:
    if ts is None:
        return None
    mask = bars['ts'].eq(ts)
    if not mask.any():
        return None
    return float(mdates.date2num(bars.loc[mask, 'ts'].iloc[0].tz_localize(None)))


def chart_trade(market: str, bars: pd.DataFrame, trade: pd.Series, out_path: Path, seq: int) -> None:
    day = str(trade['session_day'])
    day_bars = bars[bars['session_day'].eq(day)].copy()
    if day_bars.empty:
        return

    fig, ax = plt.subplots(figsize=(15, 7.5))
    draw_candles(ax, day_bars)

    xs = mdates.date2num(day_bars['ts'].dt.tz_localize(None))
    x0, x1 = xs.min(), xs.max()
    ax.axvspan(xs[0], xs[min(2, len(xs) - 1)], color='#d8eef8', alpha=0.35, label='Opening range')

    levels = [
        ('RH', float(trade['rh']), '#2f80ed', '-'),
        ('RL / Stop', float(trade['rl']), '#d93025', '--'),
        ('Entry', float(trade['entry']), '#111111', '-'),
        ('2R Target', float(trade['target']), '#178a45', '-'),
    ]
    for label, price, color, style in levels:
        ax.hlines(price, x0, x1, colors=color, linestyles=style, linewidth=1.2, alpha=0.9)
        ax.text(x1, price, f' {label} {price:,.2f}', color=color, va='center', fontsize=8)

    break_ts = parse_time(trade['break_time'])
    exit_ts = parse_time(trade['exit_time'])
    break_x = nearest_bar_x(day_bars, break_ts)
    exit_x = nearest_bar_x(day_bars, exit_ts)
    if break_x is not None:
        ax.axvline(break_x, color='#ff8c00', linestyle='-', linewidth=1.2, alpha=0.8)
        ax.scatter([break_x], [float(trade['break_close'])], marker='^', s=80, color='#ff8c00', zorder=6, label='Break close')
    if exit_x is not None:
        ax.axvline(exit_x, color='#178a45', linestyle='-', linewidth=1.2, alpha=0.8)
        ax.scatter([exit_x], [float(trade['exit_px'])], marker='o', s=70, color='#178a45', zorder=6, label='Target exit')

    title = (
        f"{market.upper()} v2b bullish clean-break target | {day} | "
        f"break #{int(float(trade['break_candle_num_after_or']))} "
        f"| PnL {float(trade['pts']):.2f} pts / ${float(trade['usd']):,.0f} "
        f"| MAE {float(trade['mae_pts']):.2f} pts"
    )
    ax.set_title(title, loc='left', fontsize=12)
    ax.grid(True, axis='y', alpha=0.18)
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.set_xlim(x0 - 0.003, x1 + 0.006)
    ax.set_ylabel('Price')
    ax.legend(loc='upper left', fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def select_evenly(df: pd.DataFrame, n: int) -> pd.DataFrame:
    if len(df) <= n:
        return df.copy()
    positions = sorted(set(round(i * (len(df) - 1) / (n - 1)) for i in range(n)))
    return df.iloc[positions].copy()


def write_index(out_dir: Path, market: str, rows: list[tuple[pd.Series, Path]]) -> None:
    lines = [
        f'# {market.upper()} v2b Clean-Break Bullish Winners',
        '',
        f'{len(rows)} target-winner charts, sampled evenly across history.',
        '',
        '| # | Date | Break # | Break Time | PnL | MAE | Chart |',
        '|---:|---|---:|---:|---:|---:|---|',
    ]
    for i, (trade, path) in enumerate(rows, 1):
        bt = parse_time(trade['break_time'])
        btxt = bt.strftime('%H:%M') if bt is not None else ''
        lines.append(
            f"| {i} | {trade['session_day']} | {int(float(trade['break_candle_num_after_or']))} | "
            f"{btxt} | {float(trade['pts']):.2f} pts | {float(trade['mae_pts']):.2f} pts | "
            f"[{path.name}]({path.name}) |"
        )
    (out_dir / 'INDEX.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def run_market(market: str, cfg: dict, n: int) -> None:
    bars = load_bars(cfg['bars'])
    trades = pd.read_csv(cfg['trades'])
    winners = trades[trades['result'].eq('Target')].sort_values('session_day').reset_index(drop=True)
    sample = select_evenly(winners, n)
    out_dir = cfg['out']
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for seq, (_, trade) in enumerate(sample.iterrows(), 1):
        out_path = out_dir / f"{seq:02d}_{trade['session_day']}_win.png"
        chart_trade(market, bars, trade, out_path, seq)
        rows.append((trade, out_path))
    write_index(out_dir, market, rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--market', choices=['mnq', 'nq', 'both'], default='both')
    ap.add_argument('--n', type=int, default=50)
    args = ap.parse_args()
    markets = ['mnq', 'nq'] if args.market == 'both' else [args.market]
    for market in markets:
        run_market(market, MARKETS[market], args.n)
        print(f"Wrote {MARKETS[market]['out'] / 'INDEX.md'}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
