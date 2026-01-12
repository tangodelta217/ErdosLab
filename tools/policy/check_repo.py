#!/usr/bin/env python3
"""Repo policy checks for problem status and evidence."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ALLOWED_STATES = {
    "partial",
    "solved",
    "disproved",
    "literature_solved",
    "ambiguous",
}


def ensure_problems_dir(root: Path) -> Tuple[Path, bool]:
    problems_dir = root / "problems"
    if problems_dir.exists():
        return problems_dir, False

    problems_dir.mkdir(parents=True, exist_ok=True)
    placeholder = problems_dir / ".gitkeep"
    if not placeholder.exists():
        placeholder.write_text("", encoding="utf-8")
    return problems_dir, True


def load_json(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return None, "root is not an object"
        return data, None
    except Exception as exc:  # pylint: disable=broad-except
        return None, str(exc)


def get_nested(data: Dict[str, Any], keys: List[str]) -> Tuple[Optional[Any], bool]:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None, False
        current = current[key]
    return current, True


def is_within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_repo_path(root: Path, base_dir: Path, path_str: str) -> Tuple[Optional[Path], Optional[str]]:
    path = Path(path_str)
    candidates = []

    if path.is_absolute():
        candidates.append(path)
    else:
        candidates.append(root / path)
        candidates.append(base_dir / path)

    for candidate in candidates:
        resolved = candidate.resolve()
        if not is_within_root(resolved, root):
            continue
        return resolved, None

    return None, "path escapes repo"


def validate_lean_evidence(
    root: Path,
    problem_dir: Path,
    evidence: Dict[str, Any],
    errors: List[str],
    idx: int,
) -> None:
    file_path = evidence.get("file")
    theorem = evidence.get("theorem")

    if not isinstance(file_path, str) or not file_path.strip():
        errors.append(f"evidence[{idx}].file is required for lean evidence")
        return
    if not isinstance(theorem, str) or not theorem.strip():
        errors.append(f"evidence[{idx}].theorem is required for lean evidence")
        return

    resolved, err = resolve_repo_path(root, problem_dir, file_path)
    if err is not None or resolved is None:
        errors.append(f"evidence[{idx}].file path is invalid: {file_path}")
        return

    if not resolved.exists():
        errors.append(f"evidence[{idx}].file does not exist: {file_path}")
        return

    try:
        content = resolved.read_text(encoding="utf-8")
    except Exception as exc:  # pylint: disable=broad-except
        errors.append(f"evidence[{idx}].file could not be read: {exc}")
        return

    if not re.search(re.escape(theorem), content):
        errors.append(
            f"evidence[{idx}].file does not mention theorem name: {theorem}"
        )


def validate_problem(status_path: Path, root: Path) -> List[str]:
    errors: List[str] = []
    data, err = load_json(status_path)
    if err is not None or data is None:
        return [f"invalid JSON: {err}"]

    problem_id = data.get("problem_id")
    if not isinstance(problem_id, str) or not problem_id.strip():
        errors.append("problem_id is required")

    claim_state, ok = get_nested(data, ["claim", "state"])
    if not ok:
        errors.append("claim.state is required")
        claim_state = None
    elif claim_state not in ALLOWED_STATES:
        errors.append(f"claim.state must be one of {sorted(ALLOWED_STATES)}")

    frozen_file, ok = get_nested(data, ["frozen_statement", "file"])
    if not ok:
        errors.append("frozen_statement.file is required")
    elif not isinstance(frozen_file, str) or not frozen_file.strip():
        errors.append("frozen_statement.file must be a non-empty string")

    if claim_state in {"solved", "disproved"}:
        required_files = [
            status_path.parent / "statement" / "frozen_v1.md",
            status_path.parent / "report" / "writeup.md",
        ]
        for req in required_files:
            if not req.exists():
                errors.append(f"missing required file: {req.relative_to(root)}")

        evidence = data.get("evidence")
        if not isinstance(evidence, list):
            errors.append("evidence list is required for solved/disproved")
        else:
            has_required = False
            for idx, item in enumerate(evidence):
                if not isinstance(item, dict):
                    errors.append(f"evidence[{idx}] must be an object")
                    continue
                evidence_type = item.get("type")
                if evidence_type in {"lean", "certificate"}:
                    has_required = True
                if evidence_type == "lean":
                    validate_lean_evidence(root, status_path.parent, item, errors, idx)

            if not has_required:
                errors.append("evidence must include type lean or certificate")

    if claim_state == "literature_solved":
        required_files = [
            status_path.parent / "literature" / "primary_sources.md",
            status_path.parent / "literature" / "mapping.md",
        ]
        for req in required_files:
            if not req.exists():
                errors.append(f"missing required file: {req.relative_to(root)}")

    if claim_state == "ambiguous":
        required_file = status_path.parent / "statement" / "variants.md"
        if not required_file.exists():
            errors.append(f"missing required file: {required_file.relative_to(root)}")

    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    problems_dir, created = ensure_problems_dir(root)

    if created:
        print("Created problems/ placeholder; no problems to validate yet.")

    status_files = sorted(problems_dir.glob("*/status.json"))
    if not status_files:
        print("No status.json files found under problems/.")
        print("Summary: 0 problems checked, 0 errors.")
        return 0

    total_errors = 0
    for status_path in status_files:
        errors = validate_problem(status_path, root)
        if errors:
            total_errors += len(errors)
            print(f"Errors in {status_path.relative_to(root)}:")
            for error in errors:
                print(f"  - {error}")

    print(
        f"Summary: {len(status_files)} problem(s) checked, {total_errors} error(s)."
    )

    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
