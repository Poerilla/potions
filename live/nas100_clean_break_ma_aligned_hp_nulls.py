"""NAS100 clean-break arm-asof ma_aligned HP — dedicated matched nulls.

Each intended multiplier needs its own null suite (do not infer ×4 from ×1.5).
Default: exact **4×** (extra=3.0) on the arm-asof HP mask.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nas100_clean_break_ma_aligned_hp_nulls --email
  python -m live.nas100_clean_break_ma_aligned_hp_nulls --email --mults 1.5,4
  python -m live.nas100_clean_break_ma_aligned_hp_nulls --email --smoke
"""

from __future__ import annotations

import argparse
import csv
import json
import traceback
from datetime import date
from pathlib import Path
from typing import List, Sequence, Tuple

import pandas as pd

import live.intraday_condition_overlay as overlay
import live.intraday_hp_sizeup_nulls as nulls_mod

from .intraday_condition_overlay import select_cross_book_hits, select_single_book_hits
from .intraday_hp_sizeup_nulls import evaluate_pair, phone_email, render_summary
from .notify_email import send_email
from .run_ledger import begin_run, complete_run, fail_run

REPO = Path(__file__).resolve().parents[1]
PARENT_HUB = REPO / "live" / "state" / "nas100_clean_break_ma_aligned_size15_broker"
ARM_CAMPAIGNS = PARENT_HUB / "arm_asof_campaigns.csv"
HA_PROFILE = REPO / "live" / "state" / "nas100_clean_break_ha_conditions" / "profile"
BOOK = "nas100_v2b_clean_break_trail06"
CONDITION = "5m MA vs trade (arm-asof)"
BUCKET = "ma_aligned"
PARENT_DSR = "TRL-2026-00201"
DSR = "TRL-2026-00202"
SEED = 20260913


def _hub_for_mult(mult: float) -> Path:
    if abs(mult - 4.0) < 1e-9:
        return PARENT_HUB / "nulls_x4"
    slug = ("%.2f" % mult).replace(".", "_").rstrip("0").rstrip("_")
    return PARENT_HUB / ("nulls_x%s" % slug)


def _progress(msg: str, *, hub: Path) -> None:
    hub.mkdir(parents=True, exist_ok=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as f:
        f.write(msg.rstrip() + "\n")
    print(msg, flush=True)


def _append_dsr(*, mults: Sequence[float], hub: Path) -> None:
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
            "trial_class": "NULL_SUITE",
            "trial_subclass": "nas100_clean_break_ma_aligned_arm_asof_nulls",
            "is_independent": "TRUE",
            "market": "NAS100",
            "replay_type": "FULL_HISTORY",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {
                    "parent_dsr": PARENT_DSR,
                    "hp_contract": "arm_asof_no_qty_refresh",
                    "condition": "%s=%s" % (CONDITION, BUCKET),
                    "mults": list(mults),
                    "hub": str(hub.relative_to(REPO)),
                }
            ),
            "fixed_parameters_ref": "live/nas100_clean_break_ma_aligned_hp_nulls.py",
            "num_params_varied": "1",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "1.00",
            "status": "PENDING",
            "notes": "Dedicated matched nulls for arm-asof ma_aligned at stated multiplier(s)",
            "disclosure_review": "FALSE",
        }
    )
    with path.open("a", newline="") as fh:
        csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore").writerow(row)


def _mark_dsr(status: str) -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    out = []
    for ln in path.read_text().splitlines():
        if ln.startswith(DSR + ",") and ",PENDING," in ln:
            ln = ln.replace(",PENDING,", ",%s," % status, 1)
        out.append(ln)
    path.write_text("\n".join(out) + "\n")


def _load_campaigns() -> pd.DataFrame:
    if not ARM_CAMPAIGNS.exists():
        raise FileNotFoundError(
            "Missing arm-asof campaigns at %s — run "
            "live.nas100_clean_break_ma_aligned_size15_broker first" % ARM_CAMPAIGNS
        )
    df = pd.read_csv(ARM_CAMPAIGNS)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True)
    if "ma5_align_arm" not in df.columns:
        raise ValueError("arm_asof_campaigns.csv missing ma5_align_arm")
    # evaluate_pair / hp_mask use COND_COL → column; keep fill-asof ma5_align intact
    # for candidate ledger contrast while HP mask uses arm-asof via patched COND_COL.
    if "book" not in df.columns:
        df["book"] = BOOK
    if "month_name" not in df.columns:
        df["month_name"] = df["entry_ts"].dt.month_name()
    return df


def _patch_overlay_for_arm_asof() -> None:
    overlay.COND_COL[CONDITION] = "ma5_align_arm"
    overlay.CAUSAL_LIVE_READY.add(CONDITION)
    # Keep fill-asof mapping for candidate discovery from HA notables.
    overlay.COND_COL.setdefault("5m MA vs trade", "ma5_align")


def run_nulls(
    *,
    mults: Sequence[float] = (4.0,),
    email: bool = False,
    smoke: bool = False,
) -> pd.DataFrame:
    primary_hub = _hub_for_mult(float(mults[0]))
    primary_hub.mkdir(parents=True, exist_ok=True)
    _append_dsr(mults=mults, hub=primary_hub)
    _patch_overlay_for_arm_asof()

    campaigns = _load_campaigns()
    notables = (
        pd.read_csv(HA_PROFILE / "notables.csv")
        if (HA_PROFILE / "notables.csv").exists()
        else pd.DataFrame()
    )
    singles = select_single_book_hits(
        notables, min_z=0.5, min_n=40, top_per_book=10
    ) if not notables.empty else pd.DataFrame()
    crosses = select_cross_book_hits(notables, min_books=2) if not notables.empty else pd.DataFrame()

    n_placebo = 400 if smoke else 2000
    n_shift = 200 if smoke else 800
    n_master = 100 if smoke else 400
    n_wf = 100 if smoke else 400

    all_results: List[dict] = []
    for i, mult in enumerate(mults):
        extra = float(mult) - 1.0
        hub = _hub_for_mult(float(mult))
        hub.mkdir(parents=True, exist_ok=True)
        nulls_mod.HUB = hub
        nulls_mod.PROFILE_HUB = HA_PROFILE
        _progress(
            "START arm-asof ma_aligned matched nulls @ %.2f× (extra=%.2f) "
            "smoke=%s hub=%s"
            % (float(mult), extra, smoke, hub.relative_to(REPO)),
            hub=hub,
        )
        try:
            res = evaluate_pair(
                campaigns,
                notables,
                singles,
                crosses,
                book=BOOK,
                condition=CONDITION,
                bucket=BUCKET,
                extra=extra,
                n_placebo=n_placebo,
                n_shift=n_shift,
                n_master=n_master,
                n_wf_placebo=n_wf,
                seed=SEED + i * 97,
            )
            res["hp_contract"] = "arm_asof_no_qty_refresh"
            res["parent_hub"] = str(PARENT_HUB.relative_to(REPO))
            all_results.append(res)
            _progress(
                "DONE @ %.2f× decision=%s ΔN/S=%+.3f hp=%.0f%% p_master=%.3f"
                % (
                    float(mult),
                    res.get("decision"),
                    float(res.get("sleeve_delta_ns") or 0.0),
                    100.0 * float(res.get("boost_frac") or 0.0),
                    float(res.get("p_master_delta_ns") or float("nan")),
                ),
                hub=hub,
            )
            summary = render_summary([res], pd.DataFrame())
            # Prepend contract banner.
            banner = "\n".join(
                [
                    "# NAS100 clean-break — arm-asof ma_aligned nulls @ %.2f×" % float(mult),
                    "",
                    "HP contract: `arm_asof_no_qty_refresh` (`ma5_align_arm=ma_aligned`).",
                    "Source campaigns: `%s`." % ARM_CAMPAIGNS.relative_to(REPO),
                    "Parent Engine scales: `%s`." % PARENT_HUB.relative_to(REPO),
                    "DSR: %s (parent %s)." % (DSR, PARENT_DSR),
                    "",
                    "Coverage note: arm-asof HP is ~55% of campaigns — above the",
                    "35% SIZE-UP VALIDATED gate, so expect RISK THROTTLE even if",
                    "placebo/shift beat unless coverage is re-scoped.",
                    "",
                ]
            )
            (hub / "SUMMARY.md").write_text(banner + summary, encoding="utf-8")
            body = phone_email([res], pd.DataFrame())
            body = (
                "potions: NAS100 arm-asof ma_aligned nulls @ %.2f×\n\nHub: %s\n"
                "HP: %s=%s (arm-asof)\nDSR: %s\n\n%s"
                % (float(mult), hub, CONDITION, BUCKET, DSR, body)
            )
            (hub / "EMAIL.txt").write_text(body, encoding="utf-8")
            pd.DataFrame([res]).to_csv(hub / "pair_decisions.csv", index=False)
            (hub / "RUN_COMPLETE.json").write_text(
                json.dumps(
                    {
                        "status": "ok",
                        "size_mult": float(mult),
                        "decision": res.get("decision"),
                        "delta_ns": res.get("sleeve_delta_ns"),
                        "boost_frac": res.get("boost_frac"),
                        "p_master_delta_ns": res.get("p_master_delta_ns"),
                        "dsr": DSR,
                    },
                    indent=2,
                    default=str,
                )
                + "\n",
                encoding="utf-8",
            )
            if email:
                send_email(
                    subject="potions: NAS100 arm-asof ma_aligned nulls @ %.2f× complete"
                    % float(mult),
                    body=body,
                )
                _progress("email sent", hub=hub)
        except Exception:
            tb = traceback.format_exc()
            _progress("CRASH @ %.2f×\n%s" % (float(mult), tb[-2000:]), hub=hub)
            fail_body = (
                "potions: NAS100 arm-asof ma_aligned nulls @ %.2f× FAILED\n\nHub: %s\n\n%s\n"
                % (float(mult), hub, tb[-2500:])
            )
            (hub / "EMAIL.txt").write_text(fail_body, encoding="utf-8")
            if email:
                send_email(
                    subject="potions: NAS100 arm-asof ma_aligned nulls @ %.2f× FAILED"
                    % float(mult),
                    body=fail_body,
                )
            raise

    out = pd.DataFrame(all_results)
    if len(mults) > 1:
        combined = PARENT_HUB / "nulls_mult_compare"
        combined.mkdir(parents=True, exist_ok=True)
        out.to_csv(combined / "pair_decisions.csv", index=False)
        (combined / "SUMMARY.md").write_text(
            render_summary(all_results, pd.DataFrame()), encoding="utf-8"
        )
    _mark_dsr("COMPLETE")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument(
        "--mults",
        default="4",
        help="Comma-separated stated multipliers (default: 4)",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)
    mults: Tuple[float, ...] = tuple(
        float(x.strip()) for x in str(args.mults).split(",") if x.strip()
    )
    if not mults:
        raise SystemExit("--mults empty")
    hub0 = _hub_for_mult(float(mults[0]))
    rid = begin_run(
        run_class="ha",
        variant_slug="nas100_clean_break_ma_aligned_arm_asof_nulls",
        instrument="NAS100",
        hub_path=str(hub0.relative_to(REPO)),
        dsr_trial_id=DSR,
        meta={
            "hp_contract": "arm_asof_no_qty_refresh",
            "condition": "%s=%s" % (CONDITION, BUCKET),
            "mults": list(mults),
            "smoke": bool(args.smoke),
        },
        notes="Dedicated matched nulls arm-asof ma_aligned at stated mult(s)",
    )
    try:
        out = run_nulls(mults=mults, email=bool(args.email), smoke=bool(args.smoke))
        primary = out.iloc[0].to_dict() if not out.empty else {}
        complete_run(
            rid,
            net_usd=float(primary.get("sleeve_book_net") or primary.get("sleeve_inc_net") or 0.0),
            ns=float(primary.get("sleeve_delta_ns") or 0.0),
            trades=int(primary.get("boost_n") or 0),
            meta={
                "decision": primary.get("decision"),
                "size_mult": primary.get("size_mult"),
                "p_master_delta_ns": primary.get("p_master_delta_ns"),
                "boost_frac": primary.get("boost_frac"),
            },
        )
        return 0
    except Exception as exc:
        fail_run(rid, notes=str(exc)[:500])
        _mark_dsr("FAILED")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
