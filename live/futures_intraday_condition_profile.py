"""Futures intraday condition profile for HP size-up v1.

Builds campaign tapes + causal features for the top-8 selected futures books,
profiles carry-over and futures-native conditions, and shortlists ≤3 candidates
per book (≤1 per feature family).

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.futures_intraday_condition_profile --email
"""

from __future__ import annotations

import argparse
import json
import math
import traceback
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

from .futures_intraday_hp_sizeup_lib import (
    CONDITION_COLS,
    CAUSAL_LIVE_READY,
    NEEDS_LIVE_PROXY,
    PROFILE_HUB,
    STUDY,
    BOOK_UNIVERSE,
    annotate_campaigns,
    feature_family,
    load_campaigns,
    select_top_futures_books,
    write_selection_artifacts,
)
from .notify_email import send_email

MIN_N = 40
HP_COV_LO = 0.05
HP_COV_HI = 0.35


def score_nets(nets: np.ndarray) -> Dict[str, float]:
    nets = np.asarray(nets, dtype=float)
    if nets.size == 0:
        return {"n": 0, "net": 0.0, "stress": 0.0, "ns": 0.0, "wr": 0.0, "avg": 0.0}
    eq = np.cumsum(nets)
    peak = np.maximum.accumulate(eq)
    stress = float(abs((eq - peak).min()))
    net = float(nets.sum())
    return {
        "n": int(nets.size),
        "net": net,
        "stress": stress,
        "ns": (net / stress) if stress > 1e-9 else (99.0 if net > 0 else 0.0),
        "wr": float((nets > 0).mean()),
        "avg": float(nets.mean()),
    }


def summarize_bucket(df: pd.DataFrame, baseline: Dict[str, float]) -> Dict[str, float]:
    n = int(len(df))
    if n == 0:
        return {"n": 0}
    nets = df["net_usd"].to_numpy(float)
    sc = score_nets(nets)
    p0 = baseline["wr"]
    n0 = baseline["n"]
    se = math.sqrt(max(p0 * (1 - p0) * (1 / n + 1 / max(n0, 1)), 1e-12))
    z = (sc["wr"] - p0) / se if se > 0 else 0.0
    return {
        "n": n,
        "wins": int((nets > 0).sum()),
        "wr": sc["wr"],
        "avg_net": sc["avg"],
        "net": sc["net"],
        "stress": sc["stress"],
        "ns": sc["ns"],
        "wr_lift_pp": 100.0 * (sc["wr"] - p0),
        "avg_lift": sc["avg"] - baseline["avg"],
        "z_wr": z,
    }


def incremental_125(all_nets: np.ndarray, mask: np.ndarray) -> Dict[str, float]:
    sized = all_nets.copy()
    sized[mask] = sized[mask] * 1.25
    base = score_nets(all_nets)
    full = score_nets(sized)
    inc = np.zeros_like(all_nets)
    inc[mask] = 0.25 * all_nets[mask]
    sleeve = score_nets(inc)
    return {
        "inc_net": sleeve["net"],
        "inc_stress": score_nets(inc)["stress"] if False else float(abs(np.minimum.accumulate(np.cumsum(inc)).min())) if inc.size else 0.0,
        "inc_ns": sleeve["ns"],
        "book_ns_base": base["ns"],
        "book_ns_sized": full["ns"],
        "book_stress_x": full["stress"] / base["stress"] if base["stress"] > 1e-9 else 1.0,
    }


def _inc_stress_path(all_nets: np.ndarray, mask: np.ndarray) -> float:
    inc = np.zeros_like(all_nets)
    inc[mask] = 0.25 * all_nets[mask]
    eq = np.cumsum(inc)
    if eq.size == 0:
        return 0.0
    peak = np.maximum.accumulate(eq)
    return float(abs((eq - peak).min()))


def profile_book(df: pd.DataFrame, min_n: int = MIN_N) -> Tuple[pd.DataFrame, Dict[str, float], List[dict]]:
    all_nets = df["net_usd"].to_numpy(float)
    baseline = score_nets(all_nets)
    baseline["avg"] = baseline["avg"]
    rows = []
    notables = []
    for col, title in CONDITION_COLS:
        if col not in df.columns:
            continue
        for val, g in df.groupby(col, dropna=False):
            if str(val) in {"nan", "None", ""} or str(val).endswith("_na") or str(val) == "na":
                # keep in matrix but skip notables later
                pass
            stats = summarize_bucket(g, baseline)
            if stats.get("n", 0) < min_n:
                continue
            mask = (df[col].astype(str) == str(val)).to_numpy()
            cov = float(mask.mean()) if len(mask) else 0.0
            inc = incremental_125(all_nets, mask)
            inc["inc_stress"] = _inc_stress_path(all_nets, mask)
            if abs(inc["inc_stress"]) > 1e-9:
                inc["inc_ns"] = inc["inc_net"] / inc["inc_stress"]
            row = {
                "book": df["book"].iloc[0],
                "symbol": df["symbol"].iloc[0],
                "condition": title,
                "bucket": str(val),
                "feature": feature_family(title),
                "family": feature_family(title),
                "coverage": cov,
                "causal_live_ready": title in CAUSAL_LIVE_READY,
                "needs_proxy": title in NEEDS_LIVE_PROXY,
                **stats,
                **inc,
            }
            # Yearly breakdown for HP bucket
            years = []
            if "year" in g.columns:
                for y, yg in g.groupby("year"):
                    years.append("%s:%.0f" % (y, yg["net_usd"].sum()))
            row["yearly_net"] = ";".join(years[:12])
            rows.append(row)
            scale = max(abs(baseline["avg"]), 1.0)
            notable = (
                stats["n"] >= min_n
                and stats["avg_lift"] > 0
                and stats["wr_lift_pp"] > 0
                and (
                    abs(stats["z_wr"]) >= 1.64
                    or abs(stats["avg_lift"]) >= 0.35 * scale
                )
                and not str(val).endswith("_na")
                and str(val) not in {"na", "or_pre_open", "cross_none"}
            )
            if notable:
                notables.append(row)
    table = pd.DataFrame(rows)
    if not table.empty:
        table = table.sort_values(["inc_ns", "avg_lift"], ascending=False).reset_index(drop=True)
    return table, baseline, notables


def shortlist_candidates(
    matrix: pd.DataFrame,
    baselines: Dict[str, dict],
    *,
    max_per_book: int = 3,
) -> pd.DataFrame:
    """≤3 per book, ≤1 per feature family, coverage 5–35%, causal, positive base."""
    ledger_rows = []
    short_rows = []
    if matrix.empty:
        return pd.DataFrame(), pd.DataFrame()

    for book, g in matrix.groupby("book"):
        base = baselines.get(book, {})
        base_ok = float(base.get("net", 0.0)) > 0 and float(base.get("ns", 0.0)) > 0
        ranked = g.sort_values(["inc_ns", "avg_lift", "z_wr"], ascending=False)
        seen_fam = set()
        picked = 0
        for _, r in ranked.iterrows():
            cond = str(r["condition"])
            bucket = str(r["bucket"])
            fam = str(r["family"])
            cov = float(r["coverage"])
            reason = []
            if not base_ok:
                reason.append("negative_or_flat_base")
            if not bool(r["causal_live_ready"]):
                reason.append("not_causal_live_ready")
            if bool(r["needs_proxy"]) and cond.startswith("ATR14"):
                reason.append("atr_static_quartile_proxy")
            if cov < HP_COV_LO:
                reason.append("coverage_too_low")
            if cov > HP_COV_HI:
                reason.append("coverage_too_broad")
            if float(r["avg_lift"]) <= 0 or float(r["wr_lift_pp"]) <= 0:
                reason.append("no_dual_lift")
            if float(r["n"]) < MIN_N:
                reason.append("low_n")
            if str(bucket).endswith("_na") or bucket in {"na", "or_pre_open"}:
                reason.append("na_bucket")
            # Exclude generic MA-cross (not in CONDITION_COLS) and prefer ma_opposed
            if cond == "5m MA vs trade" and bucket != "ma_opposed":
                reason.append("prefer_ma_opposed_only")
            status = "examined"
            shortlisted = False
            if not reason and fam not in seen_fam and picked < max_per_book:
                shortlisted = True
                seen_fam.add(fam)
                picked += 1
                status = "shortlisted"
            elif not reason and (fam in seen_fam or picked >= max_per_book):
                reason.append("family_or_book_cap")
                status = "rejected_cap"
            elif reason:
                status = "rejected"
                if cov > HP_COV_HI and "coverage_too_broad" in reason and float(r["inc_ns"]) > 0:
                    status = "risk_budget_profile_only"

            row = {
                **{k: r[k] for k in r.index},
                "status": status,
                "shortlisted": shortlisted,
                "reject_reason": ";".join(reason),
            }
            ledger_rows.append(row)
            if shortlisted:
                short_rows.append(row)

    ledger = pd.DataFrame(ledger_rows)
    short = pd.DataFrame(short_rows)
    return short, ledger


def yearly_bucket_table(df: pd.DataFrame, col: str, bucket: str) -> pd.DataFrame:
    mask = df[col].astype(str) == str(bucket)
    rows = []
    for y, g in df.groupby("year"):
        m = mask.loc[g.index]
        hp = g.loc[m]
        sc_all = score_nets(g["net_usd"].to_numpy(float))
        sc_hp = score_nets(hp["net_usd"].to_numpy(float)) if len(hp) else score_nets(np.array([]))
        rows.append(
            {
                "year": int(y),
                "n_all": sc_all["n"],
                "net_all": sc_all["net"],
                "ns_all": sc_all["ns"],
                "n_hp": sc_hp["n"],
                "net_hp": sc_hp["net"],
                "ns_hp": sc_hp["ns"],
            }
        )
    return pd.DataFrame(rows)


def render_profile(
    books_meta: list,
    baselines: Dict[str, dict],
    notables: List[dict],
    short: pd.DataFrame,
    matrix: pd.DataFrame,
) -> str:
    lines = [
        "# Futures intraday condition profile",
        "",
        "Study: `%s`" % STUDY,
        "",
        "Diagnostic + shortlist for 1.25× HP size-up. Not a promotion gate by itself.",
        "",
        "## Selected books (top 8 after sleeve/family dedup)",
        "",
        "| book | symbol | family | tracker N/S | campaigns | status |",
        "|---|---|---|---:|---:|---|",
    ]
    for b in books_meta:
        lines.append(
            "| %s | %s | %s | %.2f | %d | %s |"
            % (b["key"], b["symbol"], b["family"], b["tracker_ns"], b.get("n_campaigns", 0), b["status"])
        )
    lines.extend(["", "## Baselines", "", "| book | n | net | stress | N/S | WR |", "|---|---:|---:|---:|---:|---:|"])
    for k, b in baselines.items():
        lines.append(
            "| %s | %d | %+.0f | %.0f | %.2f | %.1f%% |"
            % (k, b["n"], b["net"], b["stress"], b["ns"], 100 * b["wr"])
        )
    lines.extend(["", "## Shortlisted candidates (≤3/book, ≤1/family, cov 5–35%)", ""])
    if short is None or short.empty:
        lines.append("_none_")
    else:
        lines.append("| book | condition=bucket | fam | cov | n | avg lift | inc N/S | z_WR |")
        lines.append("|---|---|---|---:|---:|---:|---:|---:|")
        for _, r in short.iterrows():
            lines.append(
                "| %s | %s=%s | %s | %.0f%% | %d | %+.0f | %.2f | %.2f |"
                % (
                    r["book"],
                    r["condition"],
                    r["bucket"],
                    r["family"],
                    100 * r["coverage"],
                    r["n"],
                    r["avg_lift"],
                    r["inc_ns"],
                    r["z_wr"],
                )
            )
    lines.extend(["", "## Cross-book notable repeats", ""])
    if notables:
        nd = pd.DataFrame(notables)
        hits = (
            nd.groupby(["condition", "bucket"])
            .agg(n_books=("book", "nunique"), books=("book", lambda s: ",".join(sorted(set(s)))))
            .reset_index()
            .sort_values("n_books", ascending=False)
        )
        lines.append("| condition=bucket | books | n |")
        lines.append("|---|---|---:|")
        for _, r in hits.head(25).iterrows():
            lines.append("| %s=%s | %s | %d |" % (r["condition"], r["bucket"], r["books"], r["n_books"]))
    else:
        lines.append("_none_")
    lines.extend(
        [
            "",
            "## Carry-over vs futures-native",
            "",
            "- Carry: Thu/Fri DOW, RSI against / extremes, ATR regime, prior-week opposition,",
            "  week-of-month, entry hour, MA **opposition** (not generic 5m MA-cross).",
            "- Futures-native: overnight location/compression, prior RTH structure, OR15,",
            "  VWAP, opening volume, ES/NQ/YM agreement, ST-age proxy, roll/holiday flags.",
            "- HTF: yearly ORB up/down/inside, monthly OR up/down/inside, prior-quarter",
            "  inside/breakout type, weekly ATR SuperTrend align/oppose.",
            "",
            "Artifacts: `condition_matrix.csv`, `candidate_ledger.csv`, `causal_feature_audit.csv`,",
            "`*_campaigns.csv`, `SELECTED_BOOKS.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--min-n", type=int, default=MIN_N)
    ap.add_argument("--books", type=int, default=8)
    ap.add_argument(
        "--symbol",
        type=str,
        default="",
        help="Restrict to one symbol (e.g. ES) — skips top-N sleeve dedup",
    )
    ap.add_argument(
        "--out-hub",
        type=str,
        default="",
        help="Override output hub path (default: futures_intraday_condition_profile)",
    )
    args = ap.parse_args(argv)

    hub = Path(args.out_hub) if args.out_hub else PROFILE_HUB
    if args.out_hub and not Path(args.out_hub).is_absolute():
        from .fx_v2b_london_ungated import REPO

        hub = REPO / args.out_hub
    hub.mkdir(parents=True, exist_ok=True)
    try:
        if args.symbol:
            sym = args.symbol.upper()
            books = [b for b in BOOK_UNIVERSE if b.symbol.upper() == sym and b.fills.exists()]
            if not books:
                raise RuntimeError("no books for symbol %s" % sym)
            univ = pd.DataFrame(
                [
                    {
                        "key": b.key,
                        "symbol": b.symbol,
                        "family": b.family,
                        "tracker_ns": b.tracker_ns,
                        "selected": True,
                        "viable": True,
                        "score": b.tracker_ns,
                        "notes": "symbol_filter=%s" % sym,
                    }
                    for b in books
                ]
            )
            write_selection_artifacts(books, univ, hub)
        else:
            books, univ = select_top_futures_books(n=args.books)
            write_selection_artifacts(books, univ, hub)
        print("Selected %d books:" % len(books), flush=True)
        for b in books:
            print("  - %s (%s %s ns=%.2f)" % (b.key, b.symbol, b.family, b.tracker_ns), flush=True)

        all_campaigns = []
        matrices = []
        notables: List[dict] = []
        baselines: Dict[str, dict] = {}
        books_meta = []
        causal_audit_rows = []

        for book in books:
            print("BOOK %s ..." % book.key, flush=True)
            camp = load_campaigns(book)
            if camp.empty:
                print("  empty campaigns — skip", flush=True)
                continue
            print("  campaigns=%d — annotating features ..." % len(camp), flush=True)
            ann = annotate_campaigns(camp, book.symbol)
            ann.to_csv(hub / ("%s_campaigns.csv" % book.key), index=False)
            all_campaigns.append(ann)

            # Causal feature audit sample
            for col, title in CONDITION_COLS:
                if col not in ann.columns:
                    continue
                causal_audit_rows.append(
                    {
                        "book": book.key,
                        "condition": title,
                        "feature_col": col,
                        "n": int(ann[col].notna().sum()),
                        "n_unique": int(ann[col].astype(str).nunique()),
                        "causal_live_ready": title in CAUSAL_LIVE_READY,
                        "needs_proxy": title in NEEDS_LIVE_PROXY,
                        "family": feature_family(title),
                    }
                )

            table, baseline, book_notables = profile_book(ann, min_n=args.min_n)
            baseline["book"] = book.key
            baselines[book.key] = baseline
            table.to_csv(hub / ("%s_buckets.csv" % book.key), index=False)
            matrices.append(table)
            notables.extend(book_notables)
            books_meta.append(
                {
                    "key": book.key,
                    "symbol": book.symbol,
                    "family": book.family,
                    "tracker_ns": book.tracker_ns,
                    "status": book.status,
                    "n_campaigns": len(ann),
                    "sleeve": book.sleeve,
                }
            )
            print(
                "  baseline net=%+.0f N/S=%.2f notables=%d"
                % (baseline["net"], baseline["ns"], len(book_notables)),
                flush=True,
            )

        if not all_campaigns:
            raise RuntimeError("no campaigns loaded")

        campaigns = pd.concat(all_campaigns, ignore_index=True)
        campaigns.to_csv(hub / "all_campaigns.csv", index=False)
        matrix = pd.concat(matrices, ignore_index=True) if matrices else pd.DataFrame()
        matrix.to_csv(hub / "condition_matrix.csv", index=False)
        pd.DataFrame(notables).to_csv(hub / "notables.csv", index=False)
        pd.DataFrame(causal_audit_rows).to_csv(hub / "causal_feature_audit.csv", index=False)

        short, ledger = shortlist_candidates(matrix, baselines, max_per_book=3)
        if not ledger.empty:
            ledger.to_csv(hub / "candidate_ledger.csv", index=False)
        if not short.empty:
            short.to_csv(hub / "shortlist.csv", index=False)

        (hub / "baselines.json").write_text(json.dumps(baselines, indent=2), encoding="utf-8")
        (hub / "SELECTED_BOOKS.json").write_text(
            json.dumps({"study": STUDY, "books": books_meta, "symbol_filter": args.symbol or None}, indent=2),
            encoding="utf-8",
        )

        summary = render_profile(books_meta, baselines, notables, short, matrix)
        (hub / "PROFILE.md").write_text(summary, encoding="utf-8")
        (hub / "SUMMARY.md").write_text(summary, encoding="utf-8")

        email_lines = [
            "potions: futures_intraday_condition_profile complete",
            "Hub: %s" % hub,
            "Books: %d%s" % (len(books_meta), (" symbol=" + args.symbol.upper()) if args.symbol else ""),
            "Shortlist: %d candidates" % (0 if short is None or short.empty else len(short)),
            "",
        ]
        if short is not None and not short.empty:
            for _, r in short.head(12).iterrows():
                email_lines.append(
                    "%s | %s=%s | cov=%.0f%% incN/S=%.2f"
                    % (r["book"], r["condition"], r["bucket"], 100 * r["coverage"], r["inc_ns"])
                )
        # Highlight new HTF buckets among notables
        if notables:
            htf_titles = {
                "Yearly ORB direction",
                "Monthly OR direction",
                "Prior quarter type",
                "Weekly ATR trend vs trade",
            }
            htf_n = [n for n in notables if n.get("condition") in htf_titles]
            if htf_n:
                email_lines.append("")
                email_lines.append("HTF notables:")
                for n in htf_n[:12]:
                    email_lines.append(
                        "  %s | %s=%s | n=%d wr_lift=%+.1fpp avg_lift=%+.0f"
                        % (
                            n["book"],
                            n["condition"],
                            n["bucket"],
                            n["n"],
                            n.get("wr_lift_pp", 0),
                            n.get("avg_lift", 0),
                        )
                    )
        email_lines.append("")
        email_lines.append("Stance: profile/shortlist only — null suite next.")
        body = "\n".join(email_lines)
        (hub / "EMAIL.txt").write_text(body, encoding="utf-8")
        if args.email:
            send_email(subject="potions: futures condition profile complete", body=body)
        print(summary[:2000], flush=True)
        return 0
    except Exception:
        tb = traceback.format_exc()
        (hub / "FAIL.txt").write_text(tb, encoding="utf-8")
        if args.email:
            send_email(subject="potions: futures condition profile FAILED", body=tb[-4000:])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
