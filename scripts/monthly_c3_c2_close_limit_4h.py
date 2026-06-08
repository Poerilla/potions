#!/usr/bin/env python3
"""MNQ monthly C3 study: buy limit at C2 close on 4-hour bars.

Long-only first pass:
- For each monthly C3 candle, place a standing buy limit at the prior C2 close.
- The limit is armed only after a 4-hour close above the C2 close, then can
  fill on a later touch of the C2 close during the C3 month.
- Unlimited re-entry attempts are allowed during that C3 month.
- Exit if a 4-hour candle closes 50 points below the C2 close.
- Exit when the daily chart confirms a lower high; the fill is modeled at the
  next 4-hour bar open.
- Entries stop after the C3 month ends, but an open trade can continue until an
  exit signal appears.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import pytz


ROOT = Path(__file__).resolve().parents[1]
NY = pytz.timezone('America/New_York')
MNQ = ROOT / 'mnq'
C3_DIR = MNQ / 'case_studies' / 'monthly_candles' / 'c3_marked'
C3_SETUPS = C3_DIR / 'c3_setups.csv'
MONTHLY_CANDLES = MNQ / 'case_studies' / 'monthly_candles' / 'monthly_candles.csv'
FOUR_H = MNQ / 'data' / 'mnq_front_month_4h_from_1m.csv'
DAILY = MNQ / 'mnq_daily.csv'
OUT_DIR = C3_DIR / 'c2_close_limit_4h_lower_high_exit'
POINT_VALUE = 2.0


def as_bool(value) -> bool:
    return str(value).strip().lower() in {'1', 'true', 'yes', 'y'}


def load_4h(path: Path) -> pd.DataFrame:
    bars = pd.read_csv(path)
    bars['time'] = pd.to_datetime(bars['time'], utc=True).dt.tz_convert(NY)
    bars['date'] = pd.to_datetime(bars['date']).dt.date
    bars['month'] = bars['time'].dt.tz_localize(None).dt.to_period('M').astype(str)
    return bars.sort_values('time').reset_index(drop=True)


def load_daily(path: Path) -> pd.DataFrame:
    daily = pd.read_csv(path, parse_dates=['date'])
    daily['date'] = daily['date'].dt.date
    daily = daily.sort_values('date').reset_index(drop=True)
    daily['prev_high'] = daily['high'].astype(float).shift(1)
    daily['lower_high'] = daily['high'].astype(float) < daily['prev_high']
    return daily


def load_monthly(path: Path) -> dict[str, pd.Series]:
    monthly = pd.read_csv(path)
    return {str(row['month']): row for _, row in monthly.iterrows()}


def build_lower_high_exit_indices(bars4h: pd.DataFrame, daily: pd.DataFrame) -> dict[int, str]:
    """Map 4h bar index to the daily lower-high date that becomes actionable."""
    by_idx: dict[int, str] = {}
    dates = bars4h['date']
    lower_high_dates = daily[daily['lower_high']]['date'].tolist()
    for day in lower_high_dates:
        matches = bars4h.index[dates > day]
        if len(matches) == 0:
            continue
        by_idx[int(matches[0])] = pd.Timestamp(day).date().isoformat()
    return by_idx


def max_closed_drawdown(net_values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in net_values:
        equity += value
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def profit_factor(values: pd.Series) -> float:
    gross_profit = float(values[values > 0].sum())
    gross_loss = abs(float(values[values < 0].sum()))
    if gross_loss == 0:
        return float('inf') if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def simulate_setup(
    setup: pd.Series,
    monthly: dict[str, pd.Series],
    bars4h: pd.DataFrame,
    daily_exit_idx: dict[int, str],
    stop_offset: float,
    max_days_after_month: int,
) -> list[dict]:
    setup_id = int(setup['setup_id'])
    c2_month = str(setup['c2_month'])
    c3_month = str(setup['c3_month'])
    c3_period = pd.Period(c3_month, freq='M')
    c2_close = float(monthly[c2_month]['close'])
    stop_level = c2_close - stop_offset
    start_matches = bars4h.index[bars4h['month'].eq(c3_month)]
    if len(start_matches) == 0:
        return []

    month_end = c3_period.end_time
    hard_end = month_end + pd.Timedelta(days=max_days_after_month)
    start_idx = int(start_matches[0])
    trades: list[dict] = []

    in_trade = False
    armed = False
    arm_idx = start_idx
    rearm_idx = start_idx
    attempt = 0
    entry_time = pd.NaT
    entry_idx = -1
    entry_px = 0.0
    mae_pts = 0.0
    mfe_pts = 0.0
    min_low = 0.0
    max_high = 0.0

    for idx in range(start_idx, len(bars4h)):
        row = bars4h.iloc[idx]
        bar_time = pd.Timestamp(row['time'])
        if bar_time.tz_localize(None) > hard_end and not in_trade:
            break
        if bar_time.tz_localize(None) > hard_end and in_trade:
            exit_px = float(row['open'])
            trades.append(
                make_trade_row(
                    setup,
                    attempt,
                    c2_close,
                    stop_level,
                    entry_time,
                    entry_idx,
                    entry_px,
                    bar_time,
                    idx,
                    exit_px,
                    'max_holding_window_exit',
                    mae_pts,
                    mfe_pts,
                )
            )
            break

        if in_trade and idx in daily_exit_idx:
            exit_px = float(row['open'])
            trades.append(
                make_trade_row(
                    setup,
                    attempt,
                    c2_close,
                    stop_level,
                    entry_time,
                    entry_idx,
                    entry_px,
                    bar_time,
                    idx,
                    exit_px,
                    f'daily_lower_high_next_4h_open:{daily_exit_idx[idx]}',
                    mae_pts,
                    mfe_pts,
                )
            )
            in_trade = False
            armed = False
            arm_idx = idx + 1
            rearm_idx = idx + 1
            continue

        if in_trade:
            low = float(row['low'])
            high = float(row['high'])
            close = float(row['close'])
            min_low = min(min_low, low)
            max_high = max(max_high, high)
            mae_pts = min(mae_pts, min_low - entry_px)
            mfe_pts = max(mfe_pts, max_high - entry_px)
            if close <= stop_level:
                trades.append(
                    make_trade_row(
                        setup,
                        attempt,
                        c2_close,
                        stop_level,
                        entry_time,
                        entry_idx,
                        entry_px,
                        bar_time + pd.Timedelta(hours=4),
                        idx,
                        close,
                        '4h_close_50pt_below_c2_close',
                        mae_pts,
                        mfe_pts,
                    )
                )
                in_trade = False
                armed = False
                arm_idx = idx + 1
                rearm_idx = idx + 1
            continue

        entry_allowed = str(row['month']) == c3_month and idx >= rearm_idx
        if not entry_allowed:
            if pd.Period(str(row['month']), freq='M') > c3_period:
                break
            continue

        if not armed:
            if float(row['close']) > c2_close:
                armed = True
                arm_idx = idx + 1
            continue

        if idx >= arm_idx and float(row['low']) <= c2_close:
            attempt += 1
            in_trade = True
            armed = False
            entry_time = bar_time
            entry_idx = idx
            entry_px = c2_close
            min_low = float(row['low'])
            max_high = float(row['high'])
            mae_pts = min(0.0, min_low - entry_px)
            mfe_pts = max(0.0, max_high - entry_px)
            if float(row['close']) <= stop_level:
                trades.append(
                    make_trade_row(
                        setup,
                        attempt,
                        c2_close,
                        stop_level,
                        entry_time,
                        entry_idx,
                        entry_px,
                        bar_time + pd.Timedelta(hours=4),
                        idx,
                        float(row['close']),
                        'same_bar_4h_close_50pt_below_c2_close',
                        mae_pts,
                        mfe_pts,
                    )
                )
                in_trade = False
                armed = False
                arm_idx = idx + 1
                rearm_idx = idx + 1

    if in_trade:
        last = bars4h.iloc[-1]
        trades.append(
            make_trade_row(
                setup,
                attempt,
                c2_close,
                stop_level,
                entry_time,
                entry_idx,
                entry_px,
                pd.Timestamp(last['time']),
                len(bars4h) - 1,
                float(last['close']),
                'data_end_open_trade',
                mae_pts,
                mfe_pts,
            )
        )
    return trades


def make_trade_row(
    setup: pd.Series,
    attempt: int,
    c2_close: float,
    stop_level: float,
    entry_time: pd.Timestamp,
    entry_idx: int,
    entry_px: float,
    exit_time: pd.Timestamp,
    exit_idx: int,
    exit_px: float,
    exit_reason: str,
    mae_pts: float,
    mfe_pts: float,
) -> dict:
    net_pts = exit_px - entry_px
    return {
        'setup_id': int(setup['setup_id']),
        'attempt': int(attempt),
        'direction': str(setup['direction']),
        'c3_hit': as_bool(setup['c3_hit']),
        'c1_month': str(setup['c1_month']),
        'c2_month': str(setup['c2_month']),
        'c3_month': str(setup['c3_month']),
        'c2_close': round(c2_close, 4),
        'stop_level': round(stop_level, 4),
        'entry_time': entry_time,
        'entry_idx': entry_idx,
        'entry_px': round(entry_px, 4),
        'exit_time': exit_time,
        'exit_idx': exit_idx,
        'exit_px': round(exit_px, 4),
        'exit_reason': exit_reason,
        'exit_category': exit_reason.split(':', 1)[0],
        'bars_held': int(exit_idx - entry_idx + 1),
        'net_pts': round(net_pts, 4),
        'net_usd': round(net_pts * POINT_VALUE, 2),
        'mae_pts': round(mae_pts, 4),
        'mfe_pts': round(mfe_pts, 4),
    }


def summarize(trades: pd.DataFrame, setups: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    buckets = [('all', trades)]
    if not trades.empty:
        for direction, group in trades.groupby('direction', sort=True):
            buckets.append((f'c3_{direction}', group))
        for hit, group in trades.groupby('c3_hit', sort=True):
            buckets.append((f'c3_hit_{hit}', group))
        for reason, group in trades.groupby('exit_category', sort=True):
            buckets.append((f'exit_{reason}', group))

    for bucket, group in buckets:
        if group.empty:
            rows.append(
                {
                    'bucket': bucket,
                    'setups': len(setups),
                    'filled_setups': 0,
                    'trades': 0,
                    'wins': 0,
                    'win_rate': 0.0,
                    'net_pts': 0.0,
                    'net_usd': 0.0,
                    'max_closed_dd_usd': 0.0,
                    'profit_factor': 0.0,
                    'avg_trade_usd': 0.0,
                    'avg_mae_pts': 0.0,
                    'worst_mae_pts': 0.0,
                    'avg_mfe_pts': 0.0,
                }
            )
            continue
        vals = group['net_usd'].astype(float)
        rows.append(
            {
                'bucket': bucket,
                'setups': len(setups),
                'filled_setups': int(group['setup_id'].nunique()),
                'trades': len(group),
                'wins': int((vals > 0).sum()),
                'win_rate': round(float((vals > 0).mean()) * 100, 2),
                'net_pts': round(float(group['net_pts'].sum()), 2),
                'net_usd': round(float(vals.sum()), 2),
                'max_closed_dd_usd': round(max_closed_drawdown(vals.tolist()), 2),
                'profit_factor': round(profit_factor(vals), 3),
                'avg_trade_usd': round(float(vals.mean()), 2),
                'avg_mae_pts': round(float(group['mae_pts'].mean()), 2),
                'worst_mae_pts': round(float(group['mae_pts'].min()), 2),
                'avg_mfe_pts': round(float(group['mfe_pts'].mean()), 2),
            }
        )
    return pd.DataFrame(rows)


def setup_summary(trades: pd.DataFrame, setups: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for _, setup in setups.iterrows():
        sub = trades[trades['setup_id'].eq(int(setup['setup_id']))] if not trades.empty else pd.DataFrame()
        rows.append(
            {
                'setup_id': int(setup['setup_id']),
                'direction': str(setup['direction']),
                'c3_hit': as_bool(setup['c3_hit']),
                'c2_month': str(setup['c2_month']),
                'c3_month': str(setup['c3_month']),
                'attempts': len(sub),
                'net_pts': round(float(sub['net_pts'].sum()), 2) if not sub.empty else 0.0,
                'net_usd': round(float(sub['net_usd'].sum()), 2) if not sub.empty else 0.0,
                'wins': int((sub['net_usd'].astype(float) > 0).sum()) if not sub.empty else 0,
                'worst_mae_pts': round(float(sub['mae_pts'].min()), 2) if not sub.empty else 0.0,
                'best_mfe_pts': round(float(sub['mfe_pts'].max()), 2) if not sub.empty else 0.0,
            }
        )
    return pd.DataFrame(rows)


def write_readme(out_dir: Path, summary_df: pd.DataFrame, setup_df: pd.DataFrame, stop_offset: float, max_days: int) -> None:
    lines = [
        '# MNQ Monthly C3: C2-Close Limit Long / Daily Lower-High Exit',
        '',
        'Long-only replacement study after discarding the 5-minute ATR drill-down.',
        '',
        '## Rules',
        '',
        '- Use every monthly C3 setup.',
        '- During the C3 month, arm a buy limit at the C2 monthly close after a confirmed 4-hour close above C2 close.',
        '- Fill is modeled on a later 4-hour bar touch at the C2 close.',
        f'- Exit if a 4-hour candle closes `{stop_offset:g}` points below the C2 close.',
        '- Exit when the daily chart confirms a lower high, filled at the next 4-hour bar open.',
        '- Unlimited re-entry attempts are allowed while still inside the C3 month.',
        '- Entries stop after the C3 month, but an open trade can continue until an exit signal appears.',
        '- Position size is 1 MNQ contract.',
        '',
        '## Summary',
        '',
        summary_df.to_markdown(index=False),
        '',
        '## Setup Notes',
        '',
        f'- C3 setups reviewed: `{len(setup_df)}`',
        f'- Setups with at least one fill: `{int((setup_df["attempts"] > 0).sum())}`',
        f'- Maximum hold window after C3 month end: `{max_days}` days.',
        '',
        '## Files',
        '',
        '- [trades.csv](trades.csv)',
        '- [setup_summary.csv](setup_summary.csv)',
        '- [summary.csv](summary.csv)',
        '',
        '## Causality Notes',
        '',
        '- The C2 close is known before the C3 month begins.',
        '- The 4-hour close stop is modeled at the confirming 4-hour close.',
        '- A daily lower high is only known after that daily candle completes, so the model exits at the next 4-hour bar open.',
        '- Same-bar limit-fill then 4-hour close-stop is allowed because the close-stop information is only known at that bar close.',
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def update_c3_index() -> None:
    index = C3_DIR / 'INDEX.md'
    text = index.read_text(encoding='utf-8')
    line = '- [C2-close limit long / daily lower-high exit](c2_close_limit_4h_lower_high_exit/README.md)'
    if line in text:
        return
    marker = '- [4h context charts for every C3](4h_context/INDEX.md)'
    if marker in text:
        text = text.replace(marker, marker + '\n' + line)
    else:
        text += '\n' + line + '\n'
    index.write_text(text, encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--stop-offset', type=float, default=50.0)
    ap.add_argument('--max-days-after-month', type=int, default=90)
    ap.add_argument('--out-dir', type=Path, default=OUT_DIR)
    args = ap.parse_args()

    setups = pd.read_csv(C3_SETUPS)
    monthly = load_monthly(MONTHLY_CANDLES)
    bars4h = load_4h(FOUR_H)
    daily = load_daily(DAILY)
    daily_exit_idx = build_lower_high_exit_indices(bars4h, daily)

    all_trades: list[dict] = []
    for _, setup in setups.iterrows():
        all_trades.extend(
            simulate_setup(
                setup,
                monthly,
                bars4h,
                daily_exit_idx,
                args.stop_offset,
                args.max_days_after_month,
            )
        )

    trades = pd.DataFrame(all_trades)
    setup_df = setup_summary(trades, setups)
    summary_df = summarize(trades, setups)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    trades.to_csv(args.out_dir / 'trades.csv', index=False)
    setup_df.to_csv(args.out_dir / 'setup_summary.csv', index=False)
    summary_df.to_csv(args.out_dir / 'summary.csv', index=False)
    write_readme(args.out_dir, summary_df, setup_df, args.stop_offset, args.max_days_after_month)
    update_c3_index()

    print(f'Wrote {args.out_dir / "README.md"}')
    print(summary_df.to_string(index=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
