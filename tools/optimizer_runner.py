#!/usr/bin/env python3
"""Run a lightweight optimization loop over a scoring command."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import solver_scaffold


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a scoring loop.")
    parser.add_argument("problem", help="Problem id (e.g. 379 or P0379).")
    parser.add_argument(
        "--config",
        help="Override optimizer config (relative to repo root).",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        help="Override number of iterations.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        help="Override top-k results stored.",
    )
    parser.add_argument(
        "--objective",
        choices=["maximize", "minimize"],
        help="Override objective (default from config).",
    )
    parser.add_argument(
        "--run-id",
        help="Override run id (default: timestamp).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing.",
    )
    return parser.parse_args()


def load_config(path: Path) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    if not path.exists():
        return None, f"config not found: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"invalid JSON: {exc}"
    if not isinstance(payload, dict):
        return None, "config must be a JSON object"
    return payload, None


def resolve_command(command: Any, seed: int) -> Optional[List[str]]:
    if isinstance(command, list) and all(isinstance(item, str) for item in command):
        return [item.replace("{seed}", str(seed)) for item in command]
    if isinstance(command, str):
        return [command.replace("{seed}", str(seed))]
    return None


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    blob = match.group(0)
    try:
        data = json.loads(blob)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def log_event(root: Path, message: str) -> None:
    logs_dir = root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "optimizer.log"
    timestamp = now_iso()
    with log_path.open("a", encoding="utf-8", errors="ignore") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def run_single(
    root: Path,
    command: List[str],
    seed: int,
    env: Dict[str, str],
    run_dir: Path,
    dry_run: bool,
) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {
        "seed": seed,
        "command": command,
        "started_at": now_iso(),
        "status": "pending",
    }
    seed_dir = run_dir / f"seed_{seed:04d}"
    seed_dir.mkdir(parents=True, exist_ok=True)

    if dry_run:
        metadata["status"] = "dry-run"
        metadata["finished_at"] = now_iso()
        (seed_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=False) + "\n", encoding="utf-8"
        )
        return metadata

    result = subprocess.run(
        command,
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **env, "RUN_SEED": str(seed)},
    )
    (seed_dir / "stdout.log").write_text(result.stdout or "", encoding="utf-8")
    (seed_dir / "stderr.log").write_text(result.stderr or "", encoding="utf-8")

    payload = extract_json(result.stdout or "")
    score = None
    valid = False
    if payload and isinstance(payload.get("score"), (int, float)):
        score = float(payload["score"])
        valid = bool(payload.get("valid", True))

    metadata["exit_code"] = result.returncode
    metadata["score"] = score
    metadata["valid"] = valid
    metadata["candidate"] = payload.get("candidate") if payload else None
    metadata["status"] = "ok" if result.returncode == 0 else "error"
    metadata["finished_at"] = now_iso()
    (seed_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    return metadata


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

    config_path = (
        Path(args.config)
        if args.config
        else problem_dir / "compute" / "optimizer.json"
    )
    if not config_path.is_absolute():
        config_path = root / config_path

    config, err = load_config(config_path)
    if err:
        print(f"ERROR: {err}")
        return 1

    command = config.get("command")
    if command is None:
        print("ERROR: optimizer config missing command")
        return 1

    iterations = args.iterations or int(config.get("iterations", 10))
    top_k = args.top_k or int(config.get("top_k", 5))
    objective = args.objective or str(config.get("objective", "maximize"))
    seed_start = int(config.get("seed_start", 1))
    env = config.get("env") if isinstance(config.get("env"), dict) else {}

    run_id = args.run_id or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = problem_dir / "compute" / "results" / run_id / "optimizer"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.json").write_text(
        json.dumps(config, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )

    results: List[Dict[str, Any]] = []
    for idx in range(iterations):
        seed = seed_start + idx
        resolved = resolve_command(command, seed)
        if resolved is None:
            print("ERROR: command must be list or string")
            return 1
        metadata = run_single(
            root=root,
            command=resolved,
            seed=seed,
            env={k: str(v) for k, v in env.items()},
            run_dir=run_dir,
            dry_run=args.dry_run,
        )
        results.append(metadata)

    valid_results = [
        item for item in results if item.get("valid") and item.get("score") is not None
    ]
    reverse = objective != "minimize"
    ranked = sorted(valid_results, key=lambda x: x["score"], reverse=reverse)
    top = ranked[:top_k]

    summary = {
        "problem_id": problem_id,
        "run_id": run_id,
        "objective": objective,
        "iterations": iterations,
        "top_k": top_k,
        "generated_at": now_iso(),
        "top_results": top,
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )

    summary_lines = [
        "# Optimizer Summary",
        "",
        f"- objective: {objective}",
        f"- iterations: {iterations}",
        f"- top_k: {top_k}",
        f"- generated_at: {summary['generated_at']}",
        "",
        "Top results:",
    ]
    if top:
        for item in top:
            summary_lines.append(
                f"- seed {item.get('seed')}: score {item.get('score')}"
            )
    else:
        summary_lines.append("- (no valid results)")
    (run_dir / "summary.md").write_text(
        "\n".join(summary_lines).rstrip() + "\n", encoding="utf-8"
    )

    log_event(root, f"optimizer run {run_id} for {problem_id} ({iterations} iters)")
    print(f"Results written to {run_dir.relative_to(root)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
