#!/usr/bin/env python3
"""
End-to-end pipeline: NQ 1-minute dbn.zst → 5-min RTH bars → 15-min ORB results.
Reuses the same logic as step1/step2 but reads dbn directly.
"""
import time as _time
from datetime import time

import databento as db
import pandas as pd
import pytz

DBN_FILE = 'glbx-mdp3-20100606-20260308.ohlcv-1m.dbn.zst'
FIVEMIN_FILE = 'nq_5min_rth.csv'
RESULTS_FILE = 'nq_orb_results.csv'

NY_TZ = pytz.timezone('America/New_York')
RTH_START = time(9, 30)
RTH_END = time(16, 0)
RANGE_END = time(9, 45)

WAIT_BREAKOUT = 0
WAIT_FILL = 1
IN_TRADE = 2
MAX_TRADES_PER_DAY = 2


def step1_to_5min():
    t0 = _time.time()
    print(f"[Step 1] Reading {DBN_FILE} ...")
    store = db.DBNStore.from_file(DBN_FILE)
    df = store.to_df().reset_index()
    print(f"  {len(df):,} rows loaded in {_time.time()-t0:.1f}s")

    df = df[~df['symbol'].str.contains('-', na=False)].copy()
    df = df[['ts_event', 'open', 'high', 'low', 'close', 'volume', 'symbol']]
    print(f"  {len(df):,} rows after removing spreads")

    print("  Converting to NY time ...")
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY_TZ)
    df['date'] = df['ts_event'].dt.date

    print("  Selecting front-month per day ...")
    daily_vol = df.groupby(['date', 'symbol'])['volume'].sum()
    front_month = daily_vol.groupby(level='date').idxmax().apply(lambda x: x[1])
    fm_map = front_month.to_dict()
    df['fm'] = df['date'].map(fm_map)
    df = df[df['symbol'] == df['fm']].copy()
    df.drop(columns=['fm'], inplace=True)
    print(f"  {len(df):,} rows after front-month filter")

    print("  Filtering to RTH ...")
    bt = df['ts_event'].dt.time
    df = df[(bt >= RTH_START) & (bt < RTH_END)].copy()
    print(f"  {len(df):,} rows in RTH")

    print("  Resampling to 5-min bars ...")
    df.set_index('ts_event', inplace=True)
    resampled = df.resample('5T').agg({
        'open': 'first', 'high': 'max', 'low': 'min',
        'close': 'last', 'volume': 'sum', 'symbol': 'first',
    }).dropna(subset=['open'])
    resampled.index.name = 'ts_event'
    resampled.reset_index(inplace=True)

    bt = resampled['ts_event'].dt.time
    resampled = resampled[(bt >= RTH_START) & (bt < RTH_END)].copy()
    resampled['volume'] = resampled['volume'].astype(int)

    resampled.to_csv(FIVEMIN_FILE, index=False)
    print(f"  {len(resampled):,} five-minute bars saved to {FIVEMIN_FILE}")
    print(f"  Step 1 done in {_time.time()-t0:.1f}s")
    return resampled


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


def step2_orb(df):
    t0 = _time.time()
    print(f"\n[Step 2] Running 15-min ORB on {len(df):,} bars ...")

    df['date'] = df['ts_event'].dt.date
    df['bar_time'] = df['ts_event'].dt.time

    days = sorted(df['date'].unique())
    print(f"  {len(days)} trading days")

    results = []
    for day in days:
        day_df = df[df['date'] == day].sort_values('ts_event')
        range_bars = day_df[day_df['bar_time'] < RANGE_END]
        if range_bars.empty:
            results.append({'Date': day, 'Day_of_Week': day.strftime('%A'),
                'Symbol': '', 'Range_High': None, 'Range_Low': None,
                'Range': None, 'Trade_Direction': 'No-Op', 'Entry_Price': None,
                'Exit_Price': None, 'Trade_PL': 0, 'Drawdown_Pct': 0, 'Result': 'No-Op'})
            continue

        rh = range_bars['high'].max()
        rl = range_bars['low'].min()
        rv = rh - rl
        sym = range_bars.iloc[0]['symbol']

        if rv <= 0:
            results.append({'Date': day, 'Day_of_Week': day.strftime('%A'),
                'Symbol': sym, 'Range_High': rh, 'Range_Low': rl,
                'Range': 0, 'Trade_Direction': 'No-Op', 'Entry_Price': None,
                'Exit_Price': None, 'Trade_PL': 0, 'Drawdown_Pct': 0, 'Result': 'No-Op'})
            continue

        trade_bars = day_df[day_df['bar_time'] >= RANGE_END]
        if trade_bars.empty:
            results.append({'Date': day, 'Day_of_Week': day.strftime('%A'),
                'Symbol': sym, 'Range_High': rh, 'Range_Low': rl,
                'Range': rv, 'Trade_Direction': 'No-Op', 'Entry_Price': None,
                'Exit_Price': None, 'Trade_PL': 0, 'Drawdown_Pct': 0, 'Result': 'No-Op'})
            continue

        day_trades = simulate_day(rh, rl, rv, trade_bars)
        if not day_trades:
            results.append({'Date': day, 'Day_of_Week': day.strftime('%A'),
                'Symbol': sym, 'Range_High': rh, 'Range_Low': rl,
                'Range': rv, 'Trade_Direction': 'No-Op', 'Entry_Price': None,
                'Exit_Price': None, 'Trade_PL': 0, 'Drawdown_Pct': 0, 'Result': 'No-Op'})
            continue

        for d, entry, exit_p, dd, res in day_trades:
            pl = 0
            if entry is not None and exit_p is not None:
                pl = (exit_p - entry) if d == 'Long' else (entry - exit_p)
            results.append({'Date': day, 'Day_of_Week': day.strftime('%A'),
                'Symbol': sym, 'Range_High': rh, 'Range_Low': rl,
                'Range': rv, 'Trade_Direction': d, 'Entry_Price': entry,
                'Exit_Price': exit_p, 'Trade_PL': round(pl, 6),
                'Drawdown_Pct': dd, 'Result': res})

    out = pd.DataFrame(results)
    out['Cumulative_PL'] = out['Trade_PL'].cumsum().round(6)
    out.to_csv(RESULTS_FILE, index=False)

    all_t = out[out['Result'].isin(['Win', 'Loss', 'EOD-Close'])]
    def tag(r):
        if r['Result'] in ('Win','Loss'): return r['Result']
        return 'Win' if r['Trade_PL'] > 0 else 'Loss'
    all_t = all_t.copy()
    all_t['Tag'] = all_t.apply(tag, axis=1)
    wins = (all_t['Tag']=='Win').sum()
    losses = (all_t['Tag']=='Loss').sum()

    print(f"\n{'='*55}")
    print(f"  NQ 15-Min ORB")
    print(f"  Trading days:      {len(days)}")
    print(f"  Total trades:      {len(all_t)}")
    print(f"  Wins:              {wins}  ({wins/max(len(all_t),1)*100:.1f}%)")
    print(f"  Losses:            {losses}  ({losses/max(len(all_t),1)*100:.1f}%)")
    print(f"  Final Cum. P/L:    {out['Cumulative_PL'].iloc[-1]:.2f} pts")
    if len(all_t) > 0:
        print(f"  Avg Drawdown:      {all_t['Drawdown_Pct'].mean():.1f}%")
        print(f"  Avg Win DD:        {all_t[all_t['Tag']=='Win']['Drawdown_Pct'].mean():.1f}%")
    print(f"  Step 2 done in {_time.time()-t0:.1f}s")
    print(f"{'='*55}")
    print(f"Saved {len(out)} rows to {RESULTS_FILE}")


def main():
    five_min = step1_to_5min()
    five_min['ts_event'] = pd.to_datetime(five_min['ts_event'], utc=True).dt.tz_convert(NY_TZ)
    step2_orb(five_min)


if __name__ == '__main__':
    main()
