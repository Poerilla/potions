"""Instrument deep-check: yearly board + NQ-style robustness for one strategy book.

Works on broker-like Engine+PaperBroker state roots (fills / unit_trades / equity_curve)
and research sims that only ship ``trades.csv`` (e.g. London sweep reversal).

Outputs under ``<hub>/deep_check/<strategy_id>/``:

- ``YEARLY.md`` / ``yearly_breakdown.csv`` — net, stress, N/S, 100k-compounded return
- ``ROBUSTNESS_AUDIT.md`` — concentration, rolling, exits, timing, full-SL, regimes
- ``EMAIL.html`` + ``EMAIL.txt`` — HTML multipart bodies
- campaign / timing / exit CSVs + equity / rolling charts

Usage::

  python -m live.instrument_deep_check \\
    --state-root live/state/fx_v2b_asia_range_london/states/usdjpy_v2b_asia_range_london_S_1_1_3 \\
    --email

  python -m live.instrument_deep_check \\
    --state-root live/state/fx_london_sweep_reversal/states/usdjpy_london_sweep_1_1_1 \\
    --email
"""

from __future__ import annotations

import argparse
import html
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .fx_v2b_london_ungated import JPY_USD, MARKETS, REPO, _usd_norm
from .replay_audit import POINT_VALUES

NY = "America/New_York"
START_EQUITY = 100_000.0

# Futures / CFD fees when symbol is not in the FX MARKETS table used for London books.
_DEFAULT_FEE_PER_UNIT = {
    "NQ": 1.50,
    "MNQ": 1.50,
    "ES": 1.50,
    "MES": 1.50,
    "YM": 1.50,
    "MYM": 1.50,
    "NAS100": 1.50,
    "US30": 1.50,
    "SPX500": 1.50,
}


@dataclass(frozen=True)
class BookPaths:
    state_root: Path
    output_root: Path
    symbol: str
    quote: str
    strategy_id: str
    label: str
    fills: Optional[Path]
    unit_trades: Optional[Path]
    equity_curve: Optional[Path]
    orders: Optional[Path]
    trades_csv: Optional[Path]
    metrics: Optional[Path]
    daily: Optional[Path]
    point_value: float
    tick: float
    fee_per_unit: float


def money(value: float) -> str:
    return "$%s%.2f" % ("-" if value < 0 else "", abs(value))


def pct(value: float) -> str:
    return "%+.2f%%" % (100.0 * value)


def max_drawdown(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    peak = values.cummax()
    return float((values - peak).min())


def profit_factor(pnls: pd.Series) -> float:
    gains = float(pnls[pnls > 0].sum())
    losses = abs(float(pnls[pnls < 0].sum()))
    if losses == 0:
        return math.inf if gains > 0 else 0.0
    return gains / losses


def max_losing_streak(pnls: pd.Series) -> int:
    best = 0
    current = 0
    for value in pnls:
        if value < 0:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def _to_usd(series: pd.Series, quote: str) -> pd.Series:
    if quote == "JPY":
        return series.astype(float) / float(JPY_USD)
    return series.astype(float)


def _resolve_symbol(metrics: dict, state_root: Path) -> str:
    raw = metrics.get("symbol") or metrics.get("market") or state_root.name.split("_")[0]
    symbol = str(raw).upper()
    if symbol not in MARKETS and symbol.lower() in {"eurusd", "gbpusd", "usdjpy", "audjpy"}:
        symbol = symbol.upper()
    return symbol


def _resolve_market_economics(symbol: str, metrics: dict) -> Tuple[float, float, float, str]:
    """Return (point_value, tick, fee_per_unit, quote).

    Prefer FX MARKETS (London books), then replay_audit POINT_VALUES / broker ticks.
    Never silently default futures to the FX $100k lot — that 5000×-inflates NQ.
    """
    market = MARKETS.get(symbol)
    if market is not None:
        return (
            float(market.point_value),
            float(market.tick),
            float(market.fee_per_unit),
            str(metrics.get("quote") or market.quote),
        )
    if symbol not in POINT_VALUES:
        raise KeyError(
            "No point_value for %s (not in FX MARKETS or replay_audit.POINT_VALUES)" % symbol
        )
    tick = float(DEFAULT_TICK_SIZE.get(symbol, metrics.get("tick") or 0.00001))
    fee = float(metrics.get("fee_per_unit") or _DEFAULT_FEE_PER_UNIT.get(symbol, 7.0))
    quote = str(metrics.get("quote") or "USD")
    return float(POINT_VALUES[symbol]), tick, fee, quote


def _resolve_paths(
    state_root: Path,
    output_root: Optional[Path],
    label: Optional[str],
) -> BookPaths:
    state_root = state_root.resolve()
    metrics_path = state_root / "metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else {}
    symbol = _resolve_symbol(metrics, state_root)
    point_value, tick, fee_per_unit, quote = _resolve_market_economics(symbol, metrics)
    strategy_id = str(metrics.get("strategy_id") or state_root.name)
    hub = state_root.parent.parent if state_root.parent.name == "states" else state_root.parent
    out = output_root or (hub / "deep_check" / strategy_id)
    daily = REPO / "fx" / ("%s_daily.csv" % symbol.lower())
    return BookPaths(
        state_root=state_root,
        output_root=out,
        symbol=symbol,
        quote=quote,
        strategy_id=strategy_id,
        label=label or strategy_id,
        fills=state_root / "fills.csv" if (state_root / "fills.csv").exists() else None,
        unit_trades=state_root / "unit_trades.csv" if (state_root / "unit_trades.csv").exists() else None,
        equity_curve=state_root / "equity_curve.csv" if (state_root / "equity_curve.csv").exists() else None,
        orders=state_root / "orders.csv" if (state_root / "orders.csv").exists() else None,
        trades_csv=state_root / "trades.csv" if (state_root / "trades.csv").exists() else None,
        metrics=metrics_path if metrics_path.exists() else None,
        daily=daily if daily.exists() else None,
        point_value=point_value,
        tick=tick,
        fee_per_unit=fee_per_unit,
    )


def load_campaigns_from_fills(paths: BookPaths) -> pd.DataFrame:
    assert paths.fills is not None
    fills = pd.read_csv(paths.fills)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1).astype(int)
    entry_reasons = {"entry", "runner_entry", "add"}
    rows = []
    for trade_id, group in fills.sort_values("ts").groupby("trade_id"):
        # Prefer side for pyramid books (adds are buys, not exits).
        buys = group[group["side"].astype(str).str.lower() == "buy"]
        sells = group[group["side"].astype(str).str.lower() == "sell"]
        if buys.empty and sells.empty:
            # Legacy fallback: reason tags
            entries = group[group["reason"].astype(str).isin(entry_reasons)]
            exits = group[~group["reason"].astype(str).isin(entry_reasons)]
        else:
            entries = buys
            exits = sells
        if entries.empty or exits.empty:
            continue
        entry = entries.iloc[0]
        side = "long" if str(entry["side"]).lower() == "buy" else "short"
        entry_px = float(entry["price"])
        # Cost-basis PnL across all entry units vs their share of exits is approximate
        # when sizes pyramid; prefer unit_trades overlay when available.
        net_native = 0.0
        exit_reasons: List[str] = []
        remaining_entry_qty = int(entries["quantity"].sum())
        # Match sell qty against average entry for fill-only path
        avg_entry = float((entries["price"] * entries["quantity"]).sum() / max(1, entries["quantity"].sum()))
        for _idx, exit_row in exits.iterrows():
            qty = int(exit_row["quantity"])
            px = float(exit_row["price"])
            pts = px - avg_entry if side == "long" else avg_entry - px
            net_native += pts * paths.point_value * qty - paths.fee_per_unit * qty
            # Fee on entry side too (open + close)
            exit_reasons.append(str(exit_row["reason"]))
        # Entry fees
        net_native -= paths.fee_per_unit * float(entries["quantity"].sum())
        reason_set = sorted(set(exit_reasons))
        stop_tags = {"wide_stop", "stop", "runner_stop", "be_stop", "trail_stop", "boundary_stop"}
        full_sl = bool(reason_set) and all(r in stop_tags or r.endswith("_stop") for r in reason_set) and (
            "wide_stop" in reason_set or "stop" in reason_set or "trail_stop" in reason_set
        )
        # Full initial SL: every exit is wide_stop / stop (no TP, no EOD, no runner/BE salvage).
        full_initial_sl = bool(reason_set) and set(reason_set).issubset({"wide_stop", "stop"})
        rows.append(
            {
                "trade_id": str(trade_id),
                "session": pd.Timestamp(entry["ts"]).date().isoformat(),
                "year": int(pd.Timestamp(entry["ts"]).year),
                "side": side,
                "entry_ts": pd.Timestamp(entry["ts"]),
                "exit_ts": pd.Timestamp(exits["ts"].max()),
                "entry_price": entry_px,
                "entry_qty": int(entries["quantity"].sum()),
                "net_usd": float(_usd_norm(net_native, paths.quote)),
                "exit_reasons": ",".join(reason_set),
                "hit_tp": any(r.startswith("tp") or r == "target" for r in reason_set),
                "eod_close": any(r in {"eod_close", "eod"} for r in reason_set),
                "full_initial_sl": full_initial_sl,
                "any_stop_exit": any(r in stop_tags or "stop" in r for r in reason_set),
            }
        )
    return pd.DataFrame(rows).sort_values("entry_ts").reset_index(drop=True)


def load_campaigns_from_trades_csv(paths: BookPaths) -> pd.DataFrame:
    assert paths.trades_csv is not None
    raw = pd.read_csv(paths.trades_csv)
    raw["entry_ts"] = pd.to_datetime(raw["entry_ts"], utc=True).dt.tz_convert(NY)
    raw["exit_ts"] = pd.to_datetime(raw["exit_ts"], utc=True).dt.tz_convert(NY)
    raw["net_usd"] = _to_usd(pd.to_numeric(raw["net_usd"], errors="coerce").fillna(0.0), paths.quote)
    rows = []
    for idx, row in raw.iterrows():
        reason = str(row.get("exit_reason") or "")
        reasons = [p for p in reason.replace("+", ",").split(",") if p]
        # Full initial SL: pure ``stop`` (all units hit initial SL, no TP/BE/EOD mix).
        full_initial_sl = reason.strip() == "stop"
        session = str(row.get("session") or pd.Timestamp(row["entry_ts"]).date().isoformat())
        rows.append(
            {
                "trade_id": "%s_%s" % (paths.strategy_id, session),
                "session": session,
                "year": int(pd.Timestamp(row["entry_ts"]).year),
                "side": str(row.get("side") or "").lower(),
                "entry_ts": pd.Timestamp(row["entry_ts"]),
                "exit_ts": pd.Timestamp(row["exit_ts"]),
                "entry_price": float(row.get("entry_price") or 0.0),
                "entry_qty": 3,
                "net_usd": float(row["net_usd"]),
                "exit_reasons": reason,
                "hit_tp": any(r.startswith("tp") for r in reasons),
                "eod_close": any(r.startswith("eod") for r in reasons),
                "full_initial_sl": full_initial_sl,
                "any_stop_exit": "stop" in reason,
                "london_high": float(row["london_high"]) if "london_high" in raw.columns else np.nan,
                "london_low": float(row["london_low"]) if "london_low" in raw.columns else np.nan,
            }
        )
    return pd.DataFrame(rows).sort_values("entry_ts").reset_index(drop=True)


def _overlay_unit_trade_pnl(campaigns: pd.DataFrame, paths: BookPaths) -> pd.DataFrame:
    """Replace fill-recomputed $ with broker unit_trades nets (authoritative)."""
    assert paths.unit_trades is not None
    ut = pd.read_csv(paths.unit_trades)
    if "net_usd" not in ut.columns or "trade_id" not in ut.columns:
        return campaigns
    ut["net_usd"] = _to_usd(pd.to_numeric(ut["net_usd"], errors="coerce").fillna(0.0), paths.quote)
    by_trade = ut.groupby(ut["trade_id"].astype(str))["net_usd"].sum()
    out = campaigns.copy()
    mapped = out["trade_id"].astype(str).map(by_trade)
    if mapped.isna().any():
        missing = out.loc[mapped.isna(), "trade_id"].astype(str).unique().tolist()
        raise ValueError(
            "unit_trades missing net for trade_id(s): %s (refusing fill-recomputed $)"
            % ", ".join(missing[:8])
        )
    out["net_usd"] = mapped.astype(float)
    return out


def load_campaigns(paths: BookPaths) -> pd.DataFrame:
    if paths.fills is not None:
        campaigns = load_campaigns_from_fills(paths)
        if paths.unit_trades is not None:
            return _overlay_unit_trade_pnl(campaigns, paths)
        return campaigns
    if paths.trades_csv is not None:
        return load_campaigns_from_trades_csv(paths)
    raise FileNotFoundError("Need fills.csv or trades.csv under %s" % paths.state_root)


def yearly_from_equity(paths: BookPaths, campaigns: pd.DataFrame) -> pd.DataFrame:
    """Per-year net (from campaigns) + stress from equity curve when present."""
    trade_years = (
        campaigns.groupby("year")
        .agg(
            trades=("net_usd", "count"),
            net_usd=("net_usd", "sum"),
            win_rate_pct=("net_usd", lambda s: 100.0 * float((s > 0).mean())),
            profit_factor=("net_usd", profit_factor),
            closed_dd_usd=("net_usd", lambda s: max_drawdown(s.cumsum())),
        )
        .reset_index()
        .sort_values("year")
    )

    stress_by_year: Dict[int, float] = {}
    if paths.equity_curve is not None and paths.equity_curve.exists():
        eq = pd.read_csv(paths.equity_curve)
        eq["ts"] = pd.to_datetime(eq["ts"], utc=True).dt.tz_convert(NY)
        eq["year"] = eq["ts"].dt.year
        stress_col = "intrabar_stress_equity_usd"
        if stress_col not in eq.columns:
            stress_col = "close_equity_usd"
        eq[stress_col] = _to_usd(pd.to_numeric(eq[stress_col], errors="coerce").fillna(0.0), paths.quote)
        for year, g in eq.groupby("year"):
            # Year-local peak-to-trough on the stress equity path.
            stress_by_year[int(year)] = abs(max_drawdown(g[stress_col]))
    else:
        for row in trade_years.itertuples(index=False):
            stress_by_year[int(row.year)] = abs(float(row.closed_dd_usd))

    def _year_stress(y: int) -> float:
        if int(y) in stress_by_year:
            return -abs(float(stress_by_year[int(y)]))
        closed = float(trade_years.loc[trade_years["year"] == y, "closed_dd_usd"].iloc[0])
        return -abs(closed)

    trade_years["stress_dd_usd"] = trade_years["year"].map(_year_stress)
    trade_years["net_over_stress"] = trade_years.apply(
        lambda r: float(r["net_usd"]) / abs(float(r["stress_dd_usd"])) if float(r["stress_dd_usd"]) else 0.0,
        axis=1,
    )

    equity = START_EQUITY
    rets = []
    start_eqs = []
    end_eqs = []
    for row in trade_years.itertuples(index=False):
        start_eqs.append(equity)
        ret = float(row.net_usd) / equity if equity else 0.0
        rets.append(ret)
        equity = equity + float(row.net_usd)
        end_eqs.append(equity)
    trade_years["start_equity_100k"] = start_eqs
    trade_years["end_equity_100k"] = end_eqs
    trade_years["return_on_start_equity"] = rets
    return trade_years


def add_daily_atr(campaigns: pd.DataFrame, daily_path: Optional[Path]) -> pd.DataFrame:
    if daily_path is None or not daily_path.exists():
        campaigns = campaigns.copy()
        campaigns["atr14"] = np.nan
        return campaigns
    daily = pd.read_csv(daily_path, parse_dates=["date"]).sort_values("date")
    for col in ["open", "high", "low", "close"]:
        if col in daily.columns:
            daily[col] = pd.to_numeric(daily[col], errors="coerce")
    prev_close = daily["close"].shift(1)
    tr = pd.concat(
        [
            daily["high"] - daily["low"],
            (daily["high"] - prev_close).abs(),
            (daily["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    daily["atr14"] = tr.rolling(14).mean().shift(1)
    daily["session"] = daily["date"].dt.date.astype(str)
    return campaigns.merge(daily[["session", "atr14"]], on="session", how="left")


def add_range_width(campaigns: pd.DataFrame, paths: BookPaths) -> pd.DataFrame:
    out = campaigns.copy()
    if "london_high" in out.columns and "london_low" in out.columns:
        out["range_width"] = out["london_high"] - out["london_low"]
        out["range_label"] = "london_kz_width"
        return out
    # Asia / OR width from feature snapshots when present.
    snap = paths.state_root / "feature_snapshots.csv"
    if snap.exists():
        feat = pd.read_csv(snap)
        # Prefer asia range / OR high-low style columns if present.
        cols = {c.lower(): c for c in feat.columns}
        hi = cols.get("asia_high") or cols.get("or_high") or cols.get("range_high")
        lo = cols.get("asia_low") or cols.get("or_low") or cols.get("range_low")
        sess_col = cols.get("session") or cols.get("session_date") or cols.get("date")
        if hi and lo and sess_col:
            feat = feat[[sess_col, hi, lo]].copy()
            feat["session"] = pd.to_datetime(feat[sess_col], errors="coerce").dt.date.astype(str)
            feat["range_width"] = pd.to_numeric(feat[hi], errors="coerce") - pd.to_numeric(feat[lo], errors="coerce")
            feat = feat.dropna(subset=["session"]).drop_duplicates("session")
            out = out.merge(feat[["session", "range_width"]], on="session", how="left")
            out["range_label"] = "asia_or_width"
            return out
    out["range_width"] = np.nan
    out["range_label"] = "n/a"
    return out


def add_quartiles(df: pd.DataFrame, col: str, out_col: str) -> None:
    valid = pd.to_numeric(df[col], errors="coerce")
    if valid.notna().sum() < 4:
        df[out_col] = ""
        return
    try:
        df[out_col] = pd.qcut(valid, 4, labels=["Q1 low", "Q2", "Q3", "Q4 high"], duplicates="drop")
    except (ValueError, IndexError):
        df[out_col] = ""


def summarize_group(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    rows = []
    for key, g in df.groupby(group_col, dropna=False, observed=False):
        if str(key) in {"", "nan", "NaN"}:
            continue
        pnl = g["net_usd"]
        closed = max_drawdown(pnl.cumsum())
        rows.append(
            {
                group_col: str(key),
                "trades": len(g),
                "net_usd": float(pnl.sum()),
                "win_rate_pct": 100.0 * float((pnl > 0).mean()) if len(g) else 0.0,
                "profit_factor": profit_factor(pnl),
                "avg_trade": float(pnl.mean()) if len(g) else 0.0,
                "closed_dd_usd": closed,
                "net_over_closed_dd": float(pnl.sum()) / abs(closed) if closed else 0.0,
            }
        )
    return pd.DataFrame(rows)


def rolling_metrics(campaigns: pd.DataFrame, window: int = 50) -> pd.DataFrame:
    rows = []
    for i in range(window, len(campaigns) + 1):
        g = campaigns.iloc[i - window : i]
        pnl = g["net_usd"]
        dd = max_drawdown(pnl.cumsum())
        rows.append(
            {
                "end_entry_ts": g.iloc[-1]["entry_ts"],
                "end_trade_id": g.iloc[-1]["trade_id"],
                "window": window,
                "trades": len(g),
                "net_usd": float(pnl.sum()),
                "win_rate_pct": 100.0 * float((pnl > 0).mean()),
                "profit_factor": profit_factor(pnl),
                "closed_dd_usd": dd,
                "net_over_closed_dd": float(pnl.sum()) / abs(dd) if dd else 0.0,
            }
        )
    return pd.DataFrame(rows)


def timing_distributions(campaigns: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, dict]:
    c = campaigns.copy()
    c["entry_hm"] = c["entry_ts"].dt.strftime("%H:%M")
    c["exit_hm"] = c["exit_ts"].dt.strftime("%H:%M")
    c["entry_hour"] = c["entry_ts"].dt.hour
    c["exit_hour"] = c["exit_ts"].dt.hour
    entry = (
        c.groupby("entry_hour")
        .agg(trades=("net_usd", "count"), net_usd=("net_usd", "sum"), win_rate_pct=("net_usd", lambda s: 100.0 * float((s > 0).mean())))
        .reset_index()
        .sort_values("entry_hour")
    )
    exit_tbl = (
        c.groupby("exit_hour")
        .agg(trades=("net_usd", "count"), net_usd=("net_usd", "sum"), win_rate_pct=("net_usd", lambda s: 100.0 * float((s > 0).mean())))
        .reset_index()
        .sort_values("exit_hour")
    )
    summary = {
        "n_trades": int(len(c)),
        "pct_hit_tp": 100.0 * float(c["hit_tp"].mean()) if len(c) else 0.0,
        "pct_eod": 100.0 * float(c["eod_close"].mean()) if len(c) else 0.0,
        "pct_full_initial_sl": 100.0 * float(c["full_initial_sl"].mean()) if len(c) else 0.0,
        "full_initial_sl_count": int(c["full_initial_sl"].sum()) if len(c) else 0,
        "median_entry_hm": str(c["entry_hm"].mode().iloc[0]) if len(c) else "",
        "median_exit_hm": str(c["exit_hm"].mode().iloc[0]) if len(c) else "",
    }
    return entry, exit_tbl, summary


def exit_reason_contribution(paths: BookPaths, campaigns: pd.DataFrame) -> pd.DataFrame:
    if paths.unit_trades is not None and paths.unit_trades.exists():
        ut = pd.read_csv(paths.unit_trades)
        ut["net_usd"] = _to_usd(pd.to_numeric(ut["net_usd"], errors="coerce").fillna(0.0), paths.quote)
        return (
            ut.groupby("exit_reason", dropna=False)["net_usd"]
            .agg(units="count", net_usd="sum", avg_unit="mean")
            .reset_index()
            .sort_values("net_usd", ascending=False)
        )
    # Fall back to campaign exit_reason strings (London sweep).
    rows = []
    for reason, g in campaigns.groupby("exit_reasons"):
        rows.append(
            {
                "exit_reason": reason,
                "units": int(len(g)),
                "net_usd": float(g["net_usd"].sum()),
                "avg_unit": float(g["net_usd"].mean()) if len(g) else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values("net_usd", ascending=False)


def stop_slippage_audit(paths: BookPaths) -> pd.DataFrame:
    if paths.fills is None or paths.orders is None:
        return pd.DataFrame()
    fills = pd.read_csv(paths.fills)
    orders = pd.read_csv(paths.orders)
    if "broker_order_id" not in fills.columns or "broker_order_id" not in orders.columns:
        return pd.DataFrame()
    merged = fills.merge(
        orders[
            [
                c
                for c in ["broker_order_id", "trade_id", "side", "order_type", "quantity", "stop_price", "bracket_role"]
                if c in orders.columns
            ]
        ],
        on="broker_order_id",
        how="left",
        suffixes=("_fill", "_order"),
    )
    if "order_type" not in merged.columns:
        return pd.DataFrame()
    merged = merged[merged["order_type"].astype(str) == "stop"].copy()
    if merged.empty:
        return merged
    merged["price"] = pd.to_numeric(merged["price"], errors="coerce")
    merged["stop_price"] = pd.to_numeric(merged["stop_price"], errors="coerce")
    qty_col = "quantity_fill" if "quantity_fill" in merged.columns else "quantity"
    merged[qty_col] = pd.to_numeric(merged[qty_col], errors="coerce").fillna(0)
    side_col = "side_fill" if "side_fill" in merged.columns else "side"
    sell = merged[side_col].astype(str).str.lower().eq("sell")
    buy = merged[side_col].astype(str).str.lower().eq("buy")
    merged["adverse_slip_pts"] = 0.0
    merged.loc[sell, "adverse_slip_pts"] = (merged.loc[sell, "stop_price"] - merged.loc[sell, "price"]).clip(lower=0)
    merged.loc[buy, "adverse_slip_pts"] = (merged.loc[buy, "price"] - merged.loc[buy, "stop_price"]).clip(lower=0)
    merged["gap_beyond_1tick_pts"] = (merged["adverse_slip_pts"] - float(paths.tick)).clip(lower=0)
    merged["adverse_slip_usd"] = _to_usd(
        merged["adverse_slip_pts"] * paths.point_value * merged[qty_col], paths.quote
    )
    merged["gap_beyond_1tick_usd"] = _to_usd(
        merged["gap_beyond_1tick_pts"] * paths.point_value * merged[qty_col], paths.quote
    )
    return merged


def recovery_stats(paths: BookPaths) -> Dict[str, float]:
    if paths.equity_curve is None or not paths.equity_curve.exists():
        return {
            "max_recovery_bars": 0.0,
            "max_recovery_calendar_days": 0.0,
            "unresolved_recovery_calendar_days": 0.0,
            "bars_in_drawdown_pct": 0.0,
        }
    eq = pd.read_csv(paths.equity_curve)
    eq["ts"] = pd.to_datetime(eq["ts"], utc=True).dt.tz_convert(NY)
    eq["close_equity_usd"] = _to_usd(pd.to_numeric(eq["close_equity_usd"], errors="coerce").fillna(0.0), paths.quote)
    peak = -math.inf
    peak_ts: Optional[pd.Timestamp] = None
    current_start: Optional[pd.Timestamp] = None
    max_recovery_bars = 0
    max_recovery_days = 0
    unresolved_days = 0
    bars_in_dd = 0
    for row in eq.itertuples(index=False):
        value = float(row.close_equity_usd)
        ts = pd.Timestamp(row.ts)
        if value >= peak:
            if current_start is not None:
                max_recovery_bars = max(max_recovery_bars, bars_in_dd)
                max_recovery_days = max(max_recovery_days, (ts.date() - current_start.date()).days)
            peak = value
            peak_ts = ts
            current_start = None
            bars_in_dd = 0
        else:
            if current_start is None:
                current_start = peak_ts
                bars_in_dd = 0
            bars_in_dd += 1
    if current_start is not None and not eq.empty:
        unresolved_days = (pd.Timestamp(eq.iloc[-1]["ts"]).date() - current_start.date()).days
        max_recovery_bars = max(max_recovery_bars, bars_in_dd)
        max_recovery_days = max(max_recovery_days, unresolved_days)
    return {
        "max_recovery_bars": float(max_recovery_bars),
        "max_recovery_calendar_days": float(max_recovery_days),
        "unresolved_recovery_calendar_days": float(unresolved_days),
        "bars_in_drawdown_pct": 100.0
        * float((eq["close_equity_usd"] < eq["close_equity_usd"].cummax()).mean())
        if not eq.empty
        else 0.0,
    }


def write_plots(output_root: Path, campaigns: pd.DataFrame, rolling: pd.DataFrame, label: str) -> None:
    chart_dir = output_root / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    fig, (ax, dd_ax) = plt.subplots(2, 1, figsize=(14, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    x = campaigns["entry_ts"]
    equity = campaigns["net_usd"].cumsum()
    ax.plot(x, equity, color="#0f766e", linewidth=1.6, label="Campaign close equity")
    ax.set_title("%s campaign equity" % label)
    ax.grid(True, alpha=0.3)
    ax.legend()
    dd = equity - equity.cummax()
    dd_ax.fill_between(x, dd, 0, color="#dc2626", alpha=0.35)
    dd_ax.set_ylabel("DD")
    dd_ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.savefig(chart_dir / "campaign_equity_dd.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    if not rolling.empty:
        fig, axes = plt.subplots(3, 1, figsize=(14, 9), sharex=True)
        axes[0].plot(rolling["end_entry_ts"], rolling["profit_factor"], color="#2563eb")
        axes[0].axhline(1.0, color="#777", linestyle="--", linewidth=0.8)
        axes[0].set_title("Rolling 50-campaign PF")
        axes[1].plot(rolling["end_entry_ts"], rolling["win_rate_pct"], color="#16a34a")
        axes[1].set_title("Rolling 50-campaign win rate")
        axes[2].plot(rolling["end_entry_ts"], rolling["net_over_closed_dd"], color="#9333ea")
        axes[2].set_title("Rolling 50-campaign Net / closed-DD")
        for ax in axes:
            ax.grid(True, alpha=0.3)
        fig.autofmt_xdate()
        fig.savefig(chart_dir / "rolling_50_metrics.png", dpi=140, bbox_inches="tight")
        plt.close(fig)

    # Entry / exit hour histograms
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].hist(campaigns["entry_ts"].dt.hour, bins=np.arange(0, 25) - 0.5, color="#0f766e", edgecolor="white")
    axes[0].set_title("Entry hour (NY)")
    axes[0].set_xticks(range(0, 24, 2))
    axes[1].hist(campaigns["exit_ts"].dt.hour, bins=np.arange(0, 25) - 0.5, color="#b45309", edgecolor="white")
    axes[1].set_title("Exit hour (NY)")
    axes[1].set_xticks(range(0, 24, 2))
    for ax in axes:
        ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(chart_dir / "entry_exit_hour_hist.png", dpi=140, bbox_inches="tight")
    plt.close(fig)


def _md_table(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "_(empty)_"
    try:
        return df.to_markdown(index=False, floatfmt=".2f")
    except Exception:
        return "```\n%s\n```" % df.to_string(index=False)


def write_yearly_md(paths: BookPaths, yearly: pd.DataFrame, timing: dict) -> str:
    lines = [
        "# %s — year-by-year" % paths.label,
        "",
        "Starting equity compound path assumes **$100,000** at the first traded year.",
        "Stress is year-local peak-to-trough on intrabar stress equity when an equity curve exists;",
        "otherwise closed campaign DD is used as the stress proxy (same as London sweep hub).",
        "",
        "| year | trades | net | stress | N/S | win% | PF | start eq | year return | end eq |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in yearly.itertuples(index=False):
        lines.append(
            "| %d | %d | %s | %s | %.2f | %.1f | %.2f | %s | %s | %s |"
            % (
                int(row.year),
                int(row.trades),
                money(float(row.net_usd)),
                money(float(row.stress_dd_usd)),
                float(row.net_over_stress),
                float(row.win_rate_pct),
                float(row.profit_factor) if math.isfinite(float(row.profit_factor)) else 0.0,
                money(float(row.start_equity_100k)),
                pct(float(row.return_on_start_equity)),
                money(float(row.end_equity_100k)),
            )
        )
    lines += [
        "",
        "## Timing snapshot",
        "",
        "- Hit TP (any unit): **%.1f%%**" % timing["pct_hit_tp"],
        "- Reach EOD/flatten: **%.1f%%**" % timing["pct_eod"],
        "- Full initial SL losses: **%d** (%.1f%%)" % (timing["full_initial_sl_count"], timing["pct_full_initial_sl"]),
        "- Modal entry time: %s · modal exit time: %s" % (timing["median_entry_hm"], timing["median_exit_hm"]),
        "",
    ]
    text = "\n".join(lines)
    (paths.output_root / "YEARLY.md").write_text(text, encoding="utf-8")
    return text


def write_robustness_md(
    paths: BookPaths,
    campaigns: pd.DataFrame,
    yearly: pd.DataFrame,
    rolling: pd.DataFrame,
    unit_contrib: pd.DataFrame,
    stop_audit: pd.DataFrame,
    recovery: Dict[str, float],
    quartiles: Dict[str, pd.DataFrame],
    timing: dict,
    prior_opposed: bool,
) -> str:
    total_net = float(campaigns["net_usd"].sum())
    top10 = campaigns.nlargest(10, "net_usd")
    worst10 = campaigns.nsmallest(10, "net_usd")
    top10_net = float(top10["net_usd"].sum())
    worst10_net = float(worst10["net_usd"].sum())
    rolling_bad = rolling[rolling["profit_factor"] < 1.0] if not rolling.empty else pd.DataFrame()
    stop_gap = float(stop_audit["gap_beyond_1tick_usd"].sum()) if not stop_audit.empty else 0.0
    stop_slip = float(stop_audit["adverse_slip_usd"].sum()) if not stop_audit.empty else 0.0

    concerns = []
    if total_net and top10_net / total_net > 0.45:
        concerns.append("Top-10 winners contribute more than 45% of total net.")
    if not rolling_bad.empty:
        concerns.append("%d rolling 50-campaign windows have PF < 1.0." % len(rolling_bad))
    if yearly["net_usd"].min() < 0:
        concerns.append("At least one calendar year is net-negative.")
    if not yearly.empty and yearly["net_over_stress"].min() < 1.0:
        weak = yearly.sort_values("net_over_stress").iloc[0]
        concerns.append(
            "Weakest year is %s: %s net, %.2f N/S."
            % (str(int(weak["year"])), money(float(weak["net_usd"])), float(weak["net_over_stress"]))
        )
    if stop_gap > abs(total_net) * 0.10 and stop_gap > 0:
        concerns.append("Gap-through stop damage is more than 10% of |net|.")
    if timing["pct_full_initial_sl"] > 25:
        concerns.append("Full initial SL share is high (%.1f%%)." % timing["pct_full_initial_sl"])
    if not concerns:
        concerns.append("No single audit bucket broke the model; still paper-parity before live size.")

    lines = [
        "# %s — instrument deep-check / robustness" % paths.label,
        "",
        "Adapted from the NQ prior-opposed robustness audit. Prior-opposed gap/OR filters are %s."
        % ("included" if prior_opposed else "**not applicable** — skipped"),
        "",
        "## Headline",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Campaigns | %d |" % len(campaigns),
        "| Net | %s |" % money(total_net),
        "| Campaign closed DD | %s |" % money(max_drawdown(campaigns["net_usd"].cumsum())),
        "| Win rate | %.2f%% |" % (100.0 * float((campaigns["net_usd"] > 0).mean())),
        "| Profit factor | %.3f |" % profit_factor(campaigns["net_usd"]),
        "| Avg trade | %s |" % money(float(campaigns["net_usd"].mean())),
        "| Median trade | %s |" % money(float(campaigns["net_usd"].median())),
        "| Max losing streak | %d |" % max_losing_streak(campaigns["net_usd"]),
        "| Full initial SL losses | %d (%.1f%%) |"
        % (timing["full_initial_sl_count"], timing["pct_full_initial_sl"]),
        "| Hit TP (any) | %.1f%% |" % timing["pct_hit_tp"],
        "| EOD / flatten | %.1f%% |" % timing["pct_eod"],
        "",
        "## Fragility",
        "",
    ]
    for item in concerns:
        lines.append("- %s" % item)
    lines += [
        "",
        "## Concentration",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Top 10 winners net | %s |" % money(top10_net),
        "| Top 10 share of net | %.2f%% |" % (100.0 * top10_net / total_net if total_net else 0.0),
        "| Worst 10 losers net | %s |" % money(worst10_net),
        "| Worst 10 share of |net| | %.2f%% |" % (100.0 * abs(worst10_net) / abs(total_net) if total_net else 0.0),
        "",
        "## Execution fragility",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Stop adverse fill cost | %s |" % money(stop_slip),
        "| Gap-through beyond 1 tick | %s |" % money(stop_gap),
        "| Filled stop count | %d |" % len(stop_audit),
        "",
        "## Recovery",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Max recovery bars | %.0f |" % recovery["max_recovery_bars"],
        "| Max recovery calendar days | %.0f |" % recovery["max_recovery_calendar_days"],
        "| Unresolved recovery days | %.0f |" % recovery["unresolved_recovery_calendar_days"],
        "| Bars in close-equity DD | %.2f%% |" % recovery["bars_in_drawdown_pct"],
        "",
        "## Yearly stability",
        "",
        _md_table(
            yearly[
                [
                    "year",
                    "trades",
                    "net_usd",
                    "stress_dd_usd",
                    "net_over_stress",
                    "win_rate_pct",
                    "profit_factor",
                    "return_on_start_equity",
                ]
            ]
        ),
        "",
        "## Rolling stability (50)",
        "",
        "- Windows: %d" % len(rolling),
        "- Worst rolling PF: %.3f" % (float(rolling["profit_factor"].min()) if not rolling.empty else 0.0),
        "- Worst rolling Net/closed-DD: %.2f"
        % (float(rolling["net_over_closed_dd"].min()) if not rolling.empty else 0.0),
        "- Rolling PF < 1.0 count: %d" % len(rolling_bad),
        "",
        "## Exit dependency",
        "",
        _md_table(unit_contrib),
        "",
        "## Cross-regime quartiles",
        "",
    ]
    for name, table in quartiles.items():
        lines += ["### %s" % name, "", _md_table(table), ""]
    lines += [
        "## Files",
        "",
        "- `yearly_breakdown.csv`",
        "- `campaigns_robustness.csv`",
        "- `rolling_50.csv`",
        "- `exit_reason_contribution.csv`",
        "- `entry_hour_dist.csv` / `exit_hour_dist.csv`",
        "- `charts/`",
        "",
    ]
    text = "\n".join(lines)
    (paths.output_root / "ROBUSTNESS_AUDIT.md").write_text(text, encoding="utf-8")
    return text


def _html_escape_md_table(md: str) -> str:
    # Very small markdown-table → HTML converter for email.
    lines = [ln for ln in md.splitlines() if ln.strip().startswith("|")]
    if len(lines) < 2:
        return "<pre>%s</pre>" % html.escape(md)
    header = [c.strip() for c in lines[0].strip("|").split("|")]
    body_lines = lines[2:] if len(lines) > 2 and set(lines[1].replace("|", "").replace("-", "").replace(":", "").strip()) <= {""} else lines[1:]
    out = ['<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;font-family:Menlo,Consolas,monospace;font-size:12px">']
    out.append("<thead><tr>" + "".join("<th>%s</th>" % html.escape(h) for h in header) + "</tr></thead><tbody>")
    for ln in body_lines:
        cols = [c.strip() for c in ln.strip("|").split("|")]
        out.append("<tr>" + "".join("<td>%s</td>" % html.escape(c) for c in cols) + "</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def write_email_bodies(paths: BookPaths, yearly: pd.DataFrame, timing: dict, campaigns: pd.DataFrame) -> Tuple[str, str]:
    total_net = float(campaigns["net_usd"].sum())
    weak = yearly.sort_values("net_over_stress").iloc[0] if not yearly.empty else None
    text_lines = [
        "potions: deep-check %s" % paths.label,
        "",
        "Hub: %s" % paths.output_root,
        "State: %s" % paths.state_root,
        "Net=%s  trades=%d  full_SL=%d (%.1f%%)  hit_TP=%.1f%%  EOD=%.1f%%"
        % (
            money(total_net),
            len(campaigns),
            timing["full_initial_sl_count"],
            timing["pct_full_initial_sl"],
            timing["pct_hit_tp"],
            timing["pct_eod"],
        ),
        "",
        "Year | net | stress | N/S | ret on start eq",
    ]
    for row in yearly.itertuples(index=False):
        text_lines.append(
            "%d | %s | %s | %.2f | %s"
            % (
                int(row.year),
                money(float(row.net_usd)),
                money(float(row.stress_dd_usd)),
                float(row.net_over_stress),
                pct(float(row.return_on_start_equity)),
            )
        )
    if weak is not None:
        text_lines += [
            "",
            "Weakest N/S year: %d (%s net, N/S=%.2f)"
            % (int(weak["year"]), money(float(weak["net_usd"])), float(weak["net_over_stress"])),
        ]
    text_lines += [
        "",
        "End equity if $100k at year-1 start: %s" % money(float(yearly.iloc[-1]["end_equity_100k"])) if not yearly.empty else "",
        "",
        "See YEARLY.md + ROBUSTNESS_AUDIT.md in hub.",
    ]
    text = "\n".join([ln for ln in text_lines if ln is not None])

    yearly_md = _md_table(
        yearly[
            [
                "year",
                "trades",
                "net_usd",
                "stress_dd_usd",
                "net_over_stress",
                "return_on_start_equity",
                "start_equity_100k",
                "end_equity_100k",
            ]
        ].assign(return_on_start_equity=lambda d: d["return_on_start_equity"].map(lambda x: round(100.0 * x, 2)))
    )
    html_body = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>%(title)s</title></head>
<body style="font-family:Georgia,serif;color:#111;max-width:900px">
<h1 style="font-size:20px">%(title)s</h1>
<p><b>State</b>: <code>%(state)s</code><br/>
<b>Deep-check hub</b>: <code>%(hub)s</code></p>
<p>Net <b>%(net)s</b> · trades %(n)d · full initial SL <b>%(full_sl)d</b> (%(full_sl_pct).1f%%)
· hit TP %(tp).1f%% · EOD %(eod).1f%%</p>
<h2>Year-by-year</h2>
%(yearly_table)s
<p style="font-size:13px;color:#444">return_on_start_equity is %% of equity at year start, compounding from $100,000 at year 1.
stress_dd_usd is year-local peak-to-trough (negative).</p>
<p>Modal entry %(entry)s · modal exit %(exit)s</p>
</body></html>
""" % {
        "title": html.escape("potions deep-check: %s" % paths.label),
        "state": html.escape(str(paths.state_root)),
        "hub": html.escape(str(paths.output_root)),
        "net": html.escape(money(total_net)),
        "n": len(campaigns),
        "full_sl": timing["full_initial_sl_count"],
        "full_sl_pct": timing["pct_full_initial_sl"],
        "tp": timing["pct_hit_tp"],
        "eod": timing["pct_eod"],
        "yearly_table": _html_escape_md_table(yearly_md),
        "entry": html.escape(str(timing["median_entry_hm"])),
        "exit": html.escape(str(timing["median_exit_hm"])),
    }
    (paths.output_root / "EMAIL.txt").write_text(text + "\n", encoding="utf-8")
    (paths.output_root / "EMAIL.html").write_text(html_body, encoding="utf-8")
    return text, html_body


def run_deep_check(
    state_root: Path,
    *,
    output_root: Optional[Path] = None,
    label: Optional[str] = None,
    prior_opposed: bool = False,
    force: bool = True,
    email: bool = False,
) -> Path:
    paths = _resolve_paths(state_root, output_root, label)
    if force and paths.output_root.exists():
        shutil.rmtree(paths.output_root)
    paths.output_root.mkdir(parents=True, exist_ok=True)

    campaigns = load_campaigns(paths)
    campaigns = add_daily_atr(campaigns, paths.daily)
    campaigns = add_range_width(campaigns, paths)
    add_quartiles(campaigns, "atr14", "atr14_quartile")
    if campaigns["range_width"].notna().any():
        add_quartiles(campaigns, "range_width", "range_width_quartile")
    else:
        campaigns["range_width_quartile"] = ""

    yearly = yearly_from_equity(paths, campaigns)
    rolling = rolling_metrics(campaigns, 50)
    unit_contrib = exit_reason_contribution(paths, campaigns)
    stop_audit = stop_slippage_audit(paths)
    recovery = recovery_stats(paths)
    entry_hour, exit_hour, timing = timing_distributions(campaigns)

    quartiles: Dict[str, pd.DataFrame] = {
        "ATR14 quartile": summarize_group(campaigns, "atr14_quartile"),
    }
    if campaigns["range_width_quartile"].astype(str).str.len().gt(0).any():
        label_range = str(campaigns["range_label"].iloc[0]) if "range_label" in campaigns.columns else "range"
        quartiles["%s quartile" % label_range] = summarize_group(campaigns, "range_width_quartile")
    if prior_opposed:
        # Placeholder: caller can pre-merge gap/OR columns named gap_pts / or_width_pts.
        if "gap_pts" in campaigns.columns:
            add_quartiles(campaigns, "gap_pts", "gap_quartile")
            quartiles["Opening gap quartile"] = summarize_group(campaigns, "gap_quartile")
        if "or_width_pts" in campaigns.columns:
            add_quartiles(campaigns, "or_width_pts", "or_width_quartile")
            quartiles["Opening range width quartile"] = summarize_group(campaigns, "or_width_quartile")

    campaigns.to_csv(paths.output_root / "campaigns_robustness.csv", index=False)
    yearly.to_csv(paths.output_root / "yearly_breakdown.csv", index=False)
    rolling.to_csv(paths.output_root / "rolling_50.csv", index=False)
    unit_contrib.to_csv(paths.output_root / "exit_reason_contribution.csv", index=False)
    entry_hour.to_csv(paths.output_root / "entry_hour_dist.csv", index=False)
    exit_hour.to_csv(paths.output_root / "exit_hour_dist.csv", index=False)
    if not stop_audit.empty:
        stop_audit.to_csv(paths.output_root / "stop_slippage_audit.csv", index=False)
    campaigns.nlargest(10, "net_usd").to_csv(paths.output_root / "top_10_winners.csv", index=False)
    campaigns.nsmallest(10, "net_usd").to_csv(paths.output_root / "worst_10_losers.csv", index=False)
    for name, table in quartiles.items():
        table.to_csv(paths.output_root / ("%s.csv" % name.lower().replace(" ", "_")), index=False)

    write_plots(paths.output_root, campaigns, rolling, paths.label)
    write_yearly_md(paths, yearly, timing)
    write_robustness_md(
        paths, campaigns, yearly, rolling, unit_contrib, stop_audit, recovery, quartiles, timing, prior_opposed
    )
    text, html_body = write_email_bodies(paths, yearly, timing, campaigns)

    try:
        from .run_ledger import log_run, metrics_from_yearly_csv

        total_net = float(campaigns["net_usd"].sum()) if "net_usd" in campaigns.columns else 0.0
        yearly_path = paths.output_root / "yearly_breakdown.csv"
        ymetrics = metrics_from_yearly_csv(yearly_path)
        # Whole-book stress proxy: sum of |year stress| or campaign closed DD.
        stress = 0.0
        if "stress_dd_usd" in yearly.columns and not yearly.empty:
            stress = -float(yearly["stress_dd_usd"].abs().sum())
        close_dd = None
        if "closed_dd_usd" in campaigns.columns and not campaigns.empty:
            close_dd = -float(campaigns["closed_dd_usd"].abs().max())
        ns = (total_net / abs(stress)) if abs(stress) > 1e-12 else 0.0
        instrument = ""
        parent_slug = ""
        metrics_json = paths.state_root / "metrics.json"
        if metrics_json.exists():
            try:
                mj = json.loads(metrics_json.read_text())
                instrument = str(mj.get("instrument") or "")
                parent_slug = str(mj.get("variant_slug") or mj.get("strategy_id") or "")
            except Exception:
                instrument = ""
        if not instrument:
            # Heuristic from state root name / parent hub.
            instrument = str(paths.label or "").split()[0].upper() if paths.label else ""
        log_run(
            run_class="deep_check",
            variant_slug=str(paths.output_root.name),
            instrument=instrument,
            hub_path=paths.output_root,
            engine="deep_check",
            parent_run_id="",
            net_usd=total_net,
            stress_dd_usd=stress,
            close_mtm_dd_usd=close_dd,
            ns=ns,
            trades=int(len(campaigns)),
            yearly_csv_path=yearly_path,
            equity_curve_path=paths.equity_curve,
            meta={
                "state_root": str(paths.state_root),
                "parent_variant_slug": parent_slug or paths.state_root.name,
                "label": paths.label,
                "prior_opposed": bool(prior_opposed),
                "full_initial_sl_pct": timing.get("pct_full_initial_sl"),
                "n_years": ymetrics.get("n_years"),
                "avg_yearly_ns": ymetrics.get("avg_yearly_ns"),
            },
            notes="instrument_deep_check",
            **{k: v for k, v in ymetrics.items() if k.startswith("avg_yearly") or k == "n_years"},
        )
    except Exception as exc:
        print("run_ledger skip: %s" % exc, flush=True)

    if email:
        from .notify_email import send_email

        send_email(
            subject="potions: deep-check %s" % paths.label,
            body=text,
            html=html_body,
        )
        print("email sent", flush=True)

    print("Wrote %s" % (paths.output_root / "ROBUSTNESS_AUDIT.md"), flush=True)
    return paths.output_root


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state-root", type=Path, required=True)
    ap.add_argument("--output-root", type=Path, default=None)
    ap.add_argument("--label", default=None)
    ap.add_argument("--prior-opposed", action="store_true", help="Include gap/OR quartile sections when columns exist")
    ap.add_argument("--no-force", action="store_true")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    run_deep_check(
        args.state_root,
        output_root=args.output_root,
        label=args.label,
        prior_opposed=args.prior_opposed,
        force=not args.no_force,
        email=args.email,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
