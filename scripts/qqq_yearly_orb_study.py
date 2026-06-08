#!/usr/bin/env python3
"""QQQ yearly ORB study.

Rules are intentionally simple and ETF-native:
- Jan-Mar defines the yearly opening range.
- Apr-Dec is the trade window.
- Core QQQ variants are long-only; inverse rows use PSQ as a 1x inverse ETF proxy.
- Close-confirmed orders fill next open.
- Resting stop/limit orders can fill intraday from the following trade window.

This is a research/passive benchmark study, not a broker execution model.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

from qqq_obv_supertrend_study import load_qqq_daily


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_START = "2000-01-01"


@dataclass
class Trade:
    variant: str
    year: int
    setup_date: Optional[pd.Timestamp]
    entry_date: pd.Timestamp
    entry_price: float
    exit_date: pd.Timestamp
    exit_price: float
    exit_reason: str
    entry_equity: float
    exit_equity: float
    mae_pct: float
    mfe_pct: float

    @property
    def net(self) -> float:
        return self.exit_equity - self.entry_equity

    @property
    def return_pct(self) -> float:
        return self.exit_equity / self.entry_equity - 1.0 if self.entry_equity else 0.0

    @property
    def days_held(self) -> int:
        return int((self.exit_date - self.entry_date).days)


def money(value: float) -> str:
    return "$%s%s" % ("-" if value < 0 else "", format(abs(value), ",.0f"))


def pct(value: float) -> str:
    return "%.2f%%" % (value * 100.0)


def default_completed_end(today: Optional[dt.date] = None) -> str:
    day = today or dt.date.today()
    day = day - dt.timedelta(days=1)
    while day.weekday() >= 5:
        day = day - dt.timedelta(days=1)
    return day.isoformat()


def _at(values: list, idx: int) -> float:
    try:
        return values[idx]
    except Exception:
        return np.nan


def load_adjusted_daily(ticker: str, start: str, end: str, cache_dir: Path, refresh: bool = False) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    ticker = ticker.upper()
    cache = cache_dir / ("%s_%s_%s_daily.csv" % (ticker, start, end))
    if cache.exists() and not refresh:
        return pd.read_csv(cache, parse_dates=["date"])

    start_dt = dt.datetime.fromisoformat(start).replace(tzinfo=dt.timezone.utc)
    end_dt = (dt.datetime.fromisoformat(end) + dt.timedelta(days=2)).replace(tzinfo=dt.timezone.utc)
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/%s"
        "?period1=%d&period2=%d&interval=1d&events=history&includeAdjustedClose=true"
        % (ticker, int(start_dt.timestamp()), int(end_dt.timestamp()))
    )
    response = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    payload = response.json()
    result = payload.get("chart", {}).get("result", [])
    if not result:
        raise RuntimeError("No Yahoo chart data for %s: %s" % (ticker, json.dumps(payload)[:400]))

    data = result[0]
    timestamps = data.get("timestamp", [])
    quote = data.get("indicators", {}).get("quote", [{}])[0]
    adj = data.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose", [])
    rows = []
    for i, ts in enumerate(timestamps):
        rows.append(
            {
                "date": pd.to_datetime(ts, unit="s", utc=True).tz_convert(None).normalize(),
                "open_raw": _at(quote.get("open", []), i),
                "high_raw": _at(quote.get("high", []), i),
                "low_raw": _at(quote.get("low", []), i),
                "close_raw": _at(quote.get("close", []), i),
                "adj_close": _at(adj, i),
                "volume": _at(quote.get("volume", []), i),
                "data_source": "yahoo_chart_api",
                "ticker": ticker,
            }
        )
    raw = pd.DataFrame(rows).sort_values("date").dropna(subset=["close_raw", "adj_close"]).reset_index(drop=True)
    if raw.empty:
        raise RuntimeError("No %s daily rows returned for %s through %s" % (ticker, start, end))
    factor = pd.to_numeric(raw["adj_close"], errors="coerce") / pd.to_numeric(raw["close_raw"], errors="coerce")
    factor = factor.replace([np.inf, -np.inf], np.nan).fillna(1.0)
    out = raw.copy()
    out["open"] = pd.to_numeric(out["open_raw"], errors="coerce") * factor
    out["high"] = pd.to_numeric(out["high_raw"], errors="coerce") * factor
    out["low"] = pd.to_numeric(out["low_raw"], errors="coerce") * factor
    out["close"] = pd.to_numeric(out["adj_close"], errors="coerce")
    out["volume"] = pd.to_numeric(out["volume"], errors="coerce").fillna(0.0)
    out = out[(out["date"] >= pd.to_datetime(start)) & (out["date"] <= pd.to_datetime(end))]
    out = out.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    out.to_csv(cache, index=False)
    return out


def max_drawdown(equity: pd.Series) -> float:
    vals = pd.to_numeric(equity, errors="coerce").dropna()
    if vals.empty:
        return 0.0
    return float((vals - vals.cummax()).min())


def max_drawdown_pct(equity: pd.Series) -> float:
    vals = pd.to_numeric(equity, errors="coerce").dropna()
    if vals.empty:
        return 0.0
    return float((vals / vals.cummax() - 1.0).min())


def cagr(equity: pd.Series, dates: pd.Series) -> float:
    vals = pd.to_numeric(equity, errors="coerce").dropna()
    if vals.empty:
        return 0.0
    years = max((pd.Timestamp(dates.iloc[-1]) - pd.Timestamp(dates.iloc[0])).days / 365.25, 1.0)
    return float((vals.iloc[-1] / vals.iloc[0]) ** (1.0 / years) - 1.0)


def first_trading_day_each_month(daily: pd.DataFrame) -> set[pd.Timestamp]:
    work = daily[["date"]].copy()
    work["month"] = work["date"].dt.to_period("M")
    return set(pd.to_datetime(work.groupby("month")["date"].first()))


def buy_hold_equity(daily: pd.DataFrame, capital: float) -> pd.DataFrame:
    out = daily[["date", "close"]].copy()
    first = float(out.iloc[0]["close"])
    out["variant"] = "QQQ buy-and-hold"
    out["equity"] = capital * pd.to_numeric(out["close"], errors="coerce") / first
    out["exposed"] = 1.0
    return out[["date", "variant", "equity", "exposed"]]


def monthly_dca_equity(daily: pd.DataFrame, capital: float) -> pd.DataFrame:
    invest_dates = first_trading_day_each_month(daily)
    installments = len(invest_dates)
    installment = capital / installments if installments else 0.0
    cash = capital
    shares = 0.0
    rows = []
    for _, bar in daily.iterrows():
        date = pd.Timestamp(bar["date"])
        close = float(bar["close"])
        if date in invest_dates and cash > 0:
            buy = min(installment, cash)
            shares += buy / close
            cash -= buy
        equity = cash + shares * close
        invested_value = shares * close
        rows.append(
            {
                "date": date,
                "variant": "QQQ monthly DCA cash-funded",
                "equity": equity,
                "exposed": invested_value / equity if equity else 0.0,
            }
        )
    return pd.DataFrame(rows)


def hybrid_stop_breakout_plus_monthly_dca(daily: pd.DataFrame, levels: pd.DataFrame, capital: float) -> pd.DataFrame:
    """Monthly DCA core plus a tactical sweep of not-yet-DCA cash during ORB risk-on windows."""
    invest_dates = first_trading_day_each_month(daily)
    installments = len(invest_dates)
    installment = capital / installments if installments else 0.0
    cash = capital
    dca_shares = 0.0
    tactical_shares = 0.0
    pending_tactical_exit = False
    rows = []

    by_year = {int(row["year"]): row for _, row in levels.iterrows()}
    for _, bar in daily.iterrows():
        date = pd.Timestamp(bar["date"])
        year = int(date.year)
        month = int(date.month)
        open_px = float(bar["open"])
        high = float(bar["high"])
        close = float(bar["close"])
        level = by_year.get(year)

        if pending_tactical_exit and tactical_shares > 0:
            cash += tactical_shares * open_px
            tactical_shares = 0.0
            pending_tactical_exit = False

        if date in invest_dates and installment > 0:
            if cash > 0:
                buy = min(installment, cash)
                dca_shares += buy / close
                cash -= buy
            else:
                # When future DCA cash is already tactically invested, convert that
                # slice into permanent DCA shares without creating a synthetic trade.
                reclass_value = min(installment, tactical_shares * close)
                if reclass_value > 0:
                    shares = reclass_value / close
                    tactical_shares -= shares
                    dca_shares += shares

        if level is not None and month >= 4 and tactical_shares == 0 and cash > 0:
            or_high = float(level["or_high"])
            if high >= or_high:
                fill = max(or_high, open_px)
                tactical_shares += cash / fill
                cash = 0.0

        invested_value = (dca_shares + tactical_shares) * close
        equity = cash + invested_value
        rows.append(
            {
                "date": date,
                "variant": "hybrid_stop_breakout_plus_monthly_dca",
                "equity": equity,
                "exposed": invested_value / equity if equity else 0.0,
            }
        )

        if level is not None and month >= 4 and tactical_shares > 0:
            or_high = float(level["or_high"])
            if close <= or_high:
                pending_tactical_exit = True

        if is_last_row_of_year(daily, date) and tactical_shares > 0:
            cash += tactical_shares * close
            tactical_shares = 0.0
            rows[-1]["equity"] = cash + dca_shares * close
            rows[-1]["exposed"] = (dca_shares * close) / rows[-1]["equity"] if rows[-1]["equity"] else 0.0
            pending_tactical_exit = False

    return pd.DataFrame(rows)


def blend_equity_curves(left: pd.DataFrame, right: pd.DataFrame, variant: str, left_weight: float = 0.5) -> pd.DataFrame:
    right_weight = 1.0 - left_weight
    merged = left.merge(right, on="date", suffixes=("_left", "_right"))
    out = pd.DataFrame()
    out["date"] = merged["date"]
    out["variant"] = variant
    out["equity"] = merged["equity_left"] * left_weight + merged["equity_right"] * right_weight
    out["exposed"] = merged["exposed_left"] * left_weight + merged["exposed_right"] * right_weight
    return out


def build_or_levels(daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    work = daily.copy()
    work["year"] = work["date"].dt.year
    work["month"] = work["date"].dt.month
    for year, group in work.groupby("year"):
        or_bars = group[group["month"] <= 3]
        trade_bars = group[group["month"] >= 4]
        if or_bars.empty or trade_bars.empty:
            continue
        rows.append(
            {
                "year": int(year),
                "or_start": or_bars["date"].min(),
                "or_end": or_bars["date"].max(),
                "trade_start": trade_bars["date"].min(),
                "trade_end": trade_bars["date"].max(),
                "or_high": float(or_bars["high"].max()),
                "or_low": float(or_bars["low"].min()),
                "or_range": float(or_bars["high"].max() - or_bars["low"].min()),
                "or_days": int(len(or_bars)),
                "trade_days": int(len(trade_bars)),
            }
        )
    return pd.DataFrame(rows)


def simulate_orb_variant(daily: pd.DataFrame, levels: pd.DataFrame, variant: str, capital: float) -> tuple[pd.DataFrame, list[Trade]]:
    cash = capital
    shares = 0.0
    entry_price: Optional[float] = None
    entry_date: Optional[pd.Timestamp] = None
    entry_equity = 0.0
    setup_date: Optional[pd.Timestamp] = None
    mae_pct = 0.0
    mfe_pct = 0.0
    pending_entry = False
    pending_exit = False
    pending_limit = False
    rows = []
    trades: list[Trade] = []

    by_year = {int(row["year"]): row for _, row in levels.iterrows()}
    prev_close_by_year: dict[int, float] = {}

    for _, bar in daily.iterrows():
        date = pd.Timestamp(bar["date"])
        year = int(date.year)
        month = int(date.month)
        open_px = float(bar["open"])
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        level = by_year.get(year)

        in_position = shares > 0
        if pending_exit and in_position:
            cash, trade = exit_position(
                variant,
                year,
                setup_date,
                entry_date,
                entry_price,
                entry_equity,
                shares,
                date,
                open_px,
                "range_close_next_open",
                mae_pct,
                mfe_pct,
            )
            trades.append(trade)
            shares = 0.0
            entry_price = None
            entry_date = None
            setup_date = None
            mae_pct = 0.0
            mfe_pct = 0.0
            pending_exit = False
            pending_limit = False

        if pending_entry and shares == 0:
            shares, entry_price, entry_date, entry_equity = enter_position(cash, date, open_px)
            cash = 0.0
            pending_entry = False

        if level is not None and month >= 4 and shares == 0:
            or_high = float(level["or_high"])
            if variant == "stop_breakout_range_close" and high >= or_high:
                fill = max(or_high, open_px)
                shares, entry_price, entry_date, entry_equity = enter_position(cash, date, fill)
                cash = 0.0
                setup_date = date
            elif variant == "limit_retest_after_close" and pending_limit and low <= or_high:
                fill = open_px if open_px <= or_high else or_high
                shares, entry_price, entry_date, entry_equity = enter_position(cash, date, fill)
                cash = 0.0
                pending_limit = False

        if shares > 0 and entry_price is not None:
            mae_pct = min(mae_pct, low / entry_price - 1.0)
            mfe_pct = max(mfe_pct, high / entry_price - 1.0)

        equity = shares * close if shares > 0 else cash
        rows.append({"date": date, "variant": variant, "equity": equity, "exposed": 1.0 if shares > 0 else 0.0})

        if level is not None and month >= 4:
            or_high = float(level["or_high"])
            prev_close = prev_close_by_year.get(year)
            fresh_long_close = close > or_high and (prev_close is None or prev_close <= or_high)
            if shares > 0 and close <= or_high:
                pending_exit = True
            elif shares == 0 and variant == "close_breakout_next_open" and fresh_long_close:
                pending_entry = True
                setup_date = date
            elif shares == 0 and variant == "limit_retest_after_close" and fresh_long_close:
                pending_limit = True
                setup_date = date
            prev_close_by_year[year] = close

        is_year_last_row = is_last_row_of_year(daily, date)
        if is_year_last_row and shares > 0 and entry_price is not None and entry_date is not None:
            cash, trade = exit_position(
                variant,
                year,
                setup_date,
                entry_date,
                entry_price,
                entry_equity,
                shares,
                date,
                close,
                "year_end_close",
                mae_pct,
                mfe_pct,
            )
            trades.append(trade)
            rows[-1]["equity"] = cash
            shares = 0.0
            entry_price = None
            entry_date = None
            setup_date = None
            mae_pct = 0.0
            mfe_pct = 0.0
            pending_entry = False
            pending_exit = False
            pending_limit = False

    return pd.DataFrame(rows), trades


def simulate_psq_inverse_breakdown(
    daily: pd.DataFrame,
    levels: pd.DataFrame,
    inverse_daily: pd.DataFrame,
    capital: float,
) -> tuple[pd.DataFrame, list[Trade]]:
    return simulate_close_confirmed_dual_orb(
        daily=daily,
        levels=levels,
        inverse_daily=inverse_daily,
        capital=capital,
        variant="PSQ inverse close-breakdown next-open",
        allow_long=False,
        allow_inverse=True,
    )


def simulate_close_confirmed_dual_orb(
    daily: pd.DataFrame,
    levels: pd.DataFrame,
    inverse_daily: pd.DataFrame,
    capital: float,
    variant: str = "QQQ/PSQ dual close-confirmed ORB",
    allow_long: bool = True,
    allow_inverse: bool = True,
) -> tuple[pd.DataFrame, list[Trade]]:
    work = daily.merge(
        inverse_daily[["date", "open", "high", "low", "close"]].rename(
            columns={"open": "inverse_open", "high": "inverse_high", "low": "inverse_low", "close": "inverse_close"}
        ),
        on="date",
        how="left",
    ).sort_values("date")
    cash = capital
    shares = 0.0
    position_symbol: Optional[str] = None
    entry_price: Optional[float] = None
    entry_date: Optional[pd.Timestamp] = None
    entry_equity = 0.0
    setup_date: Optional[pd.Timestamp] = None
    mae_pct = 0.0
    mfe_pct = 0.0
    pending_entry_symbol: Optional[str] = None
    pending_exit = False
    rows = []
    trades: list[Trade] = []

    by_year = {int(row["year"]): row for _, row in levels.iterrows()}
    prev_close_by_year: dict[int, float] = {}

    for _, bar in work.iterrows():
        date = pd.Timestamp(bar["date"])
        year = int(date.year)
        month = int(date.month)
        qqq_open = float(bar["open"])
        qqq_high = float(bar["high"])
        qqq_low = float(bar["low"])
        qqq_close = float(bar["close"])
        inverse_open = float(bar["inverse_open"]) if not pd.isna(bar["inverse_open"]) else np.nan
        inverse_high = float(bar["inverse_high"]) if not pd.isna(bar["inverse_high"]) else np.nan
        inverse_low = float(bar["inverse_low"]) if not pd.isna(bar["inverse_low"]) else np.nan
        inverse_close = float(bar["inverse_close"]) if not pd.isna(bar["inverse_close"]) else np.nan
        level = by_year.get(year)

        if pending_exit and shares > 0 and position_symbol is not None:
            exit_px = qqq_open if position_symbol == "QQQ" else inverse_open
            if not pd.isna(exit_px):
                cash, trade = exit_position(
                    variant,
                    year,
                    setup_date,
                    entry_date,
                    entry_price,
                    entry_equity,
                    shares,
                    date,
                    exit_px,
                    "range_reclaim_next_open",
                    mae_pct,
                    mfe_pct,
                )
                trades.append(trade)
                shares = 0.0
                position_symbol = None
                entry_price = None
                entry_date = None
                setup_date = None
                mae_pct = 0.0
                mfe_pct = 0.0
                pending_exit = False

        if pending_entry_symbol is not None and shares == 0:
            entry_px = qqq_open if pending_entry_symbol == "QQQ" else inverse_open
            if not pd.isna(entry_px):
                shares, entry_price, entry_date, entry_equity = enter_position(cash, date, entry_px)
                cash = 0.0
                position_symbol = pending_entry_symbol
                pending_entry_symbol = None

        if shares > 0 and entry_price is not None and position_symbol is not None:
            if position_symbol == "QQQ":
                mae_pct = min(mae_pct, qqq_low / entry_price - 1.0)
                mfe_pct = max(mfe_pct, qqq_high / entry_price - 1.0)
                mark_close = qqq_close
            else:
                mark_close = inverse_close if not pd.isna(inverse_close) else entry_price
                mark_low = inverse_low if not pd.isna(inverse_low) else mark_close
                mark_high = inverse_high if not pd.isna(inverse_high) else mark_close
                mae_pct = min(mae_pct, mark_low / entry_price - 1.0)
                mfe_pct = max(mfe_pct, mark_high / entry_price - 1.0)
            equity = shares * mark_close
            exposed = 1.0
        else:
            equity = cash
            exposed = 0.0
        rows.append({"date": date, "variant": variant, "equity": equity, "exposed": exposed})

        if level is not None and month >= 4:
            or_high = float(level["or_high"])
            or_low = float(level["or_low"])
            prev_close = prev_close_by_year.get(year)
            fresh_long_close = qqq_close > or_high and (prev_close is None or prev_close <= or_high)
            fresh_short_close = qqq_close < or_low and (prev_close is None or prev_close >= or_low)
            if shares > 0 and position_symbol == "QQQ" and qqq_close <= or_high:
                pending_exit = True
            elif shares > 0 and position_symbol == "PSQ" and qqq_close >= or_low:
                pending_exit = True
            elif shares == 0 and pending_entry_symbol is None:
                if allow_long and fresh_long_close:
                    pending_entry_symbol = "QQQ"
                    setup_date = date
                elif allow_inverse and fresh_short_close and not pd.isna(inverse_close):
                    pending_entry_symbol = "PSQ"
                    setup_date = date
            prev_close_by_year[year] = qqq_close

        is_year_last_row = is_last_row_of_year(daily, date)
        if is_year_last_row and shares > 0 and position_symbol is not None and entry_price is not None and entry_date is not None:
            exit_px = qqq_close if position_symbol == "QQQ" else inverse_close
            if pd.isna(exit_px):
                exit_px = entry_price
            cash, trade = exit_position(
                variant,
                year,
                setup_date,
                entry_date,
                entry_price,
                entry_equity,
                shares,
                date,
                exit_px,
                "year_end_close",
                mae_pct,
                mfe_pct,
            )
            trades.append(trade)
            rows[-1]["equity"] = cash
            rows[-1]["exposed"] = 0.0
            shares = 0.0
            position_symbol = None
            entry_price = None
            entry_date = None
            setup_date = None
            mae_pct = 0.0
            mfe_pct = 0.0
            pending_entry_symbol = None
            pending_exit = False

    return pd.DataFrame(rows), trades


def is_last_row_of_year(daily: pd.DataFrame, date: pd.Timestamp) -> bool:
    year_dates = daily[daily["date"].dt.year == date.year]["date"]
    return bool(not year_dates.empty and pd.Timestamp(year_dates.max()) == date)


def enter_position(cash: float, date: pd.Timestamp, price: float) -> tuple[float, float, pd.Timestamp, float]:
    if price <= 0:
        raise ValueError("Entry price must be positive")
    shares = cash / price
    return shares, price, date, cash


def exit_position(
    variant: str,
    year: int,
    setup_date: Optional[pd.Timestamp],
    entry_date: Optional[pd.Timestamp],
    entry_price: Optional[float],
    entry_equity: float,
    shares: float,
    exit_date: pd.Timestamp,
    exit_price: float,
    reason: str,
    mae_pct: float,
    mfe_pct: float,
) -> tuple[float, Trade]:
    if entry_date is None or entry_price is None:
        raise ValueError("Cannot exit without an entry")
    exit_equity = shares * exit_price
    return (
        exit_equity,
        Trade(
            variant=variant,
            year=year,
            setup_date=setup_date,
            entry_date=entry_date,
            entry_price=entry_price,
            exit_date=exit_date,
            exit_price=exit_price,
            exit_reason=reason,
            entry_equity=entry_equity,
            exit_equity=exit_equity,
            mae_pct=mae_pct,
            mfe_pct=mfe_pct,
        ),
    )


def summarize_equity(equity: pd.DataFrame, capital: float) -> pd.DataFrame:
    rows = []
    for variant, group in equity.groupby("variant"):
        group = group.sort_values("date")
        series = pd.to_numeric(group["equity"], errors="coerce")
        net = float(series.iloc[-1] - capital)
        dd = max_drawdown(series)
        dd_pct = max_drawdown_pct(series)
        rows.append(
            {
                "variant": variant,
                "start_capital": capital,
                "end_capital": float(series.iloc[-1]),
                "net": net,
                "return_pct": net / capital * 100.0,
                "cagr_pct": cagr(series, group["date"]) * 100.0,
                "max_dd": dd,
                "max_dd_pct": dd_pct * 100.0,
                "net_over_dd": net / abs(dd) if dd < 0 else math.inf,
                "exposure_pct": 100.0 * float(pd.to_numeric(group["exposed"], errors="coerce").mean()),
            }
        )
    return pd.DataFrame(rows).sort_values("net_over_dd", ascending=False)


def trades_to_frame(trades: Iterable[Trade]) -> pd.DataFrame:
    rows = []
    for trade in trades:
        rows.append(
            {
                "variant": trade.variant,
                "year": trade.year,
                "setup_date": trade.setup_date.date().isoformat() if trade.setup_date is not None else "",
                "entry_date": trade.entry_date.date().isoformat(),
                "entry_price": trade.entry_price,
                "exit_date": trade.exit_date.date().isoformat(),
                "exit_price": trade.exit_price,
                "exit_reason": trade.exit_reason,
                "entry_equity": trade.entry_equity,
                "exit_equity": trade.exit_equity,
                "net": trade.net,
                "return_pct": trade.return_pct * 100.0,
                "mae_pct": trade.mae_pct * 100.0,
                "mfe_pct": trade.mfe_pct * 100.0,
                "days_held": trade.days_held,
                "result": "Win" if trade.net > 0 else "Loss" if trade.net < 0 else "Scratch",
            }
        )
    return pd.DataFrame(rows)


def summarize_trades(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    rows = []
    for variant, group in trades.groupby("variant"):
        wins = group[group["net"] > 0]
        losses = group[group["net"] < 0]
        gross_win = float(wins["net"].sum())
        gross_loss = float(losses["net"].sum())
        rows.append(
            {
                "variant": variant,
                "trades": int(len(group)),
                "wins": int(len(wins)),
                "losses": int(len(losses)),
                "win_rate_pct": 100.0 * len(wins) / len(group) if len(group) else math.nan,
                "profit_factor": gross_win / abs(gross_loss) if gross_loss < 0 else math.inf,
                "avg_trade_return_pct": float(group["return_pct"].mean()),
                "median_trade_return_pct": float(group["return_pct"].median()),
                "avg_days_held": float(group["days_held"].mean()),
                "worst_trade_pct": float(group["return_pct"].min()),
                "best_trade_pct": float(group["return_pct"].max()),
            }
        )
    return pd.DataFrame(rows).sort_values("profit_factor", ascending=False)


def build_yearly_summary(equity: pd.DataFrame) -> pd.DataFrame:
    rows = []
    work = equity.copy()
    work["year"] = work["date"].dt.year
    for (variant, year), group in work.groupby(["variant", "year"]):
        group = group.sort_values("date")
        start = float(group.iloc[0]["equity"])
        end = float(group.iloc[-1]["equity"])
        rows.append(
            {
                "variant": variant,
                "year": int(year),
                "start_equity": start,
                "end_equity": end,
                "net": end - start,
                "return_pct": (end / start - 1.0) * 100.0 if start else math.nan,
                "max_dd": max_drawdown(group["equity"]),
                "exposure_pct": 100.0 * float(group["exposed"].mean()),
            }
        )
    return pd.DataFrame(rows).sort_values(["year", "variant"])


def plot_candles(ax: plt.Axes, df: pd.DataFrame, width_days: float = 0.7) -> None:
    x = mdates.date2num(pd.to_datetime(df["date"]).dt.to_pydatetime())
    colors = np.where(df["close"] >= df["open"], "#168a5a", "#c43d3d")
    ax.vlines(x, df["low"], df["high"], color=colors, linewidth=0.85, alpha=0.9)
    for xi, o, c, color in zip(x, df["open"], df["close"], colors):
        bottom = min(float(o), float(c))
        height = max(abs(float(c) - float(o)), 0.01)
        ax.add_patch(
            plt.Rectangle((xi - width_days / 2.0, bottom), width_days, height, facecolor=color, edgecolor=color, linewidth=0.35, alpha=0.82)
        )


def plot_equity(equity: pd.DataFrame, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(16, 8))
    colors = {
        "QQQ buy-and-hold": "#111827",
        "QQQ monthly DCA cash-funded": "#6b7280",
        "stop_breakout_range_close": "#0f766e",
        "50/50 stop_breakout + monthly DCA": "#0891b2",
        "hybrid_stop_breakout_plus_monthly_dca": "#b45309",
        "PSQ inverse close-breakdown next-open": "#dc2626",
        "QQQ/PSQ dual close-confirmed ORB": "#9333ea",
        "close_breakout_next_open": "#2563eb",
        "limit_retest_after_close": "#7c3aed",
    }
    for variant, group in equity.groupby("variant"):
        group = group.sort_values("date")
        ax.plot(group["date"], group["equity"], label=variant, linewidth=1.25, color=colors.get(variant))
    ax.set_title("QQQ yearly ORB variants vs passive benchmarks")
    ax.set_ylabel("Equity ($)")
    ax.grid(True, color="#e6e6e6", linewidth=0.55, alpha=0.8)
    ax.legend(loc="upper left", fontsize=8)
    ax.xaxis.set_major_locator(mdates.YearLocator(base=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)


def plot_year_chart(year: int, daily: pd.DataFrame, level: pd.Series, trades: pd.DataFrame, out: Path) -> None:
    group = daily[daily["date"].dt.year == year].copy()
    if group.empty:
        return
    fig, ax = plt.subplots(figsize=(16, 7))
    plot_candles(ax, group, width_days=0.7)
    ax.axhline(float(level["or_high"]), color="#0f766e", linewidth=1.4, label="Jan-Mar OR high")
    ax.axhline(float(level["or_low"]), color="#c2410c", linewidth=1.4, label="Jan-Mar OR low")
    ax.axvspan(pd.Timestamp(level["or_start"]), pd.Timestamp(level["or_end"]), color="#e5e7eb", alpha=0.38, label="OR window")
    markers = {
        "stop_breakout_range_close": ("^", "#0f766e"),
        "close_breakout_next_open": ("o", "#2563eb"),
        "limit_retest_after_close": ("D", "#7c3aed"),
    }
    year_trades = trades[trades["year"].eq(year)] if not trades.empty else trades
    for variant, marker in markers.items():
        subset = year_trades[year_trades["variant"].eq(variant)] if not year_trades.empty else pd.DataFrame()
        if subset.empty:
            continue
        entry_dates = pd.to_datetime(subset["entry_date"])
        exit_dates = pd.to_datetime(subset["exit_date"])
        ax.scatter(entry_dates, subset["entry_price"], marker=marker[0], color=marker[1], s=55, label="%s entry" % variant, zorder=8)
        ax.scatter(exit_dates, subset["exit_price"], marker="x", color=marker[1], s=45, label="%s exit" % variant, zorder=8)
    ax.set_title("QQQ yearly ORB - %d" % year)
    ax.set_ylabel("Adjusted price")
    ax.grid(True, color="#e6e6e6", linewidth=0.55, alpha=0.8)
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    for label in ax.get_xticklabels():
        label.set_rotation(60)
        label.set_fontsize(8)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=135, bbox_inches="tight")
    plt.close(fig)


def write_report(
    out_root: Path,
    daily: pd.DataFrame,
    inverse_daily: pd.DataFrame,
    levels: pd.DataFrame,
    equity_summary: pd.DataFrame,
    trade_summary: pd.DataFrame,
    yearly_summary: pd.DataFrame,
    capital: float,
) -> None:
    lines = [
        "# QQQ Yearly ORB Study",
        "",
        "Data: Yahoo daily QQQ adjusted OHLCV.",
        "Window: **%s through %s**. Starting capital: **%s**." % (
            daily["date"].min().date().isoformat(),
            daily["date"].max().date().isoformat(),
            money(capital),
        ),
        "",
        "Rules:",
        "",
        "- Jan-Mar defines the yearly opening range.",
        "- Apr-Dec is the trade window.",
        "- Core QQQ variants are long-only; inverse rows buy PSQ as a 1x inverse ETF proxy. No leverage, no fees, no cash interest.",
        "- `stop_breakout_range_close`: resting buy stop at the OR high from Apr 1; exit next open after a daily close back below/at the OR high, or year-end close.",
        "- `close_breakout_next_open`: wait for a fresh daily close above the OR high, enter next open; same range-close/year-end exit.",
        "- `limit_retest_after_close`: after a fresh daily close above the OR high, rest a buy limit at the OR high; same range-close/year-end exit.",
        "- `50/50 stop_breakout + monthly DCA`: half the account follows `stop_breakout_range_close`; half follows cash-funded monthly DCA.",
        "- `hybrid_stop_breakout_plus_monthly_dca`: permanent monthly DCA core plus a tactical sweep of not-yet-DCA cash during `stop_breakout_range_close` risk-on windows; range-close only liquidates the tactical sleeve.",
        "- `PSQ inverse close-breakdown next-open`: buy PSQ at the next open after QQQ closes below the yearly OR low; exit next open after QQQ closes back above/at the OR low, or year-end close.",
        "- `QQQ/PSQ dual close-confirmed ORB`: buy QQQ after a close above the OR high, or PSQ after a close below the OR low; one side at a time, next-open fills only.",
        "",
        "Exposure is average invested market value divided by account equity, so monthly DCA reflects gradual capital deployment instead of a simple in/out flag.",
        "PSQ inverse rows can only trade after local PSQ data begins: **%s**." % inverse_daily["date"].min().date().isoformat(),
        "",
        "## Equity Ranking",
        "",
        "| Rank | Variant | End Capital | Net | Return | CAGR | Max DD | Max DD % | Net/DD | Exposure |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, (_, row) in enumerate(equity_summary.iterrows(), start=1):
        lines.append(
            "| %d | %s | %s | %s | %.1f%% | %.2f%% | %s | %.2f%% | %.2f | %.1f%% |"
            % (
                rank,
                row["variant"],
                money(float(row["end_capital"])),
                money(float(row["net"])),
                float(row["return_pct"]),
                float(row["cagr_pct"]),
                money(float(row["max_dd"])),
                float(row["max_dd_pct"]),
                float(row["net_over_dd"]),
                float(row["exposure_pct"]),
            )
        )
    lines.extend(
        [
            "",
            "## Trade Stats",
            "",
            "| Variant | Trades | Win Rate | PF | Avg Return | Median Return | Avg Days | Worst | Best |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    if trade_summary.empty:
        lines.append("| No trades | 0 |  |  |  |  |  |  |  |")
    else:
        for _, row in trade_summary.iterrows():
            lines.append(
                "| %s | %d | %.1f%% | %.2f | %.2f%% | %.2f%% | %.1f | %.2f%% | %.2f%% |"
                % (
                    row["variant"],
                    int(row["trades"]),
                    float(row["win_rate_pct"]),
                    float(row["profit_factor"]),
                    float(row["avg_trade_return_pct"]),
                    float(row["median_trade_return_pct"]),
                    float(row["avg_days_held"]),
                    float(row["worst_trade_pct"]),
                    float(row["best_trade_pct"]),
                )
            )

    latest_year = int(levels["year"].max()) if not levels.empty else int(daily["date"].dt.year.max())
    lines.extend(
        [
            "",
            "## Charts",
            "",
            "- [Equity comparison](charts/equity_comparison.png)",
            "- [Latest yearly chart](charts/yearly/%d.png)" % latest_year,
            "",
            "## Yearly OR Levels",
            "",
            "| Year | OR High | OR Low | OR Range | OR Days | Trade Days | Chart |",
            "|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for _, row in levels.iterrows():
        year = int(row["year"])
        rel = "charts/yearly/%d.png" % year
        lines.append(
            "| %d | %.2f | %.2f | %.2f | %d | %d | [%s](%s) |"
            % (year, row["or_high"], row["or_low"], row["or_range"], int(row["or_days"]), int(row["trade_days"]), rel, rel)
        )

    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `QQQ_daily_yearly_orb.csv`",
            "- `PSQ_daily_yearly_orb.csv`",
            "- `or_levels.csv`",
            "- `trades.csv`",
            "- `equity_curves.csv`",
            "- `equity_summary.csv`",
            "- `trade_summary.csv`",
            "- `yearly_summary.csv`",
        ]
    )
    (out_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out_root / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build QQQ yearly ORB study.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=default_completed_end())
    parser.add_argument("--capital", type=float, default=10_000.0)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output-root", type=Path, default=ROOT / "nq" / "case_studies" / "qqq_yearly_orb_study")
    args = parser.parse_args()

    out_root = args.output_root
    out_root.mkdir(parents=True, exist_ok=True)
    daily = load_qqq_daily(args.start, args.end, ROOT / "data" / "benchmarks", refresh=args.refresh)
    daily = daily.sort_values("date").reset_index(drop=True)
    inverse_daily = load_adjusted_daily("PSQ", args.start, args.end, ROOT / "data" / "benchmarks", refresh=args.refresh)
    inverse_daily = inverse_daily.sort_values("date").reset_index(drop=True)
    levels = build_or_levels(daily)

    buy_hold = buy_hold_equity(daily, args.capital)
    monthly_dca = monthly_dca_equity(daily, args.capital)
    hybrid = hybrid_stop_breakout_plus_monthly_dca(daily, levels, args.capital)
    equity_parts = [buy_hold, monthly_dca, hybrid]
    all_trades: list[Trade] = []
    stop_breakout_equity: Optional[pd.DataFrame] = None
    for variant in ["stop_breakout_range_close", "close_breakout_next_open", "limit_retest_after_close"]:
        equity, trades = simulate_orb_variant(daily, levels, variant, args.capital)
        equity_parts.append(equity)
        all_trades.extend(trades)
        if variant == "stop_breakout_range_close":
            stop_breakout_equity = equity

    if stop_breakout_equity is not None:
        equity_parts.append(blend_equity_curves(stop_breakout_equity, monthly_dca, "50/50 stop_breakout + monthly DCA"))

    inverse_equity, inverse_trades = simulate_psq_inverse_breakdown(daily, levels, inverse_daily, args.capital)
    equity_parts.append(inverse_equity)
    all_trades.extend(inverse_trades)
    dual_equity, dual_trades = simulate_close_confirmed_dual_orb(daily, levels, inverse_daily, args.capital)
    equity_parts.append(dual_equity)
    all_trades.extend(dual_trades)

    equity_curves = pd.concat(equity_parts, ignore_index=True)
    trades = trades_to_frame(all_trades)
    equity_summary = summarize_equity(equity_curves, args.capital)
    trade_summary = summarize_trades(trades)
    yearly_summary = build_yearly_summary(equity_curves)

    daily.to_csv(out_root / "QQQ_daily_yearly_orb.csv", index=False)
    inverse_daily.to_csv(out_root / "PSQ_daily_yearly_orb.csv", index=False)
    levels.to_csv(out_root / "or_levels.csv", index=False)
    trades.to_csv(out_root / "trades.csv", index=False)
    equity_curves.to_csv(out_root / "equity_curves.csv", index=False)
    equity_summary.to_csv(out_root / "equity_summary.csv", index=False)
    trade_summary.to_csv(out_root / "trade_summary.csv", index=False)
    yearly_summary.to_csv(out_root / "yearly_summary.csv", index=False)

    plot_equity(equity_curves, out_root / "charts" / "equity_comparison.png")
    for _, level in levels.iterrows():
        year = int(level["year"])
        plot_year_chart(year, daily, level, trades, out_root / "charts" / "yearly" / ("%d.png" % year))

    write_report(out_root, daily, inverse_daily, levels, equity_summary, trade_summary, yearly_summary, args.capital)
    print("Wrote %s" % (out_root / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
