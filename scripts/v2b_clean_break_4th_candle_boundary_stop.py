#!/usr/bin/env python3
"""Bullish v2b clean-break variant: only the 4th RTH candle may break out.

Default interpretation:
- OR is the first three 5-minute RTH candles: 09:30, 09:35, 09:40.
- The "4th candle" is therefore the 09:45 candle, which is break #1 after OR.
- Trade only if that candle is the first range break and it breaks upward.
- If that breakout candle does not close above RH, close at that candle close.
- If it closes above RH, move the stop to RH immediately after the candle close.
- From the next 5-minute candle onward, any trade back into the range exits at RH.
- Target remains entry + 2 * OR range.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
NY_TZ = 'America/New_York'


MARKETS = {
    'mnq': {
        'bars': ROOT / 'mnq' / 'mnq_5min_rth.csv',
        'out': ROOT / 'mnq' / 'mnq_v2b_clean_break_4th_candle_boundary_stop.csv',
        'point_value': 2.0,
        'tick_size': 0.25,
    },
    'nq': {
        'bars': ROOT / 'nq' / 'nq_5min_rth.csv',
        'out': ROOT / 'nq' / 'nq_v2b_clean_break_4th_candle_boundary_stop.csv',
        'point_value': 20.0,
        'tick_size': 0.25,
    },
}


def money(value: float) -> str:
    return f'${value:,.0f}'


def max_drawdown(values: pd.Series) -> float:
    values = pd.to_numeric(values, errors='coerce').fillna(0.0)
    curve = values.cumsum()
    return float((curve - curve.cummax()).min()) if not curve.empty else 0.0


def profit_factor(values: pd.Series) -> float:
    values = pd.to_numeric(values, errors='coerce').fillna(0.0)
    wins = float(values[values > 0].sum())
    losses = abs(float(values[values < 0].sum()))
    if losses == 0:
        return math.inf if wins > 0 else math.nan
    return wins / losses


def load_5m(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df['ts'] = pd.to_datetime(df['ts_event'], utc=True).dt.tz_convert(NY_TZ)
    df['session_day'] = df['ts'].dt.date.astype(str)
    df['time'] = df['ts'].dt.strftime('%H:%M')
    return df.sort_values('ts').reset_index(drop=True)


def base_row(day: str, bars: pd.DataFrame, market: str) -> dict:
    symbol = str(bars.iloc[0]['symbol']) if 'symbol' in bars and not bars.empty else ''
    return {
        'market': market,
        'session_day': day,
        'symbol': symbol,
        'status': 'No-Op',
        'result': 'No-Op',
        'rh': math.nan,
        'rl': math.nan,
        'range': math.nan,
        'entry': math.nan,
        'target': math.nan,
        'stop': math.nan,
        'exit_px': math.nan,
        'pts': 0.0,
        'usd': 0.0,
        'break_time': '',
        'break_candle_num_after_or': math.nan,
        'break_close': math.nan,
        'exit_time': '',
        'mae_pts': 0.0,
        'mfe_pts': 0.0,
    }


def session_result(
    day: str,
    bars: pd.DataFrame,
    market: str,
    point_value: float,
    tick_size: float,
    slip_ticks: int,
    required_break_num: int,
) -> dict:
    row = base_row(day, bars, market)
    range_bars = bars[bars['time'].isin(['09:30', '09:35', '09:40'])]
    trade_bars = bars[bars['time'] >= '09:45'].reset_index(drop=True)
    if len(range_bars) < 3 or trade_bars.empty:
        row['status'] = 'Missing range/trade bars'
        return row

    rh = float(range_bars['high'].max())
    rl = float(range_bars['low'].min())
    or_range = rh - rl
    row.update({'rh': rh, 'rl': rl, 'range': or_range})
    if or_range <= 0:
        row['status'] = 'Bad range'
        return row

    trigger = rh + tick_size
    entry = trigger + slip_ticks * tick_size
    target = entry + 2.0 * or_range
    boundary_stop = rh

    first_break_idx = None
    first_break_side = None
    for idx, bar in trade_bars.iterrows():
        up = float(bar['high']) >= trigger
        down = float(bar['low']) <= rl - tick_size
        if up and down:
            first_break_idx = idx
            first_break_side = 'ambiguous'
            break
        if up:
            first_break_idx = idx
            first_break_side = 'up'
            break
        if down:
            first_break_idx = idx
            first_break_side = 'down'
            break

    if first_break_idx is None:
        row['status'] = 'No range break'
        return row

    break_bar = trade_bars.iloc[first_break_idx]
    candle_num = int(first_break_idx + 1)
    row.update(
        {
            'break_time': break_bar['ts'].isoformat(),
            'break_candle_num_after_or': candle_num,
            'break_close': float(break_bar['close']),
        }
    )
    if candle_num != required_break_num:
        row['status'] = f'Initial break not required candle ({candle_num})'
        row['result'] = 'Skipped'
        return row
    if first_break_side == 'ambiguous':
        row['status'] = 'Initial break ambiguous'
        row['result'] = 'Skipped'
        return row
    if first_break_side == 'down':
        row['status'] = 'Initial break down'
        row['result'] = 'Skipped'
        return row

    row.update({'entry': entry, 'target': target, 'stop': boundary_stop, 'status': 'Required candle break up'})

    break_low = float(break_bar['low'])
    break_high = float(break_bar['high'])
    break_close = float(break_bar['close'])
    max_adverse = max(0.0, entry - break_low)
    max_favorable = max(0.0, break_high - entry)

    if break_close <= rh:
        pts = break_close - entry
        row.update(
            {
                'status': 'Failed clean close',
                'result': 'Failed-Clean-Close',
                'exit_px': break_close,
                'exit_time': break_bar['ts'].isoformat(),
                'pts': pts,
                'usd': pts * point_value,
                'mae_pts': max_adverse,
                'mfe_pts': max_favorable,
            }
        )
        return row

    # If the breakout candle itself reaches 2R before its close, keep the win.
    # The RH stop is considered active after this candle closes.
    if break_high >= target:
        pts = target - entry
        row.update(
            {
                'status': 'Required candle target',
                'result': 'Target',
                'exit_px': target,
                'exit_time': break_bar['ts'].isoformat(),
                'pts': pts,
                'usd': pts * point_value,
                'mae_pts': max_adverse,
                'mfe_pts': max_favorable,
            }
        )
        return row

    for _, bar in trade_bars.iloc[first_break_idx + 1 :].iterrows():
        low = float(bar['low'])
        high = float(bar['high'])
        max_adverse = max(max_adverse, max(0.0, entry - low))
        max_favorable = max(max_favorable, max(0.0, high - entry))
        # Once the breakout candle has closed cleanly, coming back into the
        # range means exiting at the upper OR boundary.
        if low <= boundary_stop:
            pts = boundary_stop - entry
            row.update(
                {
                    'status': 'Boundary re-entry stop',
                    'result': 'Boundary-Stop',
                    'exit_px': boundary_stop,
                    'exit_time': bar['ts'].isoformat(),
                    'pts': pts,
                    'usd': pts * point_value,
                    'mae_pts': max_adverse,
                    'mfe_pts': max_favorable,
                }
            )
            return row
        if high >= target:
            pts = target - entry
            row.update(
                {
                    'status': 'Required candle target',
                    'result': 'Target',
                    'exit_px': target,
                    'exit_time': bar['ts'].isoformat(),
                    'pts': pts,
                    'usd': pts * point_value,
                    'mae_pts': max_adverse,
                    'mfe_pts': max_favorable,
                }
            )
            return row

    last = trade_bars.iloc[-1]
    exit_px = float(last['close'])
    pts = exit_px - entry
    row.update(
        {
            'status': 'Required candle EOD',
            'result': 'EOD-Win' if pts > 0 else 'EOD-Loss' if pts < 0 else 'EOD-Flat',
            'exit_px': exit_px,
            'exit_time': last['ts'].isoformat(),
            'pts': pts,
            'usd': pts * point_value,
            'mae_pts': max_adverse,
            'mfe_pts': max_favorable,
        }
    )
    return row


def run_market(market: str, cfg: dict, slip_ticks: int, required_break_num: int) -> pd.DataFrame:
    bars = load_5m(cfg['bars'])
    rows = [
        session_result(day, day_bars, market, cfg['point_value'], cfg['tick_size'], slip_ticks, required_break_num)
        for day, day_bars in bars.groupby('session_day', sort=True)
    ]
    out = pd.DataFrame(rows)
    cfg['out'].parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(cfg['out'], index=False)
    return out


def summarize(df: pd.DataFrame) -> dict:
    traded = df[df['entry'].notna()].copy()
    target = traded[traded['result'].eq('Target')]
    boundary = traded[traded['result'].eq('Boundary-Stop')]
    failed = traded[traded['result'].eq('Failed-Clean-Close')]
    eod = traded[traded['result'].astype(str).str.startswith('EOD')]
    return {
        'sessions': int(len(df)),
        'trades': int(len(traded)),
        'targets': int(len(target)),
        'boundary_stops': int(len(boundary)),
        'failed_clean_close': int(len(failed)),
        'eod': int(len(eod)),
        'win_rate': float((len(target) + len(eod[eod['pts'] > 0])) / len(traded) * 100.0) if len(traded) else 0.0,
        'target_rate': float(len(target) / len(traded) * 100.0) if len(traded) else 0.0,
        'net_pts': float(traded['pts'].sum()) if len(traded) else 0.0,
        'net_usd': float(traded['usd'].sum()) if len(traded) else 0.0,
        'max_dd_usd': max_drawdown(traded['usd']) if len(traded) else 0.0,
        'pf': profit_factor(traded['usd']) if len(traded) else math.nan,
        'avg_trade_usd': float(traded['usd'].mean()) if len(traded) else 0.0,
        'avg_mae_target_pts': float(target['mae_pts'].mean()) if len(target) else 0.0,
        'median_mae_target_pts': float(target['mae_pts'].median()) if len(target) else 0.0,
    }


def write_report(results: dict[str, pd.DataFrame], out_dir: Path, slip_ticks: int, required_break_num: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    candle_label = '09:45 / 4th RTH candle' if required_break_num == 1 else f'break #{required_break_num} after OR'
    lines = [
        '# v2b 4th-Candle Clean Break With Boundary Stop',
        '',
        f'This variant only trades when the initial bullish breakout happens on **{candle_label}**.',
        '',
        'Rules:',
        '',
        '- Opening range: 09:30, 09:35, and 09:40 five-minute candles.',
        '- First post-range break only. If it is not the required candle or not bullish, skip.',
        f'- Buy stop: `RH + 1 tick + {slip_ticks} slip tick(s)`.',
        '- Breakout candle must close above `RH`; otherwise close at that candle close.',
        '- After the breakout candle closes cleanly, stop moves immediately to `RH`.',
        '- Any later trade back into the range exits at `RH`.',
        '- Target remains `entry + 2 * opening_range`.',
        '- Same-bar ambiguity after the clean close is boundary-stop first.',
        '',
        '## Summary',
        '',
        '| Market | Sessions | Trades | Targets | Boundary Stops | Failed Clean | EOD | Target Rate | Win Rate | Net | Max DD | PF | Avg Trade |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for market, df in results.items():
        s = summarize(df)
        lines.append(
            f"| {market.upper()} | {s['sessions']} | {s['trades']} | {s['targets']} | {s['boundary_stops']} | "
            f"{s['failed_clean_close']} | {s['eod']} | {s['target_rate']:.1f}% | {s['win_rate']:.1f}% | "
            f"{money(s['net_usd'])} | {money(s['max_dd_usd'])} | {s['pf']:.2f} | {money(s['avg_trade_usd'])} |"
        )
    lines.extend(['', '## Output CSVs', ''])
    for market, cfg in MARKETS.items():
        lines.append(f"- `{cfg['out'].relative_to(ROOT)}`")
    lines.append('')
    (out_dir / 'README.md').write_text('\n'.join(lines), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--slip-ticks', type=int, default=1)
    ap.add_argument(
        '--required-break-num',
        type=int,
        default=1,
        help='1 means 09:45, the 4th RTH candle / first candle after OR.',
    )
    ap.add_argument(
        '--report-dir',
        type=Path,
        default=ROOT / 'mnq' / 'case_studies' / 'v2b_clean_break_4th_candle_boundary_stop',
    )
    args = ap.parse_args()
    results = {
        market: run_market(market, cfg, args.slip_ticks, args.required_break_num)
        for market, cfg in MARKETS.items()
    }
    write_report(results, args.report_dir, args.slip_ticks, args.required_break_num)
    print(f"Wrote {args.report_dir / 'README.md'}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
