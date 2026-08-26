"""
Config loader.

Reads repoeval.toml at the workspace root and deep-merges an optional sibling
repoeval.local.toml on top. Returns a typed Config object used by every
stage.

Contracts
---------
- If the primary config file is missing, we fail loudly. Never silently
  fall back to hardcoded defaults — that would hide misconfiguration.
- repoeval.local.toml is optional and never checked in; used for per-machine
  overrides (API keys, workspace paths). Overlay values win at every level.
- CLI overrides are applied last through `Config.override()` and take
  precedence over both files.
"""

from __future__ import annotations

import copy
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_TABLES: tuple[str, ...] = (
    "general",
    "llm",
    "docker",
    "hygiene",
    "knowledge",
    "tasks",
    "validator",
)

_REDACT_MARKERS: frozenset[str] = frozenset({
    "key",
    "token",
    "secret",
    "password",
    "credential",
})

_MISSING = object()


class ConfigError(Exception):
    """Raised when the config is missing, malformed, or misses required keys."""


@dataclass
class Config:
    """Typed access to repoeval.toml.

    Sub-table accessors (`llm()`, `docker()`, …) return raw dicts. Individual
    stages validate the keys they consume; we don't try to model every field
    here because the surface area evolves phase by phase.
    """

    config_path: Path
    raw: dict[str, Any]
    local_path: Path | None = None

    def get(self, dotted_key: str, default: Any = _MISSING) -> Any:
        cur: Any = self.raw
        for part in dotted_key.split("."):
            if not isinstance(cur, dict) or part not in cur:
                if default is _MISSING:
                    raise ConfigError(f"missing key: {dotted_key}")
                return default
            cur = cur[part]
        return cur

    def override(self, overrides: dict[str, Any]) -> Config:
        new_raw = copy.deepcopy(self.raw)
        for dotted, value in overrides.items():
            _set_dotted(new_raw, dotted, value)
        return Config(
            config_path=self.config_path,
            raw=new_raw,
            local_path=self.local_path,
        )

    def general(self) -> dict[str, Any]:
        return self.raw["general"]

    def llm(self) -> dict[str, Any]:
        return self.raw["llm"]

    def docker(self) -> dict[str, Any]:
        return self.raw["docker"]

    def hygiene(self) -> dict[str, Any]:
        return self.raw["hygiene"]

    def knowledge(self) -> dict[str, Any]:
        return self.raw["knowledge"]

    def tasks(self) -> dict[str, Any]:
        return self.raw["tasks"]

    def validator(self) -> dict[str, Any]:
        return self.raw["validator"]

    def pretty(self) -> str:
        lines = [f"# {self.config_path}"]
        if self.local_path:
            lines.append(f"# + local overrides: {self.local_path}")
        lines.append("")
        for dotted, value in _iter_flat(self.raw):
            display = _redact_value(dotted, value)
            lines.append(f"{dotted} = {_toml_repr(display)}")
        return "\n".join(lines)


def load(path: Path) -> Config:
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")

    raw = tomllib.loads(path.read_text())

    local_path = path.parent / "repoeval.local.toml"
    local_used: Path | None = None
    if local_path.exists():
        overlay = tomllib.loads(local_path.read_text())
        raw = _deep_merge(raw, overlay)
        local_used = local_path

    missing = [t for t in REQUIRED_TABLES if t not in raw]
    if missing:
        raise ConfigError(
            f"missing required top-level tables: {missing}"
        )

    return Config(config_path=path, raw=raw, local_path=local_used)


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = dict(base)
    for k, v in overlay.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def _set_dotted(d: dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    cur = d
    for part in parts[:-1]:
        if part not in cur or not isinstance(cur[part], dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value


def _iter_flat(obj: Any, prefix: str = ""):
    if isinstance(obj, dict):
        for k in sorted(obj.keys()):
            child_prefix = f"{prefix}.{k}" if prefix else k
            yield from _iter_flat(obj[k], child_prefix)
    else:
        yield prefix, obj


def _redact_value(dotted_key: str, value: Any) -> Any:
    last = dotted_key.rsplit(".", 1)[-1].lower()
    if set(last.split("_")) & _REDACT_MARKERS:
        return "<redacted>"
    return value


def _toml_repr(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return f'"{v}"'
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_toml_repr(x) for x in v) + "]"
    return str(v)
