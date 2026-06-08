#!/usr/bin/env python3
"""Fair benchmark comparison for futures strategy sleeves vs ETF exposure.

The goal is to avoid TradingView's misleading "all capital into the chart
symbol" comparison when the strategy itself is only using a risk-sized slice of
the account.

Default study:
- $50k starting capital.
- 2020-01-01 through 2025-12-31, matching the current yearly ORB Python sample.
- Yearly ORB sleeves are sized at each calendar-year start with the existing
  3x open-heat stress-DD rule.
- ETF benchmarks use Yahoo chart adjusted close data and put the full $50k into
  QQQ, DIA, SPY, or 50/50 QQQ/DIA.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_START = '2020-01-01'
DEFAULT_END = '2025-12-31'


@dataclass(frozen=True)
class Sleeve:
    name: str
    daily: pd.DataFrame
    base_stress_dd: float
    base_contracts: int


def money(value: float) -> str:
    return f'${value:,.0f}'


def max_drawdown(equity: pd.Series) -> float:
    equity = equity.astype(float)
    return float((equity - equity.cummax()).min()) if not equity.empty else 0.0


def yahoo_daily(symbol: str, start: str, end: str, cache_dir: Path, refresh: bool = False) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f'{symbol.upper()}_{start}_{end}_yahoo_daily.csv'
    if cache.exists() and not refresh:
        return pd.read_csv(cache, parse_dates=['date'])

    start_dt = dt.datetime.fromisoformat(start).replace(tzinfo=dt.timezone.utc)
    # Yahoo period2 is exclusive-ish. Add two days to avoid losing the final session.
    end_dt = (dt.datetime.fromisoformat(end) + dt.timedelta(days=2)).replace(tzinfo=dt.timezone.utc)
    url = (
        f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol.upper()}'
        f'?period1={int(start_dt.timestamp())}&period2={int(end_dt.timestamp())}'
        '&interval=1d&events=history&includeAdjustedClose=true'
    )
    response = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
    response.raise_for_status()
    payload = response.json()
    result = payload.get('chart', {}).get('result', [])
    if not result:
        raise RuntimeError(f'No Yahoo chart data for {symbol}: {json.dumps(payload)[:300]}')

    data = result[0]
    timestamps = data.get('timestamp', [])
    quote = data.get('indicators', {}).get('quote', [{}])[0]
    adj = data.get('indicators', {}).get('adjclose', [{}])[0].get('adjclose', [])
    rows: list[dict] = []
    for i, ts in enumerate(timestamps):
        row = {
            'date': pd.to_datetime(ts, unit='s', utc=True).date().isoformat(),
            'open': quote.get('open', [None] * len(timestamps))[i],
            'high': quote.get('high', [None] * len(timestamps))[i],
            'low': quote.get('low', [None] * len(timestamps))[i],
            'close': quote.get('close', [None] * len(timestamps))[i],
            'adj_close': adj[i] if i < len(adj) else None,
            'volume': quote.get('volume', [None] * len(timestamps))[i],
        }
        rows.append(row)
    df = pd.DataFrame(rows)
    df['date'] = pd.to_datetime(df['date'])
    df = df[(df['date'] >= pd.to_datetime(start)) & (df['date'] <= pd.to_datetime(end))]
    df = df.dropna(subset=['adj_close']).sort_values('date').reset_index(drop=True)
    df.to_csv(cache, index=False)
    return df


def etf_equity(symbol: str, capital: float, start: str, end: str, refresh: bool = False) -> pd.DataFrame:
    prices = yahoo_daily(symbol, start, end, ROOT / 'data' / 'benchmarks', refresh)
    first = float(prices.iloc[0]['adj_close'])
    out = prices[['date', 'adj_close']].copy()
    out['symbol'] = symbol.upper()
    out['equity'] = capital * pd.to_numeric(out['adj_close'], errors='coerce') / first
    return out[['date', 'symbol', 'equity']]


def combined_etf_equity(symbols: list[str], weights: list[float], capital: float, start: str, end: str, refresh: bool) -> pd.DataFrame:
    parts = []
    for symbol, weight in zip(symbols, weights):
        eq = etf_equity(symbol, capital * weight, start, end, refresh)
        eq = eq.rename(columns={'equity': symbol.upper()})
        parts.append(eq[['date', symbol.upper()]])
    merged = parts[0]
    for part in parts[1:]:
        merged = merged.merge(part, on='date', how='outer')
    merged = merged.sort_values('date').ffill().dropna()
    merged['symbol'] = '+'.join(f'{int(w * 100)}%{s.upper()}' for s, w in zip(symbols, weights))
    merged['equity'] = merged[[s.upper() for s in symbols]].sum(axis=1)
    return merged[['date', 'symbol', 'equity']]


def parse_yearly_units(raw: pd.DataFrame, point_value: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    trades = raw[raw['Entry_Date'].notna()].copy().reset_index(drop=True)
    trades['trade_id'] = range(1, len(trades) + 1)
    trades['Entry_Date'] = pd.to_datetime(trades['Entry_Date'])
    trades['Final_Exit_Date'] = pd.to_datetime(
        trades[['Unit1_Exit_Date', 'Unit2_Exit_Date', 'Unit3_Exit_Date']].max(axis=1)
    )
    trades['mae_usd'] = pd.to_numeric(trades['MAE_Position_Pts'], errors='coerce').fillna(0.0) * point_value
    trades['trade_usd'] = pd.to_numeric(trades['Trade_PL'], errors='coerce').fillna(0.0) * point_value

    units = []
    for _, row in trades.iterrows():
        direction = str(row['Trade_Direction'])
        entry = float(row['Entry_Price'])
        for unit in (1, 2, 3):
            exit_date = row.get(f'Unit{unit}_Exit_Date')
            exit_px = row.get(f'Unit{unit}_Exit_Price')
            if pd.isna(exit_date) or pd.isna(exit_px):
                continue
            exit_px = float(exit_px)
            pts = exit_px - entry if direction == 'Long' else entry - exit_px
            units.append(
                {
                    'date': pd.to_datetime(exit_date),
                    'trade_id': int(row['trade_id']),
                    'usd': pts * point_value,
                }
            )
    return trades, pd.DataFrame(units)


def base_daily_from_trades(
    trades: pd.DataFrame,
    units: pd.DataFrame,
    start: str,
    end: str,
) -> pd.DataFrame:
    days = pd.date_range(start, end, freq='D')
    pnl = units.groupby('date')['usd'].sum() if not units.empty else pd.Series(dtype=float)
    rows = []
    closed = 0.0
    peak = 0.0
    for day in days:
        closed += float(pnl.get(day, 0.0))
        active = trades[(trades['Entry_Date'] <= day) & (trades['Final_Exit_Date'] >= day)]
        heat = float(active['mae_usd'].sum()) if not active.empty else 0.0
        peak = max(peak, closed)
        rows.append(
            {
                'date': day,
                'daily_pnl': float(pnl.get(day, 0.0)),
                'closed_eq': closed,
                'heat': heat,
                'stress_eq': closed - heat,
                'closed_dd': closed - peak,
                'stress_dd': closed - heat - peak,
            }
        )
    return pd.DataFrame(rows)


def mnq_yearly_sleeve(start: str, end: str) -> Sleeve:
    raw = pd.read_csv(ROOT / 'mnq' / 'mnq_yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close.csv')
    trades, units = parse_yearly_units(raw, 2.0)
    daily = base_daily_from_trades(trades, units, start, end)
    return Sleeve('Yearly ORB MNQ standalone', daily, abs(float(daily['stress_dd'].min())), 3)


def mnq_mym_pair_sleeve(start: str, end: str) -> Sleeve:
    path = ROOT / 'mnq' / 'case_studies' / 'yearly_orb_mnq_mym_portfolio' / 'mnq1_mym4_daily_stress_equity.csv'
    raw = pd.read_csv(path, parse_dates=['date'])
    days = pd.date_range(start, end, freq='D')
    work = raw.set_index('date').reindex(days).ffill().fillna(0.0).reset_index().rename(columns={'index': 'date'})
    work['daily_pnl'] = pd.to_numeric(work['closed_eq'], errors='coerce').fillna(0.0).diff().fillna(work['closed_eq'])
    daily = work[['date', 'daily_pnl', 'closed_eq', 'heat', 'stress_eq', 'closed_dd', 'stress_dd']].copy()
    return Sleeve('Yearly ORB MNQ+MYM portfolio', daily, abs(float(daily['stress_dd'].min())), 15)


def simulate_sleeve(sleeve: Sleeve, capital: float, buffer_mult: float) -> tuple[pd.DataFrame, dict]:
    required_per_bundle = sleeve.base_stress_dd * buffer_mult
    rows = []
    current = capital
    peak_closed = capital
    peak_stress_ref = capital
    yearly_bundles: dict[int, int] = {}
    for _, row in sleeve.daily.iterrows():
        date = pd.Timestamp(row['date'])
        if date.year not in yearly_bundles:
            yearly_bundles[date.year] = max(0, int(current // required_per_bundle)) if required_per_bundle > 0 else 0
        bundles = yearly_bundles[date.year]
        day_pnl = float(row['daily_pnl']) * bundles
        heat = float(row['heat']) * bundles
        current += day_pnl
        peak_closed = max(peak_closed, current)
        peak_stress_ref = max(peak_stress_ref, current)
        stress_equity = current - heat
        rows.append(
            {
                'date': date,
                'year': date.year,
                'bundles': bundles,
                'max_contracts': bundles * sleeve.base_contracts,
                'daily_pnl': day_pnl,
                'closed_equity': current,
                'active_heat': heat,
                'stress_equity': stress_equity,
                'closed_dd': current - peak_closed,
                'stress_dd': stress_equity - peak_stress_ref,
            }
        )
    daily = pd.DataFrame(rows)
    summary = {
        'name': sleeve.name,
        'start_capital': capital,
        'end_capital': float(daily.iloc[-1]['closed_equity']) if not daily.empty else capital,
        'net': float(daily.iloc[-1]['closed_equity'] - capital) if not daily.empty else 0.0,
        'closed_dd': float(daily['closed_dd'].min()) if not daily.empty else 0.0,
        'stress_dd': float(daily['stress_dd'].min()) if not daily.empty else 0.0,
        'base_stress_dd': sleeve.base_stress_dd,
        'required_per_bundle': required_per_bundle,
        'peak_bundles': int(daily['bundles'].max()) if not daily.empty else 0,
        'peak_contracts': int(daily['max_contracts'].max()) if not daily.empty else 0,
    }
    return daily, summary


def simulate_fixed_sleeve(sleeve: Sleeve, capital: float, bundles: int = 1) -> tuple[pd.DataFrame, dict]:
    rows = []
    current = capital
    peak_closed = capital
    peak_stress_ref = capital
    for _, row in sleeve.daily.iterrows():
        date = pd.Timestamp(row['date'])
        day_pnl = float(row['daily_pnl']) * bundles
        heat = float(row['heat']) * bundles
        current += day_pnl
        peak_closed = max(peak_closed, current)
        peak_stress_ref = max(peak_stress_ref, current)
        stress_equity = current - heat
        rows.append(
            {
                'date': date,
                'year': date.year,
                'bundles': bundles,
                'max_contracts': bundles * sleeve.base_contracts,
                'daily_pnl': day_pnl,
                'closed_equity': current,
                'active_heat': heat,
                'stress_equity': stress_equity,
                'closed_dd': current - peak_closed,
                'stress_dd': stress_equity - peak_stress_ref,
            }
        )
    daily = pd.DataFrame(rows)
    summary = {
        'name': f'{sleeve.name} (1 bundle fixed)',
        'start_capital': capital,
        'end_capital': float(daily.iloc[-1]['closed_equity']) if not daily.empty else capital,
        'net': float(daily.iloc[-1]['closed_equity'] - capital) if not daily.empty else 0.0,
        'closed_dd': float(daily['closed_dd'].min()) if not daily.empty else 0.0,
        'stress_dd': float(daily['stress_dd'].min()) if not daily.empty else 0.0,
        'base_stress_dd': sleeve.base_stress_dd,
        'required_per_bundle': sleeve.base_stress_dd,
        'peak_bundles': bundles,
        'peak_contracts': bundles * sleeve.base_contracts,
    }
    return daily, summary


def summarize_etf(label: str, equity: pd.DataFrame, capital: float) -> dict:
    values = pd.to_numeric(equity['equity'], errors='coerce')
    return {
        'name': label,
        'start_capital': capital,
        'end_capital': float(values.iloc[-1]),
        'net': float(values.iloc[-1] - capital),
        'closed_dd': max_drawdown(values),
        'stress_dd': max_drawdown(values),
        'peak_bundles': 1,
        'peak_contracts': 0,
    }


def write_report(
    out_dir: Path,
    start: str,
    end: str,
    capital: float,
    buffer_mult: float,
    summaries: list[dict],
    outputs: list[Path],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        '# Fair Benchmark Comparison',
        '',
        f'Window: **{start} through {end}**. Starting capital: **{money(capital)}**.',
        '',
        'Purpose: TradingView buy-and-hold assumes the full initial capital is passively exposed to the chart symbol for the full test. That is not apples-to-apples against a futures system that uses only a risk-sized sleeve and can sit in cash. This report compares both sides from the same starting capital.',
        '',
        'Futures rows include both a fixed one-bundle sleeve and an annual risk-scaled sleeve. The annual scaling rule chooses `floor(current capital / (3 x base open-heat stress DD))` bundles at each calendar-year start. ETF benchmarks invest the full starting capital and hold through the window. ETF data uses Yahoo chart adjusted close, cached under `data/benchmarks/`.',
        '',
        '## Summary',
        '',
        '| Sleeve | End Capital | Net | Max DD / Stress DD | Return | Net/DD | Peak Size |',
        '|---|---:|---:|---:|---:|---:|---:|',
    ]
    for row in summaries:
        dd = float(row['stress_dd'])
        net = float(row['net'])
        net_dd = net / abs(dd) if dd < 0 else math.inf
        peak = row.get('peak_contracts', 0)
        peak_text = f"{row.get('peak_bundles', 0)} bundles / {peak} contracts" if peak else 'full ETF capital'
        lines.append(
            f"| {row['name']} | {money(row['end_capital'])} | {money(net)} | {money(dd)} | "
            f"{net / capital * 100.0:.1f}% | {net_dd:.2f} | {peak_text} |"
        )
    lines.extend(
        [
            '',
            '## Read',
            '',
            '- The ETF rows are a useful passive-capital benchmark, but they accept full drawdown exposure with no stop or de-risking.',
            '- The fixed futures rows show what a single strategy sleeve would have done inside a `$50k` account without compounding size.',
            '- The annual risk-scaled futures rows show what the same `$50k` would have done under the existing 3x stress-DD rule. This is closer to how we would actually capitalize and grow a futures test account, but the ending contract counts can become operationally unrealistic.',
            '- This is still not a forecast. It is a fairer normalization layer for comparing passive exposure against a rules-based futures sleeve.',
            '',
            '## Outputs',
            '',
        ]
    )
    for path in outputs:
        lines.append(f'- `{path.relative_to(ROOT)}`')
    (out_dir / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--start', default=DEFAULT_START)
    ap.add_argument('--end', default=DEFAULT_END)
    ap.add_argument('--capital', type=float, default=50_000.0)
    ap.add_argument('--buffer-mult', type=float, default=3.0)
    ap.add_argument('--refresh-benchmarks', action='store_true')
    args = ap.parse_args()

    out_dir = ROOT / 'mnq' / 'case_studies' / 'fair_benchmark_comparison'
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    summaries: list[dict] = []

    for sleeve in [mnq_yearly_sleeve(args.start, args.end), mnq_mym_pair_sleeve(args.start, args.end)]:
        fixed_daily, fixed_summary = simulate_fixed_sleeve(sleeve, args.capital)
        fixed_path = out_dir / f"{sleeve.name.lower().replace(' ', '_').replace('+', '_')}_fixed_1bundle_50k_daily.csv"
        fixed_daily.to_csv(fixed_path, index=False)
        outputs.append(fixed_path)
        summaries.append(fixed_summary)

        daily, summary = simulate_sleeve(sleeve, args.capital, args.buffer_mult)
        summary['name'] = f"{summary['name']} (3x DD annual scale)"
        path = out_dir / f"{sleeve.name.lower().replace(' ', '_').replace('+', '_')}_3xdd_annual_scale_50k_daily.csv"
        daily.to_csv(path, index=False)
        outputs.append(path)
        summaries.append(summary)

    etf_specs = [
        ('QQQ buy-and-hold', etf_equity('QQQ', args.capital, args.start, args.end, args.refresh_benchmarks)),
        ('DIA buy-and-hold', etf_equity('DIA', args.capital, args.start, args.end, args.refresh_benchmarks)),
        ('SPY buy-and-hold', etf_equity('SPY', args.capital, args.start, args.end, args.refresh_benchmarks)),
        (
            '50/50 QQQ+DIA buy-and-hold',
            combined_etf_equity(['QQQ', 'DIA'], [0.5, 0.5], args.capital, args.start, args.end, args.refresh_benchmarks),
        ),
    ]
    for label, equity in etf_specs:
        safe = label.lower().replace('/', '').replace(' ', '_').replace('+', '_').replace('-', '_')
        path = out_dir / f'{safe}_50k_daily.csv'
        equity.to_csv(path, index=False)
        outputs.append(path)
        summaries.append(summarize_etf(label, equity, args.capital))

    summary_path = out_dir / 'summary.csv'
    pd.DataFrame(summaries).to_csv(summary_path, index=False)
    outputs.append(summary_path)
    write_report(out_dir, args.start, args.end, args.capital, args.buffer_mult, summaries, outputs)
    print(f'Wrote {out_dir / "README.md"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
