from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .causality import AUDIT
from .models import new_id, utc_now_iso


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_artifact(path: Path, base: Optional[Path] = None) -> Dict[str, Any]:
    path = Path(path)
    resolved_path = path.resolve()
    resolved_base = Path(base).resolve() if base is not None else None
    rel = str(resolved_path.relative_to(resolved_base)) if resolved_base is not None and _is_relative_to(resolved_path, resolved_base) else str(path)
    if not path.exists() or not path.is_file():
        return {"path": rel, "exists": False, "sha256": "", "bytes": 0}
    return {
        "path": rel,
        "exists": True,
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def write_run_manifest(
    output_root: Path,
    *,
    command: Optional[Iterable[str]] = None,
    data_inputs: Optional[Iterable[Path]] = None,
    output_paths: Optional[Iterable[Path]] = None,
    strategy_config: Optional[Dict[str, Any]] = None,
    broker_realism_config: Optional[Dict[str, Any]] = None,
    causality_mode: str = AUDIT,
    extra: Optional[Dict[str, Any]] = None,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    repo_root = Path(repo_root or _discover_repo_root(output_root))
    command_list = list(command) if command is not None else list(sys.argv)
    data_inputs = [path for path in (data_inputs or []) if path is not None]
    output_paths = [path for path in (output_paths or []) if path is not None]
    manifest = {
        "run_id": new_id("run"),
        "created_at": utc_now_iso(),
        "command": command_list,
        "cwd": os.getcwd(),
        "python": {
            "executable": sys.executable,
            "version": sys.version,
            "platform": platform.platform(),
        },
        "git": git_state(repo_root),
        "causality_mode": causality_mode,
        "strategy_config": strategy_config or {},
        "broker_realism_config": broker_realism_config or {},
        "data_inputs": [file_artifact(Path(path), repo_root) for path in data_inputs],
        "outputs": [file_artifact(Path(path), output_root) for path in output_paths],
        "extra": extra or {},
    }
    manifest_path = output_root / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checksum = sha256_file(manifest_path)
    (output_root / "run_manifest.sha256").write_text("%s  run_manifest.json\n" % checksum, encoding="utf-8")
    return manifest


def git_state(repo_root: Path) -> Dict[str, Any]:
    repo_root = Path(repo_root)
    commit = _git(repo_root, ["rev-parse", "HEAD"])
    status = _git(repo_root, ["status", "--short"])
    return {
        "repo_root": str(repo_root),
        "commit": commit,
        "dirty": bool(status.strip()),
        "status_short": status.splitlines(),
    }


def _git(repo_root: Path, args: List[str]) -> str:
    try:
        proc = subprocess.run(
            ["git"] + args,
            cwd=str(repo_root),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError:
        return ""
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


def _discover_repo_root(path: Path) -> Path:
    current = Path(path).resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".git").exists():
            return parent
    return current


def _is_relative_to(path: Path, base: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(base).resolve())
        return True
    except ValueError:
        return False
