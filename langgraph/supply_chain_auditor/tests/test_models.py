"""Tests for model helpers (PRContext.from_env)."""

from __future__ import annotations

from auditor_core.models import PRContext


def test_from_env_populates_fields():
    pr = PRContext.from_env(
        {
            "PR_REPO": "diagridio/ai-agents",
            "PR_NUMBER": "42",
            "PR_TITLE": "Bump x from 1 to 2",
            "PR_BODY": "body",
        }
    )
    assert pr.repo == "diagridio/ai-agents"
    assert pr.number == 42
    assert pr.title == "Bump x from 1 to 2"
    assert pr.body == "body"


def test_from_env_defaults_number_to_zero_when_absent():
    pr = PRContext.from_env({"PR_REPO": "o/r"})
    assert pr.number == 0


def test_from_env_handles_invalid_number():
    pr = PRContext.from_env({"PR_NUMBER": "not-a-number"})
    assert pr.number == 0


def test_from_env_empty_is_safe():
    pr = PRContext.from_env({})
    assert pr.repo == "" and pr.number == 0
