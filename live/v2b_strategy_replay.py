from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

from .bars import rth_bars
from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .replay_audit import POINT_VALUES, Unit
from .replay_realism import hardened_replay_engine_kwargs
from .store import FlatFileStore


REPO = Path(__file__).resolve().parents[1]
MNQ_ROOT = REPO / "mnq"
V2D = MNQ_ROOT / "v2d"
CASE = MNQ_ROOT / "case_studies" / "midnight_open_hourly_charts"
SCRIPTS = REPO / "scripts"
DEFAULT_DBN = MNQ_ROOT / "raw" / "extracted_new" / "glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst"
HISTORY_START = date(2021, 3, 4)
FEE_PER_UNIT = 1.50
DEFAULT_SLIPPAGE_TICKS = 1.0

sys.path[:0] = [str(MNQ_ROOT), str(SCRIPTS), str(V2D), str(CASE)]

from benchmark_v2b_scaleout_candidates import causal_regime_v2b  # noqa: E402

import build_midnight_open_hourly_charts as mdata  # noqa: E402


@dataclass(frozen=True)
class ReplayResult:
    mode: str
    strategy_id: str
    state_root: Path
    units: int
    trades: int
    net_usd: float
    closed_dd_usd: float
    intrabar_stress_dd_usd: float
    max_open_units: int
    win_rate: float
    profit_factor: float

    @property
    def net_over_stress(self) -> float:
        return self.net_usd / abs(self.intrabar_stress_dd_usd) if self.intrabar_stress_dd_usd else 0.0


def run(output_root: Path, dbn: Path, modes: List[str], max_days: Optional[int] = None) -> List[ReplayResult]:
    output_root.mkdir(parents=True, exist_ok=True)
    print("Loading MNQ 1m DBN for V2B StrategyPlugin replay...", flush=True)
    gby = mdata.load_1m_by_ny_date(dbn.resolve(), "mnq")
    regime = causal_regime_v2b()
    regime_dates = [
        day.isoformat()
        for day in sorted(gby.keys())
        if day >= HISTORY_START and day in regime.index and bool(regime.loc[day])
    ]
    if max_days is not None:
        regime_dates = regime_dates[:max_days]
    print("Regime sessions to replay: %d" % len(regime_dates), flush=True)

    bars_by_mode: Dict[str, List[AuditBar]] = {}
    results: List[ReplayResult] = []
    for mode in modes:
        strategy_id = "mnq_v2b_scaleout_%s" % mode
        state_root = output_root / "states" / strategy_id
        if state_root.exists():
            shutil.rmtree(state_root)
        store = FlatFileStore(state_root, defer_table_writes=True)
        store.ensure()
        instance = StrategyInstance(
            strategy_id=strategy_id,
            strategy_type="v2b_scaleout",
            version="v1",
            instrument="MNQ",
            broker_instrument="MNQ",
            account_mode="paper",
            enabled=True,
            timeframes="1m",
            max_contracts=2,
            max_open_orders=24,
            config_json=json.dumps(
                {
                    "mode": mode,
                    "entry_qty": 2,
                    "tick_size": 0.25,
                    "use_regime_filter": True,
                    "regime_dates": regime_dates,
                    "record_levels": False,
                },
                sort_keys=True,
            ),
        )
        store.write_table("strategy_instances", [as_row(instance)])
        engine = Engine(
            store=store,
            persist_bars=False,
            persist_health=False,
            **hardened_replay_engine_kwargs(slippage_ticks=DEFAULT_SLIPPAGE_TICKS),
        )

        audit_bars: List[AuditBar] = []
        print("Replaying %s..." % mode, flush=True)
        for idx, day_s in enumerate(regime_dates, start=1):
            day = date.fromisoformat(day_s)
            df = rth_bars(gby.get(day), day, dense=True)
            if df.empty:
                continue
            for ts, row in df.iterrows():
                ts_s = pd.Timestamp(ts).isoformat()
                bar = Bar(
                    instrument="MNQ",
                    timeframe="1m",
                    ts=ts_s,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0.0)),
                    complete=True,
                    source=str(dbn),
                )
                engine.process_bar(bar)
                audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
            if idx % 250 == 0:
                print("  %s: %d/%d sessions" % (mode, idx, len(regime_dates)), flush=True)

        bars_by_mode[mode] = audit_bars
        store.flush_tables()
        fills_path = state_root / "fills.csv"
        units = units_from_v2b_fills(fills_path, strategy_id)
        audit = fast_intraday_audit(
            strategy_id=strategy_id,
            state_root=state_root,
            bars=audit_bars,
            units=units,
            instrument="MNQ",
            fee_per_unit=FEE_PER_UNIT,
        )
        results.append(
            ReplayResult(
                mode=mode,
                strategy_id=strategy_id,
                state_root=state_root,
                units=len(units),
                trades=len({u.trade_id for u in units}),
                net_usd=audit["net_usd"],
                closed_dd_usd=audit["closed_dd_usd"],
                intrabar_stress_dd_usd=audit["intrabar_stress_dd_usd"],
                max_open_units=audit["max_open_units"],
                win_rate=audit["win_rate"],
                profit_factor=audit["profit_factor"],
            )
        )

    write_summary(output_root, results)
    return results


def audit_existing(output_root: Path, dbn: Path, modes: List[str]) -> List[ReplayResult]:
    print("Loading MNQ 1m DBN for V2B audit-only pass...", flush=True)
    gby = mdata.load_1m_by_ny_date(dbn.resolve(), "mnq")
    regime = causal_regime_v2b()
    regime_dates = [
        day.isoformat()
        for day in sorted(gby.keys())
        if day >= HISTORY_START and day in regime.index and bool(regime.loc[day])
    ]
    audit_bars: List[AuditBar] = []
    for day_s in regime_dates:
        day = date.fromisoformat(day_s)
        df = _rth_bars(gby.get(day), day)
        for ts, row in df.iterrows():
            audit_bars.append(
                AuditBar(
                    pd.Timestamp(ts).isoformat(),
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                )
            )

    results: List[ReplayResult] = []
    for mode in modes:
        strategy_id = "mnq_v2b_scaleout_%s" % mode
        state_root = output_root / "states" / strategy_id
        units = units_from_v2b_fills(state_root / "fills.csv", strategy_id)
        audit = fast_intraday_audit(
            strategy_id=strategy_id,
            state_root=state_root,
            bars=audit_bars,
            units=units,
            instrument="MNQ",
            fee_per_unit=FEE_PER_UNIT,
        )
        results.append(
            ReplayResult(
                mode=mode,
                strategy_id=strategy_id,
                state_root=state_root,
                units=len(units),
                trades=len({u.trade_id for u in units}),
                net_usd=audit["net_usd"],
                closed_dd_usd=audit["closed_dd_usd"],
                intrabar_stress_dd_usd=audit["intrabar_stress_dd_usd"],
                max_open_units=audit["max_open_units"],
                win_rate=audit["win_rate"],
                profit_factor=audit["profit_factor"],
            )
        )
    write_summary(output_root, results)
    return results


def units_from_v2b_fills(path: Path, candidate: str) -> List[Unit]:
    rows = _read_csv(path)
    rows.sort(key=lambda row: row.get("ts", ""))
    open_lots: Dict[str, List[tuple[str, float, str]]] = {}
    out: List[Unit] = []
    n = 0
    for row in rows:
        side = row.get("side", "").lower()
        qty = int(float(row.get("quantity") or 0))
        ts = row.get("ts", "")
        price = float(row.get("price") or 0.0)
        reason = row.get("reason", "")
        trade_id = row.get("trade_id") or candidate
        if reason in {"entry", "add", "time_add"}:
            direction = "Long" if side == "buy" else "Short"
            lots = open_lots.setdefault(trade_id, [])
            for _ in range(qty):
                lots.append((ts, price, direction))
            continue
        lots = open_lots.get(trade_id, [])
        close_direction = "Long" if side == "sell" else "Short"
        for _ in range(qty):
            match_idx = next((idx for idx, lot in enumerate(lots) if lot[2] == close_direction), None)
            if match_idx is None:
                continue
            entry_ts, entry_price, direction = lots.pop(match_idx)
            n += 1
            out.append(
                Unit(
                    candidate=candidate,
                    trade_id=trade_id,
                    unit_id=str(n),
                    direction=direction,
                    entry_ts=entry_ts,
                    entry_price=entry_price,
                    exit_ts=ts,
                    exit_price=price,
                    exit_reason=reason,
                )
            )
    return out


@dataclass(frozen=True)
class AuditBar:
    ts: str
    open: float
    high: float
    low: float
    close: float


def _rth_bars(df: Optional[pd.DataFrame], session_day: date) -> pd.DataFrame:
    return rth_bars(df, session_day, dense=True)


def fast_intraday_audit(
    *,
    strategy_id: str,
    state_root: Path,
    bars: List[AuditBar],
    units: List[Unit],
    instrument: str,
    fee_per_unit: float,
) -> Dict[str, float]:
    point_value = POINT_VALUES[instrument]
    units = sorted(units, key=lambda u: (u.entry_ts, u.exit_ts, u.unit_id))
    entries = sorted(units, key=lambda u: u.entry_ts)
    exits = sorted(units, key=lambda u: u.exit_ts)
    entry_i = 0
    exit_i = 0
    active: List[Unit] = []
    realized_usd = 0.0
    peak_close = 0.0
    close_dd = 0.0
    intrabar_dd = 0.0
    max_open = 0
    equity_rows: List[Dict[str, str]] = []

    for bar in bars:
        while exit_i < len(exits) and exits[exit_i].exit_ts < bar.ts:
            unit = exits[exit_i]
            realized_usd += unit.points * point_value - fee_per_unit
            exit_i += 1
        while entry_i < len(entries) and entries[entry_i].entry_ts <= bar.ts:
            active.append(entries[entry_i])
            entry_i += 1
        active = [unit for unit in active if unit.exit_ts >= bar.ts]
        close_equity = realized_usd + sum((bar.close - u.entry_price) * u.sign * point_value for u in active)
        intrabar_equity = realized_usd + sum(_intrabar_usd(u, bar, point_value) for u in active)
        max_open = max(max_open, len(active))
        close_dd = min(close_dd, close_equity - peak_close)
        intrabar_dd = min(intrabar_dd, intrabar_equity - peak_close)
        peak_close = max(peak_close, close_equity)
        equity_rows.append(
            {
                "ts": bar.ts,
                "realized_usd": "%.2f" % realized_usd,
                "open_units": str(len(active)),
                "close_equity_usd": "%.2f" % close_equity,
                "intrabar_stress_equity_usd": "%.2f" % intrabar_equity,
                "close_dd_usd": "%.2f" % close_dd,
                "intrabar_stress_dd_usd": "%.2f" % intrabar_dd,
            }
        )

    unit_rows: List[Dict[str, str]] = []
    unit_nets = []
    for unit in units:
        net = unit.points * point_value - fee_per_unit
        unit_nets.append(net)
        unit_rows.append(
            {
                "candidate": strategy_id,
                "trade_id": unit.trade_id,
                "unit_id": unit.unit_id,
                "direction": unit.direction,
                "entry_ts": unit.entry_ts,
                "entry_price": "%.2f" % unit.entry_price,
                "exit_ts": unit.exit_ts,
                "exit_price": "%.2f" % unit.exit_price,
                "exit_reason": unit.exit_reason,
                "net_usd": "%.2f" % net,
            }
        )
    _write_csv(state_root / "unit_trades.csv", unit_rows)
    _write_csv(state_root / "equity_curve.csv", equity_rows)

    arr = np.array(unit_nets, dtype=float)
    wins = float(arr[arr > 0].sum()) if len(arr) else 0.0
    losses = abs(float(arr[arr < 0].sum())) if len(arr) else 0.0
    pf = wins / losses if losses > 1e-9 else (math.inf if wins > 0 else 0.0)
    win_rate = 100.0 * float((arr > 0).mean()) if len(arr) else 0.0
    return {
        "net_usd": float(arr.sum()) if len(arr) else 0.0,
        "closed_dd_usd": close_dd,
        "intrabar_stress_dd_usd": intrabar_dd,
        "max_open_units": max_open,
        "win_rate": win_rate,
        "profit_factor": pf,
    }


def _intrabar_usd(unit: Unit, bar: AuditBar, point_value: float) -> float:
    if unit.sign > 0:
        return (bar.low - unit.entry_price) * point_value
    return (unit.entry_price - bar.high) * point_value


def _write_csv(path: Path, rows: Iterable[Dict[str, str]]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return sign + f"{abs(value):,.2f}"


def write_summary(output_root: Path, results: List[ReplayResult]) -> None:
    rows = [
        {
            "mode": r.mode,
            "strategy_id": r.strategy_id,
            "state_root": str(r.state_root),
            "units": str(r.units),
            "trades": str(r.trades),
            "net_usd": "%.2f" % r.net_usd,
            "closed_dd_usd": "%.2f" % r.closed_dd_usd,
            "intrabar_stress_dd_usd": "%.2f" % r.intrabar_stress_dd_usd,
            "max_open_units": str(r.max_open_units),
            "win_rate_pct": "%.2f" % r.win_rate,
            "profit_factor": "%.3f" % r.profit_factor if math.isfinite(r.profit_factor) else "inf",
            "net_over_stress_dd": "%.2f" % r.net_over_stress,
        }
        for r in results
    ]
    _write_csv(output_root / "v2b_strategy_plugin_summary.csv", rows)
    lines = [
        "# V2B Intraday StrategyPlugin Replay",
        "",
        "This hardens the v2b family into a true intraday `StrategyPlugin` path. The old `$83k / -$3.1k` row is retained as a research scanner reference only: it scans Long first across the whole day and can therefore choose a later Long over an earlier Short. The live-orderable rows below use actual resting order modes.",
        "",
        "| Mode | Units | Trades | Net | Closed DD | Intrabar Stress DD | Max Open Units | Net / Stress | Win % | PF |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in sorted(results, key=lambda item: item.net_over_stress, reverse=True):
        pf = "%.2f" % r.profit_factor if math.isfinite(r.profit_factor) else "inf"
        lines.append(
            "| %s | %d | %d | $%s | $%s | $%s | %d | %.2f | %.1f%% | %s |"
            % (
                r.mode,
                r.units,
                r.trades,
                money(r.net_usd),
                money(r.closed_dd_usd),
                money(r.intrabar_stress_dd_usd),
                r.max_open_units,
                r.net_over_stress,
                r.win_rate,
                pf,
            )
        )
    lines.extend(
        [
            "",
            "## Live Read",
            "",
            "- `oco_then_reverse` is closest to a normal TV/Tradovate harness: both breakout stops are live after the 09:30-09:45 OR, first fill wins, and the opposite side may arm after that leg exits.",
            "- `strict_long_then_short` is the literal executable version of the old wording: short is allowed only after a filled long exits. If long never fills, no short is taken.",
            "- The plugin submits protective exits from `on_fill`; TP1 cancels/rebuilds TP2 behind the runner stop so same-bar runner-stop-vs-TP2 ambiguity stays pessimistic.",
            "- Fees are applied in the audit at `$1.50` per closed MNQ unit, matching the research run.",
            "",
        ]
    )
    (output_root / "V2B_STRATEGY_PLUGIN_REPLAY.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay MNQ v2b as a true intraday StrategyPlugin.")
    parser.add_argument("--output-root", type=Path, default=REPO / "live" / "state" / "v2b_strategy_plugin_replay")
    parser.add_argument("--dbn", type=Path, default=DEFAULT_DBN)
    parser.add_argument("--mode", action="append", choices=["oco_then_reverse", "strict_long_then_short"], help="Mode to replay; repeatable.")
    parser.add_argument("--max-days", type=int, default=None, help="Optional smoke-test cap on regime sessions.")
    parser.add_argument("--audit-existing", action="store_true", help="Re-audit existing fill files without rerunning the strategy.")
    args = parser.parse_args()
    modes = args.mode or ["oco_then_reverse", "strict_long_then_short"]
    if args.audit_existing:
        audit_existing(args.output_root, args.dbn, modes)
    else:
        run(args.output_root, args.dbn, modes, max_days=args.max_days)
    print("Wrote %s" % (args.output_root / "V2B_STRATEGY_PLUGIN_REPLAY.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
