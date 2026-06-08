#!/usr/bin/env python3
"""
NQ WO 55% breakout reversal study (sample charts).

**Pre-gap context:** ≥1 prior 1h bar fully O+C above WO (short) or below WO (long); wicks may touch WO.
**Gap candle:** crosses WO with ≥55% of O–C on exit side (long: open < WO < close; short: mirror).
**Entry:** limit @ WO from the **next** bar only (never on gap bar).
**Post-gap filter:** no fill if a 3-bar swing forms before WO retest, unless the gap bar is part of that swing.
**Fill window:** ``MAX_FILL_WAIT_BARS`` bars after gap; else ``no_fill``.
**Exit:** 2ct scale-out — +50 on leg 1, runner ±300, SL ∓50 (BE on runner after +50).
Max 2 trades/week; no second trade after TP1 / target win.
Charts: **black outline** = causal Heikin Ashi pin bar on that 1h candle.

Usage::

  python3 nq/case_studies/build_nq_wo_gap_reversal_sample.py --force
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
POTIONS_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from build_nq_weekly_1h_level_study import (  # noqa: E402
    BG,
    NY,
    build_daily_atr,
    build_weekly_table,
    clip_sun_fri_through_friday_close,
    concat_1m,
    draw_levels,
    load_1m_by_ny_date,
    plot_candles,
    prior_week_levels,
    resample_1h,
    style_axes,
    week_context,
    week_hourly_slice,
)
TARGET_PTS = 300.0
STOP_PTS = 50.0
TP1_PTS = 50.0
CONTRACTS = 2
GAP_PCT = 0.55
MAX_TRADES_WEEK = 2
MAX_FILL_WAIT_BARS = 6


@dataclass
class SetupEvent:
    kind: str
    side: Literal['long', 'short']
    bar_idx: int
    ts: pd.Timestamp
    note: str = ''


@dataclass
class Trade:
    side: Literal['long', 'short']
    breakout_idx: int
    gap_idx: int
    entry_idx: int
    exit_idx: int
    entry: float
    exit: float
    target: float
    stop: float
    tp1: float
    pts: float
    result: str
    skipped: bool = False
    skip_reason: str = ''


@dataclass
class WeekSim:
    week_start: pd.Timestamp
    week_key: str
    wo: float
    events: list[SetupEvent] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def bearish_breakout_candle(row: pd.Series, wo: float) -> bool:
    """Open above WO, close below WO; ≥55% of O–C range is below WO."""
    o, c = float(row['open']), float(row['close'])
    if not (o > wo > c):
        return False
    body = o - c
    if body <= 0:
        return False
    below = wo - c
    above = o - wo
    if below <= above:
        return False
    return (below / body) >= GAP_PCT


def bullish_breakout_candle(row: pd.Series, wo: float) -> bool:
    """Open below WO, close above WO; ≥55% of O–C range is above WO."""
    o, c = float(row['open']), float(row['close'])
    if not (c > wo > o):
        return False
    body = c - o
    if body <= 0:
        return False
    above = c - wo
    below = wo - o
    if above <= below:
        return False
    return (above / body) >= GAP_PCT


def candle_fully_above_wo(row: pd.Series, wo: float) -> bool:
    o, c = float(row['open']), float(row['close'])
    return o > wo and c > wo


def candle_fully_below_wo(row: pd.Series, wo: float) -> bool:
    o, c = float(row['open']), float(row['close'])
    return o < wo and c < wo


def first_pre_gap_bar(
    bars: pd.DataFrame, wo: float, gap_idx: int, side: Literal['long', 'short']
) -> int | None:
    """First bar before gap with full O+C on the required side of WO."""
    for k in range(gap_idx):
        row = bars.iloc[k]
        if side == 'short' and candle_fully_above_wo(row, wo):
            return k
        if side == 'long' and candle_fully_below_wo(row, wo):
            return k
    return None


def is_swing_high_at(bars: pd.DataFrame, i: int) -> bool:
    if i < 1 or i >= len(bars) - 1:
        return False
    h = float(bars.iloc[i]['high'])
    return h > float(bars.iloc[i - 1]['high']) and h > float(bars.iloc[i + 1]['high'])


def is_swing_low_at(bars: pd.DataFrame, i: int) -> bool:
    if i < 1 or i >= len(bars) - 1:
        return False
    lo = float(bars.iloc[i]['low'])
    return lo < float(bars.iloc[i - 1]['low']) and lo < float(bars.iloc[i + 1]['low'])


def swing_includes_gap(gap_idx: int, swing_center: int) -> bool:
    return swing_center - 1 <= gap_idx <= swing_center + 1


def blocking_swing_before_bar(
    bars: pd.DataFrame,
    side: Literal['long', 'short'],
    gap_idx: int,
    before_bar: int,
) -> int | None:
    """Swing confirmed before ``before_bar`` (center i known once i+1 < before_bar)."""
    if before_bar < 2:
        return None
    last_center = min(before_bar - 2, len(bars) - 2)
    for i in range(max(1, gap_idx + 1), last_center + 1):
        if side == 'long':
            if is_swing_high_at(bars, i) and not swing_includes_gap(gap_idx, i):
                return i
        elif is_swing_low_at(bars, i) and not swing_includes_gap(gap_idx, i):
            return i
    return None


def compute_ha_candles(bars: pd.DataFrame) -> pd.DataFrame:
    """Causal Heikin Ashi from regular OHLC (sequential, no lookahead)."""
    rows: list[dict] = []
    prev_o = prev_c = None
    for ts, row in bars.iterrows():
        o, h, l, c = (
            float(row['open']),
            float(row['high']),
            float(row['low']),
            float(row['close']),
        )
        ha_c = (o + h + l + c) / 4.0
        ha_o = (o + c) / 2.0 if prev_o is None else (prev_o + prev_c) / 2.0
        ha_h = max(h, ha_o, ha_c)
        ha_l = min(l, ha_o, ha_c)
        rows.append({'ha_open': ha_o, 'ha_high': ha_h, 'ha_low': ha_l, 'ha_close': ha_c})
        prev_o, prev_c = ha_o, ha_c
    return pd.DataFrame(rows, index=bars.index)


def classify_ha_pin(ha: pd.Series) -> Literal['bullish_ha_pin', 'bearish_ha_pin', 'none']:
    h, l = float(ha['ha_high']), float(ha['ha_low'])
    rng = h - l
    if rng <= 0:
        return 'none'
    o, c = float(ha['ha_open']), float(ha['ha_close'])
    body = abs(c - o)
    upper = h - max(o, c)
    lower = min(o, c) - l
    body_pct = body / rng
    upper_pct = upper / rng
    lower_pct = lower / rng
    if body_pct <= 0.25 and lower_pct >= 0.65 and upper_pct <= 0.15:
        return 'bullish_ha_pin'
    if body_pct <= 0.25 and upper_pct >= 0.65 and lower_pct <= 0.15:
        return 'bearish_ha_pin'
    return 'none'


def ha_pins_for_week(bars: pd.DataFrame, ha_full: pd.DataFrame) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for i, ts in enumerate(bars.index):
        if ts not in ha_full.index:
            continue
        kind = classify_ha_pin(ha_full.loc[ts])
        if kind != 'none':
            out.append((i, kind))
    return out


def _exit_scale_2ct(
    bars: pd.DataFrame,
    side: Literal['long', 'short'],
    entry_idx: int,
    wo: float,
) -> tuple[float, str, int, bool, float]:
    """2ct: +TP1_PTS then runner TARGET_PTS; BE on runner after TP1."""
    stop = wo - STOP_PTS if side == 'long' else wo + STOP_PTS
    tp1 = wo + TP1_PTS if side == 'long' else wo - TP1_PTS
    runner_tgt = wo + TARGET_PTS if side == 'long' else wo - TARGET_PTS
    tp1_hit = False
    exit_idx = entry_idx

    for j in range(entry_idx, len(bars)):
        row = bars.iloc[j]
        h, l = float(row['high']), float(row['low'])
        if not tp1_hit:
            if side == 'long':
                if l <= stop:
                    return -STOP_PTS * CONTRACTS, 'stop_both', j, False, float(stop)
                if h >= tp1:
                    tp1_hit = True
                    exit_idx = j
            else:
                if h >= stop:
                    return -STOP_PTS * CONTRACTS, 'stop_both', j, False, float(stop)
                if l <= tp1:
                    tp1_hit = True
                    exit_idx = j
        else:
            if side == 'long':
                if l <= wo:
                    return TP1_PTS, 'tp1+be', j, True, wo
                if h >= runner_tgt:
                    return TP1_PTS + TARGET_PTS, 'tp1+target', j, True, runner_tgt
            else:
                if h >= wo:
                    return TP1_PTS, 'tp1+be', j, True, wo
                if l <= runner_tgt:
                    return TP1_PTS + TARGET_PTS, 'tp1+target', j, True, runner_tgt
            exit_idx = j

    if not tp1_hit:
        close = float(bars.iloc[exit_idx]['close'])
        leg = (close - wo) if side == 'long' else (wo - close)
        return leg * CONTRACTS, 'eod_both', exit_idx, False, close

    close = float(bars.iloc[exit_idx]['close'])
    leg2 = (close - wo) if side == 'long' else (wo - close)
    return TP1_PTS + leg2, 'tp1+eod', exit_idx, True, close


def simulate_fill_and_exit(
    bars: pd.DataFrame,
    side: Literal['long', 'short'],
    breakout_idx: int,
    wo: float,
) -> tuple[Trade | None, str | None]:
    """Limit @ WO from bar after gap; 2ct scale-out exit."""
    entry_idx = None
    fill_end = min(breakout_idx + 1 + MAX_FILL_WAIT_BARS, len(bars))
    for j in range(breakout_idx + 1, fill_end):
        swing_i = blocking_swing_before_bar(bars, side, breakout_idx, j)
        if swing_i is not None:
            kind = 'swing high' if side == 'long' else 'swing low'
            return None, f'{kind} @ bar {swing_i} before WO retest'
        row = bars.iloc[j]
        h, l = float(row['high']), float(row['low'])
        if l <= wo <= h:
            entry_idx = j
            break
    if entry_idx is None:
        return None, f'no WO retest within {MAX_FILL_WAIT_BARS} bars after gap'

    stop = wo - STOP_PTS if side == 'long' else wo + STOP_PTS
    tp1 = wo + TP1_PTS if side == 'long' else wo - TP1_PTS
    runner_tgt = wo + TARGET_PTS if side == 'long' else wo - TARGET_PTS
    pts, result, exit_idx, won, exit_px = _exit_scale_2ct(bars, side, entry_idx, wo)
    return (
        Trade(
            side=side,
            breakout_idx=breakout_idx,
            gap_idx=breakout_idx,
            entry_idx=entry_idx,
            exit_idx=exit_idx,
            entry=wo,
            exit=exit_px,
            target=runner_tgt,
            stop=stop,
            tp1=tp1,
            pts=pts,
            result=result,
        ),
        None,
    )


def simulate_week(
    bars: pd.DataFrame,
    wo: float,
    week_start: pd.Timestamp,
    *,
    short_only: bool = False,
) -> WeekSim:
    sim = WeekSim(week_start=week_start, week_key=week_start.date().isoformat(), wo=wo)
    n = len(bars)
    if n < 5:
        return sim

    trades_taken = 0
    had_win = False
    long_breakout_used = False
    short_breakout_used = False

    for i in range(n):
        row = bars.iloc[i]
        ts = pd.Timestamp(bars.index[i])

        if trades_taken >= MAX_TRADES_WEEK or had_win:
            continue

        side: Literal['long', 'short'] | None = None
        if not short_only and not long_breakout_used and bullish_breakout_candle(row, wo):
            side = 'long'
        elif not short_breakout_used and bearish_breakout_candle(row, wo):
            side = 'short'

        if side is None:
            continue

        pre_bar = first_pre_gap_bar(bars, wo, i, side)
        if pre_bar is None:
            reason = 'no full O+C above WO before gap' if side == 'short' else 'no full O+C below WO before gap'
            sim.events.append(SetupEvent('skip', side, i, ts, reason))
            if side == 'long':
                long_breakout_used = True
            else:
                short_breakout_used = True
            continue

        pre_ts = pd.Timestamp(bars.index[pre_bar])
        pre_note = 'trade above WO' if side == 'short' else 'trade below WO'
        sim.events.append(SetupEvent('pre_gap', side, pre_bar, pre_ts, pre_note))

        kind = 'breakout_long' if side == 'long' else 'breakout_short'
        note = '55% gap up through WO' if side == 'long' else '55% gap down through WO'
        sim.events.append(SetupEvent(kind, side, i, ts, note))

        for j in range(i + 1, min(i + 6, n)):
            r = bars.iloc[j]
            if float(r['low']) <= wo <= float(r['high']):
                sim.events.append(
                    SetupEvent('retest_touch', side, j, pd.Timestamp(bars.index[j]), f'bar+{j - i} touches WO')
                )
                break

        tr, block = simulate_fill_and_exit(bars, side, i, wo)
        if tr is None:
            ev_kind = 'skip' if block and 'swing' in block else 'no_fill'
            sim.events.append(SetupEvent(ev_kind, side, i, ts, block or 'no fill'))
            if side == 'long':
                long_breakout_used = True
            else:
                short_breakout_used = True
            continue

        sim.trades.append(tr)
        trades_taken += 1
        if side == 'long':
            long_breakout_used = True
        else:
            short_breakout_used = True
        if tr.result.startswith('tp1') or tr.result == 'target':
            had_win = True

    return sim


def plot_week_study(
    out_path: Path,
    bars: pd.DataFrame,
    ctx: dict[str, float],
    sim: WeekSim,
    weekly: pd.DataFrame,
    week,
    ha_pins: list[tuple[int, str]] | None = None,
) -> None:
    import matplotlib.patches as mpatches

    fig, ax = plt.subplots(figsize=(16, 8), facecolor=BG)
    x0 = mdates.date2num(bars.index[0])
    x1 = mdates.date2num(bars.index[-1])
    pad = max((bars['high'].max() - bars['low'].min()) * 0.08, 20.0)
    y_clip = (float(bars['low'].min()) - pad, float(bars['high'].max()) + pad)
    draw_levels(ax, x0, x1, ctx, y_clip=y_clip)
    plot_candles(ax, bars, width_days=(60 / (24 * 60)) * 0.68)

    width_days = (60 / (24 * 60)) * 0.68
    for i, kind in ha_pins or []:
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
        ax.annotate(
            tag,
            xy=(x, float(row['high']) + 3),
            fontsize=6,
            color='#ECEFF1',
            ha='center',
            zorder=9,
        )

    width_days = (60 / (24 * 60)) * 0.68
    for ev in sim.events:
        row = bars.iloc[ev.bar_idx]
        x = mdates.date2num(bars.index[ev.bar_idx])
        if ev.kind in ('breakout_long', 'breakout_short'):
            color = '#FF9800' if ev.kind == 'breakout_long' else '#FF5722'
            ax.add_patch(
                mpatches.Rectangle(
                    (x - width_days * 0.55, float(row['low']) - 2),
                    width_days * 1.1,
                    float(row['high']) - float(row['low']) + 4,
                    fill=False,
                    edgecolor=color,
                    linewidth=2.2,
                    zorder=6,
                )
            )
        elif ev.kind == 'pre_gap':
            ax.add_patch(
                mpatches.Rectangle(
                    (x - width_days * 0.55, float(row['low']) - 2),
                    width_days * 1.1,
                    float(row['high']) - float(row['low']) + 4,
                    fill=False,
                    edgecolor='#4FC3F7',
                    linewidth=1.5,
                    linestyle=':',
                    zorder=5,
                )
            )
        elif ev.kind == 'retest_touch':
            ax.scatter([x], [sim.wo], marker='d', s=50, color='#B0BEC5', zorder=7, alpha=0.9)
        elif ev.kind == 'skip':
            ax.add_patch(
                mpatches.Rectangle(
                    (x - width_days * 0.55, float(row['low']) - 2),
                    width_days * 1.1,
                    float(row['high']) - float(row['low']) + 4,
                    fill=False,
                    edgecolor='#78909C',
                    linewidth=1.5,
                    linestyle='--',
                    zorder=6,
                )
            )

    for tr in sim.trades:
        if tr.skipped:
            continue
        et = bars.index[tr.entry_idx]
        xt = bars.index[tr.exit_idx]
        color = '#76FF03' if tr.pts > 0 else '#FF1744'
        ax.axhline(tr.tp1, color='#FFD54F', linestyle=':', alpha=0.75, linewidth=0.9)
        ax.axhline(tr.target, color='#76FF03', linestyle=':', alpha=0.7, linewidth=0.9)
        ax.axhline(tr.stop, color='#FF1744', linestyle=':', alpha=0.7, linewidth=0.9)
        ax.axhline(tr.entry, color='#78909C', linestyle='-', alpha=0.35, linewidth=0.8)
        ax.scatter([et], [tr.entry], marker='o', s=120, color='#FFC107', zorder=12, edgecolors='black')
        ax.scatter([xt], [tr.exit], marker='X', s=120, color=color, zorder=12, edgecolors='black')
        ax.annotate(
            f"{tr.side[0].upper()} {tr.result} {tr.pts:+.0f}pt",
            xy=(xt, tr.exit),
            xytext=(8, 12),
            textcoords='offset points',
            color=color,
            fontsize=8,
            fontweight='bold',
        )

    trade_txt = ' | '.join(f"{t.side} {t.result} {t.pts:+.0f}" for t in sim.trades) or 'no fill'
    nf = [e for e in sim.events if e.kind == 'no_fill']
    nf_txt = f" · {nf[0].note}" if nf else ''
    title = (
        f"NQ WO gap · 2ct +{TP1_PTS:.0f}/runner {TARGET_PTS:.0f} · {sim.week_key} · "
        f"WO {sim.wo:.1f} · {trade_txt}{nf_txt}"
    )
    style_axes(ax, title)
    ax.set_ylabel('NQ', color='#9FB3C8')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%a %H:%M', tz=NY))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=6))
    ax.set_xlim(bars.index[0] - pd.Timedelta(hours=2), bars.index[-1] + pd.Timedelta(hours=2))
    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, bbox_inches='tight', facecolor=BG)
    plt.close(fig)


def week_has_chart_content(sim: WeekSim) -> bool:
    if sim.trades:
        return True
    return any(e.kind.startswith('breakout') for e in sim.events)


def summarize_trades_df(tdf: pd.DataFrame, label: str) -> list[str]:
    if tdf.empty:
        return [f'### {label}', '', '_No trades._', '']
    n = len(tdf)
    wins = (tdf['pts'] > 0).sum()
    net = tdf['pts'].sum()
    gross_win = tdf.loc[tdf['pts'] > 0, 'pts'].sum()
    gross_loss = abs(tdf.loc[tdf['pts'] < 0, 'pts'].sum())
    pf = gross_win / gross_loss if gross_loss else float('inf')
    lines = [
        f'### {label}',
        '',
        f'- Trades: **{n}** · Net: **{net:+.1f} pts** · Win rate: **{100 * wins / n:.1f}%**',
        f'- Targets: {(tdf["result"].str.contains("target", na=False)).sum()} · '
        f'Stops: {(tdf["result"].str.contains("stop", na=False)).sum()} · '
        f'EOD/other: {len(tdf) - (tdf["result"].str.contains("target|stop", na=False)).sum()}',
        f'- Profit factor: **{pf:.2f}** · Avg/trade: **{net / n:+.2f} pts**',
        '',
        '| Year | Trades | Net pts |',
        '|---|---:|---:|',
    ]
    for year, g in tdf.groupby('year', sort=True):
        lines.append(f'| {year} | {len(g)} | {g["pts"].sum():+.1f} |')
    lines.append('')
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--output-root', type=Path, default=HERE / 'nq_weekly_wo_gap_reversal_sample')
    ap.add_argument(
        '--charts',
        type=int,
        default=0,
        help='If >0, also emit this many ranked sample charts under charts/sample/',
    )
    ap.add_argument('--start', type=str, default='2023-01-01')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    if args.force:
        import shutil

        cd = args.output_root / 'charts'
        if cd.exists():
            shutil.rmtree(cd)
    chart_root = args.output_root / 'charts'
    chart_root.mkdir(parents=True, exist_ok=True)

    dbn = POTIONS_ROOT / 'nq' / 'raw' / 'glbx-mdp3-20100606-20260308.ohlcv-1m.dbn.zst'
    print(f'Loading NQ 1m ...', flush=True)
    gby = load_1m_by_ny_date(dbn, 'nq')
    one_min = concat_1m(gby)
    one_min = one_min[one_min.index >= pd.Timestamp(args.start, tz=NY)]
    hourly = resample_1h(one_min)
    daily_atr = build_daily_atr(hourly)
    weekly = build_weekly_table(hourly, daily_atr)
    ha_full = compute_ha_candles(hourly)

    all_sims: list[tuple[WeekSim, object, pd.DataFrame, dict]] = []
    both_rows: list[dict] = []
    short_rows_all: list[dict] = []
    for week in weekly.index:
        ctx = week_context(weekly, week)
        if ctx is None:
            continue
        ws = weekly.loc[week, 'week_start']
        if ws < pd.Timestamp(args.start, tz=NY):
            continue
        bars = week_hourly_slice(hourly, ws)
        if len(bars) < 20:
            continue
        wo = float(ctx['WO'])
        sim = simulate_week(bars, wo, ws)
        sim_short = simulate_week(bars, wo, ws, short_only=True)
        for t in sim.trades:
            both_rows.append(
                {'week': sim.week_key, 'side': t.side, 'result': t.result, 'pts': t.pts}
            )
        for t in sim_short.trades:
            short_rows_all.append(
                {'week': sim_short.week_key, 'side': t.side, 'result': t.result, 'pts': t.pts}
            )
        if week_has_chart_content(sim):
            all_sims.append((sim, week, bars, ctx))

    all_sims.sort(key=lambda x: x[0].week_key)

    rows: list[dict] = []
    chart_count = 0
    index_rows: list[str] = []

    for sim, week, bars, ctx in all_sims:
        year = sim.week_key[:4]
        rel = f'charts/{year}/{sim.week_key}.png'
        out = args.output_root / rel
        plot_week_study(out, bars, ctx, sim, weekly, week, ha_pins=ha_pins_for_week(bars, ha_full))
        chart_count += 1
        tdesc = ', '.join(f'{t.side[0].upper()} {t.result} {t.pts:+.0f}' for t in sim.trades) or '—'
        setups = ', '.join(
            f'{e.side[0].upper()}{"↑" if e.kind == "breakout_long" else "↓"}'
            for e in sim.events
            if e.kind.startswith('breakout')
        )
        index_rows.append(
            f'| {sim.week_key} | {tdesc} | {setups or "—"} | [{year}/{sim.week_key}.png](charts/{year}/{sim.week_key}.png) |'
        )
        for t in sim.trades:
            rows.append(
                {
                    'chart': rel,
                    'week': sim.week_key,
                    'side': t.side,
                    'breakout_idx': t.breakout_idx,
                    'gap_idx': t.gap_idx,
                    'entry_idx': t.entry_idx,
                    'result': t.result,
                    'pts': round(t.pts, 2),
                    'entry': t.entry,
                    'exit': t.exit,
                    'stop_pts': STOP_PTS,
                }
            )
        for e in sim.events:
            rows.append(
                {
                    'chart': rel,
                    'week': sim.week_key,
                    'event': e.kind,
                    'side': e.side,
                    'bar_idx': e.bar_idx,
                    'note': e.note,
                    'stop_pts': STOP_PTS,
                }
            )
        if chart_count % 20 == 0:
            print(f'  … {chart_count} charts', flush=True)

    print(f'  {chart_count} weekly charts under charts/{{year}}/ (long + short setups)', flush=True)

    pd.DataFrame(rows).to_csv(args.output_root / 'study_log.csv', index=False)
    both_tdf = pd.DataFrame(both_rows)
    short_tdf = pd.DataFrame(short_rows_all)
    if not both_tdf.empty:
        both_tdf['year'] = both_tdf['week'].str[:4].astype(int)
    if not short_tdf.empty:
        short_tdf['year'] = short_tdf['week'].str[:4].astype(int)
    short_tdf.to_csv(args.output_root / 'short_only_trades_2023plus.csv', index=False)

    lines = [
        '# NQ WO 55% gap reversal study',
        '',
        f'Period: **{args.start}** → present · Exit: **2ct +{TP1_PTS:.0f} / runner {TARGET_PTS:.0f}** · SL **{STOP_PTS:.0f}**',
        '',
        '## Rules',
        '',
        '- **Pre-gap:** ≥1 prior bar fully O+C above WO (short) or below WO (long); wicks may touch WO.',
        '- **Gap candle:** crosses WO with ≥55% of O–C on exit side (cyan dotted = pre-gap context bar).',
        '- **Entry:** limit @ WO from the **next** bar only (not on gap bar).',
        f'- **Fill window:** {MAX_FILL_WAIT_BARS} bars after gap; else `no_fill`.',
        '- **Post-gap:** skip if 3-bar swing forms before WO retest, unless gap bar is in that swing.',
        f'- **Exit:** 2 contracts — +{TP1_PTS:.0f} on leg 1, runner ±{TARGET_PTS:.0f}, initial SL ∓{STOP_PTS:.0f}, BE on runner after +{TP1_PTS:.0f}.',
        '- Max 2 trades/week; no 2nd trade after TP1 / target win. Charts show **both** long and short setups.',
        '- Orange = long gap · red = short gap · grey diamond = first WO touch · **black outline = HA pin** (causal).',
        '- Yellow dotted = TP1 (+50) · green dotted = runner target · grey solid = WO/BE.',
        '',
        f'## Charts ({chart_count} weeks)',
        '',
        'One chart per week with at least one gap setup (filled or not). Paths: `charts/YYYY/YYYY-MM-DD.png`.',
        '',
        'Full trade log: [`study_log.csv`](study_log.csv)',
        '',
        '| Week | Trades | Setups | Chart |',
        '|---|---|---|---|',
        *index_rows,
        '',
        *summarize_trades_df(both_tdf, f'Both sides (2ct +{TP1_PTS:.0f}/{TARGET_PTS:.0f})'),
        *summarize_trades_df(short_tdf, f'Short only (2ct +{TP1_PTS:.0f}/{TARGET_PTS:.0f})'),
        '',
        'Short-only log: [`short_only_trades_2023plus.csv`](short_only_trades_2023plus.csv)',
        '',
        '## Side split (both sides)',
        '',
    ]
    if not both_tdf.empty:
        for side, g in both_tdf.groupby('side'):
            lines.append(f'- **{side}:** {len(g)} trades, net **{g["pts"].sum():+.1f} pts**')
        lines.append('')

    (args.output_root / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Done → {args.output_root / "INDEX.md"} ({chart_count} charts)', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
