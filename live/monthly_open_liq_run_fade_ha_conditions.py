"""HA (high-probability conditions) mill for NQ liq-run fade 1:1 HP 1m broker.

Target book: ``liq_run_fade_1r1_reentry_hp_1m_broker``
(~+$552k / N/S 1.03 / 183 entries).

Pipeline (same machinery as quarterly ATR4 / intraday HA):

1. Condition profile on Engine+PaperBroker campaign tape (entry-asof features)
2. Filter / 1.25× / 1.5× overlays on notable buckets
3. Matched-added-exposure nulls on strongest size-up candidates (when N allows)

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.monthly_open_liq_run_fade_ha_conditions --email
  python -m live.monthly_open_liq_run_fade_ha_conditions --email --smoke
  python -m live.monthly_open_liq_run_fade_ha_conditions --email --profile-only
"""

from __future__ import annotations

import argparse
import json
import traceback
from dataclasses import dataclass
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
from .quarterly_atr4_fade_broker import MARKETS
from .run_ledger import log_run

HUB = (
    REPO
    / "live"
    / "state"
    / "monthly_open_atr_extension_band"
    / "liq_run_fade_1r1_reentry_hp_1m_ha"
)
PROFILE_HUB = HUB / "profile"
OVERLAY_HUB = HUB / "overlay"
NULLS_HUB = HUB / "nulls"
NY = "America/New_York"
MIN_N_DEFAULT = 12  # 183 campaigns — slightly above quarterly thin-book floor


@dataclass(frozen=True)
class FadeBook:
    key: str
    label: str
    symbol: str
    fills: Path


BOOK = FadeBook(
    "nq_liq_run_fade_1r1_reentry_hp_1m",
    "NQ liq-run fade 1:1 reentry HP (1m broker)",
    "NQ",
    REPO
    / "live/state/monthly_open_atr_extension_band"
    / "liq_run_fade_1r1_reentry_hp_1m_broker"
    / "states/nq_liq_run_fade_1r1_reentry_hp_1m/fills.csv",
)

# Reminder block for email / SUMMARY (path-sim + broker family).
VARIANT_NS_RANK = """\
Variant N/S reminder (same liq-run fade family):

  Best N/S overall (path sim, HP lookback):
    2c half+open $1k SL     HP N/S 3.46  (+$32k)   — small-risk sleeve
  Best among full-size structural books (path sim, HP lookback):
    1:1 unlimited reentry   HP N/S 2.24  (+$618k)  — this book's 1h cousin
  This book (1m Engine+PaperBroker, HP):
    1:1 unlimited reentry   N/S 1.03     (+$552k / 183 entries)
  Other HP path-sim refs:
    win3 reentry cap        HP N/S 1.58
    2c BE+2R                HP N/S 1.02
    base once/month 1:1     HP N/S 0.64
    liq-days=4 1m broker    N/S -0.60
"""


def _progress(msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def load_campaigns(book: FadeBook) -> pd.DataFrame:
    market = MARKETS[book.symbol.upper()]
    fee = float(market.fee_per_unit)
    fills = pd.read_csv(book.fills)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1).astype(int)
    rows = []
    for trade_id, group in fills.sort_values("ts").groupby("trade_id"):
        entries = group[group["reason"].astype(str) == "entry"]
        exits = group[group["reason"].astype(str) != "entry"]
        if entries.empty or exits.empty:
            continue
        entry = entries.iloc[0]
        side = "long" if str(entry["side"]).lower() == "buy" else "short"
        entry_px = float(entry["price"])
        net = 0.0
        for _, exit_row in exits.iterrows():
            qty = int(exit_row["quantity"])
            px = float(exit_row["price"])
            pts = px - entry_px if side == "long" else entry_px - px
            net += pts * market.point_value * qty - fee * qty
        rows.append(
            {
                "book": book.key,
                "family": "monthly_open_liq_run_fade",
                "symbol": book.symbol,
                "trade_id": str(trade_id),
                "side": side,
                "entry_ts": pd.Timestamp(entry["ts"]),
                "exit_ts": pd.Timestamp(exits["ts"].max()),
                "entry_price": entry_px,
                "net_usd": float(net),
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
    book = BOOK
    _progress("PROFILE %s ..." % book.key)
    if not book.fills.exists():
        raise SystemExit("Missing fills: %s" % book.fills)
    camp = load_campaigns(book)
    _progress("  campaigns=%d" % len(camp))
    if camp.empty:
        raise SystemExit("No campaigns from fills")

    _progress("  building features for %s ..." % book.symbol)
    feats = build_feature_frames(book.symbol)
    ann = annotate_campaigns(camp, feats)
    ann.to_csv(PROFILE_HUB / ("%s_campaigns.csv" % book.key), index=False)
    ann.to_csv(PROFILE_HUB / "all_campaigns.csv", index=False)

    table, baseline, book_notables = profile_book(ann, min_n=min_n)
    baseline["book"] = book.key
    table.to_csv(PROFILE_HUB / ("%s_buckets.csv" % book.key), index=False)
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
        "  baseline n=%d WR=%.0f%% net=$%.0f notables=%d"
        % (
            int(baseline["n"]),
            100.0 * baseline["wr"],
            baseline["net"],
            len(book_notables),
        )
    )

    lines = [
        "# NQ liq-run fade HP 1m — HA condition profile",
        "",
        "High-probability condition study on **1m Engine+PaperBroker** tape",
        "(+$552k / N/S 1.03 / 183 entries). Features: DOW / week-of-month / hour /",
        "5m MA / hourly RSI+OBV / ATR quartile / prior range-half.",
        "Diagnostic — not a promotion gate.",
        "",
        "min_n=%d." % min_n,
        "",
        "## Book",
        "",
        "- **%s**: n=%d WR=%.1f%% avg=$%.0f net=$%.0f"
        % (
            book.label,
            int(baseline["n"]),
            100.0 * baseline["wr"],
            baseline["avg_net"],
            baseline["net"],
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
    lines += ["", "Hub: `%s`" % PROFILE_HUB, ""]
    (PROFILE_HUB / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")

    email_body = (
        "potions: NQ liq-run fade HA profile complete\n\n"
        "Hub: %s\nBook: %s\ncampaigns: %d  notables: %d\n"
        "baseline net=$%.0f\n\n%s\n"
        % (
            PROFILE_HUB,
            book.key,
            len(ann),
            len(notables_df),
            baseline["net"],
            VARIANT_NS_RANK,
        )
    )
    (PROFILE_HUB / "EMAIL.txt").write_text(email_body, encoding="utf-8")
    if email:
        send_email(subject="potions: NQ liq-run fade HA profile complete", body=email_body)
        _progress("profile email sent")
    return notables_df


def _select_hits(notables: pd.DataFrame, *, min_n: int, top: int = 10) -> pd.DataFrame:
    if notables.empty:
        return notables
    df = notables[notables["n"] >= min_n].copy()
    return df.head(top).reset_index(drop=True)


def run_overlay(*, email: bool = False, min_n: int = MIN_N_DEFAULT) -> pd.DataFrame:
    OVERLAY_HUB.mkdir(parents=True, exist_ok=True)
    campaigns = pd.read_csv(PROFILE_HUB / "all_campaigns.csv")
    campaigns["entry_ts"] = pd.to_datetime(campaigns["entry_ts"], utc=True)
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
        "# NQ liq-run fade HP 1m — HA overlays",
        "",
        "Filter / 1.25× / 1.5× on profile notables vs baseline 1m broker tape.",
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
        "potions: NQ liq-run fade HA overlay complete",
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
        send_email(subject="potions: NQ liq-run fade HA overlay complete", body=email_txt)
        _progress("overlay email sent")
    return results


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
            if len(pairs) >= (2 if smoke else 6):
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
            "# NQ liq-run fade HA nulls\n\n%s\n" % msg, encoding="utf-8"
        )
        (NULLS_HUB / "EMAIL.txt").write_text(
            "potions: NQ liq-run fade HA nulls skipped\n\nHub: %s\n%s\n"
            % (NULLS_HUB, msg),
            encoding="utf-8",
        )
        if email:
            send_email(
                subject="potions: NQ liq-run fade HA nulls skipped",
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
        _progress("NULLS %s | %s=%s ..." % (book, cond, bucket))
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
                seed=20260825 + i * 17,
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
        "# NQ liq-run fade HP 1m — HA matched nulls",
        "",
        "1.25× matched-added-exposure on top size-up candidates from the overlay.",
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

    email_body = "potions: NQ liq-run fade HA nulls complete\n\nHub: %s\nPairs: %d\n\n" % (
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
        send_email(subject="potions: NQ liq-run fade HA nulls complete", body=email_body)
        _progress("nulls email sent")
    return out


def write_root_summary() -> None:
    parts = [
        "# NQ liq-run fade 1:1 HP 1m — HA mill",
        "",
        "Source book: `liq_run_fade_1r1_reentry_hp_1m_broker` (+$552k / N/S 1.03 / 183).",
        "",
        "```",
        VARIANT_NS_RANK.rstrip(),
        "```",
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
    _progress("START NQ liq-run fade HA mill")
    _progress(VARIANT_NS_RANK)

    try:
        if not args.overlay_only and not args.nulls_only:
            run_profile(min_n=args.min_n, email=False)
        if args.profile_only:
            write_root_summary()
            if args.email:
                send_email(
                    subject="potions: NQ liq-run fade HA profile-only complete",
                    body=(PROFILE_HUB / "EMAIL.txt").read_text(encoding="utf-8"),
                )
            log_run(
                run_class="ha",
                variant_slug="nq_liq_run_fade_1r1_reentry_hp_1m_ha_profile",
                instrument="NQ",
                hub_path=str(HUB.relative_to(REPO)),
                notes="HA profile-only",
            )
            _progress("DONE profile-only")
            return 0
        if not args.nulls_only:
            run_overlay(email=False, min_n=args.min_n)
        if not args.overlay_only:
            run_nulls(email=False, smoke=args.smoke)
        write_root_summary()

        body_parts = [
            "potions: NQ liq-run fade HA mill complete",
            "",
            "Hub: %s" % HUB.resolve(),
            "Book: liq_run_fade_1r1_reentry_hp_1m_broker (+$552k / N/S 1.03 / 183).",
            "",
            VARIANT_NS_RANK,
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
            json.dumps({"ok": True, "hub": str(HUB)}, indent=2) + "\n", encoding="utf-8"
        )
        log_run(
            run_class="ha",
            variant_slug="nq_liq_run_fade_1r1_reentry_hp_1m_ha",
            instrument="NQ",
            hub_path=str(HUB.relative_to(REPO)),
            notes="HA condition mill profile+overlay+nulls",
            meta={"source": "liq_run_fade_1r1_reentry_hp_1m_broker"},
        )
        if args.email:
            send_email(subject="potions: NQ liq-run fade HA mill complete", body=body)
            _progress("consolidated email sent")
        _progress("DONE")
        return 0
    except Exception:
        err = traceback.format_exc()
        _progress("CRASH\n%s" % err)
        (HUB / "EMAIL.txt").write_text(
            "potions: NQ liq-run fade HA mill FAILED\n\nHub: %s\n\n%s\n" % (HUB, err),
            encoding="utf-8",
        )
        if args.email:
            send_email(
                subject="potions: NQ liq-run fade HA mill FAILED",
                body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
