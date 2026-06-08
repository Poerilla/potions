#!/usr/bin/env python3
"""
Render N annotated charts of v2d (fade-the-breakout) trades for visual verification.

For each sampled day, walks the 1-min bars through the v2d simulation
to find the actual entry and exit times. Then renders a 5-min candle
chart with:
  - Opening range band (9:30-9:45)
  - Range boundaries (RH, RL)
  - The BREAKOUT trigger that armed the fade (yellow dashed marker)
  - The fade ENTRY (yellow triangle, just inside the range)
  - The fade TARGET (opposite range boundary, green line)
  - The fade STOP (RH+Range or RL-Range, red line — much wider than v2b)
  - Exit marker (X colored by Win/Loss)

Output: mnq/v2d/case_studies/<date>.png  +  INDEX.md
"""
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.dates as mdates
import argparse
import random
from datetime import time
from pathlib import Path

import databento as db
import pandas as pd
import pytz

import matplotlib
matplotlib.use('Agg')


NY = pytz.timezone('America/New_York')
DBN_FILE = '/home/tester/hsm/potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'
CSV_FILE = '/home/tester/hsm/potions/mnq/v2d/mnq_orb_results_v2d.csv'
OUT_DIR = Path('/home/tester/hsm/potions/mnq/v2d/case_studies')
TICK = 0.25
MULT = 2.00


def load_dbn_once():
    print(f"Loading DBN ...")
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
    return {d: g for d, g in df.groupby(df.index.date)}


def find_v2d_events(df1, rh, rl, trade_direction, entry_price, target, stop):
    """
    Walk the v2d state machine to find for THIS trade:
      - the breakout-detect bar (when the trigger that armed the fade fired)
      - the entry bar (when the fade fill happened)
      - the exit bar (when target/stop hit)
    Returns dict.
    """
    long_break_trig = rh + TICK
    short_break_trig = rl - TICK
    short_fade_trig = rh - TICK   # fade-Short entry trigger (sell stop)
    long_fade_trig = rl + TICK   # fade-Long entry trigger (buy stop)

    after_range = df1[df1.index.time >= time(9, 45)]

    # For a fade-Long trade: we need a Short breakout first (price <= short_break_trig)
    # For a fade-Short trade: we need a Long breakout first (price >= long_break_trig)
    if trade_direction == 'Long':
        breakout_trig = short_break_trig
        breakout_dir = 'down'
        entry_trig = long_fade_trig
        entry_dir = 'up'
    else:
        breakout_trig = long_break_trig
        breakout_dir = 'up'
        entry_trig = short_fade_trig
        entry_dir = 'down'

    breakout_time = None
    for ts, bar in after_range.iterrows():
        if breakout_dir == 'up' and bar['high'] >= breakout_trig:
            breakout_time = ts
            break
        if breakout_dir == 'down' and bar['low'] <= breakout_trig:
            breakout_time = ts
            break

    entry_time = None
    if breakout_time is not None:
        # entry can happen on bars AFTER the breakout bar
        after_break = df1[df1.index > breakout_time]
        for ts, bar in after_break.iterrows():
            if entry_dir == 'up' and bar['high'] >= entry_trig:
                entry_time = ts
                break
            if entry_dir == 'down' and bar['low'] <= entry_trig:
                entry_time = ts
                break

    if entry_time is None:
        entry_time = after_range.index[0]

    exit_time = None
    for ts, bar in df1[df1.index >= entry_time].iterrows():
        if trade_direction == 'Long':
            if bar['low'] < stop:
                exit_time = ts
                break
            if bar['high'] >= target:
                exit_time = ts
                break
        else:
            if bar['high'] > stop:
                exit_time = ts
                break
            if bar['low'] <= target:
                exit_time = ts
                break
    if exit_time is None:
        exit_time = df1.index[-1]

    return {
        'breakout_time': breakout_time,
        'entry_time': entry_time,
        'exit_time': exit_time,
    }


def draw_chart(date_obj, df1, csv_rows, outpath):
    if df1.empty:
        return None
    rng_bars = df1[(df1.index.time >= time(9, 30)) &
                   (df1.index.time < time(9, 45))]
    rh = rng_bars['high'].max()
    rl = rng_bars['low'].min()
    rv = rh - rl

    trades = []
    for _, r in csv_rows.iterrows():
        d = r['Trade_Direction']
        target = rh if d == 'Long' else rl
        stop = rl - rv if d == 'Long' else rh + rv
        entry_price = r['Entry_Price']
        events = find_v2d_events(df1, rh, rl, d, entry_price, target, stop)
        if r['Result'].startswith('EOD'):
            events['exit_time'] = df1.index[-1]
        trades.append({
            'direction': d, 'entry': entry_price, 'exit_price': r['Exit_Price'],
            'target': target, 'stop': stop, 'result': r['Result'],
            'entry_time': events['entry_time'], 'exit_time': events['exit_time'],
            'breakout_time': events['breakout_time'],
            'pl_pts': r['Trade_PL'],
        })

    bars5 = df1.resample('5T').agg(
        open=('open', 'first'), high=('high', 'max'),
        low=('low', 'min'), close=('close', 'last')).dropna(subset=['open'])

    pattern = '+'.join([f"{t['direction'][0]}{t['result'][0]}" for t in trades])
    total_pl = sum(t['pl_pts'] for t in trades)
    sym = csv_rows['Symbol'].iloc[0]

    fig = plt.figure(figsize=(16, 9), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')
    ax.axvspan(bars5.index[0], bars5.index[0] + pd.Timedelta(minutes=15),
               color='#1F4E79', alpha=0.30, zorder=0)
    ax.axhline(rh, color='#E0E0E0', linestyle='--', linewidth=1.2, zorder=2)
    ax.axhline(rl, color='#E0E0E0', linestyle='--', linewidth=1.2, zorder=2)
    ax.axhspan(rl, rh, color='#1F4E79', alpha=0.10, zorder=0)
    # Fade entry triggers (just inside range)
    ax.axhline(rh - TICK, color='#FF9800', linestyle=':',
               linewidth=0.9, alpha=0.7, zorder=2)
    ax.axhline(rl + TICK, color='#FF9800', linestyle=':',
               linewidth=0.9, alpha=0.7, zorder=2)
    # Breakout triggers (outside range)
    ax.axhline(rh + TICK, color='#9E9E9E', linestyle=':',
               linewidth=0.7, alpha=0.5, zorder=2)
    ax.axhline(rl - TICK, color='#9E9E9E', linestyle=':',
               linewidth=0.7, alpha=0.5, zorder=2)
    # SL extremes (way outside range)
    ax.axhline(rh + rv, color='#E91E63', linestyle='--',
               linewidth=0.8, alpha=0.5, zorder=2)
    ax.axhline(rl - rv, color='#E91E63', linestyle='--',
               linewidth=0.8, alpha=0.5, zorder=2)

    # Candles
    for ts, row in bars5.iterrows():
        x = mdates.date2num(ts)
        width = 5/(24*60)*0.7
        c = '#26A69A' if row['close'] >= row['open'] else '#EF5350'
        ax.vlines(x, row['low'], row['high'], color=c, linewidth=0.8, zorder=3)
        body_lo = min(row['open'], row['close'])
        body_hi = max(row['open'], row['close'])
        ax.add_patch(mpatches.Rectangle(
            (x - width/2, body_lo), width, max(body_hi-body_lo, 0.05),
            facecolor=c, edgecolor=c, alpha=0.95, zorder=3))

    color_for = {'Win': '#76FF03', 'Loss': '#FF1744',
                 'EOD-Win': '#69F0AE', 'EOD-Loss': '#FFB74D'}
    label_offset = [+22, -32, +44, -54]

    for i, t in enumerate(trades, 1):
        # 1) Mark the breakout that armed the fade
        if t['breakout_time'] is not None:
            x_b = mdates.date2num(t['breakout_time'])
            break_y = rh + TICK if t['direction'] == 'Short' else rl - TICK
            ax.scatter([x_b], [break_y], marker='*', color='#9E9E9E', s=120,
                       zorder=9, edgecolor='black', linewidth=1.0)
            ax.annotate(f"#{i} {'L' if t['direction']=='Short' else 'S'} BREAK\n(armed fade)",
                        xy=(x_b, break_y), xytext=(
                            8, 22 if t['direction'] == 'Short' else -32),
                        textcoords='offset points', color='#BDBDBD', fontsize=8,
                        ha='left', zorder=9,
                        bbox=dict(boxstyle='round,pad=0.2', fc='#0D1B2A', ec='#9E9E9E', alpha=0.9))

        # 2) Entry marker (where fade filled)
        x_e = mdates.date2num(t['entry_time'])
        ax.scatter([x_e], [t['entry']],
                   marker='^' if t['direction'] == 'Long' else 'v',
                   color='#FFC107', s=200, zorder=10, edgecolor='black', linewidth=1.5)
        ax.annotate(f"#{i} FADE {t['direction']} @ {t['entry']:.2f}",
                    xy=(x_e, t['entry']),
                    xytext=(8, label_offset[(i-1) % len(label_offset)]),
                    textcoords='offset points', color='#FFC107', fontsize=9,
                    fontweight='bold', zorder=10, ha='left',
                    bbox=dict(boxstyle='round,pad=0.3', fc='#0D1B2A', ec='#FFC107', alpha=0.95))

        # 3) Target/stop horizontal lines from entry to exit
        x_x = mdates.date2num(t['exit_time'])
        ax.plot([x_e, x_x], [t['target'], t['target']], color='#76FF03',
                linewidth=1.0, linestyle='-', alpha=0.7, zorder=4)
        ax.plot([x_e, x_x], [t['stop'], t['stop']], color='#FF1744',
                linewidth=1.0, linestyle='-', alpha=0.7, zorder=4)

        # 4) Exit marker
        c = color_for.get(t['result'], '#FFC107')
        ax.scatter([x_x], [t['exit_price']],
                   marker='X', color=c, s=200, zorder=10, edgecolor='black', linewidth=1.5)
        ax.annotate(f"#{i} {t['result']} {t['pl_pts']:+.1f}pt (${t['pl_pts']*MULT:+.0f})",
                    xy=(x_x, t['exit_price']),
                    xytext=(8, -label_offset[(i-1) % len(label_offset)]),
                    textcoords='offset points', color=c, fontsize=9, fontweight='bold',
                    zorder=10, ha='left',
                    bbox=dict(boxstyle='round,pad=0.3', fc='#0D1B2A', ec=c, alpha=0.95))

    last_x = mdates.date2num(bars5.index[-1]) + 0.005
    ax.text(last_x, rh, f' RH {rh:.2f}',
            color='#E0E0E0', fontsize=8, va='center')
    ax.text(last_x, rl, f' RL {rl:.2f}',
            color='#E0E0E0', fontsize=8, va='center')
    ax.text(last_x, rh + rv, f' SL-Short {rh+rv:.0f}',
            color='#E91E63', fontsize=7, va='center', alpha=0.8)
    ax.text(last_x, rl - rv, f' SL-Long {rl-rv:.0f}',
            color='#E91E63', fontsize=7, va='center', alpha=0.8)

    title = f"{date_obj}  ·  {sym}  ·  Range {rv:.1f}pt  ·  v2d FADE  ·  {pattern}"
    subtitle = f"Net: {total_pl:+.2f}pt  (${total_pl*MULT:+.0f}/MNQ)"
    ax.set_title(f"{title}\n{subtitle}", color='white',
                 fontsize=13, fontweight='bold', pad=12, loc='left')
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
    return pattern, total_pl, rv, sym


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-n', type=int, default=30)
    ap.add_argument('--seed', type=int, default=42)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv = pd.read_csv(CSV_FILE)
    csv['Date'] = pd.to_datetime(csv['Date']).dt.date
    avail_days = sorted(csv['Date'].unique())

    rng = random.Random(args.seed)
    sampled = sorted(rng.sample(avail_days, min(args.n, len(avail_days))))
    print(f"Sampling {len(sampled)} v2d trade days (seed={args.seed})")

    by_date = load_dbn_once()
    print(f"  {len(by_date):,} days indexed in DBN")

    rows = []
    for i, d in enumerate(sampled, 1):
        if d not in by_date:
            continue
        df1 = by_date[d]
        csv_rows = csv[csv['Date'] == d]
        outpath = OUT_DIR / f'{d}.png'
        try:
            res = draw_chart(d, df1, csv_rows, outpath)
            if res:
                pattern, total_pl, rv, sym = res
                rows.append({'date': d, 'symbol': sym, 'range': round(rv, 2),
                             'pattern': pattern, 'pl_pts': round(total_pl, 2),
                             'pl_dollar': round(total_pl * MULT, 0)})
                if i % 10 == 0:
                    print(f"  ... {i}/{len(sampled)}")
        except Exception as e:
            print(f"  {d}: error - {e}")

    # INDEX.md
    idx = OUT_DIR / 'INDEX.md'
    with open(idx, 'w') as f:
        f.write(f"# v2d Fade Strategy — {len(rows)} Sample Days (MNQ NY)\n\n")
        f.write(
            "Charts show: range band, breakout that armed the fade (★), fade entry (▲▼),\n")
        f.write(
            "target (opposite range boundary, green) and stop (RH+Range or RL-Range, red dashed).\n\n")
        wins = sum(1 for r in rows if r['pl_dollar'] > 0)
        sample_pl = sum(r['pl_dollar'] for r in rows)
        f.write(f"**Sample stats:** {len(rows)} days, {wins} green ({wins/len(rows)*100:.1f}%), "
                f"net ${sample_pl:+,.0f}/MNQ\n\n")
        f.write("| Date | Symbol | Range | Pattern | Net pts | Net $/MNQ | Chart |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for r in sorted(rows, key=lambda x: x['date']):
            f.write(f"| {r['date']} | {r['symbol']} | {r['range']} | {r['pattern']} | "
                    f"{r['pl_pts']:+.1f} | ${r['pl_dollar']:+,.0f} | "
                    f"[{r['date']}.png]({r['date']}.png) |\n")

    print(f"\nDone. {len(rows)} charts + INDEX.md in {OUT_DIR}")


if __name__ == '__main__':
    main()
