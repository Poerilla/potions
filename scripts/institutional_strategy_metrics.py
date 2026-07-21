#!/usr/bin/env python3
"""Build institutional-style risk metrics for the current strategy leaderboard.

The existing tracker is mostly ranked by Net / intrabar stress DD. This report
adds the metrics a CTM/CTA allocator will usually ask for: Sharpe, Sortino,
Calmar/MAR, drawdown duration, skew, benchmark correlation, beta, and downside
capture.

Methodology:
- Futures reference capital defaults to 3x each strategy's intrabar stress DD.
- Returns are daily changes in realized/close equity divided by that reference
  capital. This keeps Sharpe/Sortino comparable across different contract
  multipliers while preserving each strategy's native path.
- CAGR uses the same 3x stress-capital anchor.
- Benchmark fit uses QQQ adjusted-close daily returns over the same dates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "institutional_strategy_metrics"

QQQ = REPO / "data" / "benchmarks" / "QQQ_2010-06-06_2026-03-08_yahoo_daily.csv"

POINT_VALUE = {
    "NQ": 20.0,
    "MNQ": 2.0,
    "ES": 50.0,
    "MES": 5.0,
    "YM": 5.0,
    "MYM": 0.5,
    # FX / metals (Histdata / FX raw conventions used in Monday OR + sweeps)
    "EURUSD": 100_000.0,
    "GBPUSD": 100_000.0,
    "USDJPY": 100_000.0,
    "AUDJPY": 100_000.0,
    "XAUUSD": 100.0,
    "XAGUSD": 1000.0,
}

# Convert quote-currency equity to ≈USD for JPY crosses (same 110 FX as Monday OR broker)
JPY_USD = 110.0
JPY_INSTRUMENTS = {"USDJPY", "AUDJPY"}


def _to_usd_equity(instrument: str, equity: pd.Series) -> pd.Series:
    if instrument.upper() in JPY_INSTRUMENTS:
        return equity / JPY_USD
    return equity


def _to_usd_money(instrument: str, value: float) -> float:
    if instrument.upper() in JPY_INSTRUMENTS:
        return value / JPY_USD
    return value



@dataclass
class Candidate:
    name: str
    family: str
    instrument: str
    net_usd: float
    stress_dd_usd: float
    closed_dd_usd: float
    profit_factor: float
    win_rate_pct: float
    max_open_units: int
    equity_path: Path
    source_summary: Path
    notes: str = ""


def _num(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: object, default: int = 0) -> int:
    return int(round(_num(value, float(default))))


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _prior_opposed_candidates() -> list[Candidate]:
    out: list[Candidate] = []
    for market in ["nq", "mnq", "ym", "es", "mym"]:
        root = REPO / "live" / "state" / f"{market}_v2b_prior_opposed_stpmc_broker_like"
        summary_path = root / "summary.csv"
        df = _read_csv(summary_path)
        if df.empty:
            continue
        row = df.iloc[0]
        state_root = Path(str(row.get("state_root") or ""))
        if not state_root.is_absolute():
            cand = REPO / str(state_root).replace("potions/", "")
            state_root = cand if cand.exists() else root / "states" / str(row.get("strategy_id"))
        equity = state_root / "equity_curve.csv"
        if not equity.exists():
            continue
        inst = market.upper()
        out.append(
            Candidate(
                name=f"{inst} prior-opposed v2b gate S_1_1_3 (legacy fill stamp)",
                family="Prior-opposed v2b legacy",
                instrument=inst,
                net_usd=_num(row.get("net_usd")),
                stress_dd_usd=_num(row.get("intrabar_stress_dd_usd")),
                closed_dd_usd=_num(row.get("closed_dd_usd")),
                profit_factor=_num(row.get("profit_factor")),
                win_rate_pct=_num(row.get("win_rate_pct")),
                max_open_units=5,
                equity_path=equity,
                source_summary=summary_path,
                notes="Legacy hourly fill-stamp gate — diagnostic only; prefer resting-limit.",
            )
        )
    return out


def _broker_like_candidates() -> list[Candidate]:
    summary_path = REPO / "live" / "state" / "broker_like_replays" / "summary.csv"
    df = _read_csv(summary_path)
    out: list[Candidate] = []
    if df.empty:
        return out
    for _, row in df.iterrows():
        slug = str(row.get("slug") or "")
        inst = str(row.get("instrument") or "").upper()
        equity = REPO / "live" / "state" / "broker_like_replays" / "audits" / slug / "equity_curve.csv"
        if not equity.exists():
            continue
        out.append(
            Candidate(
                name=str(row.get("candidate") or slug),
                family="Broker-like leaderboard",
                instrument=inst,
                net_usd=_num(row.get("net_usd")),
                stress_dd_usd=_num(row.get("intrabar_mtm_dd_usd")),
                closed_dd_usd=_num(row.get("close_mtm_dd_usd")),
                profit_factor=float("nan"),
                win_rate_pct=float("nan"),
                max_open_units=_int(row.get("max_open_units")),
                equity_path=equity,
                source_summary=summary_path,
                notes="Generated broker-like replay table row.",
            )
        )
    return out


def _hourly_candidates() -> list[Candidate]:
    out: list[Candidate] = []

    # Best cross-market rows excluding YM, whose dedicated sweep is in a sibling folder.
    best_path = (
        REPO
        / "live"
        / "state"
        / "hourly_st_pmc_strategyplugin_variants_cross_market"
        / "best_by_market"
        / "summary.csv"
    )
    df = _read_csv(best_path)
    for _, row in df.iterrows():
        market = str(row.get("market") or "").lower()
        strategy_id = str(row.get("strategy_id") or "")
        if not strategy_id:
            continue
        equity = (
            REPO
            / "live"
            / "state"
            / "hourly_st_pmc_strategyplugin_variants_cross_market"
            / market
            / "audits"
            / strategy_id
            / strategy_id
            / "equity_curve.csv"
        )
        if not equity.exists():
            continue
        inst = str(row.get("instrument") or market.upper()).upper()
        out.append(
            Candidate(
                name=f"{inst} hourly ST+PMC {row.get('variant')}",
                family="Hourly ST+PMC",
                instrument=inst,
                net_usd=_num(row.get("net_usd")),
                stress_dd_usd=_num(row.get("intrabar_stress_dd_usd")),
                closed_dd_usd=_num(row.get("closed_dd_usd")),
                profit_factor=_num(row.get("profit_factor")),
                win_rate_pct=_num(row.get("win_rate_pct")),
                max_open_units=_int(row.get("max_open_units")),
                equity_path=equity,
                source_summary=best_path,
                notes="Best hourly ST+PMC row for this market.",
            )
        )

    # YM has its own complete sweep. Include the best-efficiency row, best-net
    # practical one-unit row, and original base 50/150 case-study rule.
    ym_path = REPO / "live" / "state" / "hourly_st_pmc_strategyplugin_variants" / "summary.csv"
    ym_df = _read_csv(ym_path)
    keep_variants = {"ma_bull_prior_only", "sl40_tp120_3r", "base_1x_50sl_150tp"}
    for _, row in ym_df.iterrows():
        variant = str(row.get("variant") or "")
        if variant not in keep_variants:
            continue
        strategy_id = str(row.get("strategy_id") or "")
        equity = (
            REPO
            / "live"
            / "state"
            / "hourly_st_pmc_strategyplugin_variants"
            / "audits"
            / strategy_id
            / strategy_id
            / "equity_curve.csv"
        )
        if not equity.exists():
            continue
        label = "YM hourly ST+PMC base 50/150" if variant == "base_1x_50sl_150tp" else f"YM hourly ST+PMC {variant}"
        out.append(
            Candidate(
                name=label,
                family="Hourly ST+PMC",
                instrument="YM",
                net_usd=_num(row.get("net_usd")),
                stress_dd_usd=_num(row.get("intrabar_stress_dd_usd")),
                closed_dd_usd=_num(row.get("closed_dd_usd")),
                profit_factor=_num(row.get("profit_factor")),
                win_rate_pct=_num(row.get("win_rate_pct")),
                max_open_units=_int(row.get("max_open_units")),
                equity_path=equity,
                source_summary=ym_path,
                notes="Dedicated YM hourly ST+PMC StrategyPlugin variant sweep.",
            )
        )
    return out


def _load_equity_usd(path: Path, instrument: str) -> pd.Series:
    df = pd.read_csv(path)
    if "ts" not in df:
        raise ValueError(f"Missing ts column in {path}")
    ts = pd.to_datetime(df["ts"], errors="coerce", utc=True)
    if ts.isna().all():
        ts = pd.to_datetime(df["ts"], errors="coerce")
    df = df.loc[ts.notna()].copy()
    ts = ts.loc[ts.notna()]
    inst = instrument.upper()
    if "close_equity_usd" in df:
        equity = pd.to_numeric(df["close_equity_usd"], errors="coerce")
    elif "close_equity_points" in df:
        if inst not in POINT_VALUE:
            raise ValueError(f"No point value for {inst} in {path}")
        equity = pd.to_numeric(df["close_equity_points"], errors="coerce") * POINT_VALUE[inst]
        equity = _to_usd_equity(inst, equity)
    else:
        raise ValueError(f"No close equity column in {path}")
    daily = pd.DataFrame({"date": ts.dt.date, "equity": equity}).dropna()
    if daily.empty:
        raise ValueError(f"No valid equity rows in {path}")
    return daily.groupby("date")["equity"].last().sort_index()


def _load_unit_returns(path: Path, instrument: str) -> pd.Series:
    unit_path = path.parent / "unit_fills.csv"
    if not unit_path.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(unit_path)
    if "usd" not in df:
        return pd.Series(dtype=float)
    # unit_fills stores gross quote-currency USD (or JPY for JPY pairs); fee $1.50/unit in USD.
    gross = pd.to_numeric(df["usd"], errors="coerce").dropna()
    gross = _to_usd_equity(instrument, gross)
    return gross - 1.50


def _drawdown_duration_days(equity: pd.Series) -> tuple[int, int, bool]:
    peak = equity.cummax()
    underwater = equity < peak
    max_days = 0
    episodes = 0
    start: Optional[pd.Timestamp] = None
    last_date: Optional[pd.Timestamp] = None
    for raw_date, is_underwater in underwater.items():
        date = pd.Timestamp(raw_date)
        if is_underwater and start is None:
            start = date
            episodes += 1
        if not is_underwater and start is not None:
            max_days = max(max_days, (date - start).days)
            start = None
        last_date = date
    unrecovered = start is not None
    if unrecovered and last_date is not None and start is not None:
        max_days = max(max_days, (last_date - start).days)
    return max_days, episodes, unrecovered


def _qqq_returns() -> pd.Series:
    df = pd.read_csv(QQQ)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    px_col = "adj_close" if "adj_close" in df else "close"
    px = pd.to_numeric(df[px_col], errors="coerce")
    returns = px.pct_change()
    return pd.Series(returns.values, index=df["date"]).dropna()


def _metrics_for(candidate: Candidate, qqq_returns: pd.Series) -> dict[str, object]:
    equity = _load_equity_usd(candidate.equity_path, candidate.instrument)
    unit_returns = _load_unit_returns(candidate.equity_path, candidate.instrument)
    profit_factor = candidate.profit_factor
    win_rate_pct = candidate.win_rate_pct
    if (not np.isfinite(profit_factor)) and len(unit_returns):
        gross_win = float(unit_returns[unit_returns > 0].sum())
        gross_loss = abs(float(unit_returns[unit_returns < 0].sum()))
        profit_factor = gross_win / gross_loss if gross_loss else math.nan
    if (not np.isfinite(win_rate_pct)) and len(unit_returns):
        win_rate_pct = 100.0 * float((unit_returns > 0).mean())

    capital = abs(candidate.stress_dd_usd) * 3.0 if candidate.stress_dd_usd else math.nan
    daily_pnl = equity.diff().fillna(0.0)
    returns = daily_pnl / capital if capital and np.isfinite(capital) else daily_pnl * math.nan
    returns = returns.replace([np.inf, -np.inf], np.nan).dropna()

    start = pd.Timestamp(equity.index.min())
    end = pd.Timestamp(equity.index.max())
    years = max((end - start).days / 365.25, 1.0 / 365.25)
    total_return = candidate.net_usd / capital if capital and np.isfinite(capital) else math.nan
    cagr = (1.0 + total_return) ** (1.0 / years) - 1.0 if total_return > -1 else math.nan
    max_dd_pct = abs(candidate.stress_dd_usd) / capital if capital and np.isfinite(capital) else math.nan
    calmar = cagr / max_dd_pct if max_dd_pct and np.isfinite(max_dd_pct) else math.nan

    daily_std = returns.std(ddof=1)
    sharpe = returns.mean() / daily_std * math.sqrt(252.0) if daily_std and np.isfinite(daily_std) else math.nan
    downside = returns[returns < 0.0]
    downside_std = downside.std(ddof=1)
    sortino = (
        returns.mean() * 252.0 / (downside_std * math.sqrt(252.0))
        if downside_std and np.isfinite(downside_std)
        else math.nan
    )
    skew = returns.skew() if len(returns) > 2 else math.nan
    worst_day = returns.min() if len(returns) else math.nan
    best_day = returns.max() if len(returns) else math.nan
    dd_duration, dd_episodes, unrecovered = _drawdown_duration_days(equity)

    common = pd.DataFrame({"strategy": returns, "qqq": qqq_returns}).dropna()
    corr = beta = up_capture = downside_capture = math.nan
    if len(common) > 2 and common["strategy"].std(ddof=1) > 0 and common["qqq"].std(ddof=1) > 0:
        corr = common["strategy"].corr(common["qqq"])
        beta = common["strategy"].cov(common["qqq"]) / common["qqq"].var()
        up = common[common["qqq"] > 0]
        down = common[common["qqq"] < 0]
        if not up.empty and abs(up["qqq"].sum()) > 1e-12:
            up_capture = up["strategy"].sum() / up["qqq"].sum()
        if not down.empty and abs(down["qqq"].sum()) > 1e-12:
            downside_capture = down["strategy"].sum() / down["qqq"].sum()

    unit_skew = unit_returns.skew() if len(unit_returns) > 2 else math.nan

    return {
        "name": candidate.name,
        "family": candidate.family,
        "instrument": candidate.instrument,
        "start": start.date().isoformat(),
        "end": end.date().isoformat(),
        "years": years,
        "reference_capital_3x_stress": capital,
        "net_usd": candidate.net_usd,
        "total_return_pct": total_return * 100.0,
        "cagr_pct": cagr * 100.0,
        "intrabar_stress_dd_usd": candidate.stress_dd_usd,
        "stress_dd_pct_of_ref": max_dd_pct * 100.0,
        "closed_dd_usd": candidate.closed_dd_usd,
        "net_over_stress": candidate.net_usd / abs(candidate.stress_dd_usd) if candidate.stress_dd_usd else math.nan,
        "calmar_mar": calmar,
        "sharpe_daily": sharpe,
        "sortino_daily": sortino,
        "daily_skew": skew,
        "unit_return_skew": unit_skew,
        "max_drawdown_duration_days": dd_duration,
        "drawdown_episodes": dd_episodes,
        "drawdown_unrecovered_at_end": bool(unrecovered),
        "worst_day_pct": worst_day * 100.0,
        "best_day_pct": best_day * 100.0,
        "qqq_daily_corr": corr,
        "qqq_beta": beta,
        "qqq_up_capture": up_capture,
        "qqq_downside_capture": downside_capture,
        "profit_factor": profit_factor,
        "win_rate_pct": win_rate_pct,
        "max_open_units": candidate.max_open_units,
        "equity_path": _rel(candidate.equity_path),
        "source_summary": _rel(candidate.source_summary),
        "notes": candidate.notes,
    }


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO.resolve()))
    except Exception:
        return str(path)


def _fmt_money(value: object) -> str:
    x = _num(value, math.nan)
    if not np.isfinite(x):
        return "n/a"
    return f"${x:,.0f}"


def _fmt_pct(value: object, digits: int = 1) -> str:
    x = _num(value, math.nan)
    if not np.isfinite(x):
        return "n/a"
    return f"{x:.{digits}f}%"


def _fmt_num(value: object, digits: int = 2) -> str:
    x = _num(value, math.nan)
    if not np.isfinite(x):
        return "n/a"
    return f"{x:.{digits}f}"


def _resting_limit_candidates() -> list[Candidate]:
    """Causal prior-opposed resting-limit hour-complete family (promotion baseline)."""
    specs = [
        (
            "NQ",
            REPO / "live/state/nq_v2b_prior_opposed_causal_proxies/resting_limit",
        ),
        (
            "MNQ",
            REPO / "live/state/mnq_v2b_prior_opposed_stpmc_resting_limit",
        ),
        (
            "YM",
            REPO / "live/state/ym_v2b_prior_opposed_stpmc_resting_limit",
        ),
        (
            "MYM",
            REPO / "live/state/mym_v2b_prior_opposed_stpmc_resting_limit",
        ),
    ]
    out: list[Candidate] = []
    for inst, root in specs:
        summary_path = root / "summary.csv"
        df = _read_csv(summary_path)
        if df.empty:
            continue
        row = df.iloc[0]
        state_root = Path(str(row.get("state_root") or ""))
        if not state_root.is_absolute():
            # summaries sometimes store potions/live/... relative to repo parent
            cand = REPO / str(state_root).replace("potions/", "")
            if not cand.exists():
                cand = Path(str(state_root))
            state_root = cand if cand.exists() else root / "states" / str(row.get("strategy_id"))
        equity = state_root / "equity_curve.csv"
        if not equity.exists():
            continue
        out.append(
            Candidate(
                name=f"{inst} prior-opposed v2b resting-limit (hour-complete)",
                family="Prior-opposed v2b resting-limit",
                instrument=inst,
                net_usd=_num(row.get("net_usd")),
                stress_dd_usd=_num(row.get("intrabar_stress_dd_usd")),
                closed_dd_usd=_num(row.get("closed_dd_usd")),
                profit_factor=_num(row.get("profit_factor")),
                win_rate_pct=_num(row.get("win_rate_pct")),
                max_open_units=5,
                equity_path=equity,
                source_summary=summary_path,
                notes="Causal resting-limit hour-complete gate; preferred over legacy fill-stamp.",
            )
        )
    return out


def _monday_or_candidates() -> list[Candidate]:
    """Phase 2 Monday OR anchors (ex-silver)."""
    specs = [
        ("EURUSD", "M1_S2_R2", "live/state/monday_or_sizing_sweep_broker", "paper-only (sub-period FAIL)"),
        ("USDJPY", "M2_S3_R1", "live/state/monday_or_sizing_sweep_broker_usdjpy", "Phase 2 primary"),
        ("GBPUSD", "M1_S1_R2", "live/state/monday_or_sizing_sweep_broker_gbpusd", "paper-only (sub-period FAIL)"),
        ("AUDJPY", "M1_S2_R2", "live/state/monday_or_sizing_sweep_broker_audjpy", "satellite; sub-period PASS"),
        ("XAUUSD", "M2_S2_R3", "live/state/monday_or_sizing_sweep_broker_xauusd", "heat caution"),
    ]
    out: list[Candidate] = []
    for sym, tag, root_rel, note in specs:
        root = REPO / root_rel
        results = _read_csv(root / "results.csv")
        if results.empty:
            continue
        rows = results[results["tag"] == tag]
        if rows.empty:
            continue
        row = rows.iloc[0]
        sid = f"{sym.lower()}_{tag.lower()}"
        equity = root / "audits" / sid / sid / "equity_curve.csv"
        if not equity.exists():
            continue
        out.append(
            Candidate(
                name=f"{sym} Monday OR {tag}",
                family="Monday OR FX",
                instrument=sym,
                net_usd=_num(row.get("net_usd_approx")),
                stress_dd_usd=_num(row.get("stress_usd_approx")),
                closed_dd_usd=_num(row.get("closed_dd")),
                profit_factor=float("nan"),
                win_rate_pct=float("nan"),
                max_open_units=_int(row.get("main_entry", 3)) + _int(row.get("side_entry", 0)),
                equity_path=equity,
                source_summary=root / "results.csv",
                notes=note,
            )
        )
    return out


def _fx_metals_candidates() -> list[Candidate]:
    """Promoted / top FX+metals sleeves with saved equity curves."""
    out: list[Candidate] = []

    # EURUSD hourly ST+PMC MA-bull (promoted intraday baseline)
    stpmc_eq = (
        REPO
        / "live/state/eurusd_baseline_dca_nospread/audits"
        / "eurusd_hourly_st_pmc_sl25_tp75_3r_ma_bull_prior"
        / "eurusd_hourly_st_pmc_sl25_tp75_3r_ma_bull_prior"
        / "equity_curve.csv"
    )
    if stpmc_eq.exists():
        out.append(
            Candidate(
                name="EURUSD hourly ST+PMC 25/75 MA-bull prior",
                family="FX ST+PMC",
                instrument="EURUSD",
                net_usd=23533.7,  # matches tracker / equity*PV
                stress_dd_usd=-15745.46,
                closed_dd_usd=-1128.5,
                profit_factor=float("nan"),
                win_rate_pct=27.4,
                max_open_units=1,
                equity_path=stpmc_eq,
                source_summary=stpmc_eq.parent / "reports" / "MTM_AUDIT.md",
                notes="Promoted FX intraday baseline.",
            )
        )

    # EURUSD monthly FBO atr80 1/1/3
    fbo_eq = (
        REPO
        / "live/state/eurusd_monthly_orb_fbo_filtered_broker/audits"
        / "eurusd_monthly_orb_fbo_filt_atr80only_1_1_3"
        / "equity_curve.csv"
    )
    if fbo_eq.exists():
        out.append(
            Candidate(
                name="EURUSD Monthly ORB FBO 1/1/3 atr80",
                family="FX Monthly FBO",
                instrument="EURUSD",
                net_usd=91898.0,
                stress_dd_usd=-56828.25,
                closed_dd_usd=-17493.5,
                profit_factor=float("nan"),
                win_rate_pct=52.1,
                max_open_units=5,
                equity_path=fbo_eq,
                source_summary=fbo_eq.parent / "reports" / "MTM_AUDIT.md",
                notes="Promoted FX monthly filtered sleeve.",
            )
        )

    # Cross-pair FBO atr80 leaders from summary.csv
    cross = REPO / "live/state/fx_cross_pair_tracker_leaders"
    cross_summary = cross / "summary.csv"
    cdf = _read_csv(cross_summary)
    fbo_map = {
        ("USDJPY", "1_1_3_atr80"): "fbo_1_1_3_atr80_usdjpy",
        ("GBPUSD", "1_1_3_atr80"): "fbo_1_1_3_atr80_gbpusd",
        ("AUDJPY", "1_1_3_atr80"): "fbo_1_1_3_atr80_audjpy",
    }
    if not cdf.empty:
        for (inst, variant), sid in fbo_map.items():
            hit = cdf[(cdf["pair"] == inst) & (cdf["family"] == "monthly_fbo") & (cdf["variant"] == variant)]
            if hit.empty:
                continue
            row = hit.iloc[0]
            equity = cross / "audits" / sid / "equity_curve.csv"
            if not equity.exists():
                continue
            out.append(
                Candidate(
                    name=f"{inst} Monthly ORB FBO 1/1/3 atr80",
                    family="FX Monthly FBO",
                    instrument=inst,
                    net_usd=_num(row.get("net_usd_approx")),
                    stress_dd_usd=_num(row.get("stress_usd_approx")),
                    closed_dd_usd=0.0,
                    profit_factor=float("nan"),
                    win_rate_pct=_num(row.get("wr")),
                    max_open_units=5,
                    equity_path=equity,
                    source_summary=cross_summary,
                    notes="Cross-pair FBO atr80 leader.",
                )
            )

    for market in ("gbpusd", "usdjpy", "audjpy"):
        equity = (
            cross
            / "st_pmc"
            / market
            / "audits"
            / f"{market}_hourly_st_pmc_sl25_tp75_3r_ma_bull_prior"
            / f"{market}_hourly_st_pmc_sl25_tp75_3r_ma_bull_prior"
            / "equity_curve.csv"
        )
        if not equity.exists():
            continue
        inst = market.upper()
        hit = cdf[(cdf["pair"] == inst) & (cdf["family"] == "hourly_st_pmc")] if not cdf.empty else pd.DataFrame()
        net = stress = float("nan")
        wr = float("nan")
        if not hit.empty:
            row = hit.iloc[0]
            net = _num(row.get("net_usd_approx"))
            stress = _num(row.get("stress_usd_approx"))
            wr = _num(row.get("wr"))
        out.append(
            Candidate(
                name=f"{inst} hourly ST+PMC 25/75 MA-bull prior",
                family="FX ST+PMC",
                instrument=inst,
                net_usd=net,
                stress_dd_usd=stress,
                closed_dd_usd=float("nan"),
                profit_factor=float("nan"),
                win_rate_pct=wr,
                max_open_units=1,
                equity_path=equity,
                source_summary=cross_summary if cross_summary.exists() else equity,
                notes="Cross-pair ST+PMC MA-bull.",
            )
        )

    # Metals / AUDJPY yearly ORB top rows
    metal_specs = [
        (
            "XAUUSD",
            REPO / "live/state/metals_futures_strats_sweep/audits/xauusd_yearly_orb_scaleout3/equity_curve.csv",
            REPO / "live/state/metals_futures_strats_sweep/summary.csv",
            "xauusd_yearly_orb_scaleout3",
        ),
        (
            "XAGUSD",
            REPO / "live/state/metals_futures_strats_sweep/audits/xagusd_yearly_orb_scaleout3/equity_curve.csv",
            REPO / "live/state/metals_futures_strats_sweep/summary.csv",
            "xagusd_yearly_orb_scaleout3",
        ),
        (
            "AUDJPY",
            REPO / "live/state/audjpy_futures_strats_sweep/audits/audjpy_yearly_orb_scaleout3/equity_curve.csv",
            REPO / "live/state/audjpy_futures_strats_sweep/summary.csv",
            "audjpy_yearly_orb_scaleout3",
        ),
    ]
    for inst, equity, summary, sid in metal_specs:
        if not equity.exists():
            continue
        sdf = _read_csv(summary)
        net = stress = float("nan")
        if not sdf.empty and "strategy_id" in sdf.columns:
            hit = sdf[sdf["strategy_id"] == sid]
            if not hit.empty:
                row = hit.iloc[0]
                if "net_usd_approx" in row.index:
                    net = _num(row.get("net_usd_approx"))
                elif "net_usd" in row.index:
                    net = _num(row.get("net_usd"))
                if "stress_usd" in row.index and pd.notna(row.get("stress_usd")):
                    stress = _num(row.get("stress_usd"))
                    if stress > 0:
                        stress = -stress
                elif "stress_jpy" in row.index and pd.notna(row.get("stress_jpy")):
                    stress = -abs(_num(row.get("stress_jpy"))) / JPY_USD
        out.append(
            Candidate(
                name=f"{inst} Yearly ORB scaleout3",
                family="FX/Metals Yearly ORB",
                instrument=inst,
                net_usd=net,
                stress_dd_usd=stress,
                closed_dd_usd=float("nan"),
                profit_factor=float("nan"),
                win_rate_pct=float("nan"),
                max_open_units=3,
                equity_path=equity,
                source_summary=summary,
                notes="Top-4 / metals sweep yearly ORB.",
            )
        )

    # Fill nan nets/stress from equity curves where needed
    filled: list[Candidate] = []
    for cand in out:
        net = cand.net_usd
        stress = cand.stress_dd_usd
        closed = cand.closed_dd_usd
        try:
            eq = _load_equity_usd(cand.equity_path, cand.instrument)
            if not np.isfinite(net):
                net = float(eq.iloc[-1])
            # Prefer curve intrabar dd if stress missing
            raw = pd.read_csv(cand.equity_path)
            if not np.isfinite(stress):
                if "intrabar_dd_usd" in raw:
                    stress = float(pd.to_numeric(raw["intrabar_dd_usd"], errors="coerce").min())
                    stress = _to_usd_money(cand.instrument, stress)
                elif "intrabar_stress_dd_usd" in raw:
                    stress = float(pd.to_numeric(raw["intrabar_stress_dd_usd"], errors="coerce").min())
            if not np.isfinite(closed) and "close_dd_usd" in raw:
                closed = float(pd.to_numeric(raw["close_dd_usd"], errors="coerce").min())
                closed = _to_usd_money(cand.instrument, closed)
        except Exception:
            pass
        if not np.isfinite(net) or not np.isfinite(stress) or stress == 0:
            continue
        filled.append(
            Candidate(
                name=cand.name,
                family=cand.family,
                instrument=cand.instrument,
                net_usd=float(net),
                stress_dd_usd=float(stress if stress < 0 else -abs(stress)),
                closed_dd_usd=float(closed) if np.isfinite(closed) else 0.0,
                profit_factor=cand.profit_factor,
                win_rate_pct=cand.win_rate_pct,
                max_open_units=cand.max_open_units,
                equity_path=cand.equity_path,
                source_summary=cand.source_summary,
                notes=cand.notes,
            )
        )
    return filled


def _write_markdown(metrics: pd.DataFrame) -> None:
    ranked = metrics.sort_values(["calmar_mar", "net_over_stress"], ascending=[False, False]).reset_index(drop=True)
    top = ranked.head(30)
    lines: list[str] = [
        "# Institutional Strategy Metrics",
        "",
        "Generated from saved replay equity curves and summary CSVs. These are **hypothetical/backtested** metrics, not audited live performance.",
        "",
        "## Method",
        "",
        "- Reference capital is **3x each strategy's intrabar stress DD**.",
        "- Daily returns are daily close-equity changes divided by that reference capital.",
        "- Calmar/MAR is CAGR divided by max intrabar stress DD percentage on that reference capital.",
        "- Sharpe and Sortino are daily-return annualized metrics using 252 trading days.",
        "- Correlation, beta, up-capture, and downside-capture are measured against QQQ adjusted-close returns over each strategy's overlapping dates.",
        "- Drawdown duration uses close-equity high-water marks; intrabar stress still defines the capital anchor.",
        "",
        "## Ranked Snapshot",
        "",
        "| Rank | Strategy | Window | Ref Cap | Net | CAGR | Calmar | Sharpe | Sortino | DD duration | QQQ corr | QQQ downside capture | PF | Notes |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for idx, row in top.iterrows():
        lines.append(
            "| {rank} | {name} | {start} to {end} | {cap} | {net} | {cagr} | {calmar} | {sharpe} | {sortino} | {duration}d | {corr} | {downcap} | {pf} | {notes} |".format(
                rank=idx + 1,
                name=row["name"],
                start=row["start"],
                end=row["end"],
                cap=_fmt_money(row["reference_capital_3x_stress"]),
                net=_fmt_money(row["net_usd"]),
                cagr=_fmt_pct(row["cagr_pct"]),
                calmar=_fmt_num(row["calmar_mar"]),
                sharpe=_fmt_num(row["sharpe_daily"]),
                sortino=_fmt_num(row["sortino_daily"]),
                duration=int(row["max_drawdown_duration_days"]),
                corr=_fmt_num(row["qqq_daily_corr"]),
                downcap=_fmt_num(row["qqq_downside_capture"]),
                pf=_fmt_num(row["profit_factor"]),
                notes=str(row["family"]),
            )
        )

    lines.extend(
        [
            "",
            "## Reading The Metrics",
            "",
            "- **Sharpe is only a baseline.** Strategies with lumpy intraday payouts can look mediocre on Sharpe while still having attractive drawdown-adjusted economics.",
            "- **Sortino matters for runner-style systems.** It penalizes downside volatility while leaving upside volatility alone.",
            "- **Calmar/MAR is the main CTA-style metric here.** The prior-opposed and yearly ORB rows remain strong because their CAGR is high relative to their modeled stress capital.",
            "- **Drawdown duration is now tracked explicitly.** A shallow drawdown that lasts months is operationally different from a deeper but fast-recovering one.",
            "- **QQQ downside capture is a portfolio-fit measure.** Negative values mean the strategy tended to make money on QQQ down days over the overlap.",
            "- **Capacity/slippage is not solved by these ratios.** Live shadow/paper runs must track expected vs actual fill price, queue slippage, rejected orders, and broker reconciliation deltas.",
            "",
            "Full machine-readable table: [`metrics.csv`](metrics.csv).",
        ]
    )
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build() -> pd.DataFrame:
    OUT.mkdir(parents=True, exist_ok=True)
    qqq = _qqq_returns()
    candidates: list[Candidate] = []
    candidates.extend(_resting_limit_candidates())
    candidates.extend(_prior_opposed_candidates())
    candidates.extend(_broker_like_candidates())
    candidates.extend(_hourly_candidates())
    candidates.extend(_monday_or_candidates())
    candidates.extend(_fx_metals_candidates())

    rows: list[dict[str, object]] = []
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for cand in candidates:
        key = (cand.name, str(cand.equity_path))
        if key in seen:
            continue
        seen.add(key)
        try:
            rows.append(_metrics_for(cand, qqq))
        except Exception as exc:  # noqa: BLE001 - report generation should continue.
            errors.append(f"{cand.name}: {exc}")

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["calmar_mar", "net_over_stress"], ascending=[False, False])
        df.to_csv(OUT / "metrics.csv", index=False)
        _write_markdown(df)
    if errors:
        (OUT / "errors.txt").write_text("\n".join(errors) + "\n", encoding="utf-8")
    return df


def main() -> int:
    df = build()
    print(f"Wrote {OUT / 'metrics.csv'} ({len(df)} rows)")
    print(f"Wrote {OUT / 'SUMMARY.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
