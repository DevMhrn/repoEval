"""Tests for pipeline.knowledge.extractors.imports."""

from __future__ import annotations

import ast
from pathlib import Path

from pipeline.knowledge.extractors.imports import (
    EXTERNAL_PREFIX,
    extract_import_edges,
)
from pipeline.knowledge.walkers.python import ParsedModule


def _mod(module_id: str, source: str, tmp_path: Path, *, is_init: bool = False) -> ParsedModule:
    rel = module_id.replace(".", "/")
    filename = f"{rel}/__init__.py" if is_init else f"{rel}.py"
    path = tmp_path / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    return ParsedModule(path=path, module_id=module_id, tree=ast.parse(source))


def _pairs(edges):
    return {(e.source, e.target) for e in edges}


def test_absolute_import_creates_edge(tmp_path: Path):
    mod = _mod("pkg.a", "import pkg.b\n", tmp_path)
    edges = extract_import_edges(mod, known_module_ids={"pkg", "pkg.a", "pkg.b"})
    assert ("pkg.a", "pkg.b") in _pairs(edges)


def test_from_import_targets_module_not_symbol(tmp_path: Path):
    mod = _mod("pkg.a", "from pkg.b import x, y\n", tmp_path)
    edges = extract_import_edges(mod, known_module_ids={"pkg", "pkg.a", "pkg.b"})
    assert ("pkg.a", "pkg.b") in _pairs(edges)
    edge = next(e for e in edges if e.target == "pkg.b")
    assert edge.metadata["kind"] == "from"
    assert edge.metadata["names"] == ["x", "y"]


def test_unknown_module_goes_to_external(tmp_path: Path):
    mod = _mod("pkg.a", "import numpy\n", tmp_path)
    edges = extract_import_edges(mod, known_module_ids={"pkg", "pkg.a"})
    target_names = {e.target for e in edges}
    assert f"{EXTERNAL_PREFIX}.numpy" in target_names


def test_relative_import_from_submodule(tmp_path: Path):
    mod = _mod("pkg.sub.mod", "from . import util\n", tmp_path)
    edges = extract_import_edges(
        mod, known_module_ids={"pkg", "pkg.sub", "pkg.sub.util", "pkg.sub.mod"}
    )
    assert ("pkg.sub.mod", "pkg.sub.util") in _pairs(edges)


def test_relative_import_with_module_name(tmp_path: Path):
    mod = _mod("pkg.sub.mod", "from .other import x\n", tmp_path)
    edges = extract_import_edges(
        mod, known_module_ids={"pkg", "pkg.sub", "pkg.sub.other", "pkg.sub.mod"}
    )
    assert ("pkg.sub.mod", "pkg.sub.other") in _pairs(edges)


def test_relative_import_from_package_init(tmp_path: Path):
    mod = _mod("pkg", "from . import sub\n", tmp_path, is_init=True)
    edges = extract_import_edges(mod, known_module_ids={"pkg", "pkg.sub"})
    assert ("pkg", "pkg.sub") in _pairs(edges)


def test_two_dot_relative_import(tmp_path: Path):
    mod = _mod("pkg.sub.mod", "from ..other import x\n", tmp_path)
    edges = extract_import_edges(
        mod, known_module_ids={"pkg", "pkg.other", "pkg.sub", "pkg.sub.mod"}
    )
    assert ("pkg.sub.mod", "pkg.other") in _pairs(edges)


def test_duplicate_imports_dedupe(tmp_path: Path):
    mod = _mod(
        "pkg.a",
        "from pkg.b import x\nfrom pkg.b import y\nimport pkg.b\n",
        tmp_path,
    )
    edges = extract_import_edges(mod, known_module_ids={"pkg", "pkg.a", "pkg.b"})
    assert sum(1 for e in edges if e.target == "pkg.b") == 1
    edge = next(e for e in edges if e.target == "pkg.b")
    assert set(edge.metadata.get("names", [])) == {"x", "y"}


def test_all_edges_are_imports_type(tmp_path: Path):
    mod = _mod("pkg.a", "import os\nfrom pkg.b import x\n", tmp_path)
    edges = extract_import_edges(mod, known_module_ids={"pkg", "pkg.a", "pkg.b"})
    assert all(e.type == "imports" for e in edges)


def test_no_imports_produces_no_edges(tmp_path: Path):
    mod = _mod("pkg.a", "x = 1\ndef f(): pass\n", tmp_path)
    assert extract_import_edges(mod, known_module_ids={"pkg.a"}) == []


def test_known_prefix_keeps_full_dotted_name(tmp_path: Path):
    """Import of `glom.core` when only `glom` is known should still
    resolve to `glom.core` (not truncate to `glom`)."""
    mod = _mod("app", "import glom.core\n", tmp_path)
    edges = extract_import_edges(mod, known_module_ids={"glom", "app"})
    targets = {e.target for e in edges}
    assert "glom.core" in targets
