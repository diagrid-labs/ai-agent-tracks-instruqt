# Supply Chain Auditor (LangGraph)

An AI agent that runs as a **GitHub Action on Dependabot PRs** and checks whether
a dependency bump's **upstream release notes match the actual source code
changes** — catching the classic supply-chain attack where malicious code is
slipped into an update whose changelog says something innocent.

It's built as an **explicit, staged [LangGraph](https://www.langchain.com/langgraph)
pipeline** run as a durable Dapr Workflow via the
[Diagrid `diagrid`](https://pypi.org/project/diagrid/) adapter, and uses
[Claude](https://www.anthropic.com/claude) for the analysis step.

## How it works

```
START → gather_evidence → ┬─ analyze  ─┐→ render_report → END
                          └─ finalize ─┘
        (resolve repo,      (Claude judges    (Markdown report;
         fetch notes+diff,    notes vs diff,    app.py posts the
         run heuristics)      reconciled)       PR comment)
```

- **`graph.py`** — the pipeline. Only `analyze` calls the LLM; every other node
  is plain Python. Each node runs as a durable Dapr Workflow activity, so a crash after the LLM
  `analyze` node resumes at `render_report` — Dapr replays `gather_evidence` and
  `analyze` from durable state, so neither the GitHub fetch nor the Claude call is
  repeated. See "Crash-and-Resume" below.
- **`auditor_core/`** — the audit logic: parsing the bump, resolving the source
  repo, GitHub fetching, the red-flag heuristics, the untrusted-content
  guardrail, the verdict reconcile, and the report rendering.
- **`tools.py`** — the audit steps exposed as LangChain tools.
- **`app.py`** — one-shot entry point: read the PR context from the environment,
  run the workflow per bumped dependency, post one combined PR comment, exit.

### The security model

1. **Deterministic heuristics run first, without the LLM** (`auditor_core/redflags.py`):
   install hooks, download-then-exec, obfuscation, raw-IP egress, credential
   access, CI-workflow edits, binary blobs, plus evidence flags (unresolved repo,
   missing notes). A prompt-injected diff can't suppress them.
2. **The LLM grounds its judgement in the untrusted, nonce-tagged evidence** and
   produces a structured verdict — but it can only *raise* risk.
3. **Reconcile enforces a floor** (`auditor_core/reconcile.py`):
   `final_score = max(llm_score, heuristic_floor)`. A CRITICAL heuristic pins
   FAIL/BLOCK regardless of what the model says. "Could not verify" never PASSes.

The changelog and diff are attacker-controllable, so they're fetched into
nonce-tagged `UNTRUSTED` blocks and the model is instructed to treat them as data,
never as instructions.

Posture: **advisory** — the auditor posts a comment and exits 0; it never blocks
a merge by itself. Gate a required check on `recommendation == block` (driven by
the high-precision deterministic layer) if you want to enforce it.

## Configuration

Create a local `.env` with these keys:

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `ANTHROPIC_API_KEY` | yes | — | Claude API key for the analysis step |
| `GITHUB_TOKEN` | no | — | Enables posting the PR comment + authenticated reads; **dry-run without it** |
| `LLM_MODEL` | no | `claude-sonnet-4-6` | Chat model (`claude-opus-4-8` for deeper analysis) |
| `LLM_MAX_TOKENS` | no | `8000` | Max output tokens |
| `LOG_LEVEL` | no | `INFO` | Logging verbosity |
| `DAPR_GRPC_ENDPOINT` | no | — | Catalyst gRPC gateway (CI; lets the adapter skip a local sidecar) |
| `DAPR_API_TOKEN` | no | — | Catalyst App-ID token (CI) |

In the GitHub Action, `PR_REPO`, `PR_NUMBER`, `PR_TITLE`, `PR_BODY`, and the
`DEP_*` Dependabot metadata are injected for you.

## Run

The auditor needs the bumped dependency. In the GitHub Action that comes from
`dependabot/fetch-metadata`; **locally, just pass a real Dependabot PR number**
and the auditor fetches the PR title from GitHub to find the bump.

### Diagrid Catalyst via the CLI

Install the CLI first (`curl -fsSL https://downloads.diagrid.io/cli/install.sh | bash`,
or see [docs.diagrid.io](https://docs.diagrid.io)), then:

```bash
uv sync
diagrid login                                                   # once
# first time only: diagrid project create supply-chain-auditor --enable-agent-infrastructure
ANTHROPIC_API_KEY=sk-ant-... \
PR_REPO=dapr/dapr-agents PR_NUMBER=635 DEP_ECOSYSTEM=pip \
diagrid dev run --file supply-chain-auditor-langgraph.yaml --approve
```

The CLI wires the Dapr connection from your `diagrid login` session — you do
**not** set `DAPR_GRPC_ENDPOINT` / `DAPR_API_TOKEN` yourself (those are only for a
CLI-less direct connection, e.g. the GitHub Action).

### Local Dapr sidecar

```bash
dapr init    # once per machine, if you haven't already
uv run dapr run --app-id supply-chain-auditor-langgraph --resources-path ./resources -- python app.py
```

Without `GITHUB_TOKEN` the comment is a **dry-run** (printed, not posted) and
GitHub reads are unauthenticated (rate-limited). To skip the PR fetch, pass the
bump explicitly with `DEP_NAMES` / `DEP_PREV_VERSION` / `DEP_NEW_VERSION` —
grouped Dependabot PRs need that explicit form (or the Action's fetch-metadata).

### As a GitHub Action

`.github/workflows/supply-chain-audit.yml` (in the repo root) triggers on
Dependabot PRs, connects to Catalyst via the `DAPR_GRPC_ENDPOINT` /
`DAPR_API_TOKEN` secrets, runs `python app.py`, and the auditor posts the comment
with the workflow's `GITHUB_TOKEN`.

> **Dependabot secrets:** workflows triggered by Dependabot PRs do **not** receive
> your normal Actions secrets. Add `ANTHROPIC_API_KEY`, `DAPR_GRPC_ENDPOINT`, and
> `DAPR_API_TOKEN` under **Settings → Secrets and variables → Dependabot** (not
> Actions), or they'll be empty at runtime. `GITHUB_TOKEN` is still provided.

## Crash-and-Resume (durability demo)

This is the durability lesson: the workflow is interrupted mid-run by a **real process
crash**, and on restart it resumes from durable Redis state — **without re-invoking the
Claude `analyze` call that already completed.** An append-only *stage ledger*
(`audit-ledger.log`) makes this provable.

### How it works

- **The crash — one line you toggle by hand.** `graph.py`'s `render_report` node ships
  with an armed crash gated on the ledger count:

  ```python
  if ledger.count() >= 2: os._exit(1)     # ← comment out for the resume run
  ```

  By the time `render_report` runs, `gather_evidence` and `analyze` have each recorded a
  ledger line (count == 2), so the process dies **after** the Claude call has completed
  and been checkpointed. There is no environment variable or marker file — *you* are the
  switch. (Because it ships armed, a normal run also crashes here; comment it out for a
  clean, non-crashing run.)
- **The stage ledger.** Each node appends one line — `<timestamp>\t<stage>\t<detail>` —
  to `audit-ledger.log`. Recording happens inside a checkpointed workflow activity, so on
  resume a completed stage replays from durable history and is **not** re-appended. The
  finished ledger holds each stage exactly once, with a visible time gap at the restart.
- **Resume is automatic.** `app.py` runs the workflow under a deterministic instance ID
  (`audit-<repo>-<pr>-<package>`). On the second run it finds the in-flight instance in
  Redis and polls it to completion instead of starting over — Dapr re-dispatches the
  pending `render_report` node into the restarted process.

The ledger and report are written to `AUDIT_OUTPUT_DIR` (default: an `audit-out` folder in
the working directory). Set it to a known path so you can find them easily.

### Run 1 — crash

The crash ships **armed**, so no edit is needed. Set the output dir and run against a real
Dependabot PR with a resolvable source repo (so the `analyze` branch is taken):

```bash
export AUDIT_OUTPUT_DIR="$PWD/audit-out"
ANTHROPIC_API_KEY=sk-ant-... PR_REPO=dapr/dapr-agents PR_NUMBER=635 DEP_ECOSYSTEM=pip \
  uv run dapr run --app-id supply-chain-auditor-langgraph --resources-path ./resources -- python app.py
```

The process dies inside `render_report`, after `analyze` completed and checkpointed.
Inspect the ledger — it holds the `gather_evidence` and `analyze` lines:

```bash
cat "$AUDIT_OUTPUT_DIR/audit-ledger.log"
```

### Run 2 — comment out and resume

Comment out the crash line in `graph.py`'s `render_report`:

```python
# if ledger.count() >= 2: os._exit(1)
```

Re-run the **same** command. Dapr rehydrates instance `audit-dapr-dapr-agents-635-<pkg>`,
replays `gather_evidence` + `analyze` from history (no re-fetch, no second Claude call), and
runs only `render_report` to completion.

### Verify — durability, proven

```bash
cat "$AUDIT_OUTPUT_DIR/audit-ledger.log"
```

Confirm:

1. **Exactly three lines — `gather_evidence`, `analyze`, `render_report`, each once.** The
   `analyze` line was written on run 1 and **not** repeated on resume: the Claude call ran
   exactly once.
2. **A clear timestamp gap** before the `render_report` line — the wall-clock cost of the
   crash + restart, inside a single logical workflow run.

### Reset for a fresh demo

Purge the workflow state **and** the ledger (so stale lines do not count toward the crash
gate):

```bash
docker exec dapr_redis redis-cli flushall
rm -f "$AUDIT_OUTPUT_DIR/audit-ledger.log"
```

## Test

```bash
uv run pytest        # unit tests, ≥80% coverage; all network/LLM/Dapr mocked
```

The adversarial case to try: a fixture diff that adds a `postinstall` hook with a
"docs only" changelog yields **FAIL / block** via `SC-INSTALL-HOOK`, proving the
heuristic floor overrides the narrative (`tests/test_reconcile.py`,
`tests/test_graph_nodes.py`).
