from __future__ import annotations

from datetime import date

import pandas as pd

from potions.live.bars import dense_rth_1m_bars, rth_bars, rth_minute_index


def test_rth_minute_index_has_390_bars():
    idx = rth_minute_index(date(2026, 3, 4))
    assert len(idx) == 390
    assert idx[0].strftime("%H:%M") == "09:30"
    assert idx[-1].strftime("%H:%M") == "15:59"


def test_dense_rth_forward_fills_missing_minute():
    ts1 = pd.Timestamp("2026-03-04 09:30:00-05:00")
    ts2 = pd.Timestamp("2026-03-04 09:32:00-05:00")
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [100.5, 101.5],
            "low": [99.5, 100.5],
            "close": [100.25, 101.25],
            "volume": [100.0, 200.0],
        },
        index=[ts1, ts2],
    )
    dense = dense_rth_1m_bars(df, date(2026, 3, 4))
    gap = pd.Timestamp("2026-03-04 09:31:00-05:00")
    assert gap in dense.index
    assert dense.loc[gap, "open"] == 100.25
    assert dense.loc[gap, "high"] == 100.25
    assert dense.loc[gap, "low"] == 100.25
    assert dense.loc[gap, "close"] == 100.25
    assert dense.loc[gap, "volume"] == 0.0


def test_rth_bars_dense_alias():
    ts = pd.Timestamp("2026-03-04 10:00:00-05:00")
    df = pd.DataFrame(
        {"open": [1.0], "high": [2.0], "low": [0.5], "close": [1.5], "volume": [10.0]},
        index=[ts],
    )
    out = rth_bars(df, date(2026, 3, 4), dense=True)
    assert len(out) == 390
