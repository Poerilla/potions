#!/usr/bin/env python3
"""
v2b / v2d performance restricted to **C3 setup days** (from ``setups.csv``).

Scenarios (×1 unless noted):
- Canon **v2b** OCO on C3 days (both sides, max 2 legs).
- **v2b extension**: long on bullish C3, short on bearish C3 only.
- **Tracker v2b scaleout** (×2 MNQ, TP1+runner) on C3 days; optional **MA50>MA150** filter.
- **v2d fade** on C3 days (both sides); **fade the extension** (short on bull C3, long on bear).
- **C3 study** (hit + swing + opposite v2b break) for reference.

Example::

  python3 compare_v2b_on_c3_days.py
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time
from pathlib import Path

import databento as db
import numpy as np
import pandas as pd
import pytz

HERE = Path(__file__).resolve().parent
MNQ_ROOT = HERE.parent.parent
V2D = MNQ_ROOT / 'v2d'
DAILY_DBN = MNQ_ROOT / 'raw' / 'glbx-mdp3-20100606-20260308.ohlcv-1d.dbn.zst'
DEFAULT_SETUPS = HERE.parent / 'daily_candlestick_theory' / 'setups.csv'
DEFAULT_DBN = HERE.parent.parent / 'raw' / 'extracted_new' / 'glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'
C3_CSV = HERE / 'backtest_c3_swing_orb_fade_trades_mnq.csv'

if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(V2D) not in sys.path:
    sys.path.insert(0, str(V2D))

import build_midnight_open_hourly_charts as mdata  # noqa: E402
from analyze_atr_fade_touch_excursions import leg_excursions, mtm_drawdown  # noqa: E402
from backtest_midnight_open_flip import ORB_HI, Trade, USD_PER_POINT, orb_v2b_targets  # noqa: E402
from compare_c3_vs_v2d_metrics import (  # noqa: E402
    BookStats,
    pf_from_pnl,
    simulate_v2d_ny_day,
    stats_from_pnl,
    stats_from_trades,
)
from run_adaptive_50_150_scaleout import (  # noqa: E402
    EOD_CUTOFF,
    FEE_RT,
    MULT,
    RTH_HI,
    RTH_LO,
    TICK,
    _EPS,
    find_fill_v2b_long,
    find_fill_v2b_short,
    find_fill_v2d_long,
    find_fill_v2d_short,
    path_after_prior,
    rth_slice,
    simulate_scale_out_leg,
    trade_params,
)

NY = pytz.timezone('America/New_York')
ORB_END = ORB_HI
SLIP = 1
USD_PP = USD_PER_POINT['mnq']


def daily_regime_v2b() -> pd.Series:
    store = db.DBNStore.from_file(str(DAILY_DBN))
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')].copy()
    df['date'] = pd.to_datetime(df['ts_event']).dt.date
    fm = df.loc[df.groupby('date')['volume'].idxmax()]
    close = fm.set_index('date').sort_index()['close']
    ma_fast = close.rolling(50).mean()
    ma_slow = close.rolling(150).mean()
    return (ma_fast > ma_slow).shift(1).fillna(True)


def load_c3_days(setups_csv: Path) -> dict[date, str]:
    df = pd.read_csv(setups_csv)
    out: dict[date, str] = {}
    for _, row in df.iterrows():
        d = date.fromisoformat(str(row['c3_date']))
        out[d] = str(row['direction'])
    return out


def simulate_v2b_ny_day(
    session_day: date,
    sess_1m: pd.DataFrame,
    *,
    allow_long: bool = True,
    allow_short: bool = True,
    usd_per_point: float = USD_PP,
) -> list[Trade]:
    """Canon v2b OCO (max 2 legs) with optional side filter."""
    orb = orb_v2b_targets(sess_1m, session_day)
    if orb is None:
        return []
    rh, rl, rv, _, _ = orb
    if rv <= 0:
        return []

    tick = TICK
    slip = SLIP * tick
    orb_ready = NY.localize(datetime.combine(session_day, ORB_END))
    session_end = NY.localize(datetime.combine(session_day, RTH_HI))

    long_trig = rh + tick
    short_trig = rl - tick
    long_entry = long_trig + slip
    short_entry = short_trig - slip

    arm_long = allow_long
    arm_short = allow_short
    trades: list[Trade] = []
    post = sess_1m[(sess_1m.index >= orb_ready) & (sess_1m.index < session_end)].sort_index()

    in_trade = False
    side = entry_px = stop_px = tp_px = entry_ts = None

    def open_t(s: str, ep: float, st: float, tg: float, ts: pd.Timestamp) -> None:
        nonlocal in_trade, side, entry_px, stop_px, tp_px, entry_ts
        in_trade = True
        side = s
        entry_px, stop_px, tp_px, entry_ts = ep, st, tg, ts

    def close_t(ts: pd.Timestamp, xp: float, reason: str) -> None:
        nonlocal in_trade, arm_long, arm_short
        trades.append(Trade(session_day, side, entry_ts, entry_px, ts, xp, reason, usd_per_point))
        if side == 'long':
            arm_long = False
        else:
            arm_short = False
        in_trade = False

    for ts, bar in post.iterrows():
        if ts.time() >= time(15, 55) and not in_trade:
            break
        hi, lo, op = float(bar['high']), float(bar['low']), float(bar['open'])

        if not in_trade and len(trades) < 2 and (arm_long or arm_short):
            lh = arm_long and hi >= long_trig
            sh = arm_short and lo <= short_trig
            if lh and sh:
                mid = (rh + rl) / 2
                if op >= mid and arm_short:
                    open_t('short', short_entry, rh, rl - rv, ts)
                    arm_short = False
                elif arm_long:
                    open_t('long', long_entry, rl, rh + rv, ts)
                    arm_long = False
            elif lh and arm_long:
                open_t('long', long_entry, rl, rh + rv, ts)
                arm_long = False
            elif sh and arm_short:
                open_t('short', short_entry, rh, rl - rv, ts)
                arm_short = False

        if in_trade:
            if side == 'long':
                if lo < stop_px:
                    close_t(ts, stop_px, 'sl_v2b')
                elif hi >= tp_px:
                    close_t(ts, tp_px, 'tp_v2b')
            else:
                if hi > stop_px:
                    close_t(ts, stop_px, 'sl_v2b')
                elif lo <= tp_px:
                    close_t(ts, tp_px, 'tp_v2b')
            if len(trades) >= 2 and not in_trade:
                break

    if in_trade and not post.empty:
        last_ts = post.index.max()
        close_t(last_ts, float(post.loc[last_ts, 'close']), 'session_16:00')

    return trades


def simulate_v2d_ny_day_filtered(
    session_day: date,
    sess_1m: pd.DataFrame,
    *,
    allow_long: bool = True,
    allow_short: bool = True,
) -> list[Trade]:
    all_t = simulate_v2d_ny_day(session_day, sess_1m)
    out: list[Trade] = []
    for t in all_t:
        if t.side == 'long' and not allow_long:
            continue
        if t.side == 'short' and not allow_short:
            continue
        out.append(t)
        if len(out) >= 2:
            break
    return out


def scaleout_legs_day(
    session_day: date,
    day_raw: pd.DataFrame,
    *,
    regime: str,
    directions: list[str],
) -> list[float]:
    """Returns net USD per scaleout leg (×2 MNQ, fees included)."""
    rth = rth_slice(day_raw, session_day)
    if rth.empty:
        return []
    rh = float(rth[rth.index.map(lambda t: t.time() < ORB_END)]['high'].max())
    rl = float(rth[rth.index.map(lambda t: t.time() < ORB_END)]['low'].min())
    rv = rh - rl
    if rv <= _EPS:
        return []

    nets: list[float] = []
    prior_exit: pd.Timestamp | None = None

    for direction in directions:
        if len(nets) >= 2:
            break
        pm = trade_params(regime, direction, rh, rl, rv)
        if pm is None:
            continue
        sub = path_after_prior(rth, session_day, prior_exit)
        if sub.empty:
            continue
        if regime == 'v2b':
            if direction == 'Long':
                fts, _ = find_fill_v2b_long(sub, rh)
            else:
                fts, _ = find_fill_v2b_short(sub, rl)
        elif direction == 'Long':
            fts, _ = find_fill_v2d_long(sub, rl)
        else:
            fts, _ = find_fill_v2d_short(sub, rh)
        if fts is None:
            continue
        net_usd, _, exit_ts, _, _, _ = simulate_scale_out_leg(
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
        nets.append(net_usd)
        if exit_ts is not None:
            prior_exit = exit_ts

    return nets


def extension_sides(direction: str) -> tuple[bool, bool]:
    """C2 extension direction → (allow_long, allow_short) for v2b."""
    if direction == 'bullish':
        return True, False
    return False, True


def fade_extension_sides(direction: str) -> tuple[bool, bool]:
    """Fade the extension move (v2d after opposite OR break)."""
    if direction == 'bullish':
        return False, True  # short fade after up break
    return True, False


def print_table(rows: list[BookStats], title: str) -> None:
    print(f'\n## {title}\n', flush=True)
    print(
        '| Scenario | Legs | Net | Win% | PF | Median | Closed DD | MTM DD | Net/MTM |',
        flush=True,
    )
    print('|---|---:|---:|---:|---:|---:|---:|---:|---:|', flush=True)
    for r in rows:
        pf = f'{r.pf:.2f}' if np.isfinite(r.pf) else '—'
        mtm = f'${r.mtm_dd:,.0f}' if np.isfinite(r.mtm_dd) else '—'
        npm = f'{r.net_per_dd:.2f}' if np.isfinite(r.net_per_dd) else '—'
        print(
            f'| {r.name} | {r.n} | ${r.net:,.0f} | {r.win_pct:.1f}% | {pf} | ${r.median:,.0f} | '
            f'${r.closed_dd:,.0f} | {mtm} | {npm} |',
            flush=True,
        )
        if r.note:
            print(f'| _{r.note}_ | | | | | | | | |', flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('Example::')[0].strip())
    ap.add_argument('--dbn', type=Path, default=DEFAULT_DBN)
    ap.add_argument('--setups-csv', type=Path, default=DEFAULT_SETUPS)
    args = ap.parse_args()

    if not args.setups_csv.is_file() or not args.dbn.is_file():
        print('Missing setups or DBN', file=sys.stderr)
        return 1

    c3_days = load_c3_days(args.setups_csv)
    regime = daily_regime_v2b()

    print('Loading 1m DBN ...', flush=True)
    gby = mdata.load_1m_by_ny_date(args.dbn.resolve(), 'mnq')

    v2b_all: list[Trade] = []
    v2b_ext: list[Trade] = []
    v2d_all: list[Trade] = []
    v2d_fade_ext: list[Trade] = []
    scale_v2b_all: list[float] = []
    scale_v2b_ext: list[float] = []
    scale_v2b_adaptive: list[float] = []

    n_c3_with_bars = 0
    n_adaptive_v2b_days = 0

    for session_day, direction in sorted(c3_days.items()):
        raw = gby.get(session_day)
        if raw is None:
            continue
        sess = mdata.slice_session_1m(raw, session_day)
        if sess.empty:
            continue
        n_c3_with_bars += 1

        allow_l, allow_s = extension_sides(direction)
        fl, fs = fade_extension_sides(direction)

        v2b_all.extend(simulate_v2b_ny_day(session_day, sess))
        v2b_ext.extend(simulate_v2b_ny_day(session_day, sess, allow_long=allow_l, allow_short=allow_s))
        v2d_all.extend(simulate_v2d_ny_day(session_day, sess))
        v2d_fade_ext.extend(
            simulate_v2d_ny_day_filtered(session_day, sess, allow_long=fl, allow_short=fs)
        )

        dirs_both = ['Long', 'Short']
        dirs_ext = ['Long'] if allow_l else ['Short']
        scale_v2b_all.extend(scaleout_legs_day(session_day, raw, regime='v2b', directions=dirs_both))
        scale_v2b_ext.extend(scaleout_legs_day(session_day, raw, regime='v2b', directions=dirs_ext))

        is_v2b_regime = bool(regime.loc[session_day]) if session_day in regime.index else True
        if is_v2b_regime:
            n_adaptive_v2b_days += 1
            scale_v2b_adaptive.extend(scaleout_legs_day(session_day, raw, regime='v2b', directions=dirs_both))

    rows: list[BookStats] = []

    rows.append(
        stats_from_trades(
            'Canon v2b OCO (×1) — C3 days, both sides',
            v2b_all,
            gby,
            note=f'{n_c3_with_bars} C3 calendar days with session data',
        )
    )
    rows.append(
        stats_from_trades(
            'v2b OCO (×1) — C3 days, **with** C2 extension',
            v2b_ext,
            gby,
            note='Bull C3 → long break only; bear C3 → short break only',
        )
    )
    rows.append(
        stats_from_pnl(
            'Tracker v2b scaleout (×2) — C3 days, both sides',
            np.array(scale_v2b_all),
            note='TP1+runner; same rules as STRATEGY_TRACKER leader',
        )
    )
    rows.append(
        stats_from_pnl(
            'Tracker v2b scaleout (×2) — C3 + MA50>MA150 days',
            np.array(scale_v2b_adaptive),
            note=f'v2b regime on {n_adaptive_v2b_days}/{n_c3_with_bars} C3 days',
        )
    )
    rows.append(
        stats_from_pnl(
            'Tracker v2b scaleout (×2) — C3 days, extension only',
            np.array(scale_v2b_ext),
            note='Long on bull C3 / short on bear C3',
        )
    )
    rows.append(
        stats_from_trades(
            'v2d fade (×1) — C3 days, both fade sides',
            v2d_all,
            gby,
            note='Canon v2d; up to 2 legs/day',
        )
    )
    rows.append(
        stats_from_trades(
            'v2d fade (×1) — C3 days, **fade extension**',
            v2d_fade_ext,
            gby,
            note='Bull C3 → short fade; bear C3 → long fade',
        )
    )

    if C3_CSV.is_file():
        from compare_c3_vs_v2d_metrics import load_trades

        c3_trades = [t for t in load_trades(C3_CSV) if t.session in c3_days]
        rows.append(
            stats_from_trades(
                'C3 study: hit + swing + **opposite** v2b break (×1)',
                c3_trades,
                gby,
                note='Current research branch',
            )
        )

    # Full-book context from scaleout CSV (all days, v2b only)
    so_path = V2D / 'adaptive_50_150_scaleout_legs.csv'
    if so_path.is_file():
        so = pd.read_csv(so_path)
        so['date_iso'] = pd.to_datetime(so['date_iso']).dt.date
        v2b_only = so[so['regime'] == 'v2b']['scaleout_net_2ct'].astype(float).values
        rows.append(
            stats_from_pnl(
                'Reference: tracker v2b scaleout ALL days (×2)',
                v2b_only,
                note='STRATEGY_TRACKER leader baseline; not C3-filtered',
            )
        )

    print_table(rows, f'v2b / v2d on C3 setup days ({len(c3_days)} setups, {n_c3_with_bars} with 1m data)')

    print('\n### Read-through\n', flush=True)
    print(
        '- **Extension-aligned v2b** = breakout **with** the C2 hit (long if bull C3, short if bear).',
        flush=True,
    )
    print(
        '- **Fade extension** = canon **v2d** (fade **against** the extension after opposite OR break).',
        flush=True,
    )
    print(
        '- **C3 opposite break** = v2b entry **against** the extension (after hit + swing); different from both rows above.',
        flush=True,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
