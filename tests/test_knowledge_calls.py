"""Tests for pipeline.knowledge.extractors.calls."""

from __future__ import annotations

import ast
from pathlib import Path

from pipeline.knowledge.extractors.calls import extract_call_edges
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


def test_direct_call_to_top_level_function(tmp_path: Path):
    mod = _mod(
        "pkg.core",
        (
            "def helper(): return 1\n"
            "def caller():\n"
            "    return helper()\n"
        ),
        tmp_path,
    )
    known = {"pkg.core", "pkg.core.helper", "pkg.core.caller"}
    edges = extract_call_edges(mod, known_node_ids=known)
    assert ("pkg.core.caller", "pkg.core.helper") in _pairs(edges)


def test_method_calling_other_method_resolves_when_known(tmp_path: Path):
    mod = _mod(
        "pkg.core",
        (
            "class C:\n"
            "    def a(self):\n"
            "        return 1\n"
            "    def b(self):\n"
            "        return self.a()\n"
        ),
        tmp_path,
    )
    known = {"pkg.core.C", "pkg.core.C.a", "pkg.core.C.b"}
    edges = extract_call_edges(mod, known_node_ids=known)
    # self.a() — head is 'self' which isn't in name_map; won't resolve.
    # This documents the limitation.
    assert ("pkg.core.C.b", "pkg.core.C.a") not in _pairs(edges)


def test_call_to_imported_symbol(tmp_path: Path):
    mod = _mod(
        "app.main",
        (
            "from pkg.util import helper\n"
            "def caller():\n"
            "    return helper()\n"
        ),
        tmp_path,
    )
    known = {"pkg.util.helper", "app.main.caller"}
    edges = extract_call_edges(mod, known_node_ids=known)
    assert ("app.main.caller", "pkg.util.helper") in _pairs(edges)


def test_qualified_call_pkg_util_helper(tmp_path: Path):
    mod = _mod(
        "app.main",
        (
            "import pkg.util\n"
            "def caller():\n"
            "    return pkg.util.helper()\n"
        ),
        tmp_path,
    )
    known = {"pkg.util.helper", "app.main.caller"}
    edges = extract_call_edges(mod, known_node_ids=known)
    assert ("app.main.caller", "pkg.util.helper") in _pairs(edges)


def test_unresolved_call_produces_no_edge(tmp_path: Path):
    mod = _mod(
        "pkg.core",
        "def caller():\n    return random_function()\n",
        tmp_path,
    )
    known = {"pkg.core.caller"}
    assert extract_call_edges(mod, known_node_ids=known) == []


def test_repeated_call_increments_weight(tmp_path: Path):
    mod = _mod(
        "pkg.core",
        (
            "def helper(): return 1\n"
            "def caller():\n"
            "    helper()\n"
            "    helper()\n"
            "    return helper()\n"
        ),
        tmp_path,
    )
    known = {"pkg.core.helper", "pkg.core.caller"}
    edges = extract_call_edges(mod, known_node_ids=known)
    edge = next(e for e in edges if e.source == "pkg.core.caller")
    assert edge.weight == 3.0


def test_self_recursion_not_recorded(tmp_path: Path):
    mod = _mod(
        "pkg.core",
        "def fact(n):\n    return 1 if n <= 1 else n * fact(n - 1)\n",
        tmp_path,
    )
    known = {"pkg.core.fact"}
    edges = extract_call_edges(mod, known_node_ids=known)
    assert edges == []


def test_alias_import_resolves_to_original_target(tmp_path: Path):
    mod = _mod(
        "app",
        (
            "from pkg import helper as h\n"
            "def caller():\n"
            "    return h()\n"
        ),
        tmp_path,
    )
    known = {"pkg.helper", "app.caller"}
    edges = extract_call_edges(mod, known_node_ids=known)
    assert ("app.caller", "pkg.helper") in _pairs(edges)


def test_call_to_external_symbol_not_in_known_is_dropped(tmp_path: Path):
    mod = _mod(
        "pkg.core",
        (
            "import os\n"
            "def caller():\n"
            "    return os.path.join('a', 'b')\n"
        ),
        tmp_path,
    )
    known = {"pkg.core.caller"}
    assert extract_call_edges(mod, known_node_ids=known) == []


def test_edges_sorted_by_source_then_target(tmp_path: Path):
    mod = _mod(
        "pkg.core",
        (
            "def a(): pass\n"
            "def b(): pass\n"
            "def c():\n"
            "    b(); a()\n"
        ),
        tmp_path,
    )
    known = {"pkg.core.a", "pkg.core.b", "pkg.core.c"}
    edges = extract_call_edges(mod, known_node_ids=known)
    keys = [(e.source, e.target) for e in edges]
    assert keys == sorted(keys)


def test_class_method_calling_class_method_via_class_name(tmp_path: Path):
    mod = _mod(
        "pkg.core",
        (
            "class C:\n"
            "    def a(self): pass\n"
            "    def b(self):\n"
            "        C.a(self)\n"
        ),
        tmp_path,
    )
    known = {"pkg.core.C", "pkg.core.C.a", "pkg.core.C.b"}
    edges = extract_call_edges(mod, known_node_ids=known)
    # C.a resolves through name_map (C -> pkg.core.C, then .a)
    assert ("pkg.core.C.b", "pkg.core.C.a") in _pairs(edges)
