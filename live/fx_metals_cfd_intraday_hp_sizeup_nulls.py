"""FX / metals / CFD HP size-up null suite (Phase 2).

Matched-added-exposure validation on the width-aware profile shortlist and
predeclared width-first priority pairs @ 1.25×.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.fx_metals_cfd_intraday_hp_sizeup_nulls --priority-1-25 --email
  python -m live.fx_metals_cfd_intraday_hp_sizeup_nulls --shortlist --email
  python -m live.fx_metals_cfd_intraday_hp_sizeup_nulls --pair eurusd_st_pmc_3r:Day of week:Thursday --email
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

import live.intraday_condition_overlay as overlay
import live.intraday_hp_sizeup_nulls as fxnulls

from .fx_metals_cfd_intraday_condition_profile_lib import (
    CAUSAL_LIVE_READY,
    COND_COL,
    NEEDS_LIVE_PROXY,
    PHASE2_HUB,
    PROFILE_HUB,
    STUDY as PROFILE_STUDY,
)
from .intraday_condition_overlay import score_nets
from .intraday_hp_sizeup_nulls import (
    EXTRA_SIZE,
    evaluate_pair,
    phone_email,
    render_summary,
)
from .notify_email import send_email

STUDY = "fx_metals_cfd_intraday_hp_sizeup_nulls"
NULLS_HUB = PHASE2_HUB
LIVE_HUB = NULLS_HUB.parent / "fx_metals_cfd_intraday_hp_live_plan"
SEED = 20260812

# One HP multiplier per symbol per session (portfolio rule).
SYMBOL_SLEEVE = {
    "EURUSD": "eurusd",
    "GBPUSD": "gbpusd",
    "USDJPY": "usdjpy",
    "AUDJPY": "audjpy",
    "US30": "us30",
    "NAS100": "nas100",
    "XAUUSD": "xauusd",
    "XAGUSD": "xagusd",
}

DECISION_ALIAS = {
    "BORDERLINE PAPER": "PROVISIONAL PAPER",
    "RISK-BUDGET PROFILE": "RISK THROTTLE",
}

# Width-first null queue (~25 pairs) — analogous to futures NQ or_norm priority.
PRIORITY_1_25: List[Tuple[str, str, str]] = [
    # Monday OR — session range vs ATR
    ("usdjpy_monday_or", "Monday session range vs ATR", "mon_wide"),
    ("us30_monday_or", "Monday session range vs ATR", "mon_wide"),
    ("eurusd_monday_or", "Monday session range vs ATR", "mon_wide"),
    ("gbpusd_monday_or", "Monday session range vs ATR", "mon_wide"),
    ("xauusd_monday_or", "Monday session range vs ATR", "mon_wide"),
    ("usdjpy_monday_or", "Monday session range vs ATR", "mon_norm"),
    ("us30_monday_or", "Prior-day range percentile", "prior_range_exp"),
    ("usdjpy_monday_or", "Prior-day range percentile", "prior_range_norm"),
    # ST+PMC — prior-day range + calendar carry-over
    ("eurusd_st_pmc_3r", "Prior-day range percentile", "prior_range_exp"),
    ("usdjpy_st_pmc_3r", "Prior-day range percentile", "prior_range_exp"),
    ("gbpusd_st_pmc_3r", "Prior-day range percentile", "prior_range_norm"),
    ("us30_st_pmc_3r", "Prior-day range percentile", "prior_range_norm"),
    ("eurusd_st_pmc_3r", "Day of week", "Thursday"),
    ("nas100_st_pmc_3r", "Prior quarter type", "q_break_down"),
    # v2b / London / Asia
    ("us30_london_prior_opposed", "London OR width vs ATR", "lor_norm"),
    ("usdjpy_asia_range", "Prior-day range percentile", "prior_range_norm"),
    ("us30_monday_or", "Entry hour (NY)", "11"),
    # Quarterly breakout — width + HTF
    ("xauusd_quarterly_breakout", "Prior-quarter range width", "pqw_q2"),
    ("audjpy_quarterly_breakout", "Prior-quarter range width", "pqw_q1"),
    ("eurusd_quarterly_breakout", "Prior-day range percentile", "prior_range_comp"),
    ("eurusd_quarterly_breakout", "ATR causal rolling percentile", "atr_pctl_q2"),
    ("gbpusd_quarterly_breakout", "ATR causal rolling percentile", "atr_pctl_q1"),
    ("usdjpy_quarterly_breakout", "ATR causal rolling percentile", "atr_pctl_q4"),
    ("audjpy_quarterly_breakout", "Prior-day range percentile", "prior_range_exp"),
    ("xauusd_quarterly_breakout", "ATR causal rolling percentile", "atr_pctl_q2"),
    ("eurusd_quarterly_breakout", "Prior-quarter range width", "pqw_q2"),
]


def _patch_fx_globals() -> None:
    """Point FX nulls/overlay at FX/metals/CFD profile hubs + condition maps."""
    fxnulls.HUB = NULLS_HUB
    fxnulls.OVERLAY_HUB = PROFILE_HUB
    fxnulls.PROFILE_HUB = PROFILE_HUB
    overlay.PROFILE_HUB = PROFILE_HUB
    overlay.COND_COL.clear()
    overlay.COND_COL.update(COND_COL)
    overlay.CAUSAL_LIVE_READY.clear()
    overlay.CAUSAL_LIVE_READY.update(CAUSAL_LIVE_READY)
    overlay.NEEDS_LIVE_PROXY.clear()
    overlay.NEEDS_LIVE_PROXY.update(NEEDS_LIVE_PROXY)
    fxnulls._causal = lambda condition: (
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
        pass


def _book_sleeve(df: pd.DataFrame) -> str:
    if "sleeve" in df.columns and len(df):
        return str(df["sleeve"].iloc[0])
    if "symbol" in df.columns and len(df):
        sym = str(df["symbol"].iloc[0]).upper()
        return SYMBOL_SLEEVE.get(sym, sym.lower())
    return "?"


def write_frozen_compare(
    hub: Path,
    campaigns: pd.DataFrame,
    book: str,
    condition: str,
    bucket: str,
) -> pd.DataFrame:
    """1.00× vs 1.25× sensitivity for a single frozen candidate (not validation)."""
    df = campaigns[campaigns["book"] == book].sort_values("entry_ts").reset_index(drop=True)
    m = overlay.hp_mask(df, condition, bucket)
    base = df["net_usd"].to_numpy(float)
    base_sc = score_nets(base)
    rows: List[dict] = []
    for mult in (1.0, 1.25):
        sized = base.copy()
        if float(mult) != 1.0:
            sized[m] = sized[m] * float(mult)
        sc = score_nets(sized)
        rows.append(
            {
                "book": book,
                "condition": condition,
                "bucket": bucket,
                "mult": float(mult),
                "hp_n": int(m.sum()),
                "hp_pct": round(100.0 * float(m.mean()), 2),
                "net": round(sc["net"], 2),
                "stress": round(sc["stress"], 2),
                "ns": round(sc["ns"], 3),
                "max_dd": round(sc["max_dd"], 2),
                "delta_net": round(sc["net"] - base_sc["net"], 2),
                "delta_ns": round(sc["ns"] - base_sc["ns"], 3),
            }
        )
    out = pd.DataFrame(rows)
    out.to_csv(hub / "compare_1x_1_25x.csv", index=False)
    lines = [
        "# Frozen compare — 1.00× vs 1.25× (sensitivity, not validation)",
        "",
        "| mult | hp n | hp % | net | stress | N/S | Δnet | ΔN/S |",
        "|------|------|------|-----|--------|-----|------|------|",
    ]
    for r in rows:
        lines.append(
            "| %.2f× | %d | %.0f%% | %.0f | %.0f | %.2f | %.0f | %.2f |"
            % (r["mult"], r["hp_n"], r["hp_pct"], r["net"], r["stress"], r["ns"], r["delta_net"], r["delta_ns"])
        )
    (hub / "COMPARE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def portfolio_overlap_gate(results: List[dict], campaigns: pd.DataFrame) -> pd.DataFrame:
    """Same-symbol stacking + quarterly/intraday overlap on shared HP dates."""
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
                "inc_joint_ns",
                "gate",
            ]
        )

    masks: Dict[str, Tuple[dict, pd.DataFrame, np.ndarray]] = {}
    for r in passing:
        book = r["book"]
        df = campaigns[campaigns["book"] == book].sort_values("entry_ts").reset_index(drop=True)
        m = overlay.hp_mask(df, r["condition"], r["bucket"])
        masks[r["slug"]] = (r, df, m)

    keys = list(masks.keys())
    for i, ka in enumerate(keys):
        ra, dfa, ma = masks[ka]
        sleeve_a = _book_sleeve(dfa)
        dates_a = set(dfa.loc[ma, "session_date"].astype(str)) if "session_date" in dfa.columns else set()
        fam_a = str(dfa["family"].iloc[0]) if "family" in dfa.columns and len(dfa) else ""
        for kb in keys[i + 1 :]:
            rb, dfb, mb = masks[kb]
            sleeve_b = _book_sleeve(dfb)
            dates_b = set(dfb.loc[mb, "session_date"].astype(str)) if "session_date" in dfb.columns else set()
            fam_b = str(dfb["family"].iloc[0]) if "family" in dfb.columns and len(dfb) else ""
            shared = dates_a & dates_b
            extra_a = float(ra.get("size_mult") or 1.25) - 1.0
            extra_b = float(rb.get("size_mult") or 1.25) - 1.0

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
            same_sleeve = sleeve_a == sleeve_b
            qb_mix = ("quarterly_breakout" in fam_a) ^ ("quarterly_breakout" in fam_b)
            gate = "PASS"
            if same_sleeve:
                gate = "FAIL_SAME_SYMBOL_STACK"
            elif same_sleeve is False and qb_mix and shared:
                gate = "HOLD_ONE_HP_PER_SYMBOL"
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
                    "inc_corr": corr,
                    "inc_joint_ns": jsc["ns"],
                    "gate": gate,
                }
            )
    return pd.DataFrame(rows)


def write_live_plan(results: List[dict], portfolio: pd.DataFrame) -> None:
    """Phase 3 hub — tiered LIVE_PLAN after null pass."""
    LIVE_HUB.mkdir(parents=True, exist_ok=True)
    validated = [r for r in results if r["decision"] == "SIZE-UP VALIDATED"]
    provisional = [r for r in results if r["decision"] == "PROVISIONAL PAPER"]
    shadow = [
        r for r in results if r["decision"] in ("RISK THROTTLE", "RISK-BUDGET PROFILE")
    ]
    camp = pd.read_csv(PROFILE_HUB / "all_campaigns.csv")
    by_sleeve: Dict[str, list] = {}
    for r in validated:
        sub = camp[camp["book"] == r["book"]]
        sleeve = _book_sleeve(sub) if len(sub) else "?"
        by_sleeve.setdefault(sleeve, []).append(r)
    final: List[dict] = []
    for _sleeve, group in by_sleeve.items():
        best = max(group, key=lambda x: float(x.get("sleeve_delta_ns") or x.get("sleeve_inc_ns") or 0.0))
        final.append(best)
        for g in group:
            if g is not best:
                g["decision"] = "NOT VALIDATED"
                g["portfolio_note"] = "same_symbol_superseded_by_%s" % best["slug"]

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
        "profile_study": PROFILE_STUDY,
        "base_multiplier": 1.0,
        "hp_extra": 0.25,
        "stated_multiplier": 1.25,
        "tiers": {
            "A_paper": tier_a,
            "B_provisional_paper": tier_b,
            "C_shadow_only": tier_c,
        },
        "notes": [
            "Only SIZE-UP VALIDATED @ exact 1.25× is Tier A paper.",
            "Tier B provisional @ 1.25×; retain baseline + incremental ledger.",
            "Tier C shadow only — no size change.",
            "At most one HP multiplier per symbol per session.",
            "Quarterly breakout + intraday HP on same symbol requires overlap pass.",
            "Do not infer 2×/3× from a 1.25× pass.",
        ],
    }
    (LIVE_HUB / "hp_size_rules.json").write_text(json.dumps(rules_doc, indent=2), encoding="utf-8")

    lines = [
        "# FX / metals / CFD HP live plan (Phase 3)",
        "",
        "Study: `%s` (profile: `%s`)" % (STUDY, PROFILE_STUDY),
        "",
        "Only **exact 1.25×** has null-suite standing.",
        "",
        "## Tier A — paper 1.25× (SIZE-UP VALIDATED)",
        "",
    ]
    if not tier_a:
        lines.append("_None — no SIZE-UP VALIDATED survivors after portfolio gate._")
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
        for r in tier_c:
            lines.append("- %s: %s=%s" % (r["book"], r["condition"], r["bucket"]))
    lines.extend(
        [
            "",
            "## Portfolio rules",
            "",
            "- One HP multiplier per **symbol** per session.",
            "- No quarterly-breakout + intraday HP stacking on same symbol without overlap pass.",
            "- Tier A/B: book baseline 1.0× + incremental 0.25× separately.",
            "",
        ]
    )
    (LIVE_HUB / "LIVE_PLAN.md").write_text("\n".join(lines), encoding="utf-8")


def run(
    *,
    email: bool = False,
    n_placebo: int = 5000,
    n_shift: int = 1000,
    n_master: int = 500,
    n_wf_placebo: int = 500,
    seed: int = SEED,
    max_pairs: Optional[int] = None,
    pairs: Optional[Sequence[Tuple[str, str, str]]] = None,
    use_shortlist: bool = False,
    write_plan: bool = True,
    hub: Optional[Path] = None,
) -> Path:
    hub = Path(hub) if hub is not None else NULLS_HUB
    extra = EXTRA_SIZE
    size_mult = 1.0 + extra

    _patch_fx_globals()
    fxnulls.HUB = hub
    hub.mkdir(parents=True, exist_ok=True)
    (hub / "PROGRESS.log").write_text("", encoding="utf-8")
    _progress("START %s @ %.2f× hub=%s" % (STUDY, size_mult, hub.name), hub=hub)

    campaigns = pd.read_csv(PROFILE_HUB / "all_campaigns.csv")
    campaigns["entry_ts"] = pd.to_datetime(campaigns["entry_ts"], utc=True)
    if "session_date" not in campaigns.columns:
        campaigns["session_date"] = pd.to_datetime(campaigns["entry_ts"], utc=True).dt.strftime("%Y-%m-%d")
    if "direction" not in campaigns.columns:
        campaigns["direction"] = np.where(campaigns["side"].astype(str) == "long", 1, -1)
    if "sleeve" not in campaigns.columns and "symbol" in campaigns.columns:
        campaigns["sleeve"] = campaigns["symbol"].map(
            lambda s: SYMBOL_SLEEVE.get(str(s).upper(), str(s).lower())
        )

    notables = pd.read_csv(PROFILE_HUB / "notables.csv") if (PROFILE_HUB / "notables.csv").exists() else pd.DataFrame()
    singles = overlay.select_single_book_hits(notables) if not notables.empty else pd.DataFrame()
    crosses = overlay.select_cross_book_hits(notables, min_books=2) if not notables.empty else pd.DataFrame()

    if pairs is not None:
        pair_list = list(pairs)
        _progress("explicit pairs n=%d" % len(pair_list), hub=hub)
    elif use_shortlist:
        sl = pd.read_csv(PROFILE_HUB / "shortlist.csv")
        pair_list = [
            (str(r["book"]), str(r["condition"]), str(r["bucket"])) for _, r in sl.iterrows()
        ]
        _progress("shortlist pairs n=%d" % len(pair_list), hub=hub)
    else:
        pair_list = list(PRIORITY_1_25)
        _progress("priority_1_25 pairs n=%d" % len(pair_list), hub=hub)

    if max_pairs is not None:
        pair_list = pair_list[: max_pairs]

    results: List[dict] = []
    try:
        for i, (book, cond, bucket) in enumerate(pair_list):
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
            res["decision"] = DECISION_ALIAS.get(res["decision"], res["decision"])
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
                subject="potions: FX/metals/CFD HP nulls CRASH",
                body="hub=%s\n%s" % (hub, traceback.format_exc()[-2500:]),
            )
        raise

    portfolio = portfolio_overlap_gate(results, campaigns)
    portfolio.to_csv(hub / "portfolio_overlap.csv", index=False)
    if write_plan:
        write_live_plan(results, portfolio)

    if len(pair_list) == 1:
        book, cond, bucket = pair_list[0]
        write_frozen_compare(hub, campaigns, book, cond, bucket)

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
                "delta_ns": r.get("sleeve_delta_ns"),
                "p_placebo": r.get("p_placebo_delta_ns", r.get("p_placebo_inc_ns")),
                "p_shift": r.get("p_shift_delta_ns", r.get("p_shift_inc_ns")),
                "p_master": r.get("p_master_delta_ns", r.get("p_master_inc_ns")),
                "slug": r["slug"],
            }
        )
    pd.DataFrame(dec_rows).to_csv(hub / "pair_decisions.csv", index=False)

    summary = render_summary(results, pd.DataFrame())
    title = "# FX / metals / CFD HP size-up nulls (`%s`)" % STUDY
    summary = summary.replace("# Matched-added-exposure validation suite", title)
    summary = summary.replace("BORDERLINE PAPER", "PROVISIONAL PAPER")
    (hub / "SUMMARY.md").write_text(summary, encoding="utf-8")

    body = phone_email(results, pd.DataFrame())
    body = body.replace("BORDERLINE PAPER", "PROVISIONAL PAPER")
    hub_rel = "live/state/%s/" % hub.name
    validated_n = sum(1 for r in results if r["decision"] == "SIZE-UP VALIDATED")
    prov_n = sum(1 for r in results if r["decision"] == "PROVISIONAL PAPER")
    body = (
        "Study: %s\nProfile: %s\nHub: %s\nMultiplier: %.2f×\nPairs: %d\n\n"
        % (STUDY, PROFILE_STUDY, hub_rel, size_mult, len(results))
        + body
    )
    body += (
        "\nStance: %d SIZE-UP VALIDATED, %d PROVISIONAL @1.25×.\n"
        "Portfolio: portfolio_overlap.csv.\n"
        "Phase 3 plan: live/state/fx_metals_cfd_intraday_hp_live_plan/\n"
        % (validated_n, prov_n)
    )
    (hub / "EMAIL.txt").write_text(body, encoding="utf-8")

    meta = {
        "study": STUDY,
        "profile_study": PROFILE_STUDY,
        "n_placebo": n_placebo,
        "n_shift": n_shift,
        "n_master": n_master,
        "extra": extra,
        "stated_multiplier": size_mult,
        "n_pairs": len(results),
        "n_validated": validated_n,
        "n_provisional": prov_n,
        "seed": seed,
        "hub": str(hub),
    }
    (hub / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (hub / "RUN_COMPLETE.json").write_text(
        json.dumps({"ok": True, **meta}, indent=2), encoding="utf-8"
    )

    if email:
        send_email(subject="potions: FX/metals/CFD HP nulls complete", body=body)
    _progress("DONE validated=%d provisional=%d @ %.2f×" % (validated_n, prov_n, size_mult), hub=hub)
    return hub / "SUMMARY.md"


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", action="store_true")
    p.add_argument(
        "--priority-1-25",
        action="store_true",
        help="Width-first priority queue (%d pairs)" % len(PRIORITY_1_25),
    )
    p.add_argument(
        "--shortlist",
        action="store_true",
        help="All Phase 1 shortlist rows (~44 pairs)",
    )
    p.add_argument(
        "--pair",
        action="append",
        default=[],
        help="book:Condition:bucket (repeatable)",
    )
    p.add_argument("--n-placebo", type=int, default=5000)
    p.add_argument("--n-shift", type=int, default=1000)
    p.add_argument("--n-master", type=int, default=500)
    p.add_argument("--n-wf-placebo", type=int, default=500)
    p.add_argument("--max-pairs", type=int, default=None, help="smoke: limit pairs")
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument(
        "--hub",
        type=str,
        default="",
        help="Override output hub (relative to repo or absolute path)",
    )
    args = p.parse_args(argv)

    pairs: Optional[List[Tuple[str, str, str]]] = None
    use_shortlist = False
    if args.pair:
        pairs = []
        for raw in args.pair:
            parts = str(raw).split(":")
            if len(parts) != 3:
                raise SystemExit("bad --pair %r (want book:Condition:bucket)" % raw)
            pairs.append((parts[0], parts[1], parts[2]))
    elif args.shortlist:
        use_shortlist = True
    elif args.priority_1_25:
        pairs = list(PRIORITY_1_25)
    else:
        pairs = list(PRIORITY_1_25)

    hub_path: Optional[Path] = None
    if args.hub:
        hub_path = Path(args.hub)
        if not hub_path.is_absolute():
            hub_path = Path(__file__).resolve().parent.parent / hub_path

    run(
        email=bool(args.email),
        n_placebo=int(args.n_placebo),
        n_shift=int(args.n_shift),
        n_master=int(args.n_master),
        n_wf_placebo=int(args.n_wf_placebo),
        seed=int(args.seed),
        max_pairs=args.max_pairs,
        pairs=pairs,
        use_shortlist=use_shortlist,
        write_plan=hub_path is None,
        hub=hub_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
