#!/usr/bin/env python3
"""Ingest manual solver planner output into structured run artifacts."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
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
        description="Ingest manual solver output into a run folder."
    )
    parser.add_argument("problem", help="Problem id (e.g. 379 or P0379).")
    parser.add_argument(
        "--run",
        help="Run id to ingest (default: latest).",
        default="latest",
    )
    parser.add_argument(
        "--file",
        help="Override planner_response.md path (relative to repo root).",
    )
    parser.add_argument(
        "--source",
        help="Override source label stored in plans metadata.",
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


def normalize_plan(
    raw: Dict[str, Any],
    errors: List[str],
    index: int,
    source: str,
) -> Dict[str, Any]:
    plan = dict(raw)
    if not isinstance(plan.get("strategy_name"), str):
        errors.append(f"plan[{index}] missing strategy_name")
        plan["strategy_name"] = f"Plan {index + 1}"
    if not isinstance(plan.get("high_level_idea"), str):
        errors.append(f"plan[{index}] missing high_level_idea")
        plan["high_level_idea"] = ""
    if not isinstance(plan.get("key_lemmas"), list):
        plan["key_lemmas"] = []
    if not isinstance(plan.get("definitions_needed"), list):
        plan["definitions_needed"] = []
    if not isinstance(plan.get("risk_factors"), list):
        plan["risk_factors"] = []
    if not isinstance(plan.get("experiments"), list):
        plan["experiments"] = []
    if not isinstance(plan.get("formalization_path"), list):
        plan["formalization_path"] = []
    if not isinstance(plan.get("dependency_graph"), list):
        plan["dependency_graph"] = []
    payoff = plan.get("expected_payoff")
    difficulty = plan.get("difficulty")
    if not isinstance(payoff, (int, float)):
        errors.append(f"plan[{index}] missing expected_payoff")
        payoff = 0.5
    if not isinstance(difficulty, (int, float)):
        errors.append(f"plan[{index}] missing difficulty")
        difficulty = 0.5
    payoff = max(0.0, min(1.0, float(payoff)))
    difficulty = max(0.0, min(1.0, float(difficulty)))
    plan["expected_payoff"] = payoff
    plan["difficulty"] = difficulty
    plan["status"] = "NEEDS_REVIEW"
    plan["source"] = source
    plan["ingested_at"] = now_iso()
    return plan


def plan_score(plan: Dict[str, Any]) -> float:
    payoff = plan.get("expected_payoff", 0.5)
    difficulty = plan.get("difficulty", 0.5)
    return float(payoff) - 0.5 * float(difficulty)


def write_plan_files(plans_dir: Path, plans: List[Dict[str, Any]]) -> None:
    for idx, plan in enumerate(plans, start=1):
        path = plans_dir / f"plan_{idx:03d}.json"
        path.write_text(
            json.dumps(plan, indent=2, sort_keys=False) + "\n", encoding="utf-8"
        )


def write_best(problem_dir: Path, best_plan: Dict[str, Any], score: float) -> None:
    best_dir = problem_dir / "solver" / "best"
    best_dir.mkdir(parents=True, exist_ok=True)
    plan_path = best_dir / "plan.json"
    plan_payload = dict(best_plan)
    plan_payload["score"] = score
    plan_path.write_text(
        json.dumps(plan_payload, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )

    summary_path = best_dir / "summary.md"
    summary = [
        "# Solver Summary",
        "",
        f"Selected plan: {best_plan.get('strategy_name', 'unknown')}",
        f"Score: {score:.3f}",
        "",
        "High-level idea:",
        best_plan.get("high_level_idea", ""),
        "",
        "Status: UNVERIFIED (manual review required).",
    ]
    summary_path.write_text("\n".join(summary).rstrip() + "\n", encoding="utf-8")

    next_actions_path = best_dir / "next_actions.md"
    experiments = best_plan.get("experiments", [])
    lines = ["# Next Actions", "", "Suggested experiments:"]
    if experiments:
        for item in experiments:
            lines.append(f"- {literature_scout.ascii_safe(str(item))}")
    else:
        lines.append("- TODO: define experiments.")
    next_actions_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


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

    run_dir = None
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
        print(f"ERROR: missing planner response at {response_path}")
        return 1

    response_text = response_path.read_text(encoding="utf-8")
    payload = extract_json(response_text)
    if payload is None:
        print("ERROR: could not parse JSON from planner_response.md.")
        return 1

    plans_raw = payload.get("plans")
    if not isinstance(plans_raw, list) or not plans_raw:
        print("ERROR: response JSON missing plans list.")
        return 1

    source = args.source
    if not source:
        if response_path.name == "planner_response.md":
            source = "internal reference_pro_manual"
        else:
            source = "manual_llm"

    errors: List[str] = []
    plans: List[Dict[str, Any]] = []
    for idx, raw in enumerate(plans_raw):
        if not isinstance(raw, dict):
            errors.append(f"plan[{idx}] is not an object")
            continue
        plans.append(normalize_plan(raw, errors, idx, source))

    plans.sort(key=plan_score, reverse=True)
    if run_dir is None:
        run_dir = response_path.parent
    plans_dir = run_dir / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    write_plan_files(plans_dir, plans)

    best_plan = plans[0]
    score = plan_score(best_plan)
    write_best(problem_dir, best_plan, score)

    notes_path = run_dir / "notes.md"
    if errors:
        notes = notes_path.read_text(encoding="utf-8") if notes_path.exists() else ""
        notes += "\n## Ingest warnings\n"
        for err in errors:
            notes += f"- {err}\n"
        notes_path.write_text(notes.strip() + "\n", encoding="utf-8")

    try:
        rel_run = run_dir.relative_to(root)
    except ValueError:
        rel_run = run_dir
    print(f"Ingested {len(plans)} plans into {rel_run}.")
    if errors:
        print("Warnings:")
        for err in errors:
            print(f"  - {err}")
    solver_scaffold.log_event(
        root,
        f"ingested {len(plans)} plans for {problem_id} into {run_dir.name}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
