#!/usr/bin/env python3
"""
v2e — Causal 02:00–09:30 London box, 2× MNQ

* **Default (`--side-rule pw_fade`)** — **Prior week** Mon–Fri H/L (daily) **near** the
  London box: short when |PWH−LdnH| ≤ prox, long when |PWL−LdnL| ≤ prox (if both,
  tighter |diff| wins). **Skip** the day if neither is near. **SL** = fixed 20 index
  pts; **targets** = Ldn mid (1 lot) + opposite Ldn corner (1 lot). No ORB/v2b side
  logic.
* **Alt** — `first_rth_touch` (first RTH touch of LdnH vs LdnL), legacy `v2b_row`,
  or `v2b_replay_1m`.
* **SL (non-pw_fade)** — `--sl-mode london_range` (LdnH−LdnL) or `fixed` + `--sl-points`.

`no_data` when there is no 1m for that date.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

V2E_ROOT = Path(__file__).resolve().parent.parent
POTIONS = V2E_ROOT.parent.parent
SIM_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SIM_DIR))
from sim_london_limit_scaleout import (  # noqa: E402
    ANNOTATED,
    N_CONTRACTS,
    first_rth_touch_side,
    london_0200_0930_hilo,
    rth_1m,
    simulate_long,
    simulate_short,
)
from prior_week_levels import (  # noqa: E402
    DEFAULT_DAILY_DBN,
    load_mnq_front_daily,
    pick_pw_fade_side,
    prior_week_hilo,
)
from side_v2b_replay_1m import (  # noqa: E402
    rth_slice_strictly_after_oco_bar,
    side_v2b_replay_1m,
)
from v2e_grounding_report import (  # noqa: E402
    max_drawdown_usd,
    max_drawdown_window_from_leg_table,
)
sys.path.insert(0, str(POTIONS / 'scripts'))
import annotate_mnq_v2b_range_context as ann  # noqa: E402

NLOT = N_CONTRACTS
M1 = POTIONS / 'mnq' / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'
DEFAULT_V2E_OUT = V2E_ROOT / 'data' / 'mnq_v2e_per_leg.csv'


def _sl_pts_column(s, st: str, args) -> float:
    """Index-point stop **width** used for that row (range width or fixed)."""
    if getattr(args, 'side_rule', None) == 'pw_fade':
        return float(getattr(args, 'pw_sl_pts', 20.0)) if st == 'ok' or (
            st == 'no_fill' and not (np.isnan(s.london_h) or np.isnan(s.london_l))
        ) else np.nan
    sm = getattr(args, 'sl_mode', 'london_range')
    if st == 'ok':
        if sm == 'london_range':
            return float(s.london_h) - float(s.london_l)
        return float(args.sl_points)
    if st == 'no_fill' and not (np.isnan(s.london_h) or np.isnan(s.london_l)):
        if sm == 'london_range':
            return float(s.london_h) - float(s.london_l)
        return float(args.sl_points)
    return np.nan


def _one_row(
    d,
    dr: str,
    s,
    st: str,
    args,
    v2b_net: float,
    side_rule: str,
    v2b_first: str = '',
    side_match: str = '',
    v2b_oco_fill_ts=None,
):
    vts = np.nan if v2b_oco_fill_ts is None else v2b_oco_fill_ts
    rel_last = (
        (dr == 'Short' and s.extreme_h_on_last_preopen_1m)
        or (dr == 'Long' and s.extreme_l_on_last_preopen_1m)
    )
    entry_first = st == 'ok' and s.entry_rth_idx == 0
    tight_930 = st == 'ok' and rel_last and entry_first
    return {
        'Date': d,
        'Direction': dr,
        'v2e_pnl_5m': s.pnl_dollars,
        'status': st,
        'full_5c_stop': 1 if s.n_stop >= NLOT else 0,
        'v2b_Net': v2b_net,
        'ldn_0200_0930_h': s.london_h,
        'ldn_0200_0930_l': s.london_l,
        'ldn_mid': s.ldn_mid,
        'sl_mode': (
            'fixed' if getattr(args, 'side_rule', None) == 'pw_fade'
            else getattr(args, 'sl_mode', 'london_range')
        ),
        'sl_points': _sl_pts_column(s, st, args),
        'mfe_past_london_opposite_pts': s.mfe_past_opposite_london_pts,
        'extreme_h_on_last_preopen_1m': s.extreme_h_on_last_preopen_1m,
        'extreme_l_on_last_preopen_1m': s.extreme_l_on_last_preopen_1m,
        'relevant_extreme_last_preopen_1m': rel_last,
        'entry_first_rth_1m': entry_first if st == 'ok' else False,
        'tight_930_entry_risk': tight_930,
        'side_rule': side_rule,
        'v2b_first_row_direction': v2b_first,
        'side_match_v2b_first': side_match,
        'v2b_oco_fill_ts': vts,
        'pwh': np.nan,
        'pwl': np.nan,
        'pwh_ldn_diff': np.nan,
        'pwl_ldn_diff': np.nan,
    }


def _empty_v2b_row(
    d, dr, status, v2b_net, args, side_rule, v2b_first='', side_match='',
    tight=False, rel_h=False, rel_l=False, entry_first_rth=False,
):
    return {
        'Date': d,
        'Direction': dr,
        'v2e_pnl_5m': np.nan,
        'status': status,
        'full_5c_stop': 0,
        'v2b_Net': v2b_net,
        'ldn_0200_0930_h': np.nan,
        'ldn_0200_0930_l': np.nan,
        'ldn_mid': np.nan,
        'sl_mode': (
            'fixed' if getattr(args, 'side_rule', None) == 'pw_fade'
            else getattr(args, 'sl_mode', 'london_range')
        ),
        'sl_points': np.nan,
        'mfe_past_london_opposite_pts': np.nan,
        'extreme_h_on_last_preopen_1m': rel_h,
        'extreme_l_on_last_preopen_1m': rel_l,
        'relevant_extreme_last_preopen_1m': tight,
        'entry_first_rth_1m': entry_first_rth,
        'tight_930_entry_risk': tight and entry_first_rth,
        'side_rule': side_rule,
        'v2b_first_row_direction': v2b_first,
        'side_match_v2b_first': side_match,
        'v2b_oco_fill_ts': np.nan,
        'pwh': np.nan,
        'pwl': np.nan,
        'pwh_ldn_diff': np.nan,
        'pwl_ldn_diff': np.nan,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        '--sl-mode',
        type=str,
        choices=['london_range', 'fixed'],
        default='london_range',
        help='Stop width: LdnH−LdnL (default) or fixed N index points (see --sl-points).',
    )
    ap.add_argument(
        '--sl-points',
        type=float,
        default=30.0,
        help='Stop width in index points when --sl-mode fixed; ignored for london_range',
    )
    ap.add_argument(
        '--limit-offset',
        type=int,
        default=0,
        help='0 = limit at box H/L. 1 = short 1 tick below H, long 1 tick above L',
    )
    ap.add_argument(
        '--side-rule',
        type=str,
        choices=['pw_fade', 'first_rth_touch', 'v2b_row', 'v2b_replay_1m'],
        default='pw_fade',
        help='Side: pw_fade (PWH/LdnH or PWL/LdnL proximity) | first_rth_touch | v2b_row | v2b_replay_1m.',
    )
    ap.add_argument(
        '--pw-prox-pts',
        type=float,
        default=8.0,
        help='pw_fade: max |PWH−LdnH| or |PWL−LdnL| to take a side; else skip day.',
    )
    ap.add_argument(
        '--pw-sl-pts',
        type=float,
        default=20.0,
        help='pw_fade: fixed stop width in index points (ignores --sl-mode).',
    )
    ap.add_argument(
        '--daily-dbn',
        type=Path,
        default=DEFAULT_DAILY_DBN,
        help='pw_fade: Databento MNQ ohlcv-1d for prior week H/L.',
    )
    ap.add_argument('--annotated', type=Path, default=ANNOTATED)
    ap.add_argument('--out', type=Path, default=DEFAULT_V2E_OUT)
    args = ap.parse_args()

    df = pd.read_csv(args.annotated)
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    need = set(df['Date'].unique())
    tmin, tmax = min(need), max(need)
    n_in_csv = len(df)
    n_ud = len(need)
    print(
        f'v2e (causal 02:00–09:30, side={args.side_rule}): '
        f'{n_in_csv} CSV rows, {n_ud} unique dates, 1m load...',
        flush=True,
    )
    raw = ann.load_1m_for_dates(str(M1), tmin, tmax, need)
    raw = ann.pick_front_month_day(raw)
    raw = raw.set_index('ts_event').sort_index()
    gby = {d: g for d, g in raw.groupby(
        pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False
    )}

    v2b_net_all = float(df['Net_$'].sum())
    v2b_nlot = v2b_net_all * float(NLOT)

    n_no_data = 0
    n_no_level = 0
    n_no_fill = 0
    n_no_first_touch = 0
    n_no_v2b_oco = 0
    n_no_rth_post = 0
    n_no_prior_week = 0
    n_no_pw_prox = 0
    n_full_stop = 0
    rows = []

    if args.side_rule == 'v2b_row':
        for _, r in df.iterrows():
            d, dr = r['Date'], r['Trade_Direction']
            v2b1 = r.get('Net_$', np.nan)
            day = gby.get(d)
            if day is None or len(day) == 0:
                n_no_data += 1
                rows.append(_empty_v2b_row(
                    d, dr, 'no_data', v2b1, args, 'v2b_row', dr, 'n/a',
                ))
                continue
            ldn_h, ldn_l = london_0200_0930_hilo(day)
            rth = rth_1m(day)
            if dr == 'Short':
                s = simulate_short(
                    rth, ldn_h, ldn_l, args.sl_points,
                    limit_offset_ticks=args.limit_offset, day_1m=day,
                    sl_mode=args.sl_mode,
                )
            else:
                s = simulate_long(
                    rth, ldn_h, ldn_l, args.sl_points,
                    limit_offset_ticks=args.limit_offset, day_1m=day,
                    sl_mode=args.sl_mode,
                )
            st = s.reason
            if st == 'no_level':
                n_no_level += 1
            elif st == 'no_fill':
                n_no_fill += 1
            if s.n_stop >= NLOT:
                n_full_stop += 1
            rows.append(_one_row(
                d, dr, s, st, args, v2b1, 'v2b_row', dr, 'True',
            ))
    elif args.side_rule == 'first_rth_touch':
        for d in sorted(need):
            r0 = df[df['Date'] == d].iloc[0]
            v2b1 = r0.get('Net_$', np.nan)
            v2b_d = r0['Trade_Direction']
            day = gby.get(d)
            if day is None or len(day) == 0:
                n_no_data += 1
                rows.append(_empty_v2b_row(
                    d, v2b_d, 'no_data', v2b1, args, 'first_rth_touch', v2b_d, 'n/a',
                ))
                continue
            ldn_h, ldn_l = london_0200_0930_hilo(day)
            rth = rth_1m(day)
            dr = first_rth_touch_side(
                rth, ldn_h, ldn_l, args.limit_offset,
            )
            if dr is None:
                n_no_first_touch += 1
                rows.append({
                    'Date': d,
                    'Direction': '-',
                    'v2e_pnl_5m': 0.0,
                    'status': 'no_first_rth_fill',
                    'full_5c_stop': 0,
                    'v2b_Net': v2b1,
                    'ldn_0200_0930_h': ldn_h,
                    'ldn_0200_0930_l': ldn_l,
                    'ldn_mid': (ldn_h + ldn_l) / 2.0,
                    'sl_mode': args.sl_mode,
                    'sl_points': (float(ldn_h) - float(ldn_l))
                    if args.sl_mode == 'london_range' else float(args.sl_points),
                    'mfe_past_london_opposite_pts': np.nan,
                    'extreme_h_on_last_preopen_1m': False,
                    'extreme_l_on_last_preopen_1m': False,
                    'relevant_extreme_last_preopen_1m': False,
                    'entry_first_rth_1m': False,
                    'tight_930_entry_risk': False,
                    'side_rule': 'first_rth_touch',
                    'v2b_first_row_direction': v2b_d,
                    'side_match_v2b_first': 'n/a',
                    'v2b_oco_fill_ts': np.nan,
                })
                continue
            if dr == 'Short':
                s = simulate_short(
                    rth, ldn_h, ldn_l, args.sl_points,
                    limit_offset_ticks=args.limit_offset, day_1m=day,
                    sl_mode=args.sl_mode,
                )
            else:
                s = simulate_long(
                    rth, ldn_h, ldn_l, args.sl_points,
                    limit_offset_ticks=args.limit_offset, day_1m=day,
                    sl_mode=args.sl_mode,
                )
            st = s.reason
            if st == 'no_level':
                n_no_level += 1
            elif st == 'no_fill':
                n_no_fill += 1
            if s.n_stop >= NLOT:
                n_full_stop += 1
            match = 'True' if dr == v2b_d else 'False'
            rows.append(_one_row(
                d, dr, s, st, args, v2b1, 'first_rth_touch', v2b_d, match,
            ))
    elif args.side_rule == 'v2b_replay_1m':
        for d in sorted(need):
            r0 = df[df['Date'] == d].iloc[0]
            v2b1 = r0.get('Net_$', np.nan)
            v2b_d = r0['Trade_Direction']
            day = gby.get(d)
            if day is None or len(day) == 0:
                n_no_data += 1
                rows.append(_empty_v2b_row(
                    d, v2b_d, 'no_data', v2b1, args, 'v2b_replay_1m', v2b_d, 'n/a',
                ))
                continue
            ldn_h, ldn_l = london_0200_0930_hilo(day)
            rth = rth_1m(day)
            rep = side_v2b_replay_1m(day)
            if rep is None:
                n_no_v2b_oco += 1
                rows.append({
                    'Date': d,
                    'Direction': '-',
                    'v2e_pnl_5m': 0.0,
                    'status': 'no_v2b_oco_fill',
                    'full_5c_stop': 0,
                    'v2b_Net': v2b1,
                    'ldn_0200_0930_h': ldn_h,
                    'ldn_0200_0930_l': ldn_l,
                    'ldn_mid': (float(ldn_h) + float(ldn_l)) / 2.0,
                    'sl_mode': args.sl_mode,
                    'sl_points': (float(ldn_h) - float(ldn_l))
                    if args.sl_mode == 'london_range' else float(args.sl_points),
                    'mfe_past_london_opposite_pts': np.nan,
                    'extreme_h_on_last_preopen_1m': False,
                    'extreme_l_on_last_preopen_1m': False,
                    'relevant_extreme_last_preopen_1m': False,
                    'entry_first_rth_1m': False,
                    'tight_930_entry_risk': False,
                    'side_rule': 'v2b_replay_1m',
                    'v2b_first_row_direction': v2b_d,
                    'side_match_v2b_first': 'n/a',
                    'v2b_oco_fill_ts': np.nan,
                })
                continue
            v2_side, t_fill, _orh, _orl, _orv = rep
            dr = v2_side
            rth_post = rth_slice_strictly_after_oco_bar(rth, t_fill)
            if rth_post is None or rth_post.empty:
                n_no_rth_post += 1
                rows.append({
                    'Date': d,
                    'Direction': dr,
                    'v2e_pnl_5m': 0.0,
                    'status': 'no_rth_post_v2b',
                    'full_5c_stop': 0,
                    'v2b_Net': v2b1,
                    'ldn_0200_0930_h': ldn_h,
                    'ldn_0200_0930_l': ldn_l,
                    'ldn_mid': (ldn_h + ldn_l) / 2.0,
                    'sl_mode': args.sl_mode,
                    'sl_points': (float(ldn_h) - float(ldn_l))
                    if args.sl_mode == 'london_range' else float(args.sl_points),
                    'mfe_past_london_opposite_pts': np.nan,
                    'extreme_h_on_last_preopen_1m': False,
                    'extreme_l_on_last_preopen_1m': False,
                    'relevant_extreme_last_preopen_1m': False,
                    'entry_first_rth_1m': False,
                    'tight_930_entry_risk': False,
                    'side_rule': 'v2b_replay_1m',
                    'v2b_first_row_direction': v2b_d,
                    'side_match_v2b_first': 'True' if dr == v2b_d else 'False',
                    'v2b_oco_fill_ts': t_fill,
                })
                continue
            if dr == 'Short':
                s = simulate_short(
                    rth_post, ldn_h, ldn_l, args.sl_points,
                    limit_offset_ticks=args.limit_offset, day_1m=day,
                    sl_mode=args.sl_mode,
                )
            else:
                s = simulate_long(
                    rth_post, ldn_h, ldn_l, args.sl_points,
                    limit_offset_ticks=args.limit_offset, day_1m=day,
                    sl_mode=args.sl_mode,
                )
            st = s.reason
            if st == 'no_level':
                n_no_level += 1
            elif st == 'no_fill':
                n_no_fill += 1
            if s.n_stop >= NLOT:
                n_full_stop += 1
            m_side = 'True' if dr == v2b_d else 'False'
            rows.append(_one_row(
                d, dr, s, st, args, v2b1, 'v2b_replay_1m', v2b_d, m_side,
                v2b_oco_fill_ts=t_fill,
            ))
    elif args.side_rule == 'pw_fade':
        print(
            f'Load daily (PWH/PWL): {args.daily_dbn} ...',
            flush=True,
        )
        daily_mnq = load_mnq_front_daily(args.daily_dbn)
        sl_f = float(args.pw_sl_pts)
        prox = float(args.pw_prox_pts)
        for d in sorted(need):
            r0 = df[df['Date'] == d].iloc[0]
            v2b1 = r0.get('Net_$', np.nan)
            v2b_d = r0['Trade_Direction']
            day = gby.get(d)
            if day is None or len(day) == 0:
                n_no_data += 1
                rows.append(
                    _empty_v2b_row(
                        d, v2b_d, 'no_data', v2b1, args, 'pw_fade', v2b_d, 'n/a',
                    )
                )
                continue
            ldn_h, ldn_l = london_0200_0930_hilo(day)
            rth = rth_1m(day)
            if not (np.isfinite(ldn_h) and np.isfinite(ldn_l)):
                n_no_level += 1
                p0, pl0 = prior_week_hilo(daily_mnq, d)
                er = _empty_v2b_row(
                    d, v2b_d, 'no_level', v2b1, args, 'pw_fade', v2b_d, 'n/a',
                )
                if p0 is not None and pl0 is not None:
                    er['pwh'] = p0
                    er['pwl'] = pl0
                rows.append(er)
                continue
            pwh, pwl = prior_week_hilo(daily_mnq, d)
            if pwh is None or pwl is None:
                n_no_prior_week += 1
                r = _empty_v2b_row(
                    d, v2b_d, 'no_prior_week', v2b1, args, 'pw_fade', v2b_d, 'n/a',
                )
                r['ldn_0200_0930_h'] = ldn_h
                r['ldn_0200_0930_l'] = ldn_l
                r['ldn_mid'] = (
                    (float(ldn_h) + float(ldn_l)) / 2.0
                    if np.isfinite(ldn_h) and np.isfinite(ldn_l)
                    else np.nan
                )
                r['v2e_pnl_5m'] = np.nan
                rows.append(r)
                continue
            dr, d_h, d_l = pick_pw_fade_side(
                pwh, pwl, ldn_h, ldn_l, prox,
            )
            if dr is None:
                n_no_pw_prox += 1
                rows.append(
                    {
                        'Date': d,
                        'Direction': '-',
                        'v2e_pnl_5m': 0.0,
                        'status': 'no_pw_london_prox',
                        'full_5c_stop': 0,
                        'v2b_Net': v2b1,
                        'ldn_0200_0930_h': ldn_h,
                        'ldn_0200_0930_l': ldn_l,
                        'ldn_mid': (ldn_h + ldn_l) / 2.0,
                        'sl_mode': 'fixed',
                        'sl_points': sl_f,
                        'mfe_past_london_opposite_pts': np.nan,
                        'extreme_h_on_last_preopen_1m': False,
                        'extreme_l_on_last_preopen_1m': False,
                        'relevant_extreme_last_preopen_1m': False,
                        'entry_first_rth_1m': False,
                        'tight_930_entry_risk': False,
                        'side_rule': 'pw_fade',
                        'v2b_first_row_direction': v2b_d,
                        'side_match_v2b_first': 'n/a',
                        'v2b_oco_fill_ts': np.nan,
                        'pwh': pwh,
                        'pwl': pwl,
                        'pwh_ldn_diff': d_h,
                        'pwl_ldn_diff': d_l,
                    }
                )
                continue
            if dr == 'Short':
                s = simulate_short(
                    rth, ldn_h, ldn_l, sl_f,
                    limit_offset_ticks=args.limit_offset, day_1m=day,
                    sl_mode='fixed',
                )
            else:
                s = simulate_long(
                    rth, ldn_h, ldn_l, sl_f,
                    limit_offset_ticks=args.limit_offset, day_1m=day,
                    sl_mode='fixed',
                )
            st = s.reason
            if st == 'no_level':
                n_no_level += 1
            elif st == 'no_fill':
                n_no_fill += 1
            if s.n_stop >= NLOT:
                n_full_stop += 1
            one = _one_row(
                d, dr, s, st, args, v2b1, 'pw_fade', v2b_d, 'n/a',
            )
            one['pwh'] = pwh
            one['pwl'] = pwl
            one['pwh_ldn_diff'] = d_h
            one['pwl_ldn_diff'] = d_l
            rows.append(one)
    else:
        print(f'Unknown --side-rule: {args.side_rule}', file=sys.stderr)
        return 2

    for r in rows:
        for k in ('pwh', 'pwl', 'pwh_ldn_diff', 'pwl_ldn_diff'):
            r.setdefault(k, np.nan)

    out_df = pd.DataFrame(rows)
    pnl_sum = out_df['v2e_pnl_5m'].sum(skipna=True)
    n_tight = int(out_df['tight_930_entry_risk'].sum()) if 'tight_930_entry_risk' in out_df.columns else 0
    ok = out_df['status'] == 'ok'
    n_ok = int(ok.sum())
    n_win = int((ok & (out_df['v2e_pnl_5m'] > 0)).sum())
    win_rate = (n_win / n_ok) if n_ok else float('nan')
    n_sess = n_ud - n_no_data
    pct_tight_ok = (100.0 * n_tight / n_ok) if n_ok else 0.0
    pct_tight_sess = (100.0 * n_tight / n_sess) if n_sess else 0.0

    v2b_ref_sum = 0.0
    for d in need:
        v2b_ref_sum += float(df[df['Date'] == d].iloc[0].get('Net_$', 0) or 0.0)

    print('\n========== v2e — causal 02:00–09:30 London box ==========')
    if args.side_rule == 'pw_fade':
        sl_note = f"{args.pw_sl_pts:g} idx pt fixed (pw_fade); prox ≤{args.pw_prox_pts:g} for PWH/LdnH or PWL/LdnL"
    else:
        sl_note = (
            f"Ldn range (H−L) idx pt, mode={args.sl_mode}"
            if args.sl_mode == 'london_range'
            else f"{args.sl_points} idx pt fixed, mode={args.sl_mode}"
        )
    print(
        f"  Side rule: {args.side_rule}  |  SL: {sl_note}  |  "
        f"{NLOT} MNQ  |  limit offset: {args.limit_offset} tick(s)"
    )
    if args.side_rule == 'pw_fade':
        print(
            f'  Output rows: 1 per date  |  no prior week (daily):  {n_no_prior_week}  |  '
            f'no PW/Ldn proximity:  {n_no_pw_prox}  (trade only if |PWH−LdnH| or |PWL−LdnL| ≤ {args.pw_prox_pts:g})'
        )
    elif args.side_rule == 'first_rth_touch':
        print(
            f'  Output rows: 1 per unique date ({n_ud} dates in CSV)  |  '
            f'no_first_rth_fill (neither LdnH nor LdnL in RTH):  {n_no_first_touch}'
        )
    elif args.side_rule == 'v2b_replay_1m':
        print(
            f'  Output rows: 1 per unique date  |  no v2b OCO fill (1m replay):  {n_no_v2b_oco}  |  '
            f'no RTH bars after OCO bar:  {n_no_rth_post}'
        )
    else:
        print(f'  Output rows:  {len(out_df)}  (same as v2b leg rows)')

    print(f'  unique dates in CSV:  {n_ud}  |  no 1m / no_data:  {n_no_data}')
    print(f'  no Ldn box:  {n_no_level}  |  RTH no fill (for chosen side):  {n_no_fill}')
    print(f'  {NLOT}-contract full stop-outs:  {n_full_stop}')
    print(
        f'  tight_930 (9:29 sets relevant H/L for side + first RTH 1m is the fill):  {n_tight}  |  '
        f'{pct_tight_ok:.1f}% of ok rows  |  {pct_tight_sess:.1f}% of session dates with 1m'
    )

    print('\n  --- Cumulative $ (sum of non-NaN v2e_pnl_5m) ---')
    print(f'  v2b Net_$ (1 lot, all CSV rows):     {v2b_net_all:,.2f}')
    print(
        f'  v2b 1st row/day (1 lot, {n_ud} days, ref for first-touch list):  {v2b_ref_sum:,.2f}'
    )
    print(f'  v2b ×{NLOT} (all rows, notional):     {v2b_nlot:,.2f}')
    print(f'  v2e cumulative:                      {pnl_sum:,.2f}')
    print(
        f'\n  Win rate (status=ok, v2e_pnl>0):    {n_win} / {n_ok}  =  {win_rate:.1%}'
    )

    pnl_ser = out_df['v2e_pnl_5m'].to_numpy()
    mask = np.isfinite(pnl_ser)
    pnl_f = pnl_ser[mask]
    rdf = out_df.loc[mask, ['Date', 'v2e_pnl_5m']].rename(columns={'v2e_pnl_5m': 'pnl'})
    wdw = max_drawdown_window_from_leg_table(rdf) if not rdf.empty else {}
    mdd = max_drawdown_usd(pnl_f) if pnl_f.size else 0.0
    if rdf.size:
        print(
            f'\n  Max drawdown (cumulative, all rows with finite v2e P/L, output order):  {mdd:,.2f}'
        )
        print(
            f"  Drawdown window:  {wdw.get('cluster_legs', 0)} legs, "
            f"{wdw.get('date_at_peak_leg')} → {wdw.get('date_at_trough_leg')}  "
            f"(sum in window {wdw.get('cluster_pnl', 0):+,.0f} $)"
        )

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.out, index=False)
    print(f"\nWrote {args.out}")

    risk_path = Path(args.out).parent / 'v2e_risk_snapshot.json'
    snap = {
        'side_rule': args.side_rule,
        'sl_mode': 'fixed' if args.side_rule == 'pw_fade' else args.sl_mode,
        'sl_points': float(args.pw_sl_pts) if args.side_rule == 'pw_fade' else (
            float(args.sl_points) if args.sl_mode == 'fixed' else 'london_range'
        ),
        'pw_prox_pts': float(args.pw_prox_pts) if args.side_rule == 'pw_fade' else None,
        'n_contracts': NLOT,
        'scaleout': '1 @ Ldn mid, 1 @ opposite Ldn',
        'cumulative_pnl': float(pnl_sum),
        'n_ok': n_ok,
        'n_wins': n_win,
        'win_rate': float(win_rate) if n_ok else None,
        'max_drawdown_usd': mdd,
        'drawdown_window': wdw,
        'tight_930_count': n_tight,
        'tight_930_pct_of_ok': round(pct_tight_ok, 3),
        'tight_930_pct_of_sessions_1m': round(pct_tight_sess, 3),
    }
    with open(risk_path, 'w', encoding='utf-8') as f:
        json.dump(snap, f, indent=2)
    print(f"Wrote {risk_path}")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
