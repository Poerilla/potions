from __future__ import annotations

import argparse
import csv
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd
import pytz

from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .reporting import generate_market_close_report
from .replay_audit import AuditResult, POINT_VALUES, audit_units, read_bars, units_from_live_fills
from .store import FlatFileStore


REPO = Path(__file__).resolve().parents[1]
NY = pytz.timezone("America/New_York")

DEFAULT_SLIPPAGE_TICKS = 1.0
DEFAULT_FEE_PER_UNIT = 1.50


@dataclass(frozen=True)
class MarketConfig:
    market: str
    instrument: str
    bars4h_path: Path
    daily_path: Path
    raw_1m_path: Path
    product: str


MARKETS: Dict[str, MarketConfig] = {
    "mnq": MarketConfig(
        "mnq",
        "MNQ",
        REPO / "mnq" / "data" / "mnq_front_month_4h_from_1m.csv",
        REPO / "mnq" / "mnq_daily.csv",
        REPO / "mnq" / "raw" / "extracted_new" / "glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst",
        "MNQ",
    ),
    "nq": MarketConfig(
        "nq",
        "NQ",
        REPO / "nq" / "data" / "nq_front_month_4h_from_1m.csv",
        REPO / "nq" / "nq_daily.csv",
        REPO / "nq" / "raw" / "glbx-mdp3-20100606-20260308.ohlcv-1m.dbn.zst",
        "NQ",
    ),
    "es": MarketConfig(
        "es",
        "ES",
        REPO / "es" / "data" / "es_front_month_4h_from_1m.csv",
        REPO / "es" / "es_daily.csv",
        REPO / "es" / "raw" / "glbx-mdp3-20100606-20260425.ohlcv-1m.dbn.zst",
        "ES",
    ),
    "mes": MarketConfig(
        "mes",
        "MES",
        REPO / "mes" / "data" / "mes_front_month_4h_from_1m.csv",
        REPO / "mes" / "mes_daily.csv",
        REPO / "mes" / "mes_1min_raw.csv",
        "MES",
    ),
    "ym": MarketConfig(
        "ym",
        "YM",
        REPO / "ym" / "data" / "ym_front_month_4h_from_1m.csv",
        REPO / "ym" / "ym_daily.csv",
        REPO / "ym" / "raw" / "glbx-mdp3-20100606-20260506.ohlcv-1m.dbn.zst",
        "YM",
    ),
    "mym": MarketConfig(
        "mym",
        "MYM",
        REPO / "mym" / "data" / "mym_front_month_4h_from_1m.csv",
        REPO / "mym" / "mym_daily.csv",
        REPO / "mym" / "raw" / "glbx-mdp3-20100606-20260308.ohlcv-1m (mym).dbn.zst",
        "MYM",
    ),
}


def run(output_root: Path, markets: Sequence[str], force: bool = True, rebuild_4h_cache: bool = False) -> List[AuditResult]:
    output_root.mkdir(parents=True, exist_ok=True)
    states_root = output_root / "states"
    audits_root = output_root / "audits"
    states_root.mkdir(parents=True, exist_ok=True)
    audits_root.mkdir(parents=True, exist_ok=True)
    results: List[AuditResult] = []

    for market_name in markets:
        market = MARKETS[market_name]
        cache = ensure_4h_cache(market, rebuild_4h_cache)
        if not cache.exists():
            print("Skipping %s, missing %s" % (market.instrument, cache), flush=True)
            continue
        bars = load_4h_bars(cache, market.instrument)
        if not bars:
            continue
        daily_close_ts = daily_close_bar_timestamps(bars)
        strategy_id = "%s_monthly_overlap_daily_st_retest5" % market.market
        state_root = states_root / strategy_id
        if force and state_root.exists():
            shutil.rmtree(state_root)
        store = FlatFileStore(state_root, defer_table_writes=True)
        store.ensure()
        config = {
            "daily_bars_path": str(market.daily_path),
            "daily_close_4h_ts": daily_close_ts,
            "max_attempts_per_cluster": 2,
            "max_concurrent_trades": 2,
            "close_stop_frac": 0.25,
            "retest_qty": 5,
            "record_levels": False,
        }
        instance = StrategyInstance(
            strategy_id=strategy_id,
            strategy_type="monthly_orb_overlap_st_retest",
            version="v1",
            instrument=market.instrument,
            broker_instrument=market.instrument,
            account_mode="paper",
            enabled=True,
            timeframes="4H",
            max_contracts=32,
            max_open_orders=128,
            config_json=json.dumps(config, sort_keys=True),
        )
        store.write_table("strategy_instances", [as_row(instance)])
        engine = Engine(
            store=store,
            persist_bars=True,
            persist_health=False,
            slippage_ticks=DEFAULT_SLIPPAGE_TICKS,
        )
        print("Replaying %s overlap ST-retest on %d 4h bars..." % (market.instrument, len(bars)), flush=True)
        engine.replay_bars(bars)
        store.flush_tables()
        generate_market_close_report(store, bars[-1].ts[:10])

        replay_bars = read_bars(state_root / "bars" / f"{market.instrument}_4H.csv", "ts")
        units = units_from_live_fills(
            state_root / "fills.csv",
            strategy_id,
            replay_bars[-1].ts,
            replay_bars[-1].close,
        )
        result = audit_units(
            name="%s Monthly ORB overlap daily-ST retest x5" % market.instrument,
            slug=strategy_id,
            source=state_root / "fills.csv",
            bar_source=state_root / "bars" / f"{market.instrument}_4H.csv",
            bars=replay_bars,
            units=units,
            instrument=market.instrument,
            notes=(
                "Broker-like 4h StrategyPlugin replay. Long-only overlap monthly ORB breakout, "
                "confirmed daily Supertrend filter, max two active primary packages, and one "
                "5-contract daily-ST retest limit add per runner. Orders activate only after "
                "the confirming 4h bar closes. "
                f"Realism: slippage={DEFAULT_SLIPPAGE_TICKS:g} tick(s), fee=${DEFAULT_FEE_PER_UNIT:.2f}/unit."
            ),
            output_root=audits_root,
            fee_per_unit=DEFAULT_FEE_PER_UNIT,
        )
        results.append(result)
        write_summary(output_root, results)
        print(
            "%s net=%s stress=%s ratio=%.2f"
            % (strategy_id, money(result.net_usd), money(result.intrabar_mtm_dd_usd), ratio(result)),
            flush=True,
        )

    write_summary(output_root, results)
    return results


def load_4h_bars(path: Path, instrument: str) -> List[Bar]:
    out: List[Bar] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ts = str(row.get("time") or row.get("ts") or row.get("date"))
            out.append(
                Bar(
                    instrument=instrument,
                    timeframe="4H",
                    ts=ts,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0.0),
                    complete=True,
                    source=str(path),
                )
            )
    out.sort(key=lambda bar: bar.ts)
    return out


def ensure_4h_cache(market: MarketConfig, rebuild: bool = False) -> Path:
    if market.bars4h_path.exists() and not rebuild:
        return market.bars4h_path
    if not market.raw_1m_path.exists():
        return market.bars4h_path
    print("Building %s 4h cache from %s" % (market.instrument, market.raw_1m_path), flush=True)
    bars = resample_4h(load_front_month_1m(market.raw_1m_path, market.product))
    market.bars4h_path.parent.mkdir(parents=True, exist_ok=True)
    bars.to_csv(market.bars4h_path, index=False)
    print("Wrote %s (%d rows)" % (market.bars4h_path, len(bars)), flush=True)
    return market.bars4h_path


def load_1m_source(path: Path) -> pd.DataFrame:
    if path.suffix == ".csv":
        df = pd.read_csv(
            path,
            usecols=["ts_event", "open", "high", "low", "close", "volume", "symbol"],
            parse_dates=["ts_event"],
        )
    else:
        import databento as db

        df = db.DBNStore.from_file(str(path)).to_df().reset_index()
    df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True).dt.tz_convert(NY)
    return df[["ts_event", "symbol", "open", "high", "low", "close", "volume"]]


def load_front_month_1m(path: Path, product: str) -> pd.DataFrame:
    df = load_1m_source(path)
    df = df[~df["symbol"].astype(str).str.contains("-", na=False)]
    df = df[df["symbol"].astype(str).str.startswith(product.upper())].copy()
    if df.empty:
        raise RuntimeError("No %s rows found in %s" % (product, path))
    df["date"] = df["ts_event"].dt.date
    front = (
        df.groupby(["date", "symbol"])["volume"]
        .sum()
        .groupby(level="date")
        .idxmax()
        .apply(lambda item: item[1])
        .to_dict()
    )
    df = df[df["symbol"].eq(df["date"].map(front))].copy()
    return df.set_index("ts_event").sort_index()


def resample_4h(df1: pd.DataFrame) -> pd.DataFrame:
    bars = (
        df1.resample("4h", label="left", closed="left", origin="start_day")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            symbol=("symbol", "last"),
        )
        .dropna(subset=["open"])
    )
    bars["time"] = bars.index
    bars["date"] = bars.index.date
    return bars.reset_index(drop=True)


def daily_close_bar_timestamps(bars: Sequence[Bar]) -> List[str]:
    last_by_day: Dict[str, str] = {}
    for bar in bars:
        last_by_day[bar.ts[:10]] = bar.ts
    return [last_by_day[day] for day in sorted(last_by_day)]


def write_summary(root: Path, results: Sequence[AuditResult]) -> None:
    rows = []
    for r in sorted(results, key=ratio, reverse=True):
        rows.append(
            {
                "candidate": r.name,
                "slug": r.slug,
                "instrument": r.instrument,
                "units": str(r.units),
                "trades": str(r.trades),
                "net_usd": "%.2f" % r.net_usd,
                "close_mtm_dd_usd": "%.2f" % r.close_mtm_dd_usd,
                "intrabar_mtm_dd_usd": "%.2f" % r.intrabar_mtm_dd_usd,
                "max_open_units": str(r.max_open_units),
                "net_over_stress_dd": "%.2f" % ratio(r),
            }
        )
    write_csv(root / "summary.csv", rows)
    lines = [
        "# Monthly ORB Overlap Daily-ST Retest x5 Broker-Like Replay",
        "",
        "This promotes the research `breakout_only_2active_daily_st_retest5` idea into a 4h `StrategyPlugin` replay.",
        "",
        "Important implementation hardening:",
        "",
        "- Primary entries are actual resting buy-stop orders at the combined overlap high.",
        "- Orders become active only after the 4h bar that created/updated the signal has closed.",
        "- Confirmed daily Supertrend is used as the long filter.",
        "- The retest add is an actual 5-contract buy-limit at the confirmed daily Supertrend stop, not a same-bar hindsight fill.",
        "- Retest add exits at the parent runner target or on a 4h close below the current confirmed daily Supertrend stop.",
        "- Daily close invalidation closes primary and retest units when price closes 25% back into the combined range.",
        "",
        "| Rank | Candidate | Instrument | Units | Trades | Net | Close MTM DD | Intrabar Stress DD | Max Open Units | Net / Stress DD |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for idx, row in enumerate(rows, 1):
        lines.append(
            "| %d | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                idx,
                row["candidate"],
                row["instrument"],
                row["units"],
                row["trades"],
                money(float(row["net_usd"])),
                money(float(row["close_mtm_dd_usd"])),
                money(float(row["intrabar_mtm_dd_usd"])),
                row["max_open_units"],
                row["net_over_stress_dd"],
            )
        )
    lines.extend(
        [
            "",
            "Research reference for MNQ close-fill branch was about `$87,586 / -$18,175` pess. intrabar stress. "
            "Expect the broker-like replay to be stricter because retest limits must be live before the fill bar.",
            "",
        ]
    )
    (root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def write_csv(path: Path, rows: Sequence[Dict[str, str]]) -> None:
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


def ratio(result: AuditResult) -> float:
    return result.net_usd / abs(result.intrabar_mtm_dd_usd) if result.intrabar_mtm_dd_usd else 0.0


def money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return "%s$%s" % (sign, f"{abs(value):,.2f}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run broker-like monthly overlap daily-ST retest x5 replay.")
    parser.add_argument("--output-root", type=Path, default=REPO / "live" / "state" / "monthly_overlap_st_retest_broker_like")
    parser.add_argument("--markets", default="mnq,nq", help="Comma-separated markets: mnq,nq,es,mes,ym,mym")
    parser.add_argument("--no-force", action="store_true")
    parser.add_argument("--rebuild-4h-cache", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    markets = [part.strip().lower() for part in args.markets.split(",") if part.strip()]
    unknown = [market for market in markets if market not in MARKETS]
    if unknown:
        raise SystemExit("Unknown markets: %s" % ", ".join(unknown))
    run(args.output_root, markets, force=not args.no_force, rebuild_4h_cache=args.rebuild_4h_cache)
    print("Wrote %s" % args.output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
