#!/usr/bin/env python3
"""NAS100 clean-break (live trail06_m4_e2_out_be) vs v2b_scaleout (stop at opposite OR side).

Same harness as ``live/nas100_clean_break_best_1mfill_quote_validation.py``: 1m quote bars
drive every fill (1 tick slippage), clean-break gets 5m signal bars, v2b signals on 1m.

Datasets:
  research   fx/nas100_1m.csv (2016-11 → 2025-09), synthetic half-spread 0.5 tick
  nq_recent  NQ front 1m (2025-10-01 → 2026-10-11), proxy for post-research NAS100
  demo       OANDA NAS100 1m bars stored by the live clean-break demo (real bid/ask)

Usage:
  scripts/nas100_clean_break_vs_v2b.py run --dataset research --strategy cb
  scripts/nas100_clean_break_vs_v2b.py summarize
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

sys.path.insert(0, "/home/tester/hsm")
sys.path.insert(0, "/home/tester/hsm/potions/v20-python/src")

from potions.live.broker import DEFAULT_TICK_SIZE  # noqa: E402
from potions.live.causality import AUDIT  # noqa: E402
from potions.live.engine import Engine  # noqa: E402
from potions.live.models import Bar, StrategyInstance, as_row  # noqa: E402
from potions.live.nas100_clean_break_best_1mfill_quote_validation import (  # noqa: E402
    flush_market_close_fills,
    signal_bar_from_bucket,
)
from potions.live.replay_audit import POINT_VALUES  # noqa: E402
from potions.live.store import FlatFileStore  # noqa: E402
from potions.live.v2b_clean_break_pyramid_trail_sizing_v1 import FEE_PER_UNIT, VARIANTS  # noqa: E402
from potions.live.v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills  # noqa: E402
from potions.live.verification import QuietPaperVerificationProvider  # noqa: E402

REPO = Path("/home/tester/hsm/potions")
HUB = REPO / "live/state/nas100_clean_break_vs_v2b_20261030"
NY = "America/New_York"
INSTRUMENT = "NAS100"
TICK = 0.1
HALF_SPREAD_TICKS = 0.5
DATASETS = {
    "research": dict(path=REPO / "fx/nas100_1m.csv", start=None, end="2025-10-01", quotes=False),
    "nq_recent": dict(path=REPO / "nq/raw/nq_front_1m_20100606_20261011.csv", start="2025-10-01", end=None, quotes=False),
    "demo": dict(
        path=REPO / "live/demo/nas100_v2b_clean_break_trail06_m4_e2_out_be_oanda/state/bars/NAS100_1m.csv",
        start=None,
        end=None,
        quotes=True,
    ),
}
STRATEGIES = ("cb", "v2b", "v2b_long")


def load_1m(dataset: str) -> pd.DataFrame:
    spec = DATASETS[dataset]
    df = pd.read_csv(spec["path"])
    ts_col = "ts_event" if "ts_event" in df.columns else "ts"
    ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
    df = df[ts.notna()].copy()
    df["ts"] = ts[ts.notna()].dt.tz_convert(NY)
    df = df.drop_duplicates("ts").sort_values("ts")
    if spec["start"]:
        df = df[df["ts"] >= pd.Timestamp(spec["start"], tz=NY)]
    if spec["end"]:
        df = df[df["ts"] < pd.Timestamp(spec["end"], tz=NY)]
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["volume"] = pd.to_numeric(df.get("volume", 0.0), errors="coerce").fillna(0.0)
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df[(df["open"] > 0) & (df["high"] >= df[["open", "close"]].max(axis=1)) & (df["low"] <= df[["open", "close"]].min(axis=1))]
    df = df[df["ts"].dt.weekday < 5]
    t = df["ts"].dt.time
    df = df[(t >= pd.Timestamp("09:30").time()) & (t < pd.Timestamp("16:00").time())].copy()
    df["session_day"] = df["ts"].dt.date.astype(str)
    df["bucket_5m"] = df["ts"].dt.floor("5min")
    return df.reset_index(drop=True)


def quote_bar(row: Any, *, quotes: bool, source: str) -> Bar:
    if quotes and pd.notna(getattr(row, "bid_close", None)):
        bid = (row.bid_open, row.bid_high, row.bid_low, row.bid_close)
        ask = (row.ask_open, row.ask_high, row.ask_low, row.ask_close)
    else:
        h = HALF_SPREAD_TICKS * TICK
        bid = (row.open - h, row.high - h, row.low - h, row.close - h)
        ask = (row.open + h, row.high + h, row.low + h, row.close + h)
    return Bar(
        instrument=INSTRUMENT, timeframe="1m", ts=pd.Timestamp(row.ts).isoformat(),
        open=float(row.open), high=float(row.high), low=float(row.low), close=float(row.close),
        volume=float(row.volume or 0.0), complete=True, source=source,
        bid_open=float(bid[0]), bid_high=float(bid[1]), bid_low=float(bid[2]), bid_close=float(bid[3]),
        ask_open=float(ask[0]), ask_high=float(ask[1]), ask_low=float(ask[2]), ask_close=float(ask[3]),
    )


def strategy_config(strategy: str, sessions: List[str]) -> Dict[str, Any]:
    if strategy == "cb":
        variant = next(v for v in VARIANTS if v.name == "trail06_m4_e2_out_be")
        cfg = dict(variant.config())
        cfg.update({"market": "nas100", "record_levels": False, "tick_size": TICK,
                    "fill_to_signal_minutes": 5, "fill_signal_bucket_end": True})
        return cfg
    cfg = {"entry_qty": 3, "tp1_qty": 1, "tp2_qty": 1, "mode": "oco_then_reverse", "rth_start": "09:30",
           "or_end": "09:45", "eod_cutoff": "15:59", "tick_size": TICK, "use_regime_filter": False,
           "prior_opposite_only": False, "record_levels": False}
    if strategy == "v2b_long":
        cfg["use_session_direction_bias"] = True
        cfg["session_direction_bias"] = {s: "Long" for s in sessions}
    return cfg


def run(dataset: str, strategy: str) -> Dict[str, Any]:
    out = HUB / dataset / strategy
    state_root = out / "state"
    if state_root.exists():
        shutil.rmtree(state_root)
    out.mkdir(parents=True, exist_ok=True)
    bars = load_1m(dataset)
    sessions = sorted(bars["session_day"].unique())
    cfg = strategy_config(strategy, sessions)
    sid = "nas100_%s_%s" % (strategy, dataset)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    store.write_table("strategy_instances", [as_row(StrategyInstance(
        strategy_id=sid, strategy_type="v2b_clean_break" if strategy == "cb" else "v2b_scaleout", version="v1",
        instrument=INSTRUMENT, broker_instrument=INSTRUMENT, account_mode="paper", enabled=True,
        timeframes="5m" if strategy == "cb" else "1m",
        max_contracts=int(cfg.get("max_pyramid_qty") or cfg.get("entry_qty") or 4), max_open_orders=24,
        config_json=json.dumps(cfg, sort_keys=True),
    ))])
    POINT_VALUES[INSTRUMENT] = 1.0
    DEFAULT_TICK_SIZE[INSTRUMENT] = TICK
    engine = Engine(store=store, persist_bars=False, persist_health=False, slippage_ticks=1.0,
                    tick_size={INSTRUMENT: TICK}, verification_provider=QuietPaperVerificationProvider(),
                    causality_mode=AUDIT)
    quotes = bool(DATASETS[dataset]["quotes"])
    source = "%s:%s" % (dataset, DATASETS[dataset]["path"].name)
    audit_bars: List[AuditBar] = []
    for _, day in bars.groupby("session_day", sort=True):
        for _, chunk in day.groupby("bucket_5m", sort=True):
            last: Optional[Bar] = None
            for row in chunk.itertuples(index=False):
                b = quote_bar(row, quotes=quotes, source=source)
                engine.process_bar(b)
                if strategy != "cb":
                    flush_market_close_fills(engine, b)
                last = b
                audit_bars.append(AuditBar(b.ts, b.open, b.high, b.low, b.close))
            if strategy == "cb" and last is not None:
                engine.process_bar(signal_bar_from_bucket(chunk), broker_fills=False)
                flush_market_close_fills(engine, last)
    store.flush_tables()
    units = units_from_v2b_fills(state_root / "fills.csv", sid)
    audit = fast_intraday_audit(strategy_id=sid, state_root=state_root, bars=audit_bars, units=units,
                                instrument=INSTRUMENT, fee_per_unit=FEE_PER_UNIT)
    trades = pd.DataFrame()
    if units:
        ut = pd.DataFrame([{"trade_id": u.trade_id, "unit_id": u.unit_id, "entry_ts": u.entry_ts,
                            "net_usd": u.points * POINT_VALUES[INSTRUMENT] - FEE_PER_UNIT} for u in units])
        ut["entry_ts"] = pd.to_datetime(ut["entry_ts"], utc=True)
        trades = ut.groupby("trade_id").agg(entry_ts=("entry_ts", "min"), net=("net_usd", "sum"),
                                            units=("unit_id", "count")).sort_values("entry_ts")
        trades.to_csv(out / "trades.csv")
    viol = state_root / "causality_violations.csv"
    res = {
        "dataset": dataset, "strategy": strategy, "sessions": len(sessions),
        "start": sessions[0] if sessions else "", "end": sessions[-1] if sessions else "",
        "trades": int(len(trades)), "units": int(len(units)),
        "net_usd": float(audit["net_usd"]), "closed_dd_usd": float(audit["closed_dd_usd"]),
        "stress_dd_usd": float(audit["intrabar_stress_dd_usd"]),
        "win_rate": float((trades["net"] > 0).mean()) if len(trades) else 0.0,
        "profit_factor": float(trades.loc[trades.net > 0, "net"].sum() / -trades.loc[trades.net < 0, "net"].sum())
        if len(trades) and (trades.net < 0).any() else 0.0,
        "causality_violations": max(0, sum(1 for _ in viol.open()) - 1) if viol.exists() else 0,
        "shorts": int((pd.read_csv(state_root / "fills.csv").query("reason == 'entry' and side == 'sell'")).shape[0])
        if (state_root / "fills.csv").exists() else 0,
    }
    res["ns"] = res["net_usd"] / abs(res["stress_dd_usd"]) if res["stress_dd_usd"] else 0.0
    if len(trades):
        yr = trades.assign(y=trades.entry_ts.dt.tz_convert(NY).dt.year).groupby("y")["net"].sum()
        res["yearly_net"] = {int(k): round(float(v), 2) for k, v in yr.items()}
    (out / "RESULT.json").write_text(json.dumps(res, indent=2))
    print(json.dumps({k: v for k, v in res.items() if k != "yearly_net"}))
    return res


def summarize() -> None:
    rows = []
    for p in sorted(HUB.glob("*/*/RESULT.json")):
        rows.append(json.loads(p.read_text()))
    df = pd.DataFrame(rows)
    cols = ["dataset", "strategy", "start", "end", "trades", "units", "net_usd", "stress_dd_usd", "ns",
            "win_rate", "profit_factor", "shorts", "causality_violations"]
    df[cols].to_csv(HUB / "summary.csv", index=False)
    print(df[cols].to_string(index=False))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--dataset", choices=sorted(DATASETS), required=True)
    r.add_argument("--strategy", choices=STRATEGIES, required=True)
    sub.add_parser("summarize")
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.dataset, a.strategy)
    else:
        summarize()


if __name__ == "__main__":
    main()
