<!--
Copyright 2026 The Dapr Authors
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at
    http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-->

# deepagents-issue-investigator

A CLI tool that investigates a GitHub issue using [DeepAgents](https://docs.langchain.com/oss/python/deepagents) (plan + tools + virtual filesystem, built on LangGraph) and writes a Markdown investigation report.

Built for the Dapr University "Deep Issue Investigation that Survives the Long Haul" track. It reads issue/PR data from a pre-baked local JSON snapshot (no live GitHub access at runtime) and demonstrates how Dapr makes a long-running agent investigation durable: kill the process mid-run, restart it, and it resumes instead of re-doing expensive LLM calls.

## Three versions

| File | What it demonstrates |
|---|---|
| `investigate-baseline.py` | In-process DeepAgents run, in-memory scratchpad. No Dapr. |
| `investigate-durable.py` | Same agent, wrapped in `DaprWorkflowDeepAgentRunner` (from `diagrid[deepagents]`). Scratchpad + workflow progress persisted to a Dapr state store. |
| `investigate-crash.py` | Durable version using `tools_crash.py`, which has a deliberate `os._exit(1)` inside `get_comments` to simulate a mid-investigation crash. Uses `crash_state.json` to persist the workflow ID across restarts. |

`investigate.py` is whichever of the three is currently active (copy the one you want over it, or use the Instruqt challenge setup scripts which do this for you).

## Setup

```bash
uv sync --active
cp .env.example .env   # fill in OPENAI_API_KEY
```

The local GitHub data snapshot is expected at `/opt/track-data/dapr/dapr/` (built by the `tools/github-collector` collector in `dapr-university-instruqt` at sandbox-image build time, seeded with `--seed-issue 1833 --neighborhood-depth 2`). For local development outside the sandbox, point `TRACK_DATA_DIR` at a snapshot you collected yourself:

```bash
TRACK_DATA_DIR=/path/to/track-data uv run python investigate.py --issue 1833
```

## Run: baseline (no Dapr)

```bash
cp investigate-baseline.py investigate.py
uv run python investigate.py --issue 1833
cat investigation-1833.md
```

## Run: durable (Dapr-backed)

Requires the Dapr CLI (`dapr init`) and the state store component in `resources/statestore.yaml` (Redis, named `agent-memory`, `actorStateStore: "true"` so it also backs the Dapr Workflow engine).

```bash
cp investigate-durable.py investigate.py
uv run dapr run --app-id deepagent --resources-path ./resources -- python investigate.py --issue 1833
cat investigation-1833.md
```

Inspect the persisted scratchpad/workflow state directly in Redis:

```bash
docker exec dapr_redis redis-cli keys "*"
```

## Run: crash and recover

```bash
cp investigate-crash.py investigate.py
uv run dapr run --app-id deepagent --resources-path ./resources -- python investigate.py --issue 1833
```

The process dies inside `get_comments` (see `tools_crash.py`) after `get_issue` has already completed and been checkpointed. The Dapr workflow ID is saved to `crash_state.json` before the crash.

Comment out the `os._exit(1)` line in `tools_crash.py`, then run the same command again:

```bash
uv run dapr run --app-id deepagent --resources-path ./resources -- python investigate.py --issue 1833
```

On restart, the script detects `crash_state.json` and polls the existing Dapr workflow by its saved ID. The Dapr Workflow engine resumes from the last checkpoint — `get_issue` is not re-executed — and `investigation-1833.md` is produced.

To reset for a fresh demo:

```bash
rm -f crash_state.json
docker exec dapr_redis redis-cli flushall
```

## Resources

- `resources/statestore.yaml` — Redis state store backing the DeepAgents scratchpad and the Dapr Workflow actor runtime.

## Files

- `investigate-*.py` — the three entry points described above.
- `tools.py` / `tools_crash.py` — agent tool functions (`get_issue`, `list_linked_prs`, `get_comments`, `search_related_issues`), reading from the local snapshot.
- `github_data.py` — loader for the local snapshot (schema matches `tools/github-collector/collect_github_data.py` in `dapr-university-instruqt`).
