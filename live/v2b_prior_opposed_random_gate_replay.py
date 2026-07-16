from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import multiprocessing as mp
import shutil
from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .nq_v2b_prior_opposed_replay import (
    DEFAULT_ST_STRATEGY_IDS,
    PRIOR_OPPOSED_MARKETS,
    Result,
    default_st_fills_path,
    default_st_orders_path,
    load_st_events,
    summarize_units,
)
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import MARKETS, _regime_dates, _rth_bars, load_1m_by_ny_date_any
from .v2b_strategy_replay import AuditBar
from .v2b_st_pmc_alignment_study import REPO


NY = "America/New_York"
DEFAULT_OUTPUT_ROOT = REPO / "live/state/v2b_prior_opposed_random_gate_replays"
METHODS = {
    "unconstrained_event_count",
    "stratified_event_count",
    "stratified_coarse_event_count",
    "shuffled_stpmc_side",
}
FINE_TIME_BUCKETS = [
    "09:30-09:45",
    "09:45-10:30",
    "10:30-12:00",
    "12:00-14:00",
    "14:00-15:30",
]
COARSE_TIME_BUCKETS = [
    "09:30-10:30",
    "10:30-12:30",
    "12:30-14:00",
    "14:00-15:55",
]
_TIME_BUCKET_MODE = "fine"
DBN_FALLBACKS = {
    "nq": REPO / "nq/raw/glbx-mdp3-20100606-20260616.ohlcv-1m.dbn.zst",
    "mnq": REPO / "mnq/raw/glbx-mdp3-20210304-20260303.ohlcv-1m.csv",
}
_WORKER_CONTEXT: Dict[str, object] = {}

SUMMARY_COLUMNS = [
    "seed",
    "method",
    "market",
    "gate_events",
    "filled_campaigns",
    "units",
    "net_usd",
    "closed_dd_usd",
    "intrabar_stress_dd_usd",
    "win_rate_pct",
    "profit_factor",
    "net_over_stress",
    "prior_opposite_entries",
    "causality_violations",
    "long_trades",
    "short_trades",
    "state_root",
    "events_path",
    "warnings",
    "counts_toward_permutation_test",
]


class NullReplayGuard:
    """Seed-freeze logging for anti-leakage protocol (spec FD1/FD10)."""

    def __init__(self, seeds: Sequence[int]):
        self._seeds = tuple(sorted(int(s) for s in seeds))
        self.seed_hash = hashlib.sha256(repr(self._seeds).encode()).hexdigest()[:16]

    def __enter__(self):
        print("[GUARD] Seeds frozen: hash=%s n=%d" % (self.seed_hash, len(self._seeds)), flush=True)
        return self

    def __exit__(self, *args):
        print("[GUARD] Null replay complete. hash=%s" % self.seed_hash, flush=True)


@dataclass(frozen=True)
class ReplayCache:
    market: str
    instrument: str
    regime_dates: List[date]
    bars_by_day: Dict[date, List[Bar]]
    audit_bars: List[AuditBar]
    session_features: pd.DataFrame
    raw_1m_by_day: Dict[date, pd.DataFrame] = field(default_factory=dict)


@dataclass(frozen=True)
class SeedResult:
    seed: int
    method: str
    market: str
    gate_events: int
    filled_campaigns: int
    units: int
    net_usd: float
    closed_dd_usd: float
    intrabar_stress_dd_usd: float
    win_rate_pct: float
    profit_factor: float
    net_over_stress: float
    prior_opposite_entries: int
    causality_violations: int
    long_trades: int
    short_trades: int
    state_root: Path
    events_path: Path
    warnings: str = ""


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _time_bucket_fine(ts: pd.Timestamp) -> str:
    t = ts.time()
    if t < time(9, 45):
        return "09:30-09:45"
    if t < time(10, 30):
        return "09:45-10:30"
    if t < time(12, 0):
        return "10:30-12:00"
    if t < time(14, 0):
        return "12:00-14:00"
    return "14:00-15:30"


def _time_bucket_coarse(ts: pd.Timestamp) -> str:
    t = ts.time()
    if t < time(10, 30):
        return "09:30-10:30"
    if t < time(12, 30):
        return "10:30-12:30"
    if t < time(14, 0):
        return "12:30-14:00"
    return "14:00-15:55"


def _time_bucket(ts: pd.Timestamp) -> str:
    if _TIME_BUCKET_MODE == "coarse":
        return _time_bucket_coarse(ts)
    return _time_bucket_fine(ts)


def _family_display_name(method: str) -> str:
    if method == "stratified_event_count":
        return "stratified_fine_buckets"
    if method == "stratified_coarse_event_count":
        return "stratified_coarse_buckets"
    return method


def _time_buckets_for_method(method: str) -> list[str]:
    if method == "stratified_coarse_event_count":
        return COARSE_TIME_BUCKETS
    if method == "stratified_event_count":
        return FINE_TIME_BUCKETS
    return []


def _opposite_side(side: str) -> str:
    return "short" if str(side).lower() == "long" else "long"


def _side_to_v2b(side: str) -> str:
    return "short" if str(side).lower() == "long" else "long"


def effective_dbn_path(market: str, override: Optional[Path] = None) -> Optional[Path]:
    if override is not None:
        return override
    cfg = MARKETS[market]
    if cfg.dbn_path.exists():
        return None
    fallback = DBN_FALLBACKS.get(market)
    if fallback is not None and fallback.exists():
        return fallback
    return cfg.dbn_path


def _has_full_rth_close(raw_day: Optional[pd.DataFrame], session: date) -> bool:
    rth = _rth_bars(raw_day, session)
    if rth.empty:
        return False
    return bool((rth.index.time >= time(15, 55)).any())


def _load_replay_cache(
    market: str,
    start: date,
    event_start: str,
    event_cutoff: str,
    dbn_path: Optional[Path] = None,
) -> ReplayCache:
    cfg = MARKETS[market]
    if dbn_path is not None:
        cfg = type(cfg)(cfg.market, cfg.instrument, cfg.daily_path, dbn_path, cfg.start, cfg.fee_per_unit)
    print("Loading %s 1m bars for random-gate replay..." % cfg.instrument, flush=True)
    gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    regime_dates = _regime_dates(cfg, gby, start=start)
    regime_dates = [d for d in regime_dates if _has_full_rth_close(gby.get(d), d)]

    start_t = _parse_hhmm(event_start)
    cutoff_t = _parse_hhmm(event_cutoff)
    bars_by_day: Dict[date, List[Bar]] = {}
    audit_bars: List[AuditBar] = []
    session_rows: List[Dict[str, object]] = []
    for day in regime_dates:
        df = _rth_bars(gby.get(day), day)
        if df.empty:
            continue
        opening = df[(df.index.time >= time(9, 30)) & (df.index.time < time(9, 45))]
        or_width = float(opening["high"].max() - opening["low"].min()) if not opening.empty else np.nan
        session_rows.append(
            {
                "session": day.isoformat(),
                "year": day.year,
                "or_width_pts": or_width,
                "regime_ok": True,
                "is_full_rth_session": True,
            }
        )
        day_bars: List[Bar] = []
        for ts, row in df.iterrows():
            ts_s = pd.Timestamp(ts).isoformat()
            bar = Bar(
                instrument=cfg.instrument,
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
            day_bars.append(bar)
            audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
        bars_by_day[day] = day_bars

    features = pd.DataFrame(session_rows)
    if not features.empty:
        try:
            features["or_width_quartile"] = pd.qcut(
                pd.to_numeric(features["or_width_pts"], errors="coerce"),
                4,
                labels=["Q1 low", "Q2", "Q3", "Q4 high"],
                duplicates="drop",
            ).astype(str)
        except ValueError:
            features["or_width_quartile"] = ""
    print("  %s random-gate regime sessions: %d" % (cfg.instrument, len(regime_dates)), flush=True)
    return ReplayCache(
        cfg.market,
        cfg.instrument,
        regime_dates,
        bars_by_day,
        audit_bars,
        features,
        raw_1m_by_day=gby,
    )


def build_eligible_universe(cache: ReplayCache, event_start: str, event_cutoff: str) -> pd.DataFrame:
    start_t = _parse_hhmm(event_start)
    cutoff_t = _parse_hhmm(event_cutoff)
    feature_by_session = cache.session_features.set_index("session").to_dict("index")
    rows: List[Dict[str, object]] = []
    for day in cache.regime_dates:
        features = feature_by_session.get(day.isoformat(), {})
        for bar in cache.bars_by_day.get(day, []):
            ts = pd.Timestamp(bar.ts)
            t = ts.time()
            if t < start_t or t > cutoff_t:
                continue
            for gate_side in ["long", "short"]:
                rows.append(
                    {
                        "market": cache.market,
                        "instrument": cache.instrument,
                        "session": day.isoformat(),
                        "year": day.year,
                        "ts": ts.isoformat(),
                        "time_bucket": _time_bucket(ts),
                        "candidate_gate_side": gate_side,
                        "intended_v2b_side": _side_to_v2b(gate_side),
                        "or_width_pts": features.get("or_width_pts", np.nan),
                        "or_width_quartile": features.get("or_width_quartile", ""),
                        "is_full_rth_session": True,
                        "regime_ok": True,
                    }
                )
    return pd.DataFrame(rows)


def load_real_event_profile(
    *,
    market: str,
    cache: ReplayCache,
    event_start: str,
    event_cutoff: str,
    st_fills_path: Optional[Path] = None,
    st_strategy_id: Optional[str] = None,
) -> pd.DataFrame:
    st_strategy_id = st_strategy_id or DEFAULT_ST_STRATEGY_IDS[market]
    st_fills = st_fills_path or default_st_fills_path(market)
    st_orders = default_st_orders_path(market, st_fills)
    if st_orders.exists() and cache.raw_1m_by_day:
        event_dict = load_st_events(
            st_fills,
            st_strategy_id,
            orders_path=st_orders,
            bars_by_ny_date=cache.raw_1m_by_day,
        )
    else:
        event_dict = load_st_events(st_fills, st_strategy_id)
    session_features = cache.session_features.set_index("session").to_dict("index")
    start_t = _parse_hhmm(event_start)
    cutoff_t = _parse_hhmm(event_cutoff)
    rows: List[Dict[str, object]] = []
    regime_sessions = {d.isoformat() for d in cache.regime_dates}
    for session, events in event_dict.items():
        if session not in regime_sessions:
            continue
        features = session_features.get(session, {})
        for event in events:
            ts = pd.Timestamp(event["ts"])
            if ts.tzinfo is None:
                ts = ts.tz_localize(NY)
            ts = ts.tz_convert(NY)
            if ts.time() < start_t or ts.time() > cutoff_t:
                continue
            gate_side = str(event["side"]).lower()
            rows.append(
                {
                    "market": market,
                    "instrument": cache.instrument,
                    "session": session,
                    "year": ts.year,
                    "ts": ts.isoformat(),
                    "time_bucket": _time_bucket(ts),
                    "candidate_gate_side": gate_side,
                    "intended_v2b_side": _side_to_v2b(gate_side),
                    "or_width_pts": features.get("or_width_pts", np.nan),
                    "or_width_quartile": features.get("or_width_quartile", ""),
                    "source": "real_stpmc_event",
                }
            )
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["session", "ts", "candidate_gate_side"]).reset_index(drop=True)
    return out


def _sample_rows(rng: np.random.Generator, pool: pd.DataFrame, n: int, warnings: List[str], label: str) -> pd.DataFrame:
    if n <= 0:
        return pool.head(0).copy()
    if pool.empty:
        warnings.append(f"{label}:EMPTY_POOL")
        return pool.copy()
    replace = len(pool) < n
    if replace:
        warnings.append(f"{label}:SAMPLED_WITH_REPLACEMENT pool={len(pool)} n={n}")
    idx = rng.choice(pool.index.to_numpy(), size=n, replace=replace)
    return pool.loc[idx].copy()


def generate_events(
    *,
    method: str,
    seed: int,
    universe: pd.DataFrame,
    real_profile: pd.DataFrame,
) -> tuple[pd.DataFrame, List[str]]:
    if method not in METHODS:
        raise ValueError(f"Unknown method: {method}")
    rng = np.random.default_rng(seed)
    warnings: List[str] = []

    if real_profile.empty:
        return real_profile.copy(), ["EMPTY_REAL_PROFILE"]

    if method == "shuffled_stpmc_side":
        out = real_profile.copy()
        sides = out["candidate_gate_side"].to_numpy(copy=True)
        rng.shuffle(sides)
        out["candidate_gate_side"] = sides
        out["intended_v2b_side"] = out["candidate_gate_side"].map(_side_to_v2b)
        out["source"] = f"shuffled_stpmc_side_seed_{seed}"
        return out.sort_values(["session", "ts", "candidate_gate_side"]).reset_index(drop=True), warnings

    samples: List[pd.DataFrame] = []
    if method == "unconstrained_event_count":
        for gate_side, group in real_profile.groupby("candidate_gate_side", dropna=False):
            pool = universe[universe["candidate_gate_side"].astype(str) == str(gate_side)]
            samples.append(_sample_rows(rng, pool, len(group), warnings, f"side={gate_side}"))

    elif method in {"stratified_event_count", "stratified_coarse_event_count"}:
        keys = ["year", "candidate_gate_side", "time_bucket", "or_width_quartile"]
        for key, group in real_profile.groupby(keys, dropna=False):
            mask = pd.Series(True, index=universe.index)
            for col, value in zip(keys, key):
                mask &= universe[col].astype(str) == str(value)
            pool = universe[mask]
            label = "stratum=" + "|".join(str(x) for x in key)
            if pool.empty:
                year, side, _bucket, quartile = key
                fallback = (
                    (universe["year"].astype(str) == str(year))
                    & (universe["candidate_gate_side"].astype(str) == str(side))
                    & (universe["or_width_quartile"].astype(str) == str(quartile))
                )
                pool = universe[fallback]
                warnings.append(f"STRATUM_MERGE_WARNING:{label}:dropped_time_bucket")
            if pool.empty:
                year, side, _bucket, _quartile = key
                fallback = (universe["year"].astype(str) == str(year)) & (
                    universe["candidate_gate_side"].astype(str) == str(side)
                )
                pool = universe[fallback]
                warnings.append(f"STRATUM_MERGE_WARNING:{label}:dropped_or_width")
            if pool.empty:
                side = key[1]
                pool = universe[universe["candidate_gate_side"].astype(str) == str(side)]
                warnings.append(f"STRATUM_MERGE_WARNING:{label}:dropped_year")
            samples.append(_sample_rows(rng, pool, len(group), warnings, label))

    if not samples:
        return universe.head(0).copy(), warnings
    out = pd.concat(samples, ignore_index=True)
    out = out.sort_values(["session", "ts", "candidate_gate_side"]).reset_index(drop=True)
    out["source"] = f"{method}_seed_{seed}"
    return out, warnings


def events_to_dynamic(events: pd.DataFrame) -> Dict[str, List[Dict[str, str]]]:
    out: Dict[str, List[Dict[str, str]]] = {}
    if events.empty:
        return out
    dedup = events.drop_duplicates(["session", "ts", "candidate_gate_side"]).copy()
    for row in dedup.sort_values(["session", "ts"]).itertuples(index=False):
        out.setdefault(str(row.session), []).append(
            {"ts": str(row.ts), "side": str(row.candidate_gate_side).lower()}
        )
    return out


def write_events(output_root: Path, market: str, method: str, seed: int, events: pd.DataFrame) -> tuple[Path, Path]:
    root = output_root / "generated_events" / market / method
    root.mkdir(parents=True, exist_ok=True)
    csv_path = root / f"seed_{seed:06d}_events.csv"
    json_path = root / f"seed_{seed:06d}_events.json"
    events.to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(events_to_dynamic(events), indent=2, sort_keys=True), encoding="utf-8")
    return csv_path, json_path


def run_seed_replay(
    *,
    cache: ReplayCache,
    output_root: Path,
    method: str,
    seed: int,
    events: pd.DataFrame,
    event_json_path: Path,
    force: bool,
    progress: bool = True,
) -> SeedResult:
    cfg = MARKETS[cache.market]
    strategy_id = f"{cache.market}_v2b_random_{method}_seed_{seed:06d}_S_1_1_3"
    state_root = output_root / "results" / cache.market / method / "states" / f"seed_{seed:06d}" / strategy_id
    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type="v2b_scaleout",
        version="v1",
        instrument=cache.instrument,
        broker_instrument=cache.instrument,
        account_mode="paper",
        enabled=True,
        timeframes="1m",
        max_contracts=5,
        max_open_orders=64,
        config_json=json.dumps(
            {
                "market": cache.market,
                "mode": "oco_then_reverse",
                "entry_qty": 5,
                "tp1_qty": 1,
                "tp2_qty": 1,
                "tick_size": 0.25,
                "use_regime_filter": True,
                "start": min(cache.regime_dates).isoformat() if cache.regime_dates else "",
                "regime_dates": [d.isoformat() for d in cache.regime_dates],
                "record_levels": False,
                "dynamic_sizing_events": events_to_dynamic(events),
                "prior_opposite_only": True,
                "prior_opposite_entry_qty": 5,
                "prior_opposite_tp1_qty": 1,
                "prior_opposite_tp2_qty": 1,
                "suppress_alerts": True,
            },
            sort_keys=True,
        ),
    )
    store.write_table("strategy_instances", [as_row(instance)])
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
        **hardened_replay_engine_kwargs(slippage_ticks=1.0),
    )
    for idx, day in enumerate(cache.regime_dates, start=1):
        for bar in cache.bars_by_day.get(day, []):
            engine.process_bar(bar)
        if progress and idx % 500 == 0:
            print("  %s seed %06d: %d/%d sessions" % (cache.instrument, seed, idx, len(cache.regime_dates)), flush=True)
    store.flush_tables()
    result: Result = summarize_units(
        strategy_id,
        state_root,
        cache.audit_bars,
        cache.instrument,
        cfg.fee_per_unit,
        market=cache.market,
        regime_days=len(cache.regime_dates),
        st_events=events_to_dynamic(events),
        start_date=min(cache.regime_dates) if cache.regime_dates else date(1900, 1, 1),
    )
    return SeedResult(
        seed=seed,
        method=method,
        market=cache.market,
        gate_events=len(events.drop_duplicates(["session", "ts", "candidate_gate_side"])),
        filled_campaigns=result.trades,
        units=result.units,
        net_usd=result.net_usd,
        closed_dd_usd=result.closed_dd_usd,
        intrabar_stress_dd_usd=result.stress_dd_usd,
        win_rate_pct=result.win_rate_pct,
        profit_factor=result.profit_factor,
        net_over_stress=result.net_stress,
        prior_opposite_entries=result.prior_opposite_entries,
        causality_violations=result.causality_violations,
        long_trades=result.long_trades,
        short_trades=result.short_trades,
        state_root=state_root,
        events_path=event_json_path,
    )


def seed_result_row(result: SeedResult, warnings: Sequence[str]) -> Dict[str, str]:
    return {
        "seed": str(result.seed),
        "method": result.method,
        "market": result.market,
        "gate_events": str(result.gate_events),
        "filled_campaigns": str(result.filled_campaigns),
        "units": str(result.units),
        "net_usd": "%.2f" % result.net_usd,
        "closed_dd_usd": "%.2f" % result.closed_dd_usd,
        "intrabar_stress_dd_usd": "%.2f" % result.intrabar_stress_dd_usd,
        "win_rate_pct": "%.2f" % result.win_rate_pct,
        "profit_factor": "%.3f" % result.profit_factor if math.isfinite(result.profit_factor) else "inf",
        "net_over_stress": "%.2f" % result.net_over_stress,
        "prior_opposite_entries": str(result.prior_opposite_entries),
        "causality_violations": str(result.causality_violations),
        "long_trades": str(result.long_trades),
        "short_trades": str(result.short_trades),
        "state_root": str(result.state_root),
        "events_path": str(result.events_path),
        "warnings": ";".join(warnings),
        "counts_toward_permutation_test": "TRUE" if result.method in METHODS else "FALSE",
    }


def _run_seed_worker(payload: Dict[str, object]) -> Dict[str, str]:
    cache = _WORKER_CONTEXT["cache"]
    universe = _WORKER_CONTEXT["universe"]
    real_profile = _WORKER_CONTEXT["real_profile"]
    output_root = _WORKER_CONTEXT["output_root"]
    method = str(payload["method"])
    seed = int(payload["seed"])
    force = bool(payload["force"])
    prune_state = bool(payload["prune_state"])
    events, warnings = generate_events(
        method=method,
        seed=seed,
        universe=universe,  # type: ignore[arg-type]
        real_profile=real_profile,  # type: ignore[arg-type]
    )
    _events_csv, events_json = write_events(output_root, cache.market, method, seed, events)  # type: ignore[attr-defined,arg-type]
    result = run_seed_replay(
        cache=cache,  # type: ignore[arg-type]
        output_root=output_root,  # type: ignore[arg-type]
        method=method,
        seed=seed,
        events=events,
        event_json_path=events_json,
        force=force,
        progress=False,
    )
    row = seed_result_row(result, warnings)
    if prune_state:
        shutil.rmtree(result.state_root.parent, ignore_errors=True)
    return row


def normalize_summary_row(row: Dict[str, str]) -> Dict[str, str]:
    out = {col: str(row.get(col, "") or "") for col in SUMMARY_COLUMNS}
    if not out["counts_toward_permutation_test"] and out["method"]:
        out["counts_toward_permutation_test"] = "TRUE" if out["method"] in METHODS else "FALSE"
    return out


def write_csv(path: Path, rows: Iterable[Dict[str, str]]) -> None:
    rows = [normalize_summary_row(row) for row in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_report(output_root: Path, market: str, method: str, summary: pd.DataFrame, real_profile: pd.DataFrame) -> None:
    report_dir = output_root / "results" / market / method
    report_dir.mkdir(parents=True, exist_ok=True)
    if summary.empty:
        text = f"# {market.upper()} {method} Random Gate Replay\n\nNo seed results.\n"
        (report_dir / "REPORT.md").write_text(text, encoding="utf-8")
        return
    net = pd.to_numeric(summary["net_usd"], errors="coerce").fillna(0.0)
    trades = pd.to_numeric(summary["filled_campaigns"], errors="coerce").fillna(0.0)
    real_summary_path = REPO / f"live/state/{market}_v2b_prior_opposed_stpmc_broker_like/summary.csv"
    real_net = np.nan
    real_trades = np.nan
    if real_summary_path.exists():
        real = pd.read_csv(real_summary_path)
        if not real.empty:
            real_net = float(real.iloc[0]["net_usd"])
            real_trades = float(real.iloc[0]["trades"])
    p_value = np.nan
    percentile = np.nan
    if math.isfinite(real_net):
        p_value = float((int((net >= real_net).sum()) + 1) / (len(net) + 1))
        percentile = float((net < real_net).sum() / len(net) * 100.0)

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(net, bins=min(30, max(5, len(net))), color="#9ba7b4", alpha=0.85)
    if math.isfinite(real_net):
        ax.axvline(real_net, color="#b23b3b", linewidth=1.8, linestyle="--", label="Real strict replay")
        ax.legend()
    ax.set_title(f"{market.upper()} {method} net distribution")
    ax.set_xlabel("Net USD")
    ax.set_ylabel("Seeds")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    chart_path = report_dir / "net_distribution.png"
    fig.savefig(chart_path, dpi=150)
    plt.close(fig)

    sample_note = (
        "Allocator-grade note: this report has 200+ random seeds; the p-value is suitable as a first null estimate."
        if len(summary) >= 200
        else "Small-sample note: p-values are directional only until the planned 200+ seed batches are run."
    )
    lines = [
        f"# {market.upper()} {method} Random Delayed-Gate Replay",
        "",
        "True `Engine + PaperBroker + StrategyPlugin` random delayed-arming replay. Strategy rules and broker realism are unchanged; only `dynamic_sizing_events` is randomized.",
        "",
        "| Seeds | Real gate events | Median net | P5 net | P95 net | Median fills | Real net | Real fills | Real net percentile | p(null >= real) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        "| %d | %d | $%.2f | $%.2f | $%.2f | %.1f | %s | %s | %s | %s |"
        % (
            len(summary),
            len(real_profile),
            float(np.percentile(net, 50)),
            float(np.percentile(net, 5)),
            float(np.percentile(net, 95)),
            float(np.percentile(trades, 50)),
            "$%.2f" % real_net if math.isfinite(real_net) else "NA",
            "%.0f" % real_trades if math.isfinite(real_trades) else "NA",
            "%.1f" % percentile if math.isfinite(percentile) else "NA",
            "%.4f" % p_value if math.isfinite(p_value) else "NA",
        ),
        "",
        sample_note,
        "",
        "![Net distribution](net_distribution.png)",
        "",
        "Files:",
        "",
        "- `summary_by_seed.csv`",
        "- `null_distribution.csv`",
        "- generated events under `../../generated_events/%s/%s/`" % (market, method),
    ]
    (report_dir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_batch(
    *,
    market: str,
    method: str,
    iterations: int,
    output_root: Path,
    start: date,
    seed_start: int,
    event_start: str,
    event_cutoff: str,
    force: bool,
    dbn_path: Optional[Path] = None,
    prune_state: bool = False,
    resume: bool = False,
    workers: int = 1,
) -> List[SeedResult]:
    global _TIME_BUCKET_MODE
    _TIME_BUCKET_MODE = "coarse" if method == "stratified_coarse_event_count" else "fine"

    output_root.mkdir(parents=True, exist_ok=True)
    result_dir = output_root / "results" / market / method
    all_seeds = [seed_start + i for i in range(iterations)]

    with NullReplayGuard(all_seeds) as guard:
        cache = _load_replay_cache(market, start, event_start, event_cutoff, dbn_path)
        universe = build_eligible_universe(cache, event_start, event_cutoff)
        real_profile = load_real_event_profile(
            market=market, cache=cache, event_start=event_start, event_cutoff=event_cutoff
        )

        universe_path = output_root / "event_universe" / f"{market}_eligible_events.csv"
        profile_path = output_root / "real_gate_profile" / f"{market}_real_event_profile.csv"
        universe_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        universe.to_csv(universe_path, index=False)
        real_profile.to_csv(profile_path, index=False)
        print("  %s eligible random event rows: %d" % (cache.instrument, len(universe)), flush=True)
        print("  %s real ST+PMC gate events in universe: %d" % (cache.instrument, len(real_profile)), flush=True)

        metadata = {
            "method": method,
            "family_display_name": _family_display_name(method),
            "time_bucket_mode": _TIME_BUCKET_MODE,
            "time_buckets": _time_buckets_for_method(method),
            "seed_start": seed_start,
            "seed_end": seed_start + iterations - 1,
            "seed_hash": guard.seed_hash,
            "seed_hash_source": "null_replay_guard_batch_start",
            "counts_toward_permutation_test": method in METHODS,
        }
        result_dir.mkdir(parents=True, exist_ok=True)
        (result_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

        summary_path = result_dir / "summary_by_seed.csv"
        rows: List[Dict[str, str]] = []
        existing_seeds = set()
        if resume and summary_path.exists():
            existing = pd.read_csv(summary_path, dtype=str).fillna("")
            rows = existing.to_dict("records")
            existing_seeds = {
                int(seed) for seed in existing.get("seed", pd.Series(dtype=str)).astype(str) if seed.isdigit()
            }
            if existing_seeds:
                print(
                    "  %s %s resume: %d existing seeds, next requested seed %06d"
                    % (cache.instrument, method, len(existing_seeds), seed_start),
                    flush=True,
                )
        pending = [seed_start + i for i in range(iterations) if seed_start + i not in existing_seeds]
        for seed in [seed_start + i for i in range(iterations) if seed_start + i in existing_seeds]:
            print("Skipping %s %s seed %06d (already in summary)" % (cache.instrument, method, seed), flush=True)

        results: List[SeedResult] = []
        if workers > 1 and pending:
            print(
                "Running %s %s with %d worker processes for %d pending seeds..."
                % (cache.instrument, method, workers, len(pending)),
                flush=True,
            )
            _WORKER_CONTEXT.clear()
            _WORKER_CONTEXT.update(
                {
                    "cache": cache,
                    "universe": universe,
                    "real_profile": real_profile,
                    "output_root": output_root,
                }
            )
            ctx = mp.get_context("fork")
            tasks = [
                {"seed": seed, "method": method, "force": force, "prune_state": prune_state}
                for seed in pending
            ]
            completed = 0
            with ctx.Pool(processes=workers) as pool:
                for row in pool.imap_unordered(_run_seed_worker, tasks):
                    rows.append(row)
                    rows = sorted(rows, key=lambda r: int(r.get("seed") or 0))
                    completed += 1
                    if completed == 1 or completed % 10 == 0 or completed == len(pending):
                        print(
                            "  %s %s completed %d/%d pending seeds"
                            % (cache.instrument, method, completed, len(pending)),
                            flush=True,
                        )
                    write_csv(summary_path, rows)
        else:
            for i, seed in enumerate(pending, start=1):
                print(
                    "Running %s %s random seed %06d (%d/%d pending)..."
                    % (cache.instrument, method, seed, i, len(pending)),
                    flush=True,
                )
                events, warnings = generate_events(
                    method=method, seed=seed, universe=universe, real_profile=real_profile
                )
                _events_csv, events_json = write_events(output_root, market, method, seed, events)
                result = run_seed_replay(
                    cache=cache,
                    output_root=output_root,
                    method=method,
                    seed=seed,
                    events=events,
                    event_json_path=events_json,
                    force=force,
                )
                results.append(result)
                rows.append(seed_result_row(result, warnings))
                rows = sorted(rows, key=lambda r: int(r.get("seed") or 0))
                write_csv(summary_path, rows)
                if prune_state:
                    shutil.rmtree(result.state_root.parent, ignore_errors=True)

        summary = pd.DataFrame(rows)
        summary.to_csv(result_dir / "null_distribution.csv", index=False)
        write_report(output_root, market, method, summary, real_profile)
        write_index(output_root)
    return results


def write_index(output_root: Path) -> None:
    result_files = sorted((output_root / "results").glob("*/*/REPORT.md")) if (output_root / "results").exists() else []
    lines = [
        "# v2b Prior-Opposed Random Delayed-Gate Replays",
        "",
        "True StrategyPlugin null tests for the prior-opposed delayed-arming gate. These are not completed-trade resamples.",
        "",
        "Current status: first-run NQ controls are smoke/small-sample nulls. Treat the p-values as directional only until the planned 200+ seed batches are complete.",
        "",
        "## Summary",
        "",
        "| Market | Method | Seeds | Median Net | Best Net | Worst Net | Median Fills | Report |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for report in result_files:
        summary_path = report.parent / "summary_by_seed.csv"
        if not summary_path.exists():
            continue
        try:
            summary = pd.read_csv(summary_path)
        except Exception:
            continue
        if summary.empty:
            continue
        net = pd.to_numeric(summary["net_usd"], errors="coerce").fillna(0.0)
        fills = pd.to_numeric(summary["filled_campaigns"], errors="coerce").fillna(0.0)
        lines.append(
            "| %s | `%s` | %d | $%.2f | $%.2f | $%.2f | %.1f | [REPORT](%s) |"
            % (
                report.parent.parent.name.upper(),
                report.parent.name,
                len(summary),
                float(np.percentile(net, 50)),
                float(net.max()),
                float(net.min()),
                float(np.percentile(fills, 50)),
                report.relative_to(output_root),
            )
        )
    lines.extend([
        "",
        "## Reports",
        "",
    ])
    for report in result_files:
        lines.append(f"- [{report.parent.parent.name.upper()} / {report.parent.name}]({report.relative_to(output_root)})")
    (output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run true random delayed-arming v2b gate replays.")
    parser.add_argument("--market", choices=PRIOR_OPPOSED_MARKETS, default="nq")
    parser.add_argument("--markets", default=None, help="Comma-separated markets. Overrides --market.")
    parser.add_argument("--method", choices=sorted(METHODS), default="unconstrained_event_count")
    parser.add_argument("--methods", default=None, help="Comma-separated methods. Overrides --method.")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--start", default="2021-03-04")
    parser.add_argument("--event-start", default="09:30")
    parser.add_argument("--event-cutoff", default="15:30")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--dbn-path", type=Path, default=None)
    parser.add_argument("--no-force", action="store_true")
    parser.add_argument("--prune-state", action="store_true", help="Delete bulky per-seed state after extracting summaries.")
    parser.add_argument("--resume", action="store_true", help="Skip seeds already present in summary_by_seed.csv.")
    parser.add_argument("--skip-missing", action="store_true", help="Skip markets whose effective 1m source is missing.")
    parser.add_argument("--workers", type=int, default=1, help="Parallel seed workers per market/method.")
    args = parser.parse_args(argv)
    start = date.fromisoformat(args.start)
    markets = [m.strip().lower() for m in (args.markets or args.market).split(",") if m.strip()]
    methods = [m.strip() for m in (args.methods or args.method).split(",") if m.strip()]
    for method in methods:
        if method not in METHODS:
            raise SystemExit("Unknown method: %s" % method)
    for market in markets:
        if market not in PRIOR_OPPOSED_MARKETS:
            raise SystemExit("Unknown market: %s" % market)
        dbn_path = args.dbn_path if len(markets) == 1 and args.dbn_path is not None else effective_dbn_path(market)
        if dbn_path is not None and not dbn_path.exists():
            msg = "Missing %s 1m source: %s" % (market.upper(), dbn_path)
            if args.skip_missing:
                print("Skipping: " + msg, flush=True)
                continue
            raise FileNotFoundError(msg)
        for method in methods:
            run_batch(
                market=market,
                method=method,
                iterations=args.iterations,
                output_root=args.output_root,
                start=start,
                seed_start=args.seed_start,
                event_start=args.event_start,
                event_cutoff=args.event_cutoff,
                force=not args.no_force,
                dbn_path=dbn_path,
                prune_state=args.prune_state,
                resume=args.resume,
                workers=max(1, int(args.workers)),
            )
    print("Wrote random-gate results to %s" % args.output_root)
    write_run_manifest(
        args.output_root,
        output_paths=[args.output_root / "INDEX.md"],
        strategy_config={
            "markets": markets,
            "methods": methods,
            "iterations": args.iterations,
            "seed_start": args.seed_start,
            "start": args.start,
            "event_start": args.event_start,
            "event_cutoff": args.event_cutoff,
        },
        broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": 1.50, "directional_adverse_path": True, "spread_model": "default"},
        causality_mode="audit",
        extra={"driver": "v2b_prior_opposed_random_gate_replay"},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
