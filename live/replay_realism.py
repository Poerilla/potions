from __future__ import annotations

from typing import Optional

from .spread_model import SpreadModel

DEFAULT_SLIPPAGE_TICKS = 1.0
DEFAULT_SPREAD_MODEL = SpreadModel(
    rth_half_spread_ticks=0.5,
    eth_half_spread_ticks=1.0,
    open_widen_half_spread_ticks=1.0,
    low_volume_threshold=50.0,
    low_volume_multiplier=1.5,
    tick_size=0.25,
)


def hardened_replay_engine_kwargs(
    *,
    slippage_ticks: float = DEFAULT_SLIPPAGE_TICKS,
    spread_model: Optional[SpreadModel] = None,
    directional_adverse_path: bool = True,
) -> dict:
    if spread_model is None:
        spread_model = DEFAULT_SPREAD_MODEL
    return {
        "slippage_ticks": slippage_ticks,
        "spread_model": spread_model,
        "directional_adverse_path": directional_adverse_path,
    }
