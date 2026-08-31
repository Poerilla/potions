"""NAS100 clean-break best-N/S validation on finer 1m broker-style data.

This is intentionally a validation run, not a new optimization sweep:

- frozen candidate: ``trail06_m4_e2_out_be``
- 5m bars drive StrategyPlugin signals only
- 1m bars drive every PaperBroker fill
- synthetic bid/ask fields are derived from the 1m mid OHLC because the local
  NAS100 history is not a full historical quote archive
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .causality import AUDIT
from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .run_ledger import begin_run, complete_run, fail_run
from .store import FlatFileStore
from .v2b_clean_break_pyramid_trail_sizing_v1 import FEE_PER_UNIT, VARIANTS
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, money, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider

REPO = Path(__file__).resolve().parents[1]
SOURCE_1M = REPO / "fx" / "nas100_1m.csv"
HUB = REPO / "live" / "state" / "nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill_validation"
STRATEGY_ID = "nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill"
VARIANT_NAME = "trail06_m4_e2_out_be"
INSTRUMENT = "NAS100"
POINT_VALUE = 1.0
TICK_SIZE = 0.1
NY = "America/New_York"


@dataclass(frozen=True)
class ValidationResult:
    sessions: int
    one_minute_bars: int
    signal_bars: int
    trades: int
    units: int
    net_usd: float
    closed_dd_usd: float
    intrabar_stress_dd_usd: float
    max_open_units: int
    win_rate: float
    profit_factor: float
    feature_snapshots: int
    causality_violations: int
    non_moc_fills_at_or_before_activation: int
    market_close_fills_before_activation: int
    entry_fills_at_or_before_activation: int
    replay_start: str
    replay_end: str

    @property
    def net_over_stress(self) -> float:
        return self.net_usd / abs(self.intrabar_stress_dd_usd) if self.intrabar_stress_dd_usd else 0.0


def load_nas100_1m(max_sessions: Optional[int] = None) -> pd.DataFrame:
    if not SOURCE_1M.exists():
        raise FileNotFoundError("Missing NAS100 1m source: %s" % SOURCE_1M)
    df = pd.read_csv(
        SOURCE_1M,
        usecols=["ts_event", "open", "high", "low", "close", "volume"],
    )
    ts_utc = pd.to_datetime(df["ts_event"], utc=True, errors="coerce")
    df = df[ts_utc.notna()].copy()
    df["ts"] = ts_utc[ts_utc.notna()].dt.tz_convert(NY)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df[(df["open"] > 0) & (df["high"] >= df[["open", "close"]].max(axis=1))]
    df = df[df["low"] <= df[["open", "close"]].min(axis=1)]
    df = df.sort_values("ts").reset_index(drop=True)
    df = df[df["ts"].dt.weekday < 5].copy()
    local_time = df["ts"].dt.time
    df = df[(local_time >= pd.Timestamp("09:30").time()) & (local_time < pd.Timestamp("16:00").time())].copy()
    df["session_day"] = df["ts"].dt.date.astype(str)
    df["bucket_5m"] = df["ts"].dt.floor("5min")
    if max_sessions is not None:
        keep = sorted(df["session_day"].unique())[: int(max_sessions)]
        df = df[df["session_day"].isin(keep)].copy()
    return df.reset_index(drop=True)


def quote_bar_from_row(row: Any, *, half_spread_ticks: float) -> Bar:
    half = float(half_spread_ticks) * TICK_SIZE
    return Bar(
        instrument=INSTRUMENT,
        timeframe="1m",
        ts=pd.Timestamp(row.ts).isoformat(),
        open=float(row.open),
        high=float(row.high),
        low=float(row.low),
        close=float(row.close),
        volume=float(row.volume or 0.0),
        complete=True,
        source=str(SOURCE_1M) + " synthetic_bid_ask_half_spread_ticks=%.2f" % half_spread_ticks,
        bid_open=float(row.open) - half,
        bid_high=float(row.high) - half,
        bid_low=float(row.low) - half,
        bid_close=float(row.close) - half,
        ask_open=float(row.open) + half,
        ask_high=float(row.high) + half,
        ask_low=float(row.low) + half,
        ask_close=float(row.close) + half,
    )


def signal_bar_from_bucket(chunk: pd.DataFrame) -> Bar:
    signal_ts = pd.Timestamp(chunk["ts"].iloc[-1])
    return Bar(
        instrument=INSTRUMENT,
        timeframe="5m",
        ts=signal_ts.isoformat(),
        open=float(chunk["open"].iloc[0]),
        high=float(chunk["high"].max()),
        low=float(chunk["low"].min()),
        close=float(chunk["close"].iloc[-1]),
        volume=float(chunk["volume"].sum()),
        complete=True,
        source=str(SOURCE_1M) + " resampled_5m_signal_only",
    )


def flush_market_close_fills(engine: Engine, bar: Bar) -> None:
    process_market_close_bar = getattr(engine.broker, "process_market_close_bar", None)
    if not callable(process_market_close_bar):
        return
    for _ in range(20):
        fills = process_market_close_bar(bar)
        if not fills:
            break
        engine.manager.on_fills(fills)


def _count_csv_rows(path: Path) -> int:
    if not path.exists() or path.stat().st_size == 0:
        return 0
    with path.open(encoding="utf-8", newline="") as fh:
        return max(0, sum(1 for _ in csv.DictReader(fh)))


def write_timing_audit(state_root: Path, output_path: Path) -> Dict[str, int]:
    orders_path = state_root / "orders.csv"
    fills_path = state_root / "fills.csv"
    if not orders_path.exists() or not fills_path.exists() or fills_path.stat().st_size == 0:
        output_path.write_text("fill_id,broker_order_id,reason,fill_ts,live_after_ts,order_type,at_or_before_activation,before_activation\n", encoding="utf-8")
        return {
            "non_moc_fills_at_or_before_activation": 0,
            "market_close_fills_before_activation": 0,
            "entry_fills_at_or_before_activation": 0,
        }
    orders = pd.read_csv(orders_path)
    fills = pd.read_csv(fills_path)
    if orders.empty or fills.empty:
        output_path.write_text("fill_id,broker_order_id,reason,fill_ts,live_after_ts,order_type,at_or_before_activation,before_activation\n", encoding="utf-8")
        return {
            "non_moc_fills_at_or_before_activation": 0,
            "market_close_fills_before_activation": 0,
            "entry_fills_at_or_before_activation": 0,
        }
    merged = fills.merge(
        orders[["broker_order_id", "order_type", "live_after_ts"]],
        on="broker_order_id",
        how="left",
    )
    merged["fill_ts_dt"] = pd.to_datetime(merged["ts"], utc=True, errors="coerce")
    merged["live_after_dt"] = pd.to_datetime(merged["live_after_ts"], utc=True, errors="coerce")
    has_activation = merged["live_after_dt"].notna() & merged["fill_ts_dt"].notna()
    merged["at_or_before_activation"] = has_activation & (merged["fill_ts_dt"] <= merged["live_after_dt"])
    merged["before_activation"] = has_activation & (merged["fill_ts_dt"] < merged["live_after_dt"])
    out = merged[
        [
            "fill_id",
            "broker_order_id",
            "reason",
            "ts",
            "live_after_ts",
            "order_type",
            "at_or_before_activation",
            "before_activation",
            "price",
            "mid_price",
            "bid_price",
            "ask_price",
            "spread",
        ]
    ].rename(columns={"ts": "fill_ts"})
    out.to_csv(output_path, index=False)
    non_moc_bad = int(
        merged[(merged["order_type"] != "market_close") & merged["at_or_before_activation"]].shape[0]
    )
    moc_before = int(
        merged[(merged["order_type"] == "market_close") & merged["before_activation"]].shape[0]
    )
    entry_bad = int(merged[(merged["reason"] == "entry") & merged["at_or_before_activation"]].shape[0])
    return {
        "non_moc_fills_at_or_before_activation": non_moc_bad,
        "market_close_fills_before_activation": moc_before,
        "entry_fills_at_or_before_activation": entry_bad,
    }


def run_validation(max_sessions: Optional[int], half_spread_ticks: float) -> ValidationResult:
    HUB.mkdir(parents=True, exist_ok=True)
    state_root = HUB / "states" / STRATEGY_ID
    if state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()

    variant = next(v for v in VARIANTS if v.name == VARIANT_NAME)
    config: Dict[str, Any] = dict(variant.config())
    config.update(
        {
            "market": "nas100",
            "record_levels": False,
            "tick_size": TICK_SIZE,
            "fill_to_signal_minutes": 5,
            "fill_signal_bucket_end": True,
            "broker_style_fill_source": "1m_proxy_synthetic_bid_ask",
            "synthetic_half_spread_ticks": float(half_spread_ticks),
        }
    )
    instance = StrategyInstance(
        strategy_id=STRATEGY_ID,
        strategy_type="v2b_clean_break",
        version="v1",
        instrument=INSTRUMENT,
        broker_instrument=INSTRUMENT,
        account_mode="paper",
        enabled=True,
        timeframes="5m",
        max_contracts=int(config.get("max_pyramid_qty") or 4),
        max_open_orders=24,
        config_json=json.dumps(config, sort_keys=True),
    )
    store.write_table("strategy_instances", [as_row(instance)])
    POINT_VALUES[INSTRUMENT] = POINT_VALUE
    DEFAULT_TICK_SIZE[INSTRUMENT] = TICK_SIZE
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        slippage_ticks=1.0,
        tick_size={INSTRUMENT: TICK_SIZE},
        verification_provider=QuietPaperVerificationProvider(),
        causality_mode=AUDIT,
    )

    bars_1m = load_nas100_1m(max_sessions=max_sessions)
    audit_bars: List[AuditBar] = []
    signal_delivery_rows: List[Dict[str, Any]] = []
    signal_bars = 0
    last_1m_bar: Optional[Bar] = None
    for session_day, day in bars_1m.groupby("session_day", sort=True):
        for bucket_ts, chunk in day.groupby("bucket_5m", sort=True):
            chunk = chunk.sort_values("ts")
            for row in chunk.itertuples(index=False):
                bar_1m = quote_bar_from_row(row, half_spread_ticks=half_spread_ticks)
                engine.process_bar(bar_1m)
                last_1m_bar = bar_1m
                audit_bars.append(AuditBar(bar_1m.ts, bar_1m.open, bar_1m.high, bar_1m.low, bar_1m.close))
            if last_1m_bar is None:
                continue
            bar_5m = signal_bar_from_bucket(chunk)
            engine.process_bar(bar_5m, broker_fills=False)
            flush_market_close_fills(engine, last_1m_bar)
            signal_bars += 1
            signal_delivery_rows.append(
                {
                    "session_day": session_day,
                    "signal_label_ts": pd.Timestamp(bucket_ts).isoformat(),
                    "signal_available_ts": bar_5m.ts,
                    "delivered_after_1m_ts": last_1m_bar.ts,
                    "one_minute_rows": int(len(chunk)),
                    "open": "%.4f" % bar_5m.open,
                    "high": "%.4f" % bar_5m.high,
                    "low": "%.4f" % bar_5m.low,
                    "close": "%.4f" % bar_5m.close,
                }
            )

    store.flush_tables()
    _write_csv(HUB / "signal_delivery_audit.csv", signal_delivery_rows)

    units = units_from_v2b_fills(state_root / "fills.csv", STRATEGY_ID)
    audit = fast_intraday_audit(
        strategy_id=STRATEGY_ID,
        state_root=state_root,
        bars=audit_bars,
        units=units,
        instrument=INSTRUMENT,
        fee_per_unit=FEE_PER_UNIT,
    )
    timing = write_timing_audit(state_root, HUB / "order_timing_audit.csv")
    feature_rows = _count_csv_rows(state_root / "feature_snapshots.csv")
    violation_rows = _count_csv_rows(state_root / "causality_violations.csv")
    replay_start = audit_bars[0].ts if audit_bars else ""
    replay_end = audit_bars[-1].ts if audit_bars else ""
    result = ValidationResult(
        sessions=int(bars_1m["session_day"].nunique()),
        one_minute_bars=len(audit_bars),
        signal_bars=signal_bars,
        trades=len({u.trade_id for u in units}),
        units=len(units),
        net_usd=float(audit["net_usd"]),
        closed_dd_usd=float(audit["closed_dd_usd"]),
        intrabar_stress_dd_usd=float(audit["intrabar_stress_dd_usd"]),
        max_open_units=int(audit["max_open_units"]),
        win_rate=float(audit["win_rate"]),
        profit_factor=float(audit["profit_factor"]),
        feature_snapshots=feature_rows,
        causality_violations=violation_rows,
        non_moc_fills_at_or_before_activation=int(timing["non_moc_fills_at_or_before_activation"]),
        market_close_fills_before_activation=int(timing["market_close_fills_before_activation"]),
        entry_fills_at_or_before_activation=int(timing["entry_fills_at_or_before_activation"]),
        replay_start=replay_start,
        replay_end=replay_end,
    )
    write_outputs(result, config, state_root)
    write_run_manifest(
        HUB,
        data_inputs=[SOURCE_1M],
        output_paths=[
            HUB / "SUMMARY.md",
            HUB / "summary.csv",
            HUB / "signal_delivery_audit.csv",
            HUB / "order_timing_audit.csv",
            state_root / "fills.csv",
            state_root / "orders.csv",
            state_root / "feature_snapshots.csv",
            state_root / "causality_violations.csv",
            state_root / "equity_curve.csv",
            state_root / "unit_trades.csv",
        ],
        strategy_config=config,
        broker_realism_config={
            "fill_tape": "1m",
            "signal_timeframe": "5m",
            "signal_broker_fills": False,
            "slippage_ticks": 1.0,
            "tick_size": TICK_SIZE,
            "point_value": POINT_VALUE,
            "fee_per_unit": FEE_PER_UNIT,
            "synthetic_half_spread_ticks": float(half_spread_ticks),
            "quote_source": "synthetic bid/ask from local NAS100 1m OHLC, not true historical quote ticks",
        },
        causality_mode=AUDIT,
        repo_root=REPO,
        extra={
            "study_id": HUB.name,
            "strategy_id": STRATEGY_ID,
            "frozen_variant": VARIANT_NAME,
            "validation_type": "finer_1m_fill_proxy_quote_replay",
            "max_sessions": max_sessions,
        },
    )
    return result


def write_outputs(result: ValidationResult, config: Dict[str, Any], state_root: Path) -> None:
    summary_rows = [
        {
            "instrument": INSTRUMENT,
            "strategy_id": STRATEGY_ID,
            "variant": VARIANT_NAME,
            "sessions": result.sessions,
            "trades": result.trades,
            "units": result.units,
            "net_usd": "%.2f" % result.net_usd,
            "closed_dd_usd": "%.2f" % result.closed_dd_usd,
            "intrabar_stress_dd_usd": "%.2f" % result.intrabar_stress_dd_usd,
            "max_open_units": result.max_open_units,
            "win_rate": "%.4f" % result.win_rate,
            "profit_factor": "%.6f" % result.profit_factor if math.isfinite(result.profit_factor) else "inf",
            "ns": "%.6f" % result.net_over_stress,
            "feature_snapshots": result.feature_snapshots,
            "causality_violations": result.causality_violations,
            "non_moc_fills_at_or_before_activation": result.non_moc_fills_at_or_before_activation,
            "market_close_fills_before_activation": result.market_close_fills_before_activation,
            "entry_fills_at_or_before_activation": result.entry_fills_at_or_before_activation,
            "replay_start": result.replay_start,
            "replay_end": result.replay_end,
        }
    ]
    _write_csv(HUB / "summary.csv", summary_rows)
    lines = [
        "# NAS100 Clean-Break Best-N/S 1m-Fill Validation",
        "",
        "STATUS: validation replay, not a new optimization sweep.",
        "",
        "## Frozen candidate",
        "",
        "- Candidate: `%s`." % VARIANT_NAME,
        "- Source family: clean-break pyramid trail sizing validation.",
        "- Signal bars: completed 5m candles, signal-only through `Engine.process_bar(..., broker_fills=False)`.",
        "- Signal timestamps: final 1m row in each 5m bucket, with the left-label retained in `signal_delivery_audit.csv`.",
        "- Fill bars: local NAS100 1m OHLC with synthetic bid/ask fields.",
        "- Quote caveat: this is finer broker-style proxy data, **not** true historical tick/bid-ask quote history.",
        "",
        "## Result",
        "",
        "| Sessions | Trades | Units | Net | Closed DD | Intrabar stress DD | Max units | Win% | PF | N/S |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        "| %d | %d | %d | $%s | $%s | $%s | %d | %.1f%% | %.2f | %.2f |"
        % (
            result.sessions,
            result.trades,
            result.units,
            money(result.net_usd),
            money(result.closed_dd_usd),
            money(result.intrabar_stress_dd_usd),
            result.max_open_units,
            result.win_rate,
            result.profit_factor,
            result.net_over_stress,
        ),
        "",
        "## Causality and timing",
        "",
        "| Check | Result |",
        "|---|---:|",
        "| Feature snapshots | %d |" % result.feature_snapshots,
        "| Causality violations | %d |" % result.causality_violations,
        "| Non-MOC fills at/before activation | %d |" % result.non_moc_fills_at_or_before_activation,
        "| MOC fills before activation | %d |" % result.market_close_fills_before_activation,
        "| Entry fills at/before activation | %d |" % result.entry_fills_at_or_before_activation,
        "| 1m bars replayed | %d |" % result.one_minute_bars,
        "| 5m signal bars delivered | %d |" % result.signal_bars,
        "",
        "## Interpretation",
        "",
        "This run removes the known high-timeframe fill hazard: the 5m candles never fill orders. "
        "They only generate strategy decisions after each bucket's 1m rows have already been processed, "
        "and fills are matched on the 1m broker-style proxy tape.",
        "",
        "The run is still not tick-proven. Synthetic bid/ask fields make fills more broker-like than "
        "mid-only OHLC, but they cannot prove sub-minute queue position or true historical spread.",
        "",
        "Artifacts:",
        "",
        "- `summary.csv`",
        "- `signal_delivery_audit.csv`",
        "- `order_timing_audit.csv`",
        "- `states/%s/feature_snapshots.csv`" % STRATEGY_ID,
        "- `states/%s/causality_violations.csv`" % STRATEGY_ID,
        "- `states/%s/equity_curve.csv`" % STRATEGY_ID,
        "- `run_manifest.json` / `run_manifest.sha256`",
        "",
        "Config:",
        "",
        "```json",
        json.dumps(config, indent=2, sort_keys=True),
        "```",
        "",
    ]
    (HUB / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def _write_csv(path: Path, rows: Iterable[Dict[str, Any]]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-sessions", type=int, default=None)
    ap.add_argument("--synthetic-half-spread-ticks", type=float, default=0.5)
    args = ap.parse_args()
    rid = begin_run(
        run_class="broker_like",
        variant_slug=STRATEGY_ID,
        instrument=INSTRUMENT,
        hub_path=str(HUB.relative_to(REPO)),
        engine="engine_paperbroker_5m_signal_1m_fill",
        dsr_trial_id="TRL-2026-00194",
        meta={
            "frozen_candidate": VARIANT_NAME,
            "validation": "1m fill proxy quote replay",
            "max_sessions": args.max_sessions,
            "synthetic_half_spread_ticks": args.synthetic_half_spread_ticks,
        },
        notes="Validation run for frozen NAS100 clean-break best-N/S candidate; no new parameter selection.",
    )
    try:
        result = run_validation(args.max_sessions, args.synthetic_half_spread_ticks)
        complete_run(
            rid,
            net_usd=result.net_usd,
            stress_dd_usd=result.intrabar_stress_dd_usd,
            close_mtm_dd_usd=result.closed_dd_usd,
            ns=result.net_over_stress,
            trades=result.trades,
            units=result.units,
            replay_start=result.replay_start,
            replay_end=result.replay_end,
            hub_path=str(HUB.relative_to(REPO)),
            equity_curve_path=HUB / "states" / STRATEGY_ID / "equity_curve.csv",
            meta={
                "frozen_candidate": VARIANT_NAME,
                "validation": "1m fill proxy quote replay",
                "feature_snapshots": result.feature_snapshots,
                "causality_violations": result.causality_violations,
                "non_moc_fills_at_or_before_activation": result.non_moc_fills_at_or_before_activation,
                "market_close_fills_before_activation": result.market_close_fills_before_activation,
                "entry_fills_at_or_before_activation": result.entry_fills_at_or_before_activation,
                "synthetic_half_spread_ticks": args.synthetic_half_spread_ticks,
            },
            notes="Completed NAS100 clean-break 5m signal / 1m fill validation.",
        )
        print((HUB / "SUMMARY.md").read_text(encoding="utf-8"))
    except Exception as exc:
        fail_run(rid, notes="%s\n%s" % (exc, traceback.format_exc()))
        raise


if __name__ == "__main__":
    main()
