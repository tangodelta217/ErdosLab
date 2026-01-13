#!/usr/bin/env python3
"""Example scoring stub for optimizer_runner (replace with real logic)."""

from __future__ import annotations

import argparse
import json
import os


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score a candidate (stub).")
    parser.add_argument("--seed", type=int, help="Seed value (default: env RUN_SEED).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    seed = args.seed if args.seed is not None else int(os.getenv("RUN_SEED", "0"))
    score = 100.0 - (seed % 10)
    payload = {
        "score": score,
        "candidate": {"seed": seed, "value": seed * seed},
        "valid": True,
        "notes": "example stub; replace with real scoring logic",
    }
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
