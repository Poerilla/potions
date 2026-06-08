#!/usr/bin/env python3
"""Monthly ORB overlapping-range breakout study.

Monthly OR = first three daily rows of each calendar month.

When adjacent monthly ORs overlap, they become one combined range. The combined
range can expand if later monthly ORs also overlap it. If a later monthly OR
gaps away from the combined range, that cluster is done and the simulator waits
for the next adjacent overlap.

Trade rules:

- Enter at the daily close that breaks out of the active combined range.
- Long target = combined high + combined range. Short target = combined low -
  combined range.
- Stop = a configurable fraction of the combined range from the **wrong** side
  (default **0.5** = midpoint). Long: ``low + frac * (high - low)``; short:
  ``high - frac * (high - low)``. Smaller ``frac`` = **wider** (deeper) stop.
- Positioning: default **one contract**; optional **two contracts** with **1 @ 1R**
  and **1 runner** to **2R** or **3R**, stop on the runner moved to **breakeven**
  after the first contract fills at 1R (conservative same-bar ordering: stop
  before TP fills when both are touched).
- One live trade at a time. Max two entries per overlap cluster.
- Re-arm after a completed trade only when price closes back inside the active
  combined range.
- If a later overlapping monthly OR expands the range while a trade is open,
  one favorable breakout through the expanded range can extend the target once.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MARKETS = {
    'mnq': {'root': ROOT / 'mnq', 'daily': ROOT / 'mnq' / 'mnq_daily.csv', 'point_value': 2.0, 'label': 'MNQ'},
    'nq': {'root': ROOT / 'nq', 'daily': ROOT / 'nq' / 'nq_daily.csv', 'point_value': 20.0, 'label': 'NQ'},
}


@dataclass
class MonthlyRange:
    period: str
    year: int
    month: int
    first_idx: int
    complete_idx: int
    start_date: object
    complete_date: object
    end_date: object
    high: float
    low: float


@dataclass
class Cluster:
    cluster_id: int
    start_period: str
    end_period: str
    start_date: object
    high: float
    low: float
    months: list[str] = field(default_factory=list)
    attempts: int = 0
    armed: bool = True
    expanded_this_month: bool = False

    @property
    def size(self) -> float:
        return self.high - self.low

    @property
    def midpoint(self) -> float:
        return self.low + self.size * 0.5


def stop_for_direction(direction: str, high: float, low: float, stop_frac: float) -> float:
    """Adverse stop: long uses support below entry; ``stop_frac`` in (0,1] measured from low upward."""
    r = high - low
    if r <= 0:
        return low
    if direction == 'Long':
        return low + stop_frac * r
    return high - stop_frac * r


def runner_target(direction: str, high: float, low: float, mult: int) -> float:
    """``mult`` R beyond the breakout boundary (``mult``=1 matches ``target_for``)."""
    r = high - low
    if direction == 'Long':
        return high + mult * r
    return low - mult * r


@dataclass
class Trade:
    market: str
    cluster_id: int
    cluster_months: str
    direction: str
    entry_date: object
    entry: float
    range_high: float
    range_low: float
    range_size: float
    stop: float
    target: float
    exit_date: object | None = None
    exit_price: float | None = None
    exit_reason: str = 'Open'
    extension_used: bool = False
    extension_date: object | None = None
    extension_old_target: float | None = None
    extension_new_target: float | None = None
    mae_pts: float = 0.0
    mfe_pts: float = 0.0
    stop_frac: float = 0.5
    contracts: int = 1
    runner_mult: int | None = None
    risk_pts: float = 0.0
    tp1: float | None = None
    tp2: float | None = None
    scaleout_pl: float | None = None
    qty_remaining: int = 1
    working_stop: float = 0.0
    leg1_pl: float | None = None

    @property
    def pl(self) -> float:
        if self.scaleout_pl is not None:
            return float(self.scaleout_pl)
        if self.exit_price is None:
            return 0.0
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


def overlap(high1: float, low1: float, high2: float, low2: float) -> bool:
    return max(low1, low2) <= min(high1, high2)


def monthly_ranges(daily: pd.DataFrame) -> list[MonthlyRange]:
    work = daily.copy()
    work['idx'] = range(len(work))
    work['period'] = pd.to_datetime(work['date']).dt.to_period('M').astype(str)
    out: list[MonthlyRange] = []
    for period, sub in work.groupby('period', sort=True):
        sub = sub.sort_values('idx').reset_index(drop=True)
        if len(sub) < 4:
            continue
        rb = sub.iloc[:3]
        year, month = map(int, period.split('-'))
        out.append(
            MonthlyRange(
                period=period,
                year=year,
                month=month,
                first_idx=int(sub.iloc[0]['idx']),
                complete_idx=int(sub.iloc[2]['idx']),
                start_date=sub.iloc[0]['date'],
                complete_date=sub.iloc[2]['date'],
                end_date=sub.iloc[-1]['date'],
                high=float(rb['high'].max()),
                low=float(rb['low'].min()),
            )
        )
    return out


def update_excursion(direction: str, entry: float, high: float, low: float, mae: float, mfe: float) -> tuple[float, float]:
    if direction == 'Long':
        return max(mae, max(0.0, entry - low)), max(mfe, max(0.0, high - entry))
    return max(mae, max(0.0, high - entry)), max(mfe, max(0.0, entry - low))


def target_for(direction: str, high: float, low: float) -> float:
    size = high - low
    return high + size if direction == 'Long' else low - size


def maybe_start_or_expand_cluster(
    active: Cluster | None,
    current: MonthlyRange,
    previous: MonthlyRange | None,
    next_cluster_id: int,
) -> tuple[Cluster | None, int, dict | None]:
    if active is not None and overlap(active.high, active.low, current.high, current.low):
        old_high, old_low = active.high, active.low
        active.high = max(active.high, current.high)
        active.low = min(active.low, current.low)
        active.end_period = current.period
        active.months.append(current.period)
        active.expanded_this_month = active.high != old_high or active.low != old_low
        return active, next_cluster_id, {
            'Cluster_ID': active.cluster_id,
            'Event': 'expand',
            'Period': current.period,
            'Range_High': active.high,
            'Range_Low': active.low,
            'Attempts': active.attempts,
        }

    if active is not None:
        active = None

    if previous is not None and overlap(previous.high, previous.low, current.high, current.low):
        cluster = Cluster(
            cluster_id=next_cluster_id,
            start_period=previous.period,
            end_period=current.period,
            start_date=previous.start_date,
            high=max(previous.high, current.high),
            low=min(previous.low, current.low),
            months=[previous.period, current.period],
            expanded_this_month=True,
        )
        return cluster, next_cluster_id + 1, {
            'Cluster_ID': cluster.cluster_id,
            'Event': 'start',
            'Period': current.period,
            'Range_High': cluster.high,
            'Range_Low': cluster.low,
            'Attempts': cluster.attempts,
        }
    return None, next_cluster_id, None


def row_inside(row: pd.Series, cluster: Cluster) -> bool:
    return cluster.low <= float(row['close']) <= cluster.high


def close_trade(trade: Trade, date: object, price: float, reason: str) -> None:
    trade.exit_date = date
    trade.exit_price = float(price)
    trade.exit_reason = reason


def trade_to_row(trade: Trade) -> dict:
    return {
        'Market': trade.market,
        'Cluster_ID': trade.cluster_id,
        'Cluster_Months': trade.cluster_months,
        'Direction': trade.direction,
        'Entry_Date': trade.entry_date,
        'Entry_Price': trade.entry,
        'Range_High': trade.range_high,
        'Range_Low': trade.range_low,
        'Range': trade.range_size,
        'Stop_Price': trade.stop,
        'Initial_Target': (
            trade.extension_old_target
            if trade.extension_used and trade.extension_old_target is not None
            else (trade.tp1 if trade.tp1 is not None else trade.target)
        ),
        'Final_Target': trade.tp2 if trade.tp2 is not None else trade.target,
        'Exit_Date': trade.exit_date,
        'Exit_Price': trade.exit_price,
        'Exit_Reason': trade.exit_reason,
        'Extension_Used': trade.extension_used,
        'Extension_Date': trade.extension_date,
        'Extension_Old_Target': trade.extension_old_target,
        'Extension_New_Target': trade.extension_new_target,
        'Trade_PL': round(trade.pl, 6),
        'Result': trade.result,
        'MAE_Price_Pts': round(trade.mae_pts, 6),
        'MFE_Price_Pts': round(trade.mfe_pts, 6),
        'Stop_Frac': trade.stop_frac,
        'Contracts': trade.contracts,
        'Runner_Mult': trade.runner_mult if trade.runner_mult is not None else '',
        'Risk_Pts': round(trade.risk_pts, 6),
        'MAE_over_Risk': (
            round(trade.mae_pts / trade.risk_pts, 4)
            if trade.risk_pts > 1e-9
            else float('nan')
        ),
    }


def _apply_extension_long(trade: Trade, active: Cluster, close_px: float, row_date: object) -> None:
    if close_px <= active.high:
        return
    new_t1 = target_for('Long', active.high, active.low)
    if new_t1 <= (trade.tp1 if trade.tp1 is not None else trade.target):
        return
    trade.extension_used = True
    trade.extension_date = row_date
    trade.extension_old_target = trade.target
    trade.target = new_t1
    if trade.tp1 is not None:
        trade.extension_new_target = new_t1
        trade.tp1 = new_t1
        if trade.runner_mult is not None:
            trade.tp2 = runner_target('Long', active.high, active.low, trade.runner_mult)
    else:
        trade.extension_new_target = new_t1


def _apply_extension_short(trade: Trade, active: Cluster, close_px: float, row_date: object) -> None:
    if close_px >= active.low:
        return
    new_t1 = target_for('Short', active.high, active.low)
    if new_t1 >= (trade.tp1 if trade.tp1 is not None else trade.target):
        return
    trade.extension_used = True
    trade.extension_date = row_date
    trade.extension_old_target = trade.target
    trade.target = new_t1
    if trade.tp1 is not None:
        trade.extension_new_target = new_t1
        trade.tp1 = new_t1
        if trade.runner_mult is not None:
            trade.tp2 = runner_target('Short', active.high, active.low, trade.runner_mult)
    else:
        trade.extension_new_target = new_t1


def simulate(
    daily: pd.DataFrame,
    market: str,
    *,
    stop_frac: float = 0.5,
    contracts: int = 1,
    runner_mult: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if contracts not in (1, 2):
        raise ValueError('contracts must be 1 or 2')
    if contracts == 2 and runner_mult not in (2, 3):
        raise ValueError('runner_mult must be 2 or 3 when contracts=2')
    if contracts == 1 and runner_mult is not None:
        raise ValueError('runner_mult is only used when contracts=2')
    if not (0 < stop_frac <= 1.0):
        raise ValueError('stop_frac must be in (0, 1]')

    ranges = monthly_ranges(daily)
    event_by_start_idx = {r.complete_idx + 1: r for r in ranges if r.complete_idx + 1 < len(daily)}
    previous_range_by_period = {ranges[i].period: ranges[i - 1] if i else None for i in range(len(ranges))}
    active: Cluster | None = None
    next_cluster_id = 1
    active_trade: Trade | None = None
    trades: list[Trade] = []
    events: list[dict] = []

    for idx, row in daily.iterrows():
        if idx in event_by_start_idx:
            current = event_by_start_idx[idx]
            previous = previous_range_by_period[current.period]
            active, next_cluster_id, event = maybe_start_or_expand_cluster(active, current, previous, next_cluster_id)
            if event:
                events.append(event)

        if active_trade is not None and active_trade.exit_date is None:
            high, low = float(row['high']), float(row['low'])
            active_trade.mae_pts, active_trade.mfe_pts = update_excursion(
                active_trade.direction,
                active_trade.entry,
                high,
                low,
                active_trade.mae_pts,
                active_trade.mfe_pts,
            )

            if active_trade.contracts == 1:
                stop_reason = 'Midpoint-Stop' if abs(active_trade.stop_frac - 0.5) < 1e-9 else 'Stop'
                if active_trade.direction == 'Long':
                    if low <= active_trade.stop:
                        close_trade(active_trade, row['date'], active_trade.stop, stop_reason)
                    elif high >= active_trade.target:
                        close_trade(active_trade, row['date'], active_trade.target, 'Target')
                else:
                    if high >= active_trade.stop:
                        close_trade(active_trade, row['date'], active_trade.stop, stop_reason)
                    elif low <= active_trade.target:
                        close_trade(active_trade, row['date'], active_trade.target, 'Target')
            else:
                # Two contracts: conservative bar ordering — adverse stop before TP.
                q = active_trade.qty_remaining
                st = active_trade.working_stop
                t1 = active_trade.tp1
                t2 = active_trade.tp2
                assert t1 is not None and t2 is not None
                if active_trade.direction == 'Long':
                    if q == 2 and low <= st:
                        active_trade.scaleout_pl = 2.0 * (st - active_trade.entry)
                        close_trade(active_trade, row['date'], st, 'Stop-2')
                    elif q == 2 and high >= t1:
                        active_trade.leg1_pl = t1 - active_trade.entry
                        active_trade.qty_remaining = 1
                        active_trade.working_stop = active_trade.entry
                        if low <= active_trade.entry:
                            active_trade.scaleout_pl = active_trade.leg1_pl + 0.0
                            close_trade(active_trade, row['date'], active_trade.entry, 'TP1+BE')
                        elif high >= t2:
                            active_trade.scaleout_pl = active_trade.leg1_pl + (t2 - active_trade.entry)
                            close_trade(active_trade, row['date'], t2, 'TP1+Runner')
                    elif q == 1 and active_trade.leg1_pl is not None:
                        if low <= st:
                            active_trade.scaleout_pl = active_trade.leg1_pl + (st - active_trade.entry)
                            close_trade(active_trade, row['date'], st, 'TP1+RunnerStop')
                        elif high >= t2:
                            active_trade.scaleout_pl = active_trade.leg1_pl + (t2 - active_trade.entry)
                            close_trade(active_trade, row['date'], t2, 'TP1+Runner')
                else:
                    if q == 2 and high >= st:
                        active_trade.scaleout_pl = 2.0 * (active_trade.entry - st)
                        close_trade(active_trade, row['date'], st, 'Stop-2')
                    elif q == 2 and low <= t1:
                        active_trade.leg1_pl = active_trade.entry - t1
                        active_trade.qty_remaining = 1
                        active_trade.working_stop = active_trade.entry
                        if high >= active_trade.entry:
                            active_trade.scaleout_pl = active_trade.leg1_pl + 0.0
                            close_trade(active_trade, row['date'], active_trade.entry, 'TP1+BE')
                        elif low <= t2:
                            active_trade.scaleout_pl = active_trade.leg1_pl + (active_trade.entry - t2)
                            close_trade(active_trade, row['date'], t2, 'TP1+Runner')
                    elif q == 1 and active_trade.leg1_pl is not None:
                        if high >= st:
                            active_trade.scaleout_pl = active_trade.leg1_pl + (active_trade.entry - st)
                            close_trade(active_trade, row['date'], st, 'TP1+RunnerStop')
                        elif low <= t2:
                            active_trade.scaleout_pl = active_trade.leg1_pl + (active_trade.entry - t2)
                            close_trade(active_trade, row['date'], t2, 'TP1+Runner')

            if active_trade.exit_date is not None:
                trades.append(active_trade)
                active_trade = None

        close_px = float(row['close'])
        if active is not None and active_trade is not None and active_trade.exit_date is None and not active_trade.extension_used:
            if active_trade.direction == 'Long' and close_px > active.high:
                if active_trade.contracts == 1 or active_trade.tp1 is None:
                    new_target = target_for('Long', active.high, active.low)
                    if new_target > active_trade.target:
                        active_trade.extension_used = True
                        active_trade.extension_date = row['date']
                        active_trade.extension_old_target = active_trade.target
                        active_trade.extension_new_target = new_target
                        active_trade.target = new_target
                else:
                    _apply_extension_long(active_trade, active, close_px, row['date'])
            elif active_trade.direction == 'Short' and close_px < active.low:
                if active_trade.contracts == 1 or active_trade.tp1 is None:
                    new_target = target_for('Short', active.high, active.low)
                    if new_target < active_trade.target:
                        active_trade.extension_used = True
                        active_trade.extension_date = row['date']
                        active_trade.extension_old_target = active_trade.target
                        active_trade.extension_new_target = new_target
                        active_trade.target = new_target
                else:
                    _apply_extension_short(active_trade, active, close_px, row['date'])

        if active is None or active_trade is not None:
            continue

        if active.attempts >= 2:
            continue

        if not active.armed:
            if row_inside(row, active):
                active.armed = True
            continue

        direction = None
        if close_px > active.high:
            direction = 'Long'
        elif close_px < active.low:
            direction = 'Short'
        if direction is None:
            continue

        target = target_for(direction, active.high, active.low)
        if (direction == 'Long' and close_px >= target) or (direction == 'Short' and close_px <= target):
            events.append(
                {
                    'Cluster_ID': active.cluster_id,
                    'Event': 'skip_overextended',
                    'Period': active.end_period,
                    'Date': row['date'],
                    'Direction': direction,
                    'Close': close_px,
                    'Range_High': active.high,
                    'Range_Low': active.low,
                }
            )
            active.armed = False
            continue

        st = stop_for_direction(direction, active.high, active.low, stop_frac)
        tp1v = target_for(direction, active.high, active.low)
        t2v = runner_target(direction, active.high, active.low, runner_mult) if runner_mult is not None else None
        risk1 = abs(close_px - st)
        active_trade = Trade(
            market=market.upper(),
            cluster_id=active.cluster_id,
            cluster_months='+'.join(active.months),
            direction=direction,
            entry_date=row['date'],
            entry=close_px,
            range_high=active.high,
            range_low=active.low,
            range_size=active.size,
            stop=st,
            target=tp1v,
            stop_frac=stop_frac,
            contracts=contracts,
            runner_mult=runner_mult,
            risk_pts=risk1,
            tp1=tp1v if contracts == 2 else None,
            tp2=t2v if contracts == 2 else None,
            qty_remaining=contracts,
            working_stop=st,
        )
        active.attempts += 1
        active.armed = False
        events.append(
            {
                'Cluster_ID': active.cluster_id,
                'Event': 'entry',
                'Period': active.end_period,
                'Date': row['date'],
                'Direction': direction,
                'Close': close_px,
                'Range_High': active.high,
                'Range_Low': active.low,
                'Attempts': active.attempts,
            }
        )

    if active_trade is not None and active_trade.exit_date is None:
        last = daily.iloc[-1]
        px = float(last['close'])
        if active_trade.contracts == 1:
            close_trade(active_trade, last['date'], px, 'Final-Close')
        else:
            if active_trade.qty_remaining == 2:
                if active_trade.direction == 'Long':
                    active_trade.scaleout_pl = 2.0 * (px - active_trade.entry)
                else:
                    active_trade.scaleout_pl = 2.0 * (active_trade.entry - px)
            else:
                assert active_trade.leg1_pl is not None
                if active_trade.direction == 'Long':
                    active_trade.scaleout_pl = active_trade.leg1_pl + (px - active_trade.entry)
                else:
                    active_trade.scaleout_pl = active_trade.leg1_pl + (active_trade.entry - px)
            close_trade(active_trade, last['date'], px, 'Final-Close')
        trades.append(active_trade)

    out = pd.DataFrame([trade_to_row(t) for t in trades])
    if not out.empty:
        out['Cumulative_PL'] = out['Trade_PL'].astype(float).cumsum()
    return out, pd.DataFrame(events)


def max_drawdown(pnl: pd.Series) -> float:
    if pnl.empty:
        return 0.0
    eq = pd.concat([pd.Series([0.0]), pnl.astype(float).cumsum()], ignore_index=True)
    return float((eq - eq.cummax()).min())


def profit_factor(pnl: pd.Series) -> float:
    gains = float(pnl[pnl > 0].sum())
    losses = float(pnl[pnl < 0].sum())
    if losses == 0:
        return math.inf if gains > 0 else math.nan
    return gains / abs(losses)


def stats(df: pd.DataFrame, point_value: float) -> dict:
    if df.empty:
        return {'trades': 0, 'net_pts': 0.0, 'net_usd': 0.0, 'dd_usd': 0.0, 'win_rate': 0.0, 'pf': math.nan, 'avg_mae': math.nan, 'max_mae': math.nan, 'avg_mae_over_risk': math.nan}
    pnl = pd.to_numeric(df['Trade_PL'], errors='coerce').fillna(0.0)
    mae = pd.to_numeric(df.get('MAE_Price_Pts', pd.Series(dtype=float)), errors='coerce')
    mor = pd.to_numeric(df['MAE_over_Risk'], errors='coerce')
    return {
        'trades': int(len(df)),
        'net_pts': float(pnl.sum()),
        'net_usd': float(pnl.sum() * point_value),
        'dd_usd': float(max_drawdown(pnl) * point_value),
        'win_rate': float((pnl > 0).mean()),
        'pf': float(profit_factor(pnl)),
        'avg_mae': float(mae.mean()),
        'max_mae': float(mae.max()),
        'avg_mae_over_risk': float(mor.mean()) if not mor.dropna().empty else float('nan'),
    }


def fmt_money(value: float) -> str:
    return f'${value:,.0f}'


def fmt_num(value: float, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return 'n/a'
    if math.isinf(value):
        return 'inf'
    return f'{value:,.{digits}f}'


def fmt_pct(value: float) -> str:
    return f'{value:.1%}'


def draw_candles(ax: plt.Axes, bars: pd.DataFrame) -> None:
    xnums = mdates.date2num(pd.to_datetime(bars['date']).dt.to_pydatetime())
    width = 0.62
    for x, (_, row) in zip(xnums, bars.iterrows()):
        o, h, l, c = map(float, [row['open'], row['high'], row['low'], row['close']])
        color = '#26A69A' if c >= o else '#EF5350'
        ax.vlines(x, l, h, color=color, linewidth=0.65, alpha=0.85, zorder=2)
        ax.add_patch(
            mpatches.Rectangle(
                (x - width / 2, min(o, c)),
                width,
                max(abs(c - o), 0.05),
                facecolor=color,
                edgecolor=color,
                alpha=0.82,
                zorder=3,
            )
        )


def chart_trades(daily: pd.DataFrame, trades: pd.DataFrame, out_root: Path, label: str) -> None:
    if trades.empty:
        return
    chart_root = out_root / 'overlap_range_breakout'
    winners = chart_root / 'winners'
    losers = chart_root / 'losers'
    winners.mkdir(parents=True, exist_ok=True)
    losers.mkdir(parents=True, exist_ok=True)
    index_lines = [f'# {label} monthly OR overlap-range breakout charts', '']
    for i, (_, tr) in enumerate(trades.iterrows(), 1):
        entry = pd.Timestamp(tr['Entry_Date']).date()
        exit_date = pd.Timestamp(tr['Exit_Date']).date()
        start = entry - pd.Timedelta(days=25).to_pytimedelta()
        end = exit_date + pd.Timedelta(days=10).to_pytimedelta()
        bars = daily[(daily['date'] >= start) & (daily['date'] <= end)].copy()
        if bars.empty:
            continue
        fig = plt.figure(figsize=(15, 7.5), facecolor='#0D1B2A')
        ax = fig.add_subplot(111)
        ax.set_facecolor('#0D1B2A')
        draw_candles(ax, bars)
        x0 = pd.Timestamp(bars.iloc[0]['date'])
        x1 = pd.Timestamp(bars.iloc[-1]['date'])
        rh, rl = float(tr['Range_High']), float(tr['Range_Low'])
        stop = float(tr['Stop_Price'])
        target = float(tr['Final_Target'])
        ax.hlines([rh, rl], x0, x1, colors='#64B5F6', linewidth=1.2, label='combined OR', zorder=4)
        ax.fill_between([x0, x1], rl, rh, color='#64B5F6', alpha=0.05, zorder=1)
        ax.hlines(stop, x0, x1, colors='#FFB74D', linestyles='--', linewidth=1.0, label='midpoint stop', zorder=4)
        ax.hlines(target, x0, x1, colors='#81C784', linestyles='--', linewidth=1.0, label='target', zorder=4)
        if bool(tr['Extension_Used']) and pd.notna(tr['Extension_Old_Target']):
            ax.hlines(float(tr['Extension_Old_Target']), x0, pd.Timestamp(tr['Extension_Date']), colors='#AED581', linestyles=':', linewidth=1.0, zorder=4)
        ex = pd.Timestamp(tr['Entry_Date'])
        xx = pd.Timestamp(tr['Exit_Date'])
        marker = '^' if tr['Direction'] == 'Long' else 'v'
        ax.scatter(ex, float(tr['Entry_Price']), marker=marker, s=95, color='#00E676', edgecolor='white', zorder=6)
        ax.scatter(xx, float(tr['Exit_Price']), marker='x', s=95, color='#FF5252', zorder=6)
        ax.set_title(
            f"{label} overlap range #{i:03d} {tr['Period'] if 'Period' in tr else tr['Cluster_Months']} "
            f"{tr['Direction']} {tr['Result']} {float(tr['Trade_PL']):+.1f} pts",
            color='white',
            fontsize=12,
        )
        ax.grid(True, color='white', alpha=0.08)
        ax.tick_params(colors='white')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        fig.autofmt_xdate()
        fig.tight_layout()
        folder = winners if float(tr['Trade_PL']) > 0 else losers
        path = folder / f"{i:03d}_{tr['Entry_Date']}_{tr['Direction'].lower()}_{tr['Result'].lower()}.png"
        fig.savefig(path, dpi=140)
        plt.close(fig)
        index_lines.append(f"- [{path.relative_to(chart_root)}]({path.relative_to(chart_root)})")
    (chart_root / 'INDEX.md').write_text('\n'.join(index_lines) + '\n')
    for folder, title in [(winners, 'winners'), (losers, 'losers')]:
        lines = [f'# {label} overlap range {title}', '']
        for p in sorted(folder.glob('*.png')):
            lines.append(f'- [{p.name}]({p.name})')
        (folder / 'INDEX.md').write_text('\n'.join(lines) + '\n')


def write_report(market: str, label: str, root: Path, trades: pd.DataFrame, events: pd.DataFrame, point_value: float) -> Path:
    case_root = root / 'case_studies' / 'monthly_orb'
    case_root.mkdir(parents=True, exist_ok=True)
    report = case_root / 'MONTHLY_ORB_OVERLAP_RANGE_BREAKOUT.md'
    s = stats(trades, point_value)
    side = trades.groupby('Direction').apply(lambda x: pd.Series(stats(x, point_value))).reset_index() if not trades.empty else pd.DataFrame()
    lines = [
        f'# {label} Monthly ORB Overlap-Range Breakout',
        '',
        'Rules:',
        '',
        '- Build monthly ORs from the first 3 daily rows of each calendar month.',
        '- If adjacent monthly ORs overlap, combine them into one range.',
        '- If later monthly ORs overlap the active combined range, expand the range.',
        '- If a later monthly OR gaps away, the active cluster is done and the engine waits for the next adjacent overlap.',
        '- Entry is the daily close that breaks out of the active combined range.',
        '- Stop is at fraction ``stop_frac`` of the combined range from the wrong side for the breakout '
        '(default **0.5** = midpoint). Smaller ``stop_frac`` places the stop **deeper** (wider).',
        '- Target is one combined range beyond the breakout-side boundary (1R).',
        '- Default **one contract**; optional **two contracts** with one lot off at 1R and one runner to **2R** or **3R**, '
        'runner stop to breakeven after 1R fills (conservative same-bar: full stop before TP when both touch).',
        '- One live trade at a time, max two entries per overlap cluster.',
        '- One favorable extension is allowed if a later overlapping month expands the range and price breaks the expanded range in the trade direction.',
        '',
        f'Dollar figures use {label} point value of ${point_value:g}/point per contract.',
        '',
        '## Summary',
        '',
        '| Trades | Net pts | Net USD | Max DD USD | Win rate | PF | Avg MAE pts | Max MAE pts | Avg MAE / risk |',
        '|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
        f"| {s['trades']} | {fmt_num(s['net_pts'])} | {fmt_money(s['net_usd'])} | {fmt_money(s['dd_usd'])} | {fmt_pct(s['win_rate'])} | {fmt_num(s['pf'], 2)} | {fmt_num(s['avg_mae'])} | {fmt_num(s['max_mae'])} | {fmt_num(s['avg_mae_over_risk'], 2)} |",
        '',
        '## Direction Split',
        '',
    ]
    if side.empty:
        lines.append('No trades.')
    else:
        lines.extend(['| Direction | Trades | Net pts | Net USD | Max DD USD | Win rate | PF |', '|---|---:|---:|---:|---:|---:|---:|'])
        for _, row in side.iterrows():
            lines.append(
                f"| {row['Direction']} | {int(row['trades'])} | {fmt_num(row['net_pts'])} | "
                f"{fmt_money(row['net_usd'])} | {fmt_money(row['dd_usd'])} | {fmt_pct(row['win_rate'])} | {fmt_num(row['pf'], 2)} |"
            )
    lines.extend(['', '## Exit Mix', ''])
    if trades.empty:
        lines.append('No trades.')
    else:
        for reason, count in trades['Exit_Reason'].value_counts().items():
            lines.append(f'- {reason}: **{count}**')
    lines.extend(['', '## Cluster Events', ''])
    if events.empty:
        lines.append('No cluster events.')
    else:
        for event, count in events['Event'].value_counts().items():
            lines.append(f'- {event}: **{count}**')
    lines.extend(['', '## Yearly Split', ''])
    if trades.empty:
        lines.append('No trades.')
    else:
        work = trades.copy()
        work['Year'] = pd.to_datetime(work['Entry_Date']).dt.year
        lines.extend(['| Year | Trades | Net pts | Wins | Losses | Avg MAE pts | Max MAE pts |', '|---:|---:|---:|---:|---:|---:|---:|'])
        for year, row in work.groupby('Year').agg(
            trades=('Trade_PL', 'size'),
            net=('Trade_PL', 'sum'),
            wins=('Trade_PL', lambda x: int((x > 0).sum())),
            losses=('Trade_PL', lambda x: int((x < 0).sum())),
            avg_mae=('MAE_Price_Pts', 'mean'),
            max_mae=('MAE_Price_Pts', 'max'),
        ).iterrows():
            lines.append(f"| {year} | {int(row['trades'])} | {row['net']:,.1f} | {int(row['wins'])} | {int(row['losses'])} | {row['avg_mae']:.1f} | {row['max_mae']:.1f} |")
    lines.extend(
        [
            '',
            '## Outputs',
            '',
            f'- `{market}/{market}_monthly_orb_overlap_range_breakout.csv`',
            f'- `{market}/{market}_monthly_orb_overlap_range_breakout_events.csv`',
            f'- Charts: `case_studies/monthly_orb/overlap_range_breakout/INDEX.md`',
            '- Stop / MAE / 2-lot runner sweep: `case_studies/monthly_orb/MONTHLY_ORB_OVERLAP_RANGE_BREAKOUT_SENSITIVITY.md` '
            '(regenerate: `python scripts/monthly_orb_overlap_range_breakout.py --sensitivity`)',
        ]
    )
    report.write_text('\n'.join(lines) + '\n')
    return report


def write_sensitivity_reports() -> None:
    """Write MNQ + NQ sensitivity tables (stop sweep + 2-lot runners)."""
    lines = [
        '# Monthly OR overlap-range breakout — MAE vs stop + 2-lot runner',
        '',
        'Generated by `python scripts/monthly_orb_overlap_range_breakout.py --sensitivity`.',
        '',
        '**Stop placement:** long stop = `low + stop_frac × range`; short stop = `high - stop_frac × range`. '
        '**0.5** = midpoint (baseline). **Smaller** `stop_frac` = stop **deeper** into the range from the long side '
        '(**wider** adverse stop, more room before exit).',
        '',
        '**Avg MAE / risk:** mean (max adverse excursion in price points ÷ |entry − stop| at entry). '
        'Values **well below 1** mean typical heat stayed far inside the nominal stop distance before the trade resolved.',
        '',
        '**2-lot scaleout:** 2 contracts, **same** structural stop as baseline until flat or scaled; **1 lot** exits at **1R** '
        '(measured move target); remaining lot moves stop to **breakeven**; runner limit at **2R** or **3R** beyond the '
        'same boundary. Intraday path: conservative ordering (full **2-lot** stop before **1R** when both touch the same bar).',
        '',
    ]
    stop_grid = [0.5, 0.45, 0.4, 0.35, 0.3, 0.25]
    for mkt in ['mnq', 'nq']:
        cfg = MARKETS[mkt]
        daily = load_daily(cfg['daily'])
        lbl = cfg['label']
        pv = cfg['point_value']
        lines += [f'## {lbl}', '', '### One contract: stop fraction sweep', '']
        lines += [
            '| stop_frac | Trades | Net pts | Net $ | Max DD $ | Win% | PF | Avg MAE | Avg MAE/risk |',
            '|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
        ]
        for sf in stop_grid:
            tr, _ = simulate(daily, mkt, stop_frac=sf, contracts=1)
            st = stats(tr, pv)
            lines.append(
                f"| {sf:.2f} | {st['trades']} | {st['net_pts']:,.1f} | {st['net_usd']:,.0f} | {st['dd_usd']:,.0f} | "
                f"{st['win_rate']:.1%} | {fmt_num(st['pf'], 2)} | {st['avg_mae']:.1f} | {fmt_num(st['avg_mae_over_risk'], 2)} |"
            )
        lines += ['', '### Two contracts, midpoint stop: 1 @ 1R + 1 runner', '']
        lines += [
            '| Runner | Trades | Net pts | Net $ | Max DD $ | Win% | PF | Avg MAE | Avg MAE/risk |',
            '|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
        ]
        for rm in (2, 3):
            tr, _ = simulate(daily, mkt, stop_frac=0.5, contracts=2, runner_mult=rm)
            st = stats(tr, pv)
            lines.append(
                f"| {rm}R | {st['trades']} | {st['net_pts']:,.1f} | {st['net_usd']:,.0f} | {st['dd_usd']:,.0f} | "
                f"{st['win_rate']:.1%} | {fmt_num(st['pf'], 2)} | {st['avg_mae']:.1f} | {fmt_num(st['avg_mae_over_risk'], 2)} |"
            )
        lines.append('')

    lines += [
        '## Interpretation (same data; small sample)',
        '',
        '- **MAE vs midpoint stop:** Mean **MAE / risk** sits near **~0.6–0.75** at the baseline half-range stop on both '
        'products. That is a **material** share of nominal risk, but **not** hugging **1.0** on average — so the midpoint '
        'stop is **not** obviously “noise-choked” in the aggregate sense; losers can still be large (see **Max MAE** in the main report).',
        '',
        '- **Widening the stop (smaller `stop_frac`):** Entry count is **unchanged** (same signals), but **net usually drags** '
        'because each loser costs more. **`stop_frac=0.25`** is an outlier here: **higher win rate** and **higher net** on '
        'this slice — treat as a **hypothesis** for more data, not a proven upgrade.',
        '',
        '- **2-lot runner:** **2R** adds a lot of **gross pts** vs 1-lot but **~2× Max DD $** on this run. **3R** shows **far fewer '
        'trades** than baseline: only **one** live position is allowed; a slow runner can block a **second** cluster attempt, '
        'so **trade count is not comparable** to the 1-lot book. Judge **2R vs 3R** on economics **and** on how much schedule '
        'overlap you can tolerate.',
        '',
    ]

    text = '\n'.join(lines) + '\n'
    for mkt in ['mnq', 'nq']:
        path = MARKETS[mkt]['root'] / 'case_studies' / 'monthly_orb' / 'MONTHLY_ORB_OVERLAP_RANGE_BREAKOUT_SENSITIVITY.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def run_market(
    market: str,
    charts: bool,
    *,
    stop_frac: float = 0.5,
    contracts: int = 1,
    runner_mult: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, Path]:
    cfg = MARKETS[market]
    daily = load_daily(cfg['daily'])
    trades, events = simulate(daily, market, stop_frac=stop_frac, contracts=contracts, runner_mult=runner_mult)
    out = cfg['root'] / f'{market}_monthly_orb_overlap_range_breakout.csv'
    events_out = cfg['root'] / f'{market}_monthly_orb_overlap_range_breakout_events.csv'
    trades.to_csv(out, index=False)
    events.to_csv(events_out, index=False)
    case_root = cfg['root'] / 'case_studies' / 'monthly_orb'
    if charts and not trades.empty:
        chart_trades(daily, trades, case_root, cfg['label'])
    report = write_report(market, cfg['label'], cfg['root'], trades, events, cfg['point_value'])
    return trades, events, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--market', choices=['mnq', 'nq', 'both'], default='both')
    ap.add_argument('--charts', action='store_true')
    ap.add_argument('--sensitivity', action='store_true', help='Write MAE/stop + 2-lot runner sensitivity tables and exit.')
    ap.add_argument('--stop-frac', type=float, default=0.5, help='Stop depth: long stop = low + frac*range (default 0.5 = midpoint).')
    ap.add_argument('--contracts', type=int, default=1, choices=[1, 2])
    ap.add_argument('--runner-mult', type=int, default=None, choices=[2, 3], help='Runner target = 2R or 3R (requires --contracts 2).')
    args = ap.parse_args()

    if args.sensitivity:
        write_sensitivity_reports()
        for mkt in ['mnq', 'nq']:
            p = MARKETS[mkt]['root'] / 'case_studies' / 'monthly_orb' / 'MONTHLY_ORB_OVERLAP_RANGE_BREAKOUT_SENSITIVITY.md'
            print(f'Wrote {p}')
        return 0

    if args.contracts == 1 and args.runner_mult is not None:
        ap.error('--runner-mult is only valid with --contracts 2')

    if args.contracts == 2 and args.runner_mult is None:
        ap.error('--runner-mult is required (2 or 3) when --contracts 2')

    markets = ['mnq', 'nq'] if args.market == 'both' else [args.market]
    for market in markets:
        trades, events, report = run_market(
            market,
            args.charts,
            stop_frac=args.stop_frac,
            contracts=args.contracts,
            runner_mult=args.runner_mult,
        )
        print(f'Wrote {market}: {len(trades)} trades, {len(events)} events, report {report}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
