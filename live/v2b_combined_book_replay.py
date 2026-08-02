"""Causal combined-book replay: prior-opposed resting-limit core + v2b satellite.

The tape-overlay study showed the prior-opposed resting-limit book (B) and the
all-days v2b S_1_1_3 book (A) are ~0.88 correlated on days both trade, while
A restricted to non-gate days is ~0 correlated with B. This driver makes that
combination causal:

- Core leg B: the promoted resting-limit Engine+PaperBroker book is reused
  as-is (its units come from its own fills.csv; 0 causality violations per
  its LOOKAHEAD_REVIEW).
- Satellite leg A: v2b S_1_1_3 re-replayed through Engine+PaperBroker with
  ``regime_dates`` restricted by a decision knowable at 09:45 arm time:
  trade only if NO prior-opposed gate limit is already resting (any event in
  B's ``dynamic_sizing_events`` for the session with ``available_at_ts`` <=
  09:45 NY). Gate limits that arm later in the session cannot retroactively
  cancel the satellite's ~09:47 entry, so those days may causally carry both
  legs — the audit prices that overlap honestly.
- Optional flat-gap skip on the satellite (OR-profile P1 policy, also
  09:45-knowable).

All portfolio variants are audited on one union bar tape (dense RTH 1m over
every participating day) with merged units, so closed net, closed DD and
intrabar stress DD are directly comparable.

Usage (from repo root):
  python -m live.v2b_combined_book_replay --market nq
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple

import pandas as pd

from .bars import rth_bars
from .or_profile_v2b_join import SIZING_TIERS, replay_dates
from .v2b_strategy_cross_market_replay import MARKETS, _regime_dates, load_1m_by_ny_date_any
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills

REPO = Path(__file__).resolve().parents[1]
ENGINE_SESSIONS = REPO / "live" / "state" / "or_profile_engine" / "%s" / "2026H2" / "sessions.csv"
A_TAPE_STATE = REPO / "live" / "state" / "v2b_sizing_sweep" / "states" / "%s_v2b_sizing_S_1_1_3"
B_STATE = {
    "nq": REPO
    / "live/state/nq_v2b_prior_opposed_causal_proxies/resting_limit/states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3",
    "mnq": REPO
    / "live/state/mnq_v2b_prior_opposed_stpmc_resting_limit/states/mnq_v2b_prior_opposed_stpmc_only_S_1_1_3",
}
WINDOW_START = date(2021, 3, 4)  # A tape start (common cross-market baseline)
ARM_TIME = time(9, 45)


def _unit_day(u) -> date:
    return datetime.fromisoformat(u.entry_ts).date()


def load_b_units_and_gates(market: str) -> Tuple[List[object], Dict[date, List[dict]]]:
    state = B_STATE[market]
    units = units_from_v2b_fills(state / "fills.csv", "%s_prior_opposed_rl" % market)
    si = pd.read_csv(state / "strategy_instances.csv")
    cfg = json.loads(si.iloc[0]["config_json"])
    gates: Dict[date, List[dict]] = {}
    for session, events in (cfg.get("dynamic_sizing_events") or {}).items():
        gates[date.fromisoformat(session)] = list(events)
    return units, gates


def gate_armed_by_0945(day: date, gates: Dict[date, List[dict]]) -> bool:
    events = gates.get(day, [])
    cutoff_naive = datetime.combine(day, ARM_TIME)
    for ev in events:
        raw = str(ev.get("available_at_ts") or ev.get("ts") or "")
        if not raw:
            continue
        try:
            ts = datetime.fromisoformat(raw)
        except ValueError:
            continue
        if ts.replace(tzinfo=None) <= cutoff_naive:
            return True
    return False


def build_union_bars(cfg, gby, days: Sequence[date]) -> List[AuditBar]:
    bars: List[AuditBar] = []
    for day in sorted(days):
        df = rth_bars(gby.get(day), day, dense=True)
        if df.empty:
            continue
        for ts, row in df.iterrows():
            bars.append(
                AuditBar(
                    pd.Timestamp(ts).isoformat(),
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                )
            )
    return bars


def main() -> None:
    ap = argparse.ArgumentParser(description="Causal combined-book replay (prior-opposed RL + v2b satellite)")
    ap.add_argument("--market", default="nq", choices=sorted(B_STATE))
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    market = args.market
    cfg = MARKETS[market]
    out_root = args.out or (REPO / "live" / "state" / ("%s_v2b_combined_book_causal" % market))
    out_root.mkdir(parents=True, exist_ok=True)

    b_units_all, gates = load_b_units_and_gates(market)
    a_units_all = units_from_v2b_fills(Path(str(A_TAPE_STATE) % market) / "fills.csv", "%s_v2b_all_days" % market)

    window_end = min(max(_unit_day(u) for u in b_units_all), max(_unit_day(u) for u in a_units_all))
    b_units = [u for u in b_units_all if WINDOW_START <= _unit_day(u) <= window_end]
    a_units_full = [u for u in a_units_all if WINDOW_START <= _unit_day(u) <= window_end]
    print(
        "%s window %s -> %s: B units %d, A(all-days) units %d"
        % (market.upper(), WINDOW_START, window_end, len(b_units), len(a_units_full)),
        flush=True,
    )

    sessions = pd.read_csv(str(ENGINE_SESSIONS) % market, keep_default_na=False)
    touch = sessions[sessions["trigger"] == "touch"]
    flat_days: Set[date] = set(pd.to_datetime(touch[touch["gap_bucket"] == "flat"]["session_date"]).dt.date)

    print("Loading %s 1m for satellite replays..." % cfg.instrument, flush=True)
    gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)
    regime = [d for d in _regime_dates(cfg, gby) if WINDOW_START <= d <= window_end]
    armed = {d for d in regime if gate_armed_by_0945(d, gates)}
    comp_days = [d for d in regime if d not in armed]
    comp_skipflat_days = [d for d in comp_days if d not in flat_days]
    print(
        "  regime days %d | gate armed by 09:45 %d | complement %d | complement+skipflat %d"
        % (len(regime), len(armed), len(comp_days), len(comp_skipflat_days)),
        flush=True,
    )

    replays = {
        "A_comp": comp_days,
        "A_comp_skipflat": comp_skipflat_days,
    }
    leg_units: Dict[str, List[object]] = {"B": b_units, "A_full": a_units_full}
    for name, days in replays.items():
        print("  replaying %s (%d sessions)..." % (name, len(days)), flush=True)
        units, _bars, _root = replay_dates(
            cfg, gby, days, SIZING_TIERS["1x"], "%s_%s" % (market, name.lower()), out_root / "states"
        )
        leg_units[name] = list(units)
        print("    %s: %d units" % (name, len(units)), flush=True)

    portfolios = {
        "B_only": ["B"],
        "A_full_only": ["A_full"],
        "B_plus_A_full_stack": ["B", "A_full"],
        "B_plus_A_complement": ["B", "A_comp"],
        "B_plus_A_complement_skipflat": ["B", "A_comp_skipflat"],
    }

    union_days: Set[date] = set(regime) | {_unit_day(u) for u in b_units}
    print("Building union audit bar tape (%d days)..." % len(union_days), flush=True)
    bars = build_union_bars(cfg, gby, sorted(union_days))

    rows: List[Dict[str, object]] = []
    for pname, legs in portfolios.items():
        units = [u for leg in legs for u in leg_units[leg]]
        audit_root = out_root / "audits" / pname
        audit_root.mkdir(parents=True, exist_ok=True)
        audit = fast_intraday_audit(
            strategy_id="%s_%s" % (market, pname),
            state_root=audit_root,
            bars=bars,
            units=units,
            instrument=cfg.instrument,
            fee_per_unit=cfg.fee_per_unit,
        )
        net = float(audit["net_usd"])
        stress = float(audit["intrabar_stress_dd_usd"])
        rows.append(
            {
                "portfolio": pname,
                "legs": "+".join(legs),
                "units": len(units),
                "traded_days": len({_unit_day(u) for u in units}),
                "net_usd": round(net, 2),
                "closed_dd_usd": round(float(audit["closed_dd_usd"]), 2),
                "intrabar_stress_dd_usd": round(stress, 2),
                "net_over_stress": round(net / abs(stress), 2) if stress else "",
                "max_open_units": int(audit["max_open_units"]),
                "win_rate_pct": round(float(audit["win_rate"]), 2),
                "profit_factor": round(float(audit["profit_factor"]), 3)
                if math.isfinite(float(audit["profit_factor"]))
                else "inf",
            }
        )
        print(
            "  %s: net $%.0f stress $%.0f N/S %s"
            % (pname, net, stress, rows[-1]["net_over_stress"]),
            flush=True,
        )
        pd.DataFrame(rows).to_csv(out_root / "portfolio_summary.csv", index=False)

    df = pd.DataFrame(rows)
    lines = [
        "# %s combined book — causal Engine+PaperBroker replay" % market.upper(),
        "",
        "Window %s -> %s. Core = prior-opposed resting-limit S_1_1_3 (promoted causal book, units from its own"
        % (WINDOW_START, window_end),
        "Engine+PaperBroker fills). Satellite = all-days v2b S_1_1_3 replayed via Engine+PaperBroker with",
        "`regime_dates` restricted to days where **no gate limit was resting at 09:45** (available_at_ts from the",
        "core's dynamic_sizing_events; gates arming later in the day may causally overlap and are kept).",
        "`skipflat` additionally drops flat-gap days (OR-profile P1, 09:45-knowable). All portfolios audited on one",
        "union 1m bar tape with merged units; hardened realism (1-tick slippage, $%.2f/RT)." % cfg.fee_per_unit,
        "",
        "| Portfolio | Legs | Units | Traded days | Net | Closed DD | Stress DD | N/S | Max open | Win % | PF |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in df.iterrows():
        lines.append(
            "| %s | %s | %d | %d | $%s | $%s | $%s | %s | %d | %s | %s |"
            % (
                r["portfolio"],
                r["legs"],
                r["units"],
                r["traded_days"],
                f"{r['net_usd']:,.0f}",
                f"{r['closed_dd_usd']:,.0f}",
                f"{r['intrabar_stress_dd_usd']:,.0f}",
                r["net_over_stress"],
                r["max_open_units"],
                r["win_rate_pct"],
                r["profit_factor"],
            )
        )
    (out_root / "SUMMARY.md").write_text("\n".join(lines))
    print("Outputs -> %s" % out_root, flush=True)


if __name__ == "__main__":
    main()
