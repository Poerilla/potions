#!/usr/bin/env python3
"""
Replay every CSV row against the MNQ DB and write one annotated chart per
``replay_row`` outcome with **status ok** and **Net_$ &lt; 0** (losing fills).

Writes into ``child_ladder_trade_samples/losses/`` (+ INDEX.md).
Uses ``build_random_samples_ladder.draw_chart`` matching the main random-sample style.

Uses current child-ladder defaults: ``replay_row(..., max_contracts`` from RESIM unless overridden.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

# parent of this file is swept_liquidity_orb_breakout/; sibling of ../case_studies
_HERE = Path(__file__).resolve().parent
CASE_STUDIES = _HERE.parent
if str(CASE_STUDIES) not in sys.path:
    sys.path.insert(0, str(CASE_STUDIES))

import build_random_samples_ladder as blr  # noqa: E402


EPS = 1e-9
OUT = _HERE / 'child_ladder_trade_samples' / 'losses'


def safe_name_part(s: str, max_len: int = 80) -> str:
    t = re.sub(r'[^\w\-.]+', '_', str(s).strip())
    return (t[:max_len] or 'row').strip('_')


def main() -> int:
    csv = pd.read_csv(blr.CSV_FILE)
    filled = csv[csv['Entry_Price'].notna()].copy()
    filled['Date'] = pd.to_datetime(filled['Date']).dt.date

    sl_pts = float(blr.DEFAULT_SL_PTS)
    child_or_edge = float(blr.DEFAULT_CHILD_OR_EDGE)
    mx = int(getattr(blr.RESIM, 'DEFAULT_MAX_CONTRACTS', 5))

    print(f'Loss charts · tier1 SL L0±{sl_pts:.0f} · child long RH−{child_or_edge:.0f} short RL+{child_or_edge:.0f} · max_contracts={mx}')
    print('Loading DBN ...')
    by_date = blr.load_dbn_once()

    OUT.mkdir(parents=True, exist_ok=True)

    losers: list[dict] = []
    n_checked = n_ok = 0

    for idx, row in filled.iterrows():
        d = row['Date']
        if isinstance(d, str):
            d = pd.to_datetime(d).date()
        if d not in by_date:
            continue
        df1 = blr.day_df_for_symbol(by_date[d], row['Symbol'])
        if df1.empty:
            continue
        n_checked += 1
        r = blr.RESIM.replay_row(row, df1, sl_pts, child_or_edge, max_contracts=mx)
        if r['status'] != 'ok':
            continue
        n_ok += 1
        net = float(r['Net_$'])
        if net >= -EPS:
            continue
        seq_part = safe_name_part(row.get('Sequence_ID', f'idx{idx}'))
        fname = f'{d}__{seq_part}.png'
        outpath = OUT / fname
        losers.append(
            {
                'date': d,
                'symbol': row['Symbol'],
                'sequence': str(row.get('Sequence_ID', '')),
                'net_usd': round(net, 2),
                'trade_pl': round(float(r['Trade_PL_pts']), 2),
                'direction': row['Trade_Direction'],
                'fname': fname,
            }
        )
        ok_pairs = [(row, r)]
        res = blr.draw_chart(d, df1, ok_pairs, outpath, sl_pts, child_or_edge)
        if res is None:
            print(f'  skip chart {fname} (draw failed)')
            losers.pop()

    idx_path = OUT / 'INDEX.md'
    parts = [
        '# Child ladder — losing trades (`Net_$ < 0`)',
        '',
        f'Replay rules match `resim_scale_in_ladder.py` '
        f'(max_contracts={mx}, tier1 SL L0±{sl_pts:.0f}, child long RH−{child_or_edge:.0f} short RL+{child_or_edge:.0f}, TP1 only).',
        '',
        f'Filled CSV rows with DB replay: {n_checked}, `ok`: {n_ok}, **loss PNGs**: **{len(losers)}**.',
        '',
        '| Date | Symbol | Dir | Sequence | Trade pts | Net $ | PNG |',
        '|---|---|---|---:|---:|---:|---|',
    ]
    for L in sorted(losers, key=lambda x: (x['date'], x['sequence'])):
        nm = L['fname']
        parts.append(
            f"| {L['date']} | {L['symbol']} | {L['direction']} | `{L['sequence']}` | "
            f"{L['trade_pl']:+.2f} | ${L['net_usd']:+,.0f} | [{nm}]({nm}) |"
        )

    idx_path.write_text('\n'.join(parts) + '\n')
    print(f'Wrote {len(losers)} PNGs under {OUT}')
    print(f'Wrote {idx_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
