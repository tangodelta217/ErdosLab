# Writeup

1) Result: solved in the affirmative by Cambie, Kovač, and Tao (per the problem page comments).
2) Statement: asks whether $\limsup S(n)=\infty$ for the defined divisibility exponent $S(n)$.
3) Primary source: https://www.erdosproblems.com/379 (accessed 2026-01-12).
4) Forum thread: https://www.erdosproblems.com/forum/thread/379.
5) External Lean formalisation (proof): https://github.com/teorth/analysis/blob/main/analysis/Analysis/Misc/erdos_379.lean.
6) External Lean statement (catalog): https://github.com/google-deepmind/formal-conjectures/blob/main/FormalConjectures/ErdosProblems/379.lean.
7) Paper reference: NO VERIFICADO (exact bibliographic details not yet confirmed).
8) Evidence status: external Lean proof imported as `ErdosLab/Problems/P0379.lean`.
9) Theorem name: `erdos_379` (states the limsup result in ENat form).
10) Local compilation confirmed via `tools/check.sh`, so claim can be marked solved.
11) Formal statement match: `S` is defined via `sSup { r | ∀ k ∈ Ico 1 n, ∃ p, p.Prime ∧ p^r ∣ choose n k }`, matching "largest integer" with `p` depending on `k`.
12) Formal conclusion: `Filter.atTop.limsup (fun n ↦ (S n : ENat)) = ⊤` matches `limsup S(n) = ∞`.
13) Note: for each `n > 1` the set is nonempty and bounded (e.g., `k = 1` gives divisibility by `n`), so `sSup` coincides with a maximum.
