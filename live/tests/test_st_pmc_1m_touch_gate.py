from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from potions.live.nq_v2b_prior_opposed_replay import (
    first_1m_limit_touch,
    load_st_events,
    touch_stats_from_events,
)


NY = "America/New_York"


def _day_bars(day: date, rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    index = []
    data = []
    for hhmm, o, h, l, c in rows:
        index.append(pd.Timestamp("%sT%s:00-05:00" % (day.isoformat(), hhmm)))
        data.append({"open": o, "high": h, "low": l, "close": c, "volume": 1.0})
    return pd.DataFrame(data, index=pd.DatetimeIndex(index, name="ts_event"))


def test_first_1m_limit_touch_buy_after_live_after():
    day = date(2021, 3, 4)
    bars = {
        day: _day_bars(
            day,
            [
                ("09:00", 100.0, 100.5, 99.8, 100.2),
                ("10:00", 100.0, 100.2, 99.5, 99.6),  # touches buy 99.5
                ("10:01", 99.6, 99.7, 99.4, 99.5),
                ("10:05", 99.5, 99.6, 99.0, 99.1),
            ],
        )
    }
    touch, status = first_1m_limit_touch(
        bars,
        side="buy",
        limit_price=99.5,
        live_after_ts="2021-03-04T09:00:00-05:00",
        fill_ts_hourly="2021-03-04T10:00:00-05:00",
    )
    assert status == "resolved_in_hour"
    assert touch is not None
    assert touch.isoformat() == "2021-03-04T10:00:00-05:00"


def test_first_1m_limit_touch_sell_skips_live_after_bar():
    day = date(2021, 3, 4)
    bars = {
        day: _day_bars(
            day,
            [
                ("09:00", 100.0, 100.8, 99.9, 100.5),  # would touch sell 100.5 but == live_after
                ("10:00", 100.4, 100.4, 100.0, 100.1),  # no touch
                ("10:17", 100.2, 100.6, 100.1, 100.5),  # first valid sell touch
            ],
        )
    }
    touch, status = first_1m_limit_touch(
        bars,
        side="sell",
        limit_price=100.5,
        live_after_ts="2021-03-04T09:00:00-05:00",
        fill_ts_hourly="2021-03-04T10:00:00-05:00",
    )
    assert status == "resolved_in_hour"
    assert touch is not None
    assert touch.isoformat() == "2021-03-04T10:17:00-05:00"


def test_first_1m_limit_touch_unresolved_keeps_none():
    day = date(2021, 3, 4)
    bars = {
        day: _day_bars(
            day,
            [
                ("10:00", 100.0, 100.2, 99.9, 100.0),
                ("10:30", 100.0, 100.1, 99.95, 100.0),
            ],
        )
    }
    touch, status = first_1m_limit_touch(
        bars,
        side="buy",
        limit_price=99.0,
        live_after_ts="2021-03-04T09:00:00-05:00",
        fill_ts_hourly="2021-03-04T10:00:00-05:00",
    )
    assert touch is None
    assert status == "unresolved"


def test_load_st_events_refines_and_buckets_by_ny_date(tmp_path: Path):
    day = date(2021, 3, 4)
    fills = pd.DataFrame(
        [
            {
                "fill_id": "f1",
                "broker_order_id": "o1",
                "intent_id": "i1",
                "strategy_id": "nq_hourly_st_pmc_sl25_tp75_3r",
                "trade_id": "t1",
                "instrument": "NQ",
                "account_mode": "paper",
                "side": "sell",
                "quantity": 1,
                "price": 100.5,
                "ts": "2021-03-04T10:00:00-05:00",
                "reason": "entry",
            }
        ]
    )
    orders = pd.DataFrame(
        [
            {
                "broker_order_id": "o1",
                "intent_id": "i1",
                "strategy_id": "nq_hourly_st_pmc_sl25_tp75_3r",
                "trade_id": "t1",
                "instrument": "NQ",
                "account_mode": "paper",
                "side": "sell",
                "order_type": "limit",
                "quantity": 1,
                "remaining_quantity": 0,
                "status": "filled",
                "limit_price": 100.5,
                "stop_price": "",
                "reduce_only": False,
                "bracket_role": "entry",
                "parent_order_id": "",
                "oco_group": "",
                "live_after_ts": "2021-03-04T09:00:00-05:00",
                "expires_after_ts": "",
                "created_at": "",
                "updated_at": "",
            }
        ]
    )
    fills_path = tmp_path / "fills.csv"
    orders_path = tmp_path / "orders.csv"
    fills.to_csv(fills_path, index=False)
    orders.to_csv(orders_path, index=False)
    bars = {
        day: _day_bars(
            day,
            [
                ("09:00", 100.0, 100.2, 99.9, 100.0),
                ("10:00", 100.0, 100.2, 99.9, 100.1),
                ("10:12", 100.1, 100.6, 100.0, 100.4),
            ],
        )
    }
    events = load_st_events(
        fills_path,
        "nq_hourly_st_pmc_sl25_tp75_3r",
        orders_path=orders_path,
        bars_by_ny_date=bars,
    )
    assert "2021-03-04" in events
    event = events["2021-03-04"][0]
    assert event["side"] == "short"
    assert event["ts"] == "2021-03-04T10:12:00-05:00"
    assert event["fill_ts_hourly"] == "2021-03-04T10:00:00-05:00"
    assert event["touch_unresolved"] == "false"
    stats = touch_stats_from_events(events)
    assert stats.resolved == 1
    assert stats.unresolved == 0
    assert stats.median_delay_minutes == 12.0


def test_load_st_events_unresolved_keeps_hourly_stamp(tmp_path: Path):
    day = date(2021, 3, 4)
    fills = pd.DataFrame(
        [
            {
                "fill_id": "f1",
                "broker_order_id": "o1",
                "intent_id": "i1",
                "strategy_id": "nq_hourly_st_pmc_sl25_tp75_3r",
                "trade_id": "t1",
                "instrument": "NQ",
                "account_mode": "paper",
                "side": "buy",
                "quantity": 1,
                "price": 99.0,
                "ts": "2021-03-04T10:00:00-05:00",
                "reason": "entry",
            }
        ]
    )
    orders = pd.DataFrame(
        [
            {
                "broker_order_id": "o1",
                "intent_id": "i1",
                "strategy_id": "nq_hourly_st_pmc_sl25_tp75_3r",
                "trade_id": "t1",
                "instrument": "NQ",
                "account_mode": "paper",
                "side": "buy",
                "order_type": "limit",
                "quantity": 1,
                "remaining_quantity": 0,
                "status": "filled",
                "limit_price": 99.0,
                "stop_price": "",
                "reduce_only": False,
                "bracket_role": "entry",
                "parent_order_id": "",
                "oco_group": "",
                "live_after_ts": "2021-03-04T09:00:00-05:00",
                "expires_after_ts": "",
                "created_at": "",
                "updated_at": "",
            }
        ]
    )
    fills_path = tmp_path / "fills.csv"
    orders_path = tmp_path / "orders.csv"
    fills.to_csv(fills_path, index=False)
    orders.to_csv(orders_path, index=False)
    bars = {day: _day_bars(day, [("10:00", 100.0, 100.2, 99.5, 100.0)])}
    events = load_st_events(
        fills_path,
        "nq_hourly_st_pmc_sl25_tp75_3r",
        orders_path=orders_path,
        bars_by_ny_date=bars,
    )
    event = events["2021-03-04"][0]
    assert event["ts"] == "2021-03-04T10:00:00-05:00"
    assert event["touch_unresolved"] == "true"
    stats = touch_stats_from_events(events)
    assert stats.unresolved == 1
    assert stats.resolved == 0


def test_resting_limit_available_at_hour_complete(tmp_path: Path):
    from potions.live.nq_v2b_prior_opposed_replay import load_st_resting_limit_events

    orders = pd.DataFrame(
        [
            {
                "broker_order_id": "o1",
                "intent_id": "i1",
                "strategy_id": "nq_hourly_st_pmc_sl25_tp75_3r",
                "trade_id": "t1",
                "instrument": "NQ",
                "account_mode": "paper",
                "side": "sell",
                "order_type": "limit",
                "quantity": 1,
                "remaining_quantity": 1,
                "status": "cancelled",
                "limit_price": 100.0,
                "stop_price": "",
                "reduce_only": False,
                "bracket_role": "entry",
                "parent_order_id": "",
                "oco_group": "",
                "live_after_ts": "2021-03-04T09:00:00-05:00",
                "expires_after_ts": "",
                "created_at": "",
                "updated_at": "",
            }
        ]
    )
    path = tmp_path / "orders.csv"
    orders.to_csv(path, index=False)
    causal = load_st_resting_limit_events(path, "nq_hourly_st_pmc_sl25_tp75_3r")
    ev = causal["2021-03-04"][0]
    assert ev["live_after_ts"] == "2021-03-04T09:00:00-05:00"
    assert ev["ts"] == "2021-03-04T10:00:00-05:00"
    assert ev["available_at_ts"] == "2021-03-04T10:00:00-05:00"
    assert ev["side"] == "short"
    left = load_st_resting_limit_events(
        path, "nq_hourly_st_pmc_sl25_tp75_3r", available_at_hour_complete=False
    )
    assert left["2021-03-04"][0]["ts"] == "2021-03-04T09:00:00-05:00"
