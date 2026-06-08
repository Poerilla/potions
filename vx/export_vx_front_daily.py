#!/usr/bin/env python3
"""
Export **VX** front-month daily OHLCV from a Databento **ohlcv-1d** DBN (XCBF.PITCH).

DBN **version 3** requires a recent ``databento`` client (e.g. ``pip install 'databento>=0.77'``)
on **Python 3.10+**. Pyenv 3.8 + databento 0.42 cannot decode v3 files.

Example::

  /usr/bin/python3.10 -m pip install --user databento
  cd potions && /usr/bin/python3.10 vx/export_vx_front_daily.py \\
    --dbn vx/raw/xcbf-pitch-20181104-20260511.ohlcv-1d.dbn.zst \\
    --out vx/vx_front_daily.csv
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import pandas as pd


def load_vx_front_daily(dbn: Path) -> pd.DataFrame:
    import databento as db

    store = db.DBNStore.from_file(str(dbn))
    df = store.to_df().reset_index()
    sy = df['symbol'].astype(str)
    # Single outright month codes only (exclude roll/spread strings with ':').
    pat = re.compile(r'^VX/[FGHJKMNQUVXZ]\d$')
    sub = df[sy.str.match(pat)].copy()
    if sub.empty:
        raise SystemExit('No VX outright rows after filter; check symbol format in DBN.')
    sub['d'] = pd.to_datetime(sub['ts_event']).dt.date
    fm = sub.loc[sub.groupby('d')['volume'].idxmax()]
    out = fm.set_index('d').sort_index()
    return out[['open', 'high', 'low', 'close', 'volume', 'symbol']].copy()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        '--dbn',
        type=Path,
        default=Path(__file__).resolve().parent / 'raw' / 'xcbf-pitch-20181104-20260511.ohlcv-1d.dbn.zst',
    )
    ap.add_argument(
        '--out',
        type=Path,
        default=Path(__file__).resolve().parent / 'vx_front_daily.csv',
    )
    args = ap.parse_args()
    if not args.dbn.is_file():
        print(f'Missing DBN: {args.dbn}', file=sys.stderr)
        sys.exit(1)
    daily = load_vx_front_daily(args.dbn)
    out = daily.reset_index()
    # index was calendar date from column 'd'
    c0 = out.columns[0]
    out = out.rename(columns={c0: 'date'})
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)
    print(f'Wrote {len(out)} rows -> {args.out}')


if __name__ == '__main__':
    main()
