"""Write / validate ``RUN_COMPLETE.json`` for a strategy hub (deterministic).

Delegates snapshot / email / board generation to ``live.hub_snapshot`` so
completion mail is decision-oriented and never titled \"completion\" while
jobs are incomplete.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .hub_snapshot import (
    build_snapshot,
    maybe_attach_exit_attribution,
    render_email,
    write_snapshot_artifacts,
)

REPO = Path(__file__).resolve().parents[1]


def _hub_path(hub: str) -> Path:
    p = Path(hub)
    if not p.is_absolute():
        p = REPO / p
    return p


def build_status(hub: Path, *, markets: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    prior = None
    latest = hub / "LATEST_SNAPSHOT.json"
    src = latest if latest.exists() else (hub / "STATUS.json")
    if src.exists():
        try:
            prior = json.loads(src.read_text(encoding="utf-8"))
        except Exception:
            prior = None
    snap = build_snapshot(hub, markets=markets, prior=prior)
    maybe_attach_exit_attribution(hub, snap)
    return snap


def write_run_complete(hub: Path, status: Dict[str, Any]) -> Path:
    paths = write_snapshot_artifacts(hub, status, email=False)
    return paths.get("status") or (hub / "STATUS.json")


def write_deterministic_email_body(hub: Path, status: Dict[str, Any]) -> Path:
    path = hub / "COMPLETION_EMAIL.txt"
    path.write_text(render_email(status), encoding="utf-8")
    return path


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--hub",
        default="live/state/fx_index_metals_st_pmc_runner_variants",
        help="Strategy hub directory",
    )
    ap.add_argument("--markets", nargs="*", default=None)
    ap.add_argument("--write", action="store_true", help="Write snapshot + STATUS/RUN_COMPLETE")
    ap.add_argument("--email-body", action="store_true", help="Write COMPLETION_EMAIL.txt")
    ap.add_argument("--email", action="store_true", help="Write artifacts and send email")
    ap.add_argument("--require-complete", action="store_true", help="Exit 2 if not complete")
    args = ap.parse_args(list(argv) if argv is not None else None)

    hub = _hub_path(args.hub)
    status = build_status(hub, markets=args.markets)
    if args.write or args.email:
        path = write_run_complete(hub, status)
        print(
            "Wrote %s status=%s complete=%s"
            % (path, status.get("status"), status.get("complete")),
            flush=True,
        )
    else:
        print(json.dumps(status, indent=2, sort_keys=True))
    if args.email_body and not (args.write or args.email):
        p = write_deterministic_email_body(hub, status)
        print("Wrote %s" % p, flush=True)
    if args.email:
        from .notify_email import send_email
        from .hub_snapshot import _email_subject

        body = (hub / "COMPLETION_EMAIL.txt").read_text(encoding="utf-8")
        send_email(subject=_email_subject(status), body=body)
        print("emailed snapshot", flush=True)
    if args.require_complete and not status.get("complete"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
