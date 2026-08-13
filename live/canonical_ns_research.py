"""Phase 1 — canonicalize whole-book N/S research artifacts.

Recomputes / backfills a cross-market candidate ledger from **existing**
approved campaign and accounting hubs. Does **not** regenerate signals.

Canonical score (higher better)::

    N/S = forced-flat net / |reachable full-book stress|
    ΔN/S = N/S_candidate − N/S_baseline   (overlays / size-ups)

Hub::

    live/state/canonical_ns_research/
      POLICY.md
      CANDIDATE_LEDGER.csv
      ELIGIBILITY_AUDIT.csv
      BASELINE_REGISTRY.csv
      ECONOMIC_SLEEVE_MAP.csv
      BOARDS.md
      ALL_RESULTS.md
      ALL_RESULTS_WITH_COUPONS.csv
      EMAIL.txt

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.canonical_ns_research --email
"""

from __future__ import annotations

import argparse
import json
import math
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .fx_v2b_london_ungated import REPO
from .notify_email import send_email

HUB = REPO / "live" / "state" / "canonical_ns_research"
MIN_ABS_STRESS = 500.0
MIN_SAMPLE = 30

# Economic sleeves for portfolio HOLD_ONE constraints
SLEEVE_MAP = [
    {"market": "NQ", "economic_sleeve": "nasdaq", "hold_one_group": "NQ/MNQ"},
    {"market": "MNQ", "economic_sleeve": "nasdaq", "hold_one_group": "NQ/MNQ"},
    {"market": "NAS100", "economic_sleeve": "nasdaq", "hold_one_group": "NQ/MNQ"},
    {"market": "YM", "economic_sleeve": "dow", "hold_one_group": "YM/MYM"},
    {"market": "MYM", "economic_sleeve": "dow", "hold_one_group": "YM/MYM"},
    {"market": "US30", "economic_sleeve": "dow", "hold_one_group": "YM/MYM"},
    {"market": "ES", "economic_sleeve": "spx", "hold_one_group": "ES/MES"},
    {"market": "MES", "economic_sleeve": "spx", "hold_one_group": "ES/MES"},
    {"market": "EURUSD", "economic_sleeve": "eurusd", "hold_one_group": "EURUSD"},
    {"market": "USDJPY", "economic_sleeve": "usdjpy", "hold_one_group": "USDJPY"},
    {"market": "GBPUSD", "economic_sleeve": "gbpusd", "hold_one_group": "GBPUSD"},
    {"market": "AUDJPY", "economic_sleeve": "audjpy", "hold_one_group": "AUDJPY"},
    {"market": "XAUUSD", "economic_sleeve": "xau", "hold_one_group": "XAUUSD"},
    {"market": "XAGUSD", "economic_sleeve": "xag", "hold_one_group": "XAGUSD"},
]


def _progress(msg: str) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as f:
        f.write(msg.rstrip() + "\n")
    print(msg, flush=True)


def _safe_float(x: Any, default: float = float("nan")) -> float:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def _ns(net: float, stress: float) -> float:
    s = abs(_safe_float(stress, 0.0))
    if s < 1e-9:
        return float("nan")
    return _safe_float(net, 0.0) / s


def _elig(
    *,
    net: float,
    stress: float,
    sample: float,
    usd_normalized: bool,
    lot_correct: bool,
    causal: bool,
    finite: bool,
    inventory: bool,
) -> Dict[str, Any]:
    reasons: List[str] = []
    if not finite and not inventory:
        reasons.append("indefinite_runner_not_flat")
    if inventory:
        reasons.append("inventory_board_only")
    if not math.isfinite(net) or not math.isfinite(stress):
        reasons.append("non_finite_accounting")
    if abs(stress) < MIN_ABS_STRESS:
        reasons.append("tiny_stress")
    if sample < MIN_SAMPLE:
        reasons.append("thin_sample")
    if net <= 0:
        reasons.append("non_positive_net")
    if not usd_normalized:
        reasons.append("needs_usd_normalize")
    if not lot_correct:
        reasons.append("lot_correct_unverified")
    if not causal:
        reasons.append("causal_unverified")
    # Size-up / overlay rankable on core+overlay boards
    rankable = (
        finite
        and (not inventory)
        and abs(stress) >= MIN_ABS_STRESS
        and sample >= MIN_SAMPLE
        and net > 0
        and usd_normalized
        and lot_correct
        and causal
        and math.isfinite(_ns(net, stress))
    )
    return {
        "rankable": bool(rankable),
        "eligibility_reasons": ";".join(reasons) if reasons else "ok",
    }


def _row(
    *,
    market: str,
    economic_sleeve: str,
    strategy_family: str,
    book_id: str,
    execution_model: str,
    candidate_type: str,
    condition_set: str,
    multiplier: float,
    baseline_net: float,
    baseline_stress: float,
    candidate_net: float,
    candidate_stress: float,
    mtm_dd: float,
    max_open: float,
    eoy_open: float,
    margin: float,
    sample_count: float,
    usd_normalized: bool,
    lot_correct: bool,
    causal: bool,
    finite: bool,
    inventory: bool,
    source_hub: str,
    notes: str = "",
) -> Dict[str, Any]:
    base_ns = _ns(baseline_net, baseline_stress)
    cand_ns = _ns(candidate_net, candidate_stress)
    el = _elig(
        net=candidate_net,
        stress=candidate_stress,
        sample=sample_count,
        usd_normalized=usd_normalized,
        lot_correct=lot_correct,
        causal=causal,
        finite=finite,
        inventory=inventory,
    )
    return {
        "market": market,
        "economic_sleeve": economic_sleeve,
        "strategy_family": strategy_family,
        "book_id": book_id,
        "execution_model": execution_model,
        "candidate_type": candidate_type,
        "condition_set": condition_set,
        "multiplier": multiplier,
        "baseline_net": baseline_net,
        "baseline_reachable_stress": abs(baseline_stress) if math.isfinite(baseline_stress) else float("nan"),
        "baseline_NS": base_ns,
        "candidate_net": candidate_net,
        "candidate_reachable_stress": abs(candidate_stress)
        if math.isfinite(candidate_stress)
        else float("nan"),
        "candidate_NS": cand_ns,
        "delta_net": candidate_net - baseline_net
        if math.isfinite(candidate_net) and math.isfinite(baseline_net)
        else float("nan"),
        "delta_stress": abs(candidate_stress) - abs(baseline_stress)
        if math.isfinite(candidate_stress) and math.isfinite(baseline_stress)
        else float("nan"),
        "delta_NS": cand_ns - base_ns
        if math.isfinite(cand_ns) and math.isfinite(base_ns)
        else float("nan"),
        "MTM_drawdown": mtm_dd,
        "max_open": max_open,
        "EOY_open": eoy_open,
        "margin": margin,
        "sample_count": sample_count,
        "USD_normalized": usd_normalized,
        "lot_correct": lot_correct,
        "causal": causal,
        "rankable": el["rankable"],
        "finite": finite,
        "inventory": inventory,
        "eligibility_reasons": el["eligibility_reasons"],
        "source_hub": source_hub,
        "notes": notes,
    }


def _sleeve_for(market: str) -> str:
    m = market.upper()
    for r in SLEEVE_MAP:
        if r["market"] == m:
            return r["economic_sleeve"]
    return m.lower()


def harvest_runner_variants() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    hubs = [
        (
            REPO / "live/state/fx_index_metals_st_pmc_runner_variants/summary.csv",
            "fx_index_metals_st_pmc_runner_variants",
            True,
            None,
        ),
        (
            REPO / "live/state/us30_st_pmc_runner_variants/summary.csv",
            "us30_st_pmc_runner_variants",
            True,
            "US30",
        ),
        (
            REPO / "live/state/futures_st_pmc_runner_variants/summary.csv",
            "futures_st_pmc_runner_variants",
            True,
            None,
        ),
    ]
    for path, hub_name, lot_ok, default_market in hubs:
        if not path.exists():
            continue
        df = pd.read_csv(path)
        market_col = "market" if "market" in df.columns else (
            "instrument" if "instrument" in df.columns else None
        )
        for _, r in df.iterrows():
            raw_m = r.get(market_col) if market_col else None
            market = str(raw_m or default_market or "?").upper()
            if market in ("?", "NAN", "NONE"):
                market = str(default_market or "?").upper()
            variant = str(r.get("variant") or "")
            net = _safe_float(r.get("net_usd"))
            stress = abs(_safe_float(r.get("stress_dd_usd")))
            sample = _safe_float(r.get("trades", r.get("units")), 0)
            indefinite = "indef" in variant.lower()
            is_3r = "3r" in variant.lower() and "runner" not in variant.lower()
            is_2r10r = "2r" in variant.lower() and "10r" in variant.lower()
            cand_type = "baseline" if is_3r else ("runner" if indefinite else "filter")
            if is_2r10r:
                cand_type = "runner"
            # Native JPY rows need USD normalize flag
            usd_ok = market not in ("AUDJPY", "USDJPY") or "usd" in str(r.get("notes", "")).lower()
            # AUDJPY/USDJPY in this hub are often JPY-native — mark needs normalize
            if market in ("AUDJPY", "USDJPY") and abs(net) > 1e6:
                usd_ok = False
            rows.append(
                _row(
                    market=market,
                    economic_sleeve=_sleeve_for(market),
                    strategy_family="st_pmc",
                    book_id="%s/%s" % (market, variant),
                    execution_model="1mfill_lot_correct",
                    candidate_type=cand_type,
                    condition_set=variant,
                    multiplier=1.0,
                    baseline_net=net if is_3r else float("nan"),
                    baseline_stress=stress if is_3r else float("nan"),
                    candidate_net=net,
                    candidate_stress=stress,
                    mtm_dd=-stress if math.isfinite(stress) else float("nan"),
                    max_open=_safe_float(r.get("max_open"), float("nan")),
                    eoy_open=_safe_float(r.get("eoy_flatten_units"), 0.0),
                    margin=float("nan"),
                    sample_count=sample,
                    usd_normalized=usd_ok,
                    lot_correct=lot_ok,
                    causal=True,
                    finite=not indefinite,
                    inventory=indefinite,
                    source_hub=hub_name,
                    notes=str(r.get("notes") or "")[:200],
                )
            )
    return rows


def harvest_asia_filters() -> List[Dict[str, Any]]:
    path = REPO / "live/state/fx_v2b_asia_range_london_usdjpy_filters/summary.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path)
    # Identify unfiltered baseline for ΔN/S
    base = df[df["variant"].astype(str).str.contains("unfiltered", case=False, na=False)]
    if base.empty:
        base_net, base_stress = float("nan"), float("nan")
    else:
        b = base.iloc[0]
        base_net = _safe_float(b.get("net_usd"))
        base_stress = abs(_safe_float(b.get("stress_dd_usd")))
    rows = []
    for _, r in df.iterrows():
        variant = str(r.get("variant") or "")
        book = str(r.get("book") or r.get("strategy_id") or "")
        net = _safe_float(r.get("net_usd"))
        stress = abs(_safe_float(r.get("stress_dd_usd")))
        is_base = "unfiltered" in variant.lower()
        rows.append(
            _row(
                market="USDJPY",
                economic_sleeve="usdjpy",
                strategy_family="asia_range_london",
                book_id=book,
                execution_model="broker_like_v2b",
                candidate_type="baseline" if is_base else "filter",
                condition_set=variant,
                multiplier=1.0,
                baseline_net=base_net,
                baseline_stress=base_stress,
                candidate_net=net,
                candidate_stress=stress,
                mtm_dd=-stress,
                max_open=_safe_float(r.get("max_open_units"), float("nan")),
                eoy_open=0.0,
                margin=float("nan"),
                sample_count=_safe_float(r.get("trades"), 0),
                usd_normalized=True,  # hub reports USD
                lot_correct=True,
                causal=True,
                finite=True,
                inventory=False,
                source_hub="fx_v2b_asia_range_london_usdjpy_filters",
                notes="Jan/roll filters are risk-throttle until FILTER_NULLS alpha claim",
            )
        )
    return rows


def harvest_hp_sizeup_results() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    hubs = [
        (REPO / "live/state/futures_intraday_hp_sizeup_nulls", "futures", 1.25),
        (REPO / "live/state/futures_intraday_hp_sizeup_nulls_2x", "futures", 2.0),
        (REPO / "live/state/intraday_hp_sizeup_nulls", "fx_index", None),
    ]
    for hub, family, default_mult in hubs:
        pairs = hub / "pairs"
        if not pairs.exists():
            continue
        for result_path in pairs.glob("*/RESULT.json"):
            try:
                r = json.loads(result_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            book = str(r.get("book") or "")
            market = book.split("_")[0].upper()
            if book.startswith("nq_"):
                market = "NQ"
            elif book.startswith("es_"):
                market = "ES"
            elif book.startswith("ym_"):
                market = "YM"
            elif book.startswith("eurusd"):
                market = "EURUSD"
            elif book.startswith("us30"):
                market = "US30"
            elif book.startswith("usdjpy"):
                market = "USDJPY"
            mult = _safe_float(r.get("size_mult"), default_mult or 1.25)
            cond = "%s=%s" % (r.get("condition"), r.get("bucket"))
            rows.append(
                _row(
                    market=market,
                    economic_sleeve=_sleeve_for(market),
                    strategy_family=family + "_hp_sizeup",
                    book_id=book,
                    execution_model="matched_added_exposure",
                    candidate_type="size_up",
                    condition_set=cond,
                    multiplier=mult,
                    baseline_net=_safe_float(r.get("sleeve_base_net")),
                    baseline_stress=_safe_float(r.get("sleeve_base_stress")),
                    candidate_net=_safe_float(r.get("sleeve_book_net")),
                    candidate_stress=_safe_float(r.get("sleeve_book_stress")),
                    mtm_dd=_safe_float(r.get("sleeve_book_max_dd")),
                    max_open=float("nan"),
                    eoy_open=0.0,
                    margin=float("nan"),
                    sample_count=_safe_float(r.get("boost_n"), 0),
                    usd_normalized=True,
                    lot_correct=True,
                    causal=str(r.get("causal") or "") == "live_ready",
                    finite=True,
                    inventory=False,
                    source_hub=hub.name,
                    notes="decision=%s p_master_ΔNS=%s"
                    % (
                        r.get("decision"),
                        r.get("p_master_delta_ns", r.get("p_master_inc_ns")),
                    ),
                )
            )
    # Sensitivity ladder from compare hub
    sens = REPO / "live/state/futures_intraday_hp_live_plan/size_sensitivity.csv"
    if sens.exists():
        sdf = pd.read_csv(sens)
        # baselines at 1.0× for ΔN/S recovery
        base_map = {}
        for _, r in sdf[sdf["mult"] == 1.0].iterrows():
            key = (str(r["book"]), str(r["condition"]), str(r["bucket"]))
            base_map[key] = r
        for _, r in sdf.iterrows():
            mult = _safe_float(r.get("mult"))
            if mult in (1.0,):
                continue
            book = str(r.get("book") or "")
            market = book.split("_")[0].upper()
            if book.startswith("nq_"):
                market = "NQ"
            elif book.startswith("es_"):
                market = "ES"
            elif book.startswith("ym_"):
                market = "YM"
            key = (book, str(r["condition"]), str(r["bucket"]))
            b = base_map.get(key)
            base_net = _safe_float(b.get("net")) if b is not None else float("nan")
            base_stress = abs(_safe_float(b.get("stress"))) if b is not None else float("nan")
            notes = "SENSITIVITY ONLY — not promotional until exact-mult nulls"
            if abs(mult - 1.25) < 1e-9 or abs(mult - 2.0) < 1e-9:
                # still list; null hubs are authoritative for these mults
                notes = "ladder row; prefer null-suite RESULT.json when present"
            rows.append(
                _row(
                    market=market,
                    economic_sleeve=_sleeve_for(market),
                    strategy_family="futures_hp_sensitivity",
                    book_id=book,
                    execution_model="linear_size_ladder",
                    candidate_type="size_up" if mult > 1.0 else "condition_overlay",
                    condition_set="%s=%s" % (r.get("condition"), r.get("bucket")),
                    multiplier=mult,
                    baseline_net=base_net,
                    baseline_stress=base_stress,
                    candidate_net=_safe_float(r.get("net")),
                    candidate_stress=abs(_safe_float(r.get("stress"))),
                    mtm_dd=_safe_float(r.get("mtm_dd")),
                    max_open=float("nan"),
                    eoy_open=0.0,
                    margin=float("nan"),
                    sample_count=_safe_float(r.get("hp_n"), 0),
                    usd_normalized=True,
                    lot_correct=True,
                    causal=True,
                    finite=True,
                    inventory=False,
                    source_hub="futures_intraday_hp_live_plan",
                    notes=notes,
                )
            )
    return rows


def harvest_prior_opposed_10r() -> List[Dict[str, Any]]:
    path = REPO / "live/state/prior_opposed_10r_addon/summary.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path)
    rows = []
    for _, r in df.iterrows():
        market = str(r.get("market") or r.get("instrument") or "?").upper()
        base_net = _safe_float(r.get("baseline_net"))
        cand_net = _safe_float(r.get("combined_net", r.get("net_usd")))
        base_ns = _safe_float(r.get("baseline_ns"))
        cand_ns = _safe_float(r.get("combined_ns"))
        stress = abs(_safe_float(r.get("combined_stress", r.get("stress_dd_usd"))))
        # Recover stresses from N/S when possible
        base_stress = abs(base_net / base_ns) if base_ns and abs(base_ns) > 1e-9 else float("nan")
        cand_stress = (
            abs(stress)
            if math.isfinite(stress) and stress > 0
            else (abs(cand_net / cand_ns) if cand_ns and abs(cand_ns) > 1e-9 else float("nan"))
        )
        rows.append(
            _row(
                market=market,
                economic_sleeve=_sleeve_for(market),
                strategy_family="prior_opposed_10r",
                book_id="%s_10r_addon" % market,
                execution_model="broker_like",
                # Addon sleeve — not ranked on finite core with flat 3R / 2R→10R.
                candidate_type="addon",
                condition_set="prior_opposed+10R",
                multiplier=1.0,
                baseline_net=base_net,
                baseline_stress=base_stress,
                candidate_net=cand_net,
                candidate_stress=cand_stress,
                mtm_dd=-cand_stress if math.isfinite(cand_stress) else float("nan"),
                max_open=float("nan"),
                eoy_open=0.0,
                margin=float("nan"),
                sample_count=_safe_float(r.get("campaigns", r.get("trades")), 0),
                usd_normalized=True,
                lot_correct=True,
                causal=True,
                finite=True,
                inventory=False,
                source_hub="prior_opposed_10r_addon",
                notes="prior-opposed 10R addon — separate from finite core board",
            )
        )
    return rows


def write_policy() -> None:
    text = """# Canonical N/S research policy

## Score (higher is better)

For each eligible flat / finite book:

```text
N/S = forced-flat net P&L / |reachable full-book stress|
```

For an overlay, filter, or size-up:

```text
ΔN/S = N/S_candidate − N/S_baseline
```

**Δnet is viability + reporting only.** Ranking, null winners, and promotion
use **ΔN/S** (then candidate N/S as secondary).

Example (NQ prior-opposed OR-normal @2×):

```text
24.06 → 36.26
ΔN/S = +12.20   (preferred over Δnet = +$581,952)
```

## Hard eligibility gates

Rank only after:

- finite / forced-flat accounting complete
- reachable full-stack stress available
- lot-correct where relevant
- USD-normalized for cross-market comparisons
- sufficient sample
- causal feature known before entry
- positive net P&L
- minimum absolute stress threshold
- no unresolved inventory / margin warning

## Boards

1. **Cross-market finite core** — USD-normalized, lot-correct, flat books.
2. **Overlay** — OOS ΔN/S by filter / condition / exact multiplier.
3. **Inventory** — forced-flat N/S for indefinite runners only (not ranked with flat).
4. **Sensitivity** — 1.5×/2×/3×/4× ladders; non-promotional until null-tested.

## Taxonomy

| Label | Meaning |
|---|---|
| SIZE-UP VALIDATED | Positive OOS ΔN/S + matched/shift/master ΔN/S nulls + WF/stress/overlap |
| PROVISIONAL PAPER | Local N/S tests pass; borderline or fails strict master ΔN/S |
| RISK THROTTLE | Lowers stress/DD / may raise N/S without superior incremental selection |
| SENSITIVITY ONLY | Historical N/S ladder without exact-multiplier null validation |
| NOT VALIDATED | Fails causal, sample, N/S placebo/shift/master, or risk gate |

## Ordering

```text
Primary:   OOS ΔN/S (higher better)
Secondary: OOS candidate N/S (higher better)
Viability: positive OOS net, DD/stress/margin, sample/coverage
```

## Portfolio

```text
Portfolio N/S = portfolio forced-flat net / |portfolio reachable joint stress|
```

HOLD_ONE: NQ/MNQ · YM/MYM · ES/MES — no simultaneous prior-opposed HP
multipliers until joint-stress validation passes.
"""
    (HUB / "POLICY.md").write_text(text, encoding="utf-8")


def write_boards(ledger: pd.DataFrame) -> None:
    lines = [
        "# Canonical N/S boards (Phase 2 rerank)",
        "",
        "Primary sort: `delta_NS` desc (overlays) or `candidate_NS` desc (baselines).",
        "",
    ]
    # Finite core = flat 3R / filters / finite 2R→10R only (no 10R addon, no indef).
    core = ledger[
        (ledger["rankable"] == True)  # noqa: E712
        & (ledger["candidate_type"].isin(["baseline", "filter", "runner"]))
        & (ledger["finite"] == True)  # noqa: E712
        & (ledger["inventory"] == False)  # noqa: E712
        & (ledger["USD_normalized"] == True)  # noqa: E712
        & (ledger["strategy_family"] != "prior_opposed_10r")
        & (~ledger["book_id"].astype(str).str.contains("indef", case=False, na=False))
    ].copy()
    core = core.sort_values("candidate_NS", ascending=False)
    lines.append("## 1. Cross-market finite core (top 25 by N/S)")
    lines.append("")
    lines.append("_Eligible: finite 3R / 2R→10R / filters. Prior-opposed 10R addon + indefinite runners excluded._")
    lines.append("")
    lines.append("| market | book | type | net | stress | N/S | source |")
    lines.append("|---|---|---|---:|---:|---:|---|")
    for _, r in core.head(25).iterrows():
        lines.append(
            "| %s | %s | %s | %+.0f | %.0f | **%.2f** | %s |"
            % (
                r["market"],
                r["book_id"][:40],
                r["candidate_type"],
                r["candidate_net"],
                r["candidate_reachable_stress"],
                r["candidate_NS"],
                r["source_hub"],
            )
        )
    lines.append("")

    overlay = ledger[
        (ledger["candidate_type"].isin(["size_up", "filter", "condition_overlay"]))
        & (ledger["delta_NS"].notna())
    ].copy()
    # Prefer null-suite hubs over sensitivity ladder duplicates.
    overlay["_pref"] = overlay["source_hub"].astype(str).map(
        lambda h: 0
        if "nulls" in h
        else (1 if "filters" in h else 2)
    )
    overlay = (
        overlay.sort_values(["_pref", "delta_NS"], ascending=[True, False])
        .drop_duplicates(
            subset=["market", "book_id", "condition_set", "multiplier"],
            keep="first",
        )
        .drop(columns=["_pref"])
        .sort_values("delta_NS", ascending=False)
    )
    lines.append("## 2. Overlay board (top 25 by ΔN/S)")
    lines.append("")
    lines.append("| market | book | condition | mult | ΔN/S | Δnet | cand N/S | notes |")
    lines.append("|---|---|---|---:|---:|---:|---:|---|")
    for _, r in overlay.head(25).iterrows():
        lines.append(
            "| %s | %s | %s | %.2f× | **%+.2f** | %+.0f | %.2f | %s |"
            % (
                r["market"],
                str(r["book_id"])[:32],
                str(r["condition_set"])[:36],
                r["multiplier"],
                r["delta_NS"],
                r["delta_net"] if math.isfinite(r["delta_net"]) else float("nan"),
                r["candidate_NS"] if math.isfinite(r["candidate_NS"]) else float("nan"),
                str(r.get("notes") or "")[:40],
            )
        )
    lines.append("")

    addon = ledger[ledger["candidate_type"] == "addon"].copy()
    addon = addon.sort_values("candidate_NS", ascending=False)
    lines.append("## 1b. Prior-opposed 10R addon (not cross-ranked with core)")
    lines.append("")
    if addon.empty:
        lines.append("_none_")
    else:
        lines.append("| market | book | net | stress | N/S | source |")
        lines.append("|---|---|---:|---:|---:|---|")
        for _, r in addon.head(15).iterrows():
            lines.append(
                "| %s | %s | %+.0f | %.0f | %.2f | %s |"
                % (
                    r["market"],
                    str(r["book_id"])[:40],
                    r["candidate_net"],
                    r["candidate_reachable_stress"],
                    r["candidate_NS"] if math.isfinite(r["candidate_NS"]) else float("nan"),
                    r["source_hub"],
                )
            )
    lines.append("")

    inv = ledger[ledger["inventory"] == True].copy()  # noqa: E712
    inv = inv.sort_values("candidate_NS", ascending=False)
    lines.append("## 3. Inventory board (indefinite runners — not cross-ranked)")
    lines.append("")
    if inv.empty:
        lines.append("_none_")
    else:
        lines.append("| market | book | net | stress | forced-flat N/S |")
        lines.append("|---|---|---:|---:|---:|")
        for _, r in inv.head(20).iterrows():
            lines.append(
                "| %s | %s | %+.0f | %.0f | %.2f |"
                % (
                    r["market"],
                    str(r["book_id"])[:40],
                    r["candidate_net"],
                    r["candidate_reachable_stress"],
                    r["candidate_NS"] if math.isfinite(r["candidate_NS"]) else float("nan"),
                )
            )
    lines.append("")

    sens = ledger[ledger["notes"].astype(str).str.contains("SENSITIVITY", na=False)].copy()
    sens = sens.sort_values("delta_NS", ascending=False, na_position="last")
    lines.append("## 4. Sensitivity board (non-promotional)")
    lines.append("")
    if sens.empty:
        lines.append("_none harvested_")
    else:
        lines.append("| market | book | mult | cand N/S | notes |")
        lines.append("|---|---|---:|---:|---|")
        for _, r in sens.head(30).iterrows():
            lines.append(
                "| %s | %s | %.2f× | %.2f | %s |"
                % (
                    r["market"],
                    str(r["book_id"])[:32],
                    r["multiplier"],
                    r["candidate_NS"] if math.isfinite(r["candidate_NS"]) else float("nan"),
                    str(r["notes"])[:48],
                )
            )
    lines.append("")
    (HUB / "BOARDS.md").write_text("\n".join(lines), encoding="utf-8")


def _coupon(cand: float, base: float) -> float:
    if not (math.isfinite(cand) and math.isfinite(base)) or base == 0.0:
        return float("nan")
    return cand / base


def _fmt_num(x: float, *, money: bool = False, signed: bool = False) -> str:
    if not math.isfinite(x):
        return "—"
    if money:
        ax = abs(x)
        body = ("{:,.0f}".format(ax)) if ax >= 100 else ("{:,.2f}".format(ax))
        if signed or x < 0:
            return ("+" if x >= 0 else "-") + body
        return body
    if signed:
        return "%+.2f" % x
    return "%.2f" % x


def write_all_results_with_coupons(ledger: pd.DataFrame) -> None:
    """Unsorted ledger dump with net / stress / N/S coupons vs each row's baseline.

    Coupon = candidate / baseline for that field (1.00 = flat). No reordering.
    """
    rows_out: List[Dict[str, Any]] = []
    md = [
        "# Canonical N/S — all results (ledger order, unsorted)",
        "",
        "Source: `CANDIDATE_LEDGER.csv` (Phase 1 harvest). **No sorting** — row order matches the ledger.",
        "",
        "**Coupon** = candidate / baseline for that field (`1.00` = flat vs own baseline).",
        "Δ columns = candidate − baseline.",
        "",
        "| # | market | book | type | condition | mult | base net | cand net | net coupon | Δnet | base stress | cand stress | stress coupon | Δstress | base N/S | cand N/S | N/S coupon | ΔN/S | rankable | notes |",
        "|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for i, r in enumerate(ledger.itertuples(index=False), start=1):
        d = r._asdict() if hasattr(r, "_asdict") else dict(zip(ledger.columns, r))
        b_net = _safe_float(d.get("baseline_net"))
        c_net = _safe_float(d.get("candidate_net"))
        b_st = _safe_float(d.get("baseline_reachable_stress"))
        c_st = _safe_float(d.get("candidate_reachable_stress"))
        b_ns = _safe_float(d.get("baseline_NS"))
        c_ns = _safe_float(d.get("candidate_NS"))
        d_net = _safe_float(d.get("delta_net"))
        d_st = _safe_float(d.get("delta_stress"))
        d_ns = _safe_float(d.get("delta_NS"))
        net_c = _coupon(c_net, b_net)
        st_c = _coupon(c_st, b_st)
        ns_c = _coupon(c_ns, b_ns)
        notes = str(d.get("notes") or "")
        notes_short = (notes[:60] + "…") if len(notes) > 60 else notes
        notes_short = notes_short.replace("|", "/")
        out = {
            "idx": i,
            "market": d.get("market"),
            "book_id": d.get("book_id"),
            "candidate_type": d.get("candidate_type"),
            "condition_set": d.get("condition_set"),
            "multiplier": d.get("multiplier"),
            "baseline_net": b_net,
            "candidate_net": c_net,
            "net_coupon": net_c,
            "delta_net": d_net,
            "baseline_stress": b_st,
            "candidate_stress": c_st,
            "stress_coupon": st_c,
            "delta_stress": d_st,
            "baseline_NS": b_ns,
            "candidate_NS": c_ns,
            "NS_coupon": ns_c,
            "delta_NS": d_ns,
            "rankable": d.get("rankable"),
            "eligibility_reasons": d.get("eligibility_reasons"),
            "source_hub": d.get("source_hub"),
            "notes": notes,
        }
        rows_out.append(out)
        md.append(
            "| %d | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                i,
                d.get("market"),
                str(d.get("book_id") or "")[:40],
                d.get("candidate_type"),
                str(d.get("condition_set") or "")[:48],
                _fmt_num(_safe_float(d.get("multiplier"))),
                _fmt_num(b_net, money=True, signed=True),
                _fmt_num(c_net, money=True, signed=True),
                _fmt_num(net_c),
                _fmt_num(d_net, money=True, signed=True),
                _fmt_num(b_st, money=True),
                _fmt_num(c_st, money=True),
                _fmt_num(st_c),
                _fmt_num(d_st, money=True, signed=True),
                _fmt_num(b_ns),
                _fmt_num(c_ns),
                _fmt_num(ns_c),
                _fmt_num(d_ns, signed=True),
                str(bool(d.get("rankable"))),
                notes_short,
            )
        )
    md.append("")
    pd.DataFrame(rows_out).to_csv(HUB / "ALL_RESULTS_WITH_COUPONS.csv", index=False)
    (HUB / "ALL_RESULTS.md").write_text("\n".join(md), encoding="utf-8")


def run(*, email: bool = False) -> Path:
    HUB.mkdir(parents=True, exist_ok=True)
    _progress("START canonical_ns_research Phase 1 backfill")
    write_policy()
    pd.DataFrame(SLEEVE_MAP).to_csv(HUB / "ECONOMIC_SLEEVE_MAP.csv", index=False)

    rows: List[Dict[str, Any]] = []
    for fn in (
        harvest_runner_variants,
        harvest_asia_filters,
        harvest_hp_sizeup_results,
        harvest_prior_opposed_10r,
    ):
        try:
            chunk = fn()
            _progress("  %s → %d rows" % (fn.__name__, len(chunk)))
            rows.extend(chunk)
        except Exception:
            _progress("  %s FAILED\n%s" % (fn.__name__, traceback.format_exc()[-1500:]))

    ledger = pd.DataFrame(rows)
    if ledger.empty:
        raise RuntimeError("no candidates harvested")

    # Baseline registry: one row per (market, strategy_family, baseline book)
    base = ledger[ledger["candidate_type"] == "baseline"].copy()
    base.to_csv(HUB / "BASELINE_REGISTRY.csv", index=False)
    ledger.to_csv(HUB / "CANDIDATE_LEDGER.csv", index=False)
    audit_cols = [
        "market",
        "book_id",
        "candidate_type",
        "candidate_NS",
        "delta_NS",
        "rankable",
        "eligibility_reasons",
        "USD_normalized",
        "lot_correct",
        "causal",
        "finite",
        "inventory",
        "source_hub",
    ]
    ledger[audit_cols].to_csv(HUB / "ELIGIBILITY_AUDIT.csv", index=False)
    write_boards(ledger)
    write_all_results_with_coupons(ledger)

    n_rank = int(ledger["rankable"].sum()) if "rankable" in ledger.columns else 0
    top = (
        ledger[ledger["delta_NS"].notna()]
        .sort_values("delta_NS", ascending=False)
        .head(5)
    )
    email_lines = [
        "canonical_ns_research Phase 1 complete",
        "hub: %s" % HUB,
        "candidates: %d (rankable=%d)" % (len(ledger), n_rank),
        "",
        "Top ΔN/S overlays:",
    ]
    for _, r in top.iterrows():
        email_lines.append(
            "  %s %s @%.2f× ΔN/S=%+.2f (Δnet=%+.0f) [%s]"
            % (
                r["market"],
                r["book_id"][:28],
                r["multiplier"],
                r["delta_NS"],
                r["delta_net"] if math.isfinite(r["delta_net"]) else float("nan"),
                r["source_hub"],
            )
        )
    email_lines.extend(
        [
            "",
            "Policy: whole-book ΔN/S is the canonical higher-is-better score.",
            "Δnet is viability/reporting only.",
            "See POLICY.md + BOARDS.md + ALL_RESULTS.md (unsorted coupons).",
        ]
    )
    body = "\n".join(email_lines)
    (HUB / "EMAIL.txt").write_text(body + "\n", encoding="utf-8")
    (HUB / "RUN_COMPLETE.json").write_text(
        json.dumps(
            {
                "ok": True,
                "n_candidates": int(len(ledger)),
                "n_rankable": n_rank,
                "hub": str(HUB),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _progress("DONE candidates=%d rankable=%d" % (len(ledger), n_rank))
    if email:
        send_email(subject="potions: canonical_ns_research Phase 1 complete", body=body)
    return HUB


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", action="store_true")
    args = p.parse_args()
    try:
        run(email=bool(args.email))
    except Exception:
        tb = traceback.format_exc()
        _progress("CRASH\n" + tb)
        if args.email:
            send_email(
                subject="potions: canonical_ns_research CRASH",
                body="hub=%s\n%s" % (HUB, tb[-2500:]),
            )
        raise


if __name__ == "__main__":
    main()
