#!/usr/bin/env python3
"""
Opening-Range Breakout on DAILY bars — three timeframes:

  1. MONTHLY ORB:   Range = first 3 trading days of the month.
                    Trade daily bars for the rest of the month.

  2. QUARTERLY ORB: Range = first 3 trading weeks of the quarter.
                    Trade daily bars for the rest of the quarter.

  3. YEARLY ORB:    Range = first 3 months (Jan-Mar) of the year.
                    Trade daily bars for the rest of the year (Apr-Dec).

Same rules as the 15-min intraday ORB:
  - Breakout = close-based (daily close above/below range boundary).
  - Entry = limit order at the breakout level (fill on breakout bar if price
    crossed through, otherwise wait for pullback).
  - Target = 1R (entry ± Range).
  - Stop = opposite boundary, strict inequality.
  - Max 2 trades per period.
  - Open position at period end is closed at last bar's close.
"""
from datetime import date
from collections import OrderedDict

import pandas as pd


INPUT_FILE = 'mnq_daily.csv'

WAIT_BREAKOUT = 0
WAIT_FILL = 1
IN_TRADE = 2

MAX_TRADES_PER_PERIOD = 2


def simulate_period(range_high, range_low, range_val, trade_bars):
    """
    Simulate trades for one period (month or quarter) after the opening range.
    trade_bars is a DataFrame of daily OHLCV bars after the range window.

    Returns list of (direction, entry, exit_price, dd_pct, result) tuples.
    """
    phase = WAIT_BREAKOUT
    direction = None
    entry = target = stop = None
    max_dd = 0.0
    trades = []

    for _, bar in trade_bars.iterrows():
        if len(trades) >= MAX_TRADES_PER_PERIOD and phase != IN_TRADE:
            break

        h, l, c = bar['high'], bar['low'], bar['close']

        # --- Pullback fill check ---
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

        # --- Manage open position ---
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

        # --- Close-based breakout (may fill on same bar) ---
        if phase == WAIT_BREAKOUT and len(trades) < MAX_TRADES_PER_PERIOD:
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

    # End-of-period: close any open position
    if phase == IN_TRADE and len(trade_bars) > 0:
        eod_price = trade_bars.iloc[-1]['close']
        dd_pct = round(max_dd * 100, 2)
        trades.append((direction, entry, eod_price, dd_pct, 'Period-Close'))

    return trades


def get_quarter(d):
    return (d.year, (d.month - 1) // 3 + 1)


def get_iso_week(d):
    return d.isocalendar()[1]


def run_monthly_orb(df):
    """Monthly ORB: range = first 3 trading days of each month."""
    df = df.copy()
    df['ym'] = df['date'].apply(lambda d: (d.year, d.month))

    periods = OrderedDict()
    for _, row in df.iterrows():
        key = row['ym']
        if key not in periods:
            periods[key] = []
        periods[key].append(row)

    results = []
    for (yr, mo), bars in periods.items():
        bars_df = pd.DataFrame(bars)
        if len(bars_df) < 4:
            continue

        range_bars = bars_df.iloc[:3]
        trade_bars = bars_df.iloc[3:].reset_index(drop=True)

        range_high = range_bars['high'].max()
        range_low = range_bars['low'].min()
        range_val = range_high - range_low
        symbol = range_bars.iloc[0]['symbol']
        period_label = f"{yr}-{mo:02d}"

        if range_val <= 0:
            results.append({
                'Period': period_label, 'Range_High': range_high,
                'Range_Low': range_low, 'Range': 0,
                'Trade_Direction': 'No-Op', 'Entry_Price': None,
                'Exit_Price': None, 'Trade_PL': 0, 'Drawdown_Pct': 0,
                'Result': 'No-Op', 'Symbol': symbol,
                'Range_Days': 3, 'Trade_Days': len(trade_bars),
            })
            continue

        day_trades = simulate_period(range_high, range_low, range_val, trade_bars)

        if not day_trades:
            results.append({
                'Period': period_label, 'Range_High': range_high,
                'Range_Low': range_low, 'Range': range_val,
                'Trade_Direction': 'No-Op', 'Entry_Price': None,
                'Exit_Price': None, 'Trade_PL': 0, 'Drawdown_Pct': 0,
                'Result': 'No-Op', 'Symbol': symbol,
                'Range_Days': 3, 'Trade_Days': len(trade_bars),
            })
            continue

        for direction, entry, exit_price, dd_pct, result_tag in day_trades:
            pl = 0
            if entry is not None and exit_price is not None:
                pl = (exit_price - entry) if direction == 'Long' else (entry - exit_price)
            results.append({
                'Period': period_label, 'Range_High': range_high,
                'Range_Low': range_low, 'Range': range_val,
                'Trade_Direction': direction, 'Entry_Price': entry,
                'Exit_Price': exit_price, 'Trade_PL': round(pl, 6),
                'Drawdown_Pct': dd_pct, 'Result': result_tag,
                'Symbol': symbol, 'Range_Days': 3,
                'Trade_Days': len(trade_bars),
            })

    return pd.DataFrame(results)


def run_quarterly_orb(df):
    """Quarterly ORB: range = first 3 trading weeks of each quarter."""
    df = df.copy()
    df['qtr'] = df['date'].apply(get_quarter)
    df['iso_week'] = df['date'].apply(get_iso_week)

    periods = OrderedDict()
    for _, row in df.iterrows():
        key = row['qtr']
        if key not in periods:
            periods[key] = []
        periods[key].append(row)

    results = []
    for (yr, q), bars in periods.items():
        bars_df = pd.DataFrame(bars)
        period_label = f"{yr}-Q{q}"
        symbol = bars_df.iloc[0]['symbol']

        # First 3 distinct ISO weeks in this quarter
        weeks_in_qtr = bars_df['iso_week'].unique()
        if len(weeks_in_qtr) < 4:
            continue

        range_weeks = set(weeks_in_qtr[:3])
        range_mask = bars_df['iso_week'].isin(range_weeks)
        range_bars = bars_df[range_mask]
        trade_bars = bars_df[~range_mask].reset_index(drop=True)

        if len(range_bars) == 0 or len(trade_bars) == 0:
            continue

        range_high = range_bars['high'].max()
        range_low = range_bars['low'].min()
        range_val = range_high - range_low

        if range_val <= 0:
            results.append({
                'Period': period_label, 'Range_High': range_high,
                'Range_Low': range_low, 'Range': 0,
                'Trade_Direction': 'No-Op', 'Entry_Price': None,
                'Exit_Price': None, 'Trade_PL': 0, 'Drawdown_Pct': 0,
                'Result': 'No-Op', 'Symbol': symbol,
                'Range_Days': len(range_bars), 'Trade_Days': len(trade_bars),
            })
            continue

        day_trades = simulate_period(range_high, range_low, range_val, trade_bars)

        if not day_trades:
            results.append({
                'Period': period_label, 'Range_High': range_high,
                'Range_Low': range_low, 'Range': range_val,
                'Trade_Direction': 'No-Op', 'Entry_Price': None,
                'Exit_Price': None, 'Trade_PL': 0, 'Drawdown_Pct': 0,
                'Result': 'No-Op', 'Symbol': symbol,
                'Range_Days': len(range_bars), 'Trade_Days': len(trade_bars),
            })
            continue

        for direction, entry, exit_price, dd_pct, result_tag in day_trades:
            pl = 0
            if entry is not None and exit_price is not None:
                pl = (exit_price - entry) if direction == 'Long' else (entry - exit_price)
            results.append({
                'Period': period_label, 'Range_High': range_high,
                'Range_Low': range_low, 'Range': range_val,
                'Trade_Direction': direction, 'Entry_Price': entry,
                'Exit_Price': exit_price, 'Trade_PL': round(pl, 6),
                'Drawdown_Pct': dd_pct, 'Result': result_tag,
                'Symbol': symbol, 'Range_Days': len(range_bars),
                'Trade_Days': len(trade_bars),
            })

    return pd.DataFrame(results)


def run_yearly_orb(df):
    """Yearly ORB: range = first 3 months (Jan-Mar), trade Apr-Dec."""
    df = df.copy()
    df['year'] = df['date'].apply(lambda d: d.year)
    df['month'] = df['date'].apply(lambda d: d.month)

    periods = OrderedDict()
    for _, row in df.iterrows():
        key = row['year']
        if key not in periods:
            periods[key] = []
        periods[key].append(row)

    results = []
    for yr, bars in periods.items():
        bars_df = pd.DataFrame(bars)
        period_label = str(yr)
        symbol = bars_df.iloc[0]['symbol']

        range_bars = bars_df[bars_df['month'] <= 3]
        trade_bars = bars_df[bars_df['month'] > 3].reset_index(drop=True)

        if len(range_bars) == 0 or len(trade_bars) == 0:
            continue

        range_high = range_bars['high'].max()
        range_low = range_bars['low'].min()
        range_val = range_high - range_low

        if range_val <= 0:
            results.append({
                'Period': period_label, 'Range_High': range_high,
                'Range_Low': range_low, 'Range': 0,
                'Trade_Direction': 'No-Op', 'Entry_Price': None,
                'Exit_Price': None, 'Trade_PL': 0, 'Drawdown_Pct': 0,
                'Result': 'No-Op', 'Symbol': symbol,
                'Range_Days': len(range_bars), 'Trade_Days': len(trade_bars),
            })
            continue

        day_trades = simulate_period(range_high, range_low, range_val, trade_bars)

        if not day_trades:
            results.append({
                'Period': period_label, 'Range_High': range_high,
                'Range_Low': range_low, 'Range': range_val,
                'Trade_Direction': 'No-Op', 'Entry_Price': None,
                'Exit_Price': None, 'Trade_PL': 0, 'Drawdown_Pct': 0,
                'Result': 'No-Op', 'Symbol': symbol,
                'Range_Days': len(range_bars), 'Trade_Days': len(trade_bars),
            })
            continue

        for direction, entry, exit_price, dd_pct, result_tag in day_trades:
            pl = 0
            if entry is not None and exit_price is not None:
                pl = (exit_price - entry) if direction == 'Long' else (entry - exit_price)
            results.append({
                'Period': period_label, 'Range_High': range_high,
                'Range_Low': range_low, 'Range': range_val,
                'Trade_Direction': direction, 'Entry_Price': entry,
                'Exit_Price': exit_price, 'Trade_PL': round(pl, 6),
                'Drawdown_Pct': dd_pct, 'Result': result_tag,
                'Symbol': symbol, 'Range_Days': len(range_bars),
                'Trade_Days': len(trade_bars),
            })

    return pd.DataFrame(results)


def print_summary(out, label):
    def tag(r):
        if r['Result'] in ('Win', 'Loss'):
            return r['Result']
        if r['Result'] == 'Period-Close':
            return 'Win' if r['Trade_PL'] > 0 else 'Loss'
        return 'No-Op'

    out['Tag'] = out.apply(tag, axis=1)
    trades = out[out['Tag'].isin(['Win', 'Loss'])]
    wins = (trades['Tag'] == 'Win').sum()
    losses = (trades['Tag'] == 'Loss').sum()
    no_ops = (out['Tag'] == 'No-Op').sum()

    print(f"\n{'='*55}")
    print(f"  {label}")
    print(f"  Periods:           {out['Period'].nunique()}")
    print(f"  Total trades:      {len(trades)}")
    print(f"  Wins:              {wins}  ({wins/max(len(trades),1)*100:.1f}%)")
    print(f"  Losses:            {losses}  ({losses/max(len(trades),1)*100:.1f}%)")
    print(f"  No-Op periods:     {no_ops}")
    print(f"  Final Cum. P/L:    {out['Cumulative_PL'].iloc[-1]:.2f} pts")
    if len(trades) > 0:
        print(f"  Avg Drawdown:      {trades['Drawdown_Pct'].mean():.1f}%")
        print(f"  Avg Win DD:        {trades[trades['Tag']=='Win']['Drawdown_Pct'].mean():.1f}%")
    print(f"{'='*55}")


def main():
    print(f"Reading {INPUT_FILE} ...")
    df = pd.read_csv(INPUT_FILE, parse_dates=['date'])
    df['date'] = df['date'].dt.date
    print(f"  {len(df)} daily bars")

    # --- Monthly ORB ---
    print("\nRunning Monthly ORB (range = first 3 trading days) ...")
    monthly = run_monthly_orb(df)
    monthly['Cumulative_PL'] = monthly['Trade_PL'].cumsum().round(6)
    monthly.to_csv('mnq_monthly_orb.csv', index=False)
    print_summary(monthly, "MONTHLY ORB (3-day opening range)")
    print(f"Saved {len(monthly)} rows to mnq_monthly_orb.csv")

    # --- Quarterly ORB ---
    print("\nRunning Quarterly ORB (range = first 3 trading weeks) ...")
    quarterly = run_quarterly_orb(df)
    quarterly['Cumulative_PL'] = quarterly['Trade_PL'].cumsum().round(6)
    quarterly.to_csv('mnq_quarterly_orb.csv', index=False)
    print_summary(quarterly, "QUARTERLY ORB (3-week opening range)")
    print(f"Saved {len(quarterly)} rows to mnq_quarterly_orb.csv")

    # --- Yearly ORB ---
    print("\nRunning Yearly ORB (range = Jan-Mar, trade Apr-Dec) ...")
    yearly = run_yearly_orb(df)
    yearly['Cumulative_PL'] = yearly['Trade_PL'].cumsum().round(6)
    yearly.to_csv('mnq_yearly_orb.csv', index=False)
    print_summary(yearly, "YEARLY ORB (3-month opening range: Jan-Mar)")
    print(f"Saved {len(yearly)} rows to mnq_yearly_orb.csv")


if __name__ == '__main__':
    main()
