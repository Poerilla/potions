"""Orchestrator for futures_intraday_hp_sizeup_v1.

1) Select top-8 books → 2) condition profile + shortlist → 3) 1.25× nulls
→ 4) portfolio gate + LIVE_PLAN → 5) baseline vs 2–4× compare + overlap → email.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.futures_intraday_hp_sizeup_v1 --email
  python -m live.futures_intraday_hp_sizeup_v1 --email --smoke
"""

from __future__ import annotations

import argparse
import traceback
from typing import Optional, Sequence

from .futures_intraday_condition_profile import main as profile_main
from .futures_intraday_hp_sizeup_compare import run as compare_run
from .futures_intraday_hp_sizeup_lib import LIVE_HUB, NULLS_HUB, PROFILE_HUB, STUDY
from .futures_intraday_hp_sizeup_nulls import run as nulls_run
from .notify_email import send_email


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", action="store_true")
    p.add_argument("--smoke", action="store_true", help="Reduced null counts + max 2 pairs")
    p.add_argument("--profile-only", action="store_true")
    p.add_argument("--nulls-only", action="store_true")
    p.add_argument("--compare-only", action="store_true")
    args = p.parse_args(list(argv) if argv is not None else None)

    PROFILE_HUB.mkdir(parents=True, exist_ok=True)
    NULLS_HUB.mkdir(parents=True, exist_ok=True)
    LIVE_HUB.mkdir(parents=True, exist_ok=True)

    if args.compare_only:
        compare_run(email=args.email)
        return 0

    if args.email and not args.nulls_only:
        send_email(
            subject="potions: %s STARTED" % STUDY,
            body=(
                "Study: %s\n"
                "Hubs:\n"
                "  %s\n"
                "  %s\n"
                "  %s\n"
                "Sequence: select top-8 → campaign tapes → profile → "
                "1.25× placebo/shift/master/WF → portfolio → LIVE_PLAN → "
                "compare/overlap.\n"
                "Smoke=%s\n"
            )
            % (STUDY, PROFILE_HUB, NULLS_HUB, LIVE_HUB, args.smoke),
        )

    try:
        if not args.nulls_only:
            rc = profile_main(["--email"] if args.email else [])
            if rc != 0:
                return rc
            if args.profile_only:
                return 0

        if args.smoke:
            nulls_run(
                email=args.email,
                n_placebo=200,
                n_shift=100,
                n_master=100,
                n_wf_placebo=50,
                max_pairs=2,
            )
        else:
            nulls_run(email=args.email)

        # Sensitivity + prior-opposed overlap (does not change null decisions)
        compare_run(email=args.email)
        return 0
    except Exception:
        tb = traceback.format_exc()
        (NULLS_HUB / "FAIL.txt").write_text(tb, encoding="utf-8")
        if args.email:
            send_email(
                subject="potions: %s FAILED" % STUDY,
                body=tb[-4000:],
            )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
