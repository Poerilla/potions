from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

from potions.live.demo.oanda_v2b_ungated_common import _remove_pidfile, pidfile_path

HSM = Path(__file__).resolve().parents[3]

HOLDER = textwrap.dedent(
    """
    import sys, time
    from pathlib import Path
    from potions.live.demo.oanda_v2b_ungated_common import acquire_instance_lock
    print(acquire_instance_lock(Path(sys.argv[1])), flush=True)
    time.sleep(float(sys.argv[2]))
    """
)


def _run_holder(root: Path, hold: float) -> subprocess.Popen:
    env = dict(os.environ, PYTHONPATH=str(HSM))
    return subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(root), str(hold)],
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )


def test_second_runner_refused_while_first_holds_lock(tmp_path: Path) -> None:
    first = _run_holder(tmp_path, 5.0)
    assert first.stdout.readline().strip() == "True"
    second = _run_holder(tmp_path, 0.0)
    out, _ = second.communicate(timeout=30)
    assert out.strip().splitlines()[-1] == "False"
    assert "REFUSING start" in (tmp_path / "PROGRESS.log").read_text()
    first.terminate()
    first.wait(timeout=30)
    third = _run_holder(tmp_path, 0.0)
    out, _ = third.communicate(timeout=30)
    assert out.strip() == "True"


def test_remove_pidfile_keeps_foreign_pid(tmp_path: Path) -> None:
    pidfile_path(tmp_path).write_text("999999\n")
    _remove_pidfile(tmp_path)
    assert pidfile_path(tmp_path).exists()
    pidfile_path(tmp_path).write_text("%d\n" % os.getpid())
    _remove_pidfile(tmp_path)
    assert not pidfile_path(tmp_path).exists()
