# Deepagents Issue Investigator

A CLI tool that investigates a GitHub issue using [DeepAgents](https://docs.langchain.com/oss/python/deepagents) (plan + tools + virtual filesystem, built on LangGraph) and writes a Markdown investigation report.

Built for the Dapr University "Make DeepAgents Reliable with Dapr Workflow - Deep Issue Investigation" track. It reads issue/PR data from a pre-baked local JSON snapshot (no live GitHub access at runtime) and demonstrates how Dapr makes a long-running agent investigation durable: kill the process mid-run, restart it, and it resumes instead of re-doing expensive LLM calls.

## Three versions

| File | What it demonstrates |
|---|---|
| `investigate-baseline.py` | In-process DeepAgents run, in-memory scratchpad. No Dapr. |
| `investigate-durable.py` | Same agent, wrapped in `DaprWorkflowDeepAgentRunner` (from `diagrid[deepagents]`). Scratchpad + workflow progress persisted to a Dapr state store. |
| `investigate-crash.py` | Durable version using `tools_crash.py`, which has a deliberate `os._exit(1)` inside `get_comments` to simulate a mid-investigation crash. Uses a deterministic workflow ID (`investigation-<issue>`) so the restart reconnects to the same Dapr workflow — no local state file. |

Each is a standalone entry point — run the one you want directly (see the sections below). Nothing is copied or renamed.

## Setup

```bash
uv sync --active
cp .env.example .env   # fill in OPENAI_API_KEY
```

Add your OpenAI API key to `.env`:

```
OPENAI_API_KEY="your_key_here"
```

The local GitHub data snapshot is committed in this directory at `data/dapr/dapr/` (seeded with issue `7326` plus the related `8236` and `9056`, `neighborhood_depth 2` — see `data/dapr/dapr/manifest.json`). 

## Run: baseline (no Dapr)

```bash
uv run python investigate-baseline.py --issue 7326
cat investigation-7326.md
```

## Run: durable (Dapr-backed)

Requires the Dapr CLI (`dapr init`) and the state store component in `resources/statestore.yaml` (Redis, named `agent-memory`, `actorStateStore: "true"` so it also backs the Dapr Workflow engine).

```bash
uv run dapr run --app-id deepagent --resources-path ./resources -- python investigate-durable.py --issue 7326
cat investigation-7326.md
```

Verify that Dapr persisted the workflow state in Redis by listing the keys using the Redis CLI:

```bash
docker exec dapr_redis redis-cli keys "*"
```

## Run: crash and recover

```bash
uv run dapr run --app-id deepagent --resources-path ./resources -- python investigate-crash.py --issue 7326
```

The process dies inside `get_comments` (see `tools_crash.py`) after `get_issue` has already completed and been checkpointed. The workflow ID is deterministic — `investigation-<issue>`; Dapr saves the workflow state under that ID.

Comment out the `os._exit(1)` line in `tools_crash.py`, then run the same command again:

```bash
uv run dapr run --app-id deepagent --resources-path ./resources -- python investigate-crash.py --issue 7326
```

On restart, the script derives the same workflow ID, asks Dapr for that instance's state, finds it still running, and polls it to completion. The Dapr Workflow engine resumes from the last checkpoint — `get_issue` is not re-executed — and `investigation-7326.md` is produced. (Because the ID is derived from the issue number, re-running a *completed* investigation just rewrites the report from Dapr's stored output rather than starting over; purge the instance or flush Redis to redo it.)

To reset for a fresh demo (purges all Dapr/Redis state):

```bash
docker exec dapr_redis redis-cli flushall
```

## Resources

- `resources/statestore.yaml` — Redis state store backing the DeepAgents scratchpad and the Dapr Workflow actor runtime.

## Files

- `investigate-*.py` — the three entry points described above.
- `tools.py` / `tools_crash.py` — agent tool functions (`get_issue`, `list_linked_prs`, `get_comments`, `search_related_issues`), reading from the local snapshot.
- `github_data.py` — loader for the local snapshot (schema matches `tools/github-collector/collect_github_data.py` in `dapr-university-instruqt`).
