"""Post-process risk accounting for ST+PMC runner variants vs fair base.

Every system report includes:
  - Max MTM drawdown (intrabar; conservative headline)
  - Max protected-floor drawdown (stop-protected capital-at-risk)
  - Max realized-equity drawdown (closed P&L only)
  - Peak open profit giveback (peak MTM equity − protected-floor equity)
  - Open exposure (max units, gross notional, margin, worst concurrent stop loss)

Protected floor: each open unit valued at its current stop.
  - Hard stop = entry ± stop_pts until TP1 fills on that trade_id
  - Runner units → breakeven stop after TP1 (`reason=target`) on the campaign

No replay re-run — uses fills.csv + audit equity_curve.csv + unit_fills.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .replay_audit import POINT_VALUES, Unit, _normalize_ts, units_from_live_fills

REPO = Path(__file__).resolve().parents[1]

# Approximate CME initial margins (USD / contract). CFD US30/NAS100: use stop-risk proxy.
MARGIN_USD = {
    "YM": 9900.0,
    "MYM": 990.0,
    "NQ": 22000.0,
    "MNQ": 2200.0,
    "MES": 1400.0,
    "ES": 14000.0,
    "US30": 500.0,  # ~1× SL50 × $1/pt CFD proxy
    "NAS100": 500.0,
}

BASE_VARIANT = "sl50_tp150_3r_1mfill"
RUNNER_VARIANTS = ("sl50_tp150_runners_2r_10r", "sl50_tp150_runners_2r_indef")
DEFAULT_STOP_PTS = 50.0
DEFAULT_FEE = 1.5


@dataclass
class RichUnit:
    trade_id: str
    unit_id: str
    direction: str
    entry_ts: str
    entry_price: float
    exit_ts: str
    exit_price: float
    exit_reason: str
    entry_reason: str

    @property
    def sign(self) -> int:
        return -1 if self.direction.lower().startswith("short") else 1

    @property
    def is_runner(self) -> bool:
        return str(self.entry_reason).startswith("runner_entry")

    @property
    def points(self) -> float:
        return (self.exit_price - self.entry_price) * self.sign


@dataclass
class RiskMetrics:
    market: str
    instrument: str
    variant: str
    net_usd: float
    units: int
    wr_pct: float
    max_mtm_dd: float
    max_close_mtm_dd: float
    max_protected_floor_dd: float
    max_realized_equity_dd: float
    peak_open_profit_giveback: float
    max_open_units: int
    max_gross_notional: float
    max_margin: float
    worst_concurrent_stop_loss: float
    ns_mtm: float
    ns_floor: float
    eoy_units: int = 0
    notes: str = ""


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def units_with_entry_reason(fills_path: Path, strategy_id: str) -> List[RichUnit]:
    """FIFO match like units_from_live_fills, retaining entry reason."""
    rows = _read_csv(fills_path)
    rows.sort(key=lambda r: r.get("ts", ""))
    open_lots: List[Tuple[str, str, float, str, str]] = []
    out: List[RichUnit] = []
    n = 0
    entry_reasons = {"entry", "runner_entry", "add", "retest_add", "bb_add"}
    for row in rows:
        if row.get("strategy_id") and row.get("strategy_id") != strategy_id:
            continue
        side = (row.get("side") or "").lower()
        qty = int(float(row.get("quantity") or 0))
        ts = _normalize_ts(row.get("ts", ""))
        price = float(row.get("price") or 0)
        reason = row.get("reason") or ""
        trade_id = row.get("trade_id") or strategy_id
        is_entry = reason in entry_reasons or str(reason).startswith("runner_entry")
        for _ in range(qty):
            if is_entry:
                direction = "Long" if side == "buy" else "Short"
                open_lots.append((trade_id, ts, price, direction, reason))
                continue
            close_direction = "Long" if side == "sell" else "Short"
            match_idx = next((i for i, lot in enumerate(open_lots) if lot[3] == close_direction), None)
            if match_idx is None:
                continue
            entry_trade, entry_ts, entry_price, direction, entry_reason = open_lots.pop(match_idx)
            n += 1
            out.append(
                RichUnit(
                    trade_id=entry_trade,
                    unit_id=str(n),
                    direction=direction,
                    entry_ts=entry_ts,
                    entry_price=entry_price,
                    exit_ts=ts,
                    exit_price=price,
                    exit_reason=reason,
                    entry_reason=entry_reason,
                )
            )
    return out


def _tp1_be_times(fills_path: Path, strategy_id: str) -> Dict[str, str]:
    """First TP1 (`target`) fill ts per trade_id → runners go BE afterward."""
    out: Dict[str, str] = {}
    for row in _read_csv(fills_path):
        if row.get("strategy_id") and row.get("strategy_id") != strategy_id:
            continue
        if (row.get("reason") or "") != "target":
            continue
        tid = row.get("trade_id") or ""
        ts = _normalize_ts(row.get("ts", ""))
        if tid and tid not in out:
            out[tid] = ts
    return out


def _stop_price(unit: RichUnit, stop_pts: float, be_active: bool) -> float:
    if be_active and unit.is_runner:
        return float(unit.entry_price)
    if unit.sign > 0:
        return float(unit.entry_price) - stop_pts
    return float(unit.entry_price) + stop_pts


def _protected_pts(unit: RichUnit, stop_pts: float, be_active: bool) -> float:
    stop = _stop_price(unit, stop_pts, be_active)
    return (stop - unit.entry_price) * unit.sign


def _parse_audit_headline(audit_md: Path) -> Dict[str, float]:
    out: Dict[str, float] = {}
    if not audit_md.exists():
        return out
    for line in audit_md.read_text(encoding="utf-8").splitlines():
        if "| Net dollars |" in line:
            out["net_usd"] = float(line.split("|")[2].strip().replace("$", "").replace(",", ""))
        elif "| Intrabar stress MTM DD |" in line:
            out["max_mtm_dd"] = float(line.split("|")[2].strip().replace("$", "").replace(",", ""))
        elif "| Close MTM DD |" in line:
            out["max_close_mtm_dd"] = float(line.split("|")[2].strip().replace("$", "").replace(",", ""))
        elif "| Max open units |" in line:
            out["max_open_units"] = float(line.split("|")[2].strip())
        elif "| Units |" in line:
            out["units"] = float(line.split("|")[2].strip())
        elif "| Winning units |" in line:
            out["win_units"] = float(line.split("|")[2].strip())
    return out


def compute_risk(
    *,
    market: str,
    instrument: str,
    variant: str,
    fills_path: Path,
    strategy_id: str,
    equity_curve_path: Path,
    audit_md: Path,
    stop_pts: float = DEFAULT_STOP_PTS,
    fee_per_unit: float = DEFAULT_FEE,
) -> RiskMetrics:
    units = units_with_entry_reason(fills_path, strategy_id)
    be_at = _tp1_be_times(fills_path, strategy_id)
    pv = float(POINT_VALUES[instrument])
    margin_each = float(MARGIN_USD.get(instrument, stop_pts * pv))

    headline = _parse_audit_headline(audit_md)
    net_usd = float(headline.get("net_usd") or sum(u.points for u in units) * pv - len(units) * fee_per_unit)
    n_units = int(headline.get("units") or len(units))
    wins = int(headline.get("win_units") or sum(1 for u in units if u.points > 0))
    wr = (100.0 * wins / n_units) if n_units else 0.0
    max_mtm_dd = float(headline.get("max_mtm_dd") or 0.0)
    max_close_mtm_dd = float(headline.get("max_close_mtm_dd") or 0.0)

    eq_rows = _read_csv(equity_curve_path) if equity_curve_path.exists() else []
    by_entry = sorted(units, key=lambda u: (u.entry_ts, u.exit_ts, u.unit_id))
    by_exit = sorted(units, key=lambda u: (u.exit_ts, u.entry_ts, u.unit_id))
    active: List[RichUnit] = []
    entry_idx = 0
    exit_idx = 0
    realized_usd = 0.0

    peak_mtm = 0.0
    peak_floor = 0.0
    peak_realized = 0.0
    max_floor_dd = 0.0
    max_realized_dd = 0.0
    peak_giveback = 0.0
    max_open = 0
    max_notional = 0.0
    max_margin = 0.0
    worst_stop = 0.0  # most negative concurrent stop PnL

    # Prefer equity-curve timestamps (hourly) so MTM path matches audit.
    timeline = [r["ts"] for r in eq_rows] if eq_rows else sorted({u.entry_ts for u in units} | {u.exit_ts for u in units})

    eq_by_ts = {r["ts"]: r for r in eq_rows}

    for ts in timeline:
        while entry_idx < len(by_entry) and by_entry[entry_idx].entry_ts <= ts:
            active.append(by_entry[entry_idx])
            entry_idx += 1
        while exit_idx < len(by_exit) and by_exit[exit_idx].exit_ts < ts:
            u = by_exit[exit_idx]
            realized_usd += u.points * pv - fee_per_unit
            try:
                active.remove(u)
            except ValueError:
                pass
            exit_idx += 1

        floor_open = 0.0
        stop_open = 0.0
        notional = 0.0
        for u in active:
            be = bool(be_at.get(u.trade_id) and be_at[u.trade_id] <= ts)
            ppt = _protected_pts(u, stop_pts, be)
            floor_open += ppt * pv
            stop_open += ppt * pv
            notional += abs(u.entry_price) * pv

        floor_eq = realized_usd + floor_open
        # MTM from audit curve when available (intrabar stress points * pv)
        if ts in eq_by_ts:
            mtm_pts = float(eq_by_ts[ts].get("intrabar_stress_points") or eq_by_ts[ts].get("close_equity_points") or 0)
            mtm_eq = mtm_pts * pv
            # realized in curve is fee-aware points; prefer our realized_usd for consistency
        else:
            mtm_eq = floor_eq  # fallback

        peak_mtm = max(peak_mtm, mtm_eq)
        peak_floor = max(peak_floor, floor_eq)
        peak_realized = max(peak_realized, realized_usd)
        max_floor_dd = min(max_floor_dd, floor_eq - peak_floor)
        max_realized_dd = min(max_realized_dd, realized_usd - peak_realized)
        peak_giveback = max(peak_giveback, peak_mtm - floor_eq)
        max_open = max(max_open, len(active))
        max_notional = max(max_notional, notional)
        max_margin = max(max_margin, len(active) * margin_each)
        worst_stop = min(worst_stop, stop_open)

    eoy = sum(1 for u in units if u.exit_reason == "year_end_flatten")
    ns_mtm = (net_usd / abs(max_mtm_dd)) if max_mtm_dd else 0.0
    ns_floor = (net_usd / abs(max_floor_dd)) if max_floor_dd else 0.0

    return RiskMetrics(
        market=market,
        instrument=instrument,
        variant=variant,
        net_usd=net_usd,
        units=n_units,
        wr_pct=wr,
        max_mtm_dd=max_mtm_dd if max_mtm_dd else max_close_mtm_dd,
        max_close_mtm_dd=max_close_mtm_dd,
        max_protected_floor_dd=max_floor_dd,
        max_realized_equity_dd=max_realized_dd,
        peak_open_profit_giveback=peak_giveback,
        max_open_units=int(headline.get("max_open_units") or max_open),
        max_gross_notional=max_notional,
        max_margin=max_margin,
        worst_concurrent_stop_loss=worst_stop,
        ns_mtm=ns_mtm,
        ns_floor=ns_floor,
        eoy_units=eoy,
    )


def _hub_specs() -> List[Dict[str, object]]:
    specs: List[Dict[str, object]] = []
    # US30 hub
    us30 = REPO / "live" / "state" / "us30_st_pmc_runner_variants"
    for variant in (BASE_VARIANT,) + RUNNER_VARIANTS:
        sid = "us30_hourly_st_pmc_%s" % variant
        specs.append(
            {
                "hub": us30,
                "hub_name": "us30_st_pmc_runner_variants",
                "market": "us30",
                "instrument": "US30",
                "variant": variant,
                "strategy_id": sid,
                "fills": us30 / "states" / sid / "fills.csv",
                "equity": us30 / "audits" / sid / sid / "equity_curve.csv",
                "audit_md": us30 / "audits" / sid / sid / "reports" / "MTM_AUDIT.md",
            }
        )
    # Futures hub
    fut = REPO / "live" / "state" / "futures_st_pmc_runner_variants"
    for market, instrument in (("ym", "YM"), ("mym", "MYM"), ("mnq", "MNQ"), ("nq", "NQ")):
        for variant in (BASE_VARIANT,) + RUNNER_VARIANTS:
            sid = "%s_hourly_st_pmc_%s" % (market, variant)
            specs.append(
                {
                    "hub": fut,
                    "hub_name": "futures_st_pmc_runner_variants",
                    "market": market,
                    "instrument": instrument,
                    "variant": variant,
                    "strategy_id": sid,
                    "fills": fut / market / "states" / sid / "fills.csv",
                    "equity": fut / market / "audits" / sid / sid / "equity_curve.csv",
                    "audit_md": fut / market / "audits" / sid / sid / "reports" / "MTM_AUDIT.md",
                }
            )
    return specs


def _fmt_usd(x: float) -> str:
    return "$%.0f" % x


def _delta(runner: float, base: float) -> str:
    d = runner - base
    sign = "+" if d >= 0 else ""
    return "%s$%.0f" % (sign, d)


def _delta_ratio(runner: float, base: float) -> str:
    d = runner - base
    sign = "+" if d >= 0 else ""
    return "%s%.2f" % (sign, d)


def write_hub_report(hub: Path, hub_name: str, rows: Sequence[RiskMetrics]) -> None:
    hub.mkdir(parents=True, exist_ok=True)
    csv_path = hub / "RUNNER_RISK_ACCOUNTING.csv"
    fields = [
        "market",
        "instrument",
        "variant",
        "net_usd",
        "units",
        "wr_pct",
        "max_mtm_dd",
        "max_close_mtm_dd",
        "max_protected_floor_dd",
        "max_realized_equity_dd",
        "peak_open_profit_giveback",
        "max_open_units",
        "max_gross_notional",
        "max_margin",
        "worst_concurrent_stop_loss",
        "ns_mtm",
        "ns_floor",
        "eoy_units",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: getattr(r, k) for k in fields})

    lines = [
        "# Runner risk accounting — %s" % hub_name,
        "",
        "Post-process from fills + equity curves (no re-replay).",
        "",
        "## Definitions",
        "",
        "| Metric | Meaning |",
        "|---|---|",
        "| **Max MTM drawdown** | Investor/economic drawdown (intrabar stress); conservative headline |",
        "| **Max protected-floor drawdown** | Equity if every open unit were stopped at its current stop (hard SL or BE after TP1 for runners) |",
        "| **Max realized-equity drawdown** | Drawdown on closed P&L only |",
        "| **Peak open profit giveback** | Max(peak MTM equity − protected-floor equity) — open paper profit above the stop floor |",
        "| **Open exposure** | Max units; gross notional (= Σ\\|entry\\|×point_value); est. initial margin; worst concurrent stop loss |",
        "",
        "Margins (approx CME day / CFD proxy): `%s`" % json.dumps(MARGIN_USD, sort_keys=True),
        "",
        "## Per-system report",
        "",
        "| market | variant | net | MTM DD | floor DD | realized DD | giveback | max units | max notional | max margin | worst stop | N/S MTM | N/S floor |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            "| `%s` | `%s` | %s | %s | %s | %s | %s | %d | %s | %s | %s | %.2f | %.2f |"
            % (
                r.market,
                r.variant,
                _fmt_usd(r.net_usd),
                _fmt_usd(r.max_mtm_dd),
                _fmt_usd(r.max_protected_floor_dd),
                _fmt_usd(r.max_realized_equity_dd),
                _fmt_usd(r.peak_open_profit_giveback),
                r.max_open_units,
                _fmt_usd(r.max_gross_notional),
                _fmt_usd(r.max_margin),
                _fmt_usd(r.worst_concurrent_stop_loss),
                r.ns_mtm,
                r.ns_floor,
            )
        )

    # Runner vs base
    lines.extend(["", "## Runner vs base (`%s`)" % BASE_VARIANT, ""])
    by_key = {(r.market, r.variant): r for r in rows}
    markets = sorted({r.market for r in rows})
    lines.append(
        "| market | runner | Δ net | Δ MTM DD | Δ floor DD | Δ realized DD | Δ giveback | Δ max units | base N/S | runner N/S | floor N/S |"
    )
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for market in markets:
        base = by_key.get((market, BASE_VARIANT))
        if not base:
            continue
        for rv in RUNNER_VARIANTS:
            r = by_key.get((market, rv))
            if not r:
                continue
            lines.append(
                "| `%s` | `%s` | %s | %s | %s | %s | %s | %+d | %.2f | %.2f | %.2f |"
                % (
                    market,
                    rv.replace("sl50_tp150_", ""),
                    _delta(r.net_usd, base.net_usd),
                    _delta(r.max_mtm_dd, base.max_mtm_dd),
                    _delta(r.max_protected_floor_dd, base.max_protected_floor_dd),
                    _delta(r.max_realized_equity_dd, base.max_realized_equity_dd),
                    _delta(r.peak_open_profit_giveback, base.peak_open_profit_giveback),
                    r.max_open_units - base.max_open_units,
                    base.ns_mtm,
                    r.ns_mtm,
                    r.ns_floor,
                )
            )

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "- `%s`" % csv_path.name,
            "- Per-variant `audits/*/reports/MTM_AUDIT.md` (headline MTM DD)",
            "",
        ]
    )
    md_path = hub / "RUNNER_RISK_ACCOUNTING.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote %s" % csv_path, flush=True)
    print("Wrote %s" % md_path, flush=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hubs", nargs="*", default=["us30", "futures"], choices=["us30", "futures"])
    ap.add_argument("--markets", nargs="*", default=None, help="Optional market filter (us30, ym, …)")
    args = ap.parse_args(list(argv) if argv is not None else None)

    want_hubs = set(args.hubs)
    want_markets = set(args.markets) if args.markets else None

    by_hub: Dict[str, List[RiskMetrics]] = {}
    for spec in _hub_specs():
        hub_name = str(spec["hub_name"])
        short = "us30" if hub_name.startswith("us30") else "futures"
        if short not in want_hubs:
            continue
        market = str(spec["market"])
        if want_markets and market not in want_markets:
            continue
        fills = Path(spec["fills"])
        equity = Path(spec["equity"])
        audit_md = Path(spec["audit_md"])
        if not fills.exists() or not audit_md.exists():
            print("SKIP %s/%s — missing fills or audit" % (market, spec["variant"]), flush=True)
            continue
        print("RISK %s/%s" % (market, spec["variant"]), flush=True)
        m = compute_risk(
            market=market,
            instrument=str(spec["instrument"]),
            variant=str(spec["variant"]),
            fills_path=fills,
            strategy_id=str(spec["strategy_id"]),
            equity_curve_path=equity,
            audit_md=audit_md,
        )
        by_hub.setdefault(hub_name, []).append(m)
        print(
            "  net=%s MTM=%s floor=%s realized=%s giveback=%s open=%d worst_stop=%s"
            % (
                _fmt_usd(m.net_usd),
                _fmt_usd(m.max_mtm_dd),
                _fmt_usd(m.max_protected_floor_dd),
                _fmt_usd(m.max_realized_equity_dd),
                _fmt_usd(m.peak_open_profit_giveback),
                m.max_open_units,
                _fmt_usd(m.worst_concurrent_stop_loss),
            ),
            flush=True,
        )

    for hub_name, rows in by_hub.items():
        hub = REPO / "live" / "state" / hub_name
        write_hub_report(hub, hub_name, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
