#!/usr/bin/env python3
"""Ingest manual literature output into candidates files."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import literature_scout

ALLOWED_ID_TYPES = {"doi", "arxiv", "zbmath", "openalex"}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest manual literature output."
    )
    parser.add_argument("problem", help="Problem id (e.g. 379 or P0379).")
    parser.add_argument(
        "--response",
        help="Path to internal reference_response.md (defaults to problems/<ID>/literature/internal reference_response.md).",
    )
    parser.add_argument(
        "--source",
        help="Override provenance label (default: internal reference_pro_manual or manual_llm).",
    )
    return parser.parse_args()


def normalize_problem_id(raw: str) -> str:
    match = re.fullmatch(r"[Pp]?(\d+)", raw.strip())
    if not match:
        raise ValueError(f"Invalid problem id: {raw!r}")
    number_str = match.group(1)
    number = int(number_str)
    width = max(4, len(number_str))
    return f"P{number:0{width}d}"


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    match = re.search(r"```json(.*?)```", text, re.S | re.I)
    if not match:
        match = re.search(r"```(.*?)```", text, re.S)
    if match:
        blob = match.group(1)
    else:
        blob = text
    try:
        data = json.loads(blob)
    except Exception:
        return None
    if isinstance(data, dict):
        return data
    return None


def normalize_id(id_type: str, value: str) -> Optional[str]:
    value = value.strip()
    if not value:
        return None
    if id_type == "doi":
        return literature_scout.doi_to_id(value)
    if id_type == "arxiv":
        if re.search(r"\d", value):
            return value
        return None
    if id_type == "zbmath":
        return value if value.isdigit() else None
    if id_type == "openalex":
        return value
    return None


def normalize_url(id_type: str, value: str, url: Optional[str]) -> Optional[str]:
    if url and isinstance(url, str):
        return url.strip()
    if id_type == "doi":
        return f"https://doi.org/{value}"
    if id_type == "arxiv":
        return f"https://arxiv.org/abs/{value}"
    if id_type == "zbmath":
        return f"https://zbmath.org/{value}"
    if id_type == "openalex":
        if value.startswith("http"):
            return value
        return f"https://openalex.org/{value}"
    return None


def normalize_candidate(
    raw: Dict[str, Any],
    errors: List[str],
    source: str,
) -> Optional[Dict[str, Any]]:
    id_type = raw.get("id_type")
    if not isinstance(id_type, str) or id_type not in ALLOWED_ID_TYPES:
        errors.append(f"candidate missing/invalid id_type: {raw.get('id_type')}")
        return None
    raw_id = raw.get("id")
    if not isinstance(raw_id, str):
        errors.append("candidate missing id")
        return None
    normalized_id = normalize_id(id_type, raw_id)
    if not normalized_id:
        errors.append(f"candidate invalid id for type {id_type}: {raw_id}")
        return None
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append(f"candidate {normalized_id} missing title")
        return None
    reasons = raw.get("reasons")
    if not isinstance(reasons, list) or not reasons:
        errors.append(f"candidate {normalized_id} missing reasons")
        return None
    confidence = raw.get("confidence")
    if not isinstance(confidence, (int, float)):
        errors.append(f"candidate {normalized_id} missing confidence")
        return None
    authors_raw = raw.get("authors") if isinstance(raw.get("authors"), list) else []
    authors = [
        literature_scout.ascii_safe(str(author))
        for author in authors_raw
        if isinstance(author, str)
    ]
    year = raw.get("year")
    year_str = str(year) if isinstance(year, (int, str)) else None
    url = normalize_url(id_type, normalized_id, raw.get("url"))
    reasons_safe = [literature_scout.ascii_safe(str(reason)) for reason in reasons]
    candidate = {
        "id": normalized_id,
        "id_type": id_type,
        "title": literature_scout.ascii_safe(title),
        "authors": authors,
        "year": year_str,
        "url": url,
        "confidence": float(confidence),
        "reasons": reasons_safe,
        "status": "NEEDS_REVIEW",
        "provenance": [
            {
                "provider": source,
                "query": "manual",
                "source_url": f"manual:{source}",
                "fetched_at": now_iso(),
                "cache_hit": False,
            }
        ],
    }
    return candidate


def load_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parent.parent
    try:
        problem_id = normalize_problem_id(args.problem)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 2

    literature_dir = root / "problems" / problem_id / "literature"
    response_path = (
        Path(args.response)
        if args.response
        else (literature_dir / "internal reference_response.md")
    )
    if not response_path.exists():
        print(f"ERROR: response file not found: {response_path}")
        return 1

    response_text = response_path.read_text(encoding="utf-8")
    payload = extract_json(response_text)
    if payload is None:
        print("ERROR: could not parse JSON from response.")
        return 1

    manual_candidates_raw = payload.get("candidates")
    if not isinstance(manual_candidates_raw, list):
        print("ERROR: response JSON missing candidates list.")
        return 1

    source = args.source
    if not source:
        if response_path.name == "internal reference_response.md":
            source = "internal reference_pro_manual"
        else:
            source = "manual_llm"

    errors: List[str] = []
    manual_candidates: List[Dict[str, Any]] = []
    for raw in manual_candidates_raw:
        if not isinstance(raw, dict):
            errors.append("candidate entry is not an object")
            continue
        candidate = normalize_candidate(raw, errors, source)
        if candidate:
            manual_candidates.append(candidate)

    response_sha = hashlib.sha256(response_text.encode("utf-8")).hexdigest()
    prompt_path = literature_dir / "internal reference_prompt.md"
    prompt_sha = None
    if prompt_path.exists():
        prompt_sha = hashlib.sha256(
            prompt_path.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()

    candidates_path = literature_dir / "candidates.json"
    queries_path = literature_dir / "queries.json"
    existing = load_json(candidates_path) or {}
    existing_candidates = existing.get("candidates") if isinstance(existing.get("candidates"), list) else []
    existing_queries = []
    queries_payload = load_json(queries_path)
    if isinstance(queries_payload, dict) and isinstance(queries_payload.get("queries"), list):
        existing_queries = queries_payload["queries"]
    existing_errors = existing.get("errors") if isinstance(existing.get("errors"), list) else []

    manual_query = {
        "provider": "internal reference_pro_manual",
        "query": "manual",
        "url": None,
        "cache_hit": False,
        "status": "ok",
        "error": None,
        "timestamp": now_iso(),
        "prompt_sha256": prompt_sha,
        "response_sha256": response_sha,
    }
    manual_query_notes = payload.get("queries")
    if isinstance(manual_query_notes, list):
        manual_query["queries"] = manual_query_notes
    merged_queries = existing_queries + [manual_query]

    merged_candidates = literature_scout.dedupe_candidates(
        existing_candidates + manual_candidates
    )
    merged_candidates.sort(
        key=lambda cand: (-cand.get("confidence", 0.0), cand.get("year") or "")
    )
    merged_candidates = merged_candidates[: literature_scout.DEFAULT_MAX_CANDIDATES]

    combined_errors = existing_errors + payload.get("errors", []) if isinstance(payload.get("errors"), list) else existing_errors
    combined_errors.extend(errors)
    solver_used = bool(existing.get("solver_used_scout"))
    if isinstance(payload.get("solver_used_scout"), bool):
        solver_used = solver_used or payload["solver_used_scout"]

    generated_at = now_iso()
    literature_scout.write_candidates_json(
        candidates_path,
        problem_id,
        generated_at,
        offline=False,
        candidates=merged_candidates,
        queries=merged_queries,
        errors=combined_errors,
        solver_used_scout=solver_used,
    )
    literature_scout.write_candidates_md(
        literature_dir / "candidates.md",
        merged_candidates,
        generated_at,
        offline=False,
        errors=combined_errors,
    )
    literature_scout.write_queries_json(queries_path, merged_queries, generated_at)
    literature_scout.write_triage_md(
        literature_dir / "triage.md", merged_candidates, generated_at
    )

    print(f"Ingested {len(manual_candidates)} manual candidates into {problem_id}.")
    if errors:
        print("Warnings:")
        for err in errors:
            print(f"  - {err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
