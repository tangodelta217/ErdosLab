#!/usr/bin/env python3
"""Validate solver planner JSON before ingest."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import solver_scaffold

DEFAULT_MAX_PLANS = int(os.getenv("SOLVER_MAX_PLANS", "8"))
ALLOWED_CHECKABILITY = {"easy", "medium", "hard"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate solver planner JSON output before ingest."
    )
    parser.add_argument("problem", help="Problem id (e.g. 379 or P0379).")
    parser.add_argument(
        "--run",
        default="latest",
        help="Run id to validate (default: latest).",
    )
    parser.add_argument(
        "--file",
        help="Override path to planner_response.md (relative to repo root).",
    )
    parser.add_argument(
        "--max-plans",
        type=int,
        default=DEFAULT_MAX_PLANS,
        help="Maximum number of plans allowed in JSON.",
    )
    return parser.parse_args()


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    match = re.search(r"```json(.*?)```", text, re.S | re.I)
    if not match:
        match = re.search(r"```(.*?)```", text, re.S)
    blob = match.group(1) if match else text
    try:
        data = json.loads(blob)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


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


def validate_list(name: str, value: Any, errors: List[str], index: int) -> List[Any]:
    if not isinstance(value, list):
        errors.append(f"plan[{index}] {name} must be a list")
        return []
    return value


def validate_plan(plan: Any, index: int, errors: List[str]) -> None:
    if not isinstance(plan, dict):
        errors.append(f"plan[{index}] must be an object")
        return
    for field in ("strategy_name", "high_level_idea"):
        if not isinstance(plan.get(field), str) or not plan.get(field):
            errors.append(f"plan[{index}] missing {field}")

    key_lemmas = validate_list("key_lemmas", plan.get("key_lemmas"), errors, index)
    for lemma_idx, lemma in enumerate(key_lemmas):
        if not isinstance(lemma, dict):
            errors.append(f"plan[{index}] key_lemmas[{lemma_idx}] must be an object")
            continue
        if not isinstance(lemma.get("statement"), str) or not lemma.get("statement"):
            errors.append(
                f"plan[{index}] key_lemmas[{lemma_idx}] missing statement"
            )
        if not isinstance(lemma.get("why_needed"), str) or not lemma.get("why_needed"):
            errors.append(
                f"plan[{index}] key_lemmas[{lemma_idx}] missing why_needed"
            )
        sources = lemma.get("likely_sources")
        if not isinstance(sources, list) or not sources:
            errors.append(
                f"plan[{index}] key_lemmas[{lemma_idx}] missing likely_sources"
            )
        checkability = lemma.get("checkability")
        if checkability not in ALLOWED_CHECKABILITY:
            errors.append(
                f"plan[{index}] key_lemmas[{lemma_idx}] checkability must be easy|medium|hard"
            )

    for field in (
        "definitions_needed",
        "risk_factors",
        "experiments",
        "formalization_path",
        "dependency_graph",
    ):
        items = validate_list(field, plan.get(field), errors, index)
        if items and not all(isinstance(item, str) for item in items):
            errors.append(f"plan[{index}] {field} must contain strings")

    payoff = plan.get("expected_payoff")
    difficulty = plan.get("difficulty")
    if not isinstance(payoff, (int, float)):
        errors.append(f"plan[{index}] expected_payoff must be a number")
    elif not 0.0 <= float(payoff) <= 1.0:
        errors.append(f"plan[{index}] expected_payoff must be in [0,1]")
    if not isinstance(difficulty, (int, float)):
        errors.append(f"plan[{index}] difficulty must be a number")
    elif not 0.0 <= float(difficulty) <= 1.0:
        errors.append(f"plan[{index}] difficulty must be in [0,1]")


def validate_payload(
    payload: Dict[str, Any], expected_problem_id: str, max_plans: int
) -> List[str]:
    errors: List[str] = []
    problem_id = payload.get("problem_id")
    if problem_id != expected_problem_id:
        errors.append(
            f"problem_id mismatch: expected {expected_problem_id}, got {problem_id}"
        )
    if not isinstance(payload.get("generated_at"), str):
        errors.append("generated_at must be a string (YYYY-MM-DD)")
    if not isinstance(payload.get("solver_used_scout"), bool):
        errors.append("solver_used_scout must be boolean")

    plans = payload.get("plans")
    if not isinstance(plans, list):
        errors.append("plans must be a list")
        return errors
    if len(plans) < 3:
        errors.append("plans must include at least 3 entries")
    if len(plans) > max_plans:
        errors.append(f"plans must include at most {max_plans} entries")
    for idx, plan in enumerate(plans):
        validate_plan(plan, idx, errors)
    return errors


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

    if args.file:
        response_path = Path(args.file)
        if not response_path.is_absolute():
            response_path = root / response_path
    else:
        run_dir, err = resolve_run_dir(problem_dir, args.run)
        if err or run_dir is None:
            print(f"ERROR: {err}")
            return 1
        response_path = run_dir / "planner_response.md"

    if not response_path.exists():
        print(f"ERROR: missing planner_response.md at {response_path}")
        return 1

    response_text = response_path.read_text(encoding="utf-8")
    payload = extract_json(response_text)
    if payload is None:
        print("ERROR: could not parse JSON from planner_response.md.")
        return 1

    errors = validate_payload(payload, problem_id, args.max_plans)
    if errors:
        print("ERROR: planner JSON failed validation.")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("OK: planner JSON validates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
