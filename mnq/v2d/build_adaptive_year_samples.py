#!/usr/bin/env python3
"""
Per-year case studies for MNQ NY **adaptive 50/150** (v2b + v2d).

Samples N trading days per calendar year from
`mnq/v2d/mnq_orb_results_adaptive_50_150.csv`, renders annotated 5-min
candles with correct entry logic per regime:
  - **v2b**: stop triggers at RH+1tick / RL-1tick (same as build_year_samples)
  - **v2d**: fade entries at CSV Entry_Price (stop-through fill), exits at
    target/stop from v2d bracket math

Outputs:
  mnq/case_studies/adaptive_by_year/<year>/<date>.png
  mnq/case_studies/adaptive_by_year/<year>/INDEX.md
  mnq/case_studies/adaptive_by_year/SUMMARY.md

Usage:
  python mnq/v2d/build_adaptive_year_samples.py
  python mnq/v2d/build_adaptive_year_samples.py -n 50 --seed 7
"""
from __future__ import annotations

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

TICK = 0.25
MULT = 2.0
FEE_RT = 1.50

DBN = '/home/tester/hsm/potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'
ADAPTIVE_CSV = Path('/home/tester/hsm/potions/mnq/v2d/mnq_orb_results_adaptive_50_150.csv')
OUT_BASE = Path('/home/tester/hsm/potions/mnq/case_studies/adaptive_by_year')
SYMBOL_PREFIX = 'MNQ'


def load_dbn():
    print(f'Loading DBN ({DBN}) ...')
    store = db.DBNStore.from_file(DBN)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith(SYMBOL_PREFIX)].copy()
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY)
    df['date'] = df['ts_event'].dt.date
    df['t'] = df['ts_event'].dt.time
    fm = (df.groupby(['date', 'symbol'])['volume'].sum()
            .groupby(level='date').idxmax().apply(lambda x: x[1]).to_dict())
    df = df[df.apply(lambda r: r['symbol'] == fm.get(r['date']), axis=1)]
    df = df[(df['t'] >= time(9, 30)) & (df['t'] < time(16, 0))].copy()
    df = df.set_index('ts_event').sort_index()
    by_date = {d: g for d, g in df.groupby(df.index.date)}
    print(f'  {len(by_date):,} RTH days')
    return by_date


def find_entry_v2b(df1, rh, rl, prior_exit, direction, target, stop, tick):
    after = df1[df1.index > prior_exit]
    long_trig = rh + tick
    short_trig = rl - tick
    entry_time = None
    for ts, bar in after.iterrows():
        if direction == 'Long' and bar['high'] >= long_trig:
            entry_time = ts
            break
        if direction == 'Short' and bar['low'] <= short_trig:
            entry_time = ts
            break
    if entry_time is None:
        entry_time = after.index[0] if not after.empty else df1.index[-1]
    exit_time = None
    for ts, bar in df1[df1.index >= entry_time].iterrows():
        if direction == 'Long':
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
    return entry_time, exit_time


def find_entry_at_price(df1, prior_exit, direction, entry_price, tick_slip=2):
    """First bar after prior_exit where a stop at entry_price would fill."""
    tol = tick_slip * TICK
    after = df1[df1.index > prior_exit]
    for ts, bar in after.iterrows():
        if direction == 'Long' and bar['high'] >= entry_price - tol:
            return ts
        if direction == 'Short' and bar['low'] <= entry_price + tol:
            return ts
    return after.index[0] if not after.empty else df1.index[-1]


def find_exit_v2d(df1, entry_time, direction, target, stop, result):
    for ts, bar in df1[df1.index >= entry_time].iterrows():
        if direction == 'Long':
            if bar['low'] < stop:
                return ts
            if bar['high'] >= target:
                return ts
        else:
            if bar['high'] > stop:
                return ts
            if bar['low'] <= target:
                return ts
    return df1.index[-1]


def build_trades_for_day(df1, csv_rows, tick):
    """Return list of trade dicts with times + levels for plotting."""
    rng_bars = df1[(df1.index.time >= time(9, 30)) & (df1.index.time < time(9, 45))]
    if rng_bars.empty:
        return [], None, None, None
    rh = float(rng_bars['high'].max())
    rl = float(rng_bars['low'].min())
    rv = rh - rl

    regime = str(csv_rows.iloc[0]['Regime'])
    prior_exit = df1[df1.index.time < time(9, 45)].index[-1]
    trades = []

    for _, r in csv_rows.iterrows():
        d = r['Trade_Direction']
        entry_px = float(r['Entry_Price'])
        if regime == 'v2b':
            target = rh + rv if d == 'Long' else rl - rv
            stop = rl if d == 'Long' else rh
            e_time, x_time = find_entry_v2b(df1, rh, rl, prior_exit, d, target, stop, tick)
            if str(r['Result']).startswith('EOD'):
                x_time = df1.index[-1]
        else:
            # v2d fade
            if d == 'Long':
                target, stop = rh, rl - rv
            else:
                target, stop = rl, rh + rv
            e_time = find_entry_at_price(df1, prior_exit, d, entry_px)
            x_time = find_exit_v2d(df1, e_time, d, target, stop, r['Result'])
            if str(r['Result']).startswith('EOD'):
                x_time = df1.index[-1]

        trades.append({
            'direction': d,
            'entry': entry_px,
            'exit_price': float(r['Exit_Price']),
            'target': target,
            'stop': stop,
            'result': r['Result'],
            'entry_time': e_time,
            'exit_time': x_time,
            'pl_pts': float(r['Trade_PL']),
            'regime': regime,
        })
        prior_exit = x_time

    return trades, rh, rl, rv


def draw_chart(date_obj, df1, csv_rows, outpath, tick, mult, ma_f, ma_s, regime_day):
    trades, rh, rl, rv = build_trades_for_day(df1, csv_rows, tick)
    if not trades or rh is None:
        return None

    bars5 = df1.resample('5min').agg(
        open=('open', 'first'),
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last'),
    ).dropna(subset=['open'])

    pattern = '+'.join(
        f"{t['direction'][0]}{t['result'][0]}" for t in trades) if trades else 'NoTrade'
    total_pl = sum(t['pl_pts'] for t in trades)
    sym = csv_rows['Symbol'].iloc[0] if not csv_rows.empty else ''

    fig = plt.figure(figsize=(14, 8), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')

    ax.axvspan(bars5.index[0], bars5.index[0] + pd.Timedelta(minutes=15),
               color='#1F4E79', alpha=0.30, zorder=0)
    ax.axhline(rh, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
    ax.axhline(rl, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
    ax.axhspan(rl, rh, color='#1F4E79', alpha=0.10, zorder=0)

    ax.axhline(rh + tick, color='#76FF03', linestyle=':', linewidth=0.8, alpha=0.7, zorder=2)
    ax.axhline(rl - tick, color='#FF5252', linestyle=':', linewidth=0.8, alpha=0.7, zorder=2)
    if regime_day == 'v2d':
        ax.axhline(rh - tick, color='#FFB74D', linestyle=':', linewidth=0.7, alpha=0.6, zorder=2)
        ax.axhline(rl + tick, color='#9575CD', linestyle=':', linewidth=0.7, alpha=0.6, zorder=2)

    for ts, row in bars5.iterrows():
        x = mdates.date2num(ts)
        width = 5 / (24 * 60) * 0.7
        is_up = row['close'] >= row['open']
        c = '#26A69A' if is_up else '#EF5350'
        ax.vlines(x, row['low'], row['high'], color=c, linewidth=0.7, zorder=3)
        body_lo = min(row['open'], row['close'])
        body_hi = max(row['open'], row['close'])
        ax.add_patch(mpatches.Rectangle(
            (x - width / 2, body_lo), width, max(body_hi - body_lo, 0.05),
            facecolor=c, edgecolor=c, alpha=0.95, zorder=3))

    color_for = {'Win': '#76FF03', 'Loss': '#FF1744', 'EOD-Win': '#69F0AE', 'EOD-Loss': '#FFB74D'}
    label_offset = [+22, -32, +44, -54]
    for i, t in enumerate(trades, 1):
        x_e = mdates.date2num(t['entry_time'])
        x_x = mdates.date2num(t['exit_time'])
        ax.scatter([x_e], [t['entry']],
                   marker='^' if t['direction'] == 'Long' else 'v',
                   color='#FFC107', s=140, zorder=10, edgecolor='black', linewidth=1.2)
        ax.annotate(f"#{i} {t['direction'][0]} @ {t['entry']:.2f}",
                    xy=(x_e, t['entry']),
                    xytext=(8, label_offset[(i - 1) % len(label_offset)]),
                    textcoords='offset points', color='#FFC107', fontsize=8,
                    fontweight='bold', zorder=10, ha='left',
                    bbox=dict(boxstyle='round,pad=0.2', fc='#0D1B2A', ec='#FFC107', alpha=0.95))
        ax.plot([x_e, x_x], [t['target'], t['target']], color='#76FF03',
                linewidth=0.9, linestyle='-', alpha=0.6, zorder=4)
        ax.plot([x_e, x_x], [t['stop'], t['stop']], color='#FF1744',
                linewidth=0.9, linestyle='-', alpha=0.6, zorder=4)
        c = color_for.get(t['result'], '#FFC107')
        ax.scatter([x_x], [t['exit_price']],
                   marker='X', color=c, s=140, zorder=10, edgecolor='black', linewidth=1.2)
        ax.annotate(f"#{i} {t['result']} {t['pl_pts']:+.0f}pt",
                    xy=(x_x, t['exit_price']),
                    xytext=(8, -label_offset[(i - 1) % len(label_offset)]),
                    textcoords='offset points', color=c, fontsize=8,
                    fontweight='bold', zorder=10, ha='left',
                    bbox=dict(boxstyle='round,pad=0.2', fc='#0D1B2A', ec=c, alpha=0.95))

    last_x = mdates.date2num(bars5.index[-1]) + 0.005
    ax.text(last_x, rh, f' RH {rh:.1f}', color='#E0E0E0', fontsize=7, va='center')
    ax.text(last_x, rl, f' RL {rl:.1f}', color='#E0E0E0', fontsize=7, va='center')

    ma_txt = ''
    if ma_f is not None and ma_s is not None and pd.notna(ma_f) and pd.notna(ma_s):
        ma_txt = f"  ·  prior MA {ma_f:.0f}/{ma_s:.0f}"
    title = (f"{date_obj}  ADAPTIVE 50/150  ·  {regime_day.upper()}{ma_txt}  ·  {sym}  ·  "
             f"Range {rv:.1f}  ·  {pattern}  ·  {total_pl:+.1f}pt (${total_pl*mult:+.0f})")
    ax.set_title(title, color='white', fontsize=9, fontweight='bold', pad=8, loc='left')
    ax.tick_params(colors='#9FB3C8', labelsize=7)
    for s in ax.spines.values():
        s.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color='#9FB3C8')
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=NY))
    ax.set_xlim(bars5.index[0] - pd.Timedelta(minutes=10),
                bars5.index[-1] + pd.Timedelta(minutes=20))

    plt.tight_layout()
    plt.savefig(outpath, dpi=100, bbox_inches='tight', facecolor='#0D1B2A')
    plt.close()
    return pattern, total_pl, rv, sym


def categorize(p):
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


def write_year_index(year, year_dir, rows, full_year_stats, mult):
    idx = year_dir / 'INDEX.md'
    cats = Counter(categorize(r['pattern']) for r in rows)
    sample_total = sum(r['pl_dollar'] for r in rows)
    sample_wins = sum(1 for r in rows if r['pl_dollar'] > 0)

    with open(idx, 'w') as f:
        f.write(f'# {year} — MNQ NY **Adaptive 50/150** case studies (sample)\n\n')
        f.write('Each chart uses the **actual regime that day** (v2b breakout vs v2d fade).\n\n')
        f.write('## Full year (adaptive CSV)\n\n')
        f.write('| Metric | Value |\n|---|---|\n')
        f.write(f"| Trading days | {full_year_stats['days']} |\n")
        f.write(f"| Trades | {full_year_stats['trades']} |\n")
        f.write(f"| Win rate (trades) | {full_year_stats['win_pct']:.1f}% |\n")
        f.write(f"| Net $/contract | ${full_year_stats['net_dollar']:+,.0f} |\n")
        f.write(f"| Days v2b | {full_year_stats['days_v2b']} | Days v2d | {full_year_stats['days_v2d']} |\n")
        f.write(f"| Best day | ${full_year_stats['best_day']:+,.0f} on {full_year_stats['best_date']} |\n")
        f.write(f"| Worst day | ${full_year_stats['worst_day']:+,.0f} on {full_year_stats['worst_date']} |\n\n")
        f.write(f'## Sample ({len(rows)} days)\n\n')
        f.write(f'- Sample net: **${sample_total:+,.0f}/contract**, {sample_wins} green days '
                f'({sample_wins/len(rows)*100:.1f}%)\n\n')
        f.write('### Pattern distribution\n\n| Category | Count | % |\n|---|---|---|\n')
        for k, v in cats.most_common():
            f.write(f'| {k} | {v} | {v / len(rows) * 100:.1f}% |\n')
        f.write('\n## Sampled days\n\n')
        f.write('| Date | Regime | Symbol | Range | Pattern | Day net $ | Chart |\n')
        f.write('|---|---|---|---|---|---|---|\n')
        for r in sorted(rows, key=lambda x: x['date']):
            f.write(f"| {r['date']} | {r['regime_day']} | {r['symbol']} | {r['range']} | {r['pattern']} | "
                    f"${r['pl_dollar']:+,.0f} | [{r['date']}.png]({r['date']}.png) |\n")


def write_summary(out_base, years_data, all_year_stats):
    summary = out_base / 'SUMMARY.md'
    with open(summary, 'w') as f:
        f.write('# MNQ NY — Adaptive 50/150 per-year case studies\n\n')
        f.write('Sampled trading days with **regime-accurate** annotations (v2b stops vs v2d fades).\n\n')
        f.write('## Year-over-year (full adaptive CSV)\n\n')
        f.write('| Year | Days | Trades | Win% | Net $ | v2b days | v2d days | Best day | Worst day |\n')
        f.write('|---|---|---|---|---|---|---|---|---|\n')
        for yr in sorted(all_year_stats):
            s = all_year_stats[yr]
            f.write(f"| **{yr}** | {s['days']} | {s['trades']} | {s['win_pct']:.1f}% | "
                    f"${s['net_dollar']:+,.0f} | {s['days_v2b']} | {s['days_v2d']} | "
                    f"${s['best_day']:+,.0f} ({s['best_date']}) | "
                    f"${s['worst_day']:+,.0f} ({s['worst_date']}) |\n")
        f.write('\n## Folders\n\n')
        for yr in sorted(years_data):
            f.write(f'- [`{yr}/`]({yr}/INDEX.md) — {len(years_data[yr])} charts\n')


def load_adaptive_csv():
    csv = pd.read_csv(ADAPTIVE_CSV)
    if 'Leg' in csv.columns:
        csv = csv[csv['Leg'].fillna('MNQ_NY') == 'MNQ_NY'].copy()
    csv['Date'] = pd.to_datetime(csv['Date']).dt.date
    csv['Year'] = pd.to_datetime(csv['Date']).dt.year
    return csv


def year_stats(ydf):
    daily = ydf.groupby('Date')['Net_$'].sum()
    return {
        'days': ydf['Date'].nunique(),
        'trades': len(ydf),
        'win_pct': (ydf['Trade_PL'] > 0).mean() * 100,
        'pts': ydf['Trade_PL'].sum(),
        'net_dollar': ydf['Net_$'].sum(),
        'best_day': daily.max(),
        'best_date': daily.idxmax(),
        'worst_day': daily.min(),
        'worst_date': daily.idxmin(),
        'days_v2b': ydf[ydf['Regime'] == 'v2b']['Date'].nunique(),
        'days_v2d': ydf[ydf['Regime'] == 'v2d']['Date'].nunique(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-n', type=int, default=100, help='Days to sample per year')
    ap.add_argument('--seed', type=int, default=42)
    args = ap.parse_args()

    OUT_BASE.mkdir(parents=True, exist_ok=True)

    csv = load_adaptive_csv()
    print(f'Adaptive CSV: {len(csv):,} rows, years {csv["Year"].min()}-{csv["Year"].max()}')

    by_date = load_dbn()

    all_year_stats = {}
    for yr in sorted(csv['Year'].unique()):
        all_year_stats[yr] = year_stats(csv[csv['Year'] == yr])

    rng = random.Random(args.seed)
    years_data = {}
    for yr in sorted(csv['Year'].unique()):
        year_dir = OUT_BASE / str(yr)
        year_dir.mkdir(parents=True, exist_ok=True)
        ydf = csv[csv['Year'] == yr]
        avail_days = sorted(ydf['Date'].unique())
        n_take = min(args.n, len(avail_days))
        sampled = sorted(rng.sample(avail_days, n_take))
        print(f'\n=== {yr} === ({len(avail_days)} days, sample {n_take})')
        rows = []
        for i, d in enumerate(sampled, 1):
            if d not in by_date:
                continue
            df1 = by_date[d]
            day_rows = ydf[ydf['Date'] == d]
            ma_f = day_rows['MA_fast_prev'].iloc[0] if 'MA_fast_prev' in day_rows.columns else None
            ma_s = day_rows['MA_slow_prev'].iloc[0] if 'MA_slow_prev' in day_rows.columns else None
            regime_day = str(day_rows['Regime'].iloc[0])
            outpath = year_dir / f'{d}.png'
            try:
                res = draw_chart(d, df1, day_rows, outpath, TICK, MULT, ma_f, ma_s, regime_day)
                if res is None:
                    continue
                pattern, total_pl, rv, sym = res
                day_net = float(day_rows['Net_$'].sum())
                rows.append({
                    'date': d,
                    'symbol': sym,
                    'range': round(rv, 2),
                    'pattern': pattern,
                    'pl_pts': round(total_pl, 2),
                    'pl_dollar': round(day_net, 0),
                    'regime_day': regime_day,
                })
                if i % 25 == 0:
                    print(f'  ... {i}/{n_take}')
            except Exception as e:
                print(f'  {d}: {e}')
        write_year_index(yr, year_dir, rows, all_year_stats[yr], MULT)
        years_data[yr] = rows
        print(f'  wrote {len(rows)} charts')

    write_summary(OUT_BASE, years_data, all_year_stats)
    print(f'\nDone. SUMMARY -> {OUT_BASE / "SUMMARY.md"}')


if __name__ == '__main__':
    main()
