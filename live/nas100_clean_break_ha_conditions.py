"""HA (high-probability conditions) mill for NAS100 clean-break trail06.

Source: ``nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill_validation``
unit-book fills (Engine+PaperBroker 1m-fill; public/demo Index Momentum = ×10).

Pipeline (same bar as weekly OD / CHOP20 / monthly FBO HA mills):

1. Condition profile on campaign tape (DOW / WoM / Entry month / hour /
   5m MA / RSI / OBV / ATR / prior range-half)
2. Filter / 1.25× / 1.5× overlays on profile notables (organic, not forced months)
3. Matched-added-exposure nulls at **1.25×** on strongest live-ready size-ups

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  export POTIONS_RUN_LEDGER=data/validation/broker_run_ledger.csv
  python -m live.nas100_clean_break_ha_conditions --email
  python -m live.nas100_clean_break_ha_conditions --email --smoke
  python -m live.nas100_clean_break_ha_conditions --email --profile-only
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import traceback
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .fx_v2b_london_ungated import REPO
from .intraday_condition_overlay import (
    CAUSAL_LIVE_READY,
    NEEDS_LIVE_PROXY,
    apply_policy,
    hp_mask,
    score_nets,
)
from .intraday_condition_profile import (
    annotate_campaigns,
    build_feature_frames,
    profile_book,
)
from .notify_email import send_email
from .run_ledger import begin_run, complete_run, fail_run

HUB = REPO / "live" / "state" / "nas100_clean_break_ha_conditions"
PROFILE_HUB = HUB / "profile"
OVERLAY_HUB = HUB / "overlay"
NULLS_HUB = HUB / "nulls"
NY = "America/New_York"
MIN_N_DEFAULT = 40  # ~1166 campaigns — intraday-style floor
DSR = "TRL-2026-00198"
DSR_LEDGER = REPO / "data" / "validation" / "dsr_trial_ledger_parallel.csv"
SOURCE_HUB = (
    REPO
    / "live"
    / "state"
    / "nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill_validation"
)
SOURCE_UNIT_TRADES = (
    SOURCE_HUB / "states" / "nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill" / "unit_trades.csv"
)
BASELINE_NOTE = (
    "NAS100 clean-break trail06_m4_e2_out_be 1m-fill unit book "
    "(~$+12.3k / N/S 6.23 / 1166; live/public default = ×10)"
)


@dataclass(frozen=True)
class CbBook:
    key: str
    label: str
    symbol: str
    unit_trades: Path


BOOK = CbBook(
    "nas100_v2b_clean_break_trail06",
    "NAS100 clean-break trail06_m4_e2_out_be (1m-fill unit)",
    "NAS100",
    SOURCE_UNIT_TRADES,
)


def _progress(msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _append_dsr_parallel() -> None:
    DSR_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    if DSR_LEDGER.exists() and DSR in DSR_LEDGER.read_text(encoding="utf-8"):
        return
    if not DSR_LEDGER.exists():
        header = (
            "trial_id,entry_date,analyst,trial_class,trial_subclass,parent_trial_id,"
            "is_independent,market,replay_window_start,replay_window_end,replay_type,"
            "is_oos,training_window_start,training_window_end,parameters_json,"
            "fixed_parameters_ref,num_params_varied,sharpe_ratio,sortino_ratio,cagr_pct,"
            "calmar_ratio,max_drawdown_pct,trade_count,pf,net_pnl,qqq_correlation,"
            "qqq_downside_capture,counts_toward_dsr,counts_toward_permutation_test,"
            "dsr_weight,dsr_exclusion_reason,status,superseded_by,run_hash,notes,"
            "disclosure_review\n"
        )
        DSR_LEDGER.write_text(
            "# PARALLEL_WHILE_PRIMARY_WIPED\n" + header, encoding="utf-8"
        )
    with DSR_LEDGER.open("r", encoding="utf-8") as rh:
        lines = [ln for ln in rh if ln.strip() and not ln.lstrip().startswith("#")]
    reader = csv.DictReader(io.StringIO("".join(lines)))
    fieldnames = list(reader.fieldnames or [])
    row = {k: "" for k in fieldnames}
    updates = {
        "trial_id": DSR,
        "entry_date": date.today().isoformat(),
        "analyst": "cursor",
        "trial_class": "FILTER_EXPLORATION",
        "trial_subclass": "nas100_clean_break_ha",
        "is_independent": "TRUE",
        "market": "NAS100",
        "replay_window_start": "2016-11-15",
        "replay_window_end": "2025-12-31",
        "replay_type": "FULL_HISTORY",
        "is_oos": "FALSE",
        "parameters_json": json.dumps(
            {
                "variant": "trail06_m4_e2_out_be",
                "pipeline": "ha_profile_overlay_nulls",
                "size_mults": [1.25, 1.5],
                "null_extra": 0.25,
                "source_hub": str(SOURCE_HUB.relative_to(REPO)),
            },
            sort_keys=True,
        ),
        "fixed_parameters_ref": str(HUB.relative_to(REPO)),
        "num_params_varied": "0",
        "trade_count": "1166",
        "net_pnl": "12253",
        "counts_toward_dsr": "TRUE",
        "counts_toward_permutation_test": "FALSE",
        "dsr_weight": "1.00",
        "status": "RUNNING",
        "notes": (
            "Full HA mill (profile+overlay+1.25× nulls) on clean-break 1m-fill; "
            "organic notables (same bar as weekly OD / FBO)"
        ),
        "disclosure_review": "FALSE",
    }
    for k, v in updates.items():
        if k in row:
            row[k] = v
    with DSR_LEDGER.open("a", encoding="utf-8", newline="") as fh:
        csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore").writerow(row)
    _progress("DSR %s appended → %s" % (DSR, DSR_LEDGER.relative_to(REPO)))


def _complete_dsr_parallel(*, notes: str, status: str = "COMPLETE") -> None:
    if not DSR_LEDGER.exists():
        return
    raw = DSR_LEDGER.read_text(encoding="utf-8")
    comment_lines = [ln for ln in raw.splitlines(True) if ln.lstrip().startswith("#")]
    data_text = "".join(
        ln for ln in raw.splitlines(True) if ln.strip() and not ln.lstrip().startswith("#")
    )
    reader = csv.DictReader(io.StringIO(data_text))
    fieldnames = list(reader.fieldnames or [])
    rows = list(reader)
    for r in rows:
        if r.get("trial_id") == DSR:
            r["status"] = status
            r["notes"] = notes[:500]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    DSR_LEDGER.write_text("".join(comment_lines) + buf.getvalue(), encoding="utf-8")


def load_campaigns(book: CbBook) -> pd.DataFrame:
    """Campaign tape = unit_trades rolled up by trade_id (pyramid-safe)."""
    if not book.unit_trades.exists():
        raise SystemExit("Missing unit_trades: %s" % book.unit_trades)
    ut = pd.read_csv(book.unit_trades)
    if ut.empty:
        return pd.DataFrame()
    ut["entry_ts"] = pd.to_datetime(ut["entry_ts"], utc=True).dt.tz_convert(NY)
    ut["exit_ts"] = pd.to_datetime(ut["exit_ts"], utc=True).dt.tz_convert(NY)
    ut["net_usd"] = pd.to_numeric(ut["net_usd"], errors="coerce")
    ut["entry_price"] = pd.to_numeric(ut["entry_price"], errors="coerce")
    rows = []
    for trade_id, g in ut.sort_values("entry_ts").groupby("trade_id", sort=False):
        first = g.iloc[0]
        side_raw = str(first["direction"]).strip().lower()
        side = "long" if side_raw.startswith("long") else "short"
        rows.append(
            {
                "book": book.key,
                "family": "v2b_clean_break",
                "symbol": book.symbol,
                "trade_id": str(trade_id),
                "side": side,
                "entry_ts": pd.Timestamp(g["entry_ts"].min()),
                "exit_ts": pd.Timestamp(g["exit_ts"].max()),
                "entry_price": float(first["entry_price"]),
                "net_usd": float(g["net_usd"].sum()),
                "n_units": int(len(g)),
            }
        )
    out = pd.DataFrame(rows).sort_values("entry_ts").reset_index(drop=True)
    if out.empty:
        return out
    out["win"] = out["net_usd"] > 0
    out["dow"] = out["entry_ts"].dt.day_name()
    out["hour_ny"] = out["entry_ts"].dt.hour
    out["month"] = out["entry_ts"].dt.month
    out["month_name"] = out["entry_ts"].dt.month_name()
    out["year"] = out["entry_ts"].dt.year
    out["week_of_month"] = ((out["entry_ts"].dt.day - 1) // 7 + 1).astype(int)
    return out


def _baseline_metrics() -> Dict[str, float]:
    path = PROFILE_HUB / "baselines.json"
    if not path.exists():
        return {}
    blob = json.loads(path.read_text(encoding="utf-8"))
    b = blob.get(BOOK.key) or {}
    return {
        "trades": float(b.get("n") or 0),
        "net_usd": float(b.get("net") or 0.0),
        "ns": float(b.get("ns") or 0.0) if "ns" in b else None,
        "stress": float(b.get("stress") or 0.0) if "stress" in b else None,
    }


def _month_bucket_table(ann: pd.DataFrame) -> pd.DataFrame:
    """Calendar-month stats appendix (diagnostic board, not a forced null set)."""
    if ann.empty or "month_name" not in ann.columns:
        return pd.DataFrame()
    base_avg = float(ann["net_usd"].mean())
    base_wr = float((ann["net_usd"] > 0).mean())
    rows = []
    for name, g in ann.groupby("month_name", sort=False):
        n = len(g)
        wr = float((g["net_usd"] > 0).mean())
        avg = float(g["net_usd"].mean())
        net = float(g["net_usd"].sum())
        years = g["year"].nunique() if "year" in g.columns else 0
        yr_pos = 0
        if "year" in g.columns and years:
            yr_nets = g.groupby("year")["net_usd"].sum()
            yr_pos = int((yr_nets > 0).sum())
        rows.append(
            {
                "month": str(name),
                "n": n,
                "wr": wr,
                "wr_lift_pp": 100.0 * (wr - base_wr),
                "avg": avg,
                "avg_lift": avg - base_avg,
                "net": net,
                "years": years,
                "years_green": yr_pos,
            }
        )
    order = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    out = pd.DataFrame(rows)
    out["_ord"] = out["month"].map({m: i for i, m in enumerate(order)})
    return out.sort_values("_ord").drop(columns=["_ord"]).reset_index(drop=True)


def run_profile(*, min_n: int, email: bool = False) -> pd.DataFrame:
    PROFILE_HUB.mkdir(parents=True, exist_ok=True)
    book = BOOK
    _progress("PROFILE %s ..." % book.key)
    if not book.unit_trades.exists():
        raise SystemExit("Missing unit_trades: %s" % book.unit_trades)
    camp = load_campaigns(book)
    _progress("  campaigns=%d net_usd≈$%.0f" % (len(camp), float(camp["net_usd"].sum())))
    if camp.empty:
        raise SystemExit("No campaigns from unit_trades")

    _progress("  building features for %s ..." % book.symbol)
    feats = build_feature_frames(book.symbol)
    ann = annotate_campaigns(camp, feats)
    if "month_name" not in ann.columns:
        ann["month_name"] = pd.to_datetime(ann["entry_ts"]).dt.month_name()
    ann.to_csv(PROFILE_HUB / ("%s_campaigns.csv" % book.key), index=False)
    ann.to_csv(PROFILE_HUB / "all_campaigns.csv", index=False)

    table, baseline, book_notables = profile_book(ann, min_n=min_n)
    nets = ann["net_usd"].to_numpy(dtype=float)
    sc = score_nets(nets, label="baseline")
    baseline = dict(baseline)
    baseline["ns"] = sc["ns"]
    baseline["stress"] = sc["stress"]
    baseline["book"] = book.key
    table.to_csv(PROFILE_HUB / ("%s_buckets.csv" % book.key), index=False)
    month_tbl = _month_bucket_table(ann)
    month_tbl.to_csv(PROFILE_HUB / "entry_month_buckets.csv", index=False)

    notables_df = pd.DataFrame(book_notables)
    if not notables_df.empty:
        notables_df = notables_df.sort_values(
            ["avg_lift", "wr_lift_pp"], ascending=False
        ).reset_index(drop=True)
    notables_df.to_csv(PROFILE_HUB / "notables.csv", index=False)
    (PROFILE_HUB / "baselines.json").write_text(
        json.dumps({book.key: baseline}, indent=2) + "\n", encoding="utf-8"
    )
    _progress(
        "  baseline n=%d WR=%.0f%% net=$%.0f N/S=%.2f notables=%d"
        % (
            int(baseline["n"]),
            100.0 * baseline["wr"],
            baseline["net"],
            float(baseline["ns"]),
            len(book_notables),
        )
    )

    lines = [
        "# NAS100 clean-break — HA condition profile",
        "",
        "High-probability condition study on **Engine+PaperBroker 1m-fill** tape",
        "(%s)." % BASELINE_NOTE,
        "Features: DOW / week-of-month / Entry month / hour / 5m MA /",
        "hourly RSI+OBV / ATR quartile / prior range-half.",
        "Diagnostic — not a promotion gate.",
        "",
        "min_n=%d." % min_n,
        "",
        "## Book",
        "",
        "- **%s**: n=%d WR=%.1f%% avg=$%.0f net=$%.0f N/S=%.2f"
        % (
            book.label,
            int(baseline["n"]),
            100.0 * baseline["wr"],
            baseline["avg_net"],
            baseline["net"],
            float(baseline["ns"]),
        ),
        "",
        "## Notables (positive WR + avg lift)",
        "",
    ]
    if notables_df.empty:
        lines.append("_None cleared the heuristic._")
    else:
        lines.append("| condition | bucket | n | WR | WRΔpp | avg | avgΔ | z_WR |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
        for _, r in notables_df.head(40).iterrows():
            lines.append(
                "| %s | %s | %d | %.0f%% | %+.1f | $%.0f | $%+.0f | %.2f |"
                % (
                    r["condition"],
                    r["bucket"],
                    int(r["n"]),
                    100.0 * float(r["wr"]),
                    float(r["wr_lift_pp"]),
                    float(r["avg_net"]),
                    float(r["avg_lift"]),
                    float(r["z_wr"]),
                )
            )
    lines += [
        "",
        "## Entry month board (appendix)",
        "",
        "| month | n | WR | WRΔpp | avg | avgΔ | net | years green |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in month_tbl.iterrows():
        lines.append(
            "| %s | %d | %.0f%% | %+.1f | $%.0f | $%+.0f | $%+.0f | %d/%d |"
            % (
                r["month"],
                int(r["n"]),
                100.0 * float(r["wr"]),
                float(r["wr_lift_pp"]),
                float(r["avg"]),
                float(r["avg_lift"]),
                float(r["net"]),
                int(r["years_green"]),
                int(r["years"]),
            )
        )
    lines += ["", "Hub: `%s`" % PROFILE_HUB, ""]
    (PROFILE_HUB / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")

    email_body = [
        "potions: NAS100 clean-break HA profile complete",
        "",
        "Hub: %s" % PROFILE_HUB,
        "Book: %s" % book.key,
        "campaigns: %d  notables: %d" % (len(ann), len(notables_df)),
        "baseline net=$%.0f N/S=%.2f" % (baseline["net"], float(baseline["ns"])),
        "DSR: %s" % DSR,
        "",
        "Top notables:",
    ]
    if notables_df.empty:
        email_body.append("  (none)")
    else:
        for _, r in notables_df.head(12).iterrows():
            email_body.append(
                "  %s=%s | n=%d WR=%.0f%% avg=$%+.0f z=%.2f"
                % (
                    r["condition"],
                    r["bucket"],
                    int(r["n"]),
                    100.0 * float(r["wr"]),
                    float(r["avg_lift"]),
                    float(r["z_wr"]),
                )
            )
    email_txt = "\n".join(email_body) + "\n"
    (PROFILE_HUB / "EMAIL.txt").write_text(email_txt, encoding="utf-8")
    if email:
        send_email(
            subject="potions: NAS100 clean-break HA profile complete", body=email_txt
        )
        _progress("profile email sent")
    return notables_df


def _select_hits(notables: pd.DataFrame, *, min_n: int, top: int = 12) -> pd.DataFrame:
    if notables.empty:
        return notables
    df = notables[notables["n"] >= min_n].copy()
    return df.head(top).reset_index(drop=True)


def run_overlay(*, email: bool = False, min_n: int = MIN_N_DEFAULT) -> pd.DataFrame:
    OVERLAY_HUB.mkdir(parents=True, exist_ok=True)
    campaigns = pd.read_csv(PROFILE_HUB / "all_campaigns.csv")
    campaigns["entry_ts"] = pd.to_datetime(campaigns["entry_ts"], utc=True)
    if "month_name" not in campaigns.columns:
        campaigns["month_name"] = campaigns["entry_ts"].dt.month_name()
    notables = (
        pd.read_csv(PROFILE_HUB / "notables.csv")
        if (PROFILE_HUB / "notables.csv").exists()
        else pd.DataFrame()
    )
    hits = _select_hits(notables, min_n=min_n)
    hits.to_csv(OVERLAY_HUB / "candidates.csv", index=False)

    policies: List[Tuple[str, float]] = [
        ("baseline", 1.0),
        ("filter", 0.0),
        ("size_1.25", 1.25),
        ("size_1.5", 1.5),
    ]
    rows: List[dict] = []
    book_key = BOOK.key
    for _, hit in hits.iterrows():
        cond = str(hit["condition"])
        bucket = str(hit["bucket"])
        causal = (
            "live_ready"
            if cond in CAUSAL_LIVE_READY
            else ("needs_rolling_proxy" if cond in NEEDS_LIVE_PROXY else "unknown")
        )
        split_full = campaigns[campaigns["book"] == book_key]
        for split_name, split_df in (
            ("full", split_full),
            ("oos", split_full.iloc[int(0.6 * len(split_full)) :]),
        ):
            if split_df.empty:
                continue
            base = score_nets(split_df["net_usd"].to_numpy(dtype=float), label="baseline")
            mask = hp_mask(split_df, cond, bucket)
            for policy, mult in policies:
                if policy == "baseline":
                    nets = split_df["net_usd"].to_numpy(dtype=float)
                else:
                    nets = apply_policy(
                        split_df,
                        mask,
                        policy=policy,
                        size_mult=float(mult),
                    )
                sc = score_nets(nets, label=policy)
                rows.append(
                    {
                        "book": book_key,
                        "condition": cond,
                        "bucket": bucket,
                        "causal": causal,
                        "split": split_name,
                        "policy": policy,
                        "size_mult": float(mult)
                        if policy.startswith("size_")
                        else (0.0 if policy == "filter" else 1.0),
                        "hp_n": int(mask.sum()),
                        "hp_frac": float(mask.mean()) if len(mask) else 0.0,
                        "base_n": base["n"],
                        "base_net": base["net"],
                        "base_ns": base["ns"],
                        "base_stress": base["stress"],
                        "n": sc["n"],
                        "net": sc["net"],
                        "avg": sc["avg"],
                        "wr": sc["wr"],
                        "pf": sc["pf"],
                        "stress": sc["stress"],
                        "ns": sc["ns"],
                        "delta_net": sc["net"] - base["net"],
                        "delta_ns": sc["ns"] - base["ns"],
                    }
                )

    results = pd.DataFrame(rows)
    results.to_csv(OVERLAY_HUB / "overlay_results.csv", index=False)
    full = results[(results["split"] == "full") & (results["policy"] != "baseline")].copy()
    if not full.empty:
        full = full.sort_values(["delta_ns", "delta_net"], ascending=False)
        full.to_csv(OVERLAY_HUB / "ranked_full.csv", index=False)

    lines = [
        "# NAS100 clean-break — HA overlays",
        "",
        "Filter / 1.25× / 1.5× on profile notables vs baseline unit tape.",
        "",
        "## Full-tape ranked by ΔN/S",
        "",
        "| condition | bucket | policy | hp% | Δnet | ΔN/S | net | N/S | causal |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    if full.empty:
        lines.append("| — | — | — | — | — | — | — | — | — |")
    else:
        for _, r in full.head(40).iterrows():
            lines.append(
                "| %s | %s | %s | %.0f%% | $%+.0f | %+.2f | $%.0f | %.2f | %s |"
                % (
                    r["condition"],
                    r["bucket"],
                    r["policy"],
                    100.0 * float(r["hp_frac"]),
                    float(r["delta_net"]),
                    float(r["delta_ns"]),
                    float(r["net"]),
                    float(r["ns"]),
                    r["causal"],
                )
            )
    lines += ["", "Hub: `%s`" % OVERLAY_HUB, ""]
    (OVERLAY_HUB / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")

    email_body = [
        "potions: NAS100 clean-break HA overlay complete",
        "",
        "Hub: %s" % OVERLAY_HUB,
        "Candidates: %d" % len(hits),
        "",
        "Top full-tape by ΔN/S:",
    ]
    if not full.empty:
        for _, r in full.head(12).iterrows():
            email_body.append(
                "  %s=%s | %s | hp=%.0f%% ΔN/S=%+.2f Δnet=$%+.0f"
                % (
                    r["condition"],
                    r["bucket"],
                    r["policy"],
                    100.0 * float(r["hp_frac"]),
                    float(r["delta_ns"]),
                    float(r["delta_net"]),
                )
            )
    else:
        email_body.append("  (no overlay rows)")
    email_txt = "\n".join(email_body) + "\n"
    (OVERLAY_HUB / "EMAIL.txt").write_text(email_txt, encoding="utf-8")
    if email:
        send_email(
            subject="potions: NAS100 clean-break HA overlay complete", body=email_txt
        )
        _progress("overlay email sent")
    return results


def run_nulls(*, email: bool = False, smoke: bool = False) -> pd.DataFrame:
    NULLS_HUB.mkdir(parents=True, exist_ok=True)
    campaigns = pd.read_csv(PROFILE_HUB / "all_campaigns.csv")
    campaigns["entry_ts"] = pd.to_datetime(campaigns["entry_ts"], utc=True)
    if "month_name" not in campaigns.columns:
        campaigns["month_name"] = campaigns["entry_ts"].dt.month_name()
    notables = (
        pd.read_csv(PROFILE_HUB / "notables.csv")
        if (PROFILE_HUB / "notables.csv").exists()
        else pd.DataFrame()
    )
    ranked = (
        pd.read_csv(OVERLAY_HUB / "ranked_full.csv")
        if (OVERLAY_HUB / "ranked_full.csv").exists()
        else pd.DataFrame()
    )

    pairs: List[Tuple[str, str, str]] = []
    if not ranked.empty:
        size = ranked[
            ranked["policy"].astype(str).str.startswith("size_")
            & (ranked["delta_ns"] > 0)
            & (ranked["hp_frac"] < 0.40)
            & (ranked["base_n"] >= 40)
            & (ranked["causal"] == "live_ready")
        ].copy()
        size = size.sort_values(["delta_ns", "delta_net"], ascending=False)
        seen = set()
        for _, r in size.iterrows():
            key = (str(r["book"]), str(r["condition"]), str(r["bucket"]))
            if key in seen:
                continue
            seen.add(key)
            pairs.append(key)
            if len(pairs) >= (2 if smoke else 8):
                break

    if not pairs and not notables.empty:
        for _, r in notables.sort_values("avg_lift", ascending=False).iterrows():
            pairs.append((BOOK.key, str(r["condition"]), str(r["bucket"])))
            if len(pairs) >= (2 if smoke else 4):
                break

    if not pairs:
        msg = "No pairs eligible for nulls (need size ΔN/S>0 + coverage)."
        _progress(msg)
        (NULLS_HUB / "SUMMARY.md").write_text(
            "# NAS100 clean-break HA nulls\n\n%s\n" % msg, encoding="utf-8"
        )
        (NULLS_HUB / "EMAIL.txt").write_text(
            "potions: NAS100 clean-break HA nulls skipped\n\nHub: %s\n%s\n"
            % (NULLS_HUB, msg),
            encoding="utf-8",
        )
        if email:
            send_email(
                subject="potions: NAS100 clean-break HA nulls skipped",
                body=(NULLS_HUB / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        return pd.DataFrame()

    n_placebo = 400 if smoke else 2000
    n_shift = 200 if smoke else 800
    n_master = 100 if smoke else 400
    n_wf = 100 if smoke else 400

    from .intraday_condition_overlay import select_cross_book_hits, select_single_book_hits
    import live.intraday_hp_sizeup_nulls as nulls_mod

    nulls_mod.HUB = NULLS_HUB
    singles = select_single_book_hits(notables, min_z=0.5, min_n=MIN_N_DEFAULT, top_per_book=10)
    crosses = select_cross_book_hits(notables, min_books=2)

    results = []
    for i, (book, cond, bucket) in enumerate(pairs):
        _progress("NULLS %s | %s=%s @ 1.25× ..." % (book, cond, bucket))
        try:
            res = nulls_mod.evaluate_pair(
                campaigns,
                notables,
                singles,
                crosses,
                book=book,
                condition=cond,
                bucket=bucket,
                extra=0.25,
                n_placebo=n_placebo,
                n_shift=n_shift,
                n_master=n_master,
                n_wf_placebo=n_wf,
                seed=20260913 + i * 17,
            )
            results.append(res)
            _progress(
                "  decision=%s ΔN/S=%+.3f p_master=%.3f"
                % (
                    res.get("decision"),
                    float(res.get("delta_ns") or res.get("sleeve_delta_ns") or 0.0),
                    float(res.get("p_master_delta_ns") or res.get("p_master") or float("nan")),
                )
            )
        except Exception:
            _progress("  CRASH pair\n" + traceback.format_exc()[-1500:])

    out = pd.DataFrame(results)
    if not out.empty:
        out.to_csv(NULLS_HUB / "pair_decisions.csv", index=False)

    lines = [
        "# NAS100 clean-break — HA matched nulls",
        "",
        "1.25× matched-added-exposure on top size-up candidates from the overlay",
        "(organic notables — same selection bar as weekly OD / FBO HA mills).",
        "",
        "| decision | condition=bucket | hp% | ΔN/S | p_plac | p_shift | p_master |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    if out.empty:
        lines.append("| — | — | — | — | — | — | — |")
    else:
        for _, r in out.iterrows():
            lines.append(
                "| %s | %s=%s | %.0f%% | %+.2f | %.3f | %.3f | %.3f |"
                % (
                    r.get("decision", ""),
                    r.get("condition", ""),
                    r.get("bucket", ""),
                    100.0 * float(r.get("boost_frac") or r.get("hp_frac") or 0.0),
                    float(r.get("sleeve_delta_ns") or r.get("delta_ns") or 0.0),
                    float(r.get("p_placebo_delta_ns") or r.get("p_placebo") or float("nan")),
                    float(r.get("p_shift_delta_ns") or r.get("p_shift") or float("nan")),
                    float(r.get("p_master_delta_ns") or r.get("p_master") or float("nan")),
                )
            )
    lines += ["", "Hub: `%s`" % NULLS_HUB, ""]
    (NULLS_HUB / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")

    email_body = "potions: NAS100 clean-break HA nulls complete\n\nHub: %s\nPairs: %d\n\n" % (
        NULLS_HUB,
        len(results),
    )
    for r in results:
        email_body += "  %s=%s | %s | ΔN/S=%+.2f hp=%.0f%%\n" % (
            r.get("condition"),
            r.get("bucket"),
            r.get("decision"),
            float(r.get("sleeve_delta_ns") or r.get("delta_ns") or 0.0),
            100.0 * float(r.get("boost_frac") or r.get("hp_frac") or 0.0),
        )
    (NULLS_HUB / "EMAIL.txt").write_text(email_body, encoding="utf-8")
    if email:
        send_email(subject="potions: NAS100 clean-break HA nulls complete", body=email_body)
        _progress("nulls email sent")
    return out


def write_root_summary() -> None:
    parts = [
        "# NAS100 clean-break — HA mill",
        "",
        "Source: `%s` (%s)."
        % (SOURCE_HUB.relative_to(REPO), BASELINE_NOTE),
        "",
        "Pipeline: profile → filter/1.25×/1.5× overlay → 1.25× matched nulls",
        "(same bar as weekly OD / FBO / CHOP20).",
        "DSR: %s (parallel ledger while primary wipe pending)." % DSR,
        "",
    ]
    for name, path in (
        ("Profile", PROFILE_HUB / "SUMMARY.md"),
        ("Overlay", OVERLAY_HUB / "SUMMARY.md"),
        ("Nulls", NULLS_HUB / "SUMMARY.md"),
    ):
        parts.append("## %s\n" % name)
        if path.exists():
            parts.append(path.read_text(encoding="utf-8"))
        else:
            parts.append("_(not run)_\n")
        parts.append("")
    (HUB / "SUMMARY.md").write_text("\n".join(parts), encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--profile-only", action="store_true")
    ap.add_argument("--overlay-only", action="store_true")
    ap.add_argument("--nulls-only", action="store_true")
    ap.add_argument("--min-n", type=int, default=MIN_N_DEFAULT)
    args = ap.parse_args(list(argv) if argv is not None else None)

    HUB.mkdir(parents=True, exist_ok=True)
    (HUB / "PROGRESS.log").write_text("", encoding="utf-8")
    _progress("START NAS100 clean-break HA mill (full organic)")
    _append_dsr_parallel()

    rid = begin_run(
        run_class="ha",
        variant_slug="nas100_clean_break_ha",
        instrument="NAS100",
        hub_path=str(HUB.relative_to(REPO)),
        dsr_trial_id=DSR,
        notes="Full HA mill profile+overlay+1.25× nulls (organic notables)",
        meta={
            "source": "nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill",
            "pipeline": "profile+overlay+nulls",
            "null_extra": 0.25,
        },
    )

    try:
        if not args.overlay_only and not args.nulls_only:
            run_profile(min_n=args.min_n, email=False)
        if args.profile_only:
            write_root_summary()
            if args.email:
                send_email(
                    subject="potions: NAS100 clean-break HA profile-only complete",
                    body=(PROFILE_HUB / "EMAIL.txt").read_text(encoding="utf-8"),
                )
            bm = _baseline_metrics()
            complete_run(
                rid,
                hub_path=str(HUB.relative_to(REPO)),
                notes="HA profile-only",
                meta={"source": BOOK.key, "pipeline": "profile"},
                net_usd=bm.get("net_usd"),
                ns=bm.get("ns"),
                stress_dd_usd=bm.get("stress"),
                trades=int(bm["trades"]) if bm.get("trades") else None,
            )
            _complete_dsr_parallel(notes="HA profile-only complete")
            _progress("DONE profile-only")
            return 0
        if not args.nulls_only:
            run_overlay(email=False, min_n=args.min_n)
        if not args.overlay_only:
            run_nulls(email=False, smoke=args.smoke)
        write_root_summary()

        decisions = []
        dec_path = NULLS_HUB / "pair_decisions.csv"
        if dec_path.exists():
            ddf = pd.read_csv(dec_path)
            if not ddf.empty and "decision" in ddf.columns:
                decisions = ddf["decision"].astype(str).tolist()

        stance = "diagnostic HA — promote size-up only if nulls VALIDATED / PROVISIONAL"
        if decisions:
            if any(d == "SIZE-UP VALIDATED" for d in decisions):
                stance = "SIZE-UP interest — see nulls VALIDATED rows (still research)"
            elif any("PROVISIONAL" in d or "BORDERLINE" in d for d in decisions):
                stance = "PROVISIONAL only — controlled paper candidate at most"
            elif any("THROTTLE" in d for d in decisions):
                stance = "RISK THROTTLE / NOT VALIDATED — shadow only; no size-up promote"
            elif all(d == "NOT VALIDATED" for d in decisions):
                stance = "NOT VALIDATED — no size-up promote"

        body_parts = [
            "potions: NAS100 clean-break HA mill complete (full organic)",
            "",
            "Hub: %s" % HUB.resolve(),
            "Book: %s" % BASELINE_NOTE,
            "DSR: %s" % DSR,
            "Stance: %s" % stance,
            "",
            "Pipeline: profile → filter/1.25×/1.5× overlay → 1.25× nulls",
            "(organic notables; same bar as weekly OD / FBO).",
            "",
        ]
        for label, p in (
            ("PROFILE", PROFILE_HUB / "EMAIL.txt"),
            ("OVERLAY", OVERLAY_HUB / "EMAIL.txt"),
            ("NULLS", NULLS_HUB / "EMAIL.txt"),
        ):
            body_parts.append("=== %s ===" % label)
            if p.exists():
                body_parts.append(p.read_text(encoding="utf-8").strip())
            else:
                body_parts.append("(missing)")
            body_parts.append("")
        body = "\n".join(body_parts) + "\n"
        (HUB / "EMAIL.txt").write_text(body, encoding="utf-8")
        (HUB / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "hub": str(HUB),
                    "dsr": DSR,
                    "decisions": decisions,
                    "stance": stance,
                    "pipeline": "full_organic_ha",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        bm = _baseline_metrics()
        complete_run(
            rid,
            hub_path=str(HUB.relative_to(REPO)),
            notes="Full HA mill profile+overlay+1.25× nulls (organic)",
            meta={
                "source": BOOK.key,
                "pipeline": "profile+overlay+nulls",
                "null_decisions": decisions,
                "stance": stance,
            },
            net_usd=bm.get("net_usd"),
            ns=bm.get("ns"),
            stress_dd_usd=bm.get("stress"),
            trades=int(bm["trades"]) if bm.get("trades") else None,
        )
        _complete_dsr_parallel(
            notes="Full HA mill done; decisions=%s; %s"
            % (",".join(decisions) or "none", stance)
        )
        if args.email:
            send_email(
                subject="potions: NAS100 clean-break HA mill complete (full)",
                body=body,
            )
            _progress("consolidated email sent")
        _progress("DONE")
        return 0
    except Exception:
        err = traceback.format_exc()
        _progress("CRASH\n%s" % err)
        (HUB / "EMAIL.txt").write_text(
            "potions: NAS100 clean-break HA mill FAILED\n\nHub: %s\n\n%s\n" % (HUB, err),
            encoding="utf-8",
        )
        fail_run(rid, notes="HA mill crashed", meta={"error": err[-2000:]})
        _complete_dsr_parallel(notes="HA mill CRASH", status="FAILED")
        if args.email:
            send_email(
                subject="potions: NAS100 clean-break HA mill FAILED",
                body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
