#!/usr/bin/env python3
"""Build weekly-candle sidecar charts for the yearly ORB scaleout3 candidate."""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
VARIANT = 'yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close'

MARKETS = {
    'mnq': {
        'label': 'MNQ',
        'daily': ROOT / 'mnq' / 'mnq_daily.csv',
        'trades': ROOT / 'mnq' / f'mnq_{VARIANT}.csv',
        'case_dir': ROOT / 'mnq' / 'case_studies' / VARIANT,
        'point_value': 2.0,
    },
    'nq': {
        'label': 'NQ',
        'daily': ROOT / 'nq' / 'nq_daily.csv',
        'trades': ROOT / 'nq' / f'nq_{VARIANT}.csv',
        'case_dir': ROOT / 'nq' / 'case_studies' / VARIANT,
        'point_value': 20.0,
    },
}

BG = '#0D1B2A'
GRID = '#9FB3C8'
GREEN = '#26A69A'
RED = '#EF5350'
TEXT = '#E8EEF5'
RANGE_BLUE = '#1F4E79'
ENTRY_YELLOW = '#FFC107'


def load_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=['date'])
    df = df.sort_values('date').reset_index(drop=True)
    df['year'] = df['date'].dt.year
    df['month'] = df['date'].dt.month
    return df


def load_trades(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if df.empty:
        return df
    df['Period'] = df['Period'].astype(str)
    for col in [
        'Entry_Date',
        'Breakout_Date',
        'Stop_Source_Date',
        'Unit1_Exit_Date',
        'Unit2_Exit_Date',
        'Unit3_Exit_Date',
    ]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    return df


def existing_years(case_dir: Path) -> list[int]:
    years: list[int] = []
    if not case_dir.exists():
        return years
    for path in case_dir.iterdir():
        if path.is_dir() and path.name.isdigit():
            years.append(int(path.name))
    return sorted(years)


def resample_weekly(year_bars: pd.DataFrame) -> pd.DataFrame:
    work = year_bars.copy().sort_values('date').reset_index(drop=True)
    work['week'] = work['date'].dt.to_period('W-FRI')
    rows: list[dict] = []
    for week, sub in work.groupby('week', sort=True):
        sub = sub.sort_values('date')
        rows.append(
            {
                'week': str(week),
                'week_start': pd.Timestamp(sub['date'].iloc[0]),
                'week_end': pd.Timestamp(sub['date'].iloc[-1]),
                'plot_date': pd.Timestamp(week.end_time).normalize(),
                'open': float(sub['open'].iloc[0]),
                'high': float(sub['high'].max()),
                'low': float(sub['low'].min()),
                'close': float(sub['close'].iloc[-1]),
                'volume': float(sub['volume'].sum()) if 'volume' in sub.columns else 0.0,
                'symbol': str(sub['symbol'].iloc[-1]) if 'symbol' in sub.columns else '',
            }
        )
    return pd.DataFrame(rows)


def range_meta(year: int, year_bars: pd.DataFrame, trades: pd.DataFrame) -> dict:
    rows = trades[trades['Period'].astype(str).eq(str(year))] if not trades.empty else pd.DataFrame()
    range_bars = year_bars[year_bars['month'] <= 3]
    if not rows.empty:
        return {
            'range_high': float(rows.iloc[0]['Range_High']),
            'range_low': float(rows.iloc[0]['Range_Low']),
            'range': float(rows.iloc[0]['Range']),
            'symbol': str(rows.iloc[0]['Symbol']),
            'range_days': int(rows.iloc[0]['Range_Days']),
            'trade_days': int(rows.iloc[0]['Trade_Days']),
        }
    if range_bars.empty:
        return {'range_high': 0.0, 'range_low': 0.0, 'range': 0.0, 'symbol': '', 'range_days': 0, 'trade_days': 0}
    rh = float(range_bars['high'].max())
    rl = float(range_bars['low'].min())
    trade_days = int((year_bars['month'] > 3).sum())
    symbol = str(year_bars.iloc[0]['symbol']) if 'symbol' in year_bars.columns and not year_bars.empty else ''
    return {'range_high': rh, 'range_low': rl, 'range': rh - rl, 'symbol': symbol, 'range_days': len(range_bars), 'trade_days': trade_days}


def draw_weekly_candles(ax: plt.Axes, weekly: pd.DataFrame) -> None:
    xs = mdates.date2num(pd.to_datetime(weekly['plot_date']))
    width = 4.4
    for x, (_, row) in zip(xs, weekly.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        color = GREEN if c >= o else RED
        ax.vlines(x, l, h, color=color, linewidth=1.05, zorder=3)
        body_low = min(o, c)
        body_high = max(o, c)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, body_low),
                width,
                max(body_high - body_low, 0.05),
                facecolor=color,
                edgecolor=color,
                linewidth=0.65,
                alpha=0.92,
                zorder=3,
            )
        )


def draw_weekly_volume(ax: plt.Axes, weekly: pd.DataFrame) -> None:
    if 'volume' not in weekly.columns or weekly['volume'].fillna(0).sum() <= 0:
        ax.text(0.5, 0.5, 'No volume column available', transform=ax.transAxes, color=TEXT, ha='center')
        return
    xs = mdates.date2num(pd.to_datetime(weekly['plot_date']))
    colors = [GREEN if float(row['close']) >= float(row['open']) else RED for _, row in weekly.iterrows()]
    volumes = weekly['volume'].astype(float)
    ax.bar(xs, volumes, width=4.6, color=colors, alpha=0.55, align='center', zorder=2)
    vol_ma = volumes.rolling(20, min_periods=4).mean()
    ax.plot(xs, vol_ma, color='#FFD54F', linewidth=1.1, alpha=0.95, zorder=3, label='20w avg volume')
    ax.set_ylabel('Weekly vol', color=GRID, fontsize=8)
    ax.tick_params(colors=GRID, labelsize=8)
    ax.grid(True, alpha=0.13, color=GRID)
    for spine in ax.spines.values():
        spine.set_color('#3A506B')
    ax.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda value, _pos: f'{value / 1_000_000:.1f}M' if value >= 1_000_000 else f'{value / 1_000:.0f}K')
    )


def parse_date(value: object) -> pd.Timestamp | None:
    if pd.isna(value) or str(value).strip() == '':
        return None
    return pd.Timestamp(value)


def draw_trades(ax: plt.Axes, rows: pd.DataFrame) -> tuple[float, str]:
    if not rows.empty and 'Trade_Direction' in rows.columns:
        rows = rows[~rows['Trade_Direction'].astype(str).eq('No-Op')].copy()
    if rows.empty:
        return 0.0, 'No-Op'
    exit_colors = {
        'TP25': '#64FFDA',
        'TP': '#76FF03',
        'BE-Stop': '#B0BEC5',
        'Swing-Stop': '#FF1744',
        'Range-Close': '#FFB74D',
        'Period-Close': '#BA68C8',
    }
    total = float(rows['Trade_PL'].astype(float).sum())
    pattern = '+'.join(f"{str(row['Trade_Direction'])[0]}{str(row['Result'])[0]}" for _, row in rows.iterrows())
    label_offsets = [18, -26, 34, -42, 50, -58, 66, -74]
    for i, (_, row) in enumerate(rows.iterrows(), 1):
        direction = str(row['Trade_Direction'])
        entry_date = parse_date(row.get('Entry_Date'))
        if entry_date is None:
            continue
        entry = float(row['Entry_Price'])
        ax.scatter(
            [mdates.date2num(entry_date)],
            [entry],
            marker='^' if direction == 'Long' else 'v',
            color=ENTRY_YELLOW,
            s=95,
            zorder=10,
            edgecolor='black',
            linewidth=0.8,
        )
        stop_source_date = parse_date(row.get('Stop_Source_Date'))
        if stop_source_date is not None and pd.notna(row.get('Stop_Source_Price')):
            ax.scatter(
                [mdates.date2num(stop_source_date)],
                [float(row['Stop_Source_Price'])],
                marker='o',
                color='#64B5F6',
                s=42,
                zorder=9,
                edgecolor='black',
                linewidth=0.6,
            )
        exit_dates: list[pd.Timestamp] = []
        for unit in (1, 2, 3):
            ex_date = parse_date(row.get(f'Unit{unit}_Exit_Date'))
            ex_price = row.get(f'Unit{unit}_Exit_Price')
            reason = str(row.get(f'Unit{unit}_Exit_Reason') or '')
            if ex_date is None or pd.isna(ex_price):
                continue
            exit_dates.append(ex_date)
            color = exit_colors.get(reason, '#E0E0E0')
            ax.scatter(
                [mdates.date2num(ex_date)],
                [float(ex_price)],
                marker='X',
                color=color,
                s=86,
                zorder=10,
                edgecolor='black',
                linewidth=0.75,
            )
        if exit_dates:
            last_exit = max(exit_dates)
        else:
            last_exit = entry_date
        x0 = mdates.date2num(entry_date)
        x1 = mdates.date2num(last_exit)
        for price, color, alpha in [
            (row.get('TP25_Price'), '#64FFDA', 0.40),
            (row.get('TP_Price'), '#76FF03', 0.50),
            (row.get('Initial_Stop_Price'), '#FF1744', 0.48),
        ]:
            if pd.notna(price):
                ax.plot([x0, x1], [float(price), float(price)], color=color, linewidth=0.75, alpha=alpha, zorder=4)
        final_price = None
        final_reason = str(row.get('Final_Reason') or '')
        for unit in (3, 2, 1):
            price = row.get(f'Unit{unit}_Exit_Price')
            if pd.notna(price):
                final_price = float(price)
                break
        if final_price is not None:
            color = exit_colors.get(final_reason.split('+')[-1], '#E0E0E0')
            ax.annotate(
                f"#{i} {direction[0]} {float(row['Trade_PL']):+.0f}",
                xy=(mdates.date2num(last_exit), final_price),
                xytext=(7, label_offsets[(i - 1) % len(label_offsets)]),
                textcoords='offset points',
                color=color,
                fontsize=7,
                fontweight='bold',
                ha='left',
                bbox=dict(boxstyle='round,pad=0.18', fc=BG, ec=color, alpha=0.92),
            )
    return total, pattern


def draw_year(
    market: str,
    cfg: dict,
    year: int,
    year_bars: pd.DataFrame,
    trade_rows: pd.DataFrame,
    out_path: Path,
    volume_panel: bool,
) -> dict:
    weekly = resample_weekly(year_bars)
    meta = range_meta(year, year_bars, trade_rows)

    if volume_panel:
        fig, (ax, ax_vol) = plt.subplots(
            2,
            1,
            sharex=True,
            figsize=(18, 10.4),
            facecolor=BG,
            gridspec_kw={'height_ratios': [4.7, 1.05], 'hspace': 0.04},
        )
        ax_vol.set_facecolor(BG)
    else:
        fig = plt.figure(figsize=(18, 9), facecolor=BG)
        ax = fig.add_subplot(111)
        ax_vol = None
    ax.set_facecolor(BG)
    draw_weekly_candles(ax, weekly)
    if ax_vol is not None:
        draw_weekly_volume(ax_vol, weekly)

    range_bars = year_bars[year_bars['month'] <= 3]
    if not range_bars.empty:
        ax.axvspan(
            pd.Timestamp(range_bars.iloc[0]['date']),
            pd.Timestamp(range_bars.iloc[-1]['date']) + pd.Timedelta(days=1),
            color=RANGE_BLUE,
            alpha=0.28,
            zorder=0,
        )

    rh = float(meta['range_high'])
    rl = float(meta['range_low'])
    rv = float(meta['range'])
    if rv > 0:
        ax.axhline(rh, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
        ax.axhline(rl, color='#E0E0E0', linestyle='--', linewidth=1.0, zorder=2)
        ax.axhspan(rl, rh, color=RANGE_BLUE, alpha=0.10, zorder=0)
        last_x = mdates.date2num(pd.Timestamp(year_bars['date'].iloc[-1])) + 2.0
        ax.text(last_x, rh, f' RH {rh:.1f}', color='#E0E0E0', fontsize=8, va='center')
        ax.text(last_x, rl, f' RL {rl:.1f}', color='#E0E0E0', fontsize=8, va='center')

    year_rows = trade_rows[trade_rows['Period'].astype(str).eq(str(year))].copy() if not trade_rows.empty else pd.DataFrame()
    if not year_rows.empty and 'Trade_Direction' in year_rows.columns:
        year_rows = year_rows[~year_rows['Trade_Direction'].astype(str).eq('No-Op')].copy()
    total_pl, pattern = draw_trades(ax, year_rows)

    dates = pd.to_datetime(year_bars['date'])
    y_low = float(min(year_bars['low'].min(), rl if rv > 0 else year_bars['low'].min()))
    y_high = float(max(year_bars['high'].max(), rh if rv > 0 else year_bars['high'].max()))
    y_rng = max(y_high - y_low, 1.0)
    ax.set_ylim(y_low - y_rng * 0.07, y_high + y_rng * 0.10)
    ax.set_xlim(dates.iloc[0] - pd.Timedelta(days=7), dates.iloc[-1] + pd.Timedelta(days=12))

    ax.set_title(
        (
            f'{year} {cfg["label"]} YEARLY ORB weekly candles · Jan-Mar range · '
            f'{len(year_rows)} trades · {pattern} · {total_pl:+.1f} contract-pts '
            f'(${total_pl * cfg["point_value"]:+,.0f})'
        ),
        color='white',
        fontsize=10,
        fontweight='bold',
        pad=8,
        loc='left',
    )
    ax.tick_params(colors=GRID, labelsize=8)
    for spine in ax.spines.values():
        spine.set_color('#3A506B')
    ax.grid(True, alpha=0.15, color=GRID)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    if ax_vol is not None:
        ax_vol.xaxis.set_major_locator(mdates.MonthLocator())
        ax_vol.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    legend_handles = [
        mpatches.Patch(facecolor=GREEN, edgecolor=GREEN, label='Weekly up candle'),
        mpatches.Patch(facecolor=RED, edgecolor=RED, label='Weekly down candle'),
        mpatches.Patch(facecolor='none', edgecolor='#E0E0E0', label='Yearly ORB H/L'),
        mpatches.Patch(facecolor='none', edgecolor=ENTRY_YELLOW, label='Trade entry marker'),
    ]
    if volume_panel:
        legend_handles.append(mpatches.Patch(facecolor='#FFD54F', edgecolor='#FFD54F', label='20w volume avg'))
    leg = ax.legend(handles=legend_handles, loc='upper left', fontsize=7, framealpha=0.16)
    for text in leg.get_texts():
        text.set_color(TEXT)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=105, bbox_inches='tight', facecolor=BG)
    plt.close(fig)

    return {
        'year': year,
        'symbol': meta['symbol'],
        'range_days': meta['range_days'],
        'trade_days': meta['trade_days'],
        'range': round(rv, 2),
        'year_volume': round(float(weekly['volume'].sum()), 0) if 'volume' in weekly.columns else 0.0,
        'range_volume': round(float(weekly[pd.to_datetime(weekly['week_end']).dt.month.le(3)]['volume'].sum()), 0)
        if 'volume' in weekly.columns
        else 0.0,
        'pattern': pattern,
        'trades': len(year_rows),
        'net_pts': round(total_pl, 2),
        'net_usd': round(total_pl * cfg['point_value'], 2),
        'chart': f'{year}/{year}.png',
    }


def write_indexes(out_dir: Path, cfg: dict, rows: list[dict], volume_panel: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        year_dir = out_dir / str(row['year'])
        lines = [
            f'# {row["year"]} {cfg["label"]} Yearly ORB Weekly-Candle Chart',
            '',
            (
                'Weekly candles resampled from the daily OHLCV data. Bottom panel shows weekly volume and a 20-week volume average. '
                'Trade markers and ORB levels come from the current yearly ORB scaleout3 inside-range swing/range-close study.'
            )
            if volume_panel
            else 'Weekly candles resampled from the daily data. Trade markers and ORB levels come from the current yearly ORB scaleout3 inside-range swing/range-close study.',
            '',
            f'Chart: [{row["year"]}.png]({row["year"]}.png)',
            '',
            '| Year | Symbol | Range Days | Trade Days | Range | Year Vol | OR Vol | Pattern | Trades | Net contract-pts |',
            '|---:|---|---:|---:|---:|---:|---:|---|---:|---:|',
            f"| {row['year']} | {row['symbol']} | {row['range_days']} | {row['trade_days']} | {row['range']:.2f} | {row['year_volume'] / 1_000_000:.2f}M | {row['range_volume'] / 1_000_000:.2f}M | {row['pattern']} | {row['trades']} | {row['net_pts']:+.2f} |",
            '',
        ]
        (year_dir / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')

    total = sum(float(row['net_pts']) for row in rows)
    lines = [
        f'# {cfg["label"]} Yearly ORB Weekly-Candle{" Volume" if volume_panel else ""} Sidecar Charts',
        '',
        (
            'These charts preserve the current yearly ORB trade annotations, but redraw the price action as weekly candles with a bottom volume panel. '
            'The original daily and weekly price-only chart folders are unchanged.'
        )
        if volume_panel
        else 'These charts preserve the current yearly ORB trade annotations, but redraw the price action as weekly candles instead of daily candles. The original daily chart folders are unchanged.',
        '',
        f'Years charted: `{len(rows)}`  ·  Net: `{total:+.2f}` contract-pts (${total * cfg["point_value"]:+,.0f})',
        '',
        '| Year | Symbol | Range Days | Trade Days | Range | Year Vol | OR Vol | Pattern | Trades | Net contract-pts | Chart |',
        '|---:|---|---:|---:|---:|---:|---:|---|---:|---:|---|',
    ]
    for row in rows:
        lines.append(
            f"| {row['year']} | {row['symbol']} | {row['range_days']} | {row['trade_days']} | "
            f"{row['range']:.2f} | {row['year_volume'] / 1_000_000:.2f}M | {row['range_volume'] / 1_000_000:.2f}M | "
            f"{row['pattern']} | {row['trades']} | {row['net_pts']:+.2f} | "
            f"[{row['year']}/]({row['year']}/INDEX.md) |"
        )
    lines.append('')
    (out_dir / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')


def update_base_index(case_dir: Path, volume_panel: bool) -> None:
    index = case_dir / 'INDEX.md'
    if not index.exists():
        return
    text = index.read_text(encoding='utf-8')
    line = (
        '- [Weekly-candle volume sidecar charts](weekly_candles_volume/INDEX.md)'
        if volume_panel
        else '- [Weekly-candle sidecar charts](weekly_candles/INDEX.md)'
    )
    if line in text:
        return
    if '## Sidecar Studies' in text:
        text = text.rstrip() + '\n' + line + '\n'
    else:
        text = text.rstrip() + '\n\n## Sidecar Studies\n\n' + line + '\n'
    index.write_text(text, encoding='utf-8')


def run_market(market: str, clean: bool, volume_panel: bool) -> Path:
    cfg = MARKETS[market]
    daily = load_daily(cfg['daily'])
    trades = load_trades(cfg['trades'])
    years = existing_years(cfg['case_dir'])
    out_dir = cfg['case_dir'] / ('weekly_candles_volume' if volume_panel else 'weekly_candles')
    if clean and out_dir.exists():
        shutil.rmtree(out_dir)
    rows: list[dict] = []
    for year in years:
        year_bars = daily[daily['year'].eq(year)].copy()
        if year_bars.empty:
            continue
        row = draw_year(market, cfg, year, year_bars, trades, out_dir / str(year) / f'{year}.png', volume_panel)
        rows.append(row)
        print(f"{cfg['label']} {row['chart']} trades={row['trades']} net={row['net_pts']:+.2f}")
    write_indexes(out_dir, cfg, rows, volume_panel)
    update_base_index(cfg['case_dir'], volume_panel)
    print(f"Wrote {cfg['label']} weekly-candle{' volume' if volume_panel else ''} charts: {out_dir / 'INDEX.md'}")
    return out_dir


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--market', choices=['mnq', 'nq', 'both'], default='both')
    ap.add_argument('--clean', action='store_true', help='Remove existing weekly_candles output first.')
    ap.add_argument('--volume-panel', action='store_true', help='Write sidecar charts with a weekly volume panel.')
    args = ap.parse_args()
    markets = ['mnq', 'nq'] if args.market == 'both' else [args.market]
    for market in markets:
        run_market(market, args.clean, args.volume_panel)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
