#!/usr/bin/env python3
"""GOOGL/QQQ first-month + LHLL static DCA with weekly RSI50 cash regime.

Primary system:
- $1,000/month cashflow.
- Buy on the combined 2-month-low first-touch-per-month + monthly LHLL signals.
- Use the static full-window matched add size.
- If prior completed weekly RSI14 EMA14 is below 50, liquidate to cash at the
  next daily open and block new signal buys.
- Redeploy all saved/liquidated cash on the first monthly buy date where the
  prior completed weekly RSI14 EMA14 is back above/equal 50.

Secondary throttle:
- Keep existing shares.
- Spend 0.25x the normal target when weekly RSI14 EMA14 is >= 50.
- Spend 0.75x the normal target when weekly RSI14 EMA14 is < 50.

70/30 hybrid:
- Spend 70% as plain monthly DCA.
- Save 30% for equal-sized bulk buys on confirmed monthly LHLL signals whose
  causal buy-date weekly RSI14 EMA14 is below 50.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from googl_qqq_combined_2m_low_lhll_dca_study import (
    DEFAULT_LOOKBACK_MONTHS,
    DEFAULT_MONTHLY_AMOUNT,
    DEFAULT_PIVOT_BARS,
    DEFAULT_START,
    DEFAULT_TICKERS,
    combined_signals,
    simulate_combined_signal_dca,
    summarize_combined,
    ticker_slug,
)
from qqq_market_structure_dca_study import first_trading_day_each_month, money, monthly_dca_open, summarize_curve
from qqq_sliding_3m_low_limit_dca_study import max_drawdown
from qqq_smoothed_rsi_chart import compute_rsi
from yearly_orb_delivery_research_charts import calculate_daily_atr_trailing_stop
from qqq_yearly_orb_study import ROOT, default_completed_end, load_adjusted_daily


OUT_DIR = ROOT / "nq" / "case_studies" / "googl_qqq_weekly_rsi50_cash_regime_study"
TOUCH_MODE = "first_touch_per_month"
SIZING_MODE = "static_full_window"
HYBRID_STRATEGY = "monthly_dca70_lhll_rsi50_bulk30"


def aggregate_weekly(daily: pd.DataFrame) -> pd.DataFrame:
    work = daily.copy().sort_values("date").reset_index(drop=True)
    work["date"] = pd.to_datetime(work["date"])
    work["_week"] = work["date"].dt.to_period("W-FRI")
    return (
        work.groupby("_week", as_index=False)
        .agg(
            date=("date", "max"),
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .sort_values("date")
        .reset_index(drop=True)
    )


def add_weekly_rsi50_state(daily: pd.DataFrame, rsi_length: int, smooth: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = daily.copy().sort_values("date").reset_index(drop=True)
    base["date"] = pd.to_datetime(base["date"])
    weekly = compute_rsi(aggregate_weekly(base), rsi_length, smooth)
    weekly_state = weekly[["date", "rsi", "rsi_smooth"]].copy().sort_values("date")
    weekly_state = weekly_state.rename(
        columns={
            "rsi": "weekly_rsi14",
            "rsi_smooth": "weekly_rsi14_ema14",
        }
    )
    mapped = pd.merge_asof(
        base[["date"]].sort_values("date"),
        weekly_state,
        on="date",
        direction="backward",
        allow_exact_matches=False,
    )
    out = base.merge(mapped, on="date", how="left")
    out["rsi_state_available"] = pd.notna(out["weekly_rsi14_ema14"])
    out["risk_on"] = pd.to_numeric(out["weekly_rsi14_ema14"], errors="coerce").ge(50.0)
    out["risk_on"] = out["risk_on"].where(out["rsi_state_available"], True).astype(bool)
    return out, weekly_state


def add_daily_atr_supertrend_state(
    daily: pd.DataFrame,
    atr_length: int,
    atr_multiplier: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = daily.copy().sort_values("date").reset_index(drop=True)
    base["date"] = pd.to_datetime(base["date"])
    atr = calculate_daily_atr_trailing_stop(base[["date", "open", "high", "low", "close"]].copy(), atr_length, atr_multiplier)
    atr_state = atr[["date", "atr", "atr_stop", "atr_trend"]].copy()
    out = base.copy()
    out["daily_atr"] = atr_state["atr"]
    out["daily_atr_stop_raw"] = atr_state["atr_stop"]
    out["daily_atr_trend_raw"] = atr_state["atr_trend"]
    out["daily_atr_stop"] = out["daily_atr_stop_raw"].shift(1)
    out["daily_atr_trend"] = out["daily_atr_trend_raw"].shift(1)
    out["atr_state_available"] = out["daily_atr_trend"].notna()
    out["atr_risk_on"] = out["daily_atr_trend"].eq("up").where(out["atr_state_available"], True).astype(bool)
    return out, atr_state


def signal_lookup(signals: pd.DataFrame) -> dict[pd.Timestamp, list[pd.Series]]:
    by_date: dict[pd.Timestamp, list[pd.Series]] = {}
    if signals.empty:
        return by_date
    for _, signal in signals.sort_values(["date", "combined_signal_index"]).iterrows():
        by_date.setdefault(pd.Timestamp(signal["date"]), []).append(signal)
    return by_date


def monthly_lhll_rsi_lt50_signals(daily: pd.DataFrame, signals: pd.DataFrame) -> pd.DataFrame:
    if signals.empty:
        return signals.copy()
    work = signals[signals["signal_family"].eq("monthly_lhll")].copy()
    if work.empty:
        return work
    work["date"] = pd.to_datetime(work["date"])
    state = daily[["date", "weekly_rsi14_ema14", "risk_on"]].copy()
    state["date"] = pd.to_datetime(state["date"])
    work = work.merge(state, on="date", how="left")
    rsi = pd.to_numeric(work["weekly_rsi14_ema14"], errors="coerce")
    work = work[rsi.lt(50.0)].copy().sort_values(["date", "combined_signal_index"]).reset_index(drop=True)
    return work


def simulate_monthly_dca_cash_regime(daily: pd.DataFrame, monthly_amount: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    invest_dates = first_trading_day_each_month(daily)
    cash = 0.0
    shares = 0.0
    contributed = 0.0
    pending_redeploy = False
    prev_risk_on = True
    rows = []
    events = []
    for _, bar in daily.sort_values("date").iterrows():
        date = pd.Timestamp(bar["date"])
        open_price = float(bar["open"])
        close_price = float(bar["close"])
        risk_on = bool(bar["risk_on"])
        contribution = 0.0
        buy_amount = 0.0
        sell_amount = 0.0

        if not risk_on and shares > 0:
            sell_amount = shares * open_price
            cash += sell_amount
            shares = 0.0
            pending_redeploy = True
            events.append(event_row(date, "monthly_dca_rsi50_cash", "risk_off_liquidation", sell_amount, open_price, cash, bar))

        if date in invest_dates:
            contribution = monthly_amount
            contributed += contribution
            cash += contribution
            if risk_on:
                buy_amount = cash
                shares += buy_amount / open_price
                cash = 0.0
                event_type = "monthly_reentry_buy" if pending_redeploy or not prev_risk_on else "monthly_buy"
                pending_redeploy = False
                events.append(event_row(date, "monthly_dca_rsi50_cash", event_type, buy_amount, open_price, cash, bar))
            else:
                events.append(event_row(date, "monthly_dca_rsi50_cash", "monthly_blocked_risk_off", 0.0, math.nan, cash, bar))

        invested = shares * close_price
        equity = cash + invested
        rows.append(
            curve_row(
                date,
                "monthly_dca_rsi50_cash",
                contribution,
                buy_amount,
                0,
                0,
                sell_amount,
                cash,
                shares,
                invested,
                equity,
                contributed,
                bar,
            )
        )
        prev_risk_on = risk_on
    return pd.DataFrame(rows), pd.DataFrame(events)


def simulate_monthly_dca_weighted_spend(
    daily: pd.DataFrame,
    monthly_amount: float,
    above_50_mult: float,
    below_50_mult: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    invest_dates = first_trading_day_each_month(daily)
    cash = 0.0
    shares = 0.0
    contributed = 0.0
    pending_reentry = False
    rows = []
    events = []
    for _, bar in daily.sort_values("date").iterrows():
        date = pd.Timestamp(bar["date"])
        open_price = float(bar["open"])
        close_price = float(bar["close"])
        risk_on = bool(bar["risk_on"])
        contribution = 0.0
        buy_amount = 0.0
        if date in invest_dates:
            contribution = monthly_amount
            contributed += contribution
            cash += contribution
            target_add = monthly_amount * (above_50_mult if risk_on else below_50_mult)
            buy_amount = min(cash, target_add)
            if buy_amount > 0:
                shares += buy_amount / open_price
                cash -= buy_amount
            events.append(
                event_row(
                    date,
                    "monthly_dca_rsi50_weighted_spend",
                    "monthly_buy_above50_weighted" if risk_on else "monthly_buy_below50_weighted",
                    buy_amount,
                    open_price if buy_amount else math.nan,
                    cash,
                    bar,
                    target_add,
                )
            )

        invested = shares * close_price
        equity = cash + invested
        rows.append(
            curve_row(
                date,
                "monthly_dca_rsi50_weighted_spend",
                contribution,
                buy_amount,
                0,
                0,
                0.0,
                cash,
                shares,
                invested,
                equity,
                contributed,
                bar,
            )
        )
    return pd.DataFrame(rows), pd.DataFrame(events)


def simulate_monthly_dca_lhll_rsi50_bulk_split(
    daily: pd.DataFrame,
    signals: pd.DataFrame,
    monthly_amount: float,
    dca_frac: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, float]:
    invest_dates = first_trading_day_each_month(daily)
    qualified = monthly_lhll_rsi_lt50_signals(daily, signals)
    by_date = signal_lookup(qualified)
    dca_amount = monthly_amount * dca_frac
    reserve_amount = monthly_amount - dca_amount
    total_reserve_budget = reserve_amount * len(invest_dates)
    target_add = total_reserve_budget / len(qualified) if len(qualified) else total_reserve_budget
    cash = 0.0
    shares = 0.0
    contributed = 0.0
    rows = []
    events = []

    for _, bar in daily.sort_values("date").iterrows():
        date = pd.Timestamp(bar["date"])
        open_price = float(bar["open"])
        close_price = float(bar["close"])
        contribution = 0.0
        day_buy = 0.0
        day_signals = 0

        if date in invest_dates:
            contribution = monthly_amount
            contributed += contribution
            cash += reserve_amount
            if dca_amount > 0:
                shares += dca_amount / open_price
                day_buy += dca_amount
                events.append(event_row(date, HYBRID_STRATEGY, "monthly_70pct_dca_buy", dca_amount, open_price, cash, bar, dca_amount))

        for signal in by_date.get(date, []):
            day_signals += 1
            buy_amount = min(cash, target_add)
            if buy_amount > 0:
                shares += buy_amount / float(signal["buy_price"])
                cash -= buy_amount
                day_buy += buy_amount
            events.append(
                signal_event_row(
                    date,
                    HYBRID_STRATEGY,
                    "monthly_lhll_rsi_lt50_bulk_buy",
                    buy_amount,
                    float(signal["buy_price"]) if buy_amount else math.nan,
                    target_add,
                    cash,
                    bar,
                    signal,
                )
            )

        invested = shares * close_price
        equity = cash + invested
        rows.append(
            curve_row(
                date,
                HYBRID_STRATEGY,
                contribution,
                day_buy,
                day_signals,
                0,
                0.0,
                cash,
                shares,
                invested,
                equity,
                contributed,
                bar,
            )
        )

    return pd.DataFrame(rows), pd.DataFrame(events), qualified, target_add


def simulate_combined_cash_regime(
    daily: pd.DataFrame,
    signals: pd.DataFrame,
    monthly_amount: float,
    static_signal_rate: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    invest_dates = first_trading_day_each_month(daily)
    by_date = signal_lookup(signals)
    cash = 0.0
    shares = 0.0
    contributed = 0.0
    pending_redeploy = False
    prev_risk_on = True
    target_add = monthly_amount * 12.0 / max(static_signal_rate, 1.0)
    rows = []
    events = []
    for _, bar in daily.sort_values("date").iterrows():
        date = pd.Timestamp(bar["date"])
        open_price = float(bar["open"])
        close_price = float(bar["close"])
        risk_on = bool(bar["risk_on"])
        contribution = 0.0
        day_buy = 0.0
        day_sells = 0.0
        day_signals = 0
        day_blocked = 0

        if not risk_on and shares > 0:
            day_sells = shares * open_price
            cash += day_sells
            shares = 0.0
            pending_redeploy = True
            events.append(event_row(date, "combined_first_month_lhll_static_rsi50_cash", "risk_off_liquidation", day_sells, open_price, cash, bar))

        if date in invest_dates:
            contribution = monthly_amount
            contributed += contribution
            cash += contribution
            if risk_on and (pending_redeploy or not prev_risk_on):
                buy_amount = cash
                shares += buy_amount / open_price
                cash = 0.0
                day_buy += buy_amount
                pending_redeploy = False
                events.append(event_row(date, "combined_first_month_lhll_static_rsi50_cash", "monthly_reentry_cash_sweep", buy_amount, open_price, cash, bar))

        for signal in by_date.get(date, []):
            day_signals += 1
            if not risk_on:
                day_blocked += 1
                events.append(
                    signal_event_row(
                        date,
                        "combined_first_month_lhll_static_rsi50_cash",
                        "signal_blocked_risk_off",
                        0.0,
                        math.nan,
                        target_add,
                        cash,
                        bar,
                        signal,
                    )
                )
                continue
            buy_amount = min(cash, target_add)
            if buy_amount > 0:
                shares += buy_amount / float(signal["buy_price"])
                cash -= buy_amount
                day_buy += buy_amount
            events.append(
                signal_event_row(
                    date,
                    "combined_first_month_lhll_static_rsi50_cash",
                    "signal_buy",
                    buy_amount,
                    float(signal["buy_price"]) if buy_amount else math.nan,
                    target_add,
                    cash,
                    bar,
                    signal,
                )
            )

        invested = shares * close_price
        equity = cash + invested
        rows.append(
            curve_row(
                date,
                "combined_first_month_lhll_static_rsi50_cash",
                contribution,
                day_buy,
                day_signals,
                day_blocked,
                day_sells,
                cash,
                shares,
                invested,
                equity,
                contributed,
                bar,
            )
        )
        prev_risk_on = risk_on
    return pd.DataFrame(rows), pd.DataFrame(events)


def simulate_combined_weighted_spend(
    daily: pd.DataFrame,
    signals: pd.DataFrame,
    monthly_amount: float,
    static_signal_rate: float,
    above_50_mult: float,
    below_50_mult: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    invest_dates = first_trading_day_each_month(daily)
    by_date = signal_lookup(signals)
    cash = 0.0
    shares = 0.0
    contributed = 0.0
    base_target = monthly_amount * 12.0 / max(static_signal_rate, 1.0)
    rows = []
    events = []
    for _, bar in daily.sort_values("date").iterrows():
        date = pd.Timestamp(bar["date"])
        close_price = float(bar["close"])
        risk_on = bool(bar["risk_on"])
        contribution = 0.0
        day_buy = 0.0
        day_signals = 0
        if date in invest_dates:
            contribution = monthly_amount
            contributed += contribution
            cash += contribution

        for signal in by_date.get(date, []):
            day_signals += 1
            target_add = base_target * (above_50_mult if risk_on else below_50_mult)
            buy_amount = min(cash, target_add)
            if buy_amount > 0:
                shares += buy_amount / float(signal["buy_price"])
                cash -= buy_amount
                day_buy += buy_amount
            events.append(
                signal_event_row(
                    date,
                    "combined_first_month_lhll_static_rsi50_weighted_spend",
                    "signal_buy_above50_weighted" if risk_on else "signal_buy_below50_weighted",
                    buy_amount,
                    float(signal["buy_price"]) if buy_amount else math.nan,
                    target_add,
                    cash,
                    bar,
                    signal,
                )
            )

        invested = shares * close_price
        equity = cash + invested
        rows.append(
            curve_row(
                date,
                "combined_first_month_lhll_static_rsi50_weighted_spend",
                contribution,
                day_buy,
                day_signals,
                0,
                0.0,
                cash,
                shares,
                invested,
                equity,
                contributed,
                bar,
            )
        )
    return pd.DataFrame(rows), pd.DataFrame(events)


def simulate_daily_atr_supertrend_matched_dca(
    daily: pd.DataFrame,
    monthly_amount: float,
    bullish_day_rate: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    invest_dates = first_trading_day_each_month(daily)
    target_add = monthly_amount * 12.0 / max(bullish_day_rate, 1.0)
    cash = 0.0
    shares = 0.0
    contributed = 0.0
    pending_reentry = False
    rows = []
    events = []
    for _, bar in daily.sort_values("date").iterrows():
        date = pd.Timestamp(bar["date"])
        open_price = float(bar["open"])
        close_price = float(bar["close"])
        atr_risk_on = bool(bar["atr_risk_on"])
        contribution = 0.0
        buy_amount = 0.0
        sell_amount = 0.0
        day_signal = 1 if atr_risk_on else 0

        if not atr_risk_on and shares > 0:
            sell_amount = shares * open_price
            cash += sell_amount
            shares = 0.0
            pending_reentry = True
            events.append(atr_event_row(date, "daily_atr_supertrend_matched_dca", "atr_bearish_liquidation", sell_amount, open_price, target_add, cash, bar))

        if date in invest_dates:
            contribution = monthly_amount
            contributed += contribution
            cash += contribution

        if atr_risk_on and cash > 0:
            buy_amount = cash if pending_reentry else min(cash, target_add)
            if buy_amount > 0:
                shares += buy_amount / open_price
                cash -= buy_amount
                events.append(
                    atr_event_row(
                        date,
                        "daily_atr_supertrend_matched_dca",
                        "atr_bullish_reentry_cash_sweep" if pending_reentry else "atr_bullish_matched_buy",
                        buy_amount,
                        open_price,
                        target_add,
                        cash,
                        bar,
                    )
                )
                pending_reentry = False

        invested = shares * close_price
        equity = cash + invested
        rows.append(
            curve_row(
                date,
                "daily_atr_supertrend_matched_dca",
                contribution,
                buy_amount,
                day_signal,
                0,
                sell_amount,
                cash,
                shares,
                invested,
                equity,
                contributed,
                bar,
            )
        )
    return pd.DataFrame(rows), pd.DataFrame(events)


def event_row(
    date: pd.Timestamp,
    strategy: str,
    event_type: str,
    amount: float,
    price: float,
    cash_after: float,
    bar: pd.Series,
    target_add: float = math.nan,
) -> dict:
    return {
        "date": date,
        "strategy": strategy,
        "event_type": event_type,
        "amount": amount,
        "price": price,
        "cash_after": cash_after,
        "target_add_amount": target_add,
        "risk_on": bool(bar["risk_on"]),
        "weekly_rsi14_ema14": float(bar["weekly_rsi14_ema14"]) if pd.notna(bar["weekly_rsi14_ema14"]) else math.nan,
    }


def atr_event_row(
    date: pd.Timestamp,
    strategy: str,
    event_type: str,
    amount: float,
    price: float,
    target_add: float,
    cash_after: float,
    bar: pd.Series,
) -> dict:
    row = event_row(date, strategy, event_type, amount, price, cash_after, bar, target_add)
    row.update(
        {
            "daily_atr": float(bar["daily_atr"]) if pd.notna(bar.get("daily_atr")) else math.nan,
            "daily_atr_stop": float(bar["daily_atr_stop"]) if pd.notna(bar.get("daily_atr_stop")) else math.nan,
            "daily_atr_trend": str(bar["daily_atr_trend"]) if pd.notna(bar.get("daily_atr_trend")) else "",
            "atr_risk_on": bool(bar["atr_risk_on"]),
        }
    )
    return row


def signal_event_row(
    date: pd.Timestamp,
    strategy: str,
    event_type: str,
    amount: float,
    price: float,
    target_add: float,
    cash_after: float,
    bar: pd.Series,
    signal: pd.Series,
) -> dict:
    row = event_row(date, strategy, event_type, amount, price, cash_after, bar)
    row.update(
        {
            "target_add_amount": target_add,
            "signal_family": signal["signal_family"],
            "signal_key": signal["signal_key"],
            "combined_signal_index": int(signal["combined_signal_index"]),
            "signal_date": pd.Timestamp(signal["signal_date"]),
        }
    )
    return row


def curve_row(
    date: pd.Timestamp,
    variant: str,
    contribution: float,
    buy_amount: float,
    signal_occurrences: int,
    blocked_signal_occurrences: int,
    sell_amount: float,
    cash: float,
    shares: float,
    invested: float,
    equity: float,
    contributed: float,
    bar: pd.Series,
) -> dict:
    return {
        "date": date,
        "variant": variant,
        "contribution": contribution,
        "buy_amount": buy_amount,
        "signal_occurrences": signal_occurrences,
        "blocked_signal_occurrences": blocked_signal_occurrences,
        "sell_amount": sell_amount,
        "cash": cash,
        "shares": shares,
        "invested_value": invested,
        "equity": equity,
        "total_contributed": contributed,
        "exposure_frac": invested / equity if equity else 0.0,
        "risk_on": bool(bar["risk_on"]),
        "weekly_rsi14_ema14": bar["weekly_rsi14_ema14"],
        "atr_risk_on": bool(bar["atr_risk_on"]) if "atr_risk_on" in bar else pd.NA,
        "daily_atr_trend": bar["daily_atr_trend"] if "daily_atr_trend" in bar else pd.NA,
        "daily_atr_stop": bar["daily_atr_stop"] if "daily_atr_stop" in bar else pd.NA,
    }


def summarize_strategy(
    ticker: str,
    strategy: str,
    curve: pd.DataFrame,
    monthly_summary: dict,
    signal_count: int,
    static_signal_rate: float,
    static_matched_add: float,
    events: pd.DataFrame,
) -> dict:
    equity = pd.to_numeric(curve["equity"], errors="coerce")
    total = float(curve.iloc[-1]["total_contributed"]) if not curve.empty else 0.0
    ending = float(equity.iloc[-1]) if not curve.empty else 0.0
    net = ending - total
    dd = max_drawdown(equity)
    event_type = events["event_type"].astype(str) if not events.empty and "event_type" in events else pd.Series(dtype=str)
    ending_cash = float(curve.iloc[-1]["cash"]) if not curve.empty else 0.0
    deployed_pct = (total - ending_cash) / total * 100.0 if total and not curve.empty else math.nan
    if total and ending_cash > total:
        deployed_pct = math.nan
    blocked_signals = (
        int(pd.to_numeric(curve["blocked_signal_occurrences"], errors="coerce").fillna(0.0).sum())
        if not curve.empty and "blocked_signal_occurrences" in curve
        else 0
    )
    is_combined = "combined" in strategy
    is_atr = "atr_supertrend" in strategy
    is_lhll_bulk = "lhll_rsi50_bulk" in strategy
    is_signal_strategy = is_combined or is_atr or is_lhll_bulk
    risk_col = "atr_risk_on" if is_atr and "atr_risk_on" in curve else "risk_on"
    return {
        "ticker": ticker,
        "strategy": strategy,
        "touch_mode": (
            TOUCH_MODE
            if is_combined
            else "daily_atr_supertrend_bullish_days"
            if is_atr
            else "monthly_lhll_weekly_rsi_lt50"
            if is_lhll_bulk
            else ""
        ),
        "sizing_mode": (
            SIZING_MODE
            if is_combined or is_atr
            else "70pct_monthly_dca_30pct_static_bulk"
            if is_lhll_bulk
            else ""
        ),
        "signal_count": signal_count if is_signal_strategy else 0,
        "signal_rate_per_year": static_signal_rate if is_signal_strategy else 0.0,
        "static_matched_add_amount": static_matched_add if is_signal_strategy else monthly_summary.get("avg_buy_amount", 0.0),
        "total_contributed": total,
        "ending_equity": ending,
        "net": net,
        "return_on_contributions_pct": net / total * 100.0 if total else math.nan,
        "max_dd": dd,
        "net_over_dd": net / abs(dd) if dd < 0 else math.inf,
        "buys": int(pd.to_numeric(curve["buy_amount"], errors="coerce").fillna(0.0).gt(0).sum()) if not curve.empty else 0,
        "sells": int(event_type.str.contains("liquidation").sum()) if not event_type.empty else 0,
        "blocked_signals": blocked_signals,
        "risk_off_days": int((~curve[risk_col].astype(bool)).sum()) if not curve.empty and risk_col in curve else 0,
        "ending_cash": ending_cash,
        "deployed_contributions_pct": deployed_pct,
        "avg_exposure_pct": float(pd.to_numeric(curve["exposure_frac"], errors="coerce").fillna(0.0).mean() * 100.0) if not curve.empty else math.nan,
        "basic_dca_ending_equity": float(monthly_summary["ending_equity"]),
        "ending_vs_basic_dca": ending - float(monthly_summary["ending_equity"]),
    }


def plot_google_vs_qqq(curves: pd.DataFrame, out: Path) -> None:
    subset = curves[curves["strategy"].eq("basic_dca_open")].copy()
    fig, ax = plt.subplots(figsize=(14, 7))
    colors = {"GOOGL": "#2563eb", "QQQ": "#111827"}
    for ticker, group in subset.groupby("ticker", sort=False):
        ax.plot(group["date"], group["equity"], linewidth=1.4, color=colors.get(ticker, None), label="%s $1k/month DCA" % ticker)
    ax.set_title("GOOGL vs QQQ equity: basic monthly DCA")
    ax.set_ylabel("Equity ($)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=8)
    ax.xaxis.set_major_locator(mdates.YearLocator(base=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_strategy_comparison(curves: pd.DataFrame, out: Path) -> None:
    tickers = sorted(curves["ticker"].unique())
    fig, axes = plt.subplots(len(tickers), 1, figsize=(14, 5.5 * len(tickers)), sharex=True)
    if len(tickers) == 1:
        axes = [axes]
    styles = {
        "basic_dca_open": ("#111827", "-", "$1k/month DCA"),
        "monthly_dca_rsi50_cash": ("#64748b", "--", "monthly DCA + weekly RSI50 cash"),
        "monthly_dca_rsi50_weighted_spend": ("#7c3aed", ":", "monthly DCA + RSI50 25/75"),
        HYBRID_STRATEGY: ("#16a34a", "-.", "70% DCA + 30% monthly LHLL RSI<50 bulk"),
        "daily_atr_supertrend_matched_dca": ("#0891b2", "-.", "daily ATR ST bullish-day matched DCA"),
        "combined_first_month_lhll_static": ("#0f766e", "-", "first/month + LHLL static"),
        "combined_first_month_lhll_static_rsi50_cash": ("#b45309", "--", "first/month + LHLL static + weekly RSI50 cash"),
        "combined_first_month_lhll_static_rsi50_weighted_spend": ("#dc2626", ":", "first/month + LHLL static + RSI50 25/75"),
    }
    for ax, ticker in zip(axes, tickers):
        sub = curves[curves["ticker"].eq(ticker)].copy()
        for strategy, (color, linestyle, label) in styles.items():
            group = sub[sub["strategy"].eq(strategy)]
            if group.empty:
                continue
            ax.plot(group["date"], group["equity"], color=color, linestyle=linestyle, linewidth=1.25, label=label)
        ax.set_title("%s equity comparison" % ticker)
        ax.set_ylabel("Equity ($)")
        ax.grid(True, alpha=0.25)
        ax.legend(loc="upper left", fontsize=8)
    axes[-1].xaxis.set_major_locator(mdates.YearLocator(base=2))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def summary_line(row: pd.Series) -> str:
    deployed = float(row["deployed_contributions_pct"])
    deployed_text = "-" if pd.isna(deployed) else "%.1f%%" % deployed
    return (
        "| %s | %s | %s | %s | %d | %s | %d | %d | %s | %s | %s | %.1f%% | %s | %s | %.2f |"
        % (
            row["ticker"],
            row["strategy"],
            row.get("touch_mode", "") or "-",
            row.get("sizing_mode", "") or "-",
            int(row["signal_count"]),
            money(float(row["static_matched_add_amount"])),
            int(row["buys"]),
            int(row["sells"]),
            money(float(row["ending_equity"])),
            money(float(row["ending_vs_basic_dca"])),
            money(float(row["max_dd"])),
            float(row["avg_exposure_pct"]),
            deployed_text,
            money(float(row["ending_cash"])),
            float(row["net_over_dd"]),
        )
    )


def write_report(
    out_dir: Path,
    summary: pd.DataFrame,
    common_start: str,
    common_end: str,
    monthly_amount: float,
    lookback_months: int,
    pivot_bars: int,
    rsi_length: int,
    smooth: int,
    above_50_mult: float,
    below_50_mult: float,
    atr_length: int,
    atr_multiplier: float,
    hybrid_dca_frac: float,
) -> None:
    lines = [
        "# GOOGL vs QQQ Weekly RSI50 Cash / Weighted-Spend Study",
        "",
        "Data: Yahoo adjusted daily OHLCV on the common GOOGL/QQQ window.",
        "",
        "Window: **%s through %s**." % (common_start, common_end),
        "",
        "Rules:",
        "",
        "- Basic benchmark: buy **%s/month** on the first trading-day open." % money(monthly_amount),
        "- Combined static benchmark: 2-month-low **first touch per month** plus confirmed monthly **low -> high -> lower low** with **%d/%d** monthly pivots." % (pivot_bars, pivot_bars),
        "- Combined add size is static full-window matched: `12 months of DCA budget / expected combined signals per year`.",
        "- Weekly RSI cash regime uses prior completed weekly RSI(%d) smoothed with EMA(%d), mapped causally with no same-bar access." % (rsi_length, smooth),
        "- If weekly RSI EMA is **below 50**, sell existing shares at the next daily open and keep monthly contributions/signals in cash.",
        "- Redeploy all cash at the first monthly buy date where the prior completed weekly RSI EMA is back **>= 50**.",
        "- Weighted-spend variant: keep existing shares, spend **%.0f%%** of the normal target when weekly RSI EMA is **>= 50**, and **%.0f%%** when it is **< 50**."
        % (above_50_mult * 100.0, below_50_mult * 100.0),
        "- 70/30 hybrid: spend **%.0f%%** as plain monthly DCA and reserve **%.0f%%** for equal-sized bulk buys on confirmed monthly LHLL signals where causal buy-date weekly RSI EMA is **< 50**."
        % (hybrid_dca_frac * 100.0, (1.0 - hybrid_dca_frac) * 100.0),
        "- The 70/30 hybrid is cashflow-real: early bulk signals can only spend reserve cash accumulated so far, and unused reserve after the final signal stays in cash.",
        "- ATR Supertrend DCA variant: monthly cash still arrives, but buys can occur on any day where the **prior completed daily ATR(%d) x %.1f Supertrend** is bullish. It liquidates at the next open after the prior completed state turns bearish, and its per-buy amount is matched to the full-window bullish-day rate."
        % (atr_length, atr_multiplier),
        "",
        "## Leaderboard",
        "",
        "| Ticker | Strategy | Touch | Sizing | Signals | Matched Add | Buys | Sells | Ending Equity | vs Basic DCA | Max DD | Avg Exposure | Deployed | Ending Cash | Net/DD |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    sort_order = {
        "basic_dca_open": 0,
        "monthly_dca_rsi50_cash": 1,
        "monthly_dca_rsi50_weighted_spend": 2,
        HYBRID_STRATEGY: 3,
        "daily_atr_supertrend_matched_dca": 4,
        "combined_first_month_lhll_static": 5,
        "combined_first_month_lhll_static_rsi50_cash": 6,
        "combined_first_month_lhll_static_rsi50_weighted_spend": 7,
    }
    ranked = summary.copy()
    ranked["_order"] = ranked["strategy"].map(sort_order).fillna(99)
    for _, row in ranked.sort_values(["ticker", "_order"]).iterrows():
        lines.append(summary_line(row))

    lines.extend(["", "## Read", ""])
    for ticker in sorted(summary["ticker"].unique()):
        t = summary[summary["ticker"].eq(ticker)].set_index("strategy")
        basic = t.loc["basic_dca_open"]
        combined = t.loc["combined_first_month_lhll_static"]
        cash = t.loc["combined_first_month_lhll_static_rsi50_cash"]
        monthly_cash = t.loc["monthly_dca_rsi50_cash"]
        weighted = t.loc["combined_first_month_lhll_static_rsi50_weighted_spend"]
        monthly_weighted = t.loc["monthly_dca_rsi50_weighted_spend"]
        atr_dca = t.loc["daily_atr_supertrend_matched_dca"]
        hybrid = t.loc[HYBRID_STRATEGY]
        lines.append(
            "- **%s:** basic DCA ends at **%s**. The 70/30 monthly DCA + monthly-LHLL-RSI<50 bulk row ends at **%s** (**%s** vs basic). Daily ATR Supertrend matched DCA ends at **%s** (**%s** vs basic). The first/month + LHLL static row is **%s** (**%s** vs basic). The weekly RSI50 cash regime ends at **%s** (**%s** vs basic, **%s** vs unfiltered combined). The %.0f/%.0f weighted combined row ends at **%s** (**%s** vs basic, **%s** vs unfiltered combined). Plain monthly DCA with %.0f/%.0f weighting ends at **%s** (**%s** vs basic)."
            % (
                ticker,
                money(float(basic["ending_equity"])),
                money(float(hybrid["ending_equity"])),
                money(float(hybrid["ending_vs_basic_dca"])),
                money(float(atr_dca["ending_equity"])),
                money(float(atr_dca["ending_vs_basic_dca"])),
                money(float(combined["ending_equity"])),
                money(float(combined["ending_vs_basic_dca"])),
                money(float(cash["ending_equity"])),
                money(float(cash["ending_vs_basic_dca"])),
                money(float(cash["ending_equity"] - combined["ending_equity"])),
                above_50_mult * 100.0,
                below_50_mult * 100.0,
                money(float(weighted["ending_equity"])),
                money(float(weighted["ending_vs_basic_dca"])),
                money(float(weighted["ending_equity"] - combined["ending_equity"])),
                above_50_mult * 100.0,
                below_50_mult * 100.0,
                money(float(monthly_weighted["ending_equity"])),
                money(float(monthly_weighted["ending_vs_basic_dca"])),
            )
        )
    lines.extend(
        [
            "",
            "## Charts",
            "",
            "- Google vs QQQ basic monthly DCA: [`charts/google_vs_qqq_basic_dca_equity.png`](charts/google_vs_qqq_basic_dca_equity.png)",
            "- Strategy comparison by ticker: [`charts/google_qqq_strategy_equity.png`](charts/google_qqq_strategy_equity.png)",
            "",
            "## Files",
            "",
            "- `summary.csv`",
            "- `curves.csv`",
        "- `events.csv`",
        "- `signals.csv`",
        "- `weekly_rsi_state.csv`",
        "- `daily_atr_state.csv`",
        "",
        ]
    )
    (out_dir / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS)
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=default_completed_end())
    parser.add_argument("--monthly-amount", type=float, default=DEFAULT_MONTHLY_AMOUNT)
    parser.add_argument("--lookback-months", type=int, default=DEFAULT_LOOKBACK_MONTHS)
    parser.add_argument("--pivot-bars", type=int, default=DEFAULT_PIVOT_BARS)
    parser.add_argument("--rsi-length", type=int, default=14)
    parser.add_argument("--smooth", type=int, default=14)
    parser.add_argument("--above-50-mult", type=float, default=0.25)
    parser.add_argument("--below-50-mult", type=float, default=0.75)
    parser.add_argument("--hybrid-dca-frac", type=float, default=0.70)
    parser.add_argument("--atr-length", type=int, default=14)
    parser.add_argument("--atr-multiplier", type=float, default=3.0)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output-root", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    out_dir = args.output_root
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "charts").mkdir(parents=True, exist_ok=True)

    raw_daily: dict[str, pd.DataFrame] = {}
    for ticker in args.tickers:
        daily = load_adjusted_daily(ticker, args.start, args.end, ROOT / "data" / "benchmarks", refresh=args.refresh)
        daily = daily.sort_values("date").reset_index(drop=True)
        daily["date"] = pd.to_datetime(daily["date"])
        raw_daily[ticker.upper()] = daily

    common_start = max(pd.Timestamp(df["date"].min()) for df in raw_daily.values())
    daily_by_ticker = {
        ticker: df[df["date"] >= common_start].copy().reset_index(drop=True)
        for ticker, df in raw_daily.items()
    }
    common_start_str = min(df["date"].min().date().isoformat() for df in daily_by_ticker.values())
    common_end_str = max(df["date"].max().date().isoformat() for df in daily_by_ticker.values())

    summary_parts = []
    curve_parts = []
    event_parts = []
    signal_parts = []
    rsi_parts = []
    atr_parts = []

    for ticker, daily_raw in daily_by_ticker.items():
        daily, weekly_state = add_weekly_rsi50_state(daily_raw, args.rsi_length, args.smooth)
        daily, atr_state = add_daily_atr_supertrend_state(daily, args.atr_length, args.atr_multiplier)
        weekly_state = weekly_state.copy()
        weekly_state["ticker"] = ticker
        rsi_parts.append(weekly_state)
        atr_state = atr_state.copy()
        atr_state["ticker"] = ticker
        atr_parts.append(atr_state)

        years = max((pd.Timestamp(daily.iloc[-1]["date"]) - pd.Timestamp(daily.iloc[0]["date"])).days / 365.25, 1e-9)
        signals, _, _, _ = combined_signals(daily, TOUCH_MODE, args.lookback_months, args.pivot_bars)
        signals = signals.copy()
        signals["ticker"] = ticker
        signal_parts.append(signals)
        static_rate = len(signals) / years if years else 0.0
        static_matched_add = args.monthly_amount * 12.0 / max(static_rate, 1.0)

        basic = monthly_dca_open(daily, args.monthly_amount)
        basic["ticker"] = ticker
        basic["strategy"] = "basic_dca_open"
        basic_summary = summarize_curve(basic, "monthly_dca_open", 0, math.nan, 0.0)
        summary_parts.append(
            summarize_strategy(ticker, "basic_dca_open", basic, basic_summary, 0, 0.0, args.monthly_amount, pd.DataFrame())
        )
        curve_parts.append(basic)

        monthly_cash, monthly_cash_events = simulate_monthly_dca_cash_regime(daily, args.monthly_amount)
        monthly_cash["ticker"] = ticker
        monthly_cash["strategy"] = "monthly_dca_rsi50_cash"
        monthly_cash_events["ticker"] = ticker
        summary_parts.append(
            summarize_strategy(ticker, "monthly_dca_rsi50_cash", monthly_cash, basic_summary, 0, 0.0, args.monthly_amount, monthly_cash_events)
        )
        curve_parts.append(monthly_cash)
        event_parts.append(monthly_cash_events)

        monthly_weighted, monthly_weighted_events = simulate_monthly_dca_weighted_spend(
            daily,
            args.monthly_amount,
            args.above_50_mult,
            args.below_50_mult,
        )
        monthly_weighted["ticker"] = ticker
        monthly_weighted["strategy"] = "monthly_dca_rsi50_weighted_spend"
        monthly_weighted_events["ticker"] = ticker
        summary_parts.append(
            summarize_strategy(
                ticker,
                "monthly_dca_rsi50_weighted_spend",
                monthly_weighted,
                basic_summary,
                0,
                0.0,
                args.monthly_amount,
                monthly_weighted_events,
            )
        )
        curve_parts.append(monthly_weighted)
        event_parts.append(monthly_weighted_events)

        hybrid, hybrid_events, hybrid_signals, hybrid_matched_add = simulate_monthly_dca_lhll_rsi50_bulk_split(
            daily,
            signals,
            args.monthly_amount,
            args.hybrid_dca_frac,
        )
        hybrid["ticker"] = ticker
        hybrid["strategy"] = HYBRID_STRATEGY
        hybrid_events["ticker"] = ticker
        hybrid_rate = len(hybrid_signals) / years if years else 0.0
        summary_parts.append(
            summarize_strategy(
                ticker,
                HYBRID_STRATEGY,
                hybrid,
                basic_summary,
                len(hybrid_signals),
                hybrid_rate,
                hybrid_matched_add,
                hybrid_events,
            )
        )
        curve_parts.append(hybrid)
        event_parts.append(hybrid_events)

        atr_bullish_days = int(daily["atr_risk_on"].astype(bool).sum())
        atr_bullish_rate = atr_bullish_days / years if years else 0.0
        atr_matched_add = args.monthly_amount * 12.0 / max(atr_bullish_rate, 1.0)
        atr_dca, atr_dca_events = simulate_daily_atr_supertrend_matched_dca(
            daily,
            args.monthly_amount,
            atr_bullish_rate,
        )
        atr_dca["ticker"] = ticker
        atr_dca["strategy"] = "daily_atr_supertrend_matched_dca"
        atr_dca_events["ticker"] = ticker
        summary_parts.append(
            summarize_strategy(
                ticker,
                "daily_atr_supertrend_matched_dca",
                atr_dca,
                basic_summary,
                atr_bullish_days,
                atr_bullish_rate,
                atr_matched_add,
                atr_dca_events,
            )
        )
        curve_parts.append(atr_dca)
        event_parts.append(atr_dca_events)

        combined, combined_events = simulate_combined_signal_dca(
            daily,
            signals,
            args.monthly_amount,
            SIZING_MODE,
            static_signal_rate=static_rate,
        )
        combined["ticker"] = ticker
        combined["strategy"] = "combined_first_month_lhll_static"
        combined_events["ticker"] = ticker
        combined_events["strategy"] = "combined_first_month_lhll_static"
        combined_events["event_type"] = "signal_buy"
        combined_summary = summarize_combined(ticker, TOUCH_MODE, SIZING_MODE, combined, signals, basic_summary, years, args.monthly_amount)
        summary_parts.append(
            summarize_strategy(
                ticker,
                "combined_first_month_lhll_static",
                combined,
                basic_summary,
                len(signals),
                static_rate,
                float(combined_summary["static_matched_add_amount"]),
                combined_events,
            )
        )
        curve_parts.append(combined)
        event_parts.append(combined_events)

        combined_cash, combined_cash_events = simulate_combined_cash_regime(daily, signals, args.monthly_amount, static_rate)
        combined_cash["ticker"] = ticker
        combined_cash["strategy"] = "combined_first_month_lhll_static_rsi50_cash"
        combined_cash_events["ticker"] = ticker
        summary_parts.append(
            summarize_strategy(
                ticker,
                "combined_first_month_lhll_static_rsi50_cash",
                combined_cash,
                basic_summary,
                len(signals),
                static_rate,
                float(combined_summary["static_matched_add_amount"]),
                combined_cash_events,
            )
        )
        curve_parts.append(combined_cash)
        event_parts.append(combined_cash_events)

        combined_weighted, combined_weighted_events = simulate_combined_weighted_spend(
            daily,
            signals,
            args.monthly_amount,
            static_rate,
            args.above_50_mult,
            args.below_50_mult,
        )
        combined_weighted["ticker"] = ticker
        combined_weighted["strategy"] = "combined_first_month_lhll_static_rsi50_weighted_spend"
        combined_weighted_events["ticker"] = ticker
        summary_parts.append(
            summarize_strategy(
                ticker,
                "combined_first_month_lhll_static_rsi50_weighted_spend",
                combined_weighted,
                basic_summary,
                len(signals),
                static_rate,
                float(combined_summary["static_matched_add_amount"]),
                combined_weighted_events,
            )
        )
        curve_parts.append(combined_weighted)
        event_parts.append(combined_weighted_events)

    summary = pd.DataFrame(summary_parts)
    curves = pd.concat(curve_parts, ignore_index=True)
    events = pd.concat(event_parts, ignore_index=True, sort=False) if event_parts else pd.DataFrame()
    signals = pd.concat(signal_parts, ignore_index=True, sort=False) if signal_parts else pd.DataFrame()
    weekly_rsi = pd.concat(rsi_parts, ignore_index=True, sort=False) if rsi_parts else pd.DataFrame()
    daily_atr = pd.concat(atr_parts, ignore_index=True, sort=False) if atr_parts else pd.DataFrame()

    summary.to_csv(out_dir / "summary.csv", index=False)
    curves.to_csv(out_dir / "curves.csv", index=False)
    events.to_csv(out_dir / "events.csv", index=False)
    signals.to_csv(out_dir / "signals.csv", index=False)
    weekly_rsi.to_csv(out_dir / "weekly_rsi_state.csv", index=False)
    daily_atr.to_csv(out_dir / "daily_atr_state.csv", index=False)
    plot_google_vs_qqq(curves, out_dir / "charts" / "google_vs_qqq_basic_dca_equity.png")
    plot_strategy_comparison(curves, out_dir / "charts" / "google_qqq_strategy_equity.png")
    write_report(
        out_dir,
        summary,
        common_start_str,
        common_end_str,
        args.monthly_amount,
        args.lookback_months,
        args.pivot_bars,
        args.rsi_length,
        args.smooth,
        args.above_50_mult,
        args.below_50_mult,
        args.atr_length,
        args.atr_multiplier,
        args.hybrid_dca_frac,
    )
    print("Wrote %s" % (out_dir / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
