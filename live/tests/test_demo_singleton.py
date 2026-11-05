from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import List, Optional

import pytest

from potions.live.demo import singleton

HSM = Path(__file__).resolve().parents[3]
DEMO_DIR = HSM / "potions" / "live" / "demo"

CLAIM = textwrap.dedent(
    """
    import json, sys, time
    from pathlib import Path
    from potions.live.demo.singleton import claim_runtime
    a = json.loads(sys.argv[1])
    ok = claim_runtime(
        strategy_id=a["sid"], output_root=Path(a["out"]), account_id=a.get("acct", ""),
        instrument=a.get("instr", ""), routes_orders=a.get("routes", False),
        registry_path=Path(a["registry"]), watchdog=False,
    )
    print("CLAIM", ok, flush=True)
    time.sleep(a.get("hold", 0))
    """
)


def _env(lock_root: Path) -> dict:
    return dict(os.environ, PYTHONPATH=str(HSM), POTIONS_SINGLETON_LOCK_ROOT=str(lock_root))


def _claim(tmp: Path, hold: float = 0.0, **kw) -> subprocess.Popen:
    payload = dict(kw, hold=hold, registry=str(tmp / "registry.json"))
    return subprocess.Popen([sys.executable, "-c", CLAIM, json.dumps(payload)], stdout=subprocess.PIPE,
                            text=True, env=_env(tmp / "locks"))


def _result(proc: subprocess.Popen) -> bool:
    out, _ = proc.communicate(timeout=60)
    lines = [l for l in out.splitlines() if l.startswith("CLAIM ")]
    return lines[-1] == "CLAIM True"


def _wait_claimed(proc: subprocess.Popen) -> None:
    line = proc.stdout.readline()
    while line and not line.startswith("CLAIM "):
        line = proc.stdout.readline()
    assert line.strip() == "CLAIM True"


@pytest.fixture()
def tmp(tmp_path: Path) -> Path:
    (tmp_path / "registry.json").write_text(json.dumps({"accounts": {
        "acct-A": {"NAS100": "sid_a"},
        "acct-B": {},
    }}))
    return tmp_path


def test_same_strategy_different_output_root_refused(tmp: Path) -> None:
    first = _claim(tmp, hold=5, sid="sid_x", out=str(tmp / "out1"))
    _wait_claimed(first)
    assert _result(_claim(tmp, sid="sid_x", out=str(tmp / "out2"))) is False
    assert "strategy lock" in (tmp / "out2" / "PROGRESS.log").read_text()
    first.terminate()
    first.wait(timeout=30)
    assert _result(_claim(tmp, sid="sid_x", out=str(tmp / "out2"))) is True


def test_same_output_root_different_strategy_refused(tmp: Path) -> None:
    first = _claim(tmp, hold=5, sid="sid_x", out=str(tmp / "out1"))
    _wait_claimed(first)
    assert _result(_claim(tmp, sid="sid_y", out=str(tmp / "out1"))) is False
    first.terminate()
    first.wait(timeout=30)


def test_route_owner_enforced(tmp: Path) -> None:
    assert _result(_claim(tmp, sid="sid_a", out=str(tmp / "a"), acct="acct-A", instr="NAS100", routes=True)) is True
    assert _result(_claim(tmp, sid="sid_other", out=str(tmp / "o"), acct="acct-A", instr="NAS100", routes=True)) is False
    assert "owned by sid_a" in (tmp / "o" / "PROGRESS.log").read_text()
    assert _result(_claim(tmp, sid="sid_a", out=str(tmp / "b"), acct="acct-B", instr="NAS100", routes=True)) is False
    assert _result(_claim(tmp, sid="sid_a", out=str(tmp / "c"), acct="acct-Z", instr="NAS100", routes=True)) is False


def test_route_lock_blocks_second_router_even_if_registry_edited(tmp: Path) -> None:
    first = _claim(tmp, hold=5, sid="sid_a", out=str(tmp / "a"), acct="acct-A", instr="NAS100", routes=True)
    _wait_claimed(first)
    reg = json.loads((tmp / "registry.json").read_text())
    reg["accounts"]["acct-A"]["NAS100"] = "sid_b"
    (tmp / "registry.json").write_text(json.dumps(reg))
    assert _result(_claim(tmp, sid="sid_b", out=str(tmp / "b"), acct="acct-A", instr="NAS100", routes=True)) is False
    assert "route lock" in (tmp / "b" / "PROGRESS.log").read_text()
    first.terminate()
    first.wait(timeout=30)


def test_paper_runner_skips_route_registry(tmp: Path) -> None:
    assert _result(_claim(tmp, sid="paper_x", out=str(tmp / "p"), acct="acct-Z", instr="EURUSD", routes=False)) is True


def test_sigkill_releases_locks(tmp: Path) -> None:
    first = _claim(tmp, hold=30, sid="sid_k", out=str(tmp / "k"))
    _wait_claimed(first)
    first.kill()
    first.wait(timeout=30)
    assert _result(_claim(tmp, sid="sid_k", out=str(tmp / "k"))) is True


def test_refused_daemon_child_restores_holder_pidfile(tmp: Path) -> None:
    first = _claim(tmp, hold=8, sid="sid_p", out=str(tmp / "p"))
    _wait_claimed(first)
    second = _claim(tmp, sid="sid_p", out=str(tmp / "p"))
    (tmp / "p" / "pidfile").write_text("%d\n" % second.pid)
    assert _result(second) is False
    assert int((tmp / "p" / "pidfile").read_text()) == first.pid
    first.terminate()
    first.wait(timeout=30)


def test_audit_flags_duplicates_and_unlocked(tmp: Path) -> None:
    out = tmp / "dup"
    out.mkdir()
    procs = [
        {"pid": 11, "command": "demo-x", "argv": [], "cwd": "", "output_root": str(out), "started_epoch": time.time()},
        {"pid": 12, "command": "demo-x", "argv": [], "cwd": "", "output_root": str(out), "started_epoch": time.time()},
    ]
    result = singleton.audit(procs)
    assert any(a.startswith("DUPLICATE_OUTPUT") for a in result["alarms"])
    assert sum(a.startswith("UNLOCKED") for a in result["alarms"]) == 2


def test_read_lock_meta_accepts_legacy_plain_pid(tmp: Path) -> None:
    lock = tmp / "daemon.lock"
    lock.write_text("4242\n", encoding="utf-8")
    assert singleton.read_lock_meta(lock) == {"pid": 4242}


def test_live_registry_has_one_owner_per_account_instrument() -> None:
    registry = singleton.load_registry()
    for account, owners in registry.items():
        assert len(set(owners.values())) == len(owners), account


# --------------------------------------------------------------------------- enforcement


RUN_FUNCS = ("run_stream_loop", "run_loop")
BEFORE = ("write_run_meta", "bootstrap_store", "bootstrap_reconcile")


def _call_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


def _delegates(fn: ast.FunctionDef) -> bool:
    body = [s for s in fn.body if not (isinstance(s, ast.Expr) and isinstance(getattr(s, "value", None), ast.Constant))]
    if len(body) != 1 or not isinstance(body[0], ast.Return) or not isinstance(body[0].value, ast.Call):
        return False
    return _call_name(body[0].value).lstrip("_") in RUN_FUNCS


def _runner_entrypoints() -> List[tuple]:
    out = []
    for path in sorted(DEMO_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name in RUN_FUNCS:
                out.append((path.name, node))
    return out


def test_every_demo_runner_claims_singleton_before_building_state() -> None:
    entries = _runner_entrypoints()
    assert len(entries) >= 30
    offenders = []
    for name, fn in entries:
        if _delegates(fn):
            continue
        calls = [n for n in ast.walk(fn) if isinstance(n, ast.Call)]
        claim_lines = [n.lineno for n in calls if _call_name(n) == "claim_runtime"]
        if not claim_lines:
            offenders.append("%s:%s has no claim_runtime()" % (name, fn.name))
            continue
        state_lines = [n.lineno for n in calls if _call_name(n) in BEFORE or _call_name(n).endswith("Runner")]
        if state_lines and min(state_lines) < min(claim_lines):
            offenders.append("%s:%s builds runner/state at line %d before claim_runtime at %d"
                             % (name, fn.name, min(state_lines), min(claim_lines)))
    assert not offenders, "\n".join(offenders)
