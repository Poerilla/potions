from __future__ import annotations

from potions.live.models import Bar
from potions.live.spread_model import SpreadModel


def test_spread_model_widens_open_session():
    model = SpreadModel(rth_half_spread_ticks=0.5, open_widen_half_spread_ticks=1.0, tick_size=0.25)
    open_bar = Bar("MNQ", "1m", "2026-03-04T09:31:00-05:00", 100.0, 101.0, 99.5, 100.5, volume=500)
    mid_bar = Bar("MNQ", "1m", "2026-03-04T10:15:00-05:00", 100.0, 101.0, 99.5, 100.5, volume=500)
    assert model.half_spread_points(open_bar) == 0.25
    assert model.half_spread_points(mid_bar) == 0.125


def test_spread_adjusts_buy_higher_sell_lower():
    model = SpreadModel(rth_half_spread_ticks=1.0, tick_size=0.25)
    bar = Bar("MNQ", "1m", "2026-03-04T10:00:00-05:00", 100.0, 101.0, 99.5, 100.5, volume=500)
    assert model.adjust_fill_price("buy", 100.0, bar) == 100.25
    assert model.adjust_fill_price("sell", 100.0, bar) == 99.75


def test_limit_touch_requires_through_spread():
    model = SpreadModel(rth_half_spread_ticks=1.0, tick_size=0.25)
    bar = Bar("MNQ", "1m", "2026-03-04T10:00:00-05:00", 100.0, 100.2, 99.75, 100.25, volume=500)
    assert not model.limit_touch_ok("sell", bar, 100.0)
    assert model.limit_touch_ok("sell", bar, 99.5)
