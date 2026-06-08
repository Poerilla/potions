#!/usr/bin/env python3
"""Annotated daily charts from monthly ORB restricted *scaleout3* trade CSV.

Mirrors ``build_baseline_restricted_charts.py`` layout but reads
``mnq_monthly_orb_restricted_scaleout3.csv`` (or NQ) with per-bundle unit exits.
Also writes ``METRICS_SCALEOUT3.md`` with PnL, MAE, closed DD, and MTM stress DD
(vs single-leg restricted) using the same stress definition as
``yearly_orb_equity_scaling.normalize_trades`` / ``base_stats``.

Output: ``baseline_restricted_scaleout3/<year>/<YYYY-MM>.png`` plus INDEX files
and ``METRICS_SCALEOUT3.md``.

Example:
  python3 mnq/case_studies/monthly_orb/build_baseline_restricted_scaleout3_charts.py
  python3 mnq/case_studies/monthly_orb/build_baseline_restricted_scaleout3_charts.py --nq
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

MNQ_ROOT = Path(__file__).resolve().parents[2]


def period_groups(daily: pd.DataFrame):
    work = daily.copy()
    work['ym'] = pd.to_datetime(work['date']).dt.to_period('M')
    for period, sub in work.groupby('ym', sort=True):
        sub = sub.sort_values('date').reset_index(drop=True)
        if len(sub) >= 4:
            yield str(period), sub


def max_drawdown(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    eq = pd.concat([pd.Series([0.0]), values.astype(float).cumsum()], ignore_index=True)
    return float((eq - eq.cummax()).min())


def normalize_scaleout(raw: pd.DataFrame, point_value: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = raw[raw['Entry_Date'].notna() & (raw['Trade_Direction'].astype(str) != 'No-Op')].copy()
    if raw.empty:
        return raw, pd.DataFrame(columns=['trade_id', 'date', 'usd', 'unit_idx'])
    raw['trade_id'] = range(1, len(raw) + 1)
    raw['Entry_Date'] = pd.to_datetime(raw['Entry_Date'])
    raw['Final_Exit_Date'] = pd.to_datetime(
        raw[['Unit1_Exit_Date', 'Unit2_Exit_Date', 'Unit3_Exit_Date']].max(axis=1)
    )
    raw['mae_usd'] = pd.to_numeric(raw['MAE_Position_Pts'], errors='coerce').fillna(0.0) * point_value
    raw['trade_usd'] = pd.to_numeric(raw['Trade_PL'], errors='coerce').fillna(0.0) * point_value
    units = []
    for _, row in raw.iterrows():
        direction = str(row['Trade_Direction'])
        entry = float(row['Entry_Price'])
        tid = int(row['trade_id'])
        for unit_idx in (1, 2, 3):
            exit_date = row.get(f'Unit{unit_idx}_Exit_Date')
            exit_px = row.get(f'Unit{unit_idx}_Exit_Price')
            if pd.isna(exit_date) or pd.isna(exit_px):
                continue
            exit_date = pd.to_datetime(exit_date)
            exit_px = float(exit_px)
            pts = exit_px - entry if direction == 'Long' else entry - exit_px
            units.append({'trade_id': tid, 'date': exit_date, 'usd': pts * point_value, 'unit_idx': unit_idx})
    return raw, pd.DataFrame(units)


def path_mae_usd_single(row: pd.Series, daily: pd.DataFrame, point_value: float) -> float:
    entry = float(row['Entry_Price'])
    direction = str(row['Trade_Direction'])
    d0 = pd.Timestamp(row['Entry_Date']).normalize()
    d1 = pd.Timestamp(row['Exit_Date']).normalize()
    w = daily[(pd.to_datetime(daily['date']).dt.normalize() >= d0) & (pd.to_datetime(daily['date']).dt.normalize() <= d1)]
    if w.empty:
        return 0.0
    if direction == 'Long':
        mae_pts = max(0.0, entry - float(w['low'].min()))
    else:
        mae_pts = max(0.0, float(w['high'].max()) - entry)
    return mae_pts * point_value


def normalize_single_leg(raw: pd.DataFrame, daily: pd.DataFrame, point_value: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = raw[raw['Entry_Date'].notna() & (raw['Trade_Direction'].astype(str) != 'No-Op')].copy()
    if raw.empty:
        return raw, pd.DataFrame(columns=['trade_id', 'date', 'usd', 'unit_idx'])
    raw['trade_id'] = range(1, len(raw) + 1)
    raw['Entry_Date'] = pd.to_datetime(raw['Entry_Date'])
    raw['Exit_Date'] = pd.to_datetime(raw['Exit_Date'])
    raw['Final_Exit_Date'] = raw['Exit_Date']
    raw['mae_usd'] = [path_mae_usd_single(r, daily, point_value) for _, r in raw.iterrows()]
    raw['trade_usd'] = pd.to_numeric(raw['Trade_PL'], errors='coerce').fillna(0.0) * point_value
    units = []
    for _, row in raw.iterrows():
        tid = int(row['trade_id'])
        exit_date = pd.to_datetime(row['Exit_Date'])
        units.append({'trade_id': tid, 'date': exit_date, 'usd': float(row['trade_usd']), 'unit_idx': 1})
    return raw, pd.DataFrame(units)


def base_stats(trades: pd.DataFrame, units: pd.DataFrame) -> dict:
    daily = units.groupby('date', sort=True)['usd'].sum().reset_index()
    closed_dd_usd = max_drawdown(daily['usd']) if not daily.empty else 0.0
    net_usd = float(units['usd'].sum()) if not units.empty else 0.0
    if trades.empty:
        return {
            'trades': 0,
            'net_usd': 0.0,
            'net_pts': 0.0,
            'closed_dd_usd': 0.0,
            'stress_dd_usd': 0.0,
            'worst_mae_usd': 0.0,
            'avg_mae_usd': 0.0,
            'max_mae_price_pts': 0.0,
            'avg_mae_price_pts': 0.0,
        }
    years = pd.date_range(trades['Entry_Date'].min(), trades['Final_Exit_Date'].max(), freq='D')
    closed_by_day = daily.set_index('date')['usd'].reindex(years, fill_value=0.0).cumsum()
    stress_values = []
    for day, closed_eq in closed_by_day.items():
        active = trades[(trades['Entry_Date'] <= day) & (trades['Final_Exit_Date'] >= day)]
        stress_values.append(float(closed_eq) - float(active['mae_usd'].sum()))
    stress_eq = pd.Series(stress_values)
    baseline_cum = closed_by_day.reset_index(drop=True)
    stress_dd_usd = float((stress_eq - baseline_cum.cummax()).min()) if not stress_eq.empty else 0.0
    net_pts = float(pd.to_numeric(trades['Trade_PL'], errors='coerce').sum()) if 'Trade_PL' in trades.columns else 0.0
    max_mae_price = (
        float(pd.to_numeric(trades['MAE_Price_Pts'], errors='coerce').max()) if 'MAE_Price_Pts' in trades.columns else 0.0
    )
    avg_mae_price = (
        float(pd.to_numeric(trades['MAE_Price_Pts'], errors='coerce').mean()) if 'MAE_Price_Pts' in trades.columns else 0.0
    )
    return {
        'trades': int(len(trades)),
        'net_usd': net_usd,
        'net_pts': net_pts,
        'closed_dd_usd': closed_dd_usd,
        'stress_dd_usd': stress_dd_usd,
        'worst_mae_usd': float(trades['mae_usd'].max()) if not trades.empty else 0.0,
        'avg_mae_usd': float(trades['mae_usd'].mean()) if not trades.empty else 0.0,
        'max_mae_price_pts': max_mae_price,
        'avg_mae_price_pts': avg_mae_price,
    }


def single_leg_mae_price_stats(raw: pd.DataFrame, daily: pd.DataFrame) -> tuple[float, float]:
    t = raw[raw['Trade_Direction'].astype(str) != 'No-Op'].copy()
    if t.empty:
        return 0.0, 0.0
    pts = []
    for _, row in t.iterrows():
        entry = float(row['Entry_Price'])
        direction = str(row['Trade_Direction'])
        d0 = pd.Timestamp(row['Entry_Date']).normalize()
        d1 = pd.Timestamp(row['Exit_Date']).normalize()
        w = daily[(pd.to_datetime(daily['date']).dt.normalize() >= d0) & (pd.to_datetime(daily['date']).dt.normalize() <= d1)]
        if w.empty:
            pts.append(0.0)
            continue
        if direction == 'Long':
            pts.append(max(0.0, entry - float(w['low'].min())))
        else:
            pts.append(max(0.0, float(w['high'].max()) - entry))
    return max(pts), sum(pts) / len(pts)


def fmt_money(v: float) -> str:
    return f'${v:,.2f}'


def draw_period_scaleout3(
    period: str,
    bars: pd.DataFrame,
    period_trades: pd.DataFrame,
    out_path: Path,
    point_value_usd: float,
) -> dict | None:
    if period_trades.empty:
        return None

    range_bars = bars.iloc[:3].copy()
    range_high = float(range_bars['high'].max())
    range_low = float(range_bars['low'].min())
    range_val = range_high - range_low
    if range_val <= 0:
        return None

    bundles = period_trades[period_trades['Trade_Direction'].astype(str) != 'No-Op'].copy()
    sym = str(bars.iloc[0]['symbol'])

    fig = plt.figure(figsize=(14, 8.5), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')

    dates = pd.to_datetime(bars['date'])
    xnums = mdates.date2num(dates)
    width = 0.58
    for x, (_, row) in zip(xnums, bars.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        col = '#26A69A' if c >= o else '#EF5350'
        ax.vlines(x, l, h, color=col, linewidth=0.8, zorder=3)
        body_lo, body_hi = min(o, c), max(o, c)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, body_lo),
                width,
                max(body_hi - body_lo, 0.05),
                facecolor=col,
                edgecolor=col,
                alpha=0.95,
                zorder=3,
            )
        )

    range_start = pd.Timestamp(range_bars.iloc[0]['date'])
    range_end = pd.Timestamp(range_bars.iloc[-1]['date']) + pd.Timedelta(days=1)
    ax.axvspan(range_start, range_end, color='#1F4E79', alpha=0.30, zorder=0)
    ax.axhline(range_high, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
    ax.axhline(range_low, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
    ax.axhspan(range_low, range_high, color='#1F4E79', alpha=0.10, zorder=0)

    color_for = {'Win': '#76FF03', 'Loss': '#FF1744', 'Scratch': '#B0BEC5', 'Range-Close': '#FFB74D'}
    bundle_colors = ['#FFC107', '#00E5FF', '#E040FB']
    label_offsets = [22, -34, 46, -58, 70, -82]

    patterns: list[str] = []
    total_pl = 0.0

    if bundles.empty:
        ax.text(
            0.5,
            0.90,
            'No filled bundles (No-Op): no usable breakout / retest in period.',
            transform=ax.transAxes,
            color='#FFB74D',
            fontsize=10,
            ha='center',
            fontweight='bold',
            bbox=dict(boxstyle='round,pad=0.35', fc='#0D1B2A', ec='#FFB74D', alpha=0.92),
            zorder=12,
        )
        pattern = 'No-Op'
    else:
        for bi, (_, tr) in enumerate(bundles.iterrows(), 1):
            direction = str(tr['Trade_Direction'])
            entry = float(tr['Entry_Price'])
            tp25 = float(tr['TP25_Price'])
            target = float(tr['TP_Price'])
            init_sl = float(tr['Initial_Stop_Price'])
            result = str(tr['Result'])
            final_r = str(tr.get('Final_Reason', ''))
            pl = float(tr['Trade_PL'])
            total_pl += pl
            patterns.append(f'{direction[0]}{result[0]}')

            entry_date = pd.Timestamp(tr['Entry_Date'])
            x_e = mdates.date2num(entry_date)
            bc = bundle_colors[(bi - 1) % len(bundle_colors)]

            ax.scatter([x_e], [entry], marker='^' if direction == 'Long' else 'v', color=bc, s=150, zorder=10, edgecolor='black', linewidth=1.1)
            ax.annotate(
                f'B{bi} {direction[0]} @ {entry:.2f}',
                xy=(x_e, entry),
                xytext=(8, label_offsets[(bi - 1) % len(label_offsets)]),
                textcoords='offset points',
                color=bc,
                fontsize=8,
                fontweight='bold',
                ha='left',
                bbox=dict(boxstyle='round,pad=0.2', fc='#0D1B2A', ec=bc, alpha=0.95),
            )
            x_band = [x_e, mdates.date2num(pd.Timestamp(bars['date'].max())) + 0.5]
            ax.plot(x_band, [tp25, tp25], color='#81C784', linewidth=0.85, alpha=0.55, linestyle=':', zorder=4)
            ax.plot(x_band, [target, target], color='#76FF03', linewidth=0.85, alpha=0.55, zorder=4)
            ax.plot(x_band, [init_sl, init_sl], color='#FF1744', linewidth=0.85, alpha=0.55, zorder=4)

            for ui in (1, 2, 3):
                ed = tr.get(f'Unit{ui}_Exit_Date')
                ep = tr.get(f'Unit{ui}_Exit_Price')
                rs = tr.get(f'Unit{ui}_Exit_Reason')
                if pd.isna(ed) or pd.isna(ep):
                    continue
                xd = mdates.date2num(pd.Timestamp(ed))
                ax.scatter([xd], [float(ep)], marker='o', color=bc, s=55, zorder=11, edgecolor='white', linewidth=0.6)
                ax.annotate(
                    f'B{bi}U{ui}\n{rs}',
                    xy=(xd, float(ep)),
                    xytext=(4, 10 + ui * 6),
                    textcoords='offset points',
                    color='#ECEFF1',
                    fontsize=6,
                    ha='left',
                )

            exit_color = color_for.get(result, '#FFB74D')
            udates = []
            for ui in (1, 2, 3):
                ed = tr.get(f'Unit{ui}_Exit_Date')
                if pd.notna(ed):
                    udates.append((pd.Timestamp(ed), ui))
            if udates:
                last_exit, u_last = max(udates, key=lambda x: x[0])
                last_px = float(tr[f'Unit{u_last}_Exit_Price'])
                x_x = mdates.date2num(last_exit)
                ax.annotate(
                    f'B{bi} Σ{pl:+.0f}pt {final_r}',
                    xy=(x_x, last_px),
                    xytext=(8, -label_offsets[(bi - 1) % len(label_offsets)]),
                    textcoords='offset points',
                    color=exit_color,
                    fontsize=8,
                    fontweight='bold',
                    ha='left',
                    bbox=dict(boxstyle='round,pad=0.2', fc='#0D1B2A', ec=exit_color, alpha=0.95),
                )

        pattern = '+'.join(patterns)

    csv_pl_total = float(period_trades['Trade_PL'].sum()) if 'Trade_PL' in period_trades.columns else total_pl
    usd_suffix = '' if abs(point_value_usd - 1.0) < 1e-9 else f' (${total_pl * point_value_usd:+.0f})'
    title = (
        f'{period}  {sym}  MONTHLY ORB RESTRICTED · SCALEOUT3  ·  '
        f'Range {range_val:.1f}  ·  {pattern}  ·  {total_pl:+.1f}pt{usd_suffix}'
    )
    ax.set_title(title, color='white', fontsize=9, fontweight='bold', pad=8, loc='left')
    ax.tick_params(colors='#9FB3C8', labelsize=7)
    for spine in ax.spines.values():
        spine.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color='#9FB3C8')
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=1), dates.iloc[-1] + pd.Timedelta(days=2))
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100, bbox_inches='tight', facecolor='#0D1B2A')
    plt.close(fig)

    return {
        'period': period,
        'year': int(period[:4]),
        'symbol': sym,
        'range': round(range_val, 2),
        'pattern': pattern,
        'trades': len(bundles),
        'net_pts': round(total_pl, 2),
        'csv_net_pts': round(csv_pl_total, 2),
        'chart': f'{period[:4]}/{period}.png',
    }


def write_indexes(out_root: Path, rows: list[dict], multiplier: float) -> None:
    by_year: dict[int, list[dict]] = {}
    for row in rows:
        by_year.setdefault(int(row['year']), []).append(row)

    title_block = '\n'.join(
        [
            '# Monthly ORB restricted — scaleout3 charts',
            '',
            'Source: `mnq_monthly_orb_restricted_scaleout3.csv` (or NQ). '
            '3-unit ladder: TP25 / full TP / runner, opposite-boundary stop, BE after TP2, '
            'range-close flatten. See `MONTHLY_ORB_RESTRICTED.md`.',
            '',
        ]
    )

    for year, yr_rows in sorted(by_year.items()):
        idx = out_root / str(year) / 'INDEX.md'
        total = sum(r['net_pts'] for r in yr_rows)
        idx.write_text(
            '\n'.join(
                [
                    f'# {year} restricted scaleout3 charts',
                    '',
                    f'Periods: {len(yr_rows)}  ·  Net: {total:+.2f} pts (${total * multiplier:+,.0f} @ ${multiplier}/pt)',
                    '',
                    '| Period | Symbol | Range | Pattern | Bundles | Net pts | Chart |',
                    '|---|---|---:|---|---:|---:|---|',
                    *[
                        (
                            f"| {r['period']} | {r['symbol']} | {r['range']:.2f} | {r['pattern']} | "
                            f"{r['trades']} | {r['net_pts']:+.2f} | [{r['period']}.png]({r['period']}.png) |"
                        )
                        for r in sorted(yr_rows, key=lambda x: x['period'])
                    ],
                    '',
                ]
            ),
            encoding='utf-8',
        )

    summary = out_root / 'INDEX.md'
    summary.write_text(
        '\n'.join(
            [
                title_block,
                f'Periods charted: {len(rows)}  ·  Net: {sum(r["net_pts"] for r in rows):+.2f} pts',
                '',
                '| Year | Periods | Net pts | Folder |',
                '|---:|---:|---:|---|',
                *[
                    (
                        f"| {year} | {len(yr_rows)} | {sum(rr['net_pts'] for rr in yr_rows):+.2f} "
                        f"| [{year}/]({year}/INDEX.md) |"
                    )
                    for year, yr_rows in sorted(by_year.items())
                ],
                '',
                '## All periods',
                '',
                '| Period | Symbol | Range | Pattern | Bundles | Net pts | Chart |',
                '|---|---|---:|---|---:|---:|---|',
                *[
                    (
                        f"| {r['period']} | {r['symbol']} | {r['range']:.2f} | {r['pattern']} | "
                        f"{r['trades']} | {r['net_pts']:+.2f} | [{r['chart']}]({r['chart']}) |"
                    )
                    for r in sorted(rows, key=lambda x: x['period'])
                ],
                '',
            ]
        ),
        encoding='utf-8',
    )


def build_metrics_md(
    label: str,
    leg_path: Path,
    scale_path: Path,
    daily_path: Path,
    mult: float,
) -> str:
    daily = pd.read_csv(daily_path, parse_dates=['date'])
    leg_raw = pd.read_csv(leg_path)
    scale_raw = pd.read_csv(scale_path)

    leg_t, leg_u = normalize_single_leg(leg_raw, daily, mult)
    scale_t, scale_u = normalize_scaleout(scale_raw, mult)

    mx_leg_pts, avg_leg_pts = single_leg_mae_price_stats(leg_raw, daily)

    st_leg = base_stats(leg_t, leg_u)
    st_scale = base_stats(scale_t, scale_u)

    lines = [
        f'## Restricted vs scaleout3 ({label})',
        '',
        '**Stress DD** uses the same daily construction as `yearly_orb_equity_scaling.base_stats`: '
        'cumulative **realized** PnL by calendar day from leg exits, minus the sum of **MAE stress** '
        '(`MAE_Position_Pts` × $/pt for scaleout3 bundles; path adverse excursion × $/pt for single-leg) '
        'for all bundles still open on that day. More negative = more conservative open-heat estimate.',
        '',
        '| Metric | Single-leg restricted | Scaleout3 restricted |',
        '|---|---:|---:|',
        f"| Trades / bundles | {st_leg['trades']} | {st_scale['trades']} |",
        f"| Net (pts) | {st_leg['net_pts']:,.2f} | {st_scale['net_pts']:,.2f} |",
        f"| Net (USD) | {fmt_money(st_leg['net_usd'])} | {fmt_money(st_scale['net_usd'])} |",
        f"| Max MAE price (pts, path) — single-leg | {mx_leg_pts:,.2f} | — |",
        f"| Avg MAE price (pts, path) — single-leg | {avg_leg_pts:,.2f} | — |",
        f"| Max MAE price (pts) — scaleout sim | — | {st_scale['max_mae_price_pts']:,.2f} |",
        f"| Avg MAE price (pts) — scaleout sim | — | {st_scale['avg_mae_price_pts']:,.2f} |",
        f"| Worst bundle MAE stress (USD) | {fmt_money(st_leg['worst_mae_usd'])} | {fmt_money(st_scale['worst_mae_usd'])} |",
        f"| Avg bundle MAE stress (USD) | {fmt_money(st_leg['avg_mae_usd'])} | {fmt_money(st_scale['avg_mae_usd'])} |",
        f"| Max drawdown — **closed** realized (USD) | {fmt_money(st_leg['closed_dd_usd'])} | {fmt_money(st_scale['closed_dd_usd'])} |",
        f"| Max drawdown — **stress / MTM** proxy (USD) | {fmt_money(st_leg['stress_dd_usd'])} | {fmt_money(st_scale['stress_dd_usd'])} |",
        '',
    ]
    return '\n'.join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, default=MNQ_ROOT / 'mnq_daily.csv')
    ap.add_argument('--scaleout-csv', type=Path, default=MNQ_ROOT / 'mnq_monthly_orb_restricted_scaleout3.csv')
    ap.add_argument('--restricted-csv', type=Path, default=MNQ_ROOT / 'mnq_monthly_orb_restricted.csv')
    ap.add_argument(
        '--out',
        type=Path,
        default=MNQ_ROOT / 'case_studies' / 'monthly_orb' / 'baseline_restricted_scaleout3',
    )
    ap.add_argument('--point-value-usd', type=float, default=2.0)
    ap.add_argument('--nq', action='store_true', help='Use NQ paths and $20/pt.')
    args = ap.parse_args()

    if args.nq:
        args.daily = MNQ_ROOT.parent / 'nq' / 'nq_daily.csv'
        args.scaleout_csv = MNQ_ROOT.parent / 'nq' / 'nq_monthly_orb_restricted_scaleout3.csv'
        args.restricted_csv = MNQ_ROOT.parent / 'nq' / 'nq_monthly_orb_restricted.csv'
        args.point_value_usd = 20.0
        args.out = MNQ_ROOT.parent / 'nq' / 'case_studies' / 'monthly_orb' / 'baseline_restricted_scaleout3'

    daily = pd.read_csv(args.daily, parse_dates=['date'])
    trades = pd.read_csv(args.scaleout_csv)

    rows: list[dict] = []
    for period, bars in period_groups(daily):
        pt = trades[trades['Period'].astype(str) == period]
        if pt.empty:
            continue
        out_path = args.out / period[:4] / f'{period}.png'
        row = draw_period_scaleout3(period, bars, pt, out_path, args.point_value_usd)
        if row:
            rows.append(row)
            print(f'{row["chart"]} {row["net_pts"]:+.2f}pt', flush=True)

    args.out.mkdir(parents=True, exist_ok=True)
    write_indexes(args.out, rows, args.point_value_usd)

    md_mnq = build_metrics_md('MNQ', MNQ_ROOT / 'mnq_monthly_orb_restricted.csv', MNQ_ROOT / 'mnq_monthly_orb_restricted_scaleout3.csv', MNQ_ROOT / 'mnq_daily.csv', 2.0)
    md_nq = build_metrics_md(
        'NQ',
        MNQ_ROOT.parent / 'nq' / 'nq_monthly_orb_restricted.csv',
        MNQ_ROOT.parent / 'nq' / 'nq_monthly_orb_restricted_scaleout3.csv',
        MNQ_ROOT.parent / 'nq' / 'nq_daily.csv',
        20.0,
    )
    metrics_path = MNQ_ROOT / 'case_studies' / 'monthly_orb' / 'METRICS_SCALEOUT3.md'
    metrics_path.write_text(
        '\n'.join(
            [
                '# Monthly ORB restricted — scaleout3 metrics',
                '',
                md_mnq,
                '',
                md_nq,
                '',
                'Regenerate charts: `python3 mnq/case_studies/monthly_orb/build_baseline_restricted_scaleout3_charts.py`',
                '',
                'Regenerate NQ charts: same with `--nq`.',
                '',
            ]
        ),
        encoding='utf-8',
    )

    print(f'Wrote {len(rows)} charts under {args.out}')
    print(f'Wrote {args.out / "INDEX.md"}')
    print(f'Wrote {metrics_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
