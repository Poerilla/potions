"""US30 ST+PMC indefinite runner — dual MTM DD study with 90-day max hold + OANDA financing.

Runs a single variant: 3 units per campaign (TP1@150 + runner@300 + indefinite runner).
Both runners move SL → BE after TP1. Indefinite runners do not block later campaigns.
Inventory is force-flattened at year-end as a safety net AND by 90-day per-lot max hold
applied in postprocess.

Dual MTM DD report
------------------
The replay itself is the same as ``sl50_tp150_runners_2r_indef`` in the existing
``us30_st_pmc_runner_variants`` hub. The novel accounting is the postprocess pass:

  runner_included (raw)
    Full open inventory at intrabar stress. Baseline for reference.

  runner_occluded
    Each open lot's adverse MTM is clipped to its live protective stop.
    Hard SL pre-TP1; BE (entry price) after TP1 for runner lots.
    A runner that is underwater but has NOT hit its BE stop is "still green"
    (contributes ≈0 to DD). Realised P&L of closed lots is unchanged.

  runner_excluded
    Open runner_entry lots are excluded from open MTM entirely.
    Their realised P&L still counts when they close.
    TP1 / primary entry lots remain in open stress.

Max hold (90-day)
-----------------
Applied purely in postprocess: runner lots whose open duration exceeds
MAX_RUNNER_HOLD_DAYS calendar days are treated as closed at the bar-close price
on the expiry bar for the purpose of equity/DD paths and the financing calculation.
This does NOT re-run the engine; the fills.csv tape stays intact.

OANDA overnight financing
--------------------------
US30 (US Wall St 30) uses SOFR + 2.5% admin fee for longs (charges deducted).
Short positions: SOFR − 2.5% (often a credit).
Daily formula: notional_usd × annual_rate / 365 (×3 on Fridays for weekend nights).
We use a conservative static SOFR assumption of 5.0% (2026 ballpark) and report
net with and without financing.

Hub: live/state/us30_st_pmc_runners_2r_indef_hold90/

Usage:
  cd /home/tester/hsm/potions
  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.us30_st_pmc_indef_hold90_study [--force] [--email]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .broker import DEFAULT_TICK_SIZE
from .fx_data import load_fx_1m_by_ny_date
from .hourly_st_pmc_loss_research import VariantConfig
from .hourly_st_pmc_strategyplugin_variants import run_variant
from .models import Bar
from .notify_email import send_email
from .replay_audit import POINT_VALUES
from .run_ledger import begin_run, complete_run, fail_run, metrics_from_audit
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, resample_hourly

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "us30_st_pmc_runners_2r_indef_hold90"
SYM = "US30"
TICK = 0.1
MAX_RUNNER_HOLD_DAYS = 90

# OANDA financing for US30_USD index CFD (conservative static):
# Reference rate: SOFR ≈ 5.0% (annualised, 2026 ballpark)
# Long: SOFR + 2.5% admin = 7.5% p.a. (charge, negative)
# Short: SOFR − 2.5% admin = 2.5% p.a. (credit, positive for short holder; but runners are directional)
SOFR_RATE = 0.050        # 5.0% annual
ADMIN_FEE = 0.025        # 2.5% p.a.
LONG_RATE_PA = SOFR_RATE + ADMIN_FEE     # 7.5% charge for longs
SHORT_RATE_PA = SOFR_RATE - ADMIN_FEE    # 2.5% credit for shorts (positive = credit)

_POINT_VALUE = 1.0       # US30 CFD: $1 per point per unit


def _load_bars() -> Tuple[List[Bar], Any]:
    one_m = REPO / "fx" / "us30_1m.csv"
    gby = load_fx_1m_by_ny_date(one_m, SYM)
    one_m_df = concat_all_1m(gby)
    hourly = resample_hourly(one_m_df)
    bars: List[Bar] = []
    for ts, row in hourly.iterrows():
        bars.append(
            Bar(
                instrument=SYM,
                timeframe="1h",
                ts=ts.isoformat(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(one_m),
            )
        )
    return bars, one_m_df


# ---------------------------------------------------------------------------
# Postprocess helpers
# ---------------------------------------------------------------------------

def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _parse_dt(ts: str) -> date:
    return date.fromisoformat(str(ts)[:10])


def _friday(d: date) -> bool:
    return d.weekday() == 4  # Friday


def _financing_days(d: date) -> float:
    """Calendar days of financing owed if position held past 5pm ET on day d.
    Fridays = 3 (Sat + Sun + Mon), weekdays = 1.
    """
    return 3.0 if _friday(d) else 1.0


def _financing_daily(notional_usd: float, side: str, d: date) -> float:
    """Financing USD for one night (negative = charge for long, positive = credit for short credit positions).
    For long US30 positions the charge is subtracted from equity.
    For short positions there may be a credit (positive).
    """
    rate_pa = LONG_RATE_PA if side == "long" else SHORT_RATE_PA
    sign = -1.0 if side == "long" else +1.0  # long is a charge; short is a credit
    days = _financing_days(d)
    return sign * abs(notional_usd) * abs(rate_pa) / 365.0 * days


class _Lot:
    """An open runner lot tracked during dual-DD postprocess."""
    __slots__ = ("trade_id", "unit_id", "entry_ts", "entry_price", "side",
                 "entry_date", "exit_ts", "exit_price", "exit_reason",
                 "be_ts", "is_runner", "max_hold_exit_ts")

    def __init__(
        self,
        trade_id: str,
        unit_id: str,
        entry_ts: str,
        entry_price: float,
        side: str,
        entry_reason: str,
        max_hold_exit_ts: Optional[str] = None,
    ):
        self.trade_id = trade_id
        self.unit_id = unit_id
        self.entry_ts = entry_ts
        self.entry_price = entry_price
        self.side = side  # "buy" / "sell"
        self.entry_date = _parse_dt(entry_ts)
        self.exit_ts: Optional[str] = None
        self.exit_price: Optional[float] = None
        self.exit_reason: Optional[str] = None
        self.be_ts: Optional[str] = None  # when SL moved to BE (TP1 fill on campaign)
        self.is_runner = str(entry_reason).startswith("runner_entry")
        self.max_hold_exit_ts = max_hold_exit_ts  # override exit if hold exceeded

    @property
    def sign(self) -> float:
        return 1.0 if self.side == "buy" else -1.0

    def live_stop(self, ts: str, stop_pts: float) -> float:
        """Stop price at a given ts. BE after TP1; hard SL otherwise."""
        if self.is_runner and self.be_ts and ts >= self.be_ts:
            return self.entry_price  # BE
        adj_pts = stop_pts * self.sign
        return self.entry_price - adj_pts

    def occluded_pts(self, current_bar_low: float, current_bar_high: float, ts: str, stop_pts: float) -> float:
        """Points contribution to occluded open equity.
        If the worst-case intrabar price is above the stop, clipped to stop-floor pts.
        For a long: worst = bar.low; for short: worst = bar.high.
        """
        stop = self.live_stop(ts, stop_pts)
        worst = current_bar_low if self.side == "buy" else current_bar_high
        # Protected floor: can't lose more than entry→stop on an open lot.
        # If worst < stop → breached (but in a backtest the stop would have fired; for occluded DD we use stop as floor).
        protected_exit = max(stop, worst) if self.side == "buy" else min(stop, worst)
        return (protected_exit - self.entry_price) * self.sign


def _build_lots_timeline(
    fills_path: Path,
    strategy_id: str,
    stop_pts: float,
    max_hold_days: int,
    hourly_close_by_ts: Dict[str, float],
    hourly_side_default: str = "buy",
) -> Tuple[List[_Lot], Dict[str, str]]:
    """FIFO-match fills into lots; record BE timestamps; apply max-hold overrides.

    Returns (closed_lots, tp1_be_by_trade) where tp1_be_by_trade maps trade_id → first TP1 fill ts.
    """
    rows = _read_csv(fills_path)
    rows.sort(key=lambda r: r.get("ts", ""))

    open_stacks: Dict[str, List[_Lot]] = defaultdict(list)
    closed: List[_Lot] = []
    tp1_be: Dict[str, str] = {}  # trade_id → ts of first "target" fill
    n = 0

    entry_reasons = {"entry", "runner_entry", "add", "retest_add", "bb_add"}

    for row in rows:
        if row.get("strategy_id") and row.get("strategy_id") != strategy_id:
            continue
        side = (row.get("side") or "").lower()
        qty = abs(int(float(row.get("quantity") or 0)))
        ts = str(row.get("ts") or "")
        price = float(row.get("price") or 0.0)
        reason = str(row.get("reason") or "")
        trade_id = str(row.get("trade_id") or strategy_id)

        is_entry = reason in entry_reasons or reason.startswith("runner_entry")
        if is_entry:
            for _ in range(qty):
                n += 1
                lot = _Lot(
                    trade_id=trade_id,
                    unit_id=str(n),
                    entry_ts=ts,
                    entry_price=price,
                    side=side,
                    entry_reason=reason,
                )
                if max_hold_days > 0 and lot.is_runner:
                    # Determine max-hold expiry timestamp: entry_date + max_hold_days
                    expiry_date = lot.entry_date + timedelta(days=max_hold_days)
                    # Find the closest hourly bar ts at or after expiry
                    expiry_iso = expiry_date.isoformat()
                    cand = next(
                        (t for t in sorted(hourly_close_by_ts.keys()) if t[:10] >= expiry_iso),
                        None,
                    )
                    lot.max_hold_exit_ts = cand
                open_stacks[trade_id].append(lot)
            continue

        # TP1 → set BE on runners of this trade_id
        if reason == "target" and trade_id not in tp1_be:
            tp1_be[trade_id] = ts
            # Mark all open runner lots on this trade_id
            for lot in open_stacks.get(trade_id, []):
                if lot.is_runner and lot.be_ts is None:
                    lot.be_ts = ts

        # Closing fill — FIFO within trade_id stack
        close_side = "buy" if side == "buy" else "sell"
        # Opposite open side
        open_side = "sell" if close_side == "buy" else "buy"
        stack = open_stacks.get(trade_id, [])
        for _ in range(qty):
            match = next((i for i, lot in enumerate(stack) if lot.side == open_side), None)
            if match is None:
                # Try cross-trade FIFO fallback
                for tid, tstack in open_stacks.items():
                    match2 = next((i for i, lot in enumerate(tstack) if lot.side == open_side), None)
                    if match2 is not None:
                        lot = tstack.pop(match2)
                        lot.exit_ts = ts
                        lot.exit_price = price
                        lot.exit_reason = reason
                        closed.append(lot)
                        break
                continue
            lot = stack.pop(match)
            lot.exit_ts = ts
            lot.exit_price = price
            lot.exit_reason = reason
            closed.append(lot)

    # Force-close any still-open lots at the last available bar close
    last_ts = max(hourly_close_by_ts.keys()) if hourly_close_by_ts else ""
    last_px = hourly_close_by_ts.get(last_ts, 0.0)
    for stack in open_stacks.values():
        for lot in stack:
            lot.exit_ts = last_ts
            lot.exit_price = last_px
            lot.exit_reason = "forced_flat_postprocess"
            closed.append(lot)

    return closed, tp1_be


def _dual_dd_pass(
    lots: List[_Lot],
    hourly_rows: List[Dict[str, Any]],
    stop_pts: float,
    max_hold_days: int,
    point_value: float = _POINT_VALUE,
    fee_per_unit: float = 1.5,
) -> Dict[str, Any]:
    """Sweep hourly equity timeline for 3 accounting modes.

    Modes:
      raw          - full open MTM at intrabar stress (conservative low/high)
      occluded     - each lot clipped to its live protective stop
      excluded     - open runner lots omitted from open MTM

    Returns dict with equity path arrays (list of dicts) and summary stats.
    """
    if not lots:
        return {"error": "no lots"}

    # Build quick lookups from hourly equity curve
    ts_sorted = [r["ts"] for r in hourly_rows]
    ts_set = set(ts_sorted)
    close_by_ts: Dict[str, float] = {r["ts"]: float(r["close_equity_points"]) * point_value for r in hourly_rows}
    intrabar_by_ts: Dict[str, float] = {r["ts"]: float(r["intrabar_stress_points"]) * point_value for r in hourly_rows}
    bar_low_by_ts: Dict[str, float] = {}
    bar_high_by_ts: Dict[str, float] = {}
    bar_close_px_by_ts: Dict[str, float] = {}
    for r in hourly_rows:
        t = r["ts"]
        bar_low_by_ts[t] = float(r.get("bar_low") or r.get("low") or 0.0)
        bar_high_by_ts[t] = float(r.get("bar_high") or r.get("high") or 0.0)
        bar_close_px_by_ts[t] = float(r.get("bar_close") or r.get("close") or 0.0)

    # Sort lots by entry/exit
    by_entry = sorted(lots, key=lambda lo: (lo.entry_ts, lo.unit_id))
    by_exit = sorted(lots, key=lambda lo: (lo.exit_ts or "", lo.unit_id))

    # For each timeline step track active lots and compute 3 equity paths
    entry_idx = 0
    exit_idx = 0
    active: List[_Lot] = []
    realized_usd = 0.0

    peak_raw = peak_occ = peak_exc = 0.0
    max_dd_raw = max_dd_occ = max_dd_exc = 0.0

    equity_rows = []
    financing_rows = []

    # Running financing total (applied end-of-day but approximated here hourly per lot opened)
    # We accumulate per-lot per-calendar-day once, outside the equity path loop.
    # Calculate per lot: notional = entry_price * point_value; accrue nightly.
    # We'll compute the full financing path in a second pass.
    daily_financing_by_date: Dict[str, float] = defaultdict(float)

    for ts in ts_sorted:
        bar_date = ts[:10]
        bar_low = bar_low_by_ts.get(ts, 0.0)
        bar_high = bar_high_by_ts.get(ts, 0.0)
        bar_close_px = bar_close_px_by_ts.get(ts, 0.0)

        # Advance entries
        while entry_idx < len(by_entry) and by_entry[entry_idx].entry_ts <= ts:
            active.append(by_entry[entry_idx])
            entry_idx += 1

        # Advance exits (for max-hold, check if overridden)
        while exit_idx < len(by_exit):
            lo = by_exit[exit_idx]
            exit_ts = lo.exit_ts or ""
            # Use max_hold_exit_ts if it comes before the actual exit
            eff_exit = lo.max_hold_exit_ts if (
                lo.max_hold_exit_ts and lo.max_hold_exit_ts < exit_ts and max_hold_days > 0
            ) else exit_ts
            if eff_exit > ts:
                break
            pts = (eff_exit and bar_close_px_by_ts.get(eff_exit) or lo.exit_price or 0.0)
            eff_exit_price = bar_close_px_by_ts.get(eff_exit, lo.exit_price or bar_close_px)
            realized_usd += (eff_exit_price - lo.entry_price) * lo.sign * point_value - fee_per_unit
            try:
                active.remove(lo)
            except ValueError:
                pass
            exit_idx += 1

        # Financing for lots open at end of this bar (daily, once per calendar date change)
        # Simplified: accrue at each unique date for each active lot.
        # We track it separately in daily_financing_by_date below.

        # Open MTM contributions
        open_raw_pts = 0.0
        open_occ_pts = 0.0
        open_exc_pts = 0.0
        open_units_total = len(active)
        open_runner_units = 0

        for lo in active:
            # Use intrabar worst-case: long → low; short → high
            worst_px = bar_low if lo.side == "buy" else bar_high
            raw_pts = (worst_px - lo.entry_price) * lo.sign
            open_raw_pts += raw_pts

            # occluded: clip adverse MTM at protective stop
            stop_px = lo.live_stop(ts, stop_pts)
            if lo.side == "buy":
                eff_worst = max(stop_px, worst_px)
            else:
                eff_worst = min(stop_px, worst_px)
            occ_pts = (eff_worst - lo.entry_price) * lo.sign
            open_occ_pts += occ_pts

            if lo.is_runner:
                open_runner_units += 1
                # excluded mode: skip runner lots from open
            else:
                open_exc_pts += raw_pts

        raw_eq = realized_usd + open_raw_pts * point_value
        occ_eq = realized_usd + open_occ_pts * point_value
        exc_eq = realized_usd + open_exc_pts * point_value

        peak_raw = max(peak_raw, raw_eq)
        peak_occ = max(peak_occ, occ_eq)
        peak_exc = max(peak_exc, exc_eq)
        max_dd_raw = min(max_dd_raw, raw_eq - peak_raw)
        max_dd_occ = min(max_dd_occ, occ_eq - peak_occ)
        max_dd_exc = min(max_dd_exc, exc_eq - peak_exc)

        equity_rows.append({
            "ts": ts,
            "realized_usd": round(realized_usd, 2),
            "raw_eq": round(raw_eq, 2),
            "occ_eq": round(occ_eq, 2),
            "exc_eq": round(exc_eq, 2),
            "open_units": open_units_total,
            "open_runner_units": open_runner_units,
            "raw_dd": round(raw_eq - peak_raw, 2),
            "occ_dd": round(occ_eq - peak_occ, 2),
            "exc_dd": round(exc_eq - peak_exc, 2),
        })

    # Financing second pass: for each lot compute per-date accrual
    financing_total = 0.0
    lot_financing: List[Dict[str, Any]] = []
    for lo in lots:
        entry_d = lo.entry_date
        eff_exit_ts = lo.exit_ts or ""
        if lo.max_hold_exit_ts and lo.max_hold_exit_ts < eff_exit_ts and max_hold_days > 0:
            eff_exit_ts = lo.max_hold_exit_ts
        exit_d = _parse_dt(eff_exit_ts) if eff_exit_ts else entry_d
        d = entry_d
        lot_fin = 0.0
        while d < exit_d:
            notional = lo.entry_price * point_value
            daily_fin = _financing_daily(notional, lo.side, d)
            lot_fin += daily_fin
            daily_financing_by_date[d.isoformat()] += daily_fin
            d += timedelta(days=1)
        financing_total += lot_fin
        lot_financing.append({
            "trade_id": lo.trade_id,
            "unit_id": lo.unit_id,
            "is_runner": lo.is_runner,
            "side": lo.side,
            "entry_ts": lo.entry_ts,
            "exit_ts": eff_exit_ts,
            "hold_days": (exit_d - entry_d).days,
            "entry_price": lo.entry_price,
            "financing_usd": round(lot_fin, 4),
        })

    # Max hold stats
    runner_lots = [lo for lo in lots if lo.is_runner]
    max_hold_exits = sum(
        1 for lo in runner_lots
        if lo.max_hold_exit_ts and lo.max_hold_exit_ts < (lo.exit_ts or "")
        and max_hold_days > 0
    )

    net_usd = realized_usd  # at end of timeline
    net_with_financing = net_usd + financing_total

    return {
        "net_usd": round(net_usd, 2),
        "financing_total_usd": round(financing_total, 4),
        "net_with_financing_usd": round(net_with_financing, 2),
        "max_dd_raw_usd": round(max_dd_raw, 2),
        "max_dd_occluded_usd": round(max_dd_occ, 2),
        "max_dd_excluded_usd": round(max_dd_exc, 2),
        "ns_raw": round(net_usd / abs(max_dd_raw), 3) if max_dd_raw else 0.0,
        "ns_occluded": round(net_usd / abs(max_dd_occ), 3) if max_dd_occ else 0.0,
        "ns_excluded": round(net_usd / abs(max_dd_exc), 3) if max_dd_exc else 0.0,
        "ns_raw_fin": round(net_with_financing / abs(max_dd_raw), 3) if max_dd_raw else 0.0,
        "n_lots": len(lots),
        "n_runner_lots": len(runner_lots),
        "max_hold_exits": max_hold_exits,
        "equity_path": equity_rows,
        "lot_financing": lot_financing,
        "financing_by_date": dict(daily_financing_by_date),
        "sofr_rate_pa": SOFR_RATE,
        "admin_fee_pa": ADMIN_FEE,
        "long_rate_pa": LONG_RATE_PA,
        "short_rate_pa": SHORT_RATE_PA,
    }


def _write_dual_dd_report(hub: Path, dd: Dict[str, Any], max_hold_days: int) -> None:
    lines = [
        "# US30 ST+PMC Indefinite Runner — Dual MTM DD Report",
        "",
        "**Variant:** `sl50_tp150_runners_2r_indef_hold90`  ",
        "**Max hold:** %d calendar days per indefinite runner lot  " % max_hold_days,
        "**Runners block entries:** No  ",
        "",
        "## MTM DD accounting modes",
        "",
        "| Mode | Definition |",
        "|---|---|",
        "| **runner_included (raw)** | Full intrabar stress across all open lots (conservative baseline) |",
        "| **runner_occluded** | Each lot clipped to its live protective stop (hard SL pre-TP1; **BE** after TP1). A runner underwater but above BE stop contributes ≈ 0 — *still green*. |",
        "| **runner_excluded** | Open `runner_entry` lots omitted from MTM entirely; their realised P&L counts when closed. Primary `entry` lots remain in stress. |",
        "",
        "## Results",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Net USD (no financing) | $%.0f |" % dd["net_usd"],
        "| Net USD (with financing) | $%.0f |" % dd["net_with_financing_usd"],
        "| Financing drag (total) | $%.0f |" % dd["financing_total_usd"],
        "| OANDA long rate (annual) | %.1f%% (SOFR %.1f%% + admin 2.5%%) |" % (dd["long_rate_pa"] * 100, dd["sofr_rate_pa"] * 100),
        "| **Max DD raw** | **$%.0f** |" % dd["max_dd_raw_usd"],
        "| **Max DD runner-occluded** | **$%.0f** |" % dd["max_dd_occluded_usd"],
        "| **Max DD runner-excluded** | **$%.0f** |" % dd["max_dd_excluded_usd"],
        "| N/S raw | %.2f |" % dd["ns_raw"],
        "| N/S occluded | %.2f |" % dd["ns_occluded"],
        "| N/S excluded | %.2f |" % dd["ns_excluded"],
        "| N/S raw (after financing) | %.2f |" % dd["ns_raw_fin"],
        "| Total lots | %d |" % dd["n_lots"],
        "| Runner lots | %d |" % dd["n_runner_lots"],
        "| Max-hold exits (≤%d d) | %d |" % (max_hold_days, dd["max_hold_exits"]),
        "",
        "## Financing model",
        "",
        "OANDA overnight financing for US30_USD (index CFD):",
        "- Reference rate: **SOFR** (US Wall St 30 reference per OANDA docs)",
        "- Long rate: SOFR + 2.5%% admin fee = **%.1f%% p.a.**" % (dd["long_rate_pa"] * 100),
        "- Short rate: SOFR \u2212 2.5%% admin fee = **%.1f%% p.a.**" % (dd["short_rate_pa"] * 100),
        "- Weekend: Fridays \u00d7 3 days of standard daily rate",
        "- Static SOFR assumption: **%.1f%%** (2026 research ballpark \u2014 actual varies)" % (dd["sofr_rate_pa"] * 100),
        "- Formula: `notional_usd × annual_rate / 365 × days`",
        "",
        "## Interpretation guide",
        "",
        "- **runner_occluded** is the economic risk capital at stake at each point in time.",
        "  Runners at BE contribute ~0 to drawdown even when underwater — they are 'still green'",
        "  until the BE stop is actually triggered.",
        "- **runner_excluded** treats open runner inventory as off-balance-sheet.",
        "  This answers: 'what is the drawdown if we only count the primary campaign risk?'",
        "- **raw** is the most conservative headline; use for worst-case capital allocation.",
        "- Runners cannot block main system entries (`runners_do_not_block_entries=True`).",
        "",
        "## Artifacts",
        "",
        "- `DUAL_MTM_DD.md` — this report",
        "- `dual_mtm_dd.csv` — per-bar equity paths (raw / occluded / excluded)",
        "- `financing.csv` — per-lot financing accrual",
        "- `summary.csv` — headline metrics",
        "- `states/` — raw fills / strategy state from Engine replay",
        "- `audits/` — broker-like audit reports",
        "",
    ]
    (hub / "DUAL_MTM_DD.md").write_text("\n".join(lines), encoding="utf-8")

    # Write equity path CSV
    eq_fields = ["ts", "realized_usd", "raw_eq", "occ_eq", "exc_eq",
                 "open_units", "open_runner_units", "raw_dd", "occ_dd", "exc_dd"]
    with (hub / "dual_mtm_dd.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=eq_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(dd["equity_path"])

    # Write financing CSV
    fin_fields = ["trade_id", "unit_id", "is_runner", "side", "entry_ts", "exit_ts",
                  "hold_days", "entry_price", "financing_usd"]
    with (hub / "financing.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fin_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(dd["lot_financing"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="Re-run even if hub exists")
    ap.add_argument("--email", action="store_true", help="Email completion summary")
    args = ap.parse_args()

    POINT_VALUES[SYM] = _POINT_VALUE
    DEFAULT_TICK_SIZE[SYM] = TICK
    OUT.mkdir(parents=True, exist_ok=True)

    one_m_path = REPO / "fx" / "us30_1m.csv"
    daily = REPO / "fx" / "us30_daily.csv"

    print("Loading US30 1m → hourly…", flush=True)
    bars, one_m_df = _load_bars()
    print("Hourly bars: %d  1m bars: %d" % (len(bars), len(one_m_df)), flush=True)

    from . import hourly_st_pmc_strategyplugin_variants as hsv
    hsv.TICK_SIZE[SYM] = TICK

    tp = 150.0
    cfg = VariantConfig(
        "sl50_tp150_runners_2r_indef_hold90",
        stop_pts=50.0,
        tp1_pts=tp,
        tp1_qty=1,
        runner_specs=((1, 2.0 * tp), (1, None)),
        runner_stop_to_be_after_tp1=True,
        year_end_flatten_runners=True,
        runners_do_not_block_entries=True,
        notes=(
            "3 units: TP150 + runner@300 + indefinite; SL→BE after TP1; "
            "EOY flatten safety net; indefinite runners do not block later campaigns; "
            "max hold %d days applied in postprocess" % MAX_RUNNER_HOLD_DAYS
        ),
    )

    rid = begin_run(
        run_class="broker_like",
        variant_slug="us30_st_pmc_runners_2r_indef_hold90",
        instrument=SYM,
        hub_path=str(OUT),
        notes="Indefinite runner dual-DD study; max hold %d days; OANDA financing" % MAX_RUNNER_HOLD_DAYS,
    )

    try:
        print("RUN %s (max_contracts=%d)" % (cfg.name, cfg.max_contracts), flush=True)
        result = run_variant(
            cfg=cfg,
            bars=bars,
            output_root=OUT,
            dbn=one_m_path,
            daily_path=daily,
            instrument=SYM,
            market="us30",
            force=bool(args.force),
            quiet=True,
            one_m=one_m_df,
        )
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        fail_run(rid, notes=tb[-2000:])
        if args.email:
            send_email(
                subject="potions: US30 indef hold90 FAILED",
                body="Hub: %s\n\nTraceback:\n%s" % (OUT, tb),
            )
        raise

    a = result.audit
    stress = float(a.intrabar_mtm_dd_usd or a.close_mtm_dd_usd or 0.0)
    ns_raw = (a.net_usd / abs(stress)) if stress else 0.0
    wr = (100.0 * float(a.win_units) / float(a.units)) if a.units else 0.0

    print(
        "Engine audit: Net=$%.0f Stress=$%.0f N/S=%.2f units=%d WR=%.1f%% max_open=%d"
        % (a.net_usd, stress, ns_raw, a.units, wr, a.max_open_units),
        flush=True,
    )

    # ------------------------------------------------------------------
    # Dual-DD postprocess
    # ------------------------------------------------------------------
    fills_path = result.state_root / "fills.csv"
    equity_curve_path = OUT / "audits" / result.strategy_id / result.strategy_id / "equity_curve.csv"

    # Build hourly close lookup for max-hold expiry resolution
    ec_rows = _read_csv(equity_curve_path)
    hourly_close_px: Dict[str, float] = {}
    for r in ec_rows:
        # bar close price needed for max-hold flatten; stored as 'bar_close' or derive from equity delta
        # Use the engine bar close from audit curve if available
        pass
    # Fallback: read from hourly bars directly
    hourly_close_px = {b.ts: b.close for b in bars}

    strategy_id = result.strategy_id
    print("Postprocess: building lot timeline (max_hold=%d days)…" % MAX_RUNNER_HOLD_DAYS, flush=True)
    lots, tp1_be = _build_lots_timeline(
        fills_path,
        strategy_id,
        stop_pts=cfg.stop_pts,
        max_hold_days=MAX_RUNNER_HOLD_DAYS,
        hourly_close_by_ts=hourly_close_px,
    )
    print("Lots matched: %d" % len(lots), flush=True)

    # Enrich ec_rows with bar low/high/close for the occluded pass
    bar_map: Dict[str, Bar] = {b.ts: b for b in bars}
    for r in ec_rows:
        t = r["ts"]
        b = bar_map.get(t)
        if b:
            r["low"] = b.low
            r["high"] = b.high
            r["close"] = b.close
            r["bar_low"] = b.low
            r["bar_high"] = b.high
            r["bar_close"] = b.close

    print("Computing dual-DD paths…", flush=True)
    dd = _dual_dd_pass(
        lots=lots,
        hourly_rows=ec_rows,
        stop_pts=cfg.stop_pts,
        max_hold_days=MAX_RUNNER_HOLD_DAYS,
        point_value=_POINT_VALUE,
    )

    print(
        "Dual-DD: raw=$%.0f  occluded=$%.0f  excluded=$%.0f  financing=$%.0f  N/S raw/occ/exc=%.2f/%.2f/%.2f"
        % (
            dd["max_dd_raw_usd"],
            dd["max_dd_occluded_usd"],
            dd["max_dd_excluded_usd"],
            dd["financing_total_usd"],
            dd["ns_raw"],
            dd["ns_occluded"],
            dd["ns_excluded"],
        ),
        flush=True,
    )

    _write_dual_dd_report(OUT, dd, MAX_RUNNER_HOLD_DAYS)

    # summary CSV
    summary_row = {
        "variant": cfg.name,
        "units": a.units,
        "trades": a.trades,
        "net_usd": round(a.net_usd, 2),
        "net_with_financing_usd": dd["net_with_financing_usd"],
        "financing_total_usd": dd["financing_total_usd"],
        "stress_dd_raw_usd": round(dd["max_dd_raw_usd"], 2),
        "stress_dd_occluded_usd": round(dd["max_dd_occluded_usd"], 2),
        "stress_dd_excluded_usd": round(dd["max_dd_excluded_usd"], 2),
        "ns_raw": dd["ns_raw"],
        "ns_occluded": dd["ns_occluded"],
        "ns_excluded": dd["ns_excluded"],
        "ns_raw_fin": dd["ns_raw_fin"],
        "wr_pct": round(wr, 1),
        "max_open": a.max_open_units,
        "n_runner_lots": dd["n_runner_lots"],
        "max_hold_exits": dd["max_hold_exits"],
        "max_hold_days": MAX_RUNNER_HOLD_DAYS,
        "sofr_rate_pa": dd["sofr_rate_pa"],
        "long_rate_pa": dd["long_rate_pa"],
        "notes": cfg.notes,
    }
    with (OUT / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(summary_row.keys()))
        w.writeheader()
        w.writerow(summary_row)

    # summary markdown
    lines = [
        "# US30 ST+PMC Indefinite Runner — Hold-90 Dual-DD Study",
        "",
        "**Hub:** `live/state/us30_st_pmc_runners_2r_indef_hold90/`  ",
        "**Date:** %s  " % date.today().isoformat(),
        "",
        "## Strategy rules",
        "",
        "- Entry: resting limit @ hourly ST stop when above/below prior-month close",
        "- 3 units per campaign: TP1 @ 150 pts (1u) + 2R runner @ 300 pts (1u) + indefinite runner (1u)",
        "- Both runners: SL → BE after TP1 fills",
        "- Runners do not block later campaigns",
        "- Max hold per indefinite runner lot: **%d calendar days** (postprocess)" % MAX_RUNNER_HOLD_DAYS,
        "- Safety net: year-end flatten",
        "- OANDA overnight financing applied in postprocess",
        "",
        "## Headline metrics",
        "",
        "| | Value |",
        "|---|---:|",
        "| Net USD | $%.0f |" % a.net_usd,
        "| Net USD (after financing) | $%.0f |" % dd["net_with_financing_usd"],
        "| Financing drag | $%.0f |" % dd["financing_total_usd"],
        "| Units (all lots) | %d |" % a.units,
        "| Trades (campaigns) | %d |" % a.trades,
        "| WR | %.1f%% |" % wr,
        "| Max open units | %d |" % a.max_open_units,
        "| Runner lots | %d |" % dd["n_runner_lots"],
        "| Max-hold exits | %d |" % dd["max_hold_exits"],
        "",
        "## Dual MTM DD table",
        "",
        "| Accounting mode | Max DD | N/S |",
        "|---|---:|---:|",
        "| **raw (full open MTM)** | $%.0f | %.2f |" % (dd["max_dd_raw_usd"], dd["ns_raw"]),
        "| **runner-occluded** | $%.0f | %.2f |" % (dd["max_dd_occluded_usd"], dd["ns_occluded"]),
        "| **runner-excluded** | $%.0f | %.2f |" % (dd["max_dd_excluded_usd"], dd["ns_excluded"]),
        "| raw (after financing drag) | — | %.2f |" % dd["ns_raw_fin"],
        "",
        "## Interpretation",
        "",
        "- **runner-occluded**: runners at BE count ≈ 0. Drawdown measures what is",
        "  economically at risk. Preferred risk metric for position-sizing.",
        "- **runner-excluded**: open runner P&L is off-balance-sheet. Shows pure main-system stress.",
        "- **raw**: most conservative; counts full unrealised swing against you.",
        "- Financing drag of **$%.0f** over %d years" % (
            dd["financing_total_usd"],
            max(1, len(set(r["ts"][:4] for r in ec_rows))),
        ) + " (SOFR %.1f%% + 2.5%% admin = %.1f%% long rate)." % (
            dd["sofr_rate_pa"] * 100,
            dd["long_rate_pa"] * 100,
        ),
        "",
        "## Artifacts",
        "",
        "- `DUAL_MTM_DD.md` — accounting mode definitions",
        "- `dual_mtm_dd.csv` — per-bar equity paths",
        "- `financing.csv` — per-lot overnight financing accrual",
        "- `summary.csv` — headline row",
        "- `states/` — raw fills + state",
        "- `audits/` — engine audit reports",
        "",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote SUMMARY.md and DUAL_MTM_DD.md", flush=True)

    # complete run ledger
    complete_run(
        rid,
        net_usd=a.net_usd,
        stress_dd_usd=stress,
        close_mtm_dd_usd=a.close_mtm_dd_usd,
        ns=ns_raw,
        trades=a.trades,
        units=a.units,
        hub_path=str(OUT),
        equity_curve_path=equity_curve_path,
        notes="dual-DD: occ=$%.0f exc=$%.0f fin=$%.0f" % (
            dd["max_dd_occluded_usd"],
            dd["max_dd_excluded_usd"],
            dd["financing_total_usd"],
        ),
        meta={
            "max_hold_days": MAX_RUNNER_HOLD_DAYS,
            "ns_occluded": dd["ns_occluded"],
            "ns_excluded": dd["ns_excluded"],
            "ns_raw_fin": dd["ns_raw_fin"],
            "max_dd_occluded_usd": dd["max_dd_occluded_usd"],
            "max_dd_excluded_usd": dd["max_dd_excluded_usd"],
            "financing_total_usd": dd["financing_total_usd"],
            "n_runner_lots": dd["n_runner_lots"],
            "max_hold_exits": dd["max_hold_exits"],
        },
    )
    print("Ledger row complete: %s" % rid, flush=True)

    email_body = """\
potions: US30 ST+PMC indef runner hold-90 study complete
Hub: %s
Variant: %s

Engine audit (raw EOY-flatten baseline):
  Net:           $%.0f
  Max stress DD: $%.0f
  N/S:           %.2f
  Units:         %d
  WR:            %.1f%%
  Max open:      %d

Dual MTM DD postprocess (max hold %d days, OANDA financing):
  Net (no financing):   $%.0f
  Net (w/ financing):   $%.0f
  Financing drag:       $%.0f  (SOFR %.1f%% + 2.5%% admin = %.1f%% long)
  Max DD raw:           $%.0f  (N/S %.2f)
  Max DD occluded:      $%.0f  (N/S %.2f)  [runners at BE = ~0 DD]
  Max DD excluded:      $%.0f  (N/S %.2f)  [runners off-balance-sheet]
  Max-hold exits:       %d / %d runner lots

Stance: RESEARCH / inventory sleeve (not N/S-ranked vs capped 3R/10R)
Runners do NOT block main system entries.
""" % (
        OUT,
        cfg.name,
        a.net_usd,
        stress,
        ns_raw,
        a.units,
        wr,
        a.max_open_units,
        MAX_RUNNER_HOLD_DAYS,
        dd["net_usd"],
        dd["net_with_financing_usd"],
        dd["financing_total_usd"],
        dd["sofr_rate_pa"] * 100,
        dd["long_rate_pa"] * 100,
        dd["max_dd_raw_usd"],
        dd["ns_raw"],
        dd["max_dd_occluded_usd"],
        dd["ns_occluded"],
        dd["max_dd_excluded_usd"],
        dd["ns_excluded"],
        dd["max_hold_exits"],
        dd["n_runner_lots"],
    )

    (OUT / "EMAIL.txt").write_text(email_body, encoding="utf-8")

    if args.email:
        send_email(
            subject="potions: US30 indef runner hold90 dual-DD complete",
            body=email_body,
        )
        print("Email sent.", flush=True)

    print("\nDone. Hub: %s" % OUT, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
