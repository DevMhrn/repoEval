"""Tests for pipeline.tasks.miners.net_new."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.common.llm_client import LLMClient, fixture_key
from pipeline.common.prompts.loader import load_prompt
from pipeline.knowledge.schema import Node, RepoGraph
from pipeline.tasks.miners.net_new import (
    NetNewProposal,
    _parse_proposals,
    mine_net_new,
)


def _prompts_dir(tmp_path: Path) -> Path:
    d = tmp_path / "prompts"
    d.mkdir()
    (d / "net_new_proposer.md").write_text(
        "repo={repo}\nmax={max_loc}\nmodules:\n{modules}\n"
    )
    return d


def _seed_fixture(fixtures: Path, model: str, prompt: str, response_text: str):
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


def _graph_with(module_ids: list[str]) -> RepoGraph:
    nodes = [
        Node(id=mid, type="module", file=f"{mid.replace('.', '/')}.py")
        for mid in module_ids
    ]
    return RepoGraph(
        repo="test-repo",
        generated_at="2026-01-01T00:00:00+00:00",
        nodes=nodes,
    )


def test_parse_proposals_from_pure_json():
    text = json.dumps(
        [
            {
                "title": "Add JSON output",
                "module": "pkg.core",
                "description": "Support --json flag on the CLI.",
                "rationale": "Users ask for machine-readable output.",
                "est_loc": 80,
                "tags": ["cli", "output"],
            }
        ]
    )
    proposals = _parse_proposals(text)
    assert len(proposals) == 1
    assert proposals[0].title == "Add JSON output"
    assert proposals[0].est_loc == 80


def test_parse_strips_code_fences():
    text = "```json\n" + json.dumps([{"title": "t", "module": "m", "description": "d"}]) + "\n```"
    proposals = _parse_proposals(text)
    assert len(proposals) == 1


def test_parse_returns_empty_on_bad_json():
    assert _parse_proposals("not json") == []
    assert _parse_proposals("{}") == []


def test_mine_filters_unknown_modules(tmp_path: Path):
    prompts_dir = _prompts_dir(tmp_path)
    fixtures = tmp_path / "fx"

    graph = _graph_with(["pkg.core"])
    tpl = load_prompt("net_new_proposer", prompts_dir=prompts_dir)
    prompt = tpl.render(
        repo=graph.repo,
        modules="- pkg.core: (no summary)",
        max_loc=200,
    )
    _seed_fixture(
        fixtures, "m", prompt,
        json.dumps(
            [
                {"title": "in-scope", "module": "pkg.core",
                 "description": "d1", "est_loc": 50},
                {"title": "off-scope", "module": "pkg.other",
                 "description": "d2", "est_loc": 50},
            ]
        ),
    )

    llm = LLMClient(mode="replay", model="m", fixtures_dir=fixtures)
    proposals = mine_net_new(
        graph, llm, prompts_dir=prompts_dir,
        max_loc_per_proposal=200,
    )
    titles = [p.title for p in proposals]
    assert "in-scope" in titles
    assert "off-scope" not in titles


def test_mine_filters_oversized_proposals(tmp_path: Path):
    prompts_dir = _prompts_dir(tmp_path)
    fixtures = tmp_path / "fx"
    graph = _graph_with(["pkg.core"])
    tpl = load_prompt("net_new_proposer", prompts_dir=prompts_dir)
    prompt = tpl.render(
        repo=graph.repo,
        modules="- pkg.core: (no summary)",
        max_loc=150,
    )
    _seed_fixture(
        fixtures, "m", prompt,
        json.dumps(
            [
                {"title": "small", "module": "pkg.core",
                 "description": "d", "est_loc": 80},
                {"title": "huge", "module": "pkg.core",
                 "description": "d", "est_loc": 500},
            ]
        ),
    )
    llm = LLMClient(mode="replay", model="m", fixtures_dir=fixtures)
    proposals = mine_net_new(
        graph, llm, prompts_dir=prompts_dir,
        max_loc_per_proposal=150,
    )
    assert [p.title for p in proposals] == ["small"]


def test_mine_respects_max_proposals(tmp_path: Path):
    prompts_dir = _prompts_dir(tmp_path)
    fixtures = tmp_path / "fx"
    graph = _graph_with(["pkg.core"])
    tpl = load_prompt("net_new_proposer", prompts_dir=prompts_dir)
    prompt = tpl.render(
        repo=graph.repo,
        modules="- pkg.core: (no summary)",
        max_loc=200,
    )
    payload = [
        {"title": f"p{i}", "module": "pkg.core", "description": "d", "est_loc": 50}
        for i in range(20)
    ]
    _seed_fixture(fixtures, "m", prompt, json.dumps(payload))
    llm = LLMClient(mode="replay", model="m", fixtures_dir=fixtures)
    proposals = mine_net_new(
        graph, llm, prompts_dir=prompts_dir, max_proposals=3,
    )
    assert len(proposals) == 3


def test_mine_drops_proposals_missing_required_fields(tmp_path: Path):
    prompts_dir = _prompts_dir(tmp_path)
    fixtures = tmp_path / "fx"
    graph = _graph_with(["pkg.core"])
    tpl = load_prompt("net_new_proposer", prompts_dir=prompts_dir)
    prompt = tpl.render(
        repo=graph.repo,
        modules="- pkg.core: (no summary)",
        max_loc=200,
    )
    _seed_fixture(
        fixtures, "m", prompt,
        json.dumps(
            [
                {"title": "", "module": "pkg.core", "description": "d"},
                {"title": "good", "module": "pkg.core", "description": "d"},
                {"title": "no-desc", "module": "pkg.core", "description": ""},
            ]
        ),
    )
    llm = LLMClient(mode="replay", model="m", fixtures_dir=fixtures)
    proposals = mine_net_new(graph, llm, prompts_dir=prompts_dir)
    assert [p.title for p in proposals] == ["good"]


def test_net_new_proposal_defaults():
    p = NetNewProposal(title="t", module="m", description="d")
    assert p.est_loc == 100
    assert p.tags == []
