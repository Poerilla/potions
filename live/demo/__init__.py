"""Parallel demo / paper-trading runtimes (separate from live/state research studies)."""

from __future__ import annotations

from pathlib import Path

DEMO_ROOT = Path(__file__).resolve().parent


def demo_run_root(name: str = "eurusd_v2b_ungated_paper") -> Path:
    return DEMO_ROOT / name
