"""Phase 2 locked Monday OR pair-tag configs (broker knobs).

Anchors from broker Phase 1 sizing sweep. Do not cross-use EURUSD and USDJPY recipes.

Cluster/skip tune-ups (2026-07-28) are pair-aware via ``PAIR_TUNEUPS`` because
some tags are shared (e.g. ``M1_S2_R2`` on EURUSD vs AUDJPY).
"""

from __future__ import annotations

from typing import Dict, Any, List, Optional, Tuple


# tag -> (entry, dd30, dd50) for main / shifted; max primary/week
TagSpec = Dict[str, Any]

PHASE2_TAGS: Dict[str, TagSpec] = {
    "M1_S2_R2": {
        "entry_qty": 3,
        "dd30_qty": 2,
        "dd50_qty": 1,
        "shifted_entry_qty": 2,
        "shifted_dd30_qty": 1,
        "shifted_dd50_qty": 1,
        "max_trades_per_week": 3,
        "label": "EURUSD Phase 2 anchor (light shifted, max 3/wk)",
    },
    "M2_S3_R1": {
        "entry_qty": 3,
        "dd30_qty": 1,
        "dd50_qty": 2,
        "shifted_entry_qty": 4,
        "shifted_dd30_qty": 2,
        "shifted_dd50_qty": 2,
        "max_trades_per_week": 2,
        # Core (broker-confirmed): sit out after +3 yen pts; skip Aug+Sep entries.
        "week_sitout_after_pts": 3.0,
        "week_sitout_blocks_shifted": True,
        "skip_entry_months": [8, 9],
        "label": (
            "USDJPY Phase 2 primary (runner-heavy + heavy shifted, max 2/wk; "
            "sitout +3 pts; skip Aug/Sep)"
        ),
    },
    "M2_S3_R2": {
        "entry_qty": 3,
        "dd30_qty": 1,
        "dd50_qty": 2,
        "shifted_entry_qty": 4,
        "shifted_dd30_qty": 2,
        "shifted_dd50_qty": 2,
        "max_trades_per_week": 3,
        # Core (broker-confirmed): skip-1-after-2W; skip Aug+Sep entries.
        "skip_after_win_streak": 2,
        "skip_after_win_n": 1,
        "skip_entry_months": [8, 9],
        "label": (
            "USDJPY Phase 2 alternate (same size, max 3/wk; skip-1-after-2W; "
            "skip Aug/Sep)"
        ),
    },
    "M1_S2_R1": {
        "entry_qty": 3,
        "dd30_qty": 2,
        "dd50_qty": 1,
        "shifted_entry_qty": 2,
        "shifted_dd30_qty": 1,
        "shifted_dd50_qty": 1,
        "max_trades_per_week": 2,
        "label": "EURUSD local perturbation (tighter max 2/wk)",
    },
    "M2_S2_R1": {
        "entry_qty": 3,
        "dd30_qty": 1,
        "dd50_qty": 2,
        "shifted_entry_qty": 2,
        "shifted_dd30_qty": 1,
        "shifted_dd50_qty": 1,
        "max_trades_per_week": 2,
        "label": "USDJPY robustness (lighter sidecar)",
    },
    # US30 Phase 1 #2 (max 3/wk). Live demos use HALF-SIZE overlay via PAIR_TUNEUPS.
    "M3_S3_R2": {
        "entry_qty": 2,
        "dd30_qty": 1,
        "dd50_qty": 1,
        "shifted_entry_qty": 4,
        "shifted_dd30_qty": 2,
        "shifted_dd50_qty": 2,
        "max_trades_per_week": 3,
        "skip_entry_months": [9],
        "label": "US30 Phase 1 #2 (main 1@30/1@50 + heavy shifted, max 3/wk; skip Sep)",
    },
}

# Default tag per pair for live/broker drivers
PAIR_PHASE2_DEFAULT: Dict[str, str] = {
    "EURUSD": "M1_S2_R2",
    "USDJPY": "M2_S3_R1",
    "GBPUSD": "M1_S1_R2",
    "AUDJPY": "M1_S2_R2",
    "XAUUSD": "M2_S2_R3",
    "US30": "M3_S3_R2",
    # Silver excluded from Phase 2 (Phase 1 reject)
    # "XAGUSD": "M2_S2_R3",
}

# Footnote / extended Phase 2 tags
FOOTNOTE_TAGS: Dict[str, TagSpec] = {
    "M1_S1_R2": {
        "entry_qty": 3,
        "dd30_qty": 2,
        "dd50_qty": 1,
        "shifted_entry_qty": 3,
        "shifted_dd30_qty": 2,
        "shifted_dd50_qty": 1,
        "max_trades_per_week": 3,
        # skip-1-after-W looked good in fill-proxy study but FAILED broker
        # (N/S 2.67→1.60, −$67k) — do not enable on GBPUSD.
        "label": "GBPUSD Phase 2 extended (matched main/shifted, max 3/wk)",
    },
    "M2_S2_R3": {
        "entry_qty": 3,
        "dd30_qty": 1,
        "dd50_qty": 2,
        "shifted_entry_qty": 2,
        "shifted_dd30_qty": 1,
        "shifted_dd50_qty": 1,
        "max_trades_per_week": 99,
        # Core: sit out rest of Mon-week after +100 gold pts; no entries in Jul/Sep/Dec.
        "week_sitout_after_pts": 100.0,
        "week_sitout_blocks_shifted": True,
        "skip_entry_months": [7, 9, 12],
        "label": (
            "XAUUSD Phase 2 core (unlimited primary/week; sitout +100 pts; "
            "skip Jul/Sep/Dec entries)"
        ),
    },
}

# Pair+tag overlays. Only broker-confirmed rules stay enabled.
# Fill-proxy candidates that failed StrategyPlugin audit are documented in
# tuneup_broker/SUMMARY.md and left OFF here.
PAIR_TUNEUPS: Dict[Tuple[str, str], Dict[str, Any]] = {
    ("USDJPY", "M2_S3_R1"): {
        "week_sitout_after_pts": 3.0,
        "week_sitout_blocks_shifted": True,
        "skip_entry_months": [8, 9],
        "tuneup_note": "sitout +3 pts + skip Aug/Sep (broker OK)",
    },
    ("USDJPY", "M2_S3_R2"): {
        "skip_after_win_streak": 2,
        "skip_after_win_n": 1,
        "skip_entry_months": [8, 9],
        "tuneup_note": "skip-1-after-2W + skip Aug/Sep (broker OK)",
    },
    ("XAUUSD", "M2_S2_R3"): {
        "week_sitout_after_pts": 100.0,
        "week_sitout_blocks_shifted": True,
        "skip_entry_months": [7, 9, 12],
        "tuneup_note": "sitout +100 pts + skip Jul/Sep/Dec",
    },
    # US30 M3_S3_R2: Sep skip from month audit; HALF-SIZE qtys (robustness concentration).
    ("US30", "M3_S3_R2"): {
        "entry_qty": 1,
        "dd30_qty": 0,
        "dd50_qty": 1,
        "shifted_entry_qty": 2,
        "shifted_dd30_qty": 1,
        "shifted_dd50_qty": 1,
        "max_trades_per_week": 3,
        "skip_entry_months": [9],
        "tuneup_note": "half-size (1-lot main) + skip Sep (missed_promote_screen 2026-08-11)",
    },
    # EURUSD skip-1-after-W: fill-proxy OK, broker ΔN/S≈0 / −$11k → OFF
    # GBPUSD skip-1-after-W: fill-proxy OK, broker N/S 2.67→1.60 → OFF
    # AUDJPY skip-1-after-2W: fill-proxy only; not yet StrategyPlugin-audited → OFF
}

# Core Phase 2 (EURUSD / USDJPY) + extended (ex-silver)
PHASE2_CORE_ANCHORS: List[Tuple[str, str]] = [
    ("EURUSD", "M1_S2_R2"),
    ("USDJPY", "M2_S3_R1"),
    ("USDJPY", "M2_S3_R2"),
]
PHASE2_EXTENDED_ANCHORS: List[Tuple[str, str]] = [
    ("GBPUSD", "M1_S1_R2"),
    ("AUDJPY", "M1_S2_R2"),
    ("XAUUSD", "M2_S2_R3"),
]

# Local perturbation cells to document (not full grid)
LOCAL_PERTURBATIONS: List[Tuple[str, str]] = [
    ("EURUSD", "M1_S2_R2"),
    ("EURUSD", "M1_S2_R1"),
    ("USDJPY", "M2_S3_R1"),
    ("USDJPY", "M2_S3_R2"),
    ("USDJPY", "M2_S2_R1"),
]

# Phase 1 broker result roots for fills reuse
PHASE1_STATE_ROOTS: Dict[str, str] = {
    "EURUSD": "live/state/monday_or_sizing_sweep_broker",
    "USDJPY": "live/state/monday_or_sizing_sweep_broker_usdjpy",
    "GBPUSD": "live/state/monday_or_sizing_sweep_broker_gbpusd",
    "AUDJPY": "live/state/monday_or_sizing_sweep_broker_audjpy",
    "XAUUSD": "live/state/monday_or_sizing_sweep_broker_xauusd",
    "XAGUSD": "live/state/monday_or_sizing_sweep_broker_xagusd",
}


def resolve_tag(tag: str) -> TagSpec:
    if tag in PHASE2_TAGS:
        return PHASE2_TAGS[tag]
    if tag in FOOTNOTE_TAGS:
        return FOOTNOTE_TAGS[tag]
    raise KeyError("Unknown Monday OR tag: %s" % tag)


def plugin_config(
    tick: float,
    tag: str,
    *,
    pair: Optional[str] = None,
    dd30_frac: float = 0.30,
    dd50_frac: float = 0.50,
    reward_R: float = 2.0,
    skip_both_opposed: bool = True,
    shifted_primary: bool = True,
    obv_ma: int = 20,
) -> Dict[str, Any]:
    spec = resolve_tag(tag)
    cfg: Dict[str, Any] = {
        "tick_size": tick,
        "entry_qty": int(spec["entry_qty"]),
        "dd30_qty": int(spec["dd30_qty"]),
        "dd50_qty": int(spec["dd50_qty"]),
        "shifted_entry_qty": int(spec["shifted_entry_qty"]),
        "shifted_dd30_qty": int(spec["shifted_dd30_qty"]),
        "shifted_dd50_qty": int(spec["shifted_dd50_qty"]),
        "max_trades_per_week": int(spec["max_trades_per_week"]),
        "dd30_frac": float(dd30_frac),
        "dd50_frac": float(dd50_frac),
        "reward_R": float(reward_R),
        "skip_both_opposed": bool(skip_both_opposed),
        "shifted_primary": bool(shifted_primary),
        "obv_ma": int(obv_ma),
    }
    # Tag-level optional knobs
    for key in (
        "week_sitout_after_pts",
        "week_sitout_blocks_shifted",
        "skip_after_win_streak",
        "skip_after_win_n",
        "skip_entry_months",
    ):
        if key in spec:
            cfg[key] = spec[key]
    # Pair overlays (shared tags / explicit lock)
    if pair:
        overlay = PAIR_TUNEUPS.get((str(pair).upper(), tag))
        if overlay:
            for key, val in overlay.items():
                if key == "tuneup_note":
                    continue
                cfg[key] = val
    # Normalize types
    if "week_sitout_after_pts" in cfg:
        cfg["week_sitout_after_pts"] = float(cfg["week_sitout_after_pts"])
    if "week_sitout_blocks_shifted" in cfg:
        cfg["week_sitout_blocks_shifted"] = bool(cfg["week_sitout_blocks_shifted"])
    if "skip_after_win_streak" in cfg:
        cfg["skip_after_win_streak"] = int(cfg["skip_after_win_streak"])
    if "skip_after_win_n" in cfg:
        cfg["skip_after_win_n"] = int(cfg["skip_after_win_n"])
    if "skip_entry_months" in cfg:
        months = []
        for m in cfg["skip_entry_months"] or []:
            try:
                mi = int(m)
            except (TypeError, ValueError):
                continue
            if 1 <= mi <= 12:
                months.append(mi)
        cfg["skip_entry_months"] = sorted(set(months))
    return cfg
