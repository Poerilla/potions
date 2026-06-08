#!/usr/bin/env python3
"""
v1b — Honest ORB with limit pullback on a bar *after* the confirmation close.

Uses 5-minute RTH bars (same as archived step2_fixed_next_bar_entry.py).
Entry: limit at range boundary after 5m close beyond range; fill when
subsequent bar touches limit.

Outputs MNQ 1-contract Net_$ ( $2/pt − $1.50 RT ) for pairing with v2d
in adaptive_v1_50_150 merge.

Only rows with real trades are written (no No-Op placeholder rows).
"""
from datetime import time
from pathlib import Path

import pandas as pd


INPUT_FILE = Path('/home/tester/hsm/potions/mnq/mnq_5min_rth.csv')
OUT_CSV = Path('/home/tester/hsm/potions/mnq/v1_limit/mnq_orb_results_v1b_limit.csv')
RANGE_END = time(9, 45)
MULT = 2.0
FEE_RT = 1.50

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
                phase = WAIT_FILL
            elif c < range_low:
                direction = 'Short'
                phase = WAIT_FILL

    if phase == IN_TRADE:
        eod_price = trade_bars.iloc[-1]['close']
        trades.append((direction, entry, eod_price, round(max_dd * 100, 2), 'EOD-Close'))
    return trades


def main():
    print(f'Reading {INPUT_FILE} ...')
    df = pd.read_csv(INPUT_FILE)
    df['ts_event'] = pd.to_datetime(df['ts_event'], utc=True).dt.tz_convert('America/New_York')
    df['date'] = df['ts_event'].dt.date
    df['bar_time'] = df['ts_event'].dt.time
    days = sorted(df['date'].unique())
    print(f'  {len(days)} calendar days in file')

    results = []
    for day in days:
        g = df[df['date'] == day].sort_values('ts_event')
        rb = g[g['bar_time'] < RANGE_END]
        if rb.empty:
            continue
        rh = rb['high'].max()
        rl = rb['low'].min()
        rv = rh - rl
        sym = rb.iloc[0]['symbol']
        if rv <= 0:
            continue
        tb = g[g['bar_time'] >= RANGE_END]
        if tb.empty:
            continue

        day_trades = simulate_day(rh, rl, rv, tb)
        if not day_trades:
            continue
        for d, entry, exit_p, dd, res in day_trades:
            pl = (exit_p - entry) if d == 'Long' else (entry - exit_p)
            results.append({
                'Date': day,
                'Day_of_Week': day.strftime('%A'),
                'Symbol': sym,
                'Range_High': rh,
                'Range_Low': rl,
                'Range': rv,
                'Trade_Direction': d,
                'Entry_Price': entry,
                'Exit_Price': exit_p,
                'Trade_PL': round(pl, 6),
                'Drawdown_Pct': dd,
                'Result': res,
                'Net_$': round(pl * MULT - FEE_RT, 2),
            })

    out = pd.DataFrame(results)
    out['Cumulative_PL'] = out['Trade_PL'].cumsum().round(6)
    out['Cumulative_$'] = out['Net_$'].cumsum().round(2)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)

    wins = (out['Trade_PL'] > 0).sum()
    eq = out['Net_$'].cumsum()
    dd = (eq - eq.cummax()).min()
    print(f'\n=== v1b limit (5m), 1 MNQ ===')
    print(f'  Trades: {len(out):,}  Win%: {wins/len(out)*100:.1f}%')
    print(f'  Net $: ${out["Net_$"].sum():,.0f}   Max DD: ${dd:,.0f}')
    print(f'  -> {OUT_CSV}')


if __name__ == '__main__':
    main()
