from __future__ import annotations

import argparse
import csv
from datetime import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import pytz

from .drawdown_distribution import build_report as build_drawdown_report
from .replay_audit import Bar, Unit, audit_units


NY_TZ = pytz.timezone("America/New_York")
RTH_START = time(9, 30)
RTH_END = time(16, 0)
RANGE_END = time(9, 45)
EOD_CUTOFF = time(15, 55)
TICK = 0.25
FEE_RT = 1.50

MNQ_1M_DBN = Path("potions/mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst")
MNQ_V2D_CHILD = Path("potions/mnq/v2d/mnq_orb_results_adaptive_50_150_child_3max.csv")


def load_mnq_1m(path: Path) -> pd.DataFrame:
    import databento as db

    store = db.DBNStore.from_file(str(path))
    df = store.to_df().reset_index()
    df = df[~df["symbol"].str.contains("-", na=False)]
    df = df[df["symbol"].str.startswith("MNQ")].copy()
    df["ts_event"] = df["ts_event"].dt.tz_convert(NY_TZ)
    df["date"] = df["ts_event"].dt.date
    df["t"] = df["ts_event"].dt.time
    front_month = (
        df.groupby(["date", "symbol"])["volume"]
        .sum()
        .groupby(level="date")
        .idxmax()
        .apply(lambda item: item[1])
        .to_dict()
    )
    df = df[df.apply(lambda row: row["symbol"] == front_month.get(row["date"]), axis=1)]
    df = df[(df["t"] >= RTH_START) & (df["t"] < RTH_END)].copy()
    df = df[df["date"] >= pd.Timestamp("2021-03-04").date()]
    df = df.set_index("ts_event").sort_index()
    return df


def bars_from_frame(df: pd.DataFrame) -> List[Bar]:
    return [
        Bar(
            ts=idx.isoformat(),
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
        )
        for idx, row in df.iterrows()
    ]


def write_bar_cache(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["ts", "open", "high", "low", "close", "volume", "symbol"])
        writer.writeheader()
        for idx, row in df.iterrows():
            writer.writerow(
                {
                    "ts": idx.isoformat(),
                    "open": "%.6f" % float(row.open),
                    "high": "%.6f" % float(row.high),
                    "low": "%.6f" % float(row.low),
                    "close": "%.6f" % float(row.close),
                    "volume": "%.0f" % float(row.volume),
                    "symbol": row.symbol,
                }
            )
    tmp.replace(path)


def simulate_plain_v2d_units(df: pd.DataFrame, candidate: str) -> List[Unit]:
    out: List[Unit] = []
    unit_n = 0
    for day, day_df in df.groupby("date"):
        day_df = day_df.sort_index()
        range_bars = day_df[day_df["t"] < RANGE_END]
        if range_bars.empty:
            continue
        rh = float(range_bars["high"].max())
        rl = float(range_bars["low"].min())
        rv = rh - rl
        if rv <= 0:
            continue
        trade_bars = day_df[day_df["t"] >= RANGE_END]
        for direction, entry_ts, entry, exit_ts, exit_price, reason in simulate_day_v2d_with_times(rh, rl, rv, trade_bars):
            unit_n += 1
            out.append(
                Unit(
                    candidate=candidate,
                    trade_id="%s-%s-%d" % (day.isoformat(), direction.lower(), unit_n),
                    unit_id=str(unit_n),
                    direction=direction,
                    entry_ts=entry_ts.isoformat(),
                    entry_price=entry,
                    exit_ts=exit_ts.isoformat(),
                    exit_price=exit_price,
                    exit_reason=reason,
                )
            )
    return out


def simulate_day_v2d_with_times(
    rh: float,
    rl: float,
    range_val: float,
    day_bars: pd.DataFrame,
    slip_ticks: int = 1,
) -> List[Tuple[str, pd.Timestamp, float, pd.Timestamp, float, str]]:
    long_break_trig = rh + TICK
    short_break_trig = rl - TICK
    short_fade_trig = rh - TICK
    long_fade_trig = rl + TICK
    short_fade_fill = short_fade_trig - slip_ticks * TICK
    long_fade_fill = long_fade_trig + slip_ticks * TICK

    long_break_done = False
    short_break_done = False
    armed_short_fade = False
    armed_long_fade = False
    traded_long = False
    traded_short = False

    in_trade = False
    direction: Optional[str] = None
    entry_ts: Optional[pd.Timestamp] = None
    entry = target = stop = 0.0
    trades: List[Tuple[str, pd.Timestamp, float, pd.Timestamp, float, str]] = []
    last_bar = None
    last_ts: Optional[pd.Timestamp] = None

    for ts, bar in day_bars.iterrows():
        ts = pd.Timestamp(ts)
        last_bar = bar
        last_ts = ts
        if not in_trade and ts.time() >= EOD_CUTOFF:
            break
        h = float(bar["high"])
        l = float(bar["low"])
        opn = float(bar["open"])
        breakout_this_bar = False

        if not in_trade:
            if not long_break_done and h >= long_break_trig:
                long_break_done = True
                breakout_this_bar = True
                if not traded_short:
                    armed_short_fade = True
            if not short_break_done and l <= short_break_trig:
                short_break_done = True
                breakout_this_bar = True
                if not traded_long:
                    armed_long_fade = True

        if not in_trade and not breakout_this_bar:
            short_hit = armed_short_fade and l <= short_fade_trig
            long_hit = armed_long_fade and h >= long_fade_trig
            if short_hit and long_hit:
                if opn >= (rh + rl) / 2.0:
                    direction, entry, target, stop = "Short", short_fade_fill, rl, rh + range_val
                    armed_short_fade = False
                else:
                    direction, entry, target, stop = "Long", long_fade_fill, rh, rl - range_val
                    armed_long_fade = False
                entry_ts = ts
                in_trade = True
            elif short_hit:
                direction, entry, target, stop = "Short", short_fade_fill, rl, rh + range_val
                entry_ts = ts
                in_trade = True
                armed_short_fade = False
            elif long_hit:
                direction, entry, target, stop = "Long", long_fade_fill, rh, rl - range_val
                entry_ts = ts
                in_trade = True
                armed_long_fade = False

        if in_trade and direction is not None and entry_ts is not None:
            closed = False
            exit_price = 0.0
            reason = ""
            if direction == "Long":
                if l < stop:
                    exit_price, reason, closed = stop, "loss_stop", True
                elif h >= target:
                    exit_price, reason, closed = target, "target", True
            else:
                if h > stop:
                    exit_price, reason, closed = stop, "loss_stop", True
                elif l <= target:
                    exit_price, reason, closed = target, "target", True
            if closed:
                trades.append((direction, entry_ts, entry, ts, exit_price, reason))
                if direction == "Long":
                    traded_long = True
                    armed_long_fade = False
                else:
                    traded_short = True
                    armed_short_fade = False
                in_trade = False
                direction = None
                entry_ts = None
                if traded_long and traded_short:
                    break
                if len(trades) >= 2:
                    break

    if in_trade and direction is not None and entry_ts is not None and last_bar is not None and last_ts is not None:
        trades.append((direction, entry_ts, entry, last_ts, float(last_bar["close"]), "eod"))
    return trades


def units_from_v2d_child_csv(path: Path, candidate: str) -> List[Unit]:
    out: List[Unit] = []
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    unit_n = 0
    for row in rows:
        if row.get("Regime") != "v2d":
            continue
        unit_n += 1
        out.append(
            Unit(
                candidate=candidate,
                trade_id="%s-%s-%s" % (row.get("Date", ""), row.get("Trade_Direction", ""), unit_n),
                unit_id=str(unit_n),
                direction=row.get("Trade_Direction", "Long"),
                entry_ts=row.get("Entry_Time", ""),
                entry_price=float(row.get("Tier1_Entry") or row.get("Entry_Price") or 0),
                exit_ts=row.get("Exit_Time", ""),
                exit_price=float(row.get("Exit_Price") or 0),
                exit_reason=row.get("Result", ""),
            )
        )
    return out


def write_summary(output_root: Path, results) -> None:
    rows: List[Dict[str, str]] = []
    for result in results:
        ratio = result.net_usd / abs(result.intrabar_mtm_dd_usd) if result.intrabar_mtm_dd_usd else 0.0
        rows.append(
            {
                "candidate": result.name,
                "slug": result.slug,
                "instrument": result.instrument,
                "units": str(result.units),
                "trades": str(result.trades),
                "net_usd": "%.2f" % result.net_usd,
                "close_mtm_dd_usd": "%.2f" % result.close_mtm_dd_usd,
                "intrabar_mtm_dd_usd": "%.2f" % result.intrabar_mtm_dd_usd,
                "max_open_units": str(result.max_open_units),
                "net_over_stress_dd": "%.2f" % ratio,
            }
        )
    rows.sort(key=lambda row: float(row["net_over_stress_dd"]), reverse=True)
    summary_csv = output_root / "v2d_summary.csv"
    summary_csv.parent.mkdir(parents=True, exist_ok=True)
    with summary_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["candidate"])
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# V2D Broker-Like 1m Replays",
        "",
        "These are 1-minute broker-like replays/audits. Plain v2d is freshly resimulated from completed 1-minute bars so entry and exit timestamps are recoverable. The v2d-child row audits the existing adaptive child file filtered to `Regime=v2d`; in that current file all v2d rows are one-contract tier-1 fills, so child adds did not materially appear in the v2d branch.",
        "",
        "| Candidate | Units | Trades | Net | Close MTM DD | Intrabar Stress DD | Max Open Units | Net / Stress DD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| %s | %s | %s | $%s | $%s | $%s | %s | %s |"
            % (
                row["candidate"],
                row["units"],
                row["trades"],
                _money(float(row["net_usd"])),
                _money(float(row["close_mtm_dd_usd"])),
                _money(float(row["intrabar_mtm_dd_usd"])),
                row["max_open_units"],
                row["net_over_stress_dd"],
            )
        )
    lines.append("")
    (output_root / "V2D_BROKER_LIKE_REPLAYS.md").write_text("\n".join(lines), encoding="utf-8")


def _money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return sign + f"{abs(value):,.2f}"


def run(output_root: Path) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    audit_root = output_root / "audits"
    bars_cache = output_root / "bars" / "MNQ_1m_rth.csv"
    df = load_mnq_1m(MNQ_1M_DBN)
    write_bar_cache(bars_cache, df)
    bars = bars_from_frame(df)
    results = []
    plain_units = simulate_plain_v2d_units(df, "mnq_v2d_fade_1m")
    results.append(
        audit_units(
            name="MNQ v2d fade 1m broker-like",
            slug="mnq_v2d_fade_1m",
            source=Path("fresh_1m_v2d_replay"),
            bar_source=bars_cache,
            bars=bars,
            units=plain_units,
            instrument="MNQ",
            notes="Fresh 1m broker-like replay of canonical v2d fade rules. One contract per leg; no fee drag in audit units.",
            output_root=audit_root,
        )
    )
    child_units = units_from_v2d_child_csv(MNQ_V2D_CHILD, "mnq_v2d_child_1m")
    results.append(
        audit_units(
            name="MNQ v2d child branch 1m broker-like",
            slug="mnq_v2d_child_1m",
            source=MNQ_V2D_CHILD,
            bar_source=bars_cache,
            bars=bars,
            units=child_units,
            instrument="MNQ",
            notes="Audits adaptive child CSV rows where Regime=v2d. Current v2d branch has one contract per leg and no filled child adds.",
            output_root=audit_root,
        )
    )
    write_summary(output_root, results)
    build_drawdown_report(output_root)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run MNQ v2d broker-like 1m replays.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("potions/live/state/broker_like_replays_monthly_boundary_stop_test"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    run(args.output_root)
    print("Wrote v2d broker-like replay artifacts under %s" % args.output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
