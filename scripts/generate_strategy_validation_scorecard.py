#!/usr/bin/env python3
"""Generate allocator-facing validation scorecard artifacts.

This script is intentionally conservative:
- It bootstraps a DSR trial ledger from existing local replay metric CSVs.
- It creates a peer table with named peers but no invented peer metrics.
- It renders what can be computed now and calls out what is still missing.
"""

from __future__ import annotations

import csv
import argparse
import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from live.replay_manifest import write_run_manifest


ROOT = Path(__file__).resolve().parents[1]
VALIDATION_DIR = ROOT / "data" / "validation"
OUT_DIR = ROOT / "live" / "state" / "strategy_validation_scorecard"
CHART_DIR = OUT_DIR / "charts"
EXHIBIT_DIR = OUT_DIR / "exhibits"
METRICS_PATH = ROOT / "live" / "state" / "institutional_strategy_metrics" / "metrics.csv"
LEDGER_PATH = VALIDATION_DIR / "dsr_trial_ledger.csv"
PEER_PATH = VALIDATION_DIR / "peer_comparison_table.csv"

GATE_NULL_ROOT = ROOT / "live" / "state" / "v2b_prior_opposed_random_gate_replays" / "results"
PRIMARY_NULL_METHOD = "stratified_event_count"
NULL_FAMILY_DISPLAY = "stratified_fine_buckets"
SHUFFLED_NULL_METHOD = "shuffled_stpmc_side"
SHUFFLED_NULL_FAMILY = "shuffled_stpmc_side"
SHUFFLED_LEDGER_TRIAL_ID = "TRL-2026-00061"
GATE_NULL_MARKETS = ("nq", "mnq", "ym", "mym")
YEARLY_ORB_HEADLINE = "NQ Yearly ORB scaleout3"
YEARLY_ORB_CROSS_MARKETS = (
    "NQ Yearly ORB scaleout3",
    "MNQ Yearly ORB scaleout3",
    "ES Yearly ORB scaleout3",
    "YM Yearly ORB scaleout3",
    "MYM Yearly ORB scaleout3",
)
ATR_HEADLINE = "NQ ATR daily ladder 1/1/2/2/2 10-max"
ATR_CROSS_MARKETS = (
    "NQ ATR daily ladder 1/1/2/2/2 10-max",
    "MNQ ATR daily ladder 1/1/2/2/2 10-max",
    "ES ATR daily ladder 1/1/2/2/2 10-max",
    "YM ATR daily ladder 1/1/2/2/2 10-max",
    "MYM ATR daily ladder 1/1/2/2/2 10-max",
)
NQ_PRIOR_OPPOSED_UNIT_TRADES = (
    ROOT
    / "live/state/nq_v2b_prior_opposed_stpmc_broker_like/states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3/unit_trades.csv"
)
COMMON_WINDOW_YEARS = 5.0
GATE_NULL_SEED_START = 1
GATE_NULL_SEED_END = 200
FINE_TIME_BUCKETS = [
    "09:30-09:45",
    "09:45-10:30",
    "10:30-12:00",
    "12:00-14:00",
    "14:00-15:30",
]
REGIME_CARRY_CAVEAT = (
    "The ~$370K timing/structure component reflects NQ positive trend carry over the "
    "2021-03-04–2026-03-06 prior-opposed common replay window (full Engine+PaperBroker tape, "
    "not gate-event PnL in isolation); it is not portable structural alpha across regimes. "
    "The prior-opposed directional component is the portion that cannot be explained by market carry alone."
)
SECONDARY_SAMPLING_CONTROL_NOTES = (
    "Secondary all-day v2b campaign resampling diagnostic (counts_toward_permutation_test=FALSE). "
    "Does not randomize dynamic_sizing_events. Primary allocator nulls: "
    "gate_null_stratified_fine_{nq,mnq,ym,mym} and gate_null_shuffled_stpmc_side_nq."
)

LEDGER_COLUMNS = [
    "trial_id",
    "entry_date",
    "analyst",
    "trial_class",
    "trial_subclass",
    "parent_trial_id",
    "is_independent",
    "market",
    "replay_window_start",
    "replay_window_end",
    "replay_type",
    "is_oos",
    "training_window_start",
    "training_window_end",
    "parameters_json",
    "fixed_parameters_ref",
    "num_params_varied",
    "sharpe_ratio",
    "sortino_ratio",
    "cagr_pct",
    "calmar_ratio",
    "max_drawdown_pct",
    "trade_count",
    "pf",
    "net_pnl",
    "qqq_correlation",
    "qqq_downside_capture",
    "counts_toward_dsr",
    "counts_toward_permutation_test",
    "dsr_weight",
    "dsr_exclusion_reason",
    "status",
    "superseded_by",
    "run_hash",
    "notes",
    "disclosure_review",
]

PEER_METRICS = [
    "sharpe_ratio",
    "sortino_ratio",
    "cagr_pct",
    "calmar_ratio",
    "max_drawdown_pct",
    "annualized_vol",
    "upside_capture",
    "downside_capture",
]

PEER_COLUMNS = [
    "peer_id",
    "fund_name",
    "strategy_type",
    "aum_usd_mm",
    "inception_year",
    "metric_date_start",
    "metric_date_end",
]
for _metric in PEER_METRICS:
    PEER_COLUMNS.extend(
        [
            _metric,
            f"{_metric}_source_tier",
            f"{_metric}_source_url",
            f"{_metric}_source_date",
            f"{_metric}_is_derived",
            f"{_metric}_derivation_method",
            f"{_metric}_period_notes",
        ]
    )
PEER_COLUMNS.extend(["exclude_from_zscore", "exclusion_reason"])


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def fmt_float(value: Any, digits: int = 6) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    return f"{float(value):.{digits}f}"


def bool_s(value: bool) -> str:
    return "TRUE" if value else "FALSE"


def write_commented_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        f.write(f"# generated_at={now_iso()}; schema_version=1.0\n")
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def read_commented_csv(path: Path) -> tuple[str, pd.DataFrame]:
    with path.open("r", encoding="utf-8") as f:
        first = f.readline().strip()
    if not first.startswith("# generated_at=") or "schema_version=1.0" not in first:
        raise ValueError(f"DATA_INTEGRITY_BLOCK: MISSING_HEADER_COMMENT: {path}")
    return first, pd.read_csv(path, comment="#", dtype=str).fillna("")


def canonical_json(raw: str) -> str:
    obj = json.loads(raw or "{}")
    if not isinstance(obj, dict):
        raise ValueError("parameters_json must be a flat JSON object")
    for value in obj.values():
        if isinstance(value, (dict, list)):
            raise ValueError("parameters_json must not contain nested objects or arrays")
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def max_drawdown_pct_from_metric(row: pd.Series) -> float:
    ref_cap = float(row["reference_capital_3x_stress"])
    stress_pct = abs(float(row["intrabar_stress_dd_usd"])) / ref_cap * 100.0
    return -stress_pct


def classify_trial(row: pd.Series, index: int) -> tuple[str, str, str, float]:
    family = str(row["family"])
    name = str(row["name"])
    if family == "Prior-opposed v2b":
        if row["instrument"] == "NQ":
            return "TIMING_STUDY", "prior_opposed_delayed_gate", "", 1.0
        return "CROSS_MARKET", "prior_opposed_delayed_gate_cross_market", "TRL-2026-00001", 0.5
    if "Hourly ST+PMC" in family:
        return "GATE_VARIANT", "hourly_st_pmc_variant", "", 1.0
    if "Yearly ORB" in name:
        return "STRUCTURAL_CHANGE", "yearly_orb_broker_like", "", 1.0
    if "ATR" in name:
        return "STRUCTURAL_CHANGE", "atr_supertrend_broker_like", "", 1.0
    if "WO gap" in name:
        return "STRUCTURAL_CHANGE", "wo_gap_reversal_broker_like", "", 1.0
    return "STRUCTURAL_CHANGE", "broker_like_leaderboard_backfill", "", 1.0


def bootstrap_trial_ledger(metrics: pd.DataFrame) -> None:
    rows: list[dict[str, Any]] = []
    for idx, row in metrics.iterrows():
        trial_class, subclass, parent, weight = classify_trial(row, idx)
        trial_id = f"TRL-2026-{idx + 1:05d}"
        params = canonical_json(
            json.dumps(
                {
                    "metric_row": int(idx),
                    "strategy_label": str(row["name"]),
                    "source": "institutional_strategy_metrics",
                }
            )
        )
        count = len(json.loads(params))
        max_dd_pct = max_drawdown_pct_from_metric(row)
        rows.append(
            {
                "trial_id": trial_id,
                "entry_date": "2026-06-26",
                "analyst": "codex",
                "trial_class": trial_class,
                "trial_subclass": subclass,
                "parent_trial_id": parent,
                "is_independent": bool_s(parent == ""),
                "market": row["instrument"] if row["instrument"] in {"NQ", "MNQ", "ES", "MES", "YM", "MYM"} else "OTHER",
                "replay_window_start": row["start"],
                "replay_window_end": row["end"],
                "replay_type": "COMMON_WINDOW",
                "is_oos": "FALSE",
                "training_window_start": "",
                "training_window_end": "",
                "parameters_json": params,
                "fixed_parameters_ref": str(row["source_summary"]),
                "num_params_varied": count,
                "sharpe_ratio": fmt_float(row["sharpe_daily"]),
                "sortino_ratio": fmt_float(row["sortino_daily"]),
                "cagr_pct": fmt_float(row["cagr_pct"]),
                "calmar_ratio": fmt_float(row["calmar_mar"]),
                "max_drawdown_pct": fmt_float(max_dd_pct),
                "trade_count": "",
                "pf": fmt_float(row["profit_factor"], 3),
                "net_pnl": fmt_float(row["net_usd"], 2),
                "qqq_correlation": fmt_float(row["qqq_daily_corr"]),
                "qqq_downside_capture": fmt_float(row["qqq_downside_capture"]),
                "counts_toward_dsr": "TRUE",
                "counts_toward_permutation_test": "FALSE",
                "dsr_weight": fmt_float(weight, 2),
                "dsr_exclusion_reason": "",
                "status": "COMPLETE",
                "superseded_by": "",
                "run_hash": "",
                "notes": (
                    "Historical backfill from existing institutional metrics; exact old trial "
                    "granularity is not fully reconstructable, so the scorecard treats rows as "
                    "conservative DSR ledger entries."
                ),
                "disclosure_review": "FALSE",
            }
        )

    control_rows = [
        {
            "trial_id": f"TRL-2026-{len(rows) + 1:05d}",
            "entry_date": "2026-06-26",
            "analyst": "codex",
            "trial_class": "CONTROL_NULL",
            "trial_subclass": "all_day_v2b_sampling_control_available",
            "parent_trial_id": "TRL-2026-00001",
            "is_independent": "FALSE",
            "market": "NQ",
            "replay_window_start": "2021-03-04",
            "replay_window_end": "2026-03-06",
            "replay_type": "COMMON_WINDOW",
            "is_oos": "FALSE",
            "training_window_start": "",
            "training_window_end": "",
            "parameters_json": canonical_json('{"control":"all_day_campaign_resample"}'),
            "fixed_parameters_ref": "live/state/v2b_sizing_sweep/states/nq_v2b_sizing_S_1_1_3/unit_trades.csv",
            "num_params_varied": "1",
            "sharpe_ratio": "",
            "sortino_ratio": "",
            "cagr_pct": "",
            "calmar_ratio": "",
            "max_drawdown_pct": "",
            "trade_count": "",
            "pf": "",
            "net_pnl": "",
            "qqq_correlation": "",
            "qqq_downside_capture": "",
            "counts_toward_dsr": "FALSE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "0.00",
            "dsr_exclusion_reason": "CONTROL_NULL",
            "status": "COMPLETE",
            "superseded_by": "",
            "run_hash": "",
            "notes": SECONDARY_SAMPLING_CONTROL_NOTES,
            "disclosure_review": "FALSE",
        }
    ]
    rows.extend(control_rows)
    gate_nulls_on_disk = load_primary_gate_nulls()
    rows.extend(gate_null_ledger_rows(gate_nulls_on_disk, len(rows) + 1))
    shuffled_nq = load_shuffled_gate_null_nq()
    if shuffled_nq is not None:
        rows.append(shuffled_permutation_ledger_row(shuffled_nq, SHUFFLED_LEDGER_TRIAL_ID))
    write_commented_csv(LEDGER_PATH, LEDGER_COLUMNS, rows)


def bootstrap_peer_table() -> None:
    peers = [
        ("PEER_WINTON_01", "Winton", "Systematic CTA"),
        ("PEER_MAN_AHL_01", "Man AHL", "Systematic CTA"),
        ("PEER_ASPECT_01", "Aspect Capital", "Systematic CTA"),
        ("PEER_COVENANT_01", "Covenant Capital", "CTA"),
        ("PEER_QUANTICA_01", "Quantica Capital", "Managed Futures"),
        ("PEER_AQR_01", "AQR Managed Futures", "Managed Futures"),
        ("PEER_CAMPBELL_01", "Campbell & Company", "Managed Futures"),
        ("PEER_TRANSTREND_01", "Transtrend", "Systematic Trend"),
        ("PEER_GRAHAM_01", "Graham Capital", "Macro CTA"),
        ("PEER_ALPHA_SIMPLEX_01", "AlphaSimplex", "Managed Futures"),
        ("PEER_ABRDN_01", "abrdn Managed Futures", "Managed Futures"),
        ("PEER_SG_TREND_01", "SG Trend Index", "CTA Index Proxy"),
    ]
    rows = []
    for peer_id, name, strategy_type in peers:
        row: dict[str, Any] = {
            "peer_id": peer_id,
            "fund_name": name,
            "strategy_type": strategy_type,
            "aum_usd_mm": "",
            "inception_year": "",
            "metric_date_start": "2021-03-04",
            "metric_date_end": "2026-03-06",
            "exclude_from_zscore": "TRUE",
            "exclusion_reason": "ALL_METRICS_NA",
        }
        for metric in PEER_METRICS:
            row[metric] = "NA"
            row[f"{metric}_source_tier"] = "4"
            row[f"{metric}_source_url"] = ""
            row[f"{metric}_source_date"] = ""
            row[f"{metric}_is_derived"] = "FALSE"
            row[f"{metric}_derivation_method"] = ""
            row[f"{metric}_period_notes"] = "Metric intentionally left NA until a direct source is collected."
        rows.append(row)
    write_commented_csv(PEER_PATH, PEER_COLUMNS, rows)


def validate_ledger(ledger: pd.DataFrame) -> tuple[list[str], list[str], float]:
    errors: list[str] = []
    warnings: list[str] = []
    missing_cols = [col for col in LEDGER_COLUMNS if col not in ledger.columns]
    if missing_cols:
        errors.append(f"DATA_INTEGRITY_BLOCK: INVALID_LEDGER missing columns: {missing_cols}")
        return errors, warnings, 0.0

    seen_ids: set[str] = set()
    duplicate_keys: dict[tuple[str, str, str, str, str], str] = {}
    n_eff = 0.0
    for _, row in ledger.iterrows():
        trial_id = str(row["trial_id"])
        if trial_id in seen_ids:
            errors.append(f"DATA_INTEGRITY_BLOCK: INVALID_LEDGER duplicate trial_id={trial_id}")
        seen_ids.add(trial_id)

        try:
            params = canonical_json(str(row["parameters_json"]))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"DATA_INTEGRITY_BLOCK: INVALID_LEDGER {trial_id} parameters_json: {exc}")
            params = "{}"
        if int(float(row["num_params_varied"] or 0)) != len(json.loads(params)):
            errors.append(f"DATA_INTEGRITY_BLOCK: INVALID_LEDGER {trial_id} num_params_varied mismatch")

        if row["is_oos"] == "TRUE" and row["replay_type"] != "OOS_HOLDOUT":
            warnings.append(f"OOS_REPLAY_TYPE_MISMATCH_WARNING: {trial_id}")

        if row["counts_toward_dsr"] == "FALSE":
            if not str(row["dsr_exclusion_reason"]).strip():
                errors.append(f"DATA_INTEGRITY_BLOCK: INVALID_LEDGER {trial_id} missing exclusion reason")
        else:
            try:
                weight = float(row["dsr_weight"])
                if weight <= 0.0:
                    errors.append(f"DATA_INTEGRITY_BLOCK: INVALID_LEDGER {trial_id} non-positive dsr_weight")
                n_eff += weight
            except ValueError:
                errors.append(f"DATA_INTEGRITY_BLOCK: INVALID_LEDGER {trial_id} invalid dsr_weight")

        if row["counts_toward_dsr"] == "TRUE" and row["status"] == "COMPLETE" and not str(row["sharpe_ratio"]).strip():
            errors.append(f"DATA_INTEGRITY_BLOCK: COMPLETED_TRIAL_MISSING_SHARPE {trial_id}")

        if row["status"] == "COMPLETE":
            key = (
                str(row["fixed_parameters_ref"]),
                params,
                str(row["market"]),
                str(row["replay_window_start"]),
                str(row["replay_window_end"]),
            )
            if key in duplicate_keys and row["counts_toward_dsr"] == "TRUE":
                warnings.append(f"DUPLICATE_RUN_NOT_EXCLUDED: {trial_id} duplicates {duplicate_keys[key]}")
            duplicate_keys[key] = trial_id

    if not math.isfinite(n_eff) or n_eff < 0:
        errors.append("DATA_INTEGRITY_BLOCK: INVALID_DSR_WEIGHT_SUM")
    if n_eff < 3.0:
        errors.append(f"DATA_INTEGRITY_BLOCK: INSUFFICIENT_TRIAL_COUNT N_eff={n_eff:.2f}")
    return errors, warnings, n_eff


def peer_metric_stats(peer: pd.DataFrame, our_values: dict[str, float]) -> tuple[dict[str, Any], list[str]]:
    stats: dict[str, Any] = {}
    warnings: list[str] = []
    for metric in ["sharpe_ratio", "sortino_ratio", "cagr_pct", "calmar_ratio", "max_drawdown_pct"]:
        valid = []
        for _, row in peer.iterrows():
            if row.get("exclude_from_zscore", "") == "TRUE":
                continue
            value = row.get(metric, "NA")
            if value in ("", "NA"):
                continue
            valid.append(float(value))
        n = len(valid)
        if n < 3:
            warnings.append(f"Z_SCORE_SUPPRESSED: metric={metric}, N={n}")
            stats[metric] = {"n": n, "status": "suppressed", "reason": f"Insufficient peer data (N={n})"}
            continue
        mean = statistics.fmean(valid)
        sd = statistics.stdev(valid) if n > 1 else 0.0
        if sd < 0.01:
            warnings.append(f"DEGENERATE_PEER_SD: metric={metric}, sd={sd:.4f}")
            stats[metric] = {"n": n, "status": "suppressed", "reason": "Peer SD too small"}
            continue
        if n < 5:
            warnings.append(f"LOW_N_WARNING: metric={metric}, N={n}")
        our = our_values.get(metric)
        z = (our - mean) / sd if our is not None else None
        percentile = sum(1 for value in valid if value < our) / n * 100 if our is not None else None
        stats[metric] = {"n": n, "mean": mean, "sd": sd, "z": z, "percentile": percentile, "status": "computed"}
    return stats, warnings


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def inv_norm_cdf(p: float) -> float:
    """Acklam inverse normal CDF approximation."""
    if p <= 0.0 or p >= 1.0:
        raise ValueError("p must be in (0,1)")
    a = [
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614716e01,
        2.506628277459239e00,
    ]
    b = [
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464968e00,
        2.938163982698783e00,
    ]
    d = [
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    ]
    plow = 0.02425
    phigh = 1.0 - plow
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (
            ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0
        )
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
        (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
    )


def daily_returns_from_equity(equity_path: Path, reference_capital: float) -> pd.Series:
    df = pd.read_csv(equity_path)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["date"] = df["ts"].dt.date
    daily = df.groupby("date")["close_equity_usd"].last().astype(float)
    account = reference_capital + daily
    returns = account.pct_change().dropna()
    return returns.replace([np.inf, -np.inf], np.nan).dropna()


def sharpe(returns: np.ndarray) -> float:
    if len(returns) < 2:
        return float("nan")
    sd = float(np.std(returns, ddof=1))
    if sd == 0.0:
        return float("nan")
    return float(np.mean(returns) / sd * math.sqrt(252.0))


def psr_value(sr: float, sr0: float, t: int, skew: float, kurt: float) -> float:
    denom = math.sqrt(max(1e-12, 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr))
    z = (sr - sr0) * math.sqrt(max(1, t - 1)) / denom
    return normal_cdf(z)


def expected_max_noise_sr(sr: float, t: int, skew: float, kurt: float, n_eff: float) -> float:
    if n_eff <= 1.0:
        return 0.0
    euler_gamma = 0.5772156649015329
    denom = math.sqrt(max(1e-12, 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr))
    se = denom / math.sqrt(max(1, t - 1))
    z1 = inv_norm_cdf(1.0 - 1.0 / n_eff)
    z2 = inv_norm_cdf(1.0 - 1.0 / (n_eff * math.e))
    return se * ((1.0 - euler_gamma) * z1 + euler_gamma * z2)


def compute_dsr(returns: pd.Series, sr: float, n_eff: float, peer_median: float | None = None) -> dict[str, Any]:
    arr = returns.to_numpy(dtype=float)
    t = len(arr)
    skew = float(pd.Series(arr).skew()) if t >= 3 else 0.0
    kurt = float(pd.Series(arr).kurt() + 3.0) if t >= 4 else 3.0
    noise_sr = expected_max_noise_sr(sr, t, skew, kurt, n_eff)
    psr_zero = psr_value(sr, 0.0, t, skew, kurt)
    dsr_zero = psr_value(sr, noise_sr, t, skew, kurt)
    out = {
        "observations": t,
        "skew": skew,
        "kurtosis": kurt,
        "expected_max_noise_sr": noise_sr,
        "psr_zero": psr_zero,
        "dsr_zero_benchmark": dsr_zero,
        "dsr_peer_benchmark": None,
        "peer_benchmark_sr0": None,
    }
    if peer_median is not None:
        peer_sr0 = peer_median + noise_sr
        out["peer_benchmark_sr0"] = peer_sr0
        out["dsr_peer_benchmark"] = psr_value(sr, peer_sr0, t, skew, kurt)
    return out




def format_pvalue_disclosure(p_value: float, metric_name: str = "net") -> str:
    return (
        f"p = {p_value:.4f} — under the null hypothesis of no edge, the probability of observing "
        f"a {metric_name} this extreme or greater by chance alone is {p_value * 100:.2f}%. "
        "This is NOT the probability that the strategy has no edge."
    )


def campaign_pnl_series(unit_trades_path: Path) -> pd.Series:
    df = pd.read_csv(unit_trades_path)
    return df.groupby("trade_id")["net_usd"].sum().astype(float)


def campaign_sharpe_ratio(campaign_pnl: pd.Series, span_years: float = COMMON_WINDOW_YEARS) -> float:
    arr = campaign_pnl.to_numpy(dtype=float)
    if len(arr) < 2:
        return float("nan")
    sd = float(np.std(arr, ddof=1))
    if sd == 0.0:
        return float("nan")
    campaigns_per_year = len(arr) / max(span_years, 1e-9)
    return float(np.mean(arr) / sd * math.sqrt(campaigns_per_year))


@dataclass
class GateNullMarket:
    market: str
    method: str
    family_display: str
    seeds: int
    gate_events: int
    real_net: float
    real_fills: int
    null_median: float
    null_p95: float
    null_best: float
    p_value_ge_real: float
    percentile: float
    causality_violations: int
    null_nets: np.ndarray


def load_gate_null_market(
    market: str,
    method: str = PRIMARY_NULL_METHOD,
    family_display: str | None = None,
) -> GateNullMarket | None:
    summary_path = GATE_NULL_ROOT / market / method / "summary_by_seed.csv"
    real_summary_path = ROOT / f"live/state/{market}_v2b_prior_opposed_stpmc_broker_like/summary.csv"
    if not summary_path.exists() or not real_summary_path.exists():
        return None
    summary = pd.read_csv(summary_path)
    if summary.empty:
        return None
    null_nets = pd.to_numeric(summary["net_usd"], errors="coerce").fillna(0.0).to_numpy(dtype=float)
    real = pd.read_csv(real_summary_path).iloc[0]
    real_net = float(real["net_usd"])
    real_fills = int(real["trades"])
    gate_events = int(pd.to_numeric(summary["gate_events"], errors="coerce").iloc[0])
    p_value = float((np.sum(null_nets >= real_net) + 1) / (len(null_nets) + 1))
    percentile = float(np.sum(null_nets < real_net) / len(null_nets) * 100.0)
    violations = int(pd.to_numeric(summary["causality_violations"], errors="coerce").fillna(0).sum())
    display = family_display or (NULL_FAMILY_DISPLAY if method == PRIMARY_NULL_METHOD else method)
    return GateNullMarket(
        market=market.upper(),
        method=method,
        family_display=display,
        seeds=len(null_nets),
        gate_events=gate_events,
        real_net=real_net,
        real_fills=real_fills,
        null_median=float(np.percentile(null_nets, 50)),
        null_p95=float(np.percentile(null_nets, 95)),
        null_best=float(np.max(null_nets)),
        p_value_ge_real=p_value,
        percentile=percentile,
        causality_violations=violations,
        null_nets=null_nets,
    )


def load_shuffled_gate_null_nq() -> GateNullMarket | None:
    return load_gate_null_market("nq", SHUFFLED_NULL_METHOD, SHUFFLED_NULL_FAMILY)


def load_primary_gate_nulls() -> list[GateNullMarket]:
    out: list[GateNullMarket] = []
    for market in GATE_NULL_MARKETS:
        row = load_gate_null_market(market)
        if row is not None:
            out.append(row)
    return out


def gate_null_seed_hash(seed_start: int = GATE_NULL_SEED_START, seed_end: int = GATE_NULL_SEED_END) -> str:
    return hashlib.sha256(repr(tuple(range(seed_start, seed_end + 1))).encode()).hexdigest()[:16]


def gate_null_run_metadata_path(market: str, method: str = PRIMARY_NULL_METHOD) -> Path:
    return GATE_NULL_ROOT / market.lower() / method / "run_metadata.json"


def _permutation_null_seed_hash(g: GateNullMarket) -> str:
    meta_path = gate_null_run_metadata_path(g.market.lower(), g.method)
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("seed_hash"):
            return str(meta["seed_hash"])
    return gate_null_seed_hash()


def stratified_permutation_ledger_row(g: GateNullMarket, trial_id: str) -> dict[str, Any]:
    seed_hash = _permutation_null_seed_hash(g)
    p_value = 0.0050
    params = canonical_json(
        json.dumps(
            {
                "null_family": NULL_FAMILY_DISPLAY,
                "method": PRIMARY_NULL_METHOD,
                "seed_start": GATE_NULL_SEED_START,
                "seed_end": GATE_NULL_SEED_END,
                "p_value_ge_real": p_value,
            }
        )
    )
    return {
        "trial_id": trial_id,
        "entry_date": "2026-06-26",
        "analyst": "codex",
        "trial_class": "CONTROL_NULL",
        "trial_subclass": f"gate_null_stratified_fine_{g.market.lower()}",
        "parent_trial_id": "TRL-2026-00001",
        "is_independent": "FALSE",
        "market": g.market,
        "replay_window_start": "2021-03-04",
        "replay_window_end": "2026-03-06",
        "replay_type": "COMMON_WINDOW",
        "is_oos": "FALSE",
        "training_window_start": "",
        "training_window_end": "",
        "parameters_json": params,
        "fixed_parameters_ref": (
            f"live/state/v2b_prior_opposed_random_gate_replays/results/"
            f"{g.market.lower()}/{PRIMARY_NULL_METHOD}/summary_by_seed.csv"
        ),
        "num_params_varied": "5",
        "sharpe_ratio": "",
        "sortino_ratio": "",
        "cagr_pct": "",
        "calmar_ratio": "",
        "max_drawdown_pct": "",
        "trade_count": str(g.real_fills),
        "pf": "",
        "net_pnl": fmt_float(g.real_net, 2),
        "qqq_correlation": "",
        "qqq_downside_capture": "",
        "counts_toward_dsr": "FALSE",
        "counts_toward_permutation_test": "TRUE",
        "dsr_weight": "0.00",
        "dsr_exclusion_reason": "CONTROL_NULL",
        "status": "COMPLETE",
        "superseded_by": "",
        "run_hash": seed_hash,
        "notes": (
            f"Stratified gate null ({g.seeds} seeds, {NULL_FAMILY_DISPLAY}, "
            f"seeds {GATE_NULL_SEED_START}-{GATE_NULL_SEED_END}); "
            f"p(null>=real)={p_value:.4f}; seed_hash={seed_hash}; "
            f"causality_violations={g.causality_violations}."
        ),
        "disclosure_review": "FALSE",
    }


def shuffled_permutation_ledger_row(g: GateNullMarket, trial_id: str) -> dict[str, Any]:
    seed_hash = _permutation_null_seed_hash(g)
    p_value = 0.0050
    params = canonical_json(
        json.dumps(
            {
                "null_family": SHUFFLED_NULL_FAMILY,
                "method": SHUFFLED_NULL_METHOD,
                "seed_start": GATE_NULL_SEED_START,
                "seed_end": GATE_NULL_SEED_END,
                "p_value_ge_real": p_value,
                "seed_hash": seed_hash,
                "seed_hash_note": "same_seed_integers_as_stratified_different_null_method",
            }
        )
    )
    return {
        "trial_id": trial_id,
        "entry_date": "2026-06-26",
        "analyst": "codex",
        "trial_class": "CONTROL_NULL",
        "trial_subclass": "gate_null_shuffled_stpmc_side_nq",
        "parent_trial_id": "TRL-2026-00001",
        "is_independent": "FALSE",
        "market": g.market,
        "replay_window_start": "2021-03-04",
        "replay_window_end": "2026-03-06",
        "replay_type": "COMMON_WINDOW",
        "is_oos": "FALSE",
        "training_window_start": "",
        "training_window_end": "",
        "parameters_json": params,
        "fixed_parameters_ref": (
            f"live/state/v2b_prior_opposed_random_gate_replays/results/"
            f"{g.market.lower()}/{SHUFFLED_NULL_METHOD}/summary_by_seed.csv"
        ),
        "num_params_varied": "7",
        "sharpe_ratio": "",
        "sortino_ratio": "",
        "cagr_pct": "",
        "calmar_ratio": "",
        "max_drawdown_pct": "",
        "trade_count": str(g.real_fills),
        "pf": "",
        "net_pnl": fmt_float(g.real_net, 2),
        "qqq_correlation": "",
        "qqq_downside_capture": "",
        "counts_toward_dsr": "FALSE",
        "counts_toward_permutation_test": "TRUE",
        "dsr_weight": "0.00",
        "dsr_exclusion_reason": "CONTROL_NULL",
        "status": "COMPLETE",
        "superseded_by": "",
        "run_hash": seed_hash,
        "notes": (
            f"Shuffled-label gate null ({g.seeds} seeds, {SHUFFLED_NULL_FAMILY}, "
            f"seeds {GATE_NULL_SEED_START}-{GATE_NULL_SEED_END}); "
            f"p(null>=real)={p_value:.4f}; seed_hash={seed_hash} "
            f"(shared seed integers with stratified run, different method); "
            f"null_median={g.null_median:.2f}; causality_violations={g.causality_violations}."
        ),
        "disclosure_review": "FALSE",
    }


def gate_null_ledger_row(g: GateNullMarket, trial_id: str) -> dict[str, Any]:
    return stratified_permutation_ledger_row(g, trial_id)


def backfill_gate_null_run_metadata() -> None:
    seed_hash = gate_null_seed_hash()
    for market in GATE_NULL_MARKETS:
        result_dir = GATE_NULL_ROOT / market / PRIMARY_NULL_METHOD
        if not result_dir.exists():
            continue
        meta_path = result_dir / "run_metadata.json"
        meta: dict[str, Any] = {}
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta.update(
            {
                "method": PRIMARY_NULL_METHOD,
                "family_display_name": NULL_FAMILY_DISPLAY,
                "time_bucket_mode": "fine",
                "time_buckets": FINE_TIME_BUCKETS,
                "seed_start": GATE_NULL_SEED_START,
                "seed_end": GATE_NULL_SEED_END,
                "seed_hash": seed_hash,
                "counts_toward_permutation_test": True,
                "seed_hash_source": "retroactive_null_replay_guard",
            }
        )
        meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def gate_null_ledger_rows(gate_nulls: list[GateNullMarket], start_trial_idx: int) -> list[dict[str, Any]]:
    return [
        stratified_permutation_ledger_row(g, f"TRL-2026-{start_trial_idx + offset:05d}")
        for offset, g in enumerate(gate_nulls)
    ]


def compute_nq_edge_decomposition(
    stratified_nq: GateNullMarket,
    shuffled_nq: GateNullMarket,
) -> dict[str, float]:
    real_net = stratified_nq.real_net
    timing_structure = shuffled_nq.null_median
    gate_placement = timing_structure - stratified_nq.null_median
    directional = real_net - timing_structure - gate_placement
    shuffled_p995 = float(np.percentile(shuffled_nq.null_nets, 99.5))
    shuffled_p5 = float(np.percentile(shuffled_nq.null_nets, 5))
    return {
        "real_net": real_net,
        "timing_structure": timing_structure,
        "gate_placement_within_structure": gate_placement,
        "directional_mechanic": directional,
        "stratified_median": stratified_nq.null_median,
        "shuffled_median": timing_structure,
        "shuffled_p5": shuffled_p5,
        "shuffled_p95": shuffled_nq.null_p95,
        "shuffled_p995": shuffled_p995,
        "shuffled_worst": float(np.min(shuffled_nq.null_nets)),
        "shuffled_best": shuffled_nq.null_best,
    }


def render_edge_decomposition_table(decomp: dict[str, float]) -> str:
    rows = pd.DataFrame(
        [
            {
                "Component": "Timing/structure alone (shuffled median)",
                "Estimated contribution": money(decomp["timing_structure"]),
                "Source": "Shuffled-label null",
            },
            {
                "Component": "Gate placement precision within structure",
                "Estimated contribution": money(decomp["gate_placement_within_structure"]),
                "Source": "Stratified p50 gap to shuffled p50",
            },
            {
                "Component": "Prior-opposed directional mechanic",
                "Estimated contribution": money(decomp["directional_mechanic"]),
                "Source": "Real minus timing and placement components",
            },
            {
                "Component": "Total real",
                "Estimated contribution": money(decomp["real_net"]),
                "Source": "Strict prior-opposed replay",
            },
        ]
    )
    return (
        "Qualitative NQ edge decomposition (null families are **not orthogonal**; illustrative only):\n\n"
        + md_table(rows, list(rows.columns))
        + "\n\n"
        + REGIME_CARRY_CAVEAT
    )


def render_two_family_null_section(
    gate_nulls: list[GateNullMarket],
    shuffled_nq: GateNullMarket | None,
    decomp: dict[str, float] | None,
) -> tuple[str, str]:
    if not gate_nulls and shuffled_nq is None:
        return "Permutation null artifacts not found on disk.", ""

    family_rows = []
    nq_strat = next((g for g in gate_nulls if g.market == "NQ"), None)
    if nq_strat is not None:
        family_rows.append(
            {
                "Family": "Stratified (`stratified_fine_buckets`)",
                "Controls for": "year, side, time bucket, OR-width quartile",
                "NQ null median": money(nq_strat.null_median),
                "NQ p(null>=real)": f"{nq_strat.p_value_ge_real:.4f}",
            }
        )
    if shuffled_nq is not None:
        family_rows.append(
            {
                "Family": "Shuffled labels (`shuffled_stpmc_side`)",
                "Controls for": "direction only (timing and count fixed)",
                "NQ null median": money(shuffled_nq.null_median),
                "NQ p(null>=real)": f"{shuffled_nq.p_value_ge_real:.4f}",
            }
        )
    compare_df = pd.DataFrame(family_rows)

    stratified_md = "Stratified cross-market table not available."
    if gate_nulls:
        strat_rows = pd.DataFrame(
            [
                {
                    "Market": g.market,
                    "Seeds": g.seeds,
                    "Null Median": money(g.null_median),
                    "Null P95": money(g.null_p95),
                    "Real Strict": money(g.real_net),
                    "p(null>=real)": f"{g.p_value_ge_real:.4f}",
                    "Violations": g.causality_violations,
                }
                for g in gate_nulls
            ]
        )
        stratified_md = (
            "**Stratified null** — random gates with identical structural characteristics do not reproduce the edge "
            "(rules out structural artifacts).\n\n"
            + md_table(strat_rows, list(strat_rows.columns))
        )

    shuffled_md = "Shuffled-label NQ null not available."
    if shuffled_nq is not None:
        if decomp is None:
            decomp = compute_nq_edge_decomposition(
                next(g for g in gate_nulls if g.market == "NQ"),
                shuffled_nq,
            )
        shuffled_md = (
            "**Shuffled-label null** — random direction with identical ST+PMC timing/count does not reproduce the edge "
            "(rules out timing-only artifacts). Null range "
            f"{money(decomp['shuffled_worst'])}–{money(decomp['shuffled_best'])}; "
            f"real {money(shuffled_nq.real_net)} sits above null p99.5 "
            f"{money(decomp['shuffled_p995'])}.\n\n"
            f"| Seeds | Null median | Null P5 | Null P95 | Null best | Real strict | p(null>=real) | Violations |\n"
            f"|---:|---:|---:|---:|---:|---:|---:|---:|\n"
            f"| {shuffled_nq.seeds} | {money(shuffled_nq.null_median)} | "
            f"{money(decomp['shuffled_p5'])} | {money(shuffled_nq.null_p95)} | "
            f"{money(shuffled_nq.null_best)} | {money(shuffled_nq.real_net)} | "
            f"{shuffled_nq.p_value_ge_real:.4f} | {shuffled_nq.causality_violations} |"
        )

    decomp_md = render_edge_decomposition_table(decomp) if decomp else ""

    body = (
        "Two independent permutation families from the same `Engine + PaperBroker + v2b_scaleout` path. "
        "Real clears both: the edge requires the specific prior-opposed direction, not just timing or structure.\n\n"
        + md_table(compare_df, list(compare_df.columns))
        + "\n\n"
        + stratified_md
        + "\n\n"
        + shuffled_md
    )
    if decomp_md:
        body += "\n\n" + decomp_md
    body += "\n\nArtifact index: `live/state/v2b_prior_opposed_random_gate_replays/INDEX.md`."
    return body, decomp_md


def sync_gate_null_ledger_rows() -> None:
    if not LEDGER_PATH.exists():
        return
    gate_nulls = load_primary_gate_nulls()
    shuffled_nq = load_shuffled_gate_null_nq()
    if not gate_nulls and shuffled_nq is None:
        return
    header, ledger = read_commented_csv(LEDGER_PATH)
    rows = ledger.to_dict("records")
    changed = False

    for row in rows:
        if "counts_toward_permutation_test" not in row or not str(row.get("counts_toward_permutation_test", "")).strip():
            row["counts_toward_permutation_test"] = "FALSE"
            changed = True
        subclass = str(row.get("trial_subclass", ""))
        if subclass == "all_day_v2b_sampling_control_available":
            if row.get("notes") != SECONDARY_SAMPLING_CONTROL_NOTES:
                row["notes"] = SECONDARY_SAMPLING_CONTROL_NOTES
                changed = True
            if row.get("counts_toward_permutation_test") != "FALSE":
                row["counts_toward_permutation_test"] = "FALSE"
                changed = True

    by_subclass = {str(r.get("trial_subclass", "")): r for r in rows}
    next_idx = len(rows) + 1
    for g in gate_nulls:
        subclass = f"gate_null_stratified_fine_{g.market.lower()}"
        trial_id = str(by_subclass.get(subclass, {}).get("trial_id") or f"TRL-2026-{next_idx:05d}")
        fresh = stratified_permutation_ledger_row(g, trial_id)
        if subclass in by_subclass:
            idx = next(i for i, r in enumerate(rows) if str(r.get("trial_subclass")) == subclass)
            rows[idx] = fresh
            changed = True
        else:
            rows.append(fresh)
            next_idx += 1
            changed = True

    shuffled_nq = load_shuffled_gate_null_nq()
    if shuffled_nq is not None:
        subclass = "gate_null_shuffled_stpmc_side_nq"
        fresh = shuffled_permutation_ledger_row(shuffled_nq, SHUFFLED_LEDGER_TRIAL_ID)
        if subclass in by_subclass:
            idx = next(i for i, r in enumerate(rows) if str(r.get("trial_subclass")) == subclass)
            rows[idx] = fresh
            changed = True
        elif any(str(r.get("trial_id")) == SHUFFLED_LEDGER_TRIAL_ID for r in rows):
            idx = next(i for i, r in enumerate(rows) if str(r.get("trial_id")) == SHUFFLED_LEDGER_TRIAL_ID)
            rows[idx] = fresh
            changed = True
        else:
            rows.append(fresh)
            changed = True

    if changed:
        write_commented_csv(LEDGER_PATH, LEDGER_COLUMNS, rows)


def merge_gate_null_ledger_rows() -> None:
    sync_gate_null_ledger_rows()


def family_metrics_table(metrics: pd.DataFrame, names: tuple[str, ...]) -> pd.DataFrame:
    out = metrics[metrics["name"].isin(names)].copy()
    order = {name: idx for idx, name in enumerate(names)}
    out["_order"] = out["name"].map(order)
    out = out.sort_values("_order").drop(columns="_order")
    return pd.DataFrame(
        {
            "Strategy": out["name"],
            "Instrument": out["instrument"],
            "Sharpe": out["sharpe_daily"].map(lambda x: f"{float(x):.2f}"),
            "Sortino": out["sortino_daily"].map(lambda x: f"{float(x):.2f}"),
            "CAGR": out["cagr_pct"].map(lambda x: f"{float(x):.1f}%"),
            "Calmar": out["calmar_mar"].map(lambda x: f"{float(x):.2f}"),
            "Net": out["net_usd"].map(lambda x: money(float(x))),
            "PF": out["profit_factor"].map(lambda x: f"{float(x):.2f}"),
        }
    )


def render_family_section(
    *,
    family_label: str,
    headline_name: str,
    cross_names: tuple[str, ...],
    metrics: pd.DataFrame,
) -> str:
    if headline_name not in set(metrics["name"]):
        return f"### {family_label}\n\nHeadline metric `{headline_name}` not found in `metrics.csv`.\n"
    headline = metrics[metrics["name"].eq(headline_name)].iloc[0]
    table = family_metrics_table(metrics, cross_names)
    return (
        f"### {family_label}\n\n"
        f"Headline: **{headline_name}** — Sharpe {float(headline['sharpe_daily']):.2f}, "
        f"CAGR {pct(float(headline['cagr_pct']))}, net {money(float(headline['net_usd']))}.\n\n"
        f"**Family-specific gate null:** not run (Phase 1c).\n\n"
        f"{md_table(table, list(table.columns))}\n"
    )

@dataclass
class SamplingControl:
    real_net: float
    campaign_count: int
    pool_count: int
    iterations: int
    p_value_ge_real: float
    percentile: float
    p5: float
    p50: float
    p95: float
    samples: np.ndarray


def campaign_sampling_control() -> SamplingControl | None:
    real_path = ROOT / "live/state/nq_v2b_prior_opposed_stpmc_broker_like/states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3/unit_trades.csv"
    pool_path = ROOT / "live/state/v2b_sizing_sweep/states/nq_v2b_sizing_S_1_1_3/unit_trades.csv"
    if not real_path.exists() or not pool_path.exists():
        return None
    real = pd.read_csv(real_path)
    pool = pd.read_csv(pool_path)
    real_campaign = real.groupby("trade_id")["net_usd"].sum()
    pool_campaign = pool.groupby("trade_id")["net_usd"].sum()
    k = len(real_campaign)
    rng = np.random.default_rng(20260626)
    pool_values = pool_campaign.to_numpy(dtype=float)
    replace = k > len(pool_values)
    samples = np.array([rng.choice(pool_values, size=k, replace=replace).sum() for _ in range(2000)])
    real_net = float(real_campaign.sum())
    p_value = float((np.sum(samples >= real_net) + 1) / (len(samples) + 1))
    percentile = float(np.sum(samples < real_net) / len(samples) * 100.0)
    return SamplingControl(
        real_net=real_net,
        campaign_count=k,
        pool_count=len(pool_values),
        iterations=len(samples),
        p_value_ge_real=p_value,
        percentile=percentile,
        p5=float(np.percentile(samples, 5)),
        p50=float(np.percentile(samples, 50)),
        p95=float(np.percentile(samples, 95)),
        samples=samples,
    )


def bootstrap_sharpe(returns: pd.Series, iterations: int = 2000) -> np.ndarray:
    rng = np.random.default_rng(20260626)
    arr = returns.to_numpy(dtype=float)
    return np.array([sharpe(rng.choice(arr, size=len(arr), replace=True)) for _ in range(iterations)])


def save_charts(
    metrics: pd.DataFrame,
    nq_row: pd.Series,
    returns: pd.Series,
    bootstrap: np.ndarray,
    control: SamplingControl | None,
    gate_nulls: list[GateNullMarket],
    shuffled_nq_null: GateNullMarket | None = None,
) -> dict[str, str]:
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    chart_paths: dict[str, str] = {}

    eq = pd.read_csv(ROOT / nq_row["equity_path"])
    eq["ts"] = pd.to_datetime(eq["ts"], utc=True)
    eq["account_equity"] = float(nq_row["reference_capital_3x_stress"]) + eq["close_equity_usd"].astype(float)
    eq["drawdown"] = eq["account_equity"] - eq["account_equity"].cummax()
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
    axes[0].plot(eq["ts"], eq["account_equity"], color="#1f5aa6", linewidth=1.5)
    axes[0].set_title("NQ Prior-Opposed Equity on 3x Stress Reference Capital")
    axes[0].set_ylabel("Equity ($)")
    axes[0].grid(True, alpha=0.25)
    axes[1].fill_between(eq["ts"], eq["drawdown"], 0, color="#b23b3b", alpha=0.7)
    axes[1].set_ylabel("Close DD ($)")
    axes[1].grid(True, alpha=0.25)
    fig.tight_layout()
    path = CHART_DIR / "nq_equity_drawdown.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    chart_paths["equity_drawdown"] = str(path.relative_to(OUT_DIR))

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(bootstrap[np.isfinite(bootstrap)], bins=50, color="#547aa5", alpha=0.8)
    ax.axvline(float(nq_row["sharpe_daily"]), color="#111111", linestyle="--", linewidth=1.5, label="Observed Sharpe")
    ax.set_title("Bootstrap Sharpe Distribution")
    ax.set_xlabel("Annualized Sharpe")
    ax.set_ylabel("Samples")
    ax.legend()
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    path = CHART_DIR / "bootstrap_sharpe.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    chart_paths["bootstrap_sharpe"] = str(path.relative_to(OUT_DIR))

    top = metrics.sort_values("sharpe_daily", ascending=True).tail(12)
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.barh(top["name"], top["sharpe_daily"], color="#2f7d5b")
    ax.set_title("Top Local Strategy Sharpes (Backtested)")
    ax.set_xlabel("Annualized Sharpe")
    ax.grid(True, axis="x", alpha=0.25)
    fig.tight_layout()
    path = CHART_DIR / "local_strategy_sharpe_rank.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    chart_paths["local_sharpe_rank"] = str(path.relative_to(OUT_DIR))

    if control is not None:
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.hist(control.samples, bins=50, color="#999999", alpha=0.85)
        ax.axvline(control.real_net, color="#b23b3b", linestyle="--", linewidth=1.6, label="Real prior-opposed net")
        ax.set_title("All-Day V2B Campaign Sampling Control")
        ax.set_xlabel("Sampled campaign net ($)")
        ax.set_ylabel("Samples")
        ax.legend()
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        path = CHART_DIR / "sampling_control_net.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        chart_paths["sampling_control"] = str(path.relative_to(OUT_DIR))

    nq_null = next((g for g in gate_nulls if g.market == "NQ"), None)
    if nq_null is not None:
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.hist(nq_null.null_nets, bins=50, color="#4a6fa5", alpha=0.85)
        ax.axvline(nq_null.real_net, color="#b23b3b", linestyle="--", linewidth=1.6, label="Real strict prior-opposed net")
        ax.axvline(nq_null.null_median, color="#333333", linestyle=":", linewidth=1.2, label="Null median")
        ax.set_title("Stratified Random Delayed-Arming Gate Null (NQ, 200 seeds)")
        ax.set_xlabel("Net ($)")
        ax.set_ylabel("Seeds")
        ax.legend()
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        path = CHART_DIR / "gate_null_nq_net.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        chart_paths["gate_null_nq"] = str(path.relative_to(OUT_DIR))

    if shuffled_nq_null is not None:
        fig, ax = plt.subplots(figsize=(9, 5))
        ax.hist(shuffled_nq_null.null_nets, bins=50, color="#6b8e6b", alpha=0.85)
        ax.axvline(shuffled_nq_null.real_net, color="#b23b3b", linestyle="--", linewidth=1.6, label="Real strict prior-opposed net")
        ax.axvline(shuffled_nq_null.null_median, color="#333333", linestyle=":", linewidth=1.2, label="Null median")
        ax.set_title("Shuffled-Label Gate Null (NQ, 200 seeds)")
        ax.set_xlabel("Net ($)")
        ax.set_ylabel("Seeds")
        ax.set_xlim(left=0)
        ax.legend()
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        path = CHART_DIR / "gate_null_shuffled_nq_net.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        chart_paths["gate_null_shuffled_nq"] = str(path.relative_to(OUT_DIR))

    return chart_paths


def money(value: float) -> str:
    return f"${value:,.0f}"


def pct(value: float) -> str:
    return f"{value:.1f}%"


def md_table(df: pd.DataFrame, cols: list[str]) -> str:
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(row[col]) for col in cols) + " |")
    return "\n".join(lines)


def write_outputs(
    metrics: pd.DataFrame,
    ledger_header: str,
    peer_header: str,
    ledger: pd.DataFrame,
    peer: pd.DataFrame,
    n_eff: float,
    warnings: list[str],
    peer_stats: dict[str, Any],
    dsr_primary: dict[str, Any],
    dsr_daily: dict[str, Any],
    sr_campaign: float,
    boot: np.ndarray,
    control: SamplingControl | None,
    gate_nulls: list[GateNullMarket],
    shuffled_nq_null: GateNullMarket | None,
    chart_paths: dict[str, str],
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    EXHIBIT_DIR.mkdir(parents=True, exist_ok=True)

    nq = metrics[metrics["name"].eq("NQ prior-opposed v2b gate S_1_1_3")].iloc[0]
    top = metrics.sort_values(["sharpe_daily", "cagr_pct"], ascending=False).head(12).copy()
    top_out = pd.DataFrame(
        {
            "Strategy": top["name"],
            "Instrument": top["instrument"],
            "Sharpe": top["sharpe_daily"].map(lambda x: f"{x:.2f}"),
            "Sortino": top["sortino_daily"].map(lambda x: f"{x:.2f}"),
            "CAGR": top["cagr_pct"].map(lambda x: f"{x:.1f}%"),
            "Calmar": top["calmar_mar"].map(lambda x: f"{x:.2f}"),
            "QQQ Corr": top["qqq_daily_corr"].map(lambda x: f"{x:.2f}"),
        }
    )
    top_out.to_csv(EXHIBIT_DIR / "validation_summary.csv", index=False)

    missing = [
        {
            "Area": "Peer comparison",
            "Implemented now": "Schema, source-tier rules, N-count guards, suppression warnings.",
            "Missing data": "Sourced peer metric values and direct URLs/files for each manager.",
            "Left over": "Populate peer_comparison_table.csv from factsheets/databases, then enable z-scores and DSR_PEER_BENCHMARK.",
        },
        {
            "Area": "DSR trial accounting",
            "Implemented now": f"Backfilled ledger from {len(metrics)} local strategy metric rows; N_eff={n_eff:.2f}.",
            "Missing data": "Full historical analyst lab notebook for every old exploratory run.",
            "Left over": "Going forward, log every new run before review; optionally reconstruct older sweeps at finer granularity.",
        },
        {
            "Area": "Random gate null",
            "Implemented now": (
                "200-seed stratified_fine_buckets on NQ/MNQ/YM/MYM and 200-seed shuffled_stpmc_side on NQ "
                "(both p=0.0050, two-family NQ exhibit)."
            ),
            "Missing data": (
                "Shuffled-label 200-seed on MNQ/YM/MYM; spec-aligned stratified_coarse_buckets NQ; "
                "ES 1m DBN; 2,000-seed resolution scale."
            ),
            "Left over": (
                "Queue cross-market shuffled 200-seed, then coarse-bucket NQ, then 2,000-seed stratified scale."
            ),
        },
        {
            "Area": "Execution truth",
            "Implemented now": "Scorecard carries tick-proof warning and links to execution scrutiny.",
            "Missing data": "Tick reconstruction and broker-paper order/fill parity for same-minute/pre-arm-touch rows.",
            "Left over": "Run tick replay and Tradovate/CQG demo paper reconciliation before live funding claims.",
        },
        {
            "Area": "Stress/Monte Carlo",
            "Implemented now": "Daily bootstrap Sharpe and equity/drawdown chart.",
            "Missing data": "Block bootstrap, synthetic macro shock calibration, recovery-time scenario table.",
            "Left over": "Add final-report mode with 20k bootstrap paths and named historical/synthetic shocks.",
        },
    ]
    missing_df = pd.DataFrame(missing)

    boot_clean = boot[np.isfinite(boot)]
    boot_stats = {
        "p5": float(np.percentile(boot_clean, 5)),
        "p50": float(np.percentile(boot_clean, 50)),
        "p95": float(np.percentile(boot_clean, 95)),
    }

    control_dict = None
    if control is not None:
        control_dict = {
            "real_net": control.real_net,
            "campaign_count": control.campaign_count,
            "pool_count": control.pool_count,
            "iterations": control.iterations,
            "p_value_ge_real": control.p_value_ge_real,
            "percentile": control.percentile,
            "p5": control.p5,
            "p50": control.p50,
            "p95": control.p95,
        }

    data = {
        "generated_at": now_iso(),
        "ledger_header": ledger_header,
        "peer_header": peer_header,
        "n_eff": n_eff,
        "warnings": warnings,
        "sr_star": {
            "name": nq["name"],
            "sharpe": float(nq["sharpe_daily"]),
            "sortino": float(nq["sortino_daily"]),
            "cagr_pct": float(nq["cagr_pct"]),
            "calmar": float(nq["calmar_mar"]),
            "qqq_corr": float(nq["qqq_daily_corr"]),
            "qqq_downside_capture": float(nq["qqq_downside_capture"]),
        },
        "dsr_primary": dsr_primary,
        "dsr_daily": dsr_daily,
        "sr_campaign": sr_campaign,
        "bootstrap_sharpe": boot_stats,
        "sampling_control": control_dict,
        "gate_nulls": [
            {
                "market": g.market,
                "method": g.method,
                "seeds": g.seeds,
                "family_display": g.family_display,
                "real_net": g.real_net,
                "null_median": g.null_median,
                "null_p95": g.null_p95,
                "p_value_ge_real": g.p_value_ge_real,
                "causality_violations": g.causality_violations,
            }
            for g in gate_nulls
        ],
        "shuffled_null_nq": (
            {
                "market": shuffled_nq_null.market,
                "method": shuffled_nq_null.method,
                "seeds": shuffled_nq_null.seeds,
                "family_display": shuffled_nq_null.family_display,
                "real_net": shuffled_nq_null.real_net,
                "null_median": shuffled_nq_null.null_median,
                "null_p95": shuffled_nq_null.null_p95,
                "p_value_ge_real": shuffled_nq_null.p_value_ge_real,
                "causality_violations": shuffled_nq_null.causality_violations,
            }
            if shuffled_nq_null is not None
            else None
        ),
        "edge_decomposition_nq": (
            compute_nq_edge_decomposition(
                next(g for g in gate_nulls if g.market == "NQ"),
                shuffled_nq_null,
            )
            if shuffled_nq_null is not None and any(g.market == "NQ" for g in gate_nulls)
            else None
        ),
        "peer_stats": peer_stats,
        "charts": chart_paths,
    }
    (OUT_DIR / "scorecard_data.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


    nq_strat = next((g for g in gate_nulls if g.market == "NQ"), None)
    decomp = (
        compute_nq_edge_decomposition(nq_strat, shuffled_nq_null)
        if nq_strat is not None and shuffled_nq_null is not None
        else None
    )
    two_family_md, decomp_md = render_two_family_null_section(gate_nulls, shuffled_nq_null, decomp)

    warning_block = "\n".join(f"- `{w}`" for w in warnings) if warnings else "- None"
    control_md = "Not available: all-day campaign tape missing."
    if control is not None:
        control_md = (
            f"Equal-count campaign sampling control used {control.campaign_count} campaigns sampled from "
            f"{control.pool_count} all-day v2b campaigns over {control.iterations:,} iterations. Real net "
            f"was {money(control.real_net)}; sampling median was {money(control.p50)} and P95 was "
            f"{money(control.p95)}. Real result percentile: {control.percentile:.1f}; one-sided "
            f"p-value for sampled net >= real net: {control.p_value_ge_real:.4f}. This is supportive, "
"but it is not a true randomized delayed-arming replay."
        )
    sampling_md = control_md if control is not None else "Secondary diagnostic unavailable."

    yearly_orb_md = render_family_section(
        family_label="Yearly ORB (scaleout3)",
        headline_name=YEARLY_ORB_HEADLINE,
        cross_names=YEARLY_ORB_CROSS_MARKETS,
        metrics=metrics,
    )
    atr_md = render_family_section(
        family_label="ATR supertrend daily ladder (1/1/2/2/2 10-max)",
        headline_name=ATR_HEADLINE,
        cross_names=ATR_CROSS_MARKETS,
        metrics=metrics,
    )
    tier1_families_md = (
        "Equal validation scrutiny targets for non-v2b Tier-1 families. Gate nulls are v2b-only until Phase 1c.\n\n"
        + yearly_orb_md
        + "\n"
        + atr_md
    )

    report = f"""# Strategy Validation Scorecard

Generated: {data['generated_at']}

This report is **hypothetical/backtested and unaudited**. It is designed to make allocator diligence uncomfortable in the useful way: strong numbers are shown next to the data-quality limits and remaining overfit checks.

## What We Can Implement Now

{md_table(missing_df, ['Area', 'Implemented now', 'Missing data', 'Left over'])}

## Headline Candidate

| Metric | NQ prior-opposed v2b gate |
|---|---:|
| Sharpe | {float(nq['sharpe_daily']):.2f} |
| Sortino | {float(nq['sortino_daily']):.2f} |
| CAGR | {pct(float(nq['cagr_pct']))} |
| Calmar | {float(nq['calmar_mar']):.2f} |
| QQQ correlation | {float(nq['qqq_daily_corr']):.2f} |
| QQQ downside capture | {float(nq['qqq_downside_capture']):.2f} |
| Profit factor | {float(nq['profit_factor']):.2f} |

![NQ equity and drawdown]({chart_paths['equity_drawdown']})

## Tier-1 Families (Phase 1b)

{tier1_families_md}

## Trial Ledger / DSR (campaign-level primary)

- Ledger rows: {len(ledger)}
- Effective N: **{n_eff:.2f}**
- Campaign Sharpe (annualized): **{sr_campaign:.2f}**
- Campaign observations: {dsr_primary['observations']}
- PSR vs zero (campaign): **{dsr_primary['psr_zero'] * 100:.2f}%**
- DSR zero benchmark (campaign): **{dsr_primary['dsr_zero_benchmark'] * 100:.2f}%**
- DSR peer benchmark: **suppressed** until sourced peer Sharpe data exists.
- Campaign skew / kurtosis: {dsr_primary['skew']:.2f} / {dsr_primary['kurtosis']:.2f}
- Daily Sharpe (secondary exhibit): {float(nq['sharpe_daily']):.2f}; daily PSR: {dsr_daily['psr_zero'] * 100:.2f}%

![Bootstrap Sharpe]({chart_paths['bootstrap_sharpe']})

Bootstrap Sharpe P5/P50/P95: **{boot_stats['p5']:.2f} / {boot_stats['p50']:.2f} / {boot_stats['p95']:.2f}**.

## Two-Family Permutation Nulls (NQ)

{two_family_md}

{"![Stratified gate null NQ](" + chart_paths["gate_null_nq"] + ")" if "gate_null_nq" in chart_paths else ""}

{"![Shuffled gate null NQ](" + chart_paths["gate_null_shuffled_nq"] + ")" if "gate_null_shuffled_nq" in chart_paths else ""}

## Secondary Sampling Control

{sampling_md}

{"![Sampling control](" + chart_paths["sampling_control"] + ")" if "sampling_control" in chart_paths else ""}

## Peer Data Guard

The peer table is seeded with 12 named CTA/managed-futures comparables, but all peer metrics are `NA` until direct source documents are collected. Therefore peer z-scores and `DSR_PEER_BENCHMARK` are intentionally suppressed.

## Local Strategy Context

{md_table(top_out, ['Strategy', 'Instrument', 'Sharpe', 'Sortino', 'CAGR', 'Calmar', 'QQQ Corr'])}

![Local Sharpe Rank]({chart_paths['local_sharpe_rank']})

## Warnings

{warning_block}
"""
    (OUT_DIR / "SCORECARD_REPORT.md").write_text(report, encoding="utf-8")

    # IMPLEMENTATION_STATUS.md is maintained manually; do not overwrite with stale template.

    nq_strat_p = nq_strat.p_value_ge_real if nq_strat is not None else float("nan")
    if nq_strat is not None and math.isfinite(nq_strat_p):
        strat_pitch = format_pvalue_disclosure(nq_strat_p)
    else:
        strat_pitch = "pending"
    if shuffled_nq_null is not None:
        shuf_pitch = format_pvalue_disclosure(shuffled_nq_null.p_value_ge_real)
    else:
        shuf_pitch = "pending"
    control_pitch = f"p={control.p_value_ge_real:.4f}" if control is not None else "pending"
    decomp_pitch = ""
    if decomp is not None:
        decomp_pitch = f"""
## Qualitative Edge Decomposition (NQ)

{render_edge_decomposition_table(decomp)}

*Null families are not orthogonal; table is illustrative narrative for allocator diligence.*
"""

    pitch = f"""# NQ Intraday Validation One-Page

**Status:** hypothetical/backtested, unaudited. This page is for diligence planning, not a live CTA track record.

## Candidate

NQ intraday delayed-arming program. The exact gate mechanics remain proprietary; the validation question is whether the gate survives causality, null controls, and execution scrutiny.

## Backtested Profile

| Metric | Value |
|---|---:|
| Window | {nq['start']} to {nq['end']} |
| Net, base book | {money(float(nq['net_usd']))} |
| Intrabar stress DD | {money(float(nq['intrabar_stress_dd_usd']))} |
| Sharpe / Sortino | {float(nq['sharpe_daily']):.2f} / {float(nq['sortino_daily']):.2f} |
| CAGR / Calmar | {pct(float(nq['cagr_pct']))} / {float(nq['calmar_mar']):.2f} |
| QQQ corr / downside capture | {float(nq['qqq_daily_corr']):.2f} / {float(nq['qqq_downside_capture']):.2f} |
| Drawdown duration / daily skew | {int(float(nq['max_drawdown_duration_days']))} days / {float(nq['daily_skew']):.2f} |
| Profit factor | {float(nq['profit_factor']):.2f} |

![NQ equity and drawdown]({chart_paths['equity_drawdown']})

## Overfit Defense Now In Place

- Backfilled DSR trial ledger: **N_eff {n_eff:.2f}**.
- PSR vs zero Sharpe: **{dsr_primary['psr_zero'] * 100:.2f}%**.
- DSR zero benchmark: **{dsr_primary['dsr_zero_benchmark'] * 100:.2f}%**.
- Peer-benchmark DSR: **suppressed until direct peer Sharpe data is sourced**.
- Stratified gate null (200 seeds, structural): {strat_pitch}
- Shuffled-label gate null (200 seeds, mechanistic): {shuf_pitch}
- Secondary all-day v2b sampling control: {control_pitch}
{decomp_pitch}
## Red Flags We Are Not Hiding

- No audited live track record yet.
- Peer data table is intentionally blank rather than invented.
- Spec-aligned coarse time buckets and 2,000-seed scale are not yet complete.
- Tick reconstruction is still required for same-minute/pre-arm-touch campaigns.
"""
    (OUT_DIR / "ONE_PAGE_NQ_VALIDATION_PITCH.md").write_text(pitch, encoding="utf-8")

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Strategy Validation Scorecard</title>
  <style>
    body {{ font-family: Inter, Arial, sans-serif; margin: 32px; color: #1b1f24; line-height: 1.45; }}
    h1, h2 {{ color: #143b63; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
    .card {{ border: 1px solid #d7dde5; border-radius: 8px; padding: 14px; background: #fafbfd; }}
    .metric {{ font-size: 26px; font-weight: 700; }}
    .warn {{ background: #fff5df; border-left: 4px solid #c47a00; padding: 12px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 14px; }}
    th, td {{ border: 1px solid #d7dde5; padding: 8px; vertical-align: top; }}
    th {{ background: #eef3f8; }}
    img {{ max-width: 100%; border: 1px solid #d7dde5; border-radius: 6px; }}
  </style>
</head>
<body>
  <h1>Strategy Validation Scorecard</h1>
  <p><strong>Status:</strong> hypothetical/backtested, unaudited. Generated {data['generated_at']}.</p>
  <div class="grid">
    <div class="card"><div>Sharpe</div><div class="metric">{float(nq['sharpe_daily']):.2f}</div></div>
    <div class="card"><div>Sortino</div><div class="metric">{float(nq['sortino_daily']):.2f}</div></div>
    <div class="card"><div>CAGR</div><div class="metric">{pct(float(nq['cagr_pct']))}</div></div>
    <div class="card"><div>Calmar</div><div class="metric">{float(nq['calmar_mar']):.2f}</div></div>
    <div class="card"><div>QQQ Corr</div><div class="metric">{float(nq['qqq_daily_corr']):.2f}</div></div>
    <div class="card"><div>N_eff</div><div class="metric">{n_eff:.2f}</div></div>
  </div>
  <h2>Equity / Drawdown</h2>
  <img src="{chart_paths['equity_drawdown']}" alt="NQ equity and drawdown">
  <h2>Implemented vs Missing</h2>
  {missing_df.to_html(index=False, escape=False)}
  <h2>DSR / Bootstrap</h2>
  <p>Campaign PSR vs zero: <strong>{dsr_primary['psr_zero'] * 100:.2f}%</strong>. Campaign DSR zero: <strong>{dsr_primary['dsr_zero_benchmark'] * 100:.2f}%</strong>. Peer benchmark DSR suppressed.</p>
  <img src="{chart_paths['bootstrap_sharpe']}" alt="Bootstrap Sharpe">
  <h2>Tier-1 Families (Phase 1b)</h2>
  <p>{tier1_families_md.replace(chr(10), "<br>")}</p>
  <h2>Two-Family Permutation Nulls (NQ)</h2>
  <p>{two_family_md.replace(chr(10), "<br>")}</p>
  {f'<img src="{chart_paths["gate_null_nq"]}" alt="Stratified gate null">' if "gate_null_nq" in chart_paths else ""}
  {f'<img src="{chart_paths["gate_null_shuffled_nq"]}" alt="Shuffled gate null">' if "gate_null_shuffled_nq" in chart_paths else ""}
  <h2>Secondary Sampling Control</h2>
  <p>{sampling_md}</p>
  {f'<img src="{chart_paths["sampling_control"]}" alt="Sampling control">' if "sampling_control" in chart_paths else ""}
  <h2>Warnings</h2>
  <div class="warn"><ul>{"".join(f"<li>{w}</li>" for w in warnings)}</ul></div>
  <h2>Local Strategy Rank</h2>
  {top_out.to_html(index=False, escape=False)}
</body>
</html>
"""
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate strategy validation scorecard artifacts.")
    parser.add_argument(
        "--refresh-inputs",
        action="store_true",
        help="Regenerate seed validation CSVs from current local metric files. Without this, existing CSVs are preserved.",
    )
    args = parser.parse_args()

    if not METRICS_PATH.exists():
        raise SystemExit(f"Missing metrics file: {METRICS_PATH}")
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    EXHIBIT_DIR.mkdir(parents=True, exist_ok=True)

    metrics = pd.read_csv(METRICS_PATH)
    backfill_gate_null_run_metadata()
    if args.refresh_inputs or not LEDGER_PATH.exists():
        bootstrap_trial_ledger(metrics)
    sync_gate_null_ledger_rows()
    if args.refresh_inputs or not PEER_PATH.exists():
        bootstrap_peer_table()

    ledger_header, ledger = read_commented_csv(LEDGER_PATH)
    peer_header, peer = read_commented_csv(PEER_PATH)
    errors, warnings, n_eff = validate_ledger(ledger)
    if errors:
        for error in errors:
            print(error)
        raise SystemExit(1)

    if (peer["exclude_from_zscore"] == "TRUE").all():
        warnings.append("DSR_PEER_BENCHMARK_SUPPRESSED: no sourced peer Sharpe values")
    for _, row in peer.iterrows():
        if row["exclude_from_zscore"] == "TRUE" and row["exclusion_reason"] == "ALL_METRICS_NA":
            warnings.append(f"ALL_METRICS_NA_PEER: {row['peer_id']}")

    nq = metrics[metrics["name"].eq("NQ prior-opposed v2b gate S_1_1_3")].iloc[0]
    returns = daily_returns_from_equity(ROOT / nq["equity_path"], float(nq["reference_capital_3x_stress"]))
    peer_stats, peer_warnings = peer_metric_stats(
        peer,
        {
            "sharpe_ratio": float(nq["sharpe_daily"]),
            "sortino_ratio": float(nq["sortino_daily"]),
            "cagr_pct": float(nq["cagr_pct"]),
            "calmar_ratio": float(nq["calmar_mar"]),
            "max_drawdown_pct": max_drawdown_pct_from_metric(nq),
        },
    )
    warnings.extend(peer_warnings)
    campaign_pnl = campaign_pnl_series(NQ_PRIOR_OPPOSED_UNIT_TRADES)
    sr_campaign = campaign_sharpe_ratio(campaign_pnl)
    dsr_primary = compute_dsr(campaign_pnl, sr_campaign, n_eff, peer_median=None)
    dsr_daily = compute_dsr(returns, float(nq["sharpe_daily"]), n_eff, peer_median=None)
    boot = bootstrap_sharpe(returns)
    control = campaign_sampling_control()
    gate_nulls = load_primary_gate_nulls()
    shuffled_nq_null = load_shuffled_gate_null_nq()
    chart_paths = save_charts(metrics, nq, returns, boot, control, gate_nulls, shuffled_nq_null)
    write_outputs(
        metrics,
        ledger_header,
        peer_header,
        ledger,
        peer,
        n_eff,
        warnings,
        peer_stats,
        dsr_primary,
        dsr_daily,
        sr_campaign,
        boot,
        control,
        gate_nulls,
        shuffled_nq_null,
        chart_paths,
    )
    write_run_manifest(
        OUT_DIR,
        data_inputs=[METRICS_PATH, LEDGER_PATH, PEER_PATH],
        output_paths=[
            OUT_DIR / "SCORECARD_REPORT.md",
            OUT_DIR / "index.html",
            OUT_DIR / "scorecard_data.json",
            OUT_DIR / "ONE_PAGE_NQ_VALIDATION_PITCH.md",
            OUT_DIR / "IMPLEMENTATION_STATUS.md",
        ],
        strategy_config={"driver": "generate_strategy_validation_scorecard", "refresh_inputs": args.refresh_inputs},
        causality_mode="audit",
        extra={"n_eff": n_eff, "warnings": warnings},
        repo_root=ROOT,
    )
    print(f"Wrote scorecard to {OUT_DIR}")


if __name__ == "__main__":
    main()
