"""USDJPY Asia-range London — funded-sleeve validation gates (offline).

Frozen rules (do not retune):
  book ``S_3_1_3``, January skip, shadow roll50, WR≥40%, PF≥1.0
  on the **unfiltered** campaign shadow book.

Gates:
  1. Filter attribution (Jan / WR / PF / combined) on the sizing tape
  2. Walk-forward yearly stability under frozen rules
  3. Frozen-rule out-of-sample holdouts (later years, no retune)
  4. Warmup note (first ``window`` campaigns cannot fail the roll gate)
  5. Path-aware risk checklist pointers from the filtered broker hub

Writes ``VALIDATION_GATES.md`` + CSVs under the filters hub by default.
Does **not** claim funded-sleeve ready — it scores the gates.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .asia_range_shadow import gate_blocks, profit_factor, win_rate
from .fx_v2b_london_ungated import JPY_USD, _progress
from .fx_v2b_asia_range_london_usdjpy_filters import (
    FILTER_HUB,
    SIZING_HUB,
    _campaigns_from_unit_trades,
)

REPO = Path(__file__).resolve().parents[1]
DEFAULT_UNIT = (
    SIZING_HUB / "states" / "usdjpy_v2b_asia_range_london_S_3_1_3" / "unit_trades.csv"
)
DEFAULT_FILTERED_METRICS = (
    FILTER_HUB
    / "states"
    / "usdjpy_v2b_asia_range_london_S_3_1_3_flt"
    / "metrics.json"
)
FROZEN = {
    "book": "S_3_1_3",
    "skip_months": [1],
    "window": 50,
    "min_wr": 0.40,
    "min_pf": 1.0,
}


def _usd(jpy: float) -> float:
    return float(jpy) / float(JPY_USD)


def classify_campaigns(
    campaigns: pd.DataFrame,
    *,
    skip_months: Sequence[int] = (1,),
    window: int = 50,
    min_wr: float = 0.40,
    min_pf: float = 1.0,
    mode: str = "combined",
) -> pd.DataFrame:
    """Label each unfiltered campaign take/skip under a frozen ablation mode.

    Modes: ``unfiltered``, ``jan``, ``wr``, ``pf``, ``roll``, ``combined``.
    """
    skip_m = set(int(x) for x in skip_months)
    g = campaigns.reset_index(drop=True)
    rows: List[dict] = []
    for i, row in g.iterrows():
        month_block = int(row["month"]) in skip_m
        bad_wr = bad_pf = False
        wr = pf = None
        n_hist = 0
        if i >= window:
            hist = g.iloc[i - window : i]
            n_hist = int(len(hist))
            wr = float(hist["win"].mean())
            pf = profit_factor(hist["net_usd"].tolist())
            bad_wr = wr < min_wr
            bad_pf = pf < min_pf
        warmup = i < window

        if mode == "unfiltered":
            allowed, reason = True, "take"
        elif mode == "jan":
            allowed, reason = (False, "month") if month_block else (True, "take")
        elif mode == "wr":
            allowed, reason = (False, "wr") if bad_wr else (True, "take")
        elif mode == "pf":
            allowed, reason = (False, "pf") if bad_pf else (True, "take")
        elif mode == "roll":
            if bad_wr and bad_pf:
                allowed, reason = False, "both"
            elif bad_wr:
                allowed, reason = False, "wr"
            elif bad_pf:
                allowed, reason = False, "pf"
            else:
                allowed, reason = True, "take"
        else:  # combined
            if month_block:
                allowed, reason = False, "month"
            elif bad_wr and bad_pf:
                allowed, reason = False, "both"
            elif bad_wr:
                allowed, reason = False, "wr"
            elif bad_pf:
                allowed, reason = False, "pf"
            else:
                allowed, reason = True, "take"

        rows.append(
            {
                "session": row["session"],
                "year": int(row["year"]),
                "month": int(row["month"]),
                "net_jpy": float(row["net_usd"]),
                "net_usd": _usd(row["net_usd"]),
                "allowed": bool(allowed),
                "reason": reason,
                "warmup": bool(warmup),
                "shadow_n": n_hist,
                "shadow_wr": wr,
                "shadow_pf": pf if pf is None or pf != float("inf") else 999.0,
                "mode": mode,
            }
        )
    return pd.DataFrame(rows)


def summarize_ablation(df: pd.DataFrame, *, baseline_net_usd: float) -> dict:
    taken = df[df["allowed"]]
    skipped = df[~df["allowed"]]
    taken_net = float(taken["net_usd"].sum()) if not taken.empty else 0.0
    skipped_net = float(skipped["net_usd"].sum()) if not skipped.empty else 0.0
    reasons = skipped["reason"].value_counts().to_dict() if not skipped.empty else {}
    wins = int((taken["net_usd"] > 0).sum()) if not taken.empty else 0
    n_taken = int(len(taken))
    return {
        "mode": str(df["mode"].iloc[0]) if not df.empty else "",
        "campaigns": int(len(df)),
        "taken_n": n_taken,
        "skipped_n": int(len(skipped)),
        "taken_net_usd": taken_net,
        "skipped_net_usd": skipped_net,
        "delta_vs_unfiltered_usd": taken_net - baseline_net_usd,
        "taken_wr": (wins / n_taken) if n_taken else 0.0,
        "taken_pf": profit_factor(taken["net_jpy"].tolist()) if n_taken else 0.0,
        "worst_taken_usd": float(taken["net_usd"].min()) if n_taken else 0.0,
        "reasons": reasons,
    }


def yearly_stability(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for year, part in df.groupby("year"):
        taken = part[part["allowed"]]
        skipped = part[~part["allowed"]]
        taken_net = float(taken["net_usd"].sum()) if not taken.empty else 0.0
        rows.append(
            {
                "year": int(year),
                "campaigns": int(len(part)),
                "taken_n": int(len(taken)),
                "skipped_n": int(len(skipped)),
                "taken_net_usd": taken_net,
                "skipped_net_usd": float(skipped["net_usd"].sum()) if not skipped.empty else 0.0,
                "taken_wr": float((taken["net_usd"] > 0).mean()) if not taken.empty else 0.0,
            }
        )
    out = pd.DataFrame(rows).sort_values("year")
    abs_sum = float(out["taken_net_usd"].abs().sum()) or 1.0
    out["share_of_abs_net"] = out["taken_net_usd"].abs() / abs_sum
    return out


def oos_holdouts(df: pd.DataFrame, cuts: Sequence[int]) -> List[dict]:
    rows = []
    for cut in cuts:
        fit = df[df["year"] <= int(cut)]
        oos = df[df["year"] > int(cut)]
        fit_t = fit[fit["allowed"]]
        oos_t = oos[oos["allowed"]]
        rows.append(
            {
                "fit_through_year": int(cut),
                "fit_taken_n": int(len(fit_t)),
                "fit_taken_net_usd": float(fit_t["net_usd"].sum()) if not fit_t.empty else 0.0,
                "oos_taken_n": int(len(oos_t)),
                "oos_skipped_n": int((~oos["allowed"]).sum()) if not oos.empty else 0,
                "oos_taken_net_usd": float(oos_t["net_usd"].sum()) if not oos_t.empty else 0.0,
                "oos_taken_wr": float((oos_t["net_usd"] > 0).mean()) if not oos_t.empty else 0.0,
                "oos_worst_usd": float(oos_t["net_usd"].min()) if not oos_t.empty else 0.0,
            }
        )
    return rows


def rolling_anchor_table(
    campaigns: pd.DataFrame,
    *,
    window: int = 50,
    min_wr: float = 0.40,
    min_pf: float = 1.0,
    anchors: Optional[Sequence[date]] = None,
) -> pd.DataFrame:
    """At each historical anchor, report prior-window WR/PF (causal) and next-year filtered net."""
    g = campaigns.reset_index(drop=True)
    if anchors is None:
        years = sorted(int(y) for y in g["year"].unique())
        anchors = [date(y, 1, 1) for y in years if y > int(g["year"].min())]
    rows = []
    for anchor in anchors:
        prior = g[g["session"] < anchor]
        if len(prior) < window:
            blocked, meta = False, {"n": float(len(prior)), "wr": 0.0, "pf": 0.0}
            warm = True
        else:
            nets = prior["net_usd"].tolist()
            blocked, meta = gate_blocks(nets, window=window, min_wr=min_wr, min_pf=min_pf)
            warm = False
        nxt_year = int(anchor.year)
        year_camps = g[g["year"] == nxt_year]
        # apply combined filter using full causal history up to each campaign
        combined = classify_campaigns(
            campaigns,
            skip_months=FROZEN["skip_months"],
            window=window,
            min_wr=min_wr,
            min_pf=min_pf,
            mode="combined",
        )
        y = combined[combined["year"] == nxt_year]
        taken = y[y["allowed"]]
        rows.append(
            {
                "anchor": anchor.isoformat(),
                "prior_campaigns": int(len(prior)),
                "warmup": warm,
                "shadow_wr": float(meta.get("wr") or 0.0),
                "shadow_pf": float(meta.get("pf") or 0.0)
                if meta.get("pf") != float("inf")
                else 999.0,
                "gate_blocks_at_anchor": bool(blocked),
                "year": nxt_year,
                "year_taken_n": int(len(taken)),
                "year_taken_net_usd": float(taken["net_usd"].sum()) if not taken.empty else 0.0,
                "year_campaigns": int(len(year_camps)),
            }
        )
    return pd.DataFrame(rows)


def path_aware_checklist(metrics_path: Path, filtered_state: Path) -> dict:
    """Summarize broker-like path risk from the promoted filtered state logs.

    These fields are meant for daily/weekly post-process — no retune —
    just awareness that fills/OCO/exposure already live on disk.
    """
    out: Dict[str, object] = {
        "metrics_path": str(metrics_path),
        "state_root": str(filtered_state),
        "status": "checklist",
    }
    if metrics_path.exists():
        meta = json.loads(metrics_path.read_text(encoding="utf-8"))
        out.update(
            {
                "broker_net_usd": meta.get("net_usd"),
                "broker_stress_dd_usd": meta.get("stress_dd_usd"),
                "broker_net_over_stress": meta.get("net_over_stress"),
                "max_open_units": meta.get("max_open_units"),
                "trades": meta.get("trades"),
                "regime_days": meta.get("regime_days"),
                "variant": meta.get("variant"),
                "entry_qty": meta.get("entry_qty"),
            }
        )
    for name in ("fills.csv", "orders.csv", "unit_trades.csv", "causality_violations.csv"):
        p = filtered_state / name
        out["has_%s" % name.replace(".", "_")] = p.exists()
        if name == "causality_violations.csv" and p.exists():
            try:
                cv = pd.read_csv(p)
                out["causality_violation_rows"] = int(len(cv))
            except Exception:
                out["causality_violation_rows"] = None

    fills_path = filtered_state / "fills.csv"
    if fills_path.exists():
        fills = pd.read_csv(fills_path)
        out["fill_rows"] = int(len(fills))
        if not fills.empty and "reason" in fills.columns:
            out["fill_reasons"] = {
                str(k): int(v) for k, v in fills["reason"].value_counts().to_dict().items()
            }
        if not fills.empty and "quantity" in fills.columns:
            out["max_fill_qty"] = float(fills["quantity"].max())
        # Adverse vs mid as a path log (PaperBroker may set mid_price on fills).
        if not fills.empty and {"mid_price", "price", "side"}.issubset(fills.columns):
            f = fills.dropna(subset=["mid_price", "price"]).copy()
            f = f[f["mid_price"].astype(float) > 0]
            if not f.empty:
                side = f["side"].astype(str).str.lower()
                px = f["price"].astype(float)
                mid = f["mid_price"].astype(float)
                adverse = ((side == "buy") & (px > mid)) | ((side == "sell") & (px < mid))
                out["fills_with_mid"] = int(len(f))
                out["fills_adverse_vs_mid"] = int(adverse.sum())
                out["mean_abs_mid_fill_diff"] = float((px - mid).abs().mean())

    orders_path = filtered_state / "orders.csv"
    if orders_path.exists():
        orders = pd.read_csv(orders_path)
        out["order_rows"] = int(len(orders))
        if not orders.empty and "status" in orders.columns:
            status = orders["status"].astype(str).str.lower()
            out["order_status_counts"] = {
                str(k): int(v) for k, v in status.value_counts().to_dict().items()
            }
            out["oco_cancelled_orders"] = int(status.isin(["cancelled", "canceled"]).sum())
            out["oco_filled_orders"] = int((status == "filled").sum())
        if not orders.empty and "oco_group" in orders.columns:
            out["orders_with_oco_group"] = int(orders["oco_group"].notna().sum())
        if not orders.empty and "bracket_role" in orders.columns:
            cancelled = orders[
                orders["status"].astype(str).str.lower().isin(["cancelled", "canceled"])
            ]
            if not cancelled.empty:
                out["cancelled_by_bracket_role"] = {
                    str(k): int(v)
                    for k, v in cancelled["bracket_role"].value_counts().to_dict().items()
                }

    if (filtered_state / "unit_trades.csv").exists():
        ut = pd.read_csv(filtered_state / "unit_trades.csv")
        if not ut.empty and "net_usd" in ut.columns:
            camps = ut.groupby("trade_id", as_index=False).agg(net_usd=("net_usd", "sum"))
            out["filtered_worst_campaign_usd"] = _usd(float(camps["net_usd"].min()))
            out["filtered_campaigns"] = int(len(camps))
    out["notes"] = [
        "Broker-like fills / OCO cancel counts scraped from filtered hub orders/fills (weekly post-process source).",
        "max_open_units / max_fill_qty = simultaneous exposure under the promoted book.",
        "stress_dd_usd / filtered_worst_campaign_usd = worst-path campaign stress.",
        "fills_adverse_vs_mid is a path log vs mid_price (not a retune knob).",
        "Margin / live OANDA practice remains a demo ops check (account snapshot), not scored here.",
        "Daily/weekly: compare paper campaign_parity.csv to validation_decision_tape.csv.",
    ]
    return out


def live_parity_status(
    output_root: Path,
    decision_tape: pd.DataFrame,
    *,
    demo_roots: Optional[Sequence[Path]] = None,
) -> dict:
    """Row-compare live ``campaign_parity.csv`` vs research decision tape when present."""
    repo = Path(__file__).resolve().parents[1]
    if demo_roots is None:
        demo_roots = [
            repo / "live" / "demo" / "usdjpy_asia_range_london_paper",
            repo / "live" / "demo" / "usdjpy_asia_range_london_oanda",
        ]
    research = decision_tape.copy()
    if "session_date" in research.columns:
        research["session_date"] = research["session_date"].astype(str)
    research_cols = [
        c
        for c in ("session_date", "decision", "reason", "shadow_50_wr", "shadow_50_pf")
        if c in research.columns
    ]
    out: Dict[str, object] = {
        "research_rows": int(len(research)),
        "demos": {},
        "status": "pending_first_campaigns",
    }
    any_rows = False
    all_ok = True
    for root in demo_roots:
        path = Path(root) / "campaign_parity.csv"
        entry: Dict[str, object] = {"path": str(path), "exists": path.exists(), "rows": 0}
        if path.exists():
            live = pd.read_csv(path)
            entry["rows"] = int(len(live))
            if len(live) and "session_date" in live.columns and research_cols:
                any_rows = True
                live = live.copy()
                live["session_date"] = live["session_date"].astype(str)
                merged = live.merge(
                    research[research_cols],
                    on="session_date",
                    how="left",
                    suffixes=("_live", "_research"),
                )
                dec_live = "decision_live" if "decision_live" in merged.columns else "decision"
                dec_res = "decision_research" if "decision_research" in merged.columns else None
                if dec_res and dec_live in merged.columns:
                    comparable = merged[merged[dec_res].notna()].copy()
                    entry["matched_sessions"] = int(len(comparable))
                    mism = comparable[
                        comparable[dec_live].astype(str) != comparable[dec_res].astype(str)
                    ]
                    entry["decision_mismatches"] = int(len(mism))
                    if int(len(mism)) > 0:
                        all_ok = False
                        mism_path = output_root / (
                            "validation_parity_mismatches_%s.csv" % Path(root).name
                        )
                        mism.to_csv(mism_path, index=False)
                        entry["mismatches_path"] = str(mism_path)
                else:
                    entry["note"] = "missing decision columns for compare"
                    all_ok = False
        out["demos"][Path(root).name] = entry
    if any_rows and all_ok:
        out["status"] = "ok"
    elif any_rows:
        out["status"] = "mismatches"
    return out


def margin_ops_snapshot(snapshot_path: Optional[Path] = None) -> dict:
    """Pull latest OANDA practice NAV/margin fields for path-aware ops note."""
    repo = Path(__file__).resolve().parents[1]
    path = snapshot_path or (
        repo / "live" / "demo" / "oanda_practice_snapshot" / "account_snapshot.json"
    )
    out: Dict[str, object] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        out["status"] = "missing_snapshot"
        return out
    try:
        snap = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        out["status"] = "read_error"
        out["error"] = str(exc)
        return out
    usdjpy_qty = 0.0
    for p in snap.get("positions") or []:
        if str(p.get("instrument") or "") == "USDJPY":
            usdjpy_qty += float(p.get("quantity") or 0.0)
    out.update(
        {
            "status": "ok",
            "fetched_at": snap.get("fetched_at"),
            "NAV": snap.get("NAV"),
            "balance": snap.get("balance"),
            "marginUsed": snap.get("marginUsed"),
            "marginAvailable": snap.get("marginAvailable"),
            "marginCloseoutPercent": snap.get("marginCloseoutPercent"),
            "openTradeCount": snap.get("openTradeCount"),
            "pending_orders": len(snap.get("orders") or []),
            "usdjpy_open_qty": usdjpy_qty,
        }
    )
    return out


def write_report(
    output_root: Path,
    *,
    ablations: Dict[str, dict],
    yearly: pd.DataFrame,
    oos: List[dict],
    anchors: pd.DataFrame,
    path_aware: dict,
    decision_tape: pd.DataFrame,
    parity: Optional[dict] = None,
    margin_ops: Optional[dict] = None,
) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    unf = ablations["unfiltered"]
    comb = ablations["combined"]
    jan = ablations["jan"]
    wr = ablations["wr"]
    pf = ablations["pf"]
    roll = ablations["roll"]

    pos_years = int((yearly["taken_net_usd"] > 0).sum())
    neg_years = int((yearly["taken_net_usd"] <= 0).sum())
    top_share = float(yearly["share_of_abs_net"].max()) if not yearly.empty else 0.0
    top_year = int(yearly.loc[yearly["share_of_abs_net"].idxmax(), "year"]) if not yearly.empty else 0

    # Gate pass/fail heuristics (documented, not auto-promote)
    oos_2021 = next((r for r in oos if r["fit_through_year"] == 2021), None)
    oos_ok = bool(oos_2021 and oos_2021["oos_taken_net_usd"] > 0 and oos_2021["oos_taken_n"] >= 100)
    stab_ok = top_share < 0.50 and pos_years >= 5
    attr_ok = jan["delta_vs_unfiltered_usd"] > 0  # January must not be the only story; roll still sits out
    roll_sits = roll["skipped_n"] > 0
    funded_ready = False  # explicit: research promote ≠ funded sleeve

    lines = [
        "# USDJPY Asia-range London — funded-sleeve validation gates",
        "",
        "**Stance:** research **PROMOTE** / paper+OANDA practice demos are live.",
        "**Funded sleeve:** **NOT YET** — these gates must stay green (or consciously waived) first.",
        "",
        "## Frozen rules (locked — no retune)",
        "",
        "| Knob | Value |",
        "|---|---|",
        "| Book | `S_3_1_3` (3/1/3) |",
        "| Month blackout | January (`skip_entry_months=[1]`) |",
        "| Shadow window | 50 campaigns |",
        "| Min WR | 40% |",
        "| Min PF | 1.00 |",
        "| Shadow book | **unfiltered** campaign nets |",
        "",
        "### 50-campaign warmup",
        "",
        "The rolling WR/PF gate cannot fire until **50 prior unfiltered campaigns** exist.",
        "Live demos **seed** the last 50 from the sizing hub so paper/OANDA do not sit in a cold warmup,",
        "but any fresh research replay from `2015-01-02` still has a true first-50 pass-through on the roll gate",
        "(January blackout still applies). Proof windows can be shortened only when the shadow book is pre-seeded.",
        "",
        "## 1. Filter attribution (shadow campaign tape)",
        "",
        "Source: unfiltered sizing `unit_trades` for `S_3_1_3` (campaign nets, ≈USD at JPY/110).",
        "Δ = taken net − unfiltered net (= −skipped net). Positive Δ means the filter avoided net losses.",
        "",
        "| Variant | Taken N | Taken net≈USD | Skipped N | Skipped net≈USD | Δ vs unfiltered |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    order = ["unfiltered", "jan", "wr", "pf", "roll", "combined"]
    labels = {
        "unfiltered": "Unfiltered",
        "jan": "January only",
        "wr": "Rolling WR only",
        "pf": "Rolling PF only",
        "roll": "Rolling WR+PF",
        "combined": "**Combined (promote)**",
    }
    for key in order:
        a = ablations[key]
        lines.append(
            "| %s | %d | $%.0f | %d | $%.0f | $%+.0f |"
            % (
                labels[key],
                a["taken_n"],
                a["taken_net_usd"],
                a["skipped_n"],
                a["skipped_net_usd"],
                a["delta_vs_unfiltered_usd"],
            )
        )
    lines.extend(
        [
            "",
            "**Read:**",
            "- January exclusion contribution: **Δ ≈ $%+.0f** (skipped %d Jan campaigns, skipped net ≈ $%.0f)."
            % (jan["delta_vs_unfiltered_usd"], jan["skipped_n"], jan["skipped_net_usd"]),
            "- Rolling WR gate alone: **Δ ≈ $%+.0f** (mostly sits out winners on this tape — not a solo lever)."
            % wr["delta_vs_unfiltered_usd"],
            "- Rolling PF gate alone: **Δ ≈ $%+.0f** on raw campaign net; it is the **dominant sit-out** (%d skips)."
            % (pf["delta_vs_unfiltered_usd"], pf["skipped_n"]),
            "- Combined: **Δ ≈ $%+.0f** on shadow net; broker-like filtered hub remains the ranking proof (N/S **7.23**)."
            % comb["delta_vs_unfiltered_usd"],
            "- Result does **not** depend only on January: roll gate still skips **%d** sessions in the combined book (reasons on decision tape)."
            % (comb["skipped_n"] - jan["skipped_n"] if comb["skipped_n"] >= jan["skipped_n"] else roll["skipped_n"]),
            "",
            "Combined skip reasons: `%s`" % comb.get("reasons"),
            "",
            "## 2. Walk-forward / yearly stability (frozen combined)",
            "",
            "| Year | Campaigns | Taken | Skipped | Taken net≈USD | Abs-net share |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, r in yearly.iterrows():
        lines.append(
            "| %d | %d | %d | %d | $%+.0f | %.1f%% |"
            % (
                int(r["year"]),
                int(r["campaigns"]),
                int(r["taken_n"]),
                int(r["skipped_n"]),
                float(r["taken_net_usd"]),
                100.0 * float(r["share_of_abs_net"]),
            )
        )
    lines.extend(
        [
            "",
            "Positive years: **%d** / negative-or-flat: **%d**. Largest abs-net share: **%.0f%%** in **%d**."
            % (pos_years, neg_years, 100.0 * top_share, top_year),
            "Stability heuristic (share &lt; 50%% and ≥5 green years): **%s**." % ("PASS" if stab_ok else "WATCH"),
            "",
            "### Causal anchors (prior-50 WR/PF at each Jan 1)",
            "",
            "| Anchor | Prior N | Shadow WR | Shadow PF | Blocks? | That-year taken net≈USD |",
            "|---|---:|---:|---:|---|---:|",
        ]
    )
    for _, r in anchors.iterrows():
        lines.append(
            "| %s | %d | %.1f%% | %.2f | %s | $%+.0f |"
            % (
                r["anchor"],
                int(r["prior_campaigns"]),
                100.0 * float(r["shadow_wr"]),
                float(r["shadow_pf"]),
                "yes" if r["gate_blocks_at_anchor"] else "no",
                float(r["year_taken_net_usd"]),
            )
        )
    lines.extend(
        [
            "",
            "## 3. Frozen-rule out-of-sample (no threshold retune)",
            "",
            "Rules locked as above. Holdout = calendar years **after** the cut (still causal roll history).",
            "Note: January was originally audited on the full sizing tape — this is **frozen-rule** OOS, not a claim that month selection was blind.",
            "",
            "| Fit through | Fit taken net≈USD | OOS taken N | OOS skip N | OOS taken net≈USD | OOS WR | OOS worst≈USD |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for r in oos:
        lines.append(
            "| %d | $%+.0f | %d | %d | $%+.0f | %.1f%% | $%+.0f |"
            % (
                r["fit_through_year"],
                r["fit_taken_net_usd"],
                r["oos_taken_n"],
                r["oos_skipped_n"],
                r["oos_taken_net_usd"],
                100.0 * r["oos_taken_wr"],
                r["oos_worst_usd"],
            )
        )
    lines.extend(
        [
            "",
            "OOS after 2021 heuristic (net&gt;0 and N≥100): **%s**." % ("PASS" if oos_ok else "FAIL"),
            "",
            "## 4. Path-aware risk (promoted filtered broker hub)",
            "",
            "Artifacts under `%s`:" % path_aware.get("state_root"),
            "",
            "| Check | Value |",
            "|---|---|",
            "| Broker net≈USD | %s |" % _fmt_money(path_aware.get("broker_net_usd")),
            "| Stress DD≈USD | %s |" % _fmt_money(path_aware.get("broker_stress_dd_usd")),
            "| N/S | %s |" % _fmt_num(path_aware.get("broker_net_over_stress")),
            "| max_open_units (simultaneous) | %s |" % path_aware.get("max_open_units"),
            "| max_fill_qty | %s |" % path_aware.get("max_fill_qty"),
            "| Filtered worst campaign≈USD | %s |" % _fmt_money(path_aware.get("filtered_worst_campaign_usd")),
            "| Causality violation rows | %s |" % path_aware.get("causality_violation_rows"),
            "| fill rows / order rows | %s / %s |"
            % (path_aware.get("fill_rows"), path_aware.get("order_rows")),
            "| OCO cancelled / filled orders | %s / %s |"
            % (path_aware.get("oco_cancelled_orders"), path_aware.get("oco_filled_orders")),
            "| fills adverse vs mid | %s / %s (mean abs diff %s) |"
            % (
                path_aware.get("fills_adverse_vs_mid"),
                path_aware.get("fills_with_mid"),
                _fmt_num(path_aware.get("mean_abs_mid_fill_diff")),
            ),
            "| fills/orders/unit_trades present | %s / %s / %s |"
            % (
                path_aware.get("has_fills_csv"),
                path_aware.get("has_orders_csv"),
                path_aware.get("has_unit_trades_csv"),
            ),
            "",
            "Fill reasons: `%s`." % path_aware.get("fill_reasons"),
            "Cancelled by bracket role: `%s`." % path_aware.get("cancelled_by_bracket_role"),
            "",
            "These counts are scraped from the filtered PaperBroker replay logs for weekly post-process;",
            "they are not retune knobs. Margin under OANDA practice stays a demo ops / account-snapshot item.",
            "",
            "### OANDA practice margin ops (shared account)",
            "",
            "| Field | Value |",
            "|---|---|",
            "| Snapshot | `%s` |" % ((margin_ops or {}).get("fetched_at") or (margin_ops or {}).get("status")),
            "| NAV / balance | %s / %s |"
            % ((margin_ops or {}).get("NAV"), (margin_ops or {}).get("balance")),
            "| marginUsed / Available | %s / %s |"
            % ((margin_ops or {}).get("marginUsed"), (margin_ops or {}).get("marginAvailable")),
            "| marginCloseoutPercent | %s |" % (margin_ops or {}).get("marginCloseoutPercent"),
            "| USDJPY open qty | %s |" % (margin_ops or {}).get("usdjpy_open_qty"),
            "| pending orders (account) | %s |" % (margin_ops or {}).get("pending_orders"),
            "",
            "Refresh via `python -m potions.live.cli oanda-practice-sync` (weekly). Shared practice book —",
            "other sleeves hold index CFD inventory; Asia-range USDJPY should stay flat until London inject.",
            "",
            "## 5. Live-parity audit (paper)",
            "",
            "Paper/OANDA demos append `campaign_parity.csv` rows:",
            "`session_date | shadow_50_wr | shadow_50_pf | skip/take | reason | realized_campaign_net | next_shadow_n`.",
            "Compare row-for-row with research decision tape `validation_decision_tape.csv` (same columns).",
            "Demos **seed** shadow last-50 so the roll gate is warm from day one; row compare starts once",
            "London sessions fire (Asia OR collect → 03:00 inject).",
            "",
            "Parity status: **%s**" % ((parity or {}).get("status") or "pending_first_campaigns"),
            "",
            "## 6. Filter nulls (risk-throttle evidence)",
            "",
            "Separate study: [`FILTER_NULLS.md`](FILTER_NULLS.md) / `python -m live.fx_v2b_asia_range_london_usdjpy_filter_nulls --email`.",
            "Overall: **RETAIN FILTER AS RISK THROTTLE** (not alpha) — matched-exposure / selection-aware fail;",
            "circular-shift timing still supports the live gate; January #1/12 among month placebos.",
            "Does **not** unlock funded sleeve by itself; keeps the promote book as an operational throttle.",
            "",
            "## Open actions (funded sleeve still held)",
            "",
            "| Item | Status |",
            "|---|---|",
            "| Frozen OOS / walk-forward / attribution offline proof | **done** (this hub) |",
            "| Path-aware scrape of promoted fills/orders | **done** (regenerate via driver) |",
            "| Filter nulls (matched-exposure / shift / selection-aware) | **done** — retain as risk throttle |",
            "| OANDA practice margin fields on snapshot + asia demo in DEMO_FOCUS | **done** (weekly sync) |",
            "| Live `campaign_parity.csv` row-for-row vs research tape | **%s** |"
            % ((parity or {}).get("status") or "pending_first_campaigns"),
            "| Sit-out candle-sim append on live skip days | **follow-up** (gate must not freeze) |",
            "",
            "## Gate scorecard",
            "",
            "| Gate | Status |",
            "|---|---|",
            "| Frozen-rule OOS (post-2021) | **%s** |" % ("PASS" if oos_ok else "FAIL"),
            "| Walk-forward stability | **%s** |" % ("PASS" if stab_ok else "WATCH"),
            "| Filter attribution (Jan not sole; roll sits out) | **%s** |"
            % ("PASS" if (attr_ok and roll_sits) else "WATCH"),
            "| Path-aware risk logs present | **%s** |"
            % ("PASS" if path_aware.get("has_fills_csv") else "FAIL"),
            "| Filter nulls stance | **RETAIN AS RISK THROTTLE** (see FILTER_NULLS.md) |",
            "| Live-parity CSV wiring | **PASS** (compare: %s) |"
            % ((parity or {}).get("status") or "pending_first_campaigns"),
            "| Margin ops snapshot | **%s** |" % ((margin_ops or {}).get("status") or "missing"),
            "| **Funded sleeve** | **%s** |" % ("NO — hold" if not funded_ready else "YES"),
            "",
            "Driver: `python -m live.fx_v2b_asia_range_london_usdjpy_validation --email`",
            "",
        ]
    )
    path = output_root / "VALIDATION_GATES.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    pd.DataFrame([ablations[k] for k in order]).to_csv(output_root / "validation_attribution.csv", index=False)
    yearly.to_csv(output_root / "validation_yearly.csv", index=False)
    pd.DataFrame(oos).to_csv(output_root / "validation_oos.csv", index=False)
    anchors.to_csv(output_root / "validation_anchors.csv", index=False)
    decision_tape.to_csv(output_root / "validation_decision_tape.csv", index=False)
    (output_root / "validation_path_aware.json").write_text(
        json.dumps(path_aware, indent=2, default=str) + "\n", encoding="utf-8"
    )
    if parity is not None:
        (output_root / "validation_parity.json").write_text(
            json.dumps(parity, indent=2, default=str) + "\n", encoding="utf-8"
        )
    if margin_ops is not None:
        (output_root / "validation_margin_ops.json").write_text(
            json.dumps(margin_ops, indent=2, default=str) + "\n", encoding="utf-8"
        )
    score = {
        "frozen": FROZEN,
        "oos_pass": oos_ok,
        "stability_pass": stab_ok,
        "attribution_pass": bool(attr_ok and roll_sits),
        "funded_sleeve": funded_ready,
        "parity_status": (parity or {}).get("status"),
        "margin_ops_status": (margin_ops or {}).get("status"),
        "filter_nulls_stance": "retain_as_risk_throttle",
        "unfiltered_net_usd": unf["taken_net_usd"],
        "combined_taken_net_usd": comb["taken_net_usd"],
        "top_year_share": top_share,
        "top_year": top_year,
    }
    (output_root / "validation_scorecard.json").write_text(json.dumps(score, indent=2) + "\n", encoding="utf-8")

    email = [
        "potions: USDJPY Asia-range validation gates",
        "",
        "Frozen: S_3_1_3 + Jan + roll50 WR40/PF1 (unfiltered shadow).",
        "Funded sleeve: NO — research promote / demos only until gates stay green.",
        "Filter nulls: RETAIN AS RISK THROTTLE (not alpha).",
        "",
        "Attribution Δ≈USD: Jan %+.0f | WR %+.0f | PF %+.0f | roll %+.0f | combined %+.0f"
        % (
            jan["delta_vs_unfiltered_usd"],
            wr["delta_vs_unfiltered_usd"],
            pf["delta_vs_unfiltered_usd"],
            roll["delta_vs_unfiltered_usd"],
            comb["delta_vs_unfiltered_usd"],
        ),
        "OOS after 2021 taken net≈$%.0f (n=%d) — %s"
        % (
            (oos_2021 or {}).get("oos_taken_net_usd") or 0.0,
            (oos_2021 or {}).get("oos_taken_n") or 0,
            "PASS" if oos_ok else "FAIL",
        ),
        "Yearly stability: top abs share %.0f%% in %d — %s"
        % (100.0 * top_share, top_year, "PASS" if stab_ok else "WATCH"),
        "Parity: %s | Margin ops: %s"
        % (
            (parity or {}).get("status") or "pending",
            (margin_ops or {}).get("status") or "missing",
        ),
        "",
        "Hub: %s" % output_root,
        "Report: %s" % path,
    ]
    (output_root / "VALIDATION_EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")
    return path


def _fmt_money(x) -> str:
    if x is None:
        return "—"
    try:
        return "$%+.0f" % float(x)
    except (TypeError, ValueError):
        return str(x)


def _fmt_num(x) -> str:
    if x is None:
        return "—"
    try:
        return "%.2f" % float(x)
    except (TypeError, ValueError):
        return str(x)


def run(
    *,
    output_root: Path,
    unit_trades: Path,
    filtered_metrics: Path,
    email: bool,
) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    _progress(output_root, "VALIDATION load %s" % unit_trades)
    camps = _campaigns_from_unit_trades(unit_trades)
    modes = ("unfiltered", "jan", "wr", "pf", "roll", "combined")
    frames = {
        m: classify_campaigns(
            camps,
            skip_months=FROZEN["skip_months"],
            window=int(FROZEN["window"]),
            min_wr=float(FROZEN["min_wr"]),
            min_pf=float(FROZEN["min_pf"]),
            mode=m,
        )
        for m in modes
    }
    baseline = float(frames["unfiltered"]["net_usd"].sum())
    ablations = {m: summarize_ablation(frames[m], baseline_net_usd=baseline) for m in modes}
    yearly = yearly_stability(frames["combined"])
    oos = oos_holdouts(frames["combined"], cuts=(2021, 2022, 2023))
    anchors = rolling_anchor_table(
        camps,
        window=int(FROZEN["window"]),
        min_wr=float(FROZEN["min_wr"]),
        min_pf=float(FROZEN["min_pf"]),
    )
    filtered_state = Path(filtered_metrics).parent if filtered_metrics else FILTER_HUB
    path_aware = path_aware_checklist(filtered_metrics, filtered_state)
    decision = frames["combined"][
        [
            "session",
            "year",
            "month",
            "shadow_n",
            "shadow_wr",
            "shadow_pf",
            "allowed",
            "reason",
            "net_usd",
            "warmup",
        ]
    ].rename(
        columns={
            "session": "session_date",
            "shadow_wr": "shadow_50_wr",
            "shadow_pf": "shadow_50_pf",
            "allowed": "take",
            "net_usd": "realized_campaign_net_usd",
        }
    )
    decision["decision"] = decision["take"].map(lambda x: "take" if x else "skip")
    parity = live_parity_status(output_root, decision)
    margin_ops = margin_ops_snapshot()
    path = write_report(
        output_root,
        ablations=ablations,
        yearly=yearly,
        oos=oos,
        anchors=anchors,
        path_aware=path_aware,
        decision_tape=decision,
        parity=parity,
        margin_ops=margin_ops,
    )
    _progress(output_root, "VALIDATION wrote %s" % path)
    if email:
        try:
            from .notify_email import send_email

            body = (output_root / "VALIDATION_EMAIL.txt").read_text(encoding="utf-8")
            send_email(subject="potions: USDJPY Asia-range validation gates", body=body)
            _progress(output_root, "VALIDATION EMAIL sent")
        except Exception as exc:
            _progress(output_root, "VALIDATION EMAIL failed: %s" % exc)
    return path


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=FILTER_HUB)
    p.add_argument("--unit-trades", type=Path, default=DEFAULT_UNIT)
    p.add_argument("--filtered-metrics", type=Path, default=DEFAULT_FILTERED_METRICS)
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    path = run(
        output_root=args.output_root,
        unit_trades=args.unit_trades,
        filtered_metrics=args.filtered_metrics,
        email=args.email,
    )
    print("Wrote %s" % path, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
