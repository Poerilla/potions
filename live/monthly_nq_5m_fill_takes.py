"""NQ monthly systems — 5m fill takes for the band vs ORB comparison table.

Signal bars stay on each system's native TF; resting fills resolve on a shared
**5m** tape (Engine ``broker_fills=False`` on HTF signals), matching the
ST+PMC 1m-fill pattern.

Table systems (NQ):
  1. band-max +0.5 · open TP + 2R runner (all weeks) — 1h signal
  2. pct75 ladder ``1_1_7`` / ``2_2_5`` (no w4) — 1h signal
  3. liq-run fade 1:1 reentry HP — strategy on 5m (was 1m)
  4. Monthly ORB overlap daily-ST retest x5 — 4h signal
  5. Monthly ORB restricted scaleout3 — daily signal
  6. Monthly ORB FBO 1/1/3 base — daily signal

Path-only ``2c half+open $1k`` and daily stop-limit cycle are excluded from
the broker-like ranking (no Engine dual-TF path here).

Hub: ``live/state/monthly_nq_5m_fill_takes/``
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .broker_like_replays import _month_end_dates
from .engine import Engine, bars_from_csv
from .models import Bar, StrategyInstance, as_row
from .monthly_atr4_helpers import load_1h
from .monthly_open_atr_extension_band_broker import (
    DEFAULT_ROLLING_BAND_MONTHS,
    build_month_plans,
)
from .monthly_open_liq_run_fade_1r1_reentry_1m_broker import build_hp_month_plans
from .monthly_orb_overlap_st_retest_replay import (
    MARKETS as OVERLAP_MARKETS,
    daily_close_bar_timestamps,
    ensure_4h_cache,
    load_4h_bars,
)
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS as Q_MARKETS
from .replay_audit import POINT_VALUES, audit_units, units_from_live_fills
from .replay_realism import hardened_replay_engine_kwargs
from .run_ledger import log_run
from .spread_model import SpreadModel
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import MARKETS as V2B_MARKETS, load_1m_by_ny_date_any
from .verification import QuietPaperVerificationProvider

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "monthly_nq_5m_fill_takes"
NY = "America/New_York"
FEE = 1.50
DSR = "TRL-2026-00144"
INSTRUMENT = "NQ"


def _progress(hub: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    hub.mkdir(parents=True, exist_ok=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _spread(tick: float) -> SpreadModel:
    return SpreadModel(
        rth_half_spread_ticks=0.5,
        eth_half_spread_ticks=1.0,
        open_widen_half_spread_ticks=1.0,
        low_volume_threshold=50.0,
        low_volume_multiplier=1.5,
        tick_size=tick,
    )


def _utc_z(ts) -> str:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return t.tz_convert("UTC").isoformat().replace("+00:00", "Z")


def _broker_needs_fill(engine: Engine) -> bool:
    broker = engine.broker
    active_ids = getattr(broker, "_active_order_ids", None)
    if active_ids:
        return True
    cache = getattr(broker, "_positions_cache", None)
    if isinstance(cache, dict):
        for pos in cache.values():
            try:
                if int(float(getattr(pos, "quantity", 0) or 0)) != 0:
                    return True
            except (TypeError, ValueError):
                continue
    open_orders = getattr(broker, "open_orders", None)
    if callable(open_orders):
        try:
            if open_orders():
                return True
        except TypeError:
            pass
    return False


def load_nq_5m(hub: Path) -> pd.DataFrame:
    """Full-session 5m OHLC from front-month 1m DBN (cached under hub)."""
    cache = hub / "cache" / "nq_5m_full.parquet"
    if cache.exists():
        _progress(hub, "LOAD 5m cache %s" % cache)
        df = pd.read_parquet(cache)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index, utc=True)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        return df.sort_index()

    cfg = V2B_MARKETS["nq"]
    _progress(hub, "LOAD 1m %s" % cfg.dbn_path)
    gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    frames: List[pd.DataFrame] = []
    for d in sorted(gby.keys()):
        part = gby[d]
        if part is None or part.empty:
            continue
        frames.append(part[["open", "high", "low", "close"] + (["volume"] if "volume" in part.columns else [])])
    if not frames:
        raise RuntimeError("no NQ 1m bars")
    one = pd.concat(frames).sort_index()
    if one.index.tz is None:
        one.index = one.index.tz_localize(NY)
    one = one.tz_convert("UTC")
    _progress(hub, "RESAMPLE 1m→5m rows=%d" % len(one))
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in one.columns:
        agg["volume"] = "sum"
    five = one.resample("5min", label="left", closed="left").agg(agg).dropna(subset=["open", "high", "low", "close"])
    cache.parent.mkdir(parents=True, exist_ok=True)
    five.to_parquet(cache)
    _progress(hub, "WROTE 5m cache bars=%d → %s" % (len(five), cache))
    return five


def bars_from_1h(df: pd.DataFrame, source: str) -> List[Bar]:
    rows: List[Bar] = []
    for ts, row in df.iterrows():
        if pd.isna(row.get("close")):
            continue
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        if min(o, h, l, c) <= 0:
            continue
        rows.append(
            Bar(
                instrument=INSTRUMENT,
                timeframe="1h",
                ts=_utc_z(ts),
                open=o,
                high=h,
                low=l,
                close=c,
                volume=float(row.get("volume", 0.0) or 0.0),
                complete=True,
                source=source,
            )
        )
    return rows


def bars_from_5m_df(df: pd.DataFrame, source: str) -> List[Bar]:
    rows: List[Bar] = []
    vol = df["volume"] if "volume" in df.columns else None
    for ts, row in df.iterrows():
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        if min(o, h, l, c) <= 0:
            continue
        rows.append(
            Bar(
                instrument=INSTRUMENT,
                timeframe="5m",
                ts=_utc_z(ts),
                open=o,
                high=h,
                low=l,
                close=c,
                volume=float(vol.loc[ts]) if vol is not None else 0.0,
                complete=True,
                source=source,
            )
        )
    return rows


def replay_signal_with_5m(
    engine: Engine,
    *,
    signal_bars: Sequence[Bar],
    five_m: pd.DataFrame,
    signal_offset_minutes: int,
    label: str,
    hub: Path,
) -> int:
    """HTF signals (no broker fills) + 5m tape for fills."""
    if int(signal_offset_minutes) < 0:
        raise ValueError("signal_offset_minutes must be >= 0")
    offset = pd.Timedelta(minutes=int(signal_offset_minutes))
    idx = five_m.index
    seen = 0
    skipped = 0
    n = len(signal_bars)
    cursor: Optional[pd.Timestamp] = None

    def replay_5m_until(start: Optional[pd.Timestamp], end: pd.Timestamp) -> int:
        nonlocal seen
        if not _broker_needs_fill(engine):
            return 0
        lo = 0 if start is None else idx.searchsorted(start, side="left")
        hi = idx.searchsorted(end, side="left")
        if lo >= hi:
            return 0
        sl = five_m.iloc[lo:hi]
        vol = sl["volume"] if "volume" in sl.columns else None
        for j, (ts, o, h, l, c) in enumerate(
            zip(sl.index, sl["open"], sl["high"], sl["low"], sl["close"])
        ):
            engine.process_bar(
                Bar(
                    instrument=INSTRUMENT,
                    timeframe="5m",
                    ts=_utc_z(ts),
                    open=float(o),
                    high=float(h),
                    low=float(l),
                    close=float(c),
                    volume=float(vol.iloc[j]) if vol is not None else 0.0,
                    complete=True,
                    source="nq_5m",
                )
            )
            seen += 1
        return len(sl)

    for i, sbar in enumerate(signal_bars):
        signal_ts = pd.Timestamp(sbar.ts)
        if signal_ts.tzinfo is None:
            signal_ts = signal_ts.tz_localize("UTC")
        else:
            signal_ts = signal_ts.tz_convert("UTC")
        signal_ts = signal_ts + offset

        before = seen
        replay_5m_until(cursor, signal_ts)
        if seen == before and not _broker_needs_fill(engine):
            skipped += 1

        shifted = Bar(
            instrument=sbar.instrument,
            timeframe=sbar.timeframe,
            ts=_utc_z(signal_ts),
            open=sbar.open,
            high=sbar.high,
            low=sbar.low,
            close=sbar.close,
            volume=sbar.volume,
            complete=sbar.complete,
            source=sbar.source,
        )
        engine.process_bar(shifted, broker_fills=False)
        cursor = signal_ts

        if (i + 1) % 5000 == 0 or (i + 1) == n:
            _progress(
                hub,
                "  %s signal %d/%d (5m=%d skipped=%d)" % (label, i + 1, n, seen, skipped),
            )

    if len(idx) > 0 and cursor is not None:
        replay_5m_until(cursor, idx[-1] + pd.Timedelta(minutes=5))
    _progress(hub, "  %s done 5m=%d skipped_sig=%d" % (label, seen, skipped))
    return seen


def _audit_and_log(
    *,
    hub: Path,
    slug: str,
    label: str,
    strategy_id: str,
    state_root: Path,
    signal_bars: Sequence[Bar],
    notes: str,
    meta: Dict[str, Any],
) -> Dict[str, float]:
    fills_path = state_root / "fills.csv"
    last = signal_bars[-1] if signal_bars else None
    units = units_from_live_fills(
        fills_path,
        strategy_id,
        last.ts if last else "",
        last.close if last else None,
    )
    audit = audit_units(
        name=label,
        slug=strategy_id,
        source=fills_path,
        bar_source=hub / "cache" / "nq_5m_full.parquet",
        bars=list(signal_bars),
        units=units,
        instrument=INSTRUMENT,
        notes=notes,
        output_root=hub / "audits",
        fee_per_unit=FEE,
    )
    stress = float(audit.intrabar_mtm_dd_usd)
    net = float(audit.net_usd)
    ns = (net / abs(stress)) if abs(stress) > 1e-9 else 0.0
    eq_path = hub / "audits" / strategy_id / "equity_curve.csv"
    metrics = {
        "slug": slug,
        "label": label,
        "strategy_id": strategy_id,
        "trades": float(audit.trades),
        "units": float(audit.units),
        "net_usd": net,
        "stress_dd": stress,
        "close_dd": float(audit.close_mtm_dd_usd),
        "ns": ns,
        "win_units": float(audit.win_units),
        "loss_units": float(audit.loss_units),
        "equity_curve": str(eq_path),
        "state_root": str(state_root),
    }
    (hub / slug / "metrics.json").write_text(
        json.dumps({**metrics, **meta}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    log_run(
        run_class="broker_like",
        variant_slug="nq_5mfill_%s" % slug,
        instrument=INSTRUMENT,
        hub_path=str((hub / slug).relative_to(REPO)),
        net_usd=net,
        stress_dd_usd=stress,
        close_mtm_dd_usd=float(audit.close_mtm_dd_usd),
        ns=ns,
        trades=int(audit.trades),
        units=int(audit.units),
        equity_curve_path=eq_path if eq_path.exists() else None,
        dsr_trial_id=DSR,
        meta=meta,
        notes="5m fill take; " + notes[:180],
    )
    _progress(
        hub,
        "DONE %s net=%+.0f stress=%+.0f N/S=%.2f trades=%d"
        % (slug, net, stress, ns, int(audit.trades)),
    )
    return metrics


def _make_engine(state_root: Path, tick: float) -> FlatFileStore:
    """Create store only; write strategy_instances before constructing Engine."""
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    return store


def _start_engine(store: FlatFileStore, tick: float) -> Engine:
    return Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        tick_size={INSTRUMENT: tick},
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
        **hardened_replay_engine_kwargs(
            slippage_ticks=1.0,
            spread_model=_spread(tick),
        ),
    )


def run_band_1h_5m(
    *,
    hub: Path,
    five_m: pd.DataFrame,
    slug: str,
    label: str,
    entry_mode: str,
    sl_mode: str,
    ladder: Tuple[int, int, int],
    skip_entry_weeks: Sequence[int],
    runner_r: Optional[float],
) -> Dict[str, float]:
    out = hub / slug
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    tick = 0.25
    POINT_VALUES[INSTRUMENT] = 20.0
    DEFAULT_TICK_SIZE[INSTRUMENT] = tick
    plans = build_month_plans(
        Q_MARKETS["NQ"],
        entry_mode=entry_mode,
        sl_mode=sl_mode,
        rolling_window=DEFAULT_ROLLING_BAND_MONTHS,
    )
    (out / "month_plans.json").write_text(
        json.dumps(plans, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    entry_qty = int(sum(ladder))
    skip_tag = "now4" if 4 in {int(w) for w in skip_entry_weeks} else "allw"
    strategy_id = "nq_5mfill_%s_%s" % (slug, skip_tag)
    state_root = out / "states" / strategy_id
    payload: Dict[str, Any] = {
        "tick_size": tick,
        "entry_qty": entry_qty,
        "entry_mode": entry_mode,
        "sl_mode": sl_mode,
        "rolling_window": int(DEFAULT_ROLLING_BAND_MONTHS),
        "timeframe": "1h",
        "month_plans": plans,
        "suppress_alerts": True,
        "skip_entry_weeks": [int(w) for w in skip_entry_weeks],
        "ladder_qtys": list(ladder),
        "require_trade_through": True,
    }
    if runner_r is not None:
        payload["runner_target_r_mult"] = float(runner_r)
    store = _make_engine(state_root, tick)
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="monthly_open_atr_extension_band",
                    version="v5",
                    instrument=INSTRUMENT,
                    broker_instrument=INSTRUMENT,
                    account_mode="paper",
                    enabled=True,
                    timeframes="1h",
                    max_contracts=entry_qty,
                    max_open_orders=64,
                    config_json=json.dumps(payload, sort_keys=True),
                )
            )
        ],
    )
    engine = _start_engine(store, tick)
    bars_1h = bars_from_1h(load_1h(Q_MARKETS["NQ"]), "load_1h")
    _progress(hub, "RUN %s 1h=%d" % (slug, len(bars_1h)))
    replay_signal_with_5m(
        engine,
        signal_bars=bars_1h,
        five_m=five_m,
        signal_offset_minutes=60,
        label=slug,
        hub=hub,
    )
    store.flush_tables()
    return _audit_and_log(
        hub=hub,
        slug=slug,
        label=label,
        strategy_id=strategy_id,
        state_root=state_root,
        signal_bars=bars_1h,
        notes="1h signal + 5m fills; entry=%s sl=%s ladder=%s skip=%s"
        % (entry_mode, sl_mode, ladder, list(skip_entry_weeks)),
        meta={
            "signal_tf": "1h",
            "fill_tf": "5m",
            "entry_mode": entry_mode,
            "sl_mode": sl_mode,
            "ladder": list(ladder),
            "skip_entry_weeks": list(skip_entry_weeks),
        },
    )


def run_liq_fade_5m(*, hub: Path, five_m: pd.DataFrame) -> Dict[str, float]:
    slug = "liq_run_fade_1r1_reentry_hp"
    label = "Liq-run fade 1:1 reentry HP (5m)"
    out = hub / slug
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    tick = 0.25
    POINT_VALUES[INSTRUMENT] = 20.0
    DEFAULT_TICK_SIZE[INSTRUMENT] = tick
    plans = build_hp_month_plans(smoke=0, liq_days=2)
    (out / "month_plans.json").write_text(
        json.dumps(plans, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    # Restrict 5m to plan months for speed
    bars: List[Bar] = []
    for key in sorted(plans.keys()):
        plan = plans[key]
        t0 = pd.Timestamp(plan["month_start_ts"])
        t1 = pd.Timestamp(plan["month_end_ts"])
        if t0.tzinfo is None:
            t0 = t0.tz_localize("UTC")
        if t1.tzinfo is None:
            t1 = t1.tz_localize("UTC")
        seg = five_m[(five_m.index >= t0) & (five_m.index < t1)]
        for ts, row in seg.iterrows():
            o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
            if min(o, h, l, c) <= 0:
                continue
            bars.append(
                Bar(
                    instrument=INSTRUMENT,
                    timeframe="5m",
                    ts=_utc_z(ts),
                    open=o,
                    high=h,
                    low=l,
                    close=c,
                    volume=float(row.get("volume", 0.0) or 0.0),
                    complete=True,
                    source="nq_5m",
                )
            )
    bars.sort(key=lambda b: b.ts)
    strategy_id = "nq_liq_run_fade_1r1_reentry_hp_5m"
    state_root = out / "states" / strategy_id
    store = _make_engine(state_root, tick)
    payload = {
        "tick_size": tick,
        "entry_qty": 10,
        "timeframe": "5m",
        "month_plans": plans,
        "max_reentries": 0,
        "liq_days": 2,
        "suppress_alerts": True,
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="monthly_open_liq_run_fade",
                    version="v1",
                    instrument=INSTRUMENT,
                    broker_instrument=INSTRUMENT,
                    account_mode="paper",
                    enabled=True,
                    timeframes="5m",
                    max_contracts=10,
                    max_open_orders=64,
                    config_json=json.dumps(payload, sort_keys=True),
                )
            )
        ],
    )
    engine = _start_engine(store, tick)
    _progress(hub, "RUN %s 5m bars=%d plans=%d" % (slug, len(bars), len(plans)))
    n = len(bars)
    for i, bar in enumerate(bars, start=1):
        engine.process_bar(bar)
        if i % 200000 == 0 or i == n:
            _progress(hub, "  %s replay %d/%d" % (slug, i, n))
    store.flush_tables()
    return _audit_and_log(
        hub=hub,
        slug=slug,
        label=label,
        strategy_id=strategy_id,
        state_root=state_root,
        signal_bars=bars,
        notes="strategy+fills on 5m; HP lookback; liq first 2 NY days; qty 10",
        meta={"signal_tf": "5m", "fill_tf": "5m", "n_plans": len(plans)},
    )


def run_overlap_4h_5m(*, hub: Path, five_m: pd.DataFrame) -> Dict[str, float]:
    slug = "monthly_orb_overlap_st_retest5"
    label = "Monthly ORB overlap daily-ST retest x5 (4h+5m)"
    out = hub / slug
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    tick = 0.25
    POINT_VALUES[INSTRUMENT] = 20.0
    DEFAULT_TICK_SIZE[INSTRUMENT] = tick
    market = OVERLAP_MARKETS["nq"]
    cache = ensure_4h_cache(market, rebuild=False)
    bars_4h = load_4h_bars(cache, market.instrument)
    daily_close_ts = daily_close_bar_timestamps(bars_4h)
    strategy_id = "nq_monthly_overlap_daily_st_retest5_5mfill"
    state_root = out / "states" / strategy_id
    store = _make_engine(state_root, tick)
    config = {
        "daily_bars_path": str(market.daily_path),
        "daily_close_4h_ts": daily_close_ts,
        "max_attempts_per_cluster": 2,
        "max_concurrent_trades": 2,
        "close_stop_frac": 0.25,
        "retest_qty": 5,
        "record_levels": False,
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="monthly_orb_overlap_st_retest",
                    version="v1",
                    instrument=INSTRUMENT,
                    broker_instrument=INSTRUMENT,
                    account_mode="paper",
                    enabled=True,
                    timeframes="4H",
                    max_contracts=32,
                    max_open_orders=128,
                    config_json=json.dumps(config, sort_keys=True),
                )
            )
        ],
    )
    engine = _start_engine(store, tick)
    _progress(hub, "RUN %s 4h=%d" % (slug, len(bars_4h)))
    replay_signal_with_5m(
        engine,
        signal_bars=bars_4h,
        five_m=five_m,
        signal_offset_minutes=240,
        label=slug,
        hub=hub,
    )
    store.flush_tables()
    return _audit_and_log(
        hub=hub,
        slug=slug,
        label=label,
        strategy_id=strategy_id,
        state_root=state_root,
        signal_bars=bars_4h,
        notes="4h signal + 5m fills; overlap ORB + daily ST retest x5",
        meta={"signal_tf": "4H", "fill_tf": "5m"},
    )


def run_daily_5m(
    *,
    hub: Path,
    five_m: pd.DataFrame,
    slug: str,
    label: str,
    strategy_type: str,
    max_contracts: int,
    config: Dict[str, Any],
) -> Dict[str, float]:
    out = hub / slug
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    tick = 0.25
    POINT_VALUES[INSTRUMENT] = 20.0
    DEFAULT_TICK_SIZE[INSTRUMENT] = tick
    daily_path = REPO / "nq" / "nq_daily.csv"
    bars_d = bars_from_csv(daily_path, INSTRUMENT, "D", source=str(daily_path))
    cfg = dict(config)
    if "month_end_dates" not in cfg:
        cfg["month_end_dates"] = _month_end_dates(bars_d)
    strategy_id = "nq_5mfill_%s" % slug
    state_root = out / "states" / strategy_id
    store = _make_engine(state_root, tick)
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type=strategy_type,
                    version="v1",
                    instrument=INSTRUMENT,
                    broker_instrument=INSTRUMENT,
                    account_mode="paper",
                    enabled=True,
                    timeframes="D",
                    max_contracts=max_contracts,
                    max_open_orders=64,
                    config_json=json.dumps(cfg, sort_keys=True),
                )
            )
        ],
    )
    engine = _start_engine(store, tick)
    # Daily bars stamped by date → treat as left-labeled session; complete ~17:00 ET
    # ≈ 21:00 UTC → offset 17h from midnight date stamp when date-only.
    _progress(hub, "RUN %s daily=%d" % (slug, len(bars_d)))
    replay_signal_with_5m(
        engine,
        signal_bars=bars_d,
        five_m=five_m,
        signal_offset_minutes=17 * 60,
        label=slug,
        hub=hub,
    )
    store.flush_tables()
    return _audit_and_log(
        hub=hub,
        slug=slug,
        label=label,
        strategy_id=strategy_id,
        state_root=state_root,
        signal_bars=bars_d,
        notes="daily signal + 5m fills; " + strategy_type,
        meta={"signal_tf": "D", "fill_tf": "5m", "strategy_type": strategy_type},
    )


def write_ranking(hub: Path, rows: Sequence[Dict[str, float]]) -> str:
    ranked = sorted(rows, key=lambda r: -float(r.get("ns") or 0.0))
    lines = [
        "# NQ monthly systems — broker-like **5m fill** ranking",
        "",
        "Signal TF unchanged per system; fills on shared full-session **5m** tape",
        "(Engine `broker_fills=False` on HTF signals). DSR `%s`." % DSR,
        "",
        "| Rank | System | Signal | Net $ | Stress | N/S | Trades | Units |",
        "|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    email = [
        "potions: NQ monthly 5m fill ranking (broker-like only)",
        "",
        "Hub: %s" % hub,
        "DSR: %s" % DSR,
        "",
    ]
    for i, r in enumerate(ranked, start=1):
        meta_path = hub / str(r["slug"]) / "metrics.json"
        signal = "?"
        if meta_path.exists():
            try:
                signal = str(json.loads(meta_path.read_text()).get("signal_tf") or "?")
            except json.JSONDecodeError:
                pass
        lines.append(
            "| %d | %s | %s | %s | %s | %.2f | %d | %d |"
            % (
                i,
                r.get("label") or r["slug"],
                signal,
                "{:,.0f}".format(float(r["net_usd"])),
                "{:,.0f}".format(float(r["stress_dd"])),
                float(r["ns"]),
                int(r["trades"]),
                int(r["units"]),
            )
        )
        email.append(
            "%d. %s  net=$%s  stress=$%s  N/S=%.2f  trades=%d"
            % (
                i,
                r.get("label") or r["slug"],
                "{:,.0f}".format(float(r["net_usd"])),
                "{:,.0f}".format(abs(float(r["stress_dd"]))),
                float(r["ns"]),
                int(r["trades"]),
            )
        )
    best = ranked[0] if ranked else None
    stance = "research"
    if best and float(best["ns"]) >= 2.0:
        stance = "research — top 5m-fill sleeve by N/S is competitive"
    elif best and float(best["ns"]) >= 1.0:
        stance = "research — edges survive 5m fills but heat remains material"
    elif best:
        stance = "lean reject under 5m fills for leaders below N/S 1"
    lines.extend(["", "## Stance", "", stance, "", "Hub: `%s`" % hub, ""])
    email.extend(["", "Stance: %s" % stance, ""])
    summary = "\n".join(lines)
    (hub / "SUMMARY.md").write_text(summary, encoding="utf-8")
    (hub / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")
    with (hub / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "rank",
                "slug",
                "label",
                "net_usd",
                "stress_dd",
                "ns",
                "trades",
                "units",
            ],
        )
        w.writeheader()
        for i, r in enumerate(ranked, start=1):
            w.writerow(
                {
                    "rank": i,
                    "slug": r["slug"],
                    "label": r.get("label") or r["slug"],
                    "net_usd": r["net_usd"],
                    "stress_dd": r["stress_dd"],
                    "ns": r["ns"],
                    "trades": r["trades"],
                    "units": r["units"],
                }
            )
    (hub / "RUN_COMPLETE.json").write_text(
        json.dumps({"ok": True, "n": len(ranked), "rows": ranked}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return summary


def run(*, output_root: Path, email: bool = False, only: Optional[Sequence[str]] = None) -> int:
    hub = Path(output_root).resolve()
    hub.mkdir(parents=True, exist_ok=True)
    _progress(hub, "START monthly NQ 5m fill takes")
    five_m = load_nq_5m(hub)
    _progress(hub, "5m bars=%d" % len(five_m))

    want = set(only) if only else None
    rows: List[Dict[str, float]] = []

    jobs = [
        (
            "band_max_plus_0p5_runner2r",
            lambda: run_band_1h_5m(
                hub=hub,
                five_m=five_m,
                slug="band_max_plus_0p5_runner2r",
                label="Band-max +0.5 · open TP + 2R runner",
                entry_mode="max",
                sl_mode="plus_0.5",
                ladder=(0, 5, 5),
                skip_entry_weeks=[],
                runner_r=2.0,
            ),
        ),
        (
            "pct75_ladder_1_1_7",
            lambda: run_band_1h_5m(
                hub=hub,
                five_m=five_m,
                slug="pct75_ladder_1_1_7",
                label="pct75 ladder 1/1/7 (no w4)",
                entry_mode="pct75",
                sl_mode="wide_2.5x",
                ladder=(1, 1, 7),
                skip_entry_weeks=[4],
                runner_r=None,
            ),
        ),
        (
            "pct75_ladder_2_2_5",
            lambda: run_band_1h_5m(
                hub=hub,
                five_m=five_m,
                slug="pct75_ladder_2_2_5",
                label="pct75 ladder 2/2/5 (no w4)",
                entry_mode="pct75",
                sl_mode="wide_2.5x",
                ladder=(2, 2, 5),
                skip_entry_weeks=[4],
                runner_r=None,
            ),
        ),
        (
            "liq_run_fade_1r1_reentry_hp",
            lambda: run_liq_fade_5m(hub=hub, five_m=five_m),
        ),
        (
            "monthly_orb_overlap_st_retest5",
            lambda: run_overlap_4h_5m(hub=hub, five_m=five_m),
        ),
        (
            "monthly_orb_restricted_scaleout3",
            lambda: run_daily_5m(
                hub=hub,
                five_m=five_m,
                slug="monthly_orb_restricted_scaleout3",
                label="Monthly ORB restricted scaleout3",
                strategy_type="monthly_orb_restricted_scaleout3",
                max_contracts=3,
                config={
                    "allow_shorts": True,
                    "or_sessions": 3,
                    "max_trades_per_month": 2,
                    "batch_qty": 1,
                    "record_levels": False,
                    "flatten_month_end": True,
                },
            ),
        ),
        (
            "monthly_orb_fbo_113",
            lambda: run_daily_5m(
                hub=hub,
                five_m=five_m,
                slug="monthly_orb_fbo_113",
                label="Monthly ORB FBO 1/1/3",
                strategy_type="monthly_orb_v2b_oco",
                max_contracts=5,
                config={
                    "allow_shorts": True,
                    "be_after": "tp1",
                    "entry_mode": "first_break_opposite",
                    "entry_qty": 5,
                    "eod_stop_to_or_mid": False,
                    "flatten_month_end": True,
                    "flip_after_stop": False,
                    "max_trades_per_month": 2,
                    "or_sessions": 3,
                    "record_levels": False,
                    "runner_r": 2.0,
                    "stop_mode": "close",
                    "tp1_qty": 1,
                    "tp1_r": 0.25,
                    "tp2_qty": 1,
                    "tp2_r": 1.0,
                },
            ),
        ),
    ]

    for slug, fn in jobs:
        if want is not None and slug not in want:
            continue
        try:
            rows.append(fn())
        except Exception:
            tb = traceback.format_exc()
            _progress(hub, "FAILED %s\n%s" % (slug, tb))
            if email:
                send_email(subject="potions: NQ 5m fill FAILED %s" % slug, body=tb[-4000:])
            raise

    summary = write_ranking(hub, rows)
    _progress(hub, "ALL DONE n=%d" % len(rows))
    if email:
        send_email(
            subject="potions: NQ monthly 5m fill ranking (broker-like)",
            body=(hub / "EMAIL.txt").read_text(encoding="utf-8"),
        )
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--email", action="store_true")
    p.add_argument(
        "--only",
        nargs="*",
        default=None,
        help="Optional subset of slugs",
    )
    args = p.parse_args(argv)
    try:
        return run(output_root=args.output_root, email=args.email, only=args.only)
    except Exception:
        tb = traceback.format_exc()
        _progress(args.output_root, "FAILED\n" + tb)
        if args.email:
            send_email(subject="potions: NQ monthly 5m fill batch FAILED", body=tb[-4000:])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
