#!/usr/bin/env python3
"""
v2d fade-the-breakout for London + NY session ORB (same sessions as london_ny_orb_stops.py).

Sessions (America/New_York):
  LONDON: range 2:00-2:15, fade/trade until 11:00 (no new setups after 10:55)
  NY:      range 9:30-9:45, fade/trade until 16:00 (no new setups after 15:55)

Outputs mirror v2b naming:
  london_orb_results_v2d.csv, ny_orb_results_v2d.csv (MNQ)
  mym_london_orb_results_v2d.csv, mym_ny_orb_results_v2d.csv (MYM)
"""
import argparse
from datetime import time, timedelta
from pathlib import Path

import databento as db
import pandas as pd
import pytz


NY_TZ = pytz.timezone('America/New_York')

LONDON = {
    'name': 'London',
    'range_start': time(2, 0),
    'range_end': time(2, 15),
    'trade_end': time(11, 0),
    'eod_cutoff': time(10, 55),
}
NY = {
    'name': 'NY',
    'range_start': time(9, 30),
    'range_end': time(9, 45),
    'trade_end': time(16, 0),
    'eod_cutoff': time(15, 55),
}
EXTENDED_START = time(2, 0)
EXTENDED_END = time(16, 0)

PRODUCTS = {
    'MNQ': {
        'tick': 0.25,
        'mult': 2.00,
        'dbn': '/home/tester/hsm/potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst',
        'history_start': pd.Timestamp('2021-03-04').date(),
    },
    'MYM': {
        'tick': 1.00,
        'mult': 0.50,
        'dbn': '/home/tester/hsm/potions/mym/raw/glbx-mdp3-20100606-20260308.ohlcv-1m (mym).dbn.zst',
        'history_start': None,
    },
}

MAX_TRADES_PER_SESSION = 2
FEE_RT = 1.50


def load_one_min(product, extended_window):
    cfg = PRODUCTS[product]
    print(f"[{product}] Loading {cfg['dbn']} ...")
    store = db.DBNStore.from_file(cfg['dbn'])
    df = store.to_df().reset_index()

    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith(product)].copy()
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY_TZ)
    df['date'] = df['ts_event'].dt.date
    df['t'] = df['ts_event'].dt.time

    fm = (df.groupby(['date', 'symbol'])['volume']
            .sum().groupby(level='date').idxmax()
            .apply(lambda x: x[1]).to_dict())
    df = df[df.apply(lambda r: r['symbol'] == fm.get(r['date']), axis=1)]

    if extended_window:
        lo, hi = extended_window
        df = df[(df['t'] >= lo) & (df['t'] < hi)]

    if cfg['history_start'] is not None:
        df = df[df['date'] >= cfg['history_start']]

    df = df.set_index('ts_event').sort_index()
    print(f"  {len(df):,} 1-min bars in extended session")
    return df


def simulate_session_v2d(rh, rl, range_val, session_bars, tick, trade_end, eod_cutoff, slip_ticks=1):
    """Fade logic with session-specific trade_end and eod_cutoff (no new setups after cutoff)."""
    long_break_trig = rh + tick
    short_break_trig = rl - tick
    short_fade_trig = rh - tick
    long_fade_trig = rl + tick
    short_fade_fill = short_fade_trig - slip_ticks * tick
    long_fade_fill = long_fade_trig + slip_ticks * tick

    long_break_done = False
    short_break_done = False
    armed_short_fade = False
    armed_long_fade = False
    traded_long = False
    traded_short = False
    in_trade = False
    direction = None
    entry = target = stop = None
    trades = []
    last_bar = None

    for _, bar in session_bars.iterrows():
        bar_time = bar.name.time()
        if bar_time >= trade_end:
            break
        last_bar = bar
        if not in_trade and bar_time >= eod_cutoff:
            break

        h, l = bar['high'], bar['low']
        breakout_this_bar = False

        if not in_trade:
            if not long_break_done and h >= long_break_trig:
                long_break_done = True
                breakout_this_bar = True
                if not traded_short:
                    armed_short_fade = True
            if not short_break_done and l <= short_break_trig:
                short_break_done = True
                breakout_this_bar = True
                if not traded_long:
                    armed_long_fade = True

        if not in_trade and not breakout_this_bar:
            short_hit = armed_short_fade and l <= short_fade_trig
            long_hit = armed_long_fade and h >= long_fade_trig
            if short_hit and long_hit:
                mid = (rh + rl) / 2
                if bar['open'] >= mid:
                    direction = 'Short'
                    entry = short_fade_fill
                    target = rl
                    stop = rh + range_val
                else:
                    direction = 'Long'
                    entry = long_fade_fill
                    target = rh
                    stop = rl - range_val
                in_trade = True
                armed_short_fade = False
                armed_long_fade = False
            elif short_hit:
                direction = 'Short'
                entry = short_fade_fill
                target = rl
                stop = rh + range_val
                in_trade = True
                armed_short_fade = False
            elif long_hit:
                direction = 'Long'
                entry = long_fade_fill
                target = rh
                stop = rl - range_val
                in_trade = True
                armed_long_fade = False

        if in_trade:
            closed = False
            if direction == 'Long':
                if l < stop:
                    trades.append(('Long', entry, stop, 'Loss'))
                    closed = True
                elif h >= target:
                    trades.append(('Long', entry, target, 'Win'))
                    closed = True
            else:
                if h > stop:
                    trades.append(('Short', entry, stop, 'Loss'))
                    closed = True
                elif l <= target:
                    trades.append(('Short', entry, target, 'Win'))
                    closed = True
            if closed:
                if direction == 'Long':
                    traded_long = True
                    armed_long_fade = False
                else:
                    traded_short = True
                    armed_short_fade = False
                in_trade = False
                direction = None
                if traded_long and traded_short:
                    break
                if len(trades) >= MAX_TRADES_PER_SESSION:
                    break

    if in_trade and last_bar is not None:
        eod = last_bar['close']
        if direction == 'Long':
            res = 'EOD-Win' if eod > entry else 'EOD-Loss'
        else:
            res = 'EOD-Win' if eod < entry else 'EOD-Loss'
        trades.append((direction, entry, eod, res))

    return trades


def run_session(df, session, tick, mult, slip_ticks):
    rs, re_ = session['range_start'], session['range_end']
    te = session['trade_end']
    ec = session['eod_cutoff']
    name = session['name']
    results = []
    for day, day_df in df.groupby(df.index.date):
        day_df = day_df.sort_index()
        day_df = day_df[(day_df.index.time >= rs) & (day_df.index.time < te)]
        range_bars = day_df[(day_df.index.time >= rs) & (day_df.index.time < re_)]
        if len(range_bars) < 3:
            continue
        rh, rl = range_bars['high'].max(), range_bars['low'].min()
        rv = rh - rl
        if rv <= 0:
            continue
        trade_bars = day_df[day_df.index.time >= re_]
        if trade_bars.empty:
            continue

        sym = trade_bars.iloc[0]['symbol']
        day_trades = simulate_session_v2d(rh, rl, rv, trade_bars, tick, te, ec, slip_ticks)
        for d, entry, exit_p, res in day_trades:
            pl = (exit_p - entry) if d == 'Long' else (entry - exit_p)
            results.append({
                'Date': day,
                'Day_of_Week': day.strftime('%A'),
                'Session': name,
                'Symbol': sym,
                'Range_High': rh, 'Range_Low': rl, 'Range': rv,
                'Trade_Direction': d,
                'Entry_Price': entry, 'Exit_Price': exit_p,
                'Trade_PL': round(pl, 6),
                'Net_$': round(pl * mult - FEE_RT, 2),
                'Result': res,
            })
    return pd.DataFrame(results)


def summarize(df, label):
    if df.empty:
        print(f"  {label}: no trades")
        return
    wins = (df['Trade_PL'] > 0).sum()
    print(f"  {label}: {len(df):,} trades, {wins/len(df)*100:.1f}% win, "
          f"{df['Trade_PL'].sum():.0f} pts, ${df['Net_$'].sum():,.0f} net")
    eq = df['Net_$'].cumsum()
    dd = eq - eq.cummax()
    print(f"         Max DD ${dd.min():,.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--product', choices=list(PRODUCTS.keys()), default='MNQ')
    ap.add_argument('--output-dir', default='/home/tester/hsm/potions/combined_orb')
    ap.add_argument('--slip-ticks', type=int, default=1)
    args = ap.parse_args()

    cfg = PRODUCTS[args.product]
    tick, mult = cfg['tick'], cfg['mult']
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    df = load_one_min(args.product, (EXTENDED_START, EXTENDED_END))
    prefix = '' if args.product == 'MNQ' else f'{args.product.lower()}_'

    print("\n--- London v2d ---")
    london = run_session(df, LONDON, tick, mult, args.slip_ticks)
    london['Cumulative_$'] = london['Net_$'].cumsum().round(2)
    summarize(london, f'{args.product} London v2d')
    lp = out / f'{prefix}london_orb_results_v2d.csv'
    london.to_csv(lp, index=False)
    print(f"  Saved {lp}")

    print("\n--- NY v2d ---")
    ny = run_session(df, NY, tick, mult, args.slip_ticks)
    ny['Cumulative_$'] = ny['Net_$'].cumsum().round(2)
    summarize(ny, f'{args.product} NY v2d')
    np_ = out / f'{prefix}ny_orb_results_v2d.csv'
    ny.to_csv(np_, index=False)
    print(f"  Saved {np_}")


if __name__ == '__main__':
    main()
