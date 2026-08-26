"""
Structured logging.

Every stage emits JSONL events to two sinks:
- stderr (for humans, pretty-printed via rich)
- a per-run JSONL file under evidence/<stage>/<timestamp>.jsonl

Event shape:
    {"ts": iso8601, "stage": "hygiene", "event": "step.start",
     "step": "pin_deps", "data": {...}}

Rationale
---------
Structured events feed three consumers: the human running the pipeline,
the transcripts/ deliverable, and the validation harness that grades
each task's evidence.

Phase 0 status: STUB — implemented in Phase 1.
"""

from __future__ import annotations

from pathlib import Path


def get_logger(stage: str, run_id: str, sink_dir: Path):
    raise NotImplementedError("Phase 1")
