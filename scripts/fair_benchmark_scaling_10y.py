#!/usr/bin/env python3
"""Ten-year scaling comparison for yearly ORB futures sleeves vs ETFs.

This is a companion to ``fair_benchmark_comparison.py``. It answers the
specific question: if the futures sleeves resize when equity supports another
risk unit, and ETF sleeves remain fully invested/compounded, who wins over a
rough 10-year window?

Sizing note:
- Futures resize only at fresh trade entry, never after a trade is already on.
- Required capital per futures bundle = 3 x full-sample open-heat stress DD.
- ETF rows are already "scaled" in the passive sense: the full account remains
  invested, so growth compounds. No margin/leverage is assumed for ETFs.
"""
from __future__ import annotations

from pathlib import Path
import math

import pandas as pd

import fair_benchmark_comparison as bench


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / 'mnq' / 'case_studies' / 'fair_benchmark_comparison'
START = '2016-01-01'
END = '2025-12-31'


def market_yearly_sleeve(market: str, point_value: float, start: str, end: str) -> tuple[bench.Sleeve, pd.DataFrame, pd.DataFrame]:
    raw = pd.read_csv(ROOT / market / f'{market}_yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close.csv')
    trades, units = bench.parse_yearly_units(raw, point_value)
    daily = bench.base_daily_from_trades(trades, units, start, end)
    sleeve = bench.Sleeve(
        f'Yearly ORB {market.upper()} standalone',
        daily,
        abs(float(daily['stress_dd'].min())),
        3,
    )
    return sleeve, trades, units


def entry_resized_sleeve(
    sleeve: bench.Sleeve,
    trades: pd.DataFrame,
    units: pd.DataFrame,
    start: str,
    end: str,
    capital: float,
    buffer_mult: float = 3.0,
) -> tuple[pd.DataFrame, dict]:
    required_per_bundle = sleeve.base_stress_dd * buffer_mult
    current = capital
    closed_peak = current
    stress_peak = current
    trade_bundles: dict[int, int] = {}
    rows = []
    for day in pd.date_range(start, end, freq='D'):
        for _, trade in trades[trades['Entry_Date'].eq(day)].iterrows():
            bundles = int(current // required_per_bundle) if required_per_bundle > 0 else 0
            trade_bundles[int(trade['trade_id'])] = max(0, bundles)

        day_units = units[units['date'].eq(day)] if not units.empty else units
        day_pnl = sum(float(unit['usd']) * trade_bundles.get(int(unit['trade_id']), 0) for _, unit in day_units.iterrows())
        active = trades[(trades['Entry_Date'] <= day) & (trades['Final_Exit_Date'] >= day)]
        heat = 0.0
        active_bundles = 0
        for _, trade in active.iterrows():
            bundles = trade_bundles.get(int(trade['trade_id']), 0)
            active_bundles += bundles
            heat += float(trade['mae_usd']) * bundles

        current += day_pnl
        closed_peak = max(closed_peak, current)
        stress_peak = max(stress_peak, current)
        stress_equity = current - heat
        rows.append(
            {
                'date': day,
                'daily_pnl': day_pnl,
                'equity': current,
                'active_heat': heat,
                'stress_equity': stress_equity,
                'closed_dd': current - closed_peak,
                'stress_dd': stress_equity - stress_peak,
                'active_bundles': active_bundles,
                'contracts': active_bundles * sleeve.base_contracts,
            }
        )

    daily = pd.DataFrame(rows)
    summary = {
        'name': f'{sleeve.name} entry-resized 3xDD',
        'start_capital': capital,
        'end_capital': float(daily.iloc[-1]['equity']),
        'net': float(daily.iloc[-1]['equity'] - capital),
        'stress_dd': float(daily['stress_dd'].min()),
        'closed_dd': float(daily['closed_dd'].min()),
        'required_per_bundle': required_per_bundle,
        'peak_contracts': int(daily['contracts'].max()),
    }
    return daily, summary


def row(name: str, capital: float, end_capital: float, stress_dd: float, peak_size: str, required: float | None = None) -> dict:
    net = end_capital - capital
    return {
        'name': name,
        'start_capital': capital,
        'end_capital': end_capital,
        'net': net,
        'stress_dd': stress_dd,
        'return_pct': net / capital * 100.0 if capital else math.nan,
        'net_dd': net / abs(stress_dd) if stress_dd < 0 else math.inf,
        'required_per_bundle': required,
        'peak_size': peak_size,
    }


def etf_row(symbol: str, capital: float, start: str, end: str) -> dict:
    equity = bench.etf_equity(symbol, capital, start, end)
    summary = bench.summarize_etf(f'{symbol} fully invested', equity, capital)
    return row(summary['name'], capital, summary['end_capital'], summary['stress_dd'], 'full ETF capital')


def combo_etf_row(label: str, symbols: list[str], weights: list[float], capital: float, start: str, end: str) -> dict:
    equity = bench.combined_etf_equity(symbols, weights, capital, start, end, False)
    summary = bench.summarize_etf(label, equity, capital)
    return row(summary['name'], capital, summary['end_capital'], summary['stress_dd'], 'full ETF capital')


def money(value: float | None) -> str:
    if value is None or pd.isna(value):
        return ''
    return f'${value:,.0f}'


def write_report(summary: pd.DataFrame, sensitivity: pd.DataFrame) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(OUT_DIR / 'scaling_10y_summary.csv', index=False)
    sensitivity.to_csv(OUT_DIR / 'scaling_10y_capital_sensitivity.csv', index=False)

    lines = [
        '# Fair Benchmark Scaling 10Y',
        '',
        f'Window: **{START} through {END}**. Futures use the yearly ORB scaleout3 inside-range swing/range-close CSVs.',
        '',
        'Assumptions:',
        '',
        '- Futures resize only at fresh trade entry.',
        '- Required futures capital per bundle = **3 x full-sample open-heat stress DD**.',
        '- ETF rows are fully invested for the whole period using adjusted close, so growth compounds. No ETF margin or leverage is assumed.',
        '- MNQ is dormant before its first local trade in 2020, so its “10Y” row is really a 10-year account window with a 2020-2025 active strategy window.',
        '',
        '## $50k Starting Capital',
        '',
        '| Sleeve | End Capital | Net | Stress DD | Return | Net/DD | Required / Bundle | Peak Size |',
        '|---|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for _, r in summary.sort_values('end_capital', ascending=False).iterrows():
        lines.append(
            f"| {r['name']} | {money(r['end_capital'])} | {money(r['net'])} | {money(r['stress_dd'])} | "
            f"{r['return_pct']:.1f}% | {r['net_dd']:.2f} | {money(r['required_per_bundle'])} | {r['peak_size']} |"
        )

    lines.extend(
        [
            '',
            '## Capital Sensitivity',
            '',
            '| Start Capital | Sleeve | End Capital | Net | Stress DD | Peak Size |',
            '|---:|---|---:|---:|---:|---:|',
        ]
    )
    for _, r in sensitivity.iterrows():
        lines.append(
            f"| {money(r['start_capital'])} | {r['name']} | {money(r['end_capital'])} | "
            f"{money(r['net'])} | {money(r['stress_dd'])} | {r['peak_size']} |"
        )

    lines.extend(
        [
            '',
            '## Read',
            '',
            '- With `$50k`, strict 3x-DD NQ cannot start because one NQ bundle needs about `$135k` of stress-DD capital.',
            '- MNQ can start from `$50k` and wins the 10-year account-window test if we allow entry-by-entry resizing.',
            '- QQQ is still a strong passive benchmark. It beats fixed MNQ over this window, but not entry-resized MNQ and not fixed NQ.',
            '- At `$150k+`, NQ can participate under the same 3x-DD rule and becomes the largest winner, but the drawdowns and contract size become much less friendly for a small automation test account.',
        ]
    )
    (OUT_DIR / 'SCALING_10Y.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    nq, nq_trades, nq_units = market_yearly_sleeve('nq', 20.0, START, END)
    mnq, mnq_trades, mnq_units = market_yearly_sleeve('mnq', 2.0, START, END)

    capital = 50_000.0
    rows = []
    for sleeve, trades, units in [(mnq, mnq_trades, mnq_units), (nq, nq_trades, nq_units)]:
        fixed_daily, fixed_summary = bench.simulate_fixed_sleeve(sleeve, capital)
        rows.append(
            row(
                f'{sleeve.name} fixed 1 bundle',
                capital,
                fixed_summary['end_capital'],
                fixed_summary['stress_dd'],
                f"{fixed_summary['peak_contracts']} contracts",
                sleeve.base_stress_dd,
            )
        )
        resized_daily, resized_summary = entry_resized_sleeve(sleeve, trades, units, START, END, capital)
        resized_daily.to_csv(OUT_DIR / f"{sleeve.name.lower().replace(' ', '_')}_entry_resized_3xdd_10y_daily.csv", index=False)
        rows.append(
            row(
                resized_summary['name'],
                capital,
                resized_summary['end_capital'],
                resized_summary['stress_dd'],
                f"{resized_summary['peak_contracts']} contracts",
                resized_summary['required_per_bundle'],
            )
        )

    rows.extend(
        [
            etf_row('QQQ', capital, START, END),
            etf_row('SPY', capital, START, END),
            combo_etf_row('50/50 QQQ+DIA fully invested', ['QQQ', 'DIA'], [0.5, 0.5], capital, START, END),
        ]
    )

    sensitivity_rows = []
    for capital in [50_000.0, 100_000.0, 150_000.0, 250_000.0]:
        for sleeve, trades, units in [(mnq, mnq_trades, mnq_units), (nq, nq_trades, nq_units)]:
            _daily, summary = entry_resized_sleeve(sleeve, trades, units, START, END, capital)
            sensitivity_rows.append(
                row(
                    summary['name'],
                    capital,
                    summary['end_capital'],
                    summary['stress_dd'],
                    f"{summary['peak_contracts']} contracts",
                    summary['required_per_bundle'],
                )
            )
        sensitivity_rows.append(etf_row('QQQ', capital, START, END))
        sensitivity_rows.append(etf_row('SPY', capital, START, END))

    write_report(pd.DataFrame(rows), pd.DataFrame(sensitivity_rows))
    print(f'Wrote {OUT_DIR / "SCALING_10Y.md"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
