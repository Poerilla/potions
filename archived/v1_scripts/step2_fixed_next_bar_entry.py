#!/usr/bin/env python3
"""
FIXED 15-min ORB backtest: the confirmation bar is NOT the entry bar.

Change vs step2_range_trades.py:
  - When a bar closes > range_high (or < range_low), we ENTER WAIT_FILL state.
  - We do NOT fill on the confirmation bar, even if its low touched range_high.
  - Entry only occurs on a SUBSEQUENT bar, where either:
      * Long: low <= range_high (limit fills on pullback)
      * Short: high >= range_low
  - All other rules unchanged.
"""
from datetime import time
import pandas as pd

INPUT_FILE = '/home/tester/hsm/potions/mnq/mnq_5min_rth.csv'
OUTPUT_FILE = '/home/tester/hsm/potions/mnq/mnq_orb_results_fixed.csv'
RANGE_END = time(9, 45)

WAIT_BREAKOUT = 0
WAIT_FILL = 1
IN_TRADE = 2
MAX_TRADES_PER_DAY = 2


def simulate_day(range_high, range_low, range_val, trade_bars):
    phase = WAIT_BREAKOUT
    direction = None
    entry = target = stop = None
    max_dd = 0.0
    trades = []

    for _, bar in trade_bars.iterrows():
        if len(trades) >= MAX_TRADES_PER_DAY and phase != IN_TRADE:
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
                continue

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

        if phase == WAIT_BREAKOUT and len(trades) < MAX_TRADES_PER_DAY:
            if c > range_high:
                direction = 'Long'
                phase = WAIT_FILL          # FIX: always wait for a later bar
            elif c < range_low:
                direction = 'Short'
                phase = WAIT_FILL          # FIX: always wait for a later bar

    if phase == IN_TRADE:
        eod_price = trade_bars.iloc[-1]['close']
        trades.append((direction, entry, eod_price, round(max_dd * 100, 2), 'EOD-Close'))
    return trades


def main():
    print(f"Reading {INPUT_FILE} ...")
    df = pd.read_csv(INPUT_FILE)
    df['ts_event'] = pd.to_datetime(df['ts_event'], utc=True).dt.tz_convert('America/New_York')
    df['date'] = df['ts_event'].dt.date
    df['bar_time'] = df['ts_event'].dt.time
    days = sorted(df['date'].unique())
    print(f"  {len(days)} trading days")

    results = []
    for day in days:
        g = df[df['date'] == day].sort_values('ts_event')
        rb = g[g['bar_time'] < RANGE_END]
        if rb.empty:
            continue
        rh = rb['high'].max(); rl = rb['low'].min(); rv = rh - rl
        sym = rb.iloc[0]['symbol']
        if rv <= 0: continue
        tb = g[g['bar_time'] >= RANGE_END]
        if tb.empty: continue

        day_trades = simulate_day(rh, rl, rv, tb)
        if not day_trades:
            results.append({'Date': day, 'Day_of_Week': day.strftime('%A'),
                'Symbol': sym, 'Range_High': rh, 'Range_Low': rl, 'Range': rv,
                'Trade_Direction': 'No-Op', 'Entry_Price': None, 'Exit_Price': None,
                'Trade_PL': 0, 'Drawdown_Pct': 0, 'Result': 'No-Op'})
            continue
        for d, entry, exit_p, dd, res in day_trades:
            pl = (exit_p - entry) if d == 'Long' else (entry - exit_p)
            results.append({'Date': day, 'Day_of_Week': day.strftime('%A'),
                'Symbol': sym, 'Range_High': rh, 'Range_Low': rl, 'Range': rv,
                'Trade_Direction': d, 'Entry_Price': entry, 'Exit_Price': exit_p,
                'Trade_PL': round(pl, 6), 'Drawdown_Pct': dd, 'Result': res})

    out = pd.DataFrame(results)
    out['Cumulative_PL'] = out['Trade_PL'].cumsum().round(6)
    out.to_csv(OUTPUT_FILE, index=False)

    traded = out[out['Result'].isin(['Win','Loss','EOD-Close'])].copy()
    def tag(r):
        if r['Result'] in ('Win','Loss'): return r['Result']
        return 'Win' if r['Trade_PL'] > 0 else 'Loss'
    traded['Tag'] = traded.apply(tag, axis=1)
    wins = (traded['Tag']=='Win').sum()
    losses = (traded['Tag']=='Loss').sum()
    eod = (traded['Result']=='EOD-Close').sum()
    noop_days = len(out[out['Result']=='No-Op'])
    print(f"\n=== FIXED backtest results ===")
    print(f"  Trades:  {len(traded)}")
    print(f"  Wins:    {wins} ({wins/max(len(traded),1)*100:.1f}%)")
    print(f"  Losses:  {losses} ({losses/max(len(traded),1)*100:.1f}%)")
    print(f"  EOD:     {eod}")
    print(f"  Total P/L: {traded['Trade_PL'].sum():.2f} pts")
    print(f"  Saved -> {OUTPUT_FILE}")

if __name__ == '__main__':
    main()
