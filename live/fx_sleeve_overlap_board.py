"""FX sleeve-overlap and joint-stress board.

Pairs (allocator-facing)::

  USDJPY Asia-range (unfiltered S_3_1_3) ↔ USDJPY Monday OR
  USDJPY Asia-range (unfiltered S_3_1_3) ↔ USDJPY filtered Asia (S_3_1_3_flt)
  USDJPY Monday OR ↔ GBPUSD fair 3R
  USDJPY Monday OR ↔ EURUSD ST+PMC Thursday (@1.25× HP sleeve)
  EURUSD ST+PMC Thursday (@1.25×) ↔ GBPUSD fair 3R

Per pair::

  shared active dates · same-direction rate · joint reachable stress ·
  daily P&L correlation · maximum simultaneous margin

Hub::

  live/state/canonical_ns_research/fx_sleeve_overlap/

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.fx_sleeve_overlap_board --email
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .intraday_condition_overlay import score_nets
from .notify_email import send_email
from .regime_overlap import book_identity, overlap_metrics

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "canonical_ns_research" / "fx_sleeve_overlap"
PROFILE = REPO / "live" / "state" / "intraday_condition_profile"

# CFD / OANDA-style research margin proxy (same as $250k board).
MARGIN_USD = {
    "EURUSD": 2000.0,
    "GBPUSD": 2000.0,
    "USDJPY": 2000.0,
}

EURUSD_THU_MULT = 1.25  # validated HP sleeve size


@dataclass
class Sleeve:
    key: str
    label: str
    market: str
    campaigns: List[dict]  # day, dir, net_usd, trade_id
    units: pd.DataFrame  # entry_ts, exit_ts, units, margin_usd (open interval)
    identity: Dict[str, str]
    notes: str = ""


def _ny_day(ts) -> str:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return str(t.date())
    return str(t.tz_convert("America/New_York").date())


def _dir(d: str) -> str:
    s = str(d).lower()
    if s.startswith("l") or s == "buy":
        return "L"
    return "S"


def _units_from_unit_rows(path: Path, *, size_mult: float = 1.0) -> pd.DataFrame:
    """Open intervals from unit_trades / unit_fills (ignore native net columns)."""
    df = pd.read_csv(path)
    return pd.DataFrame(
        {
            "entry_ts": pd.to_datetime(df["entry_ts"], utc=True),
            "exit_ts": pd.to_datetime(df["exit_ts"], utc=True),
            "units": float(size_mult),
        }
    )


def _camps_from_st_pmc_unit_fills(path: Path, *, size_mult: float = 1.0) -> List[dict]:
    """Campaign nets from lot-correct unit_fills ``usd`` column."""
    df = pd.read_csv(path)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True)
    camps: Dict[str, dict] = {}
    for _, r in df.iterrows():
        tid = str(r["trade_id"])
        if tid not in camps:
            camps[tid] = {
                "trade_id": tid,
                "day": _ny_day(r["entry_ts"]),
                "dir": _dir(r["direction"]),
                "entry_ts": str(r["entry_ts"]),
                "exit_ts": str(r["exit_ts"]),
                "net_usd": 0.0,
            }
        camps[tid]["net_usd"] += float(r["usd"]) * float(size_mult)
        # keep latest exit
        if pd.Timestamp(r["exit_ts"], tz="UTC") > pd.Timestamp(camps[tid]["exit_ts"]):
            camps[tid]["exit_ts"] = str(r["exit_ts"])
    return list(camps.values())


def _camps_from_profile(path: Path, *, mask: Optional[pd.Series] = None, size_mult: float = 1.0) -> List[dict]:
    df = pd.read_csv(path)
    if mask is not None:
        df = df.loc[mask].copy()
    out = []
    for _, r in df.iterrows():
        out.append(
            {
                "trade_id": str(r["trade_id"]),
                "day": _ny_day(r["entry_ts"]),
                "dir": _dir(r["side"]),
                "entry_ts": str(r["entry_ts"]),
                "exit_ts": str(r.get("exit_ts") or r["entry_ts"]),
                "net_usd": float(r["net_usd"]) * float(size_mult),
            }
        )
    return out


def _camps_from_fills(path: Path, symbol: str, *, size_mult: float = 1.0) -> List[dict]:
    """Rebuild USD-normalized campaigns from broker fills (same as condition profile)."""
    from .intraday_condition_profile import Book, load_campaigns

    book = Book("tmp", "tmp", symbol, path, "tmp", fee_override=1.5)
    df = load_campaigns(book)
    out = []
    for _, r in df.iterrows():
        out.append(
            {
                "trade_id": str(r["trade_id"]),
                "day": _ny_day(r["entry_ts"]),
                "dir": _dir(r["side"]),
                "entry_ts": str(r["entry_ts"]),
                "exit_ts": str(r["exit_ts"]),
                "net_usd": float(r["net_usd"]) * float(size_mult),
            }
        )
    return out


def _units_from_fills_qty(path: Path, *, size_mult: float = 1.0) -> pd.DataFrame:
    """Campaign open windows sized by entry quantity (Monday OR etc.)."""
    fills = pd.read_csv(path)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True)
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1.0)
    rows: List[dict] = []
    for tid, g in fills.sort_values("ts").groupby("trade_id"):
        entries = g[g["reason"].astype(str) == "entry"]
        exits = g[g["reason"].astype(str) != "entry"]
        if entries.empty:
            continue
        entry_ts = entries["ts"].iloc[0]
        open_qty = float(entries["quantity"].sum()) * float(size_mult)
        if open_qty <= 0:
            continue
        exit_ts = exits["ts"].max() if not exits.empty else g["ts"].iloc[-1]
        rows.append({"entry_ts": entry_ts, "exit_ts": exit_ts, "units": open_qty})
    return pd.DataFrame(rows)


def _attach_margin(units: pd.DataFrame, market: str) -> pd.DataFrame:
    m = float(MARGIN_USD[market.upper()])
    out = units.copy()
    out["margin_usd"] = out["units"].astype(float) * m
    return out


def max_simultaneous_margin(units_a: pd.DataFrame, units_b: pd.DataFrame) -> Dict[str, float]:
    """Peak sum of open margin across both sleeves (event-sweep)."""
    events: List[Tuple[pd.Timestamp, float]] = []
    for u in (units_a, units_b):
        if u is None or u.empty:
            continue
        for _, r in u.iterrows():
            m = float(r["margin_usd"])
            events.append((pd.Timestamp(r["entry_ts"]), +m))
            events.append((pd.Timestamp(r["exit_ts"]), -m))
    if not events:
        return {"max_simultaneous_margin": 0.0, "max_open_margin_a": 0.0, "max_open_margin_b": 0.0}

    def _peak(one: pd.DataFrame) -> float:
        if one is None or one.empty:
            return 0.0
        ev = []
        for _, r in one.iterrows():
            m = float(r["margin_usd"])
            ev.append((pd.Timestamp(r["entry_ts"]), +m))
            ev.append((pd.Timestamp(r["exit_ts"]), -m))
        ev.sort(key=lambda x: (x[0], -x[1]))
        cur = peak = 0.0
        for _, dm in ev:
            cur += dm
            if cur > peak:
                peak = cur
        return peak

    events.sort(key=lambda x: (x[0], -x[1]))  # entries before exits at same ts
    cur = peak = 0.0
    for _, dm in events:
        cur += dm
        if cur > peak:
            peak = cur
    return {
        "max_simultaneous_margin": round(peak, 2),
        "max_open_margin_a": round(_peak(units_a), 2),
        "max_open_margin_b": round(_peak(units_b), 2),
    }


def joint_reachable_stress(camps_a: Sequence[dict], camps_b: Sequence[dict]) -> Dict[str, float]:
    """Path stress of summed daily nets (union calendar); additive upper bound too."""
    daily_a: Dict[str, float] = {}
    daily_b: Dict[str, float] = {}
    for c in camps_a:
        daily_a[c["day"]] = daily_a.get(c["day"], 0.0) + float(c["net_usd"])
    for c in camps_b:
        daily_b[c["day"]] = daily_b.get(c["day"], 0.0) + float(c["net_usd"])
    days = sorted(set(daily_a) | set(daily_b))
    joint = np.array([daily_a.get(d, 0.0) + daily_b.get(d, 0.0) for d in days], dtype=float)
    sc = score_nets(joint, label="joint")
    sc_a = score_nets(np.array([daily_a.get(d, 0.0) for d in sorted(daily_a)], dtype=float))
    sc_b = score_nets(np.array([daily_b.get(d, 0.0) for d in sorted(daily_b)], dtype=float))
    shared = sorted(set(daily_a) & set(daily_b))
    shared_joint = np.array(
        [daily_a[d] + daily_b[d] for d in shared], dtype=float
    ) if shared else np.array([], dtype=float)
    sc_shared = score_nets(shared_joint, label="shared_days")
    return {
        "joint_reachable_stress": round(float(sc["stress"]), 2),
        "joint_net": round(float(sc["net"]), 2),
        "joint_ns": round(float(sc["ns"]), 3),
        "joint_mtm_dd": round(float(sc["max_dd"]), 2),
        "shared_day_joint_stress": round(float(sc_shared["stress"]), 2),
        "stress_a": round(float(sc_a["stress"]), 2),
        "stress_b": round(float(sc_b["stress"]), 2),
        "additive_stress_upper_bound": round(float(sc_a["stress"] + sc_b["stress"]), 2),
    }


def load_sleeves() -> Dict[str, Sleeve]:
    asia_unfilt_units_path = (
        REPO
        / "live/state/fx_v2b_asia_range_london_usdjpy_sizing/states"
        / "usdjpy_v2b_asia_range_london_S_3_1_3/unit_trades.csv"
    )
    asia_unfilt_fills = (
        REPO
        / "live/state/fx_v2b_asia_range_london_usdjpy_sizing/states"
        / "usdjpy_v2b_asia_range_london_S_3_1_3/fills.csv"
    )
    asia_flt_units_path = (
        REPO
        / "live/state/fx_v2b_asia_range_london_usdjpy_filters/states"
        / "usdjpy_v2b_asia_range_london_S_3_1_3_flt/unit_trades.csv"
    )
    monor_fills = (
        REPO
        / "live/state/monday_or_phase2/tuneup_broker/states"
        / "usdjpy_m2_s3_r1_skip_augsep/fills.csv"
    )
    monor_camps_path = PROFILE / "usdjpy_monday_or_campaigns.csv"
    asia_flt_camps_path = PROFILE / "usdjpy_asia_range_campaigns.csv"
    gbpusd_units_path = (
        REPO
        / "live/state/fx_index_metals_st_pmc_runner_variants/gbpusd/audits"
        / "gbpusd_hourly_st_pmc_sl50_tp150_3r_1mfill"
        / "gbpusd_hourly_st_pmc_sl50_tp150_3r_1mfill/unit_fills.csv"
    )
    eurusd_units_path = (
        REPO
        / "live/state/fx_index_metals_st_pmc_runner_variants/eurusd/audits"
        / "eurusd_hourly_st_pmc_sl50_tp150_3r_1mfill"
        / "eurusd_hourly_st_pmc_sl50_tp150_3r_1mfill/unit_fills.csv"
    )
    eurusd_camps_path = PROFILE / "eurusd_st_pmc_3r_campaigns.csv"

    asia_u_camps = _camps_from_fills(asia_unfilt_fills, "USDJPY")
    asia_u_units = _units_from_unit_rows(asia_unfilt_units_path)

    asia_f_camps = _camps_from_profile(asia_flt_camps_path)
    asia_f_units = _units_from_unit_rows(asia_flt_units_path)

    monor_camps = _camps_from_profile(monor_camps_path)
    monor_units = _units_from_fills_qty(monor_fills)

    gbp_camps = _camps_from_st_pmc_unit_fills(gbpusd_units_path)
    gbp_units = _units_from_unit_rows(gbpusd_units_path)

    eur_all = pd.read_csv(eurusd_camps_path)
    thu_mask = eur_all["dow"].astype(str) == "Thursday"
    eur_thu_camps = _camps_from_profile(eurusd_camps_path, mask=thu_mask, size_mult=EURUSD_THU_MULT)
    eur_units_all = pd.read_csv(eurusd_units_path)
    eur_units_all["entry_ts"] = pd.to_datetime(eur_units_all["entry_ts"], utc=True)
    eur_units_all["exit_ts"] = pd.to_datetime(eur_units_all["exit_ts"], utc=True)
    thu_days = {c["day"] for c in eur_thu_camps}
    # Match Thursday HP sleeve by NY session date of entry (trade_id schemes differ).
    eur_u = eur_units_all[
        eur_units_all["entry_ts"].dt.tz_convert("America/New_York").map(lambda t: str(t.date())).isin(thu_days)
        & (eur_units_all["entry_ts"].dt.tz_convert("America/New_York").dt.day_name() == "Thursday")
    ].copy()
    eur_thu_units = pd.DataFrame(
        {
            "entry_ts": eur_u["entry_ts"],
            "exit_ts": pd.to_datetime(eur_u["exit_ts"], utc=True),
            "units": EURUSD_THU_MULT,
        }
    )

    sleeves = {
        "asia_unfilt": Sleeve(
            key="asia_unfilt",
            label="USDJPY Asia-range unfiltered S_3_1_3",
            market="USDJPY",
            campaigns=asia_u_camps,
            units=_attach_margin(asia_u_units, "USDJPY"),
            identity=book_identity(
                market="usdjpy",
                strategy="v2b_asia_range_london",
                book="S_3_1_3",
                strategy_id="usdjpy_v2b_asia_range_london_S_3_1_3",
                hub="fx_v2b_asia_range_london_usdjpy_sizing",
            ),
            notes="THREE_BOOK A / unfiltered shadow",
        ),
        "asia_flt": Sleeve(
            key="asia_flt",
            label="USDJPY filtered Asia S_3_1_3_flt",
            market="USDJPY",
            campaigns=asia_f_camps,
            units=_attach_margin(asia_f_units, "USDJPY"),
            identity=book_identity(
                market="usdjpy",
                strategy="v2b_asia_range_london",
                book="S_3_1_3_flt",
                strategy_id="usdjpy_v2b_asia_range_london_S_3_1_3_flt",
                hub="fx_v2b_asia_range_london_usdjpy_filters",
            ),
            notes="THREE_BOOK C / demo promote",
        ),
        "monday_or": Sleeve(
            key="monday_or",
            label="USDJPY Monday OR M2_S3_R1 skip Aug/Sep",
            market="USDJPY",
            campaigns=monor_camps,
            units=_attach_margin(monor_units, "USDJPY"),
            identity=book_identity(
                market="usdjpy",
                strategy="monday_or_breakout",
                book="M2_S3_R1_skip_augsep",
                strategy_id="usdjpy_m2_s3_r1_skip_augsep",
                hub="monday_or_phase2/tuneup_broker",
            ),
        ),
        "gbpusd_3r": Sleeve(
            key="gbpusd_3r",
            label="GBPUSD fair 3R (sl50/tp150)",
            market="GBPUSD",
            campaigns=gbp_camps,
            units=_attach_margin(gbp_units, "GBPUSD"),
            identity=book_identity(
                market="gbpusd",
                strategy="hourly_st_pmc",
                book="sl50_tp150_3r_1mfill",
                strategy_id="gbpusd_hourly_st_pmc_sl50_tp150_3r_1mfill",
                hub="fx_index_metals_st_pmc_runner_variants",
            ),
        ),
        "eurusd_thu": Sleeve(
            key="eurusd_thu",
            label="EURUSD ST+PMC Thursday @1.25×",
            market="EURUSD",
            campaigns=eur_thu_camps,
            units=_attach_margin(eur_thu_units, "EURUSD"),
            identity=book_identity(
                market="eurusd",
                strategy="hourly_st_pmc",
                version="Thursday_x1.25",
                book="sl50_tp150_3r_1mfill",
                strategy_id="eurusd_st_pmc_3r_thursday_x1.25",
                hub="intraday_condition_profile + hp_sizeup",
            ),
            notes="SIZE-UP VALIDATED Thursday HP sleeve",
        ),
    }
    return sleeves


PAIRS: List[Tuple[str, str, str]] = [
    ("asia_unfilt", "monday_or", "USDJPY Asia-range ↔ USDJPY Monday OR"),
    ("asia_unfilt", "asia_flt", "USDJPY Asia-range ↔ USDJPY filtered Asia"),
    ("monday_or", "gbpusd_3r", "USDJPY Monday OR ↔ GBPUSD fair 3R"),
    ("monday_or", "eurusd_thu", "USDJPY Monday OR ↔ EURUSD ST+PMC Thursday"),
    ("eurusd_thu", "gbpusd_3r", "EURUSD ST+PMC Thursday ↔ GBPUSD fair 3R"),
]

# Demo-book appendix (filtered promote is what runs live/paper).
OPS_APPENDIX: List[Tuple[str, str, str]] = [
    ("asia_flt", "monday_or", "USDJPY filtered Asia (demo) ↔ USDJPY Monday OR"),
]


def pair_row(sa: Sleeve, sb: Sleeve, title: str, *, appendix: bool = False) -> Dict[str, Any]:
    ov = overlap_metrics(
        sa.label,
        sa.campaigns,
        sb.label,
        sb.campaigns,
        identity_a=sa.identity,
        identity_b=sb.identity,
    )
    j = joint_reachable_stress(sa.campaigns, sb.campaigns)
    m = max_simultaneous_margin(sa.units, sb.units)
    nested = (
        sa.key == "asia_unfilt"
        and sb.key == "asia_flt"
    ) or (
        sa.key == "asia_flt"
        and sb.key == "asia_unfilt"
    )
    return {
        "pair": title,
        "appendix": bool(appendix),
        "nested_filter": bool(nested),
        "sleeve_a": sa.label,
        "sleeve_b": sb.label,
        "a_campaigns": ov["a_campaigns"],
        "b_campaigns": ov["b_campaigns"],
        "shared_active_dates": ov["shared_ny_session_dates"],
        "union_active_dates": ov["union_ny_session_dates"],
        "day_jaccard": ov["day_jaccard"],
        "same_direction_rate": ov["dir_agree_rate_on_shared"],
        "same_day_same_dir_events": ov["same_day_same_dir_events"],
        "daily_pnl_corr": ov["shared_day_pnl_corr"],
        "union_daily_pnl_corr": ov["union_day_pnl_corr"],
        "corr_days": ov["corr_days"],
        "joint_reachable_stress": j["joint_reachable_stress"],
        "shared_day_joint_stress": j["shared_day_joint_stress"],
        "additive_stress_upper_bound": j["additive_stress_upper_bound"],
        "joint_net": j["joint_net"],
        "joint_ns": j["joint_ns"],
        "stress_a": j["stress_a"],
        "stress_b": j["stress_b"],
        "max_simultaneous_margin": m["max_simultaneous_margin"],
        "max_open_margin_a": m["max_open_margin_a"],
        "max_open_margin_b": m["max_open_margin_b"],
        "regime_class": ov["regime_class"],
        "recommended_sizing": ov["recommended_sizing"],
        "margin_per_unit_a": MARGIN_USD[sa.market],
        "margin_per_unit_b": MARGIN_USD[sb.market],
        "notes_a": sa.notes,
        "notes_b": sb.notes,
    }


def _money(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "n/a"
    sign = "+" if x >= 0 else "-"
    return "%s$%s" % (sign, "{:,.0f}".format(abs(x)))


def _pct(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return "%.1f%%" % (100.0 * float(x))


def _rho(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/a"
    return "%+.3f" % float(x)


def render_md(rows: List[Dict[str, Any]]) -> str:
    lines = [
        "# FX sleeve-overlap & joint-stress board",
        "",
        "Not another leverage ladder — pairwise **active-date overlap**, direction",
        "agreement, **joint reachable stress** (path DD of summed daily nets),",
        "daily P&L correlation, and **maximum simultaneous margin**.",
        "",
        "Margin proxy: EURUSD/GBPUSD/USDJPY = **$2,000 / unit** (same as $250k board).",
        "EURUSD Thursday sleeve sized at **1.25×** (SIZE-UP VALIDATED).",
        "Asia-range = unfiltered `S_3_1_3` (THREE_BOOK A); filtered Asia = `S_3_1_3_flt` (C).",
        "Unfiltered↔filtered is a **nested SAME_SLEEVE** (flt ⊂ unfilt) — joint stress /",
        "margin if both are stacked is a counterfactual warning, not a deployable book.",
        "",
        "Driver: `python -m live.fx_sleeve_overlap_board --email`",
        "",
        "## Board",
        "",
        "| pair | shared dates | same-dir rate | joint stress | daily ρ | max simul. margin | regime |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    primary = [r for r in rows if not r.get("appendix")]
    appendix = [r for r in rows if r.get("appendix")]
    for r in primary:
        lines.append(
            "| %s | %d | %s | %s | %s | %s | %s |"
            % (
                r["pair"],
                int(r["shared_active_dates"]),
                _pct(r["same_direction_rate"]),
                _money(-abs(float(r["joint_reachable_stress"]))),
                _rho(r["daily_pnl_corr"]),
                _money(float(r["max_simultaneous_margin"])),
                r["regime_class"],
            )
        )
    if appendix:
        lines.extend(
            [
                "",
                "### Ops appendix (demo filtered Asia)",
                "",
                "| pair | shared dates | same-dir rate | joint stress | daily ρ | max simul. margin | regime |",
                "|---|---:|---:|---:|---:|---:|---|",
            ]
        )
        for r in appendix:
            lines.append(
                "| %s | %d | %s | %s | %s | %s | %s |"
                % (
                    r["pair"],
                    int(r["shared_active_dates"]),
                    _pct(r["same_direction_rate"]),
                    _money(-abs(float(r["joint_reachable_stress"]))),
                    _rho(r["daily_pnl_corr"]),
                    _money(float(r["max_simultaneous_margin"])),
                    r["regime_class"],
                )
            )
    lines.extend(
        [
            "",
            "## Detail",
            "",
        ]
    )
    for r in rows:
        lines.extend(
            [
                "### %s" % r["pair"],
                "",
                "- **A:** %s (n=%d, stress=%s, max margin=%s)"
                % (
                    r["sleeve_a"],
                    int(r["a_campaigns"]),
                    _money(-abs(float(r["stress_a"]))),
                    _money(float(r["max_open_margin_a"])),
                ),
                "- **B:** %s (n=%d, stress=%s, max margin=%s)"
                % (
                    r["sleeve_b"],
                    int(r["b_campaigns"]),
                    _money(-abs(float(r["stress_b"]))),
                    _money(float(r["max_open_margin_b"])),
                ),
                "- Shared active NY dates: **%d** / union %d (Jaccard %.3f)"
                % (
                    int(r["shared_active_dates"]),
                    int(r["union_active_dates"]),
                    float(r["day_jaccard"]),
                ),
                "- Same-direction rate on shared dates: **%s** (%d same-day same-dir events)"
                % (_pct(r["same_direction_rate"]), int(r["same_day_same_dir_events"])),
                "- Daily P&L corr (shared days): **%s** (n=%d); union corr %s"
                % (_rho(r["daily_pnl_corr"]), int(r["corr_days"]), _rho(r["union_daily_pnl_corr"])),
                "- Joint reachable stress (union daily path): **%s** · shared-day path %s · additive UB %s"
                % (
                    _money(-abs(float(r["joint_reachable_stress"]))),
                    _money(-abs(float(r["shared_day_joint_stress"]))),
                    _money(-abs(float(r["additive_stress_upper_bound"]))),
                ),
                "- Joint net / N/S: %s / %.2f"
                % (_money(float(r["joint_net"])), float(r["joint_ns"])),
                "- Max simultaneous margin: **%s**"
                % _money(float(r["max_simultaneous_margin"])),
                "- Regime class: **%s** — %s" % (r["regime_class"], r["recommended_sizing"]),
            ]
        )
        if r.get("nested_filter"):
            lines.append(
                "- **Nested filter:** filtered ⊂ unfiltered; do not sum nets/margin as "
                "independent risk — pick one Asia book."
            )
        lines.append("")
    lines.extend(
        [
            "## Read guide",
            "",
            "- **SEPARATE_REGIMES** — low calendar overlap and weak shared-day linkage; still",
            "  respect portfolio stress / margin caps.",
            "- **CONDITIONAL_OVERLAP** — sparse co-firing but high same-dir or ρ when both",
            "  active → apply a simultaneous-signal shared risk cap.",
            "- **SAME_SLEEVE** — meaningful overlap + high conditional linkage → one",
            "  allocation, do not stack full independent risk.",
            "",
        ]
    )
    return "\n".join(lines)


def render_email(rows: List[Dict[str, Any]]) -> str:
    lines = [
        "FX sleeve-overlap & joint-stress board",
        "Hub: live/state/canonical_ns_research/fx_sleeve_overlap/",
        "",
        "pair | shared | same-dir | joint stress | daily ρ | max margin | regime",
        "-" * 72,
    ]
    for r in rows:
        lines.append(
            "%s | %d | %s | %s | %s | %s | %s"
            % (
                r["pair"],
                int(r["shared_active_dates"]),
                _pct(r["same_direction_rate"]),
                _money(-abs(float(r["joint_reachable_stress"]))),
                _rho(r["daily_pnl_corr"]),
                _money(float(r["max_simultaneous_margin"])),
                r["regime_class"],
            )
        )
    # Stance hints
    lines.extend(["", "Stance tips:"])
    for r in rows:
        tip = r["regime_class"]
        if tip == "SAME_SLEEVE":
            stance = "do not stack full independent risk"
        elif tip == "CONDITIONAL_OVERLAP":
            stance = "shared risk cap when both fire"
        elif tip == "SEPARATE_REGIMES":
            stance = "independent allocations ok under portfolio caps"
        else:
            stance = "research only"
        lines.append("- %s → %s (%s)" % (r["pair"], tip, stance))
    lines.append("")
    lines.append("Artifacts: BOARD.md · overlap_board.csv · EMAIL.txt")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    HUB.mkdir(parents=True, exist_ok=True)
    sleeves = load_sleeves()
    rows = []
    for ka, kb, title in PAIRS:
        rows.append(pair_row(sleeves[ka], sleeves[kb], title))
    for ka, kb, title in OPS_APPENDIX:
        rows.append(pair_row(sleeves[ka], sleeves[kb], title, appendix=True))

    df = pd.DataFrame(rows)
    df.to_csv(HUB / "overlap_board.csv", index=False)
    md = render_md(rows)
    (HUB / "BOARD.md").write_text(md, encoding="utf-8")
    email = render_email(rows)
    (HUB / "EMAIL.txt").write_text(email, encoding="utf-8")
    meta = {
        "pairs": len(rows),
        "margin_usd": MARGIN_USD,
        "eurusd_thu_mult": EURUSD_THU_MULT,
        "hub": str(HUB.relative_to(REPO)),
    }
    (HUB / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    # Also publish a pointer under canonical boards index
    boards = REPO / "live/state/canonical_ns_research/BOARDS.md"
    if boards.exists():
        text = boards.read_text(encoding="utf-8")
        marker = "## 6. FX sleeve-overlap & joint-stress"
        block = (
            "## 6. FX sleeve-overlap & joint-stress\n\n"
            "Built by `python -m live.fx_sleeve_overlap_board [--email]`.\n\n"
            "| Board | Path |\n|---|---|\n"
            "| Pairwise overlap / joint stress / max margin | "
            "[`fx_sleeve_overlap/BOARD.md`](fx_sleeve_overlap/BOARD.md) |\n\n"
        )
        if marker in text:
            # replace section through next ## or EOF
            start = text.index(marker)
            rest = text[start + len(marker) :]
            nxt = rest.find("\n## ")
            if nxt >= 0:
                text = text[:start] + block + rest[nxt + 1 :]
            else:
                text = text[:start] + block
        else:
            text = text.rstrip() + "\n\n" + block
        boards.write_text(text, encoding="utf-8")

    print(md)
    if args.email:
        send_email(subject="potions: FX sleeve-overlap & joint-stress board", body=email)
        print("emailed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
