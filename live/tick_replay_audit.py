from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any


NY = "America/New_York"


@dataclass(frozen=True)
class SyntheticTickPath:
    prices: List[float]
    labels: List[str]


@dataclass(frozen=True)
class TickReplayVerdict:
    campaign_id: str
    side: str
    entry_ts: str
    bar_open: float
    bar_high: float
    bar_low: float
    bar_close: float
    stop_price: Optional[float]
    target_price: Optional[float]
    bar_replay_outcome: str
    synthetic_path_outcome: str
    consistent: bool
    tick_data_status: str
    notes: str


def adverse_synthetic_path(side: str, o: float, h: float, l: float, c: float) -> SyntheticTickPath:
    side_l = side.lower()
    if side_l in {"long", "buy"}:
        return SyntheticTickPath([o, l, h, c], ["open", "low", "high", "close"])
    return SyntheticTickPath([o, h, l, c], ["open", "high", "low", "close"])


def bracket_outcome_on_path(
    path: SyntheticTickPath,
    *,
    side: str,
    stop_price: Optional[float],
    target_price: Optional[float],
) -> str:
    side_l = side.lower()
    long_side = side_l in {"long", "buy"}
    for price in path.prices:
        if long_side:
            if stop_price is not None and price <= stop_price:
                return "stop"
            if target_price is not None and price >= target_price:
                return "target"
        else:
            if stop_price is not None and price >= stop_price:
                return "stop"
            if target_price is not None and price <= target_price:
                return "target"
    return "none"


def bar_replay_outcome(
    *,
    side: str,
    stop_price: Optional[float],
    target_price: Optional[float],
    o: float,
    h: float,
    l: float,
) -> str:
    side_l = side.lower()
    long_side = side_l in {"long", "buy"}
    stop_hit = False
    target_hit = False
    if long_side:
        if stop_price is not None and l <= stop_price:
            stop_hit = True
        if target_price is not None and h >= target_price:
            target_hit = True
    else:
        if stop_price is not None and h >= stop_price:
            stop_hit = True
        if target_price is not None and l <= target_price:
            target_hit = True
    if stop_hit and target_hit:
        return "stop"
    if stop_hit:
        return "stop"
    if target_hit:
        return "target"
    return "none"


def load_entry_bar(
    bars_by_day: Dict[date, pd.DataFrame],
    entry_ts: str,
) -> Optional[pd.Series]:
    ts = pd.Timestamp(entry_ts)
    if ts.tzinfo is None:
        ts = ts.tz_localize(NY)
    else:
        ts = ts.tz_convert(NY)
    day = bars_by_day.get(ts.date())
    if day is None or day.empty:
        return None
    if ts not in day.index:
        idx = day.index.get_indexer([ts], method="nearest")
        if len(idx) == 0 or idx[0] < 0:
            return None
        ts = day.index[int(idx[0])]
    return day.loc[ts]


def audit_manifest_row(
    row: pd.Series,
    *,
    side: str,
    bars_by_day: Dict[date, pd.DataFrame],
    entry_ts: str,
    campaign_id: str,
    dbn_path: Path,
    stop_points: float = 25.0,
    target_points: float = 75.0,
) -> TickReplayVerdict:
    bar = load_entry_bar(bars_by_day, entry_ts)
    if bar is None:
        status = "entry_bar_not_found" if bars_by_day else "dbn_file_not_available"
        notes = (
            "Could not locate 1m entry bar"
            if bars_by_day
            else "DBN file missing: %s" % dbn_path
        )
        return TickReplayVerdict(
            campaign_id=campaign_id,
            side=side,
            entry_ts=entry_ts,
            bar_open=0.0,
            bar_high=0.0,
            bar_low=0.0,
            bar_close=0.0,
            stop_price=None,
            target_price=None,
            bar_replay_outcome="unknown",
            synthetic_path_outcome="unknown",
            consistent=True,
            tick_data_status=status,
            notes=notes,
        )
    o = float(bar["open"])
    h = float(bar["high"])
    l = float(bar["low"])
    c = float(bar["close"])
    long_side = side.lower() in {"long", "buy"}
    if long_side:
        stop_price = o - stop_points
        target_price = o + target_points
    else:
        stop_price = o + stop_points
        target_price = o - target_points
    path = adverse_synthetic_path(side, o, h, l, c)
    synthetic = bracket_outcome_on_path(path, side=side, stop_price=stop_price, target_price=target_price)
    bar_outcome = bar_replay_outcome(side=side, stop_price=stop_price, target_price=target_price, o=o, h=h, l=l)
    consistent = synthetic == bar_outcome or bar_outcome == "none" or synthetic == "none"
    if consistent:
        status = "synthetic_path_consistent_with_1m_pessimism"
        notes = "Adverse OHLC path matches stop-first 1m bar replay"
    else:
        status = "synthetic_path_conflict"
        notes = "1m pessimistic model may understate loss vs adverse path"
    return TickReplayVerdict(
        campaign_id=campaign_id,
        side=side,
        entry_ts=entry_ts,
        bar_open=o,
        bar_high=h,
        bar_low=l,
        bar_close=c,
        stop_price=stop_price,
        target_price=target_price,
        bar_replay_outcome=bar_outcome,
        synthetic_path_outcome=synthetic,
        consistent=consistent,
        tick_data_status=status,
        notes=notes,
    )


def audit_manifest(
    manifest_path: Path,
    *,
    market: str,
    dbn_path: Path,
    limit: Optional[int] = None,
) -> pd.DataFrame:
    manifest = pd.read_csv(manifest_path)
    bars_by_day: Dict[date, pd.DataFrame] = {}
    if dbn_path.exists():
        bars_by_day = load_1m_by_ny_date_any(dbn_path.resolve(), market)
    rows = []
    for _, row in manifest.head(limit or len(manifest)).iterrows():
        verdict = audit_manifest_row(
            row,
            side=str(row.get("side", "long")),
            bars_by_day=bars_by_day,
            entry_ts=str(row.get("entry_ts", "")),
            campaign_id=str(row.get("campaign_id", "")),
            dbn_path=dbn_path,
        )
        rows.append(
            {
                "campaign_id": verdict.campaign_id,
                "entry_ts": verdict.entry_ts,
                "side": verdict.side,
                "bar_replay_outcome": verdict.bar_replay_outcome,
                "synthetic_path_outcome": verdict.synthetic_path_outcome,
                "consistent": verdict.consistent,
                "tick_data_status": verdict.tick_data_status,
                "notes": verdict.notes,
            }
        )
    return pd.DataFrame(rows)


def write_tick_audit_report(
    output_dir: Path,
    market: str,
    manifest_path: Path,
    audit_df: pd.DataFrame,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    audit_df.to_csv(output_dir / "tick_replay_audit.csv", index=False)
    conflicts = int((~audit_df["consistent"].astype(bool)).sum()) if not audit_df.empty else 0
    lines = [
        "# Tick Replay Audit (%s)" % market.upper(),
        "",
        "Manifest: `%s`" % manifest_path,
        "",
        "| Rows | Conflicts |",
        "|---:|---:|",
        "| %d | %d |" % (len(audit_df), conflicts),
        "",
        "Synthetic adverse path uses open→low→high for longs and open→high→low for shorts.",
        "When trades DBN is unavailable, this is a conservative stand-in for tick reconstruction.",
        "",
    ]
    (output_dir / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Audit tick replay manifest rows against adverse synthetic paths")
    parser.add_argument("--market", required=True, choices=sorted(MARKETS.keys()))
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)
    cfg = MARKETS[args.market.lower()]
    audit_df = audit_manifest(
        Path(args.manifest),
        market=args.market.lower(),
        dbn_path=cfg.dbn_path,
        limit=args.limit or None,
    )
    out = Path(args.output_dir)
    write_tick_audit_report(out, args.market.lower(), Path(args.manifest), audit_df)
    updated = pd.read_csv(args.manifest)
    status_map = dict(zip(audit_df["campaign_id"], audit_df["tick_data_status"]))
    updated["tick_data_status"] = updated["campaign_id"].map(status_map).fillna(updated["tick_data_status"])
    updated.to_csv(out / "tick_replay_manifest_updated.csv", index=False)
    print("Wrote %s (%d rows, %d conflicts)" % (out, len(audit_df), int((~audit_df['consistent']).sum())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
