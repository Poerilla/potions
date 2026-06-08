#!/usr/bin/env python3
"""NQ confirmation run for adaptive 50/150 v2b-only scaleout.

Rules mirror the current MNQ leader candidate:
  - Use prior daily MA50 > MA150 as a causal gate.
  - When the gate is true, allow canonical v2b breakout rows only.
  - Skip v2d entirely.
  - Replay each accepted v2b leg on 1-minute front-month NQ.
  - Enter 2 contracts at RH+tick for longs or RL-tick for shorts.
  - Initial stop is the opposite OR boundary.
  - TP1 exits 1 contract at RH+Range / RL-Range.
  - Runner stop moves to entry after TP1.
  - TP2 exits the runner at RH+2*Range / RL-2*Range.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path
from typing import Iterable

import databento as db
import pandas as pd
import pytz


NQ_ROOT = Path('/home/tester/hsm/potions/nq')
DAILY_CSV = NQ_ROOT / 'nq_daily.csv'
V2B_CSV = NQ_ROOT / 'nq_orb_results_stops.csv'
M1_DBN = NQ_ROOT / 'raw' / 'glbx-mdp3-20100606-20260308.ohlcv-1m.dbn.zst'
OUT_CSV = NQ_ROOT / 'v2d' / 'nq_adaptive_50_150_v2b_scaleout.csv'
REPORT_MD = NQ_ROOT / 'v2d' / 'NQ_ADAPTIVE_50_150_V2B_SCALEOUT.md'

NY = pytz.timezone('America/New_York')
RTH_LO = time(9, 30)
RTH_HI = time(16, 0)
ORB_HI = time(9, 45)
EOD_CUTOFF = time(15, 59)

FAST = 50
SLOW = 150
TICK = 0.25
MULT = 20.0
FEE_RT = 1.50
_EPS = 1e-12


@dataclass
class SimLeg:
    date_iso: str
    symbol: str
    row_order: int
    direction: str
    ma_fast_prev: float | None
    ma_slow_prev: float | None
    range_high: float
    range_low: float
    range_size: float
    entry: float
    init_sl: float
    tp1: float
    tp2: float
    runner_sl: float
    fill_ts: str
    exit_ts: str
    net_usd: float
    gross_contract_points: float
    net_point_equiv: float
    result: str
    hit_tp1: bool
    hit_tp2: bool
    csv_net_1ct: float


def fmt_money(value: float) -> str:
    return f'${value:,.2f}'


def fmt_num(value: float) -> str:
    if math.isnan(value):
        return 'n/a'
    if math.isinf(value):
        return 'inf'
    return f'{value:,.2f}'


def fmt_pct(value: float) -> str:
    if math.isnan(value):
        return 'n/a'
    return f'{value:.2%}'


def max_drawdown(values: Iterable[float]) -> float:
    series = pd.Series(list(values), dtype=float)
    if series.empty:
        return 0.0
    equity = series.cumsum()
    return float((equity - equity.cummax()).min())


def profit_factor(values: pd.Series) -> float:
    gains = float(values[values > 0].sum())
    losses = float(values[values < 0].sum())
    if losses == 0:
        return math.inf if gains > 0 else math.nan
    return gains / abs(losses)


def load_front_month_rth(path: Path) -> pd.DataFrame:
    print(f'Loading {path} ...')
    store = db.DBNStore.from_file(str(path))
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('NQ')].copy()
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY)
    df['date'] = df['ts_event'].dt.date
    df['t'] = df['ts_event'].dt.time

    front = (
        df.groupby(['date', 'symbol'])['volume']
        .sum()
        .groupby(level='date')
        .idxmax()
        .apply(lambda item: item[1])
    )
    df = df[df['symbol'].eq(df['date'].map(front))]
    df = df[(df['t'] >= RTH_LO) & (df['t'] < RTH_HI)]
    df = df.set_index('ts_event').sort_index()
    print(f'  {len(df):,} NQ RTH front-month 1m bars')
    return df


def build_regime(daily_path: Path) -> pd.DataFrame:
    daily = pd.read_csv(daily_path)
    daily['Date'] = pd.to_datetime(daily['date']).dt.date
    daily = daily.sort_values('Date').set_index('Date')
    close = daily['close'].astype(float)
    ma_fast = close.rolling(FAST).mean()
    ma_slow = close.rolling(SLOW).mean()
    regime_v2b = (ma_fast > ma_slow).shift(1).fillna(True)
    return pd.DataFrame({
        'ma_fast_prev': ma_fast,
        'ma_slow_prev': ma_slow,
        'regime_v2b': regime_v2b,
    })


def rth_slice(idx_df: pd.DataFrame, session_day: date) -> pd.DataFrame:
    return idx_df[
        idx_df.index.map(lambda ts: ts.date() == session_day and RTH_LO <= ts.time() < RTH_HI)
    ].copy()


def or_prior_anchor(rth: pd.DataFrame, session_day: date) -> pd.Timestamp | None:
    pre = rth[rth.index.map(lambda ts: ts.date() == session_day and ts.time() < ORB_HI)]
    if pre.empty:
        return None
    return pd.Timestamp(pre.index[-1])


def path_after_prior(
    rth: pd.DataFrame,
    session_day: date,
    prior_exit_ts: pd.Timestamp | None,
) -> pd.DataFrame:
    if prior_exit_ts is None:
        anchor = or_prior_anchor(rth, session_day)
        if anchor is None:
            return rth.iloc[0:0]
        return rth[rth.index > anchor].sort_index()
    return rth[rth.index > prior_exit_ts].sort_index()


def find_fill(direction: str, sub: pd.DataFrame, rh: float, rl: float) -> tuple[pd.Timestamp | None, float | None]:
    if direction == 'Long':
        trig = rh + TICK
        for ts, bar in sub.iterrows():
            if float(bar['high']) >= trig - _EPS:
                return pd.Timestamp(ts), float(trig)
    else:
        trig = rl - TICK
        for ts, bar in sub.iterrows():
            if float(bar['low']) <= trig + _EPS:
                return pd.Timestamp(ts), float(trig)
    return None, None


def trade_params(direction: str, rh: float, rl: float, rv: float) -> dict | None:
    if rv <= _EPS:
        return None
    if direction == 'Long':
        return {
            'long_side': True,
            'entry': rh + TICK,
            'init_sl': rl,
            'tp1': rh + rv,
            'tp2': rh + 2.0 * rv,
            'runner_sl': rh + TICK,
        }
    return {
        'long_side': False,
        'entry': rl - TICK,
        'init_sl': rh,
        'tp1': rl - rv,
        'tp2': rl - 2.0 * rv,
        'runner_sl': rl - TICK,
    }


def label_result(net_usd: float, res_final: str, hit_tp1: bool, hit_tp2: bool) -> str:
    if res_final == 'Runner-BE' and hit_tp1 and not hit_tp2:
        return 'Win' if net_usd > 0 else 'Loss'
    if res_final == 'Win' and hit_tp2:
        return 'Win'
    if res_final.startswith('EOD'):
        return res_final
    return res_final


def simulate_scale_out_leg(
    rth: pd.DataFrame,
    session_day: date,
    fill_ts: pd.Timestamp,
    *,
    entry: float,
    long_side: bool,
    init_sl: float,
    tp1: float,
    tp2: float,
    runner_sl: float,
) -> tuple[float, str, pd.Timestamp | None, bool, bool]:
    path = rth[rth.index >= fill_ts].sort_index()
    qty = 2
    pnl_pts = 0.0
    fees = 0.0
    hit_tp1 = False
    hit_tp2 = False
    res_final = ''
    exit_ts: pd.Timestamp | None = None

    def fee_close(count: int) -> None:
        nonlocal fees
        fees += FEE_RT * count

    for ts, bar in path.iterrows():
        if ts.time() >= EOD_CUTOFF:
            break
        high = float(bar['high'])
        low = float(bar['low'])

        if long_side:
            if qty == 2:
                if low <= init_sl + _EPS:
                    pnl_pts += 2.0 * (init_sl - entry)
                    fee_close(2)
                    qty = 0
                    res_final = 'Loss'
                    exit_ts = pd.Timestamp(ts)
                    break
                if high >= tp1 - _EPS:
                    pnl_pts += tp1 - entry
                    fee_close(1)
                    hit_tp1 = True
                    qty = 1
                    if low <= runner_sl + _EPS:
                        pnl_pts += runner_sl - entry
                        fee_close(1)
                        qty = 0
                        res_final = 'Runner-BE'
                        exit_ts = pd.Timestamp(ts)
                        break
                    if high >= tp2 - _EPS:
                        pnl_pts += tp2 - entry
                        fee_close(1)
                        hit_tp2 = True
                        qty = 0
                        res_final = 'Win'
                        exit_ts = pd.Timestamp(ts)
                        break
            elif qty == 1:
                if low <= runner_sl + _EPS:
                    pnl_pts += runner_sl - entry
                    fee_close(1)
                    qty = 0
                    res_final = 'Runner-BE'
                    exit_ts = pd.Timestamp(ts)
                    break
                if high >= tp2 - _EPS:
                    pnl_pts += tp2 - entry
                    fee_close(1)
                    hit_tp2 = True
                    qty = 0
                    res_final = 'Win'
                    exit_ts = pd.Timestamp(ts)
                    break
        else:
            if qty == 2:
                if high >= init_sl - _EPS:
                    pnl_pts += 2.0 * (entry - init_sl)
                    fee_close(2)
                    qty = 0
                    res_final = 'Loss'
                    exit_ts = pd.Timestamp(ts)
                    break
                if low <= tp1 + _EPS:
                    pnl_pts += entry - tp1
                    fee_close(1)
                    hit_tp1 = True
                    qty = 1
                    if high >= runner_sl - _EPS:
                        pnl_pts += entry - runner_sl
                        fee_close(1)
                        qty = 0
                        res_final = 'Runner-BE'
                        exit_ts = pd.Timestamp(ts)
                        break
                    if low <= tp2 + _EPS:
                        pnl_pts += entry - tp2
                        fee_close(1)
                        hit_tp2 = True
                        qty = 0
                        res_final = 'Win'
                        exit_ts = pd.Timestamp(ts)
                        break
            elif qty == 1:
                if high >= runner_sl - _EPS:
                    pnl_pts += entry - runner_sl
                    fee_close(1)
                    qty = 0
                    res_final = 'Runner-BE'
                    exit_ts = pd.Timestamp(ts)
                    break
                if low <= tp2 + _EPS:
                    pnl_pts += entry - tp2
                    fee_close(1)
                    hit_tp2 = True
                    qty = 0
                    res_final = 'Win'
                    exit_ts = pd.Timestamp(ts)
                    break

    if qty > 0:
        tail = rth[rth.index.map(lambda ts: ts.date() == session_day and ts.time() < RTH_HI)]
        if tail.empty:
            return 0.0, 'Loss', exit_ts, hit_tp1, hit_tp2
        eod = float(tail.iloc[-1]['close'])
        exit_ts = pd.Timestamp(tail.index[-1])
        if long_side:
            pnl_pts += qty * (eod - entry)
        else:
            pnl_pts += qty * (entry - eod)
        fee_close(qty)
        res_final = 'EOD-Win' if pnl_pts > 0 else ('EOD-Loss' if pnl_pts < 0 else 'EOD-Flat')

    net_usd = round(pnl_pts * MULT - fees, 2)
    return net_usd, label_result(net_usd, res_final, hit_tp1, hit_tp2), exit_ts, hit_tp1, hit_tp2


def metrics(label: str, frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {
            'segment': label,
            'legs': 0,
            'days': 0,
            'net_usd': 0.0,
            'gross_contract_points': 0.0,
            'net_point_equiv': 0.0,
            'trade_dd_usd': 0.0,
            'daily_dd_usd': 0.0,
            'win_rate': math.nan,
            'profit_factor': math.nan,
            'avg_trade': math.nan,
            'tp1_rate': math.nan,
            'tp2_rate': math.nan,
        }
    work = frame.sort_values(['date_iso', 'row_order']).copy()
    pnl = work['net_usd'].astype(float)
    daily = work.groupby('date_iso', sort=True)['net_usd'].sum()
    return {
        'segment': label,
        'legs': int(len(work)),
        'days': int(work['date_iso'].nunique()),
        'net_usd': float(pnl.sum()),
        'gross_contract_points': float(work['gross_contract_points'].sum()),
        'net_point_equiv': float(work['net_point_equiv'].sum()),
        'trade_dd_usd': max_drawdown(pnl),
        'daily_dd_usd': max_drawdown(daily),
        'win_rate': float((pnl > 0).mean()),
        'profit_factor': profit_factor(pnl),
        'avg_trade': float(pnl.mean()),
        'tp1_rate': float(work['hit_tp1'].mean()),
        'tp2_rate': float(work['hit_tp2'].mean()),
    }


def metric_table(rows: list[dict]) -> str:
    lines = [
        '| Segment | Legs | Days | Net | Gross pts | Net pt equiv | Trade DD | Daily DD | Win rate | PF | TP1 | TP2 | Avg/trade |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for row in rows:
        lines.append(
            '| {segment} | {legs} | {days} | {net} | {gross_pts:,.2f} | {net_pts:,.2f} | {trade_dd} | {daily_dd} | {wr} | {pf} | {tp1} | {tp2} | {avg} |'.format(
                segment=row['segment'],
                legs=row['legs'],
                days=row['days'],
                net=fmt_money(row['net_usd']),
                gross_pts=row['gross_contract_points'],
                net_pts=row['net_point_equiv'],
                trade_dd=fmt_money(row['trade_dd_usd']),
                daily_dd=fmt_money(row['daily_dd_usd']),
                wr=fmt_pct(row['win_rate']),
                pf=fmt_num(row['profit_factor']),
                tp1=fmt_pct(row['tp1_rate']),
                tp2=fmt_pct(row['tp2_rate']),
                avg=fmt_money(row['avg_trade']) if not math.isnan(row['avg_trade']) else 'n/a',
            )
        )
    return '\n'.join(lines)


def run_policy(
    *,
    label: str,
    v2b_rows: pd.DataFrame,
    raw_by_day: dict[date, pd.DataFrame],
    regime: pd.DataFrame,
    use_ma_gate: bool,
) -> tuple[pd.DataFrame, dict]:
    legs: list[SimLeg] = []
    skipped_by_gate = 0
    skipped_by_fill = 0

    for session_day in sorted(v2b_rows['Date'].unique()):
        if session_day not in regime.index:
            skipped_by_gate += len(v2b_rows[v2b_rows['Date'] == session_day])
            continue
        if use_ma_gate and not bool(regime.loc[session_day, 'regime_v2b']):
            skipped_by_gate += len(v2b_rows[v2b_rows['Date'] == session_day])
            continue

        day_raw = raw_by_day.get(session_day)
        day_rows = v2b_rows[v2b_rows['Date'] == session_day].sort_values('_row_order')
        if day_raw is None or day_raw.empty:
            skipped_by_fill += len(day_rows)
            continue
        rth = rth_slice(day_raw, session_day)
        if rth.empty:
            skipped_by_fill += len(day_rows)
            continue

        prior_exit_ts: pd.Timestamp | None = None
        for _, row in day_rows.iterrows():
            direction = str(row['Trade_Direction']).strip()
            rh = float(row['Range_High'])
            rl = float(row['Range_Low'])
            rv = float(row['Range'])
            pm = trade_params(direction, rh, rl, rv)
            if pm is None:
                skipped_by_fill += 1
                continue
            sub = path_after_prior(rth, session_day, prior_exit_ts)
            if sub.empty:
                skipped_by_fill += 1
                continue
            fill_ts, _ = find_fill(direction, sub, rh, rl)
            if fill_ts is None:
                skipped_by_fill += 1
                continue
            net_usd, result, exit_ts, h1, h2 = simulate_scale_out_leg(
                rth,
                session_day,
                fill_ts,
                entry=float(pm['entry']),
                long_side=bool(pm['long_side']),
                init_sl=float(pm['init_sl']),
                tp1=float(pm['tp1']),
                tp2=float(pm['tp2']),
                runner_sl=float(pm['runner_sl']),
            )
            if exit_ts is None:
                skipped_by_fill += 1
                continue
            prior_exit_ts = exit_ts
            legs.append(
                SimLeg(
                    date_iso=session_day.isoformat(),
                    symbol=str(row.get('Symbol', '')),
                    row_order=int(row['_row_order']),
                    direction=direction,
                    ma_fast_prev=(
                        round(float(regime.loc[session_day, 'ma_fast_prev']), 4)
                        if pd.notna(regime.loc[session_day, 'ma_fast_prev']) else None
                    ),
                    ma_slow_prev=(
                        round(float(regime.loc[session_day, 'ma_slow_prev']), 4)
                        if pd.notna(regime.loc[session_day, 'ma_slow_prev']) else None
                    ),
                    range_high=rh,
                    range_low=rl,
                    range_size=rv,
                    entry=float(pm['entry']),
                    init_sl=float(pm['init_sl']),
                    tp1=float(pm['tp1']),
                    tp2=float(pm['tp2']),
                    runner_sl=float(pm['runner_sl']),
                    fill_ts=pd.Timestamp(fill_ts).isoformat(),
                    exit_ts=pd.Timestamp(exit_ts).isoformat(),
                    net_usd=net_usd,
                    gross_contract_points=(net_usd + 2.0 * FEE_RT) / MULT,
                    net_point_equiv=net_usd / MULT,
                    result=result,
                    hit_tp1=bool(h1),
                    hit_tp2=bool(h2),
                    csv_net_1ct=float(row['Net_$']),
                )
            )

    frame = pd.DataFrame([leg.__dict__ for leg in legs])
    skip = {
        'segment': label,
        'skipped_by_gate': skipped_by_gate,
        'skipped_by_fill_or_data': skipped_by_fill,
    }
    return frame, skip


def write_report(path: Path, out_csv: Path, summary_csv: Path, skip_csv: Path, rows: list[dict]) -> None:
    by = {row['segment']: row for row in rows}
    adaptive = by['adaptive 50/150 v2b-only scaleout']
    all_v2b = by['all v2b days scaleout']
    report = [
        '# NQ adaptive 50/150 v2b-only scaleout',
        '',
        'Longer-sample NQ confirmation for the MNQ leader candidate.',
        '',
        '## Rules',
        '',
        '- Compute daily MA50 and MA150 from NQ front-month daily closes.',
        '- At each RTH session, use only information known before the open: prior daily MA50 > prior daily MA150 allows v2b; otherwise the day is skipped.',
        '- No v2d fade arm is traded in this candidate.',
        '- Opening range is 09:30-09:45 New York.',
        '- Parent entry is v2b breakout: Long at `RH + 0.25`, Short at `RL - 0.25`.',
        '- Initial stop is the opposite opening-range boundary.',
        '- Trade 2 NQ contracts: 1 exits at TP1 (`RH + Range` / `RL - Range`), then the runner stop moves to entry.',
        '- Runner exits at TP2 (`RH + 2*Range` / `RL - 2*Range`), runner stop, or end of session.',
        '- Intrabar ordering is pessimistic: stop before target while fully loaded, and runner stop before TP2 when both touch.',
        '- Fill model matches the MNQ scaleout research path: no extra entry slippage beyond the boundary tick, $1.50 round-trip fee per contract, and end-of-session flatten before 16:00.',
        '',
        '## Headline',
        '',
        f'- Adaptive 50/150 v2b-only scaleout: {adaptive["legs"]:,} legs, {fmt_money(adaptive["net_usd"])}, DD {fmt_money(adaptive["trade_dd_usd"])}, PF {fmt_num(adaptive["profit_factor"])}.',
        f'- All v2b days scaleout reference: {all_v2b["legs"]:,} legs, {fmt_money(all_v2b["net_usd"])}, DD {fmt_money(all_v2b["trade_dd_usd"])}, PF {fmt_num(all_v2b["profit_factor"])}.',
        '',
        '## Metrics',
        '',
        metric_table(rows),
        '',
        '## Outputs',
        '',
        f'- Legs: [{out_csv.name}]({out_csv.name})',
        f'- Summary CSV: [{summary_csv.name}]({summary_csv.name})',
        f'- Skip audit: [{skip_csv.name}]({skip_csv.name})',
        '',
    ]
    path.write_text('\n'.join(report), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, default=DAILY_CSV)
    ap.add_argument('--v2b', type=Path, default=V2B_CSV)
    ap.add_argument('--1m-dbn', dest='m1_dbn', type=Path, default=M1_DBN)
    ap.add_argument('--out-csv', type=Path, default=OUT_CSV)
    ap.add_argument('--report', type=Path, default=REPORT_MD)
    args = ap.parse_args()

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)

    regime = build_regime(args.daily)
    v2b = pd.read_csv(args.v2b)
    v2b['_row_order'] = range(len(v2b))
    v2b['Date'] = pd.to_datetime(v2b['Date']).dt.date
    raw = load_front_month_rth(args.m1_dbn)
    raw_by_day = {
        day: frame
        for day, frame in raw.groupby(pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False)
    }

    adaptive_frame, adaptive_skips = run_policy(
        label='adaptive 50/150 v2b-only scaleout',
        v2b_rows=v2b,
        raw_by_day=raw_by_day,
        regime=regime,
        use_ma_gate=True,
    )
    adaptive_frame.insert(0, 'segment', 'adaptive_50_150_v2b_only_scaleout')

    all_frame, all_skips = run_policy(
        label='all v2b days scaleout',
        v2b_rows=v2b,
        raw_by_day=raw_by_day,
        regime=regime,
        use_ma_gate=False,
    )
    all_frame.insert(0, 'segment', 'all_v2b_days_scaleout')

    combined = pd.concat([adaptive_frame, all_frame], ignore_index=True)
    summary = [
        metrics('adaptive 50/150 v2b-only scaleout', adaptive_frame),
        metrics('all v2b days scaleout', all_frame),
    ]
    summary_csv = args.out_csv.with_suffix('.summary.csv')
    skip_csv = args.out_csv.with_suffix('.skips.csv')

    combined.to_csv(args.out_csv, index=False)
    pd.DataFrame(summary).to_csv(summary_csv, index=False)
    pd.DataFrame([adaptive_skips, all_skips]).to_csv(skip_csv, index=False)
    write_report(args.report, args.out_csv, summary_csv, skip_csv, summary)

    print(metric_table(summary))
    print(f'Wrote {args.out_csv}')
    print(f'Wrote {summary_csv}')
    print(f'Wrote {skip_csv}')
    print(f'Wrote {args.report}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
