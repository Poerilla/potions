"""HA (high-probability conditions) mill for CHOP20 boundary60 1m path books.

Source: ``live/state/chop20_dynamic_range_1m_boundary60_xmarket/{nq,ym,mym,mnq}/trades.csv``

Pipeline:
  1. Condition profile (entry-asof DOW / WoM / hour / RSI / OBV / ATR / range-half)
  2. Filter / 1.25× / 1.5× overlays on notables
  3. Matched-added-exposure nulls when N allows

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.chop20_dynamic_range_ha_conditions --email
  python -m live.chop20_dynamic_range_ha_conditions --email --smoke
  python -m live.chop20_dynamic_range_ha_conditions --email --profile-only
"""

from __future__ import annotations

import argparse
import csv
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
    CACHE,
    NY,
    annotate_campaigns,
    build_feature_frames,
    profile_book,
)
from .notify_email import send_email
from .run_ledger import begin_run, complete_run, fail_run

HUB = REPO / "live" / "state" / "chop20_dynamic_range_ha_conditions"
PROFILE_HUB = HUB / "profile"
OVERLAY_HUB = HUB / "overlay"
NULLS_HUB = HUB / "nulls"
SOURCE = REPO / "live" / "state" / "chop20_dynamic_range_1m_boundary60_xmarket"
DSR = "TRL-2026-00178"
MIN_N_DEFAULT = 8  # ~70 NQ campaigns — thin vs intraday mills
DAILY_CSV = {
    "NQ": REPO / "nq" / "nq_daily.csv",
    "YM": REPO / "ym" / "ym_daily.csv",
    "MYM": REPO / "mym" / "mym_daily.csv",
    "MNQ": REPO / "mnq" / "mnq_daily.csv",
}


@dataclass(frozen=True)
class ChopBook:
    key: str
    label: str
    symbol: str
    trades: Path


BOOKS: Tuple[ChopBook, ...] = (
    ChopBook("nq_chop20_boundary60_1m", "NQ CHOP20 boundary60 1m", "NQ", SOURCE / "nq" / "trades.csv"),
    ChopBook("ym_chop20_boundary60_1m", "YM CHOP20 boundary60 1m", "YM", SOURCE / "ym" / "trades.csv"),
    ChopBook("mym_chop20_boundary60_1m", "MYM CHOP20 boundary60 1m", "MYM", SOURCE / "mym" / "trades.csv"),
    ChopBook("mnq_chop20_boundary60_1m", "MNQ CHOP20 boundary60 1m", "MNQ", SOURCE / "mnq" / "trades.csv"),
)


def _progress(msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _append_dsr() -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    lines = path.read_text().splitlines()
    if any(ln.startswith(DSR + ",") for ln in lines):
        return
    header = next(ln for ln in lines if ln.startswith("trial_id,"))
    fields = header.split(",")
    row = {k: "" for k in fields}
    row.update(
        {
            "trial_id": DSR,
            "entry_date": date.today().isoformat(),
            "analyst": "cursor",
            "trial_class": "FILTER_EXPLORATION",
            "trial_subclass": "chop20_boundary60_ha",
            "is_independent": "TRUE",
            "market": "NQ,YM,MYM,MNQ",
            "replay_type": "FULL_HISTORY",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {
                    "pipeline": "ha_profile_overlay_nulls",
                    "source": str(SOURCE.relative_to(REPO)),
                    "variant": "touch_broken_boundary_max_age_60",
                }
            ),
            "fixed_parameters_ref": "live/chop20_dynamic_range_ha_conditions.py",
            "num_params_varied": "0",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "1.00",
            "status": "PENDING",
            "notes": "HA mill on CHOP20 boundary60 1m campaign tapes",
            "disclosure_review": "FALSE",
        }
    )
    with path.open("a", newline="") as fh:
        csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore").writerow(row)


def _mark_dsr(status: str, notes: str = "") -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    out = []
    for ln in path.read_text().splitlines():
        if ln.startswith(DSR + ",") and ",PENDING," in ln:
            ln = ln.replace(",PENDING,", ",%s," % status, 1)
            if notes:
                # leave notes column as-is if already set; status flip is enough
                pass
        out.append(ln)
    path.write_text("\n".join(out) + "\n")


def _seed_daily_cache(symbol: str) -> None:
    """Ensure _cache/bars/{sym}_1d.parquet exists for build_feature_frames."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE / ("%s_1d.parquet" % symbol.lower())
    if cache_path.exists():
        return
    csv_path = DAILY_CSV.get(symbol.upper())
    if csv_path is None or not csv_path.exists():
        return
    df = pd.read_csv(csv_path)
    col = "date" if "date" in df.columns else "ts"
    df["ts"] = pd.to_datetime(df[col], utc=False)
    if df["ts"].dt.tz is None:
        df["ts"] = df["ts"].dt.tz_localize(NY, ambiguous="infer", nonexistent="shift_forward")
    else:
        df["ts"] = df["ts"].dt.tz_convert(NY)
    out = pd.DataFrame(
        {
            "ts": df["ts"],
            "open": pd.to_numeric(df["open"], errors="coerce"),
            "high": pd.to_numeric(df["high"], errors="coerce"),
            "low": pd.to_numeric(df["low"], errors="coerce"),
            "close": pd.to_numeric(df["close"], errors="coerce"),
            "volume": pd.to_numeric(df.get("volume", 0), errors="coerce").fillna(0.0),
        }
    ).dropna(subset=["ts", "close"])
    out.to_parquet(cache_path, index=False)
    _progress("seeded %s (%d rows)" % (cache_path.name, len(out)))


def load_campaigns(book: ChopBook) -> pd.DataFrame:
    if not book.trades.exists():
        return pd.DataFrame()
    t = pd.read_csv(book.trades)
    if t.empty:
        return t
    t["entry_ts"] = pd.to_datetime(t["entry_ts"], utc=True).dt.tz_convert(NY)
    t["exit_ts"] = pd.to_datetime(t["exit_ts"], utc=True).dt.tz_convert(NY)
    rows = []
    for _, r in t.iterrows():
        rows.append(
            {
                "book": book.key,
                "family": "chop20_dynamic_range",
                "symbol": book.symbol,
                "trade_id": str(r["trade_id"]),
                "side": str(r["direction"]),
                "entry_ts": pd.Timestamp(r["entry_ts"]),
                "exit_ts": pd.Timestamp(r["exit_ts"]),
                "entry_price": float(r["entry"]),
                "net_usd": float(r["net_usd"]),
            }
        )
    out = pd.DataFrame(rows).sort_values("entry_ts").reset_index(drop=True)
    if out.empty:
        return out
    out["win"] = out["net_usd"] > 0
    out["dow"] = out["entry_ts"].dt.day_name()
    out["hour_ny"] = out["entry_ts"].dt.hour
    out["month"] = out["entry_ts"].dt.month
    out["year"] = out["entry_ts"].dt.year
    out["week_of_month"] = ((out["entry_ts"].dt.day - 1) // 7 + 1).astype(int)
    return out


def run_profile(*, min_n: int, email: bool = False) -> pd.DataFrame:
    PROFILE_HUB.mkdir(parents=True, exist_ok=True)
    all_ann = []
    all_notables = []
    baselines = {}
    for book in BOOKS:
        if not book.trades.exists():
            _progress("SKIP profile %s (missing trades)" % book.key)
            continue
        _progress("PROFILE %s …" % book.key)
        _seed_daily_cache(book.symbol)
        camp = load_campaigns(book)
        if camp.empty:
            _progress("  empty campaigns")
            continue
        _progress("  campaigns=%d net≈$%.0f" % (len(camp), float(camp["net_usd"].sum())))
        try:
            feats = build_feature_frames(book.symbol)
        except FileNotFoundError as exc:
            _progress("  feature build failed: %s — calendar-only annotate" % exc)
            ann = camp.copy()
            ann["rsi_bucket"] = "na"
            ann["obv_cross"] = "na"
            ann["ma_state"] = "na"
            ann["atr_q"] = "na"
            ann["prior_day_half"] = "na"
        else:
            ann = annotate_campaigns(camp, feats)
        ann.to_csv(PROFILE_HUB / ("%s_campaigns.csv" % book.key), index=False)
        all_ann.append(ann)
        table, baseline, book_notables = profile_book(ann, min_n=min_n)
        sc = score_nets(ann["net_usd"].to_numpy(dtype=float), label="baseline")
        baseline = dict(baseline)
        baseline["ns"] = sc["ns"]
        baseline["stress"] = sc["stress"]
        baseline["book"] = book.key
        baselines[book.key] = baseline
        table.to_csv(PROFILE_HUB / ("%s_buckets.csv" % book.key), index=False)
        for n in book_notables:
            n = dict(n)
            n["book"] = book.key
            all_notables.append(n)
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

    if all_ann:
        pd.concat(all_ann, ignore_index=True).to_csv(PROFILE_HUB / "all_campaigns.csv", index=False)
    notables_df = pd.DataFrame(all_notables)
    if not notables_df.empty:
        notables_df = notables_df.sort_values(
            ["avg_lift", "wr_lift_pp"], ascending=False
        ).reset_index(drop=True)
    notables_df.to_csv(PROFILE_HUB / "notables.csv", index=False)
    (PROFILE_HUB / "baselines.json").write_text(json.dumps(baselines, indent=2) + "\n")

    lines = [
        "# CHOP20 boundary60 — HA condition profile",
        "",
        "Diagnostic HP conditions on 1m path-aware campaign tapes.",
        "min_n=%d." % min_n,
        "",
        "## Baselines",
        "",
    ]
    for k, b in baselines.items():
        lines.append(
            "- **%s**: n=%d WR=%.0f%% net=$%.0f N/S=%.2f"
            % (k, int(b["n"]), 100.0 * b["wr"], b["net"], float(b["ns"]))
        )
    lines += ["", "## Notables (top 40)", ""]
    if notables_df.empty:
        lines.append("_None cleared the heuristic._")
    else:
        lines.append("| book | condition | bucket | n | WR | WRΔpp | avgΔ |")
        lines.append("|---|---|---|---:|---:|---:|---:|")
        for _, r in notables_df.head(40).iterrows():
            lines.append(
                "| %s | %s | %s | %d | %.0f%% | %+.1f | $%+.0f |"
                % (
                    r.get("book", ""),
                    r["condition"],
                    r["bucket"],
                    int(r["n"]),
                    100.0 * float(r["wr"]),
                    float(r["wr_lift_pp"]),
                    float(r["avg_lift"]),
                )
            )
    lines += ["", "Hub: `%s`" % PROFILE_HUB, ""]
    (PROFILE_HUB / "SUMMARY.md").write_text("\n".join(lines))
    if email:
        send_email(subject="potions: CHOP20 HA profile complete", body="\n".join(lines))
    return notables_df


def run_overlay(*, email: bool = False, min_n: int = MIN_N_DEFAULT) -> pd.DataFrame:
    OVERLAY_HUB.mkdir(parents=True, exist_ok=True)
    camp_path = PROFILE_HUB / "all_campaigns.csv"
    if not camp_path.exists():
        raise SystemExit("Run profile first")
    campaigns = pd.read_csv(camp_path)
    campaigns["entry_ts"] = pd.to_datetime(campaigns["entry_ts"], utc=True)
    notables = (
        pd.read_csv(PROFILE_HUB / "notables.csv")
        if (PROFILE_HUB / "notables.csv").exists()
        else pd.DataFrame()
    )
    hits = notables[notables["n"] >= min_n].head(12).reset_index(drop=True) if not notables.empty else notables
    hits.to_csv(OVERLAY_HUB / "candidates.csv", index=False)

    policies: List[Tuple[str, float]] = [
        ("baseline", 1.0),
        ("filter", 0.0),
        ("size_1.25", 1.25),
        ("size_1.5", 1.5),
    ]
    rows: List[dict] = []
    for book_key in campaigns["book"].unique():
        book_hits = hits[hits["book"] == book_key] if "book" in hits.columns else hits
        split_full = campaigns[campaigns["book"] == book_key]
        for _, hit in book_hits.iterrows():
            cond = str(hit["condition"])
            bucket = str(hit["bucket"])
            causal = (
                "live_ready"
                if cond in CAUSAL_LIVE_READY
                else ("needs_rolling_proxy" if cond in NEEDS_LIVE_PROXY else "unknown")
            )
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
                        nets = apply_policy(split_df, mask, policy=policy, size_mult=float(mult))
                    sc = score_nets(nets, label=policy)
                    rows.append(
                        {
                            "book": book_key,
                            "condition": cond,
                            "bucket": bucket,
                            "causal": causal,
                            "split": split_name,
                            "policy": policy,
                            "size_mult": float(mult) if policy.startswith("size_") else (0.0 if policy == "filter" else 1.0),
                            "hp_n": int(mask.sum()),
                            "hp_frac": float(mask.mean()) if len(mask) else 0.0,
                            "base_n": base["n"],
                            "base_net": base["net"],
                            "base_ns": base["ns"],
                            "base_stress": base["stress"],
                            "net": sc["net"],
                            "ns": sc["ns"],
                            "stress": sc["stress"],
                            "delta_net": sc["net"] - base["net"],
                            "delta_ns": sc["ns"] - base["ns"],
                        }
                    )
    results = pd.DataFrame(rows)
    if not results.empty:
        results.to_csv(OVERLAY_HUB / "overlay_results.csv", index=False)
        ranked = results[results["split"] == "full"].sort_values(
            ["delta_ns", "delta_net"], ascending=False
        )
        ranked.to_csv(OVERLAY_HUB / "ranked_full.csv", index=False)
    else:
        ranked = results

    lines = [
        "# CHOP20 boundary60 — HA overlay",
        "",
        "Filter / 1.25× / 1.5× on notable buckets. Thin-N book — diagnostic only.",
        "",
        "| book | condition=bucket | policy | ΔN/S | Δnet | hp% | causal |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    if ranked.empty:
        lines.append("| — | — | — | — | — | — | — |")
    else:
        show = ranked[ranked["policy"] != "baseline"].head(30)
        for _, r in show.iterrows():
            lines.append(
                "| %s | %s=%s | %s | %+.2f | $%+.0f | %.0f%% | %s |"
                % (
                    r["book"],
                    r["condition"],
                    r["bucket"],
                    r["policy"],
                    float(r["delta_ns"]),
                    float(r["delta_net"]),
                    100.0 * float(r["hp_frac"]),
                    r["causal"],
                )
            )
    lines += ["", "Hub: `%s`" % OVERLAY_HUB, ""]
    (OVERLAY_HUB / "SUMMARY.md").write_text("\n".join(lines))
    if email:
        send_email(subject="potions: CHOP20 HA overlay complete", body="\n".join(lines))
    return ranked


def run_nulls(*, email: bool = False, smoke: bool = False) -> pd.DataFrame:
    NULLS_HUB.mkdir(parents=True, exist_ok=True)
    campaigns = pd.read_csv(PROFILE_HUB / "all_campaigns.csv")
    campaigns["entry_ts"] = pd.to_datetime(campaigns["entry_ts"], utc=True)
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
            & (ranked["hp_frac"] < 0.50)
            & (ranked["base_n"] >= MIN_N_DEFAULT)
        ].copy()
        size = size.sort_values(["delta_ns", "delta_net"], ascending=False)
        seen = set()
        for _, r in size.iterrows():
            key = (str(r["book"]), str(r["condition"]), str(r["bucket"]))
            if key in seen:
                continue
            seen.add(key)
            pairs.append(key)
            if len(pairs) >= (2 if smoke else 6):
                break
    if not pairs and not notables.empty:
        for _, r in notables.sort_values("avg_lift", ascending=False).iterrows():
            pairs.append((str(r.get("book", BOOKS[0].key)), str(r["condition"]), str(r["bucket"])))
            if len(pairs) >= (2 if smoke else 4):
                break

    if not pairs:
        msg = "No pairs eligible for nulls (need size ΔN/S>0 + coverage)."
        _progress(msg)
        (NULLS_HUB / "SUMMARY.md").write_text("# CHOP20 HA nulls\n\n%s\n" % msg)
        if email:
            send_email(subject="potions: CHOP20 HA nulls skipped", body=msg)
        return pd.DataFrame()

    n_placebo = 400 if smoke else 2000
    n_shift = 200 if smoke else 800
    n_master = 100 if smoke else 400
    n_wf = 100 if smoke else 400

    from .intraday_condition_overlay import select_cross_book_hits, select_single_book_hits
    import live.intraday_hp_sizeup_nulls as nulls_mod

    nulls_mod.HUB = NULLS_HUB
    singles = select_single_book_hits(notables, min_z=0.5, min_n=MIN_N_DEFAULT, top_per_book=10)
    crosses = select_cross_book_hits(notables, min_books=2) if "book" in notables.columns else []

    results = []
    for i, (book, cond, bucket) in enumerate(pairs):
        _progress("NULLS %s | %s=%s …" % (book, cond, bucket))
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
                seed=20260828 + i * 17,
            )
            results.append(res)
            _progress(
                "  decision=%s ΔN/S=%+.3f p_master=%.3f"
                % (
                    res.get("decision"),
                    float(res.get("delta_ns") or 0.0),
                    float(res.get("p_master_delta_ns") or res.get("p_master") or float("nan")),
                )
            )
        except Exception:
            _progress("  CRASH pair\n" + traceback.format_exc()[-1500:])

    out = pd.DataFrame(results)
    if not out.empty:
        out.to_csv(NULLS_HUB / "pair_decisions.csv", index=False)

    lines = [
        "# CHOP20 boundary60 — HA matched nulls",
        "",
        "1.25× matched-added-exposure. Thin campaign N — treat VALIDATED cautiously.",
        "",
        "| decision | book | condition=bucket | ΔN/S | p_master |",
        "|---|---|---|---:|---:|",
    ]
    if out.empty:
        lines.append("| — | — | — | — | — |")
    else:
        for _, r in out.iterrows():
            lines.append(
                "| %s | %s | %s=%s | %+.2f | %.3f |"
                % (
                    r.get("decision", ""),
                    r.get("book", ""),
                    r.get("condition", ""),
                    r.get("bucket", ""),
                    float(r.get("sleeve_delta_ns") or r.get("delta_ns") or 0.0),
                    float(r.get("p_master_delta_ns") or r.get("p_master") or float("nan")),
                )
            )
    lines += ["", "Hub: `%s`" % NULLS_HUB, ""]
    (NULLS_HUB / "SUMMARY.md").write_text("\n".join(lines))
    body = "potions: CHOP20 HA nulls complete\n\n" + "\n".join(lines)
    (NULLS_HUB / "EMAIL.txt").write_text(body)
    if email:
        send_email(subject="potions: CHOP20 HA nulls complete", body=body)
    return out


def run(*, email: bool, smoke: bool, profile_only: bool, overlay_only: bool, nulls_only: bool) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    _append_dsr()
    rid = begin_run(
        run_class="ha",
        variant_slug="chop20_boundary60_ha",
        instrument="NQ",
        hub_path=str(HUB.relative_to(REPO)),
        dsr_trial_id=DSR,
        notes="HA mill running",
        meta={"pipeline": "profile+overlay+nulls"},
    )
    try:
        _progress("START CHOP20 HA mill")
        if not overlay_only and not nulls_only:
            run_profile(min_n=MIN_N_DEFAULT, email=False)
        if not profile_only and not nulls_only:
            run_overlay(email=False, min_n=MIN_N_DEFAULT)
        decisions = []
        if not profile_only and not overlay_only:
            nulls = run_nulls(email=False, smoke=smoke)
            if not nulls.empty and "decision" in nulls.columns:
                decisions = sorted({str(x) for x in nulls["decision"].tolist()})

        # Package SUMMARY
        lines = [
            "# CHOP20 Dynamic Range — HA mill",
            "",
            "Source structure: touch_broken_boundary + max_age_60 + 0.5/1/4R (1m path).",
            "",
            "## Profile",
            "",
            (PROFILE_HUB / "SUMMARY.md").read_text() if (PROFILE_HUB / "SUMMARY.md").exists() else "_missing_",
            "",
            "## Overlay",
            "",
            (OVERLAY_HUB / "SUMMARY.md").read_text() if (OVERLAY_HUB / "SUMMARY.md").exists() else "_missing_",
            "",
            "## Nulls",
            "",
            (NULLS_HUB / "SUMMARY.md").read_text() if (NULLS_HUB / "SUMMARY.md").exists() else "_missing_",
            "",
        ]
        stance = "diagnostic HA — no size-up promotion (nulls not VALIDATED)"
        if any(d == "SIZE-UP VALIDATED" or d == "VALIDATED" for d in decisions):
            stance = "SIZE-UP interest — see nulls VALIDATED (still research; thin N)"
        elif any("PROVISIONAL" in d for d in decisions):
            stance = "PROVISIONAL size-up interest — controlled paper only if repeated"
        elif any("RISK THROTTLE" in d for d in decisions):
            stance = "diagnostic HA — RISK THROTTLE only; shadow profile, no size-up"
        lines += ["**Stance:** %s" % stance, "", "DSR: `%s`" % DSR, "", "Hub: `%s`" % HUB, ""]
        body = "\n".join(lines)
        (HUB / "SUMMARY.md").write_text(body)
        (HUB / "EMAIL.txt").write_text("potions: CHOP20 HA mill complete\n\n" + body)
        _mark_dsr("COMPLETE")
        complete_run(rid, notes="HA mill done; decisions=%s" % (",".join(decisions) or "none"))
        if email:
            send_email(subject="potions: CHOP20 HA mill complete", body=(HUB / "EMAIL.txt").read_text())
        _progress("DONE HA mill")
    except Exception:
        err = traceback.format_exc()
        fail_run(rid, notes=err[-2000:])
        _mark_dsr("FAILED")
        if email:
            send_email(subject="potions: CHOP20 HA mill FAILED", body=err[-4000:])
        raise


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--profile-only", action="store_true")
    ap.add_argument("--overlay-only", action="store_true")
    ap.add_argument("--nulls-only", action="store_true")
    args = ap.parse_args()
    run(
        email=bool(args.email),
        smoke=bool(args.smoke),
        profile_only=bool(args.profile_only),
        overlay_only=bool(args.overlay_only),
        nulls_only=bool(args.nulls_only),
    )


if __name__ == "__main__":
    main()
