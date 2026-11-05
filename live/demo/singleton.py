"""One live runtime per strategy, per output folder, and per OANDA account + instrument.

Every demo/OANDA runner calls :func:`claim_runtime` before it builds an Engine or touches
state. Locks are ``fcntl.flock`` on files that stay open for the life of the process, so the
OS releases them on any exit (including SIGKILL) and there is no stale-lock cleanup.

Locks (all must be free, else the runner exits ``EXIT_REFUSED`` without trading):

* ``<output_root>/daemon.lock``                       — one process per state folder
* ``live/demo/.locks/strategy/<strategy_id>.lock``     — one process per strategy id
* ``live/demo/.locks/route/<account>__<instr>.lock``   — one router per account+instrument,
  and the strategy must be the owner in ``oanda_account_ownership.json``

flock is host-local; a daemon on another machine is only caught by the broker-side checks.
"""
from __future__ import annotations

import fcntl
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, IO, List, Optional, Tuple

DEMO_DIR = Path(__file__).resolve().parent
REPO = DEMO_DIR.parents[1]
HSM = REPO.parent
LOCK_ROOT = Path(os.environ.get("POTIONS_SINGLETON_LOCK_ROOT") or (DEMO_DIR / ".locks"))
REGISTRY_PATH = DEMO_DIR / "oanda_account_ownership.json"
AUDIT_STATE_PATH = LOCK_ROOT / "audit_state.json"
AUDIT_REPORT_PATH = DEMO_DIR / "SINGLETON_AUDIT.json"
EXIT_REFUSED = 3
WATCHDOG_SECONDS = 300
ALARM_REPEAT_SECONDS = 3600

_HELD: Dict[str, IO[str]] = {}
_CLAIM: Dict[str, Any] = {}
_WATCHDOG_STARTED = False


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _progress(output_root: Path, message: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%Y-%m-%dT%H:%M:%S"), message)
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    print(line, flush=True)


def output_lock_path(output_root: Path) -> Path:
    return Path(output_root) / "daemon.lock"


def strategy_lock_path(strategy_id: str) -> Path:
    return LOCK_ROOT / "strategy" / ("%s.lock" % strategy_id)


def route_lock_path(account_id: str, instrument: str) -> Path:
    return LOCK_ROOT / "route" / ("%s__%s.lock" % (account_id, instrument.upper()))


def read_lock_meta(path: Path) -> Dict[str, Any]:
    try:
        text = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return {}
    if not text:
        return {}
    try:
        meta = json.loads(text)
        if isinstance(meta, int):
            return {"pid": meta}
        return meta if isinstance(meta, dict) else {}
    except ValueError:
        try:
            return {"pid": int(text.splitlines()[0])}
        except ValueError:
            return {}


def lock_is_held(path: Path) -> bool:
    """True if some process holds ``path`` (probe with a fresh descriptor, then release)."""
    path = Path(path)
    if not path.exists():
        return False
    key = str(path.resolve())
    if key in _HELD:
        return True
    try:
        fh = path.open("r", encoding="utf-8")
    except OSError:
        return False
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return True
    else:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        return False
    finally:
        fh.close()


def _acquire(path: Path, meta: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    key = str(path.resolve())
    if key in _HELD:
        return True, {}
    fh = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return False, read_lock_meta(path)
    fh.seek(0)
    fh.truncate()
    fh.write(json.dumps(meta, sort_keys=True) + "\n")
    fh.flush()
    _HELD[key] = fh
    return True, {}


def _release(path: Path) -> None:
    fh = _HELD.pop(str(Path(path).resolve()), None)
    if fh is not None:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def load_registry(path: Path = REGISTRY_PATH) -> Dict[str, Dict[str, str]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {str(k): {str(i).upper(): str(s) for i, s in (v or {}).items()} for k, v in data.get("accounts", {}).items()}


def route_owner_problem(strategy_id: str, account_id: str, instrument: str, registry_path: Path = REGISTRY_PATH) -> str:
    """Empty string when ``strategy_id`` owns ``account_id``/``instrument``; else the reason."""
    try:
        registry = load_registry(registry_path)
    except (OSError, ValueError) as exc:
        return "ownership registry unreadable (%s): %s" % (registry_path, exc)
    if account_id not in registry:
        return "account %s not in %s" % (account_id, registry_path.name)
    owner = registry[account_id].get(instrument.upper())
    if not owner:
        return "account %s has no owner for %s in %s" % (account_id, instrument.upper(), registry_path.name)
    if owner != strategy_id:
        return "account %s %s is owned by %s, not %s" % (account_id, instrument.upper(), owner, strategy_id)
    return ""


def _restore_pidfile(output_root: Path, holder_pid: int, settle: float = 1.0) -> None:
    """A refused ``--daemon`` child: the spawning parent wrote our pid over the live one."""
    path = Path(output_root) / "pidfile"
    time.sleep(settle)
    try:
        if int(path.read_text(encoding="utf-8").strip()) == os.getpid():
            path.write_text("%d\n" % holder_pid, encoding="utf-8")
    except (OSError, ValueError):
        pass


def acquire_output_lock(output_root: Path) -> bool:
    """Output-folder lock only (CLI catch-all for runners that have not resolved a strategy yet)."""
    output_root = Path(output_root)
    ok, holder = _acquire(output_lock_path(output_root), _lock_meta(output_root=output_root))
    if not ok:
        if holder.get("pid"):
            _restore_pidfile(output_root, int(holder["pid"]))
        _progress(
            output_root,
            "REFUSING start: daemon.lock held by pid=%s; this pid=%s exits without trading"
            % (holder.get("pid", "?"), os.getpid()),
        )
    return ok


def _lock_meta(**extra: Any) -> Dict[str, Any]:
    meta = {
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "started_at": _utc_now(),
        "argv": list(sys.argv),
        "executable": sys.executable,
        "cwd": os.getcwd(),
    }
    meta.update({k: (str(v) if isinstance(v, Path) else v) for k, v in extra.items()})
    return meta


def claim_runtime(
    *,
    strategy_id: str,
    output_root: Path,
    account_id: str = "",
    instrument: str = "",
    routes_orders: bool = False,
    registry_path: Path = REGISTRY_PATH,
    watchdog: bool = True,
) -> bool:
    """Take every singleton lock for this runtime, or refuse. Call before building the runner."""
    output_root = Path(output_root)
    meta = _lock_meta(
        strategy_id=strategy_id,
        output_root=output_root.resolve(),
        account_id=account_id,
        instrument=instrument.upper(),
        routes_orders=bool(routes_orders),
    )
    if routes_orders:
        problem = route_owner_problem(strategy_id, account_id, instrument, registry_path)
        if problem:
            _progress(output_root, "REFUSING start: %s; this pid=%s exits without trading" % (problem, os.getpid()))
            return False
    wanted: List[Tuple[str, Path]] = [
        ("output", output_lock_path(output_root)),
        ("strategy", strategy_lock_path(strategy_id)),
    ]
    if routes_orders:
        wanted.append(("route", route_lock_path(account_id, instrument)))
    taken: List[Path] = []
    for label, path in wanted:
        already = str(path.resolve()) in _HELD if path.exists() else False
        ok, holder = _acquire(path, meta)
        if not ok:
            for p in taken:
                _release(p)
            if label == "output" and holder.get("pid"):
                _restore_pidfile(output_root, int(holder["pid"]))
            _progress(
                output_root,
                "REFUSING start: %s lock %s held by pid=%s (strategy=%s output=%s); this pid=%s exits without trading"
                % (label, path.name, holder.get("pid", "?"), holder.get("strategy_id", "?"),
                   holder.get("output_root", "?"), os.getpid()),
            )
            return False
        if not already:
            taken.append(path)
        else:
            # Re-stamp a catch-all output lock with the full runtime metadata.
            fh = _HELD[str(path.resolve())]
            fh.seek(0)
            fh.truncate()
            fh.write(json.dumps(meta, sort_keys=True) + "\n")
            fh.flush()
    _CLAIM.clear()
    _CLAIM.update(meta)
    _CLAIM["locks"] = [str(p) for _, p in wanted]
    _progress(
        output_root,
        "SINGLETON claimed strategy=%s account=%s instrument=%s routes_orders=%s pid=%s"
        % (strategy_id, account_id or "-", instrument.upper() or "-", bool(routes_orders), os.getpid()),
    )
    if watchdog:
        _start_watchdog(output_root)
    return True


# --------------------------------------------------------------------------- process scan


def _proc_cmdline(pid: int) -> List[str]:
    try:
        raw = Path("/proc/%d/cmdline" % pid).read_bytes()
    except OSError:
        return []
    return [p.decode("utf-8", "replace") for p in raw.split(b"\0") if p]


def _proc_start_epoch(pid: int) -> float:
    try:
        return Path("/proc/%d" % pid).stat().st_mtime
    except OSError:
        return 0.0


def _arg_after(argv: List[str], flag: str) -> str:
    for i, a in enumerate(argv):
        if a == flag and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return ""


def _demo_command(argv: List[str]) -> str:
    for a in argv:
        if a.startswith("demo-"):
            return a
    return ""


def runner_output_root(argv: List[str], cwd: str = "") -> Optional[Path]:
    out = _arg_after(argv, "--output-root")
    if out:
        p = Path(out)
        return (Path(cwd) / p) if cwd and not p.is_absolute() else p
    state = _arg_after(argv, "--state-root")
    if state:
        p = Path(state)
        p = (Path(cwd) / p) if cwd and not p.is_absolute() else p
        return p.parent if p.name == "state" else p
    return None


def scan_runners() -> List[Dict[str, Any]]:
    """Every live ``potions.live.cli demo-*`` runner process (not status/stop/audit/--daemon parents)."""
    out: List[Dict[str, Any]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        argv = _proc_cmdline(pid)
        if "potions.live.cli" not in argv:
            continue
        cmd = _demo_command(argv)
        if not cmd or cmd.endswith(("-status", "-stop")) or cmd in ("demo-singleton-audit", "demo-restart"):
            continue
        if "--daemon" in argv:
            continue
        try:
            cwd = os.readlink("/proc/%d/cwd" % pid)
        except OSError:
            cwd = ""
        root = runner_output_root(argv, cwd)
        out.append({
            "pid": pid,
            "command": cmd,
            "argv": argv,
            "cwd": cwd,
            "output_root": str(root.resolve()) if root else "",
            "started_epoch": _proc_start_epoch(pid),
        })
    return out


def _run_meta(output_root: str) -> Dict[str, Any]:
    if not output_root:
        return {}
    try:
        return json.loads((Path(output_root) / "RUN_META.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def audit(processes: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Classify running runners; ``alarms`` non-empty means a singleton rule is broken."""
    procs = scan_runners() if processes is None else processes
    alarms: List[str] = []
    notes: List[str] = []
    by_root: Dict[str, List[int]] = {}
    by_strategy: Dict[str, List[int]] = {}
    by_route: Dict[str, List[int]] = {}
    code = [p for d in ("live", "live/demo", "live/strategies") for p in (REPO / d).glob("*.py")]
    newest_code = max((p.stat().st_mtime for p in code), default=0.0)
    for p in procs:
        root = p["output_root"]
        by_root.setdefault(root or "?", []).append(p["pid"])
        meta = _run_meta(root)
        lock_path = output_lock_path(Path(root)) if root else None
        holder = read_lock_meta(lock_path) if lock_path else {}
        held = bool(lock_path) and lock_is_held(lock_path)
        p["lock_held"] = held
        p["lock_pid"] = holder.get("pid")
        sid = holder.get("strategy_id") or meta.get("strategy_id") or ""
        p["strategy_id"] = sid
        if sid:
            by_strategy.setdefault(sid, []).append(p["pid"])
        account = holder.get("account_id") or meta.get("oanda_account_id") or ""
        instrument = holder.get("instrument") or meta.get("instrument") or ""
        routes = holder.get("routes_orders", meta.get("oanda_routing", "_oanda" in Path(root).name))
        if routes and account and instrument:
            by_route.setdefault("%s__%s" % (account, str(instrument).upper()), []).append(p["pid"])
            problem = route_owner_problem(sid, account, instrument) if sid else ""
            if problem:
                alarms.append("WRONG_OWNER pid=%s %s" % (p["pid"], problem))
        if not held or holder.get("pid") != p["pid"]:
            alarms.append("UNLOCKED pid=%s %s output=%s (lock holder=%s)" % (p["pid"], p["command"], root, holder.get("pid")))
        elif not holder.get("strategy_id"):
            notes.append("CATCHALL_ONLY pid=%s %s holds output lock but never claimed strategy/route" % (p["pid"], p["command"]))
        pidfile = Path(root) / "pidfile" if root else None
        if pidfile and pidfile.exists():
            try:
                if int(pidfile.read_text().strip()) != p["pid"]:
                    notes.append("PIDFILE_MISMATCH pid=%s pidfile=%s" % (p["pid"], pidfile.read_text().strip()))
            except ValueError:
                pass
        if p["started_epoch"] and p["started_epoch"] < newest_code:
            notes.append("STALE_CODE pid=%s %s started before latest live/*.py edit" % (p["pid"], p["command"]))
    for label, groups in (("DUPLICATE_OUTPUT", by_root), ("DUPLICATE_STRATEGY", by_strategy), ("DUPLICATE_ROUTE", by_route)):
        for key, pids in groups.items():
            if len(pids) > 1:
                alarms.append("%s %s pids=%s" % (label, key, ",".join(str(x) for x in sorted(pids))))
    return {"ts": _utc_now(), "host": socket.gethostname(), "runners": procs, "alarms": alarms, "notes": notes}


def _alarm_due(signature: str) -> bool:
    try:
        state = json.loads(AUDIT_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    last = state.get(signature, 0)
    now = time.time()
    if now - float(last) < ALARM_REPEAT_SECONDS:
        return False
    state = {k: v for k, v in state.items() if now - float(v) < 7 * 86400}
    state[signature] = now
    AUDIT_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_STATE_PATH.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    return True


def send_alarm(subject: str, body: str, signature: str) -> bool:
    if not _alarm_due(signature):
        return False
    try:
        sys.path.insert(0, str(HSM))
        from potions.live.notify_email import send_email

        send_email(subject=subject, body=body)
        return True
    except Exception as exc:  # noqa: BLE001
        print("singleton alarm email failed: %s" % exc, file=sys.stderr)
        return False


def run_audit(*, email: bool = True, report_path: Path = AUDIT_REPORT_PATH) -> Dict[str, Any]:
    result = audit()
    slim = dict(result)
    slim["runners"] = [{k: v for k, v in r.items() if k != "argv"} for r in result["runners"]]
    report_path.write_text(json.dumps(slim, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if email and result["alarms"]:
        body = "HARD ALARM: singleton rule broken on %s\n\n%s\n\nRunners:\n%s\n\nNotes:\n%s\n" % (
            result["host"],
            "\n".join(result["alarms"]),
            "\n".join("  pid=%s %s output=%s lock_held=%s lock_pid=%s" % (
                r["pid"], r["command"], r["output_root"], r.get("lock_held"), r.get("lock_pid")) for r in result["runners"]),
            "\n".join(result["notes"]) or "-",
        )
        send_alarm("potions HARD ALARM: duplicate/unlocked demo daemon", body, "|".join(sorted(result["alarms"])))
    return result


# --------------------------------------------------------------------------- in-daemon watchdog


def _watchdog_tick(output_root: Path) -> List[str]:
    problems: List[str] = []
    for key, fh in list(_HELD.items()):
        try:
            if os.stat(key).st_ino != os.fstat(fh.fileno()).st_ino:
                problems.append("lock file %s was replaced; this pid no longer excludes others" % key)
        except OSError:
            problems.append("lock file %s was deleted; this pid no longer excludes others" % key)
    me = os.getpid()
    mine = str(Path(output_root).resolve())
    sid = _CLAIM.get("strategy_id")
    pidfile = Path(output_root) / "pidfile"
    try:
        if int(pidfile.read_text(encoding="utf-8").strip()) != me:
            pidfile.write_text("%d\n" % me, encoding="utf-8")
            _progress(Path(output_root), "SINGLETON pidfile re-asserted to lock holder pid=%s" % me)
    except (OSError, ValueError):
        pass
    for p in scan_runners():
        if p["pid"] == me:
            continue
        if p["output_root"] == mine:
            problems.append("sibling pid=%s runs on the same output root" % p["pid"])
        elif sid and read_lock_meta(output_lock_path(Path(p["output_root"]))).get("strategy_id") == sid:
            problems.append("sibling pid=%s runs strategy %s" % (p["pid"], sid))
    return problems


def _start_watchdog(output_root: Path, interval: float = WATCHDOG_SECONDS) -> None:
    global _WATCHDOG_STARTED
    if _WATCHDOG_STARTED:
        return
    _WATCHDOG_STARTED = True

    def loop() -> None:
        while True:
            time.sleep(interval)
            try:
                problems = _watchdog_tick(output_root)
            except Exception as exc:  # noqa: BLE001
                problems = []
                _progress(output_root, "SINGLETON watchdog error: %s" % exc)
            if problems:
                msg = "; ".join(problems)
                _progress(output_root, "SINGLETON HARD ALARM pid=%s: %s" % (os.getpid(), msg))
                send_alarm(
                    "potions HARD ALARM: singleton breach %s" % (_CLAIM.get("strategy_id") or output_root.name),
                    "pid=%s output=%s\n%s" % (os.getpid(), output_root, "\n".join(problems)),
                    "watchdog|%s|%s" % (output_root, msg),
                )

    threading.Thread(target=loop, name="singleton-watchdog", daemon=True).start()


# --------------------------------------------------------------------------- restart


def _launch_env() -> Dict[str, str]:
    env = os.environ.copy()
    demo_env = DEMO_DIR / ".env"
    if demo_env.exists() and not env.get("OANDA_TOKEN"):
        for line in demo_env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    bits = [str(HSM), str(REPO / "v20-python" / "src")]
    if env.get("PYTHONPATH"):
        bits.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(bits)
    return env


def _wait(predicate: Callable[[], bool], timeout: float, step: float = 0.5) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(step)
    return predicate()


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _runner_argv(output_root: Path) -> List[str]:
    holder = read_lock_meta(output_lock_path(output_root))
    if holder.get("argv"):
        return list(holder["argv"])
    runners = [p for p in scan_runners() if p["output_root"] == str(output_root)]
    return list(min(runners, key=lambda r: r["started_epoch"])["argv"]) if runners else []


def broker_flat(output_root: Path) -> Tuple[bool, str]:
    """(flat, detail) for the OANDA account this book routes to; paper books are always flat."""
    output_root = Path(output_root).resolve()
    holder = read_lock_meta(output_lock_path(output_root))
    account_id = str(holder.get("account_id") or "")
    cfg_path = _arg_after(_runner_argv(output_root), "--oanda-config")
    if not account_id and cfg_path:
        account_id = str(json.loads(Path(cfg_path).read_text(encoding="utf-8")).get("account_id") or "")
    if not account_id:
        return True, "no OANDA account (paper book)"
    env = _launch_env()
    import v20  # noqa: PLC0415

    api = v20.Context("api-fxpractice.oanda.com", 443, True, token=env.get("OANDA_TOKEN", ""))
    resp = api.account.get(account_id)
    if resp.status != 200:
        return False, "account %s query HTTP %s" % (account_id, resp.status)
    acct = resp.get("account", 200)
    detail = "account %s openTrades=%s pendingOrders=%s" % (account_id, acct.openTradeCount, acct.pendingOrderCount)
    return int(acct.openTradeCount) == 0 and int(acct.pendingOrderCount) == 0, detail


def restart(output_root: Path, *, stop_timeout: float = 60.0, start_timeout: float = 30.0) -> int:
    """Stop every runner on ``output_root``, wait for the locks to free, relaunch one, verify."""
    output_root = Path(output_root).resolve()
    lock = output_lock_path(output_root)
    runners = [p for p in scan_runners() if p["output_root"] == str(output_root)]
    holder = read_lock_meta(lock)
    argv: List[str] = []
    cwd = str(HSM)
    raw = list(holder.get("argv") or [])
    if raw and holder.get("pid") in [p["pid"] for p in runners]:
        # sys.argv under ``python -m potions.live.cli`` starts with the cli.py path.
        if raw[0].endswith("cli.py"):
            argv = [holder.get("executable") or sys.executable, "-m", "potions.live.cli"] + raw[1:]
        else:
            argv = raw
        cwd = holder.get("cwd") or cwd
    elif runners:
        oldest = min(runners, key=lambda r: r["started_epoch"])
        argv, cwd = list(oldest["argv"]), oldest["cwd"] or cwd
    if not argv:
        print("demo-restart: no running runner and no lock metadata for %s; start it with its --daemon command" % output_root)
        return 1
    for p in runners:
        os.kill(p["pid"], signal.SIGTERM)
        _progress(output_root, "demo-restart: SIGTERM pid=%s" % p["pid"])
    pids = [p["pid"] for p in runners]
    if not _wait(lambda: not any(_pid_alive(x) for x in pids) and not lock_is_held(lock), stop_timeout):
        for x in pids:
            if _pid_alive(x):
                os.kill(x, signal.SIGKILL)
                _progress(output_root, "demo-restart: SIGKILL pid=%s after %.0fs" % (x, stop_timeout))
        if not _wait(lambda: not lock_is_held(lock), 15.0):
            print("demo-restart: lock still held after SIGKILL; refusing to relaunch")
            return 1
    log_fh = (output_root / "run.log").open("a", encoding="utf-8")
    proc = subprocess.Popen(argv, stdout=log_fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            env=_launch_env(), start_new_session=True, cwd=cwd)
    (output_root / "pidfile").write_text("%d\n" % proc.pid, encoding="utf-8")
    _progress(output_root, "demo-restart: launched pid=%s" % proc.pid)
    ok = _wait(lambda: read_lock_meta(lock).get("pid") == proc.pid and lock_is_held(lock), start_timeout)
    others = [p["pid"] for p in scan_runners() if p["output_root"] == str(output_root) and p["pid"] != proc.pid]
    if not ok or proc.poll() is not None or others:
        print("demo-restart: FAILED pid=%s alive=%s lock_ok=%s others=%s (see %s)" % (
            proc.pid, proc.poll() is None, ok, others, output_root / "run.log"))
        return 1
    print("demo-restart: OK single runner pid=%s holds %s" % (proc.pid, lock))
    return 0
