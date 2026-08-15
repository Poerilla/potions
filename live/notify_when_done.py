"""Watch PIDs and/or log completion markers; email a summary when finished.

Examples::

  python -m live.notify_when_done --pids 1 2 3 --subject "batch done" --summary fx3r
  python -m live.notify_when_done --pgrep 'fx_index_metals_st_pmc_runner_variants --force --markets eurusd' \\
      --subject "EURUSD done" --summary fx --markets eurusd
"""

from __future__ import annotations

import argparse
import os
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Sequence, Set

from .format_job_summary import fx_summary, progress_snapshot, sweep_summary
from .notify_email import send_email

REPO = Path(__file__).resolve().parents[1]

HUB_BY_SUMMARY = {
    "fx": "live/state/fx_index_metals_st_pmc_runner_variants",
    "fx3r": "live/state/fx_index_metals_st_pmc_runner_variants",
    "all": "live/state/fx_index_metals_st_pmc_runner_variants",
    "sweep": "live/state/st_pmc_runner_length_sweep",
}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _pgrep(pattern: str) -> Set[int]:
    """pgrep -f, excluding this process (argv often contains the pattern)."""
    me = os.getpid()
    try:
        out = subprocess.check_output(["pgrep", "-f", pattern], text=True)
    except subprocess.CalledProcessError:
        return set()
    pids: Set[int] = set()
    for tok in out.split():
        if not tok.strip().isdigit():
            continue
        pid = int(tok)
        if pid == me:
            continue
        # Drop other notify_when_done watchers whose cmdline embeds the pattern
        try:
            cmd = Path("/proc/%d/cmdline" % pid).read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except Exception:
            cmd = ""
        if "notify_when_done" in cmd:
            continue
        pids.add(pid)
    return pids


def _run_body_cmd(cmd: str) -> str:
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT, cwd=str(REPO))
    except subprocess.CalledProcessError as exc:
        return (exc.output or "") + "\n(exit %s)\n" % exc.returncode


def _refresh_hub_email(hub: Path, markets: Optional[Sequence[str]] = None) -> Optional[str]:
    """Write decision-oriented snapshot email; return body text."""
    try:
        from .refresh_hub_snapshot import refresh_hub_snapshot

        snap = refresh_hub_snapshot(hub, markets=markets, email=False)
        body_path = hub / "COMPLETION_EMAIL.txt"
        if body_path.exists():
            return body_path.read_text(encoding="utf-8", errors="replace")
        from .hub_snapshot import render_email

        return render_email(snap)
    except Exception as exc:
        return "(hub snapshot failed: %s)\n" % exc


def _build_summary(kind: Optional[str], markets: Optional[Sequence[str]]) -> str:
    if not kind:
        return ""
    hub_rel = HUB_BY_SUMMARY.get(kind)
    if hub_rel:
        body = _refresh_hub_email(REPO / hub_rel, markets=markets)
        if body:
            return body
    if kind == "fx":
        return fx_summary(markets=markets, title="FX/index/metals ST+PMC — job complete")
    if kind == "fx3r":
        return fx_summary(
            markets=markets or ["audjpy", "xauusd", "xagusd"],
            variants=["sl50_tp150_3r_1mfill"],
            title="Fair 3R complete (AUDJPY / XAU / XAG)",
        )
    if kind == "sweep":
        return sweep_summary(markets=markets)
    if kind == "all":
        return "\n".join(
            [
                fx_summary(markets=markets, title="FX/index/metals ST+PMC — full batch"),
                sweep_summary(markets=markets),
                progress_snapshot(),
            ]
        )
    if kind == "progress":
        return progress_snapshot()
    return ""


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pids", nargs="*", type=int, default=[])
    ap.add_argument("--pgrep", default=None, help="Wait until no processes match this pattern")
    ap.add_argument("--poll-sec", type=float, default=120.0)
    ap.add_argument("--subject", required=True)
    ap.add_argument("--body", default="")
    ap.add_argument("--body-file", type=Path, default=None)
    ap.add_argument("--body-cmd", default=None)
    ap.add_argument("--also-append-cmd", default=None)
    ap.add_argument(
        "--summary",
        choices=["fx", "fx3r", "sweep", "all", "progress"],
        default=None,
        help="Auto-build phone-friendly numbers summary",
    )
    ap.add_argument("--markets", nargs="*", default=None)
    ap.add_argument(
        "--hub",
        default=None,
        help="Strategy hub for deterministic snapshot email (overrides --summary raw dump)",
    )
    ap.add_argument(
        "--on-complete",
        default=None,
        help="Shell command to run after watched jobs exit (before email). "
        "Example: scripts/run_completion_report_agent.sh live/state/… --both",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    watched: Set[int] = set(args.pids or [])
    if args.pgrep:
        watched |= _pgrep(args.pgrep)
    print("notify_when_done watching pids=%s pgrep=%r" % (sorted(watched), args.pgrep), flush=True)

    while True:
        live = {p for p in watched if _alive(p)}
        if args.pgrep:
            live |= _pgrep(args.pgrep)
        if not live:
            break
        print("still running: %s" % sorted(live), flush=True)
        time.sleep(max(5.0, float(args.poll_sec)))

    if args.on_complete:
        print("on-complete: %s" % args.on_complete, flush=True)
        oc = subprocess.run(args.on_complete, shell=True, cwd=str(REPO))
        print("on-complete exit=%s" % oc.returncode, flush=True)

    parts: List[str] = []
    if args.body:
        parts.append(args.body)

    hub_path: Optional[Path] = None
    if args.hub:
        hub_path = Path(args.hub)
        if not hub_path.is_absolute():
            hub_path = REPO / hub_path
    elif args.on_complete and "run_completion_report_agent" in (args.on_complete or ""):
        for tok in (args.on_complete or "").split():
            if tok.startswith("live/state/") or tok.endswith("_runner_variants"):
                hub_path = REPO / tok
                break
    elif args.summary in HUB_BY_SUMMARY:
        hub_path = REPO / HUB_BY_SUMMARY[args.summary]

    # Prefer decision-oriented hub snapshot over raw metric dumps.
    if hub_path is not None:
        snap_body = _refresh_hub_email(hub_path, markets=args.markets)
        if snap_body:
            parts.append(snap_body)
    else:
        summary = _build_summary(args.summary, args.markets)
        if summary:
            parts.append(summary)

    if args.body_file and args.body_file.exists():
        parts.append(args.body_file.read_text(encoding="utf-8", errors="replace"))
    if args.body_cmd:
        parts.append(_run_body_cmd(args.body_cmd))
    if args.also_append_cmd:
        parts.append(_run_body_cmd(args.also_append_cmd))
    body = "\n\n".join(p for p in parts if p) or "(no body)\n"
    if len(body) > 100_000:
        body = body[:100_000] + "\n\n…[truncated]\n"

    subject = args.subject
    # Prefer deterministic status-aware subject over caller "completion" wording.
    if hub_path is not None and (hub_path / "LATEST_SNAPSHOT.json").exists():
        try:
            from .refresh_hub_snapshot import email_subject_for_hub

            subject = email_subject_for_hub(hub_path)
        except Exception:
            pass

    try:
        to = send_email(subject=subject, body=body)
        print("emailed %s subject=%r" % (to, subject), flush=True)
    except SystemExit as exc:
        print("email skipped: %s" % exc, flush=True)
        out = REPO / "live" / "state" / "notify_skipped.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("%s\n\n%s\n" % (args.subject, body), encoding="utf-8")
        print("wrote %s" % out, flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
