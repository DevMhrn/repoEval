"""Tests for pipeline.knowledge.extractors.nodes."""

from __future__ import annotations

import ast
from pathlib import Path

from pipeline.knowledge.extractors.nodes import extract_nodes
from pipeline.knowledge.walkers.python import ParsedModule


def _parsed(module_id: str, source: str, tmp_path: Path) -> ParsedModule:
    path = tmp_path / f"{module_id.replace('.', '/')}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    return ParsedModule(path=path, module_id=module_id, tree=ast.parse(source))


def _by_id(nodes, node_id):
    matches = [n for n in nodes if n.id == node_id]
    return matches[0] if matches else None


def test_extracts_module_node(tmp_path: Path):
    mod = _parsed("pkg.core", '"""top docstring."""\nx = 1\n', tmp_path)
    nodes = extract_nodes(mod, repo_root=tmp_path)
    module_node = _by_id(nodes, "pkg.core")
    assert module_node is not None
    assert module_node.type == "module"
    assert module_node.docstring == "top docstring."
    assert module_node.file.endswith("pkg/core.py")


def test_extracts_top_level_function(tmp_path: Path):
    mod = _parsed(
        "pkg.core",
        'def glom(target, spec, **kwargs):\n    """G."""\n    return target\n',
        tmp_path,
    )
    nodes = extract_nodes(mod, repo_root=tmp_path)
    fn = _by_id(nodes, "pkg.core.glom")
    assert fn is not None
    assert fn.type == "function"
    assert fn.signature == "(target, spec, **kwargs)"
    assert fn.docstring == "G."
    assert fn.is_public is True


def test_extracts_class_and_its_methods(tmp_path: Path):
    mod = _parsed(
        "pkg.core",
        (
            "class Spec:\n"
            "    def match(self, x):\n"
            "        return x\n"
            "    def _internal(self):\n"
            "        pass\n"
        ),
        tmp_path,
    )
    nodes = extract_nodes(mod, repo_root=tmp_path)
    cls = _by_id(nodes, "pkg.core.Spec")
    match = _by_id(nodes, "pkg.core.Spec.match")
    internal = _by_id(nodes, "pkg.core.Spec._internal")

    assert cls and cls.type == "class"
    assert match and match.type == "method"
    assert match.signature == "(self, x)"
    assert internal and internal.type == "method"
    assert internal.is_public is False


def test_underscore_names_are_private(tmp_path: Path):
    mod = _parsed(
        "pkg.core", "def _helper(): pass\n", tmp_path
    )
    nodes = extract_nodes(mod, repo_root=tmp_path)
    fn = _by_id(nodes, "pkg.core._helper")
    assert fn.is_public is False


def test_async_functions_are_extracted(tmp_path: Path):
    mod = _parsed(
        "pkg.core", "async def fetch(url):\n    return url\n", tmp_path
    )
    nodes = extract_nodes(mod, repo_root=tmp_path)
    fn = _by_id(nodes, "pkg.core.fetch")
    assert fn is not None
    assert fn.type == "function"
    assert fn.signature == "(url)"


def test_nested_functions_not_extracted(tmp_path: Path):
    mod = _parsed(
        "pkg.core",
        (
            "def outer(x):\n"
            "    def inner(y):\n"
            "        return y\n"
            "    return inner(x)\n"
        ),
        tmp_path,
    )
    ids = {n.id for n in extract_nodes(mod, repo_root=tmp_path)}
    assert "pkg.core.outer" in ids
    assert "pkg.core.outer.inner" not in ids


def test_nested_class_produces_dotted_id(tmp_path: Path):
    mod = _parsed(
        "pkg.core",
        (
            "class Outer:\n"
            "    class Inner:\n"
            "        def m(self):\n"
            "            pass\n"
        ),
        tmp_path,
    )
    ids = {n.id for n in extract_nodes(mod, repo_root=tmp_path)}
    assert "pkg.core.Outer" in ids
    assert "pkg.core.Outer.Inner" in ids
    assert "pkg.core.Outer.Inner.m" in ids


def test_line_spans_recorded(tmp_path: Path):
    src = "def a():\n    return 1\n\ndef b():\n    return 2\n"
    mod = _parsed("m", src, tmp_path)
    nodes = extract_nodes(mod, repo_root=tmp_path)
    a = _by_id(nodes, "m.a")
    b = _by_id(nodes, "m.b")
    assert a.line == 1
    assert a.end_line == 2
    assert b.line == 4
    assert b.end_line == 5


def test_module_without_docstring_has_none(tmp_path: Path):
    mod = _parsed("m", "x = 1\n", tmp_path)
    node = _by_id(extract_nodes(mod, repo_root=tmp_path), "m")
    assert node.docstring is None


def test_signature_captures_defaults_and_kwargs(tmp_path: Path):
    mod = _parsed(
        "m",
        "def f(a, b=1, *, c=None, **kw):\n    return None\n",
        tmp_path,
    )
    fn = _by_id(extract_nodes(mod, repo_root=tmp_path), "m.f")
    assert fn.signature == "(a, b=1, *, c=None, **kw)"


def test_file_path_is_relative_to_repo_root(tmp_path: Path):
    src = tmp_path / "pkg" / "core.py"
    src.parent.mkdir()
    src.write_text("def x(): pass\n")
    parsed = ParsedModule(path=src, module_id="pkg.core", tree=ast.parse("def x(): pass\n"))
    nodes = extract_nodes(parsed, repo_root=tmp_path)
    assert all(n.file == "pkg/core.py" for n in nodes)
