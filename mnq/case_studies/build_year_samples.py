#!/usr/bin/env python3
"""
Build per-year case studies: sample N trading days from each year and
generate annotated 5-min candlestick charts. Outputs to:
  case_studies/by_year/<year>/<date>.png
  case_studies/by_year/<year>/INDEX.md   (year-specific summary + table)
  case_studies/by_year/SUMMARY.md         (cross-year comparison)
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
OUT_BASE = Path('/home/tester/hsm/potions/case_studies/by_year')
TICK     = 0.25


def load_dbn_once():
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
        return None
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

    pattern = '+'.join([f"{t['direction'][0]}{t['result'][0]}" for t in trades]) if trades else 'NoTrade'
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
    ax.axhline(rh + TICK, color='#76FF03', linestyle=':', linewidth=0.8, alpha=0.7, zorder=2)
    ax.axhline(rl - TICK, color='#FF5252', linestyle=':', linewidth=0.8, alpha=0.7, zorder=2)

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

    title = f"{date_obj}  ·  {sym}  ·  Range {rv:.1f}  ·  {pattern}  ·  {total_pl:+.1f}pt (${total_pl*2:+.0f}/MNQ)"
    ax.set_title(title, color='white', fontsize=10, fontweight='bold', pad=8, loc='left')
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
    if p in ('LW+LW', 'SW+SW', 'LW+SW', 'SW+LW'): return 'Double Win'
    if p in ('LL+SL', 'SL+LL'):                   return 'Double Loss'
    if p in ('LL+SW', 'SL+LW'):                   return 'Loss-then-Win'
    if p in ('LW+SL', 'SW+LL'):                   return 'Win-then-Loss'
    if 'E' in p:                                   return 'EOD-Close'
    if p in ('LW', 'SW'):                          return 'Single Win'
    if p in ('LL', 'SL'):                          return 'Single Loss'
    return 'Other'


def write_year_index(year, year_dir, rows, full_year_csv_stats):
    idx = year_dir / 'INDEX.md'
    cats = Counter(categorize(r['pattern']) for r in rows)
    sample_total = sum(r['pl_dollar'] for r in rows)
    sample_wins = sum(1 for r in rows if r['pl_dollar'] > 0)

    with open(idx, 'w') as f:
        f.write(f"# {year} — MNQ NY Case Studies (sample of {len(rows)} days)\n\n")
        f.write(f"## Full year (from CSV, all days)\n\n")
        f.write(f"| Metric | Value |\n|---|---|\n")
        f.write(f"| Trading days | {full_year_csv_stats['days']} |\n")
        f.write(f"| Total trades | {full_year_csv_stats['trades']} |\n")
        f.write(f"| Win rate | {full_year_csv_stats['win_pct']:.1f}% |\n")
        f.write(f"| Total P/L (pts) | {full_year_csv_stats['pts']:+.0f} |\n")
        f.write(f"| Total Net $/MNQ | ${full_year_csv_stats['net_dollar']:+,.0f} |\n")
        f.write(f"| Best day | ${full_year_csv_stats['best_day']:+,.0f} on {full_year_csv_stats['best_date']} |\n")
        f.write(f"| Worst day | ${full_year_csv_stats['worst_day']:+,.0f} on {full_year_csv_stats['worst_date']} |\n\n")

        f.write(f"## Sample summary ({len(rows)} days)\n\n")
        f.write(f"- Sample net: **${sample_total:+,.0f}/MNQ**, {sample_wins} green days ({sample_wins/len(rows)*100:.1f}%)\n\n")
        f.write(f"### Sample pattern distribution\n\n| Category | Count | % |\n|---|---|---|\n")
        for k, v in cats.most_common():
            f.write(f"| {k} | {v} | {v / len(rows) * 100:.1f}% |\n")
        f.write(f"\n## All sampled days (sortable)\n\n")
        f.write(f"| Date | Symbol | Range | Pattern | Net pts | Net $/MNQ | Chart |\n")
        f.write(f"|---|---|---|---|---|---|---|\n")
        for r in sorted(rows, key=lambda x: x['date']):
            f.write(f"| {r['date']} | {r['symbol']} | {r['range']} | {r['pattern']} | "
                    f"{r['pl_pts']:+.1f} | ${r['pl_dollar']:+,.0f} | "
                    f"[{r['date']}.png]({r['date']}.png) |\n")


def write_summary(years_data, all_year_stats):
    summary = OUT_BASE / 'SUMMARY.md'
    with open(summary, 'w') as f:
        f.write("# Per-Year MNQ NY ORB Case Studies (v2b)\n\n")
        f.write("Per-year case-study folders, each with up to 100 sampled trading days.\n\n")
        f.write("## Year-over-year performance (full CSV — all trading days)\n\n")
        f.write("| Year | Days | Trades | Win % | Net $/MNQ | Best day | Worst day |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for yr in sorted(all_year_stats):
            s = all_year_stats[yr]
            f.write(f"| **{yr}** | {s['days']} | {s['trades']} | {s['win_pct']:.1f}% | "
                    f"${s['net_dollar']:+,.0f} | ${s['best_day']:+,.0f} ({s['best_date']}) | "
                    f"${s['worst_day']:+,.0f} ({s['worst_date']}) |\n")
        f.write("\n## Sample folders\n\n")
        for yr in sorted(years_data):
            n = len(years_data[yr])
            f.write(f"- [`{yr}/`]({yr}/INDEX.md) — {n} day samples\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-n', type=int, default=100, help='Days per year')
    ap.add_argument('--seed', type=int, default=42)
    args = ap.parse_args()

    OUT_BASE.mkdir(parents=True, exist_ok=True)

    csv = pd.read_csv(CSV_FILE)
    csv['Date'] = pd.to_datetime(csv['Date']).dt.date
    csv['Year'] = pd.DatetimeIndex(csv['Date']).year
    print(f"Loaded {len(csv):,} v2b CSV rows across years {csv['Year'].min()}-{csv['Year'].max()}")

    by_date = load_dbn_once()

    # Per-year stats from full CSV
    all_year_stats = {}
    for yr in sorted(csv['Year'].unique()):
        ydf = csv[csv['Year'] == yr]
        daily = ydf.groupby('Date')['Trade_PL'].sum()
        net_daily = daily * 2 - 1.50  # rough proxy; actual fee-aware in CSV but close enough for summary
        all_year_stats[yr] = {
            'days': ydf['Date'].nunique(),
            'trades': len(ydf),
            'win_pct': (ydf['Trade_PL'] > 0).mean() * 100,
            'pts': ydf['Trade_PL'].sum(),
            'net_dollar': (ydf['Trade_PL'] * 2 - 1.50).sum(),
            'best_day': (daily * 2).max(),
            'best_date': (daily * 2).idxmax(),
            'worst_day': (daily * 2).min(),
            'worst_date': (daily * 2).idxmin(),
        }

    rng = random.Random(args.seed)
    years_data = {}

    for yr in sorted(csv['Year'].unique()):
        year_dir = OUT_BASE / str(yr)
        year_dir.mkdir(parents=True, exist_ok=True)
        ydf = csv[csv['Year'] == yr]
        avail_days = sorted(ydf['Date'].unique())
        n_take = min(args.n, len(avail_days))
        sampled = sorted(rng.sample(avail_days, n_take))
        print(f"\n=== {yr} === ({len(avail_days)} days available, sampling {n_take})")

        rows = []
        for i, d in enumerate(sampled, 1):
            if d not in by_date:
                continue
            df1 = by_date[d]
            csv_rows = csv[csv['Date'] == d]
            outpath = year_dir / f'{d}.png'
            try:
                res = draw_chart(d, df1, csv_rows, outpath)
                if res is None:
                    continue
                pattern, total_pl, rv, sym = res
                rows.append({'date': d, 'symbol': sym, 'range': round(rv, 2),
                             'pattern': pattern, 'pl_pts': round(total_pl, 2),
                             'pl_dollar': round(total_pl * 2, 0)})
                if i % 25 == 0:
                    print(f"  ... {i}/{n_take} done")
            except Exception as e:
                print(f"  {d}: error - {e}")

        write_year_index(yr, year_dir, rows, all_year_stats[yr])
        years_data[yr] = rows
        print(f"  {yr}: wrote {len(rows)} charts + INDEX.md")

    write_summary(years_data, all_year_stats)
    print(f"\nWrote SUMMARY.md at {OUT_BASE}")


if __name__ == '__main__':
    main()
