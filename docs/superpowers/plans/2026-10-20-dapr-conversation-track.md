# Dapr Conversation Track Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `dapr-conversation` Instruqt track — four challenges, three languages, drift-tested — whose aha moment is the same application code talking to a real LLM after one YAML field changes.

**Architecture:** One demo app per language in `ai-agent-tracks-instruqt/conversation/<language>/`, used by all four challenges; only the component behind it changes — `conversation.echo` first, `conversation.openai` from challenge 3 on. The OpenAI key comes from the Instruqt sandbox secret via a local-file secret store and `secretKeyRef`, so the learner never supplies or sees one. Track content in `dapr-university-instruqt/dapr-conversation/`.

**Tech Stack:** Dapr 1.18.x self-hosted; ASP.NET Core minimal API (.NET 10), FastAPI (Python 3.12), Spring Boot (Java 17); `conversation.echo` (Stable) and `conversation.openai` (Alpha); Robot Framework 7.x via `uv`.

**Spec:** `docs/superpowers/specs/2026-10-20-dapr-building-block-tracks-design.md`

Plan 3 of 5. **The shared contract artifacts are defined in plan 1 (`2026-10-20-dapr-secrets-track.md`, Task 2).** Read it before Task 2 here.

This is the only track that spends money and the only one whose CI uses a secret. Both are deliberate decisions recorded in spec §3.3.

## Global Constraints

Plan 1's Global Constraints apply in full. Track-specific values:

- **Track slug:** `dapr-conversation`. **Demo code:** `conversation/<language>/`.
- **Challenge slugs:** `1-what-is-the-conversation-api`, `2-component-and-parameters`, `3-swap-to-a-real-llm`, `4-pii-and-caching`.
- **Time budget:** 5 + 8 + 7 + 8 = 28 minutes; `## Time limit (minutes)` 30, `### Extra time` 10.
- **CI schedule:** daily at **07:15 UTC**.
- **The learner never supplies an API key.** The `OPENAI_API_KEY` Instruqt sandbox secret is written into `secrets.json` by `sandbox-setup.sh` and pulled by the component with `secretKeyRef`. Never prompt for a key, never print one, never commit one — `secrets.json` is git-ignored.
- **The Conversation API is alpha.** Every assignment here is more drift-prone than the other four tracks'. Assert on shape, never on model wording.
- **Model:** `gpt-4.1-mini`, matching `dapr-agents/_setup/sandbox-setup.sh`.
- **Git:** no `git add` / `commit` / `push` without the user explicitly asking in the current conversation. Ask before every commit step.

## Review Focus

Plan 1's five classes apply, with this track's specifics:

1. **Learner jumps to challenge 3 or 4.** Each `scripts/setup.sh` must ensure `secrets.json` and the OpenAI component exist, not assume an earlier challenge made them. → Tasks 3–6.
2. **Sandbox relaunched mid-track.** Rewriting `secrets.json` must truncate, and must not fail when `OPENAI_API_KEY` is already provisioned. → Task 2.
3. **`OPENAI_API_KEY` is absent or invalid** — the sandbox secret is unset, expired, or rate-limited. The learner sees an opaque sidecar error on a track that never mentioned a key. → Task 2 and Task 5.
4. **A previous challenge's app still holds port 5001.** → Task 3.
5. **Learner switches language between challenges.** → Tasks 4–6.

Plus two specific to this track:

6. **The model returns something unexpected** — refusal, empty completion, or wording nothing asserts on. Every assertion in this track must be structural. → Tasks 5 and 6.
7. **The response cache makes the second call indistinguishable from the first**, so challenge 4's caching demo looks like nothing happened. The observable must be a counter or a latency, not the text. → Task 6.

---

## Task 1: Confirm the PII obfuscation field and the alpha surface (blocking spike)

Spec §3.3 and §7: the exact config field name for PII obfuscation is **not confirmed**, and challenge 4 is built on it. The API is alpha, so the request/response shape must be read now rather than assumed.

Throwaway. Deliverable is a findings file.

**Files:**
- Create: `docs/superpowers/notes/2026-10-20-conversation-api-findings.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the PII field name and its accepted values; the exact request and response JSON shape; the usage field names; confirmation of which caching knob lives where.

- [ ] **Step 1: Read the component reference and API reference**

Record, for Dapr 1.18: the conversation component metadata fields, the request body shape, the response shape including the usage fields, and the **exact** name and placement of the PII obfuscation setting — component metadata or per-request parameter.

- [ ] **Step 2: Stand up echo on WSL2 and capture a real exchange**

`dapr init`, an echo component, then a raw call. Record the verbatim request and response JSON.

- [ ] **Step 3: Confirm the two caching knobs**

Verify that `responseCacheTTL` is component metadata and `promptCacheRetention` is a per-request parameter, as spec §3.3 states. Record what each actually does and how a caller observes it — this decides challenge 4's observable (Review Focus 7).

- [ ] **Step 4: Prove PII obfuscation scrubs**

With the field from step 1, send a prompt containing an email address and a phone number. Record what comes back and which types are scrubbed. If echo does not support scrubbing, repeat against OpenAI and record that constraint — it changes which challenge the demo belongs in.

- [ ] **Step 5: Write the findings and decide**

Record everything above. If PII obfuscation cannot be demonstrated on this runtime version, challenge 4 becomes caching and usage only, and the assignment drops the PII claim rather than describing a feature the learner cannot see.

- [ ] **Step 6: Commit the findings file** *(ask first)*

---

## Task 2: Scaffold, secret provisioning, and shared contract artifacts

**Files:**
- Create (demo repo): `conversation/README.md`, `conversation/.gitignore` (ignoring `secrets.json`)
- Create (track repo): `dapr-conversation/README.md`, `dapr-conversation/website-description.md`, `dapr-conversation/_setup/sandbox-setup.sh`
- Create (track repo): `tools/track-tester/variables/dapr_conversation.py`, `tools/track-tester/ci/setup-dapr-conversation.sh`

**Interfaces:**
- Consumes: plan 1 Task 2's patterns; Task 1's findings.
- Produces:
  - `TRACKS_SRC_DIR`, `CONV_BASE` (`<TRACKS_SRC_DIR>/conversation`), `DEMO` (`Demo1-Chat`).
  - Sandbox contract: repo cloned, `secrets.json` written from `OPENAI_API_KEY`, `local-secret-store.yaml` and both conversation components present, `dapr init` complete, demo pre-built for all three languages.

- [ ] **Step 1: Write the variables file**

`variables/dapr_conversation.py`, same shape as `dapr_secrets.py`, plus the field names Task 1 confirmed (PII field, usage fields) so assignment and suite share one source of truth.

- [ ] **Step 2: Write the track README**

All required sections. The teaser must state that **no API key is needed** — it is the differentiator from every other AI track in the catalogue and the reason this one does not lose people at challenge 1.

- [ ] **Step 3: Write `_setup/sandbox-setup.sh`**

Follow `dapr-agents/_setup/sandbox-setup.sh`, which already does exactly this: write `secrets.json` from `${OPENAI_API_KEY}` with `python3 -c 'import json, os; …'`, write `local-secret-store.yaml` (`secretstores.local.file`), and write the conversation component with `key` via `secretKeyRef` and `auth.secretStore`. Then `docker login`, `dapr init` with the containers check, `agent variable set` the pinned versions, and pre-build the demo for all three languages.

**Guard (Review Focus 3):** if `OPENAI_API_KEY` is empty, write a clear message to the sandbox log naming the missing sandbox secret, and leave the echo component working so challenges 1–2 still run. Never fail the whole launch over a key that only two challenges need.

**Idempotency (Review Focus 2):** `secrets.json` is truncated, not appended.

- [ ] **Step 4: Write `ci/setup-dapr-conversation.sh`**

Per plan 1 Task 2 step 4, reproducing the `secrets.json` provisioning from the CI secret: `OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}` in the workflow env, written to `secrets.json` the same way. The sandbox and CI must produce byte-identical component files, or CI stops testing what learners run.

- [ ] **Step 5: Verify it provisions a working sandbox**

Run: `OPENAI_API_KEY=<test key> bash tools/track-tester/ci/setup-dapr-conversation.sh`
Expected: exits 0; `secrets.json` contains the key; both conversation components present; Dapr containers running.

- [ ] **Step 6: Verify the no-key path (Review Focus 3)**

Run it with `OPENAI_API_KEY` unset.
Expected: exits 0, echo component present, a clear message naming the missing secret, and no `secrets.json` containing an empty key.

- [ ] **Step 7: Verify it is idempotent**

Run twice with a key set. Expected: same state, `secrets.json` byte-identical.

- [ ] **Step 8: Write `conversation/README.md` and `.gitignore`**

- [ ] **Step 9: Commit** *(ask first)* — confirm `secrets.json` is ignored before any `git add`.

---

## Task 3: Challenge 1 — What the Conversation API is for

5 minutes. One call against echo. No key, no spend, deterministic — which is also why it is the only challenge whose assertions can be exact.

**Files:**
- Create (demo repo): `conversation/<lang>/Demo1-Chat/` ×3, `conversation/<lang>/resources/conversation-echo.yaml`
- Create (track repo): `dapr-conversation/1-what-is-the-conversation-api/{README.md,notes.md,assignment.md,tabs.md,scripts/setup.sh,tests/challenge.robot}`

**Interfaces:**
- Consumes: `CONV_BASE`, `DEMO` from Task 2.
- Produces:
  - Component name **`llm`** — fixed for the whole track, so challenge 3's swap changes the file behind it and not the app.
  - App: id `chat-api`, app port **5001**, Dapr HTTP **3500**.
  - `POST /chat` with `{"prompt": "<text>"}` → `{"completion": "<text>", "usage": {"promptTokens": n, "completionTokens": n, "totalTokens": n}}`.

- [ ] **Step 1: Write the failing Robot suite**

One case per language, tagged `dotnet`/`python`/`java`, importing `dapr.resource` and `variables/dapr_conversation.py`, `Suite Teardown    Terminate All Processes    kill=True`. Assert that posting `{"prompt": "hello dapr"}` to `/chat` returns a completion containing `hello dapr` — echo returns the input, so this assertion is exact and will stay exact.

- [ ] **Step 2: Add the port-collision test (Review Focus 4)**

- [ ] **Step 3: Run the suite to verify it fails**

Run: `(cd tools/track-tester && uv run robot ../../dapr-conversation/1-what-is-the-conversation-api/tests/challenge.robot)`
Expected: FAIL — the demo directories do not exist.

- [ ] **Step 4: Write the three demo apps**

`POST /chat` via the SDK's conversation call against component `llm`, returning completion and usage per Interfaces. Plus each app's `dapr.yaml`.

- [ ] **Step 5: Write `conversation-echo.yaml`**

Component name `llm`, type `conversation.echo`.

- [ ] **Step 6: Run the suite to verify it passes**

- [ ] **Step 7: Write the assignment**

Why route an LLM call through a sidecar: pluggability, and the scrubbing, caching and usage accounting that come with it. Echo exists so tests and local development need no key — say that, because it is the answer to "why would I ever want a fake LLM".

- [ ] **Step 8: Write `README.md`, `notes.md`, `tabs.md`, `scripts/setup.sh`**

`notes.md` uses the full intro opener and states that no API key is required. `setup.sh` builds all three languages.

- [ ] **Step 9: Verify doc-sync passes**

- [ ] **Step 10: Commit** *(ask first)*

---

## Task 4: Challenge 2 — The component and the request parameters

8 minutes. The distinction learners conflate: component metadata versus per-request parameters.

**Files:**
- Modify (demo repo): `conversation/<lang>/Demo1-Chat/` — accept `temperature` and `responseFormat`
- Create (track repo): `dapr-conversation/2-component-and-parameters/{README.md,notes.md,assignment.md,tabs.md,scripts/setup.sh,tests/challenge.robot}`

**Interfaces:**
- Consumes: the `llm` component and `chat-api` app from Task 3.
- Produces: `POST /chat` additionally accepting `temperature` (number) and `responseFormat` (JSON Schema object), both per-request; the component's `responseCacheTTL` set in YAML.

- [ ] **Step 1: Write the failing suite**

Per language, against echo so the assertions stay deterministic:
- A request carrying `temperature` is accepted and returns a completion.
- A request carrying `responseFormat` with a JSON Schema returns a body that parses as JSON matching that schema.
- The usage fields `promptTokens`, `completionTokens`, `totalTokens` are present and numeric.
- The component file carries `responseCacheTTL` and the sidecar starts cleanly with it — proving it is metadata, not a request field.

- [ ] **Step 2: Run the suite to verify it fails**

Expected: FAIL — `temperature` and `responseFormat` are not accepted.

- [ ] **Step 3: Add the two parameters to the three demo apps**

- [ ] **Step 4: Add `responseCacheTTL` to the echo component**

Value `10m`, per spec §3.3.

- [ ] **Step 5: Run the suite to verify it passes**

- [ ] **Step 6: Write the assignment**

Two columns, stated once and plainly: metadata is set in YAML and applies to every call; parameters travel with the request. `responseCacheTTL` versus `promptCacheRetention` is the example that makes it stick, because the names look interchangeable and are not.

- [ ] **Step 7: Write `README.md`, `notes.md`, `tabs.md`, `scripts/setup.sh`**

- [ ] **Step 8: Verify doc-sync passes**

- [ ] **Step 9: Commit** *(ask first)*

---

## Task 5: Challenge 3 — Swap to a real LLM

7 minutes. **The aha moment.** Echo → OpenAI, one YAML field plus a `secretKeyRef`, no application change. This is the first challenge that spends money.

**Files:**
- Create (demo repo): `conversation/<lang>/resources/conversation-openai.yaml`
- Create (track repo): `dapr-conversation/3-swap-to-a-real-llm/{README.md,notes.md,assignment.md,tabs.md,scripts/setup.sh,scripts/check.sh,scripts/solve.sh,tests/challenge.robot}`

**Interfaces:**
- Consumes: the `llm` component name and the demo app from Task 3; `secrets.json` and `local-secret-store.yaml` from Task 2.
- Produces: `conversation-openai.yaml` — **component name `llm`**, type `conversation.openai`, `model: gpt-4.1-mini`, `key` via `secretKeyRef` against `local-secret-store`, with `auth.secretStore: local-secret-store`.

- [ ] **Step 1: Write the failing suite**

Per language, **structural assertions only** (Review Focus 6):
- `POST /chat` returns a non-empty completion.
- `totalTokens` is greater than zero — the proof it reached a real model, where echo would report nothing.
- The completion is **not** the input echoed back, distinguishing a real provider from the fake one.
- The app source is byte-identical to challenge 1's, proving the swap needed no code change.

Never assert on wording.

- [ ] **Step 2: Add the missing-key test (Review Focus 3)**

With `OPENAI_API_KEY` unset, assert the failure names the secret store or the key rather than surfacing a bare 500 — so a learner whose sandbox secret failed to provision can tell what went wrong.

- [ ] **Step 3: Run the suite to verify it fails**

Expected: FAIL — `conversation-openai.yaml` does not exist.

- [ ] **Step 4: Write `conversation-openai.yaml`**

Per Interfaces, for all three languages. Copy the `secretKeyRef` shape verbatim from `dapr-agents/_setup/sandbox-setup.sh`, which is already proven in production.

- [ ] **Step 5: Run the suite to verify it passes**

- [ ] **Step 6: Write `check.sh` and `solve.sh`**

`check.sh` asserts the loaded `llm` component is `conversation.openai` and a call returns non-zero `totalTokens`, with `fail-message "Still on echo — is conversation-openai.yaml the component in the resources folder?"`.

- [ ] **Step 7: Write the assignment**

The swap, then the point: the app was never rebuilt. Say where the key came from — the sandbox provided it, this is a secret store and a `secretKeyRef`, and that is challenge 2 of the Secrets track doing real work here.

- [ ] **Step 8: Write `README.md`, `notes.md`, `tabs.md`, `scripts/setup.sh`**

- [ ] **Step 9: Verify doc-sync passes**

- [ ] **Step 10: Commit** *(ask first)*

---

## Task 6: Challenge 4 — PII obfuscation and caching

8 minutes. The "I didn't know it did that" challenge. Scope depends on Task 1's findings.

**Files:**
- Modify (demo repo): `conversation/<lang>/resources/conversation-openai.yaml` — PII and cache settings
- Create (track repo): `dapr-conversation/4-pii-and-caching/{README.md,notes.md,assignment.md,tabs.md,scripts/setup.sh,scripts/check.sh,scripts/solve.sh,tests/challenge.robot}`

**Interfaces:**
- Consumes: the OpenAI component from Task 5; Task 1's PII field name and cache observable.
- Produces: the component carrying the PII obfuscation setting and `responseCacheTTL`; `POST /chat` returning a `cached` boolean or latency field — whichever Task 1 established is observable (Review Focus 7).

- [ ] **Step 1: Write the failing suite**

Per language:
- Post a prompt containing `jane.doe@example.com` and `+1-555-0142`; assert the outbound-facing value no longer contains either string. **Structural, not wording-dependent.**
- Post the same prompt twice; assert the second response is observably cached by the mechanism Task 1 identified — not by comparing completion text, which would pass even with no cache at all.
- Assert `totalTokens` is reported on both calls.

- [ ] **Step 2: Run the suite to verify it fails**

Expected: FAIL — the PII setting is not on the component.

- [ ] **Step 3: Add the PII and cache settings to the component**

Using Task 1's confirmed field name. If Task 1 found PII unavailable, this step and its assertions drop, and the challenge is caching and usage only.

- [ ] **Step 4: Expose the cache observable in the three demo apps**

- [ ] **Step 5: Run the suite to verify it passes**

- [ ] **Step 6: Write `check.sh` and `solve.sh`**

- [ ] **Step 7: Write the assignment**

Scrubbing first — send the email address, watch it go. Then the cache and the token counts. Be explicit that `responseCacheTTL` is per sidecar and in memory, because a learner will otherwise assume it is shared and be wrong in production.

Close the track: `---`, recap, Discord `#university` pointer. Add one honest line that the Conversation API is alpha and these details may move.

- [ ] **Step 8: Write `README.md`, `notes.md`, `tabs.md`, `scripts/setup.sh`**

- [ ] **Step 9: Verify doc-sync passes**

- [ ] **Step 10: Commit** *(ask first)*

---

## Task 7: CI workflow and whole-track verification

The first workflow in `dapr-university-instruqt` to use a secret, and the first to cost money on a schedule.

**Files:**
- Create (track repo): `.github/workflows/test-dapr-conversation.yml`

**Interfaces:**
- Consumes: `ci/setup-dapr-conversation.sh`; all four suites.
- Produces: nothing downstream.

- [ ] **Step 1: Add the `OPENAI_API_KEY` repository secret**

In `diagrid-labs/dapr-university-instruqt`. **Requires the repo owner** — flag it rather than assuming it exists; no other workflow in the repo references a secret, so there is nothing to inherit.

- [ ] **Step 2: Write the workflow**

Copy the shape from plan 1 Task 7. Schedule **07:15 UTC**; `pull_request` paths `dapr-conversation/**`, `tools/track-tester/**`, and the workflow file. Pass `OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}` to the setup step and the language legs.

**Guard against silent skipping:** if the secret is absent the live-LLM legs must **fail loudly**, not pass by skipping challenges 3–4. A green tick that tested nothing is worse than a red one.

- [ ] **Step 3: Pre-warm Maven outside the timed run**

- [ ] **Step 4: Run the whole track locally**

Run: `(cd tools/track-tester && uv run robot --name "Dapr Conversation" ../../dapr-conversation/*/tests/challenge.robot)`
Expected: PASS, all languages, all four challenges.

- [ ] **Step 5: Verify the workflow on a branch, twice**

Two consecutive runs. Both must pass. One pass proves it works; two consecutive passes are the minimum evidence that a live-LLM suite is not flaky, which is the whole risk spec §3.3 accepted.

- [ ] **Step 6: Record the daily cost**

Note the token usage of one full matrix run in the track's `notes.md` or the findings file, so the ongoing spend is a known number rather than a surprise on a bill.

- [ ] **Step 7: Confirm the time budget**

Expected: 28 minutes across the four assignments.

- [ ] **Step 8: Confirm the aha moment lands**

On a real Instruqt sandbox, complete challenge 3 in all three languages. The learner must get a real completion without ever being asked for a key.

- [ ] **Step 9: Commit** *(ask first)*
