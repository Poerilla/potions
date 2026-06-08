#!/usr/bin/env python3
"""Monthly ORB 4-hour trade studies.

Study A: first 4h breakout of the month, only if that breakout candle is one of
the three largest 4h ranges seen so far in the month. Enter at the breakout 4h
close with 3 units. Unit 1 exits halfway to TP1, unit 2 exits at TP1, and the
runner uses the breakout-side OR boundary as its stop after TP1. Before TP1, a
4h close back inside the OR exits all remaining units.

Study B: simple 4h close breakout, entry at close, TP1 at the measured move,
stop at the opposing OR boundary. Skip if the breakout close is already beyond
TP1. Max 3 trades/month or 2 wins/month, with a fresh 4h close back inside the
OR required to re-arm after each completed trade.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import pytz


ROOT = Path(__file__).resolve().parents[1]
MNQ_ROOT = ROOT / 'mnq'
CASE_ROOT = MNQ_ROOT / 'case_studies' / 'monthly_orb'
DAILY = MNQ_ROOT / 'mnq_daily.csv'
FOUR_H_CACHE = MNQ_ROOT / 'data' / 'mnq_front_month_4h_from_1m.csv'
POINT_VALUE = 2.0
NY = pytz.timezone('America/New_York')

CLEAN_OUT = MNQ_ROOT / 'mnq_monthly_orb_clean_break_rank3_scaleout_runner.csv'
SIMPLE_OUT = MNQ_ROOT / 'mnq_monthly_orb_simple_4h_opposing_stop.csv'
REPORT = CASE_ROOT / 'MONTHLY_ORB_4H_TRADE_STUDIES.md'


@dataclass
class UnitExit:
    unit: int
    time: pd.Timestamp
    price: float
    reason: str
    pl: float


@dataclass
class CleanTrade:
    period: str
    direction: str
    entry_time: pd.Timestamp
    entry: float
    range_high: float
    range_low: float
    range_size: float
    candle_rank: int
    candle_range: float
    tp50: float
    tp1: float
    runner_stop: float
    exits: list[UnitExit] = field(default_factory=list)
    tp1_hit: bool = False
    mae_pts: float = 0.0
    mfe_pts: float = 0.0
    open_at_end: bool = False

    @property
    def open_units(self) -> list[int]:
        closed = {ex.unit for ex in self.exits}
        return [u for u in (1, 2, 3) if u not in closed]

    @property
    def net_points(self) -> float:
        return sum(ex.pl for ex in self.exits)

    @property
    def result(self) -> str:
        if self.net_points > 0:
            return 'Win'
        if self.net_points < 0:
            return 'Loss'
        return 'Scratch'

    @property
    def final_reason(self) -> str:
        reasons: list[str] = []
        for ex in sorted(self.exits, key=lambda x: (x.time, x.unit)):
            if ex.reason not in reasons:
                reasons.append(ex.reason)
        return '+'.join(reasons) if reasons else 'Open'


@dataclass
class SimpleTrade:
    period: str
    direction: str
    entry_time: pd.Timestamp
    entry: float
    target: float
    stop: float
    exit_time: pd.Timestamp
    exit_price: float
    exit_reason: str
    mae_pts: float
    mfe_pts: float

    @property
    def pl(self) -> float:
        return self.exit_price - self.entry if self.direction == 'Long' else self.entry - self.exit_price

    @property
    def result(self) -> str:
        if self.pl > 0:
            return 'Win'
        if self.pl < 0:
            return 'Loss'
        return 'Scratch'


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


def month_4h(bars4h: pd.DataFrame, period: str, dates: set) -> pd.DataFrame:
    work = bars4h[bars4h['date'].isin(dates)].copy().reset_index(drop=True)
    work['candle_range'] = work['high'].astype(float) - work['low'].astype(float)
    ranks = []
    seen: list[float] = []
    for value in work['candle_range']:
        seen.append(float(value))
        rank = 1 + sum(v > float(value) for v in seen)
        ranks.append(rank)
    work['range_rank_so_far'] = ranks
    return work


def direction_setup(row: pd.Series, rh: float, rl: float, rv: float):
    c = float(row['close'])
    if c > rh:
        tp1 = rh + rv
        if c >= tp1:
            return None
        return 'Long', c, tp1, rh
    if c < rl:
        tp1 = rl - rv
        if c <= tp1:
            return None
        return 'Short', c, tp1, rl
    return None


def breakout_side(row: pd.Series, rh: float, rl: float) -> str | None:
    c = float(row['close'])
    if c > rh:
        return 'Long'
    if c < rl:
        return 'Short'
    return None


def unit_pl(direction: str, entry: float, exit_price: float) -> float:
    return exit_price - entry if direction == 'Long' else entry - exit_price


def update_excursion(direction: str, entry: float, high: float, low: float, mae: float, mfe: float):
    if direction == 'Long':
        return max(mae, max(0.0, entry - low)), max(mfe, max(0.0, high - entry))
    return max(mae, max(0.0, high - entry)), max(mfe, max(0.0, entry - low))


def close_clean_units(trade: CleanTrade, time: pd.Timestamp, price: float, reason: str) -> None:
    for unit in list(trade.open_units):
        trade.exits.append(UnitExit(unit, time, price, reason, unit_pl(trade.direction, trade.entry, price)))


def add_clean_exit(trade: CleanTrade, unit: int, time: pd.Timestamp, price: float, reason: str) -> None:
    if unit not in trade.open_units:
        return
    trade.exits.append(UnitExit(unit, time, price, reason, unit_pl(trade.direction, trade.entry, price)))


def simulate_clean_trade(period: str, breakout_row: pd.Series, rh: float, rl: float, rv: float, future4h: pd.DataFrame) -> CleanTrade:
    setup = direction_setup(breakout_row, rh, rl, rv)
    if setup is None:
        raise ValueError('breakout row is not a valid setup')
    direction, entry, tp1, runner_stop = setup
    tp50 = entry + (tp1 - entry) * 0.5 if direction == 'Long' else entry - (entry - tp1) * 0.5
    trade = CleanTrade(
        period=period,
        direction=direction,
        entry_time=pd.Timestamp(breakout_row['time']),
        entry=float(entry),
        range_high=rh,
        range_low=rl,
        range_size=rv,
        candle_rank=int(breakout_row['range_rank_so_far']),
        candle_range=float(breakout_row['candle_range']),
        tp50=float(tp50),
        tp1=float(tp1),
        runner_stop=float(runner_stop),
    )

    for _, row in future4h.iterrows():
        t = pd.Timestamp(row['time'])
        h, l, c = float(row['high']), float(row['low']), float(row['close'])
        trade.mae_pts, trade.mfe_pts = update_excursion(direction, entry, h, l, trade.mae_pts, trade.mfe_pts)

        if direction == 'Long':
            if not trade.tp1_hit:
                if 1 in trade.open_units and h >= trade.tp50:
                    add_clean_exit(trade, 1, t, trade.tp50, 'TP50')
                if 2 in trade.open_units and h >= trade.tp1:
                    add_clean_exit(trade, 2, t, trade.tp1, 'TP1')
                    trade.tp1_hit = True
                if not trade.tp1_hit and rl <= c <= rh:
                    close_clean_units(trade, t, c, 'Close-Back-Inside-Before-TP1')
                    return trade
            if trade.tp1_hit and 3 in trade.open_units and l <= trade.runner_stop:
                add_clean_exit(trade, 3, t, trade.runner_stop, 'Runner-Boundary-Stop')
                return trade
        else:
            if not trade.tp1_hit:
                if 1 in trade.open_units and l <= trade.tp50:
                    add_clean_exit(trade, 1, t, trade.tp50, 'TP50')
                if 2 in trade.open_units and l <= trade.tp1:
                    add_clean_exit(trade, 2, t, trade.tp1, 'TP1')
                    trade.tp1_hit = True
                if not trade.tp1_hit and rl <= c <= rh:
                    close_clean_units(trade, t, c, 'Close-Back-Inside-Before-TP1')
                    return trade
            if trade.tp1_hit and 3 in trade.open_units and h >= trade.runner_stop:
                add_clean_exit(trade, 3, t, trade.runner_stop, 'Runner-Boundary-Stop')
                return trade

    if trade.open_units and not future4h.empty:
        last = future4h.iloc[-1]
        close_clean_units(trade, pd.Timestamp(last['time']), float(last['close']), 'Marked-Final')
        trade.open_at_end = True
    return trade


def first_break_rank3_study(daily: pd.DataFrame, bars4h: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    trades: list[CleanTrade] = []
    skips: list[dict] = []
    for period, month_daily in period_groups(daily):
        rb = month_daily.iloc[:3]
        trade_start = month_daily.iloc[3]['date']
        dates = set(month_daily['date'])
        rh, rl = float(rb['high'].max()), float(rb['low'].min())
        rv = rh - rl
        if rv <= 0:
            continue
        m4 = month_4h(bars4h, period, dates)
        trade4h = m4[m4['date'] >= trade_start].copy().reset_index(drop=True)
        breakout_idx = None
        for idx, row in trade4h.iterrows():
            if breakout_side(row, rh, rl) is not None:
                breakout_idx = idx
                break
        if breakout_idx is None:
            skips.append({'Period': period, 'Reason': 'No valid first breakout'})
            continue
        br = trade4h.iloc[breakout_idx]
        if direction_setup(br, rh, rl, rv) is None:
            skips.append(
                {
                    'Period': period,
                    'Reason': 'First breakout close beyond TP1',
                    'Rank': int(br['range_rank_so_far']),
                    'Breakout_Time': pd.Timestamp(br['time']).isoformat(),
                }
            )
            continue
        if int(br['range_rank_so_far']) > 3:
            skips.append(
                {
                    'Period': period,
                    'Reason': 'First breakout rank > 3',
                    'Rank': int(br['range_rank_so_far']),
                    'Breakout_Time': pd.Timestamp(br['time']).isoformat(),
                }
            )
            continue
        future = bars4h[bars4h['time'] > br['time']].copy().reset_index(drop=True)
        trades.append(simulate_clean_trade(period, br, rh, rl, rv, future))

    return clean_rows(trades), pd.DataFrame(skips)


def clean_rows(trades: list[CleanTrade]) -> pd.DataFrame:
    rows = []
    cumulative = 0.0
    for t in trades:
        cumulative += t.net_points
        exits = {ex.unit: ex for ex in t.exits}
        row = {
            'Period': t.period,
            'Direction': t.direction,
            'Entry_Time': t.entry_time.isoformat(),
            'Entry_Price': t.entry,
            'Range_High': t.range_high,
            'Range_Low': t.range_low,
            'Range': t.range_size,
            'Breakout_Candle_Range': t.candle_range,
            'Breakout_Candle_Rank_So_Far': t.candle_rank,
            'TP50_Price': t.tp50,
            'TP1_Price': t.tp1,
            'Runner_Stop': t.runner_stop,
            'TP1_Hit': t.tp1_hit,
            'Open_At_End': t.open_at_end,
            'Trade_PL': round(t.net_points, 6),
            'Result': t.result,
            'Final_Reason': t.final_reason,
            'MAE_Price_Pts': round(t.mae_pts, 6),
            'MFE_Price_Pts': round(t.mfe_pts, 6),
            'Cumulative_PL': round(cumulative, 6),
        }
        for unit in (1, 2, 3):
            ex = exits.get(unit)
            row[f'Unit{unit}_Exit_Time'] = ex.time.isoformat() if ex else None
            row[f'Unit{unit}_Exit_Price'] = ex.price if ex else None
            row[f'Unit{unit}_Exit_Reason'] = ex.reason if ex else None
        rows.append(row)
    return pd.DataFrame(rows)


def simulate_simple_from_index(period: str, trade4h: pd.DataFrame, start_idx: int, rh: float, rl: float, rv: float) -> tuple[SimpleTrade, int]:
    row = trade4h.iloc[start_idx]
    setup = direction_setup(row, rh, rl, rv)
    if setup is None:
        raise ValueError('invalid simple setup')
    direction, entry, target, _boundary = setup
    stop = rl if direction == 'Long' else rh
    mae = mfe = 0.0
    for idx in range(start_idx + 1, len(trade4h)):
        bar = trade4h.iloc[idx]
        t = pd.Timestamp(bar['time'])
        h, l = float(bar['high']), float(bar['low'])
        mae, mfe = update_excursion(direction, entry, h, l, mae, mfe)
        if direction == 'Long':
            if l <= stop:
                return SimpleTrade(period, direction, pd.Timestamp(row['time']), entry, target, stop, t, stop, 'Stop', mae, mfe), idx
            if h >= target:
                return SimpleTrade(period, direction, pd.Timestamp(row['time']), entry, target, stop, t, target, 'Target', mae, mfe), idx
        else:
            if h >= stop:
                return SimpleTrade(period, direction, pd.Timestamp(row['time']), entry, target, stop, t, stop, 'Stop', mae, mfe), idx
            if l <= target:
                return SimpleTrade(period, direction, pd.Timestamp(row['time']), entry, target, stop, t, target, 'Target', mae, mfe), idx
    last = trade4h.iloc[-1]
    exit_px = float(last['close'])
    return SimpleTrade(period, direction, pd.Timestamp(row['time']), entry, target, stop, pd.Timestamp(last['time']), exit_px, 'Period-Close', mae, mfe), len(trade4h) - 1


def simple_opposing_stop_study(daily: pd.DataFrame, bars4h: pd.DataFrame) -> pd.DataFrame:
    trades: list[SimpleTrade] = []
    for period, month_daily in period_groups(daily):
        rb = month_daily.iloc[:3]
        trade_start = month_daily.iloc[3]['date']
        dates = set(month_daily['date'])
        rh, rl = float(rb['high'].max()), float(rb['low'].min())
        rv = rh - rl
        if rv <= 0:
            continue
        trade4h = month_4h(bars4h, period, dates)
        trade4h = trade4h[trade4h['date'] >= trade_start].copy().reset_index(drop=True)
        idx = 0
        armed = True
        wins = 0
        attempts = 0
        while idx < len(trade4h) and attempts < 3 and wins < 2:
            row = trade4h.iloc[idx]
            c = float(row['close'])
            if not armed:
                if rl <= c <= rh:
                    armed = True
                idx += 1
                continue
            if breakout_side(row, rh, rl) is None:
                idx += 1
                continue
            if direction_setup(row, rh, rl, rv) is None:
                armed = False
                idx += 1
                continue
            tr, exit_idx = simulate_simple_from_index(period, trade4h, idx, rh, rl, rv)
            trades.append(tr)
            attempts += 1
            if tr.exit_reason == 'Target':
                wins += 1
            armed = False
            idx = max(exit_idx + 1, idx + 1)
    return simple_rows(trades)


def simple_rows(trades: list[SimpleTrade]) -> pd.DataFrame:
    rows = []
    cumulative = 0.0
    for t in trades:
        cumulative += t.pl
        rows.append(
            {
                'Period': t.period,
                'Direction': t.direction,
                'Entry_Time': t.entry_time.isoformat(),
                'Entry_Price': t.entry,
                'Target_Price': t.target,
                'Stop_Price': t.stop,
                'Exit_Time': t.exit_time.isoformat(),
                'Exit_Price': t.exit_price,
                'Exit_Reason': t.exit_reason,
                'Trade_PL': round(t.pl, 6),
                'Result': t.result,
                'MAE_Price_Pts': round(t.mae_pts, 6),
                'MFE_Price_Pts': round(t.mfe_pts, 6),
                'Cumulative_PL': round(cumulative, 6),
            }
        )
    return pd.DataFrame(rows)


def max_drawdown(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    eq = pd.concat([pd.Series([0.0]), values.astype(float).cumsum()], ignore_index=True)
    return float((eq - eq.cummax()).min())


def profit_factor(values: pd.Series) -> float:
    gains = float(values[values > 0].sum())
    losses = float(values[values < 0].sum())
    if losses == 0:
        return math.inf if gains > 0 else math.nan
    return gains / abs(losses)


def stats(df: pd.DataFrame, point_value: float) -> dict:
    if df.empty:
        return {'trades': 0, 'net_pts': 0.0, 'net_usd': 0.0, 'dd_usd': 0.0, 'win_rate': 0.0, 'pf': math.nan}
    pnl = pd.to_numeric(df['Trade_PL'], errors='coerce').fillna(0.0)
    return {
        'trades': int(len(df)),
        'net_pts': float(pnl.sum()),
        'net_usd': float(pnl.sum() * point_value),
        'dd_pts': float(max_drawdown(pnl)),
        'dd_usd': float(max_drawdown(pnl) * point_value),
        'win_rate': float((pnl > 0).mean()),
        'pf': float(profit_factor(pnl)),
        'avg_mae': float(pd.to_numeric(df.get('MAE_Price_Pts', pd.Series(dtype=float)), errors='coerce').mean()),
        'max_mae': float(pd.to_numeric(df.get('MAE_Price_Pts', pd.Series(dtype=float)), errors='coerce').max()),
    }


def fmt_money(value: float) -> str:
    return f'${value:,.0f}'


def fmt_pct(value: float) -> str:
    return f'{value:.1%}'


def fmt_num(value: float, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return 'n/a'
    if math.isinf(value):
        return 'inf'
    return f'{value:,.{digits}f}'


def yearly_table(df: pd.DataFrame) -> list[str]:
    if df.empty:
        return ['No rows.']
    work = df.copy()
    work['Year'] = pd.to_datetime(work['Entry_Time'], utc=True).dt.year
    grouped = work.groupby('Year').agg(
        trades=('Trade_PL', 'size'),
        net_pts=('Trade_PL', 'sum'),
        wins=('Trade_PL', lambda s: int((s > 0).sum())),
        losses=('Trade_PL', lambda s: int((s < 0).sum())),
        avg_mae=('MAE_Price_Pts', 'mean'),
        max_mae=('MAE_Price_Pts', 'max'),
    )
    lines = [
        '| Year | Trades | Net pts | Wins | Losses | Avg MAE pts | Max MAE pts |',
        '|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for year, row in grouped.iterrows():
        lines.append(
            f"| {year} | {int(row['trades'])} | {row['net_pts']:,.1f} | {int(row['wins'])} | "
            f"{int(row['losses'])} | {row['avg_mae']:.1f} | {row['max_mae']:.1f} |"
        )
    return lines


def load_existing_stats(point_value: float) -> list[tuple[str, dict]]:
    rows: list[tuple[str, dict]] = []
    for name, path in [
        ('Daily restricted boundary entry', MNQ_ROOT / 'mnq_monthly_orb_restricted.csv'),
        ('Daily restricted scaleout3 boundary entry', MNQ_ROOT / 'mnq_monthly_orb_restricted_scaleout3.csv'),
        ('4h close restricted daily range-close', MNQ_ROOT / 'mnq_monthly_orb_restricted_4h_close_entry.csv'),
        ('4h close restricted scaleout3 daily range-close', MNQ_ROOT / 'mnq_monthly_orb_restricted_scaleout3_4h_close_entry.csv'),
        ('4h swing-stop single, re-armed', MNQ_ROOT / 'mnq_monthly_orb_4h_swing_stop.csv'),
        ('4h swing-stop scaleout3, re-armed', MNQ_ROOT / 'mnq_monthly_orb_scaleout3_4h_swing_stop.csv'),
    ]:
        if path.exists():
            df = pd.read_csv(path)
            df = df[df['Trade_Direction'].astype(str) != 'No-Op'] if 'Trade_Direction' in df.columns else df
            rows.append((name, stats(df, point_value)))
    return rows


def write_report(clean: pd.DataFrame, skips: pd.DataFrame, simple: pd.DataFrame, point_value: float) -> None:
    rows = load_existing_stats(point_value)
    rows.append(('Clean-break rank<=3 scaleout runner', stats(clean, point_value)))
    rows.append(('Simple 4h close + opposing OR stop', stats(simple, point_value)))
    if clean.empty or 'Open_At_End' not in clean.columns:
        clean_closed = clean
    else:
        clean_closed = clean[~clean['Open_At_End'].astype(bool)].copy()
    clean_total_pts = float(pd.to_numeric(clean.get('Trade_PL', pd.Series(dtype=float)), errors='coerce').fillna(0.0).sum())
    clean_closed_pts = float(pd.to_numeric(clean_closed.get('Trade_PL', pd.Series(dtype=float)), errors='coerce').fillna(0.0).sum())
    clean_open_runner_pts = clean_total_pts - clean_closed_pts
    clean_closed_stats = stats(clean_closed, point_value)
    lines = [
        '# MNQ Monthly ORB 4H Trade Studies',
        '',
        '## New Models',
        '',
        '**Clean-break rank<=3 scaleout runner**: first 4h breakout of the month only, skipped if the close is already beyond TP1, and that breakout candle must rank in the top 3 largest 4h high-low ranges seen so far that month. Entry is the 4h close, 3 units, unit 1 exits halfway to TP1, unit 2 exits at TP1, and the runner stops at the breakout-side OR boundary. Before TP1, a 4h close back inside the OR closes all remaining units.',
        '',
        '**Simple 4h close + opposing OR stop**: enter at a valid 4h close outside the OR, skip if entry is already beyond TP1, target TP1, stop at the opposing OR boundary, max 3 trades/month or 2 wins/month, re-arm after a 4h close back inside the OR.',
        '',
        'Dollar figures use the MNQ point value of $2/point per unit. The same point path on NQ would be roughly 10x the dollar P/L and drawdown.',
        '',
        '| Variant | Trades | Net pts | Net USD | Max DD USD | Win rate | PF | Avg MAE pts | Max MAE pts |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for name, s in rows:
        lines.append(
            f"| {name} | {s['trades']} | {fmt_num(s['net_pts'])} | {fmt_money(s['net_usd'])} | "
            f"{fmt_money(s['dd_usd'])} | {fmt_pct(s['win_rate'])} | {fmt_num(s['pf'], 2)} | "
            f"{fmt_num(s.get('avg_mae', 0.0))} | {fmt_num(s.get('max_mae', 0.0))} |"
        )
    lines.extend(
        [
            '',
            '## Interpretation',
            '',
            f'- The clean-break rank<=3 model is only profitable if still-open runners are marked at the final available bar. Excluding marked-final runners, it has **{clean_closed_stats["trades"]} closed trades**, **{fmt_num(clean_closed_stats["net_pts"])} pts**, **{fmt_money(clean_closed_stats["net_usd"])}**, and **{fmt_money(clean_closed_stats["dd_usd"])}** max closed DD.',
            f'- Marked-final runner contribution is **{fmt_num(clean_open_runner_pts)} pts** / **{fmt_money(clean_open_runner_pts * point_value)}**. Treat this as open-equity sensitivity, not harvested edge.',
            '- The simple 4h opposing-boundary model has a decent hit rate, but its profit factor and drawdown are weak. It does not beat the more selective daily restricted research variants, and it is not materially better than the 4h swing-stop branch.',
            '- The clean-break idea has directional pulse, but the sample is thin and clustered. It needs either a better runner exit or a filter that avoids the large close-back-inside losses.',
            '',
            '## Clean-Break Rank Filter',
            '',
            f'- Trades taken: **{len(clean)}**',
            f'- First-break months skipped by rank/validity: **{len(skips)}**',
            f'- TP1 hit on clean-break model: **{int(clean["TP1_Hit"].sum()) if not clean.empty else 0}**',
            f'- Runner marked open/final instead of boundary stop: **{int(clean["Open_At_End"].sum()) if not clean.empty else 0}**',
            '',
            'Exit reason mix:',
            '',
            *(f'- {reason}: **{count}**' for reason, count in (clean['Final_Reason'].value_counts().items() if not clean.empty else [])),
            '',
            '## New Model Yearly Splits',
            '',
            '### Clean-Break Rank<=3 Scaleout Runner',
            '',
            *yearly_table(clean),
            '',
            '### Simple 4H Close + Opposing OR Stop',
            '',
            *yearly_table(simple),
            '',
            '## Outputs',
            '',
            '- `mnq/mnq_monthly_orb_clean_break_rank3_scaleout_runner.csv`',
            '- `mnq/mnq_monthly_orb_clean_break_rank3_skips.csv`',
            '- `mnq/mnq_monthly_orb_simple_4h_opposing_stop.csv`',
        ]
    )
    REPORT.write_text('\n'.join(lines) + '\n')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, default=DAILY)
    ap.add_argument('--bars-4h', type=Path, default=FOUR_H_CACHE)
    ap.add_argument('--point-value-usd', type=float, default=POINT_VALUE)
    ap.add_argument('--clean-out', type=Path, default=CLEAN_OUT)
    ap.add_argument('--simple-out', type=Path, default=SIMPLE_OUT)
    args = ap.parse_args()

    daily = load_daily(args.daily)
    bars4h = load_cached_4h(args.bars_4h)
    clean, skips = first_break_rank3_study(daily, bars4h)
    simple = simple_opposing_stop_study(daily, bars4h)

    args.clean_out.parent.mkdir(parents=True, exist_ok=True)
    clean.to_csv(args.clean_out, index=False)
    skips.to_csv(MNQ_ROOT / 'mnq_monthly_orb_clean_break_rank3_skips.csv', index=False)
    simple.to_csv(args.simple_out, index=False)
    write_report(clean, skips, simple, args.point_value_usd)
    print(f'Wrote {args.clean_out} ({len(clean)} rows)')
    print(f'Wrote {args.simple_out} ({len(simple)} rows)')
    print(f'Wrote {REPORT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
