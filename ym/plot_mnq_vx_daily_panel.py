#!/usr/bin/env python3
"""
Two-panel PNG: **MNQ daily** (close + MA50 / MA150) and **VX front daily** (close).

Inputs:

- ``mnq/mnq_daily.csv`` (date, open, high, low, close, …) — same layout as other potions dailies.
- ``vx/vx_front_daily.csv`` — run ``vx/export_vx_front_daily.py`` with **Python 3.10+**
  and ``databento>=0.77`` if your VX drop is DBN v3 (see that script’s docstring).

Default output: ``ym/mnq_vx_daily_ma50_150.png`` (next to this script’s parent).

Example::

  cd potions/ym
  python3 plot_mnq_vx_daily_panel.py
  python3 plot_mnq_vx_daily_panel.py --start 2020-01-01 --out ./my_panel.png
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use('Agg')

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

YM_ROOT = Path(__file__).resolve().parent
POTIONS_ROOT = YM_ROOT.parent
DEFAULT_MNQ = POTIONS_ROOT / 'mnq' / 'mnq_daily.csv'
DEFAULT_VX = POTIONS_ROOT / 'vx' / 'vx_front_daily.csv'
DEFAULT_OUT = YM_ROOT / 'mnq_vx_daily_ma50_150.png'


def read_daily_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df['date'] = pd.to_datetime(df['date'])
    for col in ('open', 'high', 'low', 'close'):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df.sort_values('date').reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mnq-csv', type=Path, default=DEFAULT_MNQ)
    ap.add_argument('--vx-csv', type=Path, default=DEFAULT_VX)
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    ap.add_argument('--start', type=str, default=None, help='Optional YYYY-MM-DD lower bound (inclusive)')
    ap.add_argument('--figsize', type=str, default='14,9', help='W,H inches')
    ap.add_argument('--dpi', type=int, default=120)
    args = ap.parse_args()

    if not args.mnq_csv.is_file():
        print(f'Missing MNQ CSV: {args.mnq_csv}', file=sys.stderr)
        sys.exit(1)
    if not args.vx_csv.is_file():
        print(
            f'Missing VX CSV: {args.vx_csv}\n'
            'Generate it with Python 3.10+ (DBN v3): see potions/vx/export_vx_front_daily.py',
            file=sys.stderr,
        )
        sys.exit(1)

    mnq = read_daily_csv(args.mnq_csv)
    vx = read_daily_csv(args.vx_csv)

    if args.start:
        t0 = pd.Timestamp(args.start)
        mnq = mnq[mnq['date'] >= t0]
        vx = vx[vx['date'] >= t0]

    d0 = max(mnq['date'].min(), vx['date'].min())
    d1 = min(mnq['date'].max(), vx['date'].max())
    mnq = mnq[(mnq['date'] >= d0) & (mnq['date'] <= d1)]
    vx = vx[(vx['date'] >= d0) & (vx['date'] <= d1)]

    mnq = mnq.set_index('date').sort_index()
    vx = vx.set_index('date').sort_index()

    mnq['ma50'] = mnq['close'].rolling(50, min_periods=50).mean()
    mnq['ma150'] = mnq['close'].rolling(150, min_periods=150).mean()

    w, h = (float(x) for x in args.figsize.split(',', 1))
    fig, (ax_m, ax_v) = plt.subplots(
        2,
        1,
        figsize=(w, h),
        facecolor='#fafafa',
        gridspec_kw={'height_ratios': [2.2, 1.0], 'hspace': 0.12},
        sharex=True,
    )
    for ax in (ax_m, ax_v):
        ax.set_facecolor('#fafafa')

    ax_m.plot(mnq.index, mnq['close'], color='#1a1a2e', linewidth=1.0, label='MNQ close')
    ax_m.plot(mnq.index, mnq['ma50'], color='#e63946', linewidth=1.0, alpha=0.9, label='MA50')
    ax_m.plot(mnq.index, mnq['ma150'], color='#457b9d', linewidth=1.0, alpha=0.9, label='MA150')
    ax_m.set_ylabel('MNQ')
    ax_m.legend(loc='upper left', framealpha=0.92, fontsize=9)
    ax_m.grid(True, alpha=0.25)
    ax_m.set_title(f'MNQ daily + MA50/150  |  VX front daily below  |  {d0.date()} → {d1.date()}')

    ax_v.plot(vx.index, vx['close'], color='#6a4c93', linewidth=1.0, label='VX close')
    ax_v.set_ylabel('VX')
    ax_v.grid(True, alpha=0.25)
    ax_v.legend(loc='upper left', framealpha=0.92, fontsize=9)

    ax_v.xaxis.set_major_locator(mdates.YearLocator())
    ax_v.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    fig.autofmt_xdate()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=args.dpi, bbox_inches='tight')
    plt.close(fig)
    print(f'Wrote {args.out}  ({len(mnq)} MNQ days, {len(vx)} VX days aligned)')


if __name__ == '__main__':
    main()
