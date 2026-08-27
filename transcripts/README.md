# transcripts/

Curated record of how AI was used to build and run RepoEval.

## Layout

- `session_YYYYMMDD_HHMMSS.jsonl` — auto-appended per LLM call by
  `pipeline.common.llm_client` when running in record mode. Raw and
  gitignored; they carry local timestamps and would drift on every run.
- `curated/*.md` — the parts of the transcripts worth keeping. One file
  per prompt template used by the pipeline, plus a `lessons.md` with
  observations from actually running against a real repo.
- `pipeline_prompts.md` — an inventory of every prompt template + which
  stage invokes it.

## Policy

- LLM calls are captured verbatim to raw sessions (record mode). The
  raw JSONL is not committed — timestamps and call ordering churn on
  every run.
- Curated markdown is hand-picked to explain the *design decision*
  behind each prompt: what the prompt is asking for, what the model
  tends to return, what constraints we impose downstream, and what
  broke when we relied on the default output.
- `fixtures/llm/*.json` is committed and paired with these transcripts.
  A reviewer running the pipeline in replay mode gets the same
  responses the curated markdown quotes.

## Redaction

- Absolute host paths (`/Users/...`, `/home/...`) are stripped from any
  content that lands under `curated/`.
- API keys never appear in raw sessions or fixtures — the client only
  sees a redacted representation via `Config.pretty()`.
