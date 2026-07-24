"""EURUSD v2b ungated OANDA practice demo — real practice orders.

Artifacts: ``live/demo/eurusd_v2b_ungated_oanda/``. Paper sibling unchanged.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .oanda_v2b_ungated_common import (
    OandaDemoSpec,
    default_output_root as _default_output_root,
    run_stream_loop as _run_stream_loop,
    spawn_daemon as _spawn_daemon,
    status_daemon as _status_daemon,
    stop_daemon as _stop_daemon,
)

SPEC = OandaDemoSpec(
    instrument="EURUSD",
    strategy_id="eurusd_v2b_ungated_oanda",
    run_dirname="eurusd_v2b_ungated_oanda",
    tick=0.00001,
)
CLI_COMMAND = "demo-eurusd-v2b-oanda"


def default_output_root() -> Path:
    return _default_output_root(SPEC)


def run_stream_loop(*, output_root: Optional[Path] = None, config=None, max_ticks: int = 0) -> int:
    return _run_stream_loop(SPEC, output_root=output_root, config=config, max_ticks=max_ticks)


def spawn_daemon(*, output_root: Path, max_ticks: int = 0, oanda_config_path: str = "") -> int:
    return _spawn_daemon(
        SPEC,
        output_root=output_root,
        cli_command=CLI_COMMAND,
        max_ticks=max_ticks,
        oanda_config_path=oanda_config_path,
    )


def status_daemon(output_root: Path) -> int:
    return _status_daemon(output_root, spec=SPEC)


def stop_daemon(output_root: Path) -> int:
    return _stop_daemon(output_root)
