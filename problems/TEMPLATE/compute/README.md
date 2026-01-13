# Compute Experiments

Use `manifest.json` to list runnable experiments. Each experiment should be
reproducible and write its own outputs (or rely on the runner logs).

Example manifest entry:

```json
{
  "name": "small_cases",
  "description": "Enumerate small n to look for patterns.",
  "command": ["python3", "compute/experiments/small_cases.py"],
  "timeout_sec": 60
}
```
