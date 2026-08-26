"""
HygieneStage — Pipeline 1 orchestrator.

Steps (in order):
    1. Detect ecosystem.
    2. Pin dependencies to exact versions (lockfile).
    3. Generate Dockerfile that installs pinned deps and runs the test suite.
    4. Baseline test run inside the container. Capture pass/fail per test.
    5. Coverage gap analysis. Identify low-coverage modules.
    6. Generate meaningful unit tests for gap modules (LLM + guardrails).
    7. Apply lint and format tooling; auto-fix violations.
    8. Acceptance bar: docker build + run test suite TWICE. Outputs identical.

Outputs live under output/repo/ (the transformed repo) plus a hygiene report
under output/hygiene_report.json.

Phase 0 status: skeleton only.
"""

from __future__ import annotations

from ..common.stage import Stage, StageContext, StageResult


class HygieneStage(Stage):
    name = "hygiene"

    def plan(self, ctx: StageContext) -> dict:
        raise NotImplementedError("Phase 1")

    def run(self, ctx: StageContext) -> StageResult:
        raise NotImplementedError("Phase 1")

    def verify(self, ctx: StageContext) -> bool:
        raise NotImplementedError("Phase 1")
