#!/usr/bin/env python3
"""
Generate annotated 5-min candlestick charts for N randomly sampled trading
days from the v2 MNQ NY backtest. Loads the DBN once and reuses the
in-memory copy so the batch runs in a few minutes rather than 30+.

Output: random_samples/<date>.png  + random_samples/INDEX.md
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
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt


NY = pytz.timezone('America/New_York')
DBN_FILE = '/home/tester/hsm/potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'
CSV_FILE = '/home/tester/hsm/potions/mnq/mnq_orb_results_stops.csv'
OUT_DIR  = Path('/home/tester/hsm/potions/case_studies/random_samples')
TICK     = 0.25


RANDOM_SAMPLES_EPILOG = """\
Example run:
  cd potions/mnq/case_studies
  python3 build_random_samples.py -n 44 --seed 42 --start 2024-01-01

Outputs:
  PNG charts under OUT_DIR (see CSV_FILE in script for paths): ``YYYY-MM-DD.png``.
  INDEX.md batch summary unless logic skips it — progress printed while loading DBN.
"""


def load_dbn_once():
    """Load full DBN once and partition by date for fast lookup."""
    print(f"Loading DBN ({DBN_FILE}) ...")
    store = db.DBNStore.from_file(DBN_FILE)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')].copy()
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY)
    df['date'] = df['ts_event'].dt.date
    df['t'] = df['ts_event'].dt.time
    fm = (df.groupby(['date', 'symbol'])['volume'].sum()
            .groupby(level='date').idxmax().apply(lambda x: x[1]).to_dict())
    df = df[df.apply(lambda r: r['symbol'] == fm.get(r['date']), axis=1)]
    df = df[(df['t'] >= time(9, 30)) & (df['t'] < time(16, 0))].copy()
    df = df.set_index('ts_event').sort_index()

    by_date = {d: g for d, g in df.groupby(df.index.date)}
    print(f"  Loaded {len(by_date):,} trading days, {len(df):,} 1-min bars")
    return by_date


def find_entry_exit(df1, rh, rl, prior_exit, direction, target, stop):
    after = df1[df1.index > prior_exit]
    long_trig = rh + TICK
    short_trig = rl - TICK
    entry_time = None
    for ts, bar in after.iterrows():
        if direction == 'Long' and bar['high'] >= long_trig:
            entry_time = ts; break
        if direction == 'Short' and bar['low'] <= short_trig:
            entry_time = ts; break
    if entry_time is None:
        entry_time = after.index[0] if not after.empty else df1.index[-1]

    exit_time = None
    for ts, bar in df1[df1.index >= entry_time].iterrows():
        if direction == 'Long':
            if bar['low'] < stop:    exit_time = ts; break
            if bar['high'] >= target: exit_time = ts; break
        else:
            if bar['high'] > stop:   exit_time = ts; break
            if bar['low'] <= target: exit_time = ts; break
    if exit_time is None:
        exit_time = df1.index[-1]
    return entry_time, exit_time


def draw_chart(date_obj, df1, csv_rows, outpath):
    if df1.empty:
        return
    rng_bars = df1[(df1.index.time >= time(9, 30)) & (df1.index.time < time(9, 45))]
    rh = rng_bars['high'].max()
    rl = rng_bars['low'].min()
    rv = rh - rl

    trades = []
    prior_exit = df1[df1.index.time < time(9, 45)].index[-1]
    for _, r in csv_rows.iterrows():
        d = r['Trade_Direction']
        target = rh + rv if d == 'Long' else rl - rv
        stop = rl if d == 'Long' else rh
        e_time, x_time = find_entry_exit(df1, rh, rl, prior_exit, d, target, stop)
        if r['Result'].startswith('EOD'):
            x_time = df1.index[-1]
        trades.append({
            'direction': d, 'entry': r['Entry_Price'], 'exit_price': r['Exit_Price'],
            'target': target, 'stop': stop, 'result': r['Result'],
            'entry_time': e_time, 'exit_time': x_time, 'pl_pts': r['Trade_PL'],
        })
        prior_exit = x_time

    bars5 = df1.resample('5T').agg(
        open=('open', 'first'), high=('high', 'max'),
        low=('low', 'min'), close=('close', 'last')).dropna(subset=['open'])

    pattern = '+'.join([f"{t['direction'][0]}{t['result'][0]}" for t in trades])
    total_pl = sum(t['pl_pts'] for t in trades)
    sym = csv_rows['Symbol'].iloc[0]

    fig = plt.figure(figsize=(16, 9), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')

    # Opening range shading
    ax.axvspan(bars5.index[0], bars5.index[0] + pd.Timedelta(minutes=15),
               color='#1F4E79', alpha=0.30, zorder=0)
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
        ax.add_patch(mpatches.Rectangle(
            (x - width / 2, body_lo), width, max(body_hi - body_lo, 0.05),
            facecolor=c, edgecolor=c, alpha=0.95, zorder=3))

    # Trade annotations
    color_for = {'Win': '#76FF03', 'Loss': '#FF1744', 'EOD-Win': '#69F0AE', 'EOD-Loss': '#FFB74D'}
    label_offset = [+24, -36, +48, -60]
    for i, t in enumerate(trades, 1):
        x_e = mdates.date2num(t['entry_time'])
        x_x = mdates.date2num(t['exit_time'])
        ax.scatter([x_e], [t['entry']],
                   marker='^' if t['direction'] == 'Long' else 'v',
                   color='#FFC107', s=180, zorder=10, edgecolor='black', linewidth=1.5)
        ax.annotate(f"#{i} {t['direction'][0]} entry @ {t['entry']:.2f}",
                    xy=(x_e, t['entry']),
                    xytext=(8, label_offset[(i - 1) % len(label_offset)]),
                    textcoords='offset points', color='#FFC107', fontsize=8.5,
                    fontweight='bold', zorder=10, ha='left',
                    bbox=dict(boxstyle='round,pad=0.25', fc='#0D1B2A', ec='#FFC107', alpha=0.95),
                    arrowprops=dict(arrowstyle='->', color='#FFC107', lw=0.7))

        ax.plot([x_e, x_x], [t['target'], t['target']], color='#76FF03',
                linewidth=1.0, linestyle='-', alpha=0.6, zorder=4)
        ax.plot([x_e, x_x], [t['stop'], t['stop']], color='#FF1744',
                linewidth=1.0, linestyle='-', alpha=0.6, zorder=4)

        c = color_for.get(t['result'], '#FFC107')
        ax.scatter([x_x], [t['exit_price']],
                   marker='X', color=c, s=180, zorder=10, edgecolor='black', linewidth=1.5)
        ax.annotate(f"#{i} {t['result']} {t['pl_pts']:+.1f}pt (${t['pl_pts']*2:+.0f})",
                    xy=(x_x, t['exit_price']),
                    xytext=(8, -label_offset[(i - 1) % len(label_offset)]),
                    textcoords='offset points', color=c, fontsize=8.5,
                    fontweight='bold', zorder=10, ha='left',
                    bbox=dict(boxstyle='round,pad=0.25', fc='#0D1B2A', ec=c, alpha=0.95),
                    arrowprops=dict(arrowstyle='->', color=c, lw=0.7))

    last_x = mdates.date2num(bars5.index[-1]) + 0.005
    ax.text(last_x, rh, f' RH {rh:.2f}', color='#E0E0E0', fontsize=8, va='center')
    ax.text(last_x, rl, f' RL {rl:.2f}', color='#E0E0E0', fontsize=8, va='center')

    title = f"{date_obj}  ·  {sym}  ·  Range {rv:.1f} pts  ·  Pattern {pattern}"
    subtitle = f"Net: {total_pl:+.2f} pts (${total_pl*2:+.0f}/MNQ)"
    ax.set_title(f"{title}\n{subtitle}", color='white', fontsize=13,
                 fontweight='bold', pad=12, loc='left')
    ax.set_xlabel('NY Time', color='#9FB3C8', fontsize=9)
    ax.set_ylabel(f'{sym} Price', color='#9FB3C8', fontsize=9)
    ax.tick_params(colors='#9FB3C8', labelsize=8)
    for s in ax.spines.values():
        s.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color='#9FB3C8')
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=NY))
    ax.set_xlim(bars5.index[0] - pd.Timedelta(minutes=10),
                bars5.index[-1] + pd.Timedelta(minutes=25))

    plt.tight_layout()
    plt.savefig(outpath, dpi=120, bbox_inches='tight', facecolor='#0D1B2A')
    plt.close()
    return pattern, total_pl, rv


def main():
    ap = argparse.ArgumentParser(
        description='Random case-study PNGs from MNQ step2 backtest CSV.',
        epilog=RANDOM_SAMPLES_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument('-n', type=int, default=44, help='Number of random samples')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--start', default='2024-01-01', help='Earliest date to sample from')
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load CSV and pick valid days
    csv = pd.read_csv(CSV_FILE)
    csv['Date'] = pd.to_datetime(csv['Date']).dt.date
    csv = csv[csv['Date'] >= pd.to_datetime(args.start).date()]
    available_days = sorted(csv['Date'].unique())
    print(f"Available days from {args.start}: {len(available_days):,}")

    rng = random.Random(args.seed)
    sampled = sorted(rng.sample(available_days, min(args.n, len(available_days))))
    print(f"Sampling {len(sampled)} days (seed={args.seed})")

    # Load DBN once
    by_date = load_dbn_once()

    # Process each
    rows = []
    for i, d in enumerate(sampled, 1):
        if d not in by_date:
            print(f"  [{i:>3}/{len(sampled)}] {d}: no DBN data, skipping")
            continue
        df1 = by_date[d]
        csv_rows = csv[csv['Date'] == d]
        outpath = OUT_DIR / f'{d}.png'
        try:
            res = draw_chart(d, df1, csv_rows, outpath)
            if res is None:
                continue
            pattern, total_pl, rv = res
            rows.append({'date': d, 'symbol': csv_rows['Symbol'].iloc[0],
                         'range': round(rv, 2), 'pattern': pattern,
                         'pl_pts': round(total_pl, 2),
                         'pl_dollar': round(total_pl * 2, 0)})
            print(f"  [{i:>3}/{len(sampled)}] {d} {csv_rows['Symbol'].iloc[0]} "
                  f"range={rv:>6.1f} pat={pattern:<8} pl={total_pl:>+7.1f} ${total_pl*2:>+6.0f}")
        except Exception as e:
            print(f"  [{i:>3}/{len(sampled)}] {d}: error - {e}")

    # Write index markdown
    idx = OUT_DIR / 'INDEX.md'
    with open(idx, 'w') as f:
        f.write(f"# Random Sample of {len(rows)} Trading Days (v2 MNQ NY)\n\n")
        f.write(f"Sampled with seed={args.seed} from days >= {args.start}.\n")
        f.write(f"Each row links to its annotated 5-min candle chart.\n\n")

        # Categorize and summarize
        def cat(p):
            if p in ('LW+LW', 'SW+SW', 'LW+SW', 'SW+LW'): return 'Double Win'
            if p in ('LL+SL', 'SL+LL'):                   return 'Double Loss'
            if p in ('LL+SW', 'SL+LW'):                   return 'Loss-then-Win'
            if p in ('LW+SL', 'SW+LL'):                   return 'Win-then-Loss'
            if 'E' in p:                                  return 'EOD-Close'
            if p in ('LW', 'SW'):                         return 'Single Win'
            if p in ('LL', 'SL'):                         return 'Single Loss'
            return 'Other'

        cats = Counter(cat(r['pattern']) for r in rows)
        f.write("## Pattern distribution in this sample\n\n")
        f.write("| Category | Count | % |\n|---|---|---|\n")
        for k, v in cats.most_common():
            f.write(f"| {k} | {v} | {v / len(rows) * 100:.1f}% |\n")
        total = sum(r['pl_dollar'] for r in rows)
        wins = sum(1 for r in rows if r['pl_dollar'] > 0)
        f.write(f"\n**Sample summary:** {len(rows)} days, {wins} green ({wins/len(rows)*100:.1f}%), "
                f"net ${total:,.0f}/MNQ over the sample window.\n\n")

        # Sorted by date
        f.write("## All sampled days\n\n")
        f.write("| Date | Symbol | Range | Pattern | Net pts | Net $/MNQ | Chart |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for r in sorted(rows, key=lambda x: x['date']):
            d = r['date']
            f.write(f"| {d} | {r['symbol']} | {r['range']} | {r['pattern']} | "
                    f"{r['pl_pts']:+.2f} | ${r['pl_dollar']:+,.0f} | "
                    f"[{d}.png]({d}.png) |\n")

    print(f"\nWrote index: {idx}")
    print(f"Charts in:   {OUT_DIR}")


if __name__ == '__main__':
    main()
