#!/usr/bin/env python3
"""Write trade-level volume profile tables for current ORB and ATR leaders."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ORB_VARIANT = 'yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close'
ATR_VARIANT = 'atr_supertrend_weekly_primary_biweekly_10max_entry_guard_3initial'

MARKETS = {
    'mnq': {'daily': ROOT / 'mnq' / 'mnq_daily.csv', 'point_value': 2.0},
    'nq': {'daily': ROOT / 'nq' / 'nq_daily.csv', 'point_value': 20.0},
}


def add_volume_features(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    day = daily.copy().sort_values('date').reset_index(drop=True)
    day['date'] = pd.to_datetime(day['date']).dt.normalize()
    day['volume'] = pd.to_numeric(day['volume'], errors='coerce').fillna(0.0)
    day['vol_avg20_prior'] = day['volume'].shift(1).rolling(20, min_periods=5).mean()
    day['vol_x20_prior'] = day['volume'] / day['vol_avg20_prior']
    day['year'] = day['date'].dt.year

    week = day.copy()
    week['week'] = week['date'].dt.to_period('W-FRI')
    weekly = (
        week.groupby('week', sort=True)
        .agg(
            week_start=('date', 'min'),
            week_end=('date', 'max'),
            volume=('volume', 'sum'),
            open=('open', 'first'),
            close=('close', 'last'),
        )
        .reset_index()
    )
    weekly['vol_avg20_prior'] = weekly['volume'].shift(1).rolling(20, min_periods=5).mean()
    weekly['vol_x20_prior'] = weekly['volume'] / weekly['vol_avg20_prior']
    return day, weekly


def day_feature(day: pd.DataFrame, value: object, prefix: str) -> dict:
    if pd.isna(value) or str(value).strip() == '':
        return {f'{prefix}_date': '', f'{prefix}_volume': 0.0, f'{prefix}_vol_x20_prior': float('nan')}
    date = pd.Timestamp(value).normalize()
    row = day[day['date'].eq(date)]
    if row.empty:
        return {f'{prefix}_date': str(date.date()), f'{prefix}_volume': 0.0, f'{prefix}_vol_x20_prior': float('nan')}
    row = row.iloc[0]
    return {
        f'{prefix}_date': str(date.date()),
        f'{prefix}_volume': float(row['volume']),
        f'{prefix}_vol_x20_prior': float(row['vol_x20_prior']) if pd.notna(row['vol_x20_prior']) else float('nan'),
    }


def week_feature(weekly: pd.DataFrame, value: object, prefix: str) -> dict:
    if pd.isna(value) or str(value).strip() == '':
        return {f'{prefix}_week_volume': 0.0, f'{prefix}_week_vol_x20_prior': float('nan')}
    date = pd.Timestamp(value).normalize()
    rows = weekly[(weekly['week_start'] <= date) & (weekly['week_end'] >= date)]
    if rows.empty:
        return {f'{prefix}_week_volume': 0.0, f'{prefix}_week_vol_x20_prior': float('nan')}
    row = rows.iloc[0]
    return {
        f'{prefix}_week_volume': float(row['volume']),
        f'{prefix}_week_vol_x20_prior': float(row['vol_x20_prior']) if pd.notna(row['vol_x20_prior']) else float('nan'),
    }


def bucket(value: float) -> str:
    if pd.isna(value):
        return 'n/a'
    if value < 0.8:
        return '<0.8x'
    if value < 1.2:
        return '0.8-1.2x'
    if value < 2.0:
        return '1.2-2.0x'
    return '>=2.0x'


def summarize(rows: pd.DataFrame, ratio_col: str, pnl_col: str) -> pd.DataFrame:
    if rows.empty:
        return pd.DataFrame()
    work = rows.copy()
    work['bucket'] = work[ratio_col].map(bucket)
    work['win'] = pd.to_numeric(work[pnl_col], errors='coerce').fillna(0.0) > 0
    grouped = work.groupby('bucket', sort=False).agg(
        rows=(pnl_col, 'size'),
        wins=('win', 'sum'),
        win_rate=('win', 'mean'),
        net=(pnl_col, 'sum'),
        avg=(pnl_col, 'mean'),
    )
    grouped['win_rate'] = grouped['win_rate'] * 100
    return grouped.reset_index()


def write_summary(path: Path, title: str, profile: pd.DataFrame, ratio_col: str, pnl_col: str, point_value: float) -> None:
    summary = summarize(profile, ratio_col, pnl_col)
    lines = [
        f'# {title}',
        '',
        'Trade-level volume profile using causal prior-average ratios. `1.20x` means the signal/entry volume was 20% above the prior 20-session average.',
        '',
        f'Rows: `{len(profile)}`',
        '',
        '| Volume bucket | Rows | Wins | Win rate | Net pts | Net $ | Avg pts |',
        '|---|---:|---:|---:|---:|---:|---:|',
    ]
    if summary.empty:
        lines.append('| n/a | 0 | 0 | 0.0% | +0.00 | $+0 | +0.00 |')
    else:
        for _, row in summary.iterrows():
            net = float(row['net'])
            avg = float(row['avg'])
            lines.append(
                f"| {row['bucket']} | {int(row['rows'])} | {int(row['wins'])} | {float(row['win_rate']):.1f}% | "
                f"{net:+.2f} | ${net * point_value:+,.0f} | {avg:+.2f} |"
            )
    lines.extend(['', f'CSV: [`{path.name}`]({path.name})', ''])
    summary_path = path.parent / 'VOLUME_PROFILE.md'
    summary_path.write_text('\n'.join(lines), encoding='utf-8')
    index_path = path.parent / 'INDEX.md'
    if index_path.exists():
        text = index_path.read_text(encoding='utf-8')
        line = '- [Trade-level volume profile](VOLUME_PROFILE.md)'
        if line not in text:
            insert = f'\n{line}\n'
            if '\n| Year |' in text:
                text = text.replace('\n| Year |', insert + '\n| Year |', 1)
            else:
                text = text.rstrip() + insert
            index_path.write_text(text, encoding='utf-8')


def run_orb(market: str) -> None:
    cfg = MARKETS[market]
    day, weekly = add_volume_features(pd.read_csv(cfg['daily'], parse_dates=['date']))
    trade_path = ROOT / market / f'{market}_{ORB_VARIANT}.csv'
    trades = pd.read_csv(trade_path)
    rows: list[dict] = []
    for _, row in trades.iterrows():
        if str(row.get('Trade_Direction', '')).lower() == 'no-op':
            continue
        out = {
            'period': row.get('Period', ''),
            'direction': row.get('Trade_Direction', ''),
            'result': row.get('Result', ''),
            'trade_pl_pts': float(row.get('Trade_PL', 0.0) or 0.0),
            'range': float(row.get('Range', 0.0) or 0.0),
        }
        out.update(day_feature(day, row.get('Breakout_Date'), 'breakout'))
        out.update(day_feature(day, row.get('Entry_Date'), 'entry'))
        out.update(week_feature(weekly, row.get('Entry_Date'), 'entry'))
        out['breakout_vol_bucket'] = bucket(out['breakout_vol_x20_prior'])
        out['entry_vol_bucket'] = bucket(out['entry_vol_x20_prior'])
        out['entry_week_vol_bucket'] = bucket(out['entry_week_vol_x20_prior'])
        rows.append(out)
    profile = pd.DataFrame(rows)
    out_dir = ROOT / market / 'case_studies' / ORB_VARIANT / 'weekly_candles_volume'
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / 'volume_profile.csv'
    profile.to_csv(csv_path, index=False)
    write_summary(csv_path, f'{market.upper()} Yearly ORB Volume Profile', profile, 'entry_week_vol_x20_prior', 'trade_pl_pts', cfg['point_value'])
    print(f'Wrote {csv_path}')


def run_atr(market: str) -> None:
    cfg = MARKETS[market]
    day, _weekly = add_volume_features(pd.read_csv(cfg['daily'], parse_dates=['date']))
    base = ROOT / market / 'case_studies' / ATR_VARIANT
    trades = pd.read_csv(base / 'trades.csv')
    rows: list[dict] = []
    for _, row in trades.iterrows():
        out = {
            'trade_id': int(row.get('trade_id', 0)),
            'direction': row.get('direction', 'Long'),
            'exit_reason': row.get('exit_reason', ''),
            'net_points': float(row.get('net_points', 0.0) or 0.0),
            'mae_usd': float(row.get('mae_usd', 0.0) or 0.0),
        }
        out.update(day_feature(day, row.get('signal_date'), 'signal'))
        out.update(day_feature(day, row.get('entry_date'), 'entry'))
        out['signal_vol_bucket'] = bucket(out['signal_vol_x20_prior'])
        out['entry_vol_bucket'] = bucket(out['entry_vol_x20_prior'])
        rows.append(out)
    profile = pd.DataFrame(rows)
    out_dir = base / 'volume_charts'
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / 'volume_profile.csv'
    profile.to_csv(csv_path, index=False)
    write_summary(csv_path, f'{market.upper()} ATR Supertrend Volume Profile', profile, 'entry_vol_x20_prior', 'net_points', cfg['point_value'])
    print(f'Wrote {csv_path}')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--markets', nargs='+', choices=sorted(MARKETS), default=['mnq', 'nq'])
    ap.add_argument('--families', nargs='+', choices=['orb', 'atr'], default=['orb', 'atr'])
    args = ap.parse_args()
    for market in args.markets:
        if 'orb' in args.families:
            run_orb(market)
        if 'atr' in args.families:
            run_atr(market)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
