#!/usr/bin/env python3
"""
Random annotated 5‑min MNQ charts for the **child-ladder** resim (`replay_row` status
``ok`` only): first scale at L0±15, adds at child candles, exit **all lots @ TP1**.

Style matches ``build_random_samples.py`` (entry/exit markers, TP1 + SL spans, pts + $).

Uses ``resim_scale_in_ladder.py`` (canonical system for this breakout folder).

Input: ``swept_liquidity_orb_breakout/mnq_swept_orb_breakout.csv``

Output: ``swept_liquidity_orb_breakout/child_ladder_trade_samples/<date>.png`` + INDEX.md
"""
from __future__ import annotations

import argparse
import importlib.util
import random
from datetime import time
from pathlib import Path

import databento as db
import pandas as pd
import pytz

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402


NY = pytz.timezone('America/New_York')
DBN_FILE = '/home/tester/hsm/potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'
ROOT = Path(__file__).resolve().parent
CSV_FILE = ROOT / 'swept_liquidity_orb_breakout' / 'mnq_swept_orb_breakout.csv'
OUT_DIR = ROOT / 'swept_liquidity_orb_breakout' / 'child_ladder_trade_samples'
TICK = 0.25
DEFAULT_SL_PTS = 70.0


def _load_resim_mod():
    path = ROOT / 'swept_liquidity_orb_breakout' / 'resim_scale_in_ladder.py'
    spec = importlib.util.spec_from_file_location('resim_ladder', path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


RESIM = _load_resim_mod()
DEFAULT_CHILD_OR_EDGE = float(getattr(RESIM, 'DEFAULT_CHILD_OR_EDGE', 5.0))


def day_df_for_symbol(df1: pd.DataFrame, sym: str) -> pd.DataFrame:
    if 'symbol' in df1.columns:
        dd = df1[df1['symbol'] == sym]
        return dd if not dd.empty else df1
    return df1


def load_dbn_once() -> dict:
    print(f'Loading DBN ({DBN_FILE}) ...')
    store = db.DBNStore.from_file(DBN_FILE)
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith('MNQ')].copy()
    df['ts_event'] = df['ts_event'].dt.tz_convert(NY)
    df['date'] = df['ts_event'].dt.date
    df['t'] = df['ts_event'].dt.time
    fm = (
        df.groupby(['date', 'symbol'])['volume'].sum().groupby(level='date').idxmax().apply(lambda x: x[1]).to_dict()
    )
    df = df[df.apply(lambda r: r['symbol'] == fm.get(r['date']), axis=1)]
    df = df[(df['t'] >= time(9, 30)) & (df['t'] < time(16, 0))].copy()
    df = df.set_index('ts_event').sort_index()
    by_date = {d: g for d, g in df.groupby(df.index.date)}
    print(f'  Loaded {len(by_date):,} trading days, {len(df):,} 1-min bars')
    return by_date


def trade_dates_with_ok_replay(csv: pd.DataFrame, by_date: dict, sl_pts: float, child_or_edge: float) -> list:
    """Dates where at least one filled CSV row replays with status ``ok``."""
    eligible: set = set()
    filled = csv[csv['Entry_Price'].notna()]
    for _, row in filled.iterrows():
        d = row['Date']
        if isinstance(d, str):
            d = pd.to_datetime(d).date()
        if d not in by_date:
            continue
        dd = day_df_for_symbol(by_date[d], row['Symbol'])
        if dd.empty:
            continue
        r = RESIM.replay_row(row, dd, sl_pts, child_or_edge)
        if r.get('status') == 'ok':
            eligible.add(d)
    return sorted(eligible)


def collect_ok_rows_for_day(
    day_rows: pd.DataFrame, day_df: pd.DataFrame, sl_pts: float, child_or_edge: float
) -> list[tuple[pd.Series, dict]]:
    out: list[tuple[pd.Series, dict]] = []
    sym = str(day_rows['Symbol'].iloc[0])
    dd = day_df_for_symbol(day_df, sym)
    for _, row in day_rows.iterrows():
        if pd.isna(row.get('Entry_Price')):
            continue
        m = RESIM.replay_row(row, dd, sl_pts, child_or_edge)
        if m.get('status') == 'ok':
            out.append((row, m))
    out.sort(key=lambda x: x[1]['fill_ts_first'])
    return out


def draw_chart(
    date_obj,
    df1: pd.DataFrame,
    ok_pairs: list[tuple[pd.Series, dict]],
    outpath: Path,
    sl_pts: float,
    child_or_edge: float,
):
    """Annotated chart matching ``build_random_samples.draw_chart`` (child-ladder replay)."""
    if not ok_pairs or df1.empty:
        return None

    sym = str(ok_pairs[0][0]['Symbol'])

    dd = day_df_for_symbol(df1, sym)
    rng_bars = dd[(dd.index.time >= time(9, 30)) & (dd.index.time < time(9, 45))]
    rh = float(rng_bars['high'].max())
    rl = float(rng_bars['low'].min())
    rv = rh - rl

    trades = []
    for row, meta in ok_pairs:
        trades.append(
            {
                'direction': str(row['Trade_Direction']),
                'entry': float(meta['avg_entry_px']),
                'exit_price': float(meta['exit_px']),
                'target': float(meta['tp1_px']),
                'stop': float(meta['sl_px']),
                'stop_child': float(meta['sl_child_px']),
                'rh_csv': float(row['RH']),
                'rl_csv': float(row['RL']),
                'result': str(meta['result']),
                'entry_time': meta['fill_ts_first'],
                'exit_time': meta['exit_ts'],
                'pl_pts': float(meta['Trade_PL_pts']),
                'net_usd': float(meta['Net_$']),
            }
        )

    bars5 = dd.resample('5T').agg(
        open=('open', 'first'),
        high=('high', 'max'),
        low=('low', 'min'),
        close=('close', 'last'),
    ).dropna(subset=['open'])

    pattern = '+'.join([f"{t['direction'][0]}{t['result'][0]}" for t in trades])
    total_pl = sum(t['pl_pts'] for t in trades)
    total_usd = sum(t['net_usd'] for t in trades)

    fig = plt.figure(figsize=(16, 9), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')

    ax.axvspan(bars5.index[0], bars5.index[0] + pd.Timedelta(minutes=15), color='#1F4E79', alpha=0.30, zorder=0)
    ax.axhline(rh, color='#E0E0E0', linestyle='--', linewidth=1.2, zorder=2)
    ax.axhline(rl, color='#E0E0E0', linestyle='--', linewidth=1.2, zorder=2)
    ax.axhspan(rl, rh, color='#1F4E79', alpha=0.10, zorder=0)
    ax.axhline(rh + TICK, color='#76FF03', linestyle=':', linewidth=1.0, alpha=0.8, zorder=2)
    ax.axhline(rl - TICK, color='#FF5252', linestyle=':', linewidth=1.0, alpha=0.8, zorder=2)

    for ts, row in bars5.iterrows():
        x = mdates.date2num(ts)
        width = 5 / (24 * 60) * 0.7
        is_up = row['close'] >= row['open']
        c = '#26A69A' if is_up else '#EF5350'
        ax.vlines(x, row['low'], row['high'], color=c, linewidth=0.8, zorder=3)
        body_lo = min(row['open'], row['close'])
        body_hi = max(row['open'], row['close'])
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, body_lo),
                width,
                max(body_hi - body_lo, 0.05),
                facecolor=c,
                edgecolor=c,
                alpha=0.95,
                zorder=3,
            )
        )

    color_for = {'Win': '#76FF03', 'Loss': '#FF1744', 'EOD-Win': '#69F0AE', 'EOD-Loss': '#FFB74D'}
    label_offset = [+24, -36, +48, -60]

    for i, t in enumerate(trades, 1):
        x_e = mdates.date2num(t['entry_time'])
        x_x = mdates.date2num(t['exit_time'])
        ax.scatter(
            [x_e],
            [t['entry']],
            marker='^' if t['direction'] == 'Long' else 'v',
            color='#FFC107',
            s=180,
            zorder=10,
            edgecolor='black',
            linewidth=1.5,
        )
        ax.annotate(
            f"#{i} {t['direction'][0]} entry @ {t['entry']:.2f}",
            xy=(x_e, t['entry']),
            xytext=(8, label_offset[(i - 1) % len(label_offset)]),
            textcoords='offset points',
            color='#FFC107',
            fontsize=8.5,
            fontweight='bold',
            zorder=10,
            ha='left',
            bbox=dict(boxstyle='round,pad=0.25', fc='#0D1B2A', ec='#FFC107', alpha=0.95),
            arrowprops=dict(arrowstyle='->', color='#FFC107', lw=0.7),
        )

        ax.plot([x_e, x_x], [t['target'], t['target']], color='#76FF03', linewidth=1.2, linestyle='-', alpha=0.7, zorder=4)
        ax.plot([x_e, x_x], [t['stop'], t['stop']], color='#FF1744', linewidth=1.3, linestyle='-', alpha=0.75, zorder=4)
        ax.plot(
            [x_e, x_x],
            [t['stop_child'], t['stop_child']],
            color='#FFA726',
            linewidth=1.0,
            linestyle='--',
            alpha=0.85,
            zorder=4,
        )

        c = color_for.get(t['result'], '#FFC107')
        ax.scatter(
            [x_x],
            [t['exit_price']],
            marker='X',
            color=c,
            s=180,
            zorder=10,
            edgecolor='black',
            linewidth=1.5,
        )
        ax.annotate(
            f"#{i} {t['result']} {t['pl_pts']:+.1f}pt (${t['net_usd']:+.0f})",
            xy=(x_x, t['exit_price']),
            xytext=(8, -label_offset[(i - 1) % len(label_offset)]),
            textcoords='offset points',
            color=c,
            fontsize=8.5,
            fontweight='bold',
            zorder=10,
            ha='left',
            bbox=dict(boxstyle='round,pad=0.25', fc='#0D1B2A', ec=c, alpha=0.95),
            arrowprops=dict(arrowstyle='->', color=c, lw=0.7),
        )

    last_x = mdates.date2num(bars5.index[-1]) + 0.005
    ax.text(last_x, rh, f' RH {rh:.2f}', color='#E0E0E0', fontsize=8, va='center')
    ax.text(last_x, rl, f' RL {rl:.2f}', color='#E0E0E0', fontsize=8, va='center')

    title = (
        f'{date_obj}  ·  {sym}  ·  Range {rv:.1f} pts  ·  Child ladder  ·  '
        f'tier1 SL L0±{sl_pts:.0f}  ·  child adds: long RH−{child_or_edge:.0f} / short RL+{child_or_edge:.0f}  '
        f'· TP1-only  ·  Pattern {pattern}'
    )
    any_eod = any(str(t['result']).startswith('EOD') for t in trades)
    subtitle = f"Net (child replay): {total_pl:+.2f} pts (${total_usd:+,.0f})"
    if any_eod:
        subtitle += ' · EOD = session close (can lie past SL lines)'
    fig.text(
        0.01,
        0.02,
        'SL: solid red = tier-1 (L0±) · dashed orange = child adds (RH- / RL+ buffer) · RH/RL = opening range bounds',
        color='#90A4AE',
        fontsize=9,
        ha='left',
        va='bottom',
    )
    ax.set_title(
        f'{title}\n{subtitle}',
        color='white',
        fontsize=13,
        fontweight='bold',
        pad=12,
        loc='left',
    )
    ax.set_xlabel('NY Time', color='#9FB3C8', fontsize=9)
    ax.set_ylabel(f'{sym} Price', color='#9FB3C8', fontsize=9)
    ax.tick_params(colors='#9FB3C8', labelsize=8)
    for s in ax.spines.values():
        s.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color='#9FB3C8')
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=NY))
    ax.set_xlim(
        bars5.index[0] - pd.Timedelta(minutes=10),
        bars5.index[-1] + pd.Timedelta(minutes=25),
    )

    plt.tight_layout()
    plt.savefig(outpath, dpi=120, bbox_inches='tight', facecolor='#0D1B2A')
    plt.close()
    return pattern, total_pl, total_usd, rv


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('-n', type=int, default=100, help='Number of random sample days (ok-replay only)')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--start', default='2024-01-01', help='Earliest date to consider in CSV')
    ap.add_argument('--sl-pts', type=float, default=DEFAULT_SL_PTS, help='Fixed SL distance from L0 (index points)')
    ap.add_argument(
        '--child-or-edge',
        type=float,
        default=DEFAULT_CHILD_OR_EDGE,
        help='Buffer inside OR for child stops: long RH−edge, short RL+edge (matches resim --child-or-edge)',
    )
    ap.add_argument('--dates', nargs='*', default=None, metavar='YYYY-MM-DD')
    ap.add_argument('--csv', type=str, default=str(CSV_FILE))
    args = ap.parse_args()

    sl_pts = float(args.sl_pts)
    child_or_edge = float(args.child_or_edge)
    csv_path = Path(args.csv)
    if not csv_path.is_file():
        raise SystemExit(f'Missing {csv_path}')

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    csv = pd.read_csv(csv_path)
    csv['Date'] = pd.to_datetime(csv['Date']).dt.date
    csv = csv[csv['Date'] >= pd.to_datetime(args.start).date()]
    filled = csv[csv['Entry_Price'].notna()]
    print(f'CSV rows with entry (from {args.start}): {len(filled)}')

    print('Scanning for dates with at least one child-ladder replay status=ok ...')
    by_date = load_dbn_once()
    eligible = trade_dates_with_ok_replay(csv, by_date, sl_pts, child_or_edge)
    print(f'  Eligible days (≥1 ok replay): {len(eligible):,}')

    if not eligible:
        raise SystemExit('No eligible dates — nothing to chart.')

    if args.dates:
        sampled = sorted({pd.Timestamp(d).date() for d in args.dates})
        sampled = [d for d in sampled if d in eligible]
        print(f'Drawing {len(sampled)} explicit dates (eligible only)')
    else:
        rng = random.Random(args.seed)
        sampled = sorted(rng.sample(eligible, min(args.n, len(eligible))))
        print(f'Sampling {len(sampled)} days from eligible set (seed={args.seed})')

    rows_index: list[dict] = []

    for i, d in enumerate(sampled, 1):
        if d not in by_date:
            print(f'  [{i:>3}/{len(sampled)}] {d}: no DBN day')
            continue
        df1 = by_date[d]
        day_rows = filled[filled['Date'] == d]
        if day_rows.empty:
            print(f'  [{i:>3}/{len(sampled)}] {d}: no CSV rows')
            continue

        ok_pairs = collect_ok_rows_for_day(day_rows, df1, sl_pts, child_or_edge)
        if not ok_pairs:
            print(f'  [{i:>3}/{len(sampled)}] {d}: no ok replays (unexpected for eligible)')
            continue

        outpath = OUT_DIR / f'{d}.png'
        try:
            res = draw_chart(d, df1, ok_pairs, outpath, sl_pts, child_or_edge)
            if res is None:
                continue
            pattern, total_pl, total_usd, rv = res
            sym = str(day_rows['Symbol'].iloc[0])
            rows_index.append(
                {
                    'date': d,
                    'symbol': sym,
                    'range': round(float(rv), 2),
                    'pattern': pattern,
                    'pl_pts': round(total_pl, 2),
                    'net_usd': round(total_usd, 2),
                    'n_trades': len(ok_pairs),
                }
            )
            print(
                f"  [{i:>3}/{len(sampled)}] {d} {sym} n={len(ok_pairs)} "
                f'pat={pattern:<12} pl={total_pl:>+7.1f}pt ${total_usd:>+8,.0f}'
            )
        except Exception as e:
            print(f'  [{i:>3}/{len(sampled)}] {d}: {e}')
            raise

    idx_path = OUT_DIR / 'INDEX.md'
    if args.dates:
        print('Skipping INDEX (--dates only)')
        print('Charts:', OUT_DIR)
        return 0

    with open(idx_path, 'w') as f:
        f.write('# Child ladder trade samples (canonical resim)\n\n')
        f.write(
            f'Child scale-in (`resim_scale_in_ladder.py`): first fill L0±15; optional adds '
            f'at child closes; tier-1 SL **L0 ± {sl_pts:.0f}**; child-add SL '
            f'**RH − {child_or_edge:.0f}** (long) / **RL + {child_or_edge:.0f}** (short); '
            f'exit **TP1-only** (all contracts). Charts = `replay_row` status **ok** only.\n\n'
        )
        f.write(f'Sampled with seed={args.seed}, start>={args.start}, pool={len(eligible):,} eligible days.\n\n')
        tot_usd = sum(r['net_usd'] for r in rows_index)
        f.write(f'**Sample Σ net (child ladder):** ${tot_usd:,.0f} over {len(rows_index)} charts.\n\n')
        f.write('| Date | Symbol | ORB pts | Pattern | Net pts | Net $ | Trades | PNG |\n')
        f.write('|---|---|---:|---|---:|---:|---:|---|\n')
        for r in sorted(rows_index, key=lambda x: x['date']):
            dd = r['date']
            f.write(
                f"| {dd} | {r['symbol']} | {r['range']} | {r['pattern']} | "
                f"{r['pl_pts']:+.2f} | ${r['net_usd']:+,.0f} | {r['n_trades']} | "
                f"[{dd}.png]({dd}.png) |\n"
            )
    print(f'Wrote {idx_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
