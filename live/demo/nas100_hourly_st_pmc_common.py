"""Shared config / seed helpers for NAS100 hourly ST+PMC sl50_tp150_3r_1mfill demos."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import Bar, StrategyInstance, as_row
from ..store import FlatFileStore

REPO = Path(__file__).resolve().parents[2]
INSTRUMENT = "NAS100"
TICK = 0.1
VARIANT = "sl50_tp150_3r"
STRATEGY_TYPE = "hourly_st_pmc_retest"
PLUGIN_VERSION = "v2"
DAILY_BARS_PATH = REPO / "fx" / "nas100_daily.csv"
HOURLY_SEED_PATH = REPO / "fx" / "nas100_1h.csv"
SEED_HOURS = 300
# Prefer newest bars from whichever twin has more history.
SIBLING_1M_CANDIDATES = (
    REPO / "live" / "demo" / "nas100_v2b_ungated_paper" / "state" / "bars" / "NAS100_1m.csv",
    REPO / "live" / "demo" / "nas100_v2b_ungated_oanda" / "state" / "bars" / "NAS100_1m.csv",
)
TRACKER_NOTE = (
    "NAS100 ST+PMC sl50_tp150_3r 1m-fill tape N/S 4.59 net +$9.5k stress -$2.1k "
    "(live/state/st_pmc_1mfill_cross_market) — same StrategyPlugin path as US30 fair control"
)


def strategy_config_payload(*, oanda_routing: bool) -> Dict[str, Any]:
    return {
        "close_against_entry_exit": False,
        "daily_bars_path": str(DAILY_BARS_PATH),
        "entry_qty": 1,
        "ma_filter": "none",
        "pmc_cross_exit": False,
        "record_levels": False,
        "runner_qty": 0,
        "runner_stop_to_be_after_tp1": False,
        "runner_target_pts": 0.0,
        "st_flip_exit": False,
        "stop_pts": 50.0,
        "target_pts": 150.0,
        "tick_size": TICK,
        "tp1_qty": 1,
        # Fair-control 1mfill: no retest / BB pyramid (research: BB-add hurt N/S)
        "retest_add_enabled": False,
        "bb_add_enabled": False,
        "paper_only": (not oanda_routing),
        "oanda_routing": bool(oanda_routing),
        "signal_price": "mid",
        "fill_price": "oanda" if oanda_routing else "bid_ask",
        "variant": VARIANT,
        "fill_tape": "1m",
    }


def upsert_strategy_instance(store: FlatFileStore, *, strategy_id: str, oanda_routing: bool) -> None:
    payload = strategy_config_payload(oanda_routing=oanda_routing)
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
                max_contracts=1,
                max_open_orders=16,
                config_json=json.dumps(payload, sort_keys=True),
            )
        ),
    )


def seed_hourly_history(store: FlatFileStore, *, source: str = "nas100_1h_csv_seed") -> int:
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
    """Copy recent 1m bars from already-running NAS100 v2b demos (fill path warmup)."""
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
