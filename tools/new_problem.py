#!/usr/bin/env python3
"""Create a new problem directory from the TEMPLATE."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict


def usage() -> None:
    print("Usage: python3 tools/new_problem.py PXXXX \"Optional title\"")


def load_status(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except Exception:
        return {}
    return {}


def main() -> int:
    args = sys.argv[1:]
    if len(args) < 1 or len(args) > 2:
        usage()
        return 2

    problem_id = args[0]
    title = args[1] if len(args) == 2 else None

    root = Path(__file__).resolve().parent.parent
    problems_dir = root / "problems"
    template_dir = problems_dir / "TEMPLATE"

    if not template_dir.is_dir():
        print("ERROR: problems/TEMPLATE is missing.")
        return 1

    target_dir = problems_dir / problem_id
    if target_dir.exists():
        print(f"ERROR: {target_dir.relative_to(root)} already exists.")
        return 1

    shutil.copytree(template_dir, target_dir)

    status_path = target_dir / "status.json"
    data = load_status(status_path)

    data["problem_id"] = problem_id
    if title:
        data["title"] = title
    else:
        data.pop("title", None)

    claim = data.get("claim")
    if not isinstance(claim, dict):
        claim = {}
        data["claim"] = claim
    claim["state"] = "partial"

    frozen = data.get("frozen_statement")
    if not isinstance(frozen, dict):
        frozen = {}
        data["frozen_statement"] = frozen
    frozen["file"] = "statement/frozen_v1.md"

    if not isinstance(data.get("evidence"), list):
        data["evidence"] = []

    status_path.write_text(
        json.dumps(data, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    print(f"Created {target_dir.relative_to(root)}")
    print("ACTIVE was not modified.")
    print("To set ACTIVE, review the folder and run:")
    print(f"  python3 tools/set_active.py {problem_id}")
    print("Or manually replace problems/ACTIVE.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
