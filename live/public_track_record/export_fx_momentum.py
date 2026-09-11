"""Export sanitized FX Momentum public track-record JSON (no instrument / fills).

Hero series: practice/demo sleeve only, quantities normalized to the current
live lot size (research book × 100k units). Short window → daily / per-campaign
points (not weekly).

Backtest series (page bottom): same lot-cash scale from research unit_trades
(``net / exit_price``), with **yearly rolling** permanent size-ups: year 1 is
base size; at each later year-start, if prior-year PnL ≥ 2×|prior-year max DD|
(lookback only — never full-sample lookahead DD), multiply size by 2× (or 1.5×
when a full double would push exposure too far). Never sizes down; ups can
repeat indefinitely. Yearly table uses that sized path.

Does not publish symbols, session names, trade ids, or broker links.

Usage:
  PYTHONPATH=... python -m live.public_track_record.export_fx_momentum \\
    --out /path/to/fx-momentum-track/docs/data/fx_momentum.json
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
HUB_UNIT = (
    REPO
    / "live"
    / "state"
    / "fx_v2b_asia_range_london_usdjpy_filters"
    / "states"
    / "usdjpy_v2b_asia_range_london_S_3_1_3_flt"
    / "unit_trades.csv"
)
DEMO_FILLS = (
    REPO
    / "live"
    / "demo"
    / "usdjpy_asia_range_london_oanda"
    / "state"
    / "fills.csv"
)
START_EQUITY = 100_000.0
# Matches live/fx_v2b_london_ungated.JPY_USD — ranking net +$178,142 footnote.
JPY_USD = 110.0
PUBLISHED_NET = 178_142.0
PUBLISHED_STRESS = -24_627.0
PUBLISHED_NS = 7.23
LIVE_UNITS_PER_LOT = 100_000
# If |prior-year DD| × 2 would exceed this fraction of equity at review, step 1.5× not 2×.
SIZE_UP_EXPOSURE_DD_FRAC = 0.40


def _norm_live_qty(q: float) -> float:
    """Map legacy micro research qtys to current live units."""
    q = float(q)
    if q < 1_000:
        return q * float(LIVE_UNITS_PER_LOT)
    return q


def _campaigns_from_unit_trades(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    g = (
        df.groupby("trade_id", as_index=False)
        .agg(
            entry_ts=("entry_ts", "first"),
            exit_ts=("exit_ts", "last"),
            exit_price=("exit_price", "last"),
            net_jpy=("net_usd", "sum"),
        )
        .sort_values("entry_ts")
    )
    g["entry_ts"] = pd.to_datetime(g["entry_ts"], utc=True)
    g["exit_ts"] = pd.to_datetime(g["exit_ts"], utc=True)
    # Live cash ≈ research POINT_VALUES net / FX mid (demo lot = 1 std lot / research unit).
    g["cash_usd"] = g["net_jpy"].astype(float) / g["exit_price"].astype(float)
    g["net_usd_published"] = g["net_jpy"].astype(float) / float(JPY_USD)
    g["date"] = g["exit_ts"].dt.tz_convert("America/New_York").dt.date
    return g


def _campaigns_from_demo_fills(path: Path) -> pd.DataFrame:
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
        cash_jpy = 0.0
        for _, r in g.iterrows():
            q = _norm_live_qty(r["quantity"])
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
                    cash_jpy += take * (opx - px)
                else:
                    cash_jpy += take * (px - opx)
                oq -= take
                remain -= take
                if oq <= 1e-6:
                    open_lots.pop(0)
                else:
                    open_lots[0] = (oside, oq, opx)
        last_px = float(g.iloc[-1]["price"])
        usd = cash_jpy / last_px if last_px else 0.0
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


def _daily_equity(campaigns: pd.DataFrame, pnl_col: str, start: float = START_EQUITY) -> pd.DataFrame:
    daily = campaigns.groupby("date", as_index=False)[pnl_col].sum().sort_values("date")
    daily["equity"] = start + daily[pnl_col].cumsum()
    return daily


def _drawdown_stats(equity: pd.Series) -> Dict[str, float]:
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


def _sharpe_sortino(daily_rets: pd.Series, periods: int = 252) -> Tuple[float, float]:
    r = daily_rets.dropna()
    if len(r) < 5 or r.std() == 0:
        return 0.0, 0.0
    sharpe = float(r.mean() / r.std() * math.sqrt(periods))
    downside = r[r < 0]
    if len(downside) < 2 or downside.std() == 0:
        return sharpe, 0.0
    sortino = float(r.mean() / downside.std() * math.sqrt(periods))
    return sharpe, sortino


def _apply_yearly_rolling_size_up(
    cash: pd.Series,
    dates: pd.Series,
    *,
    start_equity: float = START_EQUITY,
    exposure_dd_frac: float = SIZE_UP_EXPOSURE_DD_FRAC,
) -> Tuple[pd.Series, pd.Series, List[Dict[str, Any]], float]:
    """Year-1 base size; later years may permanently step up on lookback DD.

    At the start of each calendar year after the first, inspect the *prior*
    calendar year on the sized path only (no lookahead full-sample DD):

    - If prior-year PnL ≥ 2 × |prior-year max drawdown|, multiply size by 2×.
    - If that double would make |prior DD|×2 > ``exposure_dd_frac`` × equity at
      review, step by 1.5× instead.
    - Never size down. Steps may repeat indefinitely in later years.
    """
    years = pd.Series([d.year if hasattr(d, "year") else pd.Timestamp(d).year for d in dates])
    size = 1.0
    equity = float(start_equity)
    out: List[float] = []
    mults: List[float] = []
    events: List[Dict[str, Any]] = []
    # Per-year running path for lookback DD (equity after each campaign in that year).
    year_sized: Dict[int, List[float]] = {}
    year_eq_path: Dict[int, List[float]] = {}
    seen_years: List[int] = []

    for pnl_1x, d, y in zip(cash.astype(float), dates, years.astype(int)):
        y = int(y)
        if not seen_years or y != seen_years[-1]:
            if seen_years and y < seen_years[-1]:
                raise ValueError("campaigns must be sorted by calendar year")
            if seen_years and y > seen_years[-1]:
                # Year boundary: maybe size up from lookback of the completed year.
                prev_y = seen_years[-1]
                prev_pnls = year_sized.get(prev_y) or []
                prev_eqs = year_eq_path.get(prev_y) or []
                if prev_pnls and prev_eqs:
                    pnl_y = float(sum(prev_pnls))
                    # Equity path within prev year, anchored at year-start equity.
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


def _fetch_spy(start: str, end: str) -> Optional[pd.DataFrame]:
    """Adjusted close for SPY; returns None if download fails."""
    import urllib.request

    def _from_yahoo() -> Optional[pd.DataFrame]:
        try:
            t0 = int(pd.Timestamp(start, tz="UTC").timestamp())
            t1 = int(pd.Timestamp(end, tz="UTC").timestamp()) + 2 * 86400
            url = (
                "https://query1.finance.yahoo.com/v8/finance/chart/SPY"
                "?period1=%d&period2=%d&interval=1d&events=div" % (t0, t1)
            )
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 potions-exporter"})
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


def _spy_equity(spy: pd.DataFrame, start_eq: float = START_EQUITY) -> pd.DataFrame:
    s = spy.sort_values("date").copy()
    first = float(s["close"].iloc[0])
    s["equity"] = start_eq * (s["close"].astype(float) / first)
    return s


def _path_kpis(daily: pd.DataFrame, equity_col: str = "equity") -> Dict[str, Any]:
    if daily is None or daily.empty:
        return {}
    strat_eq = daily[equity_col].astype(float)
    strat_rets = strat_eq.pct_change().fillna(0.0)
    dd = _drawdown_stats(strat_eq)
    sharpe, sortino = _sharpe_sortino(strat_rets)
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


def _series_points(daily: pd.DataFrame, *, include_start: bool = True) -> List[Dict[str, Any]]:
    pts: List[Dict[str, Any]] = []
    if include_start and len(daily):
        first = daily["date"].iloc[0]
        # Anchor the day before first PnL so the chart has a flat start.
        start_d = (pd.Timestamp(first) - pd.Timedelta(days=1)).date()
        pts.append({"date": start_d.isoformat(), "equity": round(START_EQUITY, 2)})
    for d, e in zip(daily["date"], daily["equity"]):
        pts.append({"date": d.isoformat(), "equity": round(float(e), 2)})
    return pts


def build_payload(
    *,
    unit_trades: Path = HUB_UNIT,
    demo_fills: Path = DEMO_FILLS,
) -> Dict[str, Any]:
    camps = _campaigns_from_unit_trades(unit_trades)

    # --- 1× cash path (reference only; size-ups use yearly lookback DD) ---
    daily_1x = _daily_equity(camps, "cash_usd")
    eq_1x = daily_1x["equity"].astype(float)
    dd_1x = _drawdown_stats(eq_1x)
    max_dd_1x = float(dd_1x["max_dd_usd"])

    camps = camps.copy()
    sized_pnl, size_mults, size_events, final_size = _apply_yearly_rolling_size_up(
        camps["cash_usd"], camps["date"]
    )
    camps["sized_usd"] = sized_pnl.values
    camps["size_mult"] = size_mults.values
    daily_bt = _daily_equity(camps, "sized_usd")
    bt_kpis = _path_kpis(daily_bt)
    bt_kpis["size_up_events"] = size_events
    bt_kpis["size_up_n"] = int(len(size_events))
    bt_kpis["final_size_mult"] = float(final_size)
    bt_kpis["max_dd_1x_usd"] = round(max_dd_1x, 2)
    bt_kpis["end_equity_1x"] = round(float(eq_1x.iloc[-1]), 2) if len(eq_1x) else None
    bt_kpis["ns_research"] = PUBLISHED_NS
    bt_kpis["stress_research_usd"] = PUBLISHED_STRESS
    bt_kpis["published_net_usd"] = PUBLISHED_NET

    # Yearly table (sized path) — calendar year of exit (same clock as size-ups)
    by_year = camps.copy()
    by_year["year"] = pd.to_datetime(by_year["date"]).dt.year
    yr_net = {int(y): float(v) for y, v in by_year.groupby("year")["sized_usd"].sum().items()}
    yr_size = {int(y): float(v) for y, v in by_year.groupby("year")["size_mult"].last().items()}
    yearly_rows: List[Dict[str, Any]] = []
    running = START_EQUITY
    for y in sorted(yr_net):
        sn = float(yr_net[y])
        running += sn
        yearly_rows.append(
            {
                "year": int(y),
                "strategy_pnl_usd": round(sn, 2),
                "strategy_equity_end": round(running, 2),
                "size_mult_eoy": yr_size.get(int(y), 1.0),
            }
        )

    start_d = daily_bt["date"].iloc[0].isoformat()
    end_d = daily_bt["date"].iloc[-1].isoformat()

    spy = _fetch_spy(start_d, end_d)
    spy_series: List[Dict[str, Any]] = []
    spy_kpis: Dict[str, Any] = {}
    yearly_spy: Dict[int, float] = {}
    years = (daily_bt["date"].iloc[-1] - daily_bt["date"].iloc[0]).days / 365.25
    if spy is not None and len(spy) >= 2:
        se = _spy_equity(spy)
        idx = pd.DataFrame({"date": daily_bt["date"]})
        merged = idx.merge(se[["date", "equity", "close"]], on="date", how="left").sort_values("date")
        merged["equity"] = merged["equity"].ffill().bfill()
        # Weekly downsample for long backtest chart
        merged2 = merged.copy()
        merged2["week"] = pd.to_datetime(merged2["date"]).dt.to_period("W").astype(str)
        weekly_spy = merged2.groupby("week", as_index=False).last()
        spy_series = [
            {"date": d.isoformat(), "equity": round(float(e), 2)}
            for d, e in zip(weekly_spy["date"], weekly_spy["equity"])
        ]
        seq = merged["equity"].astype(float)
        srets = seq.pct_change().fillna(0.0)
        sdd = _drawdown_stats(seq)
        ssh, sso = _sharpe_sortino(srets)
        stot = float(seq.iloc[-1] / START_EQUITY - 1.0)
        scagr = float((seq.iloc[-1] / START_EQUITY) ** (1.0 / years) - 1.0) if years > 0 else 0.0
        spy_kpis = {
            "end_equity": round(float(seq.iloc[-1]), 2),
            "total_return": round(stot, 6),
            "cagr": round(scagr, 6),
            "max_dd_usd": round(sdd["max_dd_usd"], 2),
            "max_dd_pct": round(sdd["max_dd_pct"], 6),
            "sharpe": round(ssh, 3),
            "sortino": round(sso, 3),
            "time_underwater_pct": round(sdd["time_underwater_pct"], 4),
        }
        se2 = se.copy()
        se2["year"] = pd.to_datetime(se2["date"]).dt.year
        for y, chunk in se2.groupby("year"):
            if len(chunk) < 2:
                continue
            yearly_spy[int(y)] = float(chunk["close"].iloc[-1] / chunk["close"].iloc[0] - 1.0)

    for row in yearly_rows:
        y = int(row["year"])
        if y in yearly_spy:
            row["benchmark_return"] = round(yearly_spy[y], 6)
            row["benchmark_pnl_usd"] = round(START_EQUITY * yearly_spy[y], 2)
        else:
            row["benchmark_return"] = None
            row["benchmark_pnl_usd"] = None

    pos_years = sum(1 for v in yr_net.values() if v > 0)
    n_years = len(yr_net)
    worst_year = min(yr_net.items(), key=lambda kv: kv[1]) if yr_net else (0, 0.0)
    bt_kpis["positive_years_pct"] = round(pos_years / float(n_years), 4) if n_years else 0.0
    bt_kpis["worst_year"] = int(worst_year[0])
    bt_kpis["worst_year_pnl_usd"] = round(float(worst_year[1]), 2)

    # Weekly strategy series for backtest chart
    daily2 = daily_bt.copy()
    daily2["week"] = pd.to_datetime(daily2["date"]).dt.to_period("W").astype(str)
    weekly = daily2.groupby("week", as_index=False).last()
    strat_series_bt = [
        {"date": d.isoformat(), "equity": round(float(e), 2)}
        for d, e in zip(weekly["date"], weekly["equity"])
    ]

    # --- Practice / demo short path (hero) ---
    demo = _campaigns_from_demo_fills(demo_fills) if demo_fills.exists() else pd.DataFrame()
    demo_daily = _daily_equity(demo, "cash_usd") if len(demo) else pd.DataFrame()
    # Dense: one point per campaign exit day (already daily). Keep all days — short window.
    demo_series = _series_points(demo_daily, include_start=True) if len(demo_daily) else []
    demo_kpis = _path_kpis(demo_daily) if len(demo_daily) else {}
    if len(demo):
        demo_kpis["n_campaigns"] = int(len(demo))
        demo_kpis["net_usd"] = round(float(demo["cash_usd"].sum()), 2)
        demo_kpis["window_start"] = demo_daily["date"].iloc[0].isoformat()
        demo_kpis["window_end"] = demo_daily["date"].iloc[-1].isoformat()
        # Short sleeve: drop annualized metrics that blow up on <~30 calendar days.
        span_days = (demo_daily["date"].iloc[-1] - demo_daily["date"].iloc[0]).days
        if span_days < 30:
            for k_drop in ("cagr", "calmar", "parmar", "sharpe", "sortino", "vol_daily"):
                demo_kpis.pop(k_drop, None)

    stress_note = (
        "Research intrabar stress drawdown was about −$24.6k on the ranking book "
        "(N/S 7.23). Backtest equity below uses live lot-cash scale (same default "
        "size as the practice sleeve) with yearly rolling permanent size-ups: "
        "year 1 base size; later years step 2× (or 1.5× if a full double would "
        "push exposure too far) when prior-year PnL ≥ 2×|prior-year max DD| "
        "(lookback only)."
    )

    size_up_rule = (
        "Year 1 trades at base size (1×). At each later calendar year-start, "
        "if the prior year's sized PnL is at least 2 × |that year's max drawdown| "
        "(lookback DD only — never the full-sample max DD), size permanently "
        "steps up by 2×. If a full double would make |prior DD|×2 exceed "
        f"{SIZE_UP_EXPOSURE_DD_FRAC:.0%} of equity at review, step by 1.5× "
        "instead. Size never steps down; ups may repeat indefinitely. Yearly "
        "PnL reflects that path."
    )

    payload: Dict[str, Any] = {
        "schema_version": 3,
        "product_name": "FX Momentum",
        "tab_id": "fx_momentum",
        "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "disclaimer": (
            "Top chart is an unaudited practice track (size-normalized). "
            "Bottom chart and yearly table are a hypothetical backtest with a "
            "documented size-up rule — not an offer to invest. Instrument, session "
            "rules, and trade entries/exits are intentionally undisclosed."
        ),
        "methodology": {
            "start_equity_usd": START_EQUITY,
            "equity_construction": "additive",
            "live_size_note": (
                "Practice and backtest cash paths use the current default live size "
                "(multi-lot book × standard lot). Early micro-size practice fills are "
                "normalized to that size so execution is comparable on the short chart."
            ),
            "size_up_rule": size_up_rule,
            "size_up_events": size_events,
            "size_up_exposure_dd_frac": SIZE_UP_EXPOSURE_DD_FRAC,
            "equity_footnote": (
                "Campaign cash PnL summed by session date onto a $100,000 starting "
                "balance (no compounding). Ranking footnote still cites research "
                "quote conversion ≈ +$178,142 / stress ≈ −$24,627 / N/S 7.23."
            ),
            "window_start": start_d,
            "window_end": end_d,
            "n_campaigns": int(len(camps)),
            "published_net_usd": PUBLISHED_NET,
            "published_stress_usd": PUBLISHED_STRESS,
            "published_ns": PUBLISHED_NS,
            "benchmark": "SPY buy-and-hold, long-only (unmanaged US equity)",
            "practice_on_hero": True,
            "practice_note": (
                "Hero equity uses only practice campaigns actually taken, at the "
                "current default size (legacy micro fills renormalized). The series "
                "is short and will lengthen as the sleeve trades."
            ),
        },
        "practice_kpis": demo_kpis,
        "kpis": bt_kpis,  # backtest (sized) — primary table metrics
        "benchmark_kpis": spy_kpis,
        "stress_note": stress_note,
        "risk": {
            "typical_risk_units": "modest multi-unit scale-out book (exact size undisclosed)",
            "max_simultaneous_risk_units": "low single-digit concurrent units on the research book",
            "size_up": (
                "yearly rolling permanent step-up: prior-year PnL ≥ 2×|prior-year DD| "
                f"→ ×2 (or ×1.5 if |DD|×2 > {SIZE_UP_EXPOSURE_DD_FRAC:.0%} equity); never down"
            ),
            "worst_campaign_usd_research": -12_473.0,
        },
        "equity_practice": demo_series,
        "equity_strategy": strat_series_bt,
        "equity_benchmark": spy_series,
        "yearly_table_banner": "Backtest only — size-up applied — not live trading",
        "yearly": yearly_rows,
        "campaign_net_check_usd_1x": round(float(camps["cash_usd"].sum()), 2),
        "campaign_net_check_usd_sized": round(float(camps["sized_usd"].sum()), 2),
        "practice_net_check_usd": round(float(demo["cash_usd"].sum()), 2) if len(demo) else 0.0,
    }
    return payload


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        type=Path,
        default=REPO / "live" / "public_track_record" / "fx_momentum.json",
        help="Sanitized JSON output path",
    )
    ap.add_argument("--unit-trades", type=Path, default=HUB_UNIT)
    ap.add_argument("--demo-fills", type=Path, default=DEMO_FILLS)
    args = ap.parse_args(argv)
    payload = build_payload(unit_trades=args.unit_trades, demo_fills=args.demo_fills)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("wrote", args.out)
    print(
        "practice_n=%s practice_net=%.2f bt_end=%.2f size_ups=%s final_size=%.4g spy_pts=%d"
        % (
            (payload.get("practice_kpis") or {}).get("n_campaigns"),
            payload.get("practice_net_check_usd") or 0.0,
            payload["kpis"]["end_equity"],
            payload["kpis"].get("size_up_n"),
            payload["kpis"].get("final_size_mult") or 1.0,
            len(payload["equity_benchmark"]),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
