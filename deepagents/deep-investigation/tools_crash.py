# Copyright 2026 The Dapr Authors
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Same tools as tools.py, with a deliberate crash planted in get_comments
to simulate an infrastructure failure mid-investigation. Used only by
investigate-crash.py (challenge 4).

Comment out the os._exit(1) line below before the second run to let the
workflow resume and complete.
"""
import os

from langchain_core.tools import tool

import github_data as gh
from tools import get_issue, list_linked_prs, search_related_issues


@tool
def get_comments(number: int) -> str:
    """Get all comments on a given issue or pull request number."""
    record = gh.get_issue_or_pr(number)
    if record is None:
        return f"No data found for #{number} in the local snapshot."

    # os._exit(1)  # Simulates a crash — comment out this line before the second run

    comments = record.get("comments", [])
    if not comments:
        return f"No comments found on #{number}."
    out = []
    for c in comments:
        author = c.get("user") or "unknown"
        out.append(f"--- {author} ({c['created_at']}) ---\n{c['body']}")
    return "\n\n".join(out)


TOOLS = [get_issue, list_linked_prs, get_comments, search_related_issues]
