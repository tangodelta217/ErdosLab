#!/usr/bin/env python3
"""Run reproducible experiments listed in problems/<ID>/compute/manifest.json."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import solver_scaffold


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run problem experiments.")
    parser.add_argument("problem", help="Problem id (e.g. 379 or P0379).")
    parser.add_argument(
        "--manifest",
        help="Override manifest path (relative to repo root).",
    )
    parser.add_argument(
        "--run-id",
        help="Override result run id (default: timestamp).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any experiment exits non-zero.",
    )
    parser.add_argument(
        "--only",
        help="Run a single experiment by name.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing.",
    )
    return parser.parse_args()


def load_manifest(path: Path) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    if not path.exists():
        return [], f"manifest not found: {path}"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [], f"invalid JSON: {exc}"
    experiments = payload.get("experiments")
    if not isinstance(experiments, list):
        return [], "manifest missing experiments list"
    return experiments, None


def normalize_command(command: Any) -> Optional[List[str]]:
    if isinstance(command, list) and all(isinstance(item, str) for item in command):
        return command
    if isinstance(command, str):
        return shlex.split(command)
    return None


def safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in name)


def log_event(root: Path, message: str) -> None:
    logs_dir = root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "experimenter.log"
    timestamp = now_iso()
    with log_path.open("a", encoding="utf-8", errors="ignore") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def run_experiment(
    *,
    root: Path,
    exp: Dict[str, Any],
    output_dir: Path,
    dry_run: bool,
) -> Tuple[bool, Dict[str, Any]]:
    name = str(exp.get("name") or "experiment")
    command = normalize_command(exp.get("command"))
    timeout = exp.get("timeout_sec")
    if command is None:
        return False, {
            "name": name,
            "status": "invalid",
            "error": "command must be a list or string",
        }

    metadata: Dict[str, Any] = {
        "name": name,
        "command": command,
        "status": "pending",
        "started_at": now_iso(),
    }
    exp_dir = output_dir / safe_name(name)
    exp_dir.mkdir(parents=True, exist_ok=True)

    if dry_run:
        metadata["status"] = "dry-run"
        metadata["exit_code"] = None
        metadata["finished_at"] = now_iso()
        (exp_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=False) + "\n", encoding="utf-8"
        )
        return True, metadata

    try:
        result = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout if isinstance(timeout, (int, float)) else None,
            check=False,
            env={**os.environ, **(exp.get("env") or {})},
        )
    except subprocess.TimeoutExpired:
        metadata["status"] = "timeout"
        metadata["exit_code"] = None
        metadata["finished_at"] = now_iso()
        (exp_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=False) + "\n", encoding="utf-8"
        )
        return False, metadata

    (exp_dir / "stdout.log").write_text(result.stdout or "", encoding="utf-8")
    (exp_dir / "stderr.log").write_text(result.stderr or "", encoding="utf-8")
    metadata["exit_code"] = result.returncode
    metadata["status"] = "ok" if result.returncode == 0 else "error"
    metadata["finished_at"] = now_iso()
    (exp_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    return result.returncode == 0, metadata


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

    if args.manifest:
        manifest_path = Path(args.manifest)
        if not manifest_path.is_absolute():
            manifest_path = root / manifest_path
    else:
        manifest_path = problem_dir / "compute" / "manifest.json"

    experiments, err = load_manifest(manifest_path)
    if err:
        print(f"ERROR: {err}")
        return 1

    if args.only:
        experiments = [
            exp for exp in experiments if exp.get("name") == args.only
        ]

    if not experiments:
        print("No experiments to run.")
        return 0

    run_id = args.run_id or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = problem_dir / "compute" / "results" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.json").write_text(
        json.dumps({"experiments": experiments}, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    failures = 0
    summary_lines = [
        "# Experiment Summary",
        "",
        f"- problem_id: {problem_id}",
        f"- run_id: {run_id}",
        f"- generated_at: {now_iso()}",
        "",
    ]
    for exp in experiments:
        ok, metadata = run_experiment(
            root=root, exp=exp, output_dir=output_dir, dry_run=args.dry_run
        )
        status = metadata.get("status")
        summary_lines.append(f"- {metadata.get('name')}: {status}")
        if not ok:
            failures += 1

    (output_dir / "summary.md").write_text(
        "\n".join(summary_lines).rstrip() + "\n", encoding="utf-8"
    )

    log_event(root, f"ran {len(experiments)} experiments for {problem_id} ({run_id})")
    if failures and args.strict:
        print(f"ERROR: {failures} experiment(s) failed.")
        return 1
    print(f"Results written to {output_dir.relative_to(root)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
