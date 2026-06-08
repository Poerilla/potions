#!/usr/bin/env python3
"""
Generate the adaptive MA-cross (50/150) switching trade log for MNQ.

For each trading day:
  - Read the prior day's daily 50-day vs 150-day MA relationship.
  - If 50 > 150 -> include v2b trades for that day (regime='v2b').
  - Else        -> include v2d trades for that day (regime='v2d').

Outputs a single CSV with all trades plus regime/MA context columns
suitable for joint validation, statistical analysis, and Excel export.

Output: mnq/v2d/mnq_orb_results_adaptive_50_150.csv

Unified intraday sim (**v2b / v2d + optional scale‑ins on both arms**): mnq/v2d/orb_adaptive_50_150_child.py
"""
from pathlib import Path

import argparse
import databento as db
import pandas as pd


DAILY_DBN = '/home/tester/hsm/potions/mnq/raw/glbx-mdp3-20100606-20260308.ohlcv-1d.dbn.zst'
V2B_CSV = '/home/tester/hsm/potions/mnq/mnq_orb_results_stops.csv'
V2D_CSV = '/home/tester/hsm/potions/mnq/v2d/mnq_orb_results_v2d.csv'
OUT_CSV = Path(
    '/home/tester/hsm/potions/mnq/v2d/mnq_orb_results_adaptive_50_150.csv')

FAST = 50
SLOW = 150


BUILD_ADAPTIVE_EPILOG = """\
Example run:
  cd potions/mnq/v2d
  python3 build_adaptive_trades.py
  python3 build_adaptive_trades.py --out /tmp/adaptive_50_150_custom.csv

Prerequisites:
  Existing MNQ v2b CSV (step2) and v2d CSV (step2_preplaced_stops_v2d_fade) at paths in script.

Outputs:
  CSV (--out): all trades from stitched regimes with columns Date, Regime,
    MA_fast_prev, MA_slow_prev, plus copied trade columns and cumulative_* .
  Stdout: regime day counts, Σ Net_$, win rate, max DD, year-by-year table.
"""


def daily_close():
    store = db.DBNStore.from_file(DAILY_DBN)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')].copy()
    df['date'] = pd.to_datetime(df['ts_event']).dt.date
    fm = df.loc[df.groupby('date')['volume'].idxmax()]
    return fm.set_index('date').sort_index()['close']


def main():
    ap = argparse.ArgumentParser(
        description=(
            'Build adaptive 50/150 stitched trade log (prior-day MA cross selects v2b vs v2d rows per date).'
        ),
        epilog=BUILD_ADAPTIVE_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        '--out',
        type=str,
        default=str(OUT_CSV),
        help='Output adaptive CSV path (default: mnq/v2d/mnq_orb_results_adaptive_50_150.csv)',
    )
    args = ap.parse_args()
    out_path = Path(args.out)

    print(f"Building adaptive {FAST}/{SLOW} switching trade log ...")
    close = daily_close()
    ma_fast = close.rolling(FAST).mean()
    ma_slow = close.rolling(SLOW).mean()
    # Causal: today's regime uses YESTERDAY's MAs
    regime_v2b = (ma_fast > ma_slow).shift(1).fillna(True)

    v2b = pd.read_csv(V2B_CSV)
    v2d = pd.read_csv(V2D_CSV)
    for d in (v2b, v2d):
        d['Date'] = pd.to_datetime(d['Date']).dt.date

    rows = []
    all_dates = sorted(set(v2b['Date']) | set(v2d['Date']))
    n_v2b_days = n_v2d_days = 0
    for date in all_dates:
        if date not in regime_v2b.index:
            continue
        is_v2b = bool(regime_v2b.loc[date])
        ma_f = ma_fast.loc[date] if date in ma_fast.index else None
        ma_s = ma_slow.loc[date] if date in ma_slow.index else None
        src = v2b if is_v2b else v2d
        day_trades = src[src['Date'] == date]
        if is_v2b:
            n_v2b_days += 1
        else:
            n_v2d_days += 1
        for _, t in day_trades.iterrows():
            row = t.to_dict()
            row['Regime'] = 'v2b' if is_v2b else 'v2d'
            row['MA_fast_prev'] = round(ma_f, 2) if ma_f else None
            row['MA_slow_prev'] = round(ma_s, 2) if ma_s else None
            rows.append(row)

    df = pd.DataFrame(rows)
    df['Cumulative_$'] = df['Net_$'].cumsum().round(2)
    df['Cumulative_PL'] = df['Trade_PL'].cumsum().round(6)
    cols_first = ['Date', 'Regime', 'MA_fast_prev', 'MA_slow_prev']
    df = df[cols_first + [c for c in df.columns if c not in cols_first]]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)

    # Summary
    print(f"\n  Wrote {len(df):,} adaptive trades -> {out_path}")
    print(
        f"  Days in v2b regime: {n_v2b_days}  ({n_v2b_days/(n_v2b_days+n_v2d_days)*100:.1f}%)")
    print(
        f"  Days in v2d regime: {n_v2d_days}  ({n_v2d_days/(n_v2b_days+n_v2d_days)*100:.1f}%)")
    print(f"  Total Net $/MNQ: ${df['Net_$'].sum():,.2f}")
    wins = (df['Trade_PL'] > 0).sum()
    print(f"  Win rate: {wins/len(df)*100:.1f}%   "
          f"({wins} wins / {len(df)-wins} losses+EOD)")
    eq = df['Net_$'].cumsum()
    print(f"  Max realized DD: ${(eq - eq.cummax()).min():,.2f}")

    # Year-by-year
    df['Year'] = pd.to_datetime(df['Date']).dt.year
    yr = df.groupby('Year').agg(
        Trades=('Net_$', 'size'),
        v2b_trades=('Regime', lambda x: (x == 'v2b').sum()),
        v2d_trades=('Regime', lambda x: (x == 'v2d').sum()),
        Win_pct=('Trade_PL', lambda x: (x > 0).mean() * 100),
        NetUSD=('Net_$', 'sum'),
    )
    yr['Win_pct'] = yr['Win_pct'].round(1)
    yr['NetUSD'] = yr['NetUSD'].round(0).astype(int)
    print(f"\n  Year-by-year:")
    print(yr.to_string())


if __name__ == '__main__':
    main()
