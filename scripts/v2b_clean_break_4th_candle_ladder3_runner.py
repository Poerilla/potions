#!/usr/bin/env python3
"""Bullish v2b 09:45 clean-break with 3-contract scaleout runner.

Rules:
- OR is the first three 5-minute RTH candles: 09:30, 09:35, 09:40.
- Only trade when the 09:45 candle is the first range break and breaks upward.
- Entry: RH + one tick + slippage ticks.
- If 09:45 does not close above RH, close all 3 contracts at the 09:45 close.
- If 09:45 closes above RH, keep the boundary stop at RH.
- Scaleout:
  - 1 contract exits at 1R, where 1R = entry + opening_range.
  - 1 contract exits at 2R, where 2R = entry + 2 * opening_range.
  - Runner stays open after 2R; once it is the only contract left, stop moves to 1R.
- Before 2R is hit, any later trade back into the range exits all remaining
  contracts at RH.
- Runner exits at 1R stop or EOD.
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
        'out': ROOT / 'mnq' / 'mnq_v2b_clean_break_4th_candle_ladder3_runner.csv',
        'point_value': 2.0,
        'tick_size': 0.25,
    },
    'nq': {
        'bars': ROOT / 'nq' / 'nq_5min_rth.csv',
        'out': ROOT / 'nq' / 'nq_v2b_clean_break_4th_candle_ladder3_runner.csv',
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
        'tp1': math.nan,
        'tp2': math.nan,
        'boundary_stop': math.nan,
        'runner_stop': math.nan,
        'exit_px': math.nan,
        'pts': 0.0,
        'usd': 0.0,
        'break_time': '',
        'break_close': math.nan,
        'exit_time': '',
        'qty_start': 0,
        'tp1_hit': False,
        'tp2_hit': False,
        'runner_exit': '',
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
    tp1 = entry + or_range
    tp2 = entry + 2.0 * or_range
    row.update({'entry': entry, 'tp1': tp1, 'tp2': tp2, 'boundary_stop': rh, 'runner_stop': tp1})

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
    row.update({'break_time': break_bar['ts'].isoformat(), 'break_close': float(break_bar['close'])})

    if first_break_idx != 0:
        row['status'] = f'Initial break not 09:45 ({first_break_idx + 1})'
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

    row['qty_start'] = 3
    total_pts = 0.0
    open_qty = 3
    tp1_done = False
    tp2_done = False
    max_adverse = max(0.0, entry - float(break_bar['low']))
    max_favorable = max(0.0, float(break_bar['high']) - entry)

    if float(break_bar['close']) <= rh:
        pts = (float(break_bar['close']) - entry) * 3
        row.update(
            {
                'status': 'Failed clean close',
                'result': 'Failed-Clean-Close',
                'exit_px': float(break_bar['close']),
                'exit_time': break_bar['ts'].isoformat(),
                'pts': pts,
                'usd': pts * point_value,
                'mae_pts': max_adverse,
                'mfe_pts': max_favorable,
            }
        )
        return row

    # Boundary stop starts after the 09:45 candle closes. Scaleout targets can
    # still be reached during the breakout candle after the entry is triggered.
    if float(break_bar['high']) >= tp1:
        total_pts += tp1 - entry
        open_qty -= 1
        tp1_done = True
    if float(break_bar['high']) >= tp2:
        total_pts += tp2 - entry
        open_qty -= 1
        tp2_done = True

    exit_time = ''
    exit_px = math.nan
    runner_exit = ''

    for _, bar in trade_bars.iloc[first_break_idx + 1 :].iterrows():
        low = float(bar['low'])
        high = float(bar['high'])
        max_adverse = max(max_adverse, max(0.0, entry - low))
        max_favorable = max(max_favorable, max(0.0, high - entry))
        ts = bar['ts'].isoformat()

        if open_qty == 0:
            break

        if tp2_done:
            if low <= tp1:
                total_pts += tp1 - entry
                open_qty -= 1
                exit_time = ts
                exit_px = tp1
                runner_exit = 'Runner-1R-Stop'
                break
            continue

        # Conservative ordering: before the runner is alone, coming back into
        # the range exits remaining size before any target in the same bar.
        if low <= rh:
            total_pts += (rh - entry) * open_qty
            exit_time = ts
            exit_px = rh
            runner_exit = 'Boundary-Stop'
            open_qty = 0
            break

        if not tp1_done and high >= tp1:
            total_pts += tp1 - entry
            open_qty -= 1
            tp1_done = True

        if high >= tp2:
            total_pts += tp2 - entry
            open_qty -= 1
            tp2_done = True

    if open_qty > 0:
        last = trade_bars.iloc[-1]
        eod_px = float(last['close'])
        total_pts += (eod_px - entry) * open_qty
        exit_time = last['ts'].isoformat()
        exit_px = eod_px
        runner_exit = 'EOD'

    result = 'Win' if total_pts > 0 else 'Loss' if total_pts < 0 else 'Flat'
    if tp2_done and runner_exit == 'Runner-1R-Stop':
        status = 'TP1 TP2 runner stopped at 1R'
    elif tp2_done and runner_exit == 'EOD':
        status = 'TP1 TP2 runner EOD'
    elif tp1_done and runner_exit == 'Boundary-Stop':
        status = 'TP1 then boundary stop'
    elif runner_exit == 'Boundary-Stop':
        status = 'Boundary stop before TP1'
    else:
        status = runner_exit or 'Scaleout complete'

    row.update(
        {
            'status': status,
            'result': result,
            'exit_px': exit_px,
            'exit_time': exit_time,
            'pts': total_pts,
            'usd': total_pts * point_value,
            'tp1_hit': tp1_done,
            'tp2_hit': tp2_done,
            'runner_exit': runner_exit,
            'mae_pts': max_adverse,
            'mfe_pts': max_favorable,
        }
    )
    return row


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
    traded = df[df['qty_start'] > 0].copy()
    wins = traded[traded['usd'] > 0]
    losses = traded[traded['usd'] < 0]
    return {
        'sessions': int(len(df)),
        'trades': int(len(traded)),
        'wins': int(len(wins)),
        'losses': int(len(losses)),
        'win_rate': float(len(wins) / len(traded) * 100.0) if len(traded) else 0.0,
        'tp1': int(traded['tp1_hit'].sum()) if len(traded) else 0,
        'tp2': int(traded['tp2_hit'].sum()) if len(traded) else 0,
        'failed_clean': int(traded['result'].eq('Failed-Clean-Close').sum()) if len(traded) else 0,
        'boundary': int(traded['runner_exit'].eq('Boundary-Stop').sum()) if len(traded) else 0,
        'runner_1r_stop': int(traded['runner_exit'].eq('Runner-1R-Stop').sum()) if len(traded) else 0,
        'runner_eod': int(traded['runner_exit'].eq('EOD').sum()) if len(traded) else 0,
        'net_usd': float(traded['usd'].sum()) if len(traded) else 0.0,
        'max_dd_usd': max_drawdown(traded['usd']) if len(traded) else 0.0,
        'pf': profit_factor(traded['usd']) if len(traded) else math.nan,
        'avg_trade_usd': float(traded['usd'].mean()) if len(traded) else 0.0,
        'avg_win_usd': float(wins['usd'].mean()) if len(wins) else 0.0,
        'avg_loss_usd': float(losses['usd'].mean()) if len(losses) else 0.0,
        'largest_loss_usd': float(losses['usd'].min()) if len(losses) else 0.0,
    }


def write_report(results: dict[str, pd.DataFrame], out_dir: Path, slip_ticks: int) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        '# v2b 09:45 Clean Break Ladder3 Runner',
        '',
        'Three-contract variant of the 09:45 clean-break / RH-boundary-stop idea.',
        '',
        'Rules:',
        '',
        '- Opening range: 09:30, 09:35, and 09:40 five-minute candles.',
        '- Trade only when the 09:45 candle is the first break and it breaks upward.',
        f'- Entry: `RH + 1 tick + {slip_ticks} slip tick(s)`.',
        '- If the 09:45 candle does not close above `RH`, close all 3 contracts at that close.',
        '- 1 contract exits at 1R, 1 contract exits at 2R.',
        '- Until 2R is hit, all remaining contracts use `RH` as the stop.',
        '- Once only the runner remains after 2R, runner stop moves to 1R.',
        '- Runner exits at 1R stop or EOD.',
        '',
        '## Summary',
        '',
        '| Market | Trades | Wins | Losses | Win Rate | TP1 Hits | TP2 Hits | Failed Clean | Boundary Stops | Runner 1R Stops | Runner EOD | Net | Max DD | PF | Avg Trade | Avg Win | Avg Loss | Largest Loss |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for market, df in results.items():
        s = summarize(df)
        lines.append(
            f"| {market.upper()} | {s['trades']} | {s['wins']} | {s['losses']} | {s['win_rate']:.1f}% | "
            f"{s['tp1']} | {s['tp2']} | {s['failed_clean']} | {s['boundary']} | "
            f"{s['runner_1r_stop']} | {s['runner_eod']} | {money(s['net_usd'])} | {money(s['max_dd_usd'])} | "
            f"{s['pf']:.2f} | {money(s['avg_trade_usd'])} | {money(s['avg_win_usd'])} | "
            f"{money(s['avg_loss_usd'])} | {money(s['largest_loss_usd'])} |"
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
        '--report-dir',
        type=Path,
        default=ROOT / 'mnq' / 'case_studies' / 'v2b_clean_break_4th_candle_ladder3_runner',
    )
    args = ap.parse_args()
    results = {market: run_market(market, cfg, args.slip_ticks) for market, cfg in MARKETS.items()}
    write_report(results, args.report_dir, args.slip_ticks)
    print(f"Wrote {args.report_dir / 'README.md'}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
