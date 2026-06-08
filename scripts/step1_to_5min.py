#!/usr/bin/env python3
"""
Step 1: Convert 1-minute MNQ OHLCV data to 5-minute bars,
filtered to Regular Trading Hours (9:30 AM - 4:00 PM New York time).

For each trading day, automatically selects the front-month contract
(the symbol with the highest total daily volume, excluding spreads).
"""
import time as _time
from datetime import time

import pandas as pd
import pytz

INPUT_FILE = 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'
OUTPUT_FILE = 'mnq_5min_rth.csv'
NY_TZ = pytz.timezone('America/New_York')

RTH_START = time(9, 30)
RTH_END = time(16, 0)


def main():
    t0 = _time.time()

    print(f"Reading {INPUT_FILE} ...")
    df = pd.read_csv(INPUT_FILE, usecols=['ts_event', 'open', 'high', 'low', 'close', 'volume', 'symbol'])
    print(f"  {len(df):,} rows loaded in {_time.time() - t0:.1f}s")

    # Drop calendar spreads (symbols containing "-")
    df = df[~df['symbol'].str.contains('-', na=False)].copy()
    print(f"  {len(df):,} rows after removing spreads")

    # Parse timestamps and convert UTC -> NY
    print("Converting timestamps to New York time ...")
    df['ts_event'] = pd.to_datetime(df['ts_event'], utc=True).dt.tz_convert(NY_TZ)
    df['date'] = df['ts_event'].dt.date

    # Select front-month contract per NY date (highest total volume)
    print("Selecting front-month contract per day ...")
    daily_vol = df.groupby(['date', 'symbol'])['volume'].sum()
    front_month = daily_vol.groupby(level='date').idxmax().apply(lambda x: x[1])
    front_month_map = front_month.to_dict()

    df['fm'] = df['date'].map(front_month_map)
    df = df[df['symbol'] == df['fm']].copy()
    df.drop(columns=['fm'], inplace=True)
    print(f"  {len(df):,} rows after front-month filter")

    # Filter to RTH: 9:30 AM <= time < 4:00 PM
    print("Filtering to Regular Trading Hours ...")
    bar_time = df['ts_event'].dt.time
    df = df[(bar_time >= RTH_START) & (bar_time < RTH_END)].copy()
    print(f"  {len(df):,} rows in RTH window")

    # Resample to 5-minute bars
    print("Resampling to 5-minute OHLCV bars ...")
    df.set_index('ts_event', inplace=True)
    resampled = df.resample('5T').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
        'symbol': 'first',
    }).dropna(subset=['open'])

    resampled.index.name = 'ts_event'
    resampled.reset_index(inplace=True)

    # Re-filter to RTH (resample can produce edge bins outside the window)
    bar_time = resampled['ts_event'].dt.time
    resampled = resampled[(bar_time >= RTH_START) & (bar_time < RTH_END)].copy()

    resampled['volume'] = resampled['volume'].astype(int)

    print(f"  {len(resampled):,} five-minute bars")
    print(f"Saving to {OUTPUT_FILE} ...")
    resampled.to_csv(OUTPUT_FILE, index=False)
    print(f"Done in {_time.time() - t0:.1f}s total.")


if __name__ == '__main__':
    main()
