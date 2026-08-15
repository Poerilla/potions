"""$250k standalone boards from canonical N/S research ledger.

Builds:
  INDIVIDUAL_250K_STANDALONE_RANKING  — common stress budget + annualization
  INDIVIDUAL_250K_RESEARCH_EFFICIENCY — candidate N/S (research, not funded)
  INDIVIDUAL_250K_LEVERAGE_LADDER    — sensitivity 3×/4× (and full mult ladder)

Hub::

    live/state/canonical_ns_research/
      INDIVIDUAL_250K_STANDALONE_RANKING.md|.csv
      INDIVIDUAL_250K_RESEARCH_EFFICIENCY.md|.csv
      INDIVIDUAL_250K_LEVERAGE_LADDER.md|.csv
      EMAIL_250K.txt
      EMAIL_250K_LEVERAGE.txt
"""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .runner_risk_postprocess import MARGIN_USD

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live/state/canonical_ns_research"
STATE = REPO / "live/state"

CAPITAL = 250_000.0
STRESS_BUDGET = 25_000.0  # 10%
MAX_MTM_DD = 37_500.0  # 15%
MAX_MARGIN = 125_000.0  # 50%

# Prefer null-suite rows over ladder duplicates.
_SOURCE_PREF = {
    "futures_intraday_hp_sizeup_nulls_2x": 0,
    "futures_intraday_hp_sizeup_nulls": 1,
    "intraday_hp_sizeup_nulls": 2,
    "futures_intraday_hp_live_plan": 9,
}


def _safe(x: Any, default: float = float("nan")) -> float:
    try:
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def _fmt_money(x: float, signed: bool = False) -> str:
    if not math.isfinite(x):
        return "—"
    ax = abs(x)
    body = f"{ax:,.0f}" if ax >= 100 else f"{ax:,.2f}"
    if signed or x < 0:
        return ("+" if x >= 0 else "-") + body
    return body


def _fmt_pct(x: float) -> str:
    if not math.isfinite(x):
        return "—"
    return f"{x:.1f}%"


def _fmt_num(x: float, digits: int = 2) -> str:
    if not math.isfinite(x):
        return "—"
    return f"{x:.{digits}f}"


def _selection_status(notes: str, multiplier: float) -> str:
    n = str(notes or "")
    m = re.search(r"decision=([A-Za-z0-9 _\-/]+?)(?:\s+p_master|\s+\||$)", n)
    if m:
        return m.group(1).strip()
    if "SENSITIVITY ONLY" in n.upper():
        return "SENSITIVITY ONLY"
    if "RISK THROTTLE" in n.upper() or "risk-throttle" in n.lower() or "RISK-BUDGET" in n.upper():
        return "RISK THROTTLE / PROFILE"
    if "ladder row" in n.lower():
        return "LADDER (prefer null-suite)"
    if "inventory" in n.lower():
        return "INVENTORY"
    if "10R addon" in n or "prior-opposed 10R" in n:
        return "ADDON (not finite-core)"
    if abs(multiplier - 1.0) < 1e-9:
        return "BASELINE / FILTER RESEARCH"
    return "RESEARCH (selection-aware)"


def _is_sensitivity_only_hi_mult(row: pd.Series) -> bool:
    mult = _safe(row.get("multiplier"), 1.0)
    notes = str(row.get("notes") or "")
    if mult >= 2.999:
        return True
    if "SENSITIVITY ONLY" in notes.upper() and mult >= 2.999:
        return True
    return False


def _dedupe_ledger(df: pd.DataFrame) -> pd.DataFrame:
    """Keep best source per (market, book, condition, mult)."""
    work = df.copy()
    work["_pref"] = work["source_hub"].map(lambda s: _SOURCE_PREF.get(str(s), 5))
    work = work.sort_values(["_pref", "candidate_NS"], ascending=[True, False])
    keys = ["market", "book_id", "condition_set", "multiplier"]
    return work.drop_duplicates(keys, keep="first").drop(columns=["_pref"])


def _margin_per_unit(market: str) -> float:
    m = str(market).upper()
    if m in MARGIN_USD:
        return float(MARGIN_USD[m])
    # FX / metals CFD proxy: use stop-risk style placeholder when unknown
    fxish = {
        "EURUSD": 2000.0,
        "GBPUSD": 2000.0,
        "USDJPY": 2000.0,
        "AUDJPY": 2000.0,
        "XAUUSD": 5000.0,
        "XAGUSD": 2500.0,
    }
    return float(fxish.get(m, float("nan")))


def _st_pmc_unit_fills(market: str, variant: str, hub: str) -> Optional[Path]:
    m = market.lower()
    sid = f"{m}_hourly_st_pmc_{variant}"
    if hub == "us30_st_pmc_runner_variants":
        p = STATE / hub / "audits" / sid / sid / "unit_fills.csv"
        return p if p.exists() else None
    if hub in ("futures_st_pmc_runner_variants", "fx_index_metals_st_pmc_runner_variants"):
        p = STATE / hub / m / "audits" / sid / sid / "unit_fills.csv"
        return p if p.exists() else None
    return None


def _asia_unit_trades(book_id: str) -> Optional[Path]:
    # S_3_1_3_flt → usdjpy_v2b_asia_range_london_S_3_1_3_flt
    sid = f"usdjpy_v2b_asia_range_london_{book_id}"
    p = STATE / "fx_v2b_asia_range_london_usdjpy_filters" / "states" / sid / "unit_trades.csv"
    return p if p.exists() else None


def _campaign_path(book_id: str) -> Optional[Path]:
    p = STATE / "futures_intraday_condition_profile" / f"{book_id}_campaigns.csv"
    if p.exists():
        return p
    # FX HP books under intraday condition hubs
    for alt in (
        STATE / "intraday_condition_profile" / f"{book_id}_campaigns.csv",
        STATE / "fx_intraday_condition_profile" / f"{book_id}_campaigns.csv",
    ):
        if alt.exists():
            return alt
    return None


def _load_pnl_series(row: pd.Series) -> Optional[pd.DataFrame]:
    """Return DataFrame with columns ts, pnl (native size)."""
    hub = str(row.get("source_hub") or "")
    market = str(row.get("market") or "")
    book = str(row.get("book_id") or "")
    cond = str(row.get("condition_set") or "")
    ctype = str(row.get("candidate_type") or "")

    # ST+PMC finite books
    if hub in (
        "futures_st_pmc_runner_variants",
        "fx_index_metals_st_pmc_runner_variants",
        "us30_st_pmc_runner_variants",
    ):
        variant = book.split("/", 1)[-1] if "/" in book else cond
        path = _st_pmc_unit_fills(market, variant, hub)
        if path is None:
            return None
        df = pd.read_csv(path)
        ts = pd.to_datetime(df["exit_ts"], utc=True, errors="coerce")
        pnl = df["usd"].astype(float) if "usd" in df.columns else df.get("net_usd", pd.Series(dtype=float)).astype(float)
        out = pd.DataFrame({"ts": ts, "pnl": pnl}).dropna()
        return out if len(out) else None

    # Asia range filters
    if hub == "fx_v2b_asia_range_london_usdjpy_filters":
        path = _asia_unit_trades(book)
        if path is None:
            return None
        df = pd.read_csv(path)
        ts = pd.to_datetime(df["exit_ts"], utc=True, errors="coerce")
        pnl = df["net_usd"].astype(float)
        return pd.DataFrame({"ts": ts, "pnl": pnl}).dropna()

    # HP size-up / condition overlays — campaign tapes (baseline size);
    # scale later using ledger net ratio when multiplier != 1.
    if ctype == "size_up" or hub.startswith("futures_intraday") or hub.startswith("intraday_hp"):
        path = _campaign_path(book)
        if path is None:
            return None
        df = pd.read_csv(path)
        # filter condition bucket when present
        if "=" in cond and "condition" not in df.columns:
            # campaigns are full-book; bucket filter via feature columns is complex —
            # use full campaign PnL scaled to match ledger candidate_net later.
            pass
        else:
            # Try bucket column match: condition_set like "Opening 15m range vs ATR=or_norm"
            if "=" in cond:
                feat, bucket = cond.split("=", 1)
                # map known feature names to campaign columns
                col_map = {
                    "Opening 15m range vs ATR": "or15_width_pct",  # not exact; skip filter
                }
                # Prefer notables-style: many campaigns already filtered in size_sensitivity.
                # Use unfiltered campaign dates for span; yearly from size_sensitivity when available.
                pass
        if "exit_ts" in df.columns:
            ts = pd.to_datetime(df["exit_ts"], utc=True, errors="coerce")
        else:
            ts = pd.to_datetime(df["entry_ts"], utc=True, errors="coerce")
        pnl = df["net_usd"].astype(float)
        out = pd.DataFrame({"ts": ts, "pnl": pnl}).dropna()
        return out if len(out) else None

    return None


def _size_sensitivity_row(row: pd.Series) -> Optional[pd.Series]:
    path = STATE / "futures_intraday_hp_live_plan" / "size_sensitivity.csv"
    if not path.exists():
        return None
    sdf = pd.read_csv(path)
    book = str(row.get("book_id") or "")
    cond = str(row.get("condition_set") or "")
    mult = _safe(row.get("multiplier"), 1.0)
    bucket = cond.split("=", 1)[-1] if "=" in cond else ""
    feat = cond.split("=", 1)[0] if "=" in cond else ""
    m = sdf[
        (sdf["book"].astype(str) == book)
        & (sdf["mult"].astype(float).sub(mult).abs() < 1e-9)
    ]
    if bucket:
        m2 = m[m["bucket"].astype(str) == bucket]
        if len(m2):
            m = m2
    if feat and len(m) > 1:
        m2 = m[m["condition"].astype(str) == feat]
        if len(m2):
            m = m2
    if not len(m):
        return None
    return m.iloc[0]


def _span_and_years(series: Optional[pd.DataFrame]) -> Tuple[str, str, float]:
    if series is None or not len(series):
        return "", "", float("nan")
    ts = series["ts"].dropna()
    if not len(ts):
        return "", "", float("nan")
    start = ts.min().tz_convert("America/New_York") if ts.min().tzinfo else ts.min()
    end = ts.max().tz_convert("America/New_York") if ts.max().tzinfo else ts.max()
    days = max((end - start).total_seconds() / 86400.0, 1.0)
    years = days / 365.25
    return str(start.date()), str(end.date()), years


def _worst_calendar_year(series: Optional[pd.DataFrame], scale: float) -> Tuple[str, float]:
    if series is None or not len(series):
        return "", float("nan")
    s = series.copy()
    s["year"] = s["ts"].dt.tz_convert("America/New_York").dt.year if s["ts"].dt.tz is not None else s["ts"].dt.year
    by = s.groupby("year")["pnl"].sum() * scale
    if not len(by):
        return "", float("nan")
    y = int(by.idxmin())
    return str(y), float(by.min())


def _worst_rolling_12m(series: Optional[pd.DataFrame], scale: float) -> float:
    if series is None or not len(series):
        return float("nan")
    s = series.sort_values("ts").copy()
    s["pnl_s"] = s["pnl"] * scale
    # Monthly sum then rolling 12 (drop tz before period to avoid warnings)
    ts_ny = s["ts"].dt.tz_convert("America/New_York") if s["ts"].dt.tz is not None else s["ts"]
    s["ym"] = ts_ny.dt.tz_localize(None).dt.to_period("M")
    monthly = s.groupby("ym")["pnl_s"].sum().sort_index()
    if len(monthly) < 3:
        return float(monthly.sum()) if len(monthly) else float("nan")
    roll = monthly.rolling(12, min_periods=min(12, len(monthly))).sum()
    return float(roll.min())


def _discrete_scale(stress: float) -> Tuple[float, str, int]:
    """Return (scale, sizing_mode, discrete_copies)."""
    if not math.isfinite(stress) or stress <= 0:
        return float("nan"), "unavailable", 0
    copies = int(math.floor(STRESS_BUDGET / stress + 1e-12))
    if copies >= 1:
        return float(copies), "discrete_book_copies", copies
    # Must downsize below native test size
    return STRESS_BUDGET / stress, "fractional_downsize", 0


def _build_row(row: pd.Series) -> Dict[str, Any]:
    net = _safe(row.get("candidate_net"))
    stress = abs(_safe(row.get("candidate_reachable_stress")))
    mtm = abs(_safe(row.get("MTM_drawdown")))
    ns = _safe(row.get("candidate_NS"))
    mult = _safe(row.get("multiplier"), 1.0)
    market = str(row.get("market") or "")
    max_open = _safe(row.get("max_open"), 1.0)
    if not math.isfinite(max_open) or max_open <= 0:
        max_open = 1.0

    scale, sizing_mode, discrete_copies = _discrete_scale(stress)
    # Score uses continuous fill of the stress budget (fair cross-strategy compare).
    # Discrete copies remain a feasibility field for futures/FX lot deployment.
    scale_cont = STRESS_BUDGET / stress if stress > 0 else float("nan")
    scale_use = scale_cont

    scaled_net = net * scale_use
    scaled_stress = stress * scale_use
    scaled_mtm = mtm * scale_use

    margin_unit = _margin_per_unit(market)
    # Approx margin at native book: margin_unit * max_open * (implicit size in test)
    # Size-up books already embed multiplier in stress/net; use max_open when known,
    # else 1 * multiplier as proxy for concurrent units.
    native_contracts = max_open if math.isfinite(max_open) else max(mult, 1.0)
    native_margin = margin_unit * native_contracts if math.isfinite(margin_unit) else float("nan")
    scaled_margin = native_margin * scale_use if math.isfinite(native_margin) else float("nan")

    series = _load_pnl_series(row)
    # For HP campaigns, rescale series so sum matches candidate_net (handles filters/mult)
    if series is not None and len(series) and math.isfinite(net):
        ssum = float(series["pnl"].sum())
        if abs(ssum) > 1e-9:
            series = series.copy()
            series["pnl"] = series["pnl"] * (net / ssum)

    start, end, years = _span_and_years(series)

    # Prefer size_sensitivity yearly when available (HP ladder)
    sens = _size_sensitivity_row(row)
    worst_year = ""
    worst_year_net = float("nan")
    if sens is not None:
        worst_year = str(int(sens["worst_year"])) if pd.notna(sens.get("worst_year")) else ""
        wy = _safe(sens.get("worst_net"))
        # size_sensitivity net is at ladder mult; scale from native sens net to budget
        sens_stress = abs(_safe(sens.get("stress")))
        if sens_stress > 0 and math.isfinite(wy):
            worst_year_net = wy * (scale_use * stress / sens_stress) if stress > 0 else wy * scale_use
        # span from campaigns if missing years
        if not math.isfinite(years) or years <= 0:
            # approximate from best/worst presence — still need campaign span
            pass
    if not worst_year:
        worst_year, worst_year_net = _worst_calendar_year(series, scale_use)

    worst_roll = _worst_rolling_12m(series, scale_use)

    if not math.isfinite(years) or years <= 0:
        # last resort: sample-based stub unknown
        years = float("nan")

    net_per_year = scaled_net / years if math.isfinite(years) and years > 0 else float("nan")
    ann_ret = net_per_year / CAPITAL if math.isfinite(net_per_year) else float("nan")

    pass_dd = math.isfinite(scaled_mtm) and scaled_mtm <= MAX_MTM_DD + 1e-6
    pass_margin = (not math.isfinite(scaled_margin)) or (scaled_margin <= MAX_MARGIN + 1e-6)
    pass_stress = math.isfinite(scaled_stress) and scaled_stress <= STRESS_BUDGET + 1e-6
    span_ok = math.isfinite(years) and years >= 1.0
    inside_limits = bool(
        pass_dd
        and pass_margin
        and pass_stress
        and math.isfinite(scaled_net)
        and scaled_net > 0
        and span_ok
    )

    status = _selection_status(str(row.get("notes") or ""), mult)
    if not span_ok:
        status = f"INSUFFICIENT_SPAN ({status})"

    return {
        "market": market,
        "book_id": str(row.get("book_id") or ""),
        "condition_set": str(row.get("condition_set") or ""),
        "candidate_type": str(row.get("candidate_type") or ""),
        "multiplier": mult,
        "source_hub": str(row.get("source_hub") or ""),
        "selection_status": status,
        "start_date": start,
        "end_date": end,
        "years_observed": years,
        "native_net": net,
        "native_stress": stress,
        "native_mtm_dd": mtm,
        "candidate_NS": ns,
        "delta_NS": _safe(row.get("delta_NS")),
        "size_scale": scale_use,
        "size_scale_continuous": scale_cont,
        "sizing_mode": sizing_mode,
        "discrete_copies": discrete_copies,
        "scaled_cumulative_net": scaled_net,
        "scaled_net_per_year": net_per_year,
        "annualized_return_on_250k": ann_ret,
        "annualized_net_on_250k": net_per_year,  # alias score
        "worst_calendar_year": worst_year,
        "worst_calendar_year_net": worst_year_net,
        "worst_rolling_12m_net": worst_roll,
        "scaled_mtm_dd": scaled_mtm,
        "mtm_dd_pct_of_250k": 100.0 * scaled_mtm / CAPITAL if math.isfinite(scaled_mtm) else float("nan"),
        "scaled_stress": scaled_stress,
        "reachable_stress_pct_of_250k": 100.0 * scaled_stress / CAPITAL if math.isfinite(scaled_stress) else float("nan"),
        "scaled_margin": scaled_margin,
        "margin_use_pct_of_250k": 100.0 * scaled_margin / CAPITAL if math.isfinite(scaled_margin) else float("nan"),
        "pass_mtm_dd": pass_dd,
        "pass_margin": pass_margin,
        "pass_stress": pass_stress,
        "inside_limits": inside_limits,
        "rankable": bool(row.get("rankable")),
        "notes": str(row.get("notes") or "")[:160],
    }


def build_boards(ledger: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df = ledger.copy()
    # Eligible universe: canonical rankable + USD-normalized finite non-inventory
    base = df[
        (df["rankable"] == True)  # noqa: E712
        & (df["USD_normalized"] == True)  # noqa: E712
        & (df["finite"] == True)  # noqa: E712
        & (df["inventory"] != True)  # noqa: E712
        & (df["candidate_reachable_stress"].astype(float) > 0)
        & (df["candidate_net"].astype(float) > 0)
    ].copy()
    base = _dedupe_ledger(base)

    rows = [_build_row(r) for _, r in base.iterrows()]
    all_df = pd.DataFrame(rows)

    # Deployable: exclude sensitivity-only 3×/4×
    deploy = all_df[all_df["multiplier"] < 2.999].copy()

    # Standalone ranking: inside limits preferred, score = annualized net on 250k
    # Rows without usable span sort last even if other limits pass.
    stand = deploy.copy()
    stand["_span_ok"] = stand["years_observed"].apply(lambda y: bool(math.isfinite(y) and y >= 1.0))
    stand["_score"] = stand["annualized_net_on_250k"]
    stand["_ns"] = stand["candidate_NS"]
    stand = stand.sort_values(
        by=["inside_limits", "_span_ok", "_score", "_ns"],
        ascending=[False, False, False, False],
    ).drop(columns=["_score", "_ns", "_span_ok"])

    # Research efficiency: by candidate N/S (same deployable set)
    research = deploy.copy().sort_values(by=["candidate_NS", "delta_NS"], ascending=[False, False])

    # Leverage ladder: all multipliers including 3×/4× (deduped)
    lev = all_df.copy()
    lev = lev.sort_values(
        by=["book_id", "condition_set", "multiplier", "candidate_NS"],
        ascending=[True, True, True, False],
    )

    return stand, research, lev


def _md_table(df: pd.DataFrame, cols: List[str], limit: int = 40) -> List[str]:
    lines = []
    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    lines.extend([header, sep])
    for _, r in df.head(limit).iterrows():
        cells = []
        for c in cols:
            v = r.get(c)
            if c in (
                "scaled_cumulative_net",
                "scaled_net_per_year",
                "annualized_net_on_250k",
                "worst_calendar_year_net",
                "worst_rolling_12m_net",
                "scaled_mtm_dd",
                "scaled_margin",
                "scaled_stress",
                "native_net",
                "native_stress",
            ):
                cells.append(_fmt_money(float(v) if v == v else float("nan"), signed=True))
            elif c in ("annualized_return_on_250k",):
                cells.append(_fmt_pct(100.0 * float(v)) if v == v else "—")
            elif c in (
                "mtm_dd_pct_of_250k",
                "reachable_stress_pct_of_250k",
                "margin_use_pct_of_250k",
                "years_observed",
                "candidate_NS",
                "delta_NS",
                "size_scale",
                "multiplier",
            ):
                if c.endswith("_pct_of_250k"):
                    cells.append(_fmt_pct(float(v)) if v == v else "—")
                elif c == "years_observed":
                    cells.append(_fmt_num(float(v), 2) if v == v else "—")
                elif c in ("candidate_NS", "delta_NS"):
                    cells.append(_fmt_num(float(v), 2) if v == v else "—")
                else:
                    cells.append(_fmt_num(float(v), 2) if v == v else "—")
            elif c == "inside_limits":
                cells.append("YES" if bool(v) else "NO")
            else:
                cells.append(str(v) if v == v and v is not None else "—")
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def write_boards(stand: pd.DataFrame, research: pd.DataFrame, lev: pd.DataFrame) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    stand.to_csv(HUB / "INDIVIDUAL_250K_STANDALONE_RANKING.csv", index=False)
    research.to_csv(HUB / "INDIVIDUAL_250K_RESEARCH_EFFICIENCY.csv", index=False)
    lev.to_csv(HUB / "INDIVIDUAL_250K_LEVERAGE_LADDER.csv", index=False)

    policy = [
        "# INDIVIDUAL_250K_STANDALONE_RANKING",
        "",
        "Policy:",
        "",
        "```text",
        f"capital=${CAPITAL:,.0f}",
        f"stress_budget=${STRESS_BUDGET:,.0f}  (10%)",
        f"max_MTM_DD=${MAX_MTM_DD:,.0f}      (15%)",
        f"max_margin=${MAX_MARGIN:,.0f}      (50%)",
        "score=annualized_net_on_250k",
        "tie_breaker=candidate_NS",
        "sizing=continuous fill of stress_budget for score; discrete_copies for lot feasibility",
        "eligibility=canonical rankable + USD-normalized + finite + years_observed>=1",
        "```",
        "",
        "Historical cumulative equivalents scaled to the common stress budget, then",
        "divided by years observed. **Not** live projections. 3×/4× sensitivity rows",
        "are excluded here — see `INDIVIDUAL_250K_LEVERAGE_LADDER`.",
        "",
        "Selection-aware status is retained: a top N/S expression can be the strongest",
        "research finding without yet being a funded allocation.",
        "",
        f"Rows ranked: {len(stand)} (inside_limits first; min 1y span).",
        "",
    ]
    cols = [
        "market",
        "book_id",
        "condition_set",
        "multiplier",
        "selection_status",
        "start_date",
        "end_date",
        "years_observed",
        "size_scale",
        "sizing_mode",
        "scaled_cumulative_net",
        "scaled_net_per_year",
        "annualized_return_on_250k",
        "candidate_NS",
        "worst_calendar_year",
        "worst_calendar_year_net",
        "worst_rolling_12m_net",
        "mtm_dd_pct_of_250k",
        "reachable_stress_pct_of_250k",
        "margin_use_pct_of_250k",
        "inside_limits",
    ]
    policy.extend(_md_table(stand, cols, limit=50))
    policy.append("")
    (HUB / "INDIVIDUAL_250K_STANDALONE_RANKING.md").write_text("\n".join(policy), encoding="utf-8")

    res_lines = [
        "# INDIVIDUAL_250K_RESEARCH_EFFICIENCY",
        "",
        "Policy:",
        "",
        "```text",
        "score=candidate_NS",
        "tie_breaker=delta_NS",
        "```",
        "",
        "Preserves research ranking under N/S (not $250k annualization).",
        "Same deployable universe (no 3×/4× sensitivity-only rows).",
        "",
        f"Rows: {len(research)}",
        "",
    ]
    rcols = [
        "market",
        "book_id",
        "condition_set",
        "multiplier",
        "selection_status",
        "candidate_NS",
        "delta_NS",
        "native_net",
        "native_stress",
        "years_observed",
        "scaled_net_per_year",
        "inside_limits",
    ]
    res_lines.extend(_md_table(research, rcols, limit=50))
    res_lines.append("")
    (HUB / "INDIVIDUAL_250K_RESEARCH_EFFICIENCY.md").write_text("\n".join(res_lines), encoding="utf-8")

    lev_lines = [
        "# INDIVIDUAL_250K_LEVERAGE_LADDER",
        "",
        "Sensitivity / size ladder including 3×/4×. **Not** a deployable $250k board.",
        "Metrics still normalized to the same $25k stress budget for comparison.",
        "",
        f"Rows: {len(lev)}",
        "",
    ]
    lcols = [
        "market",
        "book_id",
        "condition_set",
        "multiplier",
        "selection_status",
        "candidate_NS",
        "delta_NS",
        "size_scale",
        "scaled_cumulative_net",
        "scaled_net_per_year",
        "annualized_return_on_250k",
        "mtm_dd_pct_of_250k",
        "reachable_stress_pct_of_250k",
        "margin_use_pct_of_250k",
        "inside_limits",
        "years_observed",
    ]
    lev_lines.extend(_md_table(lev, lcols, limit=80))
    lev_lines.append("")
    (HUB / "INDIVIDUAL_250K_LEVERAGE_LADDER.md").write_text("\n".join(lev_lines), encoding="utf-8")


def _email_standalone(stand: pd.DataFrame, research: pd.DataFrame) -> str:
    top = stand[stand["inside_limits"] == True].head(8)  # noqa: E712
    if not len(top):
        top = stand.head(8)
    best_ann = stand.iloc[0] if len(stand) else None
    best_ns = research.iloc[0] if len(research) else None
    lines = [
        "INDIVIDUAL_250K_STANDALONE_RANKING + RESEARCH_EFFICIENCY",
        "",
        f"hub: {HUB}",
        f"policy: capital=${CAPITAL:,.0f} stress_budget=${STRESS_BUDGET:,.0f} "
        f"max_MTM_DD=${MAX_MTM_DD:,.0f} max_margin=${MAX_MARGIN:,.0f}",
        "score=annualized_net_on_250k  tie_breaker=candidate_NS",
        "",
        "Verdict:",
    ]
    if best_ns is not None:
        lines.append(
            f"  Best N/S research candidate: {best_ns['market']} {best_ns['book_id']} "
            f"{best_ns['condition_set']} @{best_ns['multiplier']:.2f}×  "
            f"N/S={best_ns['candidate_NS']:.2f}  status={best_ns['selection_status']}"
        )
    if best_ann is not None:
        lines.append(
            f"  Best annualized $250k standalone (board #1): {best_ann['market']} "
            f"{best_ann['book_id']} {best_ann['condition_set']} @{best_ann['multiplier']:.2f}×  "
            f"ann_net/yr=${best_ann['annualized_net_on_250k']:,.0f}  "
            f"ret={100*best_ann['annualized_return_on_250k']:.1f}%  "
            f"years={best_ann['years_observed']:.2f}  "
            f"inside_limits={best_ann['inside_limits']}  "
            f"status={best_ann['selection_status']}"
        )
    lines.extend(["", "Top standalone (inside limits preferred):", ""])
    for i, (_, r) in enumerate(top.iterrows(), 1):
        lines.append(
            f"{i:2d}. {r['market']:7s} {r['book_id'][:28]:28s} "
            f"@{r['multiplier']:.2f}×  ann/yr=${r['annualized_net_on_250k']:>10,.0f}  "
            f"N/S={r['candidate_NS']:.2f}  yrs={r['years_observed']:.1f}  "
            f"DD%={r['mtm_dd_pct_of_250k']:.1f}  marg%={r['margin_use_pct_of_250k']:.1f}  "
            f"[{r['selection_status']}]"
        )
    lines.extend(
        [
            "",
            "Research efficiency top-5 (by candidate_NS):",
            "",
        ]
    )
    for i, (_, r) in enumerate(research.head(5).iterrows(), 1):
        lines.append(
            f"{i:2d}. {r['market']:7s} {r['book_id'][:28]:28s} "
            f"@{r['multiplier']:.2f}×  N/S={r['candidate_NS']:.2f}  "
            f"ΔN/S={r['delta_NS']:+.2f}  [{r['selection_status']}]"
        )
    lines.extend(
        [
            "",
            "Artifacts:",
            f"  {HUB / 'INDIVIDUAL_250K_STANDALONE_RANKING.md'}",
            f"  {HUB / 'INDIVIDUAL_250K_RESEARCH_EFFICIENCY.md'}",
            "Leverage ladder emailed separately.",
            "",
        ]
    )
    return "\n".join(lines)


def _email_leverage(lev: pd.DataFrame) -> str:
    hi = lev[lev["multiplier"] >= 2.999].sort_values("candidate_NS", ascending=False)
    lines = [
        "INDIVIDUAL_250K_LEVERAGE_LADDER (separate)",
        "",
        f"hub: {HUB}",
        "Sensitivity-only 3×/4× and full size ladder. NOT deployable $250k board.",
        f"Still stress-normalized to ${STRESS_BUDGET:,.0f} for comparison.",
        "",
        f"3×/4× rows: {len(hi)}",
        "",
    ]
    for i, (_, r) in enumerate(hi.head(20).iterrows(), 1):
        lines.append(
            f"{i:2d}. {r['market']:7s} {r['book_id'][:28]:28s} "
            f"@{r['multiplier']:.0f}×  N/S={r['candidate_NS']:.2f}  "
            f"ann/yr=${r['annualized_net_on_250k']:>10,.0f}  "
            f"DD%={r['mtm_dd_pct_of_250k']:.1f}  inside={r['inside_limits']}  "
            f"[{r['selection_status']}]"
        )
    lines.extend(["", f"Full: {HUB / 'INDIVIDUAL_250K_LEVERAGE_LADDER.md'}", ""])
    return "\n".join(lines)


def run(*, email: bool = False) -> Path:
    ledger = pd.read_csv(HUB / "CANDIDATE_LEDGER.csv")
    stand, research, lev = build_boards(ledger)
    write_boards(stand, research, lev)

    email_body = _email_standalone(stand, research)
    lev_body = _email_leverage(lev)
    (HUB / "EMAIL_250K.txt").write_text(email_body, encoding="utf-8")
    (HUB / "EMAIL_250K_LEVERAGE.txt").write_text(lev_body, encoding="utf-8")

    prog = HUB / "PROGRESS.log"
    with prog.open("a", encoding="utf-8") as fh:
        fh.write(
            f"[250k] standalone={len(stand)} research={len(research)} "
            f"leverage={len(lev)} inside_limits="
            f"{int(stand['inside_limits'].sum()) if len(stand) else 0}\n"
        )

    if email:
        from .notify_email import send_email

        send_email(subject="potions: INDIVIDUAL_250K_STANDALONE_RANKING", body=email_body)
        send_email(subject="potions: INDIVIDUAL_250K_LEVERAGE_LADDER", body=lev_body)

    return HUB


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args()
    hub = run(email=bool(args.email))
    print(f"DONE hub={hub}")


if __name__ == "__main__":
    main()
