"""
KnowledgeStage — Pipeline 2 orchestrator.

Emits ``output/repo_graph.json`` and ``output/.okf/*.json`` from a
repo already prepared by Pipeline 1. The stage is idempotent through
the base :class:`Stage.execute` wrapper.

Best-effort enrichments (coverage, LLM summaries) skip cleanly when
their inputs are missing — coverage report absent means no coverage
metadata, LLM in replay mode with no fixtures means no summaries.
The stage still succeeds and the core graph still lands.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..common.ecosystem import detect
from ..common.llm_client import LLMClient, MissingFixtureError
from ..common.stage import Stage, StageContext, StageResult
from .build_graph import build_graph
from .enrich_coverage import enrich_with_coverage
from .enrich_git import enrich_with_git
from .enrich_llm import enrich_with_llm
from .freeze import freeze_repo_graph
from .okf import extract_module_facts, write_okf
from .schema import RepoGraph


class KnowledgeStage(Stage):
    name = "knowledge"
    config_keys = ("knowledge", "llm")

    def plan(self, ctx: StageContext) -> dict[str, Any]:
        return {
            "stage": self.name,
            "target": str(ctx.repo_path),
            "steps": [
                "walk_python",
                "extract_nodes",
                "extract_edges",
                "enrich_git",
                "enrich_coverage",
                "enrich_llm",
                "extract_okf",
                "freeze",
            ],
        }

    def verify(self, ctx: StageContext) -> bool:
        graph_path = self._graph_path(ctx)
        okf_dir = self._okf_dir(ctx)
        if not graph_path.exists():
            return False
        if not okf_dir.exists() or not any(okf_dir.iterdir()):
            return False
        try:
            RepoGraph.model_validate_json(graph_path.read_text())
        except Exception:  # noqa: BLE001
            return False
        return True

    def run(self, ctx: StageContext) -> StageResult:
        outputs: dict[str, str] = {}
        try:
            strategy = detect(ctx.repo_path)
            skip_tests = not ctx.config.get("knowledge", {}).get(
                "include_test_files", False
            )
            graph, _ = build_graph(
                ctx.repo_path,
                strategy=strategy,
                repo_name=str(ctx.repo_path),
                commit=ctx.extra.get("commit", ""),
                generated_at=ctx.extra.get("generated_at"),
                skip_tests=skip_tests,
            )

            graph = enrich_with_git(graph, ctx.repo_path)

            coverage_report = ctx.workspace / "coverage_report.json"
            if coverage_report.exists():
                graph = enrich_with_coverage(graph, coverage_report)

            graph = self._maybe_enrich_with_llm(graph, ctx)

            facts = extract_module_facts(graph)
            okf_dir = self._okf_dir(ctx)
            for path in write_okf(facts, okf_dir):
                outputs[str(path)] = "okf"

            graph_path = self._graph_path(ctx)
            freeze_repo_graph(graph, graph_path)
            outputs[str(graph_path)] = "graph"

            return StageResult(
                stage=self.name, success=True, outputs=outputs
            )
        except Exception as e:  # noqa: BLE001
            return StageResult(
                stage=self.name, success=False, error=str(e)
            )

    def _maybe_enrich_with_llm(
        self, graph: RepoGraph, ctx: StageContext
    ) -> RepoGraph:
        llm_config = ctx.config.get("llm", {})
        fixtures_dir = ctx.workspace.parent / llm_config.get(
            "fixtures_dir", "fixtures/llm"
        )
        try:
            llm = LLMClient(
                mode=llm_config.get("mode", "replay"),
                model=llm_config.get("model", "claude-sonnet-5"),
                fixtures_dir=fixtures_dir,
                temperature=llm_config.get("temperature", 0.0),
            )
            return enrich_with_llm(graph, llm)
        except MissingFixtureError:
            # replay mode without seeded fixtures → skip cleanly
            return graph
        except Exception:  # noqa: BLE001 — LLM enrichment is optional
            return graph

    def _graph_path(self, ctx: StageContext) -> Path:
        return ctx.workspace / "repo_graph.json"

    def _okf_dir(self, ctx: StageContext) -> Path:
        return ctx.workspace / ".okf"
