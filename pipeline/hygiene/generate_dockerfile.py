"""
Generate a Dockerfile for the target repo.

The template is a static ``.md`` file under ``pipeline/common/prompts/``.
We render it via the same prompt loader the LLM code uses — a template
is a template, regardless of who consumes the output. The base image is
chosen by the ecosystem strategy unless the caller overrides.

Design notes
------------
- We install ``pytest`` and its plugins at *build time* rather than at
  test time. That matches the CodingRL hard-task playbook: an image
  that has to pull test tooling on first run adds seconds to every
  verifier run and, worse, can time out.
- ``PYTHONPATH=/app/src:/app`` handles both src-layout and flat-layout
  repos without conditionals in the Dockerfile.
- ``/tmp/.container_built`` is a sentinel some downstream steps use to
  detect that they're running inside the built image rather than on the
  host — cheaper than parsing ``/proc/1/cgroup``.
"""

from __future__ import annotations

from pathlib import Path

from ..common.ecosystem import EcosystemStrategy
from ..common.prompts.loader import load_prompt

_DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "common" / "prompts"


def generate_dockerfile(
    repo_path: Path,
    strategy: EcosystemStrategy,
    *,
    base: str | None = None,
    template_dir: Path | None = None,
) -> Path:
    tpl = load_prompt("dockerfile", prompts_dir=template_dir or _DEFAULT_TEMPLATE_DIR)
    content = tpl.render(base=base or strategy.dockerfile_base())
    dockerfile = repo_path / "Dockerfile"
    dockerfile.write_text(content)
    return dockerfile
