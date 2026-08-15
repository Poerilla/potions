"""Futures HP size-up null suite (futures_intraday_hp_sizeup_v1).

Default: shortlist @ 1.25× → `futures_intraday_hp_sizeup_nulls/`.
`--predeclared-2x`: Tier A/B pairs @ exact 2× → separate hub
`futures_intraday_hp_sizeup_nulls_2x/` (does not overwrite 1.25× LIVE_PLAN).

Reuses matched-placebo / clustered-shift / master-null / nested WF from the FX
framework with futures condition columns and portfolio sleeve gates.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.futures_intraday_hp_sizeup_nulls --email
  python -m live.futures_intraday_hp_sizeup_nulls --predeclared-2x --email
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
    NULLS_HUB_2X,
    PHASE3_1_25,
    PREDECLARED_2X,
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
    "RISK-BUDGET PROFILE": "RISK THROTTLE",
}

EXTRA_2X = 1.0  # → stated 2.0×


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


def _progress(msg: str, *, hub: Path = NULLS_HUB) -> None:
    hub.mkdir(parents=True, exist_ok=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as f:
        f.write(msg.rstrip() + "\n")
    try:
        print(msg, flush=True)
    except BrokenPipeError:
        # tee/pipe closed mid-run — keep computing; PROGRESS.log already updated
        pass


def _write_2x_plan(results: List[dict], portfolio: pd.DataFrame, hub: Path) -> None:
    """Write 2× decisions under the 2× hub only — never clobber 1.25× LIVE_PLAN."""
    hub.mkdir(parents=True, exist_ok=True)
    validated = [r for r in results if r["decision"] == "SIZE-UP VALIDATED"]
    provisional = [r for r in results if r["decision"] == "PROVISIONAL PAPER"]
    shadow = [
        r
        for r in results
        if r["decision"] in ("RISK THROTTLE", "RISK-BUDGET PROFILE")
    ]
    rows = []
    for r in results:
        rows.append(
            {
                "decision": r["decision"],
                "book": r["book"],
                "condition": r["condition"],
                "bucket": r["bucket"],
                "mult": r["size_mult"],
                "p_placebo": r.get("p_placebo_delta_ns", r.get("p_placebo_inc_ns")),
                "p_shift": r.get("p_shift_delta_ns", r.get("p_shift_inc_ns")),
                "p_master": r.get("p_master_delta_ns", r.get("p_master_inc_ns")),
                "slug": r["slug"],
            }
        )
    pd.DataFrame(rows).to_csv(hub / "pair_decisions.csv", index=False)
    doc = {
        "study": STUDY,
        "base_multiplier": 1.0,
        "hp_extra": EXTRA_2X,
        "stated_multiplier": 2.0,
        "predeclared_pairs": [
            {"book": b, "condition": c, "bucket": k} for b, c, k in PREDECLARED_2X
        ],
        "validated": [
            {"book": r["book"], "condition": r["condition"], "bucket": r["bucket"]}
            for r in validated
        ],
        "provisional": [
            {"book": r["book"], "condition": r["condition"], "bucket": r["bucket"]}
            for r in provisional
        ],
        "risk_budget": [
            {"book": r["book"], "condition": r["condition"], "bucket": r["bucket"]}
            for r in shadow
        ],
        "notes": [
            "Exact 2× null suite only — independent of 1.25× standing.",
            "Does not authorize LIVE_PLAN changes; promote only after review.",
            "At most one prior-opposed HP multiplier across ES/YM/NQ per session until overlap clears.",
        ],
    }
    (hub / "hp_size_rules_2x.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    lines = [
        "# Futures HP 2× null suite (predeclared)",
        "",
        "Study: `%s`" % STUDY,
        "Hub: `live/state/futures_intraday_hp_sizeup_nulls_2x/`",
        "",
        "Predeclared before run (Tier A/B @ 1.25×): ES ST-age>180m, YM overnight-middle,",
        "NQ OR-norm. **Exact 2×** matched-added-exposure only — no inference from 1.25×.",
        "",
        "## Results",
        "",
        "| decision | book | condition=bucket | mult | p_plac | p_shift | p_master |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for r in results:
        lines.append(
            "| %s | %s | %s=%s | %.2f× | %.3f | %.3f | %.3f |"
            % (
                r["decision"],
                r["book"],
                r["condition"],
                r["bucket"],
                float(r["size_mult"]),
                float(r.get("p_placebo_delta_ns") or r.get("p_placebo_inc_ns") or 1),
                float(r.get("p_shift_delta_ns") or r.get("p_shift_inc_ns") or 1),
                float(r.get("p_master_delta_ns") or r.get("p_master_inc_ns") or 1),
            )
        )
    lines.extend(
        [
            "",
            "## Portfolio overlap",
            "",
            "See `portfolio_overlap.csv`.",
            "",
            "## Stance",
            "",
            "- SIZE-UP VALIDATED @ 2× → candidate for separate 2× paper review (not auto-deploy).",
            "- Does **not** rewrite `futures_intraday_hp_live_plan/` (1.25× remains canonical).",
            "",
        ]
    )
    (hub / "SUMMARY_2X_PLAN.md").write_text("\n".join(lines), encoding="utf-8")
    if not portfolio.empty:
        portfolio.to_csv(hub / "portfolio_overlap.csv", index=False)


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
            extra_a = float(ra.get("size_mult") or 1.25) - 1.0
            extra_b = float(rb.get("size_mult") or 1.25) - 1.0
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
                        extra_a * float(sa["net_usd"].sum()) + extra_b * float(sb["net_usd"].sum())
                    )

            def _daily_inc(df, mask, extra: float):
                inc = np.zeros(len(df))
                inc[mask] = float(extra) * df["net_usd"].to_numpy(float)[mask]
                tmp = df[["session_date"]].copy()
                tmp["inc"] = inc
                return tmp.groupby("session_date")["inc"].sum()

            da = _daily_inc(dfa, ma, extra_a)
            db = _daily_inc(dfb, mb, extra_b)
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
    shadow = [
        r
        for r in results
        if r["decision"] in ("RISK THROTTLE", "RISK-BUDGET PROFILE")
    ]
    camp = pd.read_csv(PROFILE_HUB / "all_campaigns.csv")
    by_sleeve: Dict[str, list] = {}
    for r in validated:
        sub = camp[camp["book"] == r["book"]]
        sleeve = str(sub["sleeve"].iloc[0]) if len(sub) and "sleeve" in sub.columns else "?"
        by_sleeve.setdefault(sleeve, []).append(r)
    final = []
    for _sleeve, group in by_sleeve.items():
        # One HP multiplier per economic index sleeve
        best = max(group, key=lambda x: float(x.get("sleeve_delta_ns") or x.get("sleeve_inc_ns") or 0.0))
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
            "p_placebo": r.get("p_placebo_delta_ns", r.get("p_placebo_inc_ns")),
            "p_shift": r.get("p_shift_delta_ns", r.get("p_shift_inc_ns")),
            "p_master": r.get("p_master_delta_ns", r.get("p_master_inc_ns")),
            "delta_ns": r.get("sleeve_delta_ns"),
        }

    tier_a = [_rule(r, "A") for r in final]
    tier_b = [_rule(r, "B") for r in provisional]
    tier_c = [
        {
            "book": r["book"],
            "condition": r["condition"],
            "bucket": str(r["bucket"]),
            "decision": "RISK THROTTLE",
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
    predeclared_2x: bool = False,
    phase3: bool = False,
    pairs_override: Optional[Sequence[Tuple[str, str, str]]] = None,
    hub_override: Optional[Path] = None,
    profile_hub: Optional[Path] = None,
    write_plan: bool = True,
) -> Path:
    hub = hub_override or (NULLS_HUB_2X if predeclared_2x else NULLS_HUB)
    extra = EXTRA_2X if predeclared_2x else EXTRA_SIZE
    size_mult = 1.0 + extra
    profile = profile_hub or PROFILE_HUB

    _patch_fx_globals()
    # Allow add-on studies to point at a dedicated profile hub
    if profile_hub is not None:
        fxnulls.PROFILE_HUB = profile
        fxnulls.OVERLAY_HUB = profile
        overlay.PROFILE_HUB = profile
    # Point pair artifact writer at the active hub (1.25× or 2×)
    fxnulls.HUB = hub
    hub.mkdir(parents=True, exist_ok=True)
    (hub / "PROGRESS.log").write_text("", encoding="utf-8")
    _progress(
        "START %s matched-added-exposure @ %.2f× hub=%s"
        % (STUDY, size_mult, hub.name),
        hub=hub,
    )

    campaigns = pd.read_csv(profile / "all_campaigns.csv")
    campaigns["entry_ts"] = pd.to_datetime(campaigns["entry_ts"], utc=True)
    if "session_date" not in campaigns.columns:
        campaigns["session_date"] = pd.to_datetime(campaigns["entry_ts"], utc=True).dt.strftime("%Y-%m-%d")
    if "direction" not in campaigns.columns:
        campaigns["direction"] = np.where(campaigns["side"].astype(str) == "long", 1, -1)
    if "sleeve" not in campaigns.columns and "symbol" in campaigns.columns:
        campaigns["sleeve"] = campaigns["symbol"].map(lambda s: SLEEVE.get(str(s).upper(), str(s).lower()))

    notables = pd.read_csv(profile / "notables.csv") if (profile / "notables.csv").exists() else pd.DataFrame()
    singles = overlay.select_single_book_hits(notables) if not notables.empty else pd.DataFrame()
    crosses = overlay.select_cross_book_hits(notables, min_books=2) if not notables.empty else pd.DataFrame()

    if pairs_override:
        pairs = list(pairs_override)
        _progress("pairs_override n=%d" % len(pairs), hub=hub)
    elif predeclared_2x:
        pairs = list(PREDECLARED_2X)
        _progress(
            "predeclared_2x pairs=%d: %s"
            % (len(pairs), "; ".join("%s/%s=%s" % p for p in pairs)),
            hub=hub,
        )
    elif phase3:
        pairs = list(PHASE3_1_25)
        _progress(
            "phase3_1_25 pairs=%d: %s"
            % (len(pairs), "; ".join("%s/%s=%s" % p for p in pairs)),
            hub=hub,
        )
    else:
        # Prefer shortlist under the active profile hub
        short_path = profile / "shortlist.csv"
        if short_path.exists():
            sl = pd.read_csv(short_path)
            pairs = [
                (str(r["book"]), str(r["condition"]), str(r["bucket"]))
                for _, r in sl.iterrows()
            ]
        else:
            pairs = load_shortlist_pairs()
        if max_pairs is not None:
            pairs = pairs[: max_pairs]
        _progress("pairs=%d (from shortlist)" % len(pairs), hub=hub)

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
                extra=extra,
                n_placebo=n_placebo,
                n_shift=n_shift,
                n_master=n_master,
                n_wf_placebo=n_wf_placebo,
                seed=seed + i * 17,
            )
            # Alias labels for futures brief
            res["decision"] = DECISION_ALIAS.get(res["decision"], res["decision"])
            # Copy pair artifacts to brief names
            pair_dir = hub / "pairs" / res["slug"]
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
            _progress(
                "  → %s @ %.2f× decision=%s"
                % (res["slug"], float(res["size_mult"]), res["decision"]),
                hub=hub,
            )
    except Exception:
        _progress("CRASH\n" + traceback.format_exc(), hub=hub)
        if email:
            send_email(
                subject="potions: futures HP size-up%s CRASH"
                % (" 2×" if predeclared_2x else ""),
                body="hub=%s\n%s" % (hub, traceback.format_exc()[-2500:]),
            )
        raise

    # Portfolio gate
    portfolio = portfolio_overlap_gate(results, campaigns)
    portfolio.to_csv(hub / "portfolio_overlap.csv", index=False)

    if predeclared_2x:
        _write_2x_plan(results, portfolio, hub)
    elif write_plan:
        # Apply sleeve uniqueness to decisions before reports (1.25× LIVE_PLAN only)
        write_live_plan(results, portfolio)
    else:
        _progress("skip write_live_plan (add-on / hub_override)", hub=hub)

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
                "delta_ns": r.get("sleeve_delta_ns"),
                "p_placebo": r.get("p_placebo_delta_ns", r.get("p_placebo_inc_ns")),
                "p_shift": r.get("p_shift_delta_ns", r.get("p_shift_inc_ns")),
                "p_master": r.get("p_master_delta_ns", r.get("p_master_inc_ns")),
                "wf_pos_frac": r.get("wf_frac_pos_delta"),
                "slug": r["slug"],
            }
        )
    pd.DataFrame(dec_rows).to_csv(hub / "pair_decisions.csv", index=False)

    # Rebind HUB for write_hub_reports / render_summary paths that read fxnulls.HUB
    fxnulls.HUB = hub
    summary = render_summary(results, pd.DataFrame())
    # Retitle
    title = (
        "# Futures HP size-up nulls @ 2× (`%s`, predeclared)" % STUDY
        if predeclared_2x
        else "# Futures HP size-up nulls (`%s`)" % STUDY
    )
    summary = summary.replace("# Matched-added-exposure validation suite", title)
    summary = summary.replace("BORDERLINE PAPER", "PROVISIONAL PAPER")
    (hub / "SUMMARY.md").write_text(summary, encoding="utf-8")

    body = phone_email(results, pd.DataFrame())
    body = body.replace("BORDERLINE PAPER", "PROVISIONAL PAPER")
    hub_rel = "live/state/%s/" % hub.name
    body = "Study: %s\nHub: %s\nMultiplier: %.2f×\n\n" % (STUDY, hub_rel, size_mult) + body
    validated_n = sum(1 for r in results if r["decision"] == "SIZE-UP VALIDATED")
    body += "\nPortfolio: see portfolio_overlap.csv.\n"
    if predeclared_2x:
        body += (
            "Stance: %d SIZE-UP VALIDATED @ exact 2× (predeclared Tier A/B). "
            "Does not rewrite 1.25× LIVE_PLAN.\n" % validated_n
        )
    else:
        body += "Stance: %d SIZE-UP VALIDATED @1.25× only — no 1.5×/2× inference.\n" % validated_n
    (hub / "EMAIL.txt").write_text(body, encoding="utf-8")

    meta = {
        "study": STUDY,
        "n_placebo": n_placebo,
        "n_shift": n_shift,
        "n_master": n_master,
        "extra": extra,
        "stated_multiplier": size_mult,
        "predeclared_2x": bool(predeclared_2x),
        "n_pairs": len(results),
        "n_validated": validated_n,
        "seed": seed,
        "hub": str(hub),
    }
    (hub / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (hub / "RUN_COMPLETE.json").write_text(
        json.dumps({"ok": True, **meta}, indent=2), encoding="utf-8"
    )

    if email:
        subj = (
            "potions: futures HP size-up nulls @2× complete"
            if predeclared_2x
            else "potions: futures HP size-up nulls complete"
        )
        send_email(subject=subj, body=body)
    _progress("DONE validated=%d @ %.2f×" % (validated_n, size_mult), hub=hub)
    return hub / "SUMMARY.md"


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", action="store_true")
    p.add_argument(
        "--predeclared-2x",
        action="store_true",
        help="Tier A/B pairs @ exact 2× into futures_intraday_hp_sizeup_nulls_2x/",
    )
    p.add_argument(
        "--phase3",
        action="store_true",
        help="NQ/ES/YM prior-opposed Phase-3 pairs @ 1.25× under ΔN/S objective",
    )
    p.add_argument(
        "--pair",
        action="append",
        default=[],
        help="book:Condition:bucket (repeatable); overrides shortlist",
    )
    p.add_argument("--n-placebo", type=int, default=5000)
    p.add_argument("--n-shift", type=int, default=1000)
    p.add_argument("--n-master", type=int, default=500)
    p.add_argument("--n-wf-placebo", type=int, default=500)
    p.add_argument("--max-pairs", type=int, default=None, help="smoke: limit shortlist pairs")
    p.add_argument("--seed", type=int, default=SEED)
    args = p.parse_args(argv)
    pairs_override = None
    if args.pair:
        pairs_override = []
        for raw in args.pair:
            parts = str(raw).split(":")
            if len(parts) != 3:
                raise SystemExit("bad --pair %r (want book:Condition:bucket)" % raw)
            pairs_override.append((parts[0], parts[1], parts[2]))
    run(
        email=args.email,
        n_placebo=args.n_placebo,
        n_shift=args.n_shift,
        n_master=args.n_master,
        n_wf_placebo=args.n_wf_placebo,
        seed=args.seed,
        max_pairs=args.max_pairs,
        predeclared_2x=bool(args.predeclared_2x),
        phase3=bool(args.phase3),
        pairs_override=pairs_override,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
