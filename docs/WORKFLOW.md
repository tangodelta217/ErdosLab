# Workflow

## One problem at a time
- Work on exactly one active problem at a time.
- Keep the active problem in `problems/ACTIVE/` and move it out when done.
- Avoid parallel "ACTIVE" efforts to prevent mixed evidence.

## Solved / Disproved
- A result is "Solved" or "Disproved" only with a Lean QED or a verifiable certificate.
- No `sorry` or `admit` in proofs used to claim status.
- For `solved/disproved`, `statement/semantic_audit.md` must be marked `Status: COMPLETE` (or `LEGACY` for pre-gate entries).

## PRs and CI as judge
- Every change goes through a PR and CI is the judge.
- CI should run `./tools/check.sh` as the primary entrypoint.
- No merge sin CI verde.
- Enable branch protection and required checks in GitHub.
- El workflow Lean Action CI (docgen) corre solo en main/manual y no es gate de PRs.

## Requesting review
- Request review after tests pass and link the relevant proof/evidence.
- Reviewers (including internal tool) should use `AGENTS.md` for review guidance.

## Automation (optional)
- Use `python3 tools/auto_problem.py 379 --title "Erdos Problem #379"` to scaffold a new problem.
- The script uses `tools/new_problem.py` and `tools/set_active.py`, freezes the statement, prefills docs, and runs checks.
- The literature scout runs by default and writes `candidates.md/json`, `queries.json`, and `triage.md` (best-effort; offline-safe).
- For manual internal tool Pro research, use `problems/<ID>/literature/internal reference_prompt.md`, paste the JSON output into `internal reference_response.md`, then run `python3 tools/literature_ingest.py PXXXX` to merge candidates with provenance `internal reference_pro_manual`.
- For multi-model literature runs, use `problems/<ID>/literature/llm/*_prompt.md` and ingest with `python3 tools/literature_ingest.py PXXXX --response <path> --source <label>`.
- Solver scaffolding runs by default; use `problems/<ID>/solver/runs/<RUN_ID>/planner_prompt_with_literature.md` (preferred) or `planner_prompt.md`, paste output into `planner_response.md`, run `python3 tools/solver_validate.py PXXXX --run latest`, then run `python3 tools/solver_ingest.py PXXXX --run latest` to store plans and update `solver/best`.
- For multi-model planning, use `problems/<ID>/solver/runs/<RUN_ID>/llm/planner/*_prompt.md` and ingest with `python3 tools/solver_ingest.py PXXXX --file <path> --source <label>`.
- Configure model labels with `LLM_MODELS="gpt-5.2-pro,gemini-deepthink"` (comma-separated).
- Auto-seed plans (no LLM) with `python3 tools/solver_autoplan.py PXXXX --run latest`.
- Run compute experiments with `python3 tools/experiment_runner.py PXXXX` (uses `compute/manifest.json`).
- Use `python3 tools/pattern_miner.py --input problems/PXXXX/compute/results/<RUN>/sequence.json` to inspect numeric patterns.
- Run scoring loops with `python3 tools/optimizer_runner.py PXXXX` (uses `compute/optimizer.json`).
- Scaffold Lean prompts with `python3 tools/formalizer_loop.py PXXXX --run latest` and validate with `python3 tools/formalizer_loop.py PXXXX --run latest --check`.
- For iterative Lean attempts: `python3 tools/formalizer_loop.py PXXXX --run latest --new-attempt`, then check with `--attempt latest --check`.
- Use `python3 tools/lean_search.py PXXXX --run latest` to scaffold Mathlib search queries (`#find`, `simp?`, `by?`).
- Generate a semantic audit checklist with `python3 tools/semantic_audit.py PXXXX`.
- Useful flags: `--no-fetch` (offline placeholders), `--no-lean` (skip Lean import), `--skip-checks` (skip policy/build).
- It also writes `problems/<ID>/report/forum_post.md` as a forum-ready draft (skip with `--no-forum`).
- Maintain `problems/<ID>/report/process_log.md`, `problems/<ID>/report/ai_usage.md`, and `problems/<ID>/report/exposition.md` for traceability.
