#!/usr/bin/env python3
"""
v2d — Fade-the-breakout (chop / mean-reversion) — logical inverse of v2b.

Logic:
  At 9:45 ET, watch for a break of either Range_High or Range_Low.

  After a Long breakout (price went >= RH + 1 tick), arm a fade-Short
  entry as a SELL STOP at RH - 1 tick. When price comes back down
  through RH - 1 tick, fill Short.
    - Target = RL (opposite range boundary, ~Range away)
    - SL     = RH + Range (where the v2b Long target was)

  After a Short breakout (price went <= RL - 1 tick), arm a fade-Long
  entry as a BUY STOP at RL + 1 tick. When price rises back through
  RL + 1 tick, fill Long.
    - Target = RH (opposite range boundary)
    - SL     = RL - Range (where the v2b Short target was)

  Bracket-then-reverse: max 1 fade-Long + 1 fade-Short per day.
  Force-close at 15:55.

Same outputs format as step2_preplaced_stops.py for direct comparison.
"""
import argparse
from datetime import time
from pathlib import Path

import databento as db
import pandas as pd
import pytz


NY_TZ = pytz.timezone('America/New_York')
RTH_START = time(9, 30)
RTH_END = time(16, 0)
RANGE_END = time(9, 45)
EOD_CUTOFF = time(15, 55)
MAX_TRADES_PER_DAY = 2

PRODUCTS = {
    'MNQ': {
        'tick': 0.25, 'mult': 2.00,
        'dbn': '/home/tester/hsm/potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst',
        'out': '/home/tester/hsm/potions/mnq/v2d/mnq_orb_results_v2d.csv',
        'history_start': pd.Timestamp('2021-03-04').date(),
    },
    'NQ': {
        'tick': 0.25, 'mult': 20.00,
        'dbn': '/home/tester/hsm/potions/nq/raw/glbx-mdp3-20100606-20260308.ohlcv-1m.dbn.zst',
        'out': '/home/tester/hsm/potions/nq/v2d/nq_orb_results_v2d.csv',
        'history_start': None,
    },
    'ES': {
        'tick': 0.25, 'mult': 50.00,
        'dbn': '/home/tester/hsm/potions/es/raw/glbx-mdp3-20100606-20260425.ohlcv-1m.dbn.zst',
        'out': '/home/tester/hsm/potions/es/v2d/es_orb_results_v2d.csv',
        'history_start': None,
    },
}
FEE_RT = 1.50


V2D_HELP_EPILOG = """\
Example runs:
  cd potions/scripts
  python3 step2_preplaced_stops_v2d_fade.py --product MNQ
  python3 step2_preplaced_stops_v2d_fade.py --product MNQ --slip-ticks 1

Outputs:
  CSV: MNQ defaults to mnq/v2d/mnq_orb_results_v2d.csv (see PRODUCTS dict per product).
    Columns mirror step2 (Date, Range_*, Trade_Direction, prices, Trade_PL, Net_$, Result).
  Stdout: trade count, win rate, total pts, Σ Net_$ @ 1 contract, max realized DD.
"""


def load_one_min(product):
    cfg = PRODUCTS[product]
    print(f"Loading {cfg['dbn']} ...")
    store = db.DBNStore.from_file(cfg['dbn'])
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith(product)].copy()
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY_TZ)
    df['date'] = df['ts_event'].dt.date
    df['t'] = df['ts_event'].dt.time
    fm = (df.groupby(['date', 'symbol'])['volume'].sum()
            .groupby(level='date').idxmax().apply(lambda x: x[1]).to_dict())
    df = df[df.apply(lambda r: r['symbol'] == fm.get(r['date']), axis=1)]
    df = df[(df['t'] >= RTH_START) & (df['t'] < RTH_END)]
    if cfg['history_start'] is not None:
        df = df[df['date'] >= cfg['history_start']]
    df = df.set_index('ts_event').sort_index()
    print(f"  {len(df):,} 1-min RTH front-month bars")
    return df


def simulate_day_v2d(rh, rl, range_val, day_bars, tick, slip_ticks=1):
    """v2d fade simulation. Returns list of (direction, entry, exit, result)."""
    long_break_trig  = rh + tick    # the breakout-detect levels
    short_break_trig = rl - tick

    short_fade_trig  = rh - tick    # fade entry trigger (sell stop, after long break)
    long_fade_trig   = rl + tick    # fade entry trigger (buy stop, after short break)

    short_fade_fill  = short_fade_trig - slip_ticks * tick
    long_fade_fill   = long_fade_trig  + slip_ticks * tick

    long_break_done  = False
    short_break_done = False
    armed_short_fade = False
    armed_long_fade  = False
    traded_long      = False
    traded_short     = False

    in_trade   = False
    direction  = None
    entry = target = stop = None
    trades = []
    last_bar = None

    for _, bar in day_bars.iterrows():
        last_bar = bar
        bt = bar.name.time() if hasattr(bar.name, 'time') else None
        if not in_trade and bt is not None and bt >= EOD_CUTOFF:
            break
        h, l = bar['high'], bar['low']
        breakout_this_bar = False

        # 1. Detect breakouts (only if not already detected & no trade in progress)
        if not in_trade:
            if not long_break_done and h >= long_break_trig:
                long_break_done = True
                breakout_this_bar = True
                if not traded_short:
                    armed_short_fade = True
            if not short_break_done and l <= short_break_trig:
                short_break_done = True
                breakout_this_bar = True
                if not traded_long:
                    armed_long_fade = True

        # 2. Check fade entry — skip on the bar that registered the breakout to avoid
        #    same-bar ambiguity (price had to be ABOVE the trigger for breakout to count
        #    before we can fade on a return move).
        if not in_trade and not breakout_this_bar:
            short_hit = armed_short_fade and l <= short_fade_trig
            long_hit  = armed_long_fade  and h >= long_fade_trig
            if short_hit and long_hit:
                mid = (rh + rl) / 2
                if bar['open'] >= mid:
                    direction = 'Short'
                    entry = short_fade_fill
                    target = rl
                    stop = rh + range_val
                else:
                    direction = 'Long'
                    entry = long_fade_fill
                    target = rh
                    stop = rl - range_val
                in_trade = True
                armed_short_fade = False
                armed_long_fade = False
            elif short_hit:
                direction = 'Short'
                entry = short_fade_fill
                target = rl
                stop = rh + range_val
                in_trade = True
                armed_short_fade = False
            elif long_hit:
                direction = 'Long'
                entry = long_fade_fill
                target = rh
                stop = rl - range_val
                in_trade = True
                armed_long_fade = False

        # 3. Manage trade
        if in_trade:
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
                    traded_long = True
                    armed_long_fade = False
                else:
                    traded_short = True
                    armed_short_fade = False
                in_trade = False
                direction = None
                if traded_long and traded_short:
                    break
                if len(trades) >= MAX_TRADES_PER_DAY:
                    break

    if in_trade and last_bar is not None:
        eod = last_bar['close']
        if direction == 'Long':
            res = 'EOD-Win' if eod > entry else 'EOD-Loss'
        else:
            res = 'EOD-Win' if eod < entry else 'EOD-Loss'
        trades.append((direction, entry, eod, res))

    return trades


def main():
    ap = argparse.ArgumentParser(
        description='Fade-the-breakout (v2d) — chop regime playbook.',
        epilog=V2D_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument('--product', choices=list(PRODUCTS.keys()), default='MNQ')
    ap.add_argument('--slip-ticks', type=int, default=1)
    args = ap.parse_args()

    cfg = PRODUCTS[args.product]
    tick, mult = cfg['tick'], cfg['mult']
    df = load_one_min(args.product)

    results = []
    for day, day_df in df.groupby('date'):
        day_df = day_df.sort_index()
        rng_bars = day_df[day_df['t'] < RANGE_END]
        if rng_bars.empty:
            continue
        rh, rl = rng_bars['high'].max(), rng_bars['low'].min()
        rv = rh - rl
        if rv <= 0:
            continue
        trade_bars = day_df[day_df['t'] >= RANGE_END]
        if trade_bars.empty:
            continue
        day_trades = simulate_day_v2d(rh, rl, rv, trade_bars, tick, args.slip_ticks)
        sym = trade_bars.iloc[0]['symbol']
        for d, entry, exit_p, res in day_trades:
            pl = (exit_p - entry) if d == 'Long' else (entry - exit_p)
            results.append({
                'Date': day, 'Day_of_Week': day.strftime('%A'), 'Symbol': sym,
                'Range_High': rh, 'Range_Low': rl, 'Range': rv,
                'Trade_Direction': d, 'Entry_Price': entry, 'Exit_Price': exit_p,
                'Trade_PL': round(pl, 6),
                'Net_$': round(pl * mult - FEE_RT, 2),
                'Result': res,
            })

    out = pd.DataFrame(results)
    out['Cumulative_PL'] = out['Trade_PL'].cumsum().round(6)
    out['Cumulative_$'] = out['Net_$'].cumsum().round(2)
    Path(cfg['out']).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(cfg['out'], index=False)

    wins = (out['Trade_PL'] > 0).sum()
    eq = out['Net_$'].cumsum()
    dd = eq - eq.cummax()
    print(f"\nWrote {len(out):,} trades -> {cfg['out']}")
    print(f"Win rate: {wins/max(len(out),1)*100:.1f}%  "
          f"Total P/L: {out['Trade_PL'].sum():.0f} pts  "
          f"Net $ @ 1 ctr: ${out['Net_$'].sum():,.0f}")
    print(f"Max realized DD: ${dd.min():,.2f}")


if __name__ == '__main__':
    main()
