"""EURUSD monthly ORB — v2b-style OCO + 1/1/2 scaleout (pandas daily).

Rules
-----
- OR = first ``or_sessions`` daily bars of the calendar month (default 3).
- After OR forms: OCO stop entry long @ ORH / short @ ORL.
- Max ``max_trades_per_month`` campaigns (default 2). Re-arm when flat if room left.
- Same-bar dual touch → no entry that day.
- Structure **S_1_1_2** (entry 4): 1 @ TP1=1R, 1 @ TP2=2R, 2 runner.
  TP25 language: 25% of size at TP1.
- After TP1: remaining stop → breakeven (entry).
- Initial SL = opposite OR boundary.
- **Stop mode close:** wicks through SL ignored; exit only if daily **close**
  is beyond SL.
- Flatten all at month-end close.

R = OR width. Fee $7/unit, PV $100k (1 lot unit).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .ym_hourly_st_pmc_retest_replay import concat_all_1m


REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "eurusd_monthly_orb_v2b_oco"
NY = "America/New_York"
POINT_VALUE = 100_000.0
FEE = 7.0  # match EURUSD monthly ORB / overnight sweep unit fee
ENTRY_QTY = 4
TP1_QTY = 1
TP2_QTY = 1
# runner = 2


@dataclass
class Leg:
    qty: int
    role: str  # tp1 | tp2 | runner
    target: Optional[float]
    open: bool = True


@dataclass
class Campaign:
    side: str
    entry_ts: pd.Timestamp
    entry: float
    stop: float
    r: float
    or_high: float
    or_low: float
    legs: List[Leg] = field(default_factory=list)
    month_key: str = ""
    tp1_hit: bool = False


@dataclass
class ClosedTrade:
    strategy: str
    side: str
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry: float
    exit: float
    qty: float
    reason: str
    usd: float
    month_key: str
    n_units: int


def _pnl(side: str, entry: float, exit_: float, qty: float) -> float:
    pts = (exit_ - entry) * qty if side == "long" else (entry - exit_) * qty
    return pts * POINT_VALUE - FEE * abs(qty)


def _daily(one_m: pd.DataFrame) -> pd.DataFrame:
    d = one_m.copy()
    d["ny"] = d.index.tz_convert(NY).date
    out = (
        d.groupby("ny")
        .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
        .sort_index()
    )
    out.index = pd.Index(out.index, name="date")
    return out


def _month_key(d: date) -> str:
    return "%d-%02d" % (d.year, d.month)


def _summarize(trades: Sequence[ClosedTrade], name: str) -> dict:
    if not trades:
        return {
            "strategy": name,
            "trades": 0,
            "units": 0.0,
            "net_usd": 0.0,
            "win_rate_pct": 0.0,
            "closed_dd_usd": 0.0,
            "net_over_closed_dd": 0.0,
            "avg_usd": 0.0,
        }
    usd = np.array([t.usd for t in trades], dtype=float)
    eq = np.cumsum(usd)
    dd = float((eq - np.maximum.accumulate(eq)).min())
    net = float(usd.sum())
    return {
        "strategy": name,
        "trades": len(trades),
        "units": float(sum(t.qty for t in trades)),
        "net_usd": round(net, 2),
        "win_rate_pct": round(100.0 * float((usd > 0).mean()), 2),
        "closed_dd_usd": round(dd, 2),
        "net_over_closed_dd": round(net / abs(dd), 3) if dd else 0.0,
        "avg_usd": round(net / len(trades), 2),
    }


def run(
    daily: pd.DataFrame,
    *,
    or_sessions: int = 3,
    max_trades_per_month: int = 2,
    entry_qty: int = ENTRY_QTY,
    tp1_qty: int = TP1_QTY,
    tp2_qty: int = TP2_QTY,
    name: str = "eurusd_monthly_orb_v2b_s112",
) -> Tuple[List[ClosedTrade], dict]:
    trades: List[ClosedTrade] = []
    camp: Optional[Campaign] = None
    month_trades: Dict[str, int] = {}
    or_high = or_low = None
    or_ready = False
    or_count = 0
    cur_month = ""
    armed = False

    dates = list(daily.index)

    def close_leg(leg: Leg, ts: pd.Timestamp, px: float, reason: str) -> None:
        nonlocal camp
        assert camp is not None
        usd = _pnl(camp.side, camp.entry, px, float(leg.qty))
        trades.append(
            ClosedTrade(
                name,
                camp.side,
                camp.entry_ts,
                ts,
                camp.entry,
                px,
                float(leg.qty),
                "%s:%s" % (reason, leg.role),
                usd,
                camp.month_key,
                leg.qty,
            )
        )
        leg.open = False

    def flatten_all(ts: pd.Timestamp, px: float, reason: str) -> None:
        nonlocal camp, armed
        if camp is None:
            return
        for leg in camp.legs:
            if leg.open:
                close_leg(leg, ts, px, reason)
        camp = None
        armed = False

    def open_units() -> int:
        if camp is None:
            return 0
        return sum(l.qty for l in camp.legs if l.open)

    for d in dates:
        row = daily.loc[d]
        o, h, l, c = float(row.open), float(row.high), float(row.low), float(row.close)
        ts = pd.Timestamp(d, tz=NY)
        mk = _month_key(d)

        # New month → flatten, reset OR
        if mk != cur_month:
            if camp is not None:
                # flatten at prior close already handled on last bar; safety
                flatten_all(ts, o, "month_roll")
            cur_month = mk
            or_high = or_low = None
            or_ready = False
            or_count = 0
            armed = False
            month_trades.setdefault(mk, 0)

        # Build OR
        if not or_ready:
            if or_high is None:
                or_high, or_low = h, l
            else:
                or_high = max(or_high, h)
                or_low = min(or_low, l)
            or_count += 1
            if or_count >= or_sessions:
                or_ready = True
                if or_high > or_low and month_trades[mk] < max_trades_per_month:
                    armed = True
            continue

        # Manage open campaign
        if camp is not None:
            side = camp.side
            stop = camp.stop

            # Targets first (optimistic for same-bar vs stop; stop is close-only so OK)
            for leg in camp.legs:
                if not leg.open or leg.target is None:
                    continue
                hit = (side == "long" and h >= leg.target) or (side == "short" and l <= leg.target)
                if hit:
                    close_leg(leg, ts, float(leg.target), "tp")
                    if leg.role == "tp1" and not camp.tp1_hit:
                        camp.tp1_hit = True
                        camp.stop = camp.entry  # BE for remainder

            # Daily-close stop (wicks ignored)
            stop = camp.stop
            stopped = (side == "long" and c < stop) or (side == "short" and c > stop)
            if stopped and open_units() > 0:
                flatten_all(ts, c, "stop_close")
            elif open_units() == 0:
                camp = None
                armed = False

            # Month-end flatten: last day of month in sample
            # Detect: next date different month or last bar
            # Handled below after we know if next day rolls — do at end of day if last session of month
            pass

        # Month-end: if tomorrow is new month or last bar
        idx = dates.index(d)
        is_month_end = (idx == len(dates) - 1) or (_month_key(dates[idx + 1]) != mk)
        if camp is not None and is_month_end:
            flatten_all(ts, c, "month_end")
            continue

        # Arm / entry when flat
        if camp is not None or not armed or not or_ready:
            # re-arm if flat and room
            if camp is None and or_ready and month_trades[mk] < max_trades_per_month and not armed:
                armed = True
            if camp is not None or not armed:
                continue

        # OCO touch
        long_hit = h >= float(or_high)
        short_hit = l <= float(or_low)
        if long_hit and short_hit:
            continue  # ambiguous
        if not long_hit and not short_hit:
            continue

        side = "long" if long_hit else "short"
        entry = float(or_high) if side == "long" else float(or_low)
        stop0 = float(or_low) if side == "long" else float(or_high)
        r = float(or_high) - float(or_low)
        if r <= 0:
            continue

        # Same-day close already through stop → skip (would die on entry day close)
        if side == "long" and c < stop0:
            continue
        if side == "short" and c > stop0:
            continue

        if side == "long":
            tp1, tp2 = entry + r, entry + 2 * r
        else:
            tp1, tp2 = entry - r, entry - 2 * r

        runner_qty = max(0, int(entry_qty) - int(tp1_qty) - int(tp2_qty))
        legs = []
        if int(tp1_qty) > 0:
            legs.append(Leg(int(tp1_qty), "tp1", tp1))
        if int(tp2_qty) > 0:
            legs.append(Leg(int(tp2_qty), "tp2", tp2))
        if runner_qty > 0:
            legs.append(Leg(runner_qty, "runner", None))
        camp = Campaign(
            side=side,
            entry_ts=ts,
            entry=entry,
            stop=stop0,
            r=r,
            or_high=float(or_high),
            or_low=float(or_low),
            month_key=mk,
            legs=legs,
        )
        month_trades[mk] = month_trades.get(mk, 0) + 1
        armed = False

        # Same-bar TPs after entry
        for leg in camp.legs:
            if not leg.open or leg.target is None:
                continue
            hit = (side == "long" and h >= leg.target) or (side == "short" and l <= leg.target)
            if hit:
                close_leg(leg, ts, float(leg.target), "tp")
                if leg.role == "tp1":
                    camp.tp1_hit = True
                    camp.stop = camp.entry
        # Same-bar close stop
        if camp is not None and open_units() > 0:
            stop = camp.stop
            if (side == "long" and c < stop) or (side == "short" and c > stop):
                flatten_all(ts, c, "stop_close")
        if camp is not None and open_units() == 0:
            camp = None

        # Re-arm for second trade later in month if room
        if camp is None and month_trades[mk] < max_trades_per_month:
            armed = True

    if camp is not None:
        last = dates[-1]
        flatten_all(pd.Timestamp(last, tz=NY), float(daily.loc[last, "close"]), "eod_mark")

    stats = _summarize(trades, name)
    stats["or_sessions"] = or_sessions
    stats["max_trades_per_month"] = max_trades_per_month
    stats["structure"] = "S_%d_%d_%d" % (tp1_qty, tp2_qty, max(0, entry_qty - tp1_qty - tp2_qty))
    stats["stop_mode"] = "daily_close"
    stats["months_traded"] = sum(1 for v in month_trades.values() if v > 0)
    return trades, stats


STRUCTURES = (
    ("S_1_1_2", 4, 1, 1),
    ("S_1_1_1", 3, 1, 1),
    ("S_1_1_0", 2, 1, 1),
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="EURUSD monthly ORB v2b OCO structure sweep")
    parser.add_argument("--start", default="2003-01-01")
    parser.add_argument("--end", default="2026-03-31")
    parser.add_argument("--or-sessions", type=int, default=3)
    parser.add_argument("--max-trades", type=int, default=2)
    parser.add_argument("--output-root", type=Path, default=OUT)
    args = parser.parse_args(list(argv) if argv is not None else None)
    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)

    print("Loading EURUSD daily...", flush=True)
    one_m_path, _ = ensure_eurusd_platform_files(REPO)
    one_m = concat_all_1m(load_fx_1m_by_ny_date(one_m_path, "EURUSD")).sort_index()
    start = pd.Timestamp(args.start, tz=NY)
    end = pd.Timestamp(args.end, tz=NY)
    one_m = one_m[(one_m.index >= start) & (one_m.index <= end)]
    daily = _daily(one_m)
    print("  daily bars:", len(daily), flush=True)

    all_stats = []
    lines = [
        "# EURUSD monthly ORB — v2b OCO structure sweep (pandas, daily-close SL)",
        "",
        "OR = first %d daily sessions. OCO @ ORH/ORL. Max %d trades/month."
        % (args.or_sessions, args.max_trades),
        "TP1=1R, TP2=2R, BE after TP1, daily-close SL, month-end flatten. Fee $7/unit.",
        "",
        "| Structure | Net | Closed DD | Net/DD | Units | WR |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, entry_qty, tp1_qty, tp2_qty in STRUCTURES:
        name = "eurusd_monthly_orb_v2b_%s_close_sl" % label
        print("Running", name, "...", flush=True)
        trades, stats = run(
            daily,
            or_sessions=args.or_sessions,
            max_trades_per_month=args.max_trades,
            entry_qty=entry_qty,
            tp1_qty=tp1_qty,
            tp2_qty=tp2_qty,
            name=name,
        )
        print(json.dumps(stats, indent=2), flush=True)
        all_stats.append(stats)
        tdf = pd.DataFrame([t.__dict__ for t in trades])
        if not tdf.empty:
            tdf.to_csv(out / ("trades_%s.csv" % name), index=False)
        lines.append(
            "| %s | $%s | $%s | %.2f | %.0f | %.1f%% |"
            % (
                label,
                f"{stats['net_usd']:,.0f}",
                f"{stats['closed_dd_usd']:,.0f}",
                stats["net_over_closed_dd"],
                stats["units"],
                stats["win_rate_pct"],
            )
        )
    pd.DataFrame(all_stats).to_csv(out / "leaderboard.csv", index=False)
    (out / "summary.json").write_text(json.dumps(all_stats, indent=2), encoding="utf-8")
    lines.extend(
        [
            "",
            "Pandas only — see broker stress in `live/state/eurusd_monthly_orb_v2b_oco_broker/`.",
            "",
        ]
    )
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote", out / "SUMMARY.md", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
