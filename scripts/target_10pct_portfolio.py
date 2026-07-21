#!/usr/bin/env python3
"""Backward-compatible entrypoint — delegates to portfolio_product_tiers.py (Tier B = 10%).

Prefer: python3 scripts/portfolio_product_tiers.py
"""

from __future__ import annotations

import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("portfolio_product_tiers.py")), run_name="__main__")
