#!/usr/bin/env python3
"""3-contract intraday ladder using monthly OR range-multiple targets."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import argparse
import math
import sys

import pandas as pd

from monthly_orb_intraday_ladder3_validate import (
    Ladder3Month,
    max_drawdown,
    profit_factor,
    summarize,
)
from monthly_orb_intraday_scaleout_validate import (
    IN_TRADE,
    MAX_TRADES_PER_PERIOD,
    MNQ_ROOT,
    RAW_1M,
    WAIT_BREAKOUT,
    WAIT_FILL,
    fmt_money,
    fmt_num,
    fmt_pct,
    inside_opposite_entry,
    load_daily,
    load_raw_1m,
    period_rows,
)


REPORT = MNQ_ROOT / 'case_studies' / 'monthly_orb' / 'INSIDE_SOURCE_STOP_LADDER3_RANGE_TARGETS_INTRADAY_STUDY.md'


class RangeTargetLadder3Month(Ladder3Month):
    """Same ladder mechanics, but targets are monthly OR range multiples."""

    def arm_order(self, direction: str, bar) -> bool:
        found = inside_opposite_entry(self.history, direction, self.range_high, self.range_low)
        if found is None:
            return False
        entry = float(found['price'])
        if direction == 'Long':
            initial_stop = float(found['run_low'])
            risk = entry - initial_stop
            if risk <= 0:
                return False
            targets = [
                self.range_high + self.range_val,
                self.range_high + 2.0 * self.range_val,
                self.range_high + 3.0 * self.range_val,
            ]
            boundary_stop = self.range_high
        else:
            initial_stop = float(found['run_high'])
            risk = initial_stop - entry
            if risk <= 0:
                return False
            targets = [
                self.range_low - self.range_val,
                self.range_low - 2.0 * self.range_val,
                self.range_low - 3.0 * self.range_val,
            ]
            boundary_stop = self.range_low

        self.direction = direction
        self.entry = entry
        self.initial_stop = initial_stop
        self.boundary_stop = boundary_stop
        self.risk = risk
        self.targets = targets
        self.breakout_date = bar['date']
        self.order_live_date = bar['date'] + timedelta(days=1)
        self.source = found
        self.phase = WAIT_FILL
        return True


def run_ladder3_range(daily: pd.DataFrame, raw: pd.DataFrame, *, restricted: bool) -> pd.DataFrame:
    grouped = raw.groupby(['date', 'symbol'], sort=False)
    rows = []
    for period, bars in period_rows(daily):
        sim = RangeTargetLadder3Month(period, bars, grouped, restricted=restricted)
        rows.extend(sim.run())
    out = pd.DataFrame(rows)
    if not out.empty:
        out['Cumulative_PL'] = out['Trade_PL'].astype(float).cumsum().round(6)
    return out


def write_report(rows: list[dict]) -> None:
    lines = [
        '# Inside Source-Stop 3-Contract Range-Target Ladder Intraday Study',
        '',
        'Corrected interpretation of `1R/2R/3R`: targets are monthly opening-range multiples from the breakout boundary, not source-stop risk multiples.',
        '',
        '- Long target 1 = monthly OR high + range; target 2 = OR high + 2x range; target 3 = OR high + 3x range.',
        '- Short target 1 = monthly OR low - range; target 2 = OR low - 2x range; target 3 = OR low - 3x range.',
        '- Initial stop remains the selected inside-candle/run low for longs and high for shorts.',
        '- After target 1, remaining units move their protective stop to the breakout-side range boundary.',
        '- Restricted still exits at daily close if price closes back inside the monthly OR.',
        '',
        'Results are MNQ gross before fees/slippage, using raw 1-minute bars for fill and exit order.',
        '',
        '| Variant | Trades | Net | Max DD | Net/contract | DD/contract | Win rate | PF | Avg/trade pts | Avg account R | Target 1 | Target 2 | Target 3 | Full stops | Boundary stops | Range closes | Period closes |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for row in rows:
        s = row['stats']
        lines.append(
            f"| {row['label']} | {s['trades']} | {fmt_money(s['net_usd'])} | {fmt_money(s['dd_usd'])} | "
            f"{fmt_money(s['net_per_contract_usd'])} | {fmt_money(s['dd_per_contract_usd'])} | "
            f"{fmt_pct(s['win_rate'])} | {fmt_num(s['pf'])} | {fmt_num(s['avg_trade_pts'])} | "
            f"{fmt_num(s['avg_account_r'])} | {s['target1_hits']} | {s['target2_hits']} | {s['target3_hits']} | "
            f"{s['full_stops']} | {s['boundary_stops']} | {s['range_closes']} | {s['period_closes']} |"
        )
    lines.extend([
        '',
        '## Read',
        '',
        'This version tests the idea you meant: the first scale-out waits for the full monthly measured move. It should be judged against the earlier risk-multiple ladder separately, because the target distances are much larger.',
        '',
        '## Output CSVs',
        '',
    ])
    for row in rows:
        lines.append(f"- {row['label']}: `{row['path']}`")
    lines.append('')
    REPORT.write_text('\n'.join(lines), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--daily', type=Path, default=MNQ_ROOT / 'mnq_daily.csv')
    ap.add_argument('--raw-1m', type=Path, default=RAW_1M)
    args = ap.parse_args()

    daily = load_daily(args.daily)
    print(f'Loading raw 1m from {args.raw_1m}...', file=sys.stderr)
    raw = load_raw_1m(args.raw_1m)
    print(f'Loaded {len(raw):,} minute rows', file=sys.stderr)

    rows = []
    for restricted in (False, True):
        label = 'unrestricted ladder range-target 1/2/3' if not restricted else 'restricted ladder range-target 1/2/3'
        suffix = 'source_stop_ladder3_range_targets' if not restricted else 'restricted_source_stop_ladder3_range_targets'
        out = run_ladder3_range(daily, raw, restricted=restricted)
        path = MNQ_ROOT / f'mnq_monthly_orb_inside_{suffix}_intraday.csv'
        out.to_csv(path, index=False)
        stats = summarize(out)
        rows.append({'label': label, 'path': path, 'stats': stats})
        print(
            f"{label}: {fmt_money(stats['net_usd'])}, DD {fmt_money(stats['dd_usd'])}, "
            f"WR {fmt_pct(stats['win_rate'])}, PF {fmt_num(stats['pf'])}, "
            f"T1/T2/T3 {stats['target1_hits']}/{stats['target2_hits']}/{stats['target3_hits']}, wrote {path}"
        )

    write_report(rows)
    print(f'Wrote {REPORT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
