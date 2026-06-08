#!/usr/bin/env python3
"""
Step 2: Opening-Range Breakout strategy on 5-minute RTH data.

Rules:
  1. 15-minute opening range (9:30-9:45): Range-High, Range-Low, Range.
  2. Breakout = CLOSE-BASED: a 5-min bar must CLOSE above Range-High (Long)
     or CLOSE below Range-Low (Short).
  3. If the breakout bar's low (Long) or high (Short) reaches the range boundary,
     the limit order fills on the breakout bar itself (price crossed through the
     level). Otherwise, wait for a pullback on subsequent bars.
  4. On the bar where the limit fills via the breakout bar, skip stop/target/DD
     (can't determine intra-bar sequence). Management starts next bar.
     On pullback-fill bars, management runs immediately.
  5. Target = entry +/- Range (limit order, touch-based).
  6. Stop = opposite boundary, STRICT inequality (touching 100% DD is NOT a
     stop-out; price must break through).
  7. Multiple trades per day: after a trade resolves, new breakouts can trigger
     additional entries.
  8. Open position at 4:00 PM is closed at last bar's close.

Outputs a CSV with one row per trade (multiple rows possible per day).
"""
from datetime import time

import pandas as pd


INPUT_FILE = 'mnq_5min_rth.csv'
OUTPUT_FILE = 'mnq_orb_results.csv'

RANGE_END = time(9, 45)

WAIT_BREAKOUT = 0
WAIT_FILL = 1
IN_TRADE = 2


MAX_TRADES_PER_DAY = 2


def simulate_day(range_high, range_low, range_val, trade_bars):
    """
    Simulate all trades for a single day (max MAX_TRADES_PER_DAY).
    Returns list of (direction, entry, exit_price, dd_pct, result) tuples.
    """
    phase = WAIT_BREAKOUT
    direction = None
    entry = target = stop = None
    max_dd = 0.0
    trades = []

    for _, bar in trade_bars.iterrows():
        if len(trades) >= MAX_TRADES_PER_DAY and phase != IN_TRADE:
            break

        h, l, c = bar['high'], bar['low'], bar['close']

        # --- Phase 2: pullback fill check (for bars AFTER the breakout bar) ---
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
                # Fall through to IN_TRADE — DD is valid on pullback-fill bars
            else:
                if direction == 'Long' and c < range_low:
                    direction = 'Short'
                elif direction == 'Short' and c > range_high:
                    direction = 'Long'

        # --- Phase 3: manage open position ---
        if phase == IN_TRADE:
            if direction == 'Long':
                if l < stop:
                    trades.append(('Long', entry, stop, 100.0, 'Loss'))
                    phase, direction = WAIT_BREAKOUT, None
                elif h >= target:
                    max_dd = max(max_dd, max(0.0, (entry - l) / range_val))
                    trades.append(
                        ('Long', entry, target, round(max_dd * 100, 2), 'Win'))
                    phase, direction = WAIT_BREAKOUT, None
                else:
                    max_dd = max(max_dd, max(0.0, (entry - l) / range_val))
                    continue  # still in trade — skip breakout check
            else:  # Short
                if h > stop:
                    trades.append(('Short', entry, stop, 100.0, 'Loss'))
                    phase, direction = WAIT_BREAKOUT, None
                elif l <= target:
                    max_dd = max(max_dd, max(0.0, (h - entry) / range_val))
                    trades.append(
                        ('Short', entry, target, round(max_dd * 100, 2), 'Win'))
                    phase, direction = WAIT_BREAKOUT, None
                else:
                    max_dd = max(max_dd, max(0.0, (h - entry) / range_val))
                    continue  # still in trade — skip breakout check

        # --- Phase 1: close-based breakout (may also fill on the same bar) ---
        if phase == WAIT_BREAKOUT and len(trades) < MAX_TRADES_PER_DAY:
            if c > range_high:
                direction = 'Long'
                if l <= range_high:
                    entry, target, stop = range_high, range_high + range_val, range_low
                    phase = IN_TRADE
                    max_dd = 0.0
                    continue  # skip management on breakout-fill bar
                else:
                    phase = WAIT_FILL
            elif c < range_low:
                direction = 'Short'
                if h >= range_low:
                    entry, target, stop = range_low, range_low - range_val, range_high
                    phase = IN_TRADE
                    max_dd = 0.0
                    continue  # skip management on breakout-fill bar
                else:
                    phase = WAIT_FILL

    # End-of-day: close any open position at last bar's close
    if phase == IN_TRADE:
        eod_price = trade_bars.iloc[-1]['close']
        dd_pct = round(max_dd * 100, 2)
        trades.append((direction, entry, eod_price, dd_pct, 'EOD-Close'))

    return trades


def main():
    print(f"Reading {INPUT_FILE} ...")
    df = pd.read_csv(INPUT_FILE)
    df['ts_event'] = pd.to_datetime(
        df['ts_event'], utc=True).dt.tz_convert('America/New_York')
    df['date'] = df['ts_event'].dt.date
    df['bar_time'] = df['ts_event'].dt.time

    days = sorted(df['date'].unique())
    print(f"  {len(days)} trading days found")

    results = []
    for day in days:
        day_df = df[df['date'] == day].sort_values('ts_event')

        range_bars = day_df[day_df['bar_time'] < RANGE_END]
        if range_bars.empty:
            results.append({
                'Date': day, 'Day_of_Week': day.strftime('%A'),
                'Symbol': '', 'Range_High': None, 'Range_Low': None,
                'Range': None, 'Trade_Direction': 'No-Op',
                'Entry_Price': None, 'Exit_Price': None,
                'Trade_PL': 0, 'Drawdown_Pct': 0, 'Result': 'No-Op',
            })
            continue

        range_high = range_bars['high'].max()
        range_low = range_bars['low'].min()
        range_val = range_high - range_low
        symbol = range_bars.iloc[0]['symbol']

        if range_val <= 0:
            results.append({
                'Date': day, 'Day_of_Week': day.strftime('%A'),
                'Symbol': symbol, 'Range_High': range_high, 'Range_Low': range_low,
                'Range': 0, 'Trade_Direction': 'No-Op',
                'Entry_Price': None, 'Exit_Price': None,
                'Trade_PL': 0, 'Drawdown_Pct': 0, 'Result': 'No-Op',
            })
            continue

        trade_bars = day_df[day_df['bar_time'] >= RANGE_END]
        if trade_bars.empty:
            results.append({
                'Date': day, 'Day_of_Week': day.strftime('%A'),
                'Symbol': symbol, 'Range_High': range_high, 'Range_Low': range_low,
                'Range': range_val, 'Trade_Direction': 'No-Op',
                'Entry_Price': None, 'Exit_Price': None,
                'Trade_PL': 0, 'Drawdown_Pct': 0, 'Result': 'No-Op',
            })
            continue

        day_trades = simulate_day(range_high, range_low, range_val, trade_bars)

        if not day_trades:
            results.append({
                'Date': day, 'Day_of_Week': day.strftime('%A'),
                'Symbol': symbol, 'Range_High': range_high, 'Range_Low': range_low,
                'Range': range_val, 'Trade_Direction': 'No-Op',
                'Entry_Price': None, 'Exit_Price': None,
                'Trade_PL': 0, 'Drawdown_Pct': 0, 'Result': 'No-Op',
            })
            continue

        for direction, entry, exit_price, dd_pct, result_tag in day_trades:
            if entry is not None and exit_price is not None:
                pl = (exit_price -
                      entry) if direction == 'Long' else (entry - exit_price)
            else:
                pl = 0
            results.append({
                'Date': day,
                'Day_of_Week': day.strftime('%A'),
                'Symbol': symbol,
                'Range_High': range_high,
                'Range_Low': range_low,
                'Range': range_val,
                'Trade_Direction': direction,
                'Entry_Price': entry,
                'Exit_Price': exit_price,
                'Trade_PL': round(pl, 6),
                'Drawdown_Pct': dd_pct,
                'Result': result_tag,
            })

    out = pd.DataFrame(results)
    out['Cumulative_PL'] = out['Trade_PL'].cumsum().round(6)
    out.to_csv(OUTPUT_FILE, index=False)

    # Summary
    total_days = len(days)
    all_trades = out[out['Result'].isin(['Win', 'Loss', 'EOD-Close'])]
    wins = len(all_trades[all_trades['Result'] == 'Win'])
    losses = len(all_trades[all_trades['Result'] == 'Loss'])
    eod = len(all_trades[all_trades['Result'] == 'EOD-Close'])
    no_op_rows = len(out[out['Result'] == 'No-Op'])
    trade_days = total_days - no_op_rows

    multi_trade_days = out[out['Result'] != 'No-Op'].groupby('Date').size()
    multi = (multi_trade_days > 1).sum() if len(multi_trade_days) > 0 else 0

    print(f"\n{'='*55}")
    print(f"  Trading days:      {total_days}")
    print(f"  Days with trades:  {trade_days}")
    print(f"  Total trades:      {len(all_trades)}")
    print(f"  Trades/active day: {len(all_trades)/max(trade_days,1):.2f}")
    print(f"  Multi-trade days:  {multi}")
    print(
        f"  Wins:              {wins}  ({wins/max(len(all_trades),1)*100:.1f}%)")
    print(
        f"  Losses:            {losses}  ({losses/max(len(all_trades),1)*100:.1f}%)")
    print(f"  EOD-Close:         {eod}")
    print(f"  No-Op days:        {no_op_rows}")
    print(f"  Final Cum. P/L:    {out['Cumulative_PL'].iloc[-1]:.2f} pts")
    if len(all_trades) > 0:
        print(f"  Avg Drawdown:      {all_trades['Drawdown_Pct'].mean():.1f}%")
        print(
            f"  Avg Win DD:        {all_trades[all_trades['Result']=='Win']['Drawdown_Pct'].mean():.1f}%")
    print(f"{'='*55}")
    print(f"Saved {len(out)} rows to {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
