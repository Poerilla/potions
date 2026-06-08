#!/usr/bin/env python3
"""
v2 London + NY Session ORB Backtest — Pre-Placed OCO Stop Entry

Sessions (all times in America/New_York):
  LONDON: opening range 2:00-2:15, trade until 11:00
  NY:      opening range 9:30-9:45, trade until 16:00

Entry model (v2):
  At the close of the opening range, pre-place a buy-stop at RH + 1 tick
  and a sell-stop at RL - 1 tick as an OCO pair. First trigger fills
  intrabar at RH+1tick+slip (or RL-1tick-slip); other is canceled.
  Target = Entry ± Range; Stop = opposite boundary. Re-arm for up to
  MAX_TRADES_PER_SESSION. Force-close at session trade_end.

Uses 1-minute DBN data for accurate intrabar simulation. Includes
configurable tick slippage on entries.

Outputs (default: combined_orb/):
  london_orb_results_stops.csv
  ny_orb_results_stops.csv
  combined_orb_results_stops.csv
"""
import argparse
import os
from datetime import time
from pathlib import Path

import databento as db
import pandas as pd
import pytz


NY_TZ = pytz.timezone('America/New_York')

# Session windows
LONDON = {'name': 'London', 'range_start': time(2, 0),  'range_end': time(2, 15),  'trade_end': time(11, 0)}
NY     = {'name': 'NY',     'range_start': time(9, 30), 'range_end': time(9, 45),  'trade_end': time(16, 0)}
EXTENDED_START = time(2, 0)
EXTENDED_END   = time(16, 0)

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


def simulate_session(rh, rl, range_val, session_bars, tick, trade_end, slip_ticks=1):
    """v2b bracket-then-reverse logic — see step2_preplaced_stops.py for details."""
    long_trigger  = rh + tick
    short_trigger = rl - tick
    long_entry    = long_trigger + slip_ticks * tick
    short_entry   = short_trigger - slip_ticks * tick

    arm_long = True
    arm_short = True
    phase = 'ARMED'
    direction = None
    entry = target = stop = None
    trades = []
    last_bar = None

    for _, bar in session_bars.iterrows():
        bar_time = bar.name.time()
        if bar_time >= trade_end:
            break
        last_bar = bar
        h, l = bar['high'], bar['low']

        if phase == 'ARMED':
            lh = arm_long  and h >= long_trigger
            sh = arm_short and l <= short_trigger
            if lh and sh:
                mid = (rh + rl) / 2
                if bar['open'] >= mid:
                    direction, entry = 'Long', long_entry
                    target, stop = rh + range_val, rl
                else:
                    direction, entry = 'Short', short_entry
                    target, stop = rl - range_val, rh
                phase = 'IN'
            elif lh:
                direction, entry = 'Long', long_entry
                target, stop = rh + range_val, rl
                phase = 'IN'
            elif sh:
                direction, entry = 'Short', short_entry
                target, stop = rl - range_val, rh
                phase = 'IN'

        if phase == 'IN':
            closed = False
            if direction == 'Long':
                if l < stop:
                    trades.append(('Long', entry, stop, 'Loss')); closed = True
                elif h >= target:
                    trades.append(('Long', entry, target, 'Win')); closed = True
            else:
                if h > stop:
                    trades.append(('Short', entry, stop, 'Loss')); closed = True
                elif l <= target:
                    trades.append(('Short', entry, target, 'Win')); closed = True

            if closed:
                if direction == 'Long':
                    arm_long = False
                else:
                    arm_short = False
                phase, direction = 'ARMED', None
                if not (arm_long or arm_short) or len(trades) >= MAX_TRADES_PER_SESSION:
                    phase = 'DONE'; break

    # EOD close if still open
    if phase == 'IN' and last_bar is not None:
        eod = last_bar['close']
        if direction == 'Long':
            res = 'EOD-Win' if eod > entry else 'EOD-Loss'
        else:
            res = 'EOD-Win' if eod < entry else 'EOD-Loss'
        trades.append((direction, entry, eod, res))

    return trades


def run_session(df, session, tick, mult):
    rs, re_, te = session['range_start'], session['range_end'], session['trade_end']
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
        day_trades = simulate_session(rh, rl, rv, trade_bars, tick, te)
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

    # Product-specific output file naming (avoid overwriting MNQ outputs with MYM)
    prefix = '' if args.product == 'MNQ' else f'{args.product.lower()}_'

    print("\n--- London (2:00-2:15 range, trade until 11:00) ---")
    london = run_session(df, LONDON, tick, mult)
    london['Cumulative_$'] = london['Net_$'].cumsum().round(2)
    summarize(london, f'{args.product} London')
    lp = out / f'{prefix}london_orb_results_stops.csv'
    london.to_csv(lp, index=False)
    print(f"  Saved {lp}")

    print("\n--- NY (9:30-9:45 range, trade until 16:00) ---")
    ny = run_session(df, NY, tick, mult)
    ny['Cumulative_$'] = ny['Net_$'].cumsum().round(2)
    summarize(ny, f'{args.product} NY')
    np_ = out / f'{prefix}ny_orb_results_stops.csv'
    ny.to_csv(np_, index=False)
    print(f"  Saved {np_}")

    combined = pd.concat([london, ny], ignore_index=True).sort_values(['Date', 'Session'])
    combined['Cumulative_$'] = combined['Net_$'].cumsum().round(2)
    cp = out / f'{prefix}combined_orb_results_stops.csv'
    combined.to_csv(cp, index=False)
    print(f"\nCombined -> {cp}  ({len(combined):,} total trades)")

    # Combined portfolio stats
    total_pl = combined['Trade_PL'].sum()
    total_net = combined['Net_$'].sum()
    wins = (combined['Trade_PL'] > 0).sum()
    eq = combined['Net_$'].cumsum()
    dd = eq - eq.cummax()
    print(f"\n=== Combined London + NY (1 {args.product}) ===")
    print(f"  Win rate:  {wins/len(combined)*100:.1f}%")
    print(f"  Total $:   ${total_net:,.0f}")
    print(f"  Max DD:    ${dd.min():,.2f}")


if __name__ == '__main__':
    main()
