# Handoff: Dapr Building Block Tracks — brainstorming session

**Date:** 2026-10-20
**Status:** Brainstorming in progress (`superpowers:brainstorming`). Design document NOT yet written.
**Next step:** Answer the one open question in section 6, then write the design doc.

> This file is a session handoff so the work can continue in another terminal.
> It captures the review findings, the decisions made, and what is still open.

---

## 1. Original request

Two parts:

1. Review a proposed **Dapr Bindings** track against the existing Dapr University tracks
   (`C:\dev\diagrid-labs\dapr-university-instruqt\README.md`).
2. Brainstorm **5 additional tracks** about different Dapr building block APIs.
   Each track: **3–4 challenges**, each challenge **5–10 minutes**, **~30 minutes total**.

### The proposed Bindings track (as supplied)

```
# Dapr Bindings

Goal: Explain to developers how to use the Dapr Bindings API with PostgreSQL to
      store and query data.
Languages: .NET/Python/Java
Source code: not available yet (add to diagrid-labs/ai-agent-tracks-instruqt)
Uses Catalyst: No
References:
  - https://docs.dapr.io/developing-applications/building-blocks/bindings/bindings-overview/

Install script for VM:
  - Download Postgres container

Challenges:
1. Explain Bindings API (and the difference with State Store API) + check Dapr
   installation and local postgres container
2. Inspect the code and yaml component file for the Postgres output binding and
   run the app to save state to Postgres (SQL INSERT)
3. Inspect the code for the Postgres input binding and run the app to query state
   from Postgres
```

---

## 2. Existing track inventory (recon findings)

Tracks in `dapr-university-instruqt/`:

| Folder | Covers |
| --- | --- |
| `dapr-101/` | What is Dapr, Dapr CLI, **State Management**, **Service Invocation**, **Pub/Sub** (5 challenges, 45 min, .NET/Python/Java/JavaScript) |
| `dapr-workflow/` | **Workflow** — durable execution, task chaining, fan-out/fan-in, monitor, external events, child workflows, resiliency, management (11 challenges) |
| `dapr-workflow-aspire/` | Workflow with .NET Aspire |
| `dapr-agents/` | Dapr Agents — LLM client, durable agent HTTP/pubsub, workflow + LLM |
| `dapr-agents-web-context/` | Dapr Agents advanced (Chainlit + Tavily) |
| `ai-agents-deepagents/` | DeepAgents + Dapr Workflow durability (Python) |
| `ai-agents-maf/` | Microsoft Agent Framework + Dapr Workflow (.NET Aspire) |
| `ai-agents-langgraph/`, `ai-agents-supply-chain-auditor-langchain/` | Agent framework durability tracks |
| `catalyst-101/` | Catalyst — pub/sub, state, workflow |

### Building blocks NOT yet covered

Actors, Jobs/Scheduler, Secrets, Configuration, Distributed Lock, Cryptography,
Conversation API, Bindings.

### Challenge anatomy (house style to follow)

Each challenge folder contains:

- `README.md` — Name / Url / Description
- `assignment.md` — the learner-facing instructions
- `notes.md`
- `tests/challenge.robot` — Robot Framework drift test

Track root has a `README.md` with: Name, Url, Teaser, Time limit (minutes),
Description, Time out idle users, Extra time. There is a `_setup/` folder with
`image-install.sh` and `sandbox-setup.sh`.

Assignment markdown uses annotated fences: `bash,run` for runnable commands and
`text,nocopy` for expected output. Every runnable command must be covered by the
Robot suite (there is a doc-sync checker).

**Every track opens with a concept/explainer challenge** (`1-what-is-dapr`,
`1-durable-execution`, `1-what-is-dapr-agents`), so the proposed Bindings
challenge 1 matches the house style.

---

## 3. Review of the Bindings track

### BLOCKER: Challenge 3 is not buildable as written

The **PostgreSQL binding is output-only**. Verified at
<https://docs.dapr.io/reference/components-reference/supported-bindings/postgresql/> —
it supports `exec`, `query`, and `close`, and has **no input-binding side**.

So "inspect the code for the Postgres *input* binding and run the app to query
state" cannot be built. Two ways out:

- **(a) Stay output-only** — challenge 3 uses the `query` operation on the same
  output binding. Still a good contrast with the State Store API: you get a SQL
  `SELECT` with a `WHERE` clause, which the key/value API cannot do.
- **(b) Add a real input binding** — pair Postgres with a **Cron input binding**
  that fires every N seconds and triggers a handler running the `query` operation.
  Gives learners both directions; Cron costs nothing extra in the VM.

**Recommendation: (b).** The track's teaching value collapses if "bindings" only
ever means "output," and Cron is the classic Dapr input-binding demo.

### Other findings

1. **Challenge 1 is thin.** Explainer + install check is a reading challenge.
   Three challenges where one is prose gives ~20 minutes hands-on, under the
   30-minute target. A 4th challenge fixes it.
2. **Setup script needs more than "download Postgres container."** Based on how
   `dapr-101/_setup` works, you also need the binding component YAML in the
   components dir *and* a created table, or challenge 2 fails on first run.
3. **The State Store contrast is the strongest idea in the track.** Make it
   hands-on rather than prose-only in challenge 1: have learners try the same
   `WHERE`-clause query through the State Store API and hit the wall. That is the
   moment the building block justifies itself.

---

## 4. Decisions made in this session

### The five tracks (user-selected)

**Actors, Jobs, Secrets, Configuration, Conversation API.**

Chosen because they are what people actually ask about in Discord and on customer
calls. Not selected: Distributed Lock, Cryptography.

### What people ask about (drives the structure)

The user's words: *"Getting started with these APIs, what are the parameters mean,
how to switch from one provider to another."*

### The three-act structure (agreed spine for all five tracks)

Those three recurring questions map onto a 3–4 challenge track almost exactly, and
it is the same spine every time:

- **Act 1 — one challenge, ~5 min.** What this API is for, when you would reach
  for it, plus the smallest possible working call. Matches the existing house
  style of an explainer first challenge.
- **Act 2 — one or two challenges, ~10–15 min.** The component YAML line by line,
  and the API's own parameters. **This is the part the current tracks mostly skip** —
  `dapr-101` shows `curl` commands but only glances at the component file at the
  very end of challenge 3. Making "what does this metadata field actually do" into
  its own challenge is the direct answer to question two, and it is where a track
  earns its 30 minutes.
- **Act 3 — one challenge, ~5–10 min.** Swap the provider without touching
  application code. Same app, different YAML, still works. The Dapr value
  proposition made literal — the thing a blog post cannot deliver but a VM can.

**Exception: Jobs does not fit Act 3** — the Scheduler is built into Dapr, so there
is no provider to swap. Replace Act 3 with a durability demo (see table below).
The user did not object to this.

### The anti-goal (user's words)

> *"no quick realization of the value, no aha moment"*

A track that is technically correct but feels like reading the docs out loud is a
**failure**, even if every challenge passes. So each track must be built around a
moment the learner *feels*, and it has to land early.

### The aha moment per track

| Track | Aha moment |
| --- | --- |
| **Actors** | Fire 100 concurrent increments at one actor → count is exactly 100. Do the same against a state store directly → watch updates get lost. Turn-based concurrency becomes a number on screen that is wrong one way and right the other. |
| **Jobs** | Schedule a job, kill the app, restart it → the job still fires. Side by side with an in-process timer that dies with the process. Replaces the provider-swap act. |
| **Configuration** | App is running and printing a value. Change that value in Redis from the other terminal → the running app logs the new one immediately, no restart. Live feature-flag flipping; the most visually satisfying of the five. |
| **Secrets** | **Scoping.** App A reads the secret; App B asks for the same secret and is refused. Removing a password from source code is worthy but inert — watching an app get told *no* is what sticks. |
| **Conversation API** | Same application code, three providers: echo for tests, a real LLM, then another vendor. One YAML field changes each time. Plus the parts almost nobody knows are there — PII obfuscation and caching. |

The user was asked to push back specifically on the Secrets aha (the least certain
one) and did not object.

### Languages

**.NET, Python, Java (Spring Boot)** — all five tracks. Same three as the Bindings
proposal, so authoring effort is consistent across all six tracks.

### Calls made (stated to the user, not yet explicitly confirmed)

- **Uses Catalyst: No** for all five — matches the Bindings proposal, keeps these
  as core open-source Dapr tracks.
- **Source code goes to `diagrid-labs/ai-agent-tracks-instruqt`**, following what
  the Bindings proposal already says.

---

## 5. Verified technical facts (checked against docs this session)

These were fetched from docs.dapr.io on 2026-10-20 — no need to re-verify.

- **PostgreSQL binding: output only.** Operations `exec`, `query`, `close`.
  No input binding.
- **Secret scoping is real and works as the Secrets aha moment needs.** Configured
  in a `Configuration` resource under a `secrets` section, with fields `storeName`,
  `defaultAccess` (`allow` | `deny`), `allowedSecrets`, `deniedSecrets`. Allow/deny
  lists override `defaultAccess`; if `allowedSecrets` has at least one entry, only
  those are accessible.
  **Caveat:** the docs page does not state what error or response an app receives
  when it requests a secret it is not allowed to access. This must be confirmed
  empirically on a VM before the assignment text can promise a specific visible
  failure.
- **Local echo is a Stable conversation component** (since 1.15) — the only Stable
  one on the page. So the "swap to a fake LLM for testing" challenge works with no
  API key at all.
- **The Conversation API itself is alpha**, and every provider component except
  echo is alpha: AWS Bedrock, Anthropic, DeepSeek, GoogleAI, Huggingface, Mistral,
  Ollama, OpenAI, OpenRouter.
- **Conversation caching — two separate things, do not conflate:**
  `promptCacheRetention` is a **per-request parameter** (e.g. `24h`, OpenAI);
  `responseCacheTTL` is a **component metadata field** (e.g. `10m`, in-memory and
  per sidecar). Also available: `responseFormat` (JSON Schema) for structured
  output; usage fields `promptTokens`, `completionTokens`, `totalTokens`.
- **PII obfuscation** is supported on input and output. Scrubbed types include
  phone numbers, email addresses, IP addresses, credit cards, SSNs. The exact
  config field name is not yet confirmed.

### Risk flagged to the user

The Conversation API being alpha means its assignments **will drift**. The Robot
Framework harness exists to catch exactly that, but it is a real ongoing
maintenance cost that should be priced in before committing to that fifth track.

### Reusable asset found

`dapr-agents/_setup/sandbox-setup.sh` already provisions an `OPENAI_API_KEY`
Instruqt sandbox secret into a `secrets.json` read by a **local-file secret store**,
with the conversation component pulling it via `secretKeyRef`. That pattern is
proven and directly reusable for **both** the Secrets track and the Conversation
API track.

---

## 6. Where this stands

Per `superpowers:brainstorming`, this was sized as **a project with a written
design** — five track proposals, each with goal, languages, setup requirements,
and a challenge breakdown with timings. Too much to settle in chat, and it is the
thing someone will build six tracks from.

The design document has **not** been written yet.

### THE ONE OPEN QUESTION

**Where should the design document go?**

- `C:\dev\diagrid-labs\ai-agent-tracks-instruqt\docs\superpowers\specs\` — the
  existing spec location, following the `YYYY-MM-DD-<topic>-design.md` convention
  already used by three design docs there, **or**
- somewhere in the `content-creation` repo.

### After that is answered

1. Write the design document.
2. Per the brainstorming skill, a builder-check subagent reads it first and may
   return one round of questions before handover.
3. Nothing gets built until the document is approved.

---

## 7. Standing instruction carried from the user's global config

No `git add`, `git commit`, `git push`, or any other state-changing git command
unless the user explicitly asks for that operation in the current conversation.
Read-only git commands are fine. This applies to skills that have built-in git
workflows.
