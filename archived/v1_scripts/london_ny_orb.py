#!/usr/bin/env python3
"""
London + NY Session ORB Backtest

Sessions (Eastern time):
  - LONDON: Opening range 2:00-2:15 AM, trade 2:15 AM - 11:00 AM
  - NY:      Opening range 9:30-9:45 AM, trade 9:45 AM - 4:00 PM

Same ORB rules as 15-min RTH: close-based breakout, limit fill, 1R target,
strict stop, max 2 trades per session per day.

Reads 1-minute CSV, produces 5-min bars for extended session (2 AM - 4 PM),
runs ORB on each session separately.
"""
import argparse
import os
import time as _time
from datetime import time

import pandas as pd
import pytz

NY_TZ = pytz.timezone('America/New_York')

# London: 2:00-2:15 range, trade until 11:00
LONDON_RANGE_START = time(2, 0)
LONDON_RANGE_END = time(2, 15)
LONDON_TRADE_END = time(11, 0)

# NY: 9:30-9:45 range, trade until 16:00
NY_RANGE_START = time(9, 30)
NY_RANGE_END = time(9, 45)
NY_TRADE_END = time(16, 0)

# Extended session for data: 2:00 AM - 4:00 PM (covers both)
EXTENDED_START = time(2, 0)
EXTENDED_END = time(16, 0)

WAIT_BREAKOUT = 0
WAIT_FILL = 1
IN_TRADE = 2
MAX_TRADES_PER_SESSION = 2


def simulate_session(range_high, range_low, range_val, trade_bars):
    """Same logic as step2_range_trades.simulate_day."""
    phase = WAIT_BREAKOUT
    direction = None
    entry = target = stop = None
    max_dd = 0.0
    trades = []

    for _, bar in trade_bars.iterrows():
        if len(trades) >= MAX_TRADES_PER_SESSION and phase != IN_TRADE:
            break
        h, l, c = bar['high'], bar['low'], bar['close']

        if phase == WAIT_FILL:
            filled = False
            if direction == 'Long' and l <= range_high:
                entry, target, stop = range_high, range_high + range_val, range_low
                filled = True
            elif direction == 'Short' and h >= range_low:
                entry, target, stop = range_low, range_low - range_val, range_high
                filled = True
            if filled:
                phase = IN_TRADE
                max_dd = 0.0
            else:
                if direction == 'Long' and c < range_low:
                    direction = 'Short'
                elif direction == 'Short' and c > range_high:
                    direction = 'Long'

        if phase == IN_TRADE:
            if direction == 'Long':
                if l < stop:
                    trades.append(('Long', entry, stop, 100.0, 'Loss'))
                    phase, direction = WAIT_BREAKOUT, None
                elif h >= target:
                    max_dd = max(max_dd, max(0.0, (entry - l) / range_val))
                    trades.append(('Long', entry, target, round(max_dd * 100, 2), 'Win'))
                    phase, direction = WAIT_BREAKOUT, None
                else:
                    max_dd = max(max_dd, max(0.0, (entry - l) / range_val))
                    continue
            else:
                if h > stop:
                    trades.append(('Short', entry, stop, 100.0, 'Loss'))
                    phase, direction = WAIT_BREAKOUT, None
                elif l <= target:
                    max_dd = max(max_dd, max(0.0, (h - entry) / range_val))
                    trades.append(('Short', entry, target, round(max_dd * 100, 2), 'Win'))
                    phase, direction = WAIT_BREAKOUT, None
                else:
                    max_dd = max(max_dd, max(0.0, (h - entry) / range_val))
                    continue

        if phase == WAIT_BREAKOUT and len(trades) < MAX_TRADES_PER_SESSION:
            if c > range_high:
                direction = 'Long'
                if l <= range_high:
                    entry, target, stop = range_high, range_high + range_val, range_low
                    phase = IN_TRADE
                    max_dd = 0.0
                    continue
                else:
                    phase = WAIT_FILL
            elif c < range_low:
                direction = 'Short'
                if h >= range_low:
                    entry, target, stop = range_low, range_low - range_val, range_high
                    phase = IN_TRADE
                    max_dd = 0.0
                    continue
                else:
                    phase = WAIT_FILL

    if phase == IN_TRADE:
        eod_price = trade_bars.iloc[-1]['close']
        trades.append((direction, entry, eod_price, round(max_dd * 100, 2), 'EOD-Close'))

    return trades


def load_and_resample(input_path):
    """Load 1m CSV, filter to extended session, resample to 5-min."""
    t0 = _time.time()
    print(f"Reading {input_path} ...")
    df = pd.read_csv(input_path, usecols=['ts_event', 'open', 'high', 'low', 'close', 'volume', 'symbol'])
    df = df[~df['symbol'].str.contains('-', na=False)].copy()

    df['ts_event'] = pd.to_datetime(df['ts_event'], utc=True).dt.tz_convert(NY_TZ)
    df['date'] = df['ts_event'].dt.date
    df['bar_time'] = df['ts_event'].dt.time

    daily_vol = df.groupby(['date', 'symbol'])['volume'].sum()
    front_month = daily_vol.groupby(level='date').idxmax().apply(lambda x: x[1])
    df['fm'] = df['date'].map(front_month.to_dict())
    df = df[df['symbol'] == df['fm']].copy()
    df.drop(columns=['fm'], inplace=True)

    bt = df['bar_time']
    df = df[(bt >= EXTENDED_START) & (bt < EXTENDED_END)].copy()

    df.set_index('ts_event', inplace=True)
    resampled = df.resample('5T').agg({
        'open': 'first', 'high': 'max', 'low': 'min',
        'close': 'last', 'volume': 'sum', 'symbol': 'first',
    }).dropna(subset=['open'])
    resampled.index.name = 'ts_event'
    resampled.reset_index(inplace=True)

    bt = resampled['ts_event'].dt.time
    resampled = resampled[(bt >= EXTENDED_START) & (bt < EXTENDED_END)].copy()
    resampled['volume'] = resampled['volume'].astype(int)
    resampled['bar_time'] = resampled['ts_event'].dt.time
    resampled['date'] = resampled['ts_event'].dt.date

    print(f"  {len(resampled):,} five-minute bars in {_time.time() - t0:.1f}s")
    return resampled


def run_session_orb(df, session_name, range_start, range_end, trade_end):
    """Run ORB for one session. range_start/range_end define opening range; trade_end is session close."""
    df['date'] = df['ts_event'].dt.date
    df['bar_time'] = df['ts_event'].dt.time

    days = sorted(df['date'].unique())
    results = []

    for day in days:
        day_df = df[df['date'] == day].sort_values('ts_event')
        range_bars = day_df[(day_df['bar_time'] >= range_start) & (day_df['bar_time'] < range_end)]
        if range_bars.empty or len(range_bars) < 3:
            results.append({
                'Date': day, 'Day_of_Week': day.strftime('%A'), 'Session': session_name,
                'Symbol': '', 'Range_High': None, 'Range_Low': None, 'Range': None,
                'Trade_Direction': 'No-Op', 'Entry_Price': None, 'Exit_Price': None,
                'Trade_PL': 0, 'Drawdown_Pct': 0, 'Result': 'No-Op',
            })
            continue

        rh = range_bars['high'].max()
        rl = range_bars['low'].min()
        rv = rh - rl
        sym = range_bars.iloc[0]['symbol']

        if rv <= 0:
            results.append({
                'Date': day, 'Day_of_Week': day.strftime('%A'), 'Session': session_name,
                'Symbol': sym, 'Range_High': rh, 'Range_Low': rl, 'Range': 0,
                'Trade_Direction': 'No-Op', 'Entry_Price': None, 'Exit_Price': None,
                'Trade_PL': 0, 'Drawdown_Pct': 0, 'Result': 'No-Op',
            })
            continue

        trade_bars = day_df[(day_df['bar_time'] >= range_end) & (day_df['bar_time'] < trade_end)]
        if trade_bars.empty:
            results.append({
                'Date': day, 'Day_of_Week': day.strftime('%A'), 'Session': session_name,
                'Symbol': sym, 'Range_High': rh, 'Range_Low': rl, 'Range': rv,
                'Trade_Direction': 'No-Op', 'Entry_Price': None, 'Exit_Price': None,
                'Trade_PL': 0, 'Drawdown_Pct': 0, 'Result': 'No-Op',
            })
            continue

        day_trades = simulate_session(rh, rl, rv, trade_bars)
        if not day_trades:
            results.append({
                'Date': day, 'Day_of_Week': day.strftime('%A'), 'Session': session_name,
                'Symbol': sym, 'Range_High': rh, 'Range_Low': rl, 'Range': rv,
                'Trade_Direction': 'No-Op', 'Entry_Price': None, 'Exit_Price': None,
                'Trade_PL': 0, 'Drawdown_Pct': 0, 'Result': 'No-Op',
            })
            continue

        for d, entry, exit_p, dd, res in day_trades:
            pl = (exit_p - entry) if d == 'Long' else (entry - exit_p) if entry and exit_p else 0
            results.append({
                'Date': day, 'Day_of_Week': day.strftime('%A'), 'Session': session_name,
                'Symbol': sym, 'Range_High': rh, 'Range_Low': rl, 'Range': rv,
                'Trade_Direction': d, 'Entry_Price': entry, 'Exit_Price': exit_p,
                'Trade_PL': round(pl, 6), 'Drawdown_Pct': dd, 'Result': res,
            })

    return pd.DataFrame(results)


def main():
    parser = argparse.ArgumentParser(description='London + NY Session ORB Backtest')
    _base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    parser.add_argument('input', nargs='?',
        default=os.path.join(_base, 'mnq', 'raw', 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'),
        help='Path to 1-minute OHLCV CSV')
    parser.add_argument('-o', '--output-dir', default=None,
        help='Output directory (default: combined_orb folder)')
    args = parser.parse_args()

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = args.output_dir or base

    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        return 1

    t0 = _time.time()
    df = load_and_resample(args.input)

    print("\n--- London Session ORB (2:00-2:15 range, trade until 11:00) ---")
    london = run_session_orb(
        df.copy(),
        'London',
        LONDON_RANGE_START,
        LONDON_RANGE_END,
        LONDON_TRADE_END,
    )
    london['Cumulative_PL'] = london['Trade_PL'].cumsum().round(6)
    london_path = os.path.join(out_dir, 'london_orb_results.csv')
    london.to_csv(london_path, index=False)

    l_trades = london[london['Result'].isin(['Win', 'Loss', 'EOD-Close'])]
    l_wins = len(l_trades[l_trades['Result'] == 'Win']) + len(l_trades[(l_trades['Result'] == 'EOD-Close') & (l_trades['Trade_PL'] > 0)])
    l_losses = len(l_trades[l_trades['Result'] == 'Loss']) + len(l_trades[(l_trades['Result'] == 'EOD-Close') & (l_trades['Trade_PL'] <= 0)])
    print(f"  Trades: {len(l_trades)}, Wins: {l_wins}, Losses: {l_losses}")
    print(f"  Final Cum. P/L: {london['Cumulative_PL'].iloc[-1]:.2f} pts")
    print(f"  Saved {london_path}")

    print("\n--- NY Session ORB (9:30-9:45 range, trade until 4:00) ---")
    ny = run_session_orb(
        df.copy(),
        'NY',
        NY_RANGE_START,
        NY_RANGE_END,
        NY_TRADE_END,
    )
    ny['Cumulative_PL'] = ny['Trade_PL'].cumsum().round(6)
    ny_path = os.path.join(out_dir, 'ny_orb_results.csv')
    ny.to_csv(ny_path, index=False)

    n_trades = ny[ny['Result'].isin(['Win', 'Loss', 'EOD-Close'])]
    n_wins = len(n_trades[n_trades['Result'] == 'Win']) + len(n_trades[(n_trades['Result'] == 'EOD-Close') & (n_trades['Trade_PL'] > 0)])
    n_losses = len(n_trades[n_trades['Result'] == 'Loss']) + len(n_trades[(n_trades['Result'] == 'EOD-Close') & (n_trades['Trade_PL'] <= 0)])
    print(f"  Trades: {len(n_trades)}, Wins: {n_wins}, Losses: {n_losses}")
    print(f"  Final Cum. P/L: {ny['Cumulative_PL'].iloc[-1]:.2f} pts")
    print(f"  Saved {ny_path}")

    combined = pd.concat([london, ny], ignore_index=True)
    combined = combined.sort_values(['Date', 'Session'])
    combined_path = os.path.join(out_dir, 'combined_orb_results.csv')
    combined.to_csv(combined_path, index=False)
    print(f"\nCombined: {combined_path}")

    print(f"\nDone in {_time.time() - t0:.1f}s")
    return 0


if __name__ == '__main__':
    exit(main())
