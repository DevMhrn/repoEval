"""Tests for pipeline.knowledge.okf."""

from __future__ import annotations

import json
from pathlib import Path

from pipeline.knowledge.okf import (
    ModuleFacts,
    _complexity_hint,
    _is_test_id,
    extract_module_facts,
    write_okf,
)
from pipeline.knowledge.schema import Edge, Node, RepoGraph


def _mod(id_: str, file: str = "", end_line: int = 100, **meta) -> Node:
    node = Node(
        id=id_,
        type="module",
        file=file or f"{id_.replace('.', '/')}.py",
        line=1,
        end_line=end_line,
    )
    if meta:
        node.metadata.update(meta)
    return node


def _fn(id_: str, file: str = "", is_public: bool = True) -> Node:
    return Node(
        id=id_,
        type="function",
        file=file or "x.py",
        is_public=is_public,
    )


def _cls(id_: str, file: str = "") -> Node:
    return Node(id=id_, type="class", file=file or "x.py")


def _graph(nodes: list[Node], edges: list[Edge] | None = None) -> RepoGraph:
    return RepoGraph(
        repo="x",
        generated_at="2026-01-01T00:00:00+00:00",
        nodes=nodes,
        edges=edges or [],
    )


def test_extract_lists_direct_functions_and_classes():
    graph = _graph(
        [
            _mod("pkg.core", end_line=200),
            _fn("pkg.core.public", is_public=True),
            _fn("pkg.core._private", is_public=False),
            _cls("pkg.core.Spec"),
            _fn("pkg.core.Spec.match"),  # method: nested, must be excluded
        ]
    )
    facts = extract_module_facts(graph)
    core = facts["pkg.core"]
    assert core.functions == ["_private", "public"]
    assert core.public_functions == ["public"]
    assert core.classes == ["Spec"]


def test_extract_carries_metadata_fields():
    mod = _mod("pkg.core", end_line=300)
    mod.metadata["coverage"] = {"line_rate": 0.82}
    mod.metadata["summary"] = "does core things"
    mod.metadata["git"] = {"last_commit": "sha1"}
    graph = _graph([mod, _fn("pkg.core.a")])
    facts = extract_module_facts(graph)["pkg.core"]
    assert facts.coverage == 0.82
    assert facts.summary == "does core things"
    assert facts.recent_commits == ["sha1"]


def test_test_refs_counted_from_test_modules():
    graph = _graph(
        [
            _mod("pkg.core"),
            _fn("pkg.core.target"),
            _mod("tests.test_core"),
            _fn("tests.test_core.test_a"),
        ],
        edges=[
            Edge(source="tests.test_core.test_a", target="pkg.core.target", type="calls"),
            Edge(source="tests.test_core", target="pkg.core", type="imports"),
        ],
    )
    facts = extract_module_facts(graph)
    assert facts["pkg.core"].tests_ref_count == 2


def test_external_modules_skipped():
    graph = _graph([_mod("<external>.os", file="<external>/os")])
    facts = extract_module_facts(graph)
    assert facts == {}


def test_complexity_hint_thresholds():
    assert _complexity_hint(1000, 5) == "high"
    assert _complexity_hint(50, 40) == "high"
    assert _complexity_hint(200, 5) == "medium"
    assert _complexity_hint(50, 15) == "medium"
    assert _complexity_hint(50, 5) == "low"


def test_is_test_id_recognises_common_shapes():
    assert _is_test_id("tests.test_x")
    assert _is_test_id("pkg.tests.util")
    assert _is_test_id("test_helper_test")
    assert not _is_test_id("pkg.core")


def test_write_okf_creates_one_file_per_module(tmp_path: Path):
    facts = {
        "pkg.core": ModuleFacts(
            module="pkg.core", file="pkg/core.py", loc=100,
            functions=["a"], public_functions=["a"],
        ),
        "pkg.util": ModuleFacts(
            module="pkg.util", file="pkg/util.py", loc=50,
        ),
    }
    written = write_okf(facts, tmp_path / ".okf")
    assert len(written) == 2

    core = json.loads((tmp_path / ".okf" / "pkg.core.json").read_text())
    assert core["module"] == "pkg.core"
    assert core["functions"] == ["a"]
    util = json.loads((tmp_path / ".okf" / "pkg.util.json").read_text())
    assert util["loc"] == 50


def test_write_okf_is_deterministic(tmp_path: Path):
    facts = {
        "pkg.core": ModuleFacts(module="pkg.core", file="x.py", loc=1),
    }
    write_okf(facts, tmp_path / ".okf")
    first = (tmp_path / ".okf" / "pkg.core.json").read_text()
    write_okf(facts, tmp_path / ".okf")
    second = (tmp_path / ".okf" / "pkg.core.json").read_text()
    assert first == second


def test_extract_uses_module_end_line_as_loc():
    graph = _graph([_mod("pkg.core", end_line=1234)])
    facts = extract_module_facts(graph)
    assert facts["pkg.core"].loc == 1234
