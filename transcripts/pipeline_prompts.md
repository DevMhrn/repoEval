# Prompt inventory

Every LLM interaction in RepoEval routes through
`pipeline.common.llm_client.LLMClient` and reads its prompt from a
template under `pipeline/common/prompts/`. This inventory lists every
template, which stage invokes it, and where it's exercised in the
codebase.

## Templates

| Template file | Consumer | Purpose |
|---|---|---|
| `module_summary.md` | `pipeline/knowledge/enrich_llm.py` | One-line "what is this module for" per module. Feeds Pipeline 3's task-generation prompts. |
| `instruction_writer.md` | `pipeline/tasks/instruction.py` | Turn a diff into a symptom-based, implementation-neutral task instruction. Retried up to N times when the leak scanner rejects the output. |
| `golden_rationale.md` | `pipeline/tasks/golden.py` | Author the "why this is the correct fix" prose in `goldenSolution.md`. |
| `net_new_proposer.md` | `pipeline/tasks/miners/net_new.py` | Propose a batch of small, single-module net-new features. Emits a JSON array; scope + module id are filter-enforced downstream. |
| `net_new_tests.md` | `pipeline/tasks/builders/net_new.py` | Author pytest tests for a proposed feature — tests come first so the reference implementation has a concrete target. |
| `net_new_solution.md` | `pipeline/tasks/builders/net_new.py` | Author the reference implementation that makes the just-authored tests pass. |
| `dockerfile.md` | `pipeline/hygiene/generate_dockerfile.py` | Static template (no LLM) — kept in the prompts folder because the loader handles Jinja-style placeholders uniformly. |
| `generate_tests.md` | `pipeline/hygiene/generate_tests.py` | Author coverage-gap tests for a module, filtered downstream by bug-injection mutation testing. |

## Curated commentary

Each `curated/<template>.md` file walks through:

- The exact prompt text (verbatim).
- What the model tends to return.
- The downstream guard that keeps a bad response from shipping.
- A representative fixture key from `fixtures/llm/` where the response
  is cached.

## Not committed

- `session_*.jsonl` — raw record-mode logs. Regenerated on every run.
- Anthropic API key values — never emitted anywhere.
