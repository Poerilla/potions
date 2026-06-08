#!/usr/bin/env python3
"""
Overlay the user's actual live trade days on the daily MNQ chart.

Shows:
  - Daily candles + 50/150 MAs (same as regime_chart.png)
  - Green dots above closing price = days the user traded with net WIN
  - Red dots above closing price   = days the user traded with net LOSS
  - Empty = days the user did NOT trade (~58% of trading days in the window)

Plus a statistics block comparing what was DIFFERENT about days the
user chose to trade vs days they skipped:
  - Daily range
  - Volume
  - Day of week
  - Bias-aligned distribution
  - Distance from MAs
  - Prior-day return

Output: mnq/v2d/manual_overlay_chart.png
"""
from datetime import time
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd
import pytz

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt


NY = pytz.timezone('America/New_York')
DAILY_DBN = '/home/tester/hsm/potions/mnq/raw/glbx-mdp3-20100606-20260308.ohlcv-1d.dbn.zst'
MANUAL    = '/home/tester/hsm/potions/mnq/raw/Super Trend + ICT - Openning Range.csv'
OUT_PATH  = Path('/home/tester/hsm/potions/mnq/v2d/manual_overlay_chart.png')


def load_daily():
    store = db.DBNStore.from_file(DAILY_DBN)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')].copy()
    df['date'] = pd.to_datetime(df['ts_event']).dt.date
    fm = df.loc[df.groupby('date')['volume'].idxmax()]
    return fm.set_index('date').sort_index()[['open','high','low','close','volume']]


def parse_manual():
    df = pd.read_csv(MANUAL)
    df.columns = [c.strip() for c in df.columns]
    df = df[df['Date'].notna() & (df['Date'].str.match(r'\d{1,2}/\d{1,2}/\d{4}'))].copy()
    df['Date'] = pd.to_datetime(df['Date'], format='%d/%m/%Y').dt.date
    df['IsWin'] = df['W/L'].str.upper() == 'W'
    return df


def main():
    daily = load_daily()
    manual = parse_manual()

    # Restrict daily to manual window
    win_start = manual['Date'].min()
    win_end   = manual['Date'].max()
    print(f"Manual window: {win_start} -> {win_end}")
    print(f"Manual trades: {len(manual)}, "
          f"days traded: {manual['Date'].nunique()}, "
          f"win rate: {manual['IsWin'].mean()*100:.1f}%")

    # Per-day net P/L (for color)
    day_pl = manual.groupby('Date')['P/L'].sum()
    day_win = (day_pl > 0)

    # Window daily for chart (with extra margin for MAs)
    chart_daily = daily[(daily.index >= win_start - pd.Timedelta(days=200).to_pytimedelta())
                       & (daily.index <= win_end + pd.Timedelta(days=10).to_pytimedelta())]
    chart_idx = pd.to_datetime(chart_daily.index)
    close = pd.Series(chart_daily['close'].values, index=chart_idx)
    ma50  = close.rolling(50).mean()
    ma150 = close.rolling(150).mean()

    # Window for trading-day analysis (only days in user's window)
    window_daily = daily[(daily.index >= win_start) & (daily.index <= win_end)].copy()
    print(f"Window daily bars: {len(window_daily)}")
    window_daily['Range'] = window_daily['high'] - window_daily['low']
    window_daily['Body']  = window_daily['close'] - window_daily['open']
    window_daily['DOW']   = pd.to_datetime(window_daily.index).dayofweek

    traded_set = set(manual['Date'])
    window_daily['traded'] = window_daily.index.map(lambda d: d in traded_set)

    print("\n=== Day-selection statistics ===")
    t = window_daily[window_daily['traded']]
    s = window_daily[~window_daily['traded']]
    print(f"Traded days:  {len(t)}  Mean range: {t['Range'].mean():.1f} pts   "
          f"Median: {t['Range'].median():.1f}   Vol: {t['volume'].mean():.0f}")
    print(f"Skipped days: {len(s)}  Mean range: {s['Range'].mean():.1f} pts   "
          f"Median: {s['Range'].median():.1f}   Vol: {s['volume'].mean():.0f}")

    print(f"\nDay-of-week distribution:")
    dow_names = ['Mon','Tue','Wed','Thu','Fri']
    for d in range(5):
        nt = (t['DOW'] == d).sum()
        ns = (s['DOW'] == d).sum()
        total = nt + ns
        print(f"  {dow_names[d]:>3}: traded {nt:>3} of {total:>3} ({nt/max(total,1)*100:>5.1f}%)")

    # Distance from MAs on traded vs skipped
    window_daily['ma50']  = ma50.reindex(pd.to_datetime(window_daily.index)).values
    window_daily['ma150'] = ma150.reindex(pd.to_datetime(window_daily.index)).values
    window_daily['dist_ma50_pct']  = (window_daily['close'] / window_daily['ma50']  - 1) * 100
    window_daily['dist_ma150_pct'] = (window_daily['close'] / window_daily['ma150'] - 1) * 100

    t = window_daily[window_daily['traded']]
    s = window_daily[~window_daily['traded']]
    print(f"\nDistance close from 50d MA (%):")
    print(f"  Traded:  mean {t['dist_ma50_pct'].mean():+.2f}  median {t['dist_ma50_pct'].median():+.2f}")
    print(f"  Skipped: mean {s['dist_ma50_pct'].mean():+.2f}  median {s['dist_ma50_pct'].median():+.2f}")

    # Prior day move
    window_daily['prior_body'] = (window_daily['close'].shift(1) - window_daily['open'].shift(1))
    t = window_daily[window_daily['traded']]
    s = window_daily[~window_daily['traded']]
    print(f"\nPrior day body (close-open, pts):")
    print(f"  Traded:  mean {t['prior_body'].mean():+.2f}  median {t['prior_body'].median():+.2f}")
    print(f"  Skipped: mean {s['prior_body'].mean():+.2f}  median {s['prior_body'].median():+.2f}")

    # Find runs of consecutive trade days vs gaps
    print("\nTraded vs skipped 'runs' (consecutive days):")
    diff_days = pd.Series([(d2-d1).days for d1,d2 in zip(window_daily.index[:-1], window_daily.index[1:])],
                          index=window_daily.index[1:])
    # Just the gap lengths between consecutive trade days
    traded_dates = sorted(traded_set)
    if len(traded_dates) >= 2:
        gaps = [(traded_dates[i+1] - traded_dates[i]).days for i in range(len(traded_dates)-1)]
        gaps_arr = np.array(gaps)
        print(f"  Gaps between consecutive trade days: mean {gaps_arr.mean():.1f}d, "
              f"median {np.median(gaps_arr):.0f}d, max {gaps_arr.max()}d")
        # Histogram
        bins = [1,2,3,4,7,14,30,365]
        labels = ['1d','2d','3d','4-6d','1-2w','2w-1m','1m+']
        hist = np.histogram(gaps_arr, bins=bins)[0]
        for lab, n in zip(labels, hist):
            print(f"    {lab:>6}: {n}")

    # ====== Plot ======
    fig, axes = plt.subplots(2, 1, figsize=(18, 11), sharex=True,
                              gridspec_kw={'height_ratios': [3, 1]},
                              facecolor='#0D1B2A')
    for ax in axes:
        ax.set_facecolor('#0D1B2A')
        for sp in ax.spines.values():
            sp.set_color('#3A506B')
        ax.tick_params(colors='#9FB3C8', labelsize=8)
        ax.grid(True, alpha=0.15, color='#9FB3C8')

    ax_p = axes[0]
    # Shade v2d-regime periods
    in_v2d = (ma50 <= ma150).fillna(False)
    grp = (in_v2d != in_v2d.shift()).cumsum()
    for _, period in in_v2d[in_v2d].groupby(grp):
        if len(period) >= 2:
            ax_p.axvspan(period.index[0], period.index[-1],
                         color='#FF9800', alpha=0.07, zorder=1)

    # Daily candles
    cw = 0.7
    for ts in chart_idx:
        x = mdates.date2num(ts)
        o = chart_daily['open'][ts.date()]
        h = chart_daily['high'][ts.date()]
        l = chart_daily['low'][ts.date()]
        c = chart_daily['close'][ts.date()]
        col = '#26A69A' if c >= o else '#EF5350'
        ax_p.vlines(x, l, h, color=col, linewidth=0.5, zorder=3, alpha=0.95)
        body_lo = min(o, c); body_hi = max(o, c)
        ax_p.add_patch(mpatches.Rectangle(
            (x - cw/2, body_lo), cw, max(body_hi - body_lo, (h - l) * 0.02 + 1),
            facecolor=col, edgecolor=col, alpha=0.9, zorder=3))

    # MAs
    ax_p.plot(ma50.index,  ma50.values,  color='#26C6DA', linewidth=1.6,
              alpha=0.95, zorder=5, label='50-day MA')
    ax_p.plot(ma150.index, ma150.values, color='#FF9800', linewidth=1.8,
              alpha=0.95, zorder=5, label='150-day MA')

    # Mark traded days with green dots above (winners) or red dots below (losers)
    high_max = chart_daily['high'].max()
    low_min  = chart_daily['low'].min()
    span = high_max - low_min
    win_y_offset = high_max + span * 0.02
    loss_y_offset = low_min - span * 0.02

    for d in traded_set:
        if d not in chart_daily.index:
            continue
        is_win = day_win.get(d, True)
        x = mdates.date2num(pd.Timestamp(d))
        if is_win:
            ax_p.scatter([x], [win_y_offset], marker='v', color='#76FF03',
                         s=40, zorder=10, edgecolor='black', linewidth=0.5)
        else:
            ax_p.scatter([x], [loss_y_offset], marker='^', color='#FF1744',
                         s=40, zorder=10, edgecolor='black', linewidth=0.5)

    ax_p.legend(loc='upper left', framealpha=0.85, facecolor='#0D1B2A',
                edgecolor='#3A506B', labelcolor='#E0E0E0', fontsize=9)
    ax_p.set_title("MNQ daily — your live trade days marked. "
                   "Green ▼ = day you traded with net WIN. Red ▲ = day you traded with net LOSS. "
                   f"({len(traded_set)} traded / {len(window_daily)} avail = {len(traded_set)/len(window_daily)*100:.0f}%)",
                   color='white', fontsize=12, fontweight='bold', pad=10, loc='left')
    ax_p.set_ylabel('MNQ Price', color='#9FB3C8')

    # Bottom panel: cumulative manual P/L
    ax_b = axes[1]
    sorted_dates = sorted(day_pl.index)
    cumpl = day_pl.reindex(sorted_dates).cumsum()
    ax_b.fill_between(pd.to_datetime(cumpl.index), 0, cumpl.values,
                       where=cumpl.values >= 0,
                       color='#76FF03', alpha=0.4, interpolate=True)
    ax_b.plot(pd.to_datetime(cumpl.index), cumpl.values, color='#E0E0E0', linewidth=1.0)
    ax_b.axhline(0, color='#9FB3C8', linewidth=0.5)
    ax_b.set_ylabel('Manual cumulative\nP/L (3 MNQ)', color='#9FB3C8')
    ax_b.set_title('Your live cumulative P/L (3 MNQ)',
                   color='#76FF03', fontsize=10, fontweight='bold', pad=4, loc='left')
    ax_b.set_xlabel('Date', color='#9FB3C8')
    ax_b.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax_b.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))

    plt.tight_layout()
    plt.savefig(OUT_PATH, dpi=130, bbox_inches='tight', facecolor='#0D1B2A')
    plt.close()
    print(f"\nSaved {OUT_PATH}")


if __name__ == '__main__':
    main()
