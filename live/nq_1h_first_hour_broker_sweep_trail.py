"""Broker-like Engine+PaperBroker: first-hour follow 3R, strong + sweep_with_side.

Books:
  - follow_3r_strong_sweep — body=strong AND sweep_with_side (fixed SL at FH open)
  - follow_3r_strong_sweep_st_trail — same entries, hourly ATR SuperTrend 14×3 trail

Sweep = first hour takes prior-day/week high (long follow) or low (short follow),
or London 03:00–09:29 extreme. ST trail uses hour-complete 1h bars (available_at = ts+1h).

If the trail book improves net or N/S, run the HP condition mill. Bounce/approach
stats vs the trailing stop are always recorded; 1m/5m charts only if the trail
level looks significant.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_1h_first_hour_broker_sweep_trail --email
  python -m live.nq_1h_first_hour_broker_sweep_trail --email --smoke
  python -m live.nq_1h_first_hour_broker_sweep_trail --instrument NAS100 --email
  python -m live.nq_1h_first_hour_broker_sweep_trail --instrument NAS100 --email --smoke
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
from datetime import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .futures_intraday_hp_sizeup_lib import annotate_campaigns, ensure_tf_bars
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .notify_email import send_email
from .nq_1h_first_hour_broker_ha import attach_sweep_features
from .nq_1h_first_hour_ha import FH_CONDS
from .nq_5m_large_candle_study import FEE, NQ_5M_CSV, POINT_VALUE, TICK, load_rth_5m, score_nets
from .nq_large_candle_ha_lib import (
    attach_po_context,
    attach_trade_po_labels,
    compare_current_hp,
    load_po_campaigns,
    po_buckets_table,
    profile_frame,
    write_ha_report,
)
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .spread_model import SpreadModel
from .store import FlatFileStore
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT_NQ = REPO / "live" / "state" / "nq_1h_first_hour_broker_sweep_trail"
# Keep NAS100 add-on artifacts under the existing NAS100 futures HP hub.
DEFAULT_OUT_NAS100 = (
    REPO / "live" / "state" / "futures_intraday_hp_nas100_nq_lead" / "trail_gate"
)
NY = "America/New_York"
LONDON_OPEN = time(3, 0)
LONDON_END = time(9, 30)
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
FH_OPEN = time(9, 30)
FH_CLOSE = time(10, 30)
MIN_FH_BARS = 10
MIN_WARMUP_DAYS = 60

NAS100_TICK = 0.1
NAS100_POINT_VALUE = 1.0
NAS100_1M_CSV = REPO / "fx" / "nas100_1m.csv"

INSTRUMENT_SPECS = {
    "NQ": {
        "state_prefix": "nq",
        "tick": float(TICK),
        "point_value": float(POINT_VALUE),
        "fee_per_unit": float(FEE),
        "data_inputs": [NQ_5M_CSV],
        "default_out": DEFAULT_OUT_NQ,
    },
    "NAS100": {
        "state_prefix": "nas100",
        "tick": float(NAS100_TICK),
        "point_value": float(NAS100_POINT_VALUE),
        "fee_per_unit": float(FEE),
        "data_inputs": [NAS100_1M_CSV],
        "default_out": DEFAULT_OUT_NAS100,
    },
}

# Runtime instrument selection (set in main()).
ACTIVE_INSTRUMENT: str = "NQ"
ACTIVE_STATE_PREFIX: str = "nq"
ACTIVE_TICK: float = float(TICK)
ACTIVE_POINT_VALUE: float = float(POINT_VALUE)
ACTIVE_FEE_PER_UNIT: float = float(FEE)
ACTIVE_DEFAULT_OUT: Path = DEFAULT_OUT_NQ
ACTIVE_SOURCE_PREFIX: str = "nq"

ACTIVE_PO_SYMBOL: str = "NQ"  # PO overlay lives in the NQ futures profile suite.

BOOKS: List[Tuple[str, str, Dict]] = [
    (
        "follow_3r_strong_sweep",
        "follow 3R strong + sweep_with_side",
        {"st_trail": False},
    ),
    (
        "follow_3r_strong_sweep_st_trail",
        "follow 3R strong + sweep_with_side + 1h ST trail",
        {"st_trail": True},
    ),
]


def _progress(hub: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    hub.mkdir(parents=True, exist_ok=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _ts_naive_ny(ts) -> str:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize(NY)
    else:
        t = t.tz_convert(NY)
    return t.strftime("%Y-%m-%dT%H:%M:%S")


def build_session_levels(df5_full: pd.DataFrame) -> pd.DataFrame:
    """Causal prior-day / prior-week / London levels keyed by NY calendar date."""
    src = df5_full.copy()
    src["ts"] = pd.to_datetime(src["ts"], utc=True).dt.tz_convert(NY)
    src["session_date"] = src["ts"].dt.strftime("%Y-%m-%d")
    st = src["ts"].dt.time
    rth = src[(st >= RTH_OPEN) & (st < RTH_CLOSE)]
    daily = (
        rth.groupby("session_date", sort=True)
        .agg(rth_high=("high", "max"), rth_low=("low", "min"), rth_close=("close", "last"))
        .reset_index()
    )
    daily["prev_day_high"] = daily["rth_high"].shift(1)
    daily["prev_day_low"] = daily["rth_low"].shift(1)
    dti = pd.to_datetime(daily["session_date"])
    daily["week"] = dti.dt.isocalendar().week.astype(int)
    daily["iso_year"] = dti.dt.isocalendar().year.astype(int)
    week_hl = daily.groupby(["iso_year", "week"], sort=False).agg(
        w_high=("rth_high", "max"), w_low=("rth_low", "min")
    )
    daily = daily.merge(week_hl, left_on=["iso_year", "week"], right_index=True, how="left")
    daily["w_high"] = daily["w_high"].shift(1)
    daily["w_low"] = daily["w_low"].shift(1)
    lon = src[(st >= LONDON_OPEN) & (st < LONDON_END)]
    london = lon.groupby("session_date", sort=False).agg(
        london_high=("high", "max"), london_low=("low", "min")
    )
    out = daily.merge(london, on="session_date", how="left")
    return out[
        [
            "session_date",
            "prev_day_high",
            "prev_day_low",
            "w_high",
            "w_low",
            "london_high",
            "london_low",
        ]
    ]


def build_london_session(symbol: str, df5: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """London pre-RTH window 03:00–09:29 NY per session day."""
    src = ensure_tf_bars(symbol, "5m")
    if src is None or src.empty:
        src = df5
    if src is None or src.empty:
        return pd.DataFrame()
    if "session_date" not in src.columns:
        src = src.copy()
        src["session_date"] = src["ts"].dt.tz_convert(NY).dt.strftime("%Y-%m-%d")
    rows: List[dict] = []
    for day, sess in src.groupby("session_date", sort=False):
        st = sess["ts"].dt.tz_convert(NY).dt.time
        lon = sess[(st >= LONDON_OPEN) & (st < LONDON_END)]
        if len(lon) < 4:
            continue
        london_high = float(lon["high"].max())
        london_low = float(lon["low"].min())
        rows.append(
            {
                "session_date": str(day),
                "london_high": london_high,
                "london_low": london_low,
                "london_range": float(lon["high"].max() - lon["low"].min()),
                "london_close": float(lon["close"].iloc[-1]),
            }
        )
    return pd.DataFrame(rows)


def build_first_hour(df5: pd.DataFrame, *, tick: float) -> pd.DataFrame:
    """One row per session: 09:30–10:30 OHLC + causal first-hour conditions."""
    rows: List[dict] = []
    by_day = {d: g for d, g in df5.groupby("session_date", sort=False)}
    prior_high = prior_low = prior_close = np.nan
    hist_ranges: List[float] = []
    for day, sess in by_day.items():
        st = sess["ts"].dt.tz_convert(NY).dt.time
        fh = sess[(st >= FH_OPEN) & (st < FH_CLOSE)]
        rest = sess[st >= FH_CLOSE]
        or15 = sess[(st >= FH_OPEN) & (st < time(9, 45))]
        if len(fh) < MIN_FH_BARS or rest.empty:
            if len(sess):
                prior_high = float(sess["high"].max())
                prior_low = float(sess["low"].min())
                prior_close = float(sess["close"].iloc[-1])
            continue
        o = float(fh["open"].iloc[0])
        h = float(fh["high"].max())
        l = float(fh["low"].min())
        c = float(fh["close"].iloc[-1])
        rng = h - l
        body = abs(c - o)
        direction = "long" if c > o else ("short" if c < o else "doji")
        close_loc = (c - l) / rng if rng > tick else 0.5
        if close_loc >= 2.0 / 3.0:
            close_third = "upper"
        elif close_loc <= 1.0 / 3.0:
            close_third = "lower"
        else:
            close_third = "mid"
        br = body / rng if rng > tick else 0.0
        if br >= 0.66:
            body_b = "strong"
        elif br <= 0.33:
            body_b = "weak"
        else:
            body_b = "mid"
        if np.isfinite(prior_high) and rng > 0:
            if l > prior_high:
                vs_prior = "above_pdh"
            elif h < prior_low:
                vs_prior = "below_pdl"
            else:
                vs_prior = "overlap"
        else:
            vs_prior = "na"
        gap = o - prior_close if np.isfinite(prior_close) else 0.0
        if not np.isfinite(prior_close) or abs(gap) < tick:
            gap_dir = "flat"
        elif gap > 0:
            gap_dir = "gap_up"
        else:
            gap_dir = "gap_down"
        if gap_dir == "flat" or direction == "doji":
            gap_vs = "flat"
        elif (gap_dir == "gap_up" and direction == "long") or (gap_dir == "gap_down" and direction == "short"):
            gap_vs = "gap_with"
        else:
            gap_vs = "gap_against"
        if len(or15) >= 2:
            o15 = float(or15["open"].iloc[0])
            c15 = float(or15["close"].iloc[-1])
            or15_dir = "long" if c15 > o15 else ("short" if c15 < o15 else "doji")
        else:
            or15_dir = "na"
        if or15_dir in ("long", "short") and direction in ("long", "short"):
            or15_vs = "or15_agree" if or15_dir == direction else "or15_oppose"
        else:
            or15_vs = "na"
        # causal expanding p99/p95/p90/p80 of prior first-hour ranges
        p99 = p95 = p90 = p80 = np.nan
        if len(hist_ranges) >= MIN_WARMUP_DAYS:
            s = pd.Series(hist_ranges, dtype=float)
            p99 = float(s.quantile(0.99))
            p95 = float(s.quantile(0.95))
            p90 = float(s.quantile(0.90))
            p80 = float(s.quantile(0.80))
        is_p99 = bool(np.isfinite(p99) and rng >= p99)
        is_p95 = bool(np.isfinite(p95) and rng >= p95)
        is_p90 = bool(np.isfinite(p90) and rng >= p90)
        is_p80 = bool(np.isfinite(p80) and rng >= p80)
        if np.isfinite(p99) and rng >= p99:
            size_b = "fh_p99"
        elif np.isfinite(p95) and rng >= p95:
            size_b = "fh_p95"
        elif np.isfinite(p90) and rng >= p90:
            size_b = "fh_p90"
        elif np.isfinite(p80) and rng >= p80:
            size_b = "fh_p80"
        elif np.isfinite(p80):
            size_b = "fh_lt_p80"
        else:
            size_b = "warmup"
        rows.append(
            {
                "session_date": day,
                "ts": fh["ts"].iloc[-1],
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": float(fh["volume"].sum()) if "volume" in fh.columns else 0.0,
                "range": rng,
                "body": body,
                "dir": direction,
                "n_bars": int(len(fh)),
                "year": int(pd.Timestamp(day).year),
                "hour": 10,
                "p99_thr": p99,
                "p95_thr": p95,
                "p90_thr": p90,
                "p80_thr": p80,
                "is_p99": is_p99,
                "is_p95": is_p95,
                "is_p90": is_p90,
                "is_p80": is_p80,
                "fh_size": size_b,
                "fh_body": body_b,
                "fh_close_third": close_third,
                "fh_vs_prior": vs_prior,
                "or15_vs_fh": or15_vs,
                "gap_vs_fh": gap_vs,
            }
        )
        hist_ranges.append(rng)
        prior_high = float(sess["high"].max())
        prior_low = float(sess["low"].min())
        prior_close = float(sess["close"].iloc[-1])
    out = pd.DataFrame(rows)
    if not out.empty:
        out["is_any"] = out["dir"].isin(["long", "short"]) & out["p90_thr"].notna()
    return out


def run_book(
    *,
    hub: Path,
    slug: str,
    label: str,
    cfg: Dict,
    df5: pd.DataFrame,
    h1: Optional[pd.DataFrame],
    levels_path: Path,
    force: bool,
) -> dict:
    strategy_id = "%s_fh_%s" % (ACTIVE_STATE_PREFIX, slug)
    state_root = hub / "states" / strategy_id
    metrics_path = state_root / "metrics.json"
    if (not force) and metrics_path.exists():
        _progress(hub, "CACHE %s" % strategy_id)
        return json.loads(metrics_path.read_text(encoding="utf-8"))

    POINT_VALUES[ACTIVE_INSTRUMENT] = ACTIVE_POINT_VALUE
    DEFAULT_TICK_SIZE[ACTIVE_INSTRUMENT] = ACTIVE_TICK
    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    trail = bool(cfg.get("st_trail"))
    trail_log = hub / ("%s_trail_events.jsonl" % slug)
    if trail_log.exists():
        trail_log.unlink()
    payload = {
        "tick_size": ACTIVE_TICK,
        "entry_qty": 1,
        "r_mult": 3.0,
        "fade": False,
        "fh_start": "09:30",
        "fh_end": "10:30",
        "bar_minutes": 5,
        "eod_cutoff": "15:59",
        "min_fh_bars": 10,
        "require_fh_body": "strong",
        "require_sweep_side": "sweep_with_side",
        "strong_body_min": 0.66,
        "session_levels_path": str(levels_path),
        "st_trail": trail,
        "st_atr_len": 14,
        "st_atr_mult": 3.0,
        "trail_log_path": str(trail_log) if trail else "",
        "suppress_alerts": True,
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="first_hour_follow",
                    version="v1",
                    instrument=ACTIVE_INSTRUMENT,
                    broker_instrument=ACTIVE_INSTRUMENT,
                    account_mode="paper",
                    enabled=True,
                    timeframes="5m,1h" if trail else "5m",
                    max_contracts=8,
                    max_open_orders=16,
                    config_json=json.dumps(payload, sort_keys=True),
                )
            )
        ],
    )
    spread = SpreadModel(
        rth_half_spread_ticks=0.5,
        eth_half_spread_ticks=1.0,
        open_widen_half_spread_ticks=1.0,
        low_volume_threshold=1.0 if ACTIVE_INSTRUMENT == "NAS100" else 50.0,
        low_volume_multiplier=1.5,
        tick_size=ACTIVE_TICK,
    )
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        tick_size={ACTIVE_INSTRUMENT: ACTIVE_TICK},
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
        **hardened_replay_engine_kwargs(slippage_ticks=1.0, spread_model=spread),
    )

    events: List[Tuple[pd.Timestamp, int, str, pd.Series]] = []
    for _, row in df5.iterrows():
        events.append((pd.Timestamp(row["ts"]), 1, "5m", row))
    if trail and h1 is not None and not h1.empty:
        for _, row in h1.iterrows():
            events.append((pd.Timestamp(row["ts"]), 0, "1h", row))
    events.sort(key=lambda x: (x[0], x[1]))
    _progress(hub, "RUN %s events=%s trail=%s" % (strategy_id, f"{len(events):,}", trail))
    audit_bars: List[AuditBar] = []
    n = 0
    for ts, _prio, tf, row in events:
        ts_s = _ts_naive_ny(ts)
        bar = Bar(
            instrument=ACTIVE_INSTRUMENT,
            timeframe=tf,
            ts=ts_s,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0.0) or 0.0),
            complete=True,
            source=("%s_5m" % ACTIVE_SOURCE_PREFIX) if tf == "5m" else ("%s_1h" % ACTIVE_SOURCE_PREFIX),
        )
        engine.process_bar(bar, broker_fills=(tf == "5m"))
        if tf == "5m":
            audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
        n += 1
        if n % 50000 == 0:
            _progress(hub, "  %s %d/%d" % (strategy_id, n, len(events)))
    store.flush_tables()

    units = units_from_v2b_fills(state_root / "fills.csv", strategy_id)
    audit = fast_intraday_audit(
        strategy_id=strategy_id,
        state_root=state_root,
        bars=audit_bars,
        units=units,
        instrument=ACTIVE_INSTRUMENT,
        fee_per_unit=ACTIVE_FEE_PER_UNIT,
    )
    net = float(audit.get("net_usd") or 0.0)
    stress = float(audit.get("intrabar_stress_dd_usd") or 0.0)
    trades = int(audit.get("trades") or len({u.trade_id for u in units}))
    wr = float(audit.get("win_rate") or 0.0)
    if wr > 1.0:
        wr = wr / 100.0
    bounce = summarize_trail_events(trail_log) if trail else {}
    metrics = {
        "strategy_id": strategy_id,
        "slug": slug,
        "label": label,
        "bars": len(audit_bars),
        "events": n,
        "units": int(audit.get("units") or len(units)),
        "trades": trades,
        "win_rate": wr,
        "net_usd": net,
        "closed_dd_usd": float(audit.get("closed_dd_usd") or 0.0),
        "intrabar_stress_dd_usd": stress,
        "net_over_stress": (net / abs(stress)) if stress else 0.0,
        "max_open_units": int(audit.get("max_open_units") or 0),
        "config": payload,
        "bounce": bounce,
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _progress(
        hub,
        "DONE %s trades=%d WR=%.1f%% net=$%+.0f stress=$%.0f N/S=%.2f"
        % (slug, trades, wr * 100.0, net, stress, metrics["net_over_stress"]),
    )
    return metrics


def summarize_trail_events(path: Path) -> dict:
    if not path.exists():
        return {}
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        return {}
    df = pd.DataFrame(rows)
    by = df.groupby("trade_id") if "trade_id" in df.columns else None
    n_trades = int(df["trade_id"].nunique()) if by is not None else 0
    n_approach = int((df["event"] == "approach").sum()) if "event" in df.columns else 0
    n_bounce = int((df["event"] == "bounce").sum()) if "event" in df.columns else 0
    n_agr = int((df["event"] == "aggressive_bounce").sum()) if "event" in df.columns else 0
    n_hit = int((df["event"] == "hit_bar").sum()) if "event" in df.columns else 0
    n_mod = int((df["event"] == "trail_modify").sum()) if "event" in df.columns else 0
    trades_with_bounce = 0
    trades_with_agr = 0
    trades_with_approach = 0
    max_bounce = []
    if by is not None:
        for _, g in by:
            ev = set(g["event"].astype(str)) if "event" in g.columns else set()
            if {"approach", "bounce", "aggressive_bounce", "hit_bar"} & ev:
                trades_with_approach += 1
            if {"bounce", "aggressive_bounce"} & ev:
                trades_with_bounce += 1
            if "aggressive_bounce" in ev:
                trades_with_agr += 1
            if "away_pts" in g.columns:
                mx = pd.to_numeric(g.loc[g["event"].isin(["bounce", "aggressive_bounce"]), "away_pts"], errors="coerce")
                if mx.notna().any():
                    max_bounce.append(float(mx.max()))
    bounce_rate = (trades_with_bounce / trades_with_approach) if trades_with_approach else 0.0
    agr_rate = (trades_with_agr / n_trades) if n_trades else 0.0
    med_bounce = float(np.median(max_bounce)) if max_bounce else 0.0
    significant = bool(
        (trades_with_approach >= 40 and bounce_rate >= 0.25)
        or (n_trades >= 40 and agr_rate >= 0.15)
        or (len(max_bounce) >= 25 and med_bounce >= 15.0)
    )
    return {
        "n_trades_logged": n_trades,
        "n_trail_modify": n_mod,
        "n_approach_bars": n_approach,
        "n_bounce_bars": n_bounce,
        "n_aggressive_bars": n_agr,
        "n_hit_bars": n_hit,
        "trades_with_approach": trades_with_approach,
        "trades_with_bounce": trades_with_bounce,
        "trades_with_aggressive": trades_with_agr,
        "bounce_rate_given_approach": bounce_rate,
        "aggressive_rate_of_trades": agr_rate,
        "median_bounce_pts": med_bounce,
        "significant": significant,
    }


def campaigns_from_units(hub: Path, slug: str) -> pd.DataFrame:
    from .nq_1h_first_hour_broker_ha import _to_ny

    path = hub / "states" / ("%s_fh_%s" % (ACTIVE_STATE_PREFIX, slug)) / "unit_trades.csv"
    if not path.exists():
        return pd.DataFrame()
    raw = pd.read_csv(path)
    raw["entry_ts"] = _to_ny(raw["entry_ts"])
    raw["exit_ts"] = _to_ny(raw["exit_ts"])
    raw["side"] = raw["direction"].astype(str).str.lower()
    raw["net_usd"] = pd.to_numeric(raw["net_usd"], errors="coerce")
    raw["session_date"] = raw["entry_ts"].dt.strftime("%Y-%m-%d")
    out = raw.rename(columns={"trade_id": "campaign_id"}).copy()
    out["book"] = slug
    out["symbol"] = ACTIVE_INSTRUMENT
    out["family"] = "%s_1h_first_hour_broker" % ACTIVE_STATE_PREFIX
    out["win"] = out["net_usd"] > 0
    out["dow"] = out["entry_ts"].dt.day_name()
    out["year"] = out["entry_ts"].dt.year
    out["week_of_month"] = ((out["entry_ts"].dt.day - 1) // 7 + 1).astype(int)
    return out.sort_values("entry_ts").reset_index(drop=True)


def maybe_hp_mill(hub: Path, slug: str, df5: pd.DataFrame) -> None:
    hp_hub = hub / "hp_mill"
    hp_hub.mkdir(parents=True, exist_ok=True)
    _progress(hub, "HP mill on %s ..." % slug)
    camp = campaigns_from_units(hub, slug)
    if camp.empty:
        _progress(hub, "  no campaigns")
        return
    fh = build_first_hour(df5, tick=ACTIVE_TICK)
    london = build_london_session(ACTIVE_INSTRUMENT, df5)
    po = load_po_campaigns(lambda m: _progress(hub, m))
    # PO overlay must be attached to the first-hour candle dataframe
    # before attaching per-trade PO-state labels.
    fh = attach_po_context(fh, po, p90_col="is_any", progress=lambda m: _progress(hub, m))
    camp = annotate_campaigns(camp, ACTIVE_INSTRUMENT)
    camp = attach_trade_po_labels(camp, fh)
    camp = attach_sweep_features(camp, fh, london)
    camp.to_csv(hp_hub / ("%s_campaigns.csv" % slug), index=False)
    extra = list(FH_CONDS)
    table, baseline, notables = profile_frame(camp, extra, 40)
    if not table.empty:
        table.to_csv(hp_hub / ("%s_buckets.csv" % slug), index=False)
    pd.DataFrame(notables).to_csv(hp_hub / ("%s_notables.csv" % slug), index=False)
    current_cmp = compare_current_hp({slug: camp}, po_buckets_table())
    if not current_cmp.empty:
        current_cmp.to_csv(hp_hub / ("%s_vs_current_hp.csv" % slug), index=False)
    core = [
        {
            "label": slug,
            "n": baseline["n"],
            "wr": baseline["wr"],
            "avg": baseline["avg"],
            "net": baseline["net"],
            "stress": baseline["stress"],
            "ns": baseline["ns"],
            "pf": 0.0,
        }
    ]
    write_ha_report(
        hp_hub,
        title="%s FH follow 3R strong+sweep ST-trail HP mill" % ACTIVE_INSTRUMENT,
        universe=(
            "Universe: broker-like `follow_3r_strong_sweep_st_trail` (n=%d, WR=%.1f%%, net=$%.0f, N/S=%.2f). "
            "HP mill after trail improved the gated book."
            % (baseline["n"], 100 * baseline["wr"], baseline["net"], baseline["ns"])
        ),
        email_subject="potions: %s FH strong+sweep ST-trail HP mill" % ACTIVE_INSTRUMENT,
        core=core,
        hp_sleeves=[],
        notables_by_book={slug: notables},
        current_cmp=current_cmp,
        po_n=int(len(po)),
        extra_notes=[
            "Trail book only — gated strong + sweep_with_side entries, hourly ST trail exits.",
            "Diagnostic, not a promotion gate.",
        ],
    )


def plot_bounce_charts(hub: Path, slug: str, df5: pd.DataFrame, bounce: dict) -> int:
    """5m (and 1m when cheap) charts of aggressive trail bounces. Returns n written."""
    log_path = hub / ("%s_trail_events.jsonl" % slug)
    if not log_path.exists() or not bounce.get("significant"):
        return 0
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    df = pd.DataFrame(rows)
    agr = df[df["event"].astype(str) == "aggressive_bounce"].copy()
    if agr.empty:
        agr = df[df["event"].astype(str) == "bounce"].copy()
    if agr.empty:
        return 0
    agr["away_pts"] = pd.to_numeric(agr.get("away_pts"), errors="coerce")
    agr = agr.sort_values("away_pts", ascending=False)
    days = list(agr["session_date"].astype(str).drop_duplicates().head(24))
    out_dir = hub / "trail_bounce_charts"
    out_dir.mkdir(parents=True, exist_ok=True)
    units = campaigns_from_units(hub, slug)
    n_written = 0
    for day in days:
        sess = df5[df5["session_date"].astype(str) == day]
        if sess.empty:
            continue
        day_ev = df[df["session_date"].astype(str) == day]
        fig, ax = plt.subplots(figsize=(16, 7.0))
        x = np.arange(len(sess))
        o = sess["open"].to_numpy(float)
        h = sess["high"].to_numpy(float)
        l = sess["low"].to_numpy(float)
        c = sess["close"].to_numpy(float)
        up = c >= o
        ax.vlines(x, l, h, color=np.where(up, "#2e7d32", "#c62828"), linewidth=0.8, zorder=3)
        body_h = np.maximum(np.abs(c - o), (h.max() - l.min()) * 0.001)
        for xi, oi, ci, uu in zip(x, o, c, up):
            ax.add_patch(
                plt.Rectangle(
                    (xi - 0.32, min(oi, ci)),
                    0.64,
                    body_h[int(xi)],
                    facecolor="#2e7d32" if uu else "#c62828",
                    edgecolor="#1b5e20" if uu else "#8e0000",
                    linewidth=0.3,
                    zorder=4,
                )
            )
        ts_list = list(sess["ts"])
        trail_rows = day_ev[day_ev["event"].astype(str).isin(["trail_modify", "approach", "bounce", "aggressive_bounce", "hit_bar"])]
        if not trail_rows.empty and "trail" in trail_rows.columns:
            xs, ys = [], []
            for _, r in trail_rows.iterrows():
                ts = pd.Timestamp(r["ts"])
                if ts.tzinfo is None:
                    ts = ts.tz_localize(NY)
                else:
                    ts = ts.tz_convert(NY)
                idx = min(range(len(ts_list)), key=lambda i: abs(pd.Timestamp(ts_list[i]) - ts))
                px = r.get("trail") if pd.notna(r.get("trail")) else r.get("stop_price")
                if px is None or (isinstance(px, float) and not np.isfinite(px)):
                    continue
                xs.append(idx)
                ys.append(float(px))
            if xs:
                ax.plot(xs, ys, color="#ff6f00", lw=1.4, label="ST trail stop", zorder=6)
        for _, r in day_ev[day_ev["event"] == "aggressive_bounce"].iterrows():
            ts = pd.Timestamp(r["ts"])
            if ts.tzinfo is None:
                ts = ts.tz_localize(NY)
            idx = min(range(len(ts_list)), key=lambda i: abs(pd.Timestamp(ts_list[i]) - ts))
            ax.scatter([idx], [float(r["close"])], c="#7b1fa2", s=36, zorder=7, label="aggressive bounce")
        day_tr = units[units["session_date"].astype(str) == day] if not units.empty else pd.DataFrame()
        title_extra = ""
        if not day_tr.empty:
            tr = day_tr.iloc[0]
            title_extra = " %s net=$%.0f" % (tr["side"], float(tr["net_usd"]))
        ax.set_title("%s %s ST-trail bounce%s" % (ACTIVE_INSTRUMENT, day, title_extra))
        ax.grid(True, alpha=0.25)
        handles, labels = ax.get_legend_handles_labels()
        uniq = dict(zip(labels, handles))
        if uniq:
            ax.legend(uniq.values(), uniq.keys(), loc="upper left", fontsize=8)
        fig.tight_layout()
        fig.savefig(out_dir / ("%s.png" % day), dpi=110)
        plt.close(fig)
        n_written += 1
    (out_dir / "INDEX.md").write_text(
        "# ST-trail bounce charts\n\n5m RTH, orange = trail stop, purple = aggressive bounce close.\n\n%d charts.\n"
        % n_written,
        encoding="utf-8",
    )
    return n_written


def write_summary(hub: Path, results: List[dict], charts: int) -> Path:
    lines = [
        "# %s first-hour follow 3R strong + sweep_with_side (broker-like)" % ACTIVE_INSTRUMENT,
        "",
        "Engine + PaperBroker + StrategyPlugin `first_hour_follow`.",
        "Gate: **fh_body=strong** AND **sweep_with_side** (follow a PDH/PWH/London-high sweep or a PDL/PWL/London-low sweep).",
        "Entry: `market_close` on last FH bar (10:25); initial SL = FH open; TP = 3× body; flatten 15:59.",
        "ST trail book: hour-complete ATR SuperTrend 14×3 ratchets the stop when trend is aligned; 3R TP + EOD retained.",
        "Realism: slip 1 tick, spread model, fee $1.50/unit, %s $%.0f/pt." % (ACTIVE_INSTRUMENT, ACTIVE_POINT_VALUE),
        "",
        "| Book | Trades | WR | Net | Stress DD | N/S |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        lines.append(
            "| {label} | {trades} | {wr:.1f}% | ${net:,.0f} | ${stress:,.0f} | {ns:.2f} |".format(
                label=r["label"],
                trades=r["trades"],
                wr=100.0 * float(r["win_rate"]),
                net=float(r["net_usd"]),
                stress=float(r["intrabar_stress_dd_usd"]),
                ns=float(r["net_over_stress"]),
            )
        )
    base = next((r for r in results if r["slug"] == "follow_3r_strong_sweep"), None)
    trail = next((r for r in results if "st_trail" in r["slug"]), None)
    improved = False
    if base and trail:
        improved = (float(trail["net_over_stress"]) > float(base["net_over_stress"])) or (
            float(trail["net_usd"]) > float(base["net_usd"])
        )
        lines += [
            "",
            "## Trail vs fixed stop",
            "",
            "- Improved (net or N/S): **%s**" % ("yes" if improved else "no"),
            "- ΔN/S = %+.2f, Δnet = $%+.0f, ΔWR = %+.1f pp"
            % (
                float(trail["net_over_stress"]) - float(base["net_over_stress"]),
                float(trail["net_usd"]) - float(base["net_usd"]),
                100.0 * (float(trail["win_rate"]) - float(base["win_rate"])),
            ),
        ]
    bounce = (trail or {}).get("bounce") or {}
    if bounce:
        lines += [
            "",
            "## How price meets the ST trail",
            "",
            "- Trail modifies: %d" % int(bounce.get("n_trail_modify") or 0),
            "- Approach bars (within 8 pts): %d across %d trades"
            % (int(bounce.get("n_approach_bars") or 0), int(bounce.get("trades_with_approach") or 0)),
            "- Bounce bars (close away ≥12 pts without hitting): %d; trades with a bounce: %d (rate given approach **%.0f%%**)"
            % (
                int(bounce.get("n_bounce_bars") or 0),
                int(bounce.get("trades_with_bounce") or 0),
                100.0 * float(bounce.get("bounce_rate_given_approach") or 0.0),
            ),
            "- Aggressive bounces (close away ≥25 pts): %d bars / %d trades (**%.0f%%** of trail trades)"
            % (
                int(bounce.get("n_aggressive_bars") or 0),
                int(bounce.get("trades_with_aggressive") or 0),
                100.0 * float(bounce.get("aggressive_rate_of_trades") or 0.0),
            ),
            "- Median bounce size: **%.1f pts**" % float(bounce.get("median_bounce_pts") or 0.0),
            "- Trail level significant for a future bounce play: **%s**"
            % ("yes" if bounce.get("significant") else "no"),
        ]
        if bounce.get("significant"):
            lines.append("- Charts: `trail_bounce_charts/` (%d files). 5m RTH with trail overlay." % charts)
        else:
            lines.append("- No bounce charts — trail touches did not bounce hard/often enough to treat as a level.")
    lines += [
        "",
        "Stance: diagnostic / research. Do not promote from this sleeve alone.",
        "",
    ]
    path = hub / "SUMMARY.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    pd.DataFrame(results).to_csv(hub / "summary.csv", index=False)
    return path


def write_email(hub: Path, results: List[dict], charts: int) -> Path:
    lines = [
        "%s first-hour follow 3R strong + sweep_with_side broker-like complete" % ACTIVE_INSTRUMENT,
        "Hub: %s" % hub,
        "",
    ]
    for r in results:
        lines.append(
            "%s: trades=%d WR=%.1f%% net=$%+.0f stress=$%.0f N/S=%.2f"
            % (
                r["slug"],
                r["trades"],
                100.0 * float(r["win_rate"]),
                float(r["net_usd"]),
                float(r["intrabar_stress_dd_usd"]),
                float(r["net_over_stress"]),
            )
        )
    trail = next((r for r in results if "st_trail" in r["slug"]), None)
    bounce = (trail or {}).get("bounce") or {}
    if bounce:
        lines.append(
            "Trail bounce: approach_trades=%d bounce_rate=%.0f%% agr_rate=%.0f%% median=%.1fpts significant=%s charts=%d"
            % (
                int(bounce.get("trades_with_approach") or 0),
                100.0 * float(bounce.get("bounce_rate_given_approach") or 0.0),
                100.0 * float(bounce.get("aggressive_rate_of_trades") or 0.0),
                float(bounce.get("median_bounce_pts") or 0.0),
                bounce.get("significant"),
                charts,
            )
        )
    lines.append("")
    path = hub / "EMAIL.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--instrument", type=str, default="NQ", choices=list(INSTRUMENT_SPECS.keys()))
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(argv)

    instrument = str(args.instrument).upper()
    if instrument not in INSTRUMENT_SPECS:
        raise ValueError("unknown instrument %s" % instrument)
    spec = INSTRUMENT_SPECS[instrument]

    global ACTIVE_INSTRUMENT, ACTIVE_STATE_PREFIX, ACTIVE_TICK, ACTIVE_POINT_VALUE
    global ACTIVE_FEE_PER_UNIT, ACTIVE_DEFAULT_OUT, ACTIVE_SOURCE_PREFIX, ACTIVE_PO_SYMBOL

    ACTIVE_INSTRUMENT = instrument
    ACTIVE_STATE_PREFIX = spec["state_prefix"]
    ACTIVE_TICK = float(spec["tick"])
    ACTIVE_POINT_VALUE = float(spec["point_value"])
    ACTIVE_FEE_PER_UNIT = float(spec["fee_per_unit"])
    ACTIVE_DEFAULT_OUT = Path(spec["default_out"])
    ACTIVE_SOURCE_PREFIX = ACTIVE_STATE_PREFIX
    ACTIVE_PO_SYMBOL = "NQ"  # PO overlay lives in the NQ futures profile suite.

    hub = args.out or ACTIVE_DEFAULT_OUT
    hub.mkdir(parents=True, exist_ok=True)
    if args.force and (hub / "PROGRESS.log").exists():
        (hub / "PROGRESS.log").unlink()

    try:
        _progress(hub, "load RTH 5m + full-session 5m/1h ...")
        if ACTIVE_INSTRUMENT == "NQ":
            df5 = load_rth_5m(progress=True)
            df5_full = ensure_tf_bars("NQ", "5m")
            h1 = ensure_tf_bars("NQ", "1h")
        else:
            df5_full = ensure_tf_bars("NAS100", "5m")
            if df5_full is None or df5_full.empty:
                raise RuntimeError("missing NAS100 5m bars for trail+gate")
            st = df5_full["ts"].dt.time
            df5 = df5_full[(st >= RTH_OPEN) & (st < RTH_CLOSE)].copy().reset_index(drop=True)
            df5["session_date"] = df5["ts"].dt.strftime("%Y-%m-%d")

            h1 = ensure_tf_bars("NAS100", "1h")
            if h1 is None or h1.empty:
                # Fallback: derive 1h bars from the 5m tape (still full-session).
                g = df5_full.set_index("ts").sort_index()
                h1 = (
                    g.resample("1h", label="left", closed="left")
                    .agg(
                        open=("open", "first"),
                        high=("high", "max"),
                        low=("low", "min"),
                        close=("close", "last"),
                        volume=("volume", "sum"),
                    )
                    .dropna(subset=["open", "high", "low", "close"])
                    .reset_index()
                )

        if args.smoke:
            cut = pd.Timestamp(df5["ts"].max()).tz_convert(NY) - pd.Timedelta(days=400)
            df5 = df5[df5["ts"] >= cut].reset_index(drop=True)
            df5["session_date"] = df5["ts"].dt.strftime("%Y-%m-%d")
            if df5_full is not None:
                df5_full = df5_full[df5_full["ts"] >= cut].reset_index(drop=True)
            if h1 is not None:
                h1 = h1[h1["ts"] >= cut].reset_index(drop=True)
            _progress(hub, "SMOKE bars=%d from %s" % (len(df5), cut.date()))
        levels = build_session_levels(df5_full if df5_full is not None and not df5_full.empty else df5)
        levels_path = hub / "session_levels.csv"
        levels.to_csv(levels_path, index=False)
        _progress(hub, "session_levels n=%d" % len(levels))

        results = []
        for slug, label, cfg in BOOKS:
            results.append(
                run_book(
                    hub=hub,
                    slug=slug,
                    label=label,
                    cfg=cfg,
                    df5=df5,
                    h1=h1,
                    levels_path=levels_path,
                    force=args.force,
                )
            )

        base = next((r for r in results if r["slug"] == "follow_3r_strong_sweep"), None)
        trail = next((r for r in results if "st_trail" in r["slug"]), None)
        improved = False
        if base and trail:
            improved = (float(trail["net_over_stress"]) > float(base["net_over_stress"])) or (
                float(trail["net_usd"]) > float(base["net_usd"])
            )
        charts = 0
        hp_ran = False
        if trail and improved:
            maybe_hp_mill(hub, trail["slug"], df5)
            hp_ran = True
        if trail:
            charts = plot_bounce_charts(hub, trail["slug"], df5, trail.get("bounce") or {})
            _progress(hub, "bounce charts=%d significant=%s" % (charts, (trail.get("bounce") or {}).get("significant")))

        write_summary(hub, results, charts)
        email_path = write_email(hub, results, charts)
        if hp_ran:
            extra = email_path.read_text(encoding="utf-8")
            extra += "\nHP mill: %s/hp_mill (ran because trail improved the gated book)\n" % hub
            email_path.write_text(extra, encoding="utf-8")
        write_run_manifest(
            hub,
            data_inputs=spec["data_inputs"],
            strategy_config={
                "strategy_type": "first_hour_follow",
                "books": [b[0] for b in BOOKS],
                "require_fh_body": "strong",
                "require_sweep_side": "sweep_with_side",
            },
            broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": ACTIVE_FEE_PER_UNIT, "tick": ACTIVE_TICK},
            extra={"results": results, "hp_ran": hp_ran, "charts": charts},
        )
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {"ok": True, "results": results, "hp_ran": hp_ran, "charts": charts},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if args.email:
            send_email(
                subject="potions: %s FH strong+sweep (+ST trail) broker-like complete" % ACTIVE_INSTRUMENT,
                body=email_path.read_text(encoding="utf-8"),
            )
        return 0
    except Exception:
        tb = traceback.format_exc()
        _progress(hub, "FAIL\n" + tb)
        fail = hub / "EMAIL_FAIL.txt"
        fail.write_text(
            "%s FH strong+sweep broker FAILED\nHub: %s\n\n%s\n" % (ACTIVE_INSTRUMENT, hub, tb),
            encoding="utf-8",
        )
        try:
            send_email(subject="potions: %s FH strong+sweep broker FAILED" % ACTIVE_INSTRUMENT, body=fail.read_text())
        except Exception:
            pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
