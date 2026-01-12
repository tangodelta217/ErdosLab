# Workflow

## One problem at a time
- Work on exactly one active problem at a time.
- Keep the active problem in `problems/ACTIVE/` and move it out when done.
- Avoid parallel "ACTIVE" efforts to prevent mixed evidence.

## Solved / Disproved
- A result is "Solved" or "Disproved" only with a Lean QED or a verifiable certificate.
- No `sorry` or `admit` in proofs used to claim status.

## PRs and CI as judge
- Every change goes through a PR and CI is the judge.
- CI should run `./tools/check.sh` as the primary entrypoint.

## Requesting review
- Request review after tests pass and link the relevant proof/evidence.
- Reviewers (including Codex) should use `AGENTS.md` for review guidance.
