#!/usr/bin/env python3
"""Generate a semantic audit checklist comparing statement vs Lean formalization."""

from __future__ import annotations

import argparse
import datetime as dt
import re
from pathlib import Path
from typing import List, Optional, Tuple

import solver_scaffold


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a semantic audit checklist for a problem."
    )
    parser.add_argument("problem", help="Problem id (e.g. 379 or P0379).")
    parser.add_argument(
        "--lean-file",
        help="Lean file to inspect (relative to repo root).",
    )
    parser.add_argument(
        "--run",
        default="latest",
        help="Solver run id to inspect if no Lean file is provided.",
    )
    return parser.parse_args()


def resolve_run_dir(problem_dir: Path, run_id: str) -> Tuple[Optional[Path], Optional[str]]:
    runs_dir = problem_dir / "solver" / "runs"
    if run_id == "latest":
        latest = solver_scaffold.resolve_latest_run(runs_dir)
        if not latest:
            return None, "latest run not found"
        run_id = latest
    run_dir = runs_dir / run_id
    if not run_dir.exists():
        return None, f"run directory not found: {run_dir}"
    return run_dir, None


def extract_lean_statements(path: Path) -> List[str]:
    statements = []
    if not path.exists():
        return statements
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        stripped = line.strip()
        if re.match(r"^(theorem|lemma|def|structure|class|abbrev)\s+", stripped):
            statements.append(stripped)
    return statements[:20]


def resolve_lean_file(
    root: Path, problem_id: str, problem_dir: Path, run_id: str, override: Optional[str]
) -> Optional[Path]:
    if override:
        path = Path(override)
        return path if path.is_absolute() else root / path
    lean_path = root / "ErdosLab" / "Problems" / f"{problem_id}.lean"
    if lean_path.exists():
        return lean_path
    run_dir, _ = resolve_run_dir(problem_dir, run_id)
    if run_dir:
        candidate = run_dir / "lean" / "formalizer_response.lean"
        if candidate.exists():
            return candidate
    return None


def write_audit(
    *,
    root: Path,
    problem_id: str,
    problem_dir: Path,
    run_id: str = "latest",
    lean_file: Optional[str] = None,
) -> Path:
    frozen_path = problem_dir / "statement" / "frozen_v1.md"
    frozen_text = frozen_path.read_text(encoding="utf-8") if frozen_path.exists() else ""
    statement_text = solver_scaffold.extract_statement(frozen_text)

    resolved_lean = resolve_lean_file(root, problem_id, problem_dir, run_id, lean_file)
    lean_lines = extract_lean_statements(resolved_lean) if resolved_lean else []
    lean_rel = (
        resolved_lean.relative_to(root)
        if resolved_lean and resolved_lean.exists()
        else None
    )

    audit_lines = [
        "# Semantic Audit Checklist",
        "",
        "Status: INCOMPLETE",
        "Reviewer: TBD",
        "Notes: TBD",
        "",
        f"- problem_id: {problem_id}",
        f"- generated_at: {now_iso()}",
    ]
    if lean_rel:
        audit_lines.append(f"- lean_file: {lean_rel}")
    else:
        audit_lines.append("- lean_file: (none found)")
    audit_lines += [
        "",
        "Frozen statement (excerpt):",
        "```",
        statement_text.strip(),
        "```",
        "",
        "Lean statement candidates:",
    ]
    if lean_lines:
        for line in lean_lines:
            audit_lines.append(f"- {line}")
    else:
        audit_lines.append("- (none found)")
    audit_lines += [
        "",
        "Checklist:",
        "- [ ] Quantifiers and domains match the frozen statement.",
        "- [ ] All hypotheses and side conditions are present.",
        "- [ ] Edge cases (n=0/1, empty sets, etc.) are handled.",
        "- [ ] Definitions align with the informal statement.",
        "- [ ] The Lean theorem is not a weaker/stronger variant.",
        "",
        "Reviewer notes:",
        "- ",
    ]

    audit_path = problem_dir / "statement" / "semantic_audit.md"
    audit_path.write_text("\n".join(audit_lines).rstrip() + "\n", encoding="utf-8")
    return audit_path


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parent.parent
    try:
        problem_id, _ = solver_scaffold.normalize_problem_id(args.problem)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    problem_dir = root / "problems" / problem_id
    if not problem_dir.exists():
        print(f"ERROR: missing problem directory: {problem_dir}")
        return 1

    audit_path = write_audit(
        root=root,
        problem_id=problem_id,
        problem_dir=problem_dir,
        run_id=args.run,
        lean_file=args.lean_file,
    )
    solver_scaffold.log_event(root, f"semantic audit generated for {problem_id}")
    print(f"Wrote {audit_path.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
