# Solver Planner Prompt (manual)

Version: v1

You are generating structured research plans for an Erdos problem. Do NOT claim the problem is solved. Do NOT mark anything as verified. Output only plans and experiments that could lead to a proof.

Problem context:
- problem_id: P0379
- title: Erdos Problem #379
- problem_url: https://www.erdosproblems.com/379
- forum_url: https://www.erdosproblems.com/forum/thread/379
- keywords: binomial, coefficient, denote, depending, divisible, integer, largest, prime, some, such

Frozen statement:
Let $S(n)$ denote the largest integer such that, for all $1\leq k<n$, the binomial coefficient $\binom{n}{k}$ is divisible by $p^{S(n)}$ for some prime $p$ (depending on $k$). Is it true that\[\limsup S(n)=\infty?\]

If you used literature candidates from candidates.json, set solver_used_scout=true. Otherwise keep solver_used_scout=false.

Output format (STRICT): return exactly one JSON object in a single ```json``` block. Do not include extra prose outside the JSON.

Required JSON schema:
{
  "problem_id": "P0379",
  "generated_at": "YYYY-MM-DD",
  "solver_used_scout": false,
  "plans": [
    {
      "strategy_name": "...",
      "high_level_idea": "...",
      "key_lemmas": [
        {
          "statement": "...",
          "why_needed": "...",
          "likely_sources": ["..."],
          "checkability": "easy | medium | hard"
        }
      ],
      "definitions_needed": ["..."],
      "risk_factors": ["..."],
      "experiments": ["..."],
      "formalization_path": ["..."],
      "expected_payoff": 0.0,
      "difficulty": 0.0,
      "dependency_graph": ["lemma1 -> lemma2", "lemma2 -> theorem"]
    }
  ],
  "notes": "... optional ..."
}

Rules:
- Provide 3 to 8 plans.
- expected_payoff and difficulty must be numbers in [0,1].
- Do not assert correctness; everything is speculative.
