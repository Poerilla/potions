#!/usr/bin/env python3
"""
Count **v2b clean breaks** (1m): winning trades where price reaches TP without meaningfully
pulling back into/toward the opening range boundary before target — proxy for a very tight
discretionary stop.

Replay matches ``step2_preplaced_stops.simulate_day`` (OCO, bracket-then-reverse). For each
trade that exits **Win** at TP, measure path from fill bar through target bar:

  - **Long:** excursion after the fill bar until TP: ``min(low)``.
      - **strict** — never touches RH again: ``min(low) > RH``
      - **noise10** — allow up to 10 MNQ index pts below RH: ``min(low) >= RH - 10``
  - **Short:** ``max(high)``, strict ``max(high) < RL``, noise ``max(high) <= RL + 10``

Outputs:
  - Console statistics (counts, % of wins, per calendar year)
  - ``data/clean_break_manifest.csv``
  - Optional PNGs in ``data/clean_break_charts/`` (strict winners by default)
  - Adaptive P&amp;L subset: days that contain ≥1 **strict** clean-break win (all adaptive rows
    on those session dates from baseline adaptive CSV)

Usage:
  python3 count_clean_break_v2b.py
  python3 count_clean_break_v2b.py --charts --max-charts 200
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

V2E_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_IDX = Path(__file__).resolve().parents[3] / 'scripts'
sys.path.insert(0, str(_SCRIPTS_IDX))
from step2_preplaced_stops import (  # noqa: E402
    DEFAULT_OPEN_RANGE_MIN,
    EOD_CUTOFF,
    MAX_TRADES_PER_DAY,
    PRODUCTS,
    load_one_min,
    open_range_end_time,
)

V2B_CSV = Path(str(PRODUCTS['MNQ']['out']))
ADAPTIVE_CSV = V2E_ROOT.parent / 'v2d' / 'mnq_orb_results_adaptive_50_150.csv'
OUT_DIR = V2E_ROOT / 'data' / 'clean_break_charts'
M1_FALLBACK = V2E_ROOT.parent / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv'

SCR_V2E = Path(__file__).resolve().parent
sys.path.insert(0, str(SCR_V2E))
from build_london_sweep_charts import draw_opens_research_chart  # noqa: E402
import annotate_mnq_v2b_range_context as ann  # noqa: E402

from prior_week_levels import DEFAULT_DAILY_DBN, load_mnq_front_daily, prior_week_last_close  # noqa: E402

NOISE_PTS_DEFAULT = 10.0


def simulate_day_trace(
    rh: float,
    rl: float,
    range_val: float,
    day_bars: pd.DataFrame,
    tick: float,
    slip_ticks: int = 1,
) -> Tuple[
    List[Tuple[str, float, float, str]],
    List[Tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]],
]:
    """
    Same exits as simulate_day; additionally returns list parallel to trades:
      (fill_bar_ts, entry_ts (= fill bar timestamp), exit_ts)
    Exit timestamp = bar where target/stop/EOD closure is detected.
    """
    long_trigger = rh + tick
    short_trigger = rl - tick
    long_entry = long_trigger + slip_ticks * tick
    short_entry = short_trigger - slip_ticks * tick

    arm_long = True
    arm_short = True
    phase = 'ARMED'
    direction = None
    entry = target = stop = None
    trades: List[Tuple[str, float, float, str]] = []
    meta: List[Tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]] = []
    last_bar = None
    fill_ts: Optional[pd.Timestamp] = None

    for ts, bar in day_bars.iterrows():
        last_bar = bar
        h, l = float(bar['high']), float(bar['low'])
        bar_time = ts.time() if hasattr(ts, 'time') else None

        if phase == 'ARMED' and bar_time is not None and bar_time >= EOD_CUTOFF:
            break

        if phase == 'ARMED':
            long_hit = arm_long and h >= long_trigger
            short_hit = arm_short and l <= short_trigger

            if long_hit and short_hit:
                mid = (rh + rl) / 2
                if float(bar['open']) >= mid:
                    direction, entry = 'Long', long_entry
                    target, stop = rh + range_val, rl
                else:
                    direction, entry = 'Short', short_entry
                    target, stop = rl - range_val, rh
                phase = 'IN'
                fill_ts = ts
            elif long_hit:
                direction, entry = 'Long', long_entry
                target, stop = rh + range_val, rl
                phase = 'IN'
                fill_ts = ts
            elif short_hit:
                direction, entry = 'Short', short_entry
                target, stop = rl - range_val, rh
                phase = 'IN'
                fill_ts = ts

        if phase == 'IN':
            closed = False
            exit_lab = ''
            exit_ts_here = ts
            if direction == 'Long':
                if l < stop:
                    trades.append(('Long', entry, stop, 'Loss'))
                    exit_lab = 'Loss'
                    closed = True
                elif h >= target:
                    trades.append(('Long', entry, target, 'Win'))
                    exit_lab = 'Win'
                    closed = True
            else:
                if h > stop:
                    trades.append(('Short', entry, stop, 'Loss'))
                    exit_lab = 'Loss'
                    closed = True
                elif l <= target:
                    trades.append(('Short', entry, target, 'Win'))
                    exit_lab = 'Win'
                    closed = True

            if closed:
                fu = fill_ts if fill_ts is not None else ts
                meta.append((fu, fu, ts))
                traded_dir = direction
                if traded_dir == 'Long':
                    arm_long = False
                else:
                    arm_short = False
                phase, direction = 'ARMED', None
                fill_ts = None
                entry = target = stop = None

                if not (arm_long or arm_short) or len(trades) >= MAX_TRADES_PER_DAY:
                    phase = 'DONE'
                    break

    if phase == 'IN' and last_bar is not None:
        fu = fill_ts if fill_ts is not None else last_bar.name
        tsx = last_bar.name
        ep = float(last_bar['close'])
        if direction == 'Long':
            res = 'EOD-Win' if ep > entry else 'EOD-Loss'
        else:
            res = 'EOD-Win' if ep < entry else 'EOD-Loss'
        trades.append((direction, entry, ep, res))
        meta.append((fu, fu, tsx))

    return trades, meta


def excursion_bounds(
    day_bars: pd.DataFrame,
    fill_ts: pd.Timestamp,
    exit_ts: pd.Timestamp,
    direction: str,
    skip_fill_bar: bool,
) -> Tuple[float, float]:
    """Returns (min_low, max_high) on path [fill, exit] from 1m bars."""
    path = day_bars.loc[(day_bars.index >= fill_ts) & (day_bars.index <= exit_ts)]
    if path.empty:
        return float('nan'), float('nan')
    seg = path.iloc[1:] if skip_fill_bar and len(path) > 1 else path
    if seg.empty:
        seg = path
    return float(seg['low'].min()), float(seg['high'].max())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--noise-pts', type=float, default=NOISE_PTS_DEFAULT)
    ap.add_argument('--open-range-minutes', type=int, default=DEFAULT_OPEN_RANGE_MIN)
    ap.add_argument('--charts', action='store_true', help='Write PNGs to data/clean_break_charts')
    ap.add_argument('--max-charts', type=int, default=0, help='Cap PNGs (0 = all strict wins)')
    ap.add_argument(
        '--chart-mode',
        choices=('strict_only', 'strict_and_noise10'),
        default='strict_only',
    )
    args = ap.parse_args()

    tick = PRODUCTS['MNQ']['tick']
    range_end = open_range_end_time(args.open_range_minutes)
    df = load_one_min('MNQ')

    rows: List[dict] = []
    wins = 0
    strict_clean = noise_clean = 0
    yearly = {}

    def ykey(d):
        return pd.Timestamp(d).year

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

        trades, metas = simulate_day_trace(rh, rl, rv, trade_seg, tick, 1)

        for k, ((d_, ent, xt, res), (fill_ts, _e_ts, exit_ts)) in enumerate(
            zip(trades, metas)
        ):
            if res != 'Win':
                continue
            wins += 1
            mln, mxh = excursion_bounds(trade_seg, fill_ts, exit_ts, d_, skip_fill_bar=True)

            strict = False
            noise_ok = False
            noise5_ok = False
            if d_ == 'Long':
                strict = mln > rh + 1e-12
                noise_ok = mln >= rh - args.noise_pts - 1e-12
                noise5_ok = mln >= rh - 5.0 - 1e-12
            else:
                strict = mxh < rl - 1e-12
                noise_ok = mxh <= rl + args.noise_pts + 1e-12
                noise5_ok = mxh <= rl + 5.0 + 1e-12

            if strict:
                strict_clean += 1
            if noise_ok:
                noise_clean += 1

            y = ykey(day)
            yearly.setdefault(y, {'w': 0, 'strict': 0, 'noise': 0, 'noise5': 0})
            yearly[y]['w'] += 1
            if strict:
                yearly[y]['strict'] += 1
            if noise_ok:
                yearly[y]['noise'] += 1
            if noise5_ok:
                yearly[y]['noise5'] += 1

            rows.append(
                {
                    'Date': day,
                    'Leg': k + 1,
                    'Trade_Direction': d_,
                    'Result': res,
                    'RH': rh,
                    'RL': rl,
                    'Range': rv,
                    'min_low_after_fill': mln if d_ == 'Long' else None,
                    'max_high_after_fill': mxh if d_ == 'Short' else None,
                    'strict_clean': strict,
                    'noise_clean': noise_ok,
                    'noise_clean_5pt': noise5_ok,
                    'boundary_for_long_pullback_is_RH': rh,
                    'boundary_for_short_pullback_is_RL': rl,
                }
            )

    man = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mpath = OUT_DIR / 'clean_break_manifest.csv'
    man.to_csv(mpath, index=False)

    print('\n=== v2b clean break (replay = step2 OCO / bracket-then-reverse) ===')
    print(f"Opening range: 9:30 ET + {args.open_range_minutes} min  |  noise band: {args.noise_pts} pts\n")
    print(f"V2b TP **wins** (legs hitting target): {wins:,}")
    if wins:
        print(
            f"  Strict  (long: min(low)>RH after fill bar; short: max(high)<RL): "
            f"{strict_clean:,}  ({100*strict_clean/wins:.1f}% of wins)"
        )
        n5 = sum(1 for row in rows if row.get('noise_clean_5pt'))
        print(
            f"  Noise @5pt: {n5:,}  ({100*n5/wins:.1f}% of wins)"
        )
        print(
            f"  Noise @ {args.noise_pts:g} pt: "
            f"{noise_clean:,}  ({100*noise_clean/wins:.1f}% of wins)"
        )
    print('\n=== Per calendar year (# TP wins / strict / noise@10 / noise@5) ===')
    for y in sorted(yearly):
        zz = yearly[y]
        print(
            f"  {y}:  wins={zz['w']:4d}  strict={zz['strict']:4d}  "
            f"noise@{args.noise_pts:.0f}={zz['noise']:4d}  noise@5={zz['noise5']:4d}"
        )

    # Adaptive slice: dates with ≥1 strict clean win
    if wins and ADAPTIVE_CSV.is_file():
        ad = pd.read_csv(ADAPTIVE_CSV)
        ad['Date'] = pd.to_datetime(ad['Date']).dt.date
        strict_dates = {pd.Timestamp(r['Date']).date() for _, r in man.iterrows() if r['strict_clean']}
        sub = ad[ad['Date'].isin(strict_dates)]
        whole = ad
        print('\n=== Adaptive mnq_orb_results_adaptive_50_150.csv ===')
        print(f"All rows net $: ${whole['Net_$'].sum():,.2f}  ({len(whole)} trades)")
        print(
            f"Subset: session dates with ≥1 **strict** clean-break v2b win:\n"
            f"       net $: ${sub['Net_$'].sum():,.2f}  ({len(sub)} trades on {len(strict_dates)} days)"
        )

    print(f'\nManifest: {mpath}')
    wins_df = man[man['strict_clean']]
    wins_noise = man[man['noise_clean']]

    # Charts
    if args.charts and not wins_df.empty:
        need = wins_df.copy()
        if args.chart_mode == 'strict_only':
            chart_df = wins_df.head(args.max_charts) if args.max_charts else wins_df
        else:
            cand = pd.concat([wins_df, wins_noise]).drop_duplicates(
                subset=['Date', 'Trade_Direction', 'Leg']
            )
            chart_df = cand.head(args.max_charts) if args.max_charts else cand

        dates = sorted(set(pd.to_datetime(chart_df['Date']).dt.date.unique()))
        tmin, tmax = dates[0], dates[-1]
        print(f'\nCharts: {len(chart_df)} file(s), loading 1m…', flush=True)
        raw = ann.load_1m_for_dates(str(M1_FALLBACK), tmin, tmax, set(dates))
        raw = ann.pick_front_month_day(raw).set_index('ts_event').sort_index()
        gby = {
            d: g
            for d, g in raw.groupby(
                pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False
            )
        }

        daily_mnq = None
        try:
            daily_mnq = load_mnq_front_daily(DEFAULT_DAILY_DBN)
        except Exception as e:
            print(f'(daily skipped: {e})')

        tag = 'v2b strict clean-break → TP'
        drawn = 0
        failed: List[str] = []
        v2br = pd.read_csv(V2B_CSV)
        v2br['Date'] = pd.to_datetime(v2br['Date']).dt.date

        for _, r in chart_df.iterrows():
            d = pd.Timestamp(r['Date']).date() if hasattr(r['Date'], 'year') else r['Date']
            side = r['Trade_Direction']
            if isinstance(d, pd.Timestamp):
                d = d.date()
            fn = OUT_DIR / f"{d}_{side}_Leg{r['Leg']}.png"
            # Merge row from annotated v2b for title
            vv = v2br[(v2br['Date'] == d) & (v2br['Trade_Direction'] == side)]
            if vv.empty:
                tr = pd.Series(
                    {
                        'Symbol': 'MNQ',
                        'Trade_Direction': side,
                        'Range_High': r['RH'],
                        'Range_Low': r['RL'],
                        'Range': r['Range'],
                        'Trade_PL': 0.0,
                        'Net_$': 0.0,
                        'Regime': 'strict_clean_win',
                    }
                )
            else:
                tr = vv.iloc[0].copy()
                tr['Regime'] = 'strict_clean_win'

            rh, rl, rv = float(r['RH']), float(r['RL']), float(r['Range'])
            if side == 'Long':
                tp, sl = rh + rv, rl
            else:
                tp, sl = rl - rv, rh
            if not vv.empty and 'Entry_Price' in vv.columns and pd.notna(vv.iloc[0].get('Entry_Price')):
                ent = float(vv.iloc[0]['Entry_Price'])
            else:
                ent = (rh + tick * 2) if side == 'Long' else (rl - tick * 2)

            pwc = prior_week_last_close(daily_mnq, d) if daily_mnq is not None else None
            ok = draw_opens_research_chart(
                d,
                gby,
                d,
                tr,
                fn,
                v2e_side=side,
                case_study_tag=tag,
                show_orb_ref=True,
                prior_week_close=pwc,
                level_entry=ent,
                level_tp=tp,
                level_sl=sl,
            )
            if ok:
                drawn += 1
            else:
                failed.append(str(fn.name))
        print(f'Wrote {drawn} chart(s) under {OUT_DIR}')
        if failed:
            print(f'  ({len(failed)} chart(s) skipped — no overnight 1m in export for: {failed[:12]}…)'
                  if len(failed) > 12 else f'  Skipped no-data: {failed}')

    idx = OUT_DIR / 'INDEX.md'
    with open(idx, 'w', encoding='utf-8') as f:
        f.write('# v2b clean-break winners (strict: no retest of RH/RL after fill → TP)\n\n')
        f.write(
            f'Manifest: `{mpath.name}`  ·  total TP wins scanned: **{wins}**  ·  '
            f'strict: **{strict_clean}** ({100*strict_clean/wins:.1f}% of wins)\n'
        )

    print(f'\nINDEX: {idx}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
