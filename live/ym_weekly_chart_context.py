from __future__ import annotations

from typing import Literal, Optional

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from .nq_15m_ma200_supertrend_100_week_charts import plot_candles


DojiClass = Literal["invalid", "strong_doji", "doji", "small_body", "not_doji"]


NY = "America/New_York"


def _normalize_week(ts: pd.Timestamp) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize(NY)
    else:
        t = t.tz_convert(NY)
    return t.normalize()


def weekly_bars_from_15m(bars: pd.DataFrame) -> pd.DataFrame:
    df = bars.copy()
    if df.index.name != "ts" and "ts" not in df.columns:
        df = df.reset_index()
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(NY)
        df = df.set_index("ts").sort_index()
    elif df.index.tz is None:
        df.index = df.index.tz_localize(NY)
    else:
        df.index = df.index.tz_convert(NY)
    df["week_start"] = (df.index.normalize() - pd.to_timedelta(df.index.weekday, unit="D")).floor("D")
    weekly = (
        df.groupby("week_start")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .sort_index()
    )
    weekly.index = pd.DatetimeIndex(weekly.index).tz_convert(NY)
    weekly["ma10"] = weekly["close"].rolling(10).mean()
    return weekly


def classify_doji(
    candle: dict[str, float] | pd.Series,
    *,
    min_range: float = 5.0,
) -> tuple[DojiClass, float]:
    high = float(candle["high"])
    low = float(candle["low"])
    open_ = float(candle["open"])
    close = float(candle["close"])
    range_ = high - low
    if range_ <= 0 or range_ < min_range:
        return "invalid", 0.0
    body = abs(close - open_)
    body_pct = body / range_
    if body_pct <= 0.05:
        return "strong_doji", body_pct
    if body_pct <= 0.10:
        return "doji", body_pct
    if body_pct <= 0.20:
        return "small_body", body_pct
    return "not_doji", body_pct


def _cross_direction(prev_close: float, prev_ma10: float, close: float, ma10: float) -> Optional[str]:
    if prev_close <= prev_ma10 and close > ma10:
        return "bullish"
    if prev_close >= prev_ma10 and close < ma10:
        return "bearish"
    return None


def latest_ma10_cross(weekly: pd.DataFrame, week_start: pd.Timestamp) -> Optional[dict[str, object]]:
    target = _normalize_week(week_start)
    prior = weekly[weekly.index < target].dropna(subset=["ma10"])
    if len(prior) < 2:
        return None
    for i in range(len(prior) - 1, 0, -1):
        prev = prior.iloc[i - 1]
        curr = prior.iloc[i]
        direction = _cross_direction(float(prev["close"]), float(prev["ma10"]), float(curr["close"]), float(curr["ma10"]))
        if direction:
            return {
                "cross_week": prior.index[i],
                "direction": direction,
                "ma10_at_cross": float(curr["ma10"]),
            }
    return None


def weeks_since_cross(cross_week: pd.Timestamp, week_start: pd.Timestamp) -> int:
    cross = _normalize_week(cross_week)
    target = _normalize_week(week_start)
    return int((target - cross).days // 7)


def compute_weekly_context(
    bars: pd.DataFrame,
    week_start: pd.Timestamp,
    *,
    min_range: float = 5.0,
    prior_weeks: int = 3,
) -> Optional[dict[str, object]]:
    weekly = weekly_bars_from_15m(bars)
    target = _normalize_week(week_start)
    if target not in weekly.index:
        return None

    prev_week = target - pd.Timedelta(days=7)
    if prev_week not in weekly.index:
        return None

    prev = weekly.loc[prev_week]
    doji_class, body_pct = classify_doji(prev, min_range=min_range)

    cross = latest_ma10_cross(weekly, target)
    weeks_since = None
    cross_direction = None
    cross_week = None
    ma10_at_cross = None
    if cross:
        cross_week = cross["cross_week"]
        cross_direction = cross["direction"]
        ma10_at_cross = cross["ma10_at_cross"]
        weeks_since = weeks_since_cross(cross_week, target)

    prior = weekly[(weekly.index >= target - pd.Timedelta(weeks=prior_weeks)) & (weekly.index < target)].copy()
    if len(prior) < prior_weeks:
        return None

    return {
        "prev_week": prev_week.date().isoformat(),
        "prev_doji": doji_class,
        "prev_body_pct": body_pct,
        "weeks_since_ma10_cross": weeks_since,
        "ma10_cross_direction": cross_direction,
        "ma10_cross_week": None if cross_week is None else cross_week.date().isoformat(),
        "ma10_at_cross": ma10_at_cross,
        "prior_weeks": prior,
    }


def _doji_label(doji_class: DojiClass) -> str:
    return {
        "invalid": "invalid (range too small)",
        "strong_doji": "strong doji (body <= 5% of range)",
        "doji": "doji (body <= 10% of range)",
        "small_body": "small body (body <= 20% of range)",
        "not_doji": "not doji",
    }[doji_class]


def draw_weekly_context_panel(
    fig,
    gs,
    row: int,
    context: dict[str, object],
    instrument: str,
) -> None:
    info_ax = fig.add_subplot(gs[row, 0])
    wk_ax = fig.add_subplot(gs[row, 1])

    info_ax.axis("off")
    lines = [
        "Previous weekly candle (PWC week %s)" % context["prev_week"],
        "Doji: %s (body %.1f%% of range)" % (_doji_label(context["prev_doji"]), 100.0 * float(context["prev_body_pct"])),
        "",
    ]
    if context["weeks_since_ma10_cross"] is None:
        lines.append("10W MA cross: none found before this week")
    else:
        lines.extend(
            [
                "Weeks since last 10W MA cross: %d" % int(context["weeks_since_ma10_cross"]),
                "Cross direction: %s" % str(context["ma10_cross_direction"]).upper(),
                "Cross week: %s" % context["ma10_cross_week"],
                "10W MA at cross: %.2f" % float(context["ma10_at_cross"]),
            ]
        )
    info_ax.text(
        0.02,
        0.98,
        "\n".join(lines),
        transform=info_ax.transAxes,
        va="top",
        ha="left",
        fontsize=9,
        family="monospace",
        bbox={"facecolor": "#f7f7f7", "edgecolor": "#cccccc", "alpha": 0.95, "pad": 6.0},
    )

    prior = context["prior_weeks"]
    plot_candles(wk_ax, prior, width_days=4.5)
    if context["ma10_at_cross"] is not None:
        wk_ax.axhline(float(context["ma10_at_cross"]), color="#0097a7", linestyle="-", linewidth=1.35, alpha=0.9, label="10W MA at cross")
    for ts, row in prior.iterrows():
        doji, _body_pct = classify_doji(row)
        if doji in {"strong_doji", "doji"}:
            x = mdates.date2num(ts.to_pydatetime())
            wk_ax.text(x, float(row["high"]), "D", color="#00695c", fontsize=8, ha="center", va="bottom", fontweight="bold")
    wk_ax.set_title("3 weekly candles before %s" % context.get("shown_week", ""), fontsize=9)
    wk_ax.set_ylabel(instrument, fontsize=8)
    wk_ax.grid(True, color="#e6e6e6", linewidth=0.5)
    wk_ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    if context["ma10_at_cross"] is not None:
        wk_ax.legend(loc="upper left", fontsize=7)
    for label in wk_ax.get_xticklabels():
        label.set_rotation(45)
        label.set_fontsize(7)
    wk_ax.set_xlabel("Week start (America/New_York)", fontsize=8)
