"""Shared config / seed helpers for US30 hourly ST+PMC demos.

Books (lot-correct, 1m fill tape; hub ``live/state/us30_st_pmc_runner_variants``):
  - sl50_tp150_3r              — fair control, max 1, N/S ≈ 29.4
  - sl50_tp150_runners_2r_10r  — TP1 + 2R + 10R runners, max 3, N/S ≈ 24.1
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from ..models import Bar, StrategyInstance, as_row
from ..store import FlatFileStore

REPO = Path(__file__).resolve().parents[2]
INSTRUMENT = "US30"
TICK = 0.1
STRATEGY_TYPE = "hourly_st_pmc_retest"
PLUGIN_VERSION = "v2"
DAILY_BARS_PATH = REPO / "fx" / "us30_daily.csv"
HOURLY_SEED_PATH = REPO / "fx" / "us30_1h.csv"
SEED_HOURS = 300

# Default book for legacy imports (fair control).
VARIANT = "sl50_tp150_3r"
TRACKER_NOTE = (
    "US30 ST+PMC sl50_tp150_3r 1m-fill lot-correct N/S 29.39 net +$19.0k stress -$0.65k "
    "(live/state/us30_st_pmc_runner_variants; 2026-08-08)"
)

BOOKS: Dict[str, Dict[str, Any]] = {
    "sl50_tp150_3r": {
        "variant": "sl50_tp150_3r",
        "max_contracts": 1,
        "max_open_orders": 16,
        "entry_qty": 1,
        "tp1_qty": 1,
        "runner_qty": 0,
        "runner_target_pts": 0.0,
        "runner_stop_to_be_after_tp1": False,
        "runner_specs": [],
        "tracker": (
            "US30 ST+PMC sl50_tp150_3r 1m-fill lot-correct N/S 29.39 net +$19.0k stress -$0.65k "
            "(live/state/us30_st_pmc_runner_variants; 2026-08-08)"
        ),
    },
    "sl50_tp150_runners_2r_10r": {
        "variant": "sl50_tp150_runners_2r_10r",
        "max_contracts": 3,
        "max_open_orders": 32,
        "entry_qty": 3,
        "tp1_qty": 1,
        "runner_qty": 0,
        "runner_target_pts": 0.0,
        "runner_stop_to_be_after_tp1": True,
        "runner_specs": [
            {"qty": 1, "target_pts": 300.0},
            {"qty": 1, "target_pts": 1500.0},
        ],
        "tracker": (
            "US30 ST+PMC 2R→10R runners 1m-fill lot-correct N/S 24.05 net +$56.1k stress -$2.3k "
            "(live/state/us30_st_pmc_runner_variants; 2026-08-08); bounded max 3"
        ),
    },
}


def book_spec(book: str = VARIANT) -> Dict[str, Any]:
    if book not in BOOKS:
        raise KeyError("unknown US30 ST+PMC book %r; choose from %s" % (book, sorted(BOOKS)))
    return BOOKS[book]


def strategy_config_payload(*, oanda_routing: bool, book: str = VARIANT) -> Dict[str, Any]:
    spec = book_spec(book)
    return {
        "close_against_entry_exit": False,
        "daily_bars_path": str(DAILY_BARS_PATH),
        "entry_qty": int(spec["entry_qty"]),
        "ma_filter": "none",
        "pmc_cross_exit": False,
        "record_levels": False,
        "runner_qty": int(spec["runner_qty"]),
        "runner_stop_to_be_after_tp1": bool(spec["runner_stop_to_be_after_tp1"]),
        "runner_target_pts": float(spec["runner_target_pts"]),
        "runner_specs": list(spec["runner_specs"]),
        "st_flip_exit": False,
        "stop_pts": 50.0,
        "target_pts": 150.0,
        "tick_size": TICK,
        "tp1_qty": int(spec["tp1_qty"]),
        "retest_add_enabled": False,
        "bb_add_enabled": False,
        "paper_only": (not oanda_routing),
        "oanda_routing": bool(oanda_routing),
        "signal_price": "mid",
        "fill_price": "oanda" if oanda_routing else "bid_ask",
        "variant": str(spec["variant"]),
        "fill_tape": "1m",
    }


def upsert_strategy_instance(
    store: FlatFileStore,
    *,
    strategy_id: str,
    oanda_routing: bool,
    book: str = VARIANT,
) -> None:
    spec = book_spec(book)
    payload = strategy_config_payload(oanda_routing=oanda_routing, book=book)
    store.upsert_row(
        "strategy_instances",
        "strategy_id",
        as_row(
            StrategyInstance(
                strategy_id=strategy_id,
                strategy_type=STRATEGY_TYPE,
                version=PLUGIN_VERSION,
                instrument=INSTRUMENT,
                broker_instrument=INSTRUMENT,
                account_mode="paper",
                enabled=True,
                timeframes="1h,1m",
                max_contracts=int(spec["max_contracts"]),
                max_open_orders=int(spec["max_open_orders"]),
                config_json=json.dumps(payload, sort_keys=True),
            )
        ),
    )


def seed_hourly_history(store: FlatFileStore, *, source: str = "us30_1h_csv_seed") -> int:
    """Append recent historical 1h bars so Supertrend has ATR warmup (no strategy replay)."""
    existing = store.read_bars(INSTRUMENT, "1h")
    if len(existing) >= 50:
        return 0
    if not HOURLY_SEED_PATH.exists():
        return 0
    rows: List[Dict[str, str]] = []
    with HOURLY_SEED_PATH.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return 0
    tail = rows[-SEED_HOURS:]
    have = {b.ts for b in existing}
    written = 0
    for raw in tail:
        ts = str(raw.get("ts_event") or raw.get("ts") or "").strip()
        if not ts or ts in have:
            continue
        store.append_bar(
            Bar(
                instrument=INSTRUMENT,
                timeframe="1h",
                ts=ts,
                open=float(raw["open"]),
                high=float(raw["high"]),
                low=float(raw["low"]),
                close=float(raw["close"]),
                volume=float(raw.get("volume") or 0),
                complete=True,
                source=source,
            )
        )
        written += 1
    return written
