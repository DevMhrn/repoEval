"""Tests for pipeline.knowledge.walkers.python."""

from __future__ import annotations

from pathlib import Path

from pipeline.knowledge.walkers.python import (
    ParsedModule,
    _derive_module_id,
    walk_python,
)


def test_yields_parsed_modules_for_package(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    (tmp_path / "pkg" / "core.py").write_text("def x(): pass\n")

    modules = list(walk_python(tmp_path))
    ids = {m.module_id for m in modules}
    assert "pkg" in ids
    assert "pkg.core" in ids


def test_skips_common_dirs(tmp_path: Path):
    for skip_name in (".venv", "__pycache__", "build", ".git"):
        d = tmp_path / skip_name
        d.mkdir()
        (d / "ignored.py").write_text("pass\n")
    (tmp_path / "real.py").write_text("x = 1\n")

    modules = list(walk_python(tmp_path))
    ids = {m.module_id for m in modules}
    assert "real" in ids
    assert not any(
        any(part == skip for part in m.path.parts)
        for m in modules
        for skip in (".venv", "__pycache__", "build", ".git")
    )


def test_handles_src_layout(tmp_path: Path):
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")
    (src / "core.py").write_text("")

    ids = {m.module_id for m in walk_python(tmp_path)}
    assert "pkg" in ids
    assert "pkg.core" in ids


def test_syntax_errors_are_skipped_not_fatal(tmp_path: Path):
    (tmp_path / "good.py").write_text("def x(): pass\n")
    (tmp_path / "broken.py").write_text("def broken(:\n")
    ids = {m.module_id for m in walk_python(tmp_path)}
    assert "good" in ids
    assert "broken" not in ids


def test_is_test_property_recognises_test_files(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__init__.py").write_text("")
    (tmp_path / "tests" / "test_x.py").write_text("")
    (tmp_path / "core.py").write_text("")

    modules = list(walk_python(tmp_path))
    tests = [m for m in modules if m.module_id == "tests.test_x"]
    core = [m for m in modules if m.module_id == "core"]
    assert tests and tests[0].is_test is True
    assert core and core[0].is_test is False


def test_skip_tests_flag_excludes_tests(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__init__.py").write_text("")
    (tmp_path / "tests" / "test_x.py").write_text("")
    (tmp_path / "core.py").write_text("")

    ids = {m.module_id for m in walk_python(tmp_path, skip_tests=True)}
    assert "core" in ids
    assert "tests.test_x" not in ids


def test_yields_sorted_by_path(tmp_path: Path):
    (tmp_path / "z.py").write_text("")
    (tmp_path / "a.py").write_text("")
    (tmp_path / "m.py").write_text("")

    modules = list(walk_python(tmp_path))
    paths = [m.path.name for m in modules]
    assert paths == sorted(paths)


def test_source_roots_restricts_search(tmp_path: Path):
    a = tmp_path / "sub_a"
    b = tmp_path / "sub_b"
    a.mkdir()
    b.mkdir()
    (a / "in_a.py").write_text("pass\n")
    (b / "in_b.py").write_text("pass\n")

    modules = list(walk_python(tmp_path, source_roots=[a]))
    ids = {m.module_id for m in modules}
    assert any("in_a" in i for i in ids)
    assert not any("in_b" in i for i in ids)


def test_derive_module_id_strips_src_prefix(tmp_path: Path):
    src_path = tmp_path / "src" / "pkg" / "core.py"
    src_path.parent.mkdir(parents=True)
    src_path.write_text("")
    assert _derive_module_id(src_path, tmp_path) == "pkg.core"


def test_derive_module_id_strips_init(tmp_path: Path):
    p = tmp_path / "pkg" / "__init__.py"
    p.parent.mkdir()
    p.write_text("")
    assert _derive_module_id(p, tmp_path) == "pkg"


def test_parsed_module_tree_is_usable(tmp_path: Path):
    p = tmp_path / "m.py"
    p.write_text("def hello(): return 42\n")
    m = next(walk_python(tmp_path))
    assert isinstance(m, ParsedModule)
    assert any(
        n.name == "hello"
        for n in m.tree.body
        if hasattr(n, "name")
    )


def test_empty_directory_yields_nothing(tmp_path: Path):
    assert list(walk_python(tmp_path)) == []
