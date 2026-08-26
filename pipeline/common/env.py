"""
Minimal ``.env`` loader.

Reads ``KEY=VALUE`` pairs from a ``.env`` file at (or above) the
current working directory and pushes them into ``os.environ``. Values
already present in the environment win — shell exports override the
file.

We roll our own tiny parser instead of pulling in ``python-dotenv`` to
keep the dependency surface small. The format we support is a subset:
comments (``#`` at line start), blank lines, ``KEY=VALUE`` with
optional surrounding quotes.
"""

from __future__ import annotations

import os
from pathlib import Path


def find_dotenv(start: Path | None = None) -> Path | None:
    cursor = (start or Path.cwd()).resolve()
    for parent in (cursor, *cursor.parents):
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
    return None


def load_dotenv(path: Path | None = None, *, override: bool = False) -> dict[str, str]:
    """Parse a ``.env`` file into ``os.environ``.

    ``override=False`` (default) preserves existing environment values.
    Returns the mapping actually loaded from the file (useful for
    tests). If no file is found, returns an empty dict.
    """
    if path is None:
        path = find_dotenv()
    if path is None or not path.is_file():
        return {}

    loaded: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]

        loaded[key] = value
        if override or key not in os.environ:
            os.environ[key] = value

    return loaded


def has_real_value(
    key: str,
    *,
    placeholders: tuple[str, ...] = ("your_", "todo", "changeme", "replace_me"),
) -> bool:
    """Return True if ``key`` has a non-placeholder value in the env."""
    value = os.environ.get(key, "").strip()
    if not value:
        return False
    lower = value.lower()
    return not any(lower.startswith(marker.lower()) for marker in placeholders)
