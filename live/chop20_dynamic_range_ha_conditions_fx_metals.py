"""HA mill for CHOP20 causal-entry FX/metals/index-CFD baselines.

Source: ``live/state/chop20_dynamic_range_causal_entry_fx_metals/{m}__close_to_globex__baseline/trades.csv``

Runs profile → overlay (filter / 1.25×) → nulls when N allows.
Promising filter gates can be re-sim'd via::

  python -m live.chop20_dynamic_range_causal_entry_fx_metals --email --hp-from-hub \\
    live/state/chop20_dynamic_range_ha_conditions_fx_metals

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.chop20_dynamic_range_ha_conditions_fx_metals --email
  python -m live.chop20_dynamic_range_ha_conditions_fx_metals --email --markets nas100,xauusd
  python -m live.chop20_dynamic_range_ha_conditions_fx_metals --email --profile-only
"""

from __future__ import annotations

import argparse
import csv
import json
import traceback
from datetime import date
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import pandas as pd

from . import chop20_dynamic_range_ha_conditions as base
from .chop20_dynamic_range_causal_entry_fx_metals import MARKETS as FX_MARKETS
from .chop20_dynamic_range_ha_conditions import ChopBook
from .fx_v2b_london_ungated import REPO
from .notify_email import send_email
from .run_ledger import begin_run, complete_run, fail_run

SOURCE = REPO / "live" / "state" / "chop20_dynamic_range_causal_entry_fx_metals"
HUB = REPO / "live" / "state" / "chop20_dynamic_range_ha_conditions_fx_metals"
DSR = "TRL-2026-00183"
DEFAULT_MARKETS = ("nas100", "us30", "usdjpy", "gbpusd", "xauusd", "xagusd")


def _books(markets: Sequence[str]) -> Tuple[ChopBook, ...]:
    out: List[ChopBook] = []
    for m in markets:
        cfg = FX_MARKETS[m.lower()]
        trades = SOURCE / ("%s__close_to_globex__baseline" % m.lower()) / "trades.csv"
        out.append(
            ChopBook(
                key="%s_chop20_causal_globex" % m.lower(),
                label="%s CHOP20 causal globex" % cfg.symbol,
                symbol=cfg.symbol,
                trades=trades,
            )
        )
        # Ensure daily cache seed path exists for feature frames
        base.DAILY_CSV[cfg.symbol] = cfg.daily
    return tuple(out)


def _append_dsr(markets: Sequence[str]) -> None:
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
            "trial_class": "FILTER_EXPLORATION",
            "trial_subclass": "chop20_causal_fx_metals_ha",
            "is_independent": "TRUE",
            "market": ",".join(m.upper() for m in markets),
            "replay_type": "FULL_HISTORY",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {
                    "pipeline": "ha_profile_overlay_nulls",
                    "source": str(SOURCE.relative_to(REPO)),
                    "entry_mode": "close_to_globex",
                }
            ),
            "fixed_parameters_ref": "live/chop20_dynamic_range_ha_conditions_fx_metals.py",
            "num_params_varied": "0",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "1.00",
            "status": "PENDING",
            "notes": "HA mill on CHOP20 causal FX/metals/CFD baselines",
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


def run(
    *,
    markets: Sequence[str],
    email: bool,
    smoke: bool,
    profile_only: bool,
    overlay_only: bool,
    nulls_only: bool,
) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    _append_dsr(markets)
    books = _books(markets)
    # Point base mill at this hub / books
    base.HUB = HUB
    base.PROFILE_HUB = HUB / "profile"
    base.OVERLAY_HUB = HUB / "overlay"
    base.NULLS_HUB = HUB / "nulls"
    base.SOURCE = SOURCE
    base.DSR = DSR
    base.BOOKS = books
    base.MIN_N_DEFAULT = 6  # thinner daily books

    rid = begin_run(
        run_class="ha",
        variant_slug="chop20_causal_fx_metals_ha",
        instrument="MULTI",
        hub_path=str(HUB.relative_to(REPO)),
        dsr_trial_id=DSR,
        notes="HA mill FX/metals running",
        meta={"markets": list(markets)},
    )
    try:
        base._progress("START CHOP20 FX/metals HA mill markets=%s" % ",".join(markets))
        if not overlay_only and not nulls_only:
            base.run_profile(min_n=base.MIN_N_DEFAULT, email=False)
        if not profile_only and not nulls_only:
            base.run_overlay(email=False, min_n=base.MIN_N_DEFAULT)
        decisions: List[str] = []
        if not profile_only and not overlay_only:
            nulls = base.run_nulls(email=False, smoke=smoke)
            if not nulls.empty and "decision" in nulls.columns:
                decisions = sorted({str(x) for x in nulls["decision"].tolist()})

        lines = [
            "# CHOP20 Causal FX/metals — HA mill",
            "",
            "Source: close_to_globex baselines under `%s`." % SOURCE,
            "",
            "## Profile",
            "",
            (base.PROFILE_HUB / "SUMMARY.md").read_text()
            if (base.PROFILE_HUB / "SUMMARY.md").exists()
            else "_missing_",
            "",
            "## Overlay",
            "",
            (base.OVERLAY_HUB / "SUMMARY.md").read_text()
            if (base.OVERLAY_HUB / "SUMMARY.md").exists()
            else "_missing_",
            "",
            "## Nulls",
            "",
            (base.NULLS_HUB / "SUMMARY.md").read_text()
            if (base.NULLS_HUB / "SUMMARY.md").exists()
            else "_missing_",
            "",
            "**Stance:** diagnostic HA — filter candidates only; re-sim on causal 1m before promote.",
            "",
            "DSR: `%s`" % DSR,
            "",
            "Hub: `%s`" % HUB,
            "",
        ]
        body = "\n".join(lines)
        (HUB / "SUMMARY.md").write_text(body)
        (HUB / "EMAIL.txt").write_text("potions: CHOP20 FX/metals HA mill complete\n\n" + body)
        _mark_dsr("COMPLETE")
        complete_run(rid, notes="HA mill done; decisions=%s" % (",".join(decisions) or "none"))
        if email:
            send_email(subject="potions: CHOP20 FX/metals HA mill complete", body=(HUB / "EMAIL.txt").read_text()[:12000])
        base._progress("DONE HA mill")
    except Exception:
        err = traceback.format_exc()
        fail_run(rid, notes=err[-2000:])
        _mark_dsr("FAILED")
        if email:
            send_email(subject="potions: CHOP20 FX/metals HA mill FAILED", body=err[-4000:])
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--profile-only", action="store_true")
    ap.add_argument("--overlay-only", action="store_true")
    ap.add_argument("--nulls-only", action="store_true")
    ap.add_argument("--markets", default=",".join(DEFAULT_MARKETS))
    args = ap.parse_args(argv)
    markets = [m.strip().lower() for m in args.markets.split(",") if m.strip()]
    run(
        markets=markets,
        email=bool(args.email),
        smoke=bool(args.smoke),
        profile_only=bool(args.profile_only),
        overlay_only=bool(args.overlay_only),
        nulls_only=bool(args.nulls_only),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
