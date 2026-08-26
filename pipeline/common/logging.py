"""
Structured logging.

Every stage emits JSONL events to two sinks:
- stderr (rich-formatted human-readable line, colour by severity)
- a per-run JSONL file at ``<sink_dir>/<stage>/<run_id>.jsonl``

Event record shape::

    {
      "ts": iso8601,
      "run_id": "hygiene-20260115-103000-abcd",
      "stage": "hygiene",
      "event": "step.start",
      "data": {"step": "pin_deps", ...}
    }

Rationale
---------
Structured events feed three consumers: the human running the pipeline,
the transcripts/ deliverable populated from LLM sessions, and the
validation harness that grades each task's evidence folder.

The ``run_id`` generator takes an explicit ``ts`` so the caller controls
when time is captured. That keeps the id stable across retries and lets
tests pin the id without patching the clock.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from rich.console import Console

_LEVEL_STYLES: dict[str, str] = {
    "info": "cyan",
    "step_start": "cyan",
    "step_end_ok": "green",
    "step_end_fail": "red",
    "error": "bold red",
    "warn": "yellow",
}


def make_run_id(
    stage: str,
    ts: datetime,
    *,
    entropy_source: str | None = None,
) -> str:
    """Return a run id of the form ``<stage>-YYYYMMDD-HHMMSS-<hex>``.

    ``entropy_source`` overrides the random suffix; tests supply it for
    deterministic ids. Production callers omit it and get a fresh 4-char
    hex tag.
    """
    suffix = entropy_source if entropy_source is not None else secrets.token_hex(2)
    return f"{stage}-{ts.strftime('%Y%m%d-%H%M%S')}-{suffix}"


@dataclass
class Logger:
    """Writes JSONL events to a sink file and mirrors a summary line to a
    rich Console.

    Prefer constructing via :func:`get_logger` rather than instantiating
    directly; ``get_logger`` handles the sink path convention.
    """

    stage: str
    run_id: str
    sink_path: Path
    console: Console
    _fh: TextIO | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.sink_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.sink_path.open("a", encoding="utf-8")

    def _emit(
        self,
        event: str,
        data: dict[str, Any],
        *,
        style: str = "info",
    ) -> None:
        if self._fh is None:
            raise RuntimeError("logger is closed")
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "run_id": self.run_id,
            "stage": self.stage,
            "event": event,
            "data": data,
        }
        self._fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._fh.flush()

        colour = _LEVEL_STYLES.get(style, "white")
        summary = str(data.get("step") or data.get("message") or "")
        self.console.print(
            f"[{self.stage}] {event} {summary}".rstrip(),
            style=colour,
            markup=False,
        )

    def event(self, name: str, **data: Any) -> None:
        self._emit(name, data)

    def step_start(self, name: str, **data: Any) -> None:
        payload = {"step": name, **data}
        self._emit("step.start", payload, style="step_start")

    def step_end(self, name: str, ok: bool = True, **data: Any) -> None:
        payload = {"step": name, "ok": ok, **data}
        style = "step_end_ok" if ok else "step_end_fail"
        self._emit("step.end", payload, style=style)

    def error(self, msg: str, **data: Any) -> None:
        payload = {"message": msg, **data}
        self._emit("error", payload, style="error")

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def __enter__(self) -> Logger:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def get_logger(
    stage: str,
    run_id: str,
    sink_dir: Path,
    *,
    console: Console | None = None,
) -> Logger:
    """Return a Logger writing to ``sink_dir/<stage>/<run_id>.jsonl``.

    ``console`` defaults to a stderr Console; tests may supply a Console
    backed by a ``StringIO`` to capture output.
    """
    sink_path = sink_dir / stage / f"{run_id}.jsonl"
    return Logger(
        stage=stage,
        run_id=run_id,
        sink_path=sink_path,
        console=console or Console(stderr=True),
    )
