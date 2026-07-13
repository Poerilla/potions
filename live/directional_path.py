from __future__ import annotations

from typing import Optional

from .models import Bar, BrokerOrder


def position_sign(order: BrokerOrder, position_qty: int) -> int:
    if position_qty > 0:
        return 1
    if position_qty < 0:
        return -1
    if order.reduce_only:
        return -1 if order.side == "sell" else 1
    return 0


def adverse_path_hits_stop_before_target(
    bar: Bar,
    *,
    position_sign: int,
    stop_price: float,
    target_price: float,
) -> bool:
    """Return True when the conservative intra-bar path stops out before target."""
    if position_sign > 0:
        if bar.low > stop_price:
            return False
        if bar.high < target_price:
            return True
        return True
    if position_sign < 0:
        if bar.high < stop_price:
            return False
        if bar.low > target_price:
            return True
        return True
    return False


def pessimistic_limit_fill_allowed(
    order: BrokerOrder,
    bar: Bar,
    *,
    position_qty: int,
    peer_stop_price: Optional[float],
    peer_target_price: Optional[float],
) -> bool:
    """Block optimistic limit fills when adverse path would hit stop first."""
    if order.order_type != "limit" or order.limit_price is None:
        return True
    if peer_stop_price is None:
        return True
    sign = position_sign(order, position_qty)
    if sign == 0:
        return True
    target = peer_target_price if peer_target_price is not None else order.limit_price
    stop = peer_stop_price
    if sign > 0 and order.side != "sell":
        return True
    if sign < 0 and order.side != "buy":
        return True
    stop_touched = bar.low <= stop if sign > 0 else bar.high >= stop
    target_touched = bar.high >= target if sign > 0 else bar.low <= target
    if stop_touched and target_touched:
        return False
    if stop_touched:
        return False
    if target_touched and not stop_touched:
        return True
    return True
