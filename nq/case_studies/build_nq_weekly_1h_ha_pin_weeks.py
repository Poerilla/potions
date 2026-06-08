#!/usr/bin/env python3
"""
NQ weekly 1h charts for every week containing ≥1 causal Heikin Ashi pin bar.

Same layout as the RTH level study (levels + RTH shading, no trades).
HA pin bars: black outline on the **real** 1h candle (HA computed causally).

Usage::

  python3 nq/case_studies/build_nq_weekly_1h_ha_pin_weeks.py --force
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, time
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd

HERE = Path(__file__).resolve().parent
POTIONS_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(POTIONS_ROOT))

from build_nq_weekly_1h_level_study import (  # noqa: E402
    BG,
    NY,
    build_daily_atr,
    build_weekly_table,
    concat_1m,
    load_1m_by_ny_date,
    plot_candles,
    resample_1h,
    style_axes,
    week_context,
    week_hourly_slice,
)
from build_nq_wo_gap_reversal_sample import (  # noqa: E402
    compute_ha_candles,
    ha_pins_for_week,
)
from live.build_ym_1m_atr_supertrend_sample import compute_supertrend  # noqa: E402

RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
RTH_FILL = '#243B55'
ETH_FILL = '#111D2C'
ST_ATR_LEN = 14
ST_MULT = 3.0
ST_BULL_COLOR = '#00E676'
ST_BEAR_COLOR = '#FF5252'


def resample_15m(one_min: pd.DataFrame) -> pd.DataFrame:
    return (
        one_min.resample('15min', label='right', closed='right')
        .agg(
            open=('open', 'first'),
            high=('high', 'max'),
            low=('low', 'min'),
            close=('close', 'last'),
            volume=('volume', 'sum'),
        )
        .dropna(subset=['open', 'high', 'low', 'close'])
    )


def week_15m_st_slice(st_15m: pd.DataFrame, week_start: pd.Timestamp) -> pd.DataFrame:
    week_end = week_start + pd.Timedelta(days=7)
    pad = week_start - pd.Timedelta(hours=6)
    return st_15m[(st_15m.index >= pad) & (st_15m.index < week_end)].copy()


def draw_levels_no_atr(ax, x0: float, x1: float, ctx: dict[str, float]) -> None:
    import build_nq_weekly_1h_level_study as lvl

    specs = [
        ('PWH', '#CE93D8', '-', 1.1),
        ('PWL', '#CE93D8', '-', 1.1),
        ('PWC', '#FFC107', '-.', 1.15),
        ('PWO', '#26C6DA', '-', 1.15),
        ('PW_MID', '#9FB3C8', '--', 1.0),
    ]
    for key, color, ls, lw in specs:
        lvl.hline_segment(ax, x0, x1, ctx[key], color=color, linestyle=ls, lw=lw)
    lvl.hline_segment(ax, x0, x1, ctx['WO'], color='#76FF03', linestyle='-', lw=1.0)


def shade_rth_eth(ax, bars: pd.DataFrame) -> None:
    if bars.empty:
        return
    t_start = bars.index[0] - pd.Timedelta(hours=6)
    t_end = bars.index[-1] + pd.Timedelta(hours=6)
    ax.axvspan(
        mdates.date2num(t_start),
        mdates.date2num(t_end),
        facecolor=ETH_FILL,
        alpha=0.55,
        zorder=0,
    )
    days = pd.date_range(bars.index[0].normalize(), bars.index[-1].normalize(), freq='D', tz=NY)
    for day in days:
        if day.weekday() >= 5:
            continue
        rth0 = NY.localize(datetime.combine(day.date(), RTH_OPEN))
        rth1 = NY.localize(datetime.combine(day.date(), RTH_CLOSE))
        if rth1 <= t_start or rth0 >= t_end:
            continue
        ax.axvspan(
            mdates.date2num(max(rth0, t_start)),
            mdates.date2num(min(rth1, t_end)),
            facecolor=RTH_FILL,
            alpha=0.72,
            zorder=1,
        )


def plot_week_ha_pin_chart(
    out_path: Path,
    bars: pd.DataFrame,
    ctx: dict[str, float],
    week_start: pd.Timestamp,
    ha_pins: list[tuple[int, str]],
    st_week: pd.DataFrame,
) -> None:
    fig, ax = plt.subplots(figsize=(16, 8), facecolor=BG)
    pad = max((bars['high'].max() - bars['low'].min()) * 0.08, 20.0)
    y_lo = float(bars['low'].min()) - pad
    y_hi = float(bars['high'].max()) + pad
    shade_rth_eth(ax, bars)

    x0 = mdates.date2num(bars.index[0])
    x1 = mdates.date2num(bars.index[-1])
    draw_levels_no_atr(ax, x0, x1, ctx)
    plot_candles(ax, bars, width_days=(60 / (24 * 60)) * 0.68)

    if not st_week.empty and st_week['supertrend'].notna().any():
        bull = st_week['supertrend'].where(st_week['supertrend_trend'] == 1)
        bear = st_week['supertrend'].where(st_week['supertrend_trend'] == -1)
        ax.step(
            st_week.index,
            bull,
            where='post',
            color=ST_BULL_COLOR,
            linewidth=1.4,
            alpha=0.95,
            zorder=5,
            label=f'15m ST bull ATR{ST_ATR_LEN}×{ST_MULT:g}',
        )
        ax.step(
            st_week.index,
            bear,
            where='post',
            color=ST_BEAR_COLOR,
            linewidth=1.4,
            alpha=0.95,
            zorder=5,
            label=f'15m ST bear ATR{ST_ATR_LEN}×{ST_MULT:g}',
        )

    width_days = (60 / (24 * 60)) * 0.68
    bull_n = bear_n = 0
    for i, kind in ha_pins:
        row = bars.iloc[i]
        x = mdates.date2num(bars.index[i])
        ax.add_patch(
            mpatches.Rectangle(
                (x - width_days * 0.55, float(row['low']) - 2),
                width_days * 1.1,
                float(row['high']) - float(row['low']) + 4,
                fill=False,
                edgecolor='black',
                linewidth=2.8,
                zorder=8,
            )
        )
        tag = 'HA↑pin' if kind == 'bullish_ha_pin' else 'HA↓pin'
        if kind == 'bullish_ha_pin':
            bull_n += 1
        else:
            bear_n += 1
        ax.annotate(
            tag,
            xy=(x, float(row['high']) + 3),
            fontsize=6,
            color='#ECEFF1',
            ha='center',
            zorder=9,
        )

    fri = (week_start + pd.Timedelta(days=5)).date()
    pin_txt = f' · {len(ha_pins)} HA pin ({bull_n}↑ {bear_n}↓)'
    title = (
        f"NQ 1h · {week_start.date()} – {fri} · levels + 15m ST "
        f'ATR{ST_ATR_LEN}×{ST_MULT:g} + RTH{pin_txt}'
    )
    ax.set_facecolor(BG)
    ax.set_title(title, color='white', fontsize=10, fontweight='bold', pad=8, loc='left')
    ax.tick_params(colors='#9FB3C8', labelsize=7)
    for s in ax.spines.values():
        s.set_color('#3A506B')
    ax.grid(True, alpha=0.12, color='#9FB3C8')
    handles = [
        mpatches.Patch(facecolor=RTH_FILL, alpha=0.72, label='RTH 09:30–16:00'),
        mpatches.Patch(facecolor=ETH_FILL, alpha=0.55, label='ETH / overnight'),
        mpatches.Rectangle((0, 0), 1, 1, fill=False, edgecolor='black', linewidth=2, label='HA pin bar'),
        plt.Line2D([0], [0], color=ST_BULL_COLOR, lw=1.4, label=f'15m ST bull'),
        plt.Line2D([0], [0], color=ST_BEAR_COLOR, lw=1.4, label=f'15m ST bear'),
        plt.Line2D([0], [0], color='#76FF03', lw=1.0, label='WO'),
        plt.Line2D([0], [0], color='#CE93D8', lw=1.1, label='PWH/PWL'),
    ]
    ax.legend(
        handles=handles,
        loc='upper left',
        facecolor='#1B263B',
        edgecolor='#37474F',
        labelcolor='#ECEFF1',
        fontsize=7,
        ncol=2,
    )
    ax.set_ylabel('NQ', color='#9FB3C8')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%a %H:%M', tz=NY))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
    ax.set_xlim(bars.index[0] - pd.Timedelta(hours=2), bars.index[-1] + pd.Timedelta(hours=2))
    ax.set_ylim(y_lo, y_hi)
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, bbox_inches='tight', facecolor=BG)
    plt.close(fig)


def build(*, output_root: Path, start: str, force: bool) -> str:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    dbn = HERE.parent / 'raw' / 'glbx-mdp3-20100606-20260308.ohlcv-1m.dbn.zst'
    print('Loading NQ 1m ...', flush=True)
    gby = load_1m_by_ny_date(dbn, 'nq')
    one_min = concat_1m(gby)
    one_min = one_min[one_min.index >= pd.Timestamp(start, tz=NY)]
    hourly = resample_1h(one_min)
    bars_15m = compute_supertrend(resample_15m(one_min), atr_len=ST_ATR_LEN, multiplier=ST_MULT)
    ha_full = compute_ha_candles(hourly)
    daily_atr = build_daily_atr(hourly)
    weekly = build_weekly_table(hourly, daily_atr)

    rows: list[dict] = []
    first_chart = ''
    chart_n = 0

    for w in weekly.index:
        ctx = week_context(weekly, w)
        if ctx is None:
            continue
        ws = weekly.loc[w, 'week_start']
        if ws < pd.Timestamp(start, tz=NY):
            continue
        bars = week_hourly_slice(hourly, ws)
        if len(bars) < 12:
            continue
        pins = ha_pins_for_week(bars, ha_full)
        if not pins:
            continue

        chart_n += 1
        year = ws.year
        rel = f'charts/{year}/{ws.date().isoformat()}.png'
        if not first_chart:
            first_chart = rel
        plot_week_ha_pin_chart(
            output_root / rel,
            bars,
            ctx,
            ws,
            pins,
            week_15m_st_slice(bars_15m, ws),
        )

        bull = sum(1 for _, k in pins if k == 'bullish_ha_pin')
        bear = len(pins) - bull
        rows.append(
            {
                'week_start': ws.date().isoformat(),
                'year': year,
                'chart': rel,
                'ha_pins': len(pins),
                'bullish_pins': bull,
                'bearish_pins': bear,
                'WO': ctx['WO'],
            }
        )
        if chart_n % 50 == 0:
            print(f'  … {chart_n} charts', flush=True)

    pd.DataFrame(rows).to_csv(output_root / 'manifest.csv', index=False)
    year_counts = pd.Series([r['year'] for r in rows]).value_counts().sort_index()
    total_pins = sum(r['ha_pins'] for r in rows)
    lines = [
        '# NQ weekly 1h — weeks with Heikin Ashi pin bars',
        '',
        f'**{len(rows)}** weeks with ≥1 causal HA pin on 1h candles · no trades.',
        f'Total HA pin bars flagged: **{total_pins}**.',
        '',
        '### HA pin (causal)',
        '- Body ≤ 25% of HA range',
        '- Bullish: lower wick ≥ 65%, upper ≤ 15%',
        '- Bearish: upper wick ≥ 65%, lower ≤ 15%',
        '- **Black outline** on real 1h candle (fills use real OHLC)',
        '',
        '### Chart',
        '- Prior-week levels + WO · RTH 09:30–16:00 shaded',
        f'- **15m Supertrend** `ATR({ST_ATR_LEN}) × {ST_MULT:g}` trailing stop (green bull / red bear step line on 1h chart)',
        '- Paths: `charts/YYYY/YYYY-MM-DD.png`',
        '',
        f'Earliest data: `{start}`',
        '',
        '## By year',
        '',
    ]
    for y, c in year_counts.items():
        lines.append(f'- **{y}**: {c} weeks')
    lines.extend(
        [
            '',
            '| Week | HA pins (↑/↓) | Chart |',
            '|---|---|---|',
        ]
    )
    for r in rows:
        p = f'{r["ha_pins"]} ({r["bullish_pins"]}↑/{r["bearish_pins"]}↓)'
        lines.append(f'| {r["week_start"]} | {p} | [{r["chart"].split("/")[-1]}]({r["chart"]}) |')

    (output_root / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Done → {len(rows)} charts · {output_root / "INDEX.md"}', flush=True)
    return first_chart


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--output-root', type=Path, default=HERE / 'nq_weekly_1h_ha_pin_weeks')
    ap.add_argument('--start', type=str, default='2011-01-01')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()
    first = build(output_root=args.output_root, start=args.start, force=args.force)
    if first:
        print(f'First chart: {args.output_root / first}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
