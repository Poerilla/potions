#!/usr/bin/env python3
"""Pair MNQ and MYM ATR Supertrend dynamic-sizing equity paths."""
from __future__ import annotations

from pathlib import Path

import pandas as pd


VARIANTS = [
    ('daily_3initial', 'Daily primary, 3-initial'),
    ('daily_ladder112221', 'Daily primary, ladder 1/1/2/2/2'),
    ('weekly_3initial', 'Weekly primary, 3-initial'),
    ('weekly_ladder112221', 'Weekly primary, ladder 1/1/2/2/2'),
]


def max_dd(equity: pd.Series) -> float:
    return float((equity - equity.cummax()).min()) if not equity.empty else 0.0


def load_daily(root: Path, slug: str, prefix: str) -> pd.DataFrame:
    df = pd.read_csv(root / slug / 'dynamic_daily.csv', parse_dates=['date'])
    return df[['date', 'daily_equity_delta_usd']].rename(columns={'daily_equity_delta_usd': f'{prefix}_pnl'})


def load_start(root: Path, slug: str) -> float:
    yearly = pd.read_csv(root / slug / 'dynamic_yearly.csv')
    return float(yearly['start_capital_usd'].iloc[0])


def load_end(root: Path, slug: str) -> float:
    yearly = pd.read_csv(root / slug / 'dynamic_yearly.csv')
    return float(yearly['end_capital_usd'].iloc[-1])


def main() -> int:
    mnq_root = Path('potions/mnq/case_studies/atr_supertrend_equity_scaling')
    mym_root = Path('potions/mym/case_studies/atr_supertrend_equity_scaling')
    out = Path('potions/mnq/case_studies/atr_supertrend_mnq_mym_pairing')
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    lines = [
        '# ATR Supertrend MNQ + MYM Pairing',
        '',
        'This combines the dynamic-sizing daily equity paths from the MNQ and MYM ATR Supertrend studies. Each market sizes itself independently by the same 3x historical MTM-DD rule, then the daily dollar PnL streams are summed.',
        '',
        '| Variant | Start Capital | End Capital | Net | Combined DD | MNQ Alone Net/DD | MYM Alone Net/DD | Daily PnL Corr | DD Improvement vs MNQ |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]

    for slug, label in VARIANTS:
        mnq = load_daily(mnq_root, slug, 'mnq')
        mym = load_daily(mym_root, slug, 'mym')
        combo = mnq.merge(mym, on='date', how='outer').fillna(0.0).sort_values('date')
        mnq_start = load_start(mnq_root, slug)
        mym_start = load_start(mym_root, slug)
        start = mnq_start + mym_start
        combo['combined_pnl'] = combo['mnq_pnl'] + combo['mym_pnl']
        combo['combined_equity'] = start + combo['combined_pnl'].cumsum()
        combo['combined_drawdown'] = combo['combined_equity'] - combo['combined_equity'].cummax()
        corr = float(combo[['mnq_pnl', 'mym_pnl']].corr().iloc[0, 1])
        combined_dd = max_dd(combo['combined_equity'])
        mnq_end = load_end(mnq_root, slug)
        mym_end = load_end(mym_root, slug)
        mnq_net = mnq_end - mnq_start
        mym_net = mym_end - mym_start
        mnq_equity = mnq_start + combo['mnq_pnl'].cumsum()
        mym_equity = mym_start + combo['mym_pnl'].cumsum()
        mnq_dd = max_dd(mnq_equity)
        mym_dd = max_dd(mym_equity)
        end = float(combo['combined_equity'].iloc[-1])
        combo.to_csv(out / f'{slug}_combined_daily.csv', index=False)
        dd_improvement = abs(mnq_dd) - abs(combined_dd)
        row = {
            'variant': label,
            'start_capital_usd': start,
            'end_capital_usd': end,
            'net_usd': end - start,
            'combined_dd_usd': combined_dd,
            'mnq_net_usd': mnq_net,
            'mnq_dd_usd': mnq_dd,
            'mym_net_usd': mym_net,
            'mym_dd_usd': mym_dd,
            'daily_pnl_corr': corr,
            'dd_improvement_vs_mnq_usd': dd_improvement,
        }
        rows.append(row)
        lines.append(
            f'| {label} | ${start:,.0f} | ${end:,.0f} | ${end - start:,.0f} | ${combined_dd:,.0f} | ${mnq_net:,.0f} / ${mnq_dd:,.0f} | ${mym_net:,.0f} / ${mym_dd:,.0f} | {corr:.2f} | ${dd_improvement:,.0f} |'
        )

    pd.DataFrame(rows).to_csv(out / 'summary.csv', index=False)
    lines.extend(
        [
            '',
            'Interpretation: negative or low daily PnL correlation is useful, but the combined DD still grows if MYM adds more absolute heat than it offsets. Compare `Combined DD` against MNQ-alone DD before deciding it diversifies the live account.',
            '',
        ]
    )
    (out / 'README.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Wrote {out / "README.md"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
