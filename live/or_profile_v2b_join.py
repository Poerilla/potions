"""OR profile -> v2b join, policy derivation and causal validation.

Part 3/4 of the OR Profile Probability Engine plan:

``join`` subcommand
    Joins the OR profile engine session tapes (trigger=touch, which matches
    live v2b stop fills) to the v2b ``S_1_1_3`` unit tapes by session date,
    reports v2b expectancy per terminal day label (diagnostic; labels are
    only knowable at EOD) and per pre-entry-knowable state (OR width
    quartile, gap bucket, OR location — all knowable at 09:45 when v2b arms
    its resting stops), then derives candidate policies on the fit window
    only and freezes them into ``policies.json``.

``validate`` subcommand
    Replays the validation window (sessions strictly after --fit-end)
    through Engine+PaperBroker with the frozen policies, using only
    existing v2b_scaleout config mechanisms:
      - skip gate  -> restrict ``regime_dates``
      - size tiers -> split dates into tier lists, one replay per tier with
        integer-scaled S_1_1_3 sizing, merged unit audit
    and compares net / stress DD / net-per-session vs the untouched
    S_1_1_3 baseline over the same window.

Usage (from repo root):
  python -m live.or_profile_v2b_join join --asof 2026H2 --markets nq mnq --fit-end 2024-12-31
  python -m live.or_profile_v2b_join validate --asof 2026H2 --markets nq mnq --fit-end 2024-12-31
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import (
    MARKETS,
    _regime_dates,
    load_1m_by_ny_date_any,
)
from .bars import rth_bars
from .v2b_strategy_replay import (
    AuditBar,
    DEFAULT_SLIPPAGE_TICKS,
    FEE_PER_UNIT,
    fast_intraday_audit,
    units_from_v2b_fills,
)

REPO = Path(__file__).resolve().parents[1]
ENGINE_ROOT = REPO / "live" / "state" / "or_profile_engine"
TAPE_ROOT = REPO / "live" / "state" / "v2b_sizing_sweep" / "states"

TRIGGER = "touch"
MIN_CELL_SESSIONS = 40
MIN_YEAR_SESSIONS = 10
STABILITY_THRESHOLD = 0.70

# Pre-entry-knowable dims at 09:45 (when v2b arms resting stops).
PREENTRY_DIMS: List[Tuple[str, ...]] = [
    ("or_width_q",),
    ("gap_bucket",),
    ("or_loc_bucket",),
    ("or_width_q", "gap_bucket"),
]
# Knowable at entry time (the entry IS the break) — reported, not used for skip.
ENTRYTIME_DIMS: List[Tuple[str, ...]] = [("first_break_side",), ("break_tod_bucket",)]

# Integer-clean sizing tiers as multiples of the S_1_1_3 block (tp1/tp2/runner).
SIZING_TIERS: Dict[str, Dict[str, int]] = {
    "1x": {"entry_qty": 5, "tp1_qty": 1, "tp2_qty": 1},     # 1/1/3 baseline
    "2x": {"entry_qty": 10, "tp1_qty": 2, "tp2_qty": 2},    # 2/2/6
    "no_runner": {"entry_qty": 2, "tp1_qty": 1, "tp2_qty": 1},  # 1/1/0
    "runner_3r": {"entry_qty": 5, "tp1_qty": 1, "tp2_qty": 1},  # 1/1/3 + runner TP at 3R
}

# Extension-chain ladder thresholds (a priori from OR profile plan).
CHAIN_HIGH = 0.30  # -> runner_3r
CHAIN_LOW = 0.18  # -> no_runner
MIN_CHAIN_N1 = 30
MIN_CHAIN_N2 = 20


# ---------------------------------------------------------------------------
# Loading + joining
# ---------------------------------------------------------------------------


def load_sessions(asof: str, market: str) -> pd.DataFrame:
    path = ENGINE_ROOT / market / asof / "sessions.csv"
    df = pd.read_csv(path, keep_default_na=False)
    df = df[df["trigger"] == TRIGGER].copy()
    df["session_date"] = pd.to_datetime(df["session_date"]).dt.date
    return df


def load_v2b_daily_net(market: str) -> pd.DataFrame:
    path = TAPE_ROOT / ("%s_v2b_sizing_S_1_1_3" % market) / "unit_trades.csv"
    units = pd.read_csv(path)
    units["session_date"] = pd.to_datetime(units["entry_ts"], utc=True).dt.tz_convert(
        "America/New_York"
    ).dt.date
    daily = units.groupby("session_date").agg(
        v2b_net_usd=("net_usd", "sum"),
        v2b_units=("net_usd", "size"),
        v2b_trades=("trade_id", "nunique"),
    )
    return daily.reset_index()


def join_market(asof: str, market: str) -> pd.DataFrame:
    sessions = load_sessions(asof, market)
    daily = load_v2b_daily_net(market)
    joined = sessions.merge(daily, on="session_date", how="inner")
    joined["year"] = pd.to_datetime(joined["session_date"].astype(str)).dt.year
    return joined


# ---------------------------------------------------------------------------
# Expectancy stats
# ---------------------------------------------------------------------------


def _cell_row(dims: Tuple[str, ...], key, grp: pd.DataFrame, overall_mean: float) -> Dict[str, object]:
    net = grp["v2b_net_usd"]
    gross_pos = float(net[net > 0].sum())
    gross_neg = float(-net[net < 0].sum())
    yearly = grp.groupby("year")["v2b_net_usd"].agg(["mean", "size"])
    qual = yearly[yearly["size"] >= MIN_YEAR_SESSIONS]
    edge = float(net.mean()) - overall_mean
    if len(qual) and edge != 0:
        agree = int(((qual["mean"] - overall_mean) * edge > 0).sum())
        stability = agree / len(qual)
    else:
        stability = float("nan")
    keys = key if isinstance(key, tuple) else (key,)
    return {
        "condition": "|".join("%s=%s" % (d, v) for d, v in zip(dims, keys)),
        "n_sessions": len(grp),
        "total_net": round(float(net.sum()), 2),
        "mean_net": round(float(net.mean()), 2),
        "median_net": round(float(net.median()), 2),
        "win_rate": round(float((net > 0).mean()), 3),
        "profit_factor": round(gross_pos / gross_neg, 3) if gross_neg > 0 else float("inf"),
        "edge_vs_all": round(edge, 2),
        "stability_frac": round(stability, 3) if not math.isnan(stability) else "",
        "stability_years": len(qual),
    }


def expectancy_tables(joined: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    overall_mean = float(joined["v2b_net_usd"].mean())
    label_rows = [
        _cell_row(("label",), key, grp, overall_mean) for key, grp in joined.groupby("label")
    ]
    label_df = pd.DataFrame(label_rows).sort_values("mean_net")

    state_rows: List[Dict[str, object]] = []
    for dims in PREENTRY_DIMS + ENTRYTIME_DIMS:
        valid = joined
        for d in dims:
            valid = valid[valid[d].astype(str) != ""]
        for key, grp in valid.groupby(list(dims)):
            row = _cell_row(dims, key, grp, overall_mean)
            row["knowable"] = "0945" if dims in PREENTRY_DIMS else "entry"
            state_rows.append(row)
    state_df = pd.DataFrame(state_rows).sort_values("mean_net")
    return label_df, state_df


# ---------------------------------------------------------------------------
# Policy derivation (fit window only)
# ---------------------------------------------------------------------------


def derive_policies(
    joined_fit: pd.DataFrame,
    sessions_fit: pd.DataFrame,
    market: str,
) -> Dict[str, object]:
    overall_mean = float(joined_fit["v2b_net_usd"].mean())
    policies: Dict[str, object] = {"market": market, "overall_fit_mean_net": round(overall_mean, 2)}

    # P1 skip gate: 09:45-knowable single-dim cells, negative mean, stable sign.
    skip_cells: List[Dict[str, object]] = []
    for dims in PREENTRY_DIMS:
        if len(dims) > 1:
            continue
        valid = joined_fit[joined_fit[dims[0]].astype(str) != ""]
        for key, grp in valid.groupby(dims[0]):
            row = _cell_row(dims, key, grp, overall_mean)
            if (
                row["n_sessions"] >= MIN_CELL_SESSIONS
                and float(row["mean_net"]) < 0
                and row["stability_frac"] != ""
                and float(row["stability_frac"]) >= STABILITY_THRESHOLD
                and int(row["stability_years"]) >= 3
            ):
                skip_cells.append({"dim": dims[0], "value": key, **row})
    policies["P1_skip"] = {
        "rule": "skip session when any cell matches (state knowable at 09:45)",
        "mechanism": "regime_dates restriction",
        "cells": skip_cells,
    }

    # P2 size tiers: OR-width-quartile x gap-bucket coarse map. 2x block for
    # strong stable cells, 1x default; cells already in P1 are skipped anyway.
    tier2_cells: List[Dict[str, object]] = []
    valid = joined_fit[
        (joined_fit["or_width_q"].astype(str) != "") & (joined_fit["gap_bucket"].astype(str) != "")
    ]
    for key, grp in valid.groupby(["or_width_q", "gap_bucket"]):
        row = _cell_row(("or_width_q", "gap_bucket"), key, grp, overall_mean)
        if (
            row["n_sessions"] >= MIN_CELL_SESSIONS
            and float(row["mean_net"]) >= 2.0 * overall_mean
            and float(row["mean_net"]) > 0
            and row["stability_frac"] != ""
            and float(row["stability_frac"]) >= STABILITY_THRESHOLD
            and int(row["stability_years"]) >= 3
        ):
            tier2_cells.append({"or_width_q": key[0], "gap_bucket": key[1], **row})
    policies["P2_size_tiers"] = {
        "rule": "2x S_1_1_3 block in listed cells, 1x elsewhere",
        "mechanism": "date-list split, one replay per tier (2x = 2/2/6, entry 10)",
        "tier2_cells": tier2_cells,
    }

    # P3 runner policy: drop the runner (1/1/0) in states where P(hit2R | hit1R)
    # is materially below pooled — the runner block only pays past ~2R.
    p2r_pooled_den = sessions_fit[sessions_fit["hit_1r"] == 1]
    p2r_pooled = float(p2r_pooled_den["hit_2r"].mean()) if len(p2r_pooled_den) else float("nan")
    no_runner_cells: List[Dict[str, object]] = []
    for q, grp in p2r_pooled_den[p2r_pooled_den["or_width_q"].astype(str) != ""].groupby("or_width_q"):
        p = float(grp["hit_2r"].mean())
        if len(grp) >= MIN_CELL_SESSIONS and p <= p2r_pooled - 0.05:
            no_runner_cells.append(
                {"dim": "or_width_q", "value": q, "n": len(grp), "p_2r_given_1r": round(p, 3)}
            )
    policies["P3_no_runner"] = {
        "rule": "use 1/1/0 (no runner) when P(2R|1R) in state trails pooled by >=5pts",
        "mechanism": "date-list split, no-runner tier replay (1/1/0, entry 2)",
        "p_2r_given_1r_pooled": round(p2r_pooled, 3) if not math.isnan(p2r_pooled) else "",
        "cells": no_runner_cells,
    }

    # P4 early cut (analytic estimate only): failed-break sessions (re-entry
    # before 1R) are where v2b bleeds; the empirical cutoff is the p75 of
    # 5m-candles-to-re-entry on failed breaks.
    failed = joined_fit[(joined_fit["reentry"] == 1) & (joined_fit["hit_1r"] == 0)]
    cutoff = ""
    if len(failed):
        vals = pd.to_numeric(failed["bars5_to_reentry"], errors="coerce").dropna()
        cutoff = float(vals.quantile(0.75)) if len(vals) else ""
    policies["P4_early_cut"] = {
        "rule": "flatten at OR re-entry when it fires within the empirical cutoff before 1R",
        "mechanism": "requires small v2b_scaleout config flag (not replayed here)",
        "empirical_cutoff_bars5_p75": cutoff,
        "failed_break_sessions_fit": len(failed),
        "failed_break_mean_net_fit": round(float(failed["v2b_net_usd"].mean()), 2) if len(failed) else "",
    }

    # P8 runner ladder from P(2R|1R)·P(3R|2R) chain (fit-window cells).
    chain_cells: List[Dict[str, object]] = []
    for (q, gap), grp in sessions_fit.groupby(["or_width_q", "gap_bucket"]):
        if str(q) == "" or str(gap) == "":
            continue
        h1 = grp[grp["hit_1r"] == 1]
        h2 = grp[grp["hit_2r"] == 1]
        if len(h1) < MIN_CHAIN_N1 or len(h2) < MIN_CHAIN_N2:
            continue
        p2 = float(h1["hit_2r"].mean())
        p3 = float(h2["hit_3r"].mean())
        chain = p2 * p3
        tier = "runner_3r" if chain >= CHAIN_HIGH else ("no_runner" if chain < CHAIN_LOW else "1x")
        chain_cells.append(
            {
                "or_width_q": str(q),
                "gap_bucket": str(gap),
                "n1": len(h1),
                "n2": len(h2),
                "p_2r_given_1r": round(p2, 3),
                "p_3r_given_2r": round(p3, 3),
                "chain": round(chain, 3),
                "tier": tier,
            }
        )
    # Fallback by or_width_q only when pair cell missing
    q_fallback: Dict[str, str] = {}
    for q, grp in sessions_fit.groupby("or_width_q"):
        if str(q) == "":
            continue
        h1 = grp[grp["hit_1r"] == 1]
        h2 = grp[grp["hit_2r"] == 1]
        if len(h1) < MIN_CHAIN_N1 or len(h2) < MIN_CHAIN_N2:
            continue
        chain = float(h1["hit_2r"].mean()) * float(h2["hit_3r"].mean())
        q_fallback[str(q)] = (
            "runner_3r" if chain >= CHAIN_HIGH else ("no_runner" if chain < CHAIN_LOW else "1x")
        )
    policies["P8_runner_ladder"] = {
        "rule": "runner to 3R when chain>=0.30; no runner when chain<0.18; else baseline 1/1/3",
        "mechanism": "date-list tiers + runner_target_r_mult=3.0 on runner_3r tier",
        "chain_high": CHAIN_HIGH,
        "chain_low": CHAIN_LOW,
        "pair_cells": chain_cells,
        "q_fallback": q_fallback,
    }

    # P9 reverse_only_when variants (config gates; validated separately).
    policies["P9_reverse_only_when"] = {
        "rule": "suppress reverse leg outside q1-morning edge states",
        "mechanism": "v2b_scaleout reverse_only_when + session_or_width_q map",
        "variants": {
            "time_1200": {"max_first_leg_exit_time": "12:00"},
            "time_q1q2": {"max_first_leg_exit_time": "12:00", "or_width_q_allow": ["q1", "q2"]},
            "q1_only": {"or_width_q_allow": ["q1"]},
        },
    }
    return policies


def _cells_match(row: pd.Series, cells: Sequence[Dict[str, object]], dims: Optional[Tuple[str, str]] = None) -> bool:
    for cell in cells:
        if dims is not None:
            if str(row[dims[0]]) == str(cell[dims[0]]) and str(row[dims[1]]) == str(cell[dims[1]]):
                return True
        elif str(row[cell["dim"]]) == str(cell["value"]):
            return True
    return False


def policy_date_tiers(
    sessions: pd.DataFrame, policies: Dict[str, object]
) -> Dict[str, Dict[str, List[date]]]:
    """Map each policy to {tier_name: [dates]} over the given sessions."""
    out: Dict[str, Dict[str, List[date]]] = {}

    skip_cells = policies["P1_skip"]["cells"]
    keep, skip = [], []
    for _, row in sessions.iterrows():
        (skip if _cells_match(row, skip_cells) else keep).append(row["session_date"])
    out["P1_skip"] = {"1x": keep, "skipped": skip}

    tier2_cells = policies["P2_size_tiers"]["tier2_cells"]
    t1, t2 = [], []
    for _, row in sessions.iterrows():
        if _cells_match(row, tier2_cells, dims=("or_width_q", "gap_bucket")):
            t2.append(row["session_date"])
        else:
            t1.append(row["session_date"])
    out["P2_size_tiers"] = {"1x": t1, "2x": t2}

    nr_cells = policies["P3_no_runner"]["cells"]
    base, nr = [], []
    for _, row in sessions.iterrows():
        (nr if _cells_match(row, nr_cells) else base).append(row["session_date"])
    out["P3_no_runner"] = {"1x": base, "no_runner": nr}

    combo_keep: List[date] = []
    combo_t2: List[date] = []
    combo_nr: List[date] = []
    for _, row in sessions.iterrows():
        if _cells_match(row, skip_cells):
            continue
        if _cells_match(row, tier2_cells, dims=("or_width_q", "gap_bucket")):
            combo_t2.append(row["session_date"])
        elif _cells_match(row, nr_cells):
            combo_nr.append(row["session_date"])
        else:
            combo_keep.append(row["session_date"])
    out["P5_combo"] = {"1x": combo_keep, "2x": combo_t2, "no_runner": combo_nr}

    # P8 runner ladder
    p8 = policies.get("P8_runner_ladder") or {}
    pair = {(c["or_width_q"], c["gap_bucket"]): c["tier"] for c in p8.get("pair_cells", [])}
    qfb = dict(p8.get("q_fallback") or {})
    ladder: Dict[str, List[date]] = {"1x": [], "runner_3r": [], "no_runner": []}
    for _, row in sessions.iterrows():
        key = (str(row["or_width_q"]), str(row["gap_bucket"]))
        tier = pair.get(key) or qfb.get(str(row["or_width_q"]), "1x")
        ladder.setdefault(tier, []).append(row["session_date"])
    out["P8_runner_ladder"] = ladder
    return out


# ---------------------------------------------------------------------------
# join subcommand
# ---------------------------------------------------------------------------


def run_join(asof: str, markets: Sequence[str], fit_end: date, out_root: Path) -> None:
    out_dir = out_root / asof
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_lines = ["# OR Profile -> v2b S_1_1_3 join (%s)" % asof, ""]
    summary_lines.append(
        "Trigger = `touch` (matches v2b stop fills). Fit window = tape start -> %s; "
        "policies are derived on the fit window only and frozen in `policies.json`."
        % fit_end.isoformat()
    )

    for market in markets:
        joined = join_market(asof, market)
        joined.to_csv(out_dir / ("%s_joined.csv" % market), index=False)
        joined_fit = joined[joined["session_date"] <= fit_end]
        sessions_fit = load_sessions(asof, market)
        sessions_fit = sessions_fit[sessions_fit["session_date"] <= fit_end]

        label_df, state_df = expectancy_tables(joined_fit)
        label_df.to_csv(out_dir / ("%s_v2b_by_day_label_fit.csv" % market), index=False)
        state_df.to_csv(out_dir / ("%s_v2b_by_state_fit.csv" % market), index=False)

        policies = derive_policies(joined_fit, sessions_fit, market)
        policies["asof"] = asof
        policies["fit_end"] = fit_end.isoformat()
        policies["fit_sessions"] = len(joined_fit)
        (out_dir / ("%s_policies.json" % market)).write_text(json.dumps(policies, indent=2, default=str))

        summary_lines.append("")
        summary_lines.append("## %s" % market.upper())
        summary_lines.append("")
        summary_lines.append(
            "Fit sessions joined: %d (%s -> %s), mean net/session $%.2f"
            % (
                len(joined_fit),
                joined_fit["session_date"].min(),
                joined_fit["session_date"].max(),
                joined_fit["v2b_net_usd"].mean(),
            )
        )
        summary_lines.append("")
        summary_lines.append("### v2b expectancy by terminal day label (fit, diagnostic — EOD-knowable)")
        summary_lines.append("")
        summary_lines.append(_md_table(label_df))
        summary_lines.append("")
        summary_lines.append("### v2b expectancy by pre-entry state (fit)")
        summary_lines.append("")
        knowable = state_df[state_df["knowable"] == "0945"] if "knowable" in state_df else state_df
        summary_lines.append(_md_table(knowable))
        summary_lines.append("")
        summary_lines.append("### Frozen policies")
        summary_lines.append("")
        summary_lines.append("```json")
        summary_lines.append(json.dumps({k: v for k, v in policies.items() if k.startswith("P")}, indent=2, default=str))
        summary_lines.append("```")

    (out_dir / "SUMMARY.md").write_text("\n".join(summary_lines))
    print("Join outputs -> %s" % out_dir, flush=True)


def _md_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "(no rows)"
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# validate subcommand (Engine+PaperBroker causal replay)
# ---------------------------------------------------------------------------


def replay_dates(
    cfg,
    gby: Dict[date, pd.DataFrame],
    dates: Sequence[date],
    sizing: Dict[str, int],
    slug: str,
    states_root: Path,
    extra_config: Optional[Dict[str, object]] = None,
) -> Tuple[List[object], List[AuditBar], Path]:
    state_root = states_root / slug
    if state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    config = {
        "market": cfg.market,
        "mode": "oco_then_reverse",
        "entry_qty": int(sizing["entry_qty"]),
        "tp1_qty": int(sizing["tp1_qty"]),
        "tp2_qty": int(sizing["tp2_qty"]),
        "tick_size": 0.25,
        "use_regime_filter": True,
        "regime_dates": [d.isoformat() for d in sorted(dates)],
        "record_levels": False,
    }
    if extra_config:
        config.update(extra_config)
    instance = StrategyInstance(
        strategy_id=slug,
        strategy_type="v2b_scaleout",
        version="v1",
        instrument=cfg.instrument,
        broker_instrument=cfg.instrument,
        account_mode="paper",
        enabled=True,
        timeframes="1m",
        max_contracts=int(sizing["entry_qty"]),
        max_open_orders=64,
        config_json=json.dumps(config, sort_keys=True),
    )
    store.write_table("strategy_instances", [as_row(instance)])
    engine = Engine(store=store, persist_bars=False, persist_health=False, slippage_ticks=DEFAULT_SLIPPAGE_TICKS)
    audit_bars: List[AuditBar] = []
    for day in sorted(dates):
        df = rth_bars(gby.get(day), day, dense=True)
        if df.empty:
            continue
        for ts, row in df.iterrows():
            ts_s = pd.Timestamp(ts).isoformat()
            bar = Bar(
                instrument=cfg.instrument,
                timeframe="1m",
                ts=ts_s,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(cfg.dbn_path),
            )
            engine.process_bar(bar)
            audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
    store.flush_tables()
    units = units_from_v2b_fills(state_root / "fills.csv", slug)
    return list(units), audit_bars, state_root


def run_validate(
    asof: str,
    markets: Sequence[str],
    fit_end: date,
    out_root: Path,
    only_policies: Optional[Sequence[str]] = None,
) -> None:
    out_dir = out_root / asof
    val_root = out_dir / "validation"
    val_root.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, object]] = []
    # Keep prior validation rows when running a subset so SUMMARY stays cumulative.
    prior_csv = val_root / "validation_summary.csv"
    if only_policies and prior_csv.exists():
        rows = pd.read_csv(prior_csv).to_dict(orient="records")
        rows = [r for r in rows if str(r.get("policy")) not in set(only_policies)]

    for market in markets:
        cfg = MARKETS[market]
        policies = json.loads((out_dir / ("%s_policies.json" % market)).read_text())
        sessions = load_sessions(asof, market)
        val_sessions = sessions[sessions["session_date"] > fit_end]

        print("Loading %s 1m for validation replays..." % cfg.instrument, flush=True)
        gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
        regime = set(_regime_dates(cfg, gby))
        val_sessions = val_sessions[val_sessions["session_date"].isin(regime)]
        val_dates = sorted(val_sessions["session_date"])
        print("  %s validation regime sessions: %d (> %s)" % (cfg.instrument, len(val_dates), fit_end), flush=True)

        tiers_by_policy = policy_date_tiers(val_sessions, policies)
        tiers_by_policy = {"baseline": {"1x": val_dates}, **tiers_by_policy}
        # OR-profile time gate (entry stops expire 10:30 NY; threshold a
        # priori from the stable break-time cells): alone and on the combo.
        extras_by_policy: Dict[str, Dict[str, object]] = {
            "P6_timegate": {"entry_cutoff_time": "10:30"},
            "P7_combo_timegate": {"entry_cutoff_time": "10:30"},
        }
        tiers_by_policy["P6_timegate"] = {"1x": list(val_dates)}
        tiers_by_policy["P7_combo_timegate"] = {
            t: list(ds) for t, ds in tiers_by_policy["P5_combo"].items()
        }
        # P9 reverse_only_when variants (all sessions, 1x sizing, gated reverse).
        qmap = {
            d.isoformat(): str(q)
            for d, q in zip(val_sessions["session_date"], val_sessions["or_width_q"])
        }
        for vname, gate in (policies.get("P9_reverse_only_when") or {}).get("variants", {}).items():
            pname = "P9_%s" % vname
            extras_by_policy[pname] = {
                "reverse_only_when": gate,
                "session_or_width_q": qmap,
            }
            tiers_by_policy[pname] = {"1x": list(val_dates)}

        tier_extras: Dict[str, Dict[str, object]] = {
            "runner_3r": {"runner_target_r_mult": 3.0},
        }

        if only_policies:
            keep = set(only_policies)
            tiers_by_policy = {k: v for k, v in tiers_by_policy.items() if k in keep}

        for policy_name, tiers in tiers_by_policy.items():
            extra_config = dict(extras_by_policy.get(policy_name) or {})
            if policy_name != "baseline" and not extra_config and "runner_3r" not in tiers:
                # Skip policies degenerate to the baseline (all dates in tier 1x).
                non_base = [d for t, ds in tiers.items() if t not in ("1x",) for d in ds]
                if not non_base and sorted(tiers.get("1x", [])) == list(val_dates):
                    print("  %s %s: identical to baseline, skipping replay" % (market, policy_name), flush=True)
                    continue
            all_units: List[object] = []
            audit_bars_ref: List[AuditBar] = []
            state_root_ref: Optional[Path] = None
            n_traded_days = 0
            for tier_name, dates in tiers.items():
                if tier_name == "skipped" or not dates:
                    continue
                sizing = SIZING_TIERS[tier_name]
                slug = "%s_orprof_%s_%s" % (market, policy_name.lower(), tier_name)
                cfg_extra = dict(extra_config)
                cfg_extra.update(tier_extras.get(tier_name, {}))
                units, audit_bars, state_root = replay_dates(
                    cfg, gby, dates, sizing, slug, val_root / "states",
                    extra_config=cfg_extra or None,
                )
                all_units.extend(units)
                n_traded_days += len(dates)
                if state_root_ref is None or len(audit_bars) > len(audit_bars_ref):
                    audit_bars_ref = audit_bars
                    state_root_ref = state_root
            if state_root_ref is None:
                continue
            # NOTE: for split-tier policies the stress audit walks each tier's
            # bars separately; merged stress is approximated on the union of
            # units against the longest tier's bar tape, so closed-trade net is
            # exact while intrabar stress is a lower-bound proxy for combos.
            audit = fast_intraday_audit(
                strategy_id="%s_orprof_%s" % (market, policy_name.lower()),
                state_root=state_root_ref,
                bars=audit_bars_ref,
                units=all_units,
                instrument=cfg.instrument,
                fee_per_unit=cfg.fee_per_unit,
            )
            net = float(audit["net_usd"])
            rows.append(
                {
                    "market": market,
                    "policy": policy_name,
                    "sessions": n_traded_days,
                    "units": len(all_units),
                    "net_usd": round(net, 2),
                    "net_per_session": round(net / max(1, n_traded_days), 2),
                    "closed_dd_usd": round(float(audit["closed_dd_usd"]), 2),
                    "intrabar_stress_dd_usd": round(float(audit["intrabar_stress_dd_usd"]), 2),
                    "win_rate_pct": round(float(audit["win_rate"]), 2),
                    "profit_factor": round(float(audit["profit_factor"]), 3)
                    if math.isfinite(float(audit["profit_factor"]))
                    else "inf",
                }
            )
            print("  %s %s: net $%.2f over %d sessions" % (market, policy_name, net, n_traded_days), flush=True)
            pd.DataFrame(rows).to_csv(val_root / "validation_summary.csv", index=False)

    df = pd.DataFrame(rows)
    lines = ["# OR profile policy causal validation (%s)" % asof, ""]
    lines.append(
        "Policies frozen on fit window (<= %s), replayed on validation window (> %s) via Engine+PaperBroker "
        "with the standard hardened realism (1-tick slippage, $1.50/RT, stop-first same-bar ordering)."
        % (fit_end, fit_end)
    )
    lines.append("")
    lines.append(_md_table(df))
    (val_root / "SUMMARY.md").write_text("\n".join(lines))
    print("Validation outputs -> %s" % val_root, flush=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description="OR profile -> v2b join / policy validation")
    ap.add_argument("cmd", choices=["join", "validate"])
    ap.add_argument("--asof", required=True)
    ap.add_argument("--markets", nargs="+", default=["nq", "mnq"])
    ap.add_argument("--fit-end", type=date.fromisoformat, default=date(2024, 12, 31))
    ap.add_argument("--out", type=Path, default=ENGINE_ROOT / "v2b_join")
    ap.add_argument(
        "--only",
        nargs="+",
        default=None,
        help="validate only these policy names (e.g. baseline P8_runner_ladder P9_q1_only)",
    )
    args = ap.parse_args()
    if args.cmd == "join":
        run_join(args.asof, [m.lower() for m in args.markets], args.fit_end, args.out)
    else:
        run_validate(
            args.asof,
            [m.lower() for m in args.markets],
            args.fit_end,
            args.out,
            only_policies=args.only,
        )


if __name__ == "__main__":
    main()
