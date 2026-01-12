#!/usr/bin/env bash
set -euo pipefail

if command -v rg >/dev/null 2>&1; then
  if rg -n -e "\\baxiom\\b" ErdosLab; then
    echo "ERROR: found 'axiom' in ErdosLab/"
    exit 1
  fi
else
  if grep -R -n -E "\\baxiom\\b" ErdosLab; then
    echo "ERROR: found 'axiom' in ErdosLab/"
    exit 1
  fi
fi
