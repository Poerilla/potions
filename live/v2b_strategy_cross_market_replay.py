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
from typing import Dict, Iterable, List, Optional, Sequence

import pandas as pd

from .bars import rth_bars
from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .replay_audit import POINT_VALUES, Unit
from .replay_realism import hardened_replay_engine_kwargs
from .store import FlatFileStore
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, money, units_from_v2b_fills


REPO = Path(__file__).resolve().parents[1]
MNQ_ROOT = REPO / "mnq"
CASE = MNQ_ROOT / "case_studies" / "midnight_open_hourly_charts"
SCRIPTS = REPO / "scripts"
DEFAULT_SLIPPAGE_TICKS = 1.0

sys.path[:0] = [str(MNQ_ROOT), str(SCRIPTS), str(CASE)]

import build_midnight_open_hourly_charts as mdata  # noqa: E402


@dataclass(frozen=True)
class MarketConfig:
    market: str
    instrument: str
    daily_path: Path
    dbn_path: Path
    start: Optional[date] = None
    fee_per_unit: float = 1.50


MARKETS: Dict[str, MarketConfig] = {
    "mnq": MarketConfig(
        "mnq",
        "MNQ",
        REPO / "mnq" / "mnq_daily.csv",
        REPO / "mnq" / "raw" / "glbx-mdp3-20210304-20260303.ohlcv-1m.csv",
        date(2021, 3, 4),
    ),
    "nq": MarketConfig(
        "nq",
        "NQ",
        REPO / "nq" / "nq_daily.csv",
        REPO / "nq" / "raw" / "glbx-mdp3-20100606-20260616.ohlcv-1m.dbn.zst",
    ),
    "ym": MarketConfig(
        "ym",
        "YM",
        REPO / "ym" / "ym_daily.csv",
        REPO / "ym" / "raw" / "glbx-mdp3-20100606-20260506.ohlcv-1m.dbn.zst",
    ),
    "mym": MarketConfig(
        "mym",
        "MYM",
        REPO / "mym" / "mym_daily.csv",
        REPO / "mym" / "raw" / "glbx-mdp3-20100606-20260308.ohlcv-1m (mym).dbn.zst",
    ),
    "es": MarketConfig(
        "es",
        "ES",
        REPO / "es" / "es_daily.csv",
        REPO / "es" / "raw" / "glbx-mdp3-20100606-20260425.ohlcv-1m.dbn.zst",
    ),
    "mes": MarketConfig(
        "mes",
        "MES",
        REPO / "mes" / "mes_daily.csv",
        REPO / "mes" / "mes_1min_raw.csv",
    ),
}


@dataclass(frozen=True)
class ReplayResult:
    market: str
    instrument: str
    strategy_id: str
    state_root: Path
    regime_days: int
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


def run_markets(
    *,
    output_root: Path,
    market_names: Sequence[str],
    max_days: Optional[int] = None,
    start: Optional[date] = None,
) -> List[ReplayResult]:
    output_root.mkdir(parents=True, exist_ok=True)
    results: List[ReplayResult] = []
    for market_name in market_names:
        cfg = MARKETS[market_name.lower()]
        results.append(run_market(output_root=output_root, cfg=cfg, max_days=max_days, start=start))
        write_summary(output_root, results)
    return results


def run_market(
    *,
    output_root: Path,
    cfg: MarketConfig,
    max_days: Optional[int] = None,
    start: Optional[date] = None,
) -> ReplayResult:
    if not cfg.dbn_path.exists():
        raise FileNotFoundError(cfg.dbn_path)
    if not cfg.daily_path.exists():
        raise FileNotFoundError(cfg.daily_path)

    print("Loading %s 1m DBN for V2B OCO replay..." % cfg.instrument, flush=True)
    gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    regime_dates = _regime_dates(cfg, gby, start=start)
    if max_days is not None:
        regime_dates = regime_dates[:max_days]
    print("  %s regime sessions: %d" % (cfg.instrument, len(regime_dates)), flush=True)

    strategy_id = "%s_v2b_scaleout_oco_then_reverse" % cfg.market
    state_root = output_root / "states" / strategy_id
    if state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type="v2b_scaleout",
        version="v1",
        instrument=cfg.instrument,
        broker_instrument=cfg.instrument,
        account_mode="paper",
        enabled=True,
        timeframes="1m",
        max_contracts=2,
        max_open_orders=24,
        config_json=json.dumps(
            {
                "market": cfg.market,
                "mode": "oco_then_reverse",
                "entry_qty": 2,
                "tick_size": 0.25,
                "use_regime_filter": True,
                "start": start.isoformat() if start else (cfg.start.isoformat() if cfg.start else ""),
                "regime_dates": [d.isoformat() for d in regime_dates],
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
    for idx, day in enumerate(regime_dates, start=1):
        df = rth_bars(gby.get(day), day, dense=True)
        if df.empty:
            continue
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
            engine.process_bar(bar)
            audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
        if idx % 500 == 0:
            print("  %s: %d/%d sessions" % (cfg.instrument, idx, len(regime_dates)), flush=True)

    store.flush_tables()
    units = units_from_v2b_fills(state_root / "fills.csv", strategy_id)
    audit = fast_intraday_audit(
        strategy_id=strategy_id,
        state_root=state_root,
        bars=audit_bars,
        units=units,
        instrument=cfg.instrument,
        fee_per_unit=cfg.fee_per_unit,
    )
    return ReplayResult(
        market=cfg.market,
        instrument=cfg.instrument,
        strategy_id=strategy_id,
        state_root=state_root,
        regime_days=len(regime_dates),
        units=len(units),
        trades=len({u.trade_id for u in units}),
        net_usd=audit["net_usd"],
        closed_dd_usd=audit["closed_dd_usd"],
        intrabar_stress_dd_usd=audit["intrabar_stress_dd_usd"],
        max_open_units=audit["max_open_units"],
        win_rate=audit["win_rate"],
        profit_factor=audit["profit_factor"],
    )


def _regime_dates(cfg: MarketConfig, gby: Dict[date, pd.DataFrame], start: Optional[date] = None) -> List[date]:
    daily = pd.read_csv(cfg.daily_path, parse_dates=["date"]).sort_values("date")
    daily["ma50"] = pd.to_numeric(daily["close"], errors="coerce").rolling(50).mean()
    daily["ma150"] = pd.to_numeric(daily["close"], errors="coerce").rolling(150).mean()
    daily["eligible"] = (daily["ma50"] > daily["ma150"]).shift(1).fillna(False)
    eligible = {pd.Timestamp(row["date"]).date() for _, row in daily[daily["eligible"]].iterrows()}
    out = [day for day in sorted(gby) if day in eligible]
    effective_start = start if start is not None else cfg.start
    if effective_start is not None:
        out = [day for day in out if day >= effective_start]
    return out


def load_1m_by_ny_date_any(path: Path, market: str) -> Dict[date, pd.DataFrame]:
    if path.suffix.lower() != ".csv":
        return mdata.load_1m_by_ny_date(path, market)
    inst = market.lower()
    print("Loading CSV %s (%s) ..." % (path, inst.upper()), flush=True)
    df = pd.read_csv(path, parse_dates=["ts_event"])
    df = df[~df["symbol"].astype(str).str.contains("-", na=False)]
    df = df[mdata._symbol_mask(df["symbol"].astype(str), inst)].copy()
    if df.empty:
        return {}
    if df["ts_event"].dt.tz is None:
        df["ts_event"] = df["ts_event"].dt.tz_localize("UTC")
    df["ts_event"] = df["ts_event"].dt.tz_convert(mdata.NY)
    df["d"] = df["ts_event"].dt.date
    fm = (
        df.groupby(["d", "symbol"])["volume"]
        .sum()
        .groupby(level="d")
        .idxmax()
        .apply(lambda x: x[1])
        .to_dict()
    )
    df = df[df.apply(lambda row: row["symbol"] == fm.get(row["d"]), axis=1)]
    df = df.set_index("ts_event").sort_index()
    gby = {d: g.drop(columns=["d"], errors="ignore") for d, g in df.groupby(df.index.date)}
    print("  %s NY dates with bars" % f"{len(gby):,}", flush=True)
    return gby


def _rth_bars(df: Optional[pd.DataFrame], session_day: date) -> pd.DataFrame:
    """Backward-compatible alias; prefer :func:`potions.live.bars.rth_bars`."""
    return rth_bars(df, session_day, dense=True)


def write_summary(output_root: Path, results: Sequence[ReplayResult]) -> None:
    rows = []
    for r in sorted(results, key=lambda item: item.net_over_stress, reverse=True):
        rows.append(
            {
                "market": r.market,
                "instrument": r.instrument,
                "strategy_id": r.strategy_id,
                "state_root": str(r.state_root),
                "regime_days": str(r.regime_days),
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
        )
    _write_csv(output_root / "v2b_oco_cross_market_summary.csv", rows)

    lines = [
        "# V2B OCO Then Reverse Cross-Market StrategyPlugin Replay",
        "",
        "Each row uses the same intraday `v2b_scaleout` StrategyPlugin path: prior-day MA50 > MA150 on that market's own daily close, 09:30-09:45 OR, OCO breakout stops, 2 contracts, TP1 plus runner to TP2, and same-bar pessimism from the PaperBroker/order ordering.",
        "",
        "| Rank | Market | Instrument | Regime Days | Units | Trades | Net | Closed DD | Intrabar Stress DD | Max Units | Net / Stress | Win % | PF |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for i, r in enumerate(sorted(results, key=lambda item: item.net_over_stress, reverse=True), start=1):
        pf = "%.2f" % r.profit_factor if math.isfinite(r.profit_factor) else "inf"
        lines.append(
            "| %d | %s | %s | %d | %d | %d | $%s | $%s | $%s | %d | %.2f | %.1f%% | %s |"
            % (
                i,
                r.market.upper(),
                r.instrument,
                r.regime_days,
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
            "## Read",
            "",
            "- This is the live-orderable OCO version, not the long-priority scanner.",
            "- Commission is modeled as `$1.50` per closed unit across markets for parity with the MNQ hardening pass.",
            "- Markets have different available history windows because their local DBN extracts differ.",
            "",
        ]
    )
    (output_root / "V2B_OCO_CROSS_MARKET_REPLAY.md").write_text("\n".join(lines), encoding="utf-8")


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
    parser = argparse.ArgumentParser(description="Run v2b OCO-then-reverse StrategyPlugin across markets.")
    parser.add_argument("--output-root", type=Path, default=REPO / "live" / "state" / "v2b_strategy_plugin_cross_market")
    parser.add_argument("--market", action="append", choices=sorted(MARKETS), help="Market to replay; repeatable. Defaults to all.")
    parser.add_argument("--max-days", type=int, default=None, help="Optional smoke-test cap per market.")
    parser.add_argument("--start", type=str, default=None, help="Optional common start date, YYYY-MM-DD, for apples-to-apples rankings.")
    args = parser.parse_args()
    markets = args.market or ["mnq", "nq", "ym", "mym", "es", "mes"]
    start = date.fromisoformat(args.start) if args.start else None
    run_markets(output_root=args.output_root, market_names=markets, max_days=args.max_days, start=start)
    print("Wrote %s" % (args.output_root / "V2B_OCO_CROSS_MARKET_REPLAY.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
