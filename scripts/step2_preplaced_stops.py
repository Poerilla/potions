#!/usr/bin/env python3
"""
Model C (v2b) — Pre-placed OCO stop-entry backtest with BRACKET-THEN-REVERSE.

At the end of the **opening range** (default 9:30–9:45 ET, 15 min), place
a buy-stop at `range_high + 1 tick` and a sell-stop at
`range_low - 1 tick` as an OCO pair. Use `--open-range-minutes` for e.g.
5 min (9:30–9:35). Stops are active from the first 1m bar at/after range
end through 15:55. Whichever stop triggers first fills. Attach
bracket exit (target = entry ± range, stop = opposite range boundary).

After the first trade closes (Win, Loss, or EOD), re-arm ONLY the stop
in the OPPOSITE direction. The same-direction stop is NOT re-armed, so
at most ONE Long and ONE Short can fire per day. Force-close at 15:55.

Why "bracket-then-reverse"?
  - The original v2a backtest re-armed both stops after every trade.
    On winning days that price kept extending in one direction, the same
    direction stop would "fire" again at the original trigger price even
    though current market price was already far past it — an impossible
    fill in real execution.
  - v2b solves this by only re-arming the opposite-side stop, ensuring
    every fill price is achievable in live trading via Tradovate or any
    stop-market routing path.

This is the LIVE EXECUTION MODEL — orders rest at the exchange from the
**range close** time onward.

Uses 1-minute DBN data for accurate intrabar fill simulation. Includes
1-tick slippage on entries to mirror realistic stop-market fills.

Outputs:
  mnq/mnq_orb_results_stops.csv  (or equivalent based on --product)
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
DEFAULT_OPEN_RANGE_MIN = 15      # 9:30-9:45; override with --open-range-minutes
EOD_CUTOFF = time(15, 55)          # force-close after this
MAX_TRADES_PER_DAY = 2


def open_range_end_time(minutes: int) -> time:
    """9:30 NY + `minutes` (opening range end, exclusive in bar filter)."""
    t = pd.Timestamp('2000-01-01 09:30:00') + pd.Timedelta(minutes=minutes)
    return t.time()

PRODUCTS = {
    'MNQ': {
        'tick': 0.25,
        'mult': 2.00,
        'dbn': '/home/tester/hsm/potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst',
        'out': '/home/tester/hsm/potions/mnq/mnq_orb_results_stops.csv',
        'history_start': pd.Timestamp('2021-03-04').date(),
    },
    'MYM': {
        'tick': 1.00,
        'mult': 0.50,
        'dbn': '/home/tester/hsm/potions/mym/raw/glbx-mdp3-20100606-20260308.ohlcv-1m (mym).dbn.zst',
        'out': '/home/tester/hsm/potions/mym/mym_orb_results_stops.csv',
        'history_start': None,
    },
    'NQ': {
        'tick': 0.25,
        'mult': 20.00,
        'dbn': '/home/tester/hsm/potions/nq/raw/glbx-mdp3-20100606-20260308.ohlcv-1m.dbn.zst',
        'out': '/home/tester/hsm/potions/nq/nq_orb_results_stops.csv',
        'history_start': None,   # use full history (~2010-2026)
    },
    'ES': {
        'tick': 0.25,
        'mult': 50.00,
        'dbn': '/home/tester/hsm/potions/es/raw/glbx-mdp3-20100606-20260425.ohlcv-1m.dbn.zst',
        'out': '/home/tester/hsm/potions/es/es_orb_results_stops.csv',
        'history_start': None,
    },
}

FEE_RT = 1.50                      # round-turn all-in commission + exchange fees


STEP2_HELP_EPILOG = """\
Example runs:
  cd potions/scripts
  python3 step2_preplaced_stops.py --product MNQ
  python3 step2_preplaced_stops.py --product MNQ --slip-ticks 1 \\
      --open-range-minutes 15 --out ../mnq/mnq_orb_results_stops.csv
  python3 step2_preplaced_stops.py --product MNQ --open-range-minutes 5

Outputs:
  CSV (--out): defaults to mnq/mnq_orb_results_stops.csv for MNQ; columns Date,
    Symbol, Range_*, Trade_Direction, Entry/Exit_Price, Trade_PL, Net_$,
    Result, cumulative columns.
  If open-range-minutes != 15 and --out omitted: sibling filename *_Xm.csv next to default.
  Stdout: row count, win stats, Σ pts / Net_$ summary (tail of script).
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

    # front-month per day
    fm = (df.groupby(['date', 'symbol'])['volume']
            .sum().groupby(level='date').idxmax()
            .apply(lambda x: x[1]).to_dict())
    df = df[df.apply(lambda r: r['symbol'] == fm.get(r['date']), axis=1)]
    df = df[(df['t'] >= RTH_START) & (df['t'] < RTH_END)]

    if cfg['history_start'] is not None:
        df = df[df['date'] >= cfg['history_start']]

    df = df.set_index('ts_event').sort_index()
    print(f"  {len(df):,} 1-min RTH front-month bars")
    return df


def simulate_day(rh, rl, range_val, day_bars, tick, slip_ticks=1):
    """
    Simulate one trading day using pre-placed OCO stops with
    bracket-then-reverse logic.

    On the FIRST trade, both stops are armed (long at RH+1tick, short
    at RL-1tick) as an OCO pair.

    After the first trade closes (Win/Loss/EOD), only the stop in the
    OPPOSITE direction is re-armed. The same-side stop is NOT re-armed
    because the simulator can't trust the original trigger price once
    market price has moved past it (the v2a bug).

    So at most 1 Long and 1 Short can fire per day, in either order.
    """
    long_trigger = rh + tick
    short_trigger = rl - tick
    long_entry = long_trigger + slip_ticks * tick
    short_entry = short_trigger - slip_ticks * tick

    # `arm_long` and `arm_short` track which stops are currently active.
    # Both armed at start; after a trade fires/closes, only the opposite
    # of the closed trade's direction stays armed.
    arm_long = True
    arm_short = True

    phase = 'ARMED'        # ARMED -> IN -> ARMED -> IN -> DONE
    direction = None
    entry = target = stop = None
    trades = []
    traded_dirs = set()    # track which directions have already fired
    last_bar = None

    for _, bar in day_bars.iterrows():
        last_bar = bar
        h, l = bar['high'], bar['low']
        bar_time = bar.name.time() if hasattr(bar.name, 'time') else None

        if phase == 'ARMED' and bar_time is not None and bar_time >= EOD_CUTOFF:
            break

        if phase == 'ARMED':
            long_hit = arm_long and h >= long_trigger
            short_hit = arm_short and l <= short_trigger

            if long_hit and short_hit:
                # Both triggered this minute — crude heuristic using open price
                mid = (rh + rl) / 2
                if bar['open'] >= mid:
                    direction, entry = 'Long', long_entry
                    target, stop = rh + range_val, rl
                else:
                    direction, entry = 'Short', short_entry
                    target, stop = rl - range_val, rh
                phase = 'IN'
            elif long_hit:
                direction, entry = 'Long', long_entry
                target, stop = rh + range_val, rl
                phase = 'IN'
            elif short_hit:
                direction, entry = 'Short', short_entry
                target, stop = rl - range_val, rh
                phase = 'IN'

        if phase == 'IN':
            # Pessimistic: assume stop hits before target if both occur same minute
            closed = False
            if direction == 'Long':
                if l < stop:
                    trades.append(('Long', entry, stop, 'Loss'))
                    closed = True
                elif h >= target:
                    trades.append(('Long', entry, target, 'Win'))
                    closed = True
            else:
                if h > stop:
                    trades.append(('Short', entry, stop, 'Loss'))
                    closed = True
                elif l <= target:
                    trades.append(('Short', entry, target, 'Win'))
                    closed = True

            if closed:
                traded_dirs.add(direction)
                # Bracket-then-reverse: disarm the side just traded,
                # only the opposite-side stop stays armed for a 2nd trade.
                if direction == 'Long':
                    arm_long = False
                else:
                    arm_short = False
                phase, direction = 'ARMED', None

                if not (arm_long or arm_short) or len(trades) >= MAX_TRADES_PER_DAY:
                    phase = 'DONE'
                    break

    # EOD close if still in a trade
    if phase == 'IN' and last_bar is not None:
        eod_price = last_bar['close']
        if direction == 'Long':
            res = 'EOD-Win' if eod_price > entry else 'EOD-Loss'
        else:
            res = 'EOD-Win' if eod_price < entry else 'EOD-Loss'
        trades.append((direction, entry, eod_price, res))

    return trades


def main():
    ap = argparse.ArgumentParser(
        description='Pre-placed OCO stops (v2b) backtest — README canon.',
        epilog=STEP2_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument('--product', choices=list(PRODUCTS.keys()), default='MNQ')
    ap.add_argument('--slip-ticks', type=int, default=1,
                    help='Entry slippage in ticks beyond the stop trigger')
    ap.add_argument('--open-range-minutes', type=int, default=DEFAULT_OPEN_RANGE_MIN,
                    metavar='M',
                    help='Opening range = 9:30 ET for M minutes (default 15). E.g. 5 => 9:30-9:35.')
    ap.add_argument('--out', type=str, default=None,
                    help='Output CSV (default: product path, or auto suffix _M if M != 15)')
    args = ap.parse_args()

    if not (1 <= args.open_range_minutes <= 150):
        raise SystemExit('--open-range-minutes must be 1..150 (sanity)')

    cfg = PRODUCTS[args.product]
    tick = cfg['tick']
    mult = cfg['mult']

    range_end = open_range_end_time(args.open_range_minutes)

    if args.out:
        out_path = Path(args.out)
    else:
        base = Path(cfg['out'])
        if args.open_range_minutes == DEFAULT_OPEN_RANGE_MIN:
            out_path = base
        else:
            out_path = base.parent / f'{base.stem}_{args.open_range_minutes}m{base.suffix}'

    df = load_one_min(args.product)
    _re = pd.Timestamp('2000-01-01 09:30:00') + pd.Timedelta(
        minutes=args.open_range_minutes)
    print(f"Opening range: 9:30–{_re.strftime('%H:%M')} ET"
          f" ({args.open_range_minutes} min)  |  range_end t={range_end}  |  {out_path}")

    results = []
    for day, day_df in df.groupby('date'):
        day_df = day_df.sort_index()
        range_bars = day_df[day_df['t'] < range_end]
        if range_bars.empty:
            continue
        rh, rl = range_bars['high'].max(), range_bars['low'].min()
        rv = rh - rl
        if rv <= 0:
            continue

        trade_bars = day_df[day_df['t'] >= range_end]
        if trade_bars.empty:
            continue

        day_trades = simulate_day(
            rh, rl, rv, trade_bars, tick, args.slip_ticks)
        sym = trade_bars.iloc[0]['symbol']
        for d, entry, exit_p, res in day_trades:
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
                'Net_$': round(pl * mult - FEE_RT, 2),
                'Result': res,
            })

    out = pd.DataFrame(results)
    out['Cumulative_PL'] = out['Trade_PL'].cumsum().round(6)
    out['Cumulative_$'] = out['Net_$'].cumsum().round(2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    print(f"\nWrote {len(out):,} trades -> {out_path}")

    wins = (out['Trade_PL'] > 0).sum()
    print(f"Win rate: {wins/len(out)*100:.1f}%  "
          f"Total P/L: {out['Trade_PL'].sum():.0f} pts  "
          f"Net $ @ 1 ctr: ${out['Net_$'].sum():,.0f}")

    eq = out['Net_$'].cumsum()
    dd = eq - eq.cummax()
    print(f"Max realized DD: ${dd.min():,.2f}")


if __name__ == '__main__':
    main()
