#!/usr/bin/env python3
"""
v2e — v2b breakout strategy with HH/LL daily bias filter.

Bias rule (computed at session open from daily MNQ candles):
  - HH yesterday   = yesterday_high > day-before_high  (took out prior high)
  - LL yesterday   = yesterday_low  < day-before_low   (took out prior low)
  - Bullish bias   = HH AND NOT LL  (clean higher high)
  - Bearish bias   = LL AND NOT HH  (clean lower low)
  - Both / Neither = mixed (engulfing or inside day)

Filter modes tested:
  1. STRICT     — only trade direction aligned with bias; mixed days skipped
  2. STRICT_M   — only trade aligned direction; mixed days = trade BOTH (no filter)
  3. LIBERAL    — trade aligned direction always; mixed days = trade BOTH

Applied to v2b trade list. Each trade is kept if its direction matches
the day's allowed direction(s); otherwise discarded.

Output:
  mnq/v2d/v2e_bias_filter.csv
  + summary print
"""
from pathlib import Path

import databento as db
import pandas as pd

DAILY_DBN = '/home/tester/hsm/potions/mnq/raw/glbx-mdp3-20100606-20260308.ohlcv-1d.dbn.zst'
V2B_CSV   = '/home/tester/hsm/potions/mnq/mnq_orb_results_stops.csv'
OUT_DIR   = Path('/home/tester/hsm/potions/mnq/v2d')


def load_daily_hl():
    store = db.DBNStore.from_file(DAILY_DBN)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')].copy()
    df['date'] = pd.to_datetime(df['ts_event']).dt.date
    fm = df.loc[df.groupby('date')['volume'].idxmax()]
    return fm.set_index('date').sort_index()[['high', 'low']]


def compute_bias(daily):
    """For each day, the bias REGIME for trading TODAY based on yesterday's
    HH/LL relative to day-before-yesterday. (Causally honest: today's
    decision uses only data through yesterday's close.)"""
    prior_high = daily['high'].shift(1)   # yesterday's high
    prior_low  = daily['low'].shift(1)    # yesterday's low
    pp_high    = daily['high'].shift(2)   # day-before-yesterday's high
    pp_low     = daily['low'].shift(2)    # day-before-yesterday's low
    hh = prior_high > pp_high
    ll = prior_low  < pp_low
    bias = pd.Series('mixed', index=daily.index)
    bias[hh & ~ll] = 'bull'
    bias[ll & ~hh] = 'bear'
    bias[hh & ll]  = 'engulf'
    bias[~hh & ~ll] = 'inside'
    return bias


def apply_filter(v2b, bias, mode='STRICT'):
    """Return filtered trade list and per-mode stats."""
    df = v2b.copy()
    df['Bias'] = df['Date'].map(bias.to_dict())
    keep = pd.Series(False, index=df.index)
    if mode == 'STRICT':
        keep |= (df['Bias'] == 'bull')   & (df['Trade_Direction'] == 'Long')
        keep |= (df['Bias'] == 'bear')   & (df['Trade_Direction'] == 'Short')
        # mixed/inside/engulf: skip
    elif mode == 'STRICT_M':
        keep |= (df['Bias'] == 'bull')   & (df['Trade_Direction'] == 'Long')
        keep |= (df['Bias'] == 'bear')   & (df['Trade_Direction'] == 'Short')
        keep |= df['Bias'].isin(['engulf', 'inside'])  # take both directions on mixed
    elif mode == 'LIBERAL':
        # Same as STRICT_M (the difference vs STRICT is mixed-day handling)
        keep |= (df['Bias'] == 'bull')   & (df['Trade_Direction'] == 'Long')
        keep |= (df['Bias'] == 'bear')   & (df['Trade_Direction'] == 'Short')
        keep |= df['Bias'].isin(['engulf', 'inside'])
    return df[keep].copy()


def stats(df, label):
    if len(df) == 0:
        return {'config': label, 'trades': 0, 'win_pct': 0,
                'pts': 0, 'usd': 0, 'max_dd': 0, 'sharpe': 0}
    df = df.sort_values('Date').reset_index(drop=True)
    eq = df['Net_$'].cumsum()
    dd = eq - eq.cummax()
    sigma = df['Net_$'].std()
    sharpe = df['Net_$'].mean() / sigma * (252 / max(df['Date'].nunique(), 1)) ** 0.5 if sigma > 0 else 0
    # Use sqrt(N_trades_per_yr) for sharpe
    return {
        'config': label,
        'trades': len(df),
        'win_pct': (df['Trade_PL'] > 0).mean() * 100,
        'pts':     df['Trade_PL'].sum(),
        'usd':     df['Net_$'].sum(),
        'max_dd':  abs(dd.min()),
        'sharpe':  sharpe,
    }


def main():
    daily = load_daily_hl()
    bias  = compute_bias(daily)
    print(f"Daily bias distribution (1 row per day, {len(bias):,} days):")
    print(bias.value_counts().to_string())
    print()

    v2b = pd.read_csv(V2B_CSV)
    v2b['Date'] = pd.to_datetime(v2b['Date']).dt.date
    print(f"Loaded {len(v2b):,} v2b trades  ({v2b['Date'].min()} -> {v2b['Date'].max()})")

    # By-bias breakdown of full v2b
    v2b['Bias'] = v2b['Date'].map(bias.to_dict())
    print("\nv2b trades by bias regime:")
    grp = v2b.groupby(['Bias', 'Trade_Direction']).agg(
        n=('Trade_PL', 'size'),
        wins=('Trade_PL', lambda s: (s > 0).sum()),
        pts=('Trade_PL', 'sum'),
        usd=('Net_$', 'sum'),
    )
    grp['win%'] = (grp['wins']/grp['n']*100).round(1)
    print(grp[['n','wins','win%','pts','usd']].to_string())

    rows = [stats(v2b, 'v2b alone (full)')]
    for mode in ('STRICT', 'STRICT_M', 'LIBERAL'):
        flt = apply_filter(v2b, bias, mode)
        rows.append(stats(flt, f'v2e {mode}'))

    # Save STRICT filtered trades for inspection
    strict = apply_filter(v2b, bias, 'STRICT')
    strict.sort_values('Date').to_csv(OUT_DIR / 'v2e_bias_filter.csv', index=False)

    print("\n" + "=" * 90)
    print(f"{'Config':<22} {'Trades':>8} {'Win %':>7} {'Pts':>8} "
          f"{'Net $':>10} {'Max DD':>10}")
    print("-" * 90)
    for r in rows:
        print(f"{r['config']:<22} {r['trades']:>8} {r['win_pct']:>6.1f}% "
              f"{r['pts']:>+8.1f} ${r['usd']:>+8,.0f} ${r['max_dd']:>8,.0f}")

    # Year-by-year for STRICT
    strict['Year'] = pd.to_datetime(strict['Date']).dt.year
    yr = strict.groupby('Year').agg(
        n=('Net_$', 'size'),
        wins=('Trade_PL', lambda s: (s > 0).sum()),
        usd=('Net_$', 'sum'),
    )
    yr['win%'] = (yr['wins']/yr['n']*100).round(1)
    yr['usd_3'] = (yr['usd'] * 3).round(0).astype(int)
    print("\n=== v2e STRICT year-by-year ===")
    print(yr[['n','win%','usd','usd_3']].rename(columns={'usd':'Net_$/MNQ','usd_3':'Net_$/3MNQ'}).to_string())

    # Compare on the manual window
    manual_window = (v2b['Date'] >= pd.to_datetime('2024-01-26').date()) & \
                    (v2b['Date'] <= pd.to_datetime('2025-05-16').date())
    v2b_w = v2b[manual_window].copy()
    strict_w = apply_filter(v2b_w, bias, 'STRICT')
    print("\n=== Manual window (2024-01-26 -> 2025-05-16) ===")
    for label, x in [
        ('Manual (live)',                {'trades': 173, 'win_pct': 76.3, 'pts': 9131.25, 'usd': 9131.25*2}),
        ('v2b in window',                stats(v2b_w, 'v2b in window')),
        ('v2e STRICT in window',         stats(strict_w, 'v2e STRICT')),
    ]:
        if isinstance(x, dict) and 'config' in x:
            print(f"  {label:<26} {x['trades']:>4} trades  {x['win_pct']:>5.1f}% win  "
                  f"{x['pts']:>+8.1f} pts  ${x['usd']:>+8,.0f}/MNQ  ${x['usd']*3:>+10,.0f}/3MNQ")
        else:
            print(f"  {label:<26} {x['trades']:>4} trades  {x['win_pct']:>5.1f}% win  "
                  f"{x['pts']:>+8.1f} pts  ${x['usd']:>+8,.0f}/MNQ  ${x['usd']*3:>+10,.0f}/3MNQ")


if __name__ == '__main__':
    main()
