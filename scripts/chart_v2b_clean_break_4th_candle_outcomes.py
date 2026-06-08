#!/usr/bin/env python3
"""Chart MNQ outcomes for the v2b 4th-candle boundary-stop variant."""
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
MNQ_BARS = ROOT / 'mnq' / 'mnq_5min_rth.csv'
MNQ_TRADES = ROOT / 'mnq' / 'mnq_v2b_clean_break_4th_candle_boundary_stop.csv'
OUT_ROOT = (
    ROOT
    / 'mnq'
    / 'case_studies'
    / 'v2b_clean_break_4th_candle_boundary_stop'
    / 'charts'
)


def load_bars(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df['ts'] = pd.to_datetime(df['ts_event'], utc=True).dt.tz_convert(NY_TZ)
    df['session_day'] = df['ts'].dt.date.astype(str)
    return df.sort_values('ts').reset_index(drop=True)


def parse_time(value: object) -> pd.Timestamp | None:
    if pd.isna(value) or not str(value):
        return None
    return pd.to_datetime(value, utc=True).tz_convert(NY_TZ)


def safe_name(value: object) -> str:
    return str(value).replace('/', '-').replace(' ', '_')


def draw_candles(ax: plt.Axes, bars: pd.DataFrame) -> None:
    xs = mdates.date2num(bars['ts'].dt.tz_localize(None))
    width = (xs[1] - xs[0]) * 0.72 if len(xs) > 1 else 0.002
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


def chart_trade(bars: pd.DataFrame, trade: pd.Series, out_path: Path) -> bool:
    day = str(trade['session_day'])
    day_bars = bars[bars['session_day'].eq(day)].copy()
    if day_bars.empty:
        return False

    fig, ax = plt.subplots(figsize=(15, 7.5))
    draw_candles(ax, day_bars)

    xs = mdates.date2num(day_bars['ts'].dt.tz_localize(None))
    x0, x1 = xs.min(), xs.max()
    ax.axvspan(xs[0], xs[min(2, len(xs) - 1)], color='#d8eef8', alpha=0.35, label='Opening range')

    levels = [
        ('RH / Boundary Stop', float(trade['rh']), '#2f80ed', '-'),
        ('RL', float(trade['rl']), '#d93025', '--'),
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
        exit_color = '#178a45' if float(trade['usd']) > 0 else '#d93025'
        ax.axvline(exit_x, color=exit_color, linestyle='-', linewidth=1.2, alpha=0.8)
        ax.scatter([exit_x], [float(trade['exit_px'])], marker='o', s=70, color=exit_color, zorder=6, label='Exit')

    title = (
        f"MNQ v2b 09:45 clean-break boundary stop | {day} | {trade['result']} | "
        f"{float(trade['pts']):.2f} pts / ${float(trade['usd']):,.0f} | "
        f"MAE {float(trade['mae_pts']):.2f} pts | {trade['status']}"
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
    return True


def write_index(out_dir: Path, title: str, rows: list[tuple[pd.Series, Path]]) -> None:
    lines = [
        f'# {title}',
        '',
        f'{len(rows)} charts.',
        '',
        '| # | Date | Result | Status | PnL | MAE | MFE | Chart |',
        '|---:|---|---|---|---:|---:|---:|---|',
    ]
    for i, (trade, path) in enumerate(rows, 1):
        lines.append(
            f"| {i} | {trade['session_day']} | {trade['result']} | {trade['status']} | "
            f"{float(trade['pts']):.2f} pts / ${float(trade['usd']):,.0f} | "
            f"{float(trade['mae_pts']):.2f} pts | {float(trade['mfe_pts']):.2f} pts | "
            f"[{path.name}]({path.name}) |"
        )
    (out_dir / 'INDEX.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def select_rows(df: pd.DataFrame, max_count: int | None) -> pd.DataFrame:
    if max_count is None or max_count <= 0 or len(df) <= max_count:
        return df.copy()
    positions = sorted(set(round(i * (len(df) - 1) / (max_count - 1)) for i in range(max_count)))
    return df.iloc[positions].copy()


def chart_bucket(
    bars: pd.DataFrame,
    trades: pd.DataFrame,
    bucket: str,
    title: str,
    max_count: int | None,
) -> int:
    out_dir = OUT_ROOT / bucket
    out_dir.mkdir(parents=True, exist_ok=True)
    sample = select_rows(trades.sort_values('session_day').reset_index(drop=True), max_count)
    rows: list[tuple[pd.Series, Path]] = []
    for seq, (_, trade) in enumerate(sample.iterrows(), 1):
        out_path = out_dir / f"{bucket[:-1]}_{seq:03d}_{trade['session_day']}_{safe_name(trade['result'])}.png"
        if chart_trade(bars, trade, out_path):
            rows.append((trade, out_path))
    write_index(out_dir, title, rows)
    return len(rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--max-losers', type=int, default=0, help='0 means chart all losers.')
    ap.add_argument('--max-winners', type=int, default=0, help='0 means chart all winners.')
    args = ap.parse_args()

    bars = load_bars(MNQ_BARS)
    trades = pd.read_csv(MNQ_TRADES)
    traded = trades[trades['entry'].notna()].copy()
    winners = traded[traded['usd'] > 0].copy()
    losers = traded[traded['usd'] < 0].copy()

    win_count = chart_bucket(bars, winners, 'winners', 'MNQ v2b 09:45 Boundary-Stop Winners', args.max_winners)
    loss_count = chart_bucket(bars, losers, 'losers', 'MNQ v2b 09:45 Boundary-Stop Losers', args.max_losers)
    root_index = [
        '# MNQ v2b 09:45 Boundary-Stop Outcome Charts',
        '',
        f'- [Winners](winners/INDEX.md): {win_count}',
        f'- [Losers](losers/INDEX.md): {loss_count}',
        '',
    ]
    (OUT_ROOT / 'INDEX.md').write_text('\n'.join(root_index), encoding='utf-8')
    print(f'Wrote {OUT_ROOT / "INDEX.md"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
