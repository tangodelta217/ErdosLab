#!/usr/bin/env python3
"""Generate small-case data for pattern mining (replace value() for real use)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Tuple


def value(n: int) -> int:
    """Replace with problem-specific computation."""
    return n * n


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate small-case sequence data.")
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum n to compute (default: 10).",
    )
    parser.add_argument(
        "--output",
        help="Write JSON output to file (default: stdout).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit < 1:
        print("ERROR: --limit must be >= 1")
        return 1
    pairs: List[Tuple[int, int]] = [(n, value(n)) for n in range(1, args.limit + 1)]
    payload = {
        "series": [{"n": n, "value": v} for n, v in pairs],
        "values": [v for _, v in pairs],
    }
    output = json.dumps(payload, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output.rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
