#!/usr/bin/env python3
"""
Attribute **v2b_child** leg P&L by **Regime** (`v2b` vs `v2d`) from the adaptive 50/150 CSV.

This does **not** simulate “adaptive + children” end‑to‑end — it joins rows on
``Date`` + ``Trade_Direction`` so each **child** trade inherits the regime label
recorded for that canonical adaptive leg (same session structure).

Inputs:
  --adaptive  default: mnq/v2d/mnq_orb_results_adaptive_50_150.csv
  --child     default: ./mnq_orb_open_limit_v2b_child.csv

Usage::

  cd potions/mnq/case_studies/v2b_child
  python3 report_adaptive_v2bc.py
  python3 report_adaptive_v2bc.py --child mnq_orb_open_limit_v2b_child_3max.csv
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
_MNQ = _HERE.parent.parent
ADAPT_DEFAULT = _MNQ / 'v2d' / 'mnq_orb_results_adaptive_50_150.csv'
CHILD_DEFAULT = _HERE / 'mnq_orb_open_limit_v2b_child.csv'


def norm_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s).dt.strftime('%Y-%m-%d')


HELP_EPILOG = """\
Example runs:
  cd potions/mnq/case_studies/v2b_child
  python3 report_adaptive_v2bc.py
  python3 report_adaptive_v2bc.py --child mnq_orb_open_limit_v2b_child_3max.csv
  python3 report_adaptive_v2bc.py --adaptive ../../v2d/mnq_orb_results_adaptive_50_150.csv \\
      --child mnq_orb_open_limit_v2b_child.csv

Outputs:
  Stdout only (no file): overlap counts (child vs adaptive CSV keys), Σ Net_$ splits,
    groupby Regime tables — diagnostic join, not a unified simulator.
"""


def main() -> int:
    ap = argparse.ArgumentParser(
        description='Regime attribution for v2b_child CSV',
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument('--adaptive', type=str, default=str(ADAPT_DEFAULT))
    ap.add_argument('--child', type=str, default=str(CHILD_DEFAULT))
    args = ap.parse_args()

    pa, pc = Path(args.adaptive), Path(args.child)
    if not pa.is_file():
        raise SystemExit(f'Missing adaptive CSV: {pa}')
    if not pc.is_file():
        raise SystemExit(f'Missing child CSV: {pc}')

    ad = pd.read_csv(pa)
    ch = pd.read_csv(pc)

    keys = ['Date', 'Trade_Direction']
    ad['Date'] = norm_date(ad['Date'])
    ch['Date'] = norm_date(ch['Date'])

    base = ad[keys + ['Regime', 'Net_$']].rename(columns={'Net_$': 'Net_adaptive_canon'})
    m = ch.merge(base, on=keys, how='left')

    net_c = m['Net_$'].astype(float)
    has_regime = m['Regime'].notna()
    matched_net = net_c[has_regime].sum()
    orphan_net = net_c[~has_regime].sum()

    sk = set(zip(ch['Date'], ch['Trade_Direction']))
    ak = set(zip(ad['Date'], ad['Trade_Direction']))
    only_adaptive = len(ak - sk)

    print('=== Universe overlap (Date + Trade_Direction) ===')
    print(f'  child legs:           {len(ch):,}')
    print(f'  adaptive legs:        {len(ad):,}')
    print(f'  adaptive-only keys:   {only_adaptive:,}   (no child row for join)')
    print(f'  matched (both):       {has_regime.sum():,}   Σ Net_$ {matched_net:,.2f}')
    print(f'  child-only (no row):  {(~has_regime).sum():,}   Σ Net_$ {orphan_net:,.2f}')
    print()

    print('=== v2b_child Σ Net_$ (full child CSV) ===')
    print(f'  {net_c.sum():,.2f}  (n={len(m)})')
    print()

    sub = m.dropna(subset=['Regime'])
    g = sub.groupby('Regime')['Net_$'].agg(['sum', 'count', 'mean'])
    print('=== Σ Net_$ by Regime (labels exist **only** on matched legs above) ===')
    print(g.to_string(float_format=lambda x: f'{x:,.2f}'))
    print()

    tot_ad = sub.groupby('Regime')['Net_adaptive_canon'].sum()
    tot_ch = sub.groupby('Regime')['Net_$'].sum()
    delta = tot_ch - tot_ad
    tab = pd.DataFrame({'Σ_canon_adaptive': tot_ad, 'Σ_v2b_child': tot_ch, 'Δ_child_minus_canon': delta})
    print('=== Per regime: canon adaptive vs v2b_child on same legs ===')
    print(tab.to_string(float_format=lambda x: f'{x:,.2f}'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
