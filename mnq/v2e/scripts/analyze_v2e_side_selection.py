#!/usr/bin/env python3
"""
v2e side-selection stress test (same causal London sim, alternative rules).

- **Current** — each CSV row: P/L = sim for that row's Trade_Direction (v2b leg list).
- **First row per day** — file order, first time a calendar date appears: that row's
  direction only (one "live" choice per day).
- **All short / all long** — for each *unique* session date, add short-only or long-only
  sim (one hypothetical trade per day, not 1991 independent trials).
- **Both** — per date: P/L(short) + P/L(long) (two trades, opposite directions, same day).
- **Random** — 0.5 × (all_short + all_long) = 0.5 × **Both** (pick one side at random per day).
- **Hindsight** — per date: max(P/L(short), P/L(long)).

Matches the methodology in `v2e/README.md` (Side selection & edge attribution section).

Run:  python3 analyze_v2e_side_selection.py
      python3 analyze_v2e_side_selection.py --sl-points 30 --limit-offset 0
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

V2E_ROOT = Path(__file__).resolve().parent.parent
POTIONS = V2E_ROOT.parent.parent
SIM = Path(__file__).resolve().parent
sys.path.insert(0, str(SIM))
from sim_london_limit_scaleout import (  # noqa: E402
    ANNOTATED,
    london_0200_0930_hilo,
    rth_1m,
    simulate_long,
    simulate_short,
)
sys.path.insert(0, str(POTIONS / 'scripts'))
import annotate_mnq_v2b_range_context as ann  # noqa: E402

M1 = POTIONS / 'mnq' / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        '--sl-mode', choices=['london_range', 'fixed'], default='london_range',
        help='Stop width: LdnH−LdnL (default) or fixed --sl-points',
    )
    ap.add_argument('--sl-points', type=float, default=30.0, help='Used when --sl-mode fixed')
    ap.add_argument('--limit-offset', type=int, default=0)
    ap.add_argument('--annotated', type=Path, default=ANNOTATED)
    args = ap.parse_args()

    df = pd.read_csv(args.annotated)
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    need = set(df['Date'].unique())
    tmin, tmax = min(need), max(need)
    print(
        f'v2e side study: {len(df)} rows, {len(need)} unique dates, 1m load...',
        flush=True,
    )
    raw = ann.load_1m_for_dates(str(M1), tmin, tmax, need)
    raw = ann.pick_front_month_day(raw)
    raw = raw.set_index('ts_event').sort_index()
    gby = {d: g for d, g in raw.groupby(
        pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False
    )}

    day_pl: dict = {}
    for d in sorted(need):
        day = gby.get(d)
        if day is None or len(day) == 0:
            continue
        ldn_h, ldn_l = london_0200_0930_hilo(day)
        rth = rth_1m(day)
        s_s = simulate_short(
            rth, ldn_h, ldn_l, args.sl_points,
            limit_offset_ticks=args.limit_offset, day_1m=day,
            sl_mode=args.sl_mode,
        )
        s_l = simulate_long(
            rth, ldn_h, ldn_l, args.sl_points,
            limit_offset_ticks=args.limit_offset, day_1m=day,
            sl_mode=args.sl_mode,
        )
        day_pl[d] = (float(s_s.pnl_dollars), float(s_l.pnl_dollars))

    sl_pts, off = args.sl_points, args.limit_offset

    cur = 0.0
    for _, r in df.iterrows():
        d = r['Date']
        if d not in day_pl:
            continue
        ps, pl = day_pl[d]
        cur += ps if r['Trade_Direction'] == 'Short' else pl

    first_sum = 0.0
    seen: set = set()
    for _, r in df.iterrows():
        d = r['Date']
        if d in seen or d not in day_pl:
            continue
        seen.add(d)
        ps, pl = day_pl[d]
        first_sum += ps if r['Trade_Direction'] == 'Short' else pl

    all_s = sum(p[0] for p in day_pl.values())
    all_l = sum(p[1] for p in day_pl.values())
    both = all_s + all_l
    rnd = 0.5 * both
    hind = sum(max(p[0], p[1]) for p in day_pl.values())

    print('\n========== v2e side selection (5 MNQ, causal Ldn box) ==========')
    print(f"  SL = {sl_pts} index pts  |  limit offset = {off} tick(s)")
    print(f"  Session dates with 1m:  {len(day_pl)}")
    print(f"\n  Current (v2b Trade_Direction per row):     ${cur:,.2f}")
    print(f"  First listed row per day (one leg/day):     ${first_sum:,.2f}")
    print(f"  All short (1× short per date):            ${all_s:,.2f}")
    print(f"  All long  (1× long per date):             ${all_l:,.2f}")
    print(f"  Both sides every day (short+long P/L):     ${both:,.2f}")
    print(f"  Random one side / day (expect 0.5× both):  ${rnd:,.2f}")
    print(f"  Hindsight best side / day:               ${hind:,.2f}")
    print(
        f"\n  Interpretation: edge vs random side is ~${cur - rnd:,.2f}  "
        f"(hindsight upper bound +${hind - cur:,.2f} vs current selection)."
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
