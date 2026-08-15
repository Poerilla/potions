from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

import pandas as pd

from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import MARKETS, _regime_dates, _rth_bars, load_1m_by_ny_date_any
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills
from .v2b_st_pmc_alignment_study import REPO


NY = "America/New_York"
PRIOR_OPPOSED_MARKETS = ["nq", "mnq", "es", "ym", "mym"]
DEFAULT_ST_STRATEGY_IDS = {
    market: f"{market}_hourly_st_pmc_sl25_tp75_3r" for market in PRIOR_OPPOSED_MARKETS
}


def default_st_fills_path(market: str) -> Path:
    cross_market = REPO / f"live/state/hourly_st_pmc_strategyplugin_variants_cross_market/{market}/combined_state/fills.csv"
    if cross_market.exists():
        return cross_market
    return REPO / "live/state/hourly_st_pmc_strategyplugin_variants/combined_state/fills.csv"


def default_st_orders_path(market: str, fills_path: Optional[Path] = None) -> Path:
    """Sibling orders.csv next to the ST fills tape used for the gate."""
    if fills_path is not None:
        sibling = fills_path.parent / "orders.csv"
        if sibling.exists():
            return sibling
    cross_market = REPO / f"live/state/hourly_st_pmc_strategyplugin_variants_cross_market/{market}/combined_state/orders.csv"
    if cross_market.exists():
        return cross_market
    return REPO / "live/state/hourly_st_pmc_strategyplugin_variants/combined_state/orders.csv"


@dataclass(frozen=True)
class TouchRefineStats:
    """Audit counters for 1m first-touch refinement of hourly ST fills."""

    events: int = 0
    resolved: int = 0
    unresolved: int = 0
    outside_fill_hour: int = 0
    delay_minutes: tuple = ()

    @property
    def median_delay_minutes(self) -> Optional[float]:
        if not self.delay_minutes:
            return None
        return float(pd.Series(list(self.delay_minutes)).median())


@dataclass(frozen=True)
class Result:
    strategy_id: str
    trades: int
    units: int
    net_usd: float
    closed_dd_usd: float
    stress_dd_usd: float
    win_rate_pct: float
    profit_factor: float
    net_stress: float
    state_root: Path
    instrument: str
    market: str
    regime_days: int
    prior_opposite_entries: int
    causality_violations: int
    long_trades: int
    short_trades: int
    start_date: date
    touch_stats: Optional[TouchRefineStats] = None


def _to_ny_ts(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(NY)
    return ts.tz_convert(NY)


def first_1m_limit_touch(
    bars_by_ny_date: Mapping[date, pd.DataFrame],
    *,
    side: str,
    limit_price: float,
    live_after_ts: Any,
    fill_ts_hourly: Any,
) -> tuple[Optional[pd.Timestamp], str]:
    """Return (first_1m_touch_ts, status).

    Status is one of:
    - ``resolved_in_hour``: first touch inside the left-labeled fill hour
    - ``resolved_outside_hour``: first touch after live_after but outside that hour
    - ``unresolved``: no 1m touch found after live_after
    """

    live_after = _to_ny_ts(live_after_ts)
    fill_hourly = _to_ny_ts(fill_ts_hourly)
    hour_end = fill_hourly + pd.Timedelta(hours=1)
    side_l = str(side).lower()
    if side_l not in {"buy", "sell"}:
        return None, "unresolved"

    day = live_after.date()
    end_day = max(fill_hourly.date(), live_after.date())
    frames: List[pd.DataFrame] = []
    while day <= end_day:
        df = bars_by_ny_date.get(day)
        if df is not None and not df.empty:
            frames.append(df)
        day = day + timedelta(days=1)
    if not frames:
        return None, "unresolved"

    bars = pd.concat(frames).sort_index()
    idx = pd.DatetimeIndex([_to_ny_ts(ts) for ts in bars.index])
    bars = bars.copy()
    bars.index = idx
    after = bars.index > live_after
    if side_l == "buy":
        touched = bars["low"].astype(float) <= float(limit_price)
    else:
        touched = bars["high"].astype(float) >= float(limit_price)
    hits = bars.loc[after & touched]
    if hits.empty:
        return None, "unresolved"

    in_hour = hits[(hits.index >= fill_hourly) & (hits.index < hour_end)]
    if not in_hour.empty:
        return _to_ny_ts(in_hour.index[0]), "resolved_in_hour"
    return _to_ny_ts(hits.index[0]), "resolved_outside_hour"


def touch_stats_from_events(events: Mapping[str, Sequence[Mapping[str, Any]]]) -> TouchRefineStats:
    delays: List[float] = []
    resolved = unresolved = outside = total = 0
    for day_events in events.values():
        for event in day_events:
            total += 1
            if str(event.get("touch_unresolved", "")).lower() in {"1", "true"}:
                unresolved += 1
                continue
            if "fill_ts_hourly" not in event:
                continue
            resolved += 1
            if str(event.get("touch_outside_fill_hour", "")).lower() in {"1", "true"}:
                outside += 1
            try:
                gate_ts = _to_ny_ts(event["ts"])
                hourly_ts = _to_ny_ts(event["fill_ts_hourly"])
                delays.append((gate_ts - hourly_ts).total_seconds() / 60.0)
            except Exception:
                pass
    return TouchRefineStats(
        events=total,
        resolved=resolved,
        unresolved=unresolved,
        outside_fill_hour=outside,
        delay_minutes=tuple(delays),
    )


def rth_session_date_for_ts(ts: Any) -> str:
    """Map an event timestamp to the NY RTH session date that may consume it.

    Post-16:00 timestamps roll to the next calendar day (then next weekday).
    Pre-09:30 timestamps stay on the same calendar day (pre-open same session).
    """

    stamp = _to_ny_ts(ts)
    day = stamp.date()
    if stamp.time() >= pd.Timestamp("16:00").time():
        day = day + timedelta(days=1)
    while day.weekday() >= 5:
        day = day + timedelta(days=1)
    return day.isoformat()


def load_st_resting_limit_events(
    orders_path: Path,
    strategy_id: str,
    *,
    include_cancelled: bool = True,
    available_at_hour_complete: bool = True,
) -> Dict[str, List[Dict[str, str]]]:
    """Gate events when an ST entry limit is knowably resting.

    ST+PMC decides only after a completed left-labeled hour. ``live_after_ts`` is
    that hour's left label (same-bar fill guard), not the wall-clock post time.
    When ``available_at_hour_complete`` is True (default), gate ``ts`` /
    ``available_at_ts`` are ``live_after_ts + 1h`` so v2b cannot arm before ST
    would actually have posted. Set False only for left-label diagnostics.

    Includes filled and optionally cancelled entry limits (posted, not filled).
    """

    orders = pd.read_csv(orders_path)
    orders = orders[orders["strategy_id"].astype(str) == strategy_id].copy()
    orders = orders[
        (orders["order_type"].astype(str) == "limit")
        & (orders["bracket_role"].astype(str).isin(["entry", ""]))
        & (orders["reduce_only"].astype(str).str.lower().isin(["false", "0", ""]))
    ].copy()
    # Prefer explicit entry role when present.
    if "bracket_role" in orders.columns:
        entry_mask = orders["bracket_role"].astype(str) == "entry"
        if entry_mask.any():
            orders = orders[entry_mask].copy()
    if not include_cancelled:
        orders = orders[orders["status"].astype(str) == "filled"].copy()
    orders = orders[orders["live_after_ts"].astype(str).str.len() > 0].copy()
    out: Dict[str, List[Dict[str, str]]] = {}
    for row in orders.itertuples(index=False):
        live_after = _to_ny_ts(row.live_after_ts)
        # Left-labeled hour [H, H+1h) is knowable/posted only at H+1h.
        available = live_after + pd.Timedelta(hours=1) if available_at_hour_complete else live_after
        side = "long" if str(row.side).lower() == "buy" else "short"
        event = {
            "ts": available.isoformat(),
            "side": side,
            "live_after_ts": live_after.isoformat(),
            "available_at_ts": available.isoformat(),
            "source": "st_resting_limit_hour_complete"
            if available_at_hour_complete
            else "st_resting_limit_left_label",
            "order_status": str(getattr(row, "status", "")),
        }
        if getattr(row, "limit_price", None) not in (None, ""):
            event["limit_price"] = str(float(row.limit_price))
        session = rth_session_date_for_ts(live_after)
        out.setdefault(session, []).append(event)
    for session in out:
        out[session].sort(key=lambda e: e["ts"])
    return out


def load_st_events(
    fills_path: Path,
    strategy_id: str,
    *,
    orders_path: Optional[Path] = None,
    bars_by_ny_date: Optional[Mapping[date, pd.DataFrame]] = None,
    entry_reasons: Sequence[str] = ("entry", "runner_entry"),
    gate_mode: str = "fill",
) -> Dict[str, List[Dict[str, str]]]:
    """Load same-session ST+PMC entry events for the prior-opposed gate.

    ``gate_mode``:
    - ``fill``: hourly left-label fill stamps (legacy)
    - ``fill_1m_touch``: first 1m limit touch after ``live_after_ts``
    - ``resting_limit``: ST entry limit knowable at hour-complete (requires ``orders_path``)
    - ``resting_limit_left_label``: diagnostic; uses left-label ``live_after_ts`` as gate time

    When ``orders_path`` and ``bars_by_ny_date`` are both provided and
    ``gate_mode`` is ``fill``, behavior upgrades to ``fill_1m_touch`` for
    backward compatibility with the refined replay path.
    """

    mode = str(gate_mode or "fill")
    if mode in {"resting_limit", "resting_limit_left_label"}:
        if orders_path is None:
            raise ValueError("%s gate_mode requires orders_path" % mode)
        return load_st_resting_limit_events(
            orders_path,
            strategy_id,
            available_at_hour_complete=(mode == "resting_limit"),
        )

    fills = pd.read_csv(fills_path)
    fills = fills[fills["strategy_id"].astype(str) == strategy_id].copy()
    reasons = list(entry_reasons)
    refine = mode == "fill_1m_touch" or (
        mode == "fill" and orders_path is not None and bars_by_ny_date is not None
    )
    if refine:
        # Gate tape should not double-count runner_entry on scaleout ST variants.
        reasons = ["entry"]
    fills = fills[fills["reason"].astype(str).isin(reasons)].copy()
    if fills.empty:
        return {}
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)

    orders_by_id: Dict[str, Any] = {}
    if refine:
        if orders_path is None or not orders_path.exists():
            raise FileNotFoundError(orders_path)
        orders = pd.read_csv(orders_path)
        orders = orders[orders["strategy_id"].astype(str) == strategy_id].copy()
        for row in orders.itertuples(index=False):
            orders_by_id[str(row.broker_order_id)] = row

    out: Dict[str, List[Dict[str, str]]] = {}
    for row in fills.sort_values("ts").itertuples(index=False):
        side = "long" if str(row.side).lower() == "buy" else "short"
        fill_side = str(row.side).lower()
        hourly_ts = _to_ny_ts(row.ts)
        event: Dict[str, str] = {
            "ts": hourly_ts.isoformat(),
            "side": side,
            "fill_ts_hourly": hourly_ts.isoformat(),
        }
        if refine:
            order = orders_by_id.get(str(getattr(row, "broker_order_id", "")))
            limit_price = None if order is None else getattr(order, "limit_price", None)
            live_after = None if order is None else getattr(order, "live_after_ts", None)
            if order is not None and limit_price is not None and live_after not in (None, ""):
                event["live_after_ts"] = str(live_after)
                event["limit_price"] = str(float(limit_price))
                touch_ts, status = first_1m_limit_touch(
                    bars_by_ny_date or {},
                    side=fill_side,
                    limit_price=float(limit_price),
                    live_after_ts=live_after,
                    fill_ts_hourly=hourly_ts,
                )
                if touch_ts is not None:
                    event["ts"] = touch_ts.isoformat()
                    event["available_at_ts"] = touch_ts.isoformat()
                    event["touch_unresolved"] = "false"
                    event["touch_outside_fill_hour"] = "true" if status == "resolved_outside_hour" else "false"
                else:
                    event["touch_unresolved"] = "true"
                    event["touch_outside_fill_hour"] = "false"
            else:
                event["touch_unresolved"] = "true"
                event["touch_outside_fill_hour"] = "false"
        gate_ts = _to_ny_ts(event["ts"])
        out.setdefault(gate_ts.date().isoformat(), []).append(event)
    return out


def summarize_units(
    strategy_id: str,
    state_root: Path,
    audit_bars: List[AuditBar],
    instrument: str,
    fee_per_unit: float,
    *,
    market: str,
    regime_days: int,
    st_events: Dict[str, List[Dict[str, str]]],
    start_date: date,
    touch_stats: Optional[TouchRefineStats] = None,
) -> Result:
    units = units_from_v2b_fills(state_root / "fills.csv", strategy_id)
    audit = fast_intraday_audit(
        strategy_id=strategy_id,
        state_root=state_root,
        bars=audit_bars,
        units=units,
        instrument=instrument,
        fee_per_unit=fee_per_unit,
    )
    net = float(audit["net_usd"])
    stress = float(audit["intrabar_stress_dd_usd"])
    point_value = POINT_VALUES[instrument]
    unit_pnl = [(u.points * point_value - fee_per_unit) for u in units]
    gross_win = sum(v for v in unit_pnl if v > 0)
    gross_loss = abs(sum(v for v in unit_pnl if v <= 0))
    trade_ids = sorted({u.trade_id for u in units})
    wins_by_trade = 0
    side_by_trade: Dict[str, str] = {}
    for tid in trade_ids:
        trade_units = [u for u in units if u.trade_id == tid]
        pnl = sum((u.points * point_value - fee_per_unit) for u in trade_units)
        if trade_units:
            side_by_trade[tid] = "long" if trade_units[0].direction.lower().startswith("long") else "short"
        if pnl > 0:
            wins_by_trade += 1
    validation = validate_prior_opposite_entries(state_root / "fills.csv", strategy_id, st_events)
    return Result(
        strategy_id=strategy_id,
        trades=len(trade_ids),
        units=len(units),
        net_usd=net,
        closed_dd_usd=float(audit["closed_dd_usd"]),
        stress_dd_usd=stress,
        win_rate_pct=100.0 * wins_by_trade / len(trade_ids) if trade_ids else 0.0,
        profit_factor=gross_win / gross_loss if gross_loss else math.inf,
        net_stress=net / abs(stress) if stress else 0.0,
        state_root=state_root,
        instrument=instrument,
        market=market,
        regime_days=regime_days,
        prior_opposite_entries=int(validation["prior_opposite_entries"]),
        causality_violations=int(validation["causality_violations"]),
        long_trades=sum(1 for side in side_by_trade.values() if side == "long"),
        short_trades=sum(1 for side in side_by_trade.values() if side == "short"),
        start_date=start_date,
        touch_stats=touch_stats,
    )


def validate_prior_opposite_entries(
    fills_path: Path,
    strategy_id: str,
    st_events: Dict[str, List[Dict[str, str]]],
) -> Dict[str, int]:
    fills = pd.read_csv(fills_path)
    fills = fills[fills["strategy_id"].astype(str) == strategy_id].copy()
    fills = fills[fills["reason"].astype(str) == "entry"].copy()
    if fills.empty:
        return {"prior_opposite_entries": 0, "causality_violations": 0}
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    prior_count = 0
    violations = 0
    for _trade_id, group in fills.sort_values("ts").groupby("trade_id", dropna=False):
        row = group.iloc[0]
        entry_ts = pd.Timestamp(row["ts"])
        v2b_side = "long" if str(row["side"]).lower() == "buy" else "short"
        wanted = "short" if v2b_side == "long" else "long"
        matched = False
        for event in st_events.get(entry_ts.date().isoformat(), []):
            event_ts = pd.Timestamp(event["ts"])
            if event_ts.tzinfo is None:
                event_ts = event_ts.tz_localize(NY)
            event_ts = event_ts.tz_convert(NY)
            if str(event.get("side", "")).lower() == wanted and event_ts < entry_ts:
                matched = True
        if matched:
            prior_count += 1
        else:
            violations += 1
    return {"prior_opposite_entries": prior_count, "causality_violations": violations}


def _default_output_root(market: str) -> Path:
    return REPO / f"live/state/{market}_v2b_prior_opposed_stpmc_broker_like"


def _has_full_rth_close(raw_day: Optional[pd.DataFrame], session: date) -> bool:
    rth = _rth_bars(raw_day, session)
    if rth.empty:
        return False
    cutoff = pd.Timestamp("15:55").time()
    return bool((rth.index.time >= cutoff).any())


def run(
    output_root: Path,
    force: bool,
    market: str = "nq",
    *,
    st_fills_path: Optional[Path] = None,
    st_orders_path: Optional[Path] = None,
    st_strategy_id: Optional[str] = None,
    start: date = date(2021, 3, 4),
    dbn_path: Optional[Path] = None,
    refine_st_touches: bool = True,
    gate_mode: str = "auto",
    prior_opposite_only: bool = True,
    invalidate_without_opposite_minutes: Optional[int] = None,
    strategy_id_suffix: str = "",
    require_prior_validation: Optional[bool] = None,
    book: str = "S_1_1_3",
) -> Result:
    """Replay gated/provisional v2b.

    ``gate_mode``:
    - ``auto``: 1m touch when orders+bars available, else hourly fill
    - ``fill``: hourly left-label fill stamps
    - ``fill_1m_touch``: first 1m limit touch
    - ``resting_limit``: ST entry limit knowable at hour-complete
    - ``resting_limit_left_label``: diagnostic left-label availability
    """

    market = market.lower()
    book = str(book or "S_1_1_3").strip()
    if book not in {"S_1_1_3", "S_1_1_3_plus_1x10R"}:
        raise ValueError("book must be S_1_1_3 or S_1_1_3_plus_1x10R, got %r" % book)
    cfg = MARKETS[market]
    if dbn_path is not None:
        cfg = replace(cfg, dbn_path=dbn_path)
    instrument = cfg.instrument
    output_root.mkdir(parents=True, exist_ok=True)
    suffix = str(strategy_id_suffix or "")
    book_tag = book
    if prior_opposite_only:
        strategy_id = f"{market}_v2b_prior_opposed_stpmc_only_{book_tag}{suffix}"
    else:
        strategy_id = f"{market}_v2b_provisional_stpmc_{book_tag}{suffix}"
    state_root = output_root / "states" / strategy_id
    if force and state_root.exists():
        shutil.rmtree(state_root)
    # S_1_1_3 = 5 lots (1/1/3 EOD). plus_1x10R adds one targeted runner @ 10R → 6 lots.
    if book == "S_1_1_3_plus_1x10R":
        entry_qty, max_contracts = 6, 6
        targeted_runner_qty, runner_target_r_mult = 1, 10.0
    else:
        entry_qty, max_contracts = 5, 5
        targeted_runner_qty, runner_target_r_mult = None, None
    st_strategy_id = st_strategy_id or DEFAULT_ST_STRATEGY_IDS[market]
    st_fills = st_fills_path or default_st_fills_path(market)
    if not st_fills.exists() and gate_mode not in {"resting_limit", "resting_limit_left_label"}:
        raise FileNotFoundError(st_fills)
    st_orders = st_orders_path or default_st_orders_path(market, st_fills if st_fills.exists() else None)
    print("Loading %s 1m bars..." % instrument, flush=True)
    gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)

    mode = str(gate_mode or "auto")
    if mode == "auto":
        mode = "fill_1m_touch" if (refine_st_touches and st_orders.exists()) else "fill"
    touch_stats = None
    if mode in {"resting_limit", "resting_limit_left_label"}:
        if not st_orders.exists():
            raise FileNotFoundError(st_orders)
        print("Loading ST resting-limit gate events from orders (%s)..." % mode, flush=True)
        st_events = load_st_events(
            st_fills if st_fills.exists() else st_orders,
            st_strategy_id,
            orders_path=st_orders,
            gate_mode=mode,
        )
        n_events = sum(len(v) for v in st_events.values())
        print("  resting-limit events: %d across %d sessions" % (n_events, len(st_events)), flush=True)
    elif mode == "fill_1m_touch":
        if not st_orders.exists():
            raise FileNotFoundError(st_orders)
        print("Refining ST+PMC gate timestamps with 1m first-touch...", flush=True)
        st_events = load_st_events(
            st_fills,
            st_strategy_id,
            orders_path=st_orders,
            bars_by_ny_date=gby,
            gate_mode="fill_1m_touch",
        )
        touch_stats = touch_stats_from_events(st_events)
        print(
            "  ST touch refine: resolved=%d unresolved=%d outside_hour=%d median_delay_min=%s"
            % (
                touch_stats.resolved,
                touch_stats.unresolved,
                touch_stats.outside_fill_hour,
                ("%.1f" % touch_stats.median_delay_minutes) if touch_stats.median_delay_minutes is not None else "n/a",
            ),
            flush=True,
        )
    else:
        st_events = load_st_events(st_fills, st_strategy_id, gate_mode="fill")

    regime_dates = _regime_dates(cfg, gby, start=start)
    regime_dates = [d for d in regime_dates if _has_full_rth_close(gby.get(d), d)]
    regime_dates_iso = [d.isoformat() for d in regime_dates]

    strategy_config: Dict[str, Any] = {
        "market": market,
        "mode": "oco_then_reverse",
        "entry_qty": entry_qty,
        "tp1_qty": 1,
        "tp2_qty": 1,
        "tick_size": 0.25,
        "use_regime_filter": True,
        "start": start.isoformat(),
        "regime_dates": regime_dates_iso,
        "record_levels": False,
        "dynamic_sizing_events": st_events,
        "prior_opposite_only": bool(prior_opposite_only),
        "gate_mode": mode,
        "book": book,
    }
    if targeted_runner_qty is not None:
        strategy_config["targeted_runner_qty"] = int(targeted_runner_qty)
    if runner_target_r_mult is not None:
        strategy_config["runner_target_r_mult"] = float(runner_target_r_mult)
    if prior_opposite_only:
        strategy_config.update(
            {
                "prior_opposite_entry_qty": entry_qty,
                "prior_opposite_tp1_qty": 1,
                "prior_opposite_tp2_qty": 1,
            }
        )
    if invalidate_without_opposite_minutes is not None:
        strategy_config["invalidate_without_opposite_minutes"] = int(invalidate_without_opposite_minutes)

    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type="v2b_scaleout",
        version="v1",
        instrument=instrument,
        broker_instrument=instrument,
        account_mode="paper",
        enabled=True,
        timeframes="1m",
        max_contracts=max_contracts,
        max_open_orders=64,
        config_json=json.dumps(strategy_config, sort_keys=True),
    )
    store.write_table("strategy_instances", [as_row(instance)])
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        **hardened_replay_engine_kwargs(slippage_ticks=1.0),
    )
    audit_bars: List[AuditBar] = []
    for idx, day in enumerate(regime_dates, start=1):
        df = _rth_bars(gby.get(day), day)
        if df.empty:
            continue
        for ts, row in df.iterrows():
            ts_s = pd.Timestamp(ts).isoformat()
            bar = Bar(
                instrument=instrument,
                timeframe="1m",
                ts=ts_s,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(cfg.dbn_path),
            )
            engine.process_bar(bar)
            audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
        if idx % 500 == 0:
            print("  %s %d/%d sessions" % (instrument, idx, len(regime_dates)), flush=True)
    store.flush_tables()

    validate = require_prior_validation if require_prior_validation is not None else bool(prior_opposite_only)
    if validate:
        result = summarize_units(
            strategy_id,
            state_root,
            audit_bars,
            instrument,
            cfg.fee_per_unit,
            market=market,
            regime_days=len(regime_dates),
            st_events=st_events,
            start_date=start,
            touch_stats=touch_stats,
        )
    else:
        # Provisional books are not required to have a prior at entry.
        empty_events: Dict[str, List[Dict[str, str]]] = {}
        result = summarize_units(
            strategy_id,
            state_root,
            audit_bars,
            instrument,
            cfg.fee_per_unit,
            market=market,
            regime_days=len(regime_dates),
            st_events=empty_events,
            start_date=start,
            touch_stats=touch_stats,
        )
        # Recompute prior stats informatively without counting violations.
        informative = validate_prior_opposite_entries(state_root / "fills.csv", strategy_id, st_events)
        result = replace(
            result,
            prior_opposite_entries=int(informative["prior_opposite_entries"]),
            causality_violations=0,
        ) if hasattr(result, "__dataclass_fields__") else result

    write_report(output_root, result, gate_mode=mode, invalidate_minutes=invalidate_without_opposite_minutes)
    data_inputs = [cfg.dbn_path]
    if st_fills.exists():
        data_inputs.append(st_fills)
    if st_orders.exists():
        data_inputs.append(st_orders)
    write_run_manifest(
        output_root,
        data_inputs=data_inputs,
        output_paths=[output_root / "summary.csv", output_root / "INDEX.md", state_root / "fills.csv", state_root / "orders.csv"],
        strategy_config={
            "strategy_id": strategy_id,
            "market": market,
            "start": start.isoformat(),
            "entry_qty": entry_qty,
            "sizing": book,
            "targeted_runner_qty": targeted_runner_qty,
            "runner_target_r_mult": runner_target_r_mult,
            "gate_mode": mode,
            "prior_opposite_only": prior_opposite_only,
            "invalidate_without_opposite_minutes": invalidate_without_opposite_minutes,
        },
        broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": 1.50, "directional_adverse_path": True, "spread_model": "default"},
        causality_mode="audit",
        extra={
            "driver": "nq_v2b_prior_opposed_replay",
            "causality_violations": result.causality_violations,
            "touch_resolved": None if touch_stats is None else touch_stats.resolved,
            "touch_unresolved": None if touch_stats is None else touch_stats.unresolved,
            "touch_outside_fill_hour": None if touch_stats is None else touch_stats.outside_fill_hour,
        },
    )
    return result


def write_report(
    output_root: Path,
    result: Result,
    *,
    gate_mode: str = "",
    invalidate_minutes: Optional[int] = None,
) -> None:
    rows = [
        {
            "strategy_id": result.strategy_id,
            "start_date": result.start_date.isoformat(),
            "trades": str(result.trades),
            "units": str(result.units),
            "net_usd": "%.2f" % result.net_usd,
            "closed_dd_usd": "%.2f" % result.closed_dd_usd,
            "intrabar_stress_dd_usd": "%.2f" % result.stress_dd_usd,
            "win_rate_pct": "%.2f" % result.win_rate_pct,
            "profit_factor": "%.3f" % result.profit_factor,
            "net_over_stress": "%.2f" % result.net_stress,
            "causality_violations": str(result.causality_violations),
            "prior_opposite_entries": str(result.prior_opposite_entries),
            "long_trades": str(result.long_trades),
            "short_trades": str(result.short_trades),
            "gate_mode": str(gate_mode or ""),
            "invalidate_without_opposite_minutes": ""
            if invalidate_minutes is None
            else str(int(invalidate_minutes)),
            "state_root": str(result.state_root),
        }
    ]
    if result.touch_stats is not None:
        rows[0]["touch_resolved"] = str(result.touch_stats.resolved)
        rows[0]["touch_unresolved"] = str(result.touch_stats.unresolved)
        rows[0]["touch_outside_fill_hour"] = str(result.touch_stats.outside_fill_hour)
        rows[0]["touch_median_delay_min"] = (
            ""
            if result.touch_stats.median_delay_minutes is None
            else "%.2f" % result.touch_stats.median_delay_minutes
        )
    with (output_root / "summary.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    title_extra = ""
    if gate_mode:
        title_extra = " (%s)" % gate_mode
    lines = [
        "# %s v2b Prior-Opposed / Provisional ST+PMC Broker-Like Replay%s" % (result.instrument, title_extra),
        "",
        "True `Engine + PaperBroker + StrategyPlugin` replay.",
        "",
        "| Trades | Units | Net | Closed DD | Intrabar Stress DD | Win % | PF | Net/Stress |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
        "| %d | %d | $%.2f | $%.2f | $%.2f | %.2f | %.3f | %.2f |"
        % (
            result.trades,
            result.units,
            result.net_usd,
            result.closed_dd_usd,
            result.stress_dd_usd,
            result.win_rate_pct,
            result.profit_factor,
            result.net_stress,
        ),
        "",
        "## Causality / gate",
        "",
        "- Regime sessions replayed: **%d**" % result.regime_days,
        "- Replay start: **%s**" % result.start_date.isoformat(),
        "- Gate mode: **%s**" % (gate_mode or "n/a"),
        "- Prior-opposite entries found: **%d / %d**" % (result.prior_opposite_entries, result.trades),
        "- Causal violations: **%d**" % result.causality_violations,
        "- Direction mix: **%d long / %d short**" % (result.long_trades, result.short_trades),
    ]
    if invalidate_minutes is not None:
        lines.append("- Invalidate without opposite ST within **%d** minutes of entry" % int(invalidate_minutes))
    if result.touch_stats is not None:
        median = result.touch_stats.median_delay_minutes
        lines.extend(
            [
                "",
                "## ST+PMC 1m first-touch gate timestamps",
                "",
                "- Gate events: **%d**" % result.touch_stats.events,
                "- Resolved 1m touches: **%d**" % result.touch_stats.resolved,
                "- Unresolved (kept hourly stamp): **%d**" % result.touch_stats.unresolved,
                "- Touches outside fill hour: **%d**" % result.touch_stats.outside_fill_hour,
                "- Median delay vs hourly stamp: **%s min**"
                % ("n/a" if median is None else "%.1f" % median),
            ]
        )
    lines.extend(
        [
            "",
            "Files:",
            "",
            "- `summary.csv`",
            "- `states/%s/`" % result.strategy_id,
        ]
    )
    (output_root / "INDEX.md").write_text("\n".join(lines))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Replay v2b only after prior opposite same-market ST+PMC.")
    parser.add_argument("--market", choices=PRIOR_OPPOSED_MARKETS, default="nq")
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--st-fills", type=Path, default=None)
    parser.add_argument("--st-orders", type=Path, default=None)
    parser.add_argument("--st-strategy-id", default=None)
    parser.add_argument("--start", default="2021-03-04", help="First NY session date to consider, YYYY-MM-DD.")
    parser.add_argument("--dbn-path", type=Path, default=None, help="Override the configured 1m DBN/CSV source path.")
    parser.add_argument(
        "--gate-mode",
        choices=["auto", "fill", "fill_1m_touch", "resting_limit", "resting_limit_left_label"],
        default="auto",
    )
    parser.add_argument("--no-prior-opposite-only", action="store_true", help="Trade all regime days (provisional).")
    parser.add_argument(
        "--invalidate-without-opposite-minutes",
        type=int,
        default=None,
        help="Flatten if no opposite ST event within N minutes after entry.",
    )
    parser.add_argument("--no-refine-st-touches", action="store_true", help="Use raw hourly ST fill stamps.")
    parser.add_argument(
        "--book",
        choices=["S_1_1_3", "S_1_1_3_plus_1x10R"],
        default="S_1_1_3",
        help="Unit book. plus_1x10R = freeze 1/1/3 EOD and add one runner targeting 10×R.",
    )
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    try:
        start = date.fromisoformat(args.start)
    except ValueError as exc:
        raise SystemExit("--start must be YYYY-MM-DD") from exc
    output_root = args.output_root or _default_output_root(args.market)
    if args.book == "S_1_1_3_plus_1x10R" and args.output_root is None:
        output_root = REPO / f"live/state/{args.market}_v2b_prior_opposed_plus_1x10R"
    result = run(
        output_root,
        force=not args.no_force,
        market=args.market,
        st_fills_path=args.st_fills,
        st_orders_path=args.st_orders,
        st_strategy_id=args.st_strategy_id,
        start=start,
        dbn_path=args.dbn_path,
        refine_st_touches=not args.no_refine_st_touches,
        gate_mode=args.gate_mode,
        prior_opposite_only=not args.no_prior_opposite_only,
        invalidate_without_opposite_minutes=args.invalidate_without_opposite_minutes,
        book=args.book,
    )
    print("Wrote %s (Net/Stress %.2f)" % (output_root / "INDEX.md", result.net_stress))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
