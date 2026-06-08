#!/usr/bin/env python3
"""
Update the MNQ 15-min ORB backtest with the latest 1-min OHLCV DBN data.

Reads the new DBN file (extended through 2026-04-23), regenerates the
5-min RTH bars and ORB results for the FULL history (2021-03-04 onward to
match the original CSV range), and prints a performance report covering
the new incremental period beyond the prior backtest's end date.
"""
import time as _time
from datetime import date, time

import databento as db
import pandas as pd
import pytz

RAW_DIR = '/home/tester/hsm/potions/mnq/raw'
MNQ_DIR = '/home/tester/hsm/potions/mnq'

DBN_FILE = f'{RAW_DIR}/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'
FIVEMIN_FILE = f'{MNQ_DIR}/mnq_5min_rth.csv'
RESULTS_FILE = f'{MNQ_DIR}/mnq_orb_results.csv'
PRIOR_RESULTS_BACKUP = f'{MNQ_DIR}/mnq_orb_results.prior.csv'

NY_TZ = pytz.timezone('America/New_York')
RTH_START = time(9, 30)
RTH_END = time(16, 0)
RANGE_END = time(9, 45)

MNQ_ROOT = 'MNQ'
HISTORY_START = date(2021, 3, 4)

WAIT_BREAKOUT = 0
WAIT_FILL = 1
IN_TRADE = 2
MAX_TRADES_PER_DAY = 2


def build_5min_bars():
    t0 = _time.time()
    print(f"[Step 1] Reading {DBN_FILE} ...")
    store = db.DBNStore.from_file(DBN_FILE)
    df = store.to_df().reset_index()
    print(f"  {len(df):,} rows loaded in {_time.time() - t0:.1f}s")

    df = df[~df['symbol'].str.contains('-', na=False)].copy()
    df = df[df['symbol'].str.startswith(MNQ_ROOT)].copy()
    df = df[['ts_event', 'open', 'high', 'low', 'close', 'volume', 'symbol']]
    print(f"  {len(df):,} rows after MNQ + spread filter")

    print("  Converting timestamps to NY ...")
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY_TZ)
    df['date'] = df['ts_event'].dt.date

    df = df[df['date'] >= HISTORY_START].copy()
    print(f"  {len(df):,} rows after date >= {HISTORY_START}")

    print("  Selecting front-month per day (highest daily volume) ...")
    daily_vol = df.groupby(['date', 'symbol'])['volume'].sum()
    front_month = daily_vol.groupby(level='date').idxmax().apply(lambda x: x[1])
    fm_map = front_month.to_dict()
    df['fm'] = df['date'].map(fm_map)
    df = df[df['symbol'] == df['fm']].copy()
    df.drop(columns=['fm'], inplace=True)
    print(f"  {len(df):,} rows after front-month filter")

    print("  Filtering to RTH (9:30 - 16:00 NY) ...")
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
    print(f"  {len(resampled):,} five-minute bars -> {FIVEMIN_FILE}")
    print(f"  Step 1 done in {_time.time() - t0:.1f}s")
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


def run_orb(df):
    t0 = _time.time()
    print(f"\n[Step 2] Running 15-min ORB on {len(df):,} bars ...")

    df['ts_event'] = pd.to_datetime(df['ts_event'], utc=True).dt.tz_convert(NY_TZ)
    df['date'] = df['ts_event'].dt.date
    df['bar_time'] = df['ts_event'].dt.time

    days = sorted(df['date'].unique())
    print(f"  {len(days)} trading days")

    results = []
    for day in days:
        day_df = df[df['date'] == day].sort_values('ts_event')
        range_bars = day_df[day_df['bar_time'] < RANGE_END]
        if range_bars.empty:
            results.append({
                'Date': day, 'Day_of_Week': day.strftime('%A'),
                'Symbol': '', 'Range_High': None, 'Range_Low': None,
                'Range': None, 'Trade_Direction': 'No-Op', 'Entry_Price': None,
                'Exit_Price': None, 'Trade_PL': 0, 'Drawdown_Pct': 0, 'Result': 'No-Op',
            })
            continue

        rh = range_bars['high'].max()
        rl = range_bars['low'].min()
        rv = rh - rl
        sym = range_bars.iloc[0]['symbol']

        if rv <= 0:
            results.append({
                'Date': day, 'Day_of_Week': day.strftime('%A'),
                'Symbol': sym, 'Range_High': rh, 'Range_Low': rl,
                'Range': 0, 'Trade_Direction': 'No-Op', 'Entry_Price': None,
                'Exit_Price': None, 'Trade_PL': 0, 'Drawdown_Pct': 0, 'Result': 'No-Op',
            })
            continue

        trade_bars = day_df[day_df['bar_time'] >= RANGE_END]
        if trade_bars.empty:
            results.append({
                'Date': day, 'Day_of_Week': day.strftime('%A'),
                'Symbol': sym, 'Range_High': rh, 'Range_Low': rl,
                'Range': rv, 'Trade_Direction': 'No-Op', 'Entry_Price': None,
                'Exit_Price': None, 'Trade_PL': 0, 'Drawdown_Pct': 0, 'Result': 'No-Op',
            })
            continue

        day_trades = simulate_day(rh, rl, rv, trade_bars)
        if not day_trades:
            results.append({
                'Date': day, 'Day_of_Week': day.strftime('%A'),
                'Symbol': sym, 'Range_High': rh, 'Range_Low': rl,
                'Range': rv, 'Trade_Direction': 'No-Op', 'Entry_Price': None,
                'Exit_Price': None, 'Trade_PL': 0, 'Drawdown_Pct': 0, 'Result': 'No-Op',
            })
            continue

        for d, entry, exit_p, dd, res in day_trades:
            pl = 0
            if entry is not None and exit_p is not None:
                pl = (exit_p - entry) if d == 'Long' else (entry - exit_p)
            results.append({
                'Date': day, 'Day_of_Week': day.strftime('%A'),
                'Symbol': sym, 'Range_High': rh, 'Range_Low': rl,
                'Range': rv, 'Trade_Direction': d, 'Entry_Price': entry,
                'Exit_Price': exit_p, 'Trade_PL': round(pl, 6),
                'Drawdown_Pct': dd, 'Result': res,
            })

    out = pd.DataFrame(results)
    out['Cumulative_PL'] = out['Trade_PL'].cumsum().round(6)
    out.to_csv(RESULTS_FILE, index=False)
    print(f"  Step 2 done in {_time.time() - t0:.1f}s -> {RESULTS_FILE}")
    return out


def summarize(df, label):
    traded = df[df['Result'].isin(['Win', 'Loss', 'EOD-Close'])].copy()

    def tag(r):
        if r['Result'] in ('Win', 'Loss'):
            return r['Result']
        return 'Win' if r['Trade_PL'] > 0 else 'Loss'

    traded['Tag'] = traded.apply(tag, axis=1)
    wins = (traded['Tag'] == 'Win').sum()
    losses = (traded['Tag'] == 'Loss').sum()
    eod = (traded['Result'] == 'EOD-Close').sum()
    pl = traded['Trade_PL'].sum()

    days = df['Date'].nunique()
    noop_days = (df['Result'] == 'No-Op').sum()
    trade_days = days - noop_days

    print(f"\n  === {label} ===")
    print(f"  Date range:        {df['Date'].min()} -> {df['Date'].max()}")
    print(f"  Trading days:      {days}")
    print(f"  Days with trades:  {trade_days}")
    print(f"  Total trades:      {len(traded)}")
    if len(traded):
        print(f"  Wins:              {wins}  ({wins/len(traded)*100:.1f}%)")
        print(f"  Losses:            {losses}  ({losses/len(traded)*100:.1f}%)")
        print(f"  EOD-Close:         {eod}")
        print(f"  Total P/L (pts):   {pl:.2f}")
        print(f"  Avg Trade P/L:     {pl/len(traded):.2f}")
        print(f"  Avg Drawdown %:    {traded['Drawdown_Pct'].mean():.1f}%")
        if wins:
            print(f"  Avg Win Drawdown%: {traded[traded['Tag']=='Win']['Drawdown_Pct'].mean():.1f}%")
    return {
        'days': days, 'trade_days': trade_days, 'trades': len(traded),
        'wins': wins, 'losses': losses, 'eod': eod, 'pl': pl,
    }


def compare_reports():
    print("\n" + "=" * 64)
    print("  MNQ 15-MIN ORB: Performance Report")
    print("=" * 64)

    prior = pd.read_csv(PRIOR_RESULTS_BACKUP)
    new = pd.read_csv(RESULTS_FILE)
    prior['Date'] = pd.to_datetime(prior['Date']).dt.date
    new['Date'] = pd.to_datetime(new['Date']).dt.date

    prior_end = prior['Date'].max()
    print(f"\n  Prior backtest ended: {prior_end}")
    print(f"  Updated data ends:    {new['Date'].max()}")

    # Full history summaries.
    summarize(prior, f"PRIOR RUN (through {prior_end})")
    summarize(new, f"UPDATED RUN (through {new['Date'].max()})")

    # Incremental period only.
    incr = new[new['Date'] > prior_end].copy()
    if incr.empty:
        print("\n  No new trading days beyond prior run — nothing to report.")
        return

    summarize(incr, f"NEW PERIOD ONLY ({incr['Date'].min()} -> {incr['Date'].max()})")

    # Delta on overall cumulative P/L.
    prior_cum = prior['Cumulative_PL'].iloc[-1]
    new_cum = new['Cumulative_PL'].iloc[-1]
    print(f"\n  Cumulative P/L growth: {prior_cum:.2f} -> {new_cum:.2f}  (Δ {new_cum - prior_cum:+.2f} pts)")

    # Daily P/L breakdown for the new period.
    traded = incr[incr['Result'].isin(['Win', 'Loss', 'EOD-Close'])]
    print(f"\n  --- New-period trade log ({len(traded)} trades) ---")
    pd.set_option('display.width', 160)
    pd.set_option('display.max_rows', 200)
    cols = ['Date', 'Day_of_Week', 'Symbol', 'Range', 'Trade_Direction',
            'Entry_Price', 'Exit_Price', 'Trade_PL', 'Drawdown_Pct', 'Result']
    print(traded[cols].to_string(index=False))


def main():
    import os
    if os.path.exists(RESULTS_FILE) and not os.path.exists(PRIOR_RESULTS_BACKUP):
        import shutil
        shutil.copy(RESULTS_FILE, PRIOR_RESULTS_BACKUP)
        print(f"[Backup] Prior results saved -> {PRIOR_RESULTS_BACKUP}")

    five = build_5min_bars()
    run_orb(five)
    compare_reports()


if __name__ == '__main__':
    main()
