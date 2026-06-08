#!/usr/bin/env python3
"""
Generate annotated 5-min candlestick charts for N randomly sampled trading days from the
standalone breakout-close-limit + 3-contract scale-out backtest
(``experiments/mnq_breakout_close_limit_scaleout.csv``).

Visual layout matches ``build_random_samples.py`` exactly (same figure, arrows, RH/RL, triggers).

Output: breakout_close_limit_random_samples/<date>.png  + INDEX.md
"""
import argparse
import random
from collections import Counter
from datetime import time
from pathlib import Path

import databento as db
import pandas as pd
import pytz

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402


NY = pytz.timezone('America/New_York')
DBN_FILE = '/home/tester/hsm/potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'
CSV_FILE = Path(__file__).resolve().parents[1] / 'experiments' / 'mnq_breakout_close_limit_scaleout.csv'
OUT_DIR = Path(__file__).resolve().parent / 'breakout_close_limit_random_samples'
TICK = 0.25


def resample_5m_anchor_0930(df1: pd.DataFrame) -> pd.DataFrame:
    """Must match experiments/breakout_close_limit_scaleout.py::resample_5m (NY 9:30 bucket origin)."""
    ix0 = df1.index[0]
    anchor = ix0.normalize() + pd.Timedelta(hours=9, minutes=30)
    return (
        df1.resample('5min', label='left', closed='left', origin=anchor)
        .agg(open=('open', 'first'), high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
        .dropna(subset=['open'])
    )


def load_dbn_once():
    """Load full DBN once and partition by date for fast lookup."""
    print(f'Loading DBN ({DBN_FILE}) ...')
    store = db.DBNStore.from_file(DBN_FILE)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')].copy()
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY)
    df['date'] = df['ts_event'].dt.date
    df['t'] = df['ts_event'].dt.time
    fm = (
        df.groupby(['date', 'symbol'])['volume'].sum().groupby(level='date').idxmax().apply(lambda x: x[1]).to_dict()
    )
    df = df[df.apply(lambda r: r['symbol'] == fm.get(r['date']), axis=1)]
    df = df[(df['t'] >= time(9, 30)) & (df['t'] < time(16, 0))].copy()
    df = df.set_index('ts_event').sort_index()

    by_date = {d: g for d, g in df.groupby(df.index.date)}
    print(f'  Loaded {len(by_date):,} trading days, {len(df):,} 1-min bars')
    return by_date


def _ts(series_val, tz) -> pd.Timestamp:
    ts = pd.to_datetime(series_val)
    if tz is not None:
        ts = ts.tz_convert(tz)
    elif hasattr(ts, 'tz_localize') and ts.tzinfo is None:
        ts = ts.tz_localize(NY)
    return ts


def draw_chart(date_obj, df1, csv_rows, outpath):
    if df1.empty:
        return
    rng_bars = df1[(df1.index.time >= time(9, 30)) & (df1.index.time < time(9, 45))]
    rh = rng_bars['high'].max()
    rl = rng_bars['low'].min()
    rv = rh - rl
    ix_tz = df1.index.tz

    trades = []
    for _, r in csv_rows.iterrows():
        d = r['Trade_Direction']
        target = rh + rv if d == 'Long' else rl - rv
        if pd.notna(r.get('Initial_Stop')):
            stop = float(r['Initial_Stop'])
        else:
            stop = rl if d == 'Long' else rh
        e_time = _ts(r['Entry_Time'], ix_tz)
        x_time = _ts(r['Exit_Time'], ix_tz)
        if str(r['Result']).startswith('EOD'):
            x_time = df1.index[-1]
        net_usd = float(r['Net_$'])
        trades.append(
            {
                'direction': d,
                'entry': float(r['Entry_Price']),
                'exit_price': float(r['Exit_Price']),
                'target': target,
                'stop': stop,
                'result': r['Result'],
                'entry_time': e_time,
                'exit_time': x_time,
                'pl_pts': float(r['Trade_PL']),
                'net_usd': net_usd,
            }
        )

    bars5 = resample_5m_anchor_0930(df1)

    pattern = '+'.join([f"{t['direction'][0]}{t['result'][0]}" for t in trades])
    sum_idx_leg_pts = sum(t['pl_pts'] for t in trades)
    day_net_usd = sum(t['net_usd'] for t in trades)
    sym = csv_rows['Symbol'].iloc[0]

    fig = plt.figure(figsize=(16, 9), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')

    # Opening range shading
    ax.axvspan(bars5.index[0], bars5.index[0] + pd.Timedelta(minutes=15), color='#1F4E79', alpha=0.30, zorder=0)
    # Range band
    ax.axhline(rh, color='#E0E0E0', linestyle='--', linewidth=1.2, zorder=2)
    ax.axhline(rl, color='#E0E0E0', linestyle='--', linewidth=1.2, zorder=2)
    ax.axhspan(rl, rh, color='#1F4E79', alpha=0.10, zorder=0)
    # Trigger lines
    ax.axhline(rh + TICK, color='#76FF03', linestyle=':', linewidth=1.0, alpha=0.8, zorder=2)
    ax.axhline(rl - TICK, color='#FF5252', linestyle=':', linewidth=1.0, alpha=0.8, zorder=2)

    # Candles
    for ts, row in bars5.iterrows():
        x = mdates.date2num(ts)
        width = 5 / (24 * 60) * 0.7
        is_up = row['close'] >= row['open']
        c = '#26A69A' if is_up else '#EF5350'
        ax.vlines(x, row['low'], row['high'], color=c, linewidth=0.8, zorder=3)
        body_lo = min(row['open'], row['close'])
        body_hi = max(row['open'], row['close'])
        ax.add_patch(
            mpatches.Rectangle((x - width / 2, body_lo), width, max(body_hi - body_lo, 0.05), facecolor=c, edgecolor=c, alpha=0.95, zorder=3)
        )

    # Trade annotations (identical formatting to random_samples)
    color_for = {'Win': '#76FF03', 'Loss': '#FF1744', 'EOD-Win': '#69F0AE', 'EOD-Loss': '#FFB74D'}
    label_offset = [+24, -36, +48, -60]
    for i, t in enumerate(trades, 1):
        x_e = mdates.date2num(t['entry_time'])
        x_x = mdates.date2num(t['exit_time'])
        ax.scatter(
            [x_e],
            [t['entry']],
            marker='^' if t['direction'] == 'Long' else 'v',
            color='#FFC107',
            s=180,
            zorder=10,
            edgecolor='black',
            linewidth=1.5,
        )
        ax.annotate(
            f"#{i} {t['direction'][0]} entry @ {t['entry']:.2f}",
            xy=(x_e, t['entry']),
            xytext=(8, label_offset[(i - 1) % len(label_offset)]),
            textcoords='offset points',
            color='#FFC107',
            fontsize=8.5,
            fontweight='bold',
            zorder=10,
            ha='left',
            bbox=dict(boxstyle='round,pad=0.25', fc='#0D1B2A', ec='#FFC107', alpha=0.95),
            arrowprops=dict(arrowstyle='->', color='#FFC107', lw=0.7),
        )

        ax.plot([x_e, x_x], [t['target'], t['target']], color='#76FF03', linewidth=1.0, linestyle='-', alpha=0.6, zorder=4)
        ax.plot([x_e, x_x], [t['stop'], t['stop']], color='#FF1744', linewidth=1.0, linestyle='-', alpha=0.6, zorder=4)

        c = color_for.get(t['result'], '#FFC107')
        ax.scatter([x_x], [t['exit_price']], marker='X', color=c, s=180, zorder=10, edgecolor='black', linewidth=1.5)
        ax.annotate(
            f"#{i} {t['result']} Σ{t['pl_pts']:+.1f} idx-pt (${t['net_usd']:+,.0f} net 3µ)",
            xy=(x_x, t['exit_price']),
            xytext=(8, -label_offset[(i - 1) % len(label_offset)]),
            textcoords='offset points',
            color=c,
            fontsize=8.5,
            fontweight='bold',
            zorder=10,
            ha='left',
            bbox=dict(boxstyle='round,pad=0.25', fc='#0D1B2A', ec=c, alpha=0.95),
            arrowprops=dict(arrowstyle='->', color=c, lw=0.7),
        )

    last_x = mdates.date2num(bars5.index[-1]) + 0.005
    ax.text(last_x, rh, f' RH {rh:.2f}', color='#E0E0E0', fontsize=8, va='center')
    ax.text(last_x, rl, f' RL {rl:.2f}', color='#E0E0E0', fontsize=8, va='center')

    title = f'{date_obj}  ·  {sym}  ·  Range {rv:.1f} pts  ·  Pattern {pattern}'
    subtitle = (
        f'Day net (×3 MNQ): ${day_net_usd:+,.2f}  ·  Σ idx-pt (all legs): {sum_idx_leg_pts:+.2f}'
    )
    ax.set_title(f'{title}\n{subtitle}', color='white', fontsize=13, fontweight='bold', pad=12, loc='left')
    ax.set_xlabel('NY Time', color='#9FB3C8', fontsize=9)
    ax.set_ylabel(f'{sym} Price', color='#9FB3C8', fontsize=9)
    ax.tick_params(colors='#9FB3C8', labelsize=8)
    for s in ax.spines.values():
        s.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color='#9FB3C8')
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=NY))
    ax.set_xlim(bars5.index[0] - pd.Timedelta(minutes=10), bars5.index[-1] + pd.Timedelta(minutes=25))

    plt.tight_layout()
    plt.savefig(outpath, dpi=120, bbox_inches='tight', facecolor='#0D1B2A')
    plt.close()
    return pattern, day_net_usd, sum_idx_leg_pts, rv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-n', type=int, default=44, help='Number of random samples')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--start', default='2024-01-01', help='Earliest date to sample from')
    ap.add_argument(
        '--dates',
        nargs='*',
        default=None,
        metavar='YYYY-MM-DD',
        help='If set, render exactly these calendar days (ignores -n / --seed).',
    )
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    csv = pd.read_csv(CSV_FILE)
    csv['Date'] = pd.to_datetime(csv['Date']).dt.date
    csv = csv[csv['Date'] >= pd.to_datetime(args.start).date()]
    available_days = sorted(csv['Date'].unique())
    print(f'Available days from {args.start}: {len(available_days):,}')

    if args.dates:
        sampled = sorted({pd.Timestamp(d).date() for d in args.dates})
        bad = [d for d in sampled if d not in available_days]
        if bad:
            print(f'WARNING: skipping dates with no sim rows (CSV): {bad}')
            sampled = [d for d in sampled if d in available_days]
        print(f'Rendering {len(sampled)} explicit calendar days (--dates)')
    else:
        rng = random.Random(args.seed)
        sampled = sorted(rng.sample(available_days, min(args.n, len(available_days))))
        print(f'Sampling {len(sampled)} days (seed={args.seed})')

    by_date = load_dbn_once()

    rows = []
    for i, d in enumerate(sampled, 1):
        if d not in by_date:
            print(f'  [{i:>3}/{len(sampled)}] {d}: no DBN data, skipping')
            continue
        df1 = by_date[d]
        csv_rows = csv[csv['Date'] == d]
        outpath = OUT_DIR / f'{d}.png'
        try:
            res = draw_chart(d, df1, csv_rows, outpath)
            if res is None:
                continue
            pattern, day_net_usd, sum_idx, rv = res
            rows.append(
                {
                    'date': d,
                    'symbol': csv_rows['Symbol'].iloc[0],
                    'range': round(rv, 2),
                    'pattern': pattern,
                    'sum_idx_pts': round(sum_idx, 2),
                    'net_day_3mq': round(day_net_usd, 2),
                }
            )
            print(
                f'  [{i:>3}/{len(sampled)}] {d} {csv_rows["Symbol"].iloc[0]} '
                f'range={rv:>6.1f} pat={pattern:<8} Σidx={sum_idx:>+7.1f} net3µ=${day_net_usd:>+7.2f}'
            )
        except Exception as e:
            print(f'  [{i:>3}/{len(sampled)}] {d}: error - {e}')

    idx = OUT_DIR / 'INDEX.md'
    if args.dates:
        print('\nSkipping INDEX.md (--dates refreshes PNGs only; run without --dates for INDEX).')
    else:
        with open(idx, 'w') as f:
            f.write(f'# Random sample — breakout close limit / 3ct scale-out ({len(rows)} days)\n\n')
            f.write(f'Same chart style as ``random_samples/``; data from standalone sim (no v2b CSV lookahead).\n\n')
            f.write(f'Sampled with seed={args.seed} from days >= {args.start}.\n')
            f.write('CSV: `potions/mnq/experiments/mnq_breakout_close_limit_scaleout.csv`\n\n')

            def cat(p):
                if p in ('LW+LW', 'SW+SW', 'LW+SW', 'SW+LW'):
                    return 'Double Win'
                if p in ('LL+SL', 'SL+LL'):
                    return 'Double Loss'
                if p in ('LL+SW', 'SL+LW'):
                    return 'Loss-then-Win'
                if p in ('LW+SL', 'SW+LL'):
                    return 'Win-then-Loss'
                if 'E' in p:
                    return 'EOD-Close'
                if p in ('LW', 'SW'):
                    return 'Single Win'
                if p in ('LL', 'SL'):
                    return 'Single Loss'
                return 'Other'

            cats = Counter(cat(r['pattern']) for r in rows)
            f.write('## Pattern distribution in this sample\n\n')
            f.write('| Category | Count | % |\n|---|---|---|\n')
            if rows:
                for k, v in cats.most_common():
                    f.write(f'| {k} | {v} | {v / len(rows) * 100:.1f}% |\n')
            total = sum(r['net_day_3mq'] for r in rows)
            wins = sum(1 for r in rows if r['net_day_3mq'] > 0)
            pct = (wins / len(rows) * 100.0) if rows else 0.0
            f.write(f'\n**Sample summary:** {len(rows)} days, {wins} green ({pct:.1f}%), ')
            f.write(f'net ${total:,.0f} aggregate (×3 MNQ rules, day sum of leg `Net_$`).\n\n')

            f.write('## All sampled days\n\n')
            f.write('| Date | Symbol | Range | Pattern | Σ idx-pt day | Net $ ×3MNQ day | Chart |\n')
            f.write('|---|---|---|---|---|---|---|\n')
            for r in sorted(rows, key=lambda x: x['date']):
                du = r['date']
                f.write(f"| {du} | {r['symbol']} | {r['range']} | {r['pattern']} | "
                        f"{r['sum_idx_pts']:+.2f} | ${r['net_day_3mq']:+,.0f} | "
                        f'[{du}.png]({du}.png) |\n')

        print(f'\nWrote index: {idx}')
    print(f'Charts in:   {OUT_DIR}')


if __name__ == '__main__':
    main()
