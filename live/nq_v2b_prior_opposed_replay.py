from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .replay_audit import POINT_VALUES
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


def load_st_events(fills_path: Path, strategy_id: str) -> Dict[str, List[Dict[str, str]]]:
    fills = pd.read_csv(fills_path)
    fills = fills[fills["strategy_id"].astype(str) == strategy_id].copy()
    fills = fills[fills["reason"].astype(str).isin(["entry", "runner_entry"])].copy()
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    out: Dict[str, List[Dict[str, str]]] = {}
    for row in fills.sort_values("ts").itertuples(index=False):
        side = "long" if str(row.side).lower() == "buy" else "short"
        ts = pd.Timestamp(row.ts)
        out.setdefault(ts.date().isoformat(), []).append({"ts": ts.isoformat(), "side": side})
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
    st_strategy_id: Optional[str] = None,
) -> Result:
    market = market.lower()
    cfg = MARKETS[market]
    instrument = cfg.instrument
    output_root.mkdir(parents=True, exist_ok=True)
    strategy_id = f"{market}_v2b_prior_opposed_stpmc_only_S_1_1_3"
    state_root = output_root / "states" / strategy_id
    if force and state_root.exists():
        shutil.rmtree(state_root)
    st_strategy_id = st_strategy_id or DEFAULT_ST_STRATEGY_IDS[market]
    st_fills = st_fills_path or default_st_fills_path(market)
    if not st_fills.exists():
        raise FileNotFoundError(st_fills)
    st_events = load_st_events(
        st_fills,
        st_strategy_id,
    )
    print("Loading %s 1m bars..." % instrument, flush=True)
    gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    regime_dates = _regime_dates(cfg, gby, start=date(2021, 3, 4))
    regime_dates = [d for d in regime_dates if _has_full_rth_close(gby.get(d), d)]
    regime_dates_iso = [d.isoformat() for d in regime_dates]

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
        max_contracts=5,
        max_open_orders=64,
        config_json=json.dumps(
            {
                "market": market,
                "mode": "oco_then_reverse",
                "entry_qty": 5,
                "tp1_qty": 1,
                "tp2_qty": 1,
                "tick_size": 0.25,
                "use_regime_filter": True,
                "start": "2021-03-04",
                "regime_dates": regime_dates_iso,
                "record_levels": False,
                "dynamic_sizing_events": st_events,
                "prior_opposite_only": True,
                "prior_opposite_entry_qty": 5,
                "prior_opposite_tp1_qty": 1,
                "prior_opposite_tp2_qty": 1,
            },
            sort_keys=True,
        ),
    )
    store.write_table("strategy_instances", [as_row(instance)])
    engine = Engine(store=store, persist_bars=False, persist_health=False, slippage_ticks=1.0)
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
    result = summarize_units(
        strategy_id,
        state_root,
        audit_bars,
        instrument,
        cfg.fee_per_unit,
        market=market,
        regime_days=len(regime_dates),
        st_events=st_events,
    )
    write_report(output_root, result)
    return result


def write_report(output_root: Path, result: Result) -> None:
    rows = [
        {
            "strategy_id": result.strategy_id,
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
            "state_root": str(result.state_root),
        }
    ]
    with (output_root / "summary.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# %s v2b Prior-Opposed ST+PMC Broker-Like Replay" % result.instrument,
        "",
        "True `Engine + PaperBroker + StrategyPlugin` replay. The v2b entry order is only armed after a same-session %s hourly ST+PMC entry has already fired in the opposite direction." % result.instrument,
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
        "## Causality",
        "",
        "- Regime sessions replayed: **%d**" % result.regime_days,
        "- Prior-opposite entries found: **%d / %d**" % (result.prior_opposite_entries, result.trades),
        "- Causal violations: **%d**" % result.causality_violations,
        "- Direction mix: **%d long / %d short**" % (result.long_trades, result.short_trades),
        "",
        "Files:",
        "",
        "- `summary.csv`",
        "- `states/%s/`" % result.strategy_id,
    ]
    (output_root / "INDEX.md").write_text("\n".join(lines))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Replay v2b only after prior opposite same-market ST+PMC.")
    parser.add_argument("--market", choices=PRIOR_OPPOSED_MARKETS, default="nq")
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--st-fills", type=Path, default=None)
    parser.add_argument("--st-strategy-id", default=None)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    output_root = args.output_root or _default_output_root(args.market)
    result = run(
        output_root,
        force=not args.no_force,
        market=args.market,
        st_fills_path=args.st_fills,
        st_strategy_id=args.st_strategy_id,
    )
    print("Wrote %s (Net/Stress %.2f)" % (output_root / "INDEX.md", result.net_stress))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
