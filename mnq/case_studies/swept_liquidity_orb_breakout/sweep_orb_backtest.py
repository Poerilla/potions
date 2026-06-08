#!/usr/bin/env python3
"""
Swept-liquidity ORB breakout experiment (MNQ NY, 2 MNQ logical lots).

Mechanics (causal):
  1) ORB forms 9:30–9:45 (RH, RL, RV = RH − RL).
  2) First confirmed 5 m close beyond RH+tick / RL−tick = **brk1** direction.
  3) At least one 1 m bar strictly after brk1 ends, **before brk2 5 m starts**, fully inside [RL, RH].
  4) Second confirmed 5 m close breakout **opposite** brk1 = **brk2**; limit at **brk2 close**,
     active once that 5 m bar completes.
  5) Skip if **brk1** classic OR target (RH+RV for first Long break, RL−RV for first Short break)
     touches intrabar **before** the limit fills.
  6) Scale: 2 contracts — +1 RV and +2 RV exits; SL at −1 RV from entry (same R = RV until flat).
     Same-bar pessimism: stop before profit (**loss before TP** when both spans overlap).
  7) Multiple sweeps per day allowed after skip / FLAT / resolved trade.

Fees: approximate round-trip MNQ commission per partial (2 exits → 2× FEE_RT on position).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import time as dtime
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import databento as db
import pandas as pd
import pytz


NY_TZ = pytz.timezone('America/New_York')


def open_range_end_time(minutes: int = 15) -> dtime:
    return (pd.Timestamp('2000-01-01 09:30') + pd.Timedelta(minutes=minutes)).time()


RANGE_END_T = open_range_end_time()
T_OR_END = RANGE_END_T
T_RTH0 = dtime(9, 30)
T_RTH1 = dtime(16, 0)
T_SIM_END = dtime(15, 55)

TICK = 0.25
MULT = 2.0
FEE_RT = 1.50
POSITION_SIZE = 2

DBN_DEFAULT = '/home/tester/hsm/potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'
CSV_DEFAULT = Path(__file__).resolve().parent / 'mnq_swept_orb_breakout.csv'
EPS = 1e-9


def load_one_min(history_start: Optional[str] = None) -> pd.DataFrame:
    print(f'Loading {DBN_DEFAULT} ...')
    store = db.DBNStore.from_file(DBN_DEFAULT)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')]
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY_TZ)
    df['date'] = df['ts_event'].dt.date
    df['t'] = df['ts_event'].dt.time
    fm = df.groupby(['date', 'symbol'])['volume'].sum().groupby(level='date').idxmax().apply(lambda x: x[1]).to_dict()
    df = df[df.apply(lambda r: r['symbol'] == fm.get(r['date']), axis=1)]
    df = df[(df['t'] >= T_RTH0) & (df['t'] < T_RTH1)]
    if history_start is None:
        df = df[df['date'] >= pd.Timestamp('2021-03-04').date()]
    else:
        df = df[df['date'] >= pd.Timestamp(history_start).date()]
    out = df.set_index('ts_event').sort_index()
    assert out.index.is_monotonic_increasing
    return out


def _range_left_edge(day_ix: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(day_ix).normalize() + pd.Timedelta(hours=9, minutes=30)


def resample_5m(df1: pd.DataFrame) -> pd.DataFrame:
    """Anchor 9:30 so 5 m bars align with OR window."""
    ix0 = df1.index[0]
    anch = _range_left_edge(ix0)
    return (
        df1.resample('5min', label='left', closed='left', origin=anch)
        .agg(o=('open', 'first'), h=('high', 'max'), l=('low', 'min'), c=('close', 'last'))
        .dropna(subset=['o'])
    )


def classify_5m_row(row: pd.Series, rh: float, rl: float) -> Optional[Literal['Long', 'Short']]:
    clo, opn = float(row['c']), float(row['o'])
    lt, st = rh + TICK, rl - TICK
    lon = clo >= lt - EPS
    sho = clo <= st + EPS
    if not lon and not sho:
        return None
    if lon and sho:
        return 'Long' if opn >= (rh + rl) / 2.0 else 'Short'
    return 'Long' if lon else 'Short'


def has_pullback_inside(
    m1: pd.DataFrame,
    t_start: pd.Timestamp,
    t_end_exclusive: pd.Timestamp,
    rh: float,
    rl: float,
) -> bool:
    w = m1[(m1.index >= t_start) & (m1.index < t_end_exclusive)]
    if w.empty:
        return False
    return bool(((w['low'] >= rl - EPS) & (w['high'] <= rh + EPS)).any())


def classic_or_tp_level(brk1_dir: Literal['Long', 'Short'], rh: float, rl: float, rv: float) -> float:
    """First-breakout canonical full target."""
    return rh + rv if brk1_dir == 'Long' else rl - rv


def breach_brk1_classic_tp(brk1_dir: Literal['Long', 'Short'], lvl: float, hi: float, lo: float) -> bool:
    if brk1_dir == 'Long':
        return hi >= lvl - EPS  # bullish extension
    return lo <= lvl + EPS


def breach_limit_fill(direction: Literal['Long', 'Short'], lim: float, hi: float, lo: float) -> bool:
    if direction == 'Long':
        return lo <= lim + EPS  # buy limit
    return hi >= lim - EPS  # sell limit


@dataclass
class SweepMeta:
    brk2_left_edge: pd.Timestamp
    dir2: Literal['Long', 'Short']
    limit_px: float
    brk1_dir: Literal['Long', 'Short']


def find_next_sweep(
    day_5m: pd.DataFrame,
    m1: pd.DataFrame,
    rh: float,
    rl: float,
    rv: float,
    start_ix: int,
) -> Optional[Tuple[SweepMeta, int]]:
    """brk1 → pullback strictly before second 5 m bar opens → opposite brk2."""
    ix = day_5m.index
    n = len(ix)
    for i in range(start_ix, max(0, n - 1)):
        d1 = classify_5m_row(day_5m.iloc[i], rh, rl)
        if d1 is None:
            continue
        t1_end = ix[i] + pd.Timedelta(minutes=5)
        pull_from = t1_end
        for j in range(i + 1, n):
            t_j_left = ix[j]
            if not has_pullback_inside(m1, pull_from, t_j_left, rh, rl):
                continue
            d2 = classify_5m_row(day_5m.iloc[j], rh, rl)
            if d2 is None or d2 == d1:
                continue
            meta = SweepMeta(
                brk2_left_edge=t_j_left,
                dir2=d2,
                limit_px=float(day_5m.iloc[j]['c']),
                brk1_dir=d1,
            )
            return meta, j + 1
    return None


def _skip_row(
    day: pd.Timestamp.date,
    sym: str,
    meta: SweepMeta,
    rh: float,
    rl: float,
    rv: float,
    reason: str,
    seq: str,
    session_open: Optional[float],
    sk_lvl: Optional[float],
) -> Dict[str, Any]:
    return {
        'Date': day,
        'Day_of_Week': pd.Timestamp(day).strftime('%A'),
        'Symbol': sym,
        'Sequence_ID': seq,
        'Sweep': meta.brk2_left_edge.isoformat(),
        'Trade_Direction': meta.dir2,
        'brk1_dir': meta.brk1_dir,
        'Skip_Level_or_ref': sk_lvl,
        'Entry_Price': None,
        'Exit_Price': None,
        'Trade_PL_pts': None,
        'Gross_$': None,
        'Net_$': None,
        'Result': reason,
        'Entry_Time': None,
        'Exit_Time': None,
        'TP1_Level': None,
        'TP2_Level': None,
        'SL_Level': None,
        'RH': rh,
        'RL': rl,
        'Range': rv,
        'MAE_pts': None,
        'MFE_pts': None,
        'Max_DD_From_Peak_Unreal_pts': None,
        'Session_Open_930': session_open,
    }


def _realized_pts(direction: Literal['Long', 'Short'], entry: float, exit_px: float) -> float:
    return exit_px - entry if direction == 'Long' else entry - exit_px


def simulate_sweep_trade(
    m1: pd.DataFrame,
    meta: SweepMeta,
    rh: float,
    rl: float,
    rv: float,
    sym: str,
    day_tag: pd.Timestamp.date,
    trade_tag: str,
    session_open: Optional[float],
) -> Dict[str, Any]:
    """Limit fill scanning, intraday 2-lot simulation, MAE/MFE (bar range) and close-based peak DD."""
    t_work = meta.brk2_left_edge + pd.Timedelta(minutes=5)
    fwd = m1[m1.index >= t_work]
    fwd = fwd[fwd.index.map(lambda t: t.time() < T_SIM_END)]
    lim = meta.limit_px
    d_ent = meta.dir2
    d_long = d_ent == 'Long'
    sk = classic_or_tp_level(meta.brk1_dir, rh, rl, rv)

    fill_ts: Optional[pd.Timestamp] = None

    if fwd.empty:
        return _skip_row(day_tag, sym, meta, rh, rl, rv, 'no_work_time', trade_tag, session_open, sk)

    for ts, bar in fwd.iterrows():
        lo, hi = float(bar['low']), float(bar['high'])
        # pessimistic invalidation before fill assessment
        if breach_brk1_classic_tp(meta.brk1_dir, sk, hi, lo):
            return _skip_row(day_tag, sym, meta, rh, rl, rv, 'skip_classic_TP_before_fill', trade_tag, session_open, sk)
        if breach_limit_fill(d_ent, lim, hi, lo):
            fill_ts = ts
            break

    if fill_ts is None:
        return _skip_row(day_tag, sym, meta, rh, rl, rv, 'no_limit_fill', trade_tag, session_open, sk)

    tp1 = lim + rv if d_long else lim - rv
    tp2 = lim + 2.0 * rv if d_long else lim - 2.0 * rv
    sl_px = lim - rv if d_long else lim + rv

    path = m1[m1.index >= fill_ts]
    intraday_only = path[path.index.map(lambda t: t.time() < T_SIM_END)]

    qty = POSITION_SIZE
    sum_pts = 0.0
    exit_ts: Optional[pd.Timestamp] = fill_ts
    last_exit_px = lim

    mfe_pts = 0.0
    mae_pts = 0.0
    peak_close_unreal = -1e18
    max_dd_peak_to_close = 0.0

    def unreal_from_close(px_close: float) -> float:
        return _realized_pts(d_ent, lim, px_close)

    def note_bar(hi: float, lo: float, clo: float) -> None:
        nonlocal mfe_pts, mae_pts, peak_close_unreal, max_dd_peak_to_close
        if d_long:
            mfe_pts = max(mfe_pts, hi - lim)
            mae_pts = max(mae_pts, max(0.0, lim - lo))
        else:
            mfe_pts = max(mfe_pts, lim - lo)
            mae_pts = max(mae_pts, max(0.0, hi - lim))
        uc = unreal_from_close(clo)
        peak_close_unreal = max(peak_close_unreal, uc)
        max_dd_peak_to_close = max(max_dd_peak_to_close, peak_close_unreal - uc)

    def process_long(ts_: pd.Timestamp, hi: float, lo: float) -> bool:
        nonlocal qty, sum_pts, exit_ts, last_exit_px
        if qty <= 0:
            return True
        if lo <= sl_px + EPS:
            sum_pts += qty * (sl_px - lim)
            qty = 0
            last_exit_px = sl_px
            exit_ts = ts_
            return True
        if qty == 2:
            if hi >= tp2 - EPS:
                sum_pts += (tp1 - lim) + (tp2 - lim)
                qty = 0
                last_exit_px = tp2
                exit_ts = ts_
                return True
            if hi >= tp1 - EPS:
                sum_pts += tp1 - lim
                qty = 1
                if lo <= sl_px + EPS:
                    sum_pts += sl_px - lim
                    qty = 0
                    last_exit_px = sl_px
                    exit_ts = ts_
                    return True
                if hi >= tp2 - EPS:
                    sum_pts += tp2 - lim
                    qty = 0
                    last_exit_px = tp2
                    exit_ts = ts_
                    return True
            return False
        if lo <= sl_px + EPS:
            sum_pts += sl_px - lim
            qty = 0
            last_exit_px = sl_px
            exit_ts = ts_
            return True
        if hi >= tp2 - EPS:
            sum_pts += tp2 - lim
            qty = 0
            last_exit_px = tp2
            exit_ts = ts_
            return True
        return False

    def process_short(ts_: pd.Timestamp, hi: float, lo: float) -> bool:
        nonlocal qty, sum_pts, exit_ts, last_exit_px
        if qty <= 0:
            return True
        if hi >= sl_px - EPS:
            sum_pts += qty * (lim - sl_px)
            qty = 0
            last_exit_px = sl_px
            exit_ts = ts_
            return True
        if qty == 2:
            if lo <= tp2 + EPS:
                sum_pts += (lim - tp1) + (lim - tp2)
                qty = 0
                last_exit_px = tp2
                exit_ts = ts_
                return True
            if lo <= tp1 + EPS:
                sum_pts += lim - tp1
                qty = 1
                if hi >= sl_px - EPS:
                    sum_pts += lim - sl_px
                    qty = 0
                    last_exit_px = sl_px
                    exit_ts = ts_
                    return True
                if lo <= tp2 + EPS:
                    sum_pts += lim - tp2
                    qty = 0
                    last_exit_px = tp2
                    exit_ts = ts_
                    return True
            return False
        if hi >= sl_px - EPS:
            sum_pts += lim - sl_px
            qty = 0
            last_exit_px = sl_px
            exit_ts = ts_
            return True
        if lo <= tp2 + EPS:
            sum_pts += lim - tp2
            qty = 0
            last_exit_px = tp2
            exit_ts = ts_
            return True
        return False

    flat = False
    for ts, bar in intraday_only.iterrows():
        hi = float(bar['high'])
        lo = float(bar['low'])
        clo = float(bar['close'])
        note_bar(hi, lo, clo)
        if d_long:
            flat = process_long(ts, hi, lo)
        else:
            flat = process_short(ts, hi, lo)
        if flat:
            break

    if qty > 0:
        tail = intraday_only if len(intraday_only) > 0 else path
        if tail.empty:
            tail = path
        last_row = tail.iloc[-1]
        px = float(last_row['close'])
        xt = tail.index[-1]
        sum_pts += qty * _realized_pts(d_ent, lim, px)
        qty = 0
        last_exit_px = px
        exit_ts = xt
        ok = sum_pts > EPS
        result_kind = 'EOD-Win' if ok else 'EOD-Loss'
    else:
        ok = sum_pts > EPS
        result_kind = 'Win' if ok else 'Loss'

    gross_usd = round(sum_pts * MULT, 2)
    net_usd = round(gross_usd - 2.0 * FEE_RT, 2)

    return {
        'Date': day_tag,
        'Day_of_Week': pd.Timestamp(day_tag).strftime('%A'),
        'Symbol': sym,
        'Sequence_ID': trade_tag,
        'Sweep': meta.brk2_left_edge.isoformat(),
        'Trade_Direction': d_ent,
        'brk1_dir': meta.brk1_dir,
        'Skip_Level_or_ref': sk,
        'Entry_Price': round(lim, 4),
        'Exit_Price': round(last_exit_px, 4),
        'Trade_PL_pts': round(sum_pts, 6),
        'Gross_$': gross_usd,
        'Net_$': net_usd,
        'Result': result_kind,
        'Entry_Time': fill_ts.isoformat(),
        'Exit_Time': exit_ts.isoformat() if exit_ts is not None else None,
        'TP1_Level': round(tp1, 4),
        'TP2_Level': round(tp2, 4),
        'SL_Level': round(sl_px, 4),
        'RH': rh,
        'RL': rl,
        'Range': rv,
        'MAE_pts': round(mae_pts, 6),
        'MFE_pts': round(mfe_pts, 6),
        'Max_DD_From_Peak_Unreal_pts': round(max_dd_peak_to_close, 6),
        'Session_Open_930': session_open,
    }


def simulate_day(
    day_1m: pd.DataFrame,
    day_5m: pd.DataFrame,
    rh: float,
    rl: float,
    rv: float,
) -> List[Dict[str, Any]]:
    sym = str(day_1m['symbol'].iloc[0]) if 'symbol' in day_1m.columns else ''
    session_open = float(day_1m.iloc[0]['open']) if len(day_1m) else None
    i0 = day_5m.index.searchsorted(_range_left_edge(day_5m.index[0]) + pd.Timedelta(minutes=15))
    start_ix = int(i0) if i0 < len(day_5m) else 0

    rows: List[Dict[str, Any]] = []
    seq = 0
    cur = start_ix

    while cur < len(day_5m):
        hit = find_next_sweep(day_5m, day_1m, rh, rl, rv, cur)
        if hit is None:
            break
        meta, nxt = hit
        trade_tag = f'{day_1m.index[0].date()}_{seq}'
        row = simulate_sweep_trade(day_1m, meta, rh, rl, rv, sym, day_1m.index[0].date(), trade_tag, session_open)
        rows.append(row)
        seq += 1
        cur = nxt

    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=str, default=str(CSV_DEFAULT))
    ap.add_argument('--history-start', type=str, default=None)
    args = ap.parse_args()

    df = load_one_min(args.history_start)
    out_rows: List[Dict[str, Any]] = []

    for day, ddf in df.groupby('date'):
        ddf = ddf.sort_index()
        rb = ddf[ddf['t'] < RANGE_END_T]
        if rb.empty:
            continue
        rh = float(rb['high'].max())
        rl = float(rb['low'].min())
        rv = rh - rl
        if rv <= 1e-9:
            continue
        d5 = resample_5m(ddf)
        if d5.empty:
            continue
        out_rows.extend(simulate_day(ddf, d5, rh, rl, rv))

    out = pd.DataFrame(out_rows)
    if not out.empty:
        out = out.sort_values(['Date', 'Sequence_ID'])
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    print(f'Wrote {len(out)} rows → {out_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
