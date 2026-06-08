#!/usr/bin/env python3
"""
v2e grounding: yearly/monthly P/L, drawdown, win rate, R:R, min account 3x rule,
and stop-width sweep. Uses 1m sim with optional limit offset (realistic front-of-queue
limits: short 1 tick below LdnH, long 1 tick above LdnL).

Run:  python3 v2e_grounding_report.py
     python3 v2e_grounding_report.py --limit-offset 1 --sl-ticks 5
"""
import argparse
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
    london_0200_0930_hilo,
    rth_1m,
    simulate_long,
    simulate_short,
)
sys.path.insert(0, str(POTIONS / 'scripts'))
import annotate_mnq_v2b_range_context as ann  # noqa: E402

M1 = POTIONS / 'mnq' / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'
DEFAULT_V2E_CSV = V2E_ROOT / 'data' / 'mnq_v2e_per_leg.csv'


def max_drawdown_window_from_leg_table(leg: pd.DataFrame) -> dict:
    """
    `leg` has columns `Date`, `pnl`. Rows are **in chronological sim / CSV order**
    (e.g. two same-calendar dates stay in file order; do not sort by date only).

    Returns max **peak-to-trough** drawdown on cumulative equity, and the **leg span**
    from the leg *after* the high-water mark through the trough (the cluster of trades
    that realize that drawdown).
    """
    m = leg[np.isfinite(leg['pnl'])].copy()
    if m.empty:
        return {
            'mdd_usd': 0.0, 'n_legs_in_equity': 0, 'cluster_legs': 0, 'cluster_pnl': 0.0,
            'date_at_peak_leg': None, 'date_at_trough_leg': None, 'trough_leg_iloc': -1,
        }
    pnl = m['pnl'].to_numpy(dtype=np.float64)
    eq = np.cumsum(pnl)
    n = len(eq)
    if n == 0:
        return {
            'mdd_usd': 0.0, 'n_legs_in_equity': 0, 'cluster_legs': 0, 'cluster_pnl': 0.0,
            'date_at_peak_leg': None, 'date_at_trough_leg': None, 'trough_leg_iloc': -1,
        }
    rm = np.maximum.accumulate(eq)
    dd = eq - rm
    t = int(np.argmin(dd))
    mdd = float(dd[t])
    pre = eq[0 : t + 1]
    peak_val = float(pre.max())
    w = np.where(np.isclose(pre, peak_val))[0]
    pidx = int(w[-1])
    cluster_pnl = float(pnl[pidx + 1 : t + 1].sum()) if t > pidx else 0.0
    clen = t - pidx
    d_peak = m['Date'].iloc[pidx] if pidx is not None else m['Date'].iloc[0]
    d_trough = m['Date'].iloc[t]
    return {
        'mdd_usd': mdd,
        'n_legs_in_equity': n,
        'cluster_legs': clen,
        'cluster_pnl': cluster_pnl,
        'date_at_peak_leg': str(d_peak),
        'date_at_trough_leg': str(d_trough),
        'trough_leg_iloc': t,
        'peak_leg_iloc': pidx,
    }


def load_gby(annotated: Path):
    df = pd.read_csv(annotated)
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    need = set(df['Date'].unique())
    tmin, tmax = min(need), max(need)
    print(f'Loading 1m ({len(need)} days)…', flush=True)
    raw = ann.load_1m_for_dates(str(M1), tmin, tmax, need)
    raw = ann.pick_front_month_day(raw)
    raw = raw.set_index('ts_event').sort_index()
    gby = {d: g for d, g in raw.groupby(
        pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False
    )}
    return df, gby


def run_legs(
    df, gby, sl_points: float, limit_offset: int, sl_mode: str = 'london_range',
) -> pd.DataFrame:
    out = []
    for _, r in df.iterrows():
        d, dr = r['Date'], r['Trade_Direction']
        day = gby.get(d)
        pnl, st, fstop = np.nan, 'no_data', 0
        if day is not None and len(day):
            rth = rth_1m(day)
            ldn_h, ldn_l = london_0200_0930_hilo(day)
            if dr == 'Short':
                s = simulate_short(
                    rth, ldn_h, ldn_l, sl_points,
                    limit_offset_ticks=limit_offset,
                    day_1m=day,
                    sl_mode=sl_mode,
                )
            else:
                s = simulate_long(
                    rth, ldn_h, ldn_l, sl_points,
                    limit_offset_ticks=limit_offset,
                    day_1m=day,
                    sl_mode=sl_mode,
                )
            pnl = s.pnl_dollars
            st = s.reason
            fstop = 1 if s.n_stop >= N_CONTRACTS else 0
        out.append(
            {
                'Date': d,
                'Direction': dr,
                'pnl': pnl,
                'status': st,
                'full_stop': fstop,
            }
        )
    return pd.DataFrame(out)


def max_drawdown_usd(pnl: np.ndarray) -> float:
    eq = np.cumsum(pnl)
    run_max = np.maximum.accumulate(eq)
    dd = eq - run_max
    return float(np.min(dd))  # negative


def worst_consecutive_loss_streak_sums(pnl: np.ndarray) -> float:
    """Most negative sum of a contiguous all-negative-PL segment."""
    w = 0.0
    run = 0.0
    for x in pnl:
        if x < 0:
            run += x
            w = min(w, run)
        else:
            run = 0.0
    return w


def max_consec_loss_count(pnl: np.ndarray) -> int:
    m = 0
    c = 0
    for x in pnl:
        if x < 0:
            c += 1
            m = max(m, c)
        else:
            c = 0
    return m


def print_report(leg: pd.DataFrame, title: str):
    leg = leg[np.isfinite(leg['pnl'])].copy()
    pnl = leg['pnl'].values
    n = len(pnl)
    if n == 0:
        print(f'\n{title}\n  No finite-P/L legs (all no_data?).\n')
        return
    leg = leg.copy()
    leg['ym'] = pd.to_datetime(leg['Date'].astype(str)).dt.to_period('M')
    leg['y'] = pd.to_datetime(leg['Date'].astype(str)).dt.year

    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    z = pnl[pnl == 0]
    gw, gl = wins.sum(), losses.sum()
    pf = (gw / abs(gl)) if gl < 0 else float('inf')
    avgw = wins.mean() if len(wins) else 0.0
    avgl = losses.mean() if len(losses) else 0.0
    medw = float(np.median(wins)) if len(wins) else 0.0
    medl = float(np.median(losses)) if len(losses) else 0.0
    rr = (avgw / abs(avgl)) if avgl < 0 else float('inf')
    rrm = (medw / abs(medl)) if medl < 0 else float('inf')

    wr_all = 100.0 * (len(wins) / n)
    n_act = len(wins) + len(losses)  # exclude flat as 'no result'
    wr_act = 100.0 * (len(wins) / n_act) if n_act else 0.0

    mdd = max_drawdown_usd(pnl)
    wcl = worst_consecutive_loss_streak_sums(pnl)
    mcons = max_consec_loss_count(pnl)
    # conservative margin: 3x worst of |MDD| and |losing-streak $|
    cap_a = 3.0 * abs(mdd)
    cap_b = 3.0 * abs(wcl)
    cap = max(cap_a, cap_b)

    print(f'\n{"="*72}')
    print(title)
    print(f'{"="*72}')
    print(f'Legs (v2b rows, long+short per day as listed):  {n}')
    print(f'Win / loss / flat:  {len(wins)} / {len(losses)} / {len(z)}')
    print(f'Win rate (legs with pnl>0 / all rows):  {wr_all:.1f}%')
    print(
        f'Win rate (wins / wins+losses, flat excl.):  {wr_act:.1f}%  '
        f'({len(wins)}/{n_act} legs)'
    )
    print(f'Gross $ profit (sum wins):  ${gw:,.2f}  |  gross loss:  ${gl:,.2f}')
    print(f'Profit factor (gross W / |gross L|):  {pf:.2f}' if gl < 0 else f'PF: N/A (no losing legs)')
    print(
        f'Average win: ${avgw:,.2f}  |  median win: ${medw:,.2f}  |  '
        f'avg |loss|: ${abs(avgl):,.2f}  |  median loss: ${medl:,.2f}'
    )
    print(
        f'R:R (mean W / |mean L|):  {rr:.2f}  |  (median W / |median L|):  {rrm:.2f}  '
        f'(medians are less skewed by huge winners)'
    )
    if len(losses):
        pct = np.percentile(losses, [10, 25, 50, 90, 99])
        print(
            f'Losing leg $ distribution:  p10 {pct[0]:,.1f}  p25 {pct[1]:,.1f}  p50 {pct[2]:,.1f}  '
            f'p90 {pct[3]:,.1f}  p99 {pct[4]:,.1f}'
        )

    wdw = max_drawdown_window_from_leg_table(leg[['Date', 'pnl']])
    print(
        f'\n--- Risk / account sizing ({N_CONTRACTS} MNQ, same row order as CSV) ---'
    )
    print(f'Peak-to-trough max drawdown (cumulative P/L, $):  {mdd:,.2f}')
    print(
        f"Worst drawdown cluster (legs after high-water through trough):  "
        f"{wdw['cluster_legs']} legs, sum P/L in window ${wdw['cluster_pnl']:,.2f}  |  "
        f"high-water leg date {wdw['date_at_peak_leg']}  →  trough {wdw['date_at_trough_leg']}"
    )
    print(
        f'Worst contiguous losing streak (sum of negative legs only, $):  {wcl:,.2f}  |  '
        f'max consecutive losing legs:  {mcons}'
    )
    print(
        f'Suggested min risk buffer: 3×|max DD| = ${cap_a:,.2f}  OR  3×|worst neg streak| = ${cap_b:,.2f}'
    )
    print(
        f'→ Rule-of-thumb “min notional” (use larger):  ${cap:,.2f}  '
        f'(3×|maxDD| or 3×|worst streak|; exclude CME margin & comms.)'
    )
    print(
        f'\n  Caveat: 1m OHLC, no comms/slippage; flat legs = no fill in model. '
        f'Equity DD can understate live risk. Forward paper first.'
    )

    ysum = leg.groupby('y', sort=True)['pnl'].sum()
    print(f'\n--- By calendar year (sum of leg P/L, $) ---')
    for y in ysum.index:
        m = (leg['y'] == y).sum()
        print(
            f'  {y}:  ${ysum[y]:>12,.2f}   legs={m}  '
            f'avg/leg ${ysum[y]/m:>8,.1f}'
        )

    msum = leg.groupby('ym', sort=True)['pnl'].sum()
    print(f'\n--- By month (sum $) — {len(msum)} months ---')
    for p, s in msum.items():
        print(f'  {p}:  ${s:>10,.2f}')

    print(
        f'\nTotal P/L:  ${pnl.sum():,.2f}  |  years spanned:  {int(ysum.index.min())}–{int(ysum.index.max())}  '
        f'({len(ysum)} years)'
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--annotated', type=Path, default=ANNOTATED)
    ap.add_argument(
        '--from-csv',
        type=Path,
        default=None,
        help='If set, skip 1m sim: read Date + v2e_pnl_5m from this file (e.g. mnq_v2e_per_leg.csv).',
    )
    ap.add_argument(
        '--sl-mode', choices=['london_range', 'fixed'], default='london_range',
        help='Stop width: Ldn range (default) or fixed --sl-points',
    )
    ap.add_argument(
        '--sl-points', type=float, default=30.0,
        help='Stop width in index points when --sl-mode fixed',
    )
    ap.add_argument('--limit-offset', type=int, default=0)
    ap.add_argument(
        '--sweep',
        type=float,
        nargs='+',
        default=None,
        metavar='PTS',
        help='Optional: re-run with several SL widths in **index points** (e.g. 10 15 20 30).',
    )
    args = ap.parse_args()

    if args.from_csv is not None:
        p = Path(args.from_csv)
        if not p.is_file():
            print(f'Not found: {p}', file=sys.stderr)
            return 1
        raw = pd.read_csv(p)
        if 'v2e_pnl_5m' not in raw.columns or 'Date' not in raw.columns:
            print('CSV needs Date, v2e_pnl_5m', file=sys.stderr)
            return 1
        leg = raw[['Date', 'v2e_pnl_5m']].rename(columns={'v2e_pnl_5m': 'pnl'})
        n = len(leg)
        st = f'v2e grounding (from {p.name}) | {n} rows | P/L = v2e_pnl_5m column (no 1m re-sim)'
        print_report(leg, st)
        return 0

    df, gby = load_gby(args.annotated)
    n = len(df)
    sl_desc = (
        f'Ldn range (H−L) idx pt, mode={args.sl_mode}'
        if args.sl_mode == 'london_range'
        else f'{args.sl_points} index pts, mode=fixed'
    )
    st = (
        f'v2e grounding (causal) | {n} legs | {sl_desc} | '
        f'limit offset = {args.limit_offset} tick (short below H, long above L)'
    )

    leg = run_legs(df, gby, args.sl_points, args.limit_offset, sl_mode=args.sl_mode)
    print_report(leg, st)

    if args.sweep:
        print(f'\n{"="*72}')
        print('Stop-width sweep (same limit offset) — total $ & win rate (all legs) & profit factor')
        print(f'{"="*72}')
        print(f'{"SL pts":<10} {"Total $":>14} {"WR% all":>10} {"PF":>8}')
        for sl in sorted(args.sweep):
            lg = run_legs(df, gby, sl, args.limit_offset, sl_mode='fixed')
            p = lg['pnl'].values
            p = p[np.isfinite(p)]
            gw = p[p > 0].sum()
            gl = p[p < 0].sum()
            pf = gw / abs(gl) if gl < 0 else 999.0
            wr = 100.0 * (p > 0).sum() / len(p) if len(p) else 0.0
            print(
                f'{sl:<10} {p.sum():>14,.2f} {wr:>9.1f}% {pf:>8.2f}'
            )
        print(
            f'\n( wider stop = $ risk to stop is larger; PF often falls as you pay for insurance )'
        )

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
