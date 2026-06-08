"""Flat-file live automation runtime for Potions strategy research.

The runtime is intentionally broker-agnostic and paper-first. Real broker
adapters should implement the same interfaces used by the paper broker.
"""

from .models import AccountMode, OrderIntent, StrategyInstance
from .store import FlatFileStore

__all__ = [
    "AccountMode",
    "FlatFileStore",
    "OrderIntent",
    "StrategyInstance",
]
