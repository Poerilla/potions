#!/usr/bin/env python3
"""
Side-by-side: canonical MNQ **v2** stop / OCO backtest vs **v2b_child**.

Baseline CSV (default): ``potions/mnq/mnq_orb_results_stops.csv`` from
``scripts/step2_preplaced_stops.py --product MNQ``.

Compare CSV (default): ``v2b_child/mnq_orb_open_limit_v2b_child.csv`` — tier-1 is identical when
``--max-child-adds 0``; child variants layer adds after OCO fill.

Alignment key per row: ``Date`` + ``Trade_Direction`` (max two legs/day).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

_HERE = Path(__file__).resolve().parent
_MNQ = _HERE.parent.parent
CANON_DEFAULT = _MNQ / 'mnq_orb_results_stops.csv'
CHILD_DEFAULT = _HERE / 'mnq_orb_open_limit_v2b_child.csv'


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out['Date'] = pd.to_datetime(out['Date']).dt.strftime('%Y-%m-%d')
    out['Trade_Direction'] = out['Trade_Direction'].astype(str)
    return out


def load_pair(path_canon: Path, path_child: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    a = normalize(pd.read_csv(path_canon))
    b = normalize(pd.read_csv(path_child))
    keys = ['Date', 'Trade_Direction']
    ka = a.set_index(keys).sort_index()
    kb = b.set_index(keys).sort_index()
    if not ka.index.equals(kb.index):
        missing_a = kb.index.difference(ka.index)
        missing_b = ka.index.difference(kb.index)
        raise SystemExit(
            f'Row index mismatch: only canon {len(missing_a)}, only child {len(missing_b)}. '
            'Regenerate both from same DB span.'
        )
    return ka.reset_index(), kb.reset_index()


def summarize(df: pd.DataFrame) -> dict:
    net = df['Net_$'].astype(float)
    cum = net.cumsum()
    dd = cum - cum.cummax()
    return {
        'n': len(df),
        'sum_$': net.sum(),
        'win_pct': 100.0 * (net > 0).mean(),
        'max_dd_$': dd.min(),
    }


HELP_EPILOG = """\
Example runs:
  cd potions/mnq/case_studies/v2b_child
  python3 compare_v2b_side_by_side.py
  python3 compare_v2b_side_by_side.py --canon ../../mnq/mnq_orb_results_stops.csv \\
      --child mnq_orb_open_limit_v2b_child_3max.csv

Outputs:
  Stdout: aligned Σ Net_$, win rate, max DD for canon vs child; rows where Net_$ differs.
  Requires identical Date+Trade_Direction index in both CSVs (same span / generator).
"""


def main() -> int:
    ap = argparse.ArgumentParser(
        description='Canon step2 vs v2b_child',
        epilog=HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument('--canon', type=str, default=str(CANON_DEFAULT))
    ap.add_argument('--child', type=str, default=str(CHILD_DEFAULT))
    args = ap.parse_args()
    pa, pb = Path(args.canon), Path(args.child)
    if not pa.is_file():
        raise SystemExit(f'Missing baseline CSV: {pa}')
    if not pb.is_file():
        raise SystemExit(f'Missing child CSV: {pb}')

    canon_df, child_df = load_pair(pa, pb)
    sv = summarize(canon_df)
    sc = summarize(child_df)

    net_d = child_df['Net_$'].astype(float) - canon_df['Net_$'].astype(float)

    print('=== MNQ step2 (OCO stops, README canon)  vs  v2b_child ===\n')
    print(f'Baseline: {pa}')
    print(f'Compare:  {pb}')
    print(f'Legs:     {sv["n"]}\n')

    hdr = f'{"Metric":<26} {"step2 canon":>14} {"v2b_child":>14} {"Δ":>16}'
    print(hdr)
    print('-' * len(hdr))
    print(f'{"Σ Net_$":<26} {sv["sum_$"]:>14,.2f} {sc["sum_$"]:>14,.2f} {sc["sum_$"] - sv["sum_$"]:>16,.2f}')
    print(f'{"Win rate % (>0)":<26} {sv["win_pct"]:>13.1f}% {sc["win_pct"]:>13.1f}% {sc["win_pct"] - sv["win_pct"]:>15.1f} pp')
    print(f'{"Max DD cum Net_$":<26} {sv["max_dd_$"]:>14,.2f} {sc["max_dd_$"]:>14,.2f} {sc["max_dd_$"] - sv["max_dd_$"]:>16,.2f}')

    if 'Child_Add' in child_df.columns:
        print(f'\nChild legs (Child_Add=True): {child_df["Child_Add"].sum()}  ({child_df["Child_Add"].mean()*100:.1f}%)')
        ch = child_df['Child_Add'].astype(bool)
        if ch.any():
            print(f'Sum (child Net − canon Net) on those rows: {net_d[ch].sum():,.2f}')

    nd = net_d.abs() > 1e-9
    print(f'\nLegs where Net_$ differs from canon: {int(nd.sum())}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
