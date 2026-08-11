"""Shadow rolling WR/PF book for Asia-range (and similar) sit-out gates.

Research + live contract
------------------------
The rolling gate must advance on **unfiltered** campaign outcomes. Using only
taken trades freezes the window after the first PF dip (sit forever).

- **Research** (`fx_v2b_asia_range_london_usdjpy_filters`): precompute skip
  sessions from the full unfiltered sizing tape, then broker-replay only the
  allowed days.
- **Live**: keep a JSON shadow book of unfiltered campaign nets. Seed from the
  research tape; each London day, append today's unfiltered outcome — live
  ``unit_trades`` when taken, else EOD candle-sim on collected 1m bars when the
  gate sat out. Gate reads prior-N before arming.

Shadow trades are not broker orders — they are simulated campaign PnLs from
collected 1m bars that inform the next session's filter.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DEFAULT_SIZING_UNIT = (
    REPO
    / "live"
    / "state"
    / "fx_v2b_asia_range_london_usdjpy_sizing"
    / "states"
    / "usdjpy_v2b_asia_range_london_S_3_1_3"
    / "unit_trades.csv"
)


def profit_factor(pnl: Sequence[float]) -> float:
    gains = sum(x for x in pnl if x > 0)
    losses = sum(-x for x in pnl if x < 0)
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def win_rate(pnl: Sequence[float]) -> float:
    if not pnl:
        return 0.0
    return sum(1 for x in pnl if x > 0) / float(len(pnl))


def gate_blocks(
    campaigns: Sequence[float],
    *,
    window: int = 50,
    min_wr: float = 0.40,
    min_pf: float = 1.0,
) -> Tuple[bool, Dict[str, float]]:
    """True when prior-``window`` shadow campaigns fail WR or PF floors.

    Meta always includes ``n`` / ``wr`` / ``pf``. When the window is full also
    includes ``bad_wr`` / ``bad_pf`` (0/1) and ``warmup`` (0 when armed).
    """
    if window <= 0 or len(campaigns) < window:
        return False, {
            "n": float(len(campaigns)),
            "wr": 0.0,
            "pf": 0.0,
            "bad_wr": 0.0,
            "bad_pf": 0.0,
            "warmup": 1.0,
        }
    hist = list(campaigns)[-window:]
    wr = win_rate(hist)
    pf = profit_factor(hist)
    bad_wr = wr < min_wr
    bad_pf = pf < min_pf
    blocked = bad_wr or bad_pf
    return blocked, {
        "n": float(len(hist)),
        "wr": wr,
        "pf": pf,
        "bad_wr": 1.0 if bad_wr else 0.0,
        "bad_pf": 1.0 if bad_pf else 0.0,
        "warmup": 0.0,
    }


def gate_reason(meta: Dict[str, float], *, month_block: bool = False) -> str:
    """Human reason code for live-parity / research decision tapes."""
    if month_block:
        return "month"
    if float(meta.get("warmup") or 0.0) >= 1.0:
        return "take"
    bad_wr = float(meta.get("bad_wr") or 0.0) >= 1.0
    bad_pf = float(meta.get("bad_pf") or 0.0) >= 1.0
    if bad_wr and bad_pf:
        return "both"
    if bad_wr:
        return "wr"
    if bad_pf:
        return "pf"
    return "take"


def campaigns_from_unit_trades(path: Path) -> List[float]:
    df = pd.read_csv(path)
    g = (
        df.groupby("trade_id", as_index=False)
        .agg(entry_ts=("entry_ts", "first"), net_usd=("net_usd", "sum"))
        .sort_values("entry_ts")
    )
    return [float(x) for x in g["net_usd"].tolist()]


def seed_shadow_nets(
    *,
    unit_trades: Optional[Path] = None,
    window: int = 50,
) -> List[float]:
    path = Path(unit_trades) if unit_trades is not None else DEFAULT_SIZING_UNIT
    nets = campaigns_from_unit_trades(path)
    if window > 0:
        return nets[-window:]
    return nets


def load_shadow_book(path: Path) -> List[float]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        nets = raw.get("nets") or raw.get("campaigns") or []
    else:
        nets = raw
    out: List[float] = []
    for x in nets:
        try:
            out.append(float(x))
        except (TypeError, ValueError):
            continue
    return out


def save_shadow_book(path: Path, nets: Sequence[float], *, meta: Optional[dict] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"nets": [float(x) for x in nets]}
    if meta:
        payload["meta"] = meta
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def append_shadow_campaign(path: Path, net_usd: float, *, keep: int = 500) -> List[float]:
    nets = load_shadow_book(path)
    nets.append(float(net_usd))
    if keep > 0 and len(nets) > keep:
        nets = nets[-keep:]
    save_shadow_book(path, nets)
    return nets
