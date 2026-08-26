"""Tests for pipeline.knowledge.enrich_llm."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.common.llm_client import LLMClient, fixture_key
from pipeline.common.prompts.loader import load_prompt
from pipeline.knowledge.enrich_llm import enrich_with_llm
from pipeline.knowledge.schema import Node, RepoGraph


def _prompts_dir(tmp_path: Path) -> Path:
    d = tmp_path / "prompts"
    d.mkdir()
    (d / "module_summary.md").write_text(
        "id: {module_id}\n"
        "doc: {docstring}\n"
        "names: {public_names}\n"
    )
    return d


def _seed_fixture(
    fixtures: Path, model: str, prompt: str, response_text: str
) -> None:
    key = fixture_key(model, 0.0, None, prompt)
    fixtures.mkdir(exist_ok=True)
    (fixtures / f"{key}.json").write_text(
        json.dumps(
            {
                "key": key,
                "model": model,
                "temperature": 0.0,
                "system": None,
                "prompt": prompt,
                "response_text": response_text,
                "input_tokens": 1,
                "output_tokens": 1,
                "saved_at": "2026-01-01T00:00:00+00:00",
            }
        )
    )


def _graph_with_modules(*mods) -> RepoGraph:
    nodes: list[Node] = []
    for mod_id, docstring, public in mods:
        nodes.append(
            Node(id=mod_id, type="module", file=f"{mod_id.replace('.', '/')}.py",
                 docstring=docstring)
        )
        for name in public:
            nodes.append(
                Node(id=f"{mod_id}.{name}", type="function",
                     file=f"{mod_id.replace('.', '/')}.py", is_public=True)
            )
    return RepoGraph(
        repo="x",
        generated_at="2026-01-01T00:00:00+00:00",
        nodes=nodes,
    )


def test_attaches_summary_to_module_nodes(tmp_path: Path):
    prompts_dir = _prompts_dir(tmp_path)
    fixtures = tmp_path / "fx"

    graph = _graph_with_modules(
        ("pkg.core", "the core module", ["glom", "Spec"]),
        ("pkg.util", "utility helpers", ["helper"]),
    )

    # Precompute prompts and seed fixtures.
    tpl = load_prompt("module_summary", prompts_dir=prompts_dir)
    for mod_id, doc, public in (
        ("pkg.core", "the core module", ["Spec", "glom"]),  # sorted
        ("pkg.util", "utility helpers", ["helper"]),
    ):
        prompt = tpl.render(
            module_id=mod_id,
            docstring=doc,
            public_names=", ".join(public),
        )
        _seed_fixture(fixtures, "m", prompt, f"summary for {mod_id}")

    llm = LLMClient(mode="replay", model="m", fixtures_dir=fixtures)
    enriched = enrich_with_llm(graph, llm, prompts_dir=prompts_dir)

    assert (
        enriched.find_node("pkg.core").metadata["summary"]
        == "summary for pkg.core"
    )
    assert (
        enriched.find_node("pkg.util").metadata["summary"]
        == "summary for pkg.util"
    )


def test_non_module_nodes_have_no_summary(tmp_path: Path):
    prompts_dir = _prompts_dir(tmp_path)
    fixtures = tmp_path / "fx"

    graph = _graph_with_modules(
        ("pkg.core", "core", ["a"]),
    )
    tpl = load_prompt("module_summary", prompts_dir=prompts_dir)
    _seed_fixture(
        fixtures, "m",
        tpl.render(module_id="pkg.core", docstring="core", public_names="a"),
        "summary",
    )

    llm = LLMClient(mode="replay", model="m", fixtures_dir=fixtures)
    enriched = enrich_with_llm(graph, llm, prompts_dir=prompts_dir)

    fn = enriched.find_node("pkg.core.a")
    assert "summary" not in fn.metadata


def test_docstring_none_becomes_placeholder(tmp_path: Path):
    prompts_dir = _prompts_dir(tmp_path)
    fixtures = tmp_path / "fx"

    graph = RepoGraph(
        repo="x",
        generated_at="2026-01-01T00:00:00+00:00",
        nodes=[Node(id="pkg.core", type="module", file="pkg/core.py")],
    )
    tpl = load_prompt("module_summary", prompts_dir=prompts_dir)
    prompt = tpl.render(
        module_id="pkg.core",
        docstring="(none)",
        public_names="(none)",
    )
    _seed_fixture(fixtures, "m", prompt, "summary text")

    llm = LLMClient(mode="replay", model="m", fixtures_dir=fixtures)
    enriched = enrich_with_llm(graph, llm, prompts_dir=prompts_dir)

    assert enriched.find_node("pkg.core").metadata["summary"] == "summary text"


def test_rerun_uses_fixture_cache_zero_api_calls(tmp_path: Path):
    """Second enrichment against the same fixtures produces the same result."""
    prompts_dir = _prompts_dir(tmp_path)
    fixtures = tmp_path / "fx"

    graph = _graph_with_modules(("pkg.core", "core", ["a"]))
    tpl = load_prompt("module_summary", prompts_dir=prompts_dir)
    _seed_fixture(
        fixtures, "m",
        tpl.render(module_id="pkg.core", docstring="core", public_names="a"),
        "cached summary",
    )
    llm = LLMClient(mode="replay", model="m", fixtures_dir=fixtures)

    a = enrich_with_llm(graph, llm, prompts_dir=prompts_dir)
    b = enrich_with_llm(graph, llm, prompts_dir=prompts_dir)
    assert (
        a.find_node("pkg.core").metadata["summary"]
        == b.find_node("pkg.core").metadata["summary"]
    )


def test_public_names_are_truncated_by_max(tmp_path: Path):
    prompts_dir = _prompts_dir(tmp_path)
    fixtures = tmp_path / "fx"

    many = [f"n_{i:02d}" for i in range(50)]
    graph = _graph_with_modules(("pkg.big", "big module", many))

    # Seed the fixture matching the truncated names call
    tpl = load_prompt("module_summary", prompts_dir=prompts_dir)
    truncated = sorted(many)[:5]
    _seed_fixture(
        fixtures, "m",
        tpl.render(module_id="pkg.big", docstring="big module",
                   public_names=", ".join(truncated)),
        "summary",
    )
    llm = LLMClient(mode="replay", model="m", fixtures_dir=fixtures)
    enriched = enrich_with_llm(
        graph, llm, prompts_dir=prompts_dir, max_public_names=5
    )
    assert enriched.find_node("pkg.big").metadata["summary"] == "summary"
