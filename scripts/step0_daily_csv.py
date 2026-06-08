#!/usr/bin/env python3
"""
Convert daily OHLCV dbn.zst to a clean CSV with one row per trading day,
using the front-month contract (highest daily volume, excluding spreads).
"""
import databento as db
import pandas as pd


INPUT_FILE = 'glbx-mdp3-20100606-20260308.ohlcv-1d.dbn.zst'
OUTPUT_FILE = 'mnq_daily.csv'


def main():
    print(f"Reading {INPUT_FILE} ...")
    store = db.DBNStore.from_file(INPUT_FILE)
    df = store.to_df().reset_index()

    # Drop spreads
    df = df[~df['symbol'].str.contains('-', na=False)].copy()
    print(f"  {len(df)} rows after removing spreads")

    df['date'] = df['ts_event'].dt.date

    # Front-month selection: highest volume per date
    idx = df.groupby('date')['volume'].idxmax()
    daily = df.loc[idx].copy()
    daily = daily.sort_values('date')

    daily = daily[['date', 'open', 'high', 'low', 'close', 'volume', 'symbol']]
    daily.to_csv(OUTPUT_FILE, index=False)
    print(f"  {len(daily)} trading days saved to {OUTPUT_FILE}")
    print(f"  Range: {daily['date'].iloc[0]} to {daily['date'].iloc[-1]}")


if __name__ == '__main__':
    main()
