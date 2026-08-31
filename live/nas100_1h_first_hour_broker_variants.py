"""NAS100 wrapper for first-hour broker variants.

Stable entrypoint::

  python -m live.nas100_1h_first_hour_broker_variants --force --email

Core implementation: ``live/nq_1h_first_hour_broker_variants.py`` (instrument-parameterized).
"""

from __future__ import annotations

import sys

from .nq_1h_first_hour_broker_variants import main as variants_main


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
    raise SystemExit(variants_main(["--instrument", "NAS100"] + argv))
