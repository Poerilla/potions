#!/usr/bin/env python3
"""
Adaptive switching (50/150 MA) with:

  • **v2b regime:** only trades that qualify as **strict clean-break TP wins** under the
    historical definition (manifest), re-simulated intraday with **2 index-point** stop loss
    and the usual OR target (boundary ± Range). **5 MNQ** per trade.

  • **v2d regime:** same rows as canonical v2d backtest (**2 MNQ** per trade; scale fees linearly).

**No** canonical v2b fills — clean-break arm only when Step 1 would have been in v2b.

Also prints how many strict clean wins are **Leg 1 vs Leg 2** (first vs second breakout of the day).

Defaults:
  --stop-pts 2  --contracts-clean 5  --contracts-v2d 2  --open-range-minutes 15
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import databento as db
import pandas as pd

POTIONS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(POTIONS / 'scripts'))
sys.path.insert(0, str(POTIONS / 'mnq' / 'v2e' / 'scripts'))

from step2_preplaced_stops import (  # noqa: E402
    EOD_CUTOFF,
    FEE_RT,
    DEFAULT_OPEN_RANGE_MIN,
    PRODUCTS,
    load_one_min,
    open_range_end_time,
)
from count_clean_break_v2b import simulate_day_trace  # noqa: E402

DAILY_DBN = '/home/tester/hsm/potions/mnq/raw/glbx-mdp3-20100606-20260308.ohlcv-1d.dbn.zst'
V2D_CSV = Path(__file__).resolve().parents[1] / 'v2d' / 'mnq_orb_results_v2d.csv'
MANIFEST_DEFAULT = (
    Path(__file__).resolve().parents[1] / 'v2e' / 'data' / 'clean_break_manifest.csv'
)
OUT_CSV = Path(__file__).resolve().parent / 'mnq_adaptive_clean_break_2sl_5ct_v2d2ct.csv'

FAST, SLOW = 50, 150
MNQ_MULT = float(PRODUCTS['MNQ']['mult'])
MNQ_TICK = float(PRODUCTS['MNQ']['tick'])


def daily_close():
    store = db.DBNStore.from_file(DAILY_DBN)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')].copy()
    df['date'] = pd.to_datetime(df['ts_event']).dt.date
    fm = df.loc[df.groupby('date')['volume'].idxmax()]
    return fm.set_index('date').sort_index()['close']


def regime_series():
    close = daily_close()
    ma_fast = close.rolling(FAST).mean()
    ma_slow = close.rolling(SLOW).mean()
    return (ma_fast > ma_slow).shift(1).fillna(True), ma_fast, ma_slow


def simulate_tight_exit(
    day_bars: pd.DataFrame,
    fill_ts: pd.Timestamp,
    direction: str,
    entry: float,
    target: float,
    stop_pts: float,
) -> Tuple[float, str]:
    """
    From fill bar through EOD: first hit of **tight** stop (entry ± stop_pts) or target.
    Pessimistic: same as step2 (stop before target when both in one bar).
    """
    path = day_bars[day_bars.index >= fill_ts]
    path = path[path.index.map(lambda t: t.time() <= EOD_CUTOFF)]
    if path.empty:
        return entry, 'EOD-Flat'

    stop_px = entry - stop_pts if direction == 'Long' else entry + stop_pts

    for _, bar in path.iterrows():
        h, l = float(bar['high']), float(bar['low'])
        if direction == 'Long':
            if l < stop_px:
                return stop_px, 'Loss'
            if h >= target:
                return target, 'Win'
        else:
            if h > stop_px:
                return stop_px, 'Loss'
            if l <= target:
                return target, 'Win'

    last = float(path.iloc[-1]['close'])
    if direction == 'Long':
        res = 'EOD-Win' if last > entry else 'EOD-Loss'
    else:
        res = 'EOD-Win' if last < entry else 'EOD-Loss'
    return last, res


def net_dollars(
    direction: str,
    entry: float,
    exit_px: float,
    result: str,
    contracts: int,
) -> float:
    """Gross $ from index points P/L, then RT fee per contract."""
    if direction == 'Long':
        pl = exit_px - entry
    else:
        pl = entry - exit_px
    gross = pl * MNQ_MULT * contracts
    return gross - FEE_RT * contracts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', type=Path, default=MANIFEST_DEFAULT)
    ap.add_argument('--stop-pts', type=float, default=2.0)
    ap.add_argument('--contracts-clean', type=int, default=5)
    ap.add_argument('--contracts-v2d', type=int, default=2)
    ap.add_argument('--open-range-minutes', type=int, default=DEFAULT_OPEN_RANGE_MIN)
    args = ap.parse_args()

    man = pd.read_csv(args.manifest)
    man['Date'] = pd.to_datetime(man['Date']).dt.date
    strict = man[man['strict_clean'].astype(bool)].copy()

    print('=== Strict clean-break TP wins — first vs second breakout (Leg column) ===\n')
    vc = strict['Leg'].value_counts().sort_index()
    for leg, n in vc.items():
        pct = 100.0 * n / len(strict)
        lbl = '1st breakout of day (Leg 1)' if leg == 1 else '2nd breakout (Leg 2)'
        print(f'  Leg {leg} ({lbl}): {int(n):4d}  ({pct:.1f}% of strict clean wins)')
    print(f'  Total strict clean winning legs: {len(strict)}')
    both = strict.groupby('Date').size()
    multi = (both > 1).sum()
    print(f'  Sessions with >1 strict-clean win leg: {int(multi)} (max 2 under v2b rules)\n')

    regime_v2b, ma_fast, ma_slow = regime_series()
    v2d = pd.read_csv(V2D_CSV)
    v2d['Date'] = pd.to_datetime(v2d['Date']).dt.date

    tick = MNQ_TICK
    range_end = open_range_end_time(args.open_range_minutes)

    df = load_one_min('MNQ')
    rows: List[dict] = []
    clean_trades_logged = 0

    for day, day_df in df.groupby('date'):
        day_df = day_df.sort_index()
        rng = day_df[day_df['t'] < range_end]
        if rng.empty:
            continue
        rh, rl = float(rng['high'].max()), float(rng['low'].min())
        rv = rh - rl
        if rv <= 0:
            continue
        trade_seg = day_df[day_df['t'] >= range_end]
        if trade_seg.empty:
            continue

        d = day
        if d not in regime_v2b.index:
            is_v2b = True
            ma_f = ma_s = None
        else:
            is_v2b = bool(regime_v2b.loc[d])
            ma_f = ma_fast.loc[d] if d in ma_fast.index else None
            ma_s = ma_slow.loc[d] if d in ma_slow.index else None

        if is_v2b:
            trs, mts = simulate_day_trace(rh, rl, rv, trade_seg, tick, 1)
            want = strict[(strict['Date'] == d)]
            for k, ((direc, ent, _orig_x, ores), (fill_ts, _, _ex)) in enumerate(
                zip(trs, mts)
            ):
                leg = k + 1
                m = want[(want['Leg'] == leg) & (want['Trade_Direction'] == direc)]
                if m.empty or ores != 'Win':
                    continue
                tar = rh + rv if direc == 'Long' else rl - rv
                exit_px, res2 = simulate_tight_exit(
                    trade_seg, fill_ts, direc, ent, tar, args.stop_pts
                )
                net = net_dollars(direc, ent, exit_px, res2, args.contracts_clean)
                pl_pts = (exit_px - ent) if direc == 'Long' else (ent - exit_px)
                sym = trade_seg.iloc[0]['symbol']
                clean_trades_logged += 1
                rows.append(
                    {
                        'Date': d,
                        'Regime': 'clean_2sl',
                        'MA_fast_prev': round(ma_f, 2) if ma_f is not None else None,
                        'MA_slow_prev': round(ma_s, 2) if ma_s is not None else None,
                        'Symbol': sym,
                        'Range_High': rh,
                        'Range_Low': rl,
                        'Range': rv,
                        'Trade_Direction': direc,
                        'Leg': leg,
                        'Entry_Price': ent,
                        'Exit_Price': exit_px,
                        'Trade_PL': round(pl_pts, 6),
                        'Net_$': round(net, 2),
                        'Result': res2,
                        'Contracts': args.contracts_clean,
                    }
                )
        else:
            day_v = v2d[v2d['Date'] == d]
            for _, t in day_v.iterrows():
                pl = float(t['Trade_PL'])
                net1 = float(t['Net_$'])
                net = net1 * args.contracts_v2d
                row = t.to_dict()
                row['Regime'] = 'v2d'
                row['MA_fast_prev'] = round(ma_f, 2) if ma_f is not None else None
                row['MA_slow_prev'] = round(ma_s, 2) if ma_s is not None else None
                row['Trade_PL'] = pl
                row['Net_$'] = round(net, 2)
                row['Contracts'] = args.contracts_v2d
                rows.append(row)

    out = pd.DataFrame(rows)
    if out.empty:
        print('No rows produced.')
        return

    out = out.sort_values(['Date', 'Leg'] if 'Leg' in out.columns else ['Date'])
    out['Cumulative_$'] = out['Net_$'].cumsum().round(2)
    out['Cumulative_PL'] = out['Trade_PL'].cumsum().round(6)
    col = [
        'Date',
        'Regime',
        'MA_fast_prev',
        'MA_slow_prev',
        'Symbol',
        'Range_High',
        'Range_Low',
        'Range',
        'Trade_Direction',
        'Leg',
        'Entry_Price',
        'Exit_Price',
        'Trade_PL',
        'Net_$',
        'Result',
        'Contracts',
    ]
    col = [c for c in col if c in out.columns] + [
        c for c in out.columns if c not in col and c not in ('Cumulative_$', 'Cumulative_PL')
    ]
    out = out[[c for c in col if c in out.columns] + ['Cumulative_PL', 'Cumulative_$']]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)

    skipped_strict = len(strict) - clean_trades_logged
    print(
        '\n(Regime gate: strict-clean legs traded only on v2b days; skipped if that session is v2d.)\n'
        f'  Strict-clean legs in manifest: {len(strict)}  |  '
        f'Logged as clean_2sl trades: {clean_trades_logged}  |  '
        f'Not taken (v2d regime that day): {skipped_strict}\n'
    )

    print('=== Adaptive backtest (clean-only v2b arm + v2d scaled) ===\n')
    print(
        f"Stop: {args.stop_pts:g} index pts  |  Clean contracts: {args.contracts_clean}  "
        f"|  v2d contracts: {args.contracts_v2d}\n"
    )
    print(f"Wrote {len(out):,} trades -> {OUT_CSV}")
    print(f"Total Net_$: ${out['Net_$'].sum():,.2f}")
    eq = out['Net_$'].cumsum()
    print(f"Max realized DD: ${(eq - eq.cummax()).min():,.2f}")
    for label, sub in (
        ('clean_2sl / v2b arm', out[out['Regime'] == 'clean_2sl']),
        ('v2d x2', out[out['Regime'] == 'v2d']),
    ):
        if sub.empty:
            continue
        print(
            f"  {label}: {len(sub)} trades  net ${sub['Net_$'].sum():,.2f}  "
            f"WR {(sub['Trade_PL'] > 0).mean() * 100:.1f}%"
        )


if __name__ == '__main__':
    main()
