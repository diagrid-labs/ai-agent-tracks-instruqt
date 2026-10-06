"""Append-only durability-demo ledger.

Records each genuinely-executed pipeline stage as one line in ``audit-ledger.log``.
Because every LangGraph node runs as a checkpointed Dapr Workflow activity, a
completed stage replays from durable history and its body is not re-executed on
resume — so a stage recorded here appears exactly once across a crash-and-restart,
proving the expensive ``analyze`` (Claude) call is not repeated.

This is demo infrastructure, kept out of the drift-checked ``auditor_core`` package.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

_LEDGER_FILENAME = "audit-ledger.log"
_APPEND_LOCK = threading.Lock()


@dataclass
class LedgerEntry:
    timestamp: str
    stage: str
    detail: str


def output_dir() -> str:
    """Directory the ledger (and report) are written to; overridable via env."""
    return os.environ.get("AUDIT_OUTPUT_DIR") or "audit-out"


def _ledger_path() -> str:
    return os.path.join(output_dir(), _LEDGER_FILENAME)


def _sanitize(value: str) -> str:
    return value.replace("\t", " ").replace("\r", " ").replace("\n", " ")


def record_stage(stage: str, detail: str) -> None:
    """Append one tab-separated line recording that ``stage`` executed."""
    timestamp = datetime.now(timezone.utc).isoformat()
    line = "\t".join((timestamp, _sanitize(stage), _sanitize(detail)))
    with _APPEND_LOCK:
        os.makedirs(output_dir(), exist_ok=True)
        with open(_ledger_path(), "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def _parse(line: str) -> LedgerEntry | None:
    if not line or not line.strip():
        return None
    parts = line.rstrip("\n").split("\t", 2)
    if len(parts) < 2:
        return None
    timestamp, stage = parts[0], parts[1]
    if not timestamp or not stage:
        return None
    detail = parts[2] if len(parts) > 2 else ""
    return LedgerEntry(timestamp=timestamp, stage=stage, detail=detail)


def read_entries() -> list[LedgerEntry]:
    """Parse the ledger, skipping blank/malformed lines. Empty if absent."""
    path = _ledger_path()
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    return [entry for entry in (_parse(line) for line in lines) if entry is not None]


def count() -> int:
    """Number of recorded stages; used by the durability-demo crash gate."""
    with _APPEND_LOCK:
        return len(read_entries())
