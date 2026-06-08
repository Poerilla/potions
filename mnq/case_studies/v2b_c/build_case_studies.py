#!/usr/bin/env python3
"""
v2b + child scale-in **case studies** (annotated PNGs).

Reads CSV from ``v2b_child`` (default: 3-contract-cap) or unified **adaptive** child CSV
(``--adaptive`` → ``mnq/v2d/mnq_orb_results_adaptive_50_150_child_3max.csv``). Charts label tier-1 as
**OCO** (``Regime=v2b``) or **fade** (``Regime=v2d``); bracket **TP_Price** / **Stop_Price** plus child segments.

Generate CSV::

  cd ../v2b_child && python3 orb_open_limit_v2b_child.py --max-child-adds 2 \\
      --out mnq_orb_open_limit_v2b_child_3max.csv

Adaptive (**50/150 + children**)::

  cd ../../v2d && python3 orb_adaptive_50_150_child.py --max-child-adds 2 \\
      --out mnq_orb_results_adaptive_50_150_child_3max.csv

  cd ../case_studies/v2b_c && python3 build_case_studies.py --adaptive --stratify-regimes -n 36 --seed 43 --start 2024-01-01

With ``--adaptive``, PNGs default to ``case_studies/adaptive_c/`` (override with ``--out-dir``).
"""
from __future__ import annotations

import argparse
import math
import random
from datetime import time
from pathlib import Path
from typing import Optional

import databento as db
import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd
import pytz

NY = pytz.timezone('America/New_York')
DBN_FILE = '/home/tester/hsm/potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst'
_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parent
MNQ_ROOT = _HERE.parent.parent
CSV_DEFAULT = ROOT / 'v2b_child' / 'mnq_orb_open_limit_v2b_child_3max.csv'
ADAPTIVE_CHILD_CSV_DEFAULT = MNQ_ROOT / 'v2d' / 'mnq_orb_results_adaptive_50_150_child_3max.csv'
ADAPTIVE_OUT_DEFAULT = ROOT / 'adaptive_c'
OUT_DIR = _HERE
TICK = 0.25


def resample_5m_anchor_0930(df1: pd.DataFrame) -> pd.DataFrame:
    ix0 = df1.index[0]
    anchor = ix0.normalize() + pd.Timedelta(hours=9, minutes=30)
    return (
        df1.resample('5min', label='left', closed='left', origin=anchor)
        .agg(open=('open', 'first'), high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
        .dropna(subset=['open'])
    )


def load_dbn_once():
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
    print(f'  Loaded {len(by_date):,} trading days')
    return by_date


def _ts(series_val, ix_tz) -> Optional[pd.Timestamp]:
    if pd.isna(series_val) or str(series_val).strip() == '':
        return None
    ts = pd.to_datetime(series_val)
    if ix_tz is not None:
        ts = ts.tz_convert(ix_tz) if ts.tzinfo else ts.tz_localize(NY)
    return ts


def _f(x) -> Optional[float]:
    if pd.isna(x) or x == '':
        return None
    try:
        v = float(x)
        if isinstance(v, float) and (math.isnan(v)):
            return None
        return v
    except (TypeError, ValueError):
        return None


def draw_chart(date_obj, df1: pd.DataFrame, csv_rows: pd.DataFrame, outpath: Path):
    """PNG renderer. When CSV rows include ``Regime`` (``v2b`` / ``v2d``), titles and tier‑1 labels adapt."""
    if df1.empty:
        return None
    rng_bars = df1[(df1.index.time >= time(9, 30)) & (df1.index.time < time(9, 45))]
    rh = float(rng_bars['high'].max())
    rl = float(rng_bars['low'].min())
    rv = rh - rl
    ix_tz = df1.index.tz

    legs = []
    for _, r in csv_rows.iterrows():
        d = str(r['Trade_Direction'])
        if pd.notna(r.get('TP_Price')):
            target = float(r['TP_Price'])
        else:
            target = rh + rv if d == 'Long' else rl - rv
        stop = float(r['Stop_Price']) if pd.notna(r.get('Stop_Price')) else (rl if d == 'Long' else rh)
        e_time = _ts(r['Entry_Time'], ix_tz)
        x_time = _ts(r['Exit_Time'], ix_tz)
        if e_time is None or x_time is None:
            continue
        if str(r['Result']).startswith('EOD'):
            x_time = df1.index[-1]
        net_usd = float(r['Net_$'])
        ncx = int(r['Contracts']) if pd.notna(r.get('Contracts')) else 1
        tier1 = _f(r.get('Tier1_Entry'))
        if tier1 is None:
            tier1 = float(r['Entry_Price'])

        legs.append(
            {
                'direction': d,
                'tier1_px': tier1,
                'tier1_ts': e_time,
                'avg_entry': float(r['Entry_Price']),
                'exit_price': float(r['Exit_Price']),
                'target': target,
                'stop': stop,
                'result': r['Result'],
                'exit_time': x_time,
                'pl_pts': float(r['Trade_PL']),
                'net_usd': net_usd,
                'contracts': ncx,
                'child1_lim': _f(r.get('Child_Limit_Price')),
                'child1_live': _ts(r.get('Child_Limit_Live_After'), ix_tz),
                'child1_fill': _ts(r.get('Child1_Fill_Time'), ix_tz),
                'child2_lim': _f(r.get('Child2_Limit_Price')),
                'child2_live': _ts(r.get('Child2_Limit_Live_After'), ix_tz),
                'child2_fill': _ts(r.get('Child2_Fill_Time'), ix_tz),
                'child_partial_count': int(float(r.get('Child_Partial_Exit_Count', 0) or 0))
                if pd.notna(r.get('Child_Partial_Exit_Count', 0))
                else 0,
                'child_partial_time': _ts(r.get('Child_Partial_Exit_Time'), ix_tz),
                'child_partial_price': _f(r.get('Child_Partial_Exit_Price')),
                'child_partial_reason': str(r.get('Child_Partial_Exit_Reason', '') or ''),
            }
        )

    bars5 = resample_5m_anchor_0930(df1)
    pattern = '+'.join([f"{L['direction'][0]}{str(L['result'])[0]}" for L in legs])
    sum_idx = sum(L['pl_pts'] for L in legs)
    day_net_usd = sum(L['net_usd'] for L in legs)
    sym = csv_rows['Symbol'].iloc[0]

    regime = None
    if 'Regime' in csv_rows.columns and len(csv_rows):
        regime = str(csv_rows['Regime'].iloc[0])
    tier1_word = 'fade' if regime == 'v2d' else 'OCO'
    if regime == 'v2d':
        suite_tag = 'adaptive · v2d'
        footer_lines = (
            'Gold = fade tier-1 · cyan add1 · magenta add2 · TP/Stop from CSV (v2d bracket); '
            'child rules match v2b_child (5 m RH/RL)'
        )
    elif regime == 'v2b':
        suite_tag = 'adaptive · v2b'
        footer_lines = (
            'Gold = OCO tier-1 fill · cyan add1 · magenta add2 · SL at RL/RH boundary · TP = RH+RV / RL−RV'
        )
    else:
        suite_tag = 'v2b_c'
        footer_lines = (
            'Gold = OCO tier-1 fill · cyan add1 · magenta add2 · SL at RL/RH boundary · TP = RH+RV / RL−RV'
        )
    if 'Child_Partial_Stop' in csv_rows.columns and str(csv_rows['Child_Partial_Stop'].iloc[0]) == '15m_close_inside':
        suite_tag = 'v2b_c · child 15m close stop'
        footer_lines += ' · orange circle = child-only exit on completed 15 m close back inside OR boundary'

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
    label_offset = [+28, -40, +52, -64]

    for i, L in enumerate(legs, 1):
        xd = mdates.date2num(L['tier1_ts'])
        ax.scatter(
            [xd],
            [L['tier1_px']],
            marker='^' if L['direction'] == 'Long' else 'v',
            color='#FFC107',
            s=200,
            zorder=11,
            edgecolor='black',
            linewidth=1.5,
        )
        ax.annotate(
            f'#{i} tier1 {tier1_word} ({L["contracts"]}µ) @ {L["tier1_px"]:.2f}',
            xy=(xd, L['tier1_px']),
            xytext=(10, label_offset[(i - 1) % len(label_offset)]),
            textcoords='offset points',
            color='#FFC107',
            fontsize=8.5,
            fontweight='bold',
            zorder=11,
            bbox=dict(boxstyle='round,pad=0.25', fc='#0D1B2A', ec='#FFC107', alpha=0.95),
            arrowprops=dict(arrowstyle='->', color='#FFC107', lw=0.7),
        )

        xe = mdates.date2num(L['exit_time'])
        ax.plot([xd, xe], [L['target'], L['target']], color='#76FF03', linewidth=1.0, linestyle='-', alpha=0.65, zorder=4)
        ax.plot([xd, xe], [L['stop'], L['stop']], color='#FF1744', linewidth=1.0, linestyle='-', alpha=0.65, zorder=4)

        x_end = xe
        child_line_end = mdates.date2num(L['child_partial_time']) if L['child_partial_time'] is not None else x_end
        if L['child1_lim'] is not None and L['child1_live'] is not None:
            x0 = mdates.date2num(L['child1_live'])
            ax.hlines(L['child1_lim'], x0, child_line_end, colors='#00E5FF', linestyles='--', linewidth=1.2, alpha=0.9, zorder=5)
            ax.annotate(
                f'add1 lim {L["child1_lim"]:.2f}',
                xy=(x0, L['child1_lim']),
                xytext=(6, -22),
                textcoords='offset points',
                color='#00E5FF',
                fontsize=8,
                zorder=11,
            )
        if L['child1_fill'] is not None and L['child1_lim'] is not None:
            xf = mdates.date2num(L['child1_fill'])
            ax.scatter([xf], [L['child1_lim']], marker='s', color='#00E5FF', s=120, zorder=12, edgecolor='white', linewidth=1)
            ax.annotate(
                'add1 fill',
                xy=(xf, L['child1_lim']),
                xytext=(6, 14),
                textcoords='offset points',
                color='#00E5FF',
                fontsize=8,
                fontweight='bold',
                zorder=12,
            )

        if L['child2_lim'] is not None and L['child2_live'] is not None:
            x0 = mdates.date2num(L['child2_live'])
            ax.hlines(L['child2_lim'], x0, child_line_end, colors='#E040FB', linestyles='--', linewidth=1.2, alpha=0.9, zorder=5)
            ax.annotate(
                f'add2 lim {L["child2_lim"]:.2f}',
                xy=(x0, L['child2_lim']),
                xytext=(6, -36),
                textcoords='offset points',
                color='#E040FB',
                fontsize=8,
                zorder=11,
            )
        if L['child2_fill'] is not None and L['child2_lim'] is not None:
            xf = mdates.date2num(L['child2_fill'])
            ax.scatter([xf], [L['child2_lim']], marker='D', color='#E040FB', s=110, zorder=12, edgecolor='white', linewidth=1)
            ax.annotate(
                'add2 fill',
                xy=(xf, L['child2_lim']),
                xytext=(6, 18),
                textcoords='offset points',
                color='#E040FB',
                fontsize=8,
                fontweight='bold',
                zorder=12,
            )

        if L['child_partial_count'] > 0 and L['child_partial_time'] is not None and L['child_partial_price'] is not None:
            xp = mdates.date2num(L['child_partial_time'])
            ax.scatter(
                [xp],
                [L['child_partial_price']],
                marker='o',
                color='#FFB74D',
                s=145,
                zorder=12,
                edgecolor='black',
                linewidth=1.2,
            )
            ax.annotate(
                f'child close-out x{L["child_partial_count"]}',
                xy=(xp, L['child_partial_price']),
                xytext=(8, -24),
                textcoords='offset points',
                color='#FFB74D',
                fontsize=8,
                fontweight='bold',
                zorder=12,
            )

        cc = color_for.get(str(L['result']), '#FFC107')
        ax.scatter([xe], [L['exit_price']], marker='X', color=cc, s=190, zorder=11, edgecolor='black', linewidth=1.5)
        ax.annotate(
            f'#{i} {L["result"]} {L["pl_pts"]:+.1f}pt (${L["net_usd"]:+.0f})',
            xy=(xe, L['exit_price']),
            xytext=(10, -label_offset[(i - 1) % len(label_offset)]),
            textcoords='offset points',
            color=cc,
            fontsize=8.5,
            fontweight='bold',
            zorder=11,
            bbox=dict(boxstyle='round,pad=0.25', fc='#0D1B2A', ec=cc, alpha=0.95),
            arrowprops=dict(arrowstyle='->', color=cc, lw=0.7),
        )

    last_x = mdates.date2num(bars5.index[-1]) + 0.005
    ax.text(last_x, rh, f' RH {rh:.2f}', color='#E0E0E0', fontsize=8, va='center')
    ax.text(last_x, rl, f' RL {rl:.2f}', color='#E0E0E0', fontsize=8, va='center')

    fig.text(0.01, 0.02, footer_lines, color='#90A4AE', fontsize=9, ha='left', va='bottom')

    title = f'{date_obj}  ·  {sym}  ·  Range {rv:.1f} pts  ·  {suite_tag}  ·  Pattern {pattern}'
    subtitle = f'Day net (all legs): ${day_net_usd:+,.2f}  ·  Σ pts: {sum_idx:+,.2f}'
    ax.set_title(f'{title}\n{subtitle}', color='white', fontsize=13, fontweight='bold', pad=12, loc='left')
    ax.set_xlabel('NY Time', color='#9FB3C8', fontsize=9)
    ax.set_ylabel(f'{sym} Price', color='#9FB3C8', fontsize=9)
    ax.tick_params(colors='#9FB3C8', labelsize=8)
    for s in ax.spines.values():
        s.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color='#9FB3C8')
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M', tz=NY))
    ax.set_xlim(bars5.index[0] - pd.Timedelta(minutes=10), bars5.index[-1] + pd.Timedelta(minutes=25))

    plt.tight_layout()
    plt.savefig(outpath, dpi=120, bbox_inches='tight', facecolor='#0D1B2A')
    plt.close()
    return pattern, day_net_usd, sum_idx, rv


def main() -> int:
    _help_epilog = """\
Example runs:
  v2b_child-only charts (default CSV ../v2b_child/mnq_orb_open_limit_v2b_child_3max.csv):
    cd potions/mnq/case_studies/v2b_c
    python3 build_case_studies.py -n 36 --seed 43 --start 2024-01-01

  Adaptive 50/150 + children → PNG/s under ../adaptive_c/:
    python3 build_case_studies.py --adaptive --stratify-regimes -n 36 --seed 43 --start 2024-01-01

  Explicit calendar days (no INDEX.md):
    python3 build_case_studies.py --csv ../path/to/legs.csv --dates 2025-03-31 2025-04-02

Outputs:
  One PNG per sampled date (--out-dir or defaults), named YYYY-MM-DD.png.
  Unless --dates is set: INDEX.md listing dates, pattern codes, day Net_$.
  Loads MNQ 1 m DBN once; stderr prints progress lines.
"""

    ap = argparse.ArgumentParser(
        description='ORB case study charts (v2b_c or adaptive+v2d)',
        epilog=_help_epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument('--csv', type=str, default=None, help='Leg CSV (default: v2b_child 3max, or adaptive with --adaptive)')
    ap.add_argument('--adaptive', action='store_true', help=f'Use unified adaptive child CSV ({ADAPTIVE_CHILD_CSV_DEFAULT.name})')
    ap.add_argument(
        '--out-dir',
        type=str,
        default=None,
        help=f'PNG folder (default: v2b_c here, or {ADAPTIVE_OUT_DEFAULT.name} with --adaptive)',
    )
    ap.add_argument(
        '--stratify-regimes',
        action='store_true',
        help='Balance v2b vs v2d session days when CSV has Regime column (half/half, fill remainder randomly)',
    )
    ap.add_argument('-n', type=int, default=36)
    ap.add_argument(
        '--sample-per-month',
        type=int,
        default=0,
        help='Sample up to N dates from each calendar month instead of one global random sample.',
    )
    ap.add_argument('--seed', type=int, default=43)
    ap.add_argument('--start', default='2024-01-01')
    ap.add_argument('--dates', nargs='*', default=None, metavar='YYYY-MM-DD')
    args = ap.parse_args()

    if args.csv:
        csv_path = Path(args.csv)
    elif args.adaptive:
        csv_path = ADAPTIVE_CHILD_CSV_DEFAULT
    else:
        csv_path = CSV_DEFAULT

    if not csv_path.is_file():
        msg = (
            f'Missing {csv_path}.\n'
            '  v2b_child: cd ../v2b_child && python3 orb_open_limit_v2b_child.py '
            '--max-child-adds 2 --out mnq_orb_open_limit_v2b_child_3max.csv\n'
            '  adaptive:  cd ../../v2d && python3 orb_adaptive_50_150_child.py '
            f'--max-child-adds 2 --out {ADAPTIVE_CHILD_CSV_DEFAULT.name}'
        )
        raise SystemExit(msg)

    if args.out_dir:
        out_dir = Path(args.out_dir)
    elif args.adaptive:
        out_dir = ADAPTIVE_OUT_DEFAULT
    else:
        out_dir = _HERE

    out_dir.mkdir(parents=True, exist_ok=True)

    csv = pd.read_csv(csv_path)
    csv['Date'] = pd.to_datetime(csv['Date']).dt.date
    csv = csv[csv['Date'] >= pd.to_datetime(args.start).date()]
    days_avail = sorted(csv['Date'].unique())
    print(f'CSV rows={len(csv)} days={len(days_avail)} from {args.start}  -> {out_dir}')

    has_regime = 'Regime' in csv.columns

    if args.dates:
        sampled = sorted({pd.Timestamp(d).date() for d in args.dates})
        sampled = [d for d in sampled if d in days_avail]
        print(f'Explicit dates: {len(sampled)}')
    elif args.sample_per_month > 0:
        rng = random.Random(args.seed)
        by_month: dict[str, list] = {}
        for d in days_avail:
            by_month.setdefault(pd.Timestamp(d).strftime('%Y-%m'), []).append(d)
        sampled = []
        for _, month_days in sorted(by_month.items()):
            sampled.extend(sorted(rng.sample(month_days, min(args.sample_per_month, len(month_days)))))
        sampled = sorted(sampled)
        print(f'Sampled up to {args.sample_per_month} per month: n={len(sampled)} seed={args.seed}')
    elif args.stratify_regimes and has_regime:
        day_reg = csv.groupby('Date')['Regime'].first()
        days_v2b = [d for d in days_avail if day_reg.get(d) == 'v2b']
        days_v2d = [d for d in days_avail if day_reg.get(d) == 'v2d']
        rng = random.Random(args.seed)
        half = args.n // 2
        s_v2b = rng.sample(days_v2b, min(half, len(days_v2b))) if days_v2b else []
        s_v2d = rng.sample(days_v2d, min(half, len(days_v2d))) if days_v2d else []
        sampled = sorted(set(s_v2b + s_v2d))
        pool = [d for d in days_avail if d not in sampled]
        need = args.n - len(sampled)
        if need > 0 and pool:
            sampled.extend(rng.sample(pool, min(need, len(pool))))
            sampled = sorted(sampled)
        print(
            f'Stratified Regime sample n={len(sampled)} (≤{half} v2b + ≤{half} v2d where possible) seed={args.seed}'
        )
    else:
        rng = random.Random(args.seed)
        sampled = sorted(rng.sample(days_avail, min(args.n, len(days_avail))))
        print(f'Random sample n={len(sampled)} seed={args.seed}')

    by_date = load_dbn_once()
    rows_out = []
    for i, d in enumerate(sampled, 1):
        if d not in by_date:
            print(f'  [{i}/{len(sampled)}] {d}: no DB')
            continue
        df1 = by_date[d]
        cr = csv[csv['Date'] == d]
        if cr.empty:
            continue
        outpath = out_dir / f'{d}.png'
        try:
            pat, nd, sx, rv = draw_chart(d, df1, cr, outpath)
            regime = str(cr['Regime'].iloc[0]) if has_regime else ''
            rows_out.append(
                {
                    'date': d,
                    'symbol': cr['Symbol'].iloc[0],
                    'pattern': pat,
                    'net_day': nd,
                    'rv': rv,
                    'regime': regime,
                }
            )
            suff = f' [{regime}]' if regime else ''
            print(f'  [{i:>3}/{len(sampled)}] {d} {cr["Symbol"].iloc[0]}{suff} net=${nd:+,.2f}')
        except Exception as e:
            print(f'  [{i}/{len(sampled)}] {d}: {e}')

    idx_path = out_dir / 'INDEX.md'
    if args.dates:
        print(f'Charts in {out_dir} (INDEX skipped with --dates)')
        return 0

    tot = sum(r['net_day'] for r in rows_out)
    wins = sum(1 for r in rows_out if r['net_day'] > 0)
    suite_title = 'adaptive_c — case studies (50/150 + children, v2b & v2d)' if has_regime else 'v2b_c — case studies (child scale-in)'
    suite_body = (
        'Unified **adaptive** simulator ``mnq/v2d/orb_adaptive_50_150_child.py``: MA50/150 picks **v2b OCO** or **v2d fade** tier-1; '
        'same **child** scale-in rules on both arms. Charts label tier-1 as **OCO** vs **fade** from ``Regime``.\n\n'
        if has_regime
        else (
            'Tier-1 **OCO stops** (``scripts/step2_preplaced_stops.py`` MNQ: RH+tick / RL−tick after OR) '
            '+ up to **2** child adds (``v2b_child/orb_open_limit_v2b_child.py``). '
            'Bracket TP / opposite boundary stop; child limits on qualifying **5 m** bars.\n\n'
        )
    )
    with open(idx_path, 'w') as f:
        f.write(f'# {suite_title}\n\n')
        f.write(suite_body)
        f.write(f'Sampled seed={args.seed}, start>={args.start}, CSV `{csv_path.name}`.\n\n')
        f.write(f'**Batch:** {len(rows_out)} charts, {wins} green days, Σ net ${tot:,.0f}.\n\n')
        if has_regime:
            f.write('| Date | Regime | Symbol | OR pts | Pattern | Net day $ | PNG |\n')
            f.write('|---|---|---:|---|---:|---:|---|\n')
            for r in sorted(rows_out, key=lambda x: x['date']):
                du = r['date']
                f.write(
                    f"| {du} | {r['regime']} | {r['symbol']} | {r['rv']:.1f} | {r['pattern']} | ${r['net_day']:+,.0f} | [{du}.png]({du}.png) |\n"
                )
        else:
            f.write('| Date | Symbol | OR pts | Pattern | Net day $ | PNG |\n|---|---|---:|---|---:|---|\n')
            for r in sorted(rows_out, key=lambda x: x['date']):
                du = r['date']
                f.write(
                    f"| {du} | {r['symbol']} | {r['rv']:.1f} | {r['pattern']} | ${r['net_day']:+,.0f} | [{du}.png]({du}.png) |\n"
                )
    print(f'Wrote {idx_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
