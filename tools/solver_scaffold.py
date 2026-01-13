#!/usr/bin/env python3
"""Create solver scaffolding and prompts for manual research loops."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import literature_scout
import llm_utils

DEFAULT_MAX_PLANS = int(os.getenv("SOLVER_MAX_PLANS", "8"))
DEFAULT_MAX_LITERATURE = int(os.getenv("SOLVER_MAX_LITERATURE", "8"))
PLACEHOLDER_RESPONSE = "# Paste ChatGPT Pro output below\n\n"
PLACEHOLDER_NOTES = "# Notes\n\n"


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def run_id_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_problem_id(raw: str) -> Tuple[str, int]:
    match = re.fullmatch(r"[Pp]?(\d+)", raw.strip())
    if not match:
        raise ValueError(f"Invalid problem id: {raw!r}")
    number_str = match.group(1)
    number = int(number_str)
    width = max(4, len(number_str))
    return f"P{number:0{width}d}", number


def extract_statement(frozen_text: str) -> str:
    marker = "## Statement"
    if marker not in frozen_text:
        return frozen_text.strip()
    _, tail = frozen_text.split(marker, 1)
    tail = tail.strip()
    if "## " in tail:
        statement, _ = tail.split("## ", 1)
        return statement.strip()
    return tail.strip()


def read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def log_event(root: Path, message: str) -> None:
    logs_dir = root / "logs"
    ensure_dir(logs_dir)
    log_path = logs_dir / "solver.log"
    timestamp = now_iso()
    with log_path.open("a", encoding="utf-8", errors="ignore") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def planner_prompt(
    *,
    problem_id: str,
    problem_number: int,
    title: Optional[str],
    problem_url: str,
    forum_url: str,
    statement_text: str,
) -> str:
    title_line = title or f"Erdos Problem #{problem_number}"
    keywords = literature_scout.extract_keywords(statement_text, limit=10)
    keyword_line = ", ".join(keywords) if keywords else "none"
    return (
        "# Solver Planner Prompt (manual)\n"
        "\nVersion: v1\n"
        "\nYou are generating structured research plans for an Erdos problem. "
        "Do NOT claim the problem is solved. Do NOT mark anything as verified. "
        "Output only plans and experiments that could lead to a proof.\n"
        "\nProblem context:\n"
        f"- problem_id: {problem_id}\n"
        f"- title: {title_line}\n"
        f"- problem_url: {problem_url}\n"
        f"- forum_url: {forum_url}\n"
        f"- keywords: {keyword_line}\n"
        "\nFrozen statement:\n"
        f"{statement_text}\n"
        "\nIf you used literature candidates from candidates.json, set solver_used_scout=true. "
        "Otherwise keep solver_used_scout=false.\n"
        "\nOutput format (STRICT): return exactly one JSON object in a single ```json``` block. "
        "Do not include extra prose outside the JSON.\n"
        "\nRequired JSON schema:\n"
        "{\n"
        f'  \"problem_id\": \"{problem_id}\",\n'
        "  \"generated_at\": \"YYYY-MM-DD\",\n"
        "  \"solver_used_scout\": false,\n"
        "  \"plans\": [\n"
        "    {\n"
        "      \"strategy_name\": \"...\",\n"
        "      \"high_level_idea\": \"...\",\n"
        "      \"key_lemmas\": [\n"
        "        {\n"
        "          \"statement\": \"...\",\n"
        "          \"why_needed\": \"...\",\n"
        "          \"likely_sources\": [\"...\"],\n"
        "          \"checkability\": \"easy | medium | hard\"\n"
        "        }\n"
        "      ],\n"
        "      \"definitions_needed\": [\"...\"],\n"
        "      \"risk_factors\": [\"...\"],\n"
        "      \"experiments\": [\"...\"],\n"
        "      \"formalization_path\": [\"...\"],\n"
        "      \"expected_payoff\": 0.0,\n"
        "      \"difficulty\": 0.0,\n"
        "      \"dependency_graph\": [\"lemma1 -> lemma2\", \"lemma2 -> theorem\"]\n"
        "    }\n"
        "  ],\n"
        "  \"notes\": \"... optional ...\"\n"
        "}\n"
        "\nRules:\n"
        f"- Provide 3 to {DEFAULT_MAX_PLANS} plans.\n"
        "- expected_payoff and difficulty must be numbers in [0,1].\n"
        "- Do not assert correctness; everything is speculative.\n"
    )


def render_literature_candidates(
    problem_dir: Path, max_items: int = DEFAULT_MAX_LITERATURE
) -> str:
    candidates_path = problem_dir / "literature" / "candidates.json"
    if not candidates_path.exists():
        return "- none (missing candidates.json)"
    try:
        payload = json.loads(candidates_path.read_text(encoding="utf-8"))
    except Exception:
        return "- none (invalid candidates.json)"
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return "- none (no candidates listed)"

    lines: List[str] = []
    for idx, candidate in enumerate(candidates[:max_items], start=1):
        if not isinstance(candidate, dict):
            continue
        title = literature_scout.ascii_safe(str(candidate.get("title", ""))).strip()
        title = title or "untitled"
        year = literature_scout.ascii_safe(str(candidate.get("year", ""))).strip()
        year = year or "n.d."
        authors_raw = candidate.get("authors")
        if isinstance(authors_raw, list):
            authors = [
                literature_scout.ascii_safe(str(author)).strip()
                for author in authors_raw
                if str(author).strip()
            ]
        else:
            authors = []
        authors_text = ", ".join(authors) if authors else "unknown authors"
        id_value = literature_scout.ascii_safe(str(candidate.get("id", ""))).strip()
        id_value = id_value or "unknown id"
        id_type = literature_scout.ascii_safe(
            str(candidate.get("id_type", "id"))
        ).strip()
        id_type = id_type or "id"
        url = literature_scout.ascii_safe(str(candidate.get("url", ""))).strip()
        confidence = candidate.get("confidence")
        if isinstance(confidence, (int, float)):
            confidence_text = f"{confidence:.2f}"
        else:
            confidence_text = "n/a"
        status = literature_scout.ascii_safe(
            str(candidate.get("status", "UNKNOWN"))
        ).strip()
        reasons_raw = candidate.get("reasons")
        reasons: List[str] = []
        if isinstance(reasons_raw, list):
            for reason in reasons_raw:
                reason_text = literature_scout.ascii_safe(str(reason)).strip()
                if reason_text:
                    reasons.append(reason_text)
        reasons_text = "; ".join(reasons[:3]) if reasons else ""

        line = (
            f"- [{idx}] {title} ({year}), {authors_text}. "
            f"{id_type}: {id_value}. confidence: {confidence_text}. "
            f"status: {status}."
        )
        if url:
            line += f" url: {url}."
        if reasons_text:
            line += f" reasons: {reasons_text}."
        lines.append(line)

    return "\n".join(lines) if lines else "- none (no usable candidates)"


def default_checklist() -> str:
    return (
        "# Verification Checklist\n"
        "\n- [ ] Statement matches frozen_v1.\n"
        "- [ ] No unverified claims labeled as solved.\n"
        "- [ ] Experiments are reproducible.\n"
        "- [ ] Lean attempts compile or are clearly marked as WIP.\n"
    )


def load_status(problem_dir: Path) -> Dict[str, Any]:
    status_path = problem_dir / "status.json"
    try:
        return json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def run_used(run_dir: Path) -> bool:
    response_path = run_dir / "planner_response.md"
    if response_path.exists():
        content = response_path.read_text(encoding="utf-8").strip()
        if content and not content.startswith("# Paste ChatGPT Pro output below"):
            return True
    plans_dir = run_dir / "plans"
    if plans_dir.is_dir() and any(plans_dir.glob("*.json")):
        return True
    return False


def resolve_latest_run(runs_dir: Path) -> Optional[str]:
    latest_path = runs_dir / "latest.json"
    if not latest_path.exists():
        return None
    try:
        payload = json.loads(latest_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    run_id = payload.get("run_id")
    return run_id if isinstance(run_id, str) else None


def write_latest(runs_dir: Path, run_id: str) -> None:
    payload = {"run_id": run_id, "updated_at": now_iso()}
    (runs_dir / "latest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )


def ensure_best_dir(problem_dir: Path) -> None:
    best_dir = problem_dir / "solver" / "best"
    ensure_dir(best_dir)
    plan_path = best_dir / "plan.json"
    if not plan_path.exists():
        plan_path.write_text(
            json.dumps({"status": "empty"}, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
    summary_path = best_dir / "summary.md"
    if not summary_path.exists():
        summary_path.write_text(
            "# Solver Summary\n\nNo verified plan yet.\n", encoding="utf-8"
        )
    next_actions_path = best_dir / "next_actions.md"
    if not next_actions_path.exists():
        next_actions_path.write_text(
            "# Next Actions\n\n- TODO: select a plan.\n", encoding="utf-8"
        )


def build_input_bundle(
    *,
    problem_id: str,
    title: Optional[str],
    statement_text: str,
    problem_url: str,
    forum_url: str,
    problem_dir: Path,
) -> Dict[str, Any]:
    status = load_status(problem_dir)
    keywords = literature_scout.extract_keywords(statement_text, limit=10)
    literature_path = problem_dir / "literature" / "candidates.json"
    return {
        "problem_id": problem_id,
        "title": title,
        "generated_at": now_iso(),
        "problem_url": problem_url,
        "forum_url": forum_url,
        "statement_text": statement_text,
        "keywords": keywords,
        "literature_candidates_path": str(literature_path),
        "claim_state": status.get("claim", {}).get("state"),
        "evidence": status.get("evidence", []),
        "notes": "Do not treat candidates as verified.",
    }


def ensure_run(
    *,
    problem_dir: Path,
    force_new_run: bool,
) -> Path:
    root = problem_dir.parent.parent
    runs_dir = problem_dir / "solver" / "runs"
    ensure_dir(runs_dir)
    run_id = None
    latest_id = resolve_latest_run(runs_dir)
    if latest_id and not force_new_run:
        candidate = runs_dir / latest_id
        if candidate.is_dir() and not run_used(candidate):
            log_event(root, f"reuse run {latest_id} for {problem_dir.name}")
            return candidate
        run_id = None
    if run_id is None:
        run_id = run_id_now()
    run_dir = runs_dir / run_id
    ensure_dir(run_dir)
    ensure_dir(run_dir / "plans")
    ensure_dir(run_dir / "experiments")
    ensure_dir(run_dir / "lean")
    verification_dir = run_dir / "verification"
    ensure_dir(verification_dir)
    response_path = run_dir / "planner_response.md"
    if not response_path.exists():
        response_path.write_text(PLACEHOLDER_RESPONSE, encoding="utf-8")
    notes_path = run_dir / "notes.md"
    if not notes_path.exists():
        notes_path.write_text(PLACEHOLDER_NOTES, encoding="utf-8")
    checklist_path = verification_dir / "checklist.md"
    if not checklist_path.exists():
        checklist_path.write_text(default_checklist(), encoding="utf-8")
    write_latest(runs_dir, run_id)
    log_event(root, f"created run {run_id} for {problem_dir.name}")
    return run_dir


def run_scaffold(
    *,
    problem_dir: Path,
    problem_id: str,
    problem_number: int,
    title: Optional[str],
    statement_text: Optional[str],
    problem_url: str,
    forum_url: str,
    force_new_run: bool = False,
) -> Path:
    ensure_dir(problem_dir / "solver")
    ensure_best_dir(problem_dir)
    run_dir = ensure_run(problem_dir=problem_dir, force_new_run=force_new_run)

    frozen_path = problem_dir / "statement" / "frozen_v1.md"
    if statement_text is None:
        frozen_text = read_text(frozen_path) or ""
        statement_text = extract_statement(frozen_text)

    input_bundle = build_input_bundle(
        problem_id=problem_id,
        title=title,
        statement_text=statement_text,
        problem_url=problem_url,
        forum_url=forum_url,
        problem_dir=problem_dir,
    )
    (run_dir / "input_bundle.json").write_text(
        json.dumps(input_bundle, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    prompt = planner_prompt(
        problem_id=problem_id,
        problem_number=problem_number,
        title=title,
        problem_url=problem_url,
        forum_url=forum_url,
        statement_text=statement_text,
    )
    (run_dir / "planner_prompt.md").write_text(
        prompt.rstrip() + "\n", encoding="utf-8"
    )
    literature_block = render_literature_candidates(problem_dir)
    prompt_with_lit = (
        prompt.rstrip()
        + "\n\nLiterature candidates (UNVERIFIED):\n"
        + literature_block
        + "\n"
    )
    (run_dir / "planner_prompt_with_literature.md").write_text(
        prompt_with_lit, encoding="utf-8"
    )
    llm_utils.write_model_prompts(
        run_dir / "llm" / "planner",
        prompt_with_lit,
        response_extension=".md",
        placeholder=PLACEHOLDER_RESPONSE,
    )
    return run_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create solver scaffolding for manual research loops."
    )
    parser.add_argument("problem", help="Problem id (e.g. 379 or P0379).")
    parser.add_argument("--title", help="Optional problem title.")
    parser.add_argument("--problem-url", help="Override the problem page URL.")
    parser.add_argument("--forum-url", help="Override the forum thread URL.")
    parser.add_argument(
        "--new-run",
        action="store_true",
        help="Force creation of a new run directory.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parent.parent
    try:
        problem_id, number = normalize_problem_id(args.problem)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2
    problem_dir = root / "problems" / problem_id
    if not problem_dir.exists():
        print(f"ERROR: missing problem directory: {problem_dir}")
        return 1

    problem_url = args.problem_url or f"https://www.erdosproblems.com/{number}"
    forum_url = args.forum_url or f"https://www.erdosproblems.com/forum/thread/{number}"
    run_dir = run_scaffold(
        problem_dir=problem_dir,
        problem_id=problem_id,
        problem_number=number,
        title=args.title,
        statement_text=None,
        problem_url=problem_url,
        forum_url=forum_url,
        force_new_run=args.new_run,
    )
    print(f"Solver scaffold ready: {run_dir.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
