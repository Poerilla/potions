"""Monday OR week-end flatten is Friday @ NY 15:59 only (not daily)."""

from __future__ import annotations

from datetime import datetime

import pytz

from potions.live.strategies.monday_or_breakout import _friday_week_end_due, _parse_ny


NY = pytz.timezone("America/New_York")


def _ny(y, m, d, hh, mm):
    return NY.localize(datetime(y, m, d, hh, mm))


def test_friday_week_end_fires_on_1545_left_labeled_bar():
    # 15:45 left-labeled 15m covers [15:45, 16:00) which includes 15:59.
    assert _friday_week_end_due(_ny(2026, 7, 24, 15, 45)) is True


def test_friday_week_end_not_before_1545():
    assert _friday_week_end_due(_ny(2026, 7, 24, 15, 30)) is False
    assert _friday_week_end_due(_ny(2026, 7, 24, 14, 0)) is False


def test_week_end_not_daily_tue_thu():
    # Same clock on Tue–Thu must not flatten.
    for day in (21, 22, 23):  # Tue Wed Thu of that week
        assert _friday_week_end_due(_ny(2026, 7, day, 15, 45)) is False
        assert _friday_week_end_due(_ny(2026, 7, day, 16, 0)) is False


def test_parse_ny_accepts_oanda_nanos():
    dt = _parse_ny("2026-07-24T19:45:00.123456789Z")
    assert dt.tzinfo is not None
    assert dt.astimezone(NY).hour == 15
