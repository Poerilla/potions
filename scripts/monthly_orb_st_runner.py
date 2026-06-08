#!/usr/bin/env python3
"""Monthly ORB (long-only) + weekly ATR Supertrend: 2-lot scale (scalp + runner).

- Enter when the *current* month weekly Supertrend reads bullish and monthly ORB
  long rules fire (close breakout, limit retest at RH, stop RL, target RH+R).
- Scalp (1 index unit): baseline restricted long — RL stop, TP, or daily close
  back inside that month's OR.
- Runner (1 unit): same fill; not closed by restrictive settle while weekly trend
  stays ``up``. Runner exits on RL (birth month OR low), weekly flip to bearish
  (exit at close), or (only in origin month, weekly not bullish) restrictive settle.

Runners from earlier months are not affected by new months' OR boxes.

Uses ``calculate_weekly_atr_trailing_stop_on_daily`` from
``yearly_orb_delivery_research_charts``.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from yearly_orb_delivery_research_charts import calculate_weekly_atr_trailing_stop_on_daily

WAIT_BREAKOUT = 0
WAIT_FILL = 1
MAX_TRADES_PER_PERIOD = 2
OR_LEN = 3

DEFAULT_RUNS = [
    ('MNQ', ROOT / 'mnq' / 'mnq_daily.csv', ROOT / 'mnq' / 'mnq_monthly_orb_st_runner.csv', 2.0),
    ('NQ', ROOT / 'nq' / 'nq_daily.csv', ROOT / 'nq' / 'nq_monthly_orb_st_runner.csv', 20.0),
]


def max_drawdown(values: Iterable[float]) -> float:
    series = pd.Series(list(values), dtype=float)
    if series.empty:
        return 0.0
    equity = series.cumsum()
    return float((equity - equity.cummax()).min())


def weekly_bull(wk: object) -> bool:
    return str(wk) == 'up'


def close_inside(c: float, rh: float, rl: float) -> bool:
    return rl <= c <= rh


def dd_long_pct(entry: float, low: float, r_width: float) -> float:
    if r_width <= 0:
        return 100.0
    return round(max(0.0, (entry - low) / r_width) * 100, 2)


def load_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=['date'])
    df['date'] = df['date'].dt.date
    return df.sort_values('date').reset_index(drop=True)


def attach_weekly_st(
    daily: pd.DataFrame,
    atr_length: int,
    atr_multiplier: float,
) -> pd.DataFrame:
    work = daily.copy()
    work['date'] = pd.to_datetime(work['date'])
    mapped = calculate_weekly_atr_trailing_stop_on_daily(work, atr_length, atr_multiplier)
    out = mapped.rename(
        columns={'atr_trend': 'weekly_atr_trend', 'atr_stop': 'weekly_atr_stop'}
    )
    out['date'] = out['date'].dt.date
    return out


def simulate(df: pd.DataFrame) -> tuple[list[dict], str]:
    """Return (trade ledger rows dicts, instrument symbol string)."""

    trades: list[dict] = []

    def rec(
        leg: str,
        gid: int,
        origin_ym: tuple[int, int],
        entry_px: float,
        exit_px: float,
        result: str,
        reason: str,
        entry_d: object,
        exit_d: object,
        dd_pct: float,
    ) -> None:
        trades.append(
            {
                'Leg': leg,
                'Group_Id': gid,
                'Origin_YM': f'{origin_ym[0]}-{origin_ym[1]:02d}',
                'Entry_Price': entry_px,
                'Exit_Price': exit_px,
                'Trade_PL': round(exit_px - entry_px, 6),
                'Drawdown_Pct': dd_pct,
                'Result': result,
                'Entry_Date': entry_d,
                'Exit_Date': exit_d,
                'Exit_Reason': reason,
            }
        )

    sym = str(df.iloc[0].get('symbol', 'MNQ')) if len(df) else 'MNQ'

    runners: list[dict] = []

    ym_prev: tuple[int, int] | None = None
    v_bar_ix = 0
    v_rh = v_rl = float('nan')
    v_or_live = False
    v_r = float('nan')

    phase = WAIT_BREAKOUT
    direction_long = False
    opened_trades = 0
    next_gid = 1

    open_scalp: dict | None = None

    weekly_prev: object | None = None
    prev_row: pd.Series | None = None

    def post_or() -> bool:
        return v_or_live and not math.isnan(v_r) and v_r > 0 and v_bar_ix > OR_LEN

    def matching_runner_gid(gid: int, oym: tuple[int, int]) -> dict | None:
        return next((r for r in runners if r['gid'] == gid and r['origin'] == oym), None)

    def exit_runners(h: float, l: float, c: float, d: object, wk: object, ym_bar: tuple[int, int]) -> None:
        nonlocal runners
        keep: list[dict] = []
        for rn in runners:
            oym = rn['origin']
            ent = rn['entry']
            rh_s = rn['rh']
            rl_s = rn['rl']
            rw = rh_s - rl_s

            hit = False
            bundled = (
                open_scalp is not None
                and rn['gid'] == open_scalp['gid']
                and oym == open_scalp['ym']
            )
            if l < rl_s and not bundled:

                rec(
                    'Runner',
                    rn['gid'],
                    oym,
                    ent,
                    rl_s,
                    'Loss',
                    'Stop_RL',
                    rn['entry_date'],
                    d,
                    dd_long_pct(ent, l, rw),
                )
                hit = True

            elif (
                weekly_prev is not None
                and weekly_bull(weekly_prev)
                and not weekly_bull(wk)
            ):
                rec(
                    'Runner',
                    rn['gid'],
                    oym,
                    ent,
                    c,
                    'Win' if c > ent else 'Loss',
                    'Weekly_ST_Down_Flip',
                    rn['entry_date'],
                    d,
                    dd_long_pct(ent, l, rw),
                )
                hit = True

            elif (
                oym == ym_bar
                and close_inside(c, rh_s, rl_s)
                and not weekly_bull(wk)
            ):
                rec(
                    'Runner',
                    rn['gid'],
                    oym,
                    ent,
                    c,
                    'Range-Close',
                    'Close_Back_Inside_Range_ST_Off',
                    rn['entry_date'],
                    d,
                    dd_long_pct(ent, l, rw),
                )
                hit = True

            if not hit:
                keep.append(rn)
        runners = keep

    def exit_scalp(h: float, l: float, c: float, d: object) -> None:
        nonlocal open_scalp, phase, direction_long
        if open_scalp is None:
            return
        ent = open_scalp['entry']
        tgt = open_scalp['target']
        stp = open_scalp['rl']
        rh_s = open_scalp['rh']
        rl_s = open_scalp['rl']
        rw = rh_s - rl_s

        if l < stp:

            gid = open_scalp['gid']
            oym = open_scalp['ym']
            rec(
                'Scalp',
                gid,
                oym,
                ent,
                stp,
                'Loss',
                'Stop',
                open_scalp['entry_date'],
                d,
                100.0,
            )

            rnr = matching_runner_gid(gid, oym)

            runners[:] = [r for r in runners if not (r['gid'] == gid and r['origin'] == oym)]
            rw = rh_s - rl_s
            if rnr is not None:
                rent = float(rnr['entry'])
                rec(
                    'Runner',
                    gid,
                    oym,
                    rent,
                    stp,
                    'Loss',
                    'Stop_RL',
                    rnr['entry_date'],
                    d,
                    dd_long_pct(rent, l, rw),
                )

            open_scalp = None
            phase = WAIT_BREAKOUT
            direction_long = False
            return

        if h >= tgt:
            rec(
                'Scalp',
                open_scalp['gid'],
                open_scalp['ym'],
                ent,
                tgt,
                'Win',
                'Target',
                open_scalp['entry_date'],
                d,
                dd_long_pct(ent, l, rw),
            )
            open_scalp = None
            phase = WAIT_BREAKOUT
            direction_long = False

            return

        if close_inside(c, rh_s, rl_s):
            rec(
                'Scalp',
                open_scalp['gid'],
                open_scalp['ym'],
                ent,
                c,
                'Range-Close',
                'Close_Back_Inside_Range',
                open_scalp['entry_date'],
                d,
                dd_long_pct(ent, l, rw),
            )
            open_scalp = None
            phase = WAIT_BREAKOUT
            direction_long = False

    def try_fill_same_bar_rescan(h: float, l: float, c: float, d: object, wk: object, ym_bar: tuple[int, int]) -> None:
        """After a new fill, allow same-bar RL / TP / restrict on the new scalp."""
        exit_runners(h, l, c, d, wk, ym_bar)
        exit_scalp(h, l, c, d)

    for idx, row in df.iterrows():
        d = row['date']
        ym_bar = (d.year, d.month)

        if ym_prev is None:
            ym_prev = ym_bar
            v_bar_ix = 1
            v_rh = float(row['high'])
            v_rl = float(row['low'])
            v_or_live = False
            v_r = float('nan')

        elif ym_bar != ym_prev:

            if open_scalp is not None and prev_row is not None:
                c_prev = float(prev_row['close'])
                l_prev = float(prev_row['low'])
                rw = open_scalp['rh'] - open_scalp['rl']
                rec(
                    'Scalp',
                    open_scalp['gid'],
                    open_scalp['ym'],
                    open_scalp['entry'],
                    c_prev,
                    'Period-Close',
                    'Month_Close',
                    open_scalp['entry_date'],
                    prev_row['date'],
                    dd_long_pct(open_scalp['entry'], l_prev, rw),
                )

            ym_prev = ym_bar
            opened_trades = 0
            phase = WAIT_BREAKOUT
            direction_long = False
            open_scalp = None

            v_bar_ix = 1
            v_rh = float(row['high'])
            v_rl = float(row['low'])
            v_or_live = False
            v_r = float('nan')
        else:
            v_bar_ix += 1

        sealing = not v_or_live and v_bar_ix <= OR_LEN
        if sealing:
            v_rh = max(v_rh, float(row['high']))
            v_rl = min(v_rl, float(row['low']))

        if not v_or_live and v_bar_ix == OR_LEN:
            rng = v_rh - v_rl
            v_r = rng if rng > 0 else float('nan')
            v_or_live = bool(rng > 0)

        h = float(row['high'])
        l = float(row['low'])
        c = float(row['close'])
        wk = row.get('weekly_atr_trend')

        exit_runners(h, l, c, d, wk, ym_bar)
        exit_scalp(h, l, c, d)

        if post_or() and (opened_trades < MAX_TRADES_PER_PERIOD or phase == WAIT_FILL):

            if phase == WAIT_FILL and direction_long:
                filled = False
                if weekly_bull(wk) and l <= v_rh:
                    gid = next_gid
                    next_gid += 1
                    epx = v_rh
                    open_scalp = {
                        'gid': gid,
                        'ym': ym_bar,
                        'entry': epx,
                        'target': v_rh + v_r,
                        'rl': v_rl,
                        'rh': v_rh,
                        'entry_date': d,
                    }
                    if weekly_bull(wk):
                        runners.append(
                            {
                                'gid': gid,
                                'origin': ym_bar,
                                'entry': epx,
                                'rl': v_rl,
                                'rh': v_rh,
                                'entry_date': d,
                            }
                        )

                    opened_trades += 1
                    phase = WAIT_BREAKOUT
                    direction_long = False

                    filled = True
                    try_fill_same_bar_rescan(h, l, c, d, wk, ym_bar)

                if not filled:
                    if not weekly_bull(wk):
                        phase = WAIT_BREAKOUT
                        direction_long = False

                    elif c < v_rl:
                        phase = WAIT_BREAKOUT
                        direction_long = False

            if phase == WAIT_BREAKOUT and opened_trades < MAX_TRADES_PER_PERIOD and post_or():
                if c > v_rh and weekly_bull(wk):
                    direction_long = True
                    if l <= v_rh:

                        gid = next_gid
                        next_gid += 1

                        epx = v_rh
                        open_scalp = {
                            'gid': gid,
                            'ym': ym_bar,
                            'entry': epx,

                            'target': v_rh + v_r,
                            'rl': v_rl,
                            'rh': v_rh,
                            'entry_date': d,
                        }
                        if weekly_bull(wk):
                            runners.append(
                                {
                                    'gid': gid,
                                    'origin': ym_bar,
                                    'entry': epx,
                                    'rl': v_rl,
                                    'rh': v_rh,
                                    'entry_date': d,
                                }
                            )

                        opened_trades += 1

                        direction_long = False

                        try_fill_same_bar_rescan(h, l, c, d, wk, ym_bar)

                    else:
                        phase = WAIT_FILL

                elif c > v_rh and not weekly_bull(wk):
                    direction_long = False

        weekly_prev = wk
        prev_row = row

    if open_scalp is not None and prev_row is not None:

        rw = open_scalp['rh'] - open_scalp['rl']
        rec(
            'Scalp',
            open_scalp['gid'],
            open_scalp['ym'],
            open_scalp['entry'],
            float(prev_row['close']),
            'Period-Close',
            'Series_End',
            open_scalp['entry_date'],
            prev_row['date'],
            dd_long_pct(open_scalp['entry'], float(prev_row['low']), rw),
        )

    if runners and prev_row is not None:

        cl = float(prev_row['close'])
        ll = float(prev_row['low'])
        dd_last = prev_row['date']

        for rn in list(runners):
            rw = rn['rh'] - rn['rl']
            rec(
                'Runner',
                rn['gid'],
                rn['origin'],
                rn['entry'],
                cl,
                'Period-Close',
                'Series_End',
                rn['entry_date'],
                dd_last,
                dd_long_pct(rn['entry'], ll, rw),
            )

    for t in trades:
        t['Symbol'] = sym
        t['Trade_Direction'] = 'Long'

    return trades, sym


def build_output_frame(df: pd.DataFrame, ledger: list[dict]) -> pd.DataFrame:

    df = df.copy()
    df['ym'] = df['date'].apply(lambda d: (d.year, d.month))
    sym = str(df.iloc[0].get('symbol', '')) if len(df) else ''

    ym_stats: dict[tuple[int, int], tuple[float, float, float, int]] = {}

    def period_label(ym: tuple[int, int]) -> str:
        return f'{ym[0]}-{ym[1]:02d}'

    for ym_g, grp in df.groupby('ym', sort=False):
        range_bars = grp.iloc[:3] if len(grp) >= 3 else grp
        trade_days = max(0, len(grp) - 3)
        rh = float(range_bars['high'].max()) if len(range_bars) else 0.0
        rl = float(range_bars['low'].min()) if len(range_bars) else 0.0
        ym_stats[ym_g] = (rh, rl, rh - rl, trade_days)

    rows: list[dict] = []
    exits_by_origin: dict[str, int] = {}

    for t in ledger:

        lbl = str(t['Origin_YM'])

        exits_by_origin[lbl] = exits_by_origin.get(lbl, 0) + 1

    for ym_k, tup in ym_stats.items():
        lbl = period_label(ym_k)
        if exits_by_origin.get(lbl, 0) == 0:

            rh, rl, rg, td = tup
            n_in_month = int(
                df['ym']
                .map(lambda x, k=ym_k: (int(x[0]), int(x[1])) == (int(k[0]), int(k[1])))
                .sum()
            )
            if rg > 0 and n_in_month >= 4:
                rows.append(
                    {
                        'Period': lbl,
                        'Leg': '-',
                        'Group_Id': -1,
                        'Origin_YM': lbl,
                        'Trade_Direction': 'No-Op',
                        'Entry_Price': None,
                        'Exit_Price': None,
                        'Trade_PL': 0.0,
                        'Drawdown_Pct': 0.0,
                        'Result': 'No-Op',
                        'Exit_Reason': 'No-Op',
                        **(
                            {'Symbol': sym, 'Range_High': rh, 'Range_Low': rl, 'Range': rg, 'Range_Days': 3, 'Trade_Days': td}
                        ),
                    }
                )

    for t in ledger:
        y, mo = map(int, str(t['Origin_YM']).split('-'))

        rh, rl, rg, td = ym_stats.get((y, mo), (float('nan'), float('nan'), float('nan'), 0))
        lbl = period_label((y, mo))
        rows.append(
            {
                **t,
                'Period': lbl,
                'Range_High': rh,
                'Range_Low': rl,
                'Range': rg,
                'Range_Days': 3,
                'Trade_Days': td,
            }
        )

    out = pd.DataFrame(rows)
    fills = out[out['Trade_Direction'] != 'No-Op'] if not out.empty else pd.DataFrame()
    if (
        isinstance(fills, pd.DataFrame)
        and not fills.empty
        and 'Trade_PL' in fills.columns
    ):
        fills_idx = fills.index
        out.loc[fills_idx, 'Cumulative_PL'] = fills['Trade_PL'].astype(float).cumsum().round(6)

    return out.sort_values(['Period', 'Group_Id', 'Leg'], kind='stable').reset_index(drop=True)


def runner_stats(out: pd.DataFrame) -> dict:
    rn = out[out['Leg'] == 'Runner']
    if rn.empty:
        return {}
    return {
        'runner_exits_stop_rl': int((rn['Exit_Reason'] == 'Stop_RL').sum()),
        'runner_exits_weekly_flip': int((rn['Exit_Reason'] == 'Weekly_ST_Down_Flip').sum()),
        'runner_restrictive_st_off': int((rn['Exit_Reason'] == 'Close_Back_Inside_Range_ST_Off').sum()),
        'runner_series_end': int((rn['Exit_Reason'] == 'Series_End').sum()),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--instrument', choices=['MNQ', 'NQ', 'all'], default='all')
    ap.add_argument('--daily', type=Path, default=None)
    ap.add_argument('--output', type=Path, default=None)
    ap.add_argument('--multiplier', type=float, default=None)
    ap.add_argument('--weekly-atr-len', type=int, default=14)
    ap.add_argument('--weekly-atr-mult', type=float, default=3.0)
    args = ap.parse_args()

    if args.instrument == 'all':
        runs = DEFAULT_RUNS
    else:
        base = next(x for x in DEFAULT_RUNS if x[0] == args.instrument)
        runs = [
            (
                args.instrument,
                args.daily or base[1],
                args.output or base[2],
                args.multiplier if args.multiplier is not None else base[3],
            )
        ]

    for inst, daily_path, out_path, mult in runs:
        raw = load_daily(daily_path)

        wd = attach_weekly_st(raw, args.weekly_atr_len, args.weekly_atr_mult)
        ledger, _ = simulate(wd)
        res = build_output_frame(wd, ledger)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        res.to_csv(out_path, index=False)
        fills = res[res['Trade_Direction'] != 'No-Op'].copy()
        print(f'{inst}: wrote {out_path}')
        print(f'  Scalp {fills["Leg"].eq("Scalp").sum()}  Runner {fills["Leg"].eq("Runner").sum()}')
        net = float(fills['Trade_PL'].astype(float).sum()) if not fills.empty else 0.0
        mdd = max_drawdown(fills['Trade_PL'].astype(float)) * mult if not fills.empty else 0.0
        print(f'  combined net pts {net:,.2f} (${net * mult:,.2f})  maxDD ${mdd:,.2f}')
        st = runner_stats(res)
        if st:
            print(
                '  runner exits — RL:', st['runner_exits_stop_rl'],
                'weekly↓:', st['runner_exits_weekly_flip'],
                'restrict:', st['runner_restrictive_st_off'],
                'open@series:', st['runner_series_end'],
            )

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
