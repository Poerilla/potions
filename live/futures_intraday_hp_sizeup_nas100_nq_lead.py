"""Add-on: NAS100 NQ-lead prior-opposed through the futures HP size-up mill.

Today's main futures HP pass (ES/YM/NQ) omitted this CFD sleeve. This driver
profiles + shortlists + runs 1.25× matched nulls into a **dedicated** hub so
the canonical 1.25× LIVE_PLAN is not rewritten.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.futures_intraday_hp_sizeup_nas100_nq_lead --email
  python -m live.futures_intraday_hp_sizeup_nas100_nq_lead --email --smoke
  python -m live.futures_intraday_hp_sizeup_nas100_nq_lead --email --profile-only
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from .fx_v2b_london_ungated import REPO
from .futures_intraday_condition_profile import (
    MIN_N,
    profile_book,
    render_profile,
    shortlist_candidates,
)
from .futures_intraday_hp_sizeup_lib import (
    CONDITION_COLS,
    CAUSAL_LIVE_READY,
    NEEDS_LIVE_PROXY,
    STUDY,
    annotate_campaigns,
    book_by_key,
    feature_family,
    load_campaigns,
)
from .futures_intraday_hp_sizeup_nulls import run as nulls_run
from .notify_email import send_email

BOOK_KEY = "nas100_nq_lead_prior_opposed"
HUB = REPO / "live" / "state" / "futures_intraday_hp_nas100_nq_lead"
PROFILE_HUB = HUB / "profile"
NULLS_HUB = HUB / "nulls"


def run_profile(*, email: bool = False, min_n: int = MIN_N) -> pd.DataFrame:
    PROFILE_HUB.mkdir(parents=True, exist_ok=True)
    book = book_by_key(BOOK_KEY)
    print("BOOK %s ..." % book.key, flush=True)
    camp = load_campaigns(book)
    if camp.empty:
        raise RuntimeError("empty campaigns for %s" % book.key)
    print("  campaigns=%d — annotating features ..." % len(camp), flush=True)
    ann = annotate_campaigns(camp, book.symbol)
    ann.to_csv(PROFILE_HUB / ("%s_campaigns.csv" % book.key), index=False)
    ann.to_csv(PROFILE_HUB / "all_campaigns.csv", index=False)

    table, baseline, notables = profile_book(ann, min_n=min_n)
    baseline["book"] = book.key
    baselines = {book.key: baseline}
    table.to_csv(PROFILE_HUB / ("%s_buckets.csv" % book.key), index=False)
    table.to_csv(PROFILE_HUB / "condition_matrix.csv", index=False)
    pd.DataFrame(notables).to_csv(PROFILE_HUB / "notables.csv", index=False)

    causal_audit_rows = []
    for col, title in CONDITION_COLS:
        if col not in ann.columns:
            continue
        causal_audit_rows.append(
            {
                "book": book.key,
                "condition": title,
                "feature_col": col,
                "n": int(ann[col].notna().sum()),
                "n_unique": int(ann[col].astype(str).nunique()),
                "causal_live_ready": title in CAUSAL_LIVE_READY,
                "needs_proxy": title in NEEDS_LIVE_PROXY,
                "family": feature_family(title),
            }
        )
    pd.DataFrame(causal_audit_rows).to_csv(
        PROFILE_HUB / "causal_feature_audit.csv", index=False
    )

    short, ledger = shortlist_candidates(table, baselines, max_per_book=3)
    if not ledger.empty:
        ledger.to_csv(PROFILE_HUB / "candidate_ledger.csv", index=False)
    if not short.empty:
        short.to_csv(PROFILE_HUB / "shortlist.csv", index=False)
    else:
        # still write empty for downstream clarity
        pd.DataFrame(
            columns=["book", "condition", "bucket", "coverage", "inc_ns"]
        ).to_csv(PROFILE_HUB / "shortlist.csv", index=False)

    books_meta = [
        {
            "key": book.key,
            "symbol": book.symbol,
            "family": book.family,
            "tracker_ns": book.tracker_ns,
            "status": book.status,
            "n_campaigns": len(ann),
            "sleeve": book.sleeve,
            "notes": book.notes,
        }
    ]
    (PROFILE_HUB / "baselines.json").write_text(
        json.dumps(baselines, indent=2), encoding="utf-8"
    )
    (PROFILE_HUB / "SELECTED_BOOKS.json").write_text(
        json.dumps({"study": STUDY, "addon": BOOK_KEY, "books": books_meta}, indent=2),
        encoding="utf-8",
    )

    summary = render_profile(books_meta, baselines, notables, short, table)
    header = (
        "# NAS100 NQ-lead prior-opposed HP condition profile (add-on)\n\n"
        "Dedicated hub — does **not** rewrite `futures_intraday_condition_profile/` "
        "or the ES/YM/NQ LIVE_PLAN.\n\n"
    )
    summary = header + summary
    (PROFILE_HUB / "PROFILE.md").write_text(summary, encoding="utf-8")
    (PROFILE_HUB / "SUMMARY.md").write_text(summary, encoding="utf-8")

    email_lines = [
        "potions: NAS100 NQ-lead HP profile complete",
        "Hub: live/state/futures_intraday_hp_nas100_nq_lead/profile/",
        "Book: %s (%d campaigns, baseline N/S=%.2f)"
        % (book.key, len(ann), float(baseline["ns"])),
        "Shortlist: %d candidates" % (0 if short is None or short.empty else len(short)),
        "",
    ]
    if short is not None and not short.empty:
        for _, r in short.iterrows():
            email_lines.append(
                "%s | %s=%s | cov=%.0f%% incN/S=%.2f"
                % (
                    r["book"],
                    r["condition"],
                    r["bucket"],
                    100 * float(r["coverage"]),
                    float(r["inc_ns"]),
                )
            )
    email_lines.append("")
    email_lines.append("Stance: profile/shortlist only — 1.25× null suite next.")
    body = "\n".join(email_lines)
    (PROFILE_HUB / "EMAIL.txt").write_text(body, encoding="utf-8")
    if email:
        send_email(subject="potions: NAS100 NQ-lead HP profile complete", body=body)
    print(summary[:2500], flush=True)
    return short if short is not None else pd.DataFrame()


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", action="store_true")
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--profile-only", action="store_true")
    p.add_argument("--nulls-only", action="store_true")
    args = p.parse_args(list(argv) if argv is not None else None)

    HUB.mkdir(parents=True, exist_ok=True)
    if args.email and not args.nulls_only:
        send_email(
            subject="potions: NAS100 NQ-lead HP size-up STARTED",
            body=(
                "Add-on study: NAS100 prior-opposed NQ-lead sync through HP mill.\n"
                "Hub: live/state/futures_intraday_hp_nas100_nq_lead/\n"
                "Sequence: profile → shortlist ≤3 → 1.25× placebo/shift/master/WF.\n"
                "Does not rewrite futures LIVE_PLAN.\n"
                "Smoke=%s\n" % args.smoke
            ),
        )

    try:
        if not args.nulls_only:
            short = run_profile(email=args.email)
            if args.profile_only:
                return 0
            if short is None or short.empty:
                msg = (
                    "NAS100 NQ-lead profile produced empty shortlist — "
                    "no 1.25× null pairs to run."
                )
                (HUB / "EMAIL.txt").write_text(msg, encoding="utf-8")
                if args.email:
                    send_email(
                        subject="potions: NAS100 NQ-lead HP — empty shortlist",
                        body=msg,
                    )
                print(msg, flush=True)
                return 0

        kw = dict(
            email=False,  # consolidated email from this driver
            hub_override=NULLS_HUB,
            profile_hub=PROFILE_HUB,
            write_plan=False,
        )
        if args.smoke:
            nulls_run(
                n_placebo=200,
                n_shift=100,
                n_master=100,
                n_wf_placebo=50,
                max_pairs=2,
                **kw,
            )
        else:
            nulls_run(**kw)

        # Point EMAIL at study root
        null_email = NULLS_HUB / "EMAIL.txt"
        if null_email.exists():
            body = null_email.read_text(encoding="utf-8")
            body = (
                "Add-on: NAS100 NQ-lead prior-opposed HP size-up\n"
                "Hub: live/state/futures_intraday_hp_nas100_nq_lead/\n"
                "Canonical futures LIVE_PLAN unchanged.\n\n"
                + body
            )
            (HUB / "EMAIL.txt").write_text(body, encoding="utf-8")
            (NULLS_HUB / "EMAIL.txt").write_text(body, encoding="utf-8")
            if args.email:
                send_email(
                    subject="potions: NAS100 NQ-lead HP size-up complete",
                    body=body,
                )
        (HUB / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "book": BOOK_KEY,
                    "hub": str(HUB),
                    "smoke": bool(args.smoke),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return 0
    except Exception:
        tb = traceback.format_exc()
        (HUB / "FAIL.txt").write_text(tb, encoding="utf-8")
        if args.email:
            send_email(
                subject="potions: NAS100 NQ-lead HP size-up FAILED",
                body=tb[-4000:],
            )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
