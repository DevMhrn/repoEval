# Decisions Log

Chronological record of design decisions. Each entry: what we chose, what
we rejected, why. Keeps future us honest about trade-offs.

---

## 2026-08-26 — Package manager: uv

**Chose:** `uv` for RepoEval's own dependency management and virtualenv.

**Rejected:**
- `pip + requirements.txt`: familiar but slow, no lockfile discipline.
- `poetry`: too heavy, adds a build system we don't need.

**Why:** Speed matters when the pipeline itself gets rebuilt often. `uv`
also aligns with tools the reviewer will likely already have (CodingRL uses
`uv tool install harbor==0.1.45`).

---

## 2026-08-26 — Python 3.11

**Chose:** `>=3.11,<3.12`.

**Rejected:**
- 3.12/3.13: some libraries in the LLM and graph ecosystems lag on the
  bleeding edge; not worth the risk for this scope.
- 3.10: missing `tomllib` in stdlib; would need `tomli`.

---

## 2026-08-26 — Task folder schema follows assignment, not CodingRL

**Chose:** `task.json + input/ + solution/ + verifier/ + goldenSolution.md
+ evidence/`.

**Rejected:** CodingRL's `task.toml + instruction.md + tests/ + solution/
solve.sh + environment/Dockerfile`.

**Why:** The assignment specifies the target schema explicitly. Steal
CodingRL's *design wisdom* (canary strings, rubric, model-weakness
targeting) without adopting its file layout.

---

## 2026-08-26 — LLM client: record/replay by default

**Chose:** Every LLM call goes through a client that supports `record`
mode (call API, cache to fixtures) and `replay` mode (read fixtures, never
call API).

**Rejected:** Direct SDK calls scattered through the code.

**Why:** Reviewer reproducibility. In replay mode the reviewer's run of
the pipeline is bit-identical to ours. Same choice also feeds
`transcripts/` for free.

---

## 2026-08-26 — Knowledge layer stored as JSON, queried in-memory with NetworkX

**Chose:** Static JSON files on disk; load into NetworkX at Pipeline 3
time for graph queries.

**Rejected:**
- Neo4j / Kùzu: adds infra to the reviewer's setup, higher failure risk.
- Ad-hoc dict traversal: no query power, hard to extend.

**Why:** Best of both. Portable storage, decent query power, zero infra.
Report will call this out and note "Neo4j at 100-repo scale."

---

## 2026-08-26 — Task-generation AI has knowledge layer access; graded agents do not

**Chose:** Pipeline 3's internal LLM sees the knowledge layer. The agents
being benchmarked at test time never do.

**Rejected:** Handing the knowledge graph to the graded agents.

**Why:** Handing the map to the agents being tested makes the benchmark
meaningless. The whole point is measuring what they can and cannot do
unaided.
