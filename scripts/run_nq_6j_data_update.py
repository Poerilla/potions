#!/usr/bin/env python3
"""Update the NQ prior-opposed live candidate through 2026-10-11, then run USDJPY books on 6J.

NQ path: rebuilt hourly ST+PMC sl25/tp75 gate, then resting-limit prior-opposed S_1_1_3.
6J path: Monday OR M2_S3_R1, Asia-range S_3_1_3, monthly FBO 1/1/3 and 1/2/3, hourly ST+PMC 25/75.
"""
from __future__ import annotations

import os
import subprocess
import sys
import traceback
from pathlib import Path

REPO = Path("/home/tester/hsm/potions")
os.chdir(REPO)
os.environ["PYTHONPATH"] = "/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
sys.path[:0] = ["/home/tester/hsm", str(REPO)]

from live.notify_email import send_email  # noqa: E402
from live.run_ledger import begin_run, complete_run, fail_run  # noqa: E402

PY = sys.executable
LOG_ROOT = REPO / "live/state/nq_6j_update_20261011"
NQ_1M = REPO / "nq/raw/nq_front_1m_20100606_20261011.csv"
NQ_DAILY = REPO / "nq/nq_daily_through_20261011.csv"
ST_HUB = REPO / "live/state/nq_hourly_st_pmc_sl25_tp75_3r_through_20261011"
PO_HUB = REPO / "live/state/nq_v2b_prior_opposed_stpmc_resting_limit_through_20261011"
MON_HUB = REPO / "live/state/6j_monday_or_m2_s3_r1"
ASIA_HUB = REPO / "live/state/6j_v2b_asia_range_london_S_3_1_3"
FBO_HUB = REPO / "live/state/6j_fx_tracker_leaders"


def _mail(subject: str, body: str) -> None:
    try:
        send_email(subject=subject, body=body)
    except Exception as exc:
        print("email failed:", exc, flush=True)


def _run(name: str, cmd: list, hub: Path, instrument: str, slug: str) -> str:
    hub.mkdir(parents=True, exist_ok=True)
    log = LOG_ROOT / ("%s.log" % name)
    rid = begin_run(
        run_class="broker_like",
        variant_slug=slug,
        instrument=instrument,
        hub_path=hub,
        notes=name,
        command=cmd,
        meta={"log": str(log)},
    )
    print("START", name, rid, flush=True)
    with log.open("w", encoding="utf-8") as fh:
        fh.write(" ".join(cmd) + "\n")
        fh.flush()
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, cwd=str(REPO))
    if proc.returncode != 0:
        tail = log.read_text(encoding="utf-8", errors="replace")[-4000:]
        fail_run(rid, notes="exit %s" % proc.returncode)
        _mail(
            "potions: %s FAILED" % name,
            "Hub: %s\nLog: %s\nExit: %s\n\n%s" % (hub, log, proc.returncode, tail),
        )
        raise SystemExit(proc.returncode)
    complete_run(rid, notes="finished; metrics in hub")
    print("DONE", name, flush=True)
    return rid


def main() -> int:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    _mail(
        "potions: NQ prior-opposed update and 6J USDJPY books started",
        "\n".join(
            [
                "NQ live candidate: prior-opposed resting-limit S_1_1_3, rebuilt ST gate sl25/tp75.",
                "1m: %s" % NQ_1M,
                "Daily: official rows through 2026-03-08, then 1m session bars through 2026-10-11 (%s)." % NQ_DAILY,
                "ST hub: %s" % ST_HUB,
                "Prior-opposed hub: %s" % PO_HUB,
                "6J books after that: Monday OR M2_S3_R1, Asia-range S_3_1_3, FBO 1/1/3+1/2/3 and ST 25/75.",
                "6J hubs: %s | %s | %s" % (MON_HUB, ASIA_HUB, FBO_HUB),
                "Log dir: %s" % LOG_ROOT,
            ]
        ),
    )
    _run(
        "nq_st_sl25_tp75",
        [
            PY, "-m", "live.hourly_st_pmc_strategyplugin_variants",
            "--market", "nq",
            "--variants", "sl25_tp75_3r",
            "--dbn", str(NQ_1M),
            "--daily", str(NQ_DAILY),
            "--output-root", str(ST_HUB),
        ],
        ST_HUB,
        "NQ",
        "nq_hourly_st_pmc_sl25_tp75_3r_through_20261011",
    )
    _run(
        "nq_prior_opposed_resting_limit",
        [
            PY, "-m", "live.nq_v2b_prior_opposed_replay",
            "--market", "nq",
            "--gate-mode", "resting_limit",
            "--start", "2021-03-04",
            "--book", "S_1_1_3",
            "--dbn-path", str(NQ_1M),
            "--daily", str(NQ_DAILY),
            "--st-fills", str(ST_HUB / "combined_state/fills.csv"),
            "--st-orders", str(ST_HUB / "combined_state/orders.csv"),
            "--output-root", str(PO_HUB),
            "--email",
        ],
        PO_HUB,
        "NQ",
        "nq_v2b_prior_opposed_stpmc_resting_limit_through_20261011",
    )
    _run(
        "6j_fbo_and_st",
        [
            PY, "-m", "live.fx_cross_pair_tracker_leaders",
            "--pairs", "6J",
            "--force",
            "--output-root", str(FBO_HUB),
        ],
        FBO_HUB,
        "6J",
        "6j_usdjpy_fbo_and_stpmc",
    )
    _run(
        "6j_monday_or",
        [
            PY, "-m", "live.fx_monday_or_breakout_broker",
            "--pairs", "6J",
            "--output-root", str(MON_HUB),
            "--force",
        ],
        MON_HUB,
        "6J",
        "6j_monday_or_m2_s3_r1",
    )
    _run(
        "6j_asia_range",
        [
            PY, "-m", "live.fx_v2b_asia_range_london",
            "--markets", "6J",
            "--books", "S_3_1_3",
            "--start", "2010-06-06",
            "--output-root", str(ASIA_HUB),
            "--email",
        ],
        ASIA_HUB,
        "6J",
        "6j_v2b_asia_range_london_S_3_1_3",
    )
    _mail(
        "potions: NQ update and 6J USDJPY books finished",
        "\n".join(
            [
                "NQ prior-opposed hub: %s" % PO_HUB,
                "NQ ST gate hub: %s" % ST_HUB,
                "6J Monday OR: %s" % MON_HUB,
                "6J Asia-range S_3_1_3: %s" % ASIA_HUB,
                "6J FBO + ST: %s" % FBO_HUB,
                "Logs: %s" % LOG_ROOT,
                "Stance: research update on the new tape. Not a promote.",
            ]
        ),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        err = traceback.format_exc()
        _mail("potions: NQ/6J update crashed", err[-4000:])
        raise
