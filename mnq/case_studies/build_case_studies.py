#!/usr/bin/env python3
"""
Generate annotated candlestick charts for v2 ORB case studies.

Picks 6 representative trading-day patterns from the actual v2 backtest:
  1. Loss-then-Win (most common pattern: ~25% of days)
  2. Double Win trend day (best routine outcome)
  3. Big-range trend day (windfall)
  4. Whipsaw / Double Loss (worst kind of day)
  5. EOD Close (target/stop never hit)
  6. Single-trade Win (rare clean execution)

For each: 5-min candles, range band, trigger lines, entry/exit markers, target/stop levels.
"""
import os
from datetime import time
from pathlib import Path

import databento as db
import pandas as pd
import pytz

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.dates as mdates


NY = pytz.timezone('America/New_York')
DBN_FILE = '/home/tester/hsm/potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'
OUT_DIR  = Path('/home/tester/hsm/potions/case_studies')
TICK     = 0.25


def load_day(date_obj, symbol):
    store = db.DBNStore.from_file(DBN_FILE)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'] == symbol].copy()
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY)
    df = df[df['ts_event'].dt.date == date_obj].copy()
    df = df[(df['ts_event'].dt.time >= time(9,30)) & (df['ts_event'].dt.time < time(16,0))]
    return df.set_index('ts_event').sort_index()


def to_5min(df1):
    return df1.resample('5T').agg(
        open=('open','first'), high=('high','max'),
        low=('low','min'), close=('close','last'),
        volume=('volume','sum')).dropna(subset=['open'])


def find_entry_exit(df1, rh, rl, prior_exit, direction, target, stop):
    """Walk 1-min bars after prior_exit to find when this trade was entered and exited."""
    after = df1[df1.index > prior_exit]

    long_trig  = rh + TICK
    short_trig = rl - TICK
    entry_time = None
    for ts, bar in after.iterrows():
        if direction == 'Long' and bar['high'] >= long_trig:
            entry_time = ts; break
        if direction == 'Short' and bar['low'] <= short_trig:
            entry_time = ts; break
    if entry_time is None:
        entry_time = after.index[0]

    exit_time = None
    for ts, bar in df1[df1.index >= entry_time].iterrows():
        if direction == 'Long':
            if bar['low'] < stop:  exit_time = ts; break
            if bar['high'] >= target: exit_time = ts; break
        else:
            if bar['high'] > stop: exit_time = ts; break
            if bar['low']  <= target: exit_time = ts; break
    if exit_time is None:
        exit_time = df1.index[-1]

    return entry_time, exit_time


def draw(date_obj, symbol, csv_rows, title, subtitle, outpath):
    df1 = load_day(date_obj, symbol)
    if df1.empty:
        print(f"  No 1-min data for {date_obj} {symbol}")
        return

    rng_bars = df1[(df1.index.time >= time(9,30)) & (df1.index.time < time(9,45))]
    rh = rng_bars['high'].max()
    rl = rng_bars['low'].min()
    rv = rh - rl

    # Build trade objects with derived entry/exit times
    trades = []
    prior_exit = df1[df1.index.time < time(9,45)].index[-1]  # start search after range
    for _, r in csv_rows.iterrows():
        d = r['Trade_Direction']
        target = rh + rv if d == 'Long' else rl - rv
        stop   = rl if d == 'Long' else rh
        e_time, x_time = find_entry_exit(df1, rh, rl, prior_exit, d, target, stop)
        # For EOD result, exit_time is the last bar
        if r['Result'].startswith('EOD'):
            x_time = df1.index[-1]
        trades.append({
            'direction': d,
            'entry':     r['Entry_Price'],
            'exit_price':r['Exit_Price'],
            'target':    target,
            'stop':      stop,
            'result':    r['Result'],
            'entry_time': e_time,
            'exit_time':  x_time,
            'pl_pts':    r['Trade_PL'],
        })
        prior_exit = x_time

    bars5 = to_5min(df1)

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

    # 5-min candles
    for ts, row in bars5.iterrows():
        x = mdates.date2num(ts)
        width = 5/(24*60)*0.7
        is_up = row['close'] >= row['open']
        c = '#26A69A' if is_up else '#EF5350'
        ax.vlines(x, row['low'], row['high'], color=c, linewidth=0.8, zorder=3)
        body_lo = min(row['open'], row['close']); body_hi = max(row['open'], row['close'])
        ax.add_patch(mpatches.Rectangle((x - width/2, body_lo), width, max(body_hi-body_lo, 0.05),
                                         facecolor=c, edgecolor=c, alpha=0.95, zorder=3))

    # Trade annotations
    color_for = {'Win': '#76FF03', 'Loss': '#FF1744',
                 'EOD-Win': '#69F0AE', 'EOD-Loss': '#FFB74D'}
    label_offset_alt = [+22, -32, +44, -54]  # alternate offsets if multiple trades

    for i, t in enumerate(trades, 1):
        x_e = mdates.date2num(t['entry_time'])
        x_x = mdates.date2num(t['exit_time'])

        # Entry marker (yellow triangle)
        ax.scatter([x_e], [t['entry']],
                   marker='^' if t['direction']=='Long' else 'v',
                   color='#FFC107', s=200, zorder=10, edgecolor='black', linewidth=1.5)
        ax.annotate(f"#{i} {t['direction'].upper()} ENTRY @ {t['entry']:.2f}",
                    xy=(x_e, t['entry']),
                    xytext=(8, label_offset_alt[(i-1) % len(label_offset_alt)]),
                    textcoords='offset points', color='#FFC107', fontsize=9, fontweight='bold',
                    zorder=10, ha='left',
                    bbox=dict(boxstyle='round,pad=0.3', fc='#0D1B2A', ec='#FFC107', alpha=0.95),
                    arrowprops=dict(arrowstyle='->', color='#FFC107', lw=0.8))

        # Target / stop horizontal lines (entry → exit)
        ax.plot([x_e, x_x], [t['target'], t['target']], color='#76FF03',
                linewidth=1.2, linestyle='-', alpha=0.7, zorder=4)
        ax.plot([x_e, x_x], [t['stop'], t['stop']], color='#FF1744',
                linewidth=1.2, linestyle='-', alpha=0.7, zorder=4)

        # Exit marker
        c = color_for.get(t['result'], '#FFC107')
        ax.scatter([x_x], [t['exit_price']],
                   marker='X', color=c, s=200, zorder=10, edgecolor='black', linewidth=1.5)
        dollar = t['pl_pts'] * 2
        ax.annotate(f"#{i} EXIT {t['result']}\n{t['pl_pts']:+.2f} pts (${dollar:+.0f}/MNQ)",
                    xy=(x_x, t['exit_price']),
                    xytext=(8, -label_offset_alt[(i-1) % len(label_offset_alt)]),
                    textcoords='offset points', color=c, fontsize=9, fontweight='bold',
                    zorder=10, ha='left',
                    bbox=dict(boxstyle='round,pad=0.3', fc='#0D1B2A', ec=c, alpha=0.95),
                    arrowprops=dict(arrowstyle='->', color=c, lw=0.8))

    # Right-edge labels
    last_ts = bars5.index[-1]
    last_x = mdates.date2num(last_ts) + 0.005
    ax.text(last_x, rh, f' RH {rh:.2f}', color='#E0E0E0', fontsize=9, va='center')
    ax.text(last_x, rl, f' RL {rl:.2f}', color='#E0E0E0', fontsize=9, va='center')
    ax.text(last_x, rh + TICK, f' Buy-stop @ +1 tick', color='#76FF03', fontsize=8, va='center', alpha=0.8)
    ax.text(last_x, rl - TICK, f' Sell-stop @ -1 tick', color='#FF5252', fontsize=8, va='center', alpha=0.8)

    # Title
    ax.set_title(f"{title}\n{subtitle}", color='white', fontsize=14, fontweight='bold', pad=15, loc='left')
    ax.set_xlabel('NY Time', color='#9FB3C8')
    ax.set_ylabel(f'{symbol} Price', color='#9FB3C8')
    ax.tick_params(colors='#9FB3C8')
    for s in ax.spines.values():
        s.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color='#9FB3C8')
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=NY))
    ax.set_xlim(bars5.index[0] - pd.Timedelta(minutes=10), bars5.index[-1] + pd.Timedelta(minutes=25))

    plt.tight_layout()
    plt.savefig(outpath, dpi=130, bbox_inches='tight', facecolor='#0D1B2A')
    plt.close()
    print(f"  Saved {outpath}")


def case(date_str, symbol, csv_path, title, subtitle, filename):
    date_obj = pd.to_datetime(date_str).date()
    csv = pd.read_csv(csv_path)
    csv['Date'] = pd.to_datetime(csv['Date']).dt.date
    rows = csv[csv['Date'] == date_obj].copy()
    if rows.empty:
        print(f"  No trades for {date_str}")
        return
    out = OUT_DIR / filename
    draw(date_obj, symbol, rows, title, subtitle, out)


if __name__ == '__main__':
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = '/home/tester/hsm/potions/mnq/mnq_orb_results_stops.csv'

    cases = [
        ('2025-04-28', 'MNQM5', 'Case 1 — "Stopped, then Reversed and Won" (most common pattern)',
            'Range = 116.25. Long stop fired first, price reversed, Short stop fired and hit target. Net: -1 pt = -$2/MNQ. ~25% of days look exactly like this.',
            'case1_loss_then_win.png'),

        ('2025-01-15', 'MNQH5', 'Case 2 — Double Long Win (clean trend day)',
            'Range = 121. Long stop fired, target hit. Re-armed. Long stop fired again, target hit again. +241 pts = +$482/MNQ.',
            'case2_double_long_win.png'),

        ('2025-04-07', 'MNQM5', 'Case 3 — Big-Range Windfall',
            'Range = 307.75 (~3x typical). Strong gap-down + recovery. Long target hit, re-armed, Long target hit again. +614.5 pts = +$1,229/MNQ. Rare but real.',
            'case3_big_range_windfall.png'),

        ('2025-04-11', 'MNQM5', 'Case 4 — Whipsaw / Double Loss (the worst kind of day)',
            'Range = 217.75. Long stop fired and reversed to RL (full-range loss). Short stop fired and reversed to RH (another full-range loss). -436 pts = -$873/MNQ.',
            'case4_double_loss_whipsaw.png'),

        ('2025-03-18', 'MNQM5', 'Case 5 — EOD-Close (target/stop never hit)',
            'Range = 192.25. Short triggered, but neither target nor stop reached by 16:00. Closed at the last 5-min bar essentially flat. +1.5 pts = +$3/MNQ.',
            'case5_eod_close.png'),

        ('2025-08-04', 'MNQU5', 'Case 6 — Single-Trade Win (rare clean execution)',
            'Range = 108.25. Long target hit. Price never reversed back to RL, so the second trade never armed. +107.75 pts = +$215/MNQ.',
            'case6_single_trade_win.png'),
    ]

    for date_str, sym, title, subtitle, fname in cases:
        print(f"\n[Building] {date_str} {sym}: {title}")
        case(date_str, sym, csv_path, title, subtitle, fname)

    print(f"\nDone. Charts in {OUT_DIR}")
