#!/usr/bin/env bash
set -euo pipefail

if command -v rg >/dev/null 2>&1; then
  if rg -n -e "\\bsorry\\b" -e "\\badmit\\b" ErdosLab; then
    echo "ERROR: found 'sorry' or 'admit' in ErdosLab/"
    exit 1
  fi
else
  if grep -R -n -E "\\bsorry\\b|\\badmit\\b" ErdosLab; then
    echo "ERROR: found 'sorry' or 'admit' in ErdosLab/"
    exit 1
  fi
fi
