"""
OKF — per-module fact bundles.

For each module node in the graph, aggregate the facts Pipeline 3
cares about into a small JSON. One file per module under
``output/.okf/``. Downstream miners can iterate per-module without
loading the whole graph.

The bundle intentionally omits raw source and full commit history —
those live in the code and in git respectively. What's here is
distilled, indexed, and ready to feed a scoring function.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .schema import RepoGraph


@dataclass
class ModuleFacts:
    module: str
    file: str
    loc: int
    functions: list[str] = field(default_factory=list)
    public_functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    coverage: float | None = None
    tests_ref_count: int = 0
    recent_commits: list[str] = field(default_factory=list)
    summary: str = ""
    complexity_hint: str = "medium"


def extract_module_facts(graph: RepoGraph) -> dict[str, ModuleFacts]:
    modules = [n for n in graph.nodes if n.type == "module"]
    facts_by_module: dict[str, ModuleFacts] = {}

    for mod in modules:
        if mod.id.startswith("<external>"):
            continue
        if _is_test_id(mod.id):
            continue

        functions, public_functions, classes = _direct_members(graph, mod.id)
        coverage = mod.metadata.get("coverage", {}).get("line_rate")

        facts = ModuleFacts(
            module=mod.id,
            file=mod.file,
            loc=mod.end_line,
            functions=sorted(functions),
            public_functions=sorted(public_functions),
            classes=sorted(classes),
            coverage=coverage,
            tests_ref_count=_count_test_refs(graph, mod.id),
            recent_commits=_recent_commits(mod),
            summary=str(mod.metadata.get("summary", "")).strip(),
            complexity_hint=_complexity_hint(
                mod.end_line, len(functions) + len(classes)
            ),
        )
        facts_by_module[mod.id] = facts

    return facts_by_module


def write_okf(
    facts_by_module: dict[str, ModuleFacts], okf_dir: Path
) -> list[Path]:
    okf_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for module_id, facts in sorted(facts_by_module.items()):
        target = okf_dir / f"{module_id}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(asdict(facts), indent=2, sort_keys=True)
        )
        written.append(target)
    return written


def _direct_members(
    graph: RepoGraph, module_id: str
) -> tuple[list[str], list[str], list[str]]:
    prefix = f"{module_id}."
    functions: list[str] = []
    public_functions: list[str] = []
    classes: list[str] = []
    for node in graph.nodes:
        if not node.id.startswith(prefix):
            continue
        rest = node.id[len(prefix) :]
        if "." in rest:
            continue  # nested (method or nested class) — skip
        if node.type == "function":
            functions.append(rest)
            if node.is_public:
                public_functions.append(rest)
        elif node.type == "class":
            classes.append(rest)
    return functions, public_functions, classes


def _count_test_refs(graph: RepoGraph, module_id: str) -> int:
    prefix = f"{module_id}."
    count = 0
    for edge in graph.edges:
        if not _is_test_id(edge.source):
            continue
        if edge.target == module_id or edge.target.startswith(prefix):
            count += 1
    return count


def _is_test_id(node_id: str) -> bool:
    for part in node_id.split("."):
        if part in ("tests", "test"):
            return True
        if part.startswith("test_") or part.endswith("_test"):
            return True
    return False


def _recent_commits(node) -> list[str]:
    git_meta = node.metadata.get("git", {}) if isinstance(node.metadata, dict) else {}
    last = git_meta.get("last_commit")
    return [last] if last else []


def _complexity_hint(loc: int, def_count: int) -> str:
    if loc > 500 or def_count > 30:
        return "high"
    if loc > 100 or def_count > 10:
        return "medium"
    return "low"
