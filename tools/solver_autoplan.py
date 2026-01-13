#!/usr/bin/env python3
"""Generate a lightweight automatic plan seed (no LLM) for a solver run."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import literature_scout
import solver_scaffold


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a minimal automatic plan seed for a solver run."
    )
    parser.add_argument("problem", help="Problem id (e.g. 379 or P0379).")
    parser.add_argument(
        "--run",
        default="latest",
        help="Run id to populate (default: latest).",
    )
    parser.add_argument(
        "--max-plans",
        type=int,
        default=3,
        help="Number of plans to generate (default: 3).",
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


def keyword_lemmas(keywords: List[str]) -> List[Dict[str, str]]:
    if not keywords:
        keywords = ["statement"]
    lemmas = []
    for key in keywords[:2]:
        lemmas.append(
            {
                "statement": f"Identify a known lemma or bound involving {key}.",
                "why_needed": "Provides a reusable structural component.",
                "likely_sources": ["Mathlib", "literature candidates"],
                "checkability": "medium",
            }
        )
    return lemmas


def plan_templates(keywords: List[str]) -> List[Dict[str, Any]]:
    lemmas = keyword_lemmas(keywords)
    return [
        {
            "strategy_name": "Literature-first mapping",
            "high_level_idea": (
                "Map the statement to known results; attempt to reduce the problem "
                "to a cited lemma or standard theorem."
            ),
            "key_lemmas": lemmas,
            "definitions_needed": ["Restate statement with explicit quantifiers."],
            "risk_factors": ["May rely on unavailable or misquoted references."],
            "experiments": ["Check small cases to detect counterexamples."],
            "formalization_path": ["Locate existing Mathlib results."],
            "expected_payoff": 0.45,
            "difficulty": 0.35,
            "dependency_graph": ["Lemma A -> Main theorem"],
        },
        {
            "strategy_name": "Small-case exploration",
            "high_level_idea": (
                "Search small values or finite configurations to find patterns or "
                "candidate extremals."
            ),
            "key_lemmas": [
                {
                    "statement": "Classify minimal counterexamples up to small size.",
                    "why_needed": "Guides conjectures and identifies invariants.",
                    "likely_sources": ["compute/ experiments"],
                    "checkability": "easy",
                }
            ],
            "definitions_needed": ["Explicit parameter ranges for experiments."],
            "risk_factors": ["Patterns may not generalize."],
            "experiments": ["Enumerate n up to a small bound."],
            "formalization_path": ["Translate patterns into inductive steps."],
            "expected_payoff": 0.35,
            "difficulty": 0.4,
            "dependency_graph": ["Experiment result -> conjecture -> proof outline"],
        },
        {
            "strategy_name": "Formalization-first",
            "high_level_idea": (
                "Formalize the statement and near-trivial lemmas in Lean to expose "
                "missing definitions and constraints."
            ),
            "key_lemmas": [
                {
                    "statement": "Prove base cases and sanity checks in Lean.",
                    "why_needed": "Validates definitions and boundary conditions.",
                    "likely_sources": ["Mathlib"],
                    "checkability": "easy",
                }
            ],
            "definitions_needed": ["Lean-friendly statement with parameters."],
            "risk_factors": ["May not reveal deep structure."],
            "experiments": ["None (formalization focused)."],
            "formalization_path": ["Create skeleton theorem in Lean."],
            "expected_payoff": 0.3,
            "difficulty": 0.25,
            "dependency_graph": ["Lean skeleton -> lemma library -> main proof"],
        },
    ]


def write_autoplan(
    *,
    problem_dir: Path,
    problem_id: str,
    run_dir: Path,
    max_plans: int = 3,
) -> Path:
    statement_path = problem_dir / "statement" / "frozen_v1.md"
    statement_text = (
        statement_path.read_text(encoding="utf-8") if statement_path.exists() else ""
    )
    statement = solver_scaffold.extract_statement(statement_text)
    keywords = literature_scout.extract_keywords(statement, limit=6)

    plans = plan_templates(keywords)[: max(1, max_plans)]
    payload = {
        "problem_id": problem_id,
        "generated_at": now_iso(),
        "solver_used_scout": False,
        "plans": plans,
        "notes": "AUTO-SEED only; replace with human or LLM plans.",
    }

    autoplan_path = run_dir / "planner_autoplan.json"
    autoplan_path.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    summary_lines = [
        "# Auto plan seed",
        "",
        "This file is generated without LLMs. Treat as a placeholder.",
        "",
    ]
    for idx, plan in enumerate(plans, start=1):
        summary_lines.append(f"{idx}. {plan.get('strategy_name', 'Plan')}")
    (run_dir / "planner_autoplan.md").write_text(
        "\n".join(summary_lines).rstrip() + "\n", encoding="utf-8"
    )
    return autoplan_path


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

    autoplan_path = write_autoplan(
        problem_dir=problem_dir,
        problem_id=problem_id,
        run_dir=run_dir,
        max_plans=args.max_plans,
    )

    solver_scaffold.log_event(
        root, f"autoplan seed created for {problem_id} in {run_dir.name}"
    )
    print(f"Auto plan seed written to {autoplan_path.relative_to(root)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
