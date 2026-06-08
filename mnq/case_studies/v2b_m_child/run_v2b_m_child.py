#!/usr/bin/env python3
"""
**v2b_m_child** — same **filter** as main ``v2b_m`` (long-only, ``bullish_break``, PM-high geometry,
no hemisphere). **Tier‑1** on each session is simulated like canonical MNQ ORB long: breakout **buy stop**
``RH + tick`` after OR, **stop RL**, **target RH + Range** (1 MNQ).

**Child** (optional scale-in): after tier‑1 is filled, look for the first completed **5 m** RTH bar
(strictly **after** the tier‑1 fill timestamp) whose **open, high, low, and close are all above RH**
(entire candle above the opening range). Arm a **limit buy at that bar’s open** once the bar completes.
If touched, add **+1 MNQ** at the limit price; **child stop** at **RH** (opening-range **high** boundary;
tier‑1 keeps **RL**).
**TP remains shared** at ``RH + Range`` (flat all remaining contracts there).

Intraday: **child stop**, then **tier‑1 stop**, then **TP** within each **1 m** bar (conservative).
Unsettled size → **EOD** flatten at last RTH close before **16:00**.

Fees: **\$1.50** round-trip **per MNQ** closed (same convention as ``v2b_m/limit_retest``).

Prints **side‑by‑side** aggregate stats vs **tier‑1 simulated baseline** (same days / same tier‑1 rules).

Example::

  cd potions/mnq/case_studies/v2b_m_child
  python3 run_v2b_m_child.py --export-csv ./v2b_m_child_legs.csv
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd
import pytz

CASE_STUDIES = Path(__file__).resolve().parent.parent
V2B_M_DIR = CASE_STUDIES / 'v2b_m'
MNQ_ROOT = CASE_STUDIES.parent
POTIONS_SCRIPTS = MNQ_ROOT.parent / 'scripts'

sys.path[:0] = [str(V2B_M_DIR), str(MNQ_ROOT), str(MNQ_ROOT / 'scripts'), str(POTIONS_SCRIPTS)]

import annotate_mnq_v2b_range_context as ann  # noqa: E402
from plot_daily_prior_month_levels import (  # noqa: E402
    load_mnq_front_daily,
    monthly_high_low,
    prior_month_levels_series,
)

from engine import EPS_IDX_PT, qualify_v2b_m_legs  # noqa: E402

NY = pytz.timezone('America/New_York')
RTH_LO = time(9, 30)
RTH_HI = time(16, 0)
ORB_HI = time(9, 45)
EOD_CUTOFF = time(15, 59)

TICK = 0.25
MULT = 2.0
FEE_RT = 1.50


def rth_slice(idx_df: pd.DataFrame, session_day: date) -> pd.DataFrame:
    return idx_df[
        idx_df.index.map(lambda t: (t.date() == session_day and RTH_LO <= t.time() < RTH_HI))
    ].copy()


def resample_5m_rth(rth: pd.DataFrame, session_day: date) -> pd.DataFrame:
    if rth.empty:
        return rth
    anchor = NY.localize(datetime.combine(session_day, RTH_LO))
    return (
        rth.resample('5min', label='left', closed='left', origin=anchor)
        .agg(open=('open', 'first'), high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
        .dropna(subset=['open'])
    )


@dataclass
class SimOut:
    date_iso: str
    net_usd: float
    result_label: str
    tier1_filled: bool
    child_filled: bool
    n_contracts_closed: int


def first_tier1_fill_ts(rth_1m: pd.DataFrame, session_day: date, rh: float) -> tuple[pd.Timestamp | None, float | None]:
    """Buy-stop breakout RH+tick after OR end."""
    or_end = NY.localize(datetime.combine(session_day, ORB_HI))
    trig = rh + TICK
    fwd = rth_1m[rth_1m.index >= or_end].sort_index()
    for ts, bar in fwd.iterrows():
        if float(bar['high']) >= trig - 1e-12:
            return pd.Timestamp(ts), trig
    return None, None


def find_child_arm_and_limit(
    rth_1m: pd.DataFrame,
    session_day: date,
    rh: float,
    *,
    tier1_fill_ts: pd.Timestamp,
) -> tuple[pd.Timestamp | None, float | None]:
    """
    First completed 5 m bar after tier1_fill whose OHLC are all strictly above RH.
    Returns (limit_arm_time = bar end in NY, limit_px = bar open).
    """
    bars5 = resample_5m_rth(rth_1m, session_day).sort_index()
    for ts_left, row in bars5.iterrows():
        bar_end = pd.Timestamp(ts_left) + pd.Timedelta(minutes=5)
        if bar_end <= tier1_fill_ts:
            continue
        o, h, lo, c = map(float, (row['open'], row['high'], row['low'], row['close']))
        if min(o, h, lo, c) > rh + 1e-9:
            return bar_end, o
    return None, None


def simulate_session_tracked(
    rth_1m: pd.DataFrame,
    session_day: date,
    rh: float,
    rl: float,
    rv: float,
    *,
    with_child: bool,
) -> tuple[SimOut | None, bool]:
    """Returns (SimOut, child_filled_bool)."""
    if rv <= 1e-12:
        return None, False

    t1_ts, t1_entry = first_tier1_fill_ts(rth_1m, session_day, rh)
    if t1_ts is None or t1_entry is None:
        return None, False

    target = rh + rv
    tier1_stop = rl
    child_stop = rh  # opening-range high — tighter than tier‑1 SL at RL

    arm_ts: pd.Timestamp | None = None
    limit_px: float | None = None
    if with_child:
        arm_ts, limit_px = find_child_arm_and_limit(rth_1m, session_day, rh, tier1_fill_ts=t1_ts)

    tier1_open = True
    child_open = False
    child_entry: float | None = None
    pending_limit: float | None = None
    armed = not with_child or arm_ts is None
    child_filled_flag = False

    pnl_pts = 0.0
    fees = 0.0
    n_closed = 0

    path = rth_1m[rth_1m.index >= t1_ts].sort_index()

    def close_child(stop_px: float) -> None:
        nonlocal pnl_pts, fees, n_closed, child_open, child_entry
        assert child_open and child_entry is not None
        pnl_pts += stop_px - child_entry
        fees += FEE_RT
        n_closed += 1
        child_open = False
        child_entry = None

    def close_tier1(stop_px: float) -> None:
        nonlocal pnl_pts, fees, n_closed, tier1_open
        assert tier1_open
        pnl_pts += stop_px - float(t1_entry)
        fees += FEE_RT
        n_closed += 1
        tier1_open = False

    def close_tp() -> None:
        nonlocal pnl_pts, fees, n_closed, tier1_open, child_open, child_entry
        if tier1_open:
            pnl_pts += target - float(t1_entry)
            fees += FEE_RT
            n_closed += 1
            tier1_open = False
        if child_open and child_entry is not None:
            pnl_pts += target - child_entry
            fees += FEE_RT
            n_closed += 1
            child_open = False
            child_entry = None

    settled = False
    for ts, bar in path.iterrows():
        if ts.time() >= EOD_CUTOFF:
            break

        h = float(bar['high'])
        l = float(bar['low'])

        if with_child and not armed and arm_ts is not None and pd.Timestamp(ts) >= arm_ts:
            armed = True
            if limit_px is not None and not child_open:
                pending_limit = limit_px

        if pending_limit is not None and not child_open:
            if l <= pending_limit + 1e-9:
                child_open = True
                child_entry = pending_limit
                child_filled_flag = True
                pending_limit = None

        had_pos = tier1_open or child_open
        if not had_pos:
            continue

        if child_open and l <= child_stop + 1e-12:
            close_child(child_stop)
        if tier1_open and l <= tier1_stop + 1e-12:
            close_tier1(tier1_stop)

        if tier1_open or child_open:
            if h >= target - 1e-12:
                close_tp()
                settled = True
                break

    if settled:
        res_label = 'Win'
    elif tier1_open or child_open:
        tail = rth_1m[rth_1m.index.map(lambda ti: ti.date() == session_day and ti.time() < RTH_HI)]
        if tail.empty:
            return None, False
        eod = float(tail.iloc[-1]['close'])
        ok_agg = 0.0
        if tier1_open:
            ok_agg += eod - float(t1_entry)
            fees += FEE_RT
            n_closed += 1
            tier1_open = False
        if child_open and child_entry is not None:
            ok_agg += eod - child_entry
            fees += FEE_RT
            n_closed += 1
            child_open = False
            child_entry = None
        pnl_pts += ok_agg
        if ok_agg > 0:
            res_label = 'EOD-Win'
        elif ok_agg < 0:
            res_label = 'EOD-Loss'
        else:
            res_label = 'EOD-Flat'
    else:
        res_label = 'Loss'

    net_usd = round(pnl_pts * MULT - fees, 2)

    out = SimOut(
        date_iso=session_day.isoformat(),
        net_usd=net_usd,
        result_label=res_label,
        tier1_filled=True,
        child_filled=child_filled_flag,
        n_contracts_closed=n_closed,
    )
    return out, child_filled_flag


def csv_equity_stats(legs: pd.DataFrame) -> dict:
    """Tier‑1 historical CSV legs (v2b_m export semantics)."""
    net = legs['Net_$'].astype(float)
    tp = legs['Result'].astype(str).isin(('Win', 'EOD-Win'))
    cum = net.cumsum()
    dd = float((cum - cum.cummax()).min())
    by_day = legs.groupby(pd.to_datetime(legs['Date']).dt.date)['Net_$'].sum().sort_index()
    dd_d = float((by_day.cumsum() - by_day.cumsum().cummax()).min())
    return {
        'n': len(legs),
        'sum_net': float(net.sum()),
        'wr_tp': float(tp.mean() * 100),
        'wr_net_pos': float((net > 0).mean() * 100),
        'max_dd_leg': dd,
        'max_dd_day': dd_d,
        'label': 'v2b_m tier‑1 CSV (filtered Long rows)',
    }


def sim_equity_stats(rows: list[SimOut]) -> dict:
    if not rows:
        return {'n': 0, 'sum_net': 0.0, 'wr_tp': float('nan'), 'wr_net_pos': float('nan'), 'max_dd_leg': 0.0, 'max_dd_day': 0.0, 'label': ''}
    df = pd.DataFrame([r.__dict__ for r in rows])
    net = df['net_usd'].astype(float)
    tp = df['result_label'].isin(('Win', 'EOD-Win'))
    cum = net.cumsum()
    dd = float((cum - cum.cummax()).min())
    by_day = df.groupby('date_iso')['net_usd'].sum().sort_index()
    dd_d = float((by_day.cumsum() - by_day.cummax()).min())
    return {
        'n': len(df),
        'sum_net': float(net.sum()),
        'wr_tp': float(tp.mean() * 100),
        'wr_net_pos': float((net > 0).mean() * 100),
        'max_dd_leg': dd,
        'max_dd_day': dd_d,
        'label': '',
    }


def print_block(title: str, st: dict) -> None:
    print(f'\n=== {title} ===')
    print(f"  {st['label'] or title}")
    print(f"  Sessions / legs: {st['n']}")
    print(f"  TP-style WR (Win|EOD-Win): {st['wr_tp']:.2f}%")
    print(f"  Net_$ > 0 WR:              {st['wr_net_pos']:.2f}%")
    print(f"  Σ Net_$:                   ${st['sum_net']:,.2f}")
    print(f"  Max DD (leg cumulative):    ${st['max_dd_leg']:,.2f}")
    print(f"  Max DD (daily Net sum):     ${st['max_dd_day']:,.2f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--daily-dbn', type=Path, default=MNQ_ROOT / 'raw' / 'glbx-mdp3-20100606-20260426.ohlcv-1d.dbn.zst')
    ap.add_argument('--stops-csv', type=Path, default=MNQ_ROOT / 'mnq_orb_results_stops.csv')
    ap.add_argument('--1m', dest='m1', type=Path, default=MNQ_ROOT / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv')
    ap.add_argument('--export-csv', type=Path, default=None)
    args = ap.parse_args()

    if not args.daily_dbn.is_file() or not args.stops_csv.is_file() or not args.m1.is_file():
        print('Missing DBN, stops CSV, or 1m file.', file=sys.stderr)
        return 1

    daily = load_mnq_front_daily(args.daily_dbn)
    daily.index = pd.to_datetime(daily.index)
    monthly = monthly_high_low(daily)
    pm_h, pm_l = prior_month_levels_series(daily, monthly)

    legs = qualify_v2b_m_legs(args.stops_csv, daily, pm_h, pm_l, include_hemisphere=False)
    if legs.empty:
        print('No qualified v2b_m legs.', file=sys.stderr)
        return 1

    csv_stats = csv_equity_stats(legs)
    csv_stats['label'] = 'v2b_m tier‑1 CSV (filtered Long rows; historical fills)'

    need_dates = set(pd.to_datetime(legs['Date']).dt.date.unique())
    raw = ann.load_1m_for_dates(str(args.m1), min(need_dates), max(need_dates), need_dates)
    raw = ann.pick_front_month_day(raw)
    raw = raw.set_index(pd.DatetimeIndex(pd.to_datetime(raw['ts_event']))).sort_index()
    gby = {
        d: g for d, g in raw.groupby(pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False)
    }

    rows_base: list[SimOut] = []
    rows_child: list[SimOut] = []
    export_rows: list[dict] = []

    for _, q in legs.sort_values('Date').iterrows():
        d = pd.Timestamp(q['Date']).date()
        rh = float(q['Range_High'])
        rl = float(q['Range_Low'])
        rv = float(q['Range'])

        day_raw = gby.get(d)
        if day_raw is None or day_raw.empty:
            continue
        rth = rth_slice(day_raw, d)
        if rth.empty:
            continue

        sb, _ = simulate_session_tracked(rth, d, rh, rl, rv, with_child=False)
        sc, ch_fill = simulate_session_tracked(rth, d, rh, rl, rv, with_child=True)
        if sb is None or sc is None:
            continue
        rows_base.append(sb)
        rows_child.append(sc)
        export_rows.append(
            {
                'Date': d.isoformat(),
                'Symbol': str(q.get('Symbol', '')),
                'Range_High': rh,
                'Range_Low': rl,
                'Range': rv,
                'bias_bucket': q['bias_bucket'],
                'geom_tag': q['geom_tag'],
                'pm_high': float(q['pm_high']),
                'pm_low': float(q['pm_low']),
                'EPS_IDX_PT': EPS_IDX_PT,
                'tier1_sim_Net_$': sb.net_usd,
                'child_model_Net_$': sc.net_usd,
                'child_limit_filled': ch_fill,
                'child_model_Result': sc.result_label,
                'n_contracts_closed': sc.n_contracts_closed,
            }
        )

    sim_b = sim_equity_stats(rows_base)
    sim_b['label'] = 'Sim: tier‑1 only (RH+tick breakout, SL RL, TP RH+R) — same days as below'

    sim_c = sim_equity_stats(rows_child)
    sim_c['label'] = 'Sim: tier‑1 + child limit (OHLC>RH 5 m candle; SL child @ RH)'

    print(f'Qualified v2b_m sessions (filter): {len(legs)}')
    print(f'Sessions with simulated tier‑1 fill: {len(rows_base)}')
    print(f'EPS_IDX_PT={EPS_IDX_PT}  MNQ mult=${MULT}/pt  fee ${FEE_RT}/rt per MNQ closed')

    print_block('Reference — historical CSV book', csv_stats)
    print_block('Baseline — simulated tier‑1 only', sim_b)
    print_block('v2b_m_child — simulated tier‑1 + optional child', sim_c)

    n_child_fill = sum(1 for r in rows_child if r.child_filled)
    print(f'\nChild limit actually filled (of {len(rows_child)} sim sessions): {n_child_fill}')

    if args.export_csv:
        pd.DataFrame(export_rows).to_csv(args.export_csv, index=False)
        print(f'\nWrote {args.export_csv}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
