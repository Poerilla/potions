"""TOP3 basket plus NAS100 NQ-lead prior-opposed (flat size, not NQ futures).

The NQ-futures fourth sleeve (OR-norm 2×) took ~85% of that basket's net, so
this book stays TOP3 and tries the CFD follower instead. Fills are the banked
``nas100_v2b_nq_lead_synced_S_1_1_1`` Engine tape (gate ``nq_lead_sync``).
HP size-up on this sleeve was not validated, so size is flat.

Scales walked on the same overlap window:

- **1×** native ``$1``/pt CFD
- **10×** same multiplier already used for Clean Break in this basket
- **40×** the published NQ-matched research dollar standard (entry ~$120/pt).
  Reported so the dominance is visible; it is not the add-on size.

Hub::

  live/state/top3_active_demo_portfolio/joint_1m_cb10x_plus_nas100_nq_lead/

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.top3_joint_1m_nas100_nq_lead --email
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import pandas as pd

from . import top3_joint_1m_broker_portfolio as t3
from .notify_email import send_email
from .replay_audit import POINT_VALUES
from .run_ledger import begin_run, complete_run, fail_run
from .v2b_strategy_replay import units_from_v2b_fills

REPO = t3.REPO
HUB = REPO / "live" / "state" / "top3_active_demo_portfolio" / "joint_1m_cb10x_plus_nas100_nq_lead"
FILLS = (
    REPO
    / "live/state/nas100_v2b_nq_lead_synced_broker_like/states/nas100_v2b_nq_lead_synced_S_1_1_1/fills.csv"
)
STRATEGY_ID = "nas100_v2b_nq_lead_synced_S_1_1_1"
SLEEVE = "nas100_nq_lead"
FEE = 1.50
SCALES = (1.0, 10.0, 40.0)
PRIMARY_SCALE = 10.0
PUBLISHED_TOP3_NS = 10.607987988582144


def _progress(msg: str) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(msg.rstrip() + "\n")
    try:
        print(msg, flush=True)
    except BrokenPipeError:
        pass


def load_lead_units(scale: float) -> List[t3.SleeveUnit]:
    units = units_from_v2b_fills(FILLS, STRATEGY_ID)
    pv = float(POINT_VALUES["NAS100"])
    out: List[t3.SleeveUnit] = []
    for u in units:
        out.append(
            t3.SleeveUnit(
                sleeve=SLEEVE,
                instrument="NAS100",
                unit=u,
                point_value=pv,
                fee=FEE,
                usd_div=1.0,
                size_mult=float(scale),
            )
        )
    return out


def _pack(name: str, result: dict) -> dict:
    return {
        "name": name,
        "net_usd": float(result["net_usd"]),
        "closed_dd_usd": float(result["closed_dd_usd"]),
        "intrabar_stress_dd_usd": float(result["intrabar_stress_dd_usd"]),
        "net_over_stress": float(result["net_over_stress"]),
        "max_open_units": int(result["max_open_units"]),
        "events": int(result["events"]),
        "sleeve": result["sleeve"],
    }


def _daily_pnl(rows: Sequence[dict]) -> pd.Series:
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows)
    eq = df["close_equity_usd"].astype(float)
    pnl = eq.diff()
    pnl.iloc[0] = eq.iloc[0]
    return pd.Series(pnl.to_numpy(), index=df["date"].astype(str))


def _money(x: float) -> str:
    return t3._money(x)


def _scale_label(scale: float) -> str:
    if scale == int(scale):
        return "%d×" % int(scale)
    return "%.2f×" % scale


def write_outputs(
    *,
    lo: pd.Timestamp,
    hi: pd.Timestamp,
    top3: dict,
    combined: Dict[float, dict],
    lead_only: dict,
    n_lead_units: int,
    n_lead_trades: int,
) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    primary = combined[PRIMARY_SCALE]
    pd.DataFrame(primary["equity_rows"]).to_csv(HUB / "equity_curve_1m_sample.csv", index=False)
    pd.DataFrame(primary["daily_rows"]).to_csv(HUB / "equity_curve_daily.csv", index=False)
    pd.DataFrame(top3["daily_rows"]).to_csv(HUB / "top3_equity_curve_daily.csv", index=False)
    pd.DataFrame(lead_only["daily_rows"]).to_csv(HUB / "lead_1x_equity_curve_daily.csv", index=False)

    a = _daily_pnl(top3["daily_rows"])
    b = _daily_pnl(lead_only["daily_rows"])
    both = pd.concat([a.rename("top3"), b.rename("lead")], axis=1).dropna()
    corr = float(both["top3"].corr(both["lead"])) if len(both) > 5 else float("nan")

    t3p = _pack("top3_overlap", top3)
    lead_p = _pack("nas100_nq_lead_1x", lead_only)
    rows = []
    for scale in SCALES:
        packed = _pack("top3_plus_lead_%s" % _scale_label(scale), combined[scale])
        lead_net = float(combined[scale]["sleeve"][SLEEVE]["net_usd"])
        share = (lead_net / packed["net_usd"]) if packed["net_usd"] else 0.0
        delta = packed["net_over_stress"] - t3p["net_over_stress"]
        rows.append(
            {
                "scale": scale,
                "label": _scale_label(scale),
                "combined": packed,
                "lead_net": lead_net,
                "lead_share": share,
                "delta_ns": delta,
                "improves": bool(delta > 0),
                "dominates": bool(share > 0.50),
            }
        )

    metrics = {
        "hub": str(HUB),
        "variant": "nas100_v2b_nq_lead_synced_S_1_1_1 flat size",
        "dropped": "nq_prior_opposed_rl or_norm @ 2x (NQ was ~85% of that basket net)",
        "common_window_start": lo.isoformat(),
        "common_window_end": hi.isoformat(),
        "published_top3_full_window_ns": PUBLISHED_TOP3_NS,
        "top3_overlap": t3p,
        "lead_1x": lead_p,
        "scales": [
            {
                "scale": r["scale"],
                "combined_net_usd": r["combined"]["net_usd"],
                "combined_stress_dd_usd": r["combined"]["intrabar_stress_dd_usd"],
                "combined_ns": r["combined"]["net_over_stress"],
                "delta_ns_vs_top3": r["delta_ns"],
                "lead_net_share": r["lead_share"],
                "basket_ns_improves": r["improves"],
                "lead_dominates_net": r["dominates"],
            }
            for r in rows
        ],
        "daily_close_pnl_corr_top3_vs_lead_1x": corr,
        "lead_units_full": n_lead_units,
        "lead_trades_full": n_lead_trades,
        "primary_scale": PRIMARY_SCALE,
        "method": "joint_1m_mtm_on_engine_fills",
        "hp_sizeup": "not applied; 1.25x mill was RISK THROTTLE / NOT VALIDATED",
    }
    (HUB / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    def sleeve_table(result: dict) -> List[str]:
        lines = [
            "| Sleeve | Units | Trades | Net |",
            "|---|---:|---:|---:|",
        ]
        labels = {
            "asia_range": "Asia Range",
            "monday_or": "Monday OR",
            "clean_break": "Clean Break ×10",
            SLEEVE: "NAS100 NQ-lead ×%s" % _scale_label(PRIMARY_SCALE).replace("×", ""),
        }
        for name, s in result["sleeve"].items():
            lines.append(
                "| %s | %d | %d | %s |"
                % (labels.get(name, name), int(s["units"]), int(s["trades"]), _money(float(s["net_usd"])))
            )
        return lines

    header = [
        "| Scale | Basket net | Stress DD | Basket N/S | Δ N/S vs TOP3 | Lead share of net |",
        "|---|---:|---:|---:|---:|---:|",
        "| TOP3 | %s | %s | **%.2f** |  |  |"
        % (_money(t3p["net_usd"]), _money(t3p["intrabar_stress_dd_usd"]), t3p["net_over_stress"]),
    ]
    for r in rows:
        c = r["combined"]
        header.append(
            "| TOP3 + lead %s | %s | %s | **%.2f** | **%+.2f** | %.0f%% |"
            % (
                r["label"],
                _money(c["net_usd"]),
                _money(c["intrabar_stress_dd_usd"]),
                c["net_over_stress"],
                r["delta_ns"],
                100.0 * r["lead_share"],
            )
        )
    header.append(
        "| Lead alone 1× | %s | %s | **%.2f** |  |  |"
        % (_money(lead_p["net_usd"]), _money(lead_p["intrabar_stress_dd_usd"]), lead_p["net_over_stress"])
    )

    primary_row = next(r for r in rows if r["scale"] == PRIMARY_SCALE)
    if primary_row["dominates"]:
        stance = (
            "At the Clean Break multiplier (×10) the NQ-lead sleeve is still more than half of basket net. "
            "Keep the live book at TOP3."
        )
    elif primary_row["improves"]:
        stance = (
            "At ×10 the NQ-lead sleeve raises basket N/S without taking more than half of net. "
            "Research add-on only — not a funded promote."
        )
    else:
        stance = (
            "At ×10 the NQ-lead sleeve does not raise basket N/S. Keep the live book at TOP3."
        )

    lines = [
        "# TOP3 joint 1-minute portfolio — NAS100 NQ-lead prior-opposed add-on",
        "",
        "The NQ-futures fourth sleeve is dropped. That OR-norm 2× book was ~85% of basket net.",
        "This walk keeps Asia Range, Monday OR, and Clean Break ×10, and adds the banked",
        "NAS100 NQ-lead sync prior-opposed tape (`S_1_1_1`, `nq_lead_sync`) at flat size.",
        "",
        stance,
        "",
        "## Overlap window",
        "",
        "Lead fills begin in 2021, so this is **not** the published 2016–2025 TOP3 window",
        "(that book is N/S **%.2f**). Every row below uses the same overlap." % PUBLISHED_TOP3_NS,
        "",
        *header,
        "",
        "Window %s → %s. Lead alone is the native $1/pt book (N/S is scale-invariant; net and stress scale with size). Daily close-P&L correlation vs TOP3: **%.2f**."
        % (lo.date(), hi.date(), corr),
        "",
        "Full lead tape: %d units / %d trades. Overlap sleeve nets below are the ×10 basket."
        % (n_lead_units, n_lead_trades),
        "",
        "## Sleeve nets at ×10 (overlap entries)",
        "",
        *sleeve_table(primary),
        "",
        "## Method",
        "",
        "- Asia / Monday OR / Clean Break ×10: same Engine fills as `joint_1m_cb10x`",
        "- NAS100 NQ-lead: `nas100_v2b_nq_lead_synced_S_1_1_1` fills, $1/pt, fee $1.50/unit, then ×1 / ×10 / ×40",
        "- ×10 matches the Clean Break multiplier already in this basket",
        "- ×40 is the published NQ-matched research reading (~$120 per index point at entry) and is shown because it recreates a dominant sleeve",
        "- No HP multiplier. The 1.25× mill on this book was RISK THROTTLE / NOT VALIDATED",
        "- Both NAS sleeves mark on the same NAS100 1m tape; lots stay sleeve-scoped",
        "- Causality: the lead replay recorded 29 violations (`nas100_v2b_nq_lead_synced_broker_like`). Not tick-proven",
        "",
        "Stance: live portfolio stays TOP3. NQ-lead is a research add-on candidate, not a demo wiring change.",
        "",
    ]
    (HUB / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    email_lines = [
        "TOP3 joint 1m + NAS100 NQ-lead prior-opposed (NQ futures fourth sleeve dropped)",
        "Hub: %s" % HUB,
        "Overlap window: %s → %s" % (lo.date(), hi.date()),
        "TOP3 overlap net %s stress %s N/S %.2f"
        % (_money(t3p["net_usd"]), _money(t3p["intrabar_stress_dd_usd"]), t3p["net_over_stress"]),
        "Lead alone 1× net %s stress %s N/S %.2f"
        % (_money(lead_p["net_usd"]), _money(lead_p["intrabar_stress_dd_usd"]), lead_p["net_over_stress"]),
        "Daily close P&L corr vs TOP3: %.2f" % corr,
    ]
    for r in rows:
        c = r["combined"]
        email_lines.append(
            "TOP3 + lead %s net %s stress %s N/S %.2f (Δ %+.2f, lead share %.0f%%)"
            % (
                r["label"],
                _money(c["net_usd"]),
                _money(c["intrabar_stress_dd_usd"]),
                c["net_over_stress"],
                r["delta_ns"],
                100.0 * r["lead_share"],
            )
        )
    email_lines.append(stance)
    email_lines.append(
        "Published TOP3 window (2016–2025) N/S was %.2f; this compare uses the overlap."
        % PUBLISHED_TOP3_NS
    )
    email_lines.append(
        "Stance: live book stays TOP3. No HP size-up (1.25× mill not validated). Not a demo wiring change."
    )
    (HUB / "EMAIL.txt").write_text("\n".join(email_lines) + "\n", encoding="utf-8")


def run(*, email: bool = False) -> Dict[str, object]:
    HUB.mkdir(parents=True, exist_ok=True)
    (HUB / "PROGRESS.log").write_text("", encoding="utf-8")
    rid = begin_run(
        run_class="broker_like",
        variant_slug="top3_joint_1m_cb10x_plus_nas100_nq_lead",
        instrument="PORTFOLIO",
        hub_path=str(HUB),
        meta={
            "sleeves": ["asia_range", "monday_or", "clean_break", "nas100_nq_lead"],
            "scales": list(SCALES),
            "primary_scale": PRIMARY_SCALE,
            "cb_scale": t3.CB_SCALE,
            "dropped": "nq_prior_opposed_or_norm_2x",
        },
    )
    prev_hub = t3._PROGRESS_HUB
    t3._PROGRESS_HUB = HUB
    try:
        if email:
            send_email(
                subject="potions: TOP3 + NAS100 NQ-lead prior-opposed STARTED",
                body=(
                    "NQ futures fourth sleeve dropped (it was about 85 percent of that basket net).\n"
                    "Walking TOP3 + NAS100 NQ-lead prior-opposed at 1x, 10x, and 40x.\n"
                    "Hub: %s\n" % HUB
                ),
            )
        _progress("Loading TOP3 Engine fills + NAS100 NQ-lead prior-opposed ...")
        top3_units = t3.load_sleeve_units()
        lead_1x = load_lead_units(1.0)
        n_trades = len({u.unit.trade_id for u in lead_1x})
        _progress("  lead units=%d trades=%d" % (len(lead_1x), n_trades))
        if n_trades < 100:
            raise RuntimeError("NQ-lead trade count %d is too small" % n_trades)

        all_units = list(top3_units) + list(lead_1x)
        lo, hi = t3._common_window(all_units)
        _progress("Overlap window %s → %s" % (lo, hi))
        top3_w = t3._filter_units_common(top3_units, lo, hi)
        lead_w = t3._filter_units_common(lead_1x, lo, hi)
        _progress("Overlap units top3=%d lead=%d" % (len(top3_w), len(lead_w)))

        jpy = t3.load_usdjpy_1m(lo, hi)
        nas = t3.load_nas100_1m(lo, hi)

        _progress("Walking TOP3 on overlap (%d events)..." % (len(jpy) + len(nas)))
        top3_res = t3.joint_1m_mtm(top3_w, jpy, nas, keep_bar_sample=False)
        _progress(
            "  TOP3 net=%s stress=%s N/S=%.2f"
            % (_money(float(top3_res["net_usd"])), _money(float(top3_res["intrabar_stress_dd_usd"])), float(top3_res["net_over_stress"]))
        )

        _progress("Walking NAS100 NQ-lead 1× alone ...")
        lead_res = t3.joint_1m_mtm(lead_w, [], nas, keep_bar_sample=False)
        _progress(
            "  lead 1× net=%s stress=%s N/S=%.2f"
            % (_money(float(lead_res["net_usd"])), _money(float(lead_res["intrabar_stress_dd_usd"])), float(lead_res["net_over_stress"]))
        )
        _progress(
            "  lead overlap realized %s (full-history native bank is $21129.54; overlap can be shorter)"
            % _money(float(lead_res["net_usd"]))
        )

        combined: Dict[float, dict] = {}
        for scale in SCALES:
            if scale == 1.0:
                book = list(top3_w) + list(lead_w)
            else:
                scaled = t3._filter_units_common(load_lead_units(scale), lo, hi)
                book = list(top3_w) + list(scaled)
            keep = scale == PRIMARY_SCALE
            _progress("Walking TOP3 + lead %s (%d units, bar_sample=%s)..." % (_scale_label(scale), len(book), keep))
            res = t3.joint_1m_mtm(book, jpy, nas, keep_bar_sample=keep)
            combined[scale] = res
            _progress(
                "  %s net=%s stress=%s N/S=%.2f"
                % (
                    _scale_label(scale),
                    _money(float(res["net_usd"])),
                    _money(float(res["intrabar_stress_dd_usd"])),
                    float(res["net_over_stress"]),
                )
            )

        write_outputs(
            lo=lo,
            hi=hi,
            top3=top3_res,
            combined=combined,
            lead_only=lead_res,
            n_lead_units=len(lead_1x),
            n_lead_trades=n_trades,
        )
        primary = combined[PRIMARY_SCALE]
        delta = float(primary["net_over_stress"]) - float(top3_res["net_over_stress"])
        _progress("DONE primary ×10 ΔN/S %+.2f" % delta)
        complete_run(
            rid,
            net_usd=float(primary["net_usd"]),
            stress_dd_usd=float(primary["intrabar_stress_dd_usd"]),
            close_mtm_dd_usd=float(primary["closed_dd_usd"]),
            ns=float(primary["net_over_stress"]),
            trades=int(sum(int(s["trades"]) for s in primary["sleeve"].values())),
            units=len(top3_w) + len(lead_w),
            equity_curve_path=HUB / "equity_curve_daily.csv",
            replay_start=str(lo.date()),
            replay_end=str(hi.date()),
            notes="primary_scale=10 delta_ns_vs_top3_overlap=%+.4f" % delta,
            meta={
                "top3_overlap_ns": float(top3_res["net_over_stress"]),
                "lead_1x_ns": float(lead_res["net_over_stress"]),
                "primary_scale": PRIMARY_SCALE,
                "primary_ns": float(primary["net_over_stress"]),
                "delta_ns_at_10x": delta,
            },
        )
        if email:
            send_email(
                subject="potions: TOP3 + NAS100 NQ-lead prior-opposed complete",
                body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        return {"top3": top3_res, "lead": lead_res, "combined": combined, "delta_ns_10x": delta}
    except Exception:
        tb = traceback.format_exc()
        fail_run(rid, notes=tb[-2000:])
        (HUB / "FAIL.txt").write_text(tb, encoding="utf-8")
        if email:
            send_email(
                subject="potions: TOP3 + NAS100 NQ-lead FAILED",
                body="Hub: %s\n\n%s" % (HUB, tb[-3000:]),
            )
        raise
    finally:
        t3._PROGRESS_HUB = prev_hub


def main() -> None:
    ap = argparse.ArgumentParser(description="TOP3 + NAS100 NQ-lead prior-opposed joint 1m MTM")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args()
    run(email=bool(args.email))


if __name__ == "__main__":
    main()
