#!/usr/bin/env python3
"""Bullish-only v2b clean-break study on 5-minute RTH bars.

Rules:
- Opening range is the first 15 minutes of RTH: 09:30, 09:35, 09:40 bars.
- Only the first range break of the session is considered.
- If the first break is below the OR low, skip the day.
- If the first break is above the OR high, a buy stop fills at
  OR high + one tick + slippage ticks.
- If that breakout candle closes back inside/under the OR high, close at the
  candle close and mark it as a failed clean break.
- If it closes above the OR high, keep the trade with a v2b-style stop at the
  opposite OR boundary and target = entry + 2 * OR range.

This is intentionally simple and 5-minute-causal. It is a candidate detector,
not a final live fill model.
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
        'out': ROOT / 'mnq' / 'mnq_v2b_clean_break_bullish.csv',
        'point_value': 2.0,
        'tick_size': 0.25,
    },
    'nq': {
        'bars': ROOT / 'nq' / 'nq_5min_rth.csv',
        'out': ROOT / 'nq' / 'nq_v2b_clean_break_bullish.csv',
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


def session_result(
    day: str,
    bars: pd.DataFrame,
    market: str,
    point_value: float,
    tick_size: float,
    slip_ticks: int,
) -> dict:
    range_bars = bars[bars['time'].isin(['09:30', '09:35', '09:40'])]
    trade_bars = bars[bars['time'] >= '09:45'].reset_index(drop=True)
    symbol = str(bars.iloc[0]['symbol']) if 'symbol' in bars and not bars.empty else ''
    base = {
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
    if len(range_bars) < 3 or trade_bars.empty:
        base['status'] = 'Missing range/trade bars'
        return base

    rh = float(range_bars['high'].max())
    rl = float(range_bars['low'].min())
    or_range = rh - rl
    base.update({'rh': rh, 'rl': rl, 'range': or_range})
    if or_range <= 0:
        base['status'] = 'Bad range'
        return base

    trigger = rh + tick_size
    entry = trigger + slip_ticks * tick_size
    target = entry + 2.0 * or_range
    stop = rl
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
        base['status'] = 'No range break'
        return base
    break_bar = trade_bars.iloc[first_break_idx]
    break_time = break_bar['ts'].isoformat()
    candle_num = int(first_break_idx + 1)
    base.update(
        {
            'break_time': break_time,
            'break_candle_num_after_or': candle_num,
            'break_close': float(break_bar['close']),
        }
    )
    if first_break_side == 'ambiguous':
        base['status'] = 'Initial break ambiguous'
        base['result'] = 'Skipped'
        return base
    if first_break_side == 'down':
        base['status'] = 'Initial break down'
        base['result'] = 'Skipped'
        return base

    base.update({'entry': entry, 'target': target, 'stop': stop, 'status': 'Initial break up'})

    # The defining clean-break test: the breakout candle must close above RH.
    if float(break_bar['close']) <= rh:
        exit_px = float(break_bar['close'])
        pts = exit_px - entry
        base.update(
            {
                'status': 'Failed clean close',
                'result': 'Failed-Clean-Close',
                'exit_px': exit_px,
                'exit_time': break_time,
                'pts': pts,
                'usd': pts * point_value,
                'mae_pts': max(0.0, entry - float(break_bar['low'])),
                'mfe_pts': max(0.0, float(break_bar['high']) - entry),
            }
        )
        return base

    max_adverse = max(0.0, entry - float(break_bar['low']))
    max_favorable = max(0.0, float(break_bar['high']) - entry)
    if float(break_bar['high']) >= target:
        pts = target - entry
        base.update(
            {
                'status': 'Clean break target',
                'result': 'Target',
                'exit_px': target,
                'exit_time': break_time,
                'pts': pts,
                'usd': pts * point_value,
                'mae_pts': max_adverse,
                'mfe_pts': max_favorable,
            }
        )
        return base

    for _, bar in trade_bars.iloc[first_break_idx + 1 :].iterrows():
        low = float(bar['low'])
        high = float(bar['high'])
        max_adverse = max(max_adverse, max(0.0, entry - low))
        max_favorable = max(max_favorable, max(0.0, high - entry))
        # Conservative same-5m-bar ordering after the breakout candle.
        if low <= stop:
            pts = stop - entry
            base.update(
                {
                    'status': 'Clean break stop',
                    'result': 'Stop',
                    'exit_px': stop,
                    'exit_time': bar['ts'].isoformat(),
                    'pts': pts,
                    'usd': pts * point_value,
                    'mae_pts': max_adverse,
                    'mfe_pts': max_favorable,
                }
            )
            return base
        if high >= target:
            pts = target - entry
            base.update(
                {
                    'status': 'Clean break target',
                    'result': 'Target',
                    'exit_px': target,
                    'exit_time': bar['ts'].isoformat(),
                    'pts': pts,
                    'usd': pts * point_value,
                    'mae_pts': max_adverse,
                    'mfe_pts': max_favorable,
                }
            )
            return base

    last = trade_bars.iloc[-1]
    exit_px = float(last['close'])
    pts = exit_px - entry
    base.update(
        {
            'status': 'Clean break EOD',
            'result': 'EOD-Win' if pts > 0 else 'EOD-Loss' if pts < 0 else 'EOD-Flat',
            'exit_px': exit_px,
            'exit_time': last['ts'].isoformat(),
            'pts': pts,
            'usd': pts * point_value,
            'mae_pts': max_adverse,
            'mfe_pts': max_favorable,
        }
    )
    return base


def run_market(market: str, cfg: dict, slip_ticks: int) -> pd.DataFrame:
    bars = load_5m(cfg['bars'])
    rows = [
        session_result(day, day_bars, market, cfg['point_value'], cfg['tick_size'], slip_ticks)
        for day, day_bars in bars.groupby('session_day', sort=True)
    ]
    out = pd.DataFrame(rows)
    cfg['out'].parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(cfg['out'], index=False)
    return out


def summarize(df: pd.DataFrame) -> dict:
    traded = df[df['entry'].notna()].copy()
    clean = traded[traded['status'].astype(str).str.startswith('Clean break')]
    target = traded[traded['result'].eq('Target')]
    return {
        'sessions': int(len(df)),
        'initial_up': int(traded.shape[0]),
        'initial_down_skip': int(df['status'].eq('Initial break down').sum()),
        'ambiguous_skip': int(df['status'].eq('Initial break ambiguous').sum()),
        'no_break': int(df['status'].eq('No range break').sum()),
        'failed_clean_close': int(df['result'].eq('Failed-Clean-Close').sum()),
        'clean_count': int(len(clean)),
        'targets': int(len(target)),
        'stops': int(df['result'].eq('Stop').sum()),
        'eod': int(df['result'].astype(str).str.startswith('EOD').sum()),
        'target_rate_all_up': float(len(target) / len(traded) * 100.0) if len(traded) else 0.0,
        'target_rate_clean': float(len(target) / len(clean) * 100.0) if len(clean) else 0.0,
        'net_pts': float(traded['pts'].sum()) if not traded.empty else 0.0,
        'net_usd': float(traded['usd'].sum()) if not traded.empty else 0.0,
        'max_dd_usd': max_drawdown(traded['usd']) if not traded.empty else 0.0,
        'pf': profit_factor(traded['usd']) if not traded.empty else math.nan,
        'avg_mae_target_pts': float(target['mae_pts'].mean()) if len(target) else 0.0,
        'median_mae_target_pts': float(target['mae_pts'].median()) if len(target) else 0.0,
    }


def table_for_winner_times(df: pd.DataFrame) -> pd.DataFrame:
    targets = df[df['result'].eq('Target')].copy()
    if targets.empty:
        return pd.DataFrame(columns=['break_candle_num_after_or', 'break_time_et', 'targets'])
    targets['break_time_et'] = pd.to_datetime(targets['break_time'], utc=True).dt.tz_convert(NY_TZ).dt.strftime('%H:%M')
    return (
        targets.groupby(['break_candle_num_after_or', 'break_time_et'])
        .size()
        .reset_index(name='targets')
        .sort_values(['targets', 'break_candle_num_after_or'], ascending=[False, True])
    )


def write_report(results: dict[str, pd.DataFrame], out_dir: Path, slip_ticks: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        '# v2b Clean Break Bullish Study',
        '',
        'This revisits v2b as a **bullish-only, first-break-only** clean-break detector on 5-minute RTH bars.',
        '',
        'Rules used in this first pass:',
        '',
        '- Opening range: 09:30, 09:35, and 09:40 five-minute candles.',
        '- First post-range break only. If the first break is down, the day is skipped.',
        f'- Buy stop: `RH + 1 tick + {slip_ticks} slip tick(s)`.',
        '- Clean requirement: the breakout candle must close above `RH`; otherwise the trade closes at that 5-minute close.',
        '- Target: `entry + 2 * opening_range`.',
        '- Stop: existing v2b-style opposite OR boundary, `RL`.',
        '- After the breakout candle, ambiguous same-bar stop/target ordering is stop-first.',
        '',
        'This is a 5-minute research pass. The exact order of high/low events inside a five-minute candle is not proven here.',
        '',
        '## Summary',
        '',
        '| Market | Sessions | Initial Up | Failed Clean | Clean Breaks | Targets | Stops | EOD | Target Rate / Up | Target Rate / Clean | Net | Max DD | PF |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for market, df in results.items():
        s = summarize(df)
        lines.append(
            f"| {market.upper()} | {s['sessions']} | {s['initial_up']} | {s['failed_clean_close']} | "
            f"{s['clean_count']} | {s['targets']} | {s['stops']} | {s['eod']} | "
            f"{s['target_rate_all_up']:.1f}% | {s['target_rate_clean']:.1f}% | "
            f"{money(s['net_usd'])} | {money(s['max_dd_usd'])} | {s['pf']:.2f} |"
        )

    lines.extend(['', '## Winner Clean-Break Timing', ''])
    for market, df in results.items():
        times = table_for_winner_times(df)
        lines.extend([f'### {market.upper()}', ''])
        if times.empty:
            lines.append('No target winners.')
            lines.append('')
            continue
        lines.extend(['| Break candle # after OR | Time ET | Target winners |', '|---:|---:|---:|'])
        for _, row in times.head(12).iterrows():
            lines.append(f"| {int(row['break_candle_num_after_or'])} | {row['break_time_et']} | {int(row['targets'])} |")
        lines.append('')

    lines.extend(['## Output CSVs', ''])
    for market, cfg in MARKETS.items():
        lines.append(f"- `{cfg['out'].relative_to(ROOT)}`")
    lines.append('')
    (out_dir / 'README.md').write_text('\n'.join(lines), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--slip-ticks', type=int, default=1)
    ap.add_argument('--report-dir', type=Path, default=ROOT / 'mnq' / 'case_studies' / 'v2b_clean_break_bullish')
    args = ap.parse_args()
    results = {market: run_market(market, cfg, args.slip_ticks) for market, cfg in MARKETS.items()}
    write_report(results, args.report_dir, args.slip_ticks)
    print(f"Wrote {args.report_dir / 'README.md'}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
