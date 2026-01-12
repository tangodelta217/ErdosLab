#!/usr/bin/env python3
"""Set problems/ACTIVE to a given problem directory."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def usage() -> None:
    print("Usage: python3 tools/set_active.py PXXXX")


def confirm(prompt: str) -> bool:
    reply = input(prompt).strip().lower()
    return reply in {"y", "yes"}


def remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def main() -> int:
    args = sys.argv[1:]
    yes = False
    filtered = []
    for arg in args:
        if arg in {"-y", "--yes"}:
            yes = True
        else:
            filtered.append(arg)
    args = filtered
    if len(args) != 1:
        usage()
        return 2

    problem_id = args[0]
    root = Path(__file__).resolve().parent.parent
    problems_dir = root / "problems"
    source_dir = problems_dir / problem_id
    active_dir = problems_dir / "ACTIVE"

    if not source_dir.is_dir():
        print(f"ERROR: {source_dir.relative_to(root)} does not exist.")
        return 1

    if active_dir.exists() or active_dir.is_symlink():
        if not yes and not confirm(
            f"problems/ACTIVE exists. Replace it with {problem_id}? [y/N]: "
        ):
            print("Aborted.")
            return 1
        remove_path(active_dir)
    else:
        if not yes and not confirm(f"Set problems/ACTIVE to {problem_id}? [y/N]: "):
            print("Aborted.")
            return 1

    used_symlink = False
    try:
        rel_target = source_dir.relative_to(problems_dir)
        os.symlink(rel_target, active_dir, target_is_directory=True)
        used_symlink = True
    except Exception:
        shutil.copytree(source_dir, active_dir)

    method = "symlink" if used_symlink else "copy"
    print(f"ACTIVE set to {problem_id} via {method}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
