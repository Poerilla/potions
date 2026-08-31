"""NAS100 wrapper for the first-hour follow sweep+trail runner.

This keeps `python -m live.nas100_1h_first_hour_broker_sweep_trail` as a stable
entrypoint, while the core implementation lives in:
`live/nq_1h_first_hour_broker_sweep_trail.py` (now instrument-parameterized).
"""

from __future__ import annotations

import sys

from .nq_1h_first_hour_broker_sweep_trail import main as sweep_main


def _strip_instrument(argv: list[str]) -> list[str]:
    out: list[str] = []
    skip = False
    for a in argv:
        if skip:
            skip = False
            continue
        if a == "--instrument":
            skip = True
            continue
        out.append(a)
    return out


if __name__ == "__main__":
    argv = _strip_instrument(sys.argv[1:])
    raise SystemExit(sweep_main(["--instrument", "NAS100"] + argv))

