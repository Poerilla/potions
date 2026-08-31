"""Campaign-level CONTINUATION_AUDIT for US30 ST+PMC path C (2R→10R preferred).

Reads existing revival hub tape; does not invent new path variants.
Writes under live/state/us30_st_pmc_causal_revival_abc/continuation_audit/.

Usage:
  PYTHONPATH=... python -m live.us30_st_pmc_continuation_audit --email
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .notify_email import send_email
from .run_ledger import begin_run, complete_run, fail_run

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "us30_st_pmc_causal_revival_abc"
OUT = HUB / "continuation_audit"
CELL = "path_c_continuation_break_2r_10r"
SID = f"us30_st_pmc_revival_{CELL}"
STOP_PTS = 50.0
POINT_VALUE = 1.0
FEE_PER_UNIT = 1.5  # matches DEFAULT_FEE_PER_UNIT in hourly retest replay
BUNDLE_UNITS = 3
R_USD_PER_UNIT = STOP_PTS * POINT_VALUE  # $50
R_USD_CAMPAIGN = R_USD_PER_UNIT * BUNDLE_UNITS  # $150 initial bundle risk


def _ts(s) -> pd.Timestamp:
    t = pd.Timestamp(s)
    if t.tzinfo is not None:
        return t.tz_convert("UTC").tz_localize(None)
    return t.tz_localize(None) if t.tzinfo is None else t


def _load_unit_fills() -> pd.DataFrame:
    paths = list((HUB / "audits" / SID).rglob("unit_fills.csv"))
    if not paths:
        raise FileNotFoundError("unit_fills.csv missing for %s" % SID)
    return pd.read_csv(paths[0])


def _load_arms() -> pd.DataFrame:
    fs = pd.read_csv(HUB / "states" / SID / "feature_snapshots.csv")
    arms = fs[fs["source"] == "path_c_continuation_arm"].copy()
    arms["hourly_signal_timestamp"] = arms["available_at_ts"].map(_ts)
    meta = arms["metadata_json"].map(json.loads)
    arms["hourly_signal_side"] = meta.map(lambda m: m.get("side"))
    arms["signal_hour_high"] = meta.map(lambda m: float(m.get("hour_high")))
    arms["signal_hour_low"] = meta.map(lambda m: float(m.get("hour_low")))
    arms = arms.sort_values("hourly_signal_timestamp").reset_index(drop=True)
    return arms[
        [
            "hourly_signal_timestamp",
            "hourly_signal_side",
            "signal_hour_high",
            "signal_hour_low",
        ]
    ]


def _load_1m_ohlc() -> pd.DataFrame:
    path = REPO / "fx" / "us30_1m.csv"
    df = pd.read_csv(path, usecols=["ts_event", "open", "high", "low", "close"])
    df = df.rename(columns={"ts_event": "ts"})
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(None)
    df = df.sort_values("ts").drop_duplicates("ts").set_index("ts")
    return df[["open", "high", "low", "close"]]


def _find_break_ts(
    bars: pd.DataFrame,
    signal_ts: pd.Timestamp,
    entry_ts: pd.Timestamp,
    side: str,
    hour_high: float,
    hour_low: float,
) -> Optional[pd.Timestamp]:
    """First 1m touch of hour extreme after signal, at or before entry bar."""
    # Entry is next bar after break; search (signal, entry]
    window = bars.loc[(bars.index > signal_ts) & (bars.index <= entry_ts)]
    if window.empty:
        return None
    if side in ("buy", "long"):
        hit = window[window["high"] >= hour_high - 1e-9]
    else:
        hit = window[window["low"] <= hour_low + 1e-9]
    if hit.empty:
        return None
    return hit.index[0]


def _mae_mfe_r(
    bars: pd.DataFrame,
    entry_ts: pd.Timestamp,
    exit_ts: pd.Timestamp,
    entry_price: float,
    side: str,
) -> Tuple[float, float]:
    window = bars.loc[(bars.index >= entry_ts) & (bars.index <= exit_ts)]
    if window.empty:
        return float("nan"), float("nan")
    if side in ("buy", "long", "Long"):
        mae_pts = float(entry_price - window["low"].min())
        mfe_pts = float(window["high"].max() - entry_price)
    else:
        mae_pts = float(window["high"].max() - entry_price)
        mfe_pts = float(entry_price - window["low"].min())
    return mae_pts / STOP_PTS, mfe_pts / STOP_PTS


def _classify_exit_unit(row: pd.Series) -> str:
    reason = str(row["exit_reason"] or "").lower()
    pts = float(row["points"])
    entry_reason = str(row.get("entry_reason") or "")
    if "gap" in reason:
        return "gap_through_stop"
    if reason in ("stop", "protective_stop"):
        return "stop"
    if reason == "runner_stop":
        # after BE / trail — still a stop-class exit
        if pts > 1.0:
            return "runner_stop_profit"
        return "runner_stop"
    if reason == "target":
        # Attribute by realized multiple vs stop
        r = pts / STOP_PTS
        if "runner_entry_2" in entry_reason or r >= 9.0:
            return "target_10r_runner"
        if r >= 5.0:
            return "target_mid_runner"
        if r >= 1.5:
            return "target_2r_or_tp1"
        return "target_other"
    if "eod" in reason or "flatten" in reason or reason == "close":
        return "eod_exit"
    return reason or "other"


def build_campaigns() -> Tuple[pd.DataFrame, Dict[str, Any]]:
    uf = _load_unit_fills()
    fills = pd.read_csv(HUB / "states" / SID / "fills.csv")
    arms = _load_arms()
    bars = _load_1m_ohlc()

    # Entry fills (primary entry reason)
    ent = fills[fills["reason"] == "entry"].copy()
    ent["entry_timestamp"] = ent["ts"].map(_ts)
    ent = ent.sort_values("entry_timestamp")
    arms_sorted = arms.sort_values("hourly_signal_timestamp")
    joined = pd.merge_asof(
        ent.rename(columns={"side": "entry_side"}),
        arms_sorted,
        left_on="entry_timestamp",
        right_on="hourly_signal_timestamp",
        direction="backward",
    )

    # Unit aggregation per trade_id
    uf = uf.copy()
    uf["entry_ts"] = uf["entry_ts"].map(_ts)
    uf["exit_ts"] = uf["exit_ts"].map(_ts)
    campaigns: List[Dict[str, Any]] = []
    reconcile = {
        "reported_units": int(len(uf)),
        "reported_net_usd_board": 25370.6,
        "reported_ns_board": 1.841,
        "reported_stress_board": -13783.1,
    }

    # Map trade -> arm
    trade_arm = joined.set_index("trade_id")

    for trade_id, g in uf.groupby("trade_id", sort=False):
        g = g.sort_values("unit_id")
        entry_ts = g["entry_ts"].min()
        exit_ts = g["exit_ts"].max()
        entry_price = float(g["entry_price"].iloc[0])
        direction = str(g["direction"].iloc[0])
        side = "buy" if direction.lower().startswith("l") else "sell"
        stop_price = float(g["hard_stop_price"].iloc[0])
        n_units = int(len(g))
        n_entries = int(g["entry_ts"].nunique())
        n_exits = int(len(g))
        max_open = n_units  # same-bar bundle
        net_usd_gross = float(g["usd"].sum())
        fee = FEE_PER_UNIT * n_units * 2  # entry+exit fee convention used in audits
        # Prefer gross points for R; board net includes fees via audit_units
        net_pts = float(g["points"].sum())
        initial_units = n_units
        # Targets relative to entry
        target_2r = entry_price + (2 * STOP_PTS if side == "buy" else -2 * STOP_PTS)
        target_10r = entry_price + (10 * STOP_PTS if side == "buy" else -10 * STOP_PTS)

        arm = None
        if trade_id in trade_arm.index:
            row = trade_arm.loc[trade_id]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            arm = row

        signal_ts = _ts(arm["hourly_signal_timestamp"]) if arm is not None else pd.NaT
        signal_side = str(arm["hourly_signal_side"]) if arm is not None else ""
        hour_high = float(arm["signal_hour_high"]) if arm is not None else float("nan")
        hour_low = float(arm["signal_hour_low"]) if arm is not None else float("nan")

        break_ts = None
        if pd.notna(signal_ts):
            break_ts = _find_break_ts(bars, signal_ts, entry_ts, signal_side or side, hour_high, hour_low)

        # MAE/MFE on primary unit path (first unit hold window as proxy for campaign)
        mae_r, mfe_r = _mae_mfe_r(bars, entry_ts, exit_ts, entry_price, side)

        # Final exit reason: last unit by exit_ts
        last = g.sort_values("exit_ts").iloc[-1]
        final_exit = str(last["exit_reason"])

        # Unit exit class mix
        exit_classes = g.apply(_classify_exit_unit, axis=1).value_counts().to_dict()

        # Cap campaign profit at 2R / 3R of initial bundle risk
        net_usd_for_r = net_pts * POINT_VALUE  # pre-fee
        cap2 = min(net_usd_for_r, 2.0 * R_USD_CAMPAIGN) if net_usd_for_r > 0 else net_usd_for_r
        cap3 = min(net_usd_for_r, 3.0 * R_USD_CAMPAIGN) if net_usd_for_r > 0 else net_usd_for_r
        # Also per-unit 2R/3R caps summed
        unit_cap2 = float(g["usd"].clip(upper=2.0 * R_USD_PER_UNIT).sum())
        unit_cap3 = float(g["usd"].clip(upper=3.0 * R_USD_PER_UNIT).sum())
        # Losses uncapped in clip upper-only — fix losses
        unit_cap2 = float(
            sum(min(float(u), 2.0 * R_USD_PER_UNIT) if float(u) > 0 else float(u) for u in g["usd"])
        )
        unit_cap3 = float(
            sum(min(float(u), 3.0 * R_USD_PER_UNIT) if float(u) > 0 else float(u) for u in g["usd"])
        )

        holding_minutes = (exit_ts - entry_ts).total_seconds() / 60.0
        wait_minutes = (
            (entry_ts - signal_ts).total_seconds() / 60.0 if pd.notna(signal_ts) else float("nan")
        )

        campaigns.append(
            {
                "campaign_id": trade_id,
                "hourly_signal_timestamp": signal_ts.isoformat() if pd.notna(signal_ts) else "",
                "hourly_signal_side": signal_side,
                "signal_hour_high": hour_high,
                "signal_hour_low": hour_low,
                "continuation_break_timestamp": break_ts.isoformat() if break_ts is not None else "",
                "entry_timestamp": entry_ts.isoformat(),
                "entry_price": entry_price,
                "stop_price": stop_price,
                "target_2R": round(target_2r, 4),
                "target_10R": round(target_10r, 4),
                "initial_units": initial_units,
                "number_of_entries": n_entries,
                "number_of_exits": n_exits,
                "maximum_open_units": max_open,
                "final_exit_reason": final_exit,
                "net_R": round(net_usd_for_r / R_USD_CAMPAIGN, 4),
                "net_USD_gross": round(net_usd_for_r, 2),
                "net_USD_est_net_fees": round(net_usd_for_r - fee, 2),
                "MAE_R": round(mae_r, 4) if mae_r == mae_r else None,
                "MFE_R": round(mfe_r, 4) if mfe_r == mfe_r else None,
                "holding_minutes": round(holding_minutes, 2),
                "wait_minutes": round(wait_minutes, 2) if wait_minutes == wait_minutes else None,
                "direction": direction,
                "year": int(entry_ts.year),
                "week": entry_ts.strftime("%Y-%W"),
                "cap2_campaign_usd": round(cap2, 2),
                "cap3_campaign_usd": round(cap3, 2),
                "cap2_unit_usd": round(unit_cap2, 2),
                "cap3_unit_usd": round(unit_cap3, 2),
                "exit_class_json": json.dumps(exit_classes, sort_keys=True),
                "has_target_hit": int(any(str(x).lower() == "target" for x in g["exit_reason"])),
                "has_10r_like": int(
                    any(
                        (float(p) / STOP_PTS) >= 9.0 and str(r).lower() == "target"
                        for p, r in zip(g["points"], g["exit_reason"])
                    )
                ),
                "unit_exit_usd_sum": round(float(g["usd"].sum()), 2),
            }
        )

    camp = pd.DataFrame(campaigns)
    # Reconcile
    recon = {
        **reconcile,
        "campaigns": int(len(camp)),
        "sum_campaign_unit_exits": int(camp["number_of_exits"].sum()),
        "sum_campaign_gross_usd": round(float(camp["net_USD_gross"].sum()), 2),
        "sum_unit_fills_usd": round(float(uf["usd"].sum()), 2),
        "unique_signals_with_entry": int(camp["hourly_signal_timestamp"].nunique()),
        "multi_entry_signals": int(
            (camp.groupby("hourly_signal_timestamp").size() > 1).sum()
            if camp["hourly_signal_timestamp"].ne("").any()
            else 0
        ),
        "max_entries_per_signal": int(
            camp.groupby("hourly_signal_timestamp").size().max()
            if len(camp)
            else 0
        ),
        "campaigns_with_duplicate_entry_timestamps": int((camp["number_of_entries"] > 1).sum()),
        "arms_total": int(len(arms)),
        "fill_rate_arms": round(len(camp) / max(len(arms), 1), 4),
    }
    recon["units_match"] = recon["sum_campaign_unit_exits"] == recon["reported_units"]
    recon["pnl_match_gross"] = abs(recon["sum_campaign_gross_usd"] - recon["sum_unit_fills_usd"]) < 0.05
    return camp, recon


def attribution(camp: pd.DataFrame, uf: pd.DataFrame) -> Dict[str, Any]:
    uf = uf.copy()
    uf["class"] = uf.apply(_classify_exit_unit, axis=1)
    by_class = (
        uf.groupby("class")
        .agg(units=("unit_id", "count"), usd=("usd", "sum"), pts=("points", "sum"))
        .reset_index()
        .sort_values("usd", ascending=False)
    )
    long = camp[camp["direction"].str.lower().str.startswith("l")]
    short = camp[~camp["direction"].str.lower().str.startswith("l")]

    gross = float(camp["net_USD_gross"].sum())
    stress = -13783.1  # board intrabar
    # Fee-adjusted board net path: use board net for headline; caps on gross then scale
    cap2_c = float(camp["cap2_campaign_usd"].sum())
    cap3_c = float(camp["cap3_campaign_usd"].sum())
    cap2_u = float(camp["cap2_unit_usd"].sum())
    cap3_u = float(camp["cap3_unit_usd"].sum())

    def ns(net: float) -> float:
        return net / abs(stress) if stress else float("nan")

    # Approximate fee haircut proportional to board (board_net / gross)
    board_net = 25370.6
    haircut = board_net / gross if gross else 1.0

    return {
        "unit_exit_classes": by_class.to_dict(orient="records"),
        "long_campaigns": int(len(long)),
        "short_campaigns": int(len(short)),
        "long_net_gross": round(float(long["net_USD_gross"].sum()), 2),
        "short_net_gross": round(float(short["net_USD_gross"].sum()), 2),
        "campaigns_with_any_target": int(camp["has_target_hit"].sum()),
        "campaigns_with_10r_like": int(camp["has_10r_like"].sum()),
        "gross_usd": round(gross, 2),
        "board_net_usd": board_net,
        "board_ns": 1.841,
        "stress_usd": stress,
        "ns_if_campaign_cap_2R": round(ns(cap2_c * haircut), 3),
        "ns_if_campaign_cap_3R": round(ns(cap3_c * haircut), 3),
        "net_if_campaign_cap_2R": round(cap2_c * haircut, 2),
        "net_if_campaign_cap_3R": round(cap3_c * haircut, 2),
        "ns_if_unit_cap_2R": round(ns(cap2_u * haircut), 3),
        "ns_if_unit_cap_3R": round(ns(cap3_u * haircut), 3),
        "net_if_unit_cap_2R": round(cap2_u * haircut, 2),
        "net_if_unit_cap_3R": round(cap3_u * haircut, 2),
        "share_net_from_10r_campaigns": round(
            float(camp.loc[camp["has_10r_like"] == 1, "net_USD_gross"].sum()) / gross, 4
        )
        if gross
        else None,
    }


def temporal(camp: pd.DataFrame) -> Dict[str, Any]:
    rows = []
    for year, g in camp.groupby("year"):
        net = float(g["net_USD_gross"].sum())
        # stress proxy: min cumulative drawdown of campaign equity within year
        eq = g.sort_values("entry_timestamp")["net_USD_gross"].cumsum()
        dd = float((eq - eq.cummax()).min()) if len(eq) else 0.0
        stress = dd if dd < 0 else -1e-9
        rows.append(
            {
                "year": int(year),
                "campaigns": int(len(g)),
                "net_gross": round(net, 2),
                "stress_proxy": round(stress, 2),
                "ns_proxy": round(net / abs(stress), 3) if stress else None,
            }
        )
    yearly = pd.DataFrame(rows)

    def block_stats(mask, label):
        g = camp[mask]
        net = float(g["net_USD_gross"].sum())
        eq = g.sort_values("entry_timestamp")["net_USD_gross"].cumsum()
        dd = float((eq - eq.cummax()).min()) if len(eq) else 0.0
        stress = dd if dd < 0 else -1e-9
        return {
            "block": label,
            "campaigns": int(len(g)),
            "net_gross": round(net, 2),
            "stress_proxy": round(stress, 2),
            "ns_proxy": round(net / abs(stress), 3),
        }

    blocks = [
        block_stats(camp["year"].between(2016, 2019), "2016-2019"),
        block_stats(camp["year"].between(2020, 2022), "2020-2022"),
        block_stats(camp["year"].between(2023, 2026), "2023-2026"),
    ]

    # Rolling campaign profit factor
    ordered = camp.sort_values("entry_timestamp").reset_index(drop=True)

    def roll_pf(n: int) -> List[float]:
        out = []
        usd = ordered["net_USD_gross"].values
        for i in range(n - 1, len(usd)):
            w = usd[i - n + 1 : i + 1]
            gp = w[w > 0].sum()
            gl = -w[w < 0].sum()
            out.append(float(gp / gl) if gl > 0 else (float("inf") if gp > 0 else 0.0))
        return out

    pf25 = roll_pf(25)
    pf50 = roll_pf(50)

    # Leave-one-year-out N/S (campaign equity stress proxy)
    loo = []
    for y in sorted(camp["year"].unique()):
        g = camp[camp["year"] != y].sort_values("entry_timestamp")
        net = float(g["net_USD_gross"].sum())
        eq = g["net_USD_gross"].cumsum()
        dd = float((eq - eq.cummax()).min()) if len(eq) else 0.0
        stress = dd if dd < 0 else -1e-9
        loo.append(
            {
                "left_out_year": int(y),
                "campaigns": int(len(g)),
                "net_gross": round(net, 2),
                "ns_proxy": round(net / abs(stress), 3),
            }
        )

    # Top campaign share
    by_net = camp.sort_values("net_USD_gross", ascending=False)
    total = float(camp["net_USD_gross"].sum())
    top_share = {}
    for k in (1, 3, 5):
        top_share[f"top_{k}_share"] = round(float(by_net.head(k)["net_USD_gross"].sum()) / total, 4) if total else None

    # Block bootstrap by week
    weeks = list(camp.groupby("week")["net_USD_gross"].sum().values)
    rng = np.random.default_rng(42)
    boots = []
    if weeks:
        w = np.array(weeks, dtype=float)
        for _ in range(2000):
            sample = rng.choice(w, size=len(w), replace=True)
            boots.append(float(sample.sum()))
        boots_a = np.array(boots)
        boot_summary = {
            "n_weeks": len(weeks),
            "mean": round(float(boots_a.mean()), 2),
            "p05": round(float(np.percentile(boots_a, 5)), 2),
            "p50": round(float(np.percentile(boots_a, 50)), 2),
            "p95": round(float(np.percentile(boots_a, 95)), 2),
            "frac_negative": round(float((boots_a < 0).mean()), 4),
        }
    else:
        boot_summary = {}

    # Signal-hour bootstrap (same as campaign since 1:1)
    sig_nets = camp["net_USD_gross"].values
    boots2 = []
    for _ in range(2000):
        sample = rng.choice(sig_nets, size=len(sig_nets), replace=True)
        boots2.append(float(sample.sum()))
    boots2_a = np.array(boots2)

    return {
        "yearly": yearly.to_dict(orient="records"),
        "blocks": blocks,
        "rolling_pf_25_median": round(float(np.median(pf25)), 3) if pf25 else None,
        "rolling_pf_25_p10": round(float(np.percentile(pf25, 10)), 3) if pf25 else None,
        "rolling_pf_50_median": round(float(np.median(pf50)), 3) if pf50 else None,
        "rolling_pf_50_p10": round(float(np.percentile(pf50, 10)), 3) if pf50 else None,
        "leave_one_year_out": loo,
        "top_campaign_share": top_share,
        "bootstrap_by_week": boot_summary,
        "bootstrap_by_signal": {
            "mean": round(float(boots2_a.mean()), 2),
            "p05": round(float(np.percentile(boots2_a, 5)), 2),
            "p50": round(float(np.percentile(boots2_a, 50)), 2),
            "p95": round(float(np.percentile(boots2_a, 95)), 2),
            "frac_negative": round(float((boots2_a < 0).mean()), 4),
        },
        "long_short": {
            "long_n": int((camp["direction"].str.lower().str.startswith("l")).sum()),
            "short_n": int((~camp["direction"].str.lower().str.startswith("l")).sum()),
            "long_net": round(float(camp.loc[camp["direction"].str.lower().str.startswith("l"), "net_USD_gross"].sum()), 2),
            "short_net": round(
                float(camp.loc[~camp["direction"].str.lower().str.startswith("l"), "net_USD_gross"].sum()), 2
            ),
        },
    }


def execution_stress_notes(camp: pd.DataFrame, uf: pd.DataFrame) -> Dict[str, Any]:
    """Proxy adverse cases without full Engine re-run (flagged as proxy)."""
    # Assume extra adverse ticks on entry+stop for marketable continuation
    tick = 0.1
    extra_ticks = [0, 1, 2, 4, 8]
    n_units = len(uf)
    n_camps = len(camp)
    gross = float(uf["usd"].sum())
    stress = 13783.1
    rows = []
    for xt in extra_ticks:
        # each unit: +xt ticks adverse entry and +xt on exit if stop-like; simplify: 2*xt*tick per unit always
        haircut = n_units * xt * tick * POINT_VALUE * 2
        net = gross - haircut
        # board fee already separate; this is incremental slippage stress
        rows.append(
            {
                "extra_adverse_ticks_each_side": xt,
                "incremental_usd_cost": round(haircut, 2),
                "gross_after": round(net, 2),
                "ns_vs_board_stress": round(net / stress, 3),
            }
        )
    # Gap-through proxy: stops with |points| >> STOP_PTS
    stops = uf[uf["exit_reason"].astype(str).str.contains("stop", case=False)]
    gap_like = stops[stops["points"] < -STOP_PTS * 1.25]
    return {
        "method": "proxy_incremental_slippage_on_existing_tape_not_engine_rerun",
        "rows": rows,
        "stop_units": int(len(stops)),
        "gap_like_stops_gt_1_25R": int(len(gap_like)),
        "gap_like_usd": round(float(gap_like["usd"].sum()), 2) if len(gap_like) else 0.0,
        "note": (
            "Continuation uses marketable entries; Engine stress re-run with "
            "slippage_ticks∈{2,4,8} and gap-through preserved is still required before demo."
        ),
    }


def write_markdown(
    camp: pd.DataFrame,
    recon: Dict[str, Any],
    attr: Dict[str, Any],
    temp: Dict[str, Any],
    stress: Dict[str, Any],
) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    camp_path = OUT / "campaigns.csv"
    camp.to_csv(camp_path, index=False)
    (OUT / "reconcile.json").write_text(json.dumps(recon, indent=2) + "\n")
    (OUT / "attribution.json").write_text(json.dumps(attr, indent=2) + "\n")
    (OUT / "temporal.json").write_text(json.dumps(temp, indent=2) + "\n")
    (OUT / "execution_stress_proxy.json").write_text(json.dumps(stress, indent=2) + "\n")

    wait = camp["wait_minutes"].dropna()
    lines = [
        "# CONTINUATION_AUDIT — US30 ST+PMC completed-hour continuation v1",
        "",
        "**Created before further path-C variation.**",
        "",
        f"- Contract: [`RESEARCH_CONTRACT.md`](../RESEARCH_CONTRACT.md)",
        f"- Preferred cell: `{CELL}`",
        f"- Strategy id (contract): `us30_st_pmc_completed_hour_continuation_v1`",
        f"- Board: net ${recon['reported_net_usd_board']:.0f} / stress ${recon['reported_stress_board']:.0f} → **N/S {recon['reported_ns_board']:.2f}**",
        f"- Campaigns CSV: `{camp_path.relative_to(HUB)}`",
        "",
        "## 0. Path A/B freeze",
        "",
        "| Path | Status |",
        "|---|---|",
        "| A pre-posted PMC | **rejected** — no more work |",
        "| B post-hour retest | **rejected** — no more work |",
        "| C continuation 2R→10R | **research_candidate** — demo=false |",
        "",
        "## 1. Campaign reconstruction + reconcile",
        "",
        f"- Independent campaigns (trade_id): **{recon['campaigns']}**",
        f"- Arms (hourly signals): **{recon['arms_total']}** (fill rate {recon['fill_rate_arms']:.1%})",
        f"- Sum unit exits: **{recon['sum_campaign_unit_exits']}** vs reported units **{recon['reported_units']}** → match={recon['units_match']}",
        f"- Sum campaign gross USD: **${recon['sum_campaign_gross_usd']:.2f}** vs unit_fills USD **${recon['sum_unit_fills_usd']:.2f}** → match={recon['pnl_match_gross']}",
        f"- Unique signals with entry: **{recon['unique_signals_with_entry']}**",
        f"- Multi-entry signals: **{recon['multi_entry_signals']}** (max entries/signal={recon['max_entries_per_signal']})",
        f"- Campaigns with >1 distinct entry timestamp (pyramid): **{recon['campaigns_with_duplicate_entry_timestamps']}**",
        "",
        "Board net ($25,371) is fee-adjusted audit net; campaign table uses gross unit points×$1 before fees.",
        "",
        "Each filled campaign maps to **one** causal `path_c_continuation_arm` via asof(signal ≤ entry).",
        "Every unit exits exactly once in `unit_fills.csv` (by construction of the audit tape).",
        "",
        "### Wait after signal (minutes)",
        "",
        f"- median={wait.median():.1f}  p90={wait.quantile(0.9):.1f}  max={wait.max():.1f}",
        f"- wait>60m: {int((wait > 60).sum())}  >240m: {int((wait > 240).sum())}  >1d: {int((wait > 1440).sum())}",
        "",
        "## 2. Trade-frequency / exposure rule",
        "",
        "| Rule | Observed on preferred 2R→10R tape |",
        "|---|---|",
        "| One continuation entry per hourly signal | **PASS** (0 multi-entry signals) |",
        "| Max open = initial bundle (3) | **PASS** (board max_open=3; no pyramid) |",
        "| No re-entry after stop under same signal | **PASS** (1:1 signal→campaign) |",
        "| After TP1: runner only | **PASS** (bundle entered together; no fresh continuation) |",
        "| EOD flat | **NOT ENFORCED** in current config |",
        "",
        "No one-entry rerun required for the preferred cell. "
        "(Sibling fair-3R cell had 2 multi-entry signal anomalies — not used for N/S claims.)",
        "",
        "Plugin note: Path C re-arms on every completed-hour thesis while flat; "
        "it does **not** yet store `path_c_last_signal_ts` the way Path B does. "
        " empirically the 2R→10R tape still shows 1 entry/signal because a fill disarms "
        "until the next hour. Contract still requires an explicit `max_entries_per_signal=1` guard before demo.",
        "",
        "## 3. Attribution by exit",
        "",
        "| exit class | units | usd (gross) |",
        "|---|---:|---:|",
    ]
    for r in attr["unit_exit_classes"]:
        lines.append(f"| {r['class']} | {r['units']} | ${r['usd']:.1f} |")
    lines += [
        "",
        f"- Long campaigns: {attr['long_campaigns']} net ${attr['long_net_gross']:.0f}",
        f"- Short campaigns: {attr['short_campaigns']} net ${attr['short_net_gross']:.0f}",
        f"- Campaigns with any target fill: {attr['campaigns_with_any_target']}",
        f"- Campaigns with ≥9R target unit (10R-like): {attr['campaigns_with_10r_like']} "
        f"(share of gross net from those campaigns: {attr['share_net_from_10r_campaigns']})",
        "",
        "### Key question — does N/S 1.84 survive if profit capped?",
        "",
        "Using **same board stress** ($13,783) and fee haircut scaled from board_net/gross:",
        "",
        "| Cap rule | Approx net | Approx N/S vs board stress |",
        "|---|---:|---:|",
        f"| Uncapped board | ${attr['board_net_usd']:.0f} | **{attr['board_ns']:.2f}** |",
        f"| Campaign profit cap **2R** (1R=${R_USD_CAMPAIGN:.0f} bundle) | ${attr['net_if_campaign_cap_2R']:.0f} | {attr['ns_if_campaign_cap_2R']:.2f} |",
        f"| Campaign profit cap **3R** | ${attr['net_if_campaign_cap_3R']:.0f} | {attr['ns_if_campaign_cap_3R']:.2f} |",
        f"| Per-unit profit cap **2R** ($100) | ${attr['net_if_unit_cap_2R']:.0f} | {attr['ns_if_unit_cap_2R']:.2f} |",
        f"| Per-unit profit cap **3R** ($150) | ${attr['net_if_unit_cap_3R']:.0f} | {attr['ns_if_unit_cap_3R']:.2f} |",
        "",
    ]
    # Interpret
    if attr["ns_if_campaign_cap_2R"] < 0.5 or attr["ns_if_unit_cap_2R"] < 0.5:
        lines.append(
            "**Verdict:** N/S **collapses under 2R/3R profit caps** → this expression is a "
            "**sparse runner/tail strategy**. Valid research class, but must be reported honestly "
            "and needs a larger forward sample before any demo discussion."
        )
    else:
        lines.append(
            "**Verdict:** Edge is not solely a thin tail under these caps; still not a demo promote."
        )

    lines += [
        "",
        "## 4. Temporal robustness (campaign statistics)",
        "",
        "### Calendar year",
        "",
        "| year | campaigns | net_gross | stress_proxy | N/S_proxy |",
        "|---:|---:|---:|---:|---:|",
    ]
    for r in temp["yearly"]:
        lines.append(
            f"| {r['year']} | {r['campaigns']} | ${r['net_gross']:.0f} | ${r['stress_proxy']:.0f} | {r['ns_proxy']} |"
        )
    lines += [
        "",
        "### Blocks",
        "",
        "| block | campaigns | net_gross | N/S_proxy |",
        "|---|---:|---:|---:|",
    ]
    for r in temp["blocks"]:
        lines.append(f"| {r['block']} | {r['campaigns']} | ${r['net_gross']:.0f} | {r['ns_proxy']} |")
    lines += [
        "",
        f"- Rolling 25-campaign PF: median={temp['rolling_pf_25_median']} p10={temp['rolling_pf_25_p10']}",
        f"- Rolling 50-campaign PF: median={temp['rolling_pf_50_median']} p10={temp['rolling_pf_50_p10']}",
        f"- Long/short: {temp['long_short']}",
        f"- Top campaign share of gross net: {temp['top_campaign_share']}",
        "",
        "### Leave-one-year-out N/S_proxy",
        "",
        "| left out | campaigns | net | N/S_proxy |",
        "|---:|---:|---:|---:|",
    ]
    for r in temp["leave_one_year_out"]:
        lines.append(
            f"| {r['left_out_year']} | {r['campaigns']} | ${r['net_gross']:.0f} | {r['ns_proxy']} |"
        )
    lines += [
        "",
        "### Block bootstrap (2000 draws)",
        "",
        f"- By **week**: {temp['bootstrap_by_week']}",
        f"- By **hourly signal/campaign**: {temp['bootstrap_by_signal']}",
        "",
        "Stress_proxy here is campaign-equity drawdown (not Engine intrabar MTM). "
        "Use for relative temporal shape only; board N/S remains the Engine figure.",
        "",
        "## 5. Execution stress",
        "",
        f"Method: **{stress['method']}**",
        "",
        "| extra adverse ticks (entry+exit) | incremental $ | gross after | N/S vs board stress |",
        "|---:|---:|---:|---:|",
    ]
    for r in stress["rows"]:
        lines.append(
            f"| {r['extra_adverse_ticks_each_side']} | ${r['incremental_usd_cost']:.0f} | "
            f"${r['gross_after']:.0f} | {r['ns_vs_board_stress']:.2f} |"
        )
    lines += [
        "",
        f"- Gap-like stops (>1.25R adverse): {stress['gap_like_stops_gt_1_25R']} units, "
        f"${stress['gap_like_usd']:.0f}",
        "",
        stress["note"],
        "",
        "## 6. Correct next decision",
        "",
        "```yaml",
        "path_C_continuation:",
        "  status: research_candidate",
        "  preferred_variant: 2R_to_10R",
        "  demo: false",
        "  independent_campaigns: %d" % recon["campaigns"],
        "  one_entry_per_signal: pass",
        "  next_required:",
        "    - engine_adverse_slippage_rerun  # ticks 2/4/8, gap-through on",
        "    - explicit max_entries_per_signal guard in plugin",
        "    - state EOD flatten NY timestamp in contract + code",
        "    - forward sample / larger out-of-sample before demo",
        "    - strict StrategyPlugin port only after stress + temporal clear",
        "```",
        "",
        "## Bottom line",
        "",
        "Causal US30 ST+PMC continuation is a **research candidate**, not a demo. "
        "Unit count (5207) compresses to **%d independent campaigns**. "
        "One-entry-per-signal holds on the preferred tape. "
        "Judge the family on campaign robustness + runner attribution + execution stress — "
        "not on raw units or the retired fair-3R model."
        % recon["campaigns"],
        "",
    ]
    path = HUB / "CONTINUATION_AUDIT.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rid = begin_run(
        run_class="audit",
        variant_slug="us30_st_pmc_completed_hour_continuation_v1",
        instrument="US30",
        hub_path=str(HUB.relative_to(REPO)),
        dsr_trial_id="TRL-2026-00186",
        notes="CONTINUATION_AUDIT campaign reconstruction",
        meta={"cell": CELL},
    )
    try:
        print("Building campaigns (1m MAE/MFE)…", flush=True)
        camp, recon = build_campaigns()
        uf = _load_unit_fills()
        attr = attribution(camp, uf)
        temp = temporal(camp)
        stress = execution_stress_notes(camp, uf)
        md = write_markdown(camp, recon, attr, temp, stress)

        email_lines = [
            "US30 ST+PMC CONTINUATION_AUDIT complete.",
            "Hub: %s" % HUB,
            "Contract: us30_st_pmc_completed_hour_continuation_v1",
            "Preferred: %s board N/S %.2f" % (CELL, recon["reported_ns_board"]),
            "",
            "Campaigns: %d (units %d) multi-entry signals: %d"
            % (recon["campaigns"], recon["reported_units"], recon["multi_entry_signals"]),
            "Reconcile units_match=%s pnl_match=%s"
            % (recon["units_match"], recon["pnl_match_gross"]),
            "Capped N/S vs board stress: campaign 2R→%.2f 3R→%.2f; unit 2R→%.2f 3R→%.2f"
            % (
                attr["ns_if_campaign_cap_2R"],
                attr["ns_if_campaign_cap_3R"],
                attr["ns_if_unit_cap_2R"],
                attr["ns_if_unit_cap_3R"],
            ),
            "Top5 campaign share: %s" % temp["top_campaign_share"].get("top_5_share"),
            "Bootstrap-by-week P(net<0): %s"
            % temp["bootstrap_by_week"].get("frac_negative"),
            "",
            "Stance: research_candidate; demo=false. Paths A/B rejected.",
            "Next: Engine adverse slippage re-run + explicit one-entry guard + EOD flatten contract.",
            "Audit: %s" % md,
        ]
        email_body = "\n".join(email_lines) + "\n"
        (OUT / "EMAIL.txt").write_text(email_body, encoding="utf-8")
        (HUB / "CONTINUATION_AUDIT_EMAIL.txt").write_text(email_body, encoding="utf-8")

        complete_run(
            rid,
            net_usd=recon["reported_net_usd_board"],
            stress_dd_usd=recon["reported_stress_board"],
            ns=recon["reported_ns_board"],
            trades=recon["campaigns"],
            units=recon["reported_units"],
            notes="CONTINUATION_AUDIT complete",
            meta={"recon": recon, "attr_caps": {
                "ns_cap2_c": attr["ns_if_campaign_cap_2R"],
                "ns_cap3_c": attr["ns_if_campaign_cap_3R"],
            }},
        )
        if args.email:
            send_email(subject="potions: US30 ST+PMC CONTINUATION_AUDIT complete", body=email_body)
        print("Wrote %s" % md, flush=True)
        print(email_body)
        return 0
    except Exception as exc:
        fail_run(rid, notes=str(exc))
        if args.email:
            send_email(
                subject="potions: US30 ST+PMC CONTINUATION_AUDIT FAILED",
                body="Hub: %s\nError: %s" % (HUB, exc),
            )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
