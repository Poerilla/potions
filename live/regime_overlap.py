"""Deterministic regime-overlap / risk-sleeve classification.

Four classes (never the legacy OR rule ``Jaccard < t OR |ρ| < t``):

- SEPARATE_REGIMES
- CONDITIONAL_OVERLAP
- SAME_SLEEVE
- UNRESOLVED

Join key: NY session date (+ direction). Do not join across markets on trade_id.
Every result carries exact strategy/version/book identity.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

# Thresholds tuned to preserve intended examples (YM/US30 ST+PMC SAME_SLEEVE;
# YM PO vs US30 PO CONDITIONAL_OVERLAP; sparse near-zero corr SEPARATE_REGIMES).
JACCARD_MEANINGFUL = 0.35
DIR_AGREE_HIGH = 0.70
RHO_HIGH = 0.40
MIN_SHARED_DAYS = 15
MIN_CORR_DAYS = 5
MIN_CAMPAIGNS = 20

# Execution alternatives that are one economic sleeve, not additive allocations.
DUPLICATE_SLEEVE_GROUPS = (
    frozenset({"nq", "mnq"}),
    frozenset({"nq", "mnq", "nas100"}),
    frozenset({"ym", "mym"}),
    frozenset({"ym", "mym", "us30"}),
)

CLASS_SEPARATE = "SEPARATE_REGIMES"
CLASS_CONDITIONAL = "CONDITIONAL_OVERLAP"
CLASS_SAME = "SAME_SLEEVE"
CLASS_UNRESOLVED = "UNRESOLVED"

SIZING = {
    CLASS_SEPARATE: (
        "independent strategy allocations; still subject to underlying-market "
        "and portfolio stress caps"
    ),
    CLASS_CONDITIONAL: (
        "strategies can exist separately; apply a simultaneous-signal shared "
        "risk cap when both fire"
    ),
    CLASS_SAME: (
        "one shared allocation; do not count as independent edges or stack full risk"
    ),
    CLASS_UNRESOLVED: "research only — do not size as independent or joint yet",
}


def book_identity(
    *,
    market: str,
    strategy: str,
    version: str = "",
    book: str = "",
    strategy_id: str = "",
    hub: str = "",
) -> Dict[str, str]:
    """Exact strategy/version/book identity for overlap conclusions."""
    return {
        "market": str(market).lower(),
        "strategy": str(strategy),
        "version": str(version or ""),
        "book": str(book or ""),
        "strategy_id": str(strategy_id or ""),
        "hub": str(hub or ""),
        "label": _identity_label(market, strategy, version, book, strategy_id),
    }


def _identity_label(
    market: str, strategy: str, version: str, book: str, strategy_id: str
) -> str:
    if strategy_id:
        return strategy_id
    parts = [str(market).upper(), strategy]
    if version:
        parts.append(version)
    if book:
        parts.append(book)
    return " ".join(p for p in parts if p)


def classify_regime_overlap(
    *,
    day_jaccard: float,
    dir_agree_rate_on_shared: Optional[float],
    shared_day_pnl_corr: Optional[float],
    shared_days: int,
    corr_days: int = 0,
    a_campaigns: int = 0,
    b_campaigns: int = 0,
    sample_warning: str = "",
    missing_accounting: bool = False,
) -> Dict[str, Any]:
    """Classify a pair from precomputed overlap metrics.

    Critical: low Jaccard alone does **not** imply SEPARATE_REGIMES when
    shared-day direction agreement or shared-day P&L correlation is high.
    """
    high_cond = _high_conditional(dir_agree_rate_on_shared, shared_day_pnl_corr)
    warnings: List[str] = []
    if sample_warning:
        warnings.append(sample_warning)
    if missing_accounting:
        warnings.append("missing_accounting_or_normalized_data")
        return _result(CLASS_UNRESOLVED, warnings, high_cond)

    if a_campaigns and a_campaigns < MIN_CAMPAIGNS:
        warnings.append("insufficient_campaigns_a<%d" % MIN_CAMPAIGNS)
    if b_campaigns and b_campaigns < MIN_CAMPAIGNS:
        warnings.append("insufficient_campaigns_b<%d" % MIN_CAMPAIGNS)
    if shared_days < MIN_SHARED_DAYS:
        warnings.append("insufficient_shared_days<%d" % MIN_SHARED_DAYS)
    if shared_day_pnl_corr is not None and corr_days < MIN_CORR_DAYS:
        warnings.append("insufficient_corr_days<%d" % MIN_CORR_DAYS)

    # Too little sample → UNRESOLVED (unless metrics are clearly decisive and
    # we still want a research hint; prefer UNRESOLVED for sizing).
    if warnings and (
        shared_days < MIN_SHARED_DAYS
        or (a_campaigns and a_campaigns < MIN_CAMPAIGNS)
        or (b_campaigns and b_campaigns < MIN_CAMPAIGNS)
    ):
        return _result(CLASS_UNRESOLVED, warnings, high_cond)

    meaningful_overlap = day_jaccard >= JACCARD_MEANINGFUL
    if meaningful_overlap and high_cond:
        return _result(CLASS_SAME, warnings, high_cond)
    if (not meaningful_overlap) and high_cond:
        return _result(CLASS_CONDITIONAL, warnings, high_cond)
    if (not meaningful_overlap) and (not high_cond):
        return _result(CLASS_SEPARATE, warnings, high_cond)
    # Meaningful calendar overlap but weak conditional relationship.
    warnings.append("meaningful_overlap_but_weak_conditional_relationship")
    return _result(CLASS_UNRESOLVED, warnings, high_cond)


def _high_conditional(
    dir_agree: Optional[float], rho: Optional[float]
) -> bool:
    if dir_agree is not None and dir_agree >= DIR_AGREE_HIGH:
        return True
    if rho is not None and abs(rho) >= RHO_HIGH:
        return True
    return False


def _result(cls: str, warnings: Sequence[str], high_cond: bool) -> Dict[str, Any]:
    return {
        "regime_class": cls,
        "recommended_sizing": SIZING[cls],
        "sample_size_warnings": list(warnings),
        "high_conditional_relationship": bool(high_cond),
        # Legacy boolean kept for migration; True only for SEPARATE_REGIMES.
        "regime_separable": cls == CLASS_SEPARATE,
    }


def pearson_corr(
    a: Dict[str, float], b: Dict[str, float], *, keys: Optional[Sequence[str]] = None
) -> Tuple[Optional[float], int]:
    use = list(keys) if keys is not None else sorted(set(a) & set(b))
    if len(use) < MIN_CORR_DAYS:
        return None, len(use)
    xa = [float(a.get(k, 0.0)) for k in use]
    xb = [float(b.get(k, 0.0)) for k in use]
    ma = sum(xa) / len(xa)
    mb = sum(xb) / len(xb)
    num = sum((x - ma) * (y - mb) for x, y in zip(xa, xb))
    da = math.sqrt(sum((x - ma) ** 2 for x in xa))
    db = math.sqrt(sum((y - mb) ** 2 for y in xb))
    if da < 1e-12 or db < 1e-12:
        return None, len(use)
    return num / (da * db), len(use)


def adverse_coincidence(
    a: Dict[str, float], b: Dict[str, float], shared_days: Sequence[str]
) -> Optional[float]:
    """Fraction of shared days where both sleeves have negative P&L."""
    if not shared_days:
        return None
    both_neg = 0
    for d in shared_days:
        if float(a.get(d, 0.0)) < 0 and float(b.get(d, 0.0)) < 0:
            both_neg += 1
    return round(both_neg / len(shared_days), 3)


def overlap_metrics(
    name_a: str,
    camps_a: Sequence[dict],
    name_b: str,
    camps_b: Sequence[dict],
    *,
    identity_a: Optional[Dict[str, str]] = None,
    identity_b: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Full pair metrics + classification. Campaigns need day/dir/net_usd."""
    da = {c["day"] for c in camps_a}
    db = {c["day"] for c in camps_b}
    dda = {(c["day"], c["dir"]) for c in camps_a}
    ddb = {(c["day"], c["dir"]) for c in camps_b}
    days_union = da | db
    days_inter = da & db
    dd_inter = dda & ddb

    a_by: Dict[str, List[dict]] = defaultdict(list)
    b_by: Dict[str, List[dict]] = defaultdict(list)
    for c in camps_a:
        a_by[c["day"]].append(c)
    for c in camps_b:
        b_by[c["day"]].append(c)

    dir_agree = 0
    dir_conflict = 0
    for day in days_inter:
        dirs_a = {c["dir"] for c in a_by[day]}
        dirs_b = {c["dir"] for c in b_by[day]}
        if dirs_a & dirs_b:
            dir_agree += 1
        else:
            dir_conflict += 1

    daily_a = _daily_net(camps_a)
    daily_b = _daily_net(camps_b)
    shared_keys = sorted(days_inter)
    union_keys = sorted(days_union)
    rho_shared, n_shared = pearson_corr(daily_a, daily_b, keys=shared_keys)
    rho_union, n_union = pearson_corr(daily_a, daily_b, keys=union_keys)
    jacc = (len(days_inter) / len(days_union)) if days_union else 0.0
    dir_rate = (dir_agree / len(days_inter)) if days_inter else None
    joint_stress = adverse_coincidence(daily_a, daily_b, shared_keys)

    id_a = identity_a or book_identity(market="", strategy=name_a)
    id_b = identity_b or book_identity(market="", strategy=name_b)
    cls = classify_regime_overlap(
        day_jaccard=jacc,
        dir_agree_rate_on_shared=dir_rate,
        shared_day_pnl_corr=rho_shared,
        shared_days=len(days_inter),
        corr_days=n_shared,
        a_campaigns=len(camps_a),
        b_campaigns=len(camps_b),
    )

    out: Dict[str, Any] = {
        "pair": "%s vs %s" % (id_a.get("label") or name_a, id_b.get("label") or name_b),
        "identity_a": id_a,
        "identity_b": id_b,
        "a_campaigns": len(camps_a),
        "b_campaigns": len(camps_b),
        "a_days": len(da),
        "b_days": len(db),
        "shared_ny_session_dates": len(days_inter),
        "union_ny_session_dates": len(days_union),
        "shared_days": len(days_inter),
        "union_days": len(days_union),
        "day_jaccard": round(jacc, 3),
        "a_only_dates": len(da - db),
        "b_only_dates": len(db - da),
        "a_only_days": len(da - db),
        "b_only_days": len(db - da),
        "shared_day_dir_agree": dir_agree,
        "shared_day_dir_conflict": dir_conflict,
        "dir_agree_rate_on_shared": None if dir_rate is None else round(dir_rate, 3),
        "same_day_same_dir_events": len(dd_inter),
        "shared_day_pnl_corr": None if rho_shared is None else round(rho_shared, 3),
        "daily_net_corr": None if rho_shared is None else round(rho_shared, 3),
        "corr_days": n_shared,
        "union_day_pnl_corr": None if rho_union is None else round(rho_union, 3),
        "union_corr_days": n_union,
        "shared_day_joint_stress_rate": joint_stress,
        **cls,
    }
    return out


def _daily_net(camps: Sequence[dict]) -> Dict[str, float]:
    out: Dict[str, float] = defaultdict(float)
    for c in camps:
        out[c["day"]] += float(c.get("net_usd") or 0.0)
    return dict(out)


def duplicate_sleeve_warnings(
    markets: Sequence[str],
    *,
    book: str = "",
    strategy: str = "",
) -> List[Dict[str, Any]]:
    """Emit warnings when economically duplicate execution sleeves co-appear."""
    present = {str(m).lower() for m in markets}
    warnings: List[Dict[str, Any]] = []
    checked: Set[frozenset] = set()
    for group in DUPLICATE_SLEEVE_GROUPS:
        hit = present & group
        key = frozenset(hit)
        if len(hit) < 2 or key in checked:
            continue
        # Prefer the most specific group that fully matches hits.
        if hit != group and any(hit < g and hit <= present for g in DUPLICATE_SLEEVE_GROUPS):
            # Wait for more specific; still emit if no larger subset fully present.
            larger = [g for g in DUPLICATE_SLEEVE_GROUPS if hit < g and g <= present]
            if larger:
                continue
        checked.add(key)
        sleeve = "Nasdaq" if hit <= {"nq", "mnq", "nas100"} else (
            "Dow" if hit <= {"ym", "mym", "us30"} else "shared"
        )
        warnings.append(
            {
                "warning": "DUPLICATE_EXECUTION_SLEEVE",
                "markets": sorted(hit),
                "sleeve": sleeve,
                "strategy": strategy,
                "book": book,
                "message": (
                    "%s are execution alternatives / one shared %s sleeve — "
                    "not additive independent allocations"
                    % ("/".join(sorted(m.upper() for m in hit)), sleeve)
                ),
            }
        )
    return warnings


def day_dir_sets(camps: Sequence[dict]) -> Tuple[Set[str], Set[Tuple[str, str]]]:
    return {c["day"] for c in camps}, {(c["day"], c["dir"]) for c in camps}
