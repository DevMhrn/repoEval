# Prompt — generate_tests

**Template:** `pipeline/common/prompts/generate_tests.md`
**Consumer:** `pipeline/hygiene/generate_tests.py` — Phase 1.12
**Cache:** one fixture per (module, gap)

## Why we ask

Pipeline 1 needs to raise coverage on gap modules. Writing the
increased-coverage tests by hand isn't scalable across many repos, so
we ask the LLM. But LLM-authored tests famously exhibit "coverage
theater" — they call functions without asserting on outputs, hit the
lines but verify nothing.

## Downstream guard — the reason this prompt is safe

The bug-injector in `pipeline/hygiene/bug_injector.py` mutates each
target function (invert boolean, swap `+`/`-`, off-by-one, swap
`==`/`!=`), then re-runs the LLM-authored tests against each mutant.
If the tests still pass under a mutant, they aren't testing behaviour
— they're theatre — and get discarded.

Only tests that *kill at least one mutant* land in
`output/repo/tests/generated/`.

This guard was validated on a synthetic `def add(a, b): return a + b`
module:

- The LLM authored `test_calls(): add(1, 2)` (no assertion → theatre).
  The `swap_addsub` mutant still passes it. Rejected.
- The LLM authored `test_two_plus_three(): assert add(2, 3) == 5`.
  The mutant returns `-1` — the test fails. Killed. Kept.

The theatre-rejection test lives at
`tests/test_generate_tests.py::test_generate_tests_rejects_coverage_theater`.

## Not exercised on glom

glom already has strong test coverage on its public API, so the gap
list on our run was small and we didn't invoke the LLM heavily here.
The mechanism is validated in unit tests and is ready for the
held-out repo where gaps are likely larger.
