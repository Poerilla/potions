"""Shared config / seed helpers for EURUSD hourly ST+PMC demos.

Books (lot-correct, 1m fill tape; hub ``live/state/fx_index_metals_st_pmc_runner_variants``):
  - sl50_tp150_3r              — fair control, max 1, N/S ≈ 3.01 (promote)
  - sl50_tp150_runners_2r_10r  — HALF-SIZE (2 lots: TP1 + 2R) vs full 2R→10R N/S 1.80
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import Bar, StrategyInstance, as_row
from ..store import FlatFileStore

REPO = Path(__file__).resolve().parents[2]
INSTRUMENT = "EURUSD"
TICK = 0.00001
STRATEGY_TYPE = "hourly_st_pmc_retest"
PLUGIN_VERSION = "v2"
DAILY_BARS_PATH = REPO / "fx" / "eurusd_daily.csv"
HOURLY_SEED_PATH = REPO / "fx" / "eurusd_1h.csv"
SEED_HOURS = 300
SIBLING_1M_CANDIDATES = (
    REPO / "live" / "demo" / "eurusd_v2b_ungated_paper" / "state" / "bars" / "EURUSD_1m.csv",
    REPO / "live" / "demo" / "eurusd_v2b_ungated_oanda" / "state" / "bars" / "EURUSD_1m.csv",
)

VARIANT = "sl50_tp150_3r"
TRACKER_NOTE = (
    "EURUSD ST+PMC sl50_tp150_3r 1m-fill lot-correct N/S 3.01 net +$64.4k stress -$21.4k "
    "(live/state/fx_index_metals_st_pmc_runner_variants; missed_promote_screen 2026-08-11)"
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
            "EURUSD ST+PMC sl50_tp150_3r 1m-fill lot-correct N/S 3.01 net +$64.4k stress -$21.4k "
            "(filters Jun/Aug + roll WR22%/PF1 → N/S proxy 7.23; missed_promote_screen 2026-08-11)"
        ),
    },
    # Half-size vs full 3-lot 2R→10R (robustness: top-10 concentration).
    "sl50_tp150_runners_2r_10r": {
        "variant": "sl50_tp150_runners_2r_half",
        "max_contracts": 2,
        "max_open_orders": 24,
        "entry_qty": 2,
        "tp1_qty": 1,
        "runner_qty": 0,
        "runner_target_pts": 0.0,
        "runner_stop_to_be_after_tp1": True,
        "runner_specs": [
            {"qty": 1, "target_pts": 0.030},  # 2R of 150 pips
        ],
        "tracker": (
            "EURUSD ST+PMC 2R runner HALF-SIZE (full 2R→10R N/S 1.80 concentrated); "
            "missed_promote_screen 2026-08-11"
        ),
    },
}


def book_spec(book: str = VARIANT) -> Dict[str, Any]:
    if book not in BOOKS:
        raise KeyError("unknown EURUSD ST+PMC book %r; choose from %s" % (book, sorted(BOOKS)))
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
        "stop_pts": 0.0050,
        "target_pts": 0.0150,
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


def seed_hourly_history(store: FlatFileStore, *, source: str = "eurusd_1h_csv_seed") -> int:
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


def inherit_1m_from_running_demos(store: FlatFileStore, *, max_bars: int = 5000) -> int:
    """Copy recent 1m bars from EURUSD v2b demo archives (fill path warmup)."""
    existing = store.read_bars(INSTRUMENT, "1m")
    if len(existing) >= 200:
        return 0
    best: Optional[Path] = None
    best_n = 0
    for path in SIBLING_1M_CANDIDATES:
        if not path.exists():
            continue
        try:
            with path.open(newline="", encoding="utf-8") as fh:
                n = sum(1 for _ in fh) - 1
        except OSError:
            continue
        if n > best_n:
            best_n = n
            best = path
    if best is None or best_n <= 0:
        return 0
    rows: List[Dict[str, str]] = []
    with best.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return 0
    tail = rows[-max_bars:]
    have = {b.ts for b in existing}
    written = 0
    for raw in tail:
        ts = str(raw.get("ts") or raw.get("ts_event") or "").strip()
        if not ts or ts in have:
            continue
        try:
            store.append_bar(
                Bar(
                    instrument=INSTRUMENT,
                    timeframe="1m",
                    ts=ts,
                    open=float(raw["open"]),
                    high=float(raw["high"]),
                    low=float(raw["low"]),
                    close=float(raw["close"]),
                    volume=float(raw.get("volume") or 0),
                    complete=True,
                    source="inherit_%s" % best.parent.parent.parent.name,
                )
            )
            written += 1
        except Exception:
            continue
    return written
