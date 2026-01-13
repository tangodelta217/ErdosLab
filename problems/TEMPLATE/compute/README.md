# Compute Experiments

Use `manifest.json` to list runnable experiments. Each experiment should be
reproducible and write its own outputs (or rely on the runner logs).
Store scripts under `compute/experiments/`.

Suggested tools:
- `python3 tools/pattern_miner.py --input <file.json>` for quick pattern checks.
- `python3 tools/optimizer_runner.py PXXXX` for scoring loops (see `optimizer.json`).

Example manifest entry:

```json
{
  "name": "small_cases",
  "description": "Enumerate small n to look for patterns.",
  "command": ["python3", "compute/experiments/small_cases.py"],
  "timeout_sec": 60
}
```
