# AGENTS

## Working agreements
- Always: plan -> changes -> tests -> summary -> commit.
- Keep commits small.
- Do not introduce `sorry` or `admit` in Lean.
- Do not add new `axiom` in project code.

## Build & test commands
- Primary entrypoint (placeholder): `./tools/check.sh`.

## Safety
- Do not run destructive commands.
- Do not touch files outside the repo.

## Review guidelines
- P0: anything that allows marking solved/disproved without evidence.
- P1: poor reproducibility, missing docs, scripts without pinning, etc.
