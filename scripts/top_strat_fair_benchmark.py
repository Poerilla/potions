#!/usr/bin/env python3
"""Fair buy/hold comparison for the current top broker-like strategy rows.

This is intentionally a comparison layer, not a new strategy study.  It reads
existing broker-like replay equity curves, capitalizes each strategy at a
simple 3x intrabar-stress-DD buffer, and compares that capital to passive ETF
buy-and-hold over the same replay window.

The DCA section is handled separately: ATR/DCA books are compared to sizing up
the strongest same-market non-DCA yearly ORB book to the same stress budget.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

import fair_benchmark_comparison as bench


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / 'mnq' / 'case_studies' / 'fair_benchmark_comparison'
BROKER_SUMMARY = ROOT / 'live' / 'state' / 'broker_like_replays' / 'summary.csv'
BROKER_AUDITS = ROOT / 'live' / 'state' / 'broker_like_replays' / 'audits'
NQ_GATE_SUMMARY = ROOT / 'live' / 'state' / 'nq_v2b_prior_opposed_stpmc_broker_like' / 'summary.csv'


@dataclass(frozen=True)
class StrategySpec:
    label: str
    slug: str
    instrument: str
    equity_path: Path
    summary_source: str
    family: str


def money(value: float | None, digits: int = 0) -> str:
    if value is None or pd.isna(value):
        return ''
    return f'${value:,.{digits}f}'


def pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return ''
    return f'{value:.1f}%'


def read_broker_summary() -> pd.DataFrame:
    return pd.read_csv(BROKER_SUMMARY)


def broker_spec(label: str, slug: str, family: str, summary: pd.DataFrame) -> StrategySpec:
    row = summary[summary['slug'].eq(slug)]
    if row.empty:
        raise ValueError(f'Missing broker-like summary row for {slug}')
    instrument = str(row.iloc[0]['instrument'])
    return StrategySpec(
        label=label,
        slug=slug,
        instrument=instrument,
        equity_path=BROKER_AUDITS / slug / 'equity_curve.csv',
        summary_source='broker_like_replays',
        family=family,
    )


def nq_prior_opposed_spec() -> StrategySpec:
    summary = pd.read_csv(NQ_GATE_SUMMARY)
    row = summary.iloc[0]
    state_root = Path(str(row['state_root']))
    return StrategySpec(
        label='NQ v2b prior-opposed ST+PMC gate S_1_1_3',
        slug=str(row['strategy_id']),
        instrument='NQ',
        equity_path=state_root / 'equity_curve.csv',
        summary_source='nq_v2b_prior_opposed_stpmc_broker_like',
        family='v2b_prior_opposed',
    )


def selected_specs() -> list[StrategySpec]:
    summary = read_broker_summary()
    specs = [
        nq_prior_opposed_spec(),
        broker_spec('NQ Yearly ORB scaleout3', 'nq_yearly_orb_scaleout3', 'yearly_orb', summary),
        broker_spec('ES Yearly ORB scaleout3', 'es_yearly_orb_scaleout3', 'yearly_orb', summary),
        broker_spec('YM Yearly ORB scaleout3', 'ym_yearly_orb_scaleout3', 'yearly_orb', summary),
        broker_spec('MNQ Yearly ORB scaleout3', 'mnq_yearly_orb_scaleout3', 'yearly_orb', summary),
        broker_spec('NQ ATR daily ladder 1/1/2/2/2 10-max', 'nq_atr_daily_ladder112221_10max', 'atr_dca', summary),
        broker_spec('MNQ ATR daily ladder 1/1/2/2/2 10-max', 'mnq_atr_daily_ladder112221_10max', 'atr_dca', summary),
        broker_spec('NQ ATR daily 3-initial 10-max', 'nq_atr_daily_3initial_10max', 'atr_dca', summary),
        broker_spec('MNQ ATR daily 3-initial 10-max', 'mnq_atr_daily_3initial_10max', 'atr_dca', summary),
    ]
    for spec in specs:
        if not spec.equity_path.exists():
            raise FileNotFoundError(spec.equity_path)
    return specs


def parse_dates(raw: pd.Series) -> pd.Series:
    # Works for date-only broker-like rows and timezone-aware intraday rows.
    return pd.to_datetime(raw, utc=True, errors='coerce').dt.tz_convert(None)


def load_equity_curve(spec: StrategySpec) -> pd.DataFrame:
    raw = pd.read_csv(spec.equity_path)
    if 'ts' not in raw.columns:
        raise ValueError(f'{spec.equity_path} has no ts column')
    raw['dt'] = parse_dates(raw['ts'])
    raw = raw.dropna(subset=['dt']).sort_values('dt')

    if 'close_equity_usd' in raw.columns:
        close_usd = pd.to_numeric(raw['close_equity_usd'], errors='coerce').fillna(0.0)
        stress_usd = pd.to_numeric(raw.get('intrabar_stress_equity_usd', close_usd), errors='coerce').fillna(close_usd)
    elif 'close_equity_points' in raw.columns:
        close_points = pd.to_numeric(raw['close_equity_points'], errors='coerce').fillna(0.0)
        final_points = float(close_points.iloc[-1])
        net_usd = summary_net_usd(spec)
        point_value = net_usd / final_points if final_points else 0.0
        close_usd = close_points * point_value
        stress_points = pd.to_numeric(raw.get('intrabar_stress_points', close_points), errors='coerce').fillna(close_points)
        stress_usd = stress_points * point_value
    else:
        raise ValueError(f'{spec.equity_path} has no recognized equity columns')

    source_close_dd = None
    if 'close_dd_usd' in raw.columns:
        source_close_dd = pd.to_numeric(raw['close_dd_usd'], errors='coerce')
    source_stress_dd = None
    if 'intrabar_stress_dd_usd' in raw.columns:
        source_stress_dd = pd.to_numeric(raw['intrabar_stress_dd_usd'], errors='coerce')
    elif 'intrabar_dd_usd' in raw.columns:
        source_stress_dd = pd.to_numeric(raw['intrabar_dd_usd'], errors='coerce')

    work = pd.DataFrame(
        {
            'date': raw['dt'].dt.normalize(),
            'close_equity_usd': close_usd,
            'intrabar_stress_equity_usd': stress_usd,
            'open_units': pd.to_numeric(raw.get('open_units', 0), errors='coerce').fillna(0.0),
        }
    )
    if source_close_dd is not None:
        work['source_close_dd_usd'] = source_close_dd.fillna(0.0)
    if source_stress_dd is not None:
        work['source_stress_dd_usd'] = source_stress_dd.fillna(0.0)

    aggregations = {
        'close_equity_usd': ('close_equity_usd', 'last'),
        'intrabar_stress_equity_usd': ('intrabar_stress_equity_usd', 'min'),
        'max_open_units': ('open_units', 'max'),
    }
    if 'source_close_dd_usd' in work.columns:
        aggregations['source_close_dd_usd'] = ('source_close_dd_usd', 'min')
    if 'source_stress_dd_usd' in work.columns:
        aggregations['source_stress_dd_usd'] = ('source_stress_dd_usd', 'min')

    daily = (
        work.groupby('date', as_index=False)
        .agg(**aggregations)
        .sort_values('date')
        .reset_index(drop=True)
    )
    daily['daily_pnl_usd'] = daily['close_equity_usd'].diff().fillna(daily['close_equity_usd'])
    daily['active_heat_usd'] = daily['close_equity_usd'] - daily['intrabar_stress_equity_usd']
    daily['peak_close_usd'] = daily['close_equity_usd'].cummax()
    computed_close_dd = daily['close_equity_usd'] - daily['peak_close_usd']
    computed_stress_dd = daily['intrabar_stress_equity_usd'] - daily['peak_close_usd']
    daily['close_dd_usd'] = daily.get('source_close_dd_usd', computed_close_dd)
    daily['stress_dd_usd'] = daily.get('source_stress_dd_usd', computed_stress_dd)
    return daily


def summary_net_usd(spec: StrategySpec) -> float:
    if spec.summary_source == 'broker_like_replays':
        summary = read_broker_summary()
        row = summary[summary['slug'].eq(spec.slug)].iloc[0]
        return float(row['net_usd'])
    if spec.summary_source == 'nq_v2b_prior_opposed_stpmc_broker_like':
        row = pd.read_csv(NQ_GATE_SUMMARY).iloc[0]
        return float(row['net_usd'])
    raise ValueError(spec.summary_source)


def strategy_metrics(spec: StrategySpec, refresh_benchmarks: bool, buffer_mult: float) -> tuple[dict, pd.DataFrame]:
    daily = load_equity_curve(spec)
    start = pd.Timestamp(daily.iloc[0]['date']).date().isoformat()
    end = pd.Timestamp(daily.iloc[-1]['date']).date().isoformat()
    net = float(daily.iloc[-1]['close_equity_usd'])
    stress_dd = float(daily['stress_dd_usd'].min())
    close_dd = float(daily['close_dd_usd'].min())
    required_capital = abs(stress_dd) * buffer_mult
    return_on_required = net / required_capital * 100.0 if required_capital else math.inf
    net_stress = net / abs(stress_dd) if stress_dd < 0 else math.inf

    qqq = bench.etf_equity('QQQ', required_capital, start, end, refresh_benchmarks)
    spy = bench.etf_equity('SPY', required_capital, start, end, refresh_benchmarks)
    qqq_summary = bench.summarize_etf('QQQ same-cap buy-and-hold', qqq, required_capital)
    spy_summary = bench.summarize_etf('SPY same-cap buy-and-hold', spy, required_capital)

    account_daily = daily.copy()
    account_daily['strategy'] = spec.label
    account_daily['account_equity_3xdd'] = required_capital + account_daily['close_equity_usd']
    account_daily['account_stress_equity_3xdd'] = required_capital + account_daily['intrabar_stress_equity_usd']

    row = {
        'strategy': spec.label,
        'slug': spec.slug,
        'instrument': spec.instrument,
        'family': spec.family,
        'window_start': start,
        'window_end': end,
        'net_usd': net,
        'close_dd_usd': close_dd,
        'stress_dd_usd': stress_dd,
        'net_over_stress': net_stress,
        'required_capital_3xdd': required_capital,
        'return_on_3xdd_capital_pct': return_on_required,
        'qqq_same_cap_net_usd': float(qqq_summary['net']),
        'qqq_same_cap_dd_usd': float(qqq_summary['stress_dd']),
        'qqq_same_cap_return_pct': float(qqq_summary['net'] / required_capital * 100.0) if required_capital else math.nan,
        'strategy_net_minus_qqq_net': net - float(qqq_summary['net']),
        'strategy_net_over_qqq_net': net / float(qqq_summary['net']) if float(qqq_summary['net']) else math.inf,
        'spy_same_cap_net_usd': float(spy_summary['net']),
        'spy_same_cap_return_pct': float(spy_summary['net'] / required_capital * 100.0) if required_capital else math.nan,
        'max_open_units': float(daily['max_open_units'].max()),
    }
    return row, account_daily


def passive_reference(start: str, end: str, capital: float, refresh_benchmarks: bool) -> pd.DataFrame:
    rows = []
    specs = [
        ('QQQ buy-and-hold', bench.etf_equity('QQQ', capital, start, end, refresh_benchmarks)),
        ('QQQ monthly DCA cash-funded', etf_dca_equity('QQQ', capital, start, end, refresh_benchmarks)),
        ('SPY buy-and-hold', bench.etf_equity('SPY', capital, start, end, refresh_benchmarks)),
        ('DIA buy-and-hold', bench.etf_equity('DIA', capital, start, end, refresh_benchmarks)),
        (
            '50/50 QQQ+DIA buy-and-hold',
            bench.combined_etf_equity(['QQQ', 'DIA'], [0.5, 0.5], capital, start, end, refresh_benchmarks),
        ),
    ]
    for label, equity in specs:
        summary = bench.summarize_etf(label, equity, capital)
        net = float(summary['net'])
        dd = float(summary['stress_dd'])
        rows.append(
            {
                'benchmark': label,
                'window_start': start,
                'window_end': end,
                'start_capital': capital,
                'end_capital': float(summary['end_capital']),
                'net_usd': net,
                'max_dd_usd': dd,
                'return_pct': net / capital * 100.0,
                'net_over_dd': net / abs(dd) if dd < 0 else math.inf,
            }
        )
    return pd.DataFrame(rows)


def etf_dca_equity(symbol: str, capital: float, start: str, end: str, refresh_benchmarks: bool) -> pd.DataFrame:
    """Cash-funded monthly DCA from a fixed starting capital pool.

    This is not a paycheck-contribution model. It starts with the same capital
    as buy-and-hold, invests equal slices on the first available trading day of
    each month, and leaves the remaining cash idle until invested.
    """
    prices = bench.yahoo_daily(symbol, start, end, ROOT / 'data' / 'benchmarks', refresh_benchmarks)
    work = prices[['date', 'adj_close']].copy().sort_values('date').reset_index(drop=True)
    work['month'] = work['date'].dt.to_period('M')
    invest_dates = set(work.groupby('month')['date'].first())
    installments = len(invest_dates)
    installment = capital / installments if installments else 0.0
    cash = capital
    shares = 0.0
    rows = []
    for _, row in work.iterrows():
        date = row['date']
        price = float(row['adj_close'])
        invested = 0.0
        if date in invest_dates and cash > 0:
            invested = min(installment, cash)
            shares += invested / price
            cash -= invested
        rows.append(
            {
                'date': date,
                'symbol': f'{symbol.upper()} monthly DCA',
                'adj_close': price,
                'invested_today': invested,
                'cash': cash,
                'shares': shares,
                'equity': cash + shares * price,
                'invested_value': shares * price,
                'exposure_frac': (shares * price) / (cash + shares * price) if cash + shares * price else 0.0,
            }
        )
    return pd.DataFrame(rows)


def summarize_equity_path(equity: pd.DataFrame, capital: float, equity_col: str = 'equity') -> dict:
    values = pd.to_numeric(equity[equity_col], errors='coerce').dropna()
    if values.empty:
        return {'end_capital': capital, 'net': 0.0, 'stress_dd': 0.0, 'return_pct': 0.0, 'net_over_dd': math.inf}
    dd = float((values - values.cummax()).min())
    net = float(values.iloc[-1] - capital)
    return {
        'end_capital': float(values.iloc[-1]),
        'net': net,
        'stress_dd': dd,
        'return_pct': net / capital * 100.0 if capital else math.nan,
        'net_over_dd': net / abs(dd) if dd < 0 else math.inf,
    }


def dca_exposure_parity(
    strategy_summary: pd.DataFrame,
    daily_parts: list[pd.DataFrame],
    capital: float,
    refresh_benchmarks: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Scale futures daily PnL by the QQQ DCA invested fraction of the same account.

    This is analytical fractional-contract math.  If QQQ DCA is 10% invested,
    the futures strategy deploys 10% of the account's 3x-stress risk capacity.
    """
    by_strategy = {str(part.iloc[0]['strategy']): part.copy() for part in daily_parts if not part.empty}
    rows = []
    daily_rows = []
    for _, summary in strategy_summary.iterrows():
        strategy = str(summary['strategy'])
        base = by_strategy.get(strategy)
        if base is None or base.empty:
            continue
        start = str(summary['window_start'])
        end = str(summary['window_end'])
        dca = etf_dca_equity('QQQ', capital, start, end, refresh_benchmarks)
        dca_summary = summarize_equity_path(dca, capital)
        dca_avg_exposure = float(pd.to_numeric(dca['exposure_frac'], errors='coerce').fillna(0.0).mean())

        base = base.sort_values('date').reset_index(drop=True)
        dca_exposure = dca[['date', 'exposure_frac']].sort_values('date').reset_index(drop=True)
        merged = pd.merge_asof(base, dca_exposure, on='date', direction='backward')
        merged['exposure_frac'] = pd.to_numeric(merged['exposure_frac'], errors='coerce').fillna(0.0)

        required = float(summary['required_capital_3xdd'])
        full_account_base_units = capital / required if required else 0.0
        merged['scaled_base_units'] = full_account_base_units * merged['exposure_frac']
        merged['scaled_daily_pnl_usd'] = pd.to_numeric(merged['daily_pnl_usd'], errors='coerce').fillna(0.0) * merged['scaled_base_units']
        merged['account_equity_usd'] = capital + merged['scaled_daily_pnl_usd'].cumsum()
        active_heat = pd.to_numeric(merged['active_heat_usd'], errors='coerce').fillna(0.0) * merged['scaled_base_units']
        merged['account_stress_equity_usd'] = merged['account_equity_usd'] - active_heat
        merged['account_peak_equity_usd'] = merged['account_equity_usd'].cummax()
        merged['account_stress_dd_usd'] = merged['account_stress_equity_usd'] - merged['account_peak_equity_usd']
        merged['account_close_dd_usd'] = merged['account_equity_usd'] - merged['account_peak_equity_usd']

        net = float(merged.iloc[-1]['account_equity_usd'] - capital)
        stress_dd = float(merged['account_stress_dd_usd'].min())
        close_dd = float(merged['account_close_dd_usd'].min())
        rows.append(
            {
                'strategy': strategy,
                'slug': summary['slug'],
                'instrument': summary['instrument'],
                'window_start': start,
                'window_end': end,
                'start_capital': capital,
                'dca_avg_exposure_pct': dca_avg_exposure * 100.0,
                'futures_full_account_base_units': full_account_base_units,
                'futures_avg_base_units': float(merged['scaled_base_units'].mean()),
                'futures_peak_base_units': float(merged['scaled_base_units'].max()),
                'futures_exposure_parity_net_usd': net,
                'futures_exposure_parity_close_dd_usd': close_dd,
                'futures_exposure_parity_stress_dd_usd': stress_dd,
                'futures_exposure_parity_return_pct': net / capital * 100.0 if capital else math.nan,
                'futures_exposure_parity_net_over_stress': net / abs(stress_dd) if stress_dd < 0 else math.inf,
                'qqq_dca_net_usd': float(dca_summary['net']),
                'qqq_dca_dd_usd': float(dca_summary['stress_dd']),
                'qqq_dca_return_pct': float(dca_summary['return_pct']),
                'qqq_dca_net_over_dd': float(dca_summary['net_over_dd']),
                'futures_minus_qqq_dca_net_usd': net - float(dca_summary['net']),
            }
        )

        keep = merged[
            [
                'date',
                'strategy',
                'exposure_frac',
                'scaled_base_units',
                'scaled_daily_pnl_usd',
                'account_equity_usd',
                'account_stress_equity_usd',
                'account_stress_dd_usd',
            ]
        ].copy()
        keep['qqq_dca_equity_usd'] = pd.merge_asof(
            keep[['date']].sort_values('date'),
            dca[['date', 'equity']].sort_values('date'),
            on='date',
            direction='backward',
        )['equity'].values
        daily_rows.append(keep)
    return pd.DataFrame(rows), pd.concat(daily_rows, ignore_index=True) if daily_rows else pd.DataFrame()


def common_account_executable_ranking(
    strategy_summary: pd.DataFrame,
    daily_parts: list[pd.DataFrame],
    capital: float,
    refresh_benchmarks: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rank futures rows from one common account using integer 3x-stress books."""
    by_strategy = {str(part.iloc[0]['strategy']): part.copy() for part in daily_parts if not part.empty}
    rows = []
    daily_rows = []
    for _, summary in strategy_summary.iterrows():
        strategy = str(summary['strategy'])
        base = by_strategy.get(strategy)
        if base is None or base.empty:
            continue
        required = float(summary['required_capital_3xdd'])
        books = int(capital // required) if required else 0
        start = str(summary['window_start'])
        end = str(summary['window_end'])
        qqq_bh = bench.etf_equity('QQQ', capital, start, end, refresh_benchmarks)
        qqq_dca = etf_dca_equity('QQQ', capital, start, end, refresh_benchmarks)
        qqq_bh_summary = bench.summarize_etf('QQQ buy-and-hold common account', qqq_bh, capital)
        qqq_dca_summary = summarize_equity_path(qqq_dca, capital)

        work = base.sort_values('date').reset_index(drop=True).copy()
        work['common_books'] = books
        work['account_equity_usd'] = capital + pd.to_numeric(work['close_equity_usd'], errors='coerce').fillna(0.0) * books
        work['account_close_dd_usd'] = pd.to_numeric(work['close_dd_usd'], errors='coerce').fillna(0.0) * books
        work['account_stress_dd_usd'] = pd.to_numeric(work['stress_dd_usd'], errors='coerce').fillna(0.0) * books
        work['account_peak_equity_usd'] = work['account_equity_usd'] - work['account_close_dd_usd']
        work['account_stress_equity_usd'] = work['account_peak_equity_usd'] + work['account_stress_dd_usd']
        net = float(work.iloc[-1]['account_equity_usd'] - capital)
        stress_dd = float(work['account_stress_dd_usd'].min())
        close_dd = float(work['account_close_dd_usd'].min())
        rows.append(
            {
                'strategy': strategy,
                'slug': summary['slug'],
                'instrument': summary['instrument'],
                'window_start': start,
                'window_end': end,
                'start_capital': capital,
                'required_capital_per_book_3xdd': required,
                'integer_books': books,
                'capital_used_3xdd': required * books,
                'idle_cash_by_3xdd_rule': capital - required * books,
                'futures_net_usd': net,
                'futures_close_dd_usd': close_dd,
                'futures_stress_dd_usd': stress_dd,
                'futures_return_pct': net / capital * 100.0 if capital else math.nan,
                'futures_net_over_stress': net / abs(stress_dd) if stress_dd < 0 else math.inf,
                'qqq_buyhold_net_usd': float(qqq_bh_summary['net']),
                'qqq_buyhold_dd_usd': float(qqq_bh_summary['stress_dd']),
                'qqq_buyhold_return_pct': float(qqq_bh_summary['net']) / capital * 100.0 if capital else math.nan,
                'qqq_dca_net_usd': float(qqq_dca_summary['net']),
                'qqq_dca_dd_usd': float(qqq_dca_summary['stress_dd']),
                'qqq_dca_return_pct': float(qqq_dca_summary['return_pct']),
                'futures_minus_qqq_dca_net_usd': net - float(qqq_dca_summary['net']),
                'futures_minus_qqq_buyhold_net_usd': net - float(qqq_bh_summary['net']),
            }
        )

        daily_rows.append(
            work[
                [
                    'date',
                    'strategy',
                    'common_books',
                    'account_equity_usd',
                    'account_stress_equity_usd',
                    'account_close_dd_usd',
                    'account_stress_dd_usd',
                ]
            ].copy()
        )
    ranking = pd.DataFrame(rows).sort_values(['futures_return_pct', 'futures_net_over_stress'], ascending=False)
    daily = pd.concat(daily_rows, ignore_index=True) if daily_rows else pd.DataFrame()
    return ranking, daily


def max_stress_normalized_ranking(
    strategy_summary: pd.DataFrame,
    daily_parts: list[pd.DataFrame],
    refresh_benchmarks: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Scale every futures row to the largest 3x-stress capital requirement."""
    by_strategy = {str(part.iloc[0]['strategy']): part.copy() for part in daily_parts if not part.empty}
    common_capital = float(pd.to_numeric(strategy_summary['required_capital_3xdd'], errors='coerce').max())
    rows = []
    daily_rows = []
    for _, summary in strategy_summary.iterrows():
        strategy = str(summary['strategy'])
        base = by_strategy.get(strategy)
        if base is None or base.empty:
            continue
        required = float(summary['required_capital_3xdd'])
        scale = common_capital / required if required else 0.0
        start = str(summary['window_start'])
        end = str(summary['window_end'])
        qqq_bh = bench.etf_equity('QQQ', common_capital, start, end, refresh_benchmarks)
        qqq_dca = etf_dca_equity('QQQ', common_capital, start, end, refresh_benchmarks)
        qqq_bh_summary = bench.summarize_etf('QQQ buy-and-hold normalized account', qqq_bh, common_capital)
        qqq_dca_summary = summarize_equity_path(qqq_dca, common_capital)

        work = base.sort_values('date').reset_index(drop=True).copy()
        work['scale_factor_base_books'] = scale
        work['account_equity_usd'] = common_capital + pd.to_numeric(work['close_equity_usd'], errors='coerce').fillna(0.0) * scale
        work['account_close_dd_usd'] = pd.to_numeric(work['close_dd_usd'], errors='coerce').fillna(0.0) * scale
        work['account_stress_dd_usd'] = pd.to_numeric(work['stress_dd_usd'], errors='coerce').fillna(0.0) * scale
        work['account_peak_equity_usd'] = work['account_equity_usd'] - work['account_close_dd_usd']
        work['account_stress_equity_usd'] = work['account_peak_equity_usd'] + work['account_stress_dd_usd']
        net = float(work.iloc[-1]['account_equity_usd'] - common_capital)
        stress_dd = float(work['account_stress_dd_usd'].min())
        close_dd = float(work['account_close_dd_usd'].min())
        rows.append(
            {
                'strategy': strategy,
                'slug': summary['slug'],
                'instrument': summary['instrument'],
                'window_start': start,
                'window_end': end,
                'start_capital': common_capital,
                'base_required_capital_3xdd': required,
                'scale_factor_base_books': scale,
                'scaled_net_usd': net,
                'scaled_close_dd_usd': close_dd,
                'scaled_stress_dd_usd': stress_dd,
                'scaled_return_pct': net / common_capital * 100.0 if common_capital else math.nan,
                'scaled_net_over_stress': net / abs(stress_dd) if stress_dd < 0 else math.inf,
                'qqq_buyhold_net_usd': float(qqq_bh_summary['net']),
                'qqq_buyhold_dd_usd': float(qqq_bh_summary['stress_dd']),
                'qqq_buyhold_return_pct': float(qqq_bh_summary['net']) / common_capital * 100.0 if common_capital else math.nan,
                'qqq_dca_net_usd': float(qqq_dca_summary['net']),
                'qqq_dca_dd_usd': float(qqq_dca_summary['stress_dd']),
                'qqq_dca_return_pct': float(qqq_dca_summary['return_pct']),
                'futures_minus_qqq_dca_net_usd': net - float(qqq_dca_summary['net']),
                'futures_minus_qqq_buyhold_net_usd': net - float(qqq_bh_summary['net']),
            }
        )

        daily_rows.append(
            work[
                [
                    'date',
                    'strategy',
                    'scale_factor_base_books',
                    'account_equity_usd',
                    'account_stress_equity_usd',
                    'account_close_dd_usd',
                    'account_stress_dd_usd',
                ]
            ].copy()
        )
    ranking = pd.DataFrame(rows).sort_values(['scaled_return_pct', 'scaled_net_over_stress'], ascending=False)
    daily = pd.concat(daily_rows, ignore_index=True) if daily_rows else pd.DataFrame()
    return ranking, daily


def summary_lookup(rows: pd.DataFrame, slug: str) -> pd.Series:
    match = rows[rows['slug'].eq(slug)]
    if match.empty:
        raise ValueError(f'Missing computed summary for {slug}')
    return match.iloc[0]


def dca_same_stress(summary: pd.DataFrame) -> pd.DataFrame:
    pairs = [
        ('nq_atr_daily_ladder112221_10max', 'nq_yearly_orb_scaleout3'),
        ('nq_atr_daily_3initial_10max', 'nq_yearly_orb_scaleout3'),
        ('mnq_atr_daily_ladder112221_10max', 'mnq_yearly_orb_scaleout3'),
        ('mnq_atr_daily_3initial_10max', 'mnq_yearly_orb_scaleout3'),
    ]
    rows = []
    for dca_slug, benchmark_slug in pairs:
        dca = summary_lookup(summary, dca_slug)
        bench_row = summary_lookup(summary, benchmark_slug)
        dca_stress = abs(float(dca['stress_dd_usd']))
        bench_stress = abs(float(bench_row['stress_dd_usd']))
        ratio = dca_stress / bench_stress if bench_stress else math.inf
        same_stress_net = float(bench_row['net_usd']) * ratio
        integer_bundles = int(dca_stress // bench_stress) if bench_stress else 0
        rows.append(
            {
                'dca_strategy': dca['strategy'],
                'benchmark_sized_strategy': bench_row['strategy'],
                'dca_net_usd': float(dca['net_usd']),
                'dca_stress_dd_usd': float(dca['stress_dd_usd']),
                'dca_net_over_stress': float(dca['net_over_stress']),
                'same_stress_sized_strategy_net_usd': same_stress_net,
                'same_stress_sized_strategy_stress_dd_usd': -dca_stress,
                'same_stress_sized_strategy_net_over_stress': float(bench_row['net_over_stress']),
                'dca_minus_same_stress_sized_strategy_net_usd': float(dca['net_usd']) - same_stress_net,
                'stress_ratio_to_benchmark': ratio,
                'integer_benchmark_bundles_at_or_under_dca_stress': integer_bundles,
                'integer_benchmark_net_usd': float(bench_row['net_usd']) * integer_bundles,
                'integer_benchmark_stress_dd_usd': -bench_stress * integer_bundles,
            }
        )
    return pd.DataFrame(rows)


def write_report(
    strategy_summary: pd.DataFrame,
    passive_primary: pd.DataFrame,
    dca: pd.DataFrame,
    max_stress_normalized: pd.DataFrame,
    common_account: pd.DataFrame,
    exposure_parity: pd.DataFrame,
    high_capital_exposure_parity: pd.DataFrame,
    high_capital: float,
    passive_start: str,
    passive_end: str,
    passive_capital: float,
    outputs: Iterable[Path],
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ranked = strategy_summary.sort_values('net_over_stress', ascending=False)

    lines = [
        '# Top Strategy Fair Benchmark',
        '',
        'This report compares passive buy-and-hold to the current top broker-like strategy rows without changing any strategy rules.',
        '',
        'Method:',
        '',
        '- The exact normalized comparison uses the largest 3x-stress capital requirement in the selected set as the starting balance for every futures setup.',
        '- Normalized futures rows scale each replay by `common capital / row required 3x-stress capital`; this is fractional-book comparison math, so every model is given the same stress-capital budget.',
        f'- The **{money(passive_capital)} common-account executable table** remains as the practical whole-book view: integer futures books only, with idle cash left idle.',
        '- QQQ rows use the same starting account and the same strategy window where a futures row is being compared.',
        '- Strategy rows use their existing replay equity curves and are capitalized at **3 x max intrabar stress DD**.',
        '- QQQ/SPY same-cap rows invest that exact 3x-stress capital over the same replay window as each strategy.',
        '- The required-capital diagnostic is a fixed one-base-book comparison; it does not compound futures size. The existing `SCALING_10Y.md` report remains the account-resized compounding view.',
        '- QQQ monthly DCA is cash-funded from the same starting capital: equal monthly buys, no new contributions, no cash interest.',
        '- The DCA section does not compare DCA to buy-and-hold only; it compares DCA to simply sizing up the strongest same-market yearly ORB book to the same stress budget.',
        '- This is comparison math only. It does not optimize entries, exits, sizing, or filters.',
        '',
        '## Passive Reference',
        '',
        f'Starting capital: **{money(passive_capital)}**. Window: **{passive_start} through {passive_end}**.',
        '',
        '| Benchmark | End Capital | Net | Max DD | Return | Net/DD |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for _, row in passive_primary.sort_values('net_over_dd', ascending=False).iterrows():
        lines.append(
            f"| {row['benchmark']} | {money(row['end_capital'])} | {money(row['net_usd'])} | "
            f"{money(row['max_dd_usd'])} | {pct(row['return_pct'])} | {row['net_over_dd']:.2f} |"
        )

    normalized_capital = float(max_stress_normalized['start_capital'].iloc[0]) if not max_stress_normalized.empty else 0.0
    normalized_anchor = ''
    if not max_stress_normalized.empty:
        anchor = max_stress_normalized.sort_values('base_required_capital_3xdd', ascending=False).iloc[0]
        normalized_anchor = f" The current anchor is {anchor['strategy']} at {money(anchor['base_required_capital_3xdd'])}."

    lines.extend(
        [
            '',
            f'## Max 3x-Stress Normalized Ranking ({money(normalized_capital)})',
            '',
            'This is the exact apples-to-apples capital-efficiency table. The starting balance equals the largest 3x-stress requirement among the selected futures rows, and every strategy is scaled by that balance divided by its own 3x-stress requirement. Fractional base books are allowed here because this is comparison math, not an order-size plan.' + normalized_anchor,
            '',
            '| Rank | Strategy | Window | Scale | Base 3x Capital | Scaled Net | Return | Stress DD | Net/DD | Same-Window QQQ DCA Net | Futures - DCA |',
            '|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|',
        ]
    )
    for rank, (_, row) in enumerate(max_stress_normalized.iterrows(), start=1):
        lines.append(
            f"| {rank} | {row['strategy']} | {row['window_start']} to {row['window_end']} | "
            f"{row['scale_factor_base_books']:.2f}x | {money(row['base_required_capital_3xdd'])} | "
            f"{money(row['scaled_net_usd'])} | {pct(row['scaled_return_pct'])} | {money(row['scaled_stress_dd_usd'])} | "
            f"{row['scaled_net_over_stress']:.2f} | {money(row['qqq_dca_net_usd'])} | {money(row['futures_minus_qqq_dca_net_usd'])} |"
        )

    lines.extend(
        [
            '',
            f'## Common {money(passive_capital)} Executable Ranking',
            '',
            'This is the practical executable version: one account size for every setup, integer futures books only, and idle cash left idle. Rows are sorted by return on the common account; Net/DD is retained as the risk-efficiency check.',
            '',
            '| Rank | Strategy | Window | Books | 3x Capital Used | Idle Cash | Futures Net | Return | Stress DD | Net/DD | Same-Window QQQ DCA Net | Futures - DCA |',
            '|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
        ]
    )
    for rank, (_, row) in enumerate(common_account.iterrows(), start=1):
        lines.append(
            f"| {rank} | {row['strategy']} | {row['window_start']} to {row['window_end']} | "
            f"{int(row['integer_books'])} | {money(row['capital_used_3xdd'])} | {money(row['idle_cash_by_3xdd_rule'])} | "
            f"{money(row['futures_net_usd'])} | {pct(row['futures_return_pct'])} | {money(row['futures_stress_dd_usd'])} | "
            f"{row['futures_net_over_stress']:.2f} | {money(row['qqq_dca_net_usd'])} | {money(row['futures_minus_qqq_dca_net_usd'])} |"
        )

    lines.extend(
        [
            '',
            '## Required-Capital Diagnostic',
            '',
            'This older diagnostic keeps each futures row at one base book and compares QQQ/SPY at that row’s 3x-stress required capital. Keep it for stress sizing context, but use the max-stress normalized table above for exact cross-setup ranking.',
            '',
            '| Strategy | Window | Net | Stress DD | 3x Stress Capital | Return on 3x Capital | Net/Stress | QQQ Same-Cap Net | Strategy / QQQ Net |',
            '|---|---|---:|---:|---:|---:|---:|---:|---:|',
        ]
    )
    for _, row in ranked.iterrows():
        lines.append(
            f"| {row['strategy']} | {row['window_start']} to {row['window_end']} | {money(row['net_usd'])} | "
            f"{money(row['stress_dd_usd'])} | {money(row['required_capital_3xdd'])} | "
            f"{pct(row['return_on_3xdd_capital_pct'])} | {row['net_over_stress']:.2f} | "
            f"{money(row['qqq_same_cap_net_usd'])} | {row['strategy_net_over_qqq_net']:.2f}x |"
        )

    lines.extend(
        [
            '',
            '## DCA vs Sizing Up',
            '',
            '| DCA Strategy | Same-Stress Sized Strategy | DCA Net | DCA Stress | Sized Strategy Net | Delta vs Sized Strategy | Integer Sized Bundles Under DCA Stress |',
            '|---|---|---:|---:|---:|---:|---:|',
        ]
    )
    for _, row in dca.iterrows():
        lines.append(
            f"| {row['dca_strategy']} | {row['benchmark_sized_strategy']} | {money(row['dca_net_usd'])} | "
            f"{money(row['dca_stress_dd_usd'])} | {money(row['same_stress_sized_strategy_net_usd'])} | "
            f"{money(row['dca_minus_same_stress_sized_strategy_net_usd'])} | "
            f"{int(row['integer_benchmark_bundles_at_or_under_dca_stress'])} |"
        )

    lines.extend(
        [
            '',
            '## QQQ DCA Exposure-Parity vs Futures',
            '',
            f'Starting capital: **{money(passive_capital)}**. For each futures row, the futures book is scaled by the QQQ monthly-DCA invested fraction over the same window. If QQQ DCA is 10% invested, futures deploys 10% of the account\'s 3x-stress risk capacity. This is fractional-contract comparison math, not an executable order-size plan.',
            '',
            '| Futures Strategy | Window | QQQ DCA Avg Exposure | Futures Avg Base Units | Futures Net | Futures Stress DD | Futures Net/DD | QQQ DCA Net | QQQ DCA DD | Futures - QQQ DCA |',
            '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|',
        ]
    )
    for _, row in exposure_parity.sort_values('futures_minus_qqq_dca_net_usd', ascending=False).iterrows():
        lines.append(
            f"| {row['strategy']} | {row['window_start']} to {row['window_end']} | "
            f"{pct(row['dca_avg_exposure_pct'])} | {row['futures_avg_base_units']:.2f} | "
            f"{money(row['futures_exposure_parity_net_usd'])} | {money(row['futures_exposure_parity_stress_dd_usd'])} | "
            f"{row['futures_exposure_parity_net_over_stress']:.2f} | {money(row['qqq_dca_net_usd'])} | "
            f"{money(row['qqq_dca_dd_usd'])} | {money(row['futures_minus_qqq_dca_net_usd'])} |"
        )

    if high_capital_exposure_parity is not None and not high_capital_exposure_parity.empty and high_capital != passive_capital:
        lines.extend(
            [
                '',
                f'## QQQ DCA Exposure-Parity Sensitivity ({money(high_capital)})',
                '',
                'Same method as above, but with a larger starting account for the high-stress futures books. Because both QQQ DCA and fractional futures exposure scale from the same account, this changes dollars but not the underlying relative math. It does show which books become closer to full-bundle executable.',
                '',
                '| Futures Strategy | Window | Futures Avg Base Units | Futures Peak Base Units | Futures Net | Futures Stress DD | QQQ DCA Net | Futures - QQQ DCA |',
                '|---|---|---:|---:|---:|---:|---:|---:|',
            ]
        )
        for _, row in high_capital_exposure_parity.sort_values('futures_minus_qqq_dca_net_usd', ascending=False).iterrows():
            lines.append(
                f"| {row['strategy']} | {row['window_start']} to {row['window_end']} | "
                f"{row['futures_avg_base_units']:.2f} | {row['futures_peak_base_units']:.2f} | "
                f"{money(row['futures_exposure_parity_net_usd'])} | {money(row['futures_exposure_parity_stress_dd_usd'])} | "
                f"{money(row['qqq_dca_net_usd'])} | {money(row['futures_minus_qqq_dca_net_usd'])} |"
            )

    nq_gate = ranked[ranked['slug'].eq('nq_v2b_prior_opposed_stpmc_only_S_1_1_3')]
    dca_loses = dca[dca['dca_minus_same_stress_sized_strategy_net_usd'] < 0]
    exposure_wins = exposure_parity[exposure_parity['futures_minus_qqq_dca_net_usd'] > 0]
    exposure_losses = exposure_parity[exposure_parity['futures_minus_qqq_dca_net_usd'] < 0]
    required_lookup = strategy_summary.set_index('strategy')['required_capital_3xdd'].to_dict()
    normalized_best = max_stress_normalized.iloc[0] if not max_stress_normalized.empty else None
    common_best = common_account.iloc[0] if not common_account.empty else None
    lines.extend(
        [
            '',
            '## Read',
            '',
        ]
    )
    if not nq_gate.empty:
        r = nq_gate.iloc[0]
        lines.append(
            f"- The NQ prior-opposed v2b gate remains the cleanest row on capital efficiency: "
            f"{money(r['net_usd'])} net on {money(r['required_capital_3xdd'])} of 3x-stress capital "
            f"({pct(r['return_on_3xdd_capital_pct'])}, {r['net_over_stress']:.2f} Net/Stress)."
        )
    if normalized_best is not None:
        lines.append(
            f"- On the max-stress normalized table, every futures row starts with {money(normalized_best['start_capital'])}; "
            f"the top row is {normalized_best['strategy']} at {normalized_best['scale_factor_base_books']:.2f}x base size, "
            f"{money(normalized_best['scaled_net_usd'])} net, {pct(normalized_best['scaled_return_pct'])} return, "
            f"and {normalized_best['scaled_net_over_stress']:.2f} Net/DD."
        )
    if common_best is not None:
        lines.append(
            f"- On the {money(passive_capital)} common-account table, the top executable row is "
            f"{common_best['strategy']} with {int(common_best['integer_books'])} books, "
            f"{money(common_best['futures_net_usd'])} net, {pct(common_best['futures_return_pct'])} return, "
            f"and {common_best['futures_net_over_stress']:.2f} Net/DD."
        )
    lines.extend(
        [
            '- Buy-and-hold is straightforward: QQQ is the strongest absolute passive benchmark in the reference window, while SPY is a little cleaner on drawdown efficiency; both remain far below the leading futures rows on Net/DD.',
            '- QQQ monthly DCA is now tracked as its own ETF strategy row. It gives up upside versus lump-sum QQQ in this rising window, but the lower drawdown makes it a serious lower-stress passive baseline.',
            '- The DCA check is the important wrinkle: the top NQ/MNQ ATR DCA rows do not beat simply sizing up the same-market yearly ORB book to the same stress budget.',
            '- The exposure-parity table remains a useful QQQ-DCA deployment lens: same starting capital, and futures exposure rises with the QQQ DCA invested fraction instead of comparing a small fixed futures book to a larger gradually invested ETF account.',
        ]
    )
    if not exposure_wins.empty:
        best = exposure_wins.sort_values('futures_minus_qqq_dca_net_usd', ascending=False).iloc[0]
        lines.append(
            f"- Best exposure-parity futures edge over QQQ DCA: {best['strategy']} beats same-window QQQ DCA by "
            f"{money(best['futures_minus_qqq_dca_net_usd'])} on a {money(best['start_capital'])} account."
        )
    if not exposure_losses.empty:
        worst_exp = exposure_losses.sort_values('futures_minus_qqq_dca_net_usd').iloc[0]
        lines.append(
            f"- Worst exposure-parity shortfall versus QQQ DCA: {worst_exp['strategy']} trails by "
            f"{money(abs(worst_exp['futures_minus_qqq_dca_net_usd']))}."
        )
    high_notes = []
    for name in ['ES Yearly ORB scaleout3', 'YM Yearly ORB scaleout3', 'NQ Yearly ORB scaleout3', 'NQ ATR daily ladder 1/1/2/2/2 10-max']:
        required = required_lookup.get(name)
        if required is not None:
            high_notes.append(f"{name} requires {money(required)}")
    if high_notes:
        feasible = [name for name, required in required_lookup.items() if required <= passive_capital]
        infeasible = [name for name, required in required_lookup.items() if required > passive_capital]
        feasible_note = ', '.join(feasible) if feasible else 'none'
        infeasible_note = ', '.join(infeasible) if infeasible else 'none'
        lines.append(
            f"- At {money(passive_capital)}, full 3x-stress one-bundle feasibility is: feasible = {feasible_note}; "
            f"still above account size = {infeasible_note}. Required-capital anchors: "
            + '; '.join(high_notes)
            + '.'
        )
    if not dca_loses.empty:
        worst = dca_loses.sort_values('dca_minus_same_stress_sized_strategy_net_usd').iloc[0]
        lines.append(
            f"- Largest DCA shortfall in this comparison: {worst['dca_strategy']} trails same-stress "
            f"{worst['benchmark_sized_strategy']} by {money(abs(worst['dca_minus_same_stress_sized_strategy_net_usd']))}."
        )
    lines.extend(
        [
            '- That does not make ATR/DCA useless; it means DCA needs to justify its operational complexity against a sized-up simpler sleeve, not just against passive QQQ.',
            '',
            '## Outputs',
            '',
        ]
    )
    for path in outputs:
        lines.append(f'- `{path.relative_to(ROOT)}`')
    (OUT_DIR / 'TOP_STRATS.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--refresh-benchmarks', action='store_true')
    ap.add_argument('--buffer-mult', type=float, default=3.0)
    ap.add_argument('--passive-start', default='2021-03-04')
    ap.add_argument('--passive-end', default='2026-03-06')
    ap.add_argument('--passive-capital', type=float, default=1_000_000.0)
    ap.add_argument('--high-stress-capital', type=float, default=1_000_000.0)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    rows: list[dict] = []
    daily_parts: list[pd.DataFrame] = []
    for spec in selected_specs():
        row, daily = strategy_metrics(spec, args.refresh_benchmarks, args.buffer_mult)
        rows.append(row)
        daily_parts.append(daily)

    strategy_summary = pd.DataFrame(rows)
    summary_path = OUT_DIR / 'top_strats_3xdd_vs_buyhold.csv'
    strategy_summary.to_csv(summary_path, index=False)
    outputs.append(summary_path)

    daily_path = OUT_DIR / 'top_strats_3xdd_daily_equity.csv'
    pd.concat(daily_parts, ignore_index=True).to_csv(daily_path, index=False)
    outputs.append(daily_path)

    passive = passive_reference(args.passive_start, args.passive_end, args.passive_capital, args.refresh_benchmarks)
    passive_path = OUT_DIR / 'top_strats_passive_reference.csv'
    passive.to_csv(passive_path, index=False)
    outputs.append(passive_path)

    qqq_dca_daily = etf_dca_equity(
        'QQQ',
        args.passive_capital,
        args.passive_start,
        args.passive_end,
        args.refresh_benchmarks,
    )
    qqq_dca_daily_path = OUT_DIR / 'top_strats_qqq_monthly_dca_daily.csv'
    qqq_dca_daily.to_csv(qqq_dca_daily_path, index=False)
    outputs.append(qqq_dca_daily_path)

    dca = dca_same_stress(strategy_summary)
    dca_path = OUT_DIR / 'top_strats_dca_same_stress.csv'
    dca.to_csv(dca_path, index=False)
    outputs.append(dca_path)

    max_stress_normalized, max_stress_normalized_daily = max_stress_normalized_ranking(
        strategy_summary=strategy_summary,
        daily_parts=daily_parts,
        refresh_benchmarks=args.refresh_benchmarks,
    )
    max_stress_normalized_path = OUT_DIR / 'top_strats_max_stress_normalized.csv'
    max_stress_normalized.to_csv(max_stress_normalized_path, index=False)
    outputs.append(max_stress_normalized_path)
    max_stress_normalized_daily_path = OUT_DIR / 'top_strats_max_stress_normalized_daily.csv'
    max_stress_normalized_daily.to_csv(max_stress_normalized_daily_path, index=False)
    outputs.append(max_stress_normalized_daily_path)

    common_account, common_account_daily = common_account_executable_ranking(
        strategy_summary=strategy_summary,
        daily_parts=daily_parts,
        capital=args.passive_capital,
        refresh_benchmarks=args.refresh_benchmarks,
    )
    common_account_path = OUT_DIR / 'top_strats_common_account_executable.csv'
    common_account.to_csv(common_account_path, index=False)
    outputs.append(common_account_path)
    common_account_daily_path = OUT_DIR / 'top_strats_common_account_executable_daily.csv'
    common_account_daily.to_csv(common_account_daily_path, index=False)
    outputs.append(common_account_daily_path)

    exposure_parity, exposure_parity_daily = dca_exposure_parity(
        strategy_summary=strategy_summary,
        daily_parts=daily_parts,
        capital=args.passive_capital,
        refresh_benchmarks=args.refresh_benchmarks,
    )
    exposure_parity_path = OUT_DIR / 'top_strats_qqq_dca_exposure_parity.csv'
    exposure_parity.to_csv(exposure_parity_path, index=False)
    outputs.append(exposure_parity_path)
    exposure_parity_daily_path = OUT_DIR / 'top_strats_qqq_dca_exposure_parity_daily.csv'
    exposure_parity_daily.to_csv(exposure_parity_daily_path, index=False)
    outputs.append(exposure_parity_daily_path)

    high_capital_exposure_parity = pd.DataFrame()
    if args.high_stress_capital != args.passive_capital:
        high_capital_exposure_parity, high_capital_exposure_parity_daily = dca_exposure_parity(
            strategy_summary=strategy_summary,
            daily_parts=daily_parts,
            capital=args.high_stress_capital,
            refresh_benchmarks=args.refresh_benchmarks,
        )
        high_capital_tag = str(int(args.high_stress_capital / 1000)) + 'k'
        high_capital_exposure_parity_path = OUT_DIR / f'top_strats_qqq_dca_exposure_parity_{high_capital_tag}.csv'
        high_capital_exposure_parity.to_csv(high_capital_exposure_parity_path, index=False)
        outputs.append(high_capital_exposure_parity_path)
        high_capital_exposure_parity_daily_path = OUT_DIR / f'top_strats_qqq_dca_exposure_parity_{high_capital_tag}_daily.csv'
        high_capital_exposure_parity_daily.to_csv(high_capital_exposure_parity_daily_path, index=False)
        outputs.append(high_capital_exposure_parity_daily_path)

    write_report(
        strategy_summary=strategy_summary,
        passive_primary=passive,
        dca=dca,
        max_stress_normalized=max_stress_normalized,
        common_account=common_account,
        exposure_parity=exposure_parity,
        high_capital_exposure_parity=high_capital_exposure_parity,
        high_capital=args.high_stress_capital,
        passive_start=args.passive_start,
        passive_end=args.passive_end,
        passive_capital=args.passive_capital,
        outputs=outputs,
    )
    print(f'Wrote {OUT_DIR / "TOP_STRATS.md"}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
