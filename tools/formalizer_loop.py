#!/usr/bin/env python3
"""Scaffold and validate manual Lean formalization attempts."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import llm_utils
import solver_scaffold

PLACEHOLDER_LEAN = "-- Paste Lean code below (no sorry/admit/axiom/unsafe)\n\nimport Mathlib\n\n"
ATTEMPT_PREFIX = "attempt_"
ATTEMPT_PATTERN = re.compile(r"attempt_(\d+)\.lean$")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scaffold a formalization prompt and optionally check Lean output."
    )
    parser.add_argument("problem", help="Problem id (e.g. 379 or P0379).")
    parser.add_argument(
        "--run",
        default="latest",
        help="Run id (default: latest).",
    )
    parser.add_argument(
        "--attempt",
        help="Use a numbered attempt file (e.g. 1 or 3). Use 'latest' for most recent.",
    )
    parser.add_argument(
        "--new-attempt",
        action="store_true",
        help="Create a new numbered attempt file and use it.",
    )
    parser.add_argument(
        "--target",
        help="Override Lean file to check (relative to repo root).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Run `lake env lean` on the target file and capture errors.",
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


def load_best_plan(problem_dir: Path) -> Optional[Dict[str, Any]]:
    plan_path = problem_dir / "solver" / "best" / "plan.json"
    if not plan_path.exists():
        return None
    try:
        data = json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def ensure_attempts_dir(lean_dir: Path) -> Path:
    attempts_dir = lean_dir / "attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)
    readme_path = attempts_dir / "README.md"
    if not readme_path.exists():
        readme_path.write_text(
            "# Lean Attempts\n\n"
            "Store iterative attempts as attempt_001.lean, attempt_002.lean, ...\n"
            "Use `tools/formalizer_loop.py --attempt latest --check` to validate.\n",
            encoding="utf-8",
        )
    return attempts_dir


def list_attempt_indices(attempts_dir: Path) -> List[int]:
    indices: List[int] = []
    for path in attempts_dir.glob(f"{ATTEMPT_PREFIX}*.lean"):
        match = ATTEMPT_PATTERN.match(path.name)
        if match:
            try:
                indices.append(int(match.group(1)))
            except ValueError:
                continue
    return sorted(indices)


def next_attempt_index(attempts_dir: Path) -> int:
    indices = list_attempt_indices(attempts_dir)
    return (indices[-1] + 1) if indices else 1


def is_placeholder(text: str) -> bool:
    return text.strip().startswith("-- Paste Lean code below")


def create_attempt(
    *,
    attempts_dir: Path,
    index: int,
    base_text: Optional[str] = None,
) -> Path:
    path = attempts_dir / f"{ATTEMPT_PREFIX}{index:03d}.lean"
    if path.exists():
        return path
    content = base_text if base_text and not is_placeholder(base_text) else PLACEHOLDER_LEAN
    path.write_text(content, encoding="utf-8")
    return path


def build_prompt(
    *,
    problem_id: str,
    statement_text: str,
    best_plan: Optional[Dict[str, Any]],
) -> str:
    lines = [
        "# Formalizer Prompt (manual)",
        "",
        "Version: v1",
        "",
        "Goal: produce Lean code that compiles in this repo using Mathlib.",
        "Rules: do NOT use sorry/admit/axiom/unsafe. Keep everything explicit.",
        "",
        f"problem_id: {problem_id}",
        "",
        "Frozen statement:",
        statement_text.strip(),
        "",
    ]
    if best_plan:
        lines.append("Suggested lemmata (from solver/best):")
        key_lemmas = best_plan.get("key_lemmas", [])
        if isinstance(key_lemmas, list) and key_lemmas:
            for lemma in key_lemmas:
                if isinstance(lemma, dict):
                    statement = str(lemma.get("statement", "")).strip()
                    if statement:
                        lines.append(f"- {statement}")
        else:
            lines.append("- (none listed)")
        lines.append("")
    lines.append(
        "Output: Lean code only (no Markdown), starting with imports, defining the "
        "main theorem and any helper lemmas."
    )
    return "\n".join(lines).rstrip() + "\n"


def write_scaffold(
    *,
    problem_dir: Path,
    problem_id: str,
    run_dir: Path,
) -> Path:
    lean_dir = run_dir / "lean"
    lean_dir.mkdir(parents=True, exist_ok=True)
    ensure_attempts_dir(lean_dir)

    frozen_path = problem_dir / "statement" / "frozen_v1.md"
    frozen_text = frozen_path.read_text(encoding="utf-8") if frozen_path.exists() else ""
    statement_text = solver_scaffold.extract_statement(frozen_text)
    best_plan = load_best_plan(problem_dir)

    prompt = build_prompt(
        problem_id=problem_id, statement_text=statement_text, best_plan=best_plan
    )
    prompt_path = lean_dir / "formalizer_prompt.md"
    if not prompt_path.exists():
        prompt_path.write_text(prompt, encoding="utf-8")

    response_path = lean_dir / "formalizer_response.lean"
    if not response_path.exists():
        response_path.write_text(PLACEHOLDER_LEAN, encoding="utf-8")

    llm_utils.write_model_prompts(
        run_dir / "llm" / "formalizer",
        prompt,
        response_extension=".lean",
        placeholder=PLACEHOLDER_LEAN,
    )

    return response_path


def run_check(root: Path, target: Path, run_dir: Path) -> int:
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
    lean_dir = run_dir / "lean"
    attempts_dir = lean_dir / "attempts"
    log_path = lean_dir / "formalizer_last_build.log"
    feedback_path = lean_dir / "formalizer_feedback.md"
    try:
        rel = target.relative_to(attempts_dir)
        stem = rel.stem
        log_path = attempts_dir / f"{stem}_build.log"
        feedback_path = attempts_dir / f"{stem}_feedback.md"
    except ValueError:
        pass
    log_path.write_text(
        (result.stdout or "") + "\n" + (result.stderr or ""),
        encoding="utf-8",
    )

    feedback_lines = [
        "# Formalizer feedback",
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
    feedback_path.write_text(
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

    response_path = write_scaffold(
        problem_dir=problem_dir,
        problem_id=problem_id,
        run_dir=run_dir,
    )
    solver_scaffold.log_event(root, f"formalizer scaffold for {problem_id} in {run_dir.name}")

    target: Optional[Path] = None
    lean_dir = run_dir / "lean"
    attempts_dir = ensure_attempts_dir(lean_dir)
    if args.new_attempt:
        base_text = None
        if response_path.exists():
            base_text = response_path.read_text(encoding="utf-8")
        attempt_index = next_attempt_index(attempts_dir)
        target = create_attempt(
            attempts_dir=attempts_dir, index=attempt_index, base_text=base_text
        )
        print(f"Created new attempt: {target.relative_to(root)}")
    elif args.attempt:
        attempt_label = args.attempt.strip().lower()
        if attempt_label == "latest":
            indices = list_attempt_indices(attempts_dir)
            if not indices:
                target = create_attempt(attempts_dir=attempts_dir, index=1)
            else:
                target = attempts_dir / f"{ATTEMPT_PREFIX}{indices[-1]:03d}.lean"
        else:
            if not attempt_label.isdigit():
                print("ERROR: --attempt must be a number or 'latest'")
                return 2
            index = int(attempt_label)
            target = attempts_dir / f"{ATTEMPT_PREFIX}{index:03d}.lean"
            if not target.exists():
                print(f"ERROR: attempt not found: {target.relative_to(root)}")
                return 1
    elif args.target:
        target = Path(args.target)
        if not target.is_absolute():
            target = root / target

    if args.check:
        if target is None:
            target = response_path
        return run_check(root, target, run_dir)

    print(f"Formalizer scaffold ready in {run_dir.relative_to(root)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
