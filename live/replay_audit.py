from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


POINT_VALUES = {
    "MNQ": 2.0,
    "NQ": 20.0,
    "MES": 5.0,
    "ES": 50.0,
    "MYM": 0.5,
    "YM": 5.0,
}


@dataclass(frozen=True)
class Bar:
    ts: str
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class Unit:
    candidate: str
    trade_id: str
    unit_id: str
    direction: str
    entry_ts: str
    entry_price: float
    exit_ts: str
    exit_price: float
    exit_reason: str

    @property
    def sign(self) -> int:
        return -1 if self.direction.lower().startswith("short") else 1

    @property
    def points(self) -> float:
        return (self.exit_price - self.entry_price) * self.sign


@dataclass
class AuditResult:
    name: str
    slug: str
    source: str
    bar_source: str
    instrument: str
    point_value: float
    units: int
    trades: int
    net_points: float
    net_usd: float
    win_units: int
    loss_units: int
    close_mtm_dd_usd: float
    intrabar_mtm_dd_usd: float
    max_open_units: int
    start_ts: str
    end_ts: str
    notes: str


def read_bars(path: Path, ts_field: str = "date") -> list[Bar]:
    rows = _read_csv(path)
    bars: list[Bar] = []
    for row in rows:
        ts = row.get(ts_field) or row.get("ts") or row.get("time") or row.get("date")
        if not ts:
            continue
        bars.append(
            Bar(
                ts=_normalize_ts(ts),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
            )
        )
    bars.sort(key=lambda b: b.ts)
    return bars


def units_from_live_fills(
    path: Path,
    candidate: str,
    mark_open_ts: str = "",
    mark_open_price: Optional[float] = None,
) -> list[Unit]:
    rows = _read_csv(path)
    rows.sort(key=lambda row: row.get("ts", ""))
    open_lots: list[tuple[str, str, float, str]] = []
    out: list[Unit] = []
    n = 0
    entry_reasons = {"entry", "runner_entry"}
    for row in rows:
        if row.get("strategy_id") and row.get("strategy_id") != candidate:
            continue
        side = row.get("side", "").lower()
        qty = int(float(row.get("quantity") or 0))
        ts = _normalize_ts(row.get("ts", ""))
        price = float(row.get("price") or 0)
        reason = row.get("reason", "")
        trade_id = row.get("trade_id") or candidate
        for _ in range(qty):
            if reason in entry_reasons:
                direction = "Long" if side == "buy" else "Short"
                open_lots.append((trade_id, ts, price, direction))
                continue
            close_direction = "Long" if side == "sell" else "Short"
            match_idx = next((idx for idx, lot in enumerate(open_lots) if lot[3] == close_direction), None)
            if match_idx is None:
                continue
            entry_trade, entry_ts, entry_price, direction = open_lots.pop(match_idx)
            n += 1
            out.append(
                Unit(
                    candidate=candidate,
                    trade_id=entry_trade,
                    unit_id=str(n),
                    direction=direction,
                    entry_ts=entry_ts,
                    entry_price=entry_price,
                    exit_ts=ts,
                    exit_price=price,
                    exit_reason=reason,
                )
            )
    if mark_open_ts and mark_open_price is not None:
        for entry_trade, entry_ts, entry_price, direction in open_lots:
            n += 1
            out.append(
                Unit(
                    candidate=candidate,
                    trade_id=entry_trade,
                    unit_id=str(n),
                    direction=direction,
                    entry_ts=entry_ts,
                    entry_price=entry_price,
                    exit_ts=mark_open_ts,
                    exit_price=mark_open_price,
                    exit_reason="open_mark",
                )
            )
    return out


def units_from_units_csv(path: Path, candidate: str) -> list[Unit]:
    out: list[Unit] = []
    for row in _read_csv(path):
        out.append(
            Unit(
                candidate=candidate,
                trade_id=str(row.get("trade_id", "")),
                unit_id=str(row.get("unit_id", "")),
                direction=row.get("direction", "Long"),
                entry_ts=_normalize_ts(row.get("entry_date", "")),
                entry_price=float(row.get("entry_price") or 0),
                exit_ts=_normalize_ts(row.get("exit_date", "")),
                exit_price=float(row.get("exit_price") or 0),
                exit_reason=row.get("exit_reason", ""),
            )
        )
    return out


def units_from_monthly_scaleout(path: Path, candidate: str) -> list[Unit]:
    out: list[Unit] = []
    for row in _read_csv(path):
        trade_id = row.get("Period", "")
        direction = row.get("Trade_Direction", "Long")
        entry_ts = _normalize_ts(row.get("Entry_Date", ""))
        entry_price = float(row.get("Entry_Price") or 0)
        for idx in range(1, 4):
            exit_price = row.get(f"Unit{idx}_Exit_Price")
            exit_ts = row.get(f"Unit{idx}_Exit_Date")
            if not exit_price or not exit_ts:
                continue
            out.append(
                Unit(
                    candidate=candidate,
                    trade_id=trade_id,
                    unit_id=f"{trade_id}-U{idx}",
                    direction=direction,
                    entry_ts=entry_ts,
                    entry_price=entry_price,
                    exit_ts=_normalize_ts(exit_ts),
                    exit_price=float(exit_price),
                    exit_reason=row.get(f"Unit{idx}_Exit_Reason", ""),
                )
            )
    return out


def units_from_overlap(path: Path, candidate: str) -> list[Unit]:
    out: list[Unit] = []
    for row in _read_csv(path):
        direction = row.get("Trade_Side", "long").title()
        trade_id = "%s-%s-%s" % (row.get("Cluster_ID", ""), row.get("Entry_Kind", ""), row.get("Entry_Time", ""))
        entry_ts = _normalize_ts(row.get("Entry_Time", ""))
        entry_price = float(row.get("Entry_Price") or 0)
        for unit_id, exit_ts, exit_price, reason, _points in _parse_unit_exits(row.get("Unit_Exits", "")):
            out.append(
                Unit(
                    candidate=candidate,
                    trade_id=trade_id,
                    unit_id=unit_id,
                    direction=direction,
                    entry_ts=entry_ts,
                    entry_price=entry_price,
                    exit_ts=_normalize_ts(exit_ts),
                    exit_price=float(exit_price),
                    exit_reason=reason,
                )
            )
    return out


def audit_units(
    *,
    name: str,
    slug: str,
    source: Path,
    bar_source: Path,
    bars: list[Bar],
    units: list[Unit],
    instrument: str,
    notes: str,
    output_root: Path,
    fee_per_unit: float = 0.0,
) -> AuditResult:
    if not bars:
        raise ValueError("No bars supplied for %s" % name)
    point_value = POINT_VALUES[instrument]
    fee_pts = float(fee_per_unit) / point_value if point_value else 0.0
    units = sorted(units, key=lambda u: (u.entry_ts, u.exit_ts, u.unit_id))
    equity_rows: list[dict[str, str]] = []
    peak_close = 0.0
    close_dd = 0.0
    intrabar_dd = 0.0
    max_open = 0
    units_by_entry = sorted(units, key=lambda u: (u.entry_ts, u.exit_ts, u.unit_id))
    units_by_exit = sorted(units, key=lambda u: (u.exit_ts, u.entry_ts, u.unit_id))
    active_units: list[Unit] = []
    entry_idx = 0
    exit_idx = 0
    realized = 0.0

    for bar in bars:
        while entry_idx < len(units_by_entry) and units_by_entry[entry_idx].entry_ts <= bar.ts:
            active_units.append(units_by_entry[entry_idx])
            entry_idx += 1
        while exit_idx < len(units_by_exit) and units_by_exit[exit_idx].exit_ts < bar.ts:
            unit = units_by_exit[exit_idx]
            realized += unit.points - fee_pts
            try:
                active_units.remove(unit)
            except ValueError:
                pass
            exit_idx += 1
        close_equity = realized + sum((bar.close - u.entry_price) * u.sign for u in active_units)
        intrabar_equity = realized + sum(_intrabar_points(u, bar) for u in active_units)
        max_open = max(max_open, len(active_units))
        close_dd = min(close_dd, (close_equity - peak_close) * point_value)
        intrabar_dd = min(intrabar_dd, (intrabar_equity - peak_close) * point_value)
        peak_close = max(peak_close, close_equity)
        equity_rows.append(
            {
                "ts": bar.ts,
                "realized_points": "%.6f" % realized,
                "open_units": str(len(active_units)),
                "close_equity_points": "%.6f" % close_equity,
                "intrabar_stress_points": "%.6f" % intrabar_equity,
                "peak_close_points": "%.6f" % peak_close,
                "close_dd_usd": "%.2f" % ((close_equity - peak_close) * point_value),
                "intrabar_dd_usd": "%.2f" % ((intrabar_equity - peak_close) * point_value),
            }
        )

    net_points = sum(u.points for u in units)
    total_fees_usd = len(units) * float(fee_per_unit)
    net_usd = net_points * point_value - total_fees_usd
    result = AuditResult(
        name=name,
        slug=slug,
        source=str(source),
        bar_source=str(bar_source),
        instrument=instrument,
        point_value=point_value,
        units=len(units),
        trades=len({u.trade_id for u in units}),
        net_points=net_points,
        net_usd=net_usd,
        win_units=len([u for u in units if u.points > 0]),
        loss_units=len([u for u in units if u.points < 0]),
        close_mtm_dd_usd=close_dd,
        intrabar_mtm_dd_usd=intrabar_dd,
        max_open_units=max_open,
        start_ts=bars[0].ts,
        end_ts=bars[-1].ts,
        notes=notes,
    )
    _write_candidate_artifacts(output_root, result, units, equity_rows)
    return result


def run_default_audit(output_root: Path) -> list[AuditResult]:
    repo = Path.cwd()
    if repo.name != "potions":
        repo = repo / "potions"
    output_root.mkdir(parents=True, exist_ok=True)

    daily_bar_path = repo / "mnq" / "mnq_daily.csv"
    live_daily_bar_path = repo / "live" / "state" / "mnq_yearly_orb_paper_replay" / "bars" / "MNQ_D.csv"
    fourh_bar_path = repo / "mnq" / "data" / "mnq_front_month_4h_from_1m.csv"
    daily_bars = read_bars(daily_bar_path, "date")
    live_daily_bars = read_bars(live_daily_bar_path, "ts") if live_daily_bar_path.exists() else daily_bars
    fourh_bars = read_bars(fourh_bar_path, "time")

    candidates = [
        (
            "Yearly ORB scaleout3 live-runtime replay",
            "mnq_yearly_orb_scaleout3_live_runtime",
            repo / "live" / "state" / "mnq_yearly_orb_paper_replay" / "fills.csv",
            live_daily_bar_path,
            live_daily_bars,
            units_from_live_fills,
            "True paper-runtime replay fills from PaperBroker.",
        ),
        (
            "ATR Supertrend weekly-primary 10max 3-initial",
            "mnq_atr_weekly_primary_10max_3initial",
            repo / "mnq" / "case_studies" / "atr_supertrend_weekly_primary_biweekly_10max_entry_guard_3initial" / "units.csv",
            daily_bar_path,
            daily_bars,
            units_from_units_csv,
            "Artifact replay of unit exits; strategy plugin not implemented in live runtime yet.",
        ),
        (
            "ATR Supertrend weekly-primary 10max ladder 1/1/2/2/2",
            "mnq_atr_weekly_primary_10max_ladder112221",
            repo / "mnq" / "case_studies" / "atr_supertrend_weekly_primary_biweekly_10max_entry_guard_ladder112221" / "units.csv",
            daily_bar_path,
            daily_bars,
            units_from_units_csv,
            "Artifact replay of unit exits; strategy plugin not implemented in live runtime yet.",
        ),
        (
            "ATR Supertrend daily-primary 10max 3-initial entry guard",
            "mnq_atr_daily_primary_10max_3initial_entry_guard",
            repo / "mnq" / "case_studies" / "atr_supertrend_dca_long_biweekly_10max_weekly_flat_entry_guard_3initial" / "units.csv",
            daily_bar_path,
            daily_bars,
            units_from_units_csv,
            "Artifact replay of unit exits; strategy plugin not implemented in live runtime yet.",
        ),
        (
            "ATR Supertrend daily-primary 10max ladder 1/1/2/2/2 entry guard",
            "mnq_atr_daily_primary_10max_ladder112221_entry_guard",
            repo / "mnq" / "case_studies" / "atr_supertrend_dca_long_biweekly_10max_weekly_flat_entry_guard_ladder112221" / "units.csv",
            daily_bar_path,
            daily_bars,
            units_from_units_csv,
            "Artifact replay of unit exits; strategy plugin not implemented in live runtime yet.",
        ),
        (
            "ATR Supertrend daily weekly-flat 10max",
            "mnq_atr_daily_weekly_flat_10max",
            repo / "mnq" / "case_studies" / "atr_supertrend_dca_long_biweekly_10max_weekly_flat" / "units.csv",
            daily_bar_path,
            daily_bars,
            units_from_units_csv,
            "Artifact replay of unit exits; strategy plugin not implemented in live runtime yet.",
        ),
        (
            "ATR Supertrend daily weekly-flat 5max",
            "mnq_atr_daily_weekly_flat_5max",
            repo / "mnq" / "case_studies" / "atr_supertrend_dca_long_biweekly_5max_weekly_flat" / "units.csv",
            daily_bar_path,
            daily_bars,
            units_from_units_csv,
            "Artifact replay of unit exits; strategy plugin not implemented in live runtime yet.",
        ),
        (
            "Monthly ORB restricted scaleout3",
            "mnq_monthly_orb_restricted_scaleout3",
            repo / "mnq" / "mnq_monthly_orb_restricted_scaleout3.csv",
            daily_bar_path,
            daily_bars,
            units_from_monthly_scaleout,
            "Daily research artifact replay; not yet a live-runtime strategy plugin.",
        ),
        (
            "Monthly ORB overlap range breakout daily-ST retest x5",
            "mnq_monthly_orb_overlap_daily_st_retest5",
            repo / "mnq" / "case_studies" / "monthly_orb" / "overlap_range_breakout_4h_causal" / "mnq_overlap_range_breakout_4h_causal_breakout_only_2active_daily_st_retest5_close.csv",
            fourh_bar_path,
            fourh_bars,
            units_from_overlap,
            "4h causal research artifact replay; not yet a live-runtime strategy plugin.",
        ),
    ]
    results: list[AuditResult] = []
    for name, slug, source, bar_source, bars, loader, notes in candidates:
        if not source.exists():
            continue
        units = loader(source, slug)
        results.append(
            audit_units(
                name=name,
                slug=slug,
                source=source,
                bar_source=bar_source,
                bars=bars,
                units=units,
                instrument="MNQ",
                notes=notes,
                output_root=output_root,
            )
        )
    _write_summary(output_root, results)
    return results


def _intrabar_points(unit: Unit, bar: Bar) -> float:
    if unit.sign > 0:
        return bar.low - unit.entry_price
    return unit.entry_price - bar.high


def _write_candidate_artifacts(root: Path, result: AuditResult, units: list[Unit], equity_rows: list[dict[str, str]]) -> None:
    state_root = root / result.slug
    reports = state_root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    _write_csv(
        state_root / "unit_fills.csv",
        [
            {
                "candidate": u.candidate,
                "trade_id": u.trade_id,
                "unit_id": u.unit_id,
                "direction": u.direction,
                "entry_ts": u.entry_ts,
                "entry_price": "%.6f" % u.entry_price,
                "exit_ts": u.exit_ts,
                "exit_price": "%.6f" % u.exit_price,
                "exit_reason": u.exit_reason,
                "points": "%.6f" % u.points,
                "usd": "%.2f" % (u.points * result.point_value),
            }
            for u in units
        ],
    )
    _write_csv(state_root / "equity_curve.csv", equity_rows)
    text = _candidate_report(result)
    (reports / "MTM_AUDIT.md").write_text(text)


def _write_summary(root: Path, results: list[AuditResult]) -> None:
    rows = [
        {
            "candidate": r.name,
            "slug": r.slug,
            "units": str(r.units),
            "trades": str(r.trades),
            "net_usd": "%.2f" % r.net_usd,
            "close_mtm_dd_usd": "%.2f" % r.close_mtm_dd_usd,
            "intrabar_mtm_dd_usd": "%.2f" % r.intrabar_mtm_dd_usd,
            "max_open_units": str(r.max_open_units),
            "net_over_intrabar_dd": "%.2f" % (r.net_usd / abs(r.intrabar_mtm_dd_usd) if r.intrabar_mtm_dd_usd else 0.0),
        }
        for r in results
    ]
    _write_csv(root / "summary.csv", rows)
    lines = [
        "# Live Replay Candidate MTM Audit",
        "",
        "This is a flat-file replay/audit of the current leading candidates. Yearly ORB uses true `PaperBroker` fills from the live runtime. The other rows replay existing unit-level research artifacts through the same MTM calculator until their strategy plugins are implemented.",
        "",
        "| Candidate | Units | Trades | Net | Close MTM DD | Intrabar Stress DD | Max Open Units | Net / Stress DD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        ratio = r.net_usd / abs(r.intrabar_mtm_dd_usd) if r.intrabar_mtm_dd_usd else 0.0
        lines.append(
            "| %s | %d | %d | $%s | $%s | $%s | %d | %.2f |"
            % (
                r.name,
                r.units,
                r.trades,
                _money(r.net_usd),
                _money(r.close_mtm_dd_usd),
                _money(r.intrabar_mtm_dd_usd),
                r.max_open_units,
                ratio,
            )
        )
    lines.extend(
        [
            "",
            "## Caveat",
            "",
            "Artifact rows validate the execution book and MTM heat, not live-runtime signal generation. To reach the same confidence level as Yearly ORB, each candidate still needs a proper `StrategyPlugin` pass through `PaperBroker`.",
            "",
        ]
    )
    (root / "SUMMARY.md").write_text("\n".join(lines))


def _candidate_report(r: AuditResult) -> str:
    ratio = r.net_usd / abs(r.intrabar_mtm_dd_usd) if r.intrabar_mtm_dd_usd else 0.0
    lines = [
        "# %s" % r.name,
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Source | `%s` |" % r.source,
        "| Bar source | `%s` |" % r.bar_source,
        "| Bar window | `%s` to `%s` |" % (r.start_ts, r.end_ts),
        "| Units | %d |" % r.units,
        "| Trade groups | %d |" % r.trades,
        "| Winning units | %d |" % r.win_units,
        "| Losing units | %d |" % r.loss_units,
        "| Net points | %.2f |" % r.net_points,
        "| Point value | $%.2f |" % r.point_value,
        "| Net dollars | $%s |" % _money(r.net_usd),
        "| Close MTM DD | $%s |" % _money(r.close_mtm_dd_usd),
        "| Intrabar stress MTM DD | $%s |" % _money(r.intrabar_mtm_dd_usd),
        "| Max open units | %d |" % r.max_open_units,
        "| Net / intrabar stress DD | %.2f |" % ratio,
        "",
        "Notes: %s" % r.notes,
        "",
    ]
    return "\n".join(lines)


def _parse_unit_exits(text: str) -> Iterable[tuple[str, str, float, str, float]]:
    if not text:
        return []
    out = []
    pattern = re.compile(
        r"^(U\d+):(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}):([-0-9.]+):(.+):([-0-9.]+)$"
    )
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        match = pattern.match(part)
        if not match:
            raise ValueError("Could not parse unit exit: %s" % part)
        unit_id, exit_ts, exit_price, reason, points = match.groups()
        out.append((unit_id, exit_ts, float(exit_price), reason, float(points)))
    return out


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def _normalize_ts(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    if " " in value:
        value = value.replace(" ", "T", 1)
    return value


def _money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return sign + f"{abs(value):,.2f}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit candidate execution artifacts through a shared MTM replay.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("potions/live/state/candidate_mtm_audits"),
        help="Directory where candidate audit state/report folders are written.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    results = run_default_audit(args.output_root)
    for r in results:
        print(
            "%s: net=$%s close_mtm_dd=$%s intrabar_mtm_dd=$%s max_open=%d"
            % (r.slug, _money(r.net_usd), _money(r.close_mtm_dd_usd), _money(r.intrabar_mtm_dd_usd), r.max_open_units)
        )
    print("Wrote %s" % args.output_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
