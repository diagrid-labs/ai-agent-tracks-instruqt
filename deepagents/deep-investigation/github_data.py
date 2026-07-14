"""Loader for the pre-baked local GitHub snapshot produced by the
github-collector tool (see tools/github-collector/collect_github_data.py
in dapr-university-instruqt) at build time.

In the Instruqt sandbox this reads from /opt/track-data/dapr/dapr.
Override the root with TRACK_DATA_DIR for local development.
"""
import json
import os
from functools import lru_cache
from pathlib import Path

OWNER = "dapr"
REPO = "dapr"

ROOT = Path(os.environ.get("TRACK_DATA_DIR", "track-data-real"))
DATA_DIR = ROOT / OWNER / REPO


@lru_cache(maxsize=1)
def _manifest() -> dict:
    return json.loads((DATA_DIR / "manifest.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _load_record(kind: str, number: int) -> dict | None:
    path = DATA_DIR / kind / f"{number}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def get_issue_or_pr(number: int) -> dict | None:
    """Look up a record by number, checking issues then pull requests."""
    record = _load_record("issues", number)
    if record is not None:
        return record
    return _load_record("prs", number)


def seed_issue_numbers() -> list[int]:
    return _manifest().get("seed_issues", [])


def all_records() -> list[dict]:
    """All collected issues + PRs (flat collection plus neighborhood crawl)."""
    records = []
    for kind in ("issues", "prs"):
        d = DATA_DIR / kind
        if not d.exists():
            continue
        for path in d.glob("*.json"):
            records.append(json.loads(path.read_text(encoding="utf-8")))
    return records
