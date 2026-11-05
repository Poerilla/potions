"""Shared helpers for sanitized public track-record JSON (no symbols / fills)."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
START_EQUITY = 100_000.0
LIVE_UNITS_PER_LOT = 100_000
SIZE_UP_EXPOSURE_DD_FRAC = 0.40
JPY_USD = 110.0


def norm_live_qty(q: float) -> float:
    """Map legacy micro research qtys to current live units."""
    q = float(q)
    if q < 1_000:
        return q * float(LIVE_UNITS_PER_LOT)
    return q


def campaigns_from_unit_trades_fx(path: Path) -> pd.DataFrame:
    """FX research unit_trades: net column is quote-currency; cash≈USD = net / exit_price."""
    df = pd.read_csv(path)
    g = (
        df.groupby("trade_id", as_index=False)
        .agg(
            entry_ts=("entry_ts", "first"),
            exit_ts=("exit_ts", "last"),
            exit_price=("exit_price", "last"),
            net_quote=("net_usd", "sum"),
        )
        .sort_values("entry_ts")
    )
    g["entry_ts"] = pd.to_datetime(g["entry_ts"], utc=True)
    g["exit_ts"] = pd.to_datetime(g["exit_ts"], utc=True)
    g["cash_usd"] = g["net_quote"].astype(float) / g["exit_price"].astype(float)
    g["net_usd_published"] = g["net_quote"].astype(float) / float(JPY_USD)
    g["date"] = g["exit_ts"].dt.tz_convert("America/New_York").dt.date
    return g


def campaigns_from_unit_trades_usd(path: Path) -> pd.DataFrame:
    """Index/CFD unit_trades where net_usd is already ≈USD cash."""
    df = pd.read_csv(path)
    g = (
        df.groupby("trade_id", as_index=False)
        .agg(
            entry_ts=("entry_ts", "first"),
            exit_ts=("exit_ts", "last"),
            net_usd=("net_usd", "sum"),
        )
        .sort_values("entry_ts")
    )
    g["entry_ts"] = pd.to_datetime(g["entry_ts"], utc=True)
    g["exit_ts"] = pd.to_datetime(g["exit_ts"], utc=True)
    g["cash_usd"] = g["net_usd"].astype(float)
    g["date"] = g["exit_ts"].dt.tz_convert("America/New_York").dt.date
    return g


def campaigns_from_fills_fx(
    path: Path,
    *,
    point_value: float = 100_000.0,
    normalize_qty: bool = True,
) -> pd.DataFrame:
    """Rebuild campaign cash from FX fills (quote PnL × PV / exit mid)."""
    fills = pd.read_csv(path)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True)
    fills = fills.sort_values("ts")
    rows: List[Dict[str, Any]] = []
    for _tid, g in fills.groupby("trade_id", sort=False):
        g = g.sort_values("ts")
        entry = g[g["reason"] == "entry"]
        if entry.empty:
            continue
        entry = entry.iloc[0]
        open_lots: List[Tuple[str, float, float]] = []
        cash_quote = 0.0
        for _, r in g.iterrows():
            q = float(r["quantity"])
            if normalize_qty:
                q = norm_live_qty(q)
            px = float(r["price"])
            reason = str(r["reason"])
            side = str(r["side"])
            if reason == "entry":
                open_lots.append((side, q, px))
                continue
            remain = q
            while remain > 1e-6 and open_lots:
                oside, oq, opx = open_lots[0]
                take = min(remain, oq)
                move = (opx - px) if oside == "sell" else (px - opx)
                cash_quote += take * move * float(point_value)
                oq -= take
                remain -= take
                if oq <= 1e-6:
                    open_lots.pop(0)
                else:
                    open_lots[0] = (oside, oq, opx)
        last_px = float(g.iloc[-1]["price"])
        usd = cash_quote / last_px if last_px else 0.0
        exit_ts = g.iloc[-1]["ts"]
        rows.append(
            {
                "entry_ts": entry["ts"],
                "exit_ts": exit_ts,
                "cash_usd": float(usd),
                "date": exit_ts.tz_convert("America/New_York").date(),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["entry_ts", "exit_ts", "cash_usd", "date"])
    return pd.DataFrame(rows).sort_values("exit_ts").reset_index(drop=True)


def campaigns_from_fills_index(
    path: Path,
    *,
    normalize_qty: bool = False,
    base_entry_qty: Optional[float] = None,
) -> pd.DataFrame:
    """Index CFD fills: cash ≈ price move × qty (point value 1).

    When ``base_entry_qty`` is set, each campaign's cash is scaled by
    ``base_entry_qty / first_entry_qty`` so legacy research-unit practice fills
    (qty=1) report at the current default live base size.
    """
    fills = pd.read_csv(path)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True)
    fills = fills.sort_values("ts")
    rows: List[Dict[str, Any]] = []
    for _tid, g in fills.groupby("trade_id", sort=False):
        g = g.sort_values("ts")
        entry = g[g["reason"] == "entry"]
        if entry.empty:
            continue
        entry = entry.iloc[0]
        entry_qty = float(entry["quantity"])
        if normalize_qty:
            entry_qty = norm_live_qty(entry_qty)
        open_lots: List[Tuple[str, float, float]] = []
        cash = 0.0
        for _, r in g.iterrows():
            q = float(r["quantity"])
            if normalize_qty:
                q = norm_live_qty(q)
            px = float(r["price"])
            reason = str(r["reason"])
            side = str(r["side"])
            if reason == "entry":
                open_lots.append((side, q, px))
                continue
            remain = q
            while remain > 1e-6 and open_lots:
                oside, oq, opx = open_lots[0]
                take = min(remain, oq)
                if oside == "sell":
                    cash += take * (opx - px)
                else:
                    cash += take * (px - opx)
                oq -= take
                remain -= take
                if oq <= 1e-6:
                    open_lots.pop(0)
                else:
                    open_lots[0] = (oside, oq, opx)
        if base_entry_qty is not None and entry_qty > 1e-9:
            cash *= float(base_entry_qty) / entry_qty
        exit_ts = g.iloc[-1]["ts"]
        rows.append(
            {
                "entry_ts": entry["ts"],
                "exit_ts": exit_ts,
                "cash_usd": float(cash),
                "date": exit_ts.tz_convert("America/New_York").date(),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["entry_ts", "exit_ts", "cash_usd", "date"])
    return pd.DataFrame(rows).sort_values("exit_ts").reset_index(drop=True)


def daily_equity(campaigns: pd.DataFrame, pnl_col: str, start: float = START_EQUITY) -> pd.DataFrame:
    daily = campaigns.groupby("date", as_index=False)[pnl_col].sum().sort_values("date")
    daily["equity"] = start + daily[pnl_col].cumsum()
    return daily


def drawdown_stats(equity: pd.Series) -> Dict[str, float]:
    peak = equity.cummax()
    dd = equity - peak
    max_dd = float(dd.min()) if len(dd) else 0.0
    underwater = dd < -1e-9
    frac_uw = float(underwater.mean()) if len(underwater) else 0.0
    return {
        "max_dd_usd": max_dd,
        "max_dd_pct": max_dd / float(equity.iloc[0]) if len(equity) else 0.0,
        "time_underwater_pct": frac_uw,
    }


def sharpe_sortino(daily_rets: pd.Series, periods: int = 252) -> Tuple[float, float]:
    r = daily_rets.dropna()
    if len(r) < 5 or r.std() == 0:
        return 0.0, 0.0
    sharpe = float(r.mean() / r.std() * math.sqrt(periods))
    downside = r[r < 0]
    if len(downside) < 2 or downside.std() == 0:
        return sharpe, 0.0
    sortino = float(r.mean() / downside.std() * math.sqrt(periods))
    return sharpe, sortino


def apply_yearly_rolling_size_up(
    cash: pd.Series,
    dates: pd.Series,
    *,
    start_equity: float = START_EQUITY,
    exposure_dd_frac: float = SIZE_UP_EXPOSURE_DD_FRAC,
) -> Tuple[pd.Series, pd.Series, List[Dict[str, Any]], float]:
    years = pd.Series([d.year if hasattr(d, "year") else pd.Timestamp(d).year for d in dates])
    size = 1.0
    equity = float(start_equity)
    out: List[float] = []
    mults: List[float] = []
    events: List[Dict[str, Any]] = []
    year_sized: Dict[int, List[float]] = {}
    year_eq_path: Dict[int, List[float]] = {}
    seen_years: List[int] = []

    for pnl_1x, d, y in zip(cash.astype(float), dates, years.astype(int)):
        y = int(y)
        if not seen_years or y != seen_years[-1]:
            if seen_years and y < seen_years[-1]:
                raise ValueError("campaigns must be sorted by calendar year")
            if seen_years and y > seen_years[-1]:
                prev_y = seen_years[-1]
                prev_pnls = year_sized.get(prev_y) or []
                prev_eqs = year_eq_path.get(prev_y) or []
                if prev_pnls and prev_eqs:
                    pnl_y = float(sum(prev_pnls))
                    y_start = float(prev_eqs[0] - prev_pnls[0])
                    path = pd.Series([y_start] + list(prev_eqs), dtype=float)
                    dd_y = float((path - path.cummax()).min())
                    if abs(dd_y) > 1e-9 and pnl_y >= 2.0 * abs(dd_y) - 1e-9:
                        step = 2.0
                        if abs(dd_y) * 2.0 > float(exposure_dd_frac) * float(equity) + 1e-9:
                            step = 1.5
                        old = size
                        size = float(old * step)
                        events.append(
                            {
                                "effective_year": int(y),
                                "lookback_year": int(prev_y),
                                "from_mult": round(old, 6),
                                "to_mult": round(size, 6),
                                "step": float(step),
                                "lookback_pnl_usd": round(pnl_y, 2),
                                "lookback_dd_usd": round(dd_y, 2),
                                "threshold_usd": round(2.0 * abs(dd_y), 2),
                                "equity_at_review": round(float(equity), 2),
                            }
                        )
            seen_years.append(y)
            year_sized.setdefault(y, [])
            year_eq_path.setdefault(y, [])

        sized = float(pnl_1x) * size
        equity += sized
        out.append(sized)
        mults.append(size)
        year_sized[y].append(sized)
        year_eq_path[y].append(equity)

    return (
        pd.Series(out, index=cash.index),
        pd.Series(mults, index=cash.index),
        events,
        size,
    )


def fetch_spy(start: str, end: str) -> Optional[pd.DataFrame]:
    import urllib.request

    def _from_yahoo() -> Optional[pd.DataFrame]:
        try:
            t0 = int(pd.Timestamp(start, tz="UTC").timestamp())
            t1 = int(pd.Timestamp(end, tz="UTC").timestamp()) + 2 * 86400
            url = (
                "https://query1.finance.yahoo.com/v8/finance/chart/SPY"
                "?period1=%d&period2=%d&interval=1d&events=div" % (t0, t1)
            )
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 track-exporter"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            result = (body.get("chart") or {}).get("result") or []
            if not result:
                return None
            r0 = result[0]
            ts = r0.get("timestamp") or []
            adj = ((r0.get("indicators") or {}).get("adjclose") or [{}])[0].get("adjclose")
            close = ((r0.get("indicators") or {}).get("quote") or [{}])[0].get("close")
            px = adj or close
            if not ts or not px:
                return None
            rows = []
            for t, p in zip(ts, px):
                if p is None:
                    continue
                rows.append(
                    {
                        "date": pd.Timestamp(t, unit="s", tz="UTC").tz_convert("America/New_York").date(),
                        "close": float(p),
                    }
                )
            if not rows:
                return None
            return pd.DataFrame(rows)
        except Exception:
            return None

    out = _from_yahoo()
    if out is not None and not out.empty:
        return out
    try:
        import yfinance as yf  # type: ignore

        raw = yf.download("SPY", start=start, end=end, progress=False, auto_adjust=True)
        if raw is not None and not raw.empty:
            close = raw["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            df = close.reset_index()
            df.columns = ["date", "close"]
            df["date"] = pd.to_datetime(df["date"]).dt.date
            return df
    except Exception:
        pass
    return None


def spy_equity(spy: pd.DataFrame, start_eq: float = START_EQUITY) -> pd.DataFrame:
    s = spy.sort_values("date").copy()
    first = float(s["close"].iloc[0])
    s["equity"] = start_eq * (s["close"].astype(float) / first)
    return s


def path_kpis(daily: pd.DataFrame, equity_col: str = "equity") -> Dict[str, Any]:
    if daily is None or daily.empty:
        return {}
    strat_eq = daily[equity_col].astype(float)
    strat_rets = strat_eq.pct_change().fillna(0.0)
    dd = drawdown_stats(strat_eq)
    sharpe, sortino = sharpe_sortino(strat_rets)
    years = max((daily["date"].iloc[-1] - daily["date"].iloc[0]).days / 365.25, 1e-9)
    total_ret = float(strat_eq.iloc[-1] / START_EQUITY - 1.0)
    cagr = float((strat_eq.iloc[-1] / START_EQUITY) ** (1.0 / years) - 1.0) if years > 0 else 0.0
    max_dd_abs = abs(dd["max_dd_usd"])
    calmar = float(cagr / (max_dd_abs / START_EQUITY)) if max_dd_abs > 1e-9 else 0.0
    return {
        "end_equity": round(float(strat_eq.iloc[-1]), 2),
        "total_return": round(total_ret, 6),
        "cagr": round(cagr, 6),
        "max_dd_usd": round(dd["max_dd_usd"], 2),
        "max_dd_pct": round(dd["max_dd_pct"], 6),
        "vol_daily": round(float(strat_rets.std() * math.sqrt(252)), 6) if len(strat_rets) else 0.0,
        "sharpe": round(sharpe, 3),
        "sortino": round(sortino, 3),
        "calmar": round(calmar, 3),
        "parmar": round(calmar, 3),
        "time_underwater_pct": round(dd["time_underwater_pct"], 4),
        "n_points": int(len(daily)),
    }


def series_points(daily: pd.DataFrame, *, include_start: bool = True) -> List[Dict[str, Any]]:
    pts: List[Dict[str, Any]] = []
    if include_start and len(daily):
        first = daily["date"].iloc[0]
        start_d = (pd.Timestamp(first) - pd.Timedelta(days=1)).date()
        pts.append({"date": start_d.isoformat(), "equity": round(START_EQUITY, 2)})
    for d, e in zip(daily["date"], daily["equity"]):
        pts.append({"date": d.isoformat(), "equity": round(float(e), 2)})
    return pts


def _holding_hours(camps: pd.DataFrame) -> Optional[float]:
    if camps is None or camps.empty:
        return None
    if "entry_ts" not in camps.columns or "exit_ts" not in camps.columns:
        return None
    dur = (camps["exit_ts"] - camps["entry_ts"]).dt.total_seconds() / 3600.0
    dur = dur.dropna()
    if dur.empty:
        return None
    return float(dur.median())


def _trade_stats(camps: pd.DataFrame) -> Dict[str, Any]:
    if camps is None or camps.empty:
        return {}
    pnl = camps["cash_usd"].astype(float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]
    pf = float(wins.sum() / abs(losses.sum())) if len(losses) and abs(losses.sum()) > 1e-9 else None
    years = max(
        (camps["date"].iloc[-1] - camps["date"].iloc[0]).days / 365.25,
        1e-9,
    )
    hold_h = _holding_hours(camps)
    return {
        "n_trades": int(len(camps)),
        "trades_per_year": round(len(camps) / years, 1),
        "win_rate": round(float((pnl > 0).mean()), 4),
        "avg_trade_usd": round(float(pnl.mean()), 2),
        "profit_factor": round(pf, 3) if pf is not None else None,
        "avg_holding_hours": round(hold_h, 2) if hold_h is not None else None,
    }


def _monthly_matrix(daily: pd.DataFrame) -> Dict[str, Any]:
    """Calendar monthly returns (%) from additive $100k equity path."""
    if daily is None or daily.empty:
        return {"months": [], "years": [], "rows": []}
    d = daily.sort_values("date").copy()
    d["date"] = pd.to_datetime(d["date"])
    d["ym"] = d["date"].dt.to_period("M")
    # Month-end equity; start-of-month equity = prior month-end (or START).
    me = d.groupby("ym", as_index=False).last()
    eq = me["equity"].astype(float).tolist()
    periods = me["ym"].tolist()
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    by_year: Dict[int, Dict[int, float]] = {}
    prev_eq = START_EQUITY
    for per, e in zip(periods, eq):
        y = int(per.year)
        m = int(per.month)
        ret = float(e / prev_eq - 1.0) if prev_eq > 1e-9 else 0.0
        by_year.setdefault(y, {})[m] = ret
        prev_eq = float(e)
    years = sorted(by_year)
    rows = []
    for y in years:
        cells = []
        for m in range(1, 13):
            cells.append(None if m not in by_year[y] else round(by_year[y][m], 6))
        # Annual: product of (1+r) - 1 for months present, else None
        rets = [by_year[y][m] for m in range(1, 13) if m in by_year[y]]
        ann = None
        if rets:
            acc = 1.0
            for r in rets:
                acc *= 1.0 + r
            ann = round(acc - 1.0, 6)
        rows.append({"year": y, "months": cells, "annual": ann})
    # Best / worst month across sample
    flat = [(y, m, by_year[y][m]) for y in by_year for m in by_year[y]]
    best = max(flat, key=lambda t: t[2]) if flat else None
    worst = min(flat, key=lambda t: t[2]) if flat else None
    return {
        "months": months,
        "years": years,
        "rows": rows,
        "best_month": (
            {"year": best[0], "month": months[best[1] - 1], "return": round(best[2], 6)}
            if best
            else None
        ),
        "worst_month": (
            {"year": worst[0], "month": months[worst[1] - 1], "return": round(worst[2], 6)}
            if worst
            else None
        ),
    }


def _drawdown_series(daily: pd.DataFrame) -> List[Dict[str, Any]]:
    if daily is None or daily.empty:
        return []
    eq = daily["equity"].astype(float)
    peak = eq.cummax()
    dd_pct = (eq - peak) / peak.replace(0, pd.NA)
    # Weekly downsample for chart
    tmp = daily.copy()
    tmp["dd_pct"] = dd_pct.values
    tmp["week"] = pd.to_datetime(tmp["date"]).dt.to_period("W").astype(str)
    weekly = tmp.groupby("week", as_index=False).last()
    return [
        {"date": d.isoformat() if hasattr(d, "isoformat") else str(d), "dd_pct": round(float(v), 6)}
        for d, v in zip(weekly["date"], weekly["dd_pct"])
        if pd.notna(v)
    ]


def _enrich_kpis(daily: pd.DataFrame, camps: pd.DataFrame) -> Dict[str, Any]:
    k = path_kpis(daily)
    if not k:
        return k
    eq = daily["equity"].astype(float)
    dd = drawdown_stats(eq)
    # Current drawdown from last point
    peak = float(eq.cummax().iloc[-1])
    cur = float(eq.iloc[-1])
    k["current_dd_usd"] = round(cur - peak, 2)
    k["current_dd_pct"] = round((cur - peak) / peak, 6) if peak > 1e-9 else 0.0
    k["max_dd_pct"] = round(dd["max_dd_pct"], 6)
    # Yearly / monthly extremes from monthly matrix
    mm = _monthly_matrix(daily)
    if mm.get("best_month"):
        k["best_month"] = mm["best_month"]
    if mm.get("worst_month"):
        k["worst_month"] = mm["worst_month"]
    by_year = camps.copy()
    by_year["year"] = pd.to_datetime(by_year["date"]).dt.year
    yr_net = {int(y): float(v) for y, v in by_year.groupby("year")["cash_usd"].sum().items()}
    if yr_net:
        pos_years = sum(1 for v in yr_net.values() if v > 0)
        worst_year = min(yr_net.items(), key=lambda kv: kv[1])
        best_year = max(yr_net.items(), key=lambda kv: kv[1])
        k["positive_years_pct"] = round(pos_years / float(len(yr_net)), 4)
        k["worst_year"] = int(worst_year[0])
        k["worst_year_pnl_usd"] = round(float(worst_year[1]), 2)
        k["best_year"] = int(best_year[0])
        k["best_year_pnl_usd"] = round(float(best_year[1]), 2)
    k.update(_trade_stats(camps))
    return k


def build_track_payload(
    *,
    product_name: str,
    tab_id: str,
    camps: pd.DataFrame,
    demo: pd.DataFrame,
    overview: Dict[str, Any],
    assumptions: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Investor-facing tear-sheet payload: $100k additive, no size-ups, no benchmark."""
    if camps is None or camps.empty:
        raise ValueError(f"{tab_id}: empty backtest campaigns")

    camps = camps.sort_values("exit_ts").reset_index(drop=True)
    daily_bt = daily_equity(camps, "cash_usd")
    bt_kpis = _enrich_kpis(daily_bt, camps)

    by_year = camps.copy()
    by_year["year"] = pd.to_datetime(by_year["date"]).dt.year
    yr_net = {int(y): float(v) for y, v in by_year.groupby("year")["cash_usd"].sum().items()}
    yearly_rows: List[Dict[str, Any]] = []
    running = START_EQUITY
    for y in sorted(yr_net):
        sn = float(yr_net[y])
        running += sn
        yearly_rows.append(
            {
                "year": int(y),
                "strategy_pnl_usd": round(sn, 2),
                "strategy_return": round(sn / START_EQUITY, 6),
                "strategy_equity_end": round(running, 2),
            }
        )

    start_d = daily_bt["date"].iloc[0].isoformat()
    end_d = daily_bt["date"].iloc[-1].isoformat()

    # Weekly equity for long backtest chart
    daily2 = daily_bt.copy()
    daily2["week"] = pd.to_datetime(daily2["date"]).dt.to_period("W").astype(str)
    weekly = daily2.groupby("week", as_index=False).last()
    strat_series_bt = [
        {"date": d.isoformat(), "equity": round(float(e), 2)}
        for d, e in zip(weekly["date"], weekly["equity"])
    ]
    dd_series = _drawdown_series(daily_bt)
    monthly = _monthly_matrix(daily_bt)

    demo_daily = daily_equity(demo, "cash_usd") if demo is not None and len(demo) else pd.DataFrame()
    demo_series = series_points(demo_daily, include_start=True) if len(demo_daily) else []
    demo_kpis = path_kpis(demo_daily) if len(demo_daily) else {}
    live_window = {"start": None, "end": None}
    if demo is not None and len(demo):
        demo_kpis.update(_trade_stats(demo))
        demo_kpis["n_campaigns"] = int(len(demo))
        demo_kpis["net_usd"] = round(float(demo["cash_usd"].sum()), 2)
        demo_kpis["window_start"] = demo_daily["date"].iloc[0].isoformat()
        demo_kpis["window_end"] = demo_daily["date"].iloc[-1].isoformat()
        live_window = {"start": demo_kpis["window_start"], "end": demo_kpis["window_end"]}
        span_days = (demo_daily["date"].iloc[-1] - demo_daily["date"].iloc[0]).days
        if span_days < 45:
            for k_drop in ("cagr", "calmar", "parmar", "sharpe", "sortino", "vol_daily"):
                demo_kpis.pop(k_drop, None)

    assumptions = assumptions or {
        "returns": "Gross of management/performance fees; includes modeled transaction costs in the historical study.",
        "slippage": "Broker-style fills with conservative slippage/fee assumptions in the historical study.",
        "capital_path": "Growth of $100,000 additive path (no compounding of gains into larger size).",
        "capacity": "Not disclosed.",
        "minimum": "Not applicable — informational track record only.",
        "liquidity": "Strategy dependent; not a fund offering.",
    }

    return {
        "schema_version": 5,
        "product_name": product_name,
        "tab_id": tab_id,
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "disclaimer": (
            "LIVE/SIM results (top) are unaudited practice fills for this strategy only. "
            "BACKTEST results (bottom) are hypothetical historical performance — not an offer "
            "to invest and not a prediction of future results. Markets, rules, and trade-level "
            "details are intentionally undisclosed."
        ),
        "overview": overview,
        "windows": {
            "backtest": {"start": start_d, "end": end_d, "label": "BACKTEST"},
            "live": {
                "start": live_window["start"],
                "end": live_window["end"],
                "label": "LIVE / SIM (unaudited)",
            },
        },
        "assumptions": assumptions,
        "disclosures": [
            "Hypothetical performance has inherent limitations. Past performance does not guarantee future results.",
            "Live/sim results may differ from backtests due to market conditions, execution, and incomplete history.",
            "This page is informational only and is not a solicitation to invest in any fund, CTA, or managed account.",
            "Strategy rules, instruments, and trade details are intentionally undisclosed.",
        ],
        "methodology": {
            "start_equity_usd": START_EQUITY,
            "equity_construction": "additive",
            "equity_footnote": (
                "Growth of a hypothetical $100,000 starting balance. Campaign P&L is summed by "
                "session date (no compounding into larger size)."
            ),
            "n_campaigns": int(len(camps)),
        },
        "live": {
            "kpis": demo_kpis,
            "equity": demo_series,
            "note": "Unaudited practice results for this strategy sleeve only (not full-account P&L).",
        },
        "backtest": {
            "kpis": bt_kpis,
            "equity": strat_series_bt,
            "drawdown": dd_series,
            "monthly_returns": monthly,
            "yearly": yearly_rows,
            "note": "Hypothetical historical study. Separated from live/sim above.",
        },
        # Back-compat aliases used by older HTML (will be unused after tear-sheet rewrite)
        "practice_kpis": demo_kpis,
        "kpis": bt_kpis,
        "equity_practice": demo_series,
        "equity_strategy": strat_series_bt,
        "campaign_net_check_usd_1x": round(float(camps["cash_usd"].sum()), 2),
        "practice_net_check_usd": round(float(demo["cash_usd"].sum()), 2)
        if demo is not None and len(demo)
        else 0.0,
    }
