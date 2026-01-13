#!/usr/bin/env python3
"""Analyze numeric sequences for simple patterns."""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze numeric sequences for simple patterns."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Input JSON/CSV file with a numeric sequence.",
    )
    parser.add_argument(
        "--format",
        choices=["md", "json"],
        default="md",
        help="Output format (default: md).",
    )
    parser.add_argument(
        "--output",
        help="Write output to file instead of stdout.",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1e-9,
        help="Tolerance for constant checks (default: 1e-9).",
    )
    return parser.parse_args()


def load_json_series(path: Path) -> Tuple[List[Tuple[int, float]], Optional[str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [], f"invalid JSON: {exc}"

    if isinstance(payload, list):
        if all(isinstance(item, (int, float)) for item in payload):
            return [(idx + 1, float(val)) for idx, val in enumerate(payload)], None
        if all(
            isinstance(item, (list, tuple)) and len(item) == 2 for item in payload
        ):
            pairs = []
            for item in payload:
                n, v = item
                if not isinstance(n, (int, float)) or not isinstance(v, (int, float)):
                    return [], "pairs must be numeric"
                pairs.append((int(n), float(v)))
            return pairs, None
        return [], "unsupported JSON list format"

    if isinstance(payload, dict):
        series = payload.get("series") or payload.get("values")
        if isinstance(series, list):
            if series and isinstance(series[0], dict):
                pairs = []
                for entry in series:
                    n = entry.get("n")
                    v = entry.get("value")
                    if not isinstance(n, (int, float)) or not isinstance(v, (int, float)):
                        return [], "series entries must include numeric n/value"
                    pairs.append((int(n), float(v)))
                return pairs, None
            if all(isinstance(item, (int, float)) for item in series):
                return [(idx + 1, float(val)) for idx, val in enumerate(series)], None
        return [], "unsupported JSON object format"

    return [], "unsupported JSON format"


def load_csv_series(path: Path) -> Tuple[List[Tuple[int, float]], Optional[str]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            rows = list(reader)
    except Exception as exc:
        return [], f"invalid CSV: {exc}"

    if not rows:
        return [], "empty CSV"

    header = [col.strip().lower() for col in rows[0]]
    start_idx = 0
    n_idx = None
    v_idx = None
    if "n" in header and "value" in header:
        n_idx = header.index("n")
        v_idx = header.index("value")
        start_idx = 1

    pairs = []
    for row in rows[start_idx:]:
        if not row:
            continue
        if n_idx is not None and v_idx is not None:
            n = row[n_idx]
            v = row[v_idx]
        else:
            if len(row) < 2:
                return [], "CSV rows must have at least two columns"
            n, v = row[0], row[1]
        try:
            pairs.append((int(float(n)), float(v)))
        except ValueError:
            return [], "CSV values must be numeric"
    return pairs, None


def load_series(path: Path) -> Tuple[List[Tuple[int, float]], Optional[str]]:
    if not path.exists():
        return [], f"input not found: {path}"
    if path.suffix.lower() == ".json":
        return load_json_series(path)
    if path.suffix.lower() == ".csv":
        return load_csv_series(path)
    return [], "unsupported file type (use .json or .csv)"


def differences(values: List[float], order: int) -> List[float]:
    result = list(values)
    for _ in range(order):
        result = [b - a for a, b in zip(result, result[1:])]
    return result


def is_constant(seq: List[float], tol: float) -> bool:
    if len(seq) < 2:
        return False
    base = seq[0]
    return all(abs(item - base) <= tol for item in seq[1:])


def ratio_sequence(values: List[float]) -> List[float]:
    ratios = []
    for a, b in zip(values, values[1:]):
        if a == 0:
            return []
        ratios.append(b / a)
    return ratios


def summarize(
    pairs: List[Tuple[int, float]],
    tol: float,
) -> Dict[str, Any]:
    values = [v for _, v in pairs]
    summary: Dict[str, Any] = {
        "count": len(values),
        "min": min(values) if values else None,
        "max": max(values) if values else None,
    }

    diff1 = differences(values, 1)
    diff2 = differences(values, 2)
    diff3 = differences(values, 3)
    summary["diff_constant"] = {
        "order1": is_constant(diff1, tol),
        "order2": is_constant(diff2, tol),
        "order3": is_constant(diff3, tol),
    }
    ratios = ratio_sequence(values)
    summary["ratio_constant"] = is_constant(ratios, tol) if ratios else False

    guess = []
    if summary["diff_constant"]["order1"]:
        guess.append("arithmetic (degree 1)")
    if summary["diff_constant"]["order2"]:
        guess.append("quadratic (degree 2)")
    if summary["diff_constant"]["order3"]:
        guess.append("cubic (degree 3)")
    if summary["ratio_constant"]:
        guess.append("geometric")
    summary["guesses"] = guess
    summary["diff_samples"] = {
        "order1": diff1[:5],
        "order2": diff2[:5],
        "order3": diff3[:5],
    }
    summary["ratio_samples"] = ratios[:5] if ratios else []
    return summary


def render_md(
    pairs: List[Tuple[int, float]],
    summary: Dict[str, Any],
) -> str:
    lines = [
        "# Pattern Summary",
        "",
        f"- count: {summary.get('count')}",
        f"- min: {summary.get('min')}",
        f"- max: {summary.get('max')}",
        "",
        "Guesses:",
    ]
    guesses = summary.get("guesses") or []
    if guesses:
        for item in guesses:
            lines.append(f"- {item}")
    else:
        lines.append("- (none detected)")
    lines += [
        "",
        "Constant differences:",
        f"- order1: {summary['diff_constant']['order1']}",
        f"- order2: {summary['diff_constant']['order2']}",
        f"- order3: {summary['diff_constant']['order3']}",
        f"- ratio constant: {summary['ratio_constant']}",
        "",
        "Samples:",
        f"- diff1: {summary['diff_samples']['order1']}",
        f"- diff2: {summary['diff_samples']['order2']}",
        f"- diff3: {summary['diff_samples']['order3']}",
        f"- ratios: {summary['ratio_samples']}",
        "",
        "Data (first 10):",
    ]
    for n, v in pairs[:10]:
        lines.append(f"- n={n}, value={v}")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    pairs, err = load_series(input_path)
    if err:
        print(f"ERROR: {err}")
        return 1
    if not pairs:
        print("ERROR: empty series")
        return 1

    summary = summarize(pairs, args.tolerance)
    if args.format == "json":
        output = json.dumps({"series": pairs, "summary": summary}, indent=2) + "\n"
    else:
        output = render_md(pairs, summary)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output.rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
