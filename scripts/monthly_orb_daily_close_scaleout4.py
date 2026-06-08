#!/usr/bin/env python3
"""Monthly ORB daily-close breakout scaleout4 study.

Rules:

- Monthly opening range is the first three daily rows in each calendar month.
- First daily close outside the range becomes the breakout signal.
- Entry is modeled at that same daily close.
- Skip entries whose close is already beyond TP1.
- Four units:
  - unit 1 exits halfway from entry to TP1,
  - units 2 and 3 exit at TP1,
  - unit 4 exits at TP2.
- Before TP1, any daily close back inside the opening range exits all open units
  at that daily close.
- After TP1, the runner stop moves to the breakout-side range boundary.

This is daily OHLC research. Same-day ordering between targets and the moved
boundary stop is conservative: after TP1 is reached, if the same daily bar also
touches the boundary stop, the runner exits at the stop before TP2.
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MARKETS = {
    'mnq': {'root': ROOT / 'mnq', 'daily': ROOT / 'mnq' / 'mnq_daily.csv', 'point_value': 2.0, 'label': 'MNQ'},
    'nq': {'root': ROOT / 'nq', 'daily': ROOT / 'nq' / 'nq_daily.csv', 'point_value': 20.0, 'label': 'NQ'},
}


@dataclass
class UnitExit:
    unit: int
    date: object
    price: float
    reason: str
    pl: float


@dataclass
class Trade:
    period: str
    direction: str
    entry_date: object
    entry: float
    range_high: float
    range_low: float
    range_size: float
    tp50: float
    tp1: float
    tp2: float
    boundary_stop: float
    symbol: str
    exits: list[UnitExit] = field(default_factory=list)
    tp1_hit: bool = False
    mae_price_pts: float = 0.0
    mfe_price_pts: float = 0.0
    open_at_end: bool = False

    @property
    def open_units(self) -> list[int]:
        closed = {ex.unit for ex in self.exits}
        return [u for u in (1, 2, 3, 4) if u not in closed]

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
        for ex in sorted(self.exits, key=lambda x: (pd.Timestamp(x.date), x.unit)):
            if ex.reason not in reasons:
                reasons.append(ex.reason)
        return '+'.join(reasons) if reasons else 'Open'


def load_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=['date'])
    df['date'] = df['date'].dt.date
    return df.sort_values('date').reset_index(drop=True)


def period_groups(daily: pd.DataFrame):
    work = daily.copy()
    work['ym'] = pd.to_datetime(work['date']).dt.to_period('M')
    for period, sub in work.groupby('ym', sort=True):
        sub = sub.sort_values('date').reset_index(drop=True)
        if len(sub) >= 4:
            yield str(period), sub


def unit_pl(direction: str, entry: float, exit_price: float) -> float:
    return exit_price - entry if direction == 'Long' else entry - exit_price


def update_excursion(direction: str, entry: float, high: float, low: float, mae: float, mfe: float) -> tuple[float, float]:
    if direction == 'Long':
        return max(mae, max(0.0, entry - low)), max(mfe, max(0.0, high - entry))
    return max(mae, max(0.0, high - entry)), max(mfe, max(0.0, entry - low))


def close_unit(trade: Trade, unit: int, date: object, price: float, reason: str) -> None:
    if unit not in trade.open_units:
        return
    trade.exits.append(UnitExit(unit, date, price, reason, unit_pl(trade.direction, trade.entry, price)))


def close_open_units(trade: Trade, date: object, price: float, reason: str) -> None:
    for unit in list(trade.open_units):
        close_unit(trade, unit, date, price, reason)


def close_inside(close_px: float, rh: float, rl: float) -> bool:
    return rl <= close_px <= rh


def breakout_setup(row: pd.Series, rh: float, rl: float, rv: float, side: str) -> tuple[str, float, float, float] | None:
    close_px = float(row['close'])
    if close_px > rh and side in {'both', 'long'}:
        tp1 = rh + rv
        if close_px >= tp1:
            return None
        return 'Long', close_px, tp1, rh
    if close_px < rl and side in {'both', 'short'}:
        tp1 = rl - rv
        if close_px <= tp1:
            return None
        return 'Short', close_px, tp1, rl
    return None


def simulate_trade(period: str, signal_idx: int, month_daily: pd.DataFrame, rh: float, rl: float, rv: float, setup: tuple[str, float, float, float]) -> Trade:
    signal = month_daily.iloc[signal_idx]
    direction, entry, tp1, boundary_stop = setup
    tp50 = entry + (tp1 - entry) * 0.5 if direction == 'Long' else entry - (entry - tp1) * 0.5
    tp2 = rh + 2.0 * rv if direction == 'Long' else rl - 2.0 * rv
    trade = Trade(
        period=period,
        direction=direction,
        entry_date=signal['date'],
        entry=float(entry),
        range_high=float(rh),
        range_low=float(rl),
        range_size=float(rv),
        tp50=float(tp50),
        tp1=float(tp1),
        tp2=float(tp2),
        boundary_stop=float(boundary_stop),
        symbol=str(signal.get('symbol', '')),
    )

    for idx in range(signal_idx + 1, len(month_daily)):
        row = month_daily.iloc[idx]
        d = row['date']
        high, low, close_px = float(row['high']), float(row['low']), float(row['close'])
        trade.mae_price_pts, trade.mfe_price_pts = update_excursion(
            direction, entry, high, low, trade.mae_price_pts, trade.mfe_price_pts
        )

        if direction == 'Long':
            if trade.tp1_hit:
                if 4 in trade.open_units and low <= trade.boundary_stop:
                    close_unit(trade, 4, d, trade.boundary_stop, 'Boundary-Stop-After-TP1')
                    return trade
                if 4 in trade.open_units and high >= trade.tp2:
                    close_unit(trade, 4, d, trade.tp2, 'TP2')
                    return trade
            else:
                if 1 in trade.open_units and high >= trade.tp50:
                    close_unit(trade, 1, d, trade.tp50, 'TP50')
                if high >= trade.tp1:
                    close_unit(trade, 2, d, trade.tp1, 'TP1')
                    close_unit(trade, 3, d, trade.tp1, 'TP1')
                    trade.tp1_hit = True
                    if 4 in trade.open_units and low <= trade.boundary_stop:
                        close_unit(trade, 4, d, trade.boundary_stop, 'Boundary-Stop-After-TP1')
                        return trade
                    if 4 in trade.open_units and high >= trade.tp2:
                        close_unit(trade, 4, d, trade.tp2, 'TP2')
                        return trade
                elif close_inside(close_px, rh, rl):
                    close_open_units(trade, d, close_px, 'Daily-Close-Back-In-Range-Before-TP1')
                    return trade
        else:
            if trade.tp1_hit:
                if 4 in trade.open_units and high >= trade.boundary_stop:
                    close_unit(trade, 4, d, trade.boundary_stop, 'Boundary-Stop-After-TP1')
                    return trade
                if 4 in trade.open_units and low <= trade.tp2:
                    close_unit(trade, 4, d, trade.tp2, 'TP2')
                    return trade
            else:
                if 1 in trade.open_units and low <= trade.tp50:
                    close_unit(trade, 1, d, trade.tp50, 'TP50')
                if low <= trade.tp1:
                    close_unit(trade, 2, d, trade.tp1, 'TP1')
                    close_unit(trade, 3, d, trade.tp1, 'TP1')
                    trade.tp1_hit = True
                    if 4 in trade.open_units and high >= trade.boundary_stop:
                        close_unit(trade, 4, d, trade.boundary_stop, 'Boundary-Stop-After-TP1')
                        return trade
                    if 4 in trade.open_units and low <= trade.tp2:
                        close_unit(trade, 4, d, trade.tp2, 'TP2')
                        return trade
                elif close_inside(close_px, rh, rl):
                    close_open_units(trade, d, close_px, 'Daily-Close-Back-In-Range-Before-TP1')
                    return trade

    if trade.open_units:
        last = month_daily.iloc[-1]
        close_open_units(trade, last['date'], float(last['close']), 'Period-Close')
        trade.open_at_end = True
    return trade


def run_study(daily: pd.DataFrame, side: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    trades: list[Trade] = []
    skips: list[dict] = []
    for period, month_daily in period_groups(daily):
        rb = month_daily.iloc[:3]
        rh, rl = float(rb['high'].max()), float(rb['low'].min())
        rv = rh - rl
        if rv <= 0:
            skips.append({'Period': period, 'Reason': 'Invalid range'})
            continue
        signal_idx = None
        setup = None
        overextended = None
        for idx in range(3, len(month_daily)):
            row = month_daily.iloc[idx]
            close_px = float(row['close'])
            if close_px > rh and side in {'both', 'long'}:
                signal_idx = idx
                setup = breakout_setup(row, rh, rl, rv, side)
                overextended = setup is None
                break
            if close_px < rl and side in {'both', 'short'}:
                signal_idx = idx
                setup = breakout_setup(row, rh, rl, rv, side)
                overextended = setup is None
                break
        if signal_idx is None:
            skips.append({'Period': period, 'Reason': 'No breakout close'})
            continue
        if overextended:
            row = month_daily.iloc[signal_idx]
            skips.append(
                {
                    'Period': period,
                    'Reason': 'Breakout close already beyond TP1',
                    'Breakout_Date': row['date'],
                    'Breakout_Close': float(row['close']),
                    'Range_High': rh,
                    'Range_Low': rl,
                }
            )
            continue
        trades.append(simulate_trade(period, signal_idx, month_daily, rh, rl, rv, setup))
    return rows_for(trades), pd.DataFrame(skips)


def rows_for(trades: list[Trade]) -> pd.DataFrame:
    rows = []
    cumulative = 0.0
    for t in trades:
        cumulative += t.net_points
        exits = {ex.unit: ex for ex in t.exits}
        row = {
            'Period': t.period,
            'Symbol': t.symbol,
            'Direction': t.direction,
            'Entry_Date': t.entry_date,
            'Entry_Price': t.entry,
            'Range_High': t.range_high,
            'Range_Low': t.range_low,
            'Range': t.range_size,
            'TP50_Price': t.tp50,
            'TP1_Price': t.tp1,
            'TP2_Price': t.tp2,
            'Boundary_Stop_After_TP1': t.boundary_stop,
            'TP1_Hit': t.tp1_hit,
            'Open_At_Period_Close': t.open_at_end,
            'Trade_PL': round(t.net_points, 6),
            'Result': t.result,
            'Final_Reason': t.final_reason,
            'MAE_Price_Pts': round(t.mae_price_pts, 6),
            'MFE_Price_Pts': round(t.mfe_price_pts, 6),
            'Cumulative_PL': round(cumulative, 6),
        }
        for unit in (1, 2, 3, 4):
            ex = exits.get(unit)
            row[f'Unit{unit}_Exit_Date'] = ex.date if ex else None
            row[f'Unit{unit}_Exit_Price'] = ex.price if ex else None
            row[f'Unit{unit}_Exit_Reason'] = ex.reason if ex else None
        rows.append(row)
    return pd.DataFrame(rows)


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
        return {'trades': 0, 'net_pts': 0.0, 'net_usd': 0.0, 'dd_pts': 0.0, 'dd_usd': 0.0, 'win_rate': 0.0, 'pf': math.nan, 'avg_mae': math.nan, 'max_mae': math.nan}
    pnl = pd.to_numeric(df['Trade_PL'], errors='coerce').fillna(0.0)
    mae = pd.to_numeric(df.get('MAE_Price_Pts', pd.Series(dtype=float)), errors='coerce')
    return {
        'trades': int(len(df)),
        'net_pts': float(pnl.sum()),
        'net_usd': float(pnl.sum() * point_value),
        'dd_pts': float(max_drawdown(pnl)),
        'dd_usd': float(max_drawdown(pnl) * point_value),
        'win_rate': float((pnl > 0).mean()),
        'pf': float(profit_factor(pnl)),
        'avg_mae': float(mae.mean()),
        'max_mae': float(mae.max()),
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


def load_baselines(root: Path, market: str, point_value: float) -> list[tuple[str, dict]]:
    rows = []
    for label, suffix in [
        ('Daily restricted boundary entry', 'monthly_orb_restricted.csv'),
        ('Daily restricted scaleout3 boundary entry', 'monthly_orb_restricted_scaleout3.csv'),
        ('4h close restricted daily range-close', 'monthly_orb_restricted_4h_close_entry.csv'),
        ('4h close restricted scaleout3 daily range-close', 'monthly_orb_restricted_scaleout3_4h_close_entry.csv'),
        ('4h swing-stop single, re-armed', 'monthly_orb_4h_swing_stop.csv'),
        ('4h swing-stop scaleout3, re-armed', 'monthly_orb_scaleout3_4h_swing_stop.csv'),
    ]:
        path = root / f'{market}_{suffix}'
        if not path.exists():
            continue
        df = pd.read_csv(path)
        if 'Trade_Direction' in df.columns:
            df = df[df['Trade_Direction'].astype(str) != 'No-Op']
        rows.append((label, stats(df, point_value)))
    return rows


def yearly_table(df: pd.DataFrame) -> list[str]:
    if df.empty:
        return ['No rows.']
    work = df.copy()
    work['Year'] = pd.to_datetime(work['Entry_Date']).dt.year
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


def write_report(market: str, label: str, root: Path, trades: pd.DataFrame, skips: pd.DataFrame, point_value: float) -> Path:
    case_root = root / 'case_studies' / 'monthly_orb'
    case_root.mkdir(parents=True, exist_ok=True)
    report = case_root / 'MONTHLY_ORB_DAILY_CLOSE_SCALEOUT4.md'
    rows = load_baselines(root, market, point_value)
    rows.append(('Daily close breakout scaleout4 50/TP1/TP2', stats(trades, point_value)))
    side = trades.groupby('Direction').apply(lambda x: pd.Series(stats(x, point_value))).reset_index() if not trades.empty else pd.DataFrame()
    lines = [
        f'# {label} Monthly ORB Daily-Close Breakout Scaleout4',
        '',
        'Rules:',
        '',
        '- Monthly OR = first 3 daily rows in each calendar month.',
        '- Entry = first daily close outside the range, filled at that same close.',
        '- Skip if the breakout close is already beyond TP1.',
        '- Four units: 1 exits halfway to TP1, 2 exit at TP1, 1 exits at TP2.',
        '- Before TP1, any daily close back inside the OR exits all open units at that close.',
        '- After TP1, the remaining runner stop moves to the breakout-side OR boundary.',
        '- Same-bar ambiguity after TP1 is conservative: boundary stop is checked before TP2.',
        '',
        f'Dollar figures use {label} point value of ${point_value:g}/point per contract.',
        '',
        '## Comparison',
        '',
        '| Variant | Trades | Net pts | Net USD | Max DD USD | Win rate | PF | Avg MAE pts | Max MAE pts |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for name, s in rows:
        lines.append(
            f"| {name} | {s['trades']} | {fmt_num(s['net_pts'])} | {fmt_money(s['net_usd'])} | "
            f"{fmt_money(s['dd_usd'])} | {fmt_pct(s['win_rate'])} | {fmt_num(s['pf'], 2)} | "
            f"{fmt_num(s.get('avg_mae'))} | {fmt_num(s.get('max_mae'))} |"
        )
    lines.extend(['', '## Direction Split', ''])
    if side.empty:
        lines.append('No trades.')
    else:
        lines.extend(['| Direction | Trades | Net pts | Net USD | Max DD USD | Win rate | PF |', '|---|---:|---:|---:|---:|---:|---:|'])
        for _, row in side.iterrows():
            lines.append(
                f"| {row['Direction']} | {int(row['trades'])} | {fmt_num(row['net_pts'])} | "
                f"{fmt_money(row['net_usd'])} | {fmt_money(row['dd_usd'])} | "
                f"{fmt_pct(row['win_rate'])} | {fmt_num(row['pf'], 2)} |"
            )
    lines.extend(
        [
            '',
            '## Exit Mix',
            '',
        ]
    )
    if trades.empty:
        lines.append('No trades.')
    else:
        for reason, count in trades['Final_Reason'].value_counts().items():
            lines.append(f'- {reason}: **{count}**')
    lines.extend(
        [
            '',
            '## Skips',
            '',
        ]
    )
    if skips.empty:
        lines.append('No skipped months.')
    else:
        for reason, count in skips['Reason'].value_counts().items():
            lines.append(f'- {reason}: **{count}**')
    lines.extend(['', '## Yearly Split', '', *yearly_table(trades), '', '## Outputs', '', f'- `{market}/{market}_monthly_orb_daily_close_scaleout4.csv`', f'- `{market}/{market}_monthly_orb_daily_close_scaleout4_skips.csv`'])
    report.write_text('\n'.join(lines) + '\n')
    return report


def run_market(market: str, side: str) -> tuple[pd.DataFrame, pd.DataFrame, Path]:
    cfg = MARKETS[market]
    daily = load_daily(cfg['daily'])
    trades, skips = run_study(daily, side=side)
    out = cfg['root'] / f'{market}_monthly_orb_daily_close_scaleout4.csv'
    skip_out = cfg['root'] / f'{market}_monthly_orb_daily_close_scaleout4_skips.csv'
    trades.to_csv(out, index=False)
    skips.to_csv(skip_out, index=False)
    report = write_report(market, cfg['label'], cfg['root'], trades, skips, cfg['point_value'])
    return trades, skips, report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--market', choices=['mnq', 'nq', 'both'], default='both')
    ap.add_argument('--side', choices=['both', 'long', 'short'], default='both')
    args = ap.parse_args()

    markets = ['mnq', 'nq'] if args.market == 'both' else [args.market]
    for market in markets:
        trades, skips, report = run_market(market, args.side)
        print(f'Wrote {market}: {len(trades)} trades, {len(skips)} skips, report {report}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
