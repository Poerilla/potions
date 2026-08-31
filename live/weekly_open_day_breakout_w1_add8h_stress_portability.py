"""Week-1 OD half+EOW +1/8h — frozen v1 stress + cross-market portability.

Stages (NAS100 first, then frozen ports):
  1. correctness / causality / order ledger
  2. add-path attribution
  3. execution stress matrix (locked cases, not optimization)
  4. parameter-neighborhood robustness
  5. statistical / temporal checks
  6. cross-market: NQ → MNQ → YM → MYM (unchanged rules)

Hub: live/state/weekly_open_day_breakout_w1_add8h_v1_stress_port
Contract: RESEARCH_CONTRACT.yaml (max_adds=9 locked)
DSR: TRL-2026-00168
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import traceback
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import pytz

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .fx_data import load_fx_1m_by_ny_date
from .models import StrategyInstance, as_row
from .notifications import NullNotificationSink
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS, MarketSpec, _spread, ensure_4h_csv
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .run_ledger import begin_run, complete_run, fail_run
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import load_1m_by_ny_date_any
from .v2b_strategy_replay import fast_intraday_audit, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider
from .weekly_open_day_breakout_1m_broker import _progress, _replay_4h_with_1m, _signal_bars
from .weekly_open_day_breakout_variants_broker import VARIANTS
from .ym_hourly_st_pmc_retest_replay import concat_all_1m

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "weekly_open_day_breakout_w1_add8h_v1_stress_port"
NY = pytz.timezone("America/New_York")
DSR = "TRL-2026-00168"
FROZEN_MAX_ADDS = 9
ENTRY_QTY = 3
PRIMARY_VARIANT = "od_half_eow_bull_hivol_w1_add8h"
BASE_VARIANT = "od_half_eow_bull_hivol_w1"

# Futures: front-month 4h + DBN/CSV 1m (not fx/*_1m.csv).
FUTURES_SOURCES: Dict[str, Dict[str, Any]] = {
    "NQ": {
        "tick": 0.25,
        "point_value": 20.0,
        "fee": 1.50,
        "csv": REPO / "nq" / "data" / "nq_front_month_4h_from_1m.csv",
        "dbn": REPO / "nq" / "raw" / "glbx-mdp3-20100606-20260616.ohlcv-1m.dbn.zst",
    },
    "MNQ": {
        "tick": 0.25,
        "point_value": 2.0,
        "fee": 1.50,
        "csv": REPO / "mnq" / "data" / "mnq_front_month_4h_from_1m.csv",
        "dbn": REPO / "mnq" / "raw" / "glbx-mdp3-20210304-20260303.ohlcv-1m.csv",
    },
    "YM": {
        "tick": 1.0,
        "point_value": 5.0,
        "fee": 1.50,
        "csv": REPO / "ym" / "data" / "ym_front_month_4h_from_1m.csv",
        "dbn": REPO / "ym" / "raw" / "glbx-mdp3-20100606-20260506.ohlcv-1m.dbn.zst",
    },
    "MYM": {
        "tick": 1.0,
        "point_value": 0.5,
        "fee": 1.50,
        "csv": REPO / "mym" / "data" / "mym_front_month_4h_from_1m.csv",
        "dbn": REPO / "mym" / "raw" / "glbx-mdp3-20100606-20260308.ohlcv-1m (mym).dbn.zst",
    },
}


def _frozen_cfg(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = dict(VARIANTS[PRIMARY_VARIANT])
    cfg["max_adds"] = FROZEN_MAX_ADDS
    cfg["label"] = "frozen v1: week-1 half+EOW bull×hivol; +1/8h; max_adds=%d" % FROZEN_MAX_ADDS
    if overrides:
        cfg.update(overrides)
    return cfg


def _base_cfg(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = dict(VARIANTS[BASE_VARIANT])
    cfg["label"] = "frozen base: week-1 half+EOW bull×hivol; no adds"
    if overrides:
        cfg.update(overrides)
    return cfg


def _market_spec(symbol: str) -> MarketSpec:
    key = symbol.upper()
    if key in FUTURES_SOURCES:
        src = FUTURES_SOURCES[key]
        return MarketSpec(
            symbol=key,
            tick=float(src["tick"]),
            point_value=float(src["point_value"]),
            fee_per_unit=float(src["fee"]),
            csv=Path(src["csv"]),
            family="futures",
            source_1h=None,
        )
    if key not in MARKETS:
        raise KeyError("Unknown market %s" % key)
    m = MARKETS[key]
    if key in {"NQ", "MNQ", "YM"} and not m.csv.exists():
        # Prefer front-month 4h when cache missing.
        if key in FUTURES_SOURCES:
            return _market_spec(key)  # recursion via FUTURES_SOURCES — unreachable
    return m


def _load_1m(market: MarketSpec) -> pd.DataFrame:
    sym = market.symbol.upper()
    if sym in FUTURES_SOURCES:
        dbn = Path(FUTURES_SOURCES[sym]["dbn"])
        if not dbn.exists():
            raise FileNotFoundError("Missing 1m source for %s: %s" % (sym, dbn))
        gby = load_1m_by_ny_date_any(dbn.resolve(), sym.lower())
        return concat_all_1m(gby)
    path = REPO / "fx" / ("%s_1m.csv" % sym.lower())
    if not path.exists():
        raise FileNotFoundError("Missing 1m tape for %s: %s" % (sym, path))
    gby = load_fx_1m_by_ny_date(path, sym)
    return concat_all_1m(gby)


def _1m_source_path(market: MarketSpec) -> Path:
    sym = market.symbol.upper()
    if sym in FUTURES_SOURCES:
        return Path(FUTURES_SOURCES[sym]["dbn"])
    return REPO / "fx" / ("%s_1m.csv" % sym.lower())


def _load_4h_any(path: Path, symbol: str) -> pd.DataFrame:
    """Load 4h OHLC: ts_event CFD caches *or* front-month `time`/`date` CSVs (NQM0…)."""
    print("Loading %s ..." % path, flush=True)
    df = pd.read_csv(path)
    if "ts_event" not in df.columns:
        if "time" in df.columns:
            df = df.rename(columns={"time": "ts_event"})
        elif "ts" in df.columns:
            df = df.rename(columns={"ts": "ts_event"})
        else:
            raise KeyError("4h csv needs ts_event/time/ts: %s" % path)
    if "symbol" in df.columns:
        syms = df["symbol"].astype(str).str.upper()
        root = symbol.upper()
        exact = syms == root
        if bool(exact.any()):
            df = df.loc[exact].copy()
        else:
            # Continuous front-month rows use contract codes (NQM0, MNQH1, …).
            df = df.loc[syms.str.startswith(root) & ~syms.str.contains("-", na=False)].copy()
    if df.empty:
        raise RuntimeError("No 4h rows for %s in %s" % (symbol, path))
    ts = pd.to_datetime(df["ts_event"], utc=True, errors="coerce")
    if ts.isna().any():
        ts = pd.to_datetime(df["ts_event"], errors="coerce")
        if getattr(ts.dt, "tz", None) is None:
            ts = ts.dt.tz_localize(NY, ambiguous="infer", nonexistent="shift_forward")
        else:
            ts = ts.dt.tz_convert(NY)
    else:
        ts = ts.dt.tz_convert(NY)
    df = df.assign(ts_event=ts).dropna(subset=["ts_event"])
    df = df.set_index("ts_event").sort_index()
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    out = df[keep]
    print("  4h bars: %s" % f"{len(out):,}", flush=True)
    return out


@dataclass
class EngStress:
    name: str
    slippage_ticks: float = 1.0
    fee_mult: float = 1.0
    cfg_overrides: Optional[Dict[str, Any]] = None
    notes: str = ""


def _window(years: float, market: MarketSpec) -> Tuple[date, date]:
    csv_path = market.csv
    if not csv_path.exists() and market.symbol in MARKETS:
        csv_path = ensure_4h_csv(MARKETS[market.symbol])
    df = _load_4h_any(csv_path, market.symbol)
    end = df.index.max().tz_convert(NY).date() if len(df) else date.today()
    start = end - timedelta(days=int(round(365.25 * years)))
    start = start - timedelta(days=start.weekday())
    return start, end


def run_replay(
    *,
    output_root: Path,
    market: MarketSpec,
    run_id: str,
    cfg: Dict[str, Any],
    force: bool,
    start: date,
    end: date,
    causality_mode: str = "strict",
    slippage_ticks: float = 1.0,
    fee_mult: float = 1.0,
) -> dict:
    strategy_id = "%s_%s" % (market.symbol.lower(), run_id)
    state_root = output_root / "states" / strategy_id
    metrics_path = state_root / "metrics.json"
    if (not force) and metrics_path.exists():
        _progress(output_root, "CACHE %s" % strategy_id)
        return json.loads(metrics_path.read_text(encoding="utf-8"))

    csv_path = market.csv
    if not csv_path.exists():
        if market.symbol in MARKETS:
            csv_path = ensure_4h_csv(MARKETS[market.symbol])
        else:
            raise FileNotFoundError("Missing 4h for %s: %s" % (market.symbol, csv_path))

    POINT_VALUES[market.symbol] = market.point_value
    DEFAULT_TICK_SIZE[market.symbol] = market.tick

    df = _load_4h_any(csv_path, market.symbol)
    warm = pd.Timestamp(start, tz=NY) - pd.Timedelta(days=60)
    df = df[df.index >= warm]
    df = df[df.index < pd.Timestamp(end, tz=NY) + pd.Timedelta(days=1)]

    _progress(output_root, "Loading %s 1m for %s ..." % (market.symbol, run_id))
    one_m = _load_1m(market)
    one_m = one_m[one_m.index >= pd.Timestamp(start, tz=NY)]
    one_m = one_m[one_m.index < pd.Timestamp(end, tz=NY) + pd.Timedelta(days=1)]
    if one_m.empty:
        raise RuntimeError("empty 1m tape for %s" % market.symbol)
    _progress(output_root, "  %s 4h=%d 1m=%d" % (market.symbol, len(df), len(one_m)))

    # Monkeypatch source path used inside _replay_4h_with_1m progress only via market.csv family.
    # _replay_4h_with_1m calls _1m_csv(market) for Bar.source — invent a shim MarketSpec with csv only.
    signal_bars, audit_bars = _signal_bars(df, market)
    start_utc = pd.Timestamp(start, tz=NY).tz_convert("UTC")
    audit_bars = [b for b in audit_bars if pd.Timestamp(b.ts) >= start_utc]

    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {k: v for k, v in cfg.items() if k != "label"}
    payload["tick_size"] = market.tick
    entry_qty = int(payload.get("entry_qty") or ENTRY_QTY)
    max_adds = int(payload.get("max_adds") or 0)
    max_contracts = max(entry_qty + max(max_adds, 0) * int(payload.get("add_qty") or 1) + 2, 16)
    if float(payload.get("add_every_hours") or 0) > 0 and max_adds <= 0:
        max_contracts = max(max_contracts, 48)
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="weekly_open_day_breakout",
                    version="v6",
                    instrument=market.symbol,
                    broker_instrument=market.symbol,
                    account_mode="paper",
                    enabled=True,
                    timeframes="4h",
                    max_contracts=max_contracts,
                    max_open_orders=64,
                    config_json=json.dumps(payload, sort_keys=True),
                )
            )
        ],
    )
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        tick_size={market.symbol: market.tick},
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
        causality_mode=causality_mode,
        **hardened_replay_engine_kwargs(
            slippage_ticks=float(slippage_ticks),
            spread_model=_spread(market.tick, market.family),
        ),
    )
    _progress(output_root, "START %s %s slip=%.1f" % (market.symbol, run_id, slippage_ticks))
    # _replay_4h_with_1m uses _1m_csv(market) for Bar.source string only — patch via temp attr.
    _replay_4h_with_1m(
        engine,
        signal_bars=signal_bars,
        one_m=one_m,
        market=market,
        label=strategy_id,
        output_root=output_root,
    )
    store.flush_tables()

    units = units_from_v2b_fills(state_root / "fills.csv", strategy_id)
    fee = float(market.fee_per_unit) * float(fee_mult)
    audit = fast_intraday_audit(
        strategy_id=strategy_id,
        state_root=state_root,
        bars=audit_bars,
        units=units,
        instrument=market.symbol,
        fee_per_unit=fee,
    )
    net = float(audit.get("net_usd") or 0.0)
    stress = float(audit.get("intrabar_stress_dd_usd") or 0.0)
    ns = (net / abs(stress)) if stress else 0.0
    trades = int(audit.get("trades") or len({u.trade_id for u in units}))
    fills = pd.read_csv(state_root / "fills.csv") if (state_root / "fills.csv").exists() else pd.DataFrame()
    adds = int(fills["reason"].astype(str).isin(["add", "time_add"]).sum()) if len(fills) else 0
    metrics = {
        "strategy_id": strategy_id,
        "market": market.symbol,
        "run_id": run_id,
        "label": cfg.get("label") or run_id,
        "feed_tf": "1m",
        "signal_tf": "4h",
        "bars_4h": len(signal_bars),
        "bars_1m": int(len(one_m)),
        "units": int(audit.get("units") or len(units)),
        "trades": trades,
        "adds_filled": adds,
        "net_usd": net,
        "closed_dd_usd": float(audit.get("closed_dd_usd") or 0.0),
        "intrabar_stress_dd_usd": stress,
        "win_rate": float(audit.get("win_rate") or 0.0) / 100.0,
        "profit_factor": float(audit.get("profit_factor") or 0.0),
        "net_over_stress": ns,
        "max_open_units": int(audit.get("max_open_units") or 0),
        "slippage_ticks": float(slippage_ticks),
        "fee_mult": float(fee_mult),
        "fee_per_unit": fee,
        "point_value": float(market.point_value),
        "tick": float(market.tick),
        "causality_mode": causality_mode,
        "dsr_trial": DSR,
        "cfg": {k: v for k, v in cfg.items() if k != "label"},
    }
    # Causality counts
    viol = state_root / "causality_violations.csv"
    feat = state_root / "feature_snapshots.csv"
    metrics["causality_violations"] = max(0, sum(1 for _ in open(viol)) - 1) if viol.exists() else -1
    metrics["feature_snapshots"] = max(0, sum(1 for _ in open(feat)) - 1) if feat.exists() else -1
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    _progress(
        output_root,
        "DONE %s/%s net=%+.0f N/S=%.2f trades=%d adds=%d units=%d"
        % (market.symbol, run_id, net, ns, trades, adds, metrics["units"]),
    )
    return metrics


# ---------------------------------------------------------------------------
# Stage 1+2: correctness + attribution from a primary state root
# ---------------------------------------------------------------------------


def _unit_pnl(u, pv: float, fee: float) -> float:
    sign = 1.0 if u.direction == "Long" else -1.0
    return sign * (float(u.exit_price) - float(u.entry_price)) * pv - 2.0 * fee


def stage_correctness_and_attribution(
    output_root: Path,
    state_root: Path,
    strategy_id: str,
    market: MarketSpec,
    baseline_metrics: Optional[dict] = None,
) -> dict:
    out = output_root / "stage1_2"
    out.mkdir(parents=True, exist_ok=True)
    fills = pd.read_csv(state_root / "fills.csv")
    orders = pd.read_csv(state_root / "orders.csv") if (state_root / "orders.csv").exists() else pd.DataFrame()
    intents = (
        pd.read_csv(state_root / "order_intents.csv")
        if (state_root / "order_intents.csv").exists()
        else pd.DataFrame()
    )
    units = units_from_v2b_fills(state_root / "fills.csv", strategy_id)
    fee = float(market.fee_per_unit)
    pv = float(market.point_value)

    fills["ts"] = pd.to_datetime(fills["ts"], utc=True)
    fills["ts_ny"] = fills["ts"].dt.tz_convert(NY)

    issues: List[str] = []
    # Unique timestamps / no duplicate add keys
    add_fills = fills[fills["reason"].astype(str).isin(["add", "time_add"])].copy()
    dup = add_fills.duplicated(subset=["trade_id", "ts", "quantity"], keep=False)
    if dup.any():
        issues.append("duplicate_add_fills=%d" % int(dup.sum()))

    # No add after Friday 13:00 NY completion on same week (soft check: add on Fri after 13:00)
    fri_adds = add_fills[(add_fills["ts_ny"].dt.weekday == 4) & (add_fills["ts_ny"].dt.hour >= 13)]
    if len(fri_adds):
        issues.append("adds_at_or_after_fri_13=%d" % len(fri_adds))

    # Causality files
    viol_path = state_root / "causality_violations.csv"
    n_viol = max(0, sum(1 for _ in open(viol_path)) - 1) if viol_path.exists() else -1
    if n_viol != 0:
        issues.append("causality_violations=%d" % n_viol)

    # Order ledger for adds
    ledger_rows = []
    for _, r in add_fills.iterrows():
        tid = r["trade_id"]
        ts = r["ts"]
        related = orders[orders["trade_id"] == tid] if len(orders) and "trade_id" in orders.columns else pd.DataFrame()
        if len(intents) and "trade_id" in intents.columns:
            mask = intents["trade_id"] == tid
            if "reason" in intents.columns:
                mask = mask & intents["reason"].astype(str).isin(["time_add", "add"])
            intent_match = intents[mask]
        else:
            intent_match = pd.DataFrame()
        ledger_rows.append(
            {
                "trade_id": tid,
                "fill_ts": ts.isoformat(),
                "fill_ts_ny": r["ts_ny"].isoformat(),
                "fill_price": float(r["price"]),
                "qty": int(r["quantity"]),
                "side": r["side"],
                "n_orders_same_trade": int(len(related)),
                "n_add_intents_same_trade": int(len(intent_match)),
            }
        )
    pd.DataFrame(ledger_rows).to_csv(out / "add_order_ledger.csv", index=False)

    # Campaign reconstruction
    by_trade: Dict[str, List] = defaultdict(list)
    for u in units:
        by_trade[u.trade_id].append(u)

    camp_rows = []
    init_nets: List[float] = []
    add_nets: List[float] = []
    add_num_stats: Dict[int, List[float]] = defaultdict(list)
    year_stats: Dict[int, Dict[str, float]] = defaultdict(lambda: {"n": 0, "net": 0.0, "add_net": 0.0})
    bucket_nets = {"0-8h": [], "8-16h": [], "16-24h": [], "24-32h": [], "32h+": []}
    dir_nets = {"Long": [], "Short": []}

    for tid, us in by_trade.items():
        us = sorted(us, key=lambda x: x.entry_ts)
        nets = [_unit_pnl(u, pv, fee) for u in us]
        camp_net = float(sum(nets))
        init = nets[:ENTRY_QTY]
        adds = nets[ENTRY_QTY:]
        init_nets.extend(init)
        add_nets.extend(adds)
        for i, n in enumerate(adds, start=1):
            add_num_stats[i].append(n)
        entry_ts = pd.Timestamp(us[0].entry_ts)
        if entry_ts.tzinfo is None:
            entry_ts = entry_ts.tz_localize("UTC")
        entry_ny = entry_ts.tz_convert(NY)
        year = int(entry_ny.year)
        year_stats[year]["n"] += 1
        year_stats[year]["net"] += camp_net
        year_stats[year]["add_net"] += float(sum(adds))
        # time buckets by unit entry offset from campaign start
        for u, n in zip(us, nets):
            ets = pd.Timestamp(u.entry_ts)
            if ets.tzinfo is None:
                ets = ets.tz_localize("UTC")
            hrs = (ets - entry_ts).total_seconds() / 3600.0
            if hrs < 8:
                bucket_nets["0-8h"].append(n)
            elif hrs < 16:
                bucket_nets["8-16h"].append(n)
            elif hrs < 24:
                bucket_nets["16-24h"].append(n)
            elif hrs < 32:
                bucket_nets["24-32h"].append(n)
            else:
                bucket_nets["32h+"].append(n)
        direction = us[0].direction
        dir_nets.setdefault(direction, []).append(camp_net)
        # max concurrent approx = number of open units at peak (len of lots before any exit overlapping)
        # simple: max units in campaign = len(us) if all open together else track
        max_units = 0
        events = []
        for u in us:
            events.append((pd.Timestamp(u.entry_ts), 1))
            events.append((pd.Timestamp(u.exit_ts), -1))
        events.sort(key=lambda x: (x[0], -x[1]))
        cur = 0
        for _, d in events:
            cur += d
            max_units = max(max_units, cur)
        camp_rows.append(
            {
                "trade_id": tid,
                "direction": direction,
                "entry_ts": us[0].entry_ts,
                "exit_ts": max(u.exit_ts for u in us),
                "n_units": len(us),
                "n_adds": max(0, len(us) - ENTRY_QTY),
                "init_net": float(sum(init)),
                "add_net": float(sum(adds)),
                "camp_net": camp_net,
                "max_concurrent_units": max_units,
                "year": year,
                "wom": ((int(entry_ny.day) - 1) // 7) + 1,
            }
        )

    camps = pd.DataFrame(camp_rows).sort_values("camp_net", ascending=False)
    camps.to_csv(out / "campaigns.csv", index=False)

    total_net = float(camps["camp_net"].sum()) if len(camps) else 0.0
    conc = {}
    for k in (1, 3, 5, 10):
        top = float(camps["camp_net"].head(k).sum()) if len(camps) else 0.0
        conc["top_%d_pct_of_net" % k] = (100.0 * top / total_net) if total_net else 0.0

    # Rescue/hurt: initial legs net vs campaign net
    rescued = int(((camps["init_net"] <= 0) & (camps["camp_net"] > 0)).sum()) if len(camps) else 0
    hurt = int(((camps["init_net"] > 0) & (camps["camp_net"] <= 0)).sum()) if len(camps) else 0

    def _ns(nets: List[float]) -> Tuple[float, float, float]:
        if not nets:
            return 0.0, 0.0, 0.0
        s = float(sum(nets))
        # path stress proxy: running drawdown of cumulative
        eq = np.cumsum(nets)
        peak = np.maximum.accumulate(eq)
        dd = float((eq - peak).min()) if len(eq) else 0.0
        ns = (s / abs(dd)) if dd < 0 else (s if s else 0.0)
        return s, dd, ns

    init_sum, _, _ = _ns(init_nets)
    add_sum, _, _ = _ns(add_nets)

    add_num_rows = []
    for k in sorted(add_num_stats):
        nets = add_num_stats[k]
        add_num_rows.append(
            {
                "add_number": k,
                "fills": len(nets),
                "net": float(sum(nets)),
                "avg": float(np.mean(nets)),
                "win_rate": float(np.mean([1 if n > 0 else 0 for n in nets])),
            }
        )
    pd.DataFrame(add_num_rows).to_csv(out / "add_number_attribution.csv", index=False)

    year_rows = [
        {
            "year": y,
            "campaigns": int(v["n"]),
            "net": float(v["net"]),
            "add_net": float(v["add_net"]),
            "add_share": (float(v["add_net"]) / float(v["net"])) if v["net"] else 0.0,
        }
        for y, v in sorted(year_stats.items())
    ]
    pd.DataFrame(year_rows).to_csv(out / "yearly_attribution.csv", index=False)

    bucket_rows = [
        {"bucket": b, "fills": len(ns), "net": float(sum(ns)), "avg": float(np.mean(ns)) if ns else 0.0}
        for b, ns in bucket_nets.items()
    ]
    pd.DataFrame(bucket_rows).to_csv(out / "time_in_campaign_attribution.csv", index=False)

    # Friday close timing
    closes = fills[fills["reason"].astype(str) == "close"].copy()
    fri = {
        "n_close": int(len(closes)),
        "dow": closes["ts_ny"].dt.day_name().value_counts().to_dict() if len(closes) else {},
        "hour_hist": closes["ts_ny"].dt.hour.value_counts().sort_index().to_dict() if len(closes) else {},
    }

    summary = {
        "strategy_id": strategy_id,
        "campaigns": int(len(camps)),
        "units": int(len(units)),
        "adds_filled": int(len(add_fills)),
        "unit_ledger_net": float(sum(init_nets) + sum(add_nets)),
        "init_units": len(init_nets),
        "init_net": init_sum,
        "add_units": len(add_nets),
        "add_net": add_sum,
        "add_share_of_net": (add_sum / (init_sum + add_sum)) if (init_sum + add_sum) else 0.0,
        "concentration": conc,
        "rescued_by_adds": rescued,
        "hurt_by_adds": hurt,
        "max_adds_observed": int(camps["n_adds"].max()) if len(camps) else 0,
        "max_concurrent_units": int(camps["max_concurrent_units"].max()) if len(camps) else 0,
        "direction": {k: {"n": len(v), "net": float(sum(v))} for k, v in dir_nets.items()},
        "friday_closes": fri,
        "causality_violations": n_viol,
        "feature_snapshots": max(0, sum(1 for _ in open(state_root / "feature_snapshots.csv")) - 1)
        if (state_root / "feature_snapshots.csv").exists()
        else -1,
        "issues": issues,
        "pass": len(issues) == 0 and n_viol == 0,
        "baseline_ref": baseline_metrics,
    }
    (out / "CORRECTNESS_ATTRIBUTION.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")

    lines = [
        "# Stage 1–2: Correctness + add-path attribution",
        "",
        "Pass: **%s** · issues=%s · causality_violations=%s · feature_snapshots=%s"
        % (summary["pass"], issues or "[]", n_viol, summary["feature_snapshots"]),
        "",
        "| View | Value |",
        "|---|---:|",
        "| Campaigns | %d |" % summary["campaigns"],
        "| Units | %d |" % summary["units"],
        "| Adds | %d |" % summary["adds_filled"],
        "| Unit-ledger net | $%+.0f |" % summary["unit_ledger_net"],
        "| Initial legs net | $%+.0f (%d units) |" % (init_sum, len(init_nets)),
        "| Add legs net | $%+.0f (%d units) |" % (add_sum, len(add_nets)),
        "| Add share of net | %.1f%% |" % (100.0 * summary["add_share_of_net"]),
        "| Max adds observed | %d |" % summary["max_adds_observed"],
        "| Max concurrent units | %d |" % summary["max_concurrent_units"],
        "| Rescued by adds | %d |" % rescued,
        "| Hurt by adds | %d |" % hurt,
        "",
        "## Concentration",
        "",
        "| Top K campaigns | %% of net |",
        "|---:|---:|",
    ]
    for k in (1, 3, 5, 10):
        lines.append("| %d | %.1f%% |" % (k, conc["top_%d_pct_of_net" % k]))
    fragile = conc["top_5_pct_of_net"] > 30.0
    lines.extend(
        [
            "",
            "Concentration fragile (>30%% top-5): **%s**" % fragile,
            "",
            "## Add number",
            "",
            "| Add # | Fills | Net | Avg | WR |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for r in add_num_rows:
        lines.append(
            "| %d | %d | $%+.0f | $%+.1f | %.1f%% |"
            % (r["add_number"], r["fills"], r["net"], r["avg"], 100.0 * r["win_rate"])
        )
    lines.extend(["", "## Yearly", "", "| Year | N | Net | Add net | Add share |", "|---:|---:|---:|---:|---:|"])
    for r in year_rows:
        lines.append(
            "| %d | %d | $%+.0f | $%+.0f | %.0f%% |"
            % (r["year"], r["campaigns"], r["net"], r["add_net"], 100.0 * r["add_share"])
        )
    (out / "ATTRIBUTION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


# ---------------------------------------------------------------------------
# Stage 5: statistical checks from campaigns.csv
# ---------------------------------------------------------------------------


def stage_stats(output_root: Path, camps_path: Path, primary_ns: float) -> dict:
    out = output_root / "stage5_stats"
    out.mkdir(parents=True, exist_ok=True)
    camps = pd.read_csv(camps_path)
    camps["entry_ts"] = pd.to_datetime(camps["entry_ts"], utc=True)
    camps = camps.sort_values("entry_ts")

    # Chronological blocks
    blocks = [
        ("2016-2019", 2016, 2019),
        ("2020-2022", 2020, 2022),
        ("2023-2026", 2023, 2026),
    ]
    block_rows = []
    for name, y0, y1 in blocks:
        sub = camps[(camps["year"] >= y0) & (camps["year"] <= y1)]
        nets = sub["camp_net"].tolist()
        s = float(sum(nets))
        eq = np.cumsum(nets) if nets else np.array([0.0])
        peak = np.maximum.accumulate(eq)
        dd = float((eq - peak).min()) if len(eq) else 0.0
        ns = (s / abs(dd)) if dd < 0 else 0.0
        block_rows.append({"block": name, "n": len(sub), "net": s, "path_dd": dd, "ns_path": ns})
    pd.DataFrame(block_rows).to_csv(out / "chrono_blocks.csv", index=False)

    # Rolling windows
    roll_rows = []
    for w in (12, 20):
        for i in range(len(camps)):
            if i + 1 < w:
                continue
            window = camps.iloc[i + 1 - w : i + 1]
            nets = window["camp_net"].tolist()
            s = float(sum(nets))
            eq = np.cumsum(nets)
            peak = np.maximum.accumulate(eq)
            dd = float((eq - peak).min())
            ns = (s / abs(dd)) if dd < 0 else 0.0
            wins = sum(1 for n in nets if n > 0)
            losses = sum(-n for n in nets if n < 0)
            gains = sum(n for n in nets if n > 0)
            pf = (gains / losses) if losses > 0 else (float("inf") if gains > 0 else 0.0)
            roll_rows.append({"window": w, "end_idx": i, "net": s, "ns_path": ns, "pf": pf, "wr": wins / w})
    pd.DataFrame(roll_rows).to_csv(out / "rolling_windows.csv", index=False)

    # Leave-one-campaign-out
    loco = []
    all_nets = camps["camp_net"].tolist()
    for i, row in camps.iterrows():
        nets = [n for j, n in enumerate(all_nets) if camps.index[j] != i]
        s = float(sum(nets))
        eq = np.cumsum(nets) if nets else np.array([0.0])
        peak = np.maximum.accumulate(eq)
        dd = float((eq - peak).min()) if len(eq) else 0.0
        ns = (s / abs(dd)) if dd < 0 else 0.0
        loco.append({"left_out": row["trade_id"], "net": s, "ns_path": ns, "delta_ns": ns - primary_ns})
    loco_df = pd.DataFrame(loco)
    loco_df.to_csv(out / "leave_one_campaign_out.csv", index=False)

    # Leave-one-year-out
    loyo = []
    for y in sorted(camps["year"].unique()):
        nets = camps.loc[camps["year"] != y, "camp_net"].tolist()
        s = float(sum(nets))
        eq = np.cumsum(nets) if nets else np.array([0.0])
        peak = np.maximum.accumulate(eq)
        dd = float((eq - peak).min()) if len(eq) else 0.0
        ns = (s / abs(dd)) if dd < 0 else 0.0
        loyo.append({"left_out_year": int(y), "n_remaining": len(nets), "net": s, "ns_path": ns})
    pd.DataFrame(loyo).to_csv(out / "leave_one_year_out.csv", index=False)

    # Block bootstrap by campaign (1000 resamples)
    rng = np.random.default_rng(42)
    arr = np.array(all_nets, dtype=float)
    boot_ns = []
    for _ in range(1000):
        sample = rng.choice(arr, size=len(arr), replace=True)
        s = float(sample.sum())
        eq = np.cumsum(sample)
        peak = np.maximum.accumulate(eq)
        dd = float((eq - peak).min())
        boot_ns.append((s / abs(dd)) if dd < 0 else 0.0)
    boot = {
        "n_boot": 1000,
        "ns_mean": float(np.mean(boot_ns)),
        "ns_p05": float(np.percentile(boot_ns, 5)),
        "ns_p50": float(np.percentile(boot_ns, 50)),
        "ns_p95": float(np.percentile(boot_ns, 95)),
        "frac_ns_below_1": float(np.mean([1 if x < 1 else 0 for x in boot_ns])),
        "frac_ns_below_base_1_82": float(np.mean([1 if x < 1.82 else 0 for x in boot_ns])),
    }
    (out / "block_bootstrap.json").write_text(json.dumps(boot, indent=2) + "\n", encoding="utf-8")

    # Selection-aware note (idea tree size)
    selection = {
        "variants_inspected_approx": [
            "week_gate",
            "bull_condition",
            "high_vol_condition",
            "od_half_geometry",
            "eow_exit",
            "add_cadence_8h",
            "holiday_filter",
            "3r_runner",
            "oco_1r",
            "candle_sl",
            "od_sl_20r",
        ],
        "n_variants_approx": 11,
        "note": (
            "Deflated / selection-aware analysis: with ~11 related variants inspected "
            "before this frozen v1, treat headline N/S as optimistic until DSR is computed "
            "on the full trial ledger (TRL-2026-00161..00168)."
        ),
        "primary_path_ns_ref": primary_ns,
        "loco_ns_min": float(loco_df["ns_path"].min()) if len(loco_df) else None,
        "loco_ns_max": float(loco_df["ns_path"].max()) if len(loco_df) else None,
    }
    (out / "selection_aware.json").write_text(json.dumps(selection, indent=2) + "\n", encoding="utf-8")

    summary = {
        "blocks": block_rows,
        "bootstrap": boot,
        "selection": selection,
        "rolling_n": len(roll_rows),
    }
    (out / "STATS_SUMMARY.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    return summary


# ---------------------------------------------------------------------------
# Stress + neighborhood case lists
# ---------------------------------------------------------------------------


def exec_stress_cases() -> List[EngStress]:
    return [
        EngStress("slip_1tick", 1.0, 1.0, notes="current / primary"),
        EngStress("slip_2tick", 2.0, 1.0, notes="one extra adverse tick"),
        EngStress("slip_3tick", 3.0, 1.0, notes="two extra adverse ticks"),
        EngStress("fee_2x", 1.0, 2.0, notes="2× all-in fee (re-audit via fee_mult)"),
        EngStress("fee_3x", 1.0, 3.0, notes="3× all-in fee"),
        EngStress("fri_12", 1.0, 1.0, {"friday_flatten_completion_ny": "12:00"}, "Friday 12:00 NY"),
        EngStress("fri_14", 1.0, 1.0, {"friday_flatten_completion_ny": "14:00"}, "Friday 14:00 NY"),
        EngStress("add_every_16h", 1.0, 1.0, {"add_every_hours": 16.0}, "every second 8h add only"),
        EngStress("max_adds_8", 1.0, 1.0, {"max_adds": 8}, "drop final add capacity"),
        EngStress("max_adds_4", 1.0, 1.0, {"max_adds": 4}, "first N-ish adds only"),
        EngStress("no_adds", 1.0, 1.0, {"add_every_hours": 0.0, "max_adds": 0, "add_qty": 0}, "add availability off"),
    ]


def neighborhood_cases() -> List[Tuple[str, Dict[str, Any]]]:
    return [
        ("neigh_w1_primary", {}),
        ("neigh_no_week_gate", {"allow_weeks_of_month": []}),
        ("neigh_add_6h", {"add_every_hours": 6.0}),
        ("neigh_add_8h", {"add_every_hours": 8.0}),
        ("neigh_add_10h", {"add_every_hours": 10.0}),
        ("neigh_cap_8", {"max_adds": 8}),
        ("neigh_cap_9", {"max_adds": 9}),
        ("neigh_cap_10", {"max_adds": 10}),
        ("neigh_fri_12", {"friday_flatten_completion_ny": "12:00"}),
        ("neigh_fri_13", {"friday_flatten_completion_ny": "13:00"}),
        ("neigh_fri_14", {"friday_flatten_completion_ny": "14:00"}),
        ("neigh_base_no_adds", None),  # sentinel → base cfg
    ]


def _normalize_row(m: dict, market: MarketSpec) -> dict:
    """Attach native + R-normalized fields (R = od-far not known post-hoc; use $/point proxy)."""
    pv = float(m.get("point_value") or market.point_value)
    net = float(m.get("net_usd") or 0.0)
    stress = float(m.get("intrabar_stress_dd_usd") or 0.0)
    # One-contract dollar scale: divide by typical multi-unit book if max_open known — report raw + per-unit.
    units = max(1, int(m.get("units") or 1))
    return {
        **m,
        "net_per_unit": net / units,
        "stress_per_unit": stress / units,
        "net_per_point_value": net / pv if pv else net,
        "stress_per_point_value": stress / pv if pv else stress,
    }


def write_master_summary(
    output_root: Path,
    *,
    primary: dict,
    base: dict,
    attr: dict,
    stress_rows: List[dict],
    neigh_rows: List[dict],
    stats: dict,
    xmarket: List[dict],
) -> None:
    lines = [
        "# Week-1 +8h v1 — stress + portability",
        "",
        "Contract: `RESEARCH_CONTRACT.yaml` · DSR `%s` · max_adds**=%d**" % (DSR, FROZEN_MAX_ADDS),
        "",
        "## Primary vs base (NAS100)",
        "",
        "| Book | Campaigns | Units | Adds | Net | Stress | N/S |",
        "|---|---:|---:|---:|---:|---:|---:|",
        "| Base no-add | %d | %d | %d | $%+.0f | $%+.0f | %.2f |"
        % (
            int(base.get("trades") or 0),
            int(base.get("units") or 0),
            int(base.get("adds_filled") or 0),
            float(base.get("net_usd") or 0),
            float(base.get("intrabar_stress_dd_usd") or 0),
            float(base.get("net_over_stress") or 0),
        ),
        "| **+8h v1** | %d | %d | %d | $%+.0f | $%+.0f | **%.2f** |"
        % (
            int(primary.get("trades") or 0),
            int(primary.get("units") or 0),
            int(primary.get("adds_filled") or 0),
            float(primary.get("net_usd") or 0),
            float(primary.get("intrabar_stress_dd_usd") or 0),
            float(primary.get("net_over_stress") or 0),
        ),
        "",
        "Attribution pass=%s · add share of net=%.1f%% · top5 conc=%.1f%% · rescued=%d hurt=%d"
        % (
            attr.get("pass"),
            100.0 * float(attr.get("add_share_of_net") or 0),
            float((attr.get("concentration") or {}).get("top_5_pct_of_net") or 0),
            int(attr.get("rescued_by_adds") or 0),
            int(attr.get("hurt_by_adds") or 0),
        ),
        "",
        "## Stage 3 — execution stress",
        "",
        "| Case | Net | Stress | N/S | Trades | Adds | Notes |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    base_ns = float(base.get("net_over_stress") or 0)
    for r in stress_rows:
        lines.append(
            "| %s | $%+.0f | $%+.0f | %.2f | %d | %d | %s |"
            % (
                r.get("run_id"),
                float(r.get("net_usd") or 0),
                float(r.get("intrabar_stress_dd_usd") or 0),
                float(r.get("net_over_stress") or 0),
                int(r.get("trades") or 0),
                int(r.get("adds_filled") or 0),
                r.get("notes") or "",
            )
        )
    # Survival flags
    pos = all(float(r.get("net_usd") or 0) > 0 for r in stress_rows if r.get("run_id") != "stress_no_adds")
    ns_above_base = sum(
        1
        for r in stress_rows
        if r.get("run_id") not in {"stress_no_adds"} and float(r.get("net_over_stress") or 0) >= base_ns
    )
    lines.extend(
        [
            "",
            "Survival: positive net (excl. no_adds)=%s · cases with N/S≥base (%.2f): %d/%d"
            % (pos, base_ns, ns_above_base, max(1, len(stress_rows) - 1)),
            "",
            "## Stage 4 — neighborhood",
            "",
            "| Case | Net | N/S | Trades | Adds |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for r in neigh_rows:
        lines.append(
            "| %s | $%+.0f | %.2f | %d | %d |"
            % (
                r.get("run_id"),
                float(r.get("net_usd") or 0),
                float(r.get("net_over_stress") or 0),
                int(r.get("trades") or 0),
                int(r.get("adds_filled") or 0),
            )
        )
    boot = (stats or {}).get("bootstrap") or {}
    lines.extend(
        [
            "",
            "## Stage 5 — stats",
            "",
            "- Campaign bootstrap N/S: mean=%.2f p05=%.2f p50=%.2f p95=%.2f · P(N/S<1)=%.2f · P(N/S<1.82)=%.2f"
            % (
                float(boot.get("ns_mean") or 0),
                float(boot.get("ns_p05") or 0),
                float(boot.get("ns_p50") or 0),
                float(boot.get("ns_p95") or 0),
                float(boot.get("frac_ns_below_1") or 0),
                float(boot.get("frac_ns_below_base_1_82") or 0),
            ),
            "",
            "## Cross-market (frozen v1)",
            "",
            "| Market | Campaigns | Units | Adds | Net | Stress | N/S | Net/PV | Stance |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for r in xmarket:
        ns = float(r.get("net_over_stress") or 0)
        net = float(r.get("net_usd") or 0)
        if net > 0 and ns >= 2:
            stance = "research+"
        elif net > 0:
            stance = "weak+"
        else:
            stance = "fail"
        lines.append(
            "| %s | %d | %d | %d | $%+.0f | $%+.0f | %.2f | %.1f | %s |"
            % (
                r.get("market"),
                int(r.get("trades") or 0),
                int(r.get("units") or 0),
                int(r.get("adds_filled") or 0),
                net,
                float(r.get("intrabar_stress_dd_usd") or 0),
                ns,
                float(r.get("net_per_point_value") or 0),
                stance,
            )
        )
    # Decision matrix
    by_m = {str(r.get("market")): r for r in xmarket}
    nas = by_m.get("NAS100") or primary
    nq = by_m.get("NQ")
    mnq = by_m.get("MNQ")
    ym = by_m.get("YM")
    mym = by_m.get("MYM")

    def _pos(r):
        return r is not None and float(r.get("net_usd") or 0) > 0

    decision = "pending"
    if _pos(nas) and _pos(nq) and _pos(mnq) and _pos(ym) and _pos(mym):
        decision = "broader index structural effect — locked OOS/forward next; still NO demo"
    elif _pos(nas) and _pos(nq) and _pos(mnq) and (not _pos(ym) or not _pos(mym)):
        decision = "Nasdaq-specific — research-only NAS100/NQ family; no portfolio multiplier"
    elif _pos(nas) and not _pos(nq):
        decision = "CFD/instrument-specific — do not paper-promote"
    elif not _pos(nas):
        decision = "primary failed stress/port — reject / archive"

    lines.extend(
        [
            "",
            "## Decision (predeclared matrix)",
            "",
            "**%s**" % decision,
            "",
            "Paper/demo gate: **NOT YET** (see RESEARCH_CONTRACT.yaml).",
            "",
            "Hub: `%s`" % output_root,
            "",
        ]
    )
    (output_root / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    rows = []
    for label, r in [("primary", primary), ("base", base)]:
        rows.append({"board": label, **{k: v for k, v in r.items() if k != "cfg"}})
    for r in stress_rows:
        rows.append({"board": "stress", **{k: v for k, v in r.items() if k != "cfg"}})
    for r in neigh_rows:
        rows.append({"board": "neighborhood", **{k: v for k, v in r.items() if k != "cfg"}})
    for r in xmarket:
        rows.append({"board": "xmarket", **{k: v for k, v in r.items() if k != "cfg"}})
    pd.DataFrame(rows).to_csv(output_root / "summary.csv", index=False)
    (output_root / "DECISION.json").write_text(
        json.dumps({"decision": decision, "dsr": DSR, "max_adds": FROZEN_MAX_ADDS}, indent=2) + "\n",
        encoding="utf-8",
    )


def run(
    *,
    output_root: Path,
    years: float,
    force: bool,
    email: bool,
    stages: Sequence[str],
) -> int:
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    contract_src = output_root / "RESEARCH_CONTRACT.yaml"
    if not contract_src.exists():
        raise FileNotFoundError("Missing RESEARCH_CONTRACT.yaml in hub")

    nas = _market_spec("NAS100")
    start, end = _window(years, nas)
    try:
        hub_rel = str(output_root.relative_to(REPO))
    except ValueError:
        hub_rel = str(output_root)
    rid = begin_run(
        run_class="sweep",
        variant_slug="od_half_eow_bull_hivol_w1_add8h_v1_stress_port",
        instrument="NAS100,NQ,MNQ,YM,MYM",
        hub_path=hub_rel,
        dsr_trial_id=DSR,
        meta={"years": years, "stages": list(stages), "max_adds": FROZEN_MAX_ADDS},
    )
    try:
        _progress(output_root, "=== W1+8h v1 stress/port START years=%.1f stages=%s ===" % (years, ",".join(stages)))
        primary = {}
        base = {}
        attr = {}
        stress_rows: List[dict] = []
        neigh_rows: List[dict] = []
        stats: dict = {}
        xmarket: List[dict] = []

        if "primary" in stages or "all" in stages:
            primary = run_replay(
                output_root=output_root,
                market=nas,
                run_id="primary_v1",
                cfg=_frozen_cfg(),
                force=force,
                start=start,
                end=end,
                causality_mode="strict",
            )
            base = run_replay(
                output_root=output_root,
                market=nas,
                run_id="base_no_adds",
                cfg=_base_cfg(),
                force=force,
                start=start,
                end=end,
                causality_mode="strict",
            )

        if "attr" in stages or "all" in stages:
            if not primary:
                ppath = output_root / "states" / "nas100_primary_v1" / "metrics.json"
                primary = json.loads(ppath.read_text(encoding="utf-8")) if ppath.exists() else {}
            sid = primary.get("strategy_id") or "nas100_primary_v1"
            state_root = output_root / "states" / sid
            if not state_root.exists():
                # fall back to prior discovery hub
                alt = (
                    REPO
                    / "live/state/weekly_open_day_breakout_od_half_eow_bull_hivol_w1_add8h_strict/states"
                    / "nas100_wod_od_half_eow_bull_hivol_w1_add8h"
                )
                if alt.exists():
                    state_root = alt
                    sid = "nas100_wod_od_half_eow_bull_hivol_w1_add8h"
            attr = stage_correctness_and_attribution(output_root, state_root, sid, nas, base)

        if "stress" in stages or "all" in stages:
            for case in exec_stress_cases():
                cfg = _frozen_cfg(case.cfg_overrides)
                if case.name == "no_adds":
                    cfg = _base_cfg()
                m = run_replay(
                    output_root=output_root,
                    market=nas,
                    run_id="stress_%s" % case.name,
                    cfg=cfg,
                    force=force,
                    start=start,
                    end=end,
                    slippage_ticks=case.slippage_ticks,
                    fee_mult=case.fee_mult,
                )
                m["notes"] = case.notes
                stress_rows.append(m)

        if "neigh" in stages or "all" in stages:
            for name, ov in neighborhood_cases():
                if ov is None:
                    cfg = _base_cfg()
                else:
                    cfg = _frozen_cfg(ov)
                m = run_replay(
                    output_root=output_root,
                    market=nas,
                    run_id=name,
                    cfg=cfg,
                    force=force,
                    start=start,
                    end=end,
                )
                neigh_rows.append(m)

        if "stats" in stages or "all" in stages:
            camps = output_root / "stage1_2" / "campaigns.csv"
            if not camps.exists():
                raise FileNotFoundError("Need stage1_2/campaigns.csv before stats")
            if not primary:
                ppath = output_root / "states" / "nas100_primary_v1" / "metrics.json"
                primary = json.loads(ppath.read_text(encoding="utf-8")) if ppath.exists() else {}
            stats = stage_stats(output_root, camps, float(primary.get("net_over_stress") or 0))

        if "xmarket" in stages or "all" in stages:
            for sym in ("NAS100", "NQ", "MNQ", "YM", "MYM"):
                market = _market_spec(sym)
                try:
                    mstart, mend = start, end
                    # MNQ/MYM shorter history — use available window
                    if sym in FUTURES_SOURCES:
                        mstart, mend = _window(years, market)
                        # align to common end but allow shorter start
                        mstart = max(mstart, start) if False else mstart
                    m = run_replay(
                        output_root=output_root,
                        market=market,
                        run_id="xmarket_v1",
                        cfg=_frozen_cfg(),
                        force=force,
                        start=mstart,
                        end=mend,
                    )
                    xmarket.append(_normalize_row(m, market))
                except Exception as exc:
                    _progress(output_root, "XMARKET FAIL %s: %s" % (sym, exc))
                    xmarket.append(
                        {
                            "market": sym,
                            "run_id": "xmarket_v1",
                            "net_usd": 0.0,
                            "intrabar_stress_dd_usd": 0.0,
                            "net_over_stress": 0.0,
                            "trades": 0,
                            "units": 0,
                            "adds_filled": 0,
                            "error": str(exc),
                            "net_per_point_value": 0.0,
                        }
                    )

        # Reload boards if partial
        if not primary:
            p = output_root / "states" / "nas100_primary_v1" / "metrics.json"
            if p.exists():
                primary = json.loads(p.read_text(encoding="utf-8"))
        if not base:
            p = output_root / "states" / "nas100_base_no_adds" / "metrics.json"
            if p.exists():
                base = json.loads(p.read_text(encoding="utf-8"))
        if not stress_rows:
            for case in exec_stress_cases():
                p = output_root / "states" / ("nas100_stress_%s" % case.name) / "metrics.json"
                if p.exists():
                    m = json.loads(p.read_text(encoding="utf-8"))
                    m["notes"] = case.notes
                    stress_rows.append(m)
        if not neigh_rows:
            for name, _ in neighborhood_cases():
                p = output_root / "states" / ("nas100_%s" % name) / "metrics.json"
                if p.exists():
                    neigh_rows.append(json.loads(p.read_text(encoding="utf-8")))
        if not xmarket:
            for sym in ("NAS100", "NQ", "MNQ", "YM", "MYM"):
                p = output_root / "states" / ("%s_xmarket_v1" % sym.lower()) / "metrics.json"
                if p.exists():
                    xmarket.append(_normalize_row(json.loads(p.read_text(encoding="utf-8")), _market_spec(sym)))
        if not attr:
            ap = output_root / "stage1_2" / "CORRECTNESS_ATTRIBUTION.json"
            if ap.exists():
                attr = json.loads(ap.read_text(encoding="utf-8"))
        if not stats:
            sp = output_root / "stage5_stats" / "STATS_SUMMARY.json"
            if sp.exists():
                stats = json.loads(sp.read_text(encoding="utf-8"))

        write_master_summary(
            output_root,
            primary=primary or {},
            base=base or {},
            attr=attr or {},
            stress_rows=stress_rows,
            neigh_rows=neigh_rows,
            stats=stats or {},
            xmarket=xmarket,
        )
        (output_root / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": True, "dsr": DSR, "stages": list(stages)}, indent=2) + "\n",
            encoding="utf-8",
        )
        write_run_manifest(
            output_root,
            data_inputs=[nas.csv, REPO / "fx" / "nas100_1m.csv"],
            output_paths=[output_root / "summary.csv", output_root / "SUMMARY.md"],
            strategy_config={"strategy_id": "od_half_eow_bull_hivol_w1_add8h_v1", "max_adds": FROZEN_MAX_ADDS},
            causality_mode="strict",
            extra={"dsr_trial_id": DSR},
        )

        body = (output_root / "SUMMARY.md").read_text(encoding="utf-8")
        # Phone-friendly short tip
        tip = [
            "potions: w1+8h v1 stress/port COMPLETE",
            "",
            "Hub: %s" % output_root,
            "DSR: %s · max_adds=%d" % (DSR, FROZEN_MAX_ADDS),
            "",
        ]
        if primary:
            tip.append(
                "NAS100 primary: net=$%+.0f N/S=%.2f trades=%d adds=%d"
                % (
                    float(primary.get("net_usd") or 0),
                    float(primary.get("net_over_stress") or 0),
                    int(primary.get("trades") or 0),
                    int(primary.get("adds_filled") or 0),
                )
            )
        if base:
            tip.append(
                "NAS100 base:    net=$%+.0f N/S=%.2f"
                % (float(base.get("net_usd") or 0), float(base.get("net_over_stress") or 0))
            )
        dec = output_root / "DECISION.json"
        if dec.exists():
            tip.append("Decision: %s" % json.loads(dec.read_text(encoding="utf-8")).get("decision"))
        tip.append("")
        tip.append(body[:3500])
        email_body = "\n".join(tip) + "\n"
        (output_root / "EMAIL.txt").write_text(email_body, encoding="utf-8")
        if email:
            send_email(subject="potions: w1+8h v1 stress/port COMPLETE", body=email_body)

        complete_run(
            rid,
            net_usd=float((primary or {}).get("net_usd") or 0),
            stress_dd_usd=float((primary or {}).get("intrabar_stress_dd_usd") or 0),
            ns=float((primary or {}).get("net_over_stress") or 0),
            trades=int((primary or {}).get("trades") or 0),
            meta={"stages": list(stages), "xmarket": [r.get("market") for r in xmarket]},
        )
        _progress(output_root, "=== COMPLETE ===")
        return 0
    except Exception as exc:
        fail_run(rid, notes=str(exc))
        _progress(output_root, "CRASH %s\n%s" % (exc, traceback.format_exc()))
        if email:
            send_email(
                subject="potions: w1+8h v1 stress/port FAILED",
                body="Hub: %s\n\n%s\n%s" % (output_root, exc, traceback.format_exc()[-2500:]),
            )
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--years", type=float, default=10.0)
    p.add_argument("--force", action="store_true")
    p.add_argument("--email", action="store_true")
    p.add_argument(
        "--stages",
        default="all",
        help="Comma list: primary,attr,stress,neigh,stats,xmarket,all",
    )
    args = p.parse_args(argv)
    stages = [s.strip() for s in str(args.stages).split(",") if s.strip()]
    return run(
        output_root=args.output_root,
        years=float(args.years),
        force=bool(args.force),
        email=bool(args.email),
        stages=stages,
    )


if __name__ == "__main__":
    raise SystemExit(main())
