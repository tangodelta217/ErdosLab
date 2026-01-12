# Tests

## Negative test: fail-policy (do not merge)
- PR: https://github.com/tangodelta217/ErdosLab/pull/2
- Change: `claim.state` set to `solved` without evidence.
- Failure: `tools/policy/check_repo.py` rejects missing evidence (requires `lean` or `certificate`).
- Conclusion: Gate verified.
