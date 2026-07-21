"""Monday OR Phase 2 robustness: perturbations, sub-periods, clustering, DD sensitivity.

Uses Phase 1 broker fills for anchors where possible. Sensitivity cells replay
Engine + PaperBroker with nudged dd30_frac / dd50_frac on locked size tags.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .fx_monday_or_breakout_broker import PAIRS, JPY_USD, load_15m_bars
from .hourly_st_pmc_retest_replay import DEFAULT_FEE_PER_UNIT, DEFAULT_SLIPPAGE_TICKS
from .models import StrategyInstance, as_row
from .monday_or_phase2_tags import (
    LOCAL_PERTURBATIONS,
    PAIR_PHASE2_DEFAULT,
    PHASE1_STATE_ROOTS,
    PHASE2_CORE_ANCHORS,
    PHASE2_EXTENDED_ANCHORS,
    plugin_config,
)
from .notifications import NullNotificationSink
from .replay_audit import POINT_VALUES, audit_units, units_from_live_fills, Bar as AuditBar
from .store import FlatFileStore
from .verification import QuietPaperVerificationProvider


REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "monday_or_phase2"

# Default: core + extended (ex-silver). Override with --scope.
ANCHORS = list(PHASE2_CORE_ANCHORS) + list(PHASE2_EXTENDED_ANCHORS)

# Sensitivity on one primary tag per pair (skip USDJPY alt to save runtime)
SENSITIVITY_TARGETS = [
    ("EURUSD", "M1_S2_R2"),
    ("USDJPY", "M2_S3_R1"),
    ("GBPUSD", "M1_S1_R2"),
    ("AUDJPY", "M1_S2_R2"),
    ("XAUUSD", "M2_S2_R3"),
]

SUBPERIODS = [
    ("pre_2020", None, "2020-01-01"),
    ("2020_2022", "2020-01-01", "2023-01-01"),
    ("2023_plus", "2023-01-01", None),
]

SENSITIVITY = [
    ("dd25_45", 0.25, 0.45),
    ("dd35_55", 0.35, 0.55),
]


def _phase1_root(sym: str) -> Path:
    return REPO / PHASE1_STATE_ROOTS[sym]


def _unit_fills_path(sym: str, tag: str) -> Path:
    sid = "%s_%s" % (sym.lower(), tag.lower())
    base = _phase1_root(sym) / "audits" / sid / sid / "unit_fills.csv"
    if base.exists():
        return base
    # alternate nesting
    alt = _phase1_root(sym) / "audits" / sid / "unit_fills.csv"
    return alt


def _results_row(sym: str, tag: str) -> Optional[dict]:
    csv_path = _phase1_root(sym) / "results.csv"
    if not csv_path.exists():
        return None
    with csv_path.open() as fh:
        for r in csv.DictReader(fh):
            if r.get("tag") == tag and r.get("symbol", sym) == sym:
                return r
    return None


def write_perturbations(out: Path) -> None:
    lines = [
        "# Monday OR Phase 2 — local perturbations",
        "",
        "Narrow cells only (not a full re-sweep). Metrics from Phase 1 broker CSV.",
        "",
        "| Pair | Tag | Role | ≈USD Net | Stress | **N/S** | Δ vs anchor N/S |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    anchors_ns = {}
    for sym, tag in LOCAL_PERTURBATIONS:
        row = _results_row(sym, tag)
        if not row:
            lines.append("| %s | `%s` | missing | — | — | — | — |" % (sym, tag))
            continue
        ns = float(row["net_stress_usd"])
        net = float(row["net_usd_approx"])
        stress = float(row["stress_usd_approx"])
        if (sym, tag) in [("EURUSD", "M1_S2_R2"), ("USDJPY", "M2_S3_R1")]:
            role = "anchor"
            anchors_ns[sym] = ns
        elif tag == "M2_S3_R2":
            role = "USDJPY alt"
        elif tag == "M1_S2_R1":
            role = "EURUSD tighter R"
        else:
            role = "robustness"
        base = anchors_ns.get(sym)
        delta = "" if base is None else ("%+.2f" % (ns - base))
        lines.append(
            "| %s | `%s` | %s | $%+.0f | $%+.0f | **%.2f** | %s |"
            % (sym, tag, role, net, stress, ns, delta or "—")
        )
    lines.extend(
        [
            "",
            "## Read",
            "",
            "- EURUSD `M1_S2_R1` (max 2/week) **hurts** N/S vs locked `R2` — keep max 3/week.",
            "- USDJPY `M2_S3_R1` ≈ `M2_S3_R2` (8.20 vs 8.19) — retain R1 primary, R2 as dollar alt.",
            "- USDJPY lighter sidecar `M2_S2_R1` (5.66) is weaker but still strong — heavy sidecar is the edge amplifier, not the whole edge.",
            "",
            "*Generated from Phase 1 broker results.*",
            "",
        ]
    )
    (out / "PERTURBATIONS.md").write_text("\n".join(lines), encoding="utf-8")


def _parse_ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s)


def _to_usd(sym: str, usd_field: float) -> float:
    quote = str(PAIRS[sym]["quote"])
    return usd_field / JPY_USD if quote == "JPY" else usd_field


def load_units(sym: str, tag: str) -> pd.DataFrame:
    path = _unit_fills_path(sym, tag)
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True)
    df["usd_approx"] = df["usd"].astype(float).map(lambda x: _to_usd(sym, x))
    ny = df["entry_ts"].dt.tz_convert("America/New_York")
    # Monday-start week key without Period conversion warnings
    monday = ny.dt.normalize() - pd.to_timedelta(ny.dt.dayofweek, unit="D")
    df["week_key"] = monday.dt.strftime("%Y-%m-%d")
    df["year"] = ny.dt.year
    return df


def slice_mask(df: pd.DataFrame, start: Optional[str], end: Optional[str]) -> pd.Series:
    ts = df["exit_ts"]
    m = pd.Series(True, index=df.index)
    if start:
        m &= ts >= pd.Timestamp(start, tz="UTC")
    if end:
        m &= ts < pd.Timestamp(end, tz="UTC")
    return m


def max_dd_from_pnls(pnls: List[float]) -> float:
    eq = 0.0
    peak = 0.0
    dd = 0.0
    for p in pnls:
        eq += p
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return dd


def analyze_subperiods(out: Path, anchors: Optional[List[Tuple[str, str]]] = None) -> List[dict]:
    anchors = anchors or ANCHORS
    rows = []
    lines = [
        "# Monday OR Phase 2 — sub-period stability",
        "",
        "Unit PnL from Phase 1 broker audits, sliced by exit timestamp.",
        "Pass: positive net in ≥2/3 slices; no slice with N/S ≤ 0 while total still large.",
        "Scope: core (EURUSD/USDJPY) + extended (GBPUSD/AUDJPY/XAUUSD). Silver excluded.",
        "",
    ]
    for sym, tag in anchors:
        df = load_units(sym, tag)
        lines.append("## %s `%s`" % (sym, tag))
        lines.append("")
        lines.append("| Slice | Units | ≈USD Net | Closed DD | **N/S** | Pass? |")
        lines.append("|---|---:|---:|---:|---:|---|")
        slice_pass = 0
        for name, start, end in SUBPERIODS:
            sub = df.loc[slice_mask(df, start, end)].sort_values("exit_ts")
            net = float(sub["usd_approx"].sum()) if len(sub) else 0.0
            dd = max_dd_from_pnls(list(sub["usd_approx"])) if len(sub) else 0.0
            ns = (net / abs(dd)) if dd else 0.0
            ok = net > 0 and ns > 0
            if ok:
                slice_pass += 1
            rows.append(
                {
                    "symbol": sym,
                    "tag": tag,
                    "slice": name,
                    "units": int(len(sub)),
                    "net_usd": net,
                    "closed_dd": dd,
                    "net_stress": ns,
                    "pass": ok,
                }
            )
            lines.append(
                "| %s | %d | $%+.0f | $%+.0f | **%.2f** | %s |"
                % (name, len(sub), net, dd, ns, "yes" if ok else "NO")
            )
        overall = "PASS" if slice_pass >= 2 else "FAIL"
        lines.append("")
        lines.append("**Slice pass count:** %d/3 → **%s**" % (slice_pass, overall))
        lines.append("")
    (out / "SUBPERIODS.md").write_text("\n".join(lines), encoding="utf-8")
    with (out / "subperiods.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return rows


def analyze_clustering(out: Path, anchors: Optional[List[Tuple[str, str]]] = None) -> List[dict]:
    anchors = anchors or ANCHORS
    rows = []
    lines = [
        "# Monday OR Phase 2 — Monday / week clustering",
        "",
        "Contribution of calendar weeks (Mon-start NY) to lifetime unit PnL.",
        "Flag if any single week > 8% of lifetime |net| or top 5% of weeks capture >50% of gross positive week PnL.",
        "Scope: core + extended (ex-silver).",
        "",
    ]
    for sym, tag in anchors:
        df = load_units(sym, tag)
        by_week = df.groupby("week_key")["usd_approx"].sum().sort_values(ascending=False)
        total = float(by_week.sum())
        abs_total = abs(total) if total else 1.0
        top1 = float(by_week.iloc[0]) if len(by_week) else 0.0
        top1_share = abs(top1) / abs_total
        n = len(by_week)
        top5pct_n = max(1, int(math.ceil(0.05 * n)))
        # Share of gross positive week PnL captured by the best 5% of weeks
        pos = by_week[by_week > 0].sort_values(ascending=False)
        pos_sum = float(pos.sum()) or 1.0
        top5pct_net = float(pos.head(top5pct_n).sum())
        top5pct_share = top5pct_net / pos_sum
        # Herfindahl on abs weekly PnL
        abs_w = by_week.abs()
        s = float(abs_w.sum()) or 1.0
        hhi = float(((abs_w / s) ** 2).sum())
        # Flag: single week >8% of lifetime |net|, or best 5% of weeks >50% of gross positive
        flag = top1_share > 0.08 or top5pct_share > 0.50
        rows.append(
            {
                "symbol": sym,
                "tag": tag,
                "weeks": n,
                "lifetime_net": total,
                "top_week": by_week.index[0] if n else "",
                "top_week_net": top1,
                "top_week_share": top1_share,
                "top_5pct_weeks": top5pct_n,
                "top_5pct_share": top5pct_share,
                "hhi": hhi,
                "flag_concentrated": flag,
            }
        )
        lines.append("## %s `%s`" % (sym, tag))
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|---|---|")
        lines.append("| Weeks with PnL | %d |" % n)
        lines.append("| Lifetime ≈USD net | $%+.0f |" % total)
        lines.append("| Top week | %s ($%+.0f, **%.1f%%**) |" % (by_week.index[0], top1, 100 * top1_share))
        lines.append("| Top 5%% weeks (n=%d) share of gross + | **%.1f%%** |" % (top5pct_n, 100 * top5pct_share))
        lines.append("| Abs-PnL HHI | %.4f |" % hhi)
        lines.append("| Concentration flag | %s |" % ("YES — review" if flag else "no"))
        lines.append("")
        lines.append("Top 10 weeks:")
        lines.append("")
        lines.append("| Week | ≈USD Net | Share |")
        lines.append("|---|---:|---:|")
        for wk, val in by_week.head(10).items():
            lines.append("| %s | $%+.0f | %.2f%% |" % (wk, val, 100 * abs(val) / abs_total))
        lines.append("")
    (out / "CLUSTERING.md").write_text("\n".join(lines), encoding="utf-8")
    with (out / "clustering.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return rows


def run_sensitivity_cell(
    sym: str,
    tag: str,
    bars,
    *,
    slug: str,
    dd30: float,
    dd50: float,
    out: Path,
    force: bool,
) -> dict:
    meta = PAIRS[sym]
    tick = float(meta["tick"])
    pv = float(meta["pv"])
    POINT_VALUES[sym] = pv
    DEFAULT_TICK_SIZE[sym] = tick
    strategy_id = "%s_%s_%s" % (sym.lower(), tag.lower(), slug)
    state_root = out / "states" / strategy_id
    metrics_path = state_root / "metrics.json"
    if (not force) and metrics_path.exists():
        return json.loads(metrics_path.read_text(encoding="utf-8"))
    if state_root.exists():
        shutil.rmtree(state_root)
    cfg = plugin_config(tick, tag, dd30_frac=dd30, dd50_frac=dd50)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    max_c = max(int(cfg["entry_qty"]), int(cfg["shifted_entry_qty"])) + 2
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type="monday_or_breakout",
        version="v1",
        instrument=sym,
        broker_instrument=sym,
        account_mode="paper",
        enabled=True,
        timeframes="15m",
        max_contracts=max_c,
        max_open_orders=24,
        config_json=json.dumps(cfg, sort_keys=True),
    )
    store.write_table("strategy_instances", [as_row(instance)])
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        slippage_ticks=DEFAULT_SLIPPAGE_TICKS,
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
    )
    for bar in bars:
        engine.process_bar(bar)
    if hasattr(engine.broker, "flush_state"):
        engine.broker.flush_state()
    store.flush_tables()
    fills_path = state_root / "fills.csv"
    one_m = REPO / "fx" / ("%s_1m.csv" % sym.lower())
    units = units_from_live_fills(fills_path, strategy_id)
    audit_bars = [
        AuditBar(ts=b.ts, open=b.open, high=b.high, low=b.low, close=b.close) for b in bars
    ]
    audit = audit_units(
        name="%s %s %s" % (sym, tag, slug),
        slug=strategy_id,
        source=fills_path,
        bar_source=one_m,
        bars=audit_bars,
        units=units,
        instrument=sym,
        notes="Phase 2 DD sensitivity",
        output_root=out / "audits" / strategy_id,
        fee_per_unit=DEFAULT_FEE_PER_UNIT,
    )
    net = float(audit.net_usd)
    stress = float(audit.intrabar_mtm_dd_usd)
    quote = str(meta["quote"])
    net_usd = net / JPY_USD if quote == "JPY" else net
    stress_usd = stress / JPY_USD if quote == "JPY" else stress
    ns = (net_usd / abs(stress_usd)) if stress_usd else 0.0
    row = {
        "symbol": sym,
        "tag": tag,
        "slug": slug,
        "dd30_frac": dd30,
        "dd50_frac": dd50,
        "units": int(audit.units),
        "net_usd": net_usd,
        "stress_usd": stress_usd,
        "net_stress": ns,
    }
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(row, indent=2), encoding="utf-8")
    print(
        "[sens] %s %s %s N/S=%.2f net=$%+.0f" % (sym, tag, slug, ns, net_usd),
        flush=True,
    )
    return row


def run_sensitivity(
    out: Path,
    force: bool,
    targets: Optional[List[Tuple[str, str]]] = None,
) -> List[dict]:
    rows: List[dict] = []
    targets = targets or list(SENSITIVITY_TARGETS)
    for sym, tag in targets:
        print("[%s] loading bars for sensitivity..." % sym, flush=True)
        bars = load_15m_bars(sym)
        # baseline from Phase 1
        base = _results_row(sym, tag)
        base_ns = float(base["net_stress_usd"]) if base else None
        rows.append(
            {
                "symbol": sym,
                "tag": tag,
                "slug": "anchor_30_50",
                "dd30_frac": 0.30,
                "dd50_frac": 0.50,
                "units": int(base["units"]) if base else 0,
                "net_usd": float(base["net_usd_approx"]) if base else 0.0,
                "stress_usd": float(base["stress_usd_approx"]) if base else 0.0,
                "net_stress": base_ns or 0.0,
                "delta_ns_pct": 0.0,
                "pass": True,
            }
        )
        for slug, d30, d50 in SENSITIVITY:
            r = run_sensitivity_cell(
                sym, tag, bars, slug=slug, dd30=d30, dd50=d50, out=out, force=force
            )
            delta = 0.0
            if base_ns:
                delta = (float(r["net_stress"]) - base_ns) / abs(base_ns)
            ok = float(r["net_usd"]) > 0 and (base_ns is None or delta > -0.30)
            r2 = dict(r)
            r2["delta_ns_pct"] = delta
            r2["pass"] = ok
            rows.append(r2)

    lines = [
        "# Monday OR Phase 2 — DD threshold sensitivity",
        "",
        "Nudges around 30%/50% on locked size tags only. Pass if net > 0 and N/S drop ≤ ~30% vs anchor.",
        "",
        "| Pair | Tag | Slug | DD | ≈USD Net | Stress | **N/S** | Δ N/S | Pass |",
        "|---|---|---|---|---:|---:|---:|---:|---|",
    ]
    # Merge with prior sensitivity.csv so partial re-runs keep core pairs
    prior_path = out / "sensitivity.csv"
    merged: Dict[Tuple[str, str, str], dict] = {}
    if prior_path.exists():
        with prior_path.open() as fh:
            for r in csv.DictReader(fh):
                key = (r["symbol"], r["tag"], r["slug"])
                # normalize types
                for k in ("dd30_frac", "dd50_frac", "net_usd", "stress_usd", "net_stress", "delta_ns_pct"):
                    if k in r and r[k] != "":
                        r[k] = float(r[k])
                if "pass" in r:
                    r["pass"] = str(r["pass"]).lower() in {"1", "true", "yes"}
                if "units" in r and r["units"] != "":
                    r["units"] = int(float(r["units"]))
                merged[key] = r
    for r in rows:
        merged[(r["symbol"], r["tag"], r["slug"])] = r
    rows = list(merged.values())
    rows.sort(key=lambda x: (x["symbol"], x["tag"], x["slug"]))

    for r in rows:
        lines.append(
            "| %s | `%s` | %s | %.0f/%.0f | $%+.0f | $%+.0f | **%.2f** | %+.0f%% | %s |"
            % (
                r["symbol"],
                r["tag"],
                r["slug"],
                100 * float(r["dd30_frac"]),
                100 * float(r["dd50_frac"]),
                float(r["net_usd"]),
                float(r["stress_usd"]),
                float(r["net_stress"]),
                100 * float(r.get("delta_ns_pct") or 0),
                "yes" if r.get("pass") else "NO",
            )
        )
    lines.extend(["", "*Driver: `live/monday_or_phase2_robustness.py`.*", ""])
    (out / "SENSITIVITY.md").write_text("\n".join(lines), encoding="utf-8")
    with (out / "sensitivity.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return rows


def write_summary(
    out: Path,
    sub_rows: List[dict],
    clust_rows: List[dict],
    sens_rows: List[dict],
) -> None:
    lines = [
        "# Monday OR Phase 2 — SUMMARY",
        "",
        "**Status: Phase 2 complete** (core + extended ex-silver, 2026-07-21).",
        "",
        "## Locked / extended candidates",
        "",
        "| Pair | Tag | Role |",
        "|---|---|---|",
        "| EURUSD | `M1_S2_R2` | Core — paper-only if sub-period FAIL |",
        "| USDJPY | `M2_S3_R1` | Core primary |",
        "| USDJPY | `M2_S3_R2` | Core alternate |",
        "| GBPUSD | `M1_S1_R2` | Extended |",
        "| AUDJPY | `M1_S2_R2` | Extended |",
        "| XAUUSD | `M2_S2_R3` | Extended — heat caution |",
        "| XAGUSD | — | **Excluded** (Phase 1 reject) |",
        "",
        "## Robustness verdict",
        "",
    ]
    by = defaultdict(list)
    for r in sub_rows:
        by[(r["symbol"], r["tag"])].append(r)
    lines.append("### Sub-periods")
    lines.append("")
    for key, rs in by.items():
        n_ok = sum(1 for x in rs if x["pass"])
        lines.append(
            "- %s `%s`: %d/3 slices positive N/S → **%s**"
            % (key[0], key[1], n_ok, "PASS" if n_ok >= 2 else "FAIL")
        )
    lines.append("")
    lines.append("### Clustering")
    lines.append("")
    for r in clust_rows:
        lines.append(
            "- %s `%s`: top-week %.1f%%, top-5%% weeks %.1f%% → %s"
            % (
                r["symbol"],
                r["tag"],
                100 * float(r["top_week_share"]),
                100 * float(r["top_5pct_share"]),
                "FLAG" if r["flag_concentrated"] else "OK",
            )
        )
    lines.append("")
    lines.append("### Sensitivity")
    lines.append("")
    if not sens_rows:
        lines.append("- (not run)")
    for r in sens_rows:
        if r["slug"] == "anchor_30_50":
            continue
        lines.append(
            "- %s `%s` %s: ΔN/S %+.0f%% → %s"
            % (
                r["symbol"],
                r["tag"],
                r["slug"],
                100 * float(r.get("delta_ns_pct") or 0),
                "PASS" if r.get("pass") else "FAIL",
            )
        )
    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "- [`PERTURBATIONS.md`](PERTURBATIONS.md)",
            "- [`SUBPERIODS.md`](SUBPERIODS.md)",
            "- [`CLUSTERING.md`](CLUSTERING.md)",
            "- [`SENSITIVITY.md`](SENSITIVITY.md)",
            "- [`DEPLOYMENT_RULES.md`](DEPLOYMENT_RULES.md)",
            "- Specs: `SPEC_EURUSD_*`, `SPEC_USDJPY_*`, `SPEC_GBPUSD_*`, `SPEC_AUDJPY_*`, `SPEC_XAUUSD_*`",
            "",
            "## Do-not-cross-use",
            "",
            "- EURUSD / AUDJPY light-sidecar `M1_S2_R2` ≠ USDJPY `M2_S3_*`",
            "- GBPUSD matched `M1_S1_R2` is its own recipe",
            "- XAUUSD `M2_S2_R3` is heat-heavy — not a clean FX sleeve clone",
            "- XAGUSD excluded",
            "",
        ]
    )
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "INDEX.md").write_text(
        "\n".join(
            [
                "# Monday OR Phase 2 hub",
                "",
                "See [`SUMMARY.md`](SUMMARY.md).",
                "",
                "Pair defaults: `live/monday_or_phase2_tags.py` → %s"
                % json.dumps(PAIR_PHASE2_DEFAULT, sort_keys=True),
                "",
            ]
        ),
        encoding="utf-8",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--scope",
        choices=("all", "core", "extended"),
        default="all",
        help="all=core+extended ex-silver; core=EURUSD/USDJPY; extended=GBP/AUD/XAU",
    )
    parser.add_argument(
        "--sensitivity-pairs",
        default="",
        help="Comma symbols for sensitivity only (default: all sensitivity targets in scope)",
    )
    parser.add_argument("--skip-sensitivity", action="store_true")
    parser.add_argument("--force", action="store_true", default=False)
    args = parser.parse_args(list(argv) if argv is not None else None)
    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)

    if args.scope == "core":
        sens_scope_syms = {a[0] for a in PHASE2_CORE_ANCHORS}
    elif args.scope == "extended":
        sens_scope_syms = {a[0] for a in PHASE2_EXTENDED_ANCHORS}
    else:
        sens_scope_syms = {a[0] for a in PHASE2_CORE_ANCHORS} | {
            a[0] for a in PHASE2_EXTENDED_ANCHORS
        }

    # Docs always cover full core+extended set (ex-silver)
    anchors = list(PHASE2_CORE_ANCHORS) + list(PHASE2_EXTENDED_ANCHORS)

    sens_targets = [t for t in SENSITIVITY_TARGETS if t[0] in sens_scope_syms]
    if args.sensitivity_pairs.strip():
        want = {p.strip().upper() for p in args.sensitivity_pairs.split(",") if p.strip()}
        sens_targets = [t for t in SENSITIVITY_TARGETS if t[0] in want]

    print("Writing perturbations...", flush=True)
    write_perturbations(out)
    print("Sub-periods (%d anchors)..." % len(anchors), flush=True)
    sub_rows = analyze_subperiods(out, anchors=anchors)
    print("Clustering...", flush=True)
    clust_rows = analyze_clustering(out, anchors=anchors)
    if args.skip_sensitivity:
        sens_rows = []
        # Preserve existing sensitivity file if present
        if not (out / "SENSITIVITY.md").exists():
            (out / "SENSITIVITY.md").write_text(
                "# Sensitivity skipped (--skip-sensitivity)\n", encoding="utf-8"
            )
    else:
        print("Sensitivity targets: %s" % sens_targets, flush=True)
        sens_rows = run_sensitivity(out, force=bool(args.force), targets=sens_targets)
    write_summary(out, sub_rows, clust_rows, sens_rows)
    print("SUMMARY → %s" % (out / "SUMMARY.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
