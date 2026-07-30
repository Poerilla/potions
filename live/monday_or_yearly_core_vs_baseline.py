#!/usr/bin/env python3
"""Year-by-year metrics: Monday OR cores vs Phase-1 baselines.

Uses StrategyPlugin audit equity curves + unit fills.

Funding capital (user-specified book starts):
  USDJPY → $100,000
  XAUUSD → $250,000

% gain / Sharpe / CAGR / DD% use that starting capital as the return denominator
(constant). Account equity compounds: equity = capital + cumulative strategy PnL.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "monday_or_phase2" / "yearly_core_vs_baseline"

POINT_VALUE = {
    "USDJPY": 100_000.0,
    "XAUUSD": 100.0,
}
JPY_USD = 110.0
FEE_PER_UNIT_USD = 1.50

# Fixed starting capital for %-of-book metrics + equity path
START_CAPITAL = {
    "USDJPY": 100_000.0,
    "XAUUSD": 250_000.0,
}

BOOKS = [
    {
        "pair": "USDJPY",
        "tag": "M2_S3_R1",
        "label": "USDJPY M2_S3_R1",
        "baseline_equity": REPO
        / "live/state/monday_or_sizing_sweep_broker_usdjpy/audits/usdjpy_m2_s3_r1/usdjpy_m2_s3_r1/equity_curve.csv",
        # Locked core audit is skip_augsep (sitout+3 + Aug/Sep); *_tuneup audit is pre-AugSep archive.
        "core_equity": REPO
        / "live/state/monday_or_phase2/tuneup_broker/audits/usdjpy_m2_s3_r1_skip_augsep/usdjpy_m2_s3_r1_skip_augsep/equity_curve.csv",
        "core_knobs": "week_sitout_after_pts=3 + skip_entry_months=[8,9]",
    },
    {
        "pair": "USDJPY",
        "tag": "M2_S3_R2",
        "label": "USDJPY M2_S3_R2",
        "baseline_equity": REPO
        / "live/state/monday_or_sizing_sweep_broker_usdjpy/audits/usdjpy_m2_s3_r2/usdjpy_m2_s3_r2/equity_curve.csv",
        "core_equity": REPO
        / "live/state/monday_or_phase2/tuneup_broker/audits/usdjpy_m2_s3_r2_skip_augsep/usdjpy_m2_s3_r2_skip_augsep/equity_curve.csv",
        "core_knobs": "skip_after_win_streak=2 + skip_entry_months=[8,9]",
    },
    {
        "pair": "XAUUSD",
        "tag": "M2_S2_R3",
        "label": "XAUUSD M2_S2_R3",
        "baseline_equity": REPO
        / "live/state/monday_or_sizing_sweep_broker_xauusd/audits/xauusd_m2_s2_r3/xauusd_m2_s2_r3/equity_curve.csv",
        "core_equity": REPO
        / "live/state/monday_or_phase2/tuneup_broker/audits/xauusd_m2_s2_r3_tuneup/xauusd_m2_s2_r3_tuneup/equity_curve.csv",
        "core_knobs": "week_sitout_after_pts=100 + skip_entry_months=[7,9,12]",
    },
]


def _to_usd(pair: str, value: float | pd.Series) -> float | pd.Series:
    if pair.upper() == "USDJPY":
        return value / JPY_USD
    return value


def _load_equity(equity_path: Path, pair: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (bar_df 15m, daily_df). DD computed on bars; Sharpe on daily."""
    usecols = [
        "ts",
        "close_equity_points",
        "intrabar_stress_points",
        "close_dd_usd",
        "intrabar_dd_usd",
    ]
    df = pd.read_csv(equity_path, usecols=usecols)
    ts = pd.to_datetime(df["ts"], errors="coerce", utc=True)
    ok = ts.notna()
    df = df.loc[ok].copy()
    ts = ts.loc[ok]
    pv = POINT_VALUE[pair.upper()]
    close = _to_usd(pair, pd.to_numeric(df["close_equity_points"], errors="coerce") * pv)
    stress_eq = _to_usd(pair, pd.to_numeric(df["intrabar_stress_points"], errors="coerce") * pv)
    close_dd = _to_usd(pair, pd.to_numeric(df["close_dd_usd"], errors="coerce"))
    stress_dd = _to_usd(pair, pd.to_numeric(df["intrabar_dd_usd"], errors="coerce"))
    bars = pd.DataFrame(
        {
            "ts": ts.dt.tz_convert(None),
            "close_usd": close,
            "stress_eq_usd": stress_eq,
            "close_dd_usd": close_dd,
            "stress_dd_usd": stress_dd,
        }
    ).dropna(subset=["close_usd"])
    bars["date"] = bars["ts"].dt.normalize()
    bars["year"] = bars["date"].dt.year
    daily = bars.groupby("date", as_index=True)[["close_usd", "stress_eq_usd"]].last().sort_index()
    daily["year"] = daily.index.year
    return bars, daily


def _load_units(equity_path: Path, pair: str) -> pd.DataFrame:
    unit_path = equity_path.parent / "unit_fills.csv"
    if not unit_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(unit_path)
    if "exit_ts" not in df or "usd" not in df:
        return pd.DataFrame()
    ts = pd.to_datetime(df["exit_ts"], errors="coerce", utc=True)
    df = df.loc[ts.notna()].copy()
    ts = ts.loc[ts.notna()]
    gross = _to_usd(pair, pd.to_numeric(df["usd"], errors="coerce"))
    net = gross - FEE_PER_UNIT_USD
    out = pd.DataFrame(
        {
            "exit_date": ts.dt.tz_convert(None).dt.normalize(),
            "net_usd": net,
            "trade_id": df["trade_id"] if "trade_id" in df else np.arange(len(df)),
        }
    ).dropna(subset=["net_usd"])
    out["year"] = out["exit_date"].dt.year
    return out


def _sharpe_sortino(returns: pd.Series) -> tuple[float, float]:
    r = returns.replace([np.inf, -np.inf], np.nan).dropna()
    if len(r) < 2:
        return math.nan, math.nan
    std = r.std(ddof=1)
    sharpe = r.mean() / std * math.sqrt(252.0) if std and np.isfinite(std) and std > 0 else math.nan
    down = r[r < 0.0]
    dstd = down.std(ddof=1) if len(down) > 1 else math.nan
    sortino = (
        r.mean() * 252.0 / (dstd * math.sqrt(252.0))
        if dstd and np.isfinite(dstd) and dstd > 0
        else math.nan
    )
    return float(sharpe), float(sortino)


def _year_path_dd(close: pd.Series, stress_eq: pd.Series) -> tuple[float, float]:
    """Year-local peak-to-trough using close peak (audit convention)."""
    if close.empty:
        return math.nan, math.nan
    peak = close.cummax()
    close_dd = float((close - peak).min())
    stress_dd = float((stress_eq - peak).min())
    return close_dd, stress_dd


def _metrics_slice(
    *,
    pair: str,
    tag: str,
    variant: str,
    knobs: str,
    bars: pd.DataFrame,
    daily: pd.DataFrame,
    units: pd.DataFrame,
    year: int | None,
    ref_capital: float,
) -> dict[str, object]:
    if year is None:
        b = bars
        d = daily
        u = units
        label_year = "FULL"
    else:
        b = bars.loc[bars["year"] == year]
        d = daily.loc[daily["year"] == year]
        u = units.loc[units["year"] == year] if not units.empty else units
        label_year = str(year)

    if d.empty or b.empty:
        return {
            "pair": pair,
            "tag": tag,
            "variant": variant,
            "year": label_year,
            "knobs": knobs,
        }

    # Strategy PnL (from 0): change vs last strategy equity before slice
    if year is None:
        strat_start = 0.0
        strat_end = float(d["close_usd"].iloc[-1])
    else:
        prior = daily.loc[daily["year"] < year]
        strat_start = float(prior["close_usd"].iloc[-1]) if not prior.empty else float(d["close_usd"].iloc[0])
        strat_end = float(d["close_usd"].iloc[-1])
    net = strat_end - strat_start

    # Account equity = starting capital + cumulative strategy PnL
    start_eq = ref_capital + strat_start
    end_eq = ref_capital + strat_end

    # DD on 15m bars within the slice (matches audit full-sample stress)
    close_dd, stress_dd = _year_path_dd(b["close_usd"], b["stress_eq_usd"])
    path_close_dd = float(b["close_dd_usd"].min())
    path_stress_dd = float(b["stress_dd_usd"].min())
    if year is None:
        # Authoritative full-sample MTM from audit running path columns
        if np.isfinite(path_close_dd):
            close_dd = path_close_dd
        if np.isfinite(path_stress_dd):
            stress_dd = path_stress_dd

    daily_pnl = d["close_usd"].diff()
    if year is not None:
        daily_pnl = daily_pnl.copy()
        daily_pnl.iloc[0] = float(d["close_usd"].iloc[0]) - strat_start
    else:
        daily_pnl = daily_pnl.fillna(0.0)

    returns = daily_pnl / ref_capital if ref_capital and np.isfinite(ref_capital) and ref_capital > 0 else daily_pnl * math.nan
    sharpe, sortino = _sharpe_sortino(returns)
    skew = float(returns.skew()) if returns.dropna().shape[0] > 2 else math.nan

    # % of starting capital (constant denominator for year-to-year comparability)
    gain_pct = 100.0 * net / ref_capital if ref_capital else math.nan
    # Also: % of year-start account equity (compounded book)
    gain_pct_on_eq = 100.0 * net / start_eq if start_eq else math.nan
    dd_pct = 100.0 * abs(stress_dd) / ref_capital if ref_capital and np.isfinite(stress_dd) else math.nan
    dd_pct_on_eq = 100.0 * abs(stress_dd) / start_eq if start_eq and np.isfinite(stress_dd) else math.nan
    # Calmar on year = year net / |year stress DD| (same units as N/S)
    calmar = net / abs(stress_dd) if stress_dd and stress_dd != 0 else math.nan
    ns = net / abs(stress_dd) if stress_dd and stress_dd != 0 else math.nan

    # CAGR vs starting capital: (1 + net/capital)^(1/years) - 1
    start_ts = pd.Timestamp(d.index.min())
    end_ts = pd.Timestamp(d.index.max())
    years_span = max((end_ts - start_ts).days / 365.25, 1.0 / 365.25)
    total_return = net / ref_capital if ref_capital and np.isfinite(ref_capital) and ref_capital > 0 else math.nan
    if np.isfinite(total_return) and total_return > -1.0:
        cagr = (1.0 + total_return) ** (1.0 / years_span) - 1.0
    else:
        cagr = math.nan
    cagr_pct = 100.0 * cagr if np.isfinite(cagr) else math.nan

    n_units = int(len(u)) if not u.empty else 0
    n_trades = int(u["trade_id"].nunique()) if not u.empty and "trade_id" in u else 0
    wins = u.loc[u["net_usd"] > 0, "net_usd"] if not u.empty else pd.Series(dtype=float)
    losses = u.loc[u["net_usd"] < 0, "net_usd"] if not u.empty else pd.Series(dtype=float)
    wr = 100.0 * float((u["net_usd"] > 0).mean()) if n_units else math.nan
    gw = float(wins.sum()) if len(wins) else 0.0
    gl = abs(float(losses.sum())) if len(losses) else 0.0
    pf = gw / gl if gl > 0 else (math.inf if gw > 0 else math.nan)
    avg_win = float(wins.mean()) if len(wins) else math.nan
    avg_loss = float(losses.mean()) if len(losses) else math.nan
    best_day = float(returns.max() * 100.0) if returns.notna().any() else math.nan
    worst_day = float(returns.min() * 100.0) if returns.notna().any() else math.nan
    days = int(len(d))

    return {
        "pair": pair,
        "tag": tag,
        "variant": variant,
        "year": label_year,
        "knobs": knobs,
        "days": days,
        "years_span": round(years_span, 4),
        "units": n_units,
        "trades": n_trades,
        "net_usd": round(net, 2),
        "close_dd_usd": round(close_dd, 2),
        "stress_dd_usd": round(stress_dd, 2),
        "path_min_close_dd_usd": round(path_close_dd, 2) if np.isfinite(path_close_dd) else math.nan,
        "path_min_stress_dd_usd": round(path_stress_dd, 2) if np.isfinite(path_stress_dd) else math.nan,
        "net_over_stress": round(ns, 4) if np.isfinite(ns) else math.nan,
        "start_capital_usd": round(ref_capital, 2),
        "gain_pct_of_capital": round(gain_pct, 2) if np.isfinite(gain_pct) else math.nan,
        "gain_pct_on_equity": round(gain_pct_on_eq, 2) if np.isfinite(gain_pct_on_eq) else math.nan,
        "cagr_pct": round(cagr_pct, 2) if np.isfinite(cagr_pct) else math.nan,
        "stress_dd_pct_of_capital": round(dd_pct, 2) if np.isfinite(dd_pct) else math.nan,
        "stress_dd_pct_on_equity": round(dd_pct_on_eq, 2) if np.isfinite(dd_pct_on_eq) else math.nan,
        "calmar": round(calmar, 4) if np.isfinite(calmar) else math.nan,
        "sharpe": round(sharpe, 3) if np.isfinite(sharpe) else math.nan,
        "sortino": round(sortino, 3) if np.isfinite(sortino) else math.nan,
        "daily_skew": round(skew, 3) if np.isfinite(skew) else math.nan,
        "win_rate_pct": round(wr, 2) if np.isfinite(wr) else math.nan,
        "profit_factor": round(pf, 3) if np.isfinite(pf) else ("inf" if pf == math.inf else math.nan),
        "avg_win_usd": round(avg_win, 2) if np.isfinite(avg_win) else math.nan,
        "avg_loss_usd": round(avg_loss, 2) if np.isfinite(avg_loss) else math.nan,
        "best_day_pct_of_capital": round(best_day, 3) if np.isfinite(best_day) else math.nan,
        "worst_day_pct_of_capital": round(worst_day, 3) if np.isfinite(worst_day) else math.nan,
        "start_equity_usd": round(start_eq, 2),
        "end_equity_usd": round(end_eq, 2),
        # aliases kept for older readers
        "gain_pct_of_ref": round(gain_pct, 2) if np.isfinite(gain_pct) else math.nan,
        "stress_dd_pct_of_ref": round(dd_pct, 2) if np.isfinite(dd_pct) else math.nan,
        "ref_capital_3x_stress": round(ref_capital, 2),
    }


def _analyze_book(book: dict) -> pd.DataFrame:
    pair = book["pair"]
    rows: list[dict] = []
    for variant, path, knobs in (
        ("baseline", book["baseline_equity"], "Phase-1 (no tune-up)"),
        ("core", book["core_equity"], book["core_knobs"]),
    ):
        bars, daily = _load_equity(path, pair)
        units = _load_units(path, pair)
        ref = float(START_CAPITAL[pair.upper()])

        rows.append(
            _metrics_slice(
                pair=pair,
                tag=book["tag"],
                variant=variant,
                knobs=knobs,
                bars=bars,
                daily=daily,
                units=units,
                year=None,
                ref_capital=ref,
            )
        )
        for y in sorted(daily["year"].unique()):
            rows.append(
                _metrics_slice(
                    pair=pair,
                    tag=book["tag"],
                    variant=variant,
                    knobs=knobs,
                    bars=bars,
                    daily=daily,
                    units=units,
                    year=int(y),
                    ref_capital=ref,
                )
            )
    return pd.DataFrame(rows)


def _fmt_money(x: object) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "n/a"
    if not np.isfinite(v):
        return "n/a"
    return f"${v:,.0f}"


def _fmt_num(x: object, d: int = 2) -> str:
    if x == "inf":
        return "inf"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "n/a"
    if not np.isfinite(v):
        return "n/a"
    return f"{v:.{d}f}"


def _write_md(all_df: pd.DataFrame) -> None:
    lines: list[str] = []
    lines.append("# Monday OR — year-by-year: core vs Phase-1 baseline")
    lines.append("")
    lines.append("StrategyPlugin Engine + PaperBroker equity / unit fills.")
    lines.append("")
    lines.append("**Starting capital (fixed):**")
    lines.append("- **USDJPY** = **$100,000**")
    lines.append("- **XAUUSD** = **$250,000**")
    lines.append("")
    lines.append("**Methodology:**")
    lines.append("- Account equity = starting capital + cumulative strategy PnL.")
    lines.append("- Year **PnL** = end-of-year strategy equity − prior year-end.")
    lines.append("- Year **Gain%** = year PnL / **starting capital** (constant; comparable across years).")
    lines.append("- Year **Gain% on eq** = year PnL / year-start account equity (compounded).")
    lines.append("- **DD%** = year-local stress DD / starting capital (also shown on year-start equity in CSV).")
    lines.append(
        "- **CAGR%** = `(1 + net/capital)^(1/years) − 1` (partial years 2003/2026 day-annualized)."
    )
    lines.append("- **Sharpe / Sortino** from daily PnL / starting capital (252d).")
    lines.append("- **Calmar** = year net / |year stress DD| (same as N/S).")
    lines.append("- USDJPY cores: `*_skip_augsep`; gold: `xauusd_m2_s2_r3_tuneup`.")
    lines.append("")

    for book in BOOKS:
        cap = START_CAPITAL[book["pair"].upper()]
        sub = all_df[(all_df["pair"] == book["pair"]) & (all_df["tag"] == book["tag"])].copy()
        lines.append(f"## {book['label']}")
        lines.append("")
        lines.append(f"- **Start capital:** ${cap:,.0f}")
        lines.append(f"- **Baseline:** Phase-1 `{book['tag']}`")
        lines.append(f"- **Core:** {book['core_knobs']}")
        lines.append("")

        full = sub[sub["year"] == "FULL"]
        lines.append("### Full sample")
        lines.append("")
        lines.append(
            "| Variant | Start eq | End eq | PnL | Stress DD | N/S | Gain% | CAGR% | DD% | Sharpe | Sortino | Calmar | WR% | PF | Units |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for _, r in full.iterrows():
            lines.append(
                "| {v} | {s} | {e} | {net} | {dd} | {ns} | {g} | {cagr} | {ddp} | {sh} | {so} | {ca} | {wr} | {pf} | {u} |".format(
                    v=r["variant"],
                    s=_fmt_money(r["start_equity_usd"]),
                    e=_fmt_money(r["end_equity_usd"]),
                    net=_fmt_money(r["net_usd"]),
                    dd=_fmt_money(r["stress_dd_usd"]),
                    ns=_fmt_num(r["net_over_stress"]),
                    g=_fmt_num(r["gain_pct_of_capital"], 1),
                    cagr=_fmt_num(r["cagr_pct"], 1),
                    ddp=_fmt_num(r["stress_dd_pct_of_capital"], 1),
                    sh=_fmt_num(r["sharpe"], 2),
                    so=_fmt_num(r["sortino"], 2),
                    ca=_fmt_num(r["calmar"], 2),
                    wr=_fmt_num(r["win_rate_pct"], 1),
                    pf=_fmt_num(r["profit_factor"], 2),
                    u=int(r["units"]) if pd.notna(r["units"]) else 0,
                )
            )
        lines.append("")

        years = [y for y in sub["year"].unique() if y != "FULL"]
        lines.append("### Year by year — PnL, equity, %")
        lines.append("")
        lines.append(
            "| Year | Var | Start eq | PnL | End eq | Gain% | Gain% on eq | Stress DD | DD% | N/S | Sharpe | Calmar |"
        )
        lines.append("|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for y in years:
            for variant in ("baseline", "core"):
                hit = sub[(sub["year"] == y) & (sub["variant"] == variant)]
                if hit.empty:
                    continue
                r = hit.iloc[0]
                lines.append(
                    "| {y} | {v} | {s} | {net} | {e} | {g} | {ge} | {dd} | {ddp} | {ns} | {sh} | {ca} |".format(
                        y=y,
                        v=variant[:4],
                        s=_fmt_money(r["start_equity_usd"]),
                        net=_fmt_money(r["net_usd"]),
                        e=_fmt_money(r["end_equity_usd"]),
                        g=_fmt_num(r["gain_pct_of_capital"], 1),
                        ge=_fmt_num(r["gain_pct_on_equity"], 1),
                        dd=_fmt_money(r["stress_dd_usd"]),
                        ddp=_fmt_num(r["stress_dd_pct_of_capital"], 1),
                        ns=_fmt_num(r["net_over_stress"]),
                        sh=_fmt_num(r["sharpe"], 2),
                        ca=_fmt_num(r["calmar"], 2),
                    )
                )
        lines.append("")

        lines.append("### Year by year — full metrics")
        lines.append("")
        lines.append(
            "| Year | Var | PnL | Stress DD | N/S | Gain% | CAGR% | DD% | Sharpe | Sortino | Calmar | WR% | PF | Units | Trades |"
        )
        lines.append("|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for y in years:
            for variant in ("baseline", "core"):
                hit = sub[(sub["year"] == y) & (sub["variant"] == variant)]
                if hit.empty:
                    continue
                r = hit.iloc[0]
                lines.append(
                    "| {y} | {v} | {net} | {dd} | {ns} | {g} | {cagr} | {ddp} | {sh} | {so} | {ca} | {wr} | {pf} | {u} | {t} |".format(
                        y=y,
                        v=variant[:4],
                        net=_fmt_money(r["net_usd"]),
                        dd=_fmt_money(r["stress_dd_usd"]),
                        ns=_fmt_num(r["net_over_stress"]),
                        g=_fmt_num(r["gain_pct_of_capital"], 1),
                        cagr=_fmt_num(r["cagr_pct"], 1),
                        ddp=_fmt_num(r["stress_dd_pct_of_capital"], 1),
                        sh=_fmt_num(r["sharpe"], 2),
                        so=_fmt_num(r["sortino"], 2),
                        ca=_fmt_num(r["calmar"], 2),
                        wr=_fmt_num(r["win_rate_pct"], 1),
                        pf=_fmt_num(r["profit_factor"], 2),
                        u=int(r["units"]) if pd.notna(r["units"]) else 0,
                        t=int(r["trades"]) if pd.notna(r["trades"]) else 0,
                    )
                )
        lines.append("")

        lines.append("### Core − baseline (Δ)")
        lines.append("")
        lines.append("| Year | Δ PnL | Δ End eq | Δ Gain% | Δ N/S | Δ Sharpe |")
        lines.append("|---:|---:|---:|---:|---:|---:|")
        for y in ["FULL", *years]:
            b = sub[(sub["year"] == y) & (sub["variant"] == "baseline")]
            c = sub[(sub["year"] == y) & (sub["variant"] == "core")]
            if b.empty or c.empty:
                continue
            br, cr = b.iloc[0], c.iloc[0]
            d_net = float(cr["net_usd"]) - float(br["net_usd"])
            d_eq = float(cr["end_equity_usd"]) - float(br["end_equity_usd"])
            d_g = float(cr["gain_pct_of_capital"]) - float(br["gain_pct_of_capital"])
            d_ns = float(cr["net_over_stress"]) - float(br["net_over_stress"])
            d_sh = float(cr["sharpe"]) - float(br["sharpe"])
            lines.append(
                f"| {y} | {_fmt_money(d_net)} | {_fmt_money(d_eq)} | {_fmt_num(d_g, 1)} | {_fmt_num(d_ns)} | {_fmt_num(d_sh, 2)} |"
            )
        lines.append("")

    path = OUT / "YEARLY_CORE_VS_BASELINE.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", path)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    frames = []
    for book in BOOKS:
        print("analyzing", book["label"], "...", flush=True)
        frames.append(_analyze_book(book))
    all_df = pd.concat(frames, ignore_index=True)
    csv_path = OUT / "yearly_metrics.csv"
    all_df.to_csv(csv_path, index=False)
    print("wrote", csv_path)
    _write_md(all_df)


if __name__ == "__main__":
    main()
