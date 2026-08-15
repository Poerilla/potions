"""Parallel demo / paper-trading runtimes (separate from live/state research studies)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

DEMO_ROOT = Path(__file__).resolve().parent


def demo_run_root(name: str = "eurusd_v2b_ungated_paper") -> Path:
    return DEMO_ROOT / name


def next_stream_backoff(
    backoff: float,
    reconnect_max_seconds: float,
    exc: Optional[BaseException] = None,
) -> float:
    """Exponential reconnect backoff with jitter; HTTP 429 uses a higher ceiling."""
    import random

    msg = str(exc or "")
    ceiling = float(reconnect_max_seconds)
    nxt = float(backoff) * 2.0
    if "429" in msg or "Too Many Requests" in msg:
        ceiling = max(ceiling, 300.0)
        nxt = max(nxt, 120.0)
    # Bounded jitter (±20%) so sibling daemons do not reconnect in lockstep.
    jitter = 1.0 + random.uniform(-0.2, 0.2)
    return min(max(nxt * jitter, 1.0), ceiling)
