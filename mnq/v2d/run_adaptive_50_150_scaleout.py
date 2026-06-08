#!/usr/bin/env python3
"""
**Adaptive 50/150 stitched scale-out** — same daily regime routing as
``build_adaptive_trades.py`` (prior-day MA50 vs MA150 selects **v2b** vs **v2d** rows),
but each leg is **replayed on 1 m MNQ** as **2 contracts**:

- **Initial:** 2 MNQ at tier‑1 fill; stop at canonical wide stop for that regime/direction.
- **TP1:** exit **1** contract at the **tier‑1 target** for that playbook (v2b measured move to RH±R;
  v2d fade to RH or RL per ``build_adaptive_year_samples.py``).
- **Runner:** stop tightened to **range-boundary breakeven vs tier‑1 fill** —
  **Long → RH + tick**, **Short → RL − tick** (same spirit as ``v2b_m_so``).
- **TP2:** **Long v2b:** RH + 2R; **Short v2b:** RL − 2R;
  **Long v2d:** RH + R past first target; **Short v2d:** RL − R past first target.

**Fill discovery**

- **v2b:** Long first touch **RH + tick** after OR; Short **RL − tick** (no extra slip — matches
  ``v2b_m_so`` style).
- **v2d fade:** Long — short breakout (**low ≤ RL − tick**) then buy **RL + tick**; Short —
  long breakout (**high ≥ RH + tick**) then sell **RH − tick**.

Intraday **pessimistic** 1 m ordering (stop before TP; runner SL before TP2 on partial bar).
Unsettled size → last RTH close **before** 16:00 after **15:59** cutoff (same as ``v2b_m_so``).

Multi-leg days (up to 2) chain: leg **n+1** fill scan starts **after** leg **n** exit bar.

Fees **\$1.50** RT per MNQ closed; **\$2**/point.

Example::

  cd potions/mnq/v2d
  python3 run_adaptive_50_150_scaleout.py --export-csv ./adaptive_50_150_scaleout_legs.csv
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path

import pandas as pd
import pytz

V2D = Path(__file__).resolve().parent
MNQ_ROOT = V2D.parent
POTIONS_SCRIPTS = MNQ_ROOT.parent / 'scripts'

sys.path[:0] = [str(MNQ_ROOT), str(MNQ_ROOT / 'scripts'), str(POTIONS_SCRIPTS)]

import annotate_mnq_v2b_range_context as ann  # noqa: E402

NY = pytz.timezone('America/New_York')
RTH_LO = time(9, 30)
RTH_HI = time(16, 0)
ORB_HI = time(9, 45)
EOD_CUTOFF = time(15, 59)

TICK = 0.25
MULT = 2.0
FEE_RT = 1.50
_EPS = 1e-12


def rth_slice(idx_df: pd.DataFrame, session_day: date) -> pd.DataFrame:
    return idx_df[
        idx_df.index.map(lambda t: (t.date() == session_day and RTH_LO <= t.time() < RTH_HI))
    ].copy()


def or_prior_anchor(rth: pd.DataFrame, session_day: date) -> pd.Timestamp | None:
    pre = rth[rth.index.map(lambda t: t.date() == session_day and t.time() < ORB_HI)]
    if pre.empty:
        return None
    return pd.Timestamp(pre.index[-1])


def path_after_prior(rth: pd.DataFrame, session_day: date, after_ts: pd.Timestamp | None) -> pd.DataFrame:
    """Bars strictly after OR anchor (leg 1) or after prior leg exit (leg 2+)."""
    if after_ts is None:
        anchor = or_prior_anchor(rth, session_day)
        if anchor is None:
            return rth.iloc[0:0]
        return rth[rth.index > anchor].sort_index()
    return rth[rth.index > after_ts].sort_index()


def find_fill_v2b_long(sub: pd.DataFrame, rh: float) -> tuple[pd.Timestamp | None, float | None]:
    trig = rh + TICK
    for ts, bar in sub.iterrows():
        if float(bar['high']) >= trig - _EPS:
            return pd.Timestamp(ts), float(trig)
    return None, None


def find_fill_v2b_short(sub: pd.DataFrame, rl: float) -> tuple[pd.Timestamp | None, float | None]:
    trig = rl - TICK
    for ts, bar in sub.iterrows():
        if float(bar['low']) <= trig + _EPS:
            return pd.Timestamp(ts), float(trig)
    return None, None


def find_fill_v2d_long(sub: pd.DataFrame, rl: float) -> tuple[pd.Timestamp | None, float | None]:
    br = rl - TICK
    fd = rl + TICK
    phase = 0
    for ts, bar in sub.iterrows():
        if phase == 0:
            if float(bar['low']) <= br + _EPS:
                phase = 1
                if float(bar['high']) >= fd - _EPS:
                    return pd.Timestamp(ts), float(fd)
            continue
        if float(bar['high']) >= fd - _EPS:
            return pd.Timestamp(ts), float(fd)
    return None, None


def find_fill_v2d_short(sub: pd.DataFrame, rh: float) -> tuple[pd.Timestamp | None, float | None]:
    br = rh + TICK
    fd = rh - TICK
    phase = 0
    for ts, bar in sub.iterrows():
        if phase == 0:
            if float(bar['high']) >= br - _EPS:
                phase = 1
                if float(bar['low']) <= fd + _EPS:
                    return pd.Timestamp(ts), float(fd)
            continue
        if float(bar['low']) <= fd + _EPS:
            return pd.Timestamp(ts), float(fd)
    return None, None


def resolve_fill(
    regime: str,
    direction: str,
    sub: pd.DataFrame,
    rh: float,
    rl: float,
) -> tuple[pd.Timestamp | None, float | None]:
    if regime == 'v2b':
        if direction == 'Long':
            return find_fill_v2b_long(sub, rh)
        return find_fill_v2b_short(sub, rl)
    if direction == 'Long':
        return find_fill_v2d_long(sub, rl)
    return find_fill_v2d_short(sub, rh)


def trade_params(regime: str, direction: str, rh: float, rl: float, rv: float) -> dict | None:
    if rv <= _EPS:
        return None
    if regime == 'v2b':
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
    # v2d fade — targets match build_adaptive_year_samples.find_exit_v2d setup
    if direction == 'Long':
        return {
            'long_side': True,
            'entry': rl + TICK,
            'init_sl': rl - rv,
            'tp1': rh,
            'tp2': rh + rv,
            'runner_sl': rl + TICK,
        }
    return {
        'long_side': False,
        'entry': rh - TICK,
        'init_sl': rh + rv,
        'tp1': rl,
        'tp2': rl - rv,
        'runner_sl': rh - TICK,
    }


def tp_style_label(net_usd: float, res_final: str, hit_tp1: bool, hit_tp2: bool) -> str:
    if res_final == 'Runner-BE' and hit_tp1 and not hit_tp2:
        return 'Win' if net_usd > 0 else 'Loss'
    if res_final == 'Win' and hit_tp2:
        return 'Win'
    if res_final.startswith('EOD'):
        return res_final
    if res_final == 'Loss':
        return 'Loss'
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
) -> tuple[float, str, pd.Timestamp | None, bool, bool, str]:
    """
    Returns (net_usd, tp_style_label, exit_ts, hit_tp1, hit_tp2, res_final).
    """
    path = rth[rth.index >= fill_ts].sort_index()
    qty = 2
    pnl_pts = 0.0
    fees = 0.0
    hit_tp1 = False
    hit_tp2 = False
    res_final = ''
    exit_ts: pd.Timestamp | None = None

    def fee_close(n: int) -> None:
        nonlocal fees
        fees += FEE_RT * n

    for ts, bar in path.iterrows():
        if ts.time() >= EOD_CUTOFF:
            break
        h = float(bar['high'])
        l = float(bar['low'])

        if long_side:
            if qty == 2:
                if l <= init_sl + _EPS:
                    pnl_pts += 2.0 * (init_sl - entry)
                    fee_close(2)
                    qty = 0
                    res_final = 'Loss'
                    exit_ts = pd.Timestamp(ts)
                    break
                if h >= tp1 - _EPS:
                    pnl_pts += tp1 - entry
                    fee_close(1)
                    hit_tp1 = True
                    qty = 1
                    if l <= runner_sl + _EPS:
                        pnl_pts += runner_sl - entry
                        fee_close(1)
                        qty = 0
                        res_final = (
                            'Runner-BE' if abs(runner_sl - entry) < 1e-9 else 'Loss'
                        )
                        exit_ts = pd.Timestamp(ts)
                        break
                    if h >= tp2 - _EPS:
                        pnl_pts += tp2 - entry
                        fee_close(1)
                        hit_tp2 = True
                        qty = 0
                        res_final = 'Win'
                        exit_ts = pd.Timestamp(ts)
                        break
            elif qty == 1:
                if l <= runner_sl + _EPS:
                    pnl_pts += runner_sl - entry
                    fee_close(1)
                    qty = 0
                    res_final = (
                        'Runner-BE' if abs(runner_sl - entry) < 1e-9 else 'Loss'
                    )
                    exit_ts = pd.Timestamp(ts)
                    break
                if h >= tp2 - _EPS:
                    pnl_pts += tp2 - entry
                    fee_close(1)
                    hit_tp2 = True
                    qty = 0
                    res_final = 'Win'
                    exit_ts = pd.Timestamp(ts)
                    break
        else:
            if qty == 2:
                if h >= init_sl - _EPS:
                    pnl_pts += 2.0 * (entry - init_sl)
                    fee_close(2)
                    qty = 0
                    res_final = 'Loss'
                    exit_ts = pd.Timestamp(ts)
                    break
                if l <= tp1 + _EPS:
                    pnl_pts += entry - tp1
                    fee_close(1)
                    hit_tp1 = True
                    qty = 1
                    if h >= runner_sl - _EPS:
                        pnl_pts += entry - runner_sl
                        fee_close(1)
                        qty = 0
                        res_final = (
                            'Runner-BE' if abs(runner_sl - entry) < 1e-9 else 'Loss'
                        )
                        exit_ts = pd.Timestamp(ts)
                        break
                    if l <= tp2 + _EPS:
                        pnl_pts += entry - tp2
                        fee_close(1)
                        hit_tp2 = True
                        qty = 0
                        res_final = 'Win'
                        exit_ts = pd.Timestamp(ts)
                        break
            elif qty == 1:
                if h >= runner_sl - _EPS:
                    pnl_pts += entry - runner_sl
                    fee_close(1)
                    qty = 0
                    res_final = (
                        'Runner-BE' if abs(runner_sl - entry) < 1e-9 else 'Loss'
                    )
                    exit_ts = pd.Timestamp(ts)
                    break
                if l <= tp2 + _EPS:
                    pnl_pts += entry - tp2
                    fee_close(1)
                    hit_tp2 = True
                    qty = 0
                    res_final = 'Win'
                    exit_ts = pd.Timestamp(ts)
                    break

    if qty > 0:
        tail = rth[
            rth.index.map(lambda ti: ti.date() == session_day and ti.time() < RTH_HI)
        ]
        if tail.empty:
            return 0.0, 'Loss', exit_ts, hit_tp1, hit_tp2, 'Loss'
        eod = float(tail.iloc[-1]['close'])
        ts_last = pd.Timestamp(tail.index[-1])
        if long_side:
            if qty == 2:
                pnl_pts += 2.0 * (eod - entry)
                fee_close(2)
            else:
                pnl_pts += eod - entry
                fee_close(1)
        else:
            if qty == 2:
                pnl_pts += 2.0 * (entry - eod)
                fee_close(2)
            else:
                pnl_pts += entry - eod
                fee_close(1)
        res_final = 'EOD-Win' if pnl_pts > 0 else ('EOD-Loss' if pnl_pts < 0 else 'EOD-Flat')
        exit_ts = ts_last

    net_usd = round(pnl_pts * MULT - fees, 2)
    lab = tp_style_label(net_usd, res_final, hit_tp1, hit_tp2)
    return net_usd, lab, exit_ts, hit_tp1, hit_tp2, res_final


@dataclass
class RowOut:
    date_iso: str
    regime: str
    direction: str
    csv_net_1ct: float
    scaleout_net_2ct: float
    tp_style: str
    hit_tp1: bool
    hit_tp2: bool


def stats_from_net_series(net_vals: list[float]) -> dict:
    if not net_vals:
        return {'n': 0, 'sum_net': 0.0, 'mean_net': 0.0}
    df = pd.DataFrame({'net': net_vals})
    return {
        'n': len(net_vals),
        'sum_net': float(df['net'].sum()),
        'mean_net': float(df['net'].mean()),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument(
        '--adaptive-csv',
        type=Path,
        default=V2D / 'mnq_orb_results_adaptive_50_150.csv',
        help='Stitched adaptive book from build_adaptive_trades.py',
    )
    ap.add_argument(
        '--1m',
        dest='m1',
        type=Path,
        default=MNQ_ROOT / 'raw' / 'glbx-mdp3-20210304-20260303.ohlcv-1m.csv',
    )
    ap.add_argument('--export-csv', type=Path, default=None)
    args = ap.parse_args()

    if not args.adaptive_csv.is_file():
        print(f'Missing {args.adaptive_csv}', file=sys.stderr)
        return 1
    if not args.m1.is_file():
        print(f'Missing 1m {args.m1}', file=sys.stderr)
        return 1

    ad = pd.read_csv(args.adaptive_csv)
    ad['_row_order'] = range(len(ad))
    ad['Date'] = pd.to_datetime(ad['Date']).dt.date
    ad = ad.sort_values(['Date', '_row_order'])

    need_dates = set(ad['Date'].unique())
    raw = ann.load_1m_for_dates(str(args.m1), min(need_dates), max(need_dates), need_dates)
    raw = ann.pick_front_month_day(raw)
    raw = raw.set_index(pd.DatetimeIndex(pd.to_datetime(raw['ts_event']))).sort_index()
    gby = {
        d: g for d, g in raw.groupby(pd.Series(raw.index.date, index=raw.index, dtype=object), sort=False)
    }

    outs: list[RowOut] = []
    scale_nets: list[float] = []
    skipped = 0
    paired_csv_nets: list[float] = []

    full_csv_net_sum = float(ad['Net_$'].astype(float).sum())

    for session_day in sorted(ad['Date'].unique()):
        grp = ad[ad['Date'] == session_day].sort_values('_row_order')
        day_raw = gby.get(session_day)
        if day_raw is None or day_raw.empty:
            skipped += len(grp)
            continue
        rth = rth_slice(day_raw, session_day)
        if rth.empty:
            skipped += len(grp)
            continue

        prior_exit_ts: pd.Timestamp | None = None

        for _, row in grp.iterrows():
            regime = str(row['Regime']).strip().lower()
            direction = str(row['Trade_Direction']).strip()
            rh = float(row['Range_High'])
            rl = float(row['Range_Low'])
            rv = float(row['Range'])
            csv_net = float(row['Net_$'])

            pm = trade_params(regime, direction, rh, rl, rv)
            if pm is None:
                skipped += 1
                continue

            sub = path_after_prior(rth, session_day, prior_exit_ts)
            if sub.empty:
                skipped += 1
                continue

            fts, _ep = resolve_fill(regime, direction, sub, rh, rl)
            if fts is None:
                skipped += 1
                continue

            net_usd, tp_lab, exit_ts, h1, h2, _rf = simulate_scale_out_leg(
                rth,
                session_day,
                fts,
                entry=float(pm['entry']),
                long_side=bool(pm['long_side']),
                init_sl=float(pm['init_sl']),
                tp1=float(pm['tp1']),
                tp2=float(pm['tp2']),
                runner_sl=float(pm['runner_sl']),
            )
            if exit_ts is None:
                skipped += 1
                continue

            prior_exit_ts = exit_ts
            scale_nets.append(net_usd)
            paired_csv_nets.append(csv_net)
            outs.append(
                RowOut(
                    date_iso=session_day.isoformat(),
                    regime=regime,
                    direction=direction,
                    csv_net_1ct=csv_net,
                    scaleout_net_2ct=net_usd,
                    tp_style=tp_lab,
                    hit_tp1=h1,
                    hit_tp2=h2,
                )
            )

    st_paired_csv = stats_from_net_series(paired_csv_nets)
    st_so = stats_from_net_series(scale_nets)

    def dd_daily(legs: pd.DataFrame, col: str) -> float:
        if legs.empty:
            return 0.0
        legs = legs.copy()
        legs['d'] = pd.to_datetime(legs['Date']).dt.date
        by_day = legs.groupby('d')[col].sum().sort_index()
        cd = by_day.cumsum()
        return float((cd - cd.cummax()).min())

    df_out = pd.DataFrame([o.__dict__ for o in outs])
    dd_day_so = dd_daily(
        pd.DataFrame({'Date': [o.date_iso for o in outs], 'net': scale_nets}),
        'net',
    ) if outs else 0.0
    dd_day_paired_csv = dd_daily(
        pd.DataFrame({'Date': [o.date_iso for o in outs], 'net': paired_csv_nets}),
        'net',
    ) if outs else 0.0

    cum_so = pd.Series(scale_nets).cumsum() if scale_nets else pd.Series(dtype=float)
    dd_so_leg = float((cum_so - cum_so.cummax()).min()) if len(cum_so) else 0.0
    cum_pcsv = pd.Series(paired_csv_nets).cumsum() if paired_csv_nets else pd.Series(dtype=float)
    dd_pcsv_leg = float((cum_pcsv - cum_pcsv.cummax()).min()) if len(cum_pcsv) else 0.0

    cum_full = pd.Series(ad['Net_$'].astype(float).values).cumsum()
    dd_full_leg = float((cum_full - cum_full.cummax()).min())

    print(f'Adaptive stitched CSV: {args.adaptive_csv.name}')
    print(f'Legs in CSV: {len(ad)}  |  Scale-out legs simulated: {len(outs)}  |  Skipped rows: {skipped}')
    print(f'Fees: ${FEE_RT} RT/MNQ  |  ${MULT}/pt  |  tick={TICK}')
    print()
    print('=== Reference — stitched CSV full book (all legs, 1 MNQ replay as in CSV) ===')
    print(f"  Legs: {len(ad)}  Σ Net_$: ${full_csv_net_sum:,.2f}")
    print(f"  Max DD (leg cumulative): ${dd_full_leg:,.2f}")
    print()
    print('=== Reference — paired subset (same legs as successful scale-out sim, CSV Net_$) ===')
    print(f"  Legs: {st_paired_csv['n']}  Σ Net_$: ${st_paired_csv['sum_net']:,.2f}")
    print(f"  Max DD (leg cumulative): ${dd_pcsv_leg:,.2f}  |  daily sum DD: ${dd_day_paired_csv:,.2f}")
    print()
    print('=== Sim — 2 MNQ scale-out (TP1 ×1, runner BE at RH±tick, TP2 extended) ===')
    print(f"  Legs simulated: {st_so['n']}  Σ Net_$: ${st_so['sum_net']:,.2f}")
    print(f"  Max DD (leg cumulative): ${dd_so_leg:,.2f}  |  daily sum DD: ${dd_day_so:,.2f}")
    if dd_so_leg:
        print(f"  Σ Net / |max DD leg|: {st_so['sum_net'] / abs(dd_so_leg):.3f}")

    n_tp2 = sum(o.hit_tp2 for o in outs)
    n_tp1 = sum(o.hit_tp1 for o in outs)
    print(f'\nRunner path: TP1 hit: {n_tp1}/{len(outs)}  |  TP2 hit: {n_tp2}/{len(outs)}')

    if args.export_csv:
        df_out.to_csv(args.export_csv, index=False)
        print(f'\nWrote {args.export_csv}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
