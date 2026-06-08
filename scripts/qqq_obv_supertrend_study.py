#!/usr/bin/env python3
"""QQQ OBV crossover + daily Supertrend study.

Default signal definition:
- OBV is calculated from adjusted daily close direction and raw Yahoo volume.
- OBV crossover is OBV crossing its 20-day SMA.
- Daily Supertrend is ATR(14) x 3.0 on adjusted OHLC.

This is a chart/research study, not an execution model.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_START = "2000-01-01"
DEFAULT_END = None


def money(value: float) -> str:
    return "$%s%s" % ("-" if value < 0 else "", format(abs(value), ",.0f"))


def pct(value: float) -> str:
    return "%.2f%%" % (value * 100.0)


def load_qqq_daily(start: str, end: str, cache_dir: Path, refresh: bool = False) -> pd.DataFrame:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / ("QQQ_%s_%s_daily.csv" % (start, end))
    if cache.exists() and not refresh:
        return pd.read_csv(cache, parse_dates=["date"])

    raw = _download_with_yfinance(start, end)
    source = "yfinance"
    if raw is None:
        raw = _download_with_yahoo_chart_api(start, end)
        source = "yahoo_chart_api"
    if raw.empty:
        raise RuntimeError("No QQQ daily rows returned for %s through %s" % (start, end))

    raw = raw.sort_values("date").dropna(subset=["close_raw", "adj_close"]).reset_index(drop=True)
    factor = pd.to_numeric(raw["adj_close"], errors="coerce") / pd.to_numeric(raw["close_raw"], errors="coerce")
    factor = factor.replace([np.inf, -np.inf], np.nan).fillna(1.0)
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(raw["date"]),
            "open_raw": pd.to_numeric(raw["open_raw"], errors="coerce"),
            "high_raw": pd.to_numeric(raw["high_raw"], errors="coerce"),
            "low_raw": pd.to_numeric(raw["low_raw"], errors="coerce"),
            "close_raw": pd.to_numeric(raw["close_raw"], errors="coerce"),
            "adj_close": pd.to_numeric(raw["adj_close"], errors="coerce"),
            "volume": pd.to_numeric(raw["volume"], errors="coerce").fillna(0.0),
            "data_source": source,
        }
    )
    out["open"] = out["open_raw"] * factor
    out["high"] = out["high_raw"] * factor
    out["low"] = out["low_raw"] * factor
    out["close"] = out["adj_close"]
    out = out[(out["date"] >= pd.to_datetime(start)) & (out["date"] <= pd.to_datetime(end))]
    out = out.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    out.to_csv(cache, index=False)
    return out


def _download_with_yfinance(start: str, end: str) -> Optional[pd.DataFrame]:
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return None
    # yfinance's end date is exclusive. Add a day so the requested end can appear.
    end_exclusive = (pd.Timestamp(end) + pd.Timedelta(days=1)).date().isoformat()
    data = yf.download("QQQ", start=start, end=end_exclusive, auto_adjust=False, progress=False)
    if data.empty:
        return None
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [col[0] for col in data.columns]
    data = data.reset_index()
    return pd.DataFrame(
        {
            "date": pd.to_datetime(data["Date"]).dt.tz_localize(None),
            "open_raw": data["Open"],
            "high_raw": data["High"],
            "low_raw": data["Low"],
            "close_raw": data["Close"],
            "adj_close": data["Adj Close"] if "Adj Close" in data.columns else data["Close"],
            "volume": data["Volume"],
        }
    )


def _download_with_yahoo_chart_api(start: str, end: str) -> pd.DataFrame:
    start_dt = dt.datetime.fromisoformat(start).replace(tzinfo=dt.timezone.utc)
    end_dt = (dt.datetime.fromisoformat(end) + dt.timedelta(days=2)).replace(tzinfo=dt.timezone.utc)
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/QQQ"
        "?period1=%d&period2=%d&interval=1d&events=history&includeAdjustedClose=true"
        % (int(start_dt.timestamp()), int(end_dt.timestamp()))
    )
    response = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    payload = response.json()
    result = payload.get("chart", {}).get("result", [])
    if not result:
        raise RuntimeError("No Yahoo chart data for QQQ: %s" % json.dumps(payload)[:400])
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
            }
        )
    return pd.DataFrame(rows)


def add_indicators(df: pd.DataFrame, obv_ma: int, atr_len: int, atr_mult: float) -> pd.DataFrame:
    out = compute_supertrend(df, atr_len=atr_len, multiplier=atr_mult)
    close = pd.to_numeric(out["close"], errors="coerce")
    volume = pd.to_numeric(out["volume"], errors="coerce").fillna(0.0)
    direction = np.sign(close.diff()).fillna(0.0)
    out["obv"] = (direction * volume).cumsum()
    out["obv_ma"] = out["obv"].rolling(obv_ma, min_periods=obv_ma).mean()
    out["obv_above_ma"] = out["obv"] > out["obv_ma"]
    prev_above = out["obv_above_ma"].shift(1).fillna(False)
    out["obv_bull_cross"] = out["obv_above_ma"] & ~prev_above & out["obv_ma"].notna()
    out["obv_bear_cross"] = ~out["obv_above_ma"] & prev_above & out["obv_ma"].notna()
    out["st_regime"] = np.where(out["supertrend_trend"] == 1, "bullish_st", "bearish_st")
    return out


def compute_supertrend(df: pd.DataFrame, atr_len: int = 14, multiplier: float = 3.0) -> pd.DataFrame:
    out = df.copy()
    high = pd.to_numeric(out["high"], errors="coerce")
    low = pd.to_numeric(out["low"], errors="coerce")
    close = pd.to_numeric(out["close"], errors="coerce")
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / float(atr_len), adjust=False, min_periods=atr_len).mean()
    hl2 = (high + low) / 2.0
    basic_upper = hl2 + multiplier * atr
    basic_lower = hl2 - multiplier * atr
    final_upper = pd.Series(index=out.index, dtype="float64")
    final_lower = pd.Series(index=out.index, dtype="float64")
    trend = pd.Series(index=out.index, dtype="int64")
    st = pd.Series(index=out.index, dtype="float64")
    for i in range(len(out)):
        if i == 0 or pd.isna(atr.iloc[i]):
            final_upper.iloc[i] = basic_upper.iloc[i]
            final_lower.iloc[i] = basic_lower.iloc[i]
            trend.iloc[i] = 1
            st.iloc[i] = np.nan
            continue
        prev_i = i - 1
        if pd.isna(final_upper.iloc[prev_i]) or basic_upper.iloc[i] < final_upper.iloc[prev_i] or close.iloc[prev_i] > final_upper.iloc[prev_i]:
            final_upper.iloc[i] = basic_upper.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[prev_i]
        if pd.isna(final_lower.iloc[prev_i]) or basic_lower.iloc[i] > final_lower.iloc[prev_i] or close.iloc[prev_i] < final_lower.iloc[prev_i]:
            final_lower.iloc[i] = basic_lower.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[prev_i]
        prev_trend = int(trend.iloc[prev_i]) if not pd.isna(trend.iloc[prev_i]) else 1
        if prev_trend == 1:
            trend.iloc[i] = -1 if close.iloc[i] < final_lower.iloc[i] else 1
        else:
            trend.iloc[i] = 1 if close.iloc[i] > final_upper.iloc[i] else -1
        st.iloc[i] = final_lower.iloc[i] if trend.iloc[i] == 1 else final_upper.iloc[i]
    out["atr"] = atr
    out["supertrend"] = st
    out["supertrend_trend"] = trend
    return out


def build_signal_table(df: pd.DataFrame, horizons: Iterable[int]) -> pd.DataFrame:
    rows = []
    for i, row in df.iterrows():
        side = ""
        if bool(row["obv_bull_cross"]):
            side = "bullish_obv_cross"
        elif bool(row["obv_bear_cross"]):
            side = "bearish_obv_cross"
        if not side:
            continue
        item: Dict[str, object] = {
            "date": row["date"],
            "signal": side,
            "st_regime": row["st_regime"],
            "close": float(row["close"]),
            "obv": float(row["obv"]),
            "obv_ma": float(row["obv_ma"]),
            "supertrend": float(row["supertrend"]) if not pd.isna(row["supertrend"]) else math.nan,
        }
        for h in horizons:
            if i + h < len(df):
                item["fwd_%dd_return" % h] = float(df.iloc[i + h]["close"] / row["close"] - 1.0)
            else:
                item["fwd_%dd_return" % h] = math.nan
        rows.append(item)
    return pd.DataFrame(rows)


def summarize_forward_returns(signals: pd.DataFrame, horizons: Iterable[int]) -> pd.DataFrame:
    rows = []
    if signals.empty:
        return pd.DataFrame()
    for keys, group in signals.groupby(["signal", "st_regime"], dropna=False):
        signal, regime = keys
        item: Dict[str, object] = {"signal": signal, "st_regime": regime, "signals": len(group)}
        for h in horizons:
            col = "fwd_%dd_return" % h
            vals = pd.to_numeric(group[col], errors="coerce").dropna()
            item["avg_%dd" % h] = float(vals.mean()) if not vals.empty else math.nan
            item["median_%dd" % h] = float(vals.median()) if not vals.empty else math.nan
            item["hit_%dd_pct" % h] = 100.0 * float((vals > 0).mean()) if not vals.empty else math.nan
        rows.append(item)
    return pd.DataFrame(rows).sort_values(["signal", "st_regime"])


def build_equity(df: pd.DataFrame) -> pd.DataFrame:
    out = df[["date", "close", "obv_above_ma", "supertrend_trend"]].copy()
    ret = pd.to_numeric(out["close"], errors="coerce").pct_change().fillna(0.0)
    obv_pos = out["obv_above_ma"].shift(1).fillna(False).astype(float)
    st_pos = (out["supertrend_trend"].shift(1).fillna(0) == 1).astype(float)
    combo_pos = obv_pos * st_pos
    out["buy_hold"] = (1.0 + ret).cumprod()
    out["obv_long"] = (1.0 + ret * obv_pos).cumprod()
    out["supertrend_long"] = (1.0 + ret * st_pos).cumprod()
    out["obv_and_st_long"] = (1.0 + ret * combo_pos).cumprod()
    out["buy_hold_exposure"] = 1.0
    out["obv_exposure"] = obv_pos
    out["st_exposure"] = st_pos
    out["combo_exposure"] = combo_pos
    return out


def summarize_equity(equity: pd.DataFrame, start_capital: float = 10000.0) -> pd.DataFrame:
    rows = []
    years = max((equity["date"].iloc[-1] - equity["date"].iloc[0]).days / 365.25, 1.0) if len(equity) > 1 else 1.0
    specs = [
        ("QQQ buy-and-hold", "buy_hold", "buy_hold_exposure"),
        ("OBV > OBV_MA", "obv_long", "obv_exposure"),
        ("Daily Supertrend bullish", "supertrend_long", "st_exposure"),
        ("OBV > OBV_MA and Supertrend bullish", "obv_and_st_long", "combo_exposure"),
    ]
    for name, col, exposure_col in specs:
        series = pd.to_numeric(equity[col], errors="coerce").dropna()
        if series.empty:
            continue
        end_mult = float(series.iloc[-1])
        dd = max_drawdown(series)
        rows.append(
            {
                "name": name,
                "start_capital": start_capital,
                "end_capital": start_capital * end_mult,
                "net": start_capital * (end_mult - 1.0),
                "cagr_pct": ((end_mult ** (1.0 / years)) - 1.0) * 100.0,
                "max_dd_pct": dd * 100.0,
                "net_over_dd": (end_mult - 1.0) / abs(dd) if dd < 0 else math.inf,
                "exposure_pct": 100.0 * float(pd.to_numeric(equity[exposure_col], errors="coerce").fillna(0.0).mean()),
            }
        )
    return pd.DataFrame(rows)


def max_drawdown(equity_mult: pd.Series) -> float:
    equity_mult = pd.to_numeric(equity_mult, errors="coerce").dropna()
    if equity_mult.empty:
        return 0.0
    return float((equity_mult / equity_mult.cummax() - 1.0).min())


def plot_candles(ax: plt.Axes, df: pd.DataFrame, width_days: float = 0.68) -> None:
    x = mdates.date2num(pd.to_datetime(df["date"]).dt.to_pydatetime())
    colors = np.where(df["close"] >= df["open"], "#168a5a", "#c43d3d")
    ax.vlines(x, df["low"], df["high"], color=colors, linewidth=0.8, alpha=0.9)
    for xi, o, c, color in zip(x, df["open"], df["close"], colors):
        bottom = min(float(o), float(c))
        height = max(abs(float(c) - float(o)), 0.01)
        ax.add_patch(
            plt.Rectangle((xi - width_days / 2.0, bottom), width_days, height, facecolor=color, edgecolor=color, linewidth=0.35, alpha=0.82)
        )


def plot_indicator_chart(df: pd.DataFrame, equity: pd.DataFrame, out: Path, title: str, last_bars: Optional[int] = None) -> None:
    plot = df.tail(last_bars).copy() if last_bars else df.copy()
    eq = equity[equity["date"].isin(plot["date"])].copy()
    fig, axes = plt.subplots(3, 1, figsize=(18, 11), sharex=True, gridspec_kw={"height_ratios": [4, 1.65, 1.8], "hspace": 0.05})
    ax, obv_ax, eq_ax = axes
    plot_candles(ax, plot, width_days=0.66 if len(plot) < 900 else 0.3)
    bull = plot["supertrend"].where(plot["supertrend_trend"] == 1)
    bear = plot["supertrend"].where(plot["supertrend_trend"] == -1)
    ax.plot(plot["date"], bull, color="#009c5b", linewidth=1.65, label="Daily ST bullish")
    ax.plot(plot["date"], bear, color="#d62728", linewidth=1.65, label="Daily ST bearish")
    bull_cross = plot[plot["obv_bull_cross"]]
    bear_cross = plot[plot["obv_bear_cross"]]
    ax.scatter(bull_cross["date"], bull_cross["low"] * 0.985, marker="^", s=42, color="#007f5f", label="OBV bull cross", zorder=7)
    ax.scatter(bear_cross["date"], bear_cross["high"] * 1.015, marker="v", s=42, color="#c1121f", label="OBV bear cross", zorder=7)
    ax.set_title(title)
    ax.set_ylabel("QQQ adj price")
    ax.grid(True, color="#e3e6e8", linewidth=0.55, alpha=0.75)
    ax.legend(loc="upper left", fontsize=8)

    scale = 1_000_000_000.0
    obv_ax.plot(plot["date"], plot["obv"] / scale, color="#1f3a93", linewidth=1.1, label="OBV / 1B")
    obv_ax.plot(plot["date"], plot["obv_ma"] / scale, color="#f97316", linewidth=1.05, label="OBV MA")
    obv_ax.axhline(0, color="#777", linewidth=0.6, alpha=0.55)
    obv_ax.set_ylabel("OBV")
    obv_ax.grid(True, color="#e6e6e6", linewidth=0.5, alpha=0.75)
    obv_ax.legend(loc="upper left", fontsize=8)

    eq_ax.plot(eq["date"], eq["buy_hold"], color="#111827", linewidth=1.2, label="Buy/hold")
    eq_ax.plot(eq["date"], eq["obv_long"], color="#2563eb", linewidth=1.0, label="OBV long")
    eq_ax.plot(eq["date"], eq["supertrend_long"], color="#16a34a", linewidth=1.0, label="ST long")
    eq_ax.plot(eq["date"], eq["obv_and_st_long"], color="#7c3aed", linewidth=1.15, label="OBV+ST long")
    eq_ax.set_ylabel("Equity x")
    eq_ax.grid(True, color="#e6e6e6", linewidth=0.5, alpha=0.75)
    eq_ax.legend(loc="upper left", fontsize=8, ncol=4)
    eq_ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3 if last_bars else 18))
    eq_ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    for label in eq_ax.get_xticklabels():
        label.set_rotation(65)
        label.set_fontsize(8)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=135, bbox_inches="tight")
    plt.close(fig)


def build_yearly_charts(df: pd.DataFrame, equity: pd.DataFrame, out_root: Path, obv_ma: int) -> List[Dict[str, object]]:
    rows = []
    charts = out_root / "charts" / "yearly"
    charts.mkdir(parents=True, exist_ok=True)
    for year, group in df.groupby(df["date"].dt.year):
        pad_start = group["date"].iloc[0] - pd.Timedelta(days=90)
        pad = df[(df["date"] >= pad_start) & (df["date"] <= group["date"].iloc[-1])].copy()
        rel = Path("charts") / "yearly" / ("%d.png" % int(year))
        plot_indicator_chart(pad, equity, out_root / rel, "QQQ OBV %dMA + Daily Supertrend - %d" % (obv_ma, int(year)), None)
        rows.append(
            {
                "year": int(year),
                "bars": len(group),
                "return_pct": float(group["close"].iloc[-1] / group["close"].iloc[0] - 1.0) * 100.0,
                "bull_crosses": int(group["obv_bull_cross"].sum()),
                "bear_crosses": int(group["obv_bear_cross"].sum()),
                "st_bull_pct": 100.0 * float((group["supertrend_trend"] == 1).mean()),
                "chart": str(rel),
            }
        )
    return rows


def write_report(
    out_root: Path,
    daily: pd.DataFrame,
    signals: pd.DataFrame,
    forward: pd.DataFrame,
    equity_summary: pd.DataFrame,
    yearly_rows: List[Dict[str, object]],
    obv_ma: int,
    atr_len: int,
    atr_mult: float,
) -> None:
    data_source = str(daily["data_source"].iloc[-1]) if "data_source" in daily.columns and not daily.empty else "unknown"
    lines = [
        "# QQQ OBV Crossover + Daily Supertrend Study",
        "",
        "Data: Yahoo daily QQQ adjusted OHLCV. Fetch method in this run: `%s`." % data_source,
        "Window: **%s through %s**." % (daily["date"].min().date().isoformat(), daily["date"].max().date().isoformat()),
        "",
        "Rules:",
        "",
        "- OBV uses adjusted close direction and raw Yahoo volume.",
        "- OBV crossover means OBV crossing its `%d`-day simple moving average." % obv_ma,
        "- Daily Supertrend is `ATR(%d) x %.1f` on adjusted OHLC." % (atr_len, atr_mult),
        "- Equity rows are close-to-close research states with next-session execution, no costs, and no shorting.",
        "",
        "## Equity State Summary",
        "",
        "| State | End Capital on $10k | Net | CAGR | Max DD | Net/DD | Exposure |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in equity_summary.iterrows():
        lines.append(
            "| {name} | {end} | {net} | {cagr:.2f}% | {dd:.2f}% | {ndd:.2f} | {exp:.1f}% |".format(
                name=row["name"],
                end=money(float(row["end_capital"])),
                net=money(float(row["net"])),
                cagr=float(row["cagr_pct"]),
                dd=float(row["max_dd_pct"]),
                ndd=float(row["net_over_dd"]),
                exp=float(row["exposure_pct"]),
            )
        )
    lines.extend(
        [
            "",
            "## Forward Return Summary",
            "",
            "| Signal | ST Regime | Count | Avg 5d | Hit 5d | Avg 20d | Hit 20d | Avg 60d | Hit 60d |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, row in forward.iterrows():
        lines.append(
            "| {signal} | {regime} | {count} | {avg5} | {hit5:.1f}% | {avg20} | {hit20:.1f}% | {avg60} | {hit60:.1f}% |".format(
                signal=row["signal"],
                regime=row["st_regime"],
                count=int(row["signals"]),
                avg5=pct(float(row["avg_5d"])) if not pd.isna(row["avg_5d"]) else "",
                hit5=float(row["hit_5d_pct"]),
                avg20=pct(float(row["avg_20d"])) if not pd.isna(row["avg_20d"]) else "",
                hit20=float(row["hit_20d_pct"]),
                avg60=pct(float(row["avg_60d"])) if not pd.isna(row["avg_60d"]) else "",
                hit60=float(row["hit_60d_pct"]),
            )
        )
    lines.extend(
        [
            "",
            "## Charts",
            "",
            "- [Recent indicator chart](charts/qqq_obv_supertrend_recent.png)",
            "- [Full-history indicator chart](charts/qqq_obv_supertrend_full.png)",
            "",
            "## Yearly Charts",
            "",
            "| Year | Bars | Return | Bull Crosses | Bear Crosses | ST Bull % | Chart |",
            "|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in yearly_rows:
        lines.append(
            "| {year} | {bars} | {return_pct:.1f}% | {bull_crosses} | {bear_crosses} | {st_bull_pct:.1f}% | [{chart}]({chart}) |".format(**row)
        )
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `QQQ_daily_obv_supertrend.csv`",
            "- `signals.csv`",
            "- `forward_return_summary.csv`",
            "- `equity_summary.csv`",
            "- `yearly_summary.csv`",
        ]
    )
    (out_root / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _at(values: List[object], idx: int) -> object:
    return values[idx] if idx < len(values) else None


def default_completed_end(today: Optional[dt.date] = None) -> str:
    day = today or dt.date.today()
    day = day - dt.timedelta(days=1)
    while day.weekday() >= 5:
        day = day - dt.timedelta(days=1)
    return day.isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build QQQ OBV crossover + daily Supertrend study.")
    parser.add_argument("--start", default=DEFAULT_START)
    parser.add_argument("--end", default=default_completed_end())
    parser.add_argument("--obv-ma", type=int, default=20)
    parser.add_argument("--atr-len", type=int, default=14)
    parser.add_argument("--atr-mult", type=float, default=3.0)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--output-root", type=Path, default=ROOT / "nq" / "case_studies" / "qqq_obv_supertrend_study")
    args = parser.parse_args()

    out_root = args.output_root
    out_root.mkdir(parents=True, exist_ok=True)
    daily = load_qqq_daily(args.start, args.end, ROOT / "data" / "benchmarks", refresh=args.refresh)
    daily = add_indicators(daily, args.obv_ma, args.atr_len, args.atr_mult)
    horizons = [5, 10, 20, 60]
    signals = build_signal_table(daily, horizons)
    forward = summarize_forward_returns(signals, horizons)
    equity = build_equity(daily)
    equity_summary = summarize_equity(equity)

    daily.to_csv(out_root / "QQQ_daily_obv_supertrend.csv", index=False)
    signals.to_csv(out_root / "signals.csv", index=False)
    forward.to_csv(out_root / "forward_return_summary.csv", index=False)
    equity.to_csv(out_root / "equity_curves.csv", index=False)
    equity_summary.to_csv(out_root / "equity_summary.csv", index=False)

    plot_indicator_chart(daily, equity, out_root / "charts" / "qqq_obv_supertrend_recent.png", "QQQ OBV %dMA + Daily Supertrend - recent" % args.obv_ma, last_bars=760)
    plot_indicator_chart(daily, equity, out_root / "charts" / "qqq_obv_supertrend_full.png", "QQQ OBV %dMA + Daily Supertrend - full history" % args.obv_ma, last_bars=None)
    yearly_rows = build_yearly_charts(daily, equity, out_root, args.obv_ma)
    pd.DataFrame(yearly_rows).to_csv(out_root / "yearly_summary.csv", index=False)
    write_report(out_root, daily, signals, forward, equity_summary, yearly_rows, args.obv_ma, args.atr_len, args.atr_mult)
    print("Wrote %s" % (out_root / "INDEX.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
