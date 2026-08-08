"""US30 ST+PMC indefinite runner — equity / DD profile for portfolio risk design.

Reads lot-correct forced-flat equity curve and fills; writes a portfolio-facing
profile: path statistics, drawdown anatomy, open-inventory burden, and a simple
capital / sleeve sizing sketch so the book can sit in a multi-strategy portfolio
with defined risk.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from .replay_audit import POINT_VALUES

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "us30_st_pmc_runner_variants"
SID = "us30_hourly_st_pmc_sl50_tp150_runners_2r_indef"
OUT = HUB / "INDEF_PORTFOLIO_PROFILE"


@dataclass
class PathStats:
    n_bars: int
    terminal_equity: float
    peak_equity: float
    max_dd: float
    max_dd_pct_of_peak: float
    time_underwater_pct: float
    avg_dd: float
    dd_p50: float
    dd_p90: float
    dd_p99: float
    longest_uw_bars: int
    calmar_like: float
    daily_sharpe_approx: float


def _read_equity(path: Path) -> List[Dict[str, float]]:
    rows = []
    with path.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append(
                {
                    "ts": r["ts"],
                    "close_eq": float(r["close_equity_points"]) * POINT_VALUES["US30"],
                    "stress_eq": float(r["intrabar_stress_points"]) * POINT_VALUES["US30"],
                    "realized": float(r["realized_points"]) * POINT_VALUES["US30"],
                    "open_units": float(r["open_units"]),
                    "peak": float(r["peak_close_points"]) * POINT_VALUES["US30"],
                    "close_dd": float(r["close_dd_usd"]),
                    "stress_dd": float(r["intrabar_dd_usd"]),
                }
            )
    return rows


def _path_stats(eq: Sequence[Dict[str, float]], key: str = "close_eq") -> PathStats:
    xs = np.array([r[key] for r in eq], dtype=float)
    peak = np.maximum.accumulate(xs)
    dd = xs - peak  # <= 0
    underwater = dd < -1e-9
    # longest underwater streak
    longest = cur = 0
    for u in underwater:
        if u:
            cur += 1
            longest = max(longest, cur)
        else:
            cur = 0
    # approx daily: take last bar of each NY date
    by_day: Dict[str, float] = {}
    for r in eq:
        by_day[str(r["ts"])[:10]] = float(r[key])
    days = sorted(by_day)
    day_rets = []
    for i in range(1, len(days)):
        a, b = by_day[days[i - 1]], by_day[days[i]]
        day_rets.append(b - a)
    rets = np.array(day_rets, dtype=float) if day_rets else np.array([0.0])
    mu = float(np.mean(rets))
    sd = float(np.std(rets, ddof=1)) if len(rets) > 2 else 0.0
    sharpe = (mu / sd) * math.sqrt(252.0) if sd > 1e-12 else 0.0
    max_dd = float(dd.min()) if len(dd) else 0.0
    peak_at_dd = float(peak[int(np.argmin(dd))]) if len(dd) else 0.0
    terminal = float(xs[-1]) if len(xs) else 0.0
    return PathStats(
        n_bars=len(xs),
        terminal_equity=terminal,
        peak_equity=float(peak.max()) if len(peak) else 0.0,
        max_dd=max_dd,
        max_dd_pct_of_peak=(100.0 * max_dd / peak_at_dd) if peak_at_dd else 0.0,
        time_underwater_pct=100.0 * float(np.mean(underwater)) if len(underwater) else 0.0,
        avg_dd=float(np.mean(dd)),
        dd_p50=float(np.percentile(dd, 50)),
        dd_p90=float(np.percentile(dd, 10)),  # 10th pct of dd series (= more negative)
        dd_p99=float(np.percentile(dd, 1)),
        longest_uw_bars=int(longest),
        calmar_like=(terminal / abs(max_dd)) if max_dd else 0.0,
        daily_sharpe_approx=sharpe,
    )


def _inventory_profile(eq: Sequence[Dict[str, float]], fills_path: Path) -> Dict[str, object]:
    opens = np.array([r["open_units"] for r in eq], dtype=float)
    # stop-defined capital at risk ≈ open hard-risk units * 50 * $1; BE runners ≈ 0
    # Approximate from fills: count open BE vs hard at monthly samples via trade_id walk is heavy;
    # report open units distribution + worst concurrent stop from LOT report if present.
    eoy = defaultdict(int)
    reasons = defaultdict(int)
    with fills_path.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            reasons[r.get("reason") or ""] += int(float(r.get("quantity") or 0))
            if r.get("reason") == "year_end_flatten":
                eoy[str(r.get("ts") or "")[:4]] += int(float(r.get("quantity") or 0))
    return {
        "max_open_units": int(opens.max()) if len(opens) else 0,
        "p50_open": float(np.percentile(opens, 50)) if len(opens) else 0.0,
        "p90_open": float(np.percentile(opens, 90)) if len(opens) else 0.0,
        "p99_open": float(np.percentile(opens, 99)) if len(opens) else 0.0,
        "mean_open": float(opens.mean()) if len(opens) else 0.0,
        "pct_bars_flat": 100.0 * float(np.mean(opens <= 0)) if len(opens) else 0.0,
        "pct_bars_open_ge_10": 100.0 * float(np.mean(opens >= 10)) if len(opens) else 0.0,
        "pct_bars_open_ge_30": 100.0 * float(np.mean(opens >= 30)) if len(opens) else 0.0,
        "fill_reasons": dict(reasons),
        "eoy_flatten_by_year": dict(eoy),
    }


def _dd_episodes(eq: Sequence[Dict[str, float]], key: str = "close_eq") -> List[Dict[str, object]]:
    """Peak-to-trough episodes (recoveries back to prior peak)."""
    episodes = []
    peak = float(eq[0][key])
    peak_ts = eq[0]["ts"]
    trough = peak
    trough_ts = peak_ts
    in_dd = False
    for r in eq:
        x = float(r[key])
        if x >= peak - 1e-9:
            if in_dd:
                episodes.append(
                    {
                        "peak_ts": peak_ts,
                        "trough_ts": trough_ts,
                        "recover_ts": r["ts"],
                        "dd_usd": trough - peak,
                        "depth_pct": 100.0 * (trough - peak) / peak if peak else 0.0,
                    }
                )
            peak = x
            peak_ts = r["ts"]
            trough = x
            trough_ts = r["ts"]
            in_dd = False
        else:
            in_dd = True
            if x < trough:
                trough = x
                trough_ts = r["ts"]
    if in_dd:
        episodes.append(
            {
                "peak_ts": peak_ts,
                "trough_ts": trough_ts,
                "recover_ts": "",
                "dd_usd": trough - peak,
                "depth_pct": 100.0 * (trough - peak) / peak if peak else 0.0,
            }
        )
    episodes.sort(key=lambda e: e["dd_usd"])
    return episodes


def _sizing_sketch(close_stats: PathStats, stress_stats: PathStats, inv: Dict[str, object]) -> Dict[str, object]:
    """Portfolio sleeve sketch: capital from stress, risk budget, concurrency caps."""
    # Use reachable-stress DD as the economic risk unit for the sleeve.
    stress_dd = abs(stress_stats.max_dd) or 1.0
    close_dd = abs(close_stats.max_dd) or 1.0
    # Reference: fund risk budget fractions
    budgets = (0.01, 0.02, 0.05)  # 1%, 2%, 5% of fund NAV to this sleeve's stress
    rows = []
    for b in budgets:
        # units_scale such that scaled stress_dd = b * NAV → for NAV=1e6:
        # scale = b*NAV / stress_dd
        nav = 1_000_000.0
        scale = (b * nav) / stress_dd
        rows.append(
            {
                "fund_nav": nav,
                "sleeve_risk_budget_pct": 100.0 * b,
                "sleeve_risk_budget_usd": b * nav,
                "contract_scale_vs_1lot_book": round(scale, 4),
                "expected_scaled_terminal": round(close_stats.terminal_equity * scale, 0),
                "expected_scaled_stress_dd": -round(stress_dd * scale, 0),
                "scaled_max_open_units": round(float(inv["max_open_units"]) * scale, 1),
            }
        )
    return {
        "risk_anchor": "reachable_stress_dd",
        "reachable_stress_dd": stress_stats.max_dd,
        "close_mtm_dd": close_stats.max_dd,
        "hard_stop_unit_risk_usd": 50.0,  # US30 $1/pt × 50
        "be_runner_stop_risk_usd": 0.0,
        "operational_caps": {
            "suggest_max_open_units": 20,
            "suggest_max_margin_proxy_usd": 20 * 500,  # prior CFD margin proxy
            "kill_switch_stress_dd_usd": -abs(stress_dd),
            "kill_switch_open_units": int(inv["max_open_units"]),
        },
        "nav_1mm_scales": rows,
        "how_to_use": [
            "Treat forced-flat reachable stress DD as the sleeve's 1× risk unit.",
            "Pick a fund risk budget (e.g. 2% NAV) and scale contracts = budget / |stress_dd|.",
            "Cap concurrency (open units / margin) independently — indef stacks inventory.",
            "BE runners add notional/margin but little stop-defined loss; size on margin + gap risk, not on open MTM.",
            "Do not co-rank this sleeve with flat 3R/10R on N/S; allocate as a separate inventory sleeve.",
            "Pair with negatively correlated / flatter books (e.g. US30 3R or 2R→10R, FX Monday OR) and enforce a portfolio stress sum cap.",
        ],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--equity",
        type=Path,
        default=HUB / "audits_lot_correct" / SID / (SID + "_lot_correct") / "equity_curve.csv",
    )
    ap.add_argument("--fills", type=Path, default=HUB / "states" / SID / "fills.csv")
    args = ap.parse_args(list(argv) if argv is not None else None)

    if not args.equity.exists():
        raise SystemExit("Missing lot-correct equity curve: %s (run indefinite_lot_accounting first)" % args.equity)
    if not args.fills.exists():
        raise SystemExit("Missing fills: %s" % args.fills)

    OUT.mkdir(parents=True, exist_ok=True)
    eq = _read_equity(args.equity)
    close_stats = _path_stats(eq, "close_eq")
    stress_stats = _path_stats(eq, "stress_eq")
    inv = _inventory_profile(eq, args.fills)
    episodes = _dd_episodes(eq, "close_eq")[:15]
    stress_episodes = _dd_episodes(eq, "stress_eq")[:10]
    sizing = _sizing_sketch(close_stats, stress_stats, inv)

    payload = {
        "strategy_id": SID,
        "close_path": close_stats.__dict__,
        "stress_path": stress_stats.__dict__,
        "inventory": inv,
        "worst_close_dd_episodes": episodes,
        "worst_stress_dd_episodes": stress_episodes,
        "portfolio_sizing": sizing,
    }
    (OUT / "profile.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    # equity samples CSV for charts / external tools
    with (OUT / "equity_path.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["ts", "close_eq", "stress_eq", "realized", "open_units", "close_dd", "stress_dd"],
        )
        w.writeheader()
        for r in eq:
            w.writerow({k: r[k] for k in w.fieldnames})

    lines = [
        "# US30 ST+PMC indefinite runner — portfolio risk profile",
        "",
        "Source: lot-correct forced-flat equity (`audits_lot_correct`). **Not rankable** vs 3R/10R on N/S.",
        "",
        "## Equity path (close mark)",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Terminal equity | $%.0f |" % close_stats.terminal_equity,
        "| Peak equity | $%.0f |" % close_stats.peak_equity,
        "| Max close DD | $%.0f (%.1f%% of peak) |" % (close_stats.max_dd, close_stats.max_dd_pct_of_peak),
        "| Time underwater | %.1f%% |" % close_stats.time_underwater_pct,
        "| Avg DD | $%.0f |" % close_stats.avg_dd,
        "| DD p50 / p90 / p99 | $%.0f / $%.0f / $%.0f |"
        % (close_stats.dd_p50, close_stats.dd_p90, close_stats.dd_p99),
        "| Longest underwater | %d hourly bars (~%.0f days) |"
        % (close_stats.longest_uw_bars, close_stats.longest_uw_bars / 24.0),
        "| Calmar-like (terminal/|DD|) | %.2f |" % close_stats.calmar_like,
        "| Approx daily Sharpe (Δequity) | %.2f |" % close_stats.daily_sharpe_approx,
        "",
        "## Reachable stress path",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Max reachable stress DD | $%.0f |" % stress_stats.max_dd,
        "| Stress Calmar-like | %.2f |" % stress_stats.calmar_like,
        "| Stress time underwater | %.1f%% |" % stress_stats.time_underwater_pct,
        "",
        "## Open inventory burden",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Max open units | %s |" % inv["max_open_units"],
        "| Mean / p50 / p90 / p99 open | %.1f / %.1f / %.1f / %.1f |"
        % (inv["mean_open"], inv["p50_open"], inv["p90_open"], inv["p99_open"]),
        "| Bars flat | %.1f%% |" % inv["pct_bars_flat"],
        "| Bars with ≥10 open | %.1f%% |" % inv["pct_bars_open_ge_10"],
        "| Bars with ≥30 open | %.1f%% |" % inv["pct_bars_open_ge_30"],
        "",
        "EOY flatten by year: `%s`" % json.dumps(inv["eoy_flatten_by_year"], sort_keys=True),
        "",
        "## Worst close-DD episodes",
        "",
        "| peak | trough | recover | DD $ | depth % |",
        "|---|---|---|---:|---:|",
    ]
    for e in episodes[:8]:
        lines.append(
            "| %s | %s | %s | $%.0f | %.1f |"
            % (e["peak_ts"][:16], e["trough_ts"][:16], (e["recover_ts"] or "—")[:16], e["dd_usd"], e["depth_pct"])
        )

    lines.extend(
        [
            "",
            "## How to put this in a portfolio with defined risk",
            "",
            "### 1. Choose the risk anchor",
            "",
            "Use **reachable stress DD** ($%.0f at 1×) as the sleeve’s risk unit — not raw open MTM, not legacy FIFO net."
            % abs(stress_stats.max_dd),
            "Close DD ($%.0f) is the investor mark path; stress DD is the stop-aware capital-at-risk path."
            % abs(close_stats.max_dd),
            "",
            "### 2. Scale to a fund risk budget",
            "",
            "For fund NAV \\$1,000,000:",
            "",
            "| Sleeve budget | Scale vs 1-lot book | Scaled terminal | Scaled stress DD | Scaled max open |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for r in sizing["nav_1mm_scales"]:
        lines.append(
            "| %.0f%% ($%.0f) | ×%.3f | $%.0f | $%.0f | %.1f |"
            % (
                r["sleeve_risk_budget_pct"],
                r["sleeve_risk_budget_usd"],
                r["contract_scale_vs_1lot_book"],
                r["expected_scaled_terminal"],
                r["expected_scaled_stress_dd"],
                r["scaled_max_open_units"],
            )
        )

    lines.extend(
        [
            "",
            "Formula: `scale = (budget_pct × NAV) / |reachable_stress_dd|`.",
            "",
            "### 3. Cap inventory separately from P&amp;L risk",
            "",
            "Indef stacks BE runners: stop-defined loss per BE lot ≈ $0, but **margin / notional / gap risk** grow with open count.",
            "Suggested hard caps (tune to broker): max open units **20**, margin proxy, and a kill-switch if open units or stress DD hit 1× profile extremes.",
            "",
            "### 4. Sleeve role vs 3R / 2R→10R",
            "",
            "| Book | Role |",
            "|---|---|",
            "| US30 3R (N/S ~29) | Core / rankable alpha, flat inventory |",
            "| US30 2R→10R (N/S ~24) | Scaled participation, bounded 3 lots |",
            "| US30 indef (this) | **Inventory sleeve** — harvest TP1 + optional trend residue; size on stress + concurrency, not on N/S leaderboard |",
            "",
            "### 5. Portfolio assembly checklist",
            "",
        ]
    )
    for tip in sizing["how_to_use"]:
        lines.append("- %s" % tip)

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "- `profile.json` — full machine-readable profile",
            "- `equity_path.csv` — close / stress / open units path",
            "- Equity source: `%s`" % args.equity,
            "",
        ]
    )
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote %s" % (OUT / "SUMMARY.md"), flush=True)
    print("Wrote %s" % (OUT / "profile.json"), flush=True)
    print(
        "close_dd=$%.0f stress_dd=$%.0f terminal=$%.0f max_open=%s"
        % (close_stats.max_dd, stress_stats.max_dd, close_stats.terminal_equity, inv["max_open_units"]),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
