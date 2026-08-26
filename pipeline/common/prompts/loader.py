"""
Prompt template loader.

Templates are ``.md`` files under ``pipeline/common/prompts/``. Two
optional features:

- A YAML-lite front-matter block delimited by ``---`` lines carries
  ``key: value`` metadata (name, purpose, inputs, outputs).
- Body placeholders use ``{name}`` syntax and are filled by
  :meth:`PromptTemplate.render` via ``str.format_map`` with a permissive
  dict that leaves unknown keys as literal ``{unknown}`` rather than
  raising. That prevents a rename in one call site from silently
  breaking every prompt at once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class PromptNotFoundError(Exception):
    pass


class PromptRenderError(Exception):
    pass


@dataclass
class PromptTemplate:
    name: str
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def render(self, **vars: Any) -> str:
        try:
            return self.body.format_map(_SafeDict(vars))
        except (IndexError, ValueError) as e:
            raise PromptRenderError(
                f"failed to render {self.name}: {e}"
            ) from e


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def load_prompt(name: str, *, prompts_dir: Path) -> PromptTemplate:
    path = prompts_dir / f"{name}.md"
    if not path.exists():
        raise PromptNotFoundError(f"prompt template not found: {path}")

    raw = path.read_text()
    metadata: dict[str, Any] = {}
    body = raw

    if raw.startswith("---\n"):
        end = raw.find("\n---\n", 4)
        if end == -1:
            raise PromptRenderError(f"unterminated front-matter in {path}")
        front = raw[4:end]
        body = raw[end + 5 :]
        for line in front.splitlines():
            line = line.strip()
            if not line or ":" not in line:
                continue
            k, _, v = line.partition(":")
            metadata[k.strip()] = v.strip()

    return PromptTemplate(name=name, body=body.strip() + "\n", metadata=metadata)
