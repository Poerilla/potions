#!/usr/bin/env python3
"""
**v2b_m_so** — scale-out runner on the same **v2b_m** filter (long-only, ``bullish_break``,
PM-high geometry, no hemisphere).

**Tier‑1 entry** matches canonical sim: buy-stop **``RH + tick``** after OR, initial **SL ``RL``**.

**Baseline (1 MNQ):** flat at **TP = RH + Range**, SL RL (same as ``limit_retest`` / ``v2b_m_child`` tier‑1 sim).

**Scale-out (2 MNQ):**

- Open **2 contracts** at the same fill price (**RH + tick**), initial **SL RL** for both.
- **TP1:** sell **1** at **RH + Range** (classic target).
- Immediately raise the runner’s stop to **RH + one tick** (flat/breakeven band vs entry).
- **TP2:** runner exits at **RH + 2·Range**.

**Scale-out (3 MNQ)** — same stops / TP levels; **1** lot at TP1, remaining **2** at TP2 (runner SL **RH+tick** after TP1).

Intraday **pessimistic** ordering on each **1 m** bar: **full SL (RL)** before **TP1** when both touch;
after TP1, **runner SL (RH+tick)** before **TP2** when both touch. Unclosed size → **EOD** flatten at last
RTH close before **16:00**.

Fees: **\$1.50** round-trip **per MNQ** closed; **\$2**/point.

Example::

  cd potions/mnq/case_studies/v2b_m/v2b_m_so
  python3 run_v2b_m_so.py --export-csv ./v2b_m_so_compare.csv
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd
import pytz

V2B_SO = Path(__file__).resolve().parent
V2B_M = V2B_SO.parent
MNQ_ROOT = V2B_M.parents[1]
POTIONS_SCRIPTS = MNQ_ROOT.parent / 'scripts'

sys.path[:0] = [str(V2B_M), str(MNQ_ROOT), str(MNQ_ROOT / 'scripts'), str(POTIONS_SCRIPTS)]

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


def first_tier1_fill_ts(
    rth_1m: pd.DataFrame, session_day: date, rh: float
) -> tuple[pd.Timestamp | None, float | None]:
    or_end = NY.localize(datetime.combine(session_day, ORB_HI))
    trig = rh + TICK
    fwd = rth_1m[rth_1m.index >= or_end].sort_index()
    for ts, bar in fwd.iterrows():
        if float(bar['high']) >= trig - 1e-12:
            return pd.Timestamp(ts), trig
    return None, None


@dataclass
class BaselineOut:
    date_iso: str
    net_usd: float
    result_label: str


@dataclass
class ScaleOutOut:
    date_iso: str
    net_usd: float
    result_label: str
    hit_tp1: bool
    hit_tp2: bool


def simulate_baseline_1ct(
    rth_1m: pd.DataFrame,
    session_day: date,
    rh: float,
    rl: float,
    rv: float,
) -> BaselineOut | None:
    if rv <= 1e-12:
        return None
    t_fill, entry = first_tier1_fill_ts(rth_1m, session_day, rh)
    if t_fill is None or entry is None:
        return None
    target = rh + rv
    stop_sl = rl

    path = rth_1m[rth_1m.index >= t_fill].sort_index()
    settled = False
    pnl_pts = 0.0
    fees = FEE_RT

    for ts, bar in path.iterrows():
        if ts.time() >= EOD_CUTOFF:
            break
        h = float(bar['high'])
        l = float(bar['low'])
        if l <= stop_sl + 1e-12:
            pnl_pts = stop_sl - float(entry)
            settled = True
            res = 'Loss'
            break
        if h >= target - 1e-12:
            pnl_pts = target - float(entry)
            settled = True
            res = 'Win'
            break

    if not settled:
        tail = rth_1m[rth_1m.index.map(lambda ti: ti.date() == session_day and ti.time() < RTH_HI)]
        if tail.empty:
            return None
        eod = float(tail.iloc[-1]['close'])
        pnl_pts = eod - float(entry)
        res = 'EOD-Win' if pnl_pts > 0 else ('EOD-Loss' if pnl_pts < 0 else 'EOD-Flat')

    net_usd = round(pnl_pts * MULT - fees, 2)
    return BaselineOut(date_iso=session_day.isoformat(), net_usd=net_usd, result_label=res)


def simulate_scale_out_2ct(
    rth_1m: pd.DataFrame,
    session_day: date,
    rh: float,
    rl: float,
    rv: float,
) -> ScaleOutOut | None:
    if rv <= 1e-12:
        return None
    t_fill, entry_f = first_tier1_fill_ts(rth_1m, session_day, rh)
    if t_fill is None or entry_f is None:
        return None

    entry = float(entry_f)
    tp1 = rh + rv
    tp2 = rh + 2.0 * rv
    runner_sl = rh + TICK

    path = rth_1m[rth_1m.index >= t_fill].sort_index()
    qty = 2
    pnl_pts = 0.0
    fees = 0.0
    hit_tp1 = False
    hit_tp2 = False
    res_final = ''

    def fee_close(n: int = 1) -> None:
        nonlocal fees
        fees += FEE_RT * n

    for ts, bar in path.iterrows():
        if ts.time() >= EOD_CUTOFF:
            break
        h = float(bar['high'])
        l = float(bar['low'])

        if qty == 2:
            if l <= rl + 1e-12:
                pnl_pts += 2.0 * (rl - entry)
                fee_close(2)
                qty = 0
                res_final = 'Loss'
                break
            if h >= tp1 - 1e-12:
                pnl_pts += tp1 - entry
                fee_close(1)
                hit_tp1 = True
                qty = 1
                # runner same bar: SL before TP2 (pessimistic)
                if l <= runner_sl + 1e-12:
                    pnl_pts += runner_sl - entry
                    fee_close(1)
                    qty = 0
                    res_final = 'Runner-BE' if abs(runner_sl - entry) < 1e-9 else 'Loss'
                    break
                if h >= tp2 - 1e-12:
                    pnl_pts += tp2 - entry
                    fee_close(1)
                    hit_tp2 = True
                    qty = 0
                    res_final = 'Win'
                    break
        elif qty == 1:
            if l <= runner_sl + 1e-12:
                pnl_pts += runner_sl - entry
                fee_close(1)
                qty = 0
                res_final = 'Runner-BE' if abs(runner_sl - entry) < 1e-9 else 'Loss'
                break
            if h >= tp2 - 1e-12:
                pnl_pts += tp2 - entry
                fee_close(1)
                hit_tp2 = True
                qty = 0
                res_final = 'Win'
                break

    if qty > 0:
        tail = rth_1m[rth_1m.index.map(lambda ti: ti.date() == session_day and ti.time() < RTH_HI)]
        if tail.empty:
            return None
        eod = float(tail.iloc[-1]['close'])
        if qty == 2:
            pnl_pts += 2.0 * (eod - entry)
            fee_close(2)
        else:
            pnl_pts += eod - entry
            fee_close(1)
        res_final = 'EOD-Win' if pnl_pts > 0 else ('EOD-Loss' if pnl_pts < 0 else 'EOD-Flat')

    net_usd = round(pnl_pts * MULT - fees, 2)

    # TP-style banner: full TP2 / EOD wins — partial TP1-only counted if net positive as Win for WR alt
    if res_final == 'Runner-BE' and hit_tp1 and not hit_tp2:
        tp_style_label = 'Win' if net_usd > 0 else 'Loss'
    elif res_final == 'Win' and hit_tp2:
        tp_style_label = 'Win'
    elif res_final.startswith('EOD'):
        tp_style_label = res_final
    elif res_final == 'Loss':
        tp_style_label = 'Loss'
    else:
        tp_style_label = res_final

    return ScaleOutOut(
        date_iso=session_day.isoformat(),
        net_usd=net_usd,
        result_label=tp_style_label,
        hit_tp1=hit_tp1,
        hit_tp2=hit_tp2,
    )


def simulate_scale_out_3ct(
    rth_1m: pd.DataFrame,
    session_day: date,
    rh: float,
    rl: float,
    rv: float,
) -> ScaleOutOut | None:
    """3 MNQ: TP1 ×1, runners ×2 to TP2 with SL RH+tick after TP1 (same pessimistic rules as 2ct)."""
    if rv <= 1e-12:
        return None
    t_fill, entry_f = first_tier1_fill_ts(rth_1m, session_day, rh)
    if t_fill is None or entry_f is None:
        return None

    entry = float(entry_f)
    tp1 = rh + rv
    tp2 = rh + 2.0 * rv
    runner_sl = rh + TICK

    path = rth_1m[rth_1m.index >= t_fill].sort_index()
    qty = 3
    pnl_pts = 0.0
    fees = 0.0
    hit_tp1 = False
    hit_tp2 = False
    res_final = ''

    def fee_close(n: int = 1) -> None:
        nonlocal fees
        fees += FEE_RT * n

    for ts, bar in path.iterrows():
        if ts.time() >= EOD_CUTOFF:
            break
        h = float(bar['high'])
        l = float(bar['low'])

        if qty == 3:
            if l <= rl + 1e-12:
                pnl_pts += 3.0 * (rl - entry)
                fee_close(3)
                qty = 0
                res_final = 'Loss'
                break
            if h >= tp1 - 1e-12:
                pnl_pts += tp1 - entry
                fee_close(1)
                hit_tp1 = True
                qty = 2
                if l <= runner_sl + 1e-12:
                    pnl_pts += 2.0 * (runner_sl - entry)
                    fee_close(2)
                    qty = 0
                    res_final = 'Runner-BE' if abs(runner_sl - entry) < 1e-9 else 'Loss'
                    break
                if h >= tp2 - 1e-12:
                    pnl_pts += 2.0 * (tp2 - entry)
                    fee_close(2)
                    hit_tp2 = True
                    qty = 0
                    res_final = 'Win'
                    break
        elif qty == 2:
            if l <= runner_sl + 1e-12:
                pnl_pts += 2.0 * (runner_sl - entry)
                fee_close(2)
                qty = 0
                res_final = 'Runner-BE' if abs(runner_sl - entry) < 1e-9 else 'Loss'
                break
            if h >= tp2 - 1e-12:
                pnl_pts += 2.0 * (tp2 - entry)
                fee_close(2)
                hit_tp2 = True
                qty = 0
                res_final = 'Win'
                break

    if qty > 0:
        tail = rth_1m[rth_1m.index.map(lambda ti: ti.date() == session_day and ti.time() < RTH_HI)]
        if tail.empty:
            return None
        eod = float(tail.iloc[-1]['close'])
        if qty == 3:
            pnl_pts += 3.0 * (eod - entry)
            fee_close(3)
        else:
            pnl_pts += 2.0 * (eod - entry)
            fee_close(2)
        res_final = 'EOD-Win' if pnl_pts > 0 else ('EOD-Loss' if pnl_pts < 0 else 'EOD-Flat')

    net_usd = round(pnl_pts * MULT - fees, 2)

    if res_final == 'Runner-BE' and hit_tp1 and not hit_tp2:
        tp_style_label = 'Win' if net_usd > 0 else 'Loss'
    elif res_final == 'Win' and hit_tp2:
        tp_style_label = 'Win'
    elif res_final.startswith('EOD'):
        tp_style_label = res_final
    elif res_final == 'Loss':
        tp_style_label = 'Loss'
    else:
        tp_style_label = res_final

    return ScaleOutOut(
        date_iso=session_day.isoformat(),
        net_usd=net_usd,
        result_label=tp_style_label,
        hit_tp1=hit_tp1,
        hit_tp2=hit_tp2,
    )


def csv_equity_stats(legs: pd.DataFrame) -> dict:
    net = legs['Net_$'].astype(float)
    tp = legs['Result'].astype(str).isin(('Win', 'EOD-Win'))
    cum = net.cumsum()
    dd = float((cum - cum.cummax()).min())
    by_day = legs.groupby(pd.to_datetime(legs['Date']).dt.date)['Net_$'].sum().sort_index()
    dd_d = float((by_day.cumsum() - by_day.cummax()).min())
    return {
        'n': len(legs),
        'sum_net': float(net.sum()),
        'wr_tp': float(tp.mean() * 100),
        'wr_net_pos': float((net > 0).mean() * 100),
        'max_dd_leg': dd,
        'max_dd_day': dd_d,
        'label': '',
    }


def stats_from_rows(rows: list, *, label: str) -> dict:
    if not rows:
        return {
            'n': 0,
            'sum_net': 0.0,
            'wr_tp': float('nan'),
            'wr_net_pos': float('nan'),
            'max_dd_leg': 0.0,
            'max_dd_day': 0.0,
            'label': label,
        }
    df = pd.DataFrame(
        [{'d': r.date_iso, 'net': r.net_usd, 'lab': r.result_label} for r in rows]
    )
    tp = df['lab'].isin(('Win', 'EOD-Win'))
    cum = df['net'].cumsum()
    dd = float((cum - cum.cummax()).min())
    by_day = df.groupby('d')['net'].sum().sort_index()
    dd_d = float((by_day.cumsum() - by_day.cummax()).min())
    return {
        'n': len(df),
        'sum_net': float(df['net'].sum()),
        'wr_tp': float(tp.mean() * 100),
        'wr_net_pos': float((df['net'] > 0).mean() * 100),
        'max_dd_leg': dd,
        'max_dd_day': dd_d,
        'label': label,
    }


def print_block(title: str, st: dict) -> None:
    print(f'\n=== {title} ===')
    print(f"  {st['label']}")
    print(f"  Sessions: {st['n']}")
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
        print('Missing DBN, stops CSV, or 1m.', file=sys.stderr)
        return 1

    daily = load_mnq_front_daily(args.daily_dbn)
    daily.index = pd.to_datetime(daily.index)
    monthly = monthly_high_low(daily)
    pm_h, pm_l = prior_month_levels_series(daily, monthly)

    legs = qualify_v2b_m_legs(args.stops_csv, daily, pm_h, pm_l, include_hemisphere=False)
    if legs.empty:
        print('No qualified legs.', file=sys.stderr)
        return 1

    csv_st = csv_equity_stats(legs)
    csv_st['label'] = 'Historical tier‑1 CSV (v2b_m filtered Long legs)'

    need_dates = set(pd.to_datetime(legs['Date']).dt.date.unique())
    raw = ann.load_1m_for_dates(str(args.m1), min(need_dates), max(need_dates), need_dates)
    raw = ann.pick_front_month_day(raw)
    raw = raw.set_index(pd.DatetimeIndex(pd.to_datetime(raw['ts_event']))).sort_index()
    gby = {
        d: g for d, g in raw.groupby(pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False)
    }

    rows_b: list[BaselineOut] = []
    rows_so: list[ScaleOutOut] = []
    rows_so3: list[ScaleOutOut] = []
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

        b = simulate_baseline_1ct(rth, d, rh, rl, rv)
        so = simulate_scale_out_2ct(rth, d, rh, rl, rv)
        so3 = simulate_scale_out_3ct(rth, d, rh, rl, rv)
        if b is None or so is None or so3 is None:
            continue

        rows_b.append(b)
        rows_so.append(so)
        rows_so3.append(so3)
        export_rows.append(
            {
                'Date': d.isoformat(),
                'Symbol': str(q.get('Symbol', '')),
                'baseline_1ct_Net_$': b.net_usd,
                'baseline_Result': b.result_label,
                'scaleout_2ct_Net_$': so.net_usd,
                'scaleout_Result': so.result_label,
                'scaleout_3ct_Net_$': so3.net_usd,
                'scaleout_3ct_Result': so3.result_label,
                'hit_TP1_partial': so.hit_tp1,
                'hit_TP2_runner': so.hit_tp2,
                'hit_TP1_partial_3ct': so3.hit_tp1,
                'hit_TP2_runner_3ct': so3.hit_tp2,
                'bias_bucket': q['bias_bucket'],
                'geom_tag': q['geom_tag'],
                'EPS_IDX_PT': EPS_IDX_PT,
            }
        )

    st_b = stats_from_rows(
        rows_b,
        label='Sim baseline: 1 MNQ, TP RH+R, SL RL',
    )
    st_so = stats_from_rows(
        rows_so,
        label='v2b_m_so: 2 MNQ, TP1 RH+R (×1), runner SL RH+tick, TP2 RH+2R',
    )
    st_so3 = stats_from_rows(
        rows_so3,
        label='v2b_m_so: 3 MNQ, TP1 RH+R (×1), runners ×2 SL RH+tick, TP2 RH+2R',
    )

    print(f'Qualified v2b_m sessions: {len(legs)}')
    print(f'Sessions with tier‑1 sim fill: {len(rows_b)}')
    print(
        f'EPS_IDX_PT={EPS_IDX_PT}  mult={MULT} USD/pt  fee_rt={FEE_RT} USD per MNQ round-trip'
    )

    print_block('Reference — CSV book', csv_st)
    print_block('Baseline — sim 1 contract', st_b)
    print_block('Scale-out — sim 2 contracts', st_so)
    print_block('Scale-out — sim 3 contracts (1 @ TP1, 2 @ TP2)', st_so3)

    def eff(st: dict) -> float:
        dd = abs(st['max_dd_leg']) or 1e-12
        return st['sum_net'] / dd

    print('\nRisk efficiency (same leg ordering; Σ Net_$ / |max DD leg|):')
    print(f'  Baseline 1ct: {eff(st_b):.3f}')
    print(f'  Scale-out 2ct: {eff(st_so):.3f}')
    print(f'  Scale-out 3ct: {eff(st_so3):.3f}')

    n_tp2 = sum(1 for r in rows_so if r.hit_tp2)
    n_tp1 = sum(1 for r in rows_so if r.hit_tp1)
    print(f'\nScale-out 2ct: TP1 hit (≥1 lot): {n_tp1}/{len(rows_so)}  |  TP2 runner hit: {n_tp2}/{len(rows_so)}')
    n_tp2_3 = sum(1 for r in rows_so3 if r.hit_tp2)
    n_tp1_3 = sum(1 for r in rows_so3 if r.hit_tp1)
    print(
        f'Scale-out 3ct: TP1 hit (≥1 lot): {n_tp1_3}/{len(rows_so3)}  |  TP2 runners hit: {n_tp2_3}/{len(rows_so3)}'
    )

    if args.export_csv:
        pd.DataFrame(export_rows).to_csv(args.export_csv, index=False)
        print(f'\nWrote {args.export_csv}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())