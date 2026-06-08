#!/usr/bin/env python3
"""Daily-close monthly ORB breakout diagnostics with 4-hour path checks.

This is observational research, not a trade simulator.

Rules studied:

- Monthly OR is still the first 3 trading sessions from the daily file.
- A breakout event begins only after a daily candle closes outside the OR.
- Clean break means TP1 is reached before:
  - any daily close back inside the OR, and
  - any 4-hour candle trades back into the OR.
- A separate "wide berth" read counts how often TP1 is reached before the
  opposing OR boundary is touched, regardless of interim retests/closes.
- TP2 continuation is measured for clean breaks and for all break events.

Charts are full-month 4-hour candles for every month with at least one clean
daily-close break.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd
import pytz


ROOT = Path(__file__).resolve().parents[1]
MNQ_ROOT = ROOT / 'mnq'
CASE_ROOT = MNQ_ROOT / 'case_studies' / 'monthly_orb'
DAILY = MNQ_ROOT / 'mnq_daily.csv'
FOUR_H_CACHE = MNQ_ROOT / 'data' / 'mnq_front_month_4h_from_1m.csv'
OUT_CSV = MNQ_ROOT / 'mnq_monthly_orb_daily_close_breakout_diagnostics.csv'
OUT_REPORT = CASE_ROOT / 'MONTHLY_ORB_DAILY_CLOSE_BREAKOUT_DIAGNOSTICS.md'
OVERLAP_TRADES_CSV = MNQ_ROOT / 'mnq_monthly_orb_overlap_range_breakout.csv'
NY = pytz.timezone('America/New_York')


@dataclass
class BreakoutEvent:
    period: str
    direction: str
    breakout_date: object
    breakout_close: float
    range_high: float
    range_low: float
    range_size: float
    target_1r: float
    target_2r: float
    opposing_boundary: float
    traded_back_into_range_before_1r: bool = False
    daily_close_back_inside_before_1r: bool = False
    false_break_opposing_before_1r: bool = False
    hit_1r_before_opposing: bool = False
    hit_1r_time: pd.Timestamp | None = None
    clean_1r: bool = False
    hit_2r: bool = False
    hit_2r_time: pd.Timestamp | None = None
    terminal_time: pd.Timestamp | None = None
    terminal_reason: str = 'Period-Close'
    max_favorable_pts: float = 0.0
    max_adverse_pts: float = 0.0


def load_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=['date'])
    df['date'] = df['date'].dt.date
    return df.sort_values('date').reset_index(drop=True)


def load_cached_4h(path: Path) -> pd.DataFrame:
    bars = pd.read_csv(path)
    bars['time'] = pd.to_datetime(bars['time'], utc=True).dt.tz_convert(NY)
    bars['date'] = bars['time'].dt.date
    return bars.sort_values('time').reset_index(drop=True)


def period_groups(daily: pd.DataFrame):
    work = daily.copy()
    work['ym'] = pd.to_datetime(work['date']).dt.to_period('M')
    for period, sub in work.groupby('ym', sort=True):
        sub = sub.sort_values('date').reset_index(drop=True)
        if len(sub) >= 4:
            yield str(period), sub


def calendar_month_4h(bars4h: pd.DataFrame, period: str) -> pd.DataFrame:
    year, month = map(int, period.split('-'))
    t = pd.to_datetime(bars4h['time'])
    return bars4h[(t.dt.year == year) & (t.dt.month == month)].copy().reset_index(drop=True)


def add_daily_close_flags(month4h: pd.DataFrame, month_daily: pd.DataFrame) -> pd.DataFrame:
    out = month4h.copy()
    close_by_date = {pd.Timestamp(row['date']).date(): float(row['close']) for _, row in month_daily.iterrows()}
    out['daily_close'] = out['date'].map(close_by_date)
    out['is_daily_close_bar'] = False
    for d in close_by_date:
        idx = out.index[out['date'].eq(d)]
        if len(idx):
            out.loc[idx[-1], 'is_daily_close_bar'] = True
    return out


def daily_close_inside(row: pd.Series, rh: float, rl: float) -> bool:
    if not bool(row.get('is_daily_close_bar', False)):
        return False
    close_px = row.get('daily_close')
    if pd.isna(close_px):
        return False
    return rl <= float(close_px) <= rh


def update_excursion(ev: BreakoutEvent, row: pd.Series) -> None:
    h, l = float(row['high']), float(row['low'])
    if ev.direction == 'Long':
        ev.max_favorable_pts = max(ev.max_favorable_pts, h - ev.breakout_close)
        ev.max_adverse_pts = max(ev.max_adverse_pts, ev.breakout_close - l)
    else:
        ev.max_favorable_pts = max(ev.max_favorable_pts, ev.breakout_close - l)
        ev.max_adverse_pts = max(ev.max_adverse_pts, h - ev.breakout_close)


def new_event(period: str, row: pd.Series, rh: float, rl: float, rv: float) -> BreakoutEvent | None:
    close_px = float(row['close'])
    d = pd.Timestamp(row['date']).date()
    if close_px > rh:
        return BreakoutEvent(
            period=period,
            direction='Long',
            breakout_date=d,
            breakout_close=close_px,
            range_high=rh,
            range_low=rl,
            range_size=rv,
            target_1r=rh + rv,
            target_2r=rh + 2.0 * rv,
            opposing_boundary=rl,
        )
    if close_px < rl:
        return BreakoutEvent(
            period=period,
            direction='Short',
            breakout_date=d,
            breakout_close=close_px,
            range_high=rh,
            range_low=rl,
            range_size=rv,
            target_1r=rl - rv,
            target_2r=rl - 2.0 * rv,
            opposing_boundary=rh,
        )
    return None


def process_path(ev: BreakoutEvent, path4h: pd.DataFrame) -> BreakoutEvent:
    hit_1r = False
    for _, row in path4h.iterrows():
        t = pd.Timestamp(row['time'])
        h, l = float(row['high']), float(row['low'])
        update_excursion(ev, row)

        if ev.direction == 'Long':
            if not hit_1r:
                if l <= ev.opposing_boundary:
                    ev.false_break_opposing_before_1r = True
                    ev.terminal_time = t
                    ev.terminal_reason = 'Opposing-Boundary-Before-1R'
                    return ev
                if l <= ev.range_high:
                    ev.traded_back_into_range_before_1r = True
                if h >= ev.target_1r:
                    hit_1r = True
                    ev.hit_1r_before_opposing = True
                    ev.hit_1r_time = t
                    ev.clean_1r = (
                        not ev.traded_back_into_range_before_1r
                        and not ev.daily_close_back_inside_before_1r
                    )
            if hit_1r:
                if l <= ev.opposing_boundary:
                    ev.terminal_time = t
                    ev.terminal_reason = 'Opposing-Boundary-After-1R'
                    return ev
                if h >= ev.target_2r:
                    ev.hit_2r = True
                    ev.hit_2r_time = t
                    ev.terminal_time = t
                    ev.terminal_reason = 'Target-2R'
                    return ev
        else:
            if not hit_1r:
                if h >= ev.opposing_boundary:
                    ev.false_break_opposing_before_1r = True
                    ev.terminal_time = t
                    ev.terminal_reason = 'Opposing-Boundary-Before-1R'
                    return ev
                if h >= ev.range_low:
                    ev.traded_back_into_range_before_1r = True
                if l <= ev.target_1r:
                    hit_1r = True
                    ev.hit_1r_before_opposing = True
                    ev.hit_1r_time = t
                    ev.clean_1r = (
                        not ev.traded_back_into_range_before_1r
                        and not ev.daily_close_back_inside_before_1r
                    )
            if hit_1r:
                if h >= ev.opposing_boundary:
                    ev.terminal_time = t
                    ev.terminal_reason = 'Opposing-Boundary-After-1R'
                    return ev
                if l <= ev.target_2r:
                    ev.hit_2r = True
                    ev.hit_2r_time = t
                    ev.terminal_time = t
                    ev.terminal_reason = 'Target-2R'
                    return ev

        if not hit_1r and daily_close_inside(row, ev.range_high, ev.range_low):
            ev.daily_close_back_inside_before_1r = True

    if not path4h.empty:
        ev.terminal_time = pd.Timestamp(path4h.iloc[-1]['time'])
    ev.terminal_reason = 'Period-Close'
    return ev


def event_row(ev: BreakoutEvent) -> dict:
    return {
        'Period': ev.period,
        'Direction': ev.direction,
        'Breakout_Date': ev.breakout_date.isoformat(),
        'Breakout_Close': ev.breakout_close,
        'Range_High': ev.range_high,
        'Range_Low': ev.range_low,
        'Range': ev.range_size,
        'Target_1R': ev.target_1r,
        'Target_2R': ev.target_2r,
        'Opposing_Boundary': ev.opposing_boundary,
        'False_Break_Opposing_Before_1R': ev.false_break_opposing_before_1r,
        'Hit_1R_Before_Opposing': ev.hit_1r_before_opposing,
        'Hit_1R_Time': ev.hit_1r_time.isoformat() if ev.hit_1r_time is not None else None,
        'Clean_1R_No_Daily_Close_Inside_No_4H_Trade_Back_Into_Range': ev.clean_1r,
        'Daily_Close_Back_Inside_Before_1R': ev.daily_close_back_inside_before_1r,
        'Traded_Back_Into_Range_Before_1R': ev.traded_back_into_range_before_1r,
        'Hit_2R': ev.hit_2r,
        'Hit_2R_Time': ev.hit_2r_time.isoformat() if ev.hit_2r_time is not None else None,
        'Clean_And_Hit_2R': ev.clean_1r and ev.hit_2r,
        'Terminal_Time': ev.terminal_time.isoformat() if ev.terminal_time is not None else None,
        'Terminal_Reason': ev.terminal_reason,
        'Max_Favorable_Pts': round(ev.max_favorable_pts, 6),
        'Max_Adverse_Pts': round(ev.max_adverse_pts, 6),
    }


def run_diagnostics(daily: pd.DataFrame, bars4h: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    rows: list[dict] = []
    period_bars: dict[str, pd.DataFrame] = {}
    period_daily: dict[str, pd.DataFrame] = {}

    for period, month_daily in period_groups(daily):
        rb = month_daily.iloc[:3]
        rh = float(rb['high'].max())
        rl = float(rb['low'].min())
        rv = rh - rl
        if rv <= 0:
            continue
        month4h = add_daily_close_flags(calendar_month_4h(bars4h, period), month_daily)
        if month4h.empty:
            continue
        period_bars[period] = month4h
        period_daily[period] = month_daily
        trade_daily = month_daily.iloc[3:].reset_index(drop=True)

        armed = True
        skip_until = None
        for _, drow in trade_daily.iterrows():
            d = pd.Timestamp(drow['date']).date()
            if skip_until is not None and d <= skip_until:
                continue
            if not armed:
                if rl <= float(drow['close']) <= rh:
                    armed = True
                continue
            ev = new_event(period, drow, rh, rl, rv)
            if ev is None:
                continue
            # Conservative causal read: the daily close is only known after
            # that daily session. Track 4h path from later dates in the month.
            path = month4h[month4h['date'] > ev.breakout_date].copy().reset_index(drop=True)
            ev = process_path(ev, path)
            rows.append(event_row(ev))
            armed = False
            if ev.terminal_time is not None:
                skip_until = ev.terminal_time.date()

    return pd.DataFrame(rows), period_bars, period_daily


def draw_candles(ax, bars: pd.DataFrame, width: float = 0.12) -> None:
    xnums = mdates.date2num(pd.to_datetime(bars['time']).dt.tz_convert(None).dt.to_pydatetime())
    for x, (_, row) in zip(xnums, bars.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        color = '#26A69A' if c >= o else '#EF5350'
        ax.vlines(x, l, h, color=color, linewidth=0.8, zorder=3)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, min(o, c)),
                width,
                max(abs(c - o), 0.05),
                facecolor=color,
                edgecolor=color,
                alpha=0.95,
                zorder=4,
            )
        )


def line_label(ax, x0: float, x1: float, y: float, label: str, color: str, ls: str = '-') -> None:
    ax.hlines(y, x0, x1, color=color, linestyle=ls, linewidth=1.0, alpha=0.9)
    ax.text(x1, y, f' {label}', color=color, fontsize=8, va='center', ha='left')


def draw_daily_candles(ax, bars: pd.DataFrame, width: float = 0.62) -> None:
    xnums = mdates.date2num(pd.to_datetime(bars['date_ts']).dt.to_pydatetime())
    for x, (_, row) in zip(xnums, bars.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        color = '#26A69A' if c >= o else '#EF5350'
        ax.vlines(x, l, h, color=color, linewidth=0.55, alpha=0.75, zorder=2)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, min(o, c)),
                width,
                max(abs(c - o), 0.05),
                facecolor=color,
                edgecolor=color,
                alpha=0.72,
                zorder=3,
            )
        )


def marker_time_for_date(bars: pd.DataFrame, d: object) -> pd.Timestamp | None:
    w = bars[bars['date'].eq(d)]
    if w.empty:
        return None
    return pd.Timestamp(w.iloc[-1]['time'])


def draw_clean_month_chart(period: str, events: pd.DataFrame, bars: pd.DataFrame, month_daily: pd.DataFrame, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if bars.empty:
        return
    rh = float(events.iloc[0]['Range_High'])
    rl = float(events.iloc[0]['Range_Low'])
    fig = plt.figure(figsize=(16, 8.5), facecolor='#0D1B2A')
    ax = fig.add_subplot(111)
    ax.set_facecolor('#0D1B2A')
    draw_candles(ax, bars)
    xnums = mdates.date2num(pd.to_datetime(bars['time']).dt.tz_convert(None).dt.to_pydatetime())
    line_label(ax, xnums[0], xnums[-1], rh, 'OR High', '#64B5F6')
    line_label(ax, xnums[0], xnums[-1], rl, 'OR Low', '#64B5F6')
    ax.axhspan(rl, rh, color='#263D5A', alpha=0.22, zorder=1)

    range_dates = [pd.Timestamp(v).date() for v in month_daily.iloc[:3]['date']]
    shade = bars[bars['date'].isin(range_dates)]
    if not shade.empty:
        sx = mdates.date2num(pd.to_datetime(shade['time']).dt.tz_convert(None).dt.to_pydatetime())
        ax.axvspan(sx[0], sx[-1], color='#FFD54F', alpha=0.08, zorder=0)

    for i, (_, row) in enumerate(events.iterrows(), 1):
        color = '#00E676' if row['Direction'] == 'Long' else '#FF8A80'
        marker = '^' if row['Direction'] == 'Long' else 'v'
        bdate = pd.Timestamp(row['Breakout_Date']).date()
        bt = marker_time_for_date(bars, bdate)
        if bt is not None:
            bx = mdates.date2num(bt.tz_convert(None).to_pydatetime())
            ax.scatter(bx, float(row['Breakout_Close']), marker=marker, s=90, color=color, edgecolor='white', zorder=8)
            ax.text(bx, float(row['Breakout_Close']), f' #{i} daily close break', color='white', fontsize=8, ha='left')
        line_label(ax, xnums[0], xnums[-1], float(row['Target_1R']), f'#{i} TP1', '#81C784', '--')
        line_label(ax, xnums[0], xnums[-1], float(row['Target_2R']), f'#{i} TP2', '#AED581', ':')
        if pd.notna(row.get('Hit_1R_Time')):
            ht = pd.to_datetime(row['Hit_1R_Time']).tz_convert(NY)
            hx = mdates.date2num(ht.tz_convert(None).to_pydatetime())
            ax.scatter(hx, float(row['Target_1R']), marker='*', s=130, color='#00E676', edgecolor='white', zorder=9)

    ax.set_title(f'MNQ monthly ORB clean daily-close break month | {period}', color='white', fontsize=13)
    ax.grid(True, color='white', alpha=0.08)
    ax.tick_params(colors='white')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def build_clean_month_charts(events: pd.DataFrame, period_bars: dict[str, pd.DataFrame], period_daily: dict[str, pd.DataFrame], out_root: Path) -> None:
    clean = events[events['Clean_1R_No_Daily_Close_Inside_No_4H_Trade_Back_Into_Range'].eq(True)].copy()
    chart_root = out_root / 'daily_close_breakout_diagnostics' / 'clean_months'
    chart_root.mkdir(parents=True, exist_ok=True)
    lines = ['# MNQ monthly ORB clean daily-close breakout months', '']
    for period, sub in clean.groupby('Period', sort=True):
        year = str(period)[:4]
        name = f'{period}_clean_daily_close_breaks.png'
        out_path = chart_root / year / name
        draw_clean_month_chart(period, sub, period_bars[period], period_daily[period], out_path)
        lines.append(f'- [{period}]({year}/{name}) — {len(sub)} clean break(s)')
    (chart_root / 'INDEX.md').write_text('\n'.join(lines) + '\n')
    for yd in sorted([p for p in chart_root.iterdir() if p.is_dir()]):
        ylines = [f'# Clean daily-close breakout months {yd.name}', '']
        for p in sorted(yd.glob('*.png')):
            ylines.append(f'- [{p.name}]({p.name})')
        (yd / 'INDEX.md').write_text('\n'.join(ylines) + '\n')


def load_overlap_trades_csv(path: Path) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    tr = pd.read_csv(path)
    if tr.empty:
        return None
    for col in ('Entry_Date', 'Exit_Date'):
        if col in tr.columns:
            tr[col] = pd.to_datetime(tr[col]).dt.normalize()
    return tr


def _trade_overlaps_year(entry_ts: pd.Timestamp, exit_ts: pd.Timestamp, chart_d0: pd.Timestamp, chart_d1: pd.Timestamp) -> bool:
    return not (exit_ts < chart_d0 or entry_ts > chart_d1)


def draw_overlap_trade_overlays(
    ax,
    ydf: pd.DataFrame,
    trades: pd.DataFrame | None,
    ymins: list[float],
    ymaxs: list[float],
) -> None:
    """Overlay overlap-range breakout trades (combined RH/RL, stop, target, entry/exit)."""
    if trades is None or trades.empty:
        return
    chart_d0 = pd.Timestamp(ydf['date_ts'].iloc[0]).normalize()
    chart_d1 = pd.Timestamp(ydf['date_ts'].iloc[-1]).normalize()
    dates_series = pd.to_datetime(ydf['date_ts']).dt.normalize()

    for _, tr in trades.iterrows():
        entry_ts = pd.Timestamp(tr['Entry_Date']).normalize()
        exit_ts = pd.Timestamp(tr['Exit_Date']).normalize()
        if not _trade_overlaps_year(entry_ts, exit_ts, chart_d0, chart_d1):
            continue

        x0 = max(entry_ts, chart_d0)
        x1 = min(exit_ts, chart_d1)
        x0n = mdates.date2num(x0.to_pydatetime())
        x1n = mdates.date2num(x1.to_pydatetime())

        rh = float(tr['Range_High'])
        rl = float(tr['Range_Low'])
        stop = float(tr['Stop_Price'])
        tgt = float(tr['Final_Target'])
        ymins.extend([rl, rh, stop, tgt])
        ymaxs.extend([rl, rh, stop, tgt])

        ax.fill_between([x0n, x1n], rl, rh, color='#AB47BC', alpha=0.14, zorder=4)
        ax.hlines([rh, rl], x0n, x1n, colors='#CE93D8', linewidth=1.05, linestyle='-', alpha=0.88, zorder=5)
        ax.hlines(stop, x0n, x1n, colors='#FFB74D', linestyle='--', linewidth=1.0, alpha=0.92, zorder=5)
        ax.hlines(tgt, x0n, x1n, colors='#81C784', linestyle='--', linewidth=1.0, alpha=0.92, zorder=5)

        direction = str(tr['Direction'])
        mk = '^' if direction == 'Long' else 'v'
        col = '#E1BEE7' if direction == 'Long' else '#FFAB91'

        em = ydf.loc[dates_series.eq(entry_ts)]
        if not em.empty:
            ex = mdates.date2num(pd.Timestamp(em.iloc[-1]['date_ts']).to_pydatetime())
            ax.scatter(ex, float(tr['Entry_Price']), marker=mk, s=88, color=col, edgecolor='white', linewidths=0.6, zorder=8)
            cid = tr.get('Cluster_ID', '')
            try:
                cid_i = int(float(cid)) if pd.notna(cid) else 0
            except (TypeError, ValueError):
                cid_i = 0
            ax.text(
                ex,
                float(tr['Entry_Price']),
                f'  ORB#{cid_i}',
                color='#F3E5F5',
                fontsize=7,
                va='bottom' if direction == 'Long' else 'top',
                zorder=9,
            )

        xm = ydf.loc[dates_series.eq(exit_ts)]
        if not xm.empty:
            xx = mdates.date2num(pd.Timestamp(xm.iloc[-1]['date_ts']).to_pydatetime())
            ax.scatter(xx, float(tr['Exit_Price']), marker='X', s=72, color='#FF5252', edgecolor='white', linewidths=0.5, zorder=8)


def draw_yearly_range_lines(
    daily: pd.DataFrame,
    out_root: Path,
    market_label: str = 'MNQ',
    overlap_trades: pd.DataFrame | None = None,
) -> None:
    root = out_root / 'monthly_orb_yearly_range_lines'
    root.mkdir(parents=True, exist_ok=True)
    work = daily.copy()
    work['date_ts'] = pd.to_datetime(work['date'])
    work['year'] = work['date_ts'].dt.year
    work['month'] = work['date_ts'].dt.month
    root_lines = [
        f'# {market_label} monthly OR rails by year',
        '',
        'Daily candles sit behind each month\'s opening-range high/low rails. '
        'When `mnq_monthly_orb_overlap_range_breakout.csv` is present, **overlap-cluster** trades are drawn: '
        'lavender band = combined cluster range; **orange dashed** = stop; **green dashed** = target; '
        'triangle = entry, red X = exit.',
        '',
    ]
    for year, ydf in work.groupby('year', sort=True):
        ydf = ydf.sort_values('date_ts').reset_index(drop=True)
        fig = plt.figure(figsize=(15, 7.5), facecolor='#0D1B2A')
        ax = fig.add_subplot(111)
        ax.set_facecolor('#0D1B2A')
        draw_daily_candles(ax, ydf)
        ymins: list[float] = []
        ymaxs: list[float] = []
        for month, mdf in ydf.groupby('month', sort=True):
            mdf = mdf.sort_values('date_ts').reset_index(drop=True)
            if len(mdf) < 3:
                continue
            rb = mdf.iloc[:3]
            rh = float(rb['high'].max())
            rl = float(rb['low'].min())
            start = pd.Timestamp(mdf.iloc[0]['date_ts'])
            end = pd.Timestamp(mdf.iloc[-1]['date_ts'])
            color = '#26A69A' if float(mdf.iloc[-1]['close']) >= rh else '#EF5350' if float(mdf.iloc[-1]['close']) <= rl else '#FFD54F'
            ax.hlines([rh, rl], start, end, colors=color, linewidth=1.45, alpha=0.98, zorder=5)
            ax.fill_between([start, end], rl, rh, color=color, alpha=0.045, zorder=1)
            ax.text(start, rh, f' {month:02d}', color=color, fontsize=7, va='bottom', zorder=6)
            ymins.append(rl)
            ymaxs.append(rh)
        if not ymins:
            plt.close(fig)
            continue
        ymins.extend(float(v) for v in ydf['low'])
        ymaxs.extend(float(v) for v in ydf['high'])
        draw_overlap_trade_overlays(ax, ydf, overlap_trades, ymins, ymaxs)
        title = f'{market_label} daily candles with monthly opening-range rails | {year}'
        if overlap_trades is not None and not overlap_trades.empty:
            title += ' | overlap ORB trades'
        ax.set_title(title, color='white', fontsize=12)
        ax.grid(True, color='white', alpha=0.08)
        ax.tick_params(colors='white')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
        ax.set_xlim(pd.Timestamp(ydf.iloc[0]['date_ts']) - pd.Timedelta(days=3), pd.Timestamp(ydf.iloc[-1]['date_ts']) + pd.Timedelta(days=3))
        ax.set_ylim(min(ymins) * 0.995, max(ymaxs) * 1.005)
        fig.tight_layout()
        out_path = root / f'{year}.png'
        fig.savefig(out_path, dpi=140)
        plt.close(fig)
        root_lines.append(f'- [{year}]({year}.png)')
    (root / 'INDEX.md').write_text('\n'.join(root_lines) + '\n')


def write_report(events: pd.DataFrame, out_path: Path) -> None:
    if events.empty:
        out_path.write_text('# MNQ Monthly ORB Daily-Close Breakout Diagnostics\n\nNo events.\n')
        return
    total = len(events)
    false_count = int(events['False_Break_Opposing_Before_1R'].sum())
    hit_1r = int(events['Hit_1R_Before_Opposing'].sum())
    clean = int(events['Clean_1R_No_Daily_Close_Inside_No_4H_Trade_Back_Into_Range'].sum())
    hit_2r = int(events['Hit_2R'].sum())
    clean_2r = int(events['Clean_And_Hit_2R'].sum())
    by_dir = events.groupby('Direction').agg(
        breaks=('Direction', 'size'),
        false_breaks=('False_Break_Opposing_Before_1R', 'sum'),
        hit_1r=('Hit_1R_Before_Opposing', 'sum'),
        clean_1r=('Clean_1R_No_Daily_Close_Inside_No_4H_Trade_Back_Into_Range', 'sum'),
        hit_2r=('Hit_2R', 'sum'),
        clean_2r=('Clean_And_Hit_2R', 'sum'),
        avg_mae=('Max_Adverse_Pts', 'mean'),
        avg_mfe=('Max_Favorable_Pts', 'mean'),
    ).reset_index()

    lines = [
        '# MNQ Monthly ORB Daily-Close Breakout Diagnostics',
        '',
        'A breakout is counted only when a daily candle closes outside the monthly opening range after the first three trading sessions. After that close is known, the script tracks later 4-hour candles through the rest of the month.',
        '',
        'Definitions:',
        '',
        '- **Clean 1R:** TP1 trades before any daily close back inside the OR and before any 4h candle trades back into the OR.',
        '- **Wide-berth 1R:** TP1 trades before the opposing OR boundary, ignoring interim retests/closes.',
        '- **False break:** opposing OR boundary trades before TP1.',
        '- Same-bar ambiguity is conservative: an opposing-boundary touch before TP1 wins over TP1, and a range retest in the same 4h candle prevents a clean label.',
        '',
        f'- Total daily-close breakouts: **{total}**',
        f'- False breaks: **{false_count}** ({false_count / total:.1%})',
        f'- Wide-berth TP1 before opposing boundary: **{hit_1r}** ({hit_1r / total:.1%})',
        f'- Clean 1R: **{clean}** ({clean / total:.1%})',
        f'- Hit TP2: **{hit_2r}** ({hit_2r / total:.1%})',
        f'- Clean and hit TP2: **{clean_2r}** ({clean_2r / total:.1%})',
        '',
        '| Direction | Breaks | False | Wide TP1 | Clean 1R | Hit TP2 | Clean+TP2 | Avg MAE pts | Avg MFE pts |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for _, row in by_dir.iterrows():
        lines.append(
            f"| {row['Direction']} | {int(row['breaks'])} | {int(row['false_breaks'])} | "
            f"{int(row['hit_1r'])} | {int(row['clean_1r'])} | {int(row['hit_2r'])} | "
            f"{int(row['clean_2r'])} | {float(row['avg_mae']):.1f} | {float(row['avg_mfe']):.1f} |"
        )
    lines.extend(
        [
            '',
            '## Outputs',
            '',
            '- `mnq/mnq_monthly_orb_daily_close_breakout_diagnostics.csv`',
            '- `mnq/case_studies/monthly_orb/daily_close_breakout_diagnostics/clean_months/INDEX.md`',
            '- `mnq/case_studies/monthly_orb/monthly_orb_yearly_range_lines/INDEX.md`',
        ]
    )
    out_path.write_text('\n'.join(lines) + '\n')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, default=DAILY)
    ap.add_argument('--bars-4h', type=Path, default=FOUR_H_CACHE)
    ap.add_argument('--out-csv', type=Path, default=OUT_CSV)
    ap.add_argument('--case-root', type=Path, default=CASE_ROOT)
    ap.add_argument('--no-clean-charts', action='store_true')
    ap.add_argument('--no-yearly-range-lines', action='store_true')
    ap.add_argument(
        '--overlap-trades',
        type=Path,
        default=OVERLAP_TRADES_CSV,
        help='Overlap-range breakout trades CSV (default: mnq/mnq_monthly_orb_overlap_range_breakout.csv).',
    )
    ap.add_argument('--no-overlap-trades', action='store_true', help='Do not draw overlap trade overlays on yearly charts.')
    ap.add_argument(
        '--yearly-range-lines-only',
        action='store_true',
        help='Only rebuild monthly_orb_yearly_range_lines PNGs (no 4h load / diagnostics CSV).',
    )
    args = ap.parse_args()

    if args.yearly_range_lines_only:
        daily = load_daily(args.daily)
        overlap: pd.DataFrame | None = None
        if not args.no_overlap_trades:
            overlap = load_overlap_trades_csv(args.overlap_trades)
            if overlap is None:
                print(f'Note: overlap trades not found at {args.overlap_trades}; yearly charts without overlays')
        draw_yearly_range_lines(daily, args.case_root, overlap_trades=overlap)
        yr = args.case_root / 'monthly_orb_yearly_range_lines'
        print(f'Wrote yearly range lines under {yr}')
        return 0

    daily = load_daily(args.daily)
    bars4h = load_cached_4h(args.bars_4h)
    events, period_bars, period_daily = run_diagnostics(daily, bars4h)
    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    events.to_csv(args.out_csv, index=False)
    if not args.no_clean_charts:
        build_clean_month_charts(events, period_bars, period_daily, args.case_root)
    if not args.no_yearly_range_lines:
        overlap = None
        if not args.no_overlap_trades:
            overlap = load_overlap_trades_csv(args.overlap_trades)
            if overlap is None:
                print(f'Note: overlap trades not found at {args.overlap_trades}; yearly charts without overlays')
        draw_yearly_range_lines(daily, args.case_root, overlap_trades=overlap)
    write_report(events, OUT_REPORT)
    print(f'Wrote {args.out_csv} ({len(events)} rows)')
    print(f'Wrote {OUT_REPORT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
