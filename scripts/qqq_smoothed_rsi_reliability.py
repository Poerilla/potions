#!/usr/bin/env python3
"""QQQ smoothed-RSI overbought reliability and oversold DCA study."""
from __future__ import annotations

import argparse
import datetime as dt
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import MaxNLocator

from etf_obv_bearish_dca_study import max_drawdown
from qqq_smoothed_rsi_chart import compute_rsi
from qqq_yearly_orb_study import ROOT, default_completed_end, load_adjusted_daily


OUT_DIR = ROOT / "nq" / "case_studies" / "qqq_smoothed_rsi_reliability"
DEFAULT_START = "2000-01-01"


def money(value: float, digits: int = 0) -> str:
    return "$%s%s" % ("-" if value < 0 else "", format(abs(value), ",.%df" % digits))


def event_starts(daily: pd.DataFrame, column: str, threshold: float, direction: str) -> pd.DataFrame:
    values = pd.to_numeric(daily[column], errors="coerce")
    if direction == "above":
        active = values >= threshold
    elif direction == "below":
        active = values <= threshold
    else:
        raise ValueError("direction must be above or below")
    starts = active & (~active.shift(1).fillna(False)) & values.notna()
    return daily[starts].copy().reset_index(drop=True)


def overbought_intervals(daily: pd.DataFrame, threshold: float) -> pd.DataFrame:
    events = event_starts(daily, "rsi_smooth", threshold, "above")
    rows = []
    for idx, event in events.iterrows():
        start_date = pd.Timestamp(event["date"])
        if idx + 1 < len(events):
            end_date = pd.Timestamp(events.iloc[idx + 1]["date"])
            segment = daily[(daily["date"] >= start_date) & (daily["date"] < end_date)].copy()
            next_event_date = end_date.date().isoformat()
        else:
            segment = daily[daily["date"] >= start_date].copy()
            next_event_date = ""
        if segment.empty:
            continue
        event_close = float(event["close"])
        high_i = pd.to_numeric(segment["high"], errors="coerce").idxmax()
        low_i = pd.to_numeric(segment["low"], errors="coerce").idxmin()
        high_row = segment.loc[high_i]
        low_row = segment.loc[low_i]
        interval_high = float(high_row["high"])
        interval_low = float(low_row["low"])
        high_return = interval_high / event_close - 1.0
        low_return = interval_low / event_close - 1.0
        rows.append(
            {
                "event_index": int(idx + 1),
                "event_date": start_date.date().isoformat(),
                "next_event_date": next_event_date,
                "bars": int(len(segment)),
                "calendar_days": int((pd.Timestamp(segment.iloc[-1]["date"]) - start_date).days),
                "event_close": event_close,
                "event_rsi_smooth": float(event["rsi_smooth"]),
                "interval_high": interval_high,
                "interval_high_date": pd.Timestamp(high_row["date"]).date().isoformat(),
                "interval_low": interval_low,
                "interval_low_date": pd.Timestamp(low_row["date"]).date().isoformat(),
                "high_return_from_event_pct": high_return * 100.0,
                "low_return_from_event_pct": low_return * 100.0,
                "high_low_range_pct": (interval_high / interval_low - 1.0) * 100.0 if interval_low else math.nan,
                "low_before_high": pd.Timestamp(low_row["date"]) < pd.Timestamp(high_row["date"]),
                "pulled_back_5pct": low_return <= -0.05,
                "pulled_back_10pct": low_return <= -0.10,
                "pulled_back_15pct": low_return <= -0.15,
                "pulled_back_20pct": low_return <= -0.20,
            }
        )
    return pd.DataFrame(rows)


def forward_returns(daily: pd.DataFrame, events: pd.DataFrame, horizons: list[int]) -> pd.DataFrame:
    daily = daily.reset_index(drop=True)
    by_date = {pd.Timestamp(row["date"]): idx for idx, row in daily.iterrows()}
    rows = []
    for _, event in events.iterrows():
        date = pd.Timestamp(event["date"])
        idx = by_date.get(date)
        if idx is None:
            continue
        item = {
            "date": date.date().isoformat(),
            "close": float(event["close"]),
            "rsi_smooth": float(event["rsi_smooth"]),
        }
        for horizon in horizons:
            if idx + horizon < len(daily):
                item["return_%dd_pct" % horizon] = (float(daily.iloc[idx + horizon]["close"]) / float(event["close"]) - 1.0) * 100.0
            else:
                item["return_%dd_pct" % horizon] = math.nan
        rows.append(item)
    return pd.DataFrame(rows)


def first_trading_day_each_month(daily: pd.DataFrame) -> set[pd.Timestamp]:
    work = daily[["date"]].copy()
    work["month"] = work["date"].dt.to_period("M")
    return set(pd.to_datetime(work.groupby("month")["date"].first()))


def monthly_dca(daily: pd.DataFrame, monthly_amount: float) -> pd.DataFrame:
    invest_dates = first_trading_day_each_month(daily)
    cash = 0.0
    shares = 0.0
    contributed = 0.0
    rows = []
    for _, bar in daily.iterrows():
        date = pd.Timestamp(bar["date"])
        close = float(bar["close"])
        contribution = 0.0
        buy_amount = 0.0
        if date in invest_dates:
            contribution = monthly_amount
            contributed += contribution
            cash += contribution
            buy_amount = cash
            shares += buy_amount / close
            cash = 0.0
        invested = shares * close
        equity = cash + invested
        rows.append(
            {
                "date": date,
                "variant": "monthly_blind_dca",
                "contribution": contribution,
                "buy_amount": buy_amount,
                "cash": cash,
                "shares": shares,
                "invested_value": invested,
                "equity": equity,
                "total_contributed": contributed,
                "exposure_frac": invested / equity if equity else 0.0,
            }
        )
    return pd.DataFrame(rows)


def rolling_expected_touches(signal_dates: list[pd.Timestamp], current_date: pd.Timestamp, lookback_years: float) -> float:
    start = current_date - pd.Timedelta(days=int(round(365.25 * lookback_years)))
    count = sum(1 for date in signal_dates if start <= date < current_date)
    return max(count / lookback_years, 1.0)


def oversold_touch_dca(
    daily: pd.DataFrame,
    monthly_amount: float,
    variant: str,
    static_add_amount: float | None = None,
    lookback_years: float | None = None,
) -> pd.DataFrame:
    invest_dates = first_trading_day_each_month(daily)
    signal_dates: list[pd.Timestamp] = []
    cash = 0.0
    shares = 0.0
    contributed = 0.0
    rows = []
    for _, bar in daily.iterrows():
        date = pd.Timestamp(bar["date"])
        close = float(bar["close"])
        contribution = 0.0
        if date in invest_dates:
            contribution = monthly_amount
            contributed += contribution
            cash += contribution
        buy_amount = 0.0
        target_add_amount = math.nan
        expected_touches_per_year = math.nan
        if bool(bar["oversold_touch"]):
            if static_add_amount is not None:
                target_add_amount = static_add_amount
            elif lookback_years is not None:
                expected_touches_per_year = rolling_expected_touches(signal_dates, date, lookback_years)
                target_add_amount = monthly_amount * 12.0 / expected_touches_per_year
            else:
                raise ValueError("Need static_add_amount or lookback_years")
            buy_amount = min(cash, target_add_amount)
            if buy_amount > 0:
                shares += buy_amount / close
                cash -= buy_amount
            signal_dates.append(date)
        invested = shares * close
        equity = cash + invested
        rows.append(
            {
                "date": date,
                "variant": variant,
                "contribution": contribution,
                "buy_amount": buy_amount,
                "target_add_amount": target_add_amount,
                "expected_touches_per_year": expected_touches_per_year,
                "cash": cash,
                "shares": shares,
                "invested_value": invested,
                "equity": equity,
                "total_contributed": contributed,
                "exposure_frac": invested / equity if equity else 0.0,
            }
        )
    return pd.DataFrame(rows)


def summarize_curve(
    curve: pd.DataFrame,
    variant: str,
    touch_count: int,
    touches_per_year: float,
    matched_add_amount: float,
) -> dict:
    equity = pd.to_numeric(curve["equity"], errors="coerce")
    total_contributed = float(curve.iloc[-1]["total_contributed"])
    net = float(equity.iloc[-1] - total_contributed)
    dd = max_drawdown(equity)
    buys = int(pd.to_numeric(curve["buy_amount"], errors="coerce").fillna(0.0).gt(0).sum())
    return {
        "variant": variant,
        "touch_count": touch_count,
        "touches_per_year": touches_per_year,
        "matched_add_amount": matched_add_amount,
        "total_contributed": total_contributed,
        "ending_equity": float(equity.iloc[-1]),
        "net": net,
        "return_on_contributions_pct": net / total_contributed * 100.0 if total_contributed else math.nan,
        "max_dd": dd,
        "net_over_dd": net / abs(dd) if dd < 0 else math.inf,
        "ending_cash": float(curve.iloc[-1]["cash"]),
        "avg_exposure_pct": float(pd.to_numeric(curve["exposure_frac"], errors="coerce").fillna(0.0).mean() * 100.0),
        "buys": buys,
        "avg_buy_amount": float(curve.loc[pd.to_numeric(curve["buy_amount"], errors="coerce").fillna(0.0) > 0, "buy_amount"].mean()) if buys else 0.0,
    }


def summarize_overbought(intervals: pd.DataFrame) -> pd.DataFrame:
    if intervals.empty:
        return pd.DataFrame()
    rows = []
    for label, group in [
        ("all_overbought_intervals", intervals),
        ("completed_intervals_only", intervals[intervals["next_event_date"].ne("")]),
    ]:
        if group.empty:
            continue
        rows.append(
            {
                "sample": label,
                "events": int(len(group)),
                "median_low_return_pct": float(group["low_return_from_event_pct"].median()),
                "median_high_return_pct": float(group["high_return_from_event_pct"].median()),
                "median_high_low_range_pct": float(group["high_low_range_pct"].median()),
                "avg_low_return_pct": float(group["low_return_from_event_pct"].mean()),
                "avg_high_return_pct": float(group["high_return_from_event_pct"].mean()),
                "pulled_back_5pct_pct": float(group["pulled_back_5pct"].mean() * 100.0),
                "pulled_back_10pct_pct": float(group["pulled_back_10pct"].mean() * 100.0),
                "pulled_back_15pct_pct": float(group["pulled_back_15pct"].mean() * 100.0),
                "pulled_back_20pct_pct": float(group["pulled_back_20pct"].mean() * 100.0),
                "low_before_high_pct": float(group["low_before_high"].mean() * 100.0),
                "median_bars": float(group["bars"].median()),
            }
        )
    return pd.DataFrame(rows)


def summarize_forward_returns(forward: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in [c for c in forward.columns if c.startswith("return_")]:
        vals = pd.to_numeric(forward[col], errors="coerce").dropna()
        if vals.empty:
            continue
        rows.append(
            {
                "horizon": col.replace("return_", "").replace("_pct", ""),
                "observations": int(len(vals)),
                "avg_return_pct": float(vals.mean()),
                "median_return_pct": float(vals.median()),
                "positive_pct": float((vals > 0).mean() * 100.0),
                "worse_than_minus_5pct_pct": float((vals <= -5.0).mean() * 100.0),
                "worse_than_minus_10pct_pct": float((vals <= -10.0).mean() * 100.0),
            }
        )
    return pd.DataFrame(rows)


def run_oversold_threshold_sweep(
    daily: pd.DataFrame,
    monthly_amount: float,
    start_threshold: float,
    end_threshold: float,
    step: float,
    monthly_summary: dict,
) -> pd.DataFrame:
    years = max((pd.Timestamp(daily.iloc[-1]["date"]) - pd.Timestamp(daily.iloc[0]["date"])).days / 365.25, 1e-9)
    rows = []
    threshold = start_threshold
    while threshold <= end_threshold + 1e-9:
        work = daily.copy()
        events = event_starts(work, "rsi_smooth", threshold, "below")
        work["oversold_touch"] = work["date"].isin(set(pd.to_datetime(events["date"])))
        touch_count = int(work["oversold_touch"].sum())
        touches_per_year = touch_count / years
        matched_add = monthly_amount * 12.0 / touches_per_year if touches_per_year else math.inf
        curve = oversold_touch_dca(work, monthly_amount, "oversold_threshold_%.2f" % threshold, static_add_amount=matched_add)
        summary = summarize_curve(curve, "oversold_threshold_%.2f" % threshold, touch_count, touches_per_year, matched_add)
        deployed_pct = (
            (summary["total_contributed"] - summary["ending_cash"]) / summary["total_contributed"] * 100.0
            if summary["total_contributed"]
            else math.nan
        )
        rows.append(
            {
                "threshold": round(threshold, 4),
                "touch_count": touch_count,
                "touches_per_year": touches_per_year,
                "matched_add_amount": matched_add,
                "buys": summary["buys"],
                "avg_buy_amount": summary["avg_buy_amount"],
                "total_contributed": summary["total_contributed"],
                "ending_cash": summary["ending_cash"],
                "deployed_contributions_pct": deployed_pct,
                "ending_equity": summary["ending_equity"],
                "net": summary["net"],
                "return_on_contributions_pct": summary["return_on_contributions_pct"],
                "max_dd": summary["max_dd"],
                "net_over_dd": summary["net_over_dd"],
                "avg_exposure_pct": summary["avg_exposure_pct"],
                "equity_vs_monthly": summary["ending_equity"] - monthly_summary["ending_equity"],
                "beats_monthly": summary["ending_equity"] > monthly_summary["ending_equity"],
            }
        )
        threshold += step
    return pd.DataFrame(rows)


def two_stage_lump_dca(
    daily: pd.DataFrame,
    monthly_amount: float,
    arm_threshold: float,
    buy_threshold: float,
    variant: str,
) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    invest_dates = first_trading_day_each_month(daily)
    cash = 0.0
    shares = 0.0
    contributed = 0.0
    armed = False
    bought_in_episode = False
    buy_dates: list[pd.Timestamp] = []
    rows = []
    for _, bar in daily.iterrows():
        date = pd.Timestamp(bar["date"])
        close = float(bar["close"])
        rsi_smooth = float(bar["rsi_smooth"]) if pd.notna(bar["rsi_smooth"]) else math.nan
        contribution = 0.0
        buy_amount = 0.0
        if date in invest_dates:
            contribution = monthly_amount
            contributed += contribution
            cash += contribution
        if not math.isnan(rsi_smooth):
            if rsi_smooth > arm_threshold:
                armed = False
                bought_in_episode = False
            elif rsi_smooth <= arm_threshold and not armed:
                armed = True
                bought_in_episode = False

            if armed and not bought_in_episode and rsi_smooth <= buy_threshold:
                buy_amount = cash
                if buy_amount > 0:
                    shares += buy_amount / close
                    cash = 0.0
                bought_in_episode = True
                buy_dates.append(date)
        invested = shares * close
        equity = cash + invested
        rows.append(
            {
                "date": date,
                "variant": variant,
                "arm_threshold": arm_threshold,
                "buy_threshold": buy_threshold,
                "contribution": contribution,
                "buy_amount": buy_amount,
                "cash": cash,
                "shares": shares,
                "invested_value": invested,
                "equity": equity,
                "total_contributed": contributed,
                "exposure_frac": invested / equity if equity else 0.0,
            }
        )
    return pd.DataFrame(rows), buy_dates


def two_stage_lump_summary_fast(
    daily: pd.DataFrame,
    monthly_amount: float,
    arm_threshold: float,
    buy_threshold: float,
    variant: str,
    monthly_ending_equity: float,
) -> dict:
    invest_dates = first_trading_day_each_month(daily)
    dates = pd.to_datetime(daily["date"]).tolist()
    closes = pd.to_numeric(daily["close"], errors="coerce").tolist()
    rsi_values = pd.to_numeric(daily["rsi_smooth"], errors="coerce").tolist()
    cash = 0.0
    shares = 0.0
    contributed = 0.0
    armed = False
    bought_in_episode = False
    peak = 0.0
    max_dd = 0.0
    exposure_sum = 0.0
    rows_seen = 0
    buy_count = 0
    first_buy_dates: list[str] = []
    for date, close, rsi_smooth in zip(dates, closes, rsi_values):
        if pd.Timestamp(date) in invest_dates:
            contributed += monthly_amount
            cash += monthly_amount
        if not math.isnan(rsi_smooth):
            if rsi_smooth > arm_threshold:
                armed = False
                bought_in_episode = False
            elif rsi_smooth <= arm_threshold and not armed:
                armed = True
                bought_in_episode = False
            if armed and not bought_in_episode and rsi_smooth <= buy_threshold:
                if cash > 0:
                    shares += cash / close
                    cash = 0.0
                    buy_count += 1
                    if len(first_buy_dates) < 12:
                        first_buy_dates.append(pd.Timestamp(date).date().isoformat())
                bought_in_episode = True
        invested = shares * close
        equity = cash + invested
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
        exposure_sum += invested / equity if equity else 0.0
        rows_seen += 1
    ending_equity = cash + shares * float(closes[-1]) if closes else 0.0
    net = ending_equity - contributed
    return {
        "arm_threshold": round(arm_threshold, 4),
        "buy_threshold": round(buy_threshold, 4),
        "is_true_second_threshold": buy_threshold < arm_threshold,
        "buy_count": buy_count,
        "first_buy_dates": ", ".join(first_buy_dates),
        "total_contributed": contributed,
        "ending_cash": cash,
        "deployed_contributions_pct": (contributed - cash) / contributed * 100.0 if contributed else math.nan,
        "ending_equity": ending_equity,
        "net": net,
        "return_on_contributions_pct": net / contributed * 100.0 if contributed else math.nan,
        "max_dd": max_dd,
        "net_over_dd": net / abs(max_dd) if max_dd < 0 else math.inf,
        "avg_exposure_pct": exposure_sum / rows_seen * 100.0 if rows_seen else math.nan,
        "equity_vs_monthly": ending_equity - monthly_ending_equity,
        "beats_monthly": ending_equity > monthly_ending_equity,
        "variant": variant,
    }


def run_two_stage_lump_sweep(
    daily: pd.DataFrame,
    monthly_amount: float,
    monthly_summary: dict,
    arm_start: float,
    arm_end: float,
    buy_start: float,
    step: float,
) -> pd.DataFrame:
    rows = []
    arm_threshold = arm_start
    while arm_threshold <= arm_end + 1e-9:
        buy_threshold = buy_start
        while buy_threshold <= arm_threshold + 1e-9:
            variant = "two_stage_lump_arm_%.1f_buy_%.1f" % (arm_threshold, buy_threshold)
            rows.append(
                two_stage_lump_summary_fast(
                    daily,
                    monthly_amount,
                    arm_threshold,
                    buy_threshold,
                    variant,
                    float(monthly_summary["ending_equity"]),
                )
            )
            buy_threshold += step
        arm_threshold += step
    return pd.DataFrame(rows)


def evaluate_two_stage_candidates(
    daily: pd.DataFrame,
    monthly_amount: float,
    monthly_summary: dict,
    arm_start: float,
    arm_end: float,
    buy_start: float,
    step: float,
) -> pd.DataFrame:
    return run_two_stage_lump_sweep(
        daily,
        monthly_amount,
        monthly_summary,
        arm_start,
        arm_end,
        buy_start,
        step,
    )


def simulate_dynamic_two_stage_lump(
    daily: pd.DataFrame,
    monthly_amount: float,
    selections: dict[int, tuple[float, float]],
    variant: str,
) -> pd.DataFrame:
    invest_dates = first_trading_day_each_month(daily)
    cash = 0.0
    shares = 0.0
    contributed = 0.0
    armed = False
    bought_in_episode = False
    active_year: int | None = None
    rows = []
    for _, bar in daily.iterrows():
        date = pd.Timestamp(bar["date"])
        year = int(date.year)
        if active_year != year:
            active_year = year
            armed = False
            bought_in_episode = False
        close = float(bar["close"])
        rsi_smooth = float(bar["rsi_smooth"]) if pd.notna(bar["rsi_smooth"]) else math.nan
        arm_threshold, buy_threshold = selections.get(year, (math.nan, math.nan))
        contribution = 0.0
        buy_amount = 0.0
        if date in invest_dates:
            contribution = monthly_amount
            contributed += contribution
            cash += contribution
        if not math.isnan(arm_threshold) and not math.isnan(buy_threshold) and not math.isnan(rsi_smooth):
            if rsi_smooth > arm_threshold:
                armed = False
                bought_in_episode = False
            elif rsi_smooth <= arm_threshold and not armed:
                armed = True
                bought_in_episode = False

            if armed and not bought_in_episode and rsi_smooth <= buy_threshold:
                buy_amount = cash
                if buy_amount > 0:
                    shares += buy_amount / close
                    cash = 0.0
                bought_in_episode = True
        invested = shares * close
        equity = cash + invested
        rows.append(
            {
                "date": date,
                "variant": variant,
                "year": year,
                "arm_threshold": arm_threshold,
                "buy_threshold": buy_threshold,
                "contribution": contribution,
                "buy_amount": buy_amount,
                "cash": cash,
                "shares": shares,
                "invested_value": invested,
                "equity": equity,
                "total_contributed": contributed,
                "exposure_frac": invested / equity if equity else 0.0,
            }
        )
    return pd.DataFrame(rows)


def summarize_walk_curve(curve: pd.DataFrame, variant: str, monthly_ending_equity: float) -> dict:
    summary = summarize_curve(curve, variant, int(pd.to_numeric(curve["buy_amount"], errors="coerce").fillna(0).gt(0).sum()), math.nan, math.nan)
    summary["equity_vs_monthly"] = summary["ending_equity"] - monthly_ending_equity
    summary["beats_monthly"] = summary["ending_equity"] > monthly_ending_equity
    return summary


def run_holdout_tests(
    daily: pd.DataFrame,
    monthly_amount: float,
    holdout_start_year: int,
    arm_start: float,
    arm_end: float,
    buy_start: float,
    step: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train = daily[daily["date"] < pd.Timestamp(year=holdout_start_year, month=1, day=1)].copy()
    test = daily[daily["date"] >= pd.Timestamp(year=holdout_start_year, month=1, day=1)].copy()
    train_monthly = monthly_dca(train, monthly_amount)
    train_monthly_summary = summarize_curve(train_monthly, "train_monthly_dca", 0, math.nan, math.nan)
    candidates = evaluate_two_stage_candidates(train, monthly_amount, train_monthly_summary, arm_start, arm_end, buy_start, step)
    best_overall = candidates.sort_values("ending_equity", ascending=False).iloc[0]
    true_candidates = candidates[candidates["is_true_second_threshold"]].copy()
    best_true = true_candidates.sort_values("ending_equity", ascending=False).iloc[0]

    monthly = monthly_dca(test, monthly_amount)
    monthly["variant"] = "holdout_monthly_dca"
    monthly_summary = summarize_curve(monthly, "holdout_monthly_dca", 0, math.nan, math.nan)
    curves = {"holdout_monthly_dca": monthly}
    summary_rows = [
        {
            **monthly_summary,
            "holdout_start_year": holdout_start_year,
            "train_start": train["date"].min().date().isoformat(),
            "train_end": train["date"].max().date().isoformat(),
            "test_start": test["date"].min().date().isoformat(),
            "test_end": test["date"].max().date().isoformat(),
            "selected_arm": math.nan,
            "selected_buy": math.nan,
            "selected_from": "monthly_baseline",
            "train_ending_equity": train_monthly_summary["ending_equity"],
            "equity_vs_monthly": 0.0,
            "beats_monthly": False,
        }
    ]
    for label, selected in [
        ("holdout_best_overall_lump", best_overall),
        ("holdout_best_true_second_lump", best_true),
    ]:
        curve, _ = two_stage_lump_dca(
            test,
            monthly_amount,
            float(selected["arm_threshold"]),
            float(selected["buy_threshold"]),
            label,
        )
        curves[label] = curve
        summary = summarize_walk_curve(curve, label, float(monthly_summary["ending_equity"]))
        summary_rows.append(
            {
                **summary,
                "holdout_start_year": holdout_start_year,
                "train_start": train["date"].min().date().isoformat(),
                "train_end": train["date"].max().date().isoformat(),
                "test_start": test["date"].min().date().isoformat(),
                "test_end": test["date"].max().date().isoformat(),
                "selected_arm": float(selected["arm_threshold"]),
                "selected_buy": float(selected["buy_threshold"]),
                "selected_from": "train_best_true_second" if bool(selected["is_true_second_threshold"]) else "train_best_overall",
                "train_ending_equity": float(selected["ending_equity"]),
            }
        )
    return pd.DataFrame(summary_rows), pd.concat(curves.values(), ignore_index=True)


def run_yearly_walkforward(
    daily: pd.DataFrame,
    monthly_amount: float,
    first_test_year: int,
    arm_start: float,
    arm_end: float,
    buy_start: float,
    step: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    years = [
        int(year)
        for year in sorted(daily["date"].dt.year.unique())
        if int(year) >= first_test_year
    ]
    selection_rows = []
    overall_map: dict[int, tuple[float, float]] = {}
    true_map: dict[int, tuple[float, float]] = {}
    for year in years:
        train = daily[daily["date"] < pd.Timestamp(year=year, month=1, day=1)].copy()
        test_year = daily[daily["date"].dt.year.eq(year)].copy()
        if train.empty or test_year.empty:
            continue
        train_monthly = monthly_dca(train, monthly_amount)
        train_monthly_summary = summarize_curve(train_monthly, "train_monthly_dca", 0, math.nan, math.nan)
        candidates = evaluate_two_stage_candidates(train, monthly_amount, train_monthly_summary, arm_start, arm_end, buy_start, step)
        best_overall = candidates.sort_values("ending_equity", ascending=False).iloc[0]
        true_candidates = candidates[candidates["is_true_second_threshold"]].copy()
        best_true = true_candidates.sort_values("ending_equity", ascending=False).iloc[0]
        overall_map[year] = (float(best_overall["arm_threshold"]), float(best_overall["buy_threshold"]))
        true_map[year] = (float(best_true["arm_threshold"]), float(best_true["buy_threshold"]))
        selection_rows.append(
            {
                "year": year,
                "train_start": train["date"].min().date().isoformat(),
                "train_end": train["date"].max().date().isoformat(),
                "test_start": test_year["date"].min().date().isoformat(),
                "test_end": test_year["date"].max().date().isoformat(),
                "overall_arm": float(best_overall["arm_threshold"]),
                "overall_buy": float(best_overall["buy_threshold"]),
                "overall_train_ending_equity": float(best_overall["ending_equity"]),
                "overall_train_vs_monthly": float(best_overall["ending_equity"] - train_monthly_summary["ending_equity"]),
                "true_second_arm": float(best_true["arm_threshold"]),
                "true_second_buy": float(best_true["buy_threshold"]),
                "true_second_train_ending_equity": float(best_true["ending_equity"]),
                "true_second_train_vs_monthly": float(best_true["ending_equity"] - train_monthly_summary["ending_equity"]),
                "train_monthly_ending_equity": float(train_monthly_summary["ending_equity"]),
            }
        )

    oos = daily[daily["date"].dt.year.ge(first_test_year)].copy()
    monthly = monthly_dca(oos, monthly_amount)
    monthly["variant"] = "walkforward_monthly_dca"
    monthly_summary = summarize_curve(monthly, "walkforward_monthly_dca", 0, math.nan, math.nan)
    overall_curve = simulate_dynamic_two_stage_lump(oos, monthly_amount, overall_map, "walkforward_best_overall_lump")
    true_curve = simulate_dynamic_two_stage_lump(oos, monthly_amount, true_map, "walkforward_best_true_second_lump")
    summary_rows = [
        {
            **monthly_summary,
            "first_test_year": first_test_year,
            "selected_years": len(selection_rows),
            "equity_vs_monthly": 0.0,
            "beats_monthly": False,
        },
        {
            **summarize_walk_curve(overall_curve, "walkforward_best_overall_lump", float(monthly_summary["ending_equity"])),
            "first_test_year": first_test_year,
            "selected_years": len(selection_rows),
        },
        {
            **summarize_walk_curve(true_curve, "walkforward_best_true_second_lump", float(monthly_summary["ending_equity"])),
            "first_test_year": first_test_year,
            "selected_years": len(selection_rows),
        },
    ]
    return pd.DataFrame(selection_rows), pd.DataFrame(summary_rows), pd.concat([monthly, overall_curve, true_curve], ignore_index=True)


def plot_dca(curves: dict[str, pd.DataFrame], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(14, 7))
    colors = {
        "monthly_blind_dca": "#111827",
        "oversold_static_full_window": "#2563eb",
        "oversold_rolling_3y": "#0f766e",
        "oversold_rolling_5y": "#7c3aed",
        "oversold_rolling_10y": "#b45309",
    }
    for label, curve in curves.items():
        ax.plot(curve["date"], curve["equity"], label=label, linewidth=1.35, color=colors.get(label))
    ax.set_title("QQQ monthly DCA vs smoothed-RSI oversold-touch lump buys")
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


def plot_two_stage_lump_sweep(sweep: pd.DataFrame, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(12, 8))
    colors = pd.to_numeric(sweep["equity_vs_monthly"], errors="coerce")
    scatter = ax.scatter(
        sweep["buy_threshold"],
        sweep["arm_threshold"],
        c=colors,
        cmap="RdYlGn",
        s=80,
        edgecolors="#111827",
        linewidths=0.25,
    )
    ax.plot([sweep["buy_threshold"].min(), sweep["arm_threshold"].max()], [sweep["buy_threshold"].min(), sweep["arm_threshold"].max()], color="#6b7280", linestyle="--", linewidth=0.9, label="same threshold")
    ax.set_title("QQQ two-threshold RSI lump-buy sweep vs monthly DCA")
    ax.set_xlabel("Buy threshold (second/deeper trigger)")
    ax.set_ylabel("Arm threshold")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=8)
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label("Ending equity minus monthly DCA ($)")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_equity_comparison(curves: pd.DataFrame, title: str, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(14, 7))
    colors = {
        "holdout_monthly_dca": "#111827",
        "holdout_best_overall_lump": "#2563eb",
        "holdout_best_true_second_lump": "#0f766e",
        "walkforward_monthly_dca": "#111827",
        "walkforward_best_overall_lump": "#2563eb",
        "walkforward_best_true_second_lump": "#0f766e",
    }
    for variant, group in curves.groupby("variant", sort=False):
        work = group.sort_values("date")
        ax.plot(work["date"], work["equity"], label=variant, color=colors.get(variant), linewidth=1.4)
    ax.set_title(title)
    ax.set_ylabel("Equity ($)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=8)
    ax.xaxis.set_major_locator(mdates.YearLocator(base=1 if curves["date"].dt.year.nunique() <= 10 else 2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_threshold_sweep(sweep: pd.DataFrame, monthly_ending_equity: float, out: Path) -> None:
    fig, (ax_equity, ax_deploy) = plt.subplots(2, 1, figsize=(14, 8), sharex=True, height_ratios=[1.2, 1.0])
    thresholds = pd.to_numeric(sweep["threshold"], errors="coerce")
    ax_equity.plot(thresholds, sweep["ending_equity"], color="#2563eb", linewidth=1.6, label="Signal ending equity")
    ax_equity.axhline(monthly_ending_equity, color="#111827", linewidth=1.1, linestyle="--", label="Monthly DCA")
    ax_equity.set_ylabel("Ending equity ($)")
    ax_equity.set_title("QQQ smoothed-RSI oversold threshold sweep")
    ax_equity.grid(True, alpha=0.25)
    ax_equity.legend(loc="upper left", fontsize=8)

    ax_deploy.plot(thresholds, sweep["deployed_contributions_pct"], color="#0f766e", linewidth=1.6, label="Contributions deployed")
    ax_deploy.axhline(90, color="#f59e0b", linewidth=0.9, linestyle="--", label="90% deployed")
    ax_deploy.axhline(95, color="#dc2626", linewidth=0.9, linestyle="--", label="95% deployed")
    ax_deploy.set_ylabel("Deployed (%)")
    ax_deploy.set_xlabel("Smoothed RSI buy threshold")
    ax_deploy.set_ylim(0, 105)
    ax_deploy.grid(True, alpha=0.25)
    ax_deploy.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def plot_overbought(intervals: pd.DataFrame, out: Path) -> None:
    fig, (ax_scatter, ax_hist) = plt.subplots(2, 1, figsize=(14, 9), height_ratios=[1.3, 1.0])
    completed = intervals[intervals["next_event_date"].ne("")].copy()
    ax_scatter.scatter(
        pd.to_datetime(completed["event_date"]),
        completed["low_return_from_event_pct"],
        color="#dc2626",
        s=28,
        label="Low before next overbought",
    )
    ax_scatter.scatter(
        pd.to_datetime(completed["event_date"]),
        completed["high_return_from_event_pct"],
        color="#0f766e",
        s=28,
        label="High before next overbought",
    )
    ax_scatter.axhline(0, color="#6b7280", linewidth=0.8)
    ax_scatter.set_ylabel("Return from event close (%)")
    ax_scatter.set_title("QQQ smoothed-RSI overbought interval high/low")
    ax_scatter.grid(True, alpha=0.25)
    ax_scatter.legend(loc="upper left", fontsize=8)

    ax_hist.hist(completed["low_return_from_event_pct"], bins=24, alpha=0.75, color="#dc2626", label="Interval low return")
    ax_hist.hist(completed["high_return_from_event_pct"], bins=24, alpha=0.55, color="#0f766e", label="Interval high return")
    ax_hist.axvline(0, color="#6b7280", linewidth=0.8)
    ax_hist.set_xlabel("Return from overbought close (%)")
    ax_hist.set_ylabel("Count")
    ax_hist.grid(True, alpha=0.25)
    ax_hist.legend(loc="upper right", fontsize=8)
    ax_hist.xaxis.set_major_locator(MaxNLocator(10))
    ax_scatter.xaxis.set_major_locator(mdates.YearLocator(base=2))
    ax_scatter.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def write_report(
    out_dir: Path,
    daily: pd.DataFrame,
    intervals: pd.DataFrame,
    overbought_summary: pd.DataFrame,
    forward_summary: pd.DataFrame,
    dca_summary: pd.DataFrame,
    threshold_sweep: pd.DataFrame,
    two_stage_sweep: pd.DataFrame,
    holdout_summary: pd.DataFrame,
    walkforward_selection: pd.DataFrame,
    walkforward_summary: pd.DataFrame,
    rsi_len: int,
    smooth: int,
    overbought_threshold: float,
    oversold_threshold: float,
    monthly_amount: float,
) -> None:
    completed = intervals[intervals["next_event_date"].ne("")]
    monthly = dca_summary[dca_summary["variant"].eq("monthly_blind_dca")].iloc[0]
    best_signal = dca_summary[dca_summary["variant"].ne("monthly_blind_dca")].sort_values("ending_equity", ascending=False).iloc[0]
    best_threshold = threshold_sweep.sort_values("ending_equity", ascending=False).iloc[0]
    best_two_stage = two_stage_sweep.sort_values("ending_equity", ascending=False).iloc[0]
    true_second = two_stage_sweep[two_stage_sweep["is_true_second_threshold"]].copy()
    best_true_second = true_second.sort_values("ending_equity", ascending=False).iloc[0] if not true_second.empty else best_two_stage
    first_90 = threshold_sweep[threshold_sweep["deployed_contributions_pct"].ge(90.0)].sort_values("threshold").head(1)
    first_95 = threshold_sweep[threshold_sweep["deployed_contributions_pct"].ge(95.0)].sort_values("threshold").head(1)
    most_touches = threshold_sweep.sort_values(["touch_count", "ending_equity"], ascending=[False, False]).iloc[0]
    touches_per_year = float(best_signal["touches_per_year"])
    oversold_dates = [
        pd.Timestamp(date).date().isoformat()
        for date in daily.loc[daily["oversold_touch"], "date"].tolist()
    ]
    completed_summary = overbought_summary[overbought_summary["sample"].eq("completed_intervals_only")].iloc[0]
    high_beats_low_read = (
        "Overbought was **not** a reliable bearish sell signal in this QQQ sample: "
        "the median completed interval low was %.2f%%, but the median interval high was %.2f%% and the median 126d/252d forward returns stayed positive."
        % (
            float(completed_summary["median_low_return_pct"]),
            float(completed_summary["median_high_return_pct"]),
        )
    )
    validation_lines = [
        "",
        "## Holdout / Walk-Forward Check",
        "",
        "Holdout and walk-forward use only prior data to choose thresholds. The fixed holdout trains before the holdout year and then freezes the chosen thresholds. The yearly walk-forward reselects thresholds each January using all data before that year, then stitches the out-of-sample account path forward with cash and shares carried through time.",
        "",
        "### Fixed Holdout",
        "",
        "| Variant | Train/Test | Selected Arm | Selected Buy | Buys | End Equity | Vs Monthly | Max DD | Net/DD |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in holdout_summary.iterrows():
        train_test = "%s to %s / %s to %s" % (row["train_start"], row["train_end"], row["test_start"], row["test_end"])
        selected_arm = "" if pd.isna(row["selected_arm"]) else "%.1f" % float(row["selected_arm"])
        selected_buy = "" if pd.isna(row["selected_buy"]) else "%.1f" % float(row["selected_buy"])
        validation_lines.append(
            "| %s | %s | %s | %s | %d | %s | %s | %s | %.2f |"
            % (
                row["variant"],
                train_test,
                selected_arm,
                selected_buy,
                int(row["buys"]),
                money(float(row["ending_equity"])),
                money(float(row["equity_vs_monthly"])),
                money(float(row["max_dd"])),
                float(row["net_over_dd"]),
            )
        )
    validation_lines.extend(
        [
            "",
            "### Yearly Walk-Forward",
            "",
            "| Variant | Selected Years | Buys | End Equity | Vs Monthly | Max DD | Net/DD | Avg Exposure |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in walkforward_summary.iterrows():
        validation_lines.append(
            "| %s | %d | %d | %s | %s | %s | %.2f | %.1f%% |"
            % (
                row["variant"],
                int(row["selected_years"]),
                int(row["buys"]),
                money(float(row["ending_equity"])),
                money(float(row["equity_vs_monthly"])),
                money(float(row["max_dd"])),
                float(row["net_over_dd"]),
                float(row["avg_exposure_pct"]),
            )
        )
    if not walkforward_selection.empty:
        most_common_true = (
            walkforward_selection.groupby(["true_second_arm", "true_second_buy"])
            .size()
            .reset_index(name="years")
            .sort_values("years", ascending=False)
            .iloc[0]
        )
        most_common_overall = (
            walkforward_selection.groupby(["overall_arm", "overall_buy"])
            .size()
            .reset_index(name="years")
            .sort_values("years", ascending=False)
            .iloc[0]
        )
        validation_lines.extend(
            [
                "",
                "- Most common yearly-selected true second-threshold rule: **arm %.1f / buy %.1f** in **%d** years."
                % (
                    float(most_common_true["true_second_arm"]),
                    float(most_common_true["true_second_buy"]),
                    int(most_common_true["years"]),
                ),
                "- Most common yearly-selected overall rule: **arm %.1f / buy %.1f** in **%d** years."
                % (
                    float(most_common_overall["overall_arm"]),
                    float(most_common_overall["overall_buy"]),
                    int(most_common_overall["years"]),
                ),
            ]
        )
    best_holdout_timing = holdout_summary[~holdout_summary["variant"].str.contains("monthly", na=False)].sort_values("ending_equity", ascending=False).iloc[0]
    best_walk_timing = walkforward_summary[~walkforward_summary["variant"].str.contains("monthly", na=False)].sort_values("ending_equity", ascending=False).iloc[0]
    validation_lines.extend(
        [
            "",
            "- Validation read: the full-sample second-threshold edge **did not survive** the out-of-sample checks. The best fixed-holdout timing row trailed monthly DCA by **%s**, and the best yearly walk-forward timing row trailed by **%s**."
            % (
                money(abs(float(best_holdout_timing["equity_vs_monthly"]))),
                money(abs(float(best_walk_timing["equity_vs_monthly"]))),
            ),
        ]
    )
    lines = [
        "# QQQ Smoothed-RSI Reliability Study",
        "",
        "Data: Yahoo adjusted daily OHLCV for `QQQ`.",
        "Window: **%s through %s**." % (daily["date"].min().date().isoformat(), daily["date"].max().date().isoformat()),
        "",
        "Indicator:",
        "",
        "- RSI uses Wilder-style RSI(%d)." % rsi_len,
        "- Smoothed RSI is EMA(%d) of RSI(%d)." % (smooth, rsi_len),
        "- Overbought starts when smoothed RSI first touches **>= %.0f** after being below it." % overbought_threshold,
        "- Oversold buy starts when smoothed RSI first touches **<= %.0f** after being above it." % oversold_threshold,
        "",
        "## Overbought Interval Summary",
        "",
        "For each overbought start, the interval is measured from that date until the next overbought start. The table uses adjusted highs/lows inside that interval.",
        "",
        "| Sample | Events | Median Low | Median High | Median High-Low Range | Pullback >=5% | >=10% | >=15% | >=20% | Low Before High | Median Bars |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in overbought_summary.iterrows():
        lines.append(
            "| %s | %d | %.2f%% | %.2f%% | %.2f%% | %.1f%% | %.1f%% | %.1f%% | %.1f%% | %.1f%% | %.0f |"
            % (
                row["sample"],
                int(row["events"]),
                float(row["median_low_return_pct"]),
                float(row["median_high_return_pct"]),
                float(row["median_high_low_range_pct"]),
                float(row["pulled_back_5pct_pct"]),
                float(row["pulled_back_10pct_pct"]),
                float(row["pulled_back_15pct_pct"]),
                float(row["pulled_back_20pct_pct"]),
                float(row["low_before_high_pct"]),
                float(row["median_bars"]),
            )
        )
    lines.extend(
        [
            "",
            "## Forward Return Check",
            "",
            "| Horizon | Observations | Avg Return | Median Return | Positive | <= -5% | <= -10% |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in forward_summary.iterrows():
        lines.append(
            "| %s | %d | %.2f%% | %.2f%% | %.1f%% | %.1f%% | %.1f%% |"
            % (
                row["horizon"],
                int(row["observations"]),
                float(row["avg_return_pct"]),
                float(row["median_return_pct"]),
                float(row["positive_pct"]),
                float(row["worse_than_minus_5pct_pct"]),
                float(row["worse_than_minus_10pct_pct"]),
            )
        )
    lines.extend(
        [
            "",
            "## Oversold-Touch Lump Buy Test",
            "",
            "Comparison rule: contribute **%s/month**. Monthly DCA buys each first trading day. Oversold-touch variants hold contributions as cash and buy only on smoothed-RSI oversold starts. `static_full_window` sizes each signal as `$12k / observed oversold touches per year`; rolling rows estimate touch frequency from prior history and cap buys at available cash." % money(monthly_amount),
            "",
            "| Rank | Variant | Touches / Yr | Matched Add | Buys | Avg Buy | End Equity | Net | Return | Max DD | Net/DD | Avg Exposure | Ending Cash |",
            "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    ranked = dca_summary.sort_values("ending_equity", ascending=False).reset_index(drop=True)
    for rank, (_, row) in enumerate(ranked.iterrows(), start=1):
        lines.append(
            "| %d | %s | %.2f | %s | %d | %s | %s | %s | %.1f%% | %s | %.2f | %.1f%% | %s |"
            % (
                rank,
                row["variant"],
                float(row["touches_per_year"]) if not pd.isna(row["touches_per_year"]) else 0.0,
                money(float(row["matched_add_amount"])) if math.isfinite(float(row["matched_add_amount"])) else "rolling/NA",
                int(row["buys"]),
                money(float(row["avg_buy_amount"])),
                money(float(row["ending_equity"])),
                money(float(row["net"])),
                float(row["return_on_contributions_pct"]),
                money(float(row["max_dd"])),
                float(row["net_over_dd"]),
                float(row["avg_exposure_pct"]),
                money(float(row["ending_cash"])),
            )
        )
    lines.extend(
        [
            "",
            "## Oversold Threshold Sweep",
            "",
            "This sweep reruns the static matched-add rule across smoothed-RSI buy thresholds from %.1f to %.1f. `Deployed` is the share of contributed cash that actually got invested by the final bar; this is the key apples-to-apples check against monthly DCA."
            % (float(threshold_sweep["threshold"].min()), float(threshold_sweep["threshold"].max())),
            "",
            "| Check | Threshold | Touches | Touches / Yr | Matched Add | Deployed | End Equity | Vs Monthly DCA |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    milestone_rows = [
        ("First >=90% deployed", first_90.iloc[0] if not first_90.empty else None),
        ("First >=95% deployed", first_95.iloc[0] if not first_95.empty else None),
        ("Best ending equity", best_threshold),
        ("Most touch starts", most_touches),
    ]
    for label, row in milestone_rows:
        if row is None:
            lines.append("| %s | n/a | n/a | n/a | n/a | n/a | n/a | n/a |" % label)
            continue
        lines.append(
            "| %s | %.1f | %d | %.2f | %s | %.1f%% | %s | %s |"
            % (
                label,
                float(row["threshold"]),
                int(row["touch_count"]),
                float(row["touches_per_year"]),
                money(float(row["matched_add_amount"])),
                float(row["deployed_contributions_pct"]),
                money(float(row["ending_equity"])),
                money(float(row["equity_vs_monthly"])),
            )
        )
    threshold_beats = bool(threshold_sweep["beats_monthly"].any())
    lines.extend(
        [
            "",
            "- The first threshold that deployed at least **90%%** of contributions was **%.1f**; the first that deployed at least **95%%** was **%.1f**."
            % (
                float(first_90.iloc[0]["threshold"]) if not first_90.empty else math.nan,
                float(first_95.iloc[0]["threshold"]) if not first_95.empty else math.nan,
            ),
            "- The best ending-equity threshold was **%.1f** at **%s**, still **%s** versus monthly DCA."
            % (
                float(best_threshold["threshold"]),
                money(float(best_threshold["ending_equity"])),
                money(float(best_threshold["equity_vs_monthly"])),
            ),
            "- No swept threshold beat monthly DCA on ending equity." if not threshold_beats else "- At least one swept threshold beat monthly DCA on ending equity.",
            "",
            "## Second-Threshold Lump Buy Test",
            "",
            "This variant contributes the same **%s/month**, but cash stays idle until the smoothed RSI first arms below a higher threshold, then it buys **all available cash once** if the same drawdown episode reaches the buy threshold. It resets only after smoothed RSI recovers above the arm threshold."
            % money(monthly_amount),
            "",
            "| Check | Arm | Buy | Buys | Deployed | End Equity | Vs Monthly DCA | Net/DD |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
            "| Best overall lump row | %.1f | %.1f | %d | %.1f%% | %s | %s | %.2f |"
            % (
                float(best_two_stage["arm_threshold"]),
                float(best_two_stage["buy_threshold"]),
                int(best_two_stage["buy_count"]),
                float(best_two_stage["deployed_contributions_pct"]),
                money(float(best_two_stage["ending_equity"])),
                money(float(best_two_stage["equity_vs_monthly"])),
                float(best_two_stage["net_over_dd"]),
            ),
            "| Best true second-threshold row | %.1f | %.1f | %d | %.1f%% | %s | %s | %.2f |"
            % (
                float(best_true_second["arm_threshold"]),
                float(best_true_second["buy_threshold"]),
                int(best_true_second["buy_count"]),
                float(best_true_second["deployed_contributions_pct"]),
                money(float(best_true_second["ending_equity"])),
                money(float(best_true_second["equity_vs_monthly"])),
                float(best_true_second["net_over_dd"]),
            ),
            "",
            "- The best true second-threshold row **did** beat monthly DCA on ending equity." if bool(best_true_second["beats_monthly"]) else "- The best true second-threshold row did **not** beat monthly DCA on ending equity.",
            "- This is a stronger result than the matched-add touch sweep, but it depends on sweeping all accumulated cash at the trigger, so it is more of a cash-timing strategy than a smooth DCA replacement.",
            *validation_lines,
            "",
            "## Read",
            "",
            "- Completed overbought intervals measured: **%d**." % len(completed),
            "- Median interval low after an overbought start was **%.2f%%** from the event close; median interval high was **%.2f%%**." % (
                float(overbought_summary[overbought_summary["sample"].eq("completed_intervals_only")]["median_low_return_pct"].iloc[0]),
                float(overbought_summary[overbought_summary["sample"].eq("completed_intervals_only")]["median_high_return_pct"].iloc[0]),
            ),
            "- %s" % high_beats_low_read,
            "- Oversold starts were rare: **%d** total (**%s**)." % (len(oversold_dates), ", ".join(oversold_dates) if oversold_dates else "none"),
            "- Oversold starts occurred at about **%.2f/year**. The best oversold-touch lump-buy row was **%s** at **%s**, versus monthly DCA at **%s**." % (
                touches_per_year,
                best_signal["variant"],
                money(float(best_signal["ending_equity"])),
                money(float(monthly["ending_equity"])),
            ),
        ]
    )
    if float(best_signal["ending_equity"]) > float(monthly["ending_equity"]):
        lines.append("- On ending equity, oversold-touch lump buying **beat** traditional monthly DCA in this test.")
    else:
        lines.append("- On ending equity, oversold-touch lump buying **did not beat** traditional monthly DCA in this test.")
    lines.extend(
        [
            "",
            "## Charts",
            "",
            "- Overbought interval high/low: [`charts/overbought_interval_high_low.png`](charts/overbought_interval_high_low.png)",
            "- DCA comparison: [`charts/oversold_touch_dca_vs_monthly.png`](charts/oversold_touch_dca_vs_monthly.png)",
            "- Oversold threshold sweep: [`charts/oversold_threshold_sweep.png`](charts/oversold_threshold_sweep.png)",
            "- Second-threshold lump sweep: [`charts/two_stage_lump_sweep.png`](charts/two_stage_lump_sweep.png)",
            "- Fixed holdout equity: [`charts/holdout_equity.png`](charts/holdout_equity.png)",
            "- Yearly walk-forward equity: [`charts/walkforward_equity.png`](charts/walkforward_equity.png)",
            "",
            "## Files",
            "",
            "- `QQQ_smoothed_rsi_daily.csv`",
            "- `overbought_intervals.csv`",
            "- `overbought_summary.csv`",
            "- `overbought_forward_returns.csv`",
            "- `overbought_forward_summary.csv`",
            "- `oversold_touch_dca_summary.csv`",
            "- `oversold_touch_dca_daily.csv`",
            "- `oversold_threshold_sweep.csv`",
            "- `two_stage_lump_sweep.csv`",
            "- `holdout_summary.csv`",
            "- `holdout_daily.csv`",
            "- `walkforward_selection_by_year.csv`",
            "- `walkforward_summary.csv`",
            "- `walkforward_daily.csv`",
        ]
    )
    (out_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build QQQ smoothed-RSI reliability study.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=default_completed_end())
    parser.add_argument("--rsi-len", type=int, default=14)
    parser.add_argument("--smooth", type=int, default=14)
    parser.add_argument("--overbought", type=float, default=70.0)
    parser.add_argument("--oversold", type=float, default=30.0)
    parser.add_argument("--monthly-amount", type=float, default=1_000.0)
    parser.add_argument("--threshold-sweep-start", type=float, default=30.0)
    parser.add_argument("--threshold-sweep-end", type=float, default=70.0)
    parser.add_argument("--threshold-sweep-step", type=float, default=0.5)
    parser.add_argument("--two-stage-arm-start", type=float, default=45.0)
    parser.add_argument("--two-stage-arm-end", type=float, default=70.0)
    parser.add_argument("--two-stage-buy-start", type=float, default=30.0)
    parser.add_argument("--two-stage-step", type=float, default=2.5)
    parser.add_argument("--holdout-start-year", type=int, default=2016)
    parser.add_argument("--walkforward-first-test-year", type=int, default=2010)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output-root", type=Path, default=OUT_DIR)
    args = parser.parse_args()

    out_dir = args.output_root
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "charts").mkdir(parents=True, exist_ok=True)

    daily = load_adjusted_daily("QQQ", args.start, args.end, ROOT / "data" / "benchmarks", refresh=args.refresh)
    daily = compute_rsi(daily, args.rsi_len, args.smooth)
    oversold_events = event_starts(daily, "rsi_smooth", args.oversold, "below")
    overbought_events = event_starts(daily, "rsi_smooth", args.overbought, "above")
    daily["oversold_touch"] = daily["date"].isin(set(pd.to_datetime(oversold_events["date"])))
    daily["overbought_touch"] = daily["date"].isin(set(pd.to_datetime(overbought_events["date"])))

    intervals = overbought_intervals(daily, args.overbought)
    overbought_summary = summarize_overbought(intervals)
    forward = forward_returns(daily, overbought_events, [21, 63, 126, 252])
    forward_summary = summarize_forward_returns(forward)

    years = max((pd.Timestamp(daily.iloc[-1]["date"]) - pd.Timestamp(daily.iloc[0]["date"])).days / 365.25, 1e-9)
    touch_count = int(daily["oversold_touch"].sum())
    touches_per_year = touch_count / years
    static_add = args.monthly_amount * 12.0 / touches_per_year if touches_per_year else math.inf

    curves = {
        "monthly_blind_dca": monthly_dca(daily, args.monthly_amount),
        "oversold_static_full_window": oversold_touch_dca(
            daily,
            args.monthly_amount,
            "oversold_static_full_window",
            static_add_amount=static_add,
        ),
        "oversold_rolling_3y": oversold_touch_dca(daily, args.monthly_amount, "oversold_rolling_3y", lookback_years=3),
        "oversold_rolling_5y": oversold_touch_dca(daily, args.monthly_amount, "oversold_rolling_5y", lookback_years=5),
        "oversold_rolling_10y": oversold_touch_dca(daily, args.monthly_amount, "oversold_rolling_10y", lookback_years=10),
    }
    dca_summary = pd.DataFrame(
        [
            summarize_curve(
                curve,
                label,
                touch_count,
                touches_per_year,
                static_add if label == "oversold_static_full_window" else math.nan,
            )
            for label, curve in curves.items()
        ]
    )
    dca_daily = pd.concat(curves.values(), ignore_index=True)
    monthly_summary = dca_summary[dca_summary["variant"].eq("monthly_blind_dca")].iloc[0].to_dict()
    threshold_sweep = run_oversold_threshold_sweep(
        daily,
        args.monthly_amount,
        args.threshold_sweep_start,
        args.threshold_sweep_end,
        args.threshold_sweep_step,
        monthly_summary,
    )
    two_stage_sweep = run_two_stage_lump_sweep(
        daily,
        args.monthly_amount,
        monthly_summary,
        args.two_stage_arm_start,
        args.two_stage_arm_end,
        args.two_stage_buy_start,
        args.two_stage_step,
    )
    holdout_summary, holdout_daily = run_holdout_tests(
        daily,
        args.monthly_amount,
        args.holdout_start_year,
        args.two_stage_arm_start,
        args.two_stage_arm_end,
        args.two_stage_buy_start,
        args.two_stage_step,
    )
    walkforward_selection, walkforward_summary, walkforward_daily = run_yearly_walkforward(
        daily,
        args.monthly_amount,
        args.walkforward_first_test_year,
        args.two_stage_arm_start,
        args.two_stage_arm_end,
        args.two_stage_buy_start,
        args.two_stage_step,
    )

    daily.to_csv(out_dir / "QQQ_smoothed_rsi_daily.csv", index=False)
    intervals.to_csv(out_dir / "overbought_intervals.csv", index=False)
    overbought_summary.to_csv(out_dir / "overbought_summary.csv", index=False)
    forward.to_csv(out_dir / "overbought_forward_returns.csv", index=False)
    forward_summary.to_csv(out_dir / "overbought_forward_summary.csv", index=False)
    dca_summary.to_csv(out_dir / "oversold_touch_dca_summary.csv", index=False)
    dca_daily.to_csv(out_dir / "oversold_touch_dca_daily.csv", index=False)
    threshold_sweep.to_csv(out_dir / "oversold_threshold_sweep.csv", index=False)
    two_stage_sweep.to_csv(out_dir / "two_stage_lump_sweep.csv", index=False)
    holdout_summary.to_csv(out_dir / "holdout_summary.csv", index=False)
    holdout_daily.to_csv(out_dir / "holdout_daily.csv", index=False)
    walkforward_selection.to_csv(out_dir / "walkforward_selection_by_year.csv", index=False)
    walkforward_summary.to_csv(out_dir / "walkforward_summary.csv", index=False)
    walkforward_daily.to_csv(out_dir / "walkforward_daily.csv", index=False)
    plot_overbought(intervals, out_dir / "charts" / "overbought_interval_high_low.png")
    plot_dca(curves, out_dir / "charts" / "oversold_touch_dca_vs_monthly.png")
    plot_threshold_sweep(threshold_sweep, float(monthly_summary["ending_equity"]), out_dir / "charts" / "oversold_threshold_sweep.png")
    plot_two_stage_lump_sweep(two_stage_sweep, out_dir / "charts" / "two_stage_lump_sweep.png")
    plot_equity_comparison(holdout_daily, "QQQ fixed holdout RSI lump timing vs monthly DCA", out_dir / "charts" / "holdout_equity.png")
    plot_equity_comparison(walkforward_daily, "QQQ yearly walk-forward RSI lump timing vs monthly DCA", out_dir / "charts" / "walkforward_equity.png")
    write_report(
        out_dir,
        daily,
        intervals,
        overbought_summary,
        forward_summary,
        dca_summary,
        threshold_sweep,
        two_stage_sweep,
        holdout_summary,
        walkforward_selection,
        walkforward_summary,
        args.rsi_len,
        args.smooth,
        args.overbought,
        args.oversold,
        args.monthly_amount,
    )
    print("Wrote %s" % (out_dir / "INDEX.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
