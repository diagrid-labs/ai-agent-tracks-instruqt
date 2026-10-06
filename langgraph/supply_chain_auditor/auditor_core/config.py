"""Shared configuration constants.

Kept in :mod:`auditor_core` so both framework entry points read one value (and the
CI drift check keeps the two vendored copies in sync).
"""

from __future__ import annotations

# Claude model used for the analysis step; override per run with $LLM_MODEL.
DEFAULT_LLM_MODEL = "claude-sonnet-4-6"
# Max output tokens for the analysis step; override with $LLM_MAX_TOKENS.
DEFAULT_MAX_TOKENS = 8000
