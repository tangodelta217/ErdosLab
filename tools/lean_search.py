#!/usr/bin/env python3
"""Scaffold Lean search queries and capture output logs."""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
from pathlib import Path
from typing import Optional, Tuple

import llm_utils
import solver_scaffold

PLACEHOLDER_QUERY = (
    "-- Paste Lean search commands below (e.g. #find, #check, simp?, by?)\n\n"
    "import Mathlib\n\n"
)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scaffold Lean search queries and optionally run them."
    )
    parser.add_argument("problem", help="Problem id (e.g. 379 or P0379).")
    parser.add_argument(
        "--run",
        default="latest",
        help="Run id (default: latest).",
    )
    parser.add_argument(
        "--target",
        help="Override Lean query file to run (relative to repo root).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run `lake env lean` on the query file and capture output.",
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


def build_prompt(problem_id: str, statement_text: str) -> str:
    lines = [
        "# Lean Search Prompt (manual)",
        "",
        "Version: v1",
        "",
        "Goal: find useful lemmas in Mathlib with #find, #check, simp?, by?.",
        "Rules: only output Lean commands; no proofs required.",
        "",
        f"problem_id: {problem_id}",
        "",
        "Frozen statement:",
        statement_text.strip(),
        "",
        "Output: Lean commands only (no Markdown).",
    ]
    return "\n".join(lines).rstrip() + "\n"


def write_scaffold(
    *,
    problem_dir: Path,
    problem_id: str,
    run_dir: Path,
) -> Path:
    lean_dir = run_dir / "lean"
    search_dir = lean_dir / "search"
    search_dir.mkdir(parents=True, exist_ok=True)

    frozen_path = problem_dir / "statement" / "frozen_v1.md"
    frozen_text = frozen_path.read_text(encoding="utf-8") if frozen_path.exists() else ""
    statement_text = solver_scaffold.extract_statement(frozen_text)

    prompt = build_prompt(problem_id, statement_text)
    prompt_path = search_dir / "search_prompt.md"
    if not prompt_path.exists():
        prompt_path.write_text(prompt, encoding="utf-8")

    query_path = search_dir / "search_queries.lean"
    if not query_path.exists():
        query_path.write_text(PLACEHOLDER_QUERY, encoding="utf-8")

    notes_path = search_dir / "search_notes.md"
    if not notes_path.exists():
        notes_path.write_text("# Search notes\n\n", encoding="utf-8")

    llm_utils.write_model_prompts(
        run_dir / "llm" / "lean_search",
        prompt,
        response_extension=".lean",
        placeholder=PLACEHOLDER_QUERY,
    )

    return query_path


def run_check(root: Path, target: Path, search_dir: Path) -> int:
    if not target.exists():
        print(f"ERROR: missing Lean file: {target}")
        return 1

    cmd = ["lake", "env", "lean", str(target)]
    result = subprocess.run(
        cmd,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    log_path = search_dir / "search_last_run.log"
    log_path.write_text(
        (result.stdout or "") + "\n" + (result.stderr or ""),
        encoding="utf-8",
    )

    feedback_lines = [
        "# Lean search feedback",
        "",
        f"- command: {' '.join(cmd)}",
        f"- exit_code: {result.returncode}",
        f"- timestamp: {now_iso()}",
        "",
        "Lean output:",
        "```",
        (result.stdout or "") + (result.stderr or ""),
        "```",
    ]
    (search_dir / "search_feedback.md").write_text(
        "\n".join(feedback_lines).rstrip() + "\n",
        encoding="utf-8",
    )
    return 0 if result.returncode == 0 else 1


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

    run_dir, err = resolve_run_dir(problem_dir, args.run)
    if err or run_dir is None:
        print(f"ERROR: {err}")
        return 1

    query_path = write_scaffold(
        problem_dir=problem_dir,
        problem_id=problem_id,
        run_dir=run_dir,
    )
    solver_scaffold.log_event(root, f"lean search scaffold for {problem_id} in {run_dir.name}")

    if args.check:
        if args.target:
            target = Path(args.target)
            if not target.is_absolute():
                target = root / target
        else:
            target = query_path
        return run_check(root, target, query_path.parent)

    print(f"Lean search scaffold ready in {query_path.relative_to(root)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
