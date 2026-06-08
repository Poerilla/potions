#!/usr/bin/env python3
"""Monthly ORB baseline + range-close restricted, with 3-unit scaleout ladder.

Same *entry* and *range-close* rules as ``monthly_orb_restricted.py`` (first 3
sessions define the OR; close-based breakout; fill at range boundary / same-bar
touch; max 2 completed bundles per month; daily close back inside OR exits all
open units at that close).

Position management mirrors ``yearly_orb_swing_stop_scaleout3.py`` scaleout3,
except the stop is the **opposite OR boundary** (not a swing pivot):

- 3 units at the boundary entry price.
- Unit 1 exits at 25% of the distance from entry to the 1R measured-move TP.
- Unit 2 exits at the full TP (entry ± range).
- Unit 3 is the runner; initial stop is the opposite boundary; after Unit 2
  fills at TP, the stop for remaining units moves to breakeven (entry).
- Intraday ordering on each daily bar: stop first, then partial TPs, then
  range-close check (conservative vs targets).

Outputs wide CSV rows compatible with the yearly scaleout3 column layout.

Example:
  python3 scripts/monthly_orb_restricted_scaleout3.py
  python3 scripts/monthly_orb_restricted_scaleout3.py --daily mnq/mnq_daily.csv \\
      --out mnq/mnq_monthly_orb_restricted_scaleout3.csv --point-value-usd 2
"""

from __future__ import annotations

import argparse
import math
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

WAIT_BREAKOUT = 0
WAIT_FILL = 1
IN_TRADE = 2
MAX_TRADES_PER_PERIOD = 2


@dataclass
class UnitExit:
    unit: int
    date: pd.Timestamp
    price: float
    reason: str
    pl: float


@dataclass
class MonthScaleTrade:
    period: str
    direction: str
    entry: float
    target: float
    tp25: float
    initial_stop: float
    entry_date: pd.Timestamp
    breakout_date: pd.Timestamp
    breakout_close: float
    exits: list[UnitExit] = field(default_factory=list)
    be_active: bool = False
    mae_price_pts: float = 0.0
    mae_position_pts: float = 0.0
    mfe_price_pts: float = 0.0
    result: str = 'Open'
    final_reason: str = 'Open'

    @property
    def open_units(self) -> list[int]:
        closed = {ex.unit for ex in self.exits}
        return [u for u in (1, 2, 3) if u not in closed]

    @property
    def net_points(self) -> float:
        return sum(ex.pl for ex in self.exits)


def unit_pl(direction: str, entry: float, exit_price: float) -> float:
    return exit_price - entry if direction == 'Long' else entry - exit_price


def add_exit(trade: MonthScaleTrade, unit: int, date: pd.Timestamp, price: float, reason: str) -> None:
    if unit not in trade.open_units:
        return
    trade.exits.append(UnitExit(unit, date, price, reason, unit_pl(trade.direction, trade.entry, price)))


def close_units(trade: MonthScaleTrade, date: pd.Timestamp, price: float, reason: str) -> None:
    for unit in list(trade.open_units):
        add_exit(trade, unit, date, price, reason)


def classify_trade(trade: MonthScaleTrade) -> None:
    net = trade.net_points
    if net > 0:
        trade.result = 'Win'
    elif net < 0:
        trade.result = 'Loss'
    else:
        trade.result = 'Scratch'
    reasons: list[str] = []
    for ex in sorted(trade.exits, key=lambda x: (x.date, x.unit)):
        if ex.reason not in reasons:
            reasons.append(ex.reason)
    trade.final_reason = '+'.join(reasons) if reasons else 'Open'


def update_excursion(trade: MonthScaleTrade, high: float, low: float) -> None:
    open_count = len(trade.open_units)
    if open_count == 0:
        return
    if trade.direction == 'Long':
        adverse = max(0.0, trade.entry - low)
        favorable = max(0.0, high - trade.entry)
    else:
        adverse = max(0.0, high - trade.entry)
        favorable = max(0.0, trade.entry - low)
    trade.mae_price_pts = max(trade.mae_price_pts, adverse)
    trade.mae_position_pts = max(trade.mae_position_pts, adverse * open_count)
    trade.mfe_price_pts = max(trade.mfe_price_pts, favorable)


def process_open_trade(
    trade: MonthScaleTrade,
    bar: pd.Series,
    range_low: float,
    range_high: float,
) -> bool:
    """Return True when trade bundle is finished."""
    h, l, c = float(bar['high']), float(bar['low']), float(bar['close'])
    d = pd.Timestamp(bar['date'])
    update_excursion(trade, h, l)

    stop_price = trade.entry if trade.be_active else trade.initial_stop
    stop_reason = 'BE-Stop' if trade.be_active else 'Boundary-Stop'

    if trade.direction == 'Long':
        if l <= stop_price:
            close_units(trade, d, stop_price, stop_reason)
            classify_trade(trade)
            return True
        if 1 in trade.open_units and h >= trade.tp25:
            add_exit(trade, 1, d, trade.tp25, 'TP25')
        if 2 in trade.open_units and h >= trade.target:
            add_exit(trade, 2, d, trade.target, 'TP')
            trade.be_active = True
    else:
        if h >= stop_price:
            close_units(trade, d, stop_price, stop_reason)
            classify_trade(trade)
            return True
        if 1 in trade.open_units and l <= trade.tp25:
            add_exit(trade, 1, d, trade.tp25, 'TP25')
        if 2 in trade.open_units and l <= trade.target:
            add_exit(trade, 2, d, trade.target, 'TP')
            trade.be_active = True

    if trade.open_units and range_low <= c <= range_high:
        close_units(trade, d, c, 'Range-Close')
        classify_trade(trade)
        return True

    if not trade.open_units:
        classify_trade(trade)
        return True
    return False


def start_trade(
    period: str,
    direction: str,
    entry: float,
    target: float,
    initial_stop: float,
    entry_date: pd.Timestamp,
    breakout_date: pd.Timestamp,
    breakout_close: float,
) -> MonthScaleTrade:
    if direction == 'Long':
        tp25 = entry + (target - entry) * 0.25
    else:
        tp25 = entry - (entry - target) * 0.25
    return MonthScaleTrade(
        period=period,
        direction=direction,
        entry=entry,
        target=target,
        tp25=tp25,
        initial_stop=initial_stop,
        entry_date=entry_date,
        breakout_date=breakout_date,
        breakout_close=breakout_close,
    )


def simulate_month_scaleout3(
    period: str,
    range_high: float,
    range_low: float,
    range_val: float,
    trade_bars: pd.DataFrame,
) -> list[MonthScaleTrade]:
    phase = WAIT_BREAKOUT
    direction: Optional[str] = None
    entry_f = target_f = stop_f = None
    entry_date: Optional[pd.Timestamp] = None
    breakout_date: Optional[pd.Timestamp] = None
    breakout_close: Optional[float] = None
    trade: Optional[MonthScaleTrade] = None
    completed: list[MonthScaleTrade] = []
    trade_count = 0

    for _, bar in trade_bars.iterrows():
        if trade_count >= MAX_TRADES_PER_PERIOD and phase != IN_TRADE:
            break

        h = float(bar['high'])
        l = float(bar['low'])
        c = float(bar['close'])
        d = pd.Timestamp(bar['date'])

        if phase == WAIT_FILL and direction is not None:
            filled = False
            if direction == 'Long' and l <= range_high:
                entry_f, target_f, stop_f = range_high, range_high + range_val, range_low
                entry_date = d
                trade = start_trade(
                    period,
                    'Long',
                    float(entry_f),
                    float(target_f),
                    float(stop_f),
                    entry_date,
                    breakout_date or d,
                    float(breakout_close) if breakout_close is not None else c,
                )
                filled = True
            elif direction == 'Short' and h >= range_low:
                entry_f, target_f, stop_f = range_low, range_low - range_val, range_high
                entry_date = d
                trade = start_trade(
                    period,
                    'Short',
                    float(entry_f),
                    float(target_f),
                    float(stop_f),
                    entry_date,
                    breakout_date or d,
                    float(breakout_close) if breakout_close is not None else c,
                )
                filled = True

            if filled:
                phase = IN_TRADE
            else:
                if direction == 'Long' and c < range_low:
                    direction = 'Short'
                    breakout_date = d
                    breakout_close = c
                elif direction == 'Short' and c > range_high:
                    direction = 'Long'
                    breakout_date = d
                    breakout_close = c

        if phase == IN_TRADE and trade is not None:
            done = process_open_trade(trade, bar, range_low, range_high)
            if done:
                completed.append(trade)
                trade = None
                phase = WAIT_BREAKOUT
                direction = None
                entry_f = target_f = stop_f = None
                entry_date = breakout_date = breakout_close = None
                trade_count += 1
            continue

        if phase == WAIT_BREAKOUT and trade_count < MAX_TRADES_PER_PERIOD:
            if c > range_high:
                direction = 'Long'
                breakout_date = d
                breakout_close = c
                if l <= range_high:
                    entry_f = range_high
                    target_f = range_high + range_val
                    stop_f = range_low
                    entry_date = d
                    trade = start_trade(
                        period,
                        'Long',
                        float(entry_f),
                        float(target_f),
                        float(stop_f),
                        entry_date,
                        breakout_date,
                        float(breakout_close),
                    )
                    phase = IN_TRADE
                    continue
                phase = WAIT_FILL
            elif c < range_low:
                direction = 'Short'
                breakout_date = d
                breakout_close = c
                if h >= range_low:
                    entry_f = range_low
                    target_f = range_low - range_val
                    stop_f = range_high
                    entry_date = d
                    trade = start_trade(
                        period,
                        'Short',
                        float(entry_f),
                        float(target_f),
                        float(stop_f),
                        entry_date,
                        breakout_date,
                        float(breakout_close),
                    )
                    phase = IN_TRADE
                    continue
                phase = WAIT_FILL

    if phase == IN_TRADE and trade is not None and len(trade_bars) > 0:
        last = trade_bars.iloc[-1]
        close_units(trade, pd.Timestamp(last['date']), float(last['close']), 'Period-Close')
        classify_trade(trade)
        completed.append(trade)

    return completed


def trade_rows(
    trades: list[MonthScaleTrade],
    range_high: float,
    range_low: float,
    range_val: float,
    symbol: str,
    range_days: int,
    trade_days: int,
    period_label: str = '',
) -> list[dict]:
    if not trades:
        return [
            {
                'Period': period_label,
                'Range_High': range_high,
                'Range_Low': range_low,
                'Range': range_val,
                'Trade_Direction': 'No-Op',
                'Units': 0,
                'Entry_Date': None,
                'Entry_Price': None,
                'Entry_Mode': 'boundary',
                'Stop_Swing_Scope': 'opposite-boundary',
                'Breakout_Date': None,
                'Breakout_Close': None,
                'Initial_Stop_Price': None,
                'Stop_Source_Date': None,
                'Stop_Source_Price': None,
                'TP25_Price': None,
                'TP_Price': None,
                'Unit1_Exit_Price': None,
                'Unit1_Exit_Date': None,
                'Unit1_Exit_Reason': None,
                'Unit2_Exit_Price': None,
                'Unit2_Exit_Date': None,
                'Unit2_Exit_Reason': None,
                'Unit3_Exit_Price': None,
                'Unit3_Exit_Date': None,
                'Unit3_Exit_Reason': None,
                'Trade_PL': 0.0,
                'MAE_Price_Pts': 0.0,
                'MAE_Position_Pts': 0.0,
                'MFE_Price_Pts': 0.0,
                'Result': 'No-Op',
                'Final_Reason': 'No-Op',
                'Symbol': symbol,
                'Range_Days': range_days,
                'Trade_Days': trade_days,
                'Cumulative_PL': 0.0,
            }
        ]

    rows: list[dict] = []
    cumulative = 0.0
    for t in trades:
        cumulative += t.net_points
        exits = {ex.unit: ex for ex in t.exits}
        row = {
            'Period': t.period,
            'Range_High': range_high,
            'Range_Low': range_low,
            'Range': range_val,
            'Trade_Direction': t.direction,
            'Units': 3,
            'Entry_Date': t.entry_date.date().isoformat(),
            'Entry_Price': t.entry,
            'Entry_Mode': 'boundary',
            'Stop_Swing_Scope': 'opposite-boundary',
            'Breakout_Date': t.breakout_date.date().isoformat(),
            'Breakout_Close': t.breakout_close,
            'Initial_Stop_Price': t.initial_stop,
            'Stop_Source_Date': t.entry_date.date().isoformat(),
            'Stop_Source_Price': t.initial_stop,
            'TP25_Price': t.tp25,
            'TP_Price': t.target,
            'Trade_PL': round(t.net_points, 6),
            'MAE_Price_Pts': round(t.mae_price_pts, 6),
            'MAE_Position_Pts': round(t.mae_position_pts, 6),
            'MFE_Price_Pts': round(t.mfe_price_pts, 6),
            'Result': t.result,
            'Final_Reason': t.final_reason,
            'Symbol': symbol,
            'Range_Days': range_days,
            'Trade_Days': trade_days,
            'Cumulative_PL': round(cumulative, 6),
        }
        for unit in (1, 2, 3):
            ex = exits.get(unit)
            row[f'Unit{unit}_Exit_Price'] = ex.price if ex else None
            row[f'Unit{unit}_Exit_Date'] = ex.date.date().isoformat() if ex else None
            row[f'Unit{unit}_Exit_Reason'] = ex.reason if ex else None
        rows.append(row)
    return rows


def load_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=['date'])
    df['date'] = df['date'].dt.date
    return df.sort_values('date').reset_index(drop=True)


def run_scaleout3(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['ym'] = df['date'].apply(lambda d: (d.year, d.month))
    periods: OrderedDict[tuple[int, int], list] = OrderedDict()
    for _, row in df.iterrows():
        periods.setdefault(row['ym'], []).append(row)

    all_rows: list[dict] = []
    for (yr, mo), bars in periods.items():
        bars_df = pd.DataFrame(bars)
        if len(bars_df) < 4:
            continue
        range_bars = bars_df.iloc[:3]
        trade_bars = bars_df.iloc[3:].reset_index(drop=True)
        range_high = float(range_bars['high'].max())
        range_low = float(range_bars['low'].min())
        range_val = range_high - range_low
        symbol = str(range_bars.iloc[0]['symbol'])
        period_label = f'{yr}-{mo:02d}'

        if range_val <= 0:
            all_rows.extend(
                trade_rows(
                    [],
                    range_high,
                    range_low,
                    max(range_val, 0.0),
                    symbol,
                    3,
                    len(trade_bars),
                    period_label,
                )
            )
            continue

        trades = simulate_month_scaleout3(period_label, range_high, range_low, range_val, trade_bars)
        if not trades:
            all_rows.extend(
                trade_rows([], range_high, range_low, range_val, symbol, 3, len(trade_bars), period_label)
            )
            continue

        all_rows.extend(
            trade_rows(trades, range_high, range_low, range_val, symbol, 3, len(trade_bars), period_label)
        )

    out = pd.DataFrame(all_rows)
    if not out.empty:
        m = out['Trade_Direction'] != 'No-Op'
        if m.any():
            out.loc[m, 'Cumulative_PL'] = out.loc[m, 'Trade_PL'].astype(float).cumsum().values
    return out


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


def summarize(df: pd.DataFrame, multiplier: float) -> None:
    t = df[df['Trade_Direction'] != 'No-Op'].copy()
    if t.empty:
        print('No trades.')
        return
    pnl = t['Trade_PL'].astype(float)
    print(f"Bundles (3-unit trades): {len(t)}")
    print(f"Net pts (sum of bundle PL): {pnl.sum():,.2f}")
    print(f"Net USD @ ${multiplier}/pt/bundle-pt: {pnl.sum() * multiplier:,.2f}")
    print(f"Max DD (bundle PL series): {max_drawdown(pnl):,.2f} pts")
    print(f"Win rate: {(pnl > 0).mean():.2%}")
    print(f"Profit factor: {profit_factor(pnl):.3f}")
    rc = (t['Final_Reason'].str.contains('Range-Close', na=False)).sum()
    print(f"Bundles touching Range-Close exit: {rc}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, default=ROOT / 'mnq' / 'mnq_daily.csv')
    ap.add_argument(
        '--out',
        type=Path,
        default=ROOT / 'mnq' / 'mnq_monthly_orb_restricted_scaleout3.csv',
    )
    ap.add_argument('--point-value-usd', type=float, default=2.0, help='USD per index point (MNQ ~2).')
    ap.add_argument('--compare-restricted', type=Path, default=ROOT / 'mnq' / 'mnq_monthly_orb_restricted.csv')
    ap.add_argument(
        '--also-nq',
        action='store_true',
        help='Also run NQ daily -> nq/nq_monthly_orb_restricted_scaleout3.csv ($20/pt).',
    )
    args = ap.parse_args()

    daily = load_daily(args.daily)
    out_df = run_scaleout3(daily)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.out, index=False)
    print(f"Wrote {args.out} ({len(out_df)} rows)")
    summarize(out_df, args.point_value_usd)

    if args.compare_restricted.exists():
        leg = pd.read_csv(args.compare_restricted)
        leg_t = leg[leg['Trade_Direction'] != 'No-Op']
        if not leg_t.empty:
            leg_net = leg_t['Trade_PL'].astype(float).sum()
            leg_dd = max_drawdown(leg_t['Trade_PL'].astype(float))
            print('\n--- vs single-leg restricted (mnq_monthly_orb_restricted.csv) ---')
            print(f"Single-leg trades: {len(leg_t)}  net pts: {leg_net:,.2f}  maxDD pts: {leg_dd:,.2f}")

    if args.also_nq:
        nq_daily = ROOT / 'nq' / 'nq_daily.csv'
        nq_out = ROOT / 'nq' / 'nq_monthly_orb_restricted_scaleout3.csv'
        nq_cmp = ROOT / 'nq' / 'nq_monthly_orb_restricted.csv'
        print('\n=== NQ ===')
        nq_df = run_scaleout3(load_daily(nq_daily))
        nq_df.to_csv(nq_out, index=False)
        print(f"Wrote {nq_out} ({len(nq_df)} rows)")
        summarize(nq_df, 20.0)
        if nq_cmp.exists():
            leg = pd.read_csv(nq_cmp)
            leg_t = leg[leg['Trade_Direction'] != 'No-Op']
            if not leg_t.empty:
                print('\n--- vs single-leg NQ restricted ---')
                print(f"Single-leg trades: {len(leg_t)}  net pts: {leg_t['Trade_PL'].astype(float).sum():,.2f}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
