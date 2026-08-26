"""
Excision candidate mining.

Picks functions and methods that are:

- Well-tested (high line-rate coverage AND referenced by test modules).
- Non-trivial in size (LOC in a configurable band).
- Public API surface (name doesn't start with underscore).

Scores each on a mix of coverage strength, test-reference count, size
sweet spot, and an algorithmic-content heuristic (loops, conditionals,
arithmetic). The score is a hint — the selector in Phase 3.14 makes
the final call along with diversity constraints.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ...knowledge.schema import Node, RepoGraph


@dataclass
class ExcisionCandidate:
    node_id: str
    file: str
    line: int
    end_line: int
    signature: str
    docstring: str
    body_loc: int
    line_rate: float = 0.0
    tests_ref_count: int = 0
    algorithmic_score: float = 0.0
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)


def mine_excision(
    graph: RepoGraph,
    repo_path: Path,
    *,
    limit: int = 20,
    min_line_rate: float = 0.8,
    min_body_loc: int = 10,
    max_body_loc: int = 80,
    min_tests_ref: int = 1,
) -> list[ExcisionCandidate]:
    tests_ref_by_id = _count_test_refs(graph)

    candidates: list[ExcisionCandidate] = []
    for node in graph.nodes:
        if node.type not in ("function", "method"):
            continue
        if not node.is_public:
            continue

        body_loc = node.end_line - node.line
        if body_loc < min_body_loc or body_loc > max_body_loc:
            continue

        line_rate = _line_rate(node)
        if line_rate < min_line_rate:
            continue

        tests_ref = tests_ref_by_id.get(node.id, 0)
        if tests_ref < min_tests_ref:
            continue

        candidate = ExcisionCandidate(
            node_id=node.id,
            file=node.file,
            line=node.line,
            end_line=node.end_line,
            signature=node.signature or "",
            docstring=node.docstring or "",
            body_loc=body_loc,
            line_rate=line_rate,
            tests_ref_count=tests_ref,
            algorithmic_score=_algorithmic_score(repo_path, node),
        )
        _score(candidate)
        candidates.append(candidate)

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:limit]


def _line_rate(node: Node) -> float:
    coverage = node.metadata.get("coverage", {})
    return float(coverage.get("line_rate", 0.0))


def _count_test_refs(graph: RepoGraph) -> dict[str, int]:
    counts: dict[str, int] = {}
    for edge in graph.edges:
        if not _is_test_source(edge.source):
            continue
        counts[edge.target] = counts.get(edge.target, 0) + 1
    return counts


def _is_test_source(node_id: str) -> bool:
    for part in node_id.split("."):
        if part in ("tests", "test"):
            return True
        if part.startswith("test_") or part.endswith("_test"):
            return True
    return False


def _algorithmic_score(repo_path: Path, node: Node) -> float:
    src = repo_path / node.file
    if not src.exists():
        return 0.0
    try:
        lines = src.read_text().splitlines()
    except (OSError, UnicodeDecodeError):
        return 0.0
    if node.line - 1 >= len(lines):
        return 0.0
    body = "\n".join(lines[node.line - 1 : node.end_line])

    markers = (
        "for ",
        "while ",
        "if ",
        "elif ",
        "return ",
        " + ",
        " - ",
        " * ",
        " / ",
        " == ",
        " != ",
        " and ",
        " or ",
    )
    signals = sum(body.count(marker) for marker in markers)
    return round(min(1.0, signals * 0.05), 3)


def _score(candidate: ExcisionCandidate) -> None:
    reasons: list[str] = []
    score = 0.0

    coverage_bonus = max(0.0, (candidate.line_rate - 0.8) * 2)
    score += coverage_bonus
    reasons.append(f"line_rate={candidate.line_rate}")

    ref_bonus = min(0.2, candidate.tests_ref_count * 0.05)
    score += ref_bonus
    reasons.append(f"tests_ref={candidate.tests_ref_count}")

    if 20 <= candidate.body_loc <= 50:
        score += 0.2
        reasons.append("body_loc in sweet spot")
    else:
        score += 0.1

    score += candidate.algorithmic_score
    reasons.append(f"algorithmic={candidate.algorithmic_score}")

    candidate.score = round(score, 3)
    candidate.reasons = reasons
