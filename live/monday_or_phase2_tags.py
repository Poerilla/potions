"""Phase 2 locked Monday OR pair-tag configs (broker knobs).

Anchors from broker Phase 1 sizing sweep. Do not cross-use EURUSD and USDJPY recipes.
"""

from __future__ import annotations

from typing import Dict, Any, List, Tuple


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
        "label": "USDJPY Phase 2 primary (runner-heavy + heavy shifted, max 2/wk)",
    },
    "M2_S3_R2": {
        "entry_qty": 3,
        "dd30_qty": 1,
        "dd50_qty": 2,
        "shifted_entry_qty": 4,
        "shifted_dd30_qty": 2,
        "shifted_dd50_qty": 2,
        "max_trades_per_week": 3,
        "label": "USDJPY Phase 2 alternate (same size, max 3/wk)",
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
}

# Default tag per pair for live/broker drivers
PAIR_PHASE2_DEFAULT: Dict[str, str] = {
    "EURUSD": "M1_S2_R2",
    "USDJPY": "M2_S3_R1",
    "GBPUSD": "M1_S1_R2",
    "AUDJPY": "M1_S2_R2",
    "XAUUSD": "M2_S2_R3",
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
        "label": "XAUUSD Phase 2 extended (heat caution; unlimited primary/week)",
    },
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
    dd30_frac: float = 0.30,
    dd50_frac: float = 0.50,
    reward_R: float = 2.0,
    skip_both_opposed: bool = True,
    shifted_primary: bool = True,
    obv_ma: int = 20,
) -> Dict[str, Any]:
    spec = resolve_tag(tag)
    return {
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
