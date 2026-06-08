"""
Prior **calendar** week (Mon–Fri) H/L on MNQ **daily** bars (Databento front month).

The **prior week** for session date *d* = Mon–Fri of the week **before** the week
containing *d* (trading days must exist in *daily*).
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Literal, Optional, Tuple

import numpy as np
import pandas as pd
import databento as db

SYMBOL_PREFIX = 'MNQ'
_MNQ = Path(__file__).resolve().parent.parent.parent  # potions/mnq
DEFAULT_DAILY_DBN = _MNQ / 'raw' / 'glbx-mdp3-20100606-20260426.ohlcv-1d.dbn.zst'


def load_mnq_front_daily(dbn: Path) -> pd.DataFrame:
    store = db.DBNStore.from_file(str(dbn))
    df = store.to_df().reset_index()
    df = df[~df['symbol'].str.contains('-', na=False)]
    df = df[df['symbol'].str.startswith(SYMBOL_PREFIX)].copy()
    df['d'] = pd.to_datetime(df['ts_event']).dt.date
    fm = df.loc[df.groupby('d')['volume'].idxmax()]
    out = fm.set_index('d').sort_index()
    return out[['open', 'high', 'low', 'close', 'volume', 'symbol']].copy()


def _week_start_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def prior_week_hilo(
    daily: pd.DataFrame, session_day: date
) -> Tuple[Optional[float], Optional[float]]:
    """(PWH, PWL) for Mon–Fri of the week before *session_day*'s week; or (None, None)."""
    this_mon = _week_start_monday(session_day)
    prev_mon = this_mon - timedelta(days=7)
    wk = [prev_mon + timedelta(days=i) for i in range(5)]
    sub = daily.reindex(wk)
    if sub['high'].isna().all():
        return None, None
    pwh = float(sub['high'].max())
    pwl = float(sub['low'].min())
    if np.isnan(pwh) or np.isnan(pwl):
        return None, None
    return pwh, pwl


def prior_week_last_close(
    daily: pd.DataFrame, session_day: date
) -> Optional[float]:
    """
    **Close** of the last trading day in the **prior** Mon–Fri week
    (usually Friday), from daily bars. ``None`` if that week is missing in *daily*.
    """
    this_mon = _week_start_monday(session_day)
    prev_mon = this_mon - timedelta(days=7)
    wk = [prev_mon + timedelta(days=i) for i in range(5)]
    sub = daily.reindex(wk)
    sub = sub.dropna(subset=['close'])
    if sub.empty:
        return None
    return float(sub['close'].iloc[-1])


def pick_pw_fade_side(
    pwh: float,
    pwl: float,
    ldn_h: float,
    ldn_l: float,
    prox: float,
) -> Tuple[Optional[Literal['Short', 'Long']], float, float]:
    """
    * **Short** — fade PWH (limit at LdnH) if |PWH−LdnH| ≤ *prox* (stronger when both).
    * **Long** — fade PWL (limit at LdnL) if |PWL−LdnL| ≤ *prox*.

    If both qualify, the **tighter** |diff| wins; tie → Short.

    Returns ``( 'Short' | 'Long' | None, |PWH−LdnH|, |PWL−LdnL| )``.
    """
    d_h = abs(float(pwh) - float(ldn_h))
    d_l = abs(float(pwl) - float(ldn_l))
    near_h = d_h <= prox
    near_l = d_l <= prox
    if not near_h and not near_l:
        return None, d_h, d_l
    if near_h and not near_l:
        return 'Short', d_h, d_l
    if near_l and not near_h:
        return 'Long', d_h, d_l
    if d_h < d_l - 1e-9:
        return 'Short', d_h, d_l
    if d_l < d_h - 1e-9:
        return 'Long', d_h, d_l
    return 'Short', d_h, d_l
