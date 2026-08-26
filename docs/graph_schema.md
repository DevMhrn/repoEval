# Knowledge Layer — Graph Schema

Persisted at `output/repo_graph.json`. Every consumer types against
`pipeline.knowledge.schema.RepoGraph`.

## Shape

```json
{
  "schema_version": "1.0.0",
  "repo": "https://github.com/mahmoud/glom",
  "commit": "abc1234...",
  "generated_at": "2026-08-26T20:00:00+00:00",
  "nodes": [ ... ],
  "edges": [ ... ]
}
```

## Node

```json
{
  "id": "glom.core.glom",
  "type": "function",
  "file": "glom/core.py",
  "line": 42,
  "end_line": 78,
  "docstring": "...",
  "signature": "(target, spec, **kwargs)",
  "is_public": true,
  "metadata": {}
}
```

- `id` — stable dotted path. Unique across the graph. Used as the key
  everywhere downstream (mining, task manifests, evidence reports).
- `type` — one of `module | class | function | method`.
- `file` — repo-relative path.
- `line` / `end_line` — 1-based source span. Both are 0 for nodes
  without a clear source location (e.g. synthetic external packages).
- `is_public` — mirrors PEP 8 naming (identifier does not start with
  underscore).
- `metadata` — free-form dict populated by enrichment stages
  (coverage, git activity, LLM summaries).

## Edge

```json
{
  "source": "glom.mutation.assign",
  "target": "glom.core.glom",
  "type": "calls",
  "weight": 1.0,
  "metadata": {}
}
```

- `type` — one of `imports | calls | defines | inherits`.
- `weight` — reserved for call-count-weighted ranking; extractors
  default to 1.0.

## Schema evolution

Bump `SCHEMA_VERSION` in `pipeline/knowledge/schema.py` when a field is
removed or its meaning changes. Additive changes (new optional field)
are backward-compatible and don't require a bump.
