#!/usr/bin/env python3
"""Split a large staged dump into N smaller commits grouped by directory."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


TARGET_COMMITS = 50
MAX_FILES_PER_COMMIT = 900


def run(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    result = subprocess.run(args, capture_output=True, text=True, check=check, cwd=cwd)
    return result.stdout.strip()


def collect_files(repo: Path) -> list[str]:
    out = run("git", "diff", "--name-only", "750df94", "302fc09", cwd=repo)
    return [line for line in out.splitlines() if line]


def group_key(path: str, depth: int) -> str:
    parts = Path(path).parts
    if not parts:
        return ""
    depth = min(depth, len(parts))
    return str(Path(*parts[:depth]))


def split_group(files: list[str], depth: int) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    for path in files:
        key = group_key(path, depth)
        groups.setdefault(key, []).append(path)
    return groups


def partition_files(files: list[str], target: int) -> list[list[str]]:
    if not files:
        return []

    groups = {"__root__": files}
    depth = 1

    while True:
        oversized = [k for k, v in groups.items() if len(v) > MAX_FILES_PER_COMMIT]
        if not oversized:
            break
        if depth > 12:
            break
        next_groups: dict[str, list[str]] = {}
        for key, group_files in groups.items():
            if key in oversized:
                for subkey, subfiles in split_group(group_files, depth).items():
                    next_groups[subkey] = subfiles
            else:
                next_groups[key] = group_files
        groups = next_groups
        depth += 1

    # Split any remaining oversized groups by fixed-size batches.
    final_groups: list[list[str]] = []
    for group_files in groups.values():
        if len(group_files) <= MAX_FILES_PER_COMMIT:
            final_groups.append(sorted(group_files))
            continue
        sorted_files = sorted(group_files)
        for i in range(0, len(sorted_files), MAX_FILES_PER_COMMIT):
            final_groups.append(sorted_files[i : i + MAX_FILES_PER_COMMIT])

    final_groups.sort(key=lambda g: g[0])

    # Merge smallest groups until we are near the target count.
    while len(final_groups) > target:
        final_groups.sort(key=len)
        a = final_groups.pop(0)
        b = final_groups.pop(0)
        merged = sorted(a + b)
        final_groups.append(merged)
        final_groups.sort(key=lambda g: g[0])

    # If we have too few groups, split the largest ones.
    while len(final_groups) < target:
        final_groups.sort(key=len, reverse=True)
        largest = final_groups.pop(0)
        if len(largest) < 2:
            final_groups.append(largest)
            break
        mid = len(largest) // 2
        final_groups.append(largest[:mid])
        final_groups.append(largest[mid:])
        final_groups.sort(key=lambda g: g[0])

    return final_groups


def commit_label(files: list[str]) -> str:
    roots = sorted({group_key(path, 1) for path in files})
    if len(roots) == 1:
        root = roots[0]
        if len(files) == 1:
            return f"add {root}"
        inner = sorted({group_key(path, 2) for path in files if len(Path(path).parts) > 1})
        if len(inner) == 1:
            return f"add {inner[0]} ({len(files)} files)"
        return f"add {root} ({len(files)} files)"
    if len(roots) <= 3:
        return f"add {', '.join(roots)} ({len(files)} files)"
    return f"add {roots[0]} +{len(roots) - 1} more ({len(files)} files)"


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=repo, check=True)

    files = collect_files(repo)
    if not files:
        print("No files found between 750df94 and 302fc09.")
        return 1

    print(f"Resetting soft to 750df94 ({len(files)} files to re-commit)...")
    run("git", "reset", "--soft", "750df94", cwd=repo)
    run("git", "reset", cwd=repo)

    groups = partition_files(files, TARGET_COMMITS)
    print(f"Creating {len(groups)} commits...")

    for idx, group in enumerate(groups, start=1):
        for path in group:
            subprocess.run(["git", "add", "--", path], cwd=repo, check=True)
        msg = f"{commit_label(group)} [{idx}/{len(groups)}]"
        subprocess.run(["git", "commit", "-m", msg], cwd=repo, check=True)
        print(msg)

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
