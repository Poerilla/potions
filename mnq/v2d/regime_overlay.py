#!/usr/bin/env python3
"""
Daily MNQ chart with v2b/v2d regime overlay + **v2e strict-clean** (experimental).

Panels:
  Top: MNQ daily + MAs + shaded v2d regime + BEST/WORST v2b 60d windows.
  Rolling 60-day $: v2b (1 MNQ), v2d (1 MNQ), v2e strict-clean (**daily $ ÷ contracts** → 1-MNQ-ish scale).

Output: mnq/v2d/regime_chart.png
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
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


NY = pytz.timezone('America/New_York')
DAILY_DBN = '/home/tester/hsm/potions/mnq/raw/glbx-mdp3-20100606-20260308.ohlcv-1d.dbn.zst'
V2B_CSV   = '/home/tester/hsm/potions/mnq/mnq_orb_results_stops.csv'
V2D_CSV   = '/home/tester/hsm/potions/mnq/v2d/mnq_orb_results_v2d.csv'
# Strict-clean track (5 MNQ in log); plotting divides by Contracts for apples-to-ish 1-contract $/day scale
V2E_CSV = Path('/home/tester/hsm/potions/mnq/v2e/data/mnq_v2e_strict_clean_trades.csv')
OUT_PATH  = Path('/home/tester/hsm/potions/mnq/v2d/regime_chart.png')

ROLL_DAYS = 60   # 60-day rolling window for regime detection


def load_daily_mnq():
    """Load daily MNQ, pick front-month per day by volume."""
    store = db.DBNStore.from_file(DAILY_DBN)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')].copy()
    df['date'] = pd.to_datetime(df['ts_event']).dt.date
    fm = df.loc[df.groupby('date')['volume'].idxmax()]
    fm = fm.set_index('date').sort_index()
    return fm[['open', 'high', 'low', 'close', 'volume', 'symbol']]


def load_strategy_daily(csv):
    df = pd.read_csv(csv)
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    return df.groupby('Date')['Net_$'].sum()


def load_v2e_daily_normalized(path: Path):
    """
    Per-calendar-day sum of (Net_$ / Contracts) so each leg is in **~1-MNQ $** scale before
    combining (same sizing used for all legs in the log → sum of per-leg 1-lot equivalents).
    """
    if not Path(path).is_file():
        print(f'  (WARN: missing {path}; v2e panel will be zeros)', flush=True)
        return pd.Series(dtype=float)

    df = pd.read_csv(path)
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    df['net_1ct'] = df['Net_$'].astype(float) / df['Contracts'].astype(float).clip(lower=1)
    return df.groupby('Date')['net_1ct'].sum().rename('v2e')


def main():
    print("Loading daily MNQ ...")
    daily = load_daily_mnq()
    print(f"  {len(daily)} daily bars ({daily.index.min()} -> {daily.index.max()})")

    v2b = load_strategy_daily(V2B_CSV).rename('v2b')
    v2d = load_strategy_daily(V2D_CSV).rename('v2d')
    v2e_norm = load_v2e_daily_normalized(V2E_CSV)

    vx = v2e_norm.reindex(v2b.index, fill_value=0).rename('v2e')
    perf = pd.concat({'v2b': v2b, 'v2d': v2d, 'v2e': vx}, axis=1).fillna(0)
    print(f"  Strategy days: {len(perf)} ({perf.index.min()} -> {perf.index.max()})")

    # Align price to strategy date range
    aligned = daily.reindex(perf.index, method='nearest')

    # Rolling 60-day cumulative P/L
    perf['v2b_roll'] = perf['v2b'].rolling(ROLL_DAYS).sum()
    perf['v2d_roll'] = perf['v2d'].rolling(ROLL_DAYS).sum()
    perf['v2e_roll'] = perf['v2e'].rolling(ROLL_DAYS).sum()

    # Find best/worst window starts (the start date is roll_days before the peak/trough)
    best_idx  = perf['v2b_roll'].idxmax()
    worst_idx = perf['v2b_roll'].idxmin()
    best_start  = perf.index[max(0, perf.index.get_loc(best_idx)  - ROLL_DAYS + 1)]
    worst_start = perf.index[max(0, perf.index.get_loc(worst_idx) - ROLL_DAYS + 1)]

    best_v2b   = perf.loc[best_start:best_idx, 'v2b'].sum()
    best_v2d   = perf.loc[best_start:best_idx, 'v2d'].sum()
    worst_v2b  = perf.loc[worst_start:worst_idx, 'v2b'].sum()
    worst_v2d  = perf.loc[worst_start:worst_idx, 'v2d'].sum()

    print(f"\n=== BEST  60-day v2b window: {best_start} -> {best_idx} ===")
    print(f"  v2b: ${best_v2b:>+9,.0f}    v2d: ${best_v2d:>+9,.0f}    "
          f"Combined: ${best_v2b+best_v2d:>+9,.0f}")
    print(f"  MNQ price move: {daily.loc[best_start,'close']:.0f} -> {daily.loc[best_idx,'close']:.0f}  "
          f"({(daily.loc[best_idx,'close']/daily.loc[best_start,'close']-1)*100:+.1f}%)")
    print(f"\n=== WORST 60-day v2b window: {worst_start} -> {worst_idx} ===")
    print(f"  v2b: ${worst_v2b:>+9,.0f}    v2d: ${worst_v2d:>+9,.0f}    "
          f"Combined: ${worst_v2b+worst_v2d:>+9,.0f}")
    print(f"  MNQ price move: {daily.loc[worst_start,'close']:.0f} -> {daily.loc[worst_idx,'close']:.0f}  "
          f"({(daily.loc[worst_idx,'close']/daily.loc[worst_start,'close']-1)*100:+.1f}%)")

    # Find top 3 best and worst windows (non-overlapping)
    rolling = perf['v2b_roll'].dropna().copy()
    best_windows = []
    worst_windows = []
    while len(best_windows) < 3 and not rolling.empty:
        peak = rolling.idxmax()
        s = perf.index[max(0, perf.index.get_loc(peak) - ROLL_DAYS + 1)]
        best_windows.append((s, peak,
                             perf.loc[s:peak,'v2b'].sum(),
                             perf.loc[s:peak,'v2d'].sum()))
        # Mask out this window so next iteration finds different region
        mask_start = perf.index[max(0, perf.index.get_loc(peak) - ROLL_DAYS)]
        mask_end   = perf.index[min(len(perf)-1, perf.index.get_loc(peak) + ROLL_DAYS)]
        rolling = rolling.drop(rolling.loc[mask_start:mask_end].index, errors='ignore')

    rolling = perf['v2b_roll'].dropna().copy()
    while len(worst_windows) < 3 and not rolling.empty:
        trough = rolling.idxmin()
        s = perf.index[max(0, perf.index.get_loc(trough) - ROLL_DAYS + 1)]
        worst_windows.append((s, trough,
                              perf.loc[s:trough,'v2b'].sum(),
                              perf.loc[s:trough,'v2d'].sum()))
        mask_start = perf.index[max(0, perf.index.get_loc(trough) - ROLL_DAYS)]
        mask_end   = perf.index[min(len(perf)-1, perf.index.get_loc(trough) + ROLL_DAYS)]
        rolling = rolling.drop(rolling.loc[mask_start:mask_end].index, errors='ignore')

    print("\nTop 3 best v2b windows:")
    for i,(s,e,b,d) in enumerate(best_windows,1):
        print(f"  #{i}: {s} -> {e}   v2b ${b:>+8,.0f}  v2d ${d:>+8,.0f}")
    print("\nTop 3 worst v2b windows:")
    for i,(s,e,b,d) in enumerate(worst_windows,1):
        print(f"  #{i}: {s} -> {e}   v2b ${b:>+8,.0f}  v2d ${d:>+8,.0f}")

    # ====== Plot (4 stacked panels: MNQ price + v2b roll + v2d roll + v2e strict-clean roll) ======
    fig, axes = plt.subplots(
        4,
        1,
        figsize=(18, 14),
        sharex=True,
        gridspec_kw={'height_ratios': [3, 1.05, 1.05, 1.05]},
        facecolor='#0D1B2A',
    )
    for ax in axes:
        ax.set_facecolor('#0D1B2A')
        for s in ax.spines.values():
            s.set_color('#3A506B')
        ax.tick_params(colors='#9FB3C8', labelsize=8)
        ax.grid(True, alpha=0.15, color='#9FB3C8')

    # Top panel: MNQ daily candlesticks + 50/150-day moving averages
    ax_p = axes[0]
    import matplotlib.dates as mdates
    import matplotlib.patches as mpatches

    daily_idx_dt = pd.to_datetime(daily.index)
    daily_close = pd.Series(daily['close'].values, index=daily_idx_dt)
    daily_open  = pd.Series(daily['open'].values,  index=daily_idx_dt)
    daily_high  = pd.Series(daily['high'].values,  index=daily_idx_dt)
    daily_low   = pd.Series(daily['low'].values,   index=daily_idx_dt)
    ma50  = daily_close.rolling(50).mean()
    ma150 = daily_close.rolling(150).mean()

    # Shade v2d-regime periods (lightly across the panel) BEFORE candles
    regime_v2b_for_chart = (ma50 > ma150).reindex(daily_close.index).fillna(True)
    in_v2d = ~regime_v2b_for_chart
    grp = (in_v2d != in_v2d.shift()).cumsum()
    for _, period in in_v2d[in_v2d].groupby(grp):
        if len(period) >= 2:
            ax_p.axvspan(period.index[0], period.index[-1],
                         color='#FF9800', alpha=0.07, zorder=1)

    # Daily candlesticks (thin since we're showing many years)
    cw = 0.7  # candle body width in days
    for ts in daily_idx_dt:
        x = mdates.date2num(ts)
        o, h, l, c = daily_open[ts], daily_high[ts], daily_low[ts], daily_close[ts]
        is_up = c >= o
        col = '#26A69A' if is_up else '#EF5350'
        # Wick
        ax_p.vlines(x, l, h, color=col, linewidth=0.4, zorder=3, alpha=0.95)
        # Body (only if non-degenerate)
        body_lo = min(o, c); body_hi = max(o, c)
        ax_p.add_patch(mpatches.Rectangle(
            (x - cw/2, body_lo), cw, max(body_hi - body_lo, (h - l) * 0.02 + 1),
            facecolor=col, edgecolor=col, alpha=0.9, zorder=3))

    # MAs on top of candles
    ax_p.plot(ma50.index,  ma50.values,  color='#26C6DA', linewidth=1.6,
              alpha=0.95, zorder=5, label='50-day MA (v2b regime indicator)')
    ax_p.plot(ma150.index, ma150.values, color='#FF9800', linewidth=1.8,
              alpha=0.95, zorder=5, label='150-day MA (v2d regime indicator)')

    ax_p.legend(loc='upper left', framealpha=0.85, facecolor='#0D1B2A',
                edgecolor='#3A506B', labelcolor='#E0E0E0', fontsize=9)
    px = daily_close.reindex(pd.to_datetime(aligned.index))

    # Shade best/worst windows
    for i, (s, e, b, d) in enumerate(best_windows):
        c = '#76FF03'
        a = 0.20 if i == 0 else 0.10
        ax_p.axvspan(pd.Timestamp(s), pd.Timestamp(e), color=c, alpha=a, zorder=2)
        if i == 0:
            mid = pd.Timestamp(s) + (pd.Timestamp(e) - pd.Timestamp(s)) / 2
            ax_p.annotate(f"BEST v2b\n+${b:,.0f}\n(v2d: ${d:+,.0f})",
                          xy=(mid, px.max() * 0.95),
                          ha='center', color='#76FF03', fontsize=10, fontweight='bold',
                          bbox=dict(boxstyle='round,pad=0.3', fc='#0D1B2A', ec='#76FF03', alpha=0.9))
    for i, (s, e, b, d) in enumerate(worst_windows):
        c = '#FF1744'
        a = 0.20 if i == 0 else 0.10
        ax_p.axvspan(pd.Timestamp(s), pd.Timestamp(e), color=c, alpha=a, zorder=2)
        if i == 0:
            mid = pd.Timestamp(s) + (pd.Timestamp(e) - pd.Timestamp(s)) / 2
            ax_p.annotate(f"WORST v2b\n${b:+,.0f}\n(v2d: ${d:+,.0f})",
                          xy=(mid, px.min() * 1.05),
                          ha='center', color='#FF1744', fontsize=10, fontweight='bold',
                          bbox=dict(boxstyle='round,pad=0.3', fc='#0D1B2A', ec='#FF1744', alpha=0.9))

    ax_p.set_title(
        "MNQ daily — 50/150 MA cross is the adaptive regime indicator. "
        "Orange shading = 50d ≤ 150d (v2d/fade). Bottom v2e = strict-clean ORB 2 pt SL (daily $ ≈ scaled to 1 MNQ equiv).",
        color='white', fontsize=12, fontweight='bold', pad=10, loc='left')
    ax_p.set_ylabel('MNQ Price', color='#9FB3C8')

    # Middle panel: rolling 60d v2b
    ax_b = axes[1]
    roll_idx = pd.to_datetime(perf.index)
    ax_b.fill_between(roll_idx, 0, perf['v2b_roll'].values,
                       where=perf['v2b_roll'].values >= 0,
                       color='#76FF03', alpha=0.4, interpolate=True)
    ax_b.fill_between(roll_idx, 0, perf['v2b_roll'].values,
                       where=perf['v2b_roll'].values < 0,
                       color='#FF1744', alpha=0.4, interpolate=True)
    ax_b.plot(roll_idx, perf['v2b_roll'].values, color='#E0E0E0', linewidth=0.7)
    ax_b.axhline(0, color='#9FB3C8', linewidth=0.5, alpha=0.7)
    ax_b.set_ylabel(f'v2b rolling {ROLL_DAYS}d $\nat 1 MNQ', color='#9FB3C8')
    ax_b.set_title(f'v2b rolling {ROLL_DAYS}-day P/L (1 MNQ)',
                   color='#26A69A', fontsize=10, fontweight='bold', pad=4, loc='left')

    # rolling 60d v2d
    ax_d = axes[2]
    ax_d.fill_between(roll_idx, 0, perf['v2d_roll'].values,
                       where=perf['v2d_roll'].values >= 0,
                       color='#76FF03', alpha=0.4, interpolate=True)
    ax_d.fill_between(roll_idx, 0, perf['v2d_roll'].values,
                       where=perf['v2d_roll'].values < 0,
                       color='#FF1744', alpha=0.4, interpolate=True)
    ax_d.plot(roll_idx, perf['v2d_roll'].values, color='#E0E0E0', linewidth=0.7)
    ax_d.axhline(0, color='#9FB3C8', linewidth=0.5, alpha=0.7)
    ax_d.set_ylabel(f'v2d rolling {ROLL_DAYS}d $\nat 1 MNQ', color='#9FB3C8')
    ax_d.set_title(f'v2d rolling {ROLL_DAYS}-day P/L (1 MNQ) — inverse vs v2b',
                   color='#FF9800', fontsize=10, fontweight='bold', pad=4, loc='left')

    # rolling 60d v2e strict-clean (scaled dollars)
    ax_e = axes[3]
    ax_e.fill_between(roll_idx, 0, perf['v2e_roll'].values,
                      where=perf['v2e_roll'].values >= 0,
                      color='#9575CD', alpha=0.42, interpolate=True)
    ax_e.fill_between(roll_idx, 0, perf['v2e_roll'].values,
                      where=perf['v2e_roll'].values < 0,
                      color='#B39DDB', alpha=0.35, interpolate=True)
    ax_e.plot(roll_idx, perf['v2e_roll'].values, color='#E1BEE7', linewidth=0.65)
    ax_e.axhline(0, color='#9FB3C8', linewidth=0.5, alpha=0.7)
    ax_e.set_ylabel(f'v2e rolling {ROLL_DAYS}d $\n(strict-clean equiv)', color='#CFD8DC')
    ax_e.set_title(
        f'v2e strict-clean rolling {ROLL_DAYS}-day $ (Σ trade Net÷contracts/day; sparse ~1 trade/day)',
        color='#9575CD', fontsize=10, fontweight='bold', pad=4, loc='left')

    ax_e.set_xlabel('Date', color='#9FB3C8')
    ax_e.xaxis.set_major_locator(mdates.YearLocator())
    ax_e.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax_e.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=[4, 7, 10]))

    plt.tight_layout()
    plt.savefig(OUT_PATH, dpi=120, bbox_inches='tight', facecolor='#0D1B2A')
    plt.close()
    print(f"\nSaved {OUT_PATH}")


if __name__ == '__main__':
    main()
