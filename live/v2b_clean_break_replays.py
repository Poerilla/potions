from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import pandas as pd

from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .replay_audit import POINT_VALUES
from .store import FlatFileStore
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, money, units_from_v2b_fills


REPO = Path(__file__).resolve().parents[1]
FEE_PER_UNIT = 1.50
DEFAULT_SLIPPAGE_TICKS = 1.0


@dataclass(frozen=True)
class MarketConfig:
    market: str
    instrument: str
    bars_path: Path


@dataclass(frozen=True)
class VariantConfig:
    name: str
    label: str
    config: Dict[str, object]


MARKETS: Dict[str, MarketConfig] = {
    "mnq": MarketConfig("mnq", "MNQ", REPO / "mnq" / "mnq_5min_rth.csv"),
    "nq": MarketConfig("nq", "NQ", REPO / "nq" / "nq_5min_rth.csv"),
    "mym": MarketConfig("mym", "MYM", REPO / "mym" / "mym_5min_rth.csv"),
    "mes": MarketConfig("mes", "MES", REPO / "mes" / "mes_5min_rth.csv"),
}


VARIANTS: Dict[str, VariantConfig] = {
    "bullish_2r_rl_stop": VariantConfig(
        name="bullish_2r_rl_stop",
        label="Bullish clean break, 2R target, RL stop",
        config={
            "variant": "bullish_2r_rl_stop",
            "entry_qty": 1,
            "required_break_num": 0,
            "stop_mode": "opposite",
            "size_model": "single_2r",
            "entry_offset_ticks": 2,
        },
    ),
    "fourth_rl_2r": VariantConfig(
        name="fourth_rl_2r",
        label="09:45 clean break, 2R target, RL stop baseline",
        config={
            "variant": "fourth_rl_2r",
            "entry_qty": 1,
            "required_break_num": 1,
            "stop_mode": "opposite",
            "size_model": "single_2r",
            "entry_offset_ticks": 2,
        },
    ),
    "fourth_boundary_2r": VariantConfig(
        name="fourth_boundary_2r",
        label="09:45 clean break, 2R target, boundary stop",
        config={
            "variant": "fourth_boundary_2r",
            "entry_qty": 1,
            "required_break_num": 1,
            "stop_mode": "boundary",
            "size_model": "single_2r",
            "entry_offset_ticks": 2,
        },
    ),
    "fourth_ladder3_runner": VariantConfig(
        name="fourth_ladder3_runner",
        label="09:45 clean break, 3-lot ladder runner",
        config={
            "variant": "fourth_ladder3_runner",
            "entry_qty": 3,
            "required_break_num": 1,
            "stop_mode": "boundary",
            "size_model": "ladder3_runner",
            "entry_offset_ticks": 2,
        },
    ),
}


@dataclass(frozen=True)
class ReplayResult:
    market: str
    instrument: str
    variant: str
    label: str
    strategy_id: str
    state_root: Path
    sessions: int
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


def run(
    *,
    output_root: Path,
    market_names: Sequence[str],
    variant_names: Sequence[str],
    max_sessions: Optional[int] = None,
) -> List[ReplayResult]:
    output_root.mkdir(parents=True, exist_ok=True)
    results: List[ReplayResult] = []
    for market_name in market_names:
        market = MARKETS[market_name]
        bars = load_5m_bars(market.bars_path, market.instrument)
        if max_sessions is not None:
            keep = sorted(bars["session_day"].unique())[:max_sessions]
            bars = bars[bars["session_day"].isin(keep)].copy()
        print("%s sessions: %d" % (market.instrument, bars["session_day"].nunique()), flush=True)
        for variant_name in variant_names:
            result = run_one(output_root=output_root, market=market, variant=VARIANTS[variant_name], bars=bars)
            results.append(result)
            write_summary(output_root, results)
    return results


def run_one(*, output_root: Path, market: MarketConfig, variant: VariantConfig, bars: pd.DataFrame) -> ReplayResult:
    strategy_id = "%s_v2b_clean_break_%s" % (market.market, variant.name)
    state_root = output_root / "states" / strategy_id
    if state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()

    config = dict(variant.config)
    config.update({"market": market.market, "record_levels": False})
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type="v2b_clean_break",
        version="v1",
        instrument=market.instrument,
        broker_instrument=market.instrument,
        account_mode="paper",
        enabled=True,
        timeframes="5m",
        max_contracts=int(config.get("entry_qty", 1)),
        max_open_orders=16,
        config_json=json.dumps(config, sort_keys=True),
    )
    store.write_table("strategy_instances", [as_row(instance)])
    engine = Engine(store=store, persist_bars=False, persist_health=False, slippage_ticks=DEFAULT_SLIPPAGE_TICKS)

    audit_bars: List[AuditBar] = []
    print("  Replaying %s / %s..." % (market.instrument, variant.name), flush=True)
    sessions = 0
    for session_day, session_bars in bars.groupby("session_day", sort=True):
        sessions += 1
        for _, row in session_bars.iterrows():
            ts_s = pd.Timestamp(row["ts"]).isoformat()
            bar = Bar(
                instrument=market.instrument,
                timeframe="5m",
                ts=ts_s,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(market.bars_path),
            )
            engine.process_bar(bar)
            audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
        if sessions % 500 == 0:
            print("    %s / %s: %d sessions" % (market.instrument, variant.name, sessions), flush=True)

    store.flush_tables()
    units = units_from_v2b_fills(state_root / "fills.csv", strategy_id)
    audit = fast_intraday_audit(
        strategy_id=strategy_id,
        state_root=state_root,
        bars=audit_bars,
        units=units,
        instrument=market.instrument,
        fee_per_unit=FEE_PER_UNIT,
    )
    return ReplayResult(
        market=market.market,
        instrument=market.instrument,
        variant=variant.name,
        label=variant.label,
        strategy_id=strategy_id,
        state_root=state_root,
        sessions=sessions,
        units=len(units),
        trades=len({u.trade_id for u in units}),
        net_usd=audit["net_usd"],
        closed_dd_usd=audit["closed_dd_usd"],
        intrabar_stress_dd_usd=audit["intrabar_stress_dd_usd"],
        max_open_units=audit["max_open_units"],
        win_rate=audit["win_rate"],
        profit_factor=audit["profit_factor"],
    )


def load_5m_bars(path: Path, instrument: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["ts_event"], utc=True).dt.tz_convert("America/New_York")
    df["time"] = df["ts"].dt.strftime("%H:%M")
    df = df[(df["time"] >= "09:30") & (df["time"] < "16:00")].copy()
    df["session_day"] = df["ts"].dt.date.astype(str)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"]).sort_values("ts").reset_index(drop=True)
    if instrument in POINT_VALUES:
        return df
    raise KeyError("Unknown point value for %s" % instrument)


def write_summary(output_root: Path, results: Sequence[ReplayResult]) -> None:
    rows = [
        {
            "market": r.market,
            "instrument": r.instrument,
            "variant": r.variant,
            "label": r.label,
            "strategy_id": r.strategy_id,
            "state_root": str(r.state_root),
            "sessions": str(r.sessions),
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
    _write_csv(output_root / "v2b_clean_break_broker_like_summary.csv", rows)

    lines = [
        "# V2B Clean-Break Broker-Like Replays",
        "",
        "These rows harden the clean-break research scripts into `StrategyPlugin` replays through `Engine + PaperBroker` using completed 5-minute RTH bars. Entry stops can fill during the breakout candle, but the clean-close requirement is evaluated only after that 5-minute candle closes. Protective exits become active from the next 5-minute bar.",
        "",
        "Fees: `$1.50` per closed unit. Entry offset: `OR high + 2 ticks`, matching the old `one tick + one slippage tick` research scripts.",
        "",
        "| Rank | Market | Variant | Sessions | Trades | Units | Net | Closed DD | Intrabar Stress DD | Max Units | Net / Stress | Win % | PF |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for idx, r in enumerate(sorted(results, key=lambda item: item.net_over_stress, reverse=True), start=1):
        pf = "%.2f" % r.profit_factor if math.isfinite(r.profit_factor) else "inf"
        lines.append(
            "| %d | %s | %s | %d | %d | %d | $%s | $%s | $%s | %d | %.2f | %.1f%% | %s |"
            % (
                idx,
                r.instrument,
                r.label,
                r.sessions,
                r.trades,
                r.units,
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
            "## Realism Notes",
            "",
            "- The old clean-break scripts could credit some same-breakout-candle target hits after the entry. This broker-like replay does not: exits are only submitted after the candle closes cleanly.",
            "- If the breakout candle also sweeps the opposite side of the range, the plugin flattens at that candle close as an ambiguous break instead of accepting a clean long.",
            "- This is still 5-minute-bar realism, not tick replay. Intrabar stress uses each 5-minute bar's adverse extreme.",
            "- `fourth_rl_2r` is included because it appears as the historical baseline comparison for the 09:45 study, even though it did not have a standalone plugin before this pass.",
            "",
        ]
    )
    (output_root / "V2B_CLEAN_BREAK_BROKER_LIKE.md").write_text("\n".join(lines), encoding="utf-8")


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay v2b clean-break variants through Engine + PaperBroker.")
    parser.add_argument("--output-root", type=Path, default=REPO / "live" / "state" / "v2b_clean_break_broker_like")
    parser.add_argument("--market", action="append", choices=sorted(MARKETS), help="Market to replay; repeatable.")
    parser.add_argument("--variant", action="append", choices=sorted(VARIANTS), help="Variant to replay; repeatable.")
    parser.add_argument("--max-sessions", type=int, default=None, help="Optional smoke-test cap per market.")
    args = parser.parse_args()
    market_names = args.market or ["mnq", "nq"]
    variant_names = args.variant or list(VARIANTS)
    run(output_root=args.output_root, market_names=market_names, variant_names=variant_names, max_sessions=args.max_sessions)
    print("Wrote %s" % (args.output_root / "V2B_CLEAN_BREAK_BROKER_LIKE.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
