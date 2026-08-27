# Prompt — module_summary

**Template:** `pipeline/common/prompts/module_summary.md`
**Consumer:** `pipeline/knowledge/enrich_llm.py` — Phase 2.10
**Cache:** one fixture per module × prompt text (32 calls on glom)

## Why we ask

The per-module summary is what turns a `.okf/*.json` file from a
mechanical dump of names into something Pipeline 3 can actually reason
about. Downstream miners feed the summary to the net-new proposer so
proposals stay on-topic per module.

The prompt is deliberately small: module id + top-of-file docstring +
sorted public names. Feeding the full module source would waste tokens
and often teach the model nothing the docstring already says.

## Downstream guard

None strictly required — the response lands as free-form prose in a
`summary` field. If the LLM ever returns junk the effect is diluted
proposals, not broken tasks.

## Example (real fixture)

`fixtures/llm/31954b66cfcbe946.json` — `glom.core`.

**Input (excerpt):**

```
Summarise what the Python module `glom.core` is for in 1-2 sentences.

Docstring (if any):
*glom gets results.*

The ``glom`` package has one central entrypoint,
:func:`glom.glom`. Everything else in the package revolves around that
one function. ...

Public identifiers exported:
AUTO, FILL, arg_val, chain_child, format_invocation, format_oneline_trace,
format_target_spec_trace, glom, register, register_op
```

**Response:**

> `glom.core` implements the core `glom()` function and its supporting
> machinery for extracting and restructuring data from a "target"
> object according to a declarative "spec" template. It also defines
> the associated classes and utilities (e.g., Call, Coalesce, Invoke,
> Glommer, GlomError) that enable flexible, composable data access and
> transformation patterns.

That summary now appears in `output/.okf/glom.core.json`, and any
net-new proposal for `glom.core` sees it as context.
