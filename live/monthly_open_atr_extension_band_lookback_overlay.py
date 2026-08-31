"""Skip / size overlays from pct75 lookback predictors on the pct75 fade book.

Joins causal month-start features from
``live/state/monthly_open_atr_extension_band/lookback_filter`` onto the
pandas **pct75 / rolling-6m** fade tape, then scores:

- **filter** — take only HP (high-lift) months
- **skip** — drop protective (low-lift) months
- **size_1.25 / size_1.5** — size-up when HP

Decision metric is whole-book **net** and **N/S** (stress = peak-to-trough
equity DD), with chronological IS/OOS — **not** touch-rate lift alone.

Hub: ``live/state/monthly_open_atr_extension_band/lookback_overlay/``

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.monthly_open_atr_extension_band_lookback_overlay --email
"""

from __future__ import annotations

import argparse
import json
import math
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .monthly_open_atr_extension_band_broker import (
    DEFAULT_ROLLING_BAND_MONTHS,
    DEFAULT_SYMBOLS,
    backtest_market,
    collect_path_stats,
)
from .monthly_open_atr_extension_band_lookback_filter import (
    BINARY_FEATURES,
    MIN_BUCKET_N,
    OPTIONAL_BINARY,
)
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS
from .run_ledger import log_run

REPO = Path(__file__).resolve().parents[1]
LOOKBACK_HUB = (
    REPO / "live" / "state" / "monthly_open_atr_extension_band" / "lookback_filter"
)
DEFAULT_OUT = (
    REPO / "live" / "state" / "monthly_open_atr_extension_band" / "lookback_overlay"
)

HP_LIFT_MIN = 1.20
HP_Z_MIN = 1.20
SKIP_LIFT_MAX = 0.85
IS_FRAC = 0.60
SIZE_MULTS = (1.25, 1.50)


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    path = output_root / "PROGRESS.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _max_dd(equity: np.ndarray) -> float:
    if equity.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    return float((equity - peak).min())


def score_nets(nets: np.ndarray, *, label: str = "") -> Dict[str, float]:
    nets = np.asarray(nets, dtype=float)
    n = int(nets.size)
    if n == 0:
        return {
            "label": label,
            "n": 0,
            "wins": 0,
            "wr": 0.0,
            "net": 0.0,
            "avg": 0.0,
            "max_dd": 0.0,
            "stress": 0.0,
            "ns": 0.0,
        }
    eq = np.cumsum(nets)
    dd = _max_dd(eq)
    stress = abs(dd)
    net = float(nets.sum())
    wins = int((nets > 0).sum())
    return {
        "label": label,
        "n": n,
        "wins": wins,
        "wr": wins / n,
        "net": net,
        "avg": float(nets.mean()),
        "max_dd": dd,
        "stress": stress,
        "ns": (net / stress) if stress > 1e-9 else (99.0 if net > 0 else 0.0),
    }


def apply_policy(
    base: np.ndarray,
    mask: np.ndarray,
    policy: str,
    size_mult: float = 1.0,
) -> np.ndarray:
    base = np.asarray(base, dtype=float)
    mask = np.asarray(mask, dtype=bool)
    if policy == "baseline":
        return base.copy()
    if policy == "filter":
        return base[mask]
    if policy == "skip":
        return base[~mask]
    if policy.startswith("size_"):
        out = base.copy()
        out[mask] = out[mask] * float(size_mult)
        return out
    raise ValueError("unknown policy %s" % policy)


def _feature_mask(df: pd.DataFrame, feature: str, bucket: str) -> np.ndarray:
    if feature not in df.columns:
        return np.zeros(len(df), dtype=bool)
    series = df[feature]
    b = str(bucket)
    if b.lower() in {"true", "1", "yes"}:
        return series.fillna(0).astype(float).astype(bool).to_numpy()
    if b.lower() in {"false", "0", "no"}:
        return (~series.fillna(0).astype(float).astype(bool)).to_numpy()
    # categorical (cal_month, month_name, quarter, quartiles)
    return (series.astype(str) == b).to_numpy()


def build_pct75_trades(
    symbols: Sequence[str],
    *,
    rolling_window: int = DEFAULT_ROLLING_BAND_MONTHS,
) -> pd.DataFrame:
    rows = []
    for sym in symbols:
        sym = sym.upper()
        spec = MARKETS[sym]
        paths = collect_path_stats(spec)
        trades = backtest_market(
            spec,
            paths,
            band_mode="rolling",
            entry_mode="pct75",
            rolling_window=rolling_window,
        )
        rows.extend(asdict(t) for t in trades)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True)
    return df.sort_values(["entry_ts", "market", "side"]).reset_index(drop=True)


def load_features(lookback_hub: Path) -> pd.DataFrame:
    path = lookback_hub / "months_features_all.csv"
    if not path.exists():
        raise FileNotFoundError(
            "Missing %s — run live.monthly_open_atr_extension_band_lookback_filter first"
            % path
        )
    feat = pd.read_csv(path)
    # normalize bool-ish columns that may be 0/1
    for col in list(BINARY_FEATURES) + list(OPTIONAL_BINARY):
        if col in feat.columns:
            feat[col] = feat[col].fillna(0).astype(float)
    return feat


def select_candidates(lift_all: pd.DataFrame) -> pd.DataFrame:
    """HP size/filter + protective skip candidates from lookback lift tables."""
    lift = lift_all.copy()
    lift = lift[lift["label"] == "touch_pct75_any"]
    rows: List[dict] = []

    hp = lift[
        (lift["bucket"].astype(str) == "true")
        & (lift["lift"] >= HP_LIFT_MIN)
        & (lift["z"].abs() >= HP_Z_MIN)
        & (lift["n"] >= MIN_BUCKET_N)
    ]
    for _, r in hp.iterrows():
        rows.append(
            {
                "kind": "hp",
                "market": str(r["market"]),
                "feature": str(r["feature"]),
                "bucket": "true",
                "lift_n": int(r["n"]),
                "lift": float(r["lift"]),
                "z": float(r["z"]),
                "hit_rate": float(r["hit_rate"]),
            }
        )

    # categorical highs (e.g. Jul) already in lift with non-true buckets
    cat = lift[
        (lift["bucket"].astype(str) != "true")
        & (lift["feature"].isin(["cal_month", "month_name", "quarter"]))
        & (lift["lift"] >= HP_LIFT_MIN)
        & (lift["z"].abs() >= HP_Z_MIN)
        & (lift["n"] >= MIN_BUCKET_N)
    ]
    for _, r in cat.iterrows():
        rows.append(
            {
                "kind": "hp",
                "market": str(r["market"]),
                "feature": str(r["feature"]),
                "bucket": str(r["bucket"]),
                "lift_n": int(r["n"]),
                "lift": float(r["lift"]),
                "z": float(r["z"]),
                "hit_rate": float(r["hit_rate"]),
            }
        )

    skip = lift[
        (lift["bucket"].astype(str) == "true")
        & (lift["lift"] <= SKIP_LIFT_MAX)
        & (lift["n"] >= MIN_BUCKET_N)
        & (lift["feature"].isin(list(BINARY_FEATURES) + list(OPTIONAL_BINARY)))
    ]
    for _, r in skip.iterrows():
        rows.append(
            {
                "kind": "skip",
                "market": str(r["market"]),
                "feature": str(r["feature"]),
                "bucket": "true",
                "lift_n": int(r["n"]),
                "lift": float(r["lift"]),
                "z": float(r["z"]),
                "hit_rate": float(r["hit_rate"]),
            }
        )

    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).drop_duplicates(subset=["kind", "market", "feature", "bucket"])
    return out.sort_values(["kind", "market", "lift"], ascending=[True, True, False]).reset_index(
        drop=True
    )


def evaluate_candidate(
    tape: pd.DataFrame,
    *,
    market: str,
    feature: str,
    bucket: str,
    kind: str,
    lift: float,
    z: float,
    lift_n: int,
    is_frac: float = IS_FRAC,
) -> List[dict]:
    df = tape[tape["market"] == market].sort_values("entry_ts").reset_index(drop=True)
    if df.empty:
        return []
    mask = _feature_mask(df, feature, bucket)
    hit_n = int(mask.sum())
    if hit_n < 5 and kind == "hp":
        return []
    if int((~mask).sum()) < 5 and kind == "skip":
        return []

    if kind == "hp":
        policies: List[Tuple[str, float]] = [
            ("baseline", 1.0),
            ("filter", 0.0),
            ("size_1.25", 1.25),
            ("size_1.5", 1.5),
        ]
    else:
        policies = [("baseline", 1.0), ("skip", 0.0)]

    cut = max(int(len(df) * is_frac), 1)
    splits = (
        ("full", df, mask),
        ("is", df.iloc[:cut], mask[:cut]),
        ("oos", df.iloc[cut:], mask[cut:]),
    )
    out: List[dict] = []
    for split_name, split_df, split_mask in splits:
        if split_df.empty:
            continue
        base_nets = split_df["pnl_usd"].to_numpy(dtype=float)
        base = score_nets(base_nets, label="baseline")
        for policy, mult in policies:
            nets = apply_policy(base_nets, split_mask, policy, size_mult=mult)
            sc = score_nets(nets, label=policy)
            out.append(
                {
                    "kind": kind,
                    "market": market,
                    "feature": feature,
                    "bucket": str(bucket),
                    "lift": lift,
                    "z": z,
                    "lift_n": lift_n,
                    "split": split_name,
                    "policy": policy,
                    "size_mult": float(mult) if policy.startswith("size_") else (
                        0.0 if policy in {"filter", "skip"} else 1.0
                    ),
                    "hit_n": int(split_mask.sum()),
                    "hit_frac": float(split_mask.mean()) if len(split_mask) else 0.0,
                    "base_n": base["n"],
                    "base_net": base["net"],
                    "base_avg": base["avg"],
                    "base_wr": base["wr"],
                    "base_stress": base["stress"],
                    "base_ns": base["ns"],
                    "n": sc["n"],
                    "net": sc["net"],
                    "avg": sc["avg"],
                    "wr": sc["wr"],
                    "stress": sc["stress"],
                    "ns": sc["ns"],
                    "delta_net": sc["net"] - base["net"],
                    "delta_ns": sc["ns"] - base["ns"],
                    "delta_stress": sc["stress"] - base["stress"],
                }
            )
    return out


def stance_row(r: dict) -> str:
    """Promote / retain / reject from OOS net + N/S — not lift.

    Prefer overlays on **positive OOS baseline** books (same rule as
    intraday_condition_overlay LIVE_PLAN). Negative-baseline salvage =
    retain/research only.
    """
    if r.get("split") != "oos" or r.get("policy") == "baseline":
        return ""
    policy = r["policy"]
    base_ok = float(r.get("base_net") or 0.0) > 0.0
    if policy == "filter":
        if r["n"] < 8:
            return "thin"
        if (
            base_ok
            and r["net"] > 0
            and r["delta_net"] > 0
            and r["ns"] >= r["base_ns"]
            and r["avg"] >= r["base_avg"]
        ):
            return "worth_filter"
        if r["delta_net"] > 0 and r["ns"] >= 0.9 * r["base_ns"]:
            return "retain_filter"
        return "reject_filter"
    if policy == "skip":
        if r["n"] < 8:
            return "thin"
        # Require a real sit-out cohort (not 1–2 months) and leftover book >0.
        if int(r.get("hit_n") or 0) < 4:
            return "thin"
        if (
            base_ok
            and r["net"] > 0
            and r["delta_net"] >= -0.02 * abs(r["base_net"])
            and r["ns"] > r["base_ns"]
            and r["delta_ns"] >= 0.10
        ):
            return "worth_skip"
        if r["ns"] >= r["base_ns"] and r["delta_net"] >= -0.05 * abs(r["base_net"] + 1):
            return "retain_skip"
        return "reject_skip"
    if policy.startswith("size_"):
        if r["delta_net"] <= 0:
            return "reject_size"
        stress_ok = r["stress"] <= 1.35 * r["base_stress"] + 1.0
        ns_ok = r["ns"] >= 0.85 * r["base_ns"]
        # Size-up only "worth" on already-profitable OOS baseline + ΔN/S≥0.
        if (
            base_ok
            and r["net"] > 0
            and stress_ok
            and ns_ok
            and r["delta_ns"] >= 0
            and int(r.get("hit_n") or 0) >= 5
        ):
            return "worth_size"
        if stress_ok and r["delta_net"] > 0:
            return "retain_size"
        return "reject_size"
    return ""

def render_summary(
    *,
    baselines: pd.DataFrame,
    candidates: pd.DataFrame,
    results: pd.DataFrame,
) -> str:
    lines = [
        "# Monthly ATR pct75 lookback — skip / size overlay",
        "",
        "Wired lookback predictors onto the **pct75 / rolling-6m** pandas fade book.",
        "Gate = **Δnet + ΔN/S** on chronological OOS (last 40%), not touch-rate lift.",
        "",
        "## Baselines (full tape)",
        "",
        "| Market | N | Net $ | Stress $ | N/S | WR |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for _, r in baselines.iterrows():
        lines.append(
            "| %s | %d | %s | %s | %.2f | %.0f%% |"
            % (
                r["market"],
                int(r["n"]),
                "{:,.0f}".format(r["net"]),
                "{:,.0f}".format(r["stress"]),
                r["ns"],
                100 * r["wr"],
            )
        )
    lines.extend(["", "## Candidates from lookback lift", ""])
    if candidates.empty:
        lines.append("_None._")
    else:
        lines.append("| Kind | Market | Feature | Bucket | Lift n | Lift | z |")
        lines.append("|---|---|---|---|---:|---:|---:|")
        for _, r in candidates.iterrows():
            lines.append(
                "| %s | %s | %s | %s | %d | %.2fx | %.2f |"
                % (
                    r["kind"],
                    r["market"],
                    r["feature"],
                    r["bucket"],
                    int(r["lift_n"]),
                    r["lift"],
                    r["z"],
                )
            )

    oos = results[(results["split"] == "oos") & (results["policy"] != "baseline")].copy()
    lines.extend(["", "## OOS overlay scorecard (Δnet / ΔN/S)", ""])
    if oos.empty:
        lines.append("_No OOS rows._")
    else:
        show = oos.sort_values(["kind", "delta_ns", "delta_net"], ascending=[True, False, False])
        lines.append(
            "| Stance | Market | Feature | Policy | Hit n | Net $ | Δnet | N/S | ΔN/S | Stress |"
        )
        lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---:|")
        for _, r in show.iterrows():
            lines.append(
                "| %s | %s | %s=%s | %s | %d | %s | %s | %.2f | %+.2f | %s |"
                % (
                    r.get("stance") or "—",
                    r["market"],
                    r["feature"],
                    r["bucket"],
                    r["policy"],
                    int(r["hit_n"]),
                    "{:,.0f}".format(r["net"]),
                    "{:+,.0f}".format(r["delta_net"]),
                    r["ns"],
                    r["delta_ns"],
                    "{:,.0f}".format(r["stress"]),
                )
            )

    worth = oos[oos["stance"].astype(str).str.startswith("worth")] if not oos.empty else oos
    lines.extend(
        [
            "",
            "## Stance",
            "",
            "- **Do not promote** from lookback lift alone.",
            "- **worth_*** = positive OOS baseline + Δnet/ΔN/S heuristic; nulls before paper.",
            "- **retain_*** = mixed / negative-baseline salvage; shadow only.",
            "- **reject_*** / **thin** = no action.",
            "- US30/YM full tapes are flat/negative — treat overlay lifts there as salvage, not promote.",
            "",
        ]
    )
    if worth is not None and not worth.empty:
        lines.append("Cleared `worth_*` this run:")
        for _, r in worth.iterrows():
            lines.append(
                "- %s %s %s=%s %s: Δnet=%s ΔN/S=%+.2f"
                % (
                    r["market"],
                    r["kind"],
                    r["feature"],
                    r["bucket"],
                    r["policy"],
                    "{:+,.0f}".format(r["delta_net"]),
                    r["delta_ns"],
                )
            )
    else:
        lines.append("No `worth_*` OOS cells — **reject / research only**.")
    lines.append("")
    return "\n".join(lines)


def phone_email(
    output_root: Path,
    baselines: pd.DataFrame,
    results: pd.DataFrame,
) -> str:
    lines = [
        "Monthly ATR pct75 lookback overlay (skip/size)",
        "",
        "Hub: %s" % output_root,
        "",
        "Baselines:",
    ]
    for _, r in baselines.iterrows():
        lines.append(
            "  %s n=%d net=$%s N/S=%.2f"
            % (r["market"], int(r["n"]), "{:,.0f}".format(r["net"]), r["ns"])
        )
    oos = results[(results["split"] == "oos") & (results["policy"] != "baseline")].copy()
    worth = oos[oos["stance"].astype(str).str.startswith("worth")] if not oos.empty else oos
    lines.append("")
    nq_base = baselines[baselines["market"] == "NQ"]
    lines.append("")
    lines.append(
        "Note: US30/YM full-tape nets are flat/negative — size/filter there is salvage, not promote."
    )
    lines.append("")
    if worth is not None and not worth.empty:
        lines.append("worth_* OOS (positive baseline + net/N/S, not lift):")
        for _, r in worth.head(12).iterrows():
            lines.append(
                "  %s %s=%s %s hit=%d Δnet=%s ΔNS=%+.2f"
                % (
                    r["market"],
                    r["feature"],
                    r["bucket"],
                    r["policy"],
                    int(r["hit_n"]),
                    "{:+,.0f}".format(r["delta_net"]),
                    r["delta_ns"],
                )
            )
        lines.append("")
        lines.append(
            "Stance: primary shadow = NQ prior_atr_reverted size; "
            "US30 prior_bear OOS-only — still no promote; nulls required."
        )
    else:
        retain = (
            oos[oos["stance"].astype(str).str.startswith("retain")]
            if not oos.empty
            else pd.DataFrame()
        )
        lines.append("No worth_* OOS clears on positive-baseline books.")
        if not retain.empty:
            lines.append("retain_* (shadow / research):")
            for _, r in retain.head(8).iterrows():
                lines.append(
                    "  %s %s %s Δnet=%s ΔNS=%+.2f"
                    % (
                        r["market"],
                        r["feature"],
                        r["policy"],
                        "{:+,.0f}".format(r["delta_net"]),
                        r["delta_ns"],
                    )
                )
        lines.append("")
        lines.append("Stance: REJECT promote — overlays do not clear net/N/S gate.")
    if not nq_base.empty:
        lines.append(
            "NQ baseline: n=%d net=$%s N/S=%.2f"
            % (
                int(nq_base.iloc[0]["n"]),
                "{:,.0f}".format(nq_base.iloc[0]["net"]),
                float(nq_base.iloc[0]["ns"]),
            )
        )
    lines.append("Artifacts: SUMMARY.md, overlay_results.csv, trades_pct75.csv")
    return "\n".join(lines) + "\n"


def run(
    *,
    symbols: Sequence[str],
    output_root: Path,
    lookback_hub: Path = LOOKBACK_HUB,
    rolling_window: int = DEFAULT_ROLLING_BAND_MONTHS,
    email: bool = False,
) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "PROGRESS.log").write_text("", encoding="utf-8")
    _progress(output_root, "lookback overlay start symbols=%s" % list(symbols))

    try:
        _progress(output_root, "rebuild pct75 trades")
        trades = build_pct75_trades(symbols, rolling_window=rolling_window)
        trades.to_csv(output_root / "trades_pct75.csv", index=False)
        _progress(output_root, "trades=%d" % len(trades))

        feat = load_features(lookback_hub)
        lift_path = lookback_hub / "lift_all.csv"
        lift_all = pd.read_csv(lift_path)

        join_cols = ["market", "year", "month"]
        tape = trades.merge(feat, on=join_cols, how="left", suffixes=("", "_feat"))
        tape.to_csv(output_root / "trades_annotated.csv", index=False)
        missing = int(tape["touch_pct75_any"].isna().sum()) if "touch_pct75_any" in tape.columns else len(tape)
        _progress(output_root, "annotated trades=%d feature_miss=%d" % (len(tape), missing))

        candidates = select_candidates(lift_all)
        candidates.to_csv(output_root / "candidates.csv", index=False)
        _progress(output_root, "candidates=%d" % len(candidates))

        # baselines per market + portfolio
        base_rows = []
        for mkt, g in tape.groupby("market"):
            sc = score_nets(g.sort_values("entry_ts")["pnl_usd"].to_numpy(dtype=float), label=str(mkt))
            base_rows.append({"market": mkt, **{k: sc[k] for k in ("n", "net", "wr", "avg", "stress", "ns")}})
        port = score_nets(
            tape.sort_values("entry_ts")["pnl_usd"].to_numpy(dtype=float), label="PORT"
        )
        base_rows.append({"market": "PORT", **{k: port[k] for k in ("n", "net", "wr", "avg", "stress", "ns")}})
        baselines = pd.DataFrame(base_rows)
        baselines.to_csv(output_root / "baselines.csv", index=False)

        rows: List[dict] = []
        for _, c in candidates.iterrows():
            rows.extend(
                evaluate_candidate(
                    tape,
                    market=str(c["market"]),
                    feature=str(c["feature"]),
                    bucket=str(c["bucket"]),
                    kind=str(c["kind"]),
                    lift=float(c["lift"]),
                    z=float(c["z"]),
                    lift_n=int(c["lift_n"]),
                )
            )
        results = pd.DataFrame(rows)
        if not results.empty:
            results["stance"] = results.apply(lambda r: stance_row(r.to_dict()), axis=1)
            results.to_csv(output_root / "overlay_results.csv", index=False)
            oos = results[(results["split"] == "oos") & (results["policy"] != "baseline")]
            oos.to_csv(output_root / "oos_overlays.csv", index=False)

        summary = render_summary(baselines=baselines, candidates=candidates, results=results)
        (output_root / "SUMMARY.md").write_text(summary, encoding="utf-8")

        email_body = phone_email(output_root, baselines, results)
        (output_root / "EMAIL.txt").write_text(email_body, encoding="utf-8")

        worth_n = 0
        if not results.empty:
            worth_n = int(
                (
                    (results["split"] == "oos")
                    & results["stance"].astype(str).str.startswith("worth")
                ).sum()
            )
        (output_root / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "trades": len(trades),
                    "candidates": len(candidates),
                    "result_rows": len(results),
                    "worth_oos": worth_n,
                    "markets": list(symbols),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        hub_rel = str(output_root.resolve().relative_to(REPO))
        log_run(
            run_class="pandas",
            variant_slug="monthly_open_atr_ext_band_lookback_overlay",
            instrument=",".join(s.upper() for s in symbols),
            hub_path=hub_rel,
            net_usd=float(port["net"]),
            stress_dd_usd=-float(port["stress"]),
            ns=float(port["ns"]),
            trades=int(port["n"]),
            meta={"worth_oos": worth_n, "candidates": len(candidates)},
            notes="pct75 skip/size overlay vs lookback predictors; gate=net/N/S not lift",
        )

        if email:
            send_email(
                subject="potions: pct75 lookback overlay (skip/size) — worth_oos=%d" % worth_n,
                body=email_body,
            )
            _progress(output_root, "email sent")
        _progress(output_root, "DONE worth_oos=%d" % worth_n)
        return output_root
    except Exception:
        err = traceback.format_exc()
        _progress(output_root, "CRASH\n%s" % err)
        body = "potions: pct75 lookback overlay FAILED\n\nHub: %s\n\n%s\n" % (output_root, err)
        (output_root / "EMAIL.txt").write_text(body, encoding="utf-8")
        if email:
            send_email(subject="potions: pct75 lookback overlay FAILED", body=body)
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--lookback-hub", type=Path, default=LOOKBACK_HUB)
    ap.add_argument("--symbol", action="append", dest="symbols")
    ap.add_argument("--rolling-window", type=int, default=DEFAULT_ROLLING_BAND_MONTHS)
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    symbols = args.symbols or list(DEFAULT_SYMBOLS)
    run(
        symbols=symbols,
        output_root=args.output_root,
        lookback_hub=args.lookback_hub,
        rolling_window=int(args.rolling_window),
        email=bool(args.email),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
