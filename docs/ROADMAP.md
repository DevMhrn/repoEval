# Roadmap

Phase-by-phase build plan. Each phase has an entry criterion (what must
be true before starting) and an exit criterion (what proves it's done).

---

## Phase 0 — Scaffolding (current)

**Goal:** every file the pipeline will need exists as a documented stub;
the CLI runs and prints help; the smoke test passes.

**Exit criterion:**
- `uv sync` succeeds
- `./run.sh --help` prints subcommands
- `./run.sh info <repo>` prints a "not implemented" message cleanly
- `uv run pytest` passes the smoke test

**Deliverables:** directory tree + stubs + config + docs.

---

## Phase 1 — Pipeline 1: Hygiene

**Entry:** Phase 0 exit.

**Goal:** `./run.sh hygiene <path-to-glom>` produces a working,
containerized, lint-clean, deterministic version of glom under
`output/repo/`.

**Work order:**
1. Real `common/config.py`, `common/logging.py`, `common/ecosystem.py`
   (Python strategy only), `common/docker_utils.py`, `common/stage.py`.
2. `common/llm_client.py` in record mode with fixtures.
3. `hygiene/pin_deps.py` via uv/pip-tools.
4. `hygiene/generate_dockerfile.py` — Python 3.11 base + pinned deps.
5. Baseline test run inside container; hygiene report.
6. `hygiene/generate_tests.py` for coverage gaps, with bug-injection guard.
7. `hygiene/lint_setup.py` — ruff + black, auto-fix.
8. Determinism check — build + test twice, identical output.

**Exit:**
- glom `docker build && docker run` passes twice with byte-identical
  test output.
- Coverage report shows every target module >= configured threshold.
- `output/repo/` is a lint-clean, pinned, tested clone.

---

## Phase 2 — Pipeline 2: Knowledge Layer

**Entry:** Phase 1 exit — we have a cleaned repo.

**Goal:** `./run.sh knowledge output/repo` produces
`output/repo_graph.json` and `output/.okf/*.json`.

**Work order:**
1. `knowledge/extract_graph.py` — Python AST walker.
2. `knowledge/enrich_git.py` — GitPython, per-node commit history.
3. Import coverage from hygiene's report.
4. `knowledge/enrich_llm.py` — module summaries, cached.
5. `knowledge/freeze.py` — write JSON files.
6. `KnowledgeStage.verify()` — schema validation and edge sanity.

**Exit:**
- Graph loads via NetworkX without warnings.
- Every non-test module has an `.okf/<module>.json`.
- Re-running the stage is a no-op (idempotency check).

---

## Phase 3 — Pipeline 3: Tasks + Validation Harness

**Entry:** Phase 2 exit.

**Goal:** `./run.sh tasks output/repo` produces 10 validated tasks under
`tasks/` plus `tasks.json`.

**Work order:**
1. Validator first: `common/validator/checks.py` + `harness.py`.
2. Miners: `history.py`, then `excision.py`, then `net_new.py`.
3. `tasks/selector.py` — score, dedupe, diversity.
4. `tasks/builder.py` — materialize folders; prompt for instruction;
   leak scanner.
5. Wire `TasksStage` to run the whole flow; discard invalid candidates
   and loop.
6. Emit `tasks.json`.

**Exit:**
- 10 tasks under `tasks/`, each with complete `evidence/`.
- `tasks.json` indexes all with validation status.
- Every task's `validate_task()` re-run yields the same verdict.

---

## Phase 4 — Held-out dry run

**Entry:** Phase 3 exit.

**Goal:** run the entire pipeline end-to-end on a *different* Python repo
(never touched during development). Find what breaks.

**Exit:**
- Pipeline runs to completion on the held-out repo.
- All hardcoded glom-specific assumptions removed.
- Any unfixable gap documented in `REPORT.md`.

---

## Phase 5 — REPORT.md + transcripts curation

**Entry:** Phase 4 exit.

**Goal:** produce the writeup and curated prompts.

**Exit:**
- `REPORT.md` covers all required sections.
- `transcripts/` contains ~10-20 curated markdown files, not raw dumps.
- Final validation run: every task revalidates cleanly.
