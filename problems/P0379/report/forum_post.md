# Forum post draft: Erdos Problem #379

Status:
- claim.state: solved
- repo commit: 79a690b

Sources:
- problem page: https://www.erdosproblems.com/379 (accessed 2026-01-13)
- forum thread: https://www.erdosproblems.com/forum/thread/379
- latex snapshot: https://www.erdosproblems.com/latex/379 (sha256: aa5f646778f1e13fbee988e38668a6597434e62d5c1fd4594f3e87ffbdcc7483)

Statement (from frozen_v1):
Let $S(n)$ denote the largest integer such that, for all $1\leq k<n$, the binomial coefficient $\binom{n}{k}$ is divisible by $p^{S(n)}$ for some prime $p$ (depending on $k$). Is it true that\[\limsup S(n)=\infty?\]

Evidence:
- Lean file: ErdosLab/Problems/P0379.lean
- Lean source: https://raw.githubusercontent.com/teorth/analysis/main/analysis/Analysis/Misc/erdos_379.lean
- theorem: erdos_379
- reproducible build: `bash tools/check.sh`
- policy check: `python3 tools/policy/check_repo.py`

Manual checklist before posting:
- [ ] Statement matches frozen_v1 (compare hash if available).
- [ ] Bibliography verified (replace NO VERIFICADO).
- [ ] Lean proof corresponds to the frozen statement.
- [ ] CI green for the PR.
