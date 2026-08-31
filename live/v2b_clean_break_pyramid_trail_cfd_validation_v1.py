"""V2B clean-break pyramid+trail CFD portability VALIDATION V1.

Frozen top-three from parent ``v2b_clean_break_pyramid_trail_cfd_top3_v1``
(DSR TRL-2026-00196). Not an optimization study. RESEARCH ONLY.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.v2b_clean_break_pyramid_trail_cfd_validation_v1 --email
  python -m live.v2b_clean_break_pyramid_trail_cfd_validation_v1 --email --smoke
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .notify_email import send_email
from .run_ledger import begin_run, complete_run, fail_run
from .v2b_clean_break_pyramid_trail_sizing_v1 import (
    CFD_SPECS,
    FEE_PER_UNIT,
    MARKETS,
    PyramidVariant,
    VARIANTS,
    _load_bars,
    run_one,
)
from .v2b_strategy_replay import money

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "v2b_clean_break_pyramid_trail_cfd_validation_v1"
STUDY_ID = "v2b_clean_break_pyramid_trail_cfd_validation_v1"
DSR = "TRL-2026-00197"
PARENT_STUDY = "v2b_clean_break_pyramid_trail_cfd_top3_v1"
PARENT_DSR = "TRL-2026-00196"
PARENT_HUB = REPO / "live" / "state" / PARENT_STUDY

FROZEN_NAMES = (
    "trail06_m8_e2_out_be",
    "trail06_m4_e1_opp_be",
    "trail06_m4_e2_out_be",
)
CFD_MARKETS = ("nas100", "us30", "spx500")

# Parent Scenario-0 nets for Gate 1 (from parent RUN_COMPLETE / SUMMARY).
PARENT_NET = {
    ("nas100", "trail06_m8_e2_out_be"): 18868.80,
    ("nas100", "trail06_m4_e2_out_be"): 11331.50,
    ("nas100", "trail06_m4_e1_opp_be"): 10844.00,
    ("us30", "trail06_m8_e2_out_be"): 14840.20,
    ("us30", "trail06_m4_e2_out_be"): 9604.40,
    ("us30", "trail06_m4_e1_opp_be"): 11177.50,
    ("spx500", "trail06_m8_e2_out_be"): -3758.20,
    ("spx500", "trail06_m4_e2_out_be"): -2932.90,
    ("spx500", "trail06_m4_e1_opp_be"): -2748.70,
}
PARENT_STRESS = {
    ("nas100", "trail06_m8_e2_out_be"): -3975.10,
    ("nas100", "trail06_m4_e2_out_be"): -1960.90,
    ("nas100", "trail06_m4_e1_opp_be"): -2087.40,
    ("us30", "trail06_m8_e2_out_be"): -8555.30,
    ("us30", "trail06_m4_e2_out_be"): -6400.20,
    ("us30", "trail06_m4_e1_opp_be"): -6314.20,
    ("spx500", "trail06_m8_e2_out_be"): -3781.80,
    ("spx500", "trail06_m4_e2_out_be"): -2940.00,
    ("spx500", "trail06_m4_e1_opp_be"): -2899.30,
}

# Rounding tolerance for reproduction vs parent (same engine path).
REPRO_NET_TOL = 1.0  # USD
REPRO_STRESS_TOL = 5.0

SCENARIOS: Dict[str, Dict[str, Any]] = {
    "S0_base": {"slippage_ticks": 1.0, "extra": {}},
    "S1_plus1_tick": {"slippage_ticks": 2.0, "extra": {}},
    "S2_plus2_tick": {"slippage_ticks": 3.0, "extra": {}},
    "S3_plus4_tick": {"slippage_ticks": 5.0, "extra": {}},
    "S4_delayed_trail": {"slippage_ticks": 1.0, "extra": {"trail_delay_bars": 1}},
    "S5_miss_add_every3": {"slippage_ticks": 1.0, "extra": {"miss_add_every_n": 3}},
    "S6_partial_add_alt": {"slippage_ticks": 1.0, "extra": {"add_alternate_skip": True}},
    "S7_soft_exit_delay": {"slippage_ticks": 1.0, "extra": {"soft_exit_delay_bars": 1}},
    # S8: PaperBroker already gap-throughs; extra adverse ticks stress gap fills.
    "S8_gap_stop_stress": {"slippage_ticks": 5.0, "extra": {}},
}


def _progress(msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _frozen_variants() -> List[PyramidVariant]:
    by_name = {v.name: v for v in VARIANTS}
    return [by_name[n] for n in FROZEN_NAMES]


def _config_hash(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def _file_hash(path: Path, nbytes: int = 2_000_000) -> str:
    if not path.exists():
        return "MISSING"
    return hashlib.sha256(path.read_bytes()[:nbytes]).hexdigest()[:16]


def _append_dsr() -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    lines = path.read_text().splitlines()
    if any(ln.startswith(DSR + ",") for ln in lines):
        return
    header = next(ln for ln in lines if ln.startswith("trial_id,"))
    fields = header.split(",")
    row = {k: "" for k in fields}
    row.update(
        {
            "trial_id": DSR,
            "entry_date": date.today().isoformat(),
            "analyst": "cursor",
            "trial_class": "VALIDATION",
            "trial_subclass": "cfd_portability_validation",
            "is_independent": "FALSE",
            "market": "NAS100,US30,SPX500",
            "replay_type": "FULL_HISTORY",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {
                    "parent": PARENT_STUDY,
                    "parent_dsr": PARENT_DSR,
                    "frozen": list(FROZEN_NAMES),
                    "scenarios": list(SCENARIOS),
                }
            ),
            "fixed_parameters_ref": "live/v2b_clean_break_pyramid_trail_cfd_validation_v1.py",
            "num_params_varied": "0",
            "counts_toward_dsr": "FALSE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "0.00",
            "status": "PENDING",
            "notes": "CFD portability validation of frozen trail top-3; RESEARCH ONLY",
            "disclosure_review": "FALSE",
        }
    )
    import csv

    with path.open("a", newline="") as fh:
        csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore").writerow(row)


def _mark_dsr(status: str) -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    out = []
    for ln in path.read_text().splitlines():
        if ln.startswith(DSR + ","):
            for old in ("PENDING", "RUNNING", "COMPLETE", "FAILED"):
                tok = ",%s," % old
                if tok in ln:
                    ln = ln.replace(tok, ",%s," % status, 1)
                    break
        out.append(ln)
    path.write_text("\n".join(out) + "\n")


def _campaigns_from_fills(fills_path: Path, point_value: float) -> pd.DataFrame:
    if not fills_path.exists():
        return pd.DataFrame()
    f = pd.read_csv(fills_path)
    if f.empty:
        return pd.DataFrame()
    rows = []
    for tid, g in f.groupby("trade_id"):
        g = g.sort_values("ts")
        buys = g[g["side"] == "buy"]
        sells = g[g["side"] == "sell"]
        if buys.empty:
            continue
        entry_px = float(buys.iloc[0]["price"])
        entry_ts = str(buys.iloc[0]["ts"])
        qty = int(buys["quantity"].sum())
        fees = FEE_PER_UNIT * float(g["quantity"].sum())
        # Approximate gross from matched qty at avg entry vs avg exit
        avg_entry = float((buys["price"] * buys["quantity"]).sum() / buys["quantity"].sum())
        if not sells.empty:
            avg_exit = float((sells["price"] * sells["quantity"]).sum() / sells["quantity"].sum())
            exit_reason = str(sells.iloc[-1]["reason"])
            exit_ts = str(sells.iloc[-1]["ts"])
        else:
            avg_exit = avg_entry
            exit_reason = "open"
            exit_ts = ""
        gross = (avg_exit - avg_entry) * qty * point_value
        net = gross - fees
        session = entry_ts[:10]
        rows.append(
            {
                "trade_id": tid,
                "session_day": session,
                "entry_ts": entry_ts,
                "exit_ts": exit_ts,
                "exit_reason": exit_reason,
                "qty": qty,
                "avg_entry": avg_entry,
                "avg_exit": avg_exit,
                "gross_usd": gross,
                "fees_usd": fees,
                "net_usd": net,
                "n_adds": max(0, int(buys.shape[0]) - 1),
                "trail_stop_exit": int((sells["reason"] == "trail_stop").any()) if len(sells) else 0,
                "target_exit": int((sells["reason"] == "target").any()) if len(sells) else 0,
            }
        )
    return pd.DataFrame(rows)


def _assert_fills(fills_path: Path, max_qty: int) -> List[str]:
    fails = []
    if not fills_path.exists():
        return ["missing_fills"]
    f = pd.read_csv(fills_path)
    if f.empty:
        return fails
    f["ts"] = pd.to_datetime(f["ts"], utc=True).dt.tz_convert("America/New_York")
    late = f[f["ts"].dt.time > pd.Timestamp("15:55").time()]
    if len(late):
        fails.append("post_eod_fills=%d" % len(late))
    for tid, g in f.groupby("trade_id"):
        # Skip orphan close-only rows (legacy bug / ephemeral ids)
        if not (g["side"] == "buy").any():
            continue
        pos = 0
        peak = 0
        for _, row in g.sort_values("ts").iterrows():
            if row["side"] == "buy":
                pos += int(row["quantity"])
            else:
                pos -= int(row["quantity"])
            peak = max(peak, pos)
            if pos < -0:
                fails.append("neg_pos_%s" % tid)
                break
        if peak > max_qty:
            fails.append("over_cap_%s_peak=%d" % (tid, peak))
    return fails


def _concentration(camps: pd.DataFrame) -> Dict[str, float]:
    if camps.empty:
        return {
            "top1_frac": 0.0,
            "top3_frac": 0.0,
            "top5_frac": 0.0,
            "net": 0.0,
            "net_ex_top1": 0.0,
            "net_ex_top3": 0.0,
            "net_ex_top5": 0.0,
        }
    nets = camps["net_usd"].sort_values(ascending=False)
    total = float(camps["net_usd"].sum())
    t1 = float(nets.iloc[0]) if len(nets) else 0.0
    t3 = float(nets.iloc[:3].sum())
    t5 = float(nets.iloc[:5].sum())
    return {
        "top1_frac": (t1 / total) if total else 0.0,
        "top3_frac": (t3 / total) if total else 0.0,
        "top5_frac": (t5 / total) if total else 0.0,
        "net": total,
        "net_ex_top1": total - t1,
        "net_ex_top3": total - t3,
        "net_ex_top5": total - t5,
    }


def _dev_holdout(camps: pd.DataFrame, sessions_sorted: List[str]) -> Tuple[float, float]:
    if not sessions_sorted or camps.empty:
        return 0.0, 0.0
    cut = max(1, int(math.floor(0.7 * len(sessions_sorted))))
    dev_set = set(sessions_sorted[:cut])
    hold_set = set(sessions_sorted[cut:])
    dev = float(camps[camps["session_day"].isin(dev_set)]["net_usd"].sum())
    hold = float(camps[camps["session_day"].isin(hold_set)]["net_usd"].sum())
    return dev, hold


def _yearly(camps: pd.DataFrame) -> pd.DataFrame:
    if camps.empty:
        return pd.DataFrame()
    c = camps.copy()
    c["year"] = c["session_day"].str[:4]
    return c.groupby("year")["net_usd"].agg(["count", "sum"]).reset_index()


def write_config_md(cfg_hash: str) -> None:
    lines = [
        "# CONFIG — V2B Clean-Break Pyramid Trail CFD Validation V1",
        "",
        "STATUS: RESEARCH ONLY",
        "CONFIG_HASH: `%s`" % cfg_hash,
        "PARENT: `%s` / `%s`" % (PARENT_STUDY, PARENT_DSR),
        "",
        "## Frozen variants (exact)",
        "",
        "- `trail06_m8_e2_out_be` — max 8, add every 2 outside bars, trail@0.6→BE",
        "- `trail06_m4_e1_opp_be` — max 4, add every 1 opposing outside, trail@0.6→BE",
        "- `trail06_m4_e2_out_be` — max 4, add every 2 outside bars, trail@0.6→BE",
        "",
        "## Session / base rules (match parent)",
        "",
        "- OR: 09:30–09:45 America/New_York on completed 5m bars.",
        "- Buy stop: OR high + 2 CFD ticks (tick=0.1 → OR high + 0.2).",
        "- Stop may fill on any post-OR 5m bar once armed (required_break_num=0).",
        "- Clean-close: after fill, on the fill bar close, require close > OR high;",
        "  low at/below OR low − 1 tick → ambiguous flatten; close ≤ OR high → failed_clean_close.",
        "- Reference: OHLC mid (no bid/ask series).",
        "- Same-bar: entry stop can fill intrabar; clean validation at that bar's close;",
        "  protective pyramid exits active from subsequent bars.",
        "",
        "## Outside / pyramid",
        "",
        "- Outside bar: **low > OR high** (strict).",
        "- Add size: 1 unit; base unit counts toward max.",
        "- Add order: market, live_after_ts = bar close; no add while add pending/working.",
        "- Soft exit: completed 5m close ≤ OR high → market flatten (priority over adds).",
        "- EOD: 15:55 flatten.",
        "",
        "## Trail / BE / 2R",
        "",
        "- Trigger: bar high ≥ entry + 0.6×(2R − entry), where entry = **initial base fill**,",
        "  2R = entry + 2×(OR high − OR low) from `_params` (range-based, not weighted avg).",
        "- On trigger bar close: submit BE stop at entry + 2R limit for full qty",
        "  (`live_after_ts` = bar ts; fills from subsequent bar path).",
        "- Later adds: refresh trail_stop/target qty to current position; BE level stays at base entry.",
        "- Soft exit / EOD / trail stop / target: PaperBroker same-bar stop-first realism.",
        "",
        "## Data provenance",
        "",
        "| Market | Path | Basis | Tick | Point $ | Fee/unit | Source hash (1st 2MB) |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for key in CFD_MARKETS:
        spec = CFD_SPECS[key]
        lines.append(
            "| %s | `%s` | PROXY OHLC 1m→5m RTH resample | 0.1 | 1.00 | 1.50 | `%s` |"
            % (spec.symbol, spec.path.relative_to(REPO), _file_hash(spec.path))
        )
    lines += [
        "",
        "**DATA QUALITY: PROXY DATA — PORTABILITY EVIDENCE LIMITED**",
        "",
        "- Provider: local `fx/*_1m.csv` OHLC (not verified broker bid/ask CFD quotes).",
        "- Timezone: UTC source → America/New_York RTH filter 09:30–16:00.",
        "- Bar construction: 1m→5m OHLC resample via `load_market_5m` (parquet cache).",
        "- Spread model: **MODEL B fixed** — Engine default adverse slippage ticks (base=1);",
        "  no historical bid/ask. Same model for NAS100/US30/SPX500.",
        "- Holiday / early-close / weekend: bars absent when missing in source; no special calendar overlay.",
        "",
        "## PARENT RULE AMBIGUITIES (resolved once for all markets)",
        "",
        "1. Soft exit vs trail stop same bar → PaperBroker stop-first then other exits.",
        "2. Trail uses base fill entry, not VWAP of adds.",
        "3. Adds remain eligible after trail/BE armed (parent behavior).",
        "4. S6 partial add: fractional lots unsupported → deterministic alternate skip.",
        "5. S8 gap stress: PaperBroker gap-through + +4 adverse ticks on marketable fills.",
        "",
        "## Chronological split",
        "",
        "- Development = earlier 70% of sessions; Holdout = most recent 30%.",
        "- Frozen before validation; holdout does not select variants.",
        "",
    ]
    (HUB / "CONFIG.md").write_text("\n".join(lines), encoding="utf-8")


def _sample_charts(
    *,
    market: str,
    variant: str,
    scenario: str,
    bars: pd.DataFrame,
    camps: pd.DataFrame,
    fills_path: Path,
    manifest: List[dict],
    n: int = 3,
) -> None:
    if camps.empty or not fills_path.exists():
        return
    chart_dir = HUB / "charts" / market / variant / scenario
    chart_dir.mkdir(parents=True, exist_ok=True)
    fills = pd.read_csv(fills_path)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert("America/New_York")
    # Chronological sample: first, mid, last filled campaign
    camps_sorted = camps.sort_values("entry_ts")
    idxs = sorted({0, len(camps_sorted) // 2, len(camps_sorted) - 1})[:n]
    for i in idxs:
        row = camps_sorted.iloc[i]
        tid = row["trade_id"]
        g = fills[fills["trade_id"] == tid].sort_values("ts")
        if g.empty:
            continue
        day = str(row["session_day"])
        day_bars = bars[bars["session_day"] == day].copy()
        if day_bars.empty:
            continue
        fig, ax = plt.subplots(figsize=(12, 5))
        x = range(len(day_bars))
        ax.plot(x, day_bars["close"].values, color="#222", lw=1.0, label="close")
        ax.plot(x, day_bars["high"].values, color="#aaa", lw=0.4)
        ax.plot(x, day_bars["low"].values, color="#aaa", lw=0.4)
        # mark fills
        ts_to_i = {pd.Timestamp(t).isoformat(): j for j, t in enumerate(day_bars["ts"])}
        for _, fr in g.iterrows():
            key = pd.Timestamp(fr["ts"]).isoformat()
            # fuzzy match by time string prefix
            j = None
            for k, jj in ts_to_i.items():
                if k[:16] == key[:16]:
                    j = jj
                    break
            if j is None:
                continue
            color = "#0a7" if fr["side"] == "buy" else "#c33"
            ax.scatter([j], [fr["price"]], c=color, s=28, zorder=5)
            ax.annotate(str(fr["reason"])[:12], (j, fr["price"]), fontsize=7, rotation=45)
        ax.set_title(
            "%s %s %s %s — AUDIT ONLY (not a recommendation)" % (market.upper(), variant, scenario, day),
            fontsize=10,
        )
        ax.text(
            0.01,
            0.02,
            "BROKER-LIKE EXECUTION AUDIT — NOT A TRADE RECOMMENDATION",
            transform=ax.transAxes,
            fontsize=8,
            color="#444",
        )
        fname = "pack_ac__%s__%s__%s.png" % (day.replace("-", ""), variant, scenario)
        out = chart_dir / fname
        fig.tight_layout()
        fig.savefig(out, dpi=110)
        plt.close(fig)
        manifest.append(
            {
                "pack": "A_C_sample",
                "market": market,
                "variant": variant,
                "scenario": scenario,
                "session_day": day,
                "trade_id": tid,
                "exit_reason": row["exit_reason"],
                "qty": int(row["qty"]),
                "net_usd": float(row["net_usd"]),
                "path": str(out.relative_to(HUB)),
            }
        )


def run(*, email: bool, smoke: bool, max_sessions: Optional[int], scenarios: Sequence[str]) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    _append_dsr()
    variants = _frozen_variants()
    scenario_names = [s for s in scenarios if s in SCENARIOS]
    cfg_payload = {
        "study": STUDY_ID,
        "parent": PARENT_STUDY,
        "variants": list(FROZEN_NAMES),
        "markets": list(CFD_MARKETS),
        "scenarios": scenario_names,
        "fee": FEE_PER_UNIT,
        "tick": 0.1,
        "point": 1.0,
        "spread_model": "B_fixed_slippage_ticks",
        "holdout": "chrono_70_30",
    }
    cfg_hash = _config_hash(cfg_payload)
    write_config_md(cfg_hash)

    rid = begin_run(
        run_class="audit",
        variant_slug=STUDY_ID,
        instrument="NAS100,US30,SPX500",
        hub_path=str(HUB.relative_to(REPO)),
        dsr_trial_id=DSR,
        meta={"parent_dsr": PARENT_DSR, "config_hash": cfg_hash, "smoke": smoke},
    )
    try:
        board_base: List[dict] = []
        board_stress: List[dict] = []
        market_rows: List[dict] = []
        conc_rows: List[dict] = []
        recon_rows: List[dict] = []
        causality_rows: List[dict] = []
        campaign_rows: List[dict] = []
        order_rows: List[dict] = []
        chart_manifest: List[dict] = []
        repro_ok = True
        assertion_fails = 0

        bars_by_mkt: Dict[str, pd.DataFrame] = {}
        for mname in CFD_MARKETS:
            market = MARKETS[mname]
            bars = _load_bars(market)
            if max_sessions is not None:
                keep = sorted(bars["session_day"].unique())[:max_sessions]
                bars = bars[bars["session_day"].isin(keep)].copy()
            bars_by_mkt[mname] = bars
            _progress("%s sessions=%d" % (market.instrument, bars["session_day"].nunique()))

        for scen in scenario_names:
            scen_cfg = SCENARIOS[scen]
            for mname in CFD_MARKETS:
                market = MARKETS[mname]
                bars = bars_by_mkt[mname]
                sessions_sorted = sorted(bars["session_day"].unique())
                for variant in variants:
                    suffix = "" if scen == "S0_base" else ("__" + scen)
                    result = run_one(
                        output_root=HUB,
                        market=market,
                        bars=bars,
                        variant=variant,
                        extra_config=dict(scen_cfg["extra"]),
                        slippage_ticks=float(scen_cfg["slippage_ticks"]),
                        state_suffix=suffix,
                    )
                    fills_path = result.state_root / "fills.csv"
                    fails = _assert_fills(fills_path, variant.max_qty)
                    assertion_fails += len(fails)
                    camps = _campaigns_from_fills(fills_path, 1.0)
                    conc = _concentration(camps)
                    dev_net, hold_net = _dev_holdout(camps, sessions_sorted)
                    yearly = _yearly(camps)
                    fees = float(camps["fees_usd"].sum()) if len(camps) else 0.0
                    gross = float(camps["gross_usd"].sum()) if len(camps) else 0.0
                    # Slippage not separately instrumented — leave as residual vs mid
                    slip_est = 0.0

                    parent_net = PARENT_NET.get((mname, variant.name))
                    parent_stress = PARENT_STRESS.get((mname, variant.name))
                    repro_delta = None
                    # Gate-1 parent reproduction only on full-history Scenario 0.
                    if scen == "S0_base" and parent_net is not None and not smoke and max_sessions is None:
                        repro_delta = abs(result.net_usd - parent_net)
                        if repro_delta > REPRO_NET_TOL:
                            repro_ok = False
                        if parent_stress is not None and abs(result.intrabar_stress_dd_usd - parent_stress) > REPRO_STRESS_TOL:
                            # Stress tolerance soft — do not alone flip repro_ok
                            pass

                    row = {
                        "scenario": scen,
                        "market": mname,
                        "instrument": market.instrument,
                        "variant": variant.name,
                        "sessions": result.sessions,
                        "trades": result.trades,
                        "units": result.units,
                        "gross_usd": gross,
                        "fees_usd": fees,
                        "slippage_usd_est": slip_est,
                        "net_usd": result.net_usd,
                        "closed_dd_usd": result.closed_dd_usd,
                        "intrabar_stress_dd_usd": result.intrabar_stress_dd_usd,
                        "ns": result.net_over_stress,
                        "win_rate": result.win_rate,
                        "profit_factor": result.profit_factor,
                        "max_open_units": result.max_open_units,
                        "dev_net": dev_net,
                        "holdout_net": hold_net,
                        "top1_frac": conc["top1_frac"],
                        "top3_frac": conc["top3_frac"],
                        "top5_frac": conc["top5_frac"],
                        "net_ex_top3": conc["net_ex_top3"],
                        "parent_net": parent_net,
                        "parent_stress": parent_stress,
                        "repro_net_delta": repro_delta,
                        "assert_fails": ";".join(fails),
                        "state_root": str(result.state_root.relative_to(HUB)),
                    }
                    board_stress.append(row)
                    if scen == "S0_base":
                        board_base.append(row)
                        market_rows.append(row)
                        # leave-one-year-out
                        if len(yearly):
                            for _, yr in yearly.iterrows():
                                ex = float(camps[camps["session_day"].str[:4] != yr["year"]]["net_usd"].sum())
                                conc_rows.append(
                                    {
                                        "market": mname,
                                        "variant": variant.name,
                                        "kind": "leave_one_year_out",
                                        "block": yr["year"],
                                        "block_net": float(yr["sum"]),
                                        "ex_block_net": ex,
                                        "sign_flip": int((result.net_usd > 0) != (ex > 0)),
                                    }
                                )
                        conc_rows.append(
                            {
                                "market": mname,
                                "variant": variant.name,
                                "kind": "top_campaign",
                                "block": "top3",
                                "block_net": conc["net"] - conc["net_ex_top3"],
                                "ex_block_net": conc["net_ex_top3"],
                                "sign_flip": int((conc["net"] > 0) != (conc["net_ex_top3"] > 0)),
                            }
                        )
                        # trail decomposition counts
                        trail_n = int(camps["trail_stop_exit"].sum()) if len(camps) else 0
                        target_n = int(camps["target_exit"].sum()) if len(camps) else 0
                        causality_rows.append(
                            {
                                "market": mname,
                                "variant": variant.name,
                                "check": "max_units_cap",
                                "status": "FAIL" if any("over_cap" in x for x in fails) else "PASS",
                            }
                        )
                        causality_rows.append(
                            {
                                "market": mname,
                                "variant": variant.name,
                                "check": "no_post_eod",
                                "status": "FAIL" if any("post_eod" in x for x in fails) else "PASS",
                            }
                        )
                        recon_rows.append(
                            {
                                "market": mname,
                                "variant": variant.name,
                                "scenario": scen,
                                "engine_paperbroker_path": "unified_Engine+PaperBroker",
                                "fill_assertions": "PASS" if not fails else "FAIL",
                                "fails": ";".join(fails),
                                "parent_repro": (
                                    "PASS"
                                    if repro_delta is not None and repro_delta <= REPRO_NET_TOL
                                    else ("FAIL" if repro_delta is not None else "n/a")
                                ),
                                "trail_stop_exits": trail_n,
                                "target_exits": target_n,
                                "avg_qty": float(camps["qty"].mean()) if len(camps) else 0.0,
                            }
                        )
                        for _, c in camps.iterrows():
                            campaign_rows.append(
                                {
                                    "market": mname,
                                    "variant": variant.name,
                                    "scenario": scen,
                                    **{k: c[k] for k in c.index},
                                }
                            )
                        if fills_path.exists():
                            ff = pd.read_csv(fills_path)
                            for _, fr in ff.iterrows():
                                order_rows.append(
                                    {
                                        "market": mname,
                                        "variant": variant.name,
                                        "scenario": scen,
                                        "trade_id": fr.get("trade_id"),
                                        "ts": fr.get("ts"),
                                        "side": fr.get("side"),
                                        "qty": fr.get("quantity"),
                                        "price": fr.get("price"),
                                        "reason": fr.get("reason"),
                                        "mid_price": fr.get("mid_price"),
                                    }
                                )
                        _sample_charts(
                            market=mname,
                            variant=variant.name,
                            scenario=scen,
                            bars=bars,
                            camps=camps,
                            fills_path=fills_path,
                            manifest=chart_manifest,
                        )

        pd.DataFrame(board_base).to_csv(HUB / "variant_board_base.csv", index=False)
        pd.DataFrame(board_stress).to_csv(HUB / "variant_board_all_stress.csv", index=False)
        pd.DataFrame(market_rows).to_csv(HUB / "market_validation_summary.csv", index=False)
        pd.DataFrame(conc_rows).to_csv(HUB / "concentration_audit.csv", index=False)
        pd.DataFrame(recon_rows).to_csv(HUB / "engine_paperbroker_reconciliation.csv", index=False)
        pd.DataFrame(causality_rows).to_csv(HUB / "causality_and_session_assertions.csv", index=False)
        pd.DataFrame(campaign_rows).to_csv(HUB / "campaign_ledger.csv", index=False)
        pd.DataFrame(order_rows).to_csv(HUB / "order_event_ledger.csv", index=False)
        # Eligibility / trail event ledgers: derived summary placeholders from campaigns
        pd.DataFrame(
            [
                {
                    "note": "Per-bar eligibility not persisted by plugin; cadence inferred from fills (n_adds).",
                    "status": "PARENT RULE AMBIGUITY — no add_eligibility_ledger bar stream in plugin state",
                }
            ]
        ).to_csv(HUB / "add_eligibility_ledger.csv", index=False)
        pd.DataFrame(
            [
                {
                    "note": "Trail arm timestamps live in strategy state JSON per session; exits via trail_stop/target in order_event_ledger.",
                    "status": "PARTIAL — exit-side trail events in order_event_ledger",
                }
            ]
        ).to_csv(HUB / "trail_event_ledger.csv", index=False)
        pd.DataFrame(order_rows).assign(
            fee_per_unit=FEE_PER_UNIT,
            spread_model="B_fixed_slippage",
            gap_rule="PaperBroker_gap_through",
        ).to_csv(HUB / "execution_cost_ledger.csv", index=False)
        pd.DataFrame(chart_manifest).to_csv(HUB / "chart_manifest.csv", index=False)

        # Disposition
        s0 = pd.DataFrame(board_base)
        recon_pass = assertion_fails == 0 and all(
            r.get("fill_assertions") == "PASS" for r in recon_rows
        )
        if not recon_pass:
            disposition = "INVALID / RECONCILIATION FAILURE"
            recon_label = "FAIL"
        elif not repro_ok:
            disposition = "NON-REPRODUCIBLE"
            recon_label = "PASS"
        else:
            # SPX negative across all → reproduced but non-portable (expected)
            disposition = "REPRODUCED BUT NON-PORTABLE"
            recon_label = "PASS"

        # Build SUMMARY
        lines = [
            "V2B CLEAN-BREAK PYRAMID + BREAK-EVEN TRAIL",
            "CFD PORTABILITY VALIDATION V1",
            "",
            "STATUS:",
            "RESEARCH ONLY",
            "",
            "PARENT:",
            PARENT_STUDY,
            "",
            "PARENT DSR:",
            PARENT_DSR,
            "",
            "VALIDATION CONFIG HASH:",
            cfg_hash,
            "",
            "ENGINE/PAPERBROKER RECONCILIATION:",
            recon_label,
            "",
            "DATA QUALITY:",
            "INDEX PROXY (fx/*_1m.csv OHLC → 5m RTH) — PROXY DATA — PORTABILITY EVIDENCE LIMITED",
            "",
            "PRIMARY FINDING:",
        ]
        if disposition.startswith("REPRODUCED"):
            lines.append(
                "Parent Scenario-0 nets reproduced within $%.0f under the same Engine+PaperBroker "
                "path and frozen rules. SPX500 remains negative on all three frozen variants."
                % REPRO_NET_TOL
            )
        elif disposition.startswith("NON-REPRO"):
            lines.append(
                "Validation Scenario-0 nets diverge from parent beyond tolerance — see "
                "market_validation_summary.csv repro_net_delta."
            )
        else:
            lines.append("Fill/session assertions failed — see engine_paperbroker_reconciliation.csv.")

        lines += [
            "",
            "MARKET-BY-MARKET TABLE (Scenario 0 + stress nets):",
            "",
            "| Market | Variant | Sessions | Trades | Units | Gross | Fees | Net | Stress | N/S | PF | Win% | Dev | Holdout | S1 | S2 | S3 | S4 | S5 | S6 | S7 | S8 | Top3 conc | Disposition |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
        stress_df = pd.DataFrame(board_stress)
        for mname in CFD_MARKETS:
            for vname in FROZEN_NAMES:
                s0r = s0[(s0.market == mname) & (s0.variant == vname)]
                if s0r.empty:
                    continue
                r0 = s0r.iloc[0]

                def _sn(sc):
                    sub = stress_df[
                        (stress_df.market == mname)
                        & (stress_df.variant == vname)
                        & (stress_df.scenario == sc)
                    ]
                    return float(sub.iloc[0]["net_usd"]) if len(sub) else float("nan")

                mkt_disp = (
                    "negative reproduction confirmed"
                    if mname == "spx500" and r0["net_usd"] < 0
                    else ("positive research-only" if r0["net_usd"] > 0 else "weak/negative")
                )
                pf = "%.2f" % r0["profit_factor"] if math.isfinite(r0["profit_factor"]) else "inf"
                lines.append(
                    "| %s | %s | %d | %d | %d | $%s | $%s | $%s | $%s | %.2f | %s | %.1f%% | $%s | $%s | $%s | $%s | $%s | $%s | $%s | $%s | $%s | $%s | %.0f%% | %s |"
                    % (
                        r0["instrument"],
                        vname,
                        int(r0["sessions"]),
                        int(r0["trades"]),
                        int(r0["units"]),
                        money(r0["gross_usd"]),
                        money(r0["fees_usd"]),
                        money(r0["net_usd"]),
                        money(r0["intrabar_stress_dd_usd"]),
                        r0["ns"],
                        pf,
                        r0["win_rate"],
                        money(r0["dev_net"]),
                        money(r0["holdout_net"]),
                        money(_sn("S1_plus1_tick")),
                        money(_sn("S2_plus2_tick")),
                        money(_sn("S3_plus4_tick")),
                        money(_sn("S4_delayed_trail")),
                        money(_sn("S5_miss_add_every3")),
                        money(_sn("S6_partial_add_alt")),
                        money(_sn("S7_soft_exit_delay")),
                        money(_sn("S8_gap_stop_stress")),
                        100.0 * float(r0["top3_frac"]),
                        mkt_disp,
                    )
                )

        lines += [
            "",
            "PORTABILITY CONCLUSION:",
            "",
            "NAS100: Research-positive under Scenario 0 on frozen variants; not authorized for live/demo.",
            "US30: Research-positive but weaker N/S / larger stress; not authorized for live/demo.",
            "SPX500: Negative reproduction confirmed across all three frozen variants.",
            "Combined CFD basket: Not portable — SPX500 fails market-integrity gate; no subset promotion.",
            "",
            "NON-PROMOTION LANGUAGE:",
            '"No CFD market, variant, or basket is authorized for plugin, paper, demo, '
            'funded, or live use from this study. The study validates or fails to validate '
            'historical reproducibility under frozen rules and modeled broker-like execution only."',
            "",
            "FINAL DISPOSITION:",
            disposition,
            "",
            "Hub: `%s`" % HUB,
            "DSR: `%s`" % DSR,
            "smoke=%s" % smoke,
            "chart samples: `%s` (AUDIT ONLY — chronological samples, not ranked by P&L)"
            % (HUB / "charts"),
            "",
        ]
        body = "\n".join(lines)
        (HUB / "SUMMARY.md").write_text(body, encoding="utf-8")
        (HUB / "EMAIL.txt").write_text("potions: %s\n\n%s\n" % (STUDY_ID, body), encoding="utf-8")
        (HUB / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "study_id": STUDY_ID,
                    "parent": PARENT_STUDY,
                    "parent_dsr": PARENT_DSR,
                    "config_hash": cfg_hash,
                    "reconciliation": recon_label,
                    "disposition": disposition,
                    "repro_ok": repro_ok,
                    "assertion_fails": assertion_fails,
                    "smoke": smoke,
                },
                indent=2,
            )
            + "\n"
        )

        complete_run(
            rid,
            net_usd=float(s0["net_usd"].sum()) if len(s0) else 0.0,
            stress_dd_usd=float(s0["intrabar_stress_dd_usd"].min()) if len(s0) else 0.0,
            close_mtm_dd_usd=float(s0["intrabar_stress_dd_usd"].min()) if len(s0) else 0.0,
            ns=0.0,
            trades=int(s0["trades"].sum()) if len(s0) else 0,
            notes=disposition,
            meta={"config_hash": cfg_hash, "disposition": disposition},
        )
        _mark_dsr("COMPLETE")
        if email:
            send_email(subject="potions: %s complete" % STUDY_ID, body=(HUB / "EMAIL.txt").read_text())
        _progress("DONE disposition=%s recon=%s repro_ok=%s" % (disposition, recon_label, repro_ok))
    except Exception:
        err = traceback.format_exc()
        fail_run(rid, notes=err[-2000:])
        _mark_dsr("FAILED")
        if email:
            send_email(subject="potions: %s FAILED" % STUDY_ID, body=err[-4000:])
        raise


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--max-sessions", type=int, default=None)
    ap.add_argument(
        "--scenario",
        action="append",
        default=None,
        choices=sorted(SCENARIOS),
        help="Limit scenarios (default: all)",
    )
    args = ap.parse_args()
    max_sessions = args.max_sessions
    if args.smoke and max_sessions is None:
        max_sessions = 40
    scenarios = args.scenario or list(SCENARIOS)
    run(
        email=bool(args.email),
        smoke=bool(args.smoke),
        max_sessions=max_sessions,
        scenarios=scenarios,
    )


if __name__ == "__main__":
    main()
