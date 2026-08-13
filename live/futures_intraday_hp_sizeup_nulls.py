"""Futures HP size-up null suite @ 1.25× only (futures_intraday_hp_sizeup_v1).

Reuses matched-placebo / clustered-shift / master-null / nested WF from the FX
framework with futures condition columns and portfolio sleeve gates.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.futures_intraday_hp_sizeup_nulls --email
"""

from __future__ import annotations

import argparse
import json
import math
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

import live.intraday_condition_overlay as overlay
import live.intraday_hp_sizeup_nulls as fxnulls

from .futures_intraday_hp_sizeup_lib import (
    CAUSAL_LIVE_READY,
    COND_COL,
    LIVE_HUB,
    NEEDS_LIVE_PROXY,
    NULLS_HUB,
    PROFILE_HUB,
    SEED,
    STUDY,
    SLEEVE,
)
from .intraday_condition_overlay import score_nets
from .intraday_hp_sizeup_nulls import (
    EXTRA_SIZE,
    evaluate_pair,
    phone_email,
    render_summary,
)
from .notify_email import send_email

# Decision label aliases requested by the futures brief
DECISION_ALIAS = {
    "BORDERLINE PAPER": "PROVISIONAL PAPER",
}


def _patch_fx_globals() -> None:
    """Point FX nulls/overlay at futures hubs + condition maps."""
    fxnulls.HUB = NULLS_HUB
    fxnulls.OVERLAY_HUB = PROFILE_HUB
    fxnulls.PROFILE_HUB = PROFILE_HUB  # type: ignore[attr-defined]
    # book_candidates reads PROFILE_HUB from overlay import path inside fxnulls
    import live.intraday_hp_sizeup_nulls as m

    # Force book_candidates to use futures profile hub
    overlay.PROFILE_HUB = PROFILE_HUB
    overlay.COND_COL.clear()
    overlay.COND_COL.update(COND_COL)
    overlay.CAUSAL_LIVE_READY.clear()
    overlay.CAUSAL_LIVE_READY.update(CAUSAL_LIVE_READY)
    overlay.NEEDS_LIVE_PROXY.clear()
    overlay.NEEDS_LIVE_PROXY.update(NEEDS_LIVE_PROXY)

    # Patch module-level PROFILE_HUB used inside book_candidates via local name
    # (imported at function body from overlay.PROFILE_HUB each call — see code:
    #  buckets_path = PROFILE_HUB / ... where PROFILE_HUB is fxnulls import from overlay)
    # In fxnulls: `from .intraday_condition_overlay import ... PROFILE_HUB`
    # So rebind fxnulls.PROFILE_HUB
    m.PROFILE_HUB = PROFILE_HUB
    m.HUB = NULLS_HUB
    m._causal = lambda condition: (
        "live_ready"
        if condition in CAUSAL_LIVE_READY
        else ("needs_rolling_proxy" if condition in NEEDS_LIVE_PROXY else "review")
    )


def _progress(msg: str) -> None:
    NULLS_HUB.mkdir(parents=True, exist_ok=True)
    with (NULLS_HUB / "PROGRESS.log").open("a", encoding="utf-8") as f:
        f.write(msg.rstrip() + "\n")
    print(msg, flush=True)


def load_shortlist_pairs() -> List[Tuple[str, str, str]]:
    path = PROFILE_HUB / "shortlist.csv"
    if not path.exists():
        raise FileNotFoundError("missing %s — run futures condition profile first" % path)
    df = pd.read_csv(path)
    pairs = []
    for _, r in df.iterrows():
        pairs.append((str(r["book"]), str(r["condition"]), str(r["bucket"])))
    return pairs


def portfolio_overlap_gate(results: List[dict], campaigns: pd.DataFrame) -> pd.DataFrame:
    """Joint stress / same-sleeve stacking checks for passing candidates."""
    passing = [
        r
        for r in results
        if r["decision"] in {"SIZE-UP VALIDATED", "BORDERLINE PAPER", "PROVISIONAL PAPER"}
    ]
    rows = []
    if not passing:
        return pd.DataFrame(
            columns=[
                "book_a",
                "book_b",
                "sleeve_a",
                "sleeve_b",
                "same_sleeve",
                "shared_hp_dates",
                "same_dir_rate",
                "inc_corr",
                "inc_joint_net",
                "inc_joint_stress",
                "inc_joint_ns",
                "inc_joint_mtm_dd",
                "worst_simultaneous_loss",
                "max_simultaneous_hp",
                "gate",
            ]
        )

    # Build HP masks per result
    masks: Dict[str, Tuple[dict, pd.DataFrame, np.ndarray]] = {}
    for r in passing:
        book = r["book"]
        df = campaigns[campaigns["book"] == book].sort_values("entry_ts").reset_index(drop=True)
        m = overlay.hp_mask(df, r["condition"], r["bucket"])
        masks[r["slug"]] = (r, df, m)

    keys = list(masks.keys())
    for i, ka in enumerate(keys):
        ra, dfa, ma = masks[ka]
        sleeve_a = str(dfa["sleeve"].iloc[0]) if "sleeve" in dfa.columns else SLEEVE.get(
            str(dfa["symbol"].iloc[0]), "?"
        )
        dates_a = set(dfa.loc[ma, "session_date"].astype(str)) if "session_date" in dfa.columns else set()
        for kb in keys[i + 1 :]:
            rb, dfb, mb = masks[kb]
            sleeve_b = str(dfb["sleeve"].iloc[0]) if "sleeve" in dfb.columns else SLEEVE.get(
                str(dfb["symbol"].iloc[0]), "?"
            )
            dates_b = set(dfb.loc[mb, "session_date"].astype(str)) if "session_date" in dfb.columns else set()
            shared = dates_a & dates_b
            # Same-direction + joint incremental day PnL on shared dates
            same_dir = 0
            both = 0
            joint_day: List[float] = []
            for d in shared:
                sa = dfa.loc[(dfa["session_date"].astype(str) == d) & ma]
                sb = dfb.loc[(dfb["session_date"].astype(str) == d) & mb]
                if len(sa) and len(sb) and "direction" in sa.columns and "direction" in sb.columns:
                    both += 1
                    if int(sa["direction"].iloc[0]) == int(sb["direction"].iloc[0]):
                        same_dir += 1
                    joint_day.append(
                        0.25 * float(sa["net_usd"].sum()) + 0.25 * float(sb["net_usd"].sum())
                    )

            def _daily_inc(df, mask):
                inc = np.zeros(len(df))
                inc[mask] = 0.25 * df["net_usd"].to_numpy(float)[mask]
                tmp = df[["session_date"]].copy()
                tmp["inc"] = inc
                return tmp.groupby("session_date")["inc"].sum()

            da = _daily_inc(dfa, ma)
            db = _daily_inc(dfb, mb)
            joined = pd.concat([da, db], axis=1, keys=["a", "b"]).fillna(0.0)
            corr = float(joined["a"].corr(joined["b"])) if len(joined) > 3 else float("nan")
            jsc = score_nets((joined["a"] + joined["b"]).to_numpy(float))
            max_sim = 2 if shared else 1
            same_sleeve = sleeve_a == sleeve_b
            # Prior-opposed across index sleeves: hold one HP/session until joint cleared
            prior_opposed = ("prior_opposed" in str(ra["book"])) and (
                "prior_opposed" in str(rb["book"])
            )
            gate = "PASS"
            if same_sleeve:
                gate = "FAIL_SAME_SLEEVE_STACK"
            elif prior_opposed and shared:
                gate = "HOLD_ONE_HP_PER_SESSION"
            rows.append(
                {
                    "book_a": ra["book"],
                    "cond_a": "%s=%s" % (ra["condition"], ra["bucket"]),
                    "book_b": rb["book"],
                    "cond_b": "%s=%s" % (rb["condition"], rb["bucket"]),
                    "sleeve_a": sleeve_a,
                    "sleeve_b": sleeve_b,
                    "same_sleeve": same_sleeve,
                    "shared_hp_dates": len(shared),
                    "same_dir_rate": (same_dir / both) if both else float("nan"),
                    "inc_corr": corr,
                    "inc_joint_net": jsc["net"],
                    "inc_joint_stress": jsc["stress"],
                    "inc_joint_ns": jsc["ns"],
                    "inc_joint_mtm_dd": jsc["max_dd"],
                    "worst_simultaneous_loss": min(joint_day) if joint_day else float("nan"),
                    "max_simultaneous_hp": max_sim,
                    "gate": gate,
                }
            )
    return pd.DataFrame(rows)


def write_live_plan(results: List[dict], portfolio: pd.DataFrame) -> None:
    """Write tiered LIVE_PLAN + rules. Canonical prose lives in DEPLOYMENT_PLAN.md."""
    LIVE_HUB.mkdir(parents=True, exist_ok=True)
    validated = [r for r in results if r["decision"] == "SIZE-UP VALIDATED"]
    provisional = [r for r in results if r["decision"] == "PROVISIONAL PAPER"]
    shadow = [r for r in results if r["decision"] == "RISK-BUDGET PROFILE"]
    camp = pd.read_csv(PROFILE_HUB / "all_campaigns.csv")
    by_sleeve: Dict[str, list] = {}
    for r in validated:
        sub = camp[camp["book"] == r["book"]]
        sleeve = str(sub["sleeve"].iloc[0]) if len(sub) and "sleeve" in sub.columns else "?"
        by_sleeve.setdefault(sleeve, []).append(r)
    final = []
    for _sleeve, group in by_sleeve.items():
        # One HP multiplier per economic index sleeve
        best = max(group, key=lambda x: float(x.get("sleeve_inc_ns") or 0.0))
        final.append(best)
        for g in group:
            if g is not best:
                g["decision"] = "NOT VALIDATED"
                g["portfolio_note"] = "same_sleeve_superseded_by_%s" % best["slug"]

    def _rule(r: dict, tier: str) -> dict:
        return {
            "book": r["book"],
            "condition": r["condition"],
            "bucket": str(r["bucket"]),
            "multiplier": 1.25,
            "decision": r["decision"],
            "tier": tier,
            "p_placebo": r.get("p_placebo_inc_ns"),
            "p_shift": r.get("p_shift_inc_ns"),
            "p_master": r.get("p_master_inc_ns"),
        }

    tier_a = [_rule(r, "A") for r in final]
    tier_b = [_rule(r, "B") for r in provisional]
    tier_c = [
        {
            "book": r["book"],
            "condition": r["condition"],
            "bucket": str(r["bucket"]),
            "decision": "RISK-BUDGET PROFILE",
            "tier": "C",
        }
        for r in shadow
    ]

    rules_doc = {
        "study": STUDY,
        "base_multiplier": 1.0,
        "hp_extra": 0.25,
        "stated_multiplier": 1.25,
        "tiers": {
            "A_paper": tier_a,
            "B_provisional_paper": tier_b,
            "C_shadow_only": tier_c,
        },
        "rules": tier_a,
        "notes": [
            "Only SIZE-UP VALIDATED @ exact 1.25× is Tier A paper.",
            "Tier B provisional paper @ 1.25×; retain baseline + incremental ledger.",
            "Tier C shadow profile only — no size change.",
            "Do not infer 1.5×/2×/3×/4× from a 1.25× pass.",
            "At most one prior-opposed HP multiplier across ES/YM/NQ per session until overlap gate clears.",
            "Do not stack yet.",
        ],
    }
    lines_y = [
        "study: %s" % STUDY,
        "base_multiplier: 1.0",
        "hp_extra: 0.25",
        "stated_multiplier: 1.25",
        "rules:",
    ]
    for r in tier_a:
        lines_y.append("  - book: %s" % r["book"])
        lines_y.append("    condition: %s" % json.dumps(r["condition"]))
        lines_y.append("    bucket: %s" % json.dumps(str(r["bucket"])))
        lines_y.append("    multiplier: 1.25")
        lines_y.append("    decision: SIZE-UP VALIDATED")
        lines_y.append("    tier: A")
    lines_y.append("notes:")
    for n in rules_doc["notes"]:
        lines_y.append("  - %s" % json.dumps(n))
    (LIVE_HUB / "hp_size_rules.yaml").write_text("\n".join(lines_y) + "\n", encoding="utf-8")
    (LIVE_HUB / "hp_size_rules.json").write_text(json.dumps(rules_doc, indent=2), encoding="utf-8")

    lines = [
        "# Futures HP live plan",
        "",
        "Study: `%s`" % STUDY,
        "",
        "Only **exact 1.25×** has null-suite standing. No 1.5×/2×/3×/4× inferred from a",
        "1.25× pass (see `COMPARISON.md` for sensitivity).",
        "",
        "Full rollout contract: [`DEPLOYMENT_PLAN.md`](DEPLOYMENT_PLAN.md).",
        "",
        "## Tier A — paper 1.25× (SIZE-UP VALIDATED)",
        "",
    ]
    if not tier_a:
        lines.append("_None — no SIZE-UP VALIDATED survivors after portfolio sleeve gate._")
    else:
        lines.append("| book | condition=bucket | mult | p_plac | p_shift | p_master |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for r in tier_a:
            lines.append(
                "| %s | %s=%s | 1.25× | %.3f | %.3f | %.3f |"
                % (
                    r["book"],
                    r["condition"],
                    r["bucket"],
                    float(r["p_placebo"] or 1),
                    float(r["p_shift"] or 1),
                    float(r["p_master"] or 1),
                )
            )
    lines.extend(["", "## Tier B — provisional paper 1.25×", ""])
    if not tier_b:
        lines.append("_None._")
    else:
        lines.append("| book | condition=bucket | mult | p_plac | p_shift | p_master |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for r in tier_b:
            lines.append(
                "| %s | %s=%s | 1.25× | %.3f | %.3f | %.3f |"
                % (
                    r["book"],
                    r["condition"],
                    r["bucket"],
                    float(r["p_placebo"] or 1),
                    float(r["p_shift"] or 1),
                    float(r["p_master"] or 1),
                )
            )
    lines.extend(["", "## Tier C — shadow profile only", ""])
    if not tier_c:
        lines.append("_None._")
    else:
        lines.append("| book | condition=bucket |")
        lines.append("|---|---|")
        for r in tier_c:
            lines.append("| %s | %s=%s |" % (r["book"], r["condition"], r["bucket"]))
    lines.extend(
        [
            "",
            "## No action",
            "",
            "All NOT VALIDATED shortlist rows.",
            "",
            "## Portfolio rules",
            "",
            "- **At most one prior-opposed HP multiplier across ES/YM/NQ per session** until",
            "  the incremental-sleeve overlap report clears simultaneous boosts",
            "  (`prior_opposed_overlap_report.csv`).",
            "- One HP multiplier per economic index sleeve (no NQ+MNQ / YM+MYM / ES+MES).",
            "- No same-regime ST+PMC stacking without a separate overlap pass.",
            "- Tier A/B: keep 1.0× baseline ledger + book incremental 0.25× separately;",
            "  **do not stack** yet.",
            "- Tier C: annotate only — no size change.",
            "",
            "## Artifacts",
            "",
            "- `hp_size_rules.yaml` / `hp_size_rules.json`",
            "- `COMPARISON.md` / `size_sensitivity.csv`",
            "- `prior_opposed_overlap_report.csv`",
            "- `DEPLOYMENT_PLAN.md`",
            "",
        ]
    )
    (LIVE_HUB / "LIVE_PLAN.md").write_text("\n".join(lines), encoding="utf-8")
    # Keep deployment contract stable across null re-runs if already present;
    # regenerate only when missing so agents always have the full checklist.
    deploy = LIVE_HUB / "DEPLOYMENT_PLAN.md"
    if not deploy.exists():
        deploy.write_text(
            "\n".join(
                [
                    "# Futures HP deployment plan (`%s`)" % STUDY,
                    "",
                    "See LIVE_PLAN.md tiers. Regenerate prose via skill",
                    "`potions-futures-intraday-hp-sizeup` / compare driver.",
                    "",
                ]
            ),
            encoding="utf-8",
        )


def run(
    *,
    email: bool = False,
    n_placebo: int = 5000,
    n_shift: int = 1000,
    n_master: int = 500,
    n_wf_placebo: int = 500,
    seed: int = SEED,
    max_pairs: Optional[int] = None,
) -> Path:
    _patch_fx_globals()
    NULLS_HUB.mkdir(parents=True, exist_ok=True)
    (NULLS_HUB / "PROGRESS.log").write_text("", encoding="utf-8")
    _progress("START %s matched-added-exposure @ 1.25×" % STUDY)

    campaigns = pd.read_csv(PROFILE_HUB / "all_campaigns.csv")
    campaigns["entry_ts"] = pd.to_datetime(campaigns["entry_ts"], utc=True)
    if "session_date" not in campaigns.columns:
        campaigns["session_date"] = pd.to_datetime(campaigns["entry_ts"], utc=True).dt.strftime("%Y-%m-%d")
    if "direction" not in campaigns.columns:
        campaigns["direction"] = np.where(campaigns["side"].astype(str) == "long", 1, -1)
    if "sleeve" not in campaigns.columns and "symbol" in campaigns.columns:
        campaigns["sleeve"] = campaigns["symbol"].map(lambda s: SLEEVE.get(str(s).upper(), str(s).lower()))

    notables = pd.read_csv(PROFILE_HUB / "notables.csv") if (PROFILE_HUB / "notables.csv").exists() else pd.DataFrame()
    singles = overlay.select_single_book_hits(notables) if not notables.empty else pd.DataFrame()
    crosses = overlay.select_cross_book_hits(notables, min_books=2) if not notables.empty else pd.DataFrame()

    pairs = load_shortlist_pairs()
    if max_pairs is not None:
        pairs = pairs[: max_pairs]
    _progress("pairs=%d (from shortlist)" % len(pairs))

    results: List[dict] = []
    try:
        for i, (book, cond, bucket) in enumerate(pairs):
            res = evaluate_pair(
                campaigns,
                notables if not notables.empty else pd.DataFrame(columns=["book", "condition", "bucket"]),
                singles,
                crosses,
                book=book,
                condition=cond,
                bucket=bucket,
                extra=EXTRA_SIZE,
                n_placebo=n_placebo,
                n_shift=n_shift,
                n_master=n_master,
                n_wf_placebo=n_wf_placebo,
                seed=seed + i * 17,
            )
            # Alias borderline → provisional paper for futures brief labels
            if res["decision"] == "BORDERLINE PAPER":
                res["decision"] = "PROVISIONAL PAPER"
            # Copy pair artifacts to brief names
            pair_dir = NULLS_HUB / "pairs" / res["slug"]
            for src, dst in (
                ("null_placebo.csv", "matched_placebo.csv"),
                ("null_shift.csv", "clustered_shift.csv"),
                ("null_master.csv", "master_null.csv"),
                ("walk_forward.csv", "nested_walk_forward.csv"),
            ):
                sp = pair_dir / src
                if sp.exists():
                    (pair_dir / dst).write_bytes(sp.read_bytes())
            results.append(res)
    except Exception:
        _progress("CRASH\n" + traceback.format_exc())
        if email:
            send_email(
                subject="potions: futures HP size-up CRASH",
                body="hub=%s\n%s" % (NULLS_HUB, traceback.format_exc()[-2500:]),
            )
        raise

    # Portfolio gate
    portfolio = portfolio_overlap_gate(results, campaigns)
    portfolio.to_csv(NULLS_HUB / "portfolio_overlap.csv", index=False)

    # Apply sleeve uniqueness to decisions before reports
    write_live_plan(results, portfolio)

    # Pair decisions table
    dec_rows = []
    for r in results:
        dec_rows.append(
            {
                "decision": r["decision"],
                "book": r["book"],
                "condition": r["condition"],
                "bucket": r["bucket"],
                "mult": r["size_mult"],
                "hp_pct": 100.0 * r["boost_frac"],
                "inc_net": r["sleeve_inc_net"],
                "inc_ns": r["sleeve_inc_ns"],
                "p_placebo": r.get("p_placebo_inc_ns"),
                "p_shift": r.get("p_shift_inc_ns"),
                "p_master": r.get("p_master_inc_ns"),
                "wf_pos_frac": r.get("wf_frac_pos_delta"),
                "slug": r["slug"],
            }
        )
    pd.DataFrame(dec_rows).to_csv(NULLS_HUB / "pair_decisions.csv", index=False)

    # Rebind HUB for write_hub_reports
    fxnulls.HUB = NULLS_HUB
    summary = render_summary(results, pd.DataFrame())
    # Retitle
    summary = summary.replace(
        "# Matched-added-exposure validation suite",
        "# Futures HP size-up nulls (`%s`)" % STUDY,
    )
    summary = summary.replace("BORDERLINE PAPER", "PROVISIONAL PAPER")
    (NULLS_HUB / "SUMMARY.md").write_text(summary, encoding="utf-8")

    body = phone_email(results, pd.DataFrame())
    body = body.replace("BORDERLINE PAPER", "PROVISIONAL PAPER")
    body = "Study: %s\nHub: live/state/futures_intraday_hp_sizeup_nulls/\n\n" % STUDY + body
    validated_n = sum(1 for r in results if r["decision"] == "SIZE-UP VALIDATED")
    body += "\nPortfolio: see portfolio_overlap.csv; LIVE_PLAN only keeps sleeve-unique VALIDATED.\n"
    body += "Stance: %d SIZE-UP VALIDATED @1.25× only — no 1.5×/2× inference.\n" % validated_n
    (NULLS_HUB / "EMAIL.txt").write_text(body, encoding="utf-8")

    meta = {
        "study": STUDY,
        "n_placebo": n_placebo,
        "n_shift": n_shift,
        "n_master": n_master,
        "extra": EXTRA_SIZE,
        "n_pairs": len(results),
        "n_validated": validated_n,
        "seed": seed,
    }
    (NULLS_HUB / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (NULLS_HUB / "RUN_COMPLETE.json").write_text(
        json.dumps({"ok": True, **meta}, indent=2), encoding="utf-8"
    )

    if email:
        send_email(subject="potions: futures HP size-up nulls complete", body=body)
    _progress("DONE validated=%d" % validated_n)
    return NULLS_HUB / "SUMMARY.md"


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", action="store_true")
    p.add_argument("--n-placebo", type=int, default=5000)
    p.add_argument("--n-shift", type=int, default=1000)
    p.add_argument("--n-master", type=int, default=500)
    p.add_argument("--n-wf-placebo", type=int, default=500)
    p.add_argument("--max-pairs", type=int, default=None, help="smoke: limit shortlist pairs")
    p.add_argument("--seed", type=int, default=SEED)
    args = p.parse_args(argv)
    run(
        email=args.email,
        n_placebo=args.n_placebo,
        n_shift=args.n_shift,
        n_master=args.n_master,
        n_wf_placebo=args.n_wf_placebo,
        seed=args.seed,
        max_pairs=args.max_pairs,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
