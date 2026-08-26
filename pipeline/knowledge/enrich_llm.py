"""
LLM-authored module summaries.

For each module node in the graph, ask the LLM for a 1-2 sentence
summary of what the module is for. Results ride the shared
:class:`LLMClient` which caches by prompt hash — so re-runs against
an unchanged repo are 100% cache hits with zero API calls.

We deliberately send only:

- the module id
- its top-of-file docstring (may be empty)
- a sorted list of public identifier names it exports

Full source would blow context and rarely produce a better summary than
what the docstring already says. Downstream miners can always
re-inspect source when they need to.
"""

from __future__ import annotations

from pathlib import Path

from ..common.llm_client import LLMClient
from ..common.prompts.loader import load_prompt
from .schema import Node, RepoGraph

_DEFAULT_TEMPLATE_DIR = (
    Path(__file__).resolve().parent.parent / "common" / "prompts"
)


def enrich_with_llm(
    graph: RepoGraph,
    llm: LLMClient,
    *,
    prompts_dir: Path | None = None,
    max_public_names: int = 25,
) -> RepoGraph:
    tpl = load_prompt(
        "module_summary",
        prompts_dir=prompts_dir or _DEFAULT_TEMPLATE_DIR,
    )

    module_nodes = [n for n in graph.nodes if n.type == "module"]
    summaries: dict[str, str] = {}

    for mod in module_nodes:
        public_names = sorted(_public_names_in_module(graph, mod.id))[
            :max_public_names
        ]
        prompt = tpl.render(
            module_id=mod.id,
            docstring=mod.docstring or "(none)",
            public_names=(", ".join(public_names) if public_names else "(none)"),
        )
        response = llm.complete(
            prompt, purpose=f"module_summary:{mod.id}"
        )
        summaries[mod.id] = response.text.strip()

    enriched: list[Node] = []
    for node in graph.nodes:
        node_copy = node.model_copy(deep=True)
        if node.id in summaries:
            node_copy.metadata["summary"] = summaries[node.id]
        enriched.append(node_copy)

    return graph.model_copy(update={"nodes": enriched})


def _public_names_in_module(graph: RepoGraph, module_id: str) -> list[str]:
    prefix = f"{module_id}."
    result: list[str] = []
    for node in graph.nodes:
        if node.id.startswith(prefix) and node.is_public:
            result.append(node.id[len(prefix) :])
    return result
