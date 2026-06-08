from __future__ import annotations

import json
from typing import Any, Dict, List, Literal, Optional

import pandas as pd

from ..models import Bar, CancelIntent, LevelUpdate, ModifyIntent, OrderIntent, StrategyActions
from .base import StrategyContext, StrategyPlugin

Side = Literal['long', 'short']


class WoGapReversalStrategy(StrategyPlugin):
    """Weekly-open gap reversal on 1h bars (W-SUN weeks).

    Pre-gap context, 55% gap candle, limit @ WO from next bar, 6-bar fill window,
    optional swing filter, 2ct scale-out (+50 / runner +300, BE after +50).
    """

    strategy_type = 'wo_gap_reversal'
    version = 'v1'

    def __init__(self, store, instance):
        super().__init__(store, instance)
        self.config = {
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
            'tick_size': 0.25,
            'short_only': False,
            'record_levels': False,
        }
        try:
            self.config.update(json.loads(instance.config_json or '{}'))
        except json.JSONDecodeError:
            pass

    def on_bar_close(self, bar: Bar, context: StrategyContext) -> StrategyActions:
        if bar.timeframe != '1h' or not bar.complete:
            return StrategyActions.empty()
        if not _is_tradable_ts(_parse_ts(bar.ts)):
            return StrategyActions.empty()

        state = self._state()
        ts = _parse_ts(bar.ts)
        week_key = _week_sun_key(ts)
        orders: List[OrderIntent] = []
        cancels: List[CancelIntent] = []
        levels: List[LevelUpdate] = []

        if state.get('week_key') and state['week_key'] != week_key:
            cancels.extend(self._cancel_entry_limits(context, 'new_week'))
            if context.position_quantity != 0:
                orders.append(self._close_order(context, bar.ts, 'week_roll_close'))
            state = self._reset_week(state, week_key, float(bar.open))
        elif not state.get('week_key'):
            state = self._reset_week(state, week_key, float(bar.open))

        week_bars: List[Dict[str, float]] = list(state.get('week_bars') or [])
        week_bars.append(
            {
                'open': float(bar.open),
                'high': float(bar.high),
                'low': float(bar.low),
                'close': float(bar.close),
            }
        )
        state['week_bars'] = week_bars
        cur_idx = len(week_bars) - 1
        wo = float(state['wo'])

        if bool(self.config.get('record_levels')):
            levels.append(
                LevelUpdate(self.instance.strategy_id, self.instance.instrument, 'weekly_open', wo, bar.ts)
            )

        if context.position_quantity != 0:
            cancels.extend(self._cancel_entry_limits(context, 'in_position'))
            state['pending'] = None
            state['pending_entry_trade_id'] = ''
            self.state = state
            self.save_state()
            return StrategyActions(orders, cancels, [], levels, [])

        pending = dict(state.get('pending') or {}) if state.get('pending') else None
        if pending:
            gap_idx = int(pending['gap_idx'])
            side = str(pending['side'])
            if cur_idx > gap_idx + int(self.config['max_fill_wait_bars']):
                cancels.extend(self._cancel_entry_limits(context, 'fill_window_expired'))
                self._mark_direction_used(state, side)
                state['pending'] = None
                state['pending_entry_trade_id'] = ''
            elif cur_idx > gap_idx and self._swing_blocks(week_bars, side, gap_idx, cur_idx):
                cancels.extend(self._cancel_entry_limits(context, 'swing_before_retest'))
                self._mark_direction_used(state, side)
                state['pending'] = None
                state['pending_entry_trade_id'] = ''
            else:
                desired = self._entry_orders(side, wo, state, bar.ts)
                existing = self._open_entry_limits(context)
                if not existing and cur_idx >= gap_idx + 1:
                    orders.extend(desired)
                    state['pending_entry_trade_id'] = desired[0].trade_id if desired else ''
                elif existing and cur_idx >= gap_idx + 1:
                    tick = float(self.config['tick_size'])
                    same = (
                        len(existing) == len(desired)
                        and all(o.limit_price is not None and abs(o.limit_price - wo) <= tick / 2.0 for o in existing)
                    )
                    if not same:
                        cancels.extend(self._cancel_entry_limits(context, 'refresh_wo_limit'))
                        orders.extend(desired)
                        state['pending_entry_trade_id'] = desired[0].trade_id if desired else ''

        elif self._can_scan(state):
            side = self._gap_side(week_bars, cur_idx, wo, state)
            if side:
                state['pending'] = {'side': side, 'gap_idx': cur_idx}
                orders.extend(self._entry_orders(side, wo, state, bar.ts))
                if orders:
                    state['pending_entry_trade_id'] = orders[0].trade_id

        self.state = state
        self.save_state()
        return StrategyActions(orders, cancels, [], levels, [])

    def on_fill(self, fill, context: StrategyContext) -> StrategyActions:
        state = self._state()
        modifies: List[ModifyIntent] = []
        if fill.reason == 'entry':
            state['active_trade_id'] = fill.trade_id
            state['pending_entry_trade_id'] = ''
            state['pending'] = None
            state['entry_price'] = float(fill.price)
            state['trades_this_week'] = int(state.get('trades_this_week') or 0) + 1
        elif fill.reason == 'target':
            entry = float(state.get('entry_price') or fill.price)
            state['weekly_has_win'] = True
            if bool(self.config.get('runner_qty')):
                for order in context.strategy_open_orders:
                    if (
                        order.trade_id == fill.trade_id
                        and order.reduce_only
                        and order.order_type == 'stop'
                        and (order.bracket_role or '') == 'runner_stop'
                    ):
                        modifies.append(
                            ModifyIntent(
                                self.instance.strategy_id,
                                order.broker_order_id,
                                'runner_stop_to_breakeven',
                                stop_price=entry,
                                live_after_ts=fill.ts,
                            )
                        )
            if context.position_quantity == 0:
                state['active_trade_id'] = ''
        elif fill.reason in {'stop', 'protective_stop', 'close', 'week_roll_close'}:
            if context.position_quantity == 0:
                state['active_trade_id'] = ''
                if fill.reason == 'target' or (
                    fill.reason in {'close', 'week_roll_close'}
                    and self._fill_is_winner(fill, state)
                ):
                    state['weekly_has_win'] = True
        self.state = state
        self.save_state()
        return StrategyActions([], [], modifies, [], [])

    def _reset_week(self, state: Dict[str, Any], week_key: str, wo: float) -> Dict[str, Any]:
        state['week_key'] = week_key
        state['wo'] = wo
        state['week_bars'] = []
        state['trades_this_week'] = 0
        state['weekly_has_win'] = False
        state['long_breakout_used'] = False
        state['short_breakout_used'] = False
        state['pending'] = None
        state['pending_entry_trade_id'] = ''
        state['active_trade_id'] = ''
        state['entry_price'] = 0.0
        return state

    def _state(self) -> Dict[str, Any]:
        state = dict(self.state or {})
        state.setdefault('week_bars', [])
        state.setdefault('weekly_has_win', False)
        state.setdefault('long_breakout_used', False)
        state.setdefault('short_breakout_used', False)
        return state

    def _can_scan(self, state: Dict[str, Any]) -> bool:
        cap = self.config.get('max_trades_per_week')
        if cap is not None and int(state.get('trades_this_week') or 0) >= int(cap):
            return False
        if bool(self.config.get('stop_after_win')) and bool(state.get('weekly_has_win')):
            return False
        return state.get('pending') is None

    def _gap_side(self, week_bars: List[Dict[str, float]], idx: int, wo: float, state: Dict[str, Any]) -> Optional[Side]:
        row = week_bars[idx]
        short_only = bool(self.config.get('short_only'))
        if not short_only and not state.get('long_breakout_used') and _bullish_gap(row, wo, float(self.config['gap_pct'])):
            if _first_pre_gap(week_bars, idx, wo, 'long') is not None:
                return 'long'
            state['long_breakout_used'] = True
        if not state.get('short_breakout_used') and _bearish_gap(row, wo, float(self.config['gap_pct'])):
            if _first_pre_gap(week_bars, idx, wo, 'short') is not None:
                return 'short'
            state['short_breakout_used'] = True
        return None

    def _swing_blocks(self, week_bars: List[Dict[str, float]], side: Side, gap_idx: int, before_bar: int) -> bool:
        if not bool(self.config.get('use_swing_filter')):
            return False
        return _blocking_swing(week_bars, side, gap_idx, before_bar) is not None

    def _mark_direction_used(self, state: Dict[str, Any], side: str) -> None:
        if side == 'long':
            state['long_breakout_used'] = True
        else:
            state['short_breakout_used'] = True

    def _entry_orders(self, side: Side, wo: float, state: Dict[str, Any], ts: str) -> List[OrderIntent]:
        trade_id = state.get('pending_entry_trade_id') or self._next_trade_id(state)
        buy = side == 'long'
        order_side = 'buy' if buy else 'sell'
        stop_pts = float(self.config['stop_pts'])
        tp1_pts = float(self.config['tp1_pts'])
        runner_pts = float(self.config['runner_target_pts'])
        stop = wo - stop_pts if buy else wo + stop_pts
        tp1 = wo + tp1_pts if buy else wo - tp1_pts
        runner_tgt = wo + runner_pts if buy else wo - runner_pts
        tp1_qty = int(self.config.get('tp1_qty') or 1)
        runner_qty = int(self.config.get('runner_qty') or 1)
        orders: List[OrderIntent] = []
        if tp1_qty > 0:
            orders.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=order_side,
                    order_type='limit',
                    quantity=tp1_qty,
                    limit_price=wo,
                    reason='entry',
                    requires_verification=False,
                    bracket_role='entry',
                    bracket_stop_price=stop,
                    bracket_target_price=tp1,
                    live_after_ts=ts,
                )
            )
        if runner_qty > 0:
            orders.append(
                OrderIntent.create(
                    strategy_id=self.instance.strategy_id,
                    trade_id=trade_id,
                    instrument=self.instance.instrument,
                    account_mode=self.instance.account_mode,
                    side=order_side,
                    order_type='limit',
                    quantity=runner_qty,
                    limit_price=wo,
                    reason='entry',
                    requires_verification=False,
                    bracket_role='runner_entry',
                    bracket_stop_price=stop,
                    bracket_target_price=runner_tgt,
                    live_after_ts=ts,
                )
            )
        return orders

    def _close_order(self, context: StrategyContext, ts: str, reason: str) -> OrderIntent:
        qty = abs(context.position_quantity)
        side = 'sell' if context.position_quantity > 0 else 'buy'
        return OrderIntent.create(
            strategy_id=self.instance.strategy_id,
            trade_id=self.state.get('active_trade_id') or 'week_close',
            instrument=self.instance.instrument,
            account_mode=self.instance.account_mode,
            side=side,
            order_type='market',
            quantity=qty,
            reason=reason,
            requires_verification=False,
            reduce_only=True,
            bracket_role='close',
            live_after_ts=ts,
        )

    def _fill_is_winner(self, fill, state: Dict[str, Any]) -> bool:
        entry = float(state.get('entry_price') or 0.0)
        if not entry:
            return False
        if fill.side == 'sell':
            return float(fill.price) > entry
        return float(fill.price) < entry

    def _next_trade_id(self, state: Dict[str, Any]) -> str:
        n = int(state.get('trade_seq') or 0) + 1
        state['trade_seq'] = n
        return '%s-WOGAP-%05d' % (self.instance.strategy_id, n)

    def _open_entry_limits(self, context: StrategyContext):
        return [
            order
            for order in context.strategy_open_orders
            if not order.reduce_only and order.order_type == 'limit' and (order.bracket_role or '') in {'entry', 'runner_entry'}
        ]

    def _cancel_entry_limits(self, context: StrategyContext, reason: str) -> List[CancelIntent]:
        return [CancelIntent(self.instance.strategy_id, order.broker_order_id, reason) for order in self._open_entry_limits(context)]


def _parse_ts(ts: str) -> pd.Timestamp:
    out = pd.Timestamp(ts)
    if out.tzinfo is None:
        out = out.tz_localize('America/New_York')
    return out


def _week_sun_key(ts: pd.Timestamp) -> str:
    return str(ts.to_period('W-SUN'))


def _is_tradable_ts(ts: pd.Timestamp) -> bool:
    if ts.weekday() == 5:
        return False
    if ts.weekday() == 4 and (ts.hour, ts.minute) > (16, 0):
        return False
    return True


def _bullish_gap(row: Dict[str, float], wo: float, gap_pct: float) -> bool:
    o, c = row['open'], row['close']
    if not (c > wo > o):
        return False
    body = c - o
    if body <= 0:
        return False
    above = c - wo
    below = wo - o
    if above <= below:
        return False
    return (above / body) >= gap_pct


def _bearish_gap(row: Dict[str, float], wo: float, gap_pct: float) -> bool:
    o, c = row['open'], row['close']
    if not (o > wo > c):
        return False
    body = o - c
    if body <= 0:
        return False
    below = wo - c
    above = o - wo
    if below <= above:
        return False
    return (below / body) >= gap_pct


def _candle_fully_above(row: Dict[str, float], wo: float) -> bool:
    return row['open'] > wo and row['close'] > wo


def _candle_fully_below(row: Dict[str, float], wo: float) -> bool:
    return row['open'] < wo and row['close'] < wo


def _first_pre_gap(week_bars: List[Dict[str, float]], gap_idx: int, wo: float, side: Side) -> Optional[int]:
    for k in range(gap_idx):
        row = week_bars[k]
        if side == 'short' and _candle_fully_above(row, wo):
            return k
        if side == 'long' and _candle_fully_below(row, wo):
            return k
    return None


def _is_swing_high(week_bars: List[Dict[str, float]], i: int) -> bool:
    if i < 1 or i >= len(week_bars) - 1:
        return False
    h = week_bars[i]['high']
    return h > week_bars[i - 1]['high'] and h > week_bars[i + 1]['high']


def _is_swing_low(week_bars: List[Dict[str, float]], i: int) -> bool:
    if i < 1 or i >= len(week_bars) - 1:
        return False
    lo = week_bars[i]['low']
    return lo < week_bars[i - 1]['low'] and lo < week_bars[i + 1]['low']


def _swing_includes_gap(gap_idx: int, center: int) -> bool:
    return center - 1 <= gap_idx <= center + 1


def _blocking_swing(week_bars: List[Dict[str, float]], side: Side, gap_idx: int, before_bar: int) -> Optional[int]:
    if before_bar < 2:
        return None
    last_center = min(before_bar - 2, len(week_bars) - 2)
    for i in range(max(1, gap_idx + 1), last_center + 1):
        if side == 'long':
            if _is_swing_high(week_bars, i) and not _swing_includes_gap(gap_idx, i):
                return i
        elif _is_swing_low(week_bars, i) and not _swing_includes_gap(gap_idx, i):
            return i
    return None
