#!/usr/bin/env python3
"""
Cross-check the manual live trade log against the v1b (close-based + limit
retest) backtest CSV for the same date window.

Manual CSV columns (ticks at 1 MNQ tick = 0.25 pts, $0.50/tick):
  Date (DD/MM/YYYY), Day, SL (ticks), TP (ticks), DD (ticks),
  DD Amount (3-ctr $), W/L, Scaling, P/L (3-ctr $), R:R, Equity,
  Range (ticks), DD/Range, Trade Direction (L/S), Bias Aligned, Runner
  Contracts: 3
"""
from pathlib import Path

import pandas as pd

MANUAL = '/home/tester/hsm/potions/mnq/raw/Super Trend + ICT - Openning Range.csv'
V1B    = '/home/tester/hsm/potions/mnq/mnq_orb_results_fixed.csv'
V2B    = '/home/tester/hsm/potions/mnq/mnq_orb_results_stops.csv'
ADAPT  = '/home/tester/hsm/potions/mnq/v2d/mnq_orb_results_adaptive_50_150.csv'

CONTRACTS = 3
TICK = 0.25       # MNQ tick size in points
DOLLAR_PER_TICK = 0.50  # per contract


def parse_manual():
    df = pd.read_csv(MANUAL)
    # Strip whitespace from column names
    df.columns = [c.strip() for c in df.columns]
    df = df[df['Date'].notna() & (df['Date'].str.match(r'\d{1,2}/\d{1,2}/\d{4}'))].copy()
    df['Date'] = pd.to_datetime(df['Date'], format='%d/%m/%Y').dt.date
    # Convert ticks to points
    df['Range_pts']    = df['Range'] / 4
    df['SL_pts']       = df['SL']    / 4
    df['TP_pts']       = df['TP']    / 4
    df['DD_pts']       = df['DD']    / 4
    df['Direction']    = df['Trade Direction'].map({'L':'Long', 'S':'Short'})
    df['IsWin']        = df['W/L'].str.upper() == 'W'
    # Per-contract P/L in points = P/L_dollar / (3 contracts × $2/pt)
    # P/L column in CSV is total $ for 3 MNQ contracts at $2/pt
    df['PL_pts_per_contract'] = df['P/L'] / (CONTRACTS * 2.0)
    return df[['Date','Direction','IsWin','SL_pts','TP_pts','DD_pts','Range_pts',
                'PL_pts_per_contract','Bias Aligned']].rename(
                columns={'Bias Aligned':'BiasAligned'})


def load_backtest(path, label):
    df = pd.read_csv(path)
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    df['IsWin'] = df['Trade_PL'] > 0
    df['_src'] = label
    return df


def daily_summary(df, pl_col):
    return df.groupby('Date').agg(
        n_trades=(pl_col, 'size'),
        wins=('IsWin', 'sum'),
        net_pts=(pl_col, 'sum'),
    )


def main():
    print("Loading manual log ...")
    manual = parse_manual()
    print(f"  {len(manual)} manual trades, "
          f"{manual['Date'].min()} -> {manual['Date'].max()}")

    print("\nLoading v1b backtest (close-based + limit retest) ...")
    v1b = load_backtest(V1B, 'v1b')
    v1b_window = v1b[(v1b['Date'] >= manual['Date'].min()) &
                     (v1b['Date'] <= manual['Date'].max())].copy()
    print(f"  v1b in window: {len(v1b_window)} trades")

    print("\nLoading v2b backtest (pre-placed stops) ...")
    v2b = load_backtest(V2B, 'v2b')
    v2b_window = v2b[(v2b['Date'] >= manual['Date'].min()) &
                     (v2b['Date'] <= manual['Date'].max())].copy()
    print(f"  v2b in window: {len(v2b_window)} trades")

    print("\nLoading adaptive 50/150 backtest ...")
    adapt = load_backtest(ADAPT, 'adaptive')
    adapt_window = adapt[(adapt['Date'] >= manual['Date'].min()) &
                         (adapt['Date'] <= manual['Date'].max())].copy()
    print(f"  adaptive in window: {len(adapt_window)} trades")

    # ============================================================
    # Top-line comparison
    # ============================================================
    def s(df, pl_col):
        return {
            'trades': len(df),
            'wins':   df['IsWin'].sum(),
            'win%':   df['IsWin'].mean() * 100,
            'pts':    df[pl_col].sum(),
            'usd':    df[pl_col].sum() * 2 * CONTRACTS,
        }
    m = s(manual, 'PL_pts_per_contract')
    v1bs = s(v1b_window, 'Trade_PL')
    v2bs = s(v2b_window, 'Trade_PL')
    aps  = s(adapt_window, 'Trade_PL')

    print("\n" + "=" * 90)
    print(f"  TOP-LINE COMPARISON ({manual['Date'].min()} -> {manual['Date'].max()})")
    print("=" * 90)
    print(f"{'Source':<14} {'Trades':>8} {'Wins':>6} {'Win %':>7} "
          f"{'Net pts':>10} {'Net $ @ 3 MNQ':>16}")
    print("-" * 90)
    for label, x in [('Manual (live)', m), ('v1b backtest', v1bs),
                      ('v2b backtest', v2bs), ('Adaptive 50/150', aps)]:
        print(f"{label:<14} {x['trades']:>8} {x['wins']:>6} "
              f"{x['win%']:>6.1f}% {x['pts']:>+10.2f} ${x['usd']:>+14,.2f}")

    # ============================================================
    # Per-day match table
    # ============================================================
    print("\n" + "=" * 90)
    print("  DAY-BY-DAY MATCH (Manual vs v1b)")
    print("=" * 90)

    md = daily_summary(manual, 'PL_pts_per_contract')
    v1d = daily_summary(v1b_window, 'Trade_PL')
    v2d_ = daily_summary(v2b_window, 'Trade_PL')

    # Date set
    all_dates = sorted(set(md.index) | set(v1d.index))
    same_n_trades = same_dir_outcome = exact_outcome = both_traded = 0
    discrepancies = []

    print(f"{'Date':>12} {'M_n':>4} {'V1b_n':>5} "
          f"{'M_W':>3} {'V1b_W':>5} "
          f"{'M_pts':>8} {'V1b_pts':>9} {'D_pts':>8} {'note':<22}")
    print("-" * 90)
    for d in all_dates:
        in_m = d in md.index
        in_v = d in v1d.index
        if in_m and in_v:
            both_traded += 1
            mn = md.loc[d]; vn = v1d.loc[d]
            note = ''
            if mn['n_trades'] == vn['n_trades']:
                same_n_trades += 1
            else:
                note = f"trade_count_diff ({int(mn['n_trades'])}v{int(vn['n_trades'])})"
            if mn['wins'] == vn['wins']:
                same_dir_outcome += 1
            delta = mn['net_pts'] - vn['net_pts']
            if abs(delta) < 5:
                exact_outcome += 1
            print(f"{str(d):>12} {int(mn['n_trades']):>4} {int(vn['n_trades']):>5} "
                  f"{int(mn['wins']):>3} {int(vn['wins']):>5} "
                  f"{mn['net_pts']:>8.1f} {vn['net_pts']:>9.1f} "
                  f"{delta:>8.1f} {note:<22}")
        elif in_m:
            print(f"{str(d):>12} {int(md.loc[d,'n_trades']):>4} {'-':>5} "
                  f"{int(md.loc[d,'wins']):>3} {'-':>5} "
                  f"{md.loc[d,'net_pts']:>8.1f} {'-':>9} {'-':>8} "
                  f"{'manual_only':<22}")
        else:
            print(f"{str(d):>12} {'-':>4} {int(v1d.loc[d,'n_trades']):>5} "
                  f"{'-':>3} {int(v1d.loc[d,'wins']):>5} "
                  f"{'-':>8} {v1d.loc[d,'net_pts']:>9.1f} {'-':>8} "
                  f"{'v1b_only':<22}")

    print("\n" + "=" * 90)
    print("  AGGREGATE MATCH STATS")
    print("=" * 90)
    print(f"  Days in manual:                {len(md)}")
    print(f"  Days in v1b window:            {len(v1d)}")
    print(f"  Days both traded:              {both_traded}")
    print(f"  Days only in manual:           {len(md) - both_traded}")
    print(f"  Days only in v1b:              {len(v1d) - both_traded}")
    print(f"  Same trade count:              {same_n_trades}/{both_traded}")
    print(f"  Same #wins on day:             {same_dir_outcome}/{both_traded}")
    print(f"  Δ pts within ±5:               {exact_outcome}/{both_traded}")

    # ============================================================
    # Selectivity analysis: how would v1b/v2b/adaptive perform if
    # they only traded on the days you traded?
    # ============================================================
    print("\n" + "=" * 90)
    print("  SELECTIVITY: backtest restricted to days the human traded")
    print("=" * 90)
    manual_dates = set(manual['Date'])
    v1b_sel = v1b_window[v1b_window['Date'].isin(manual_dates)]
    v2b_sel = v2b_window[v2b_window['Date'].isin(manual_dates)]
    ad_sel  = adapt_window[adapt_window['Date'].isin(manual_dates)]
    print(f"{'Source':<22} {'Trades':>8} {'Win %':>7} {'Net pts':>10} "
          f"{'Net $ @ 3 MNQ':>16}")
    print("-" * 70)
    for label, x in [
        ('Manual (live)',         s(manual,  'PL_pts_per_contract')),
        ('v1b on traded days',    s(v1b_sel, 'Trade_PL')),
        ('v2b on traded days',    s(v2b_sel, 'Trade_PL')),
        ('Adaptive on traded days', s(ad_sel, 'Trade_PL')),
    ]:
        print(f"{label:<22} {x['trades']:>8} {x['win%']:>6.1f}% "
              f"{x['pts']:>+10.2f} ${x['usd']:>+14,.2f}")

    # Bias-aligned analysis (manual only)
    print("\n=== Manual breakdown by 'Bias Aligned' label ===")
    for tag, sub in manual.groupby('BiasAligned'):
        wr = sub['IsWin'].mean() * 100
        pts = sub['PL_pts_per_contract'].sum()
        print(f"  Bias = {str(tag):>10}: {len(sub):>3} trades, "
              f"{wr:>5.1f}% win, {pts:>+8.1f} pts/ctr "
              f"(${pts*2*CONTRACTS:>+10,.2f} @ 3 MNQ)")


if __name__ == '__main__':
    main()
