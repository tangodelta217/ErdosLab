#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

python3 tools/policy/check_repo.py
tools/lean/audit_no_sorry.sh
tools/lean/audit_no_axiom.sh
tools/lean/audit_no_unsafe.sh
lake build
