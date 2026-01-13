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
- No merge sin CI verde.
- Enable branch protection and required checks in GitHub.
- El workflow Lean Action CI (docgen) corre solo en main/manual y no es gate de PRs.

## Requesting review
- Request review after tests pass and link the relevant proof/evidence.
- Reviewers (including Codex) should use `AGENTS.md` for review guidance.

## Automation (optional)
- Use `python3 tools/auto_problem.py 379 --title "Erdos Problem #379"` to scaffold a new problem.
- The script uses `tools/new_problem.py` and `tools/set_active.py`, freezes the statement, prefills docs, and runs checks.
- The literature scout runs by default and writes `candidates.md/json`, `queries.json`, and `triage.md` (best-effort; offline-safe).
- Useful flags: `--no-fetch` (offline placeholders), `--no-lean` (skip Lean import), `--skip-checks` (skip policy/build).
- It also writes `problems/<ID>/report/forum_post.md` as a forum-ready draft (skip with `--no-forum`).
