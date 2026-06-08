from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional, Sequence

import pandas as pd

from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .replay_audit import AuditResult, audit_units, units_from_live_fills
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any
from .verification import QuietPaperVerificationProvider


REPO = Path(__file__).resolve().parents[1]
DEFAULT_SLIPPAGE_TICKS = 1.0
DEFAULT_FEE_PER_UNIT = 1.50
TICK_SIZES = {
    'NQ': 0.25,
    'MNQ': 0.25,
    'ES': 0.25,
    'MES': 0.25,
    'YM': 1.0,
    'MYM': 1.0,
}


@dataclass(frozen=True)
class ReplayResult:
    market: str
    strategy_id: str
    audit: AuditResult


def load_1h_bars(market: str) -> List[Bar]:
    cfg = MARKETS[market]
    print('Loading %s 1m for 1h replay...' % cfg.instrument, flush=True)
    by_day = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    sessions = sorted(by_day.keys())
    if cfg.start:
        sessions = [s for s in sessions if s >= cfg.start]
    parts = []
    for session in sessions:
        df = by_day.get(session)
        if df is not None and not df.empty:
            parts.append(df.sort_index())
    if not parts:
        return []
    one_min = pd.concat(parts).sort_index()
    hourly = (
        one_min.resample('1h', label='right', closed='right')
        .agg(
            open=('open', 'first'),
            high=('high', 'max'),
            low=('low', 'min'),
            close=('close', 'last'),
            volume=('volume', 'sum'),
        )
        .dropna(subset=['open', 'high', 'low', 'close'])
    )
    bars: List[Bar] = []
    for ts, row in hourly.iterrows():
        bars.append(
            Bar(
                instrument=cfg.instrument,
                timeframe='1h',
                ts=pd.Timestamp(ts).isoformat(),
                open=float(row['open']),
                high=float(row['high']),
                low=float(row['low']),
                close=float(row['close']),
                volume=float(row.get('volume') or 0.0),
                complete=True,
                source=str(cfg.dbn_path),
            )
        )
    print('  %s 1h bars' % f'{len(bars):,}', flush=True)
    return bars


def read_bars_for_audit(bars: List[Bar]):
    from .replay_audit import Bar as AuditBar

    return [AuditBar(ts=b.ts, open=b.open, high=b.high, low=b.low, close=b.close) for b in bars]


def money(value: float) -> str:
    return '$%s' % f'{value:,.2f}'


def profit_factor(unit_fills_path: Path) -> float:
    if not unit_fills_path.exists():
        return 0.0
    with unit_fills_path.open('r', newline='', encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))
    usd = [float(r.get('usd') or 0.0) for r in rows]
    gross_win = sum(x for x in usd if x > 0)
    gross_loss = -sum(x for x in usd if x < 0)
    return gross_win / gross_loss if gross_loss else float('inf')


def run_market(output_root: Path, market: str, force: bool) -> ReplayResult:
    cfg = MARKETS[market]
    instrument = cfg.instrument
    strategy_id = '%s_wo_gap_reversal' % market
    state_root = output_root / 'states' / strategy_id
    if state_root.exists() and force:
        shutil.rmtree(state_root)
    state_root.parent.mkdir(parents=True, exist_ok=True)

    bars = load_1h_bars(market)
    if not bars:
        raise RuntimeError('No 1h bars for %s' % market)

    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type='wo_gap_reversal',
        version='v1',
        instrument=instrument,
        broker_instrument=instrument,
        account_mode='paper',
        enabled=True,
        timeframes='1h',
        max_contracts=2,
        max_open_orders=12,
        config_json=json.dumps(
            {
                'gap_pct': 0.55,
                'use_swing_filter': True,
                'max_trades_per_week': 2,
                'stop_after_win': True,
                'max_fill_wait_bars': 6,
                'stop_pts': 50.0,
                'tp1_pts': 50.0,
                'runner_target_pts': 300.0,
                'tp1_qty': 1,
                'runner_qty': 1,
                'tick_size': TICK_SIZES[instrument],
                'short_only': False,
                'record_levels': False,
            },
            sort_keys=True,
        ),
    )
    store.write_table('strategy_instances', [as_row(instance)])
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        slippage_ticks=DEFAULT_SLIPPAGE_TICKS,
        tick_size={instrument: TICK_SIZES[instrument]},
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
    )
    for idx, bar in enumerate(bars, start=1):
        engine.process_bar(bar)
        if idx % 25000 == 0:
            print('  replayed %d/%d' % (idx, len(bars)), flush=True)
    if hasattr(engine.broker, 'flush_state'):
        engine.broker.flush_state()
    store.flush_tables()

    fills_path = state_root / 'fills.csv'
    units = units_from_live_fills(fills_path, strategy_id, bars[-1].ts, bars[-1].close)
    audit = audit_units(
        name='%s WO Gap Reversal (StrategyPlugin)' % instrument,
        slug=strategy_id,
        source=fills_path,
        bar_source=cfg.dbn_path,
        bars=read_bars_for_audit(bars),
        units=units,
        instrument=instrument,
        notes=(
            'Broker-like 1h Engine + PaperBroker. W-SUN weekly open gap reversal: '
            '55%% gap candle, limit @ WO, 6-bar fill window, swing filter, '
            '2ct +50 / runner 300, SL 50, max 2 trades/week, stop after win. '
            'Slippage=%g tick, fee=$%.2f/unit.'
            % (DEFAULT_SLIPPAGE_TICKS, DEFAULT_FEE_PER_UNIT)
        ),
        output_root=output_root / 'audits',
        fee_per_unit=DEFAULT_FEE_PER_UNIT,
    )
    return ReplayResult(market=market, strategy_id=strategy_id, audit=audit)


def write_summary(output_root: Path, results: Sequence[ReplayResult]) -> None:
    lines = [
        '# WO Gap Reversal — cross-market broker-like replay',
        '',
        'Causal **StrategyPlugin** replay through Engine + PaperBroker on **1h** bars.',
        'Rules match the NQ chart study: 55% WO gap, limit retest, swing filter, 2ct scale-out.',
        '',
        '| Market | Units | Trades | Net USD | Win % | PF | Closed DD | Stress DD | Max open | Net/Stress | Audit |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|',
    ]
    rows = []
    for result in results:
        audit = result.audit
        unit_path = output_root / 'audits' / audit.slug / 'unit_fills.csv'
        pf = profit_factor(unit_path)
        win_rate = 100.0 * audit.win_units / audit.units if audit.units else 0.0
        net_stress = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
        pf_text = 'inf' if math.isinf(pf) else '%.2f' % pf
        audit_rel = 'audits/%s/reports/MTM_AUDIT.md' % audit.slug
        lines.append(
            '| %s | %d | %d | %s | %.1f%% | %s | %s | %s | %d | %.2f | [%s](%s) |'
            % (
                result.market.upper(),
                audit.units,
                audit.trades,
                money(audit.net_usd),
                win_rate,
                pf_text,
                money(audit.close_mtm_dd_usd),
                money(audit.intrabar_mtm_dd_usd),
                audit.max_open_units,
                net_stress,
                audit.slug,
                audit_rel,
            )
        )
        rows.append(
            {
                'market': result.market,
                'units': audit.units,
                'trades': audit.trades,
                'net_usd': audit.net_usd,
                'win_rate': win_rate,
                'profit_factor': pf,
                'closed_dd': audit.close_mtm_dd_usd,
                'stress_dd': audit.intrabar_mtm_dd_usd,
                'max_open_units': audit.max_open_units,
                'net_over_stress': net_stress,
            }
        )
    pd.DataFrame(rows).to_csv(output_root / 'summary.csv', index=False)
    (output_root / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')


def run(
    output_root: Path,
    markets: Sequence[str],
    force: bool,
) -> List[ReplayResult]:
    if output_root.exists() and force:
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    results: List[ReplayResult] = []
    for market in markets:
        print('=== %s ===' % market.upper(), flush=True)
        results.append(run_market(output_root, market, force=True))
        write_summary(output_root, results)
    write_summary(output_root, results)
    print('Wrote %s' % (output_root / 'INDEX.md'), flush=True)
    return results


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Broker-like WO gap reversal cross-market replay.')
    parser.add_argument('--output-root', type=Path, default=REPO / 'live/state/wo_gap_reversal_broker_like')
    parser.add_argument('--market', action='append', choices=sorted(MARKETS), default=None)
    parser.add_argument('--no-force', action='store_true')
    args = parser.parse_args(argv)
    run(
        args.output_root,
        args.market or sorted(MARKETS),
        force=not args.no_force,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
