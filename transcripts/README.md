# transcripts/

Curated record of how AI was used to build and run RepoEval.

## What lives here

- `session_YYYYMMDD_HHMMSS.jsonl` — auto-appended per LLM call by
  `pipeline.common.llm_client` when running in record mode.
- Curated markdown files — extracted "turning point" prompts with commentary.
- `lessons.md` — running notes on what prompts worked, what didn't, and
  what to refactor next.

## Policy

- Every LLM call the pipeline makes is captured verbatim (prompt + response).
- Sensitive data is redacted before commit (API keys, absolute local paths).
- Curated markdown files are hand-picked from the raw JSONL — we don't
  commit the raw sessions themselves (they're gitignored).

Phase 0 status: directory only. Populates automatically once Phase 1 runs.
