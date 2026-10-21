# Dapr Configuration Track Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `dapr-configuration` Instruqt track — four challenges, three languages, drift-tested — whose aha moment is a running application logging a new value the instant it changes in the store, with no restart.

**Architecture:** One demo app per language in `ai-agent-tracks-instruqt/configuration/<language>/`, used by all four challenges; the component YAML behind it changes, the app does not. Track content in `dapr-university-instruqt/dapr-configuration/`. Robot suite first, then demo and assignment.

**Tech Stack:** Dapr 1.18.x self-hosted; ASP.NET Core minimal API (.NET 10), FastAPI (Python 3.12), Spring Boot (Java 17); Redis and PostgreSQL configuration stores; Robot Framework 7.x via `uv`.

**Spec:** `docs/superpowers/specs/2026-10-20-dapr-building-block-tracks-design.md`

Plan 2 of 5. **The shared contract artifacts are defined in plan 1 (`2026-10-20-dapr-secrets-track.md`, Task 2).** This plan reuses that shape — the `variables/` file, the `ci/setup-*.sh` pattern, the CI workflow's two-job structure, the `<details>` convention — and does not restate it. Read plan 1 Task 2 before starting Task 2 here.

## Global Constraints

Identical to plan 1's Global Constraints, which apply in full. Track-specific values:

- **Track slug:** `dapr-configuration`. **Demo code:** `configuration/<language>/`.
- **Challenge slugs:** `1-what-is-the-configuration-api`, `2-component-and-parameters`, `3-subscribe-and-watch`, `4-swap-the-provider`.
- **Time budget:** 5 + 7 + 8 + 8 = 28 minutes; `## Time limit (minutes)` 30, `### Extra time` 10.
- **CI schedule:** daily at **07:00 UTC**.
- **Git:** no `git add` / `commit` / `push` without the user explicitly asking in the current conversation. Ask before every commit step.

## Review Focus

The same five classes as plan 1 — they are properties of Instruqt and the harness, not of a building block — with this track's specifics:

1. **Learner jumps to challenge 3.** Each `scripts/setup.sh` seeds the configuration store's keys itself rather than assuming challenge 1 did. → Tasks 3–6.
2. **Sandbox relaunched mid-track.** Seeding Redis and Postgres must be idempotent — re-seeding must overwrite, never duplicate or error. → Task 2.
3. **Postgres is not ready when the sidecar starts.** → Task 6, readiness wait.
4. **A previous challenge's app still holds port 5001.** → Task 3, port-collision test.
5. **Learner switches language between challenges.** Every `setup.sh` builds all three. → Tasks 4–6.

Plus one specific to this track:

6. **The subscription delivers an empty first callback.** Spec §3.2 flags it as the thing learners trip on: the first callback carries only the subscription ID, no items. An assignment that shows a value arriving immediately is wrong, and a suite that asserts on the first callback's contents is flaky. → pinned in Task 5.

---

## Task 1: Verify the Postgres configuration store's change notification (blocking spike)

Spec §3.2 and §7.4: the Postgres configuration store needs a table and database-side triggers that `NOTIFY` on update. Challenge 4's whole claim is that the live update survives the swap. If it cannot be made to work inside the time budget, challenge 4 changes shape — so this is settled before anything is written.

Throwaway. Deliverable is a findings file.

**Files:**
- Create: `docs/superpowers/notes/2026-10-20-postgres-config-notify-findings.md`

**Interfaces:**
- Consumes: nothing.
- Produces: the exact table schema and trigger SQL that Task 2's setup scripts install, and a yes/no on whether subscribe-driven live updates work.

- [ ] **Step 1: Read the component reference**

Fetch the PostgreSQL configuration store page from the Dapr component reference and record the required table shape, the metadata fields, and the documented trigger/notify mechanism.

- [ ] **Step 2: Stand up Postgres and Dapr on WSL2**

Postgres in Docker; `dapr init`. Create the configuration table and trigger exactly as the reference specifies.

- [ ] **Step 3: Prove a plain get works**

```bash
curl -s "http://localhost:3500/v1.0/configuration/configstore?key=feature-flag"
```
Record the response.

- [ ] **Step 4: Prove the subscription fires on update**

Subscribe, then `UPDATE` the row in `psql`. Record whether the app receives the change, and how long it takes.

- [ ] **Step 5: Write the findings and decide**

Record the schema, the trigger SQL, and the result of step 4. Then:

- Notifications work → challenge 4 is a full swap, as designed.
- Notifications cannot be made to work in budget → challenge 4 becomes a **get-only** swap and the assignment says so plainly. Spec §3.2 permits this explicitly; it does not permit implying the subscription works.

- [ ] **Step 6: Commit the findings file** *(ask first)*

---

## Task 2: Scaffold and shared contract artifacts

**Files:**
- Create (demo repo): `configuration/README.md`
- Create (track repo): `dapr-configuration/README.md`, `dapr-configuration/website-description.md`, `dapr-configuration/_setup/sandbox-setup.sh`
- Create (track repo): `tools/track-tester/variables/dapr_configuration.py`, `tools/track-tester/ci/setup-dapr-configuration.sh`

**Interfaces:**
- Consumes: plan 1 Task 2's patterns; Task 1's schema and trigger SQL.
- Produces:
  - `TRACKS_SRC_DIR`, `CONFIG_BASE` (`<TRACKS_SRC_DIR>/configuration`), `DEMO` (`Demo1-WatchConfig`).
  - Sandbox contract: repo cloned, Redis seeded with `feature-flag=off` and `max-retries=3`, Postgres running with the configuration table and trigger installed and the same two keys seeded, `dapr init` complete, demo pre-built for all three languages.

- [ ] **Step 1: Write the variables file**

`variables/dapr_configuration.py`, same shape as `dapr_secrets.py`, adding `CONFIG_KEYS = ["feature-flag", "max-retries"]`.

- [ ] **Step 2: Write the track README**

All required sections. Description lists the four outcomes from spec §3.2's challenge table.

- [ ] **Step 3: Write `_setup/sandbox-setup.sh`**

Clone the demo repo; `docker login`; `dapr init` with the containers check; `agent variable set` the two pinned versions; seed Redis via `docker exec dapr_redis redis-cli SET`; start Postgres and install Task 1's table and trigger; pre-build the demo for all three languages.

**Idempotency (Review Focus 2):** seeding uses `SET` (not `SETNX`) for Redis and `INSERT … ON CONFLICT DO UPDATE` for Postgres; table and trigger creation uses `IF NOT EXISTS` / `CREATE OR REPLACE`.

- [ ] **Step 4: Write `ci/setup-dapr-configuration.sh`**

Per plan 1 Task 2 step 4, with Postgres provisioning added.

- [ ] **Step 5: Verify it provisions a working sandbox**

Run: `bash tools/track-tester/ci/setup-dapr-configuration.sh`
Expected: exits 0; `docker ps` shows the Dapr containers and Postgres; `redis-cli GET feature-flag` returns `off`; the Postgres table holds both keys.

- [ ] **Step 6: Verify it is idempotent**

Run it a second time. Expected: exits 0, same state, no duplicate rows.

- [ ] **Step 7: Write `configuration/README.md` in the demo repo**

- [ ] **Step 8: Commit** *(ask first)*

---

## Task 3: Challenge 1 — What the Configuration API is for

5 minutes. Read-only, app-config semantics, change notification. One `GET` against the Redis configuration store, and the contrast with the State API.

**Files:**
- Create (demo repo): `configuration/<lang>/Demo1-WatchConfig/` ×3, `configuration/<lang>/resources/configstore-redis.yaml`
- Create (track repo): `dapr-configuration/1-what-is-the-configuration-api/{README.md,notes.md,assignment.md,tabs.md,scripts/setup.sh,tests/challenge.robot}`

**Interfaces:**
- Consumes: `CONFIG_BASE`, `DEMO`, `CONFIG_KEYS` from Task 2.
- Produces:
  - Component name **`configstore`**, type `configuration.redis`, `redisHost: localhost:6379`. The name is fixed for the whole track; challenge 4 swaps the file behind it.
  - App: id `config-watcher`, app port **5001**, Dapr HTTP **3500**.
  - `GET /config/{key}` → `{"key": "<key>", "value": "<value>", "version": "<version>"}`.

- [ ] **Step 1: Write the failing Robot suite**

One case per language, tagged `dotnet`/`python`/`java`, importing `dapr.resource` and `variables/dapr_configuration.py`, `Suite Teardown    Terminate All Processes    kill=True`. Assert `curl -s http://localhost:5001/config/feature-flag` contains `off`, and that the raw API `curl -s "http://localhost:3500/v1.0/configuration/configstore?key=feature-flag"` returns the same value.

- [ ] **Step 2: Add the port-collision test (Review Focus 4)**

`Port 5001 Is Free Before The App Starts`.

- [ ] **Step 3: Run the suite to verify it fails**

Run: `(cd tools/track-tester && uv run robot ../../dapr-configuration/1-what-is-the-configuration-api/tests/challenge.robot)`
Expected: FAIL — the demo directories do not exist.

- [ ] **Step 4: Write the three demo apps**

`GET /config/{key}` via `GetConfiguration` / `get_configuration` / `getConfiguration` against store `configstore`. Plus each app's `dapr.yaml`.

- [ ] **Step 5: Write `configstore-redis.yaml`**

Per Interfaces, in each language's `resources/`.

- [ ] **Step 6: Run the suite to verify it passes**

- [ ] **Step 7: Write the assignment**

5-minute intro; numbered steps; `<details>` per language. The contrast the challenge exists for: the same Redis instance holds state and configuration, and the Configuration API gives you a version and a change feed the State API does not. Close with `---` and a lead-in.

- [ ] **Step 8: Write `README.md`, `notes.md`, `tabs.md`, `scripts/setup.sh`**

`notes.md` uses the full intro opener. `setup.sh` seeds the keys and builds all three languages (Review Focus 1, 5).

- [ ] **Step 9: Verify doc-sync passes**

- [ ] **Step 10: Commit** *(ask first)*

---

## Task 4: Challenge 2 — The component and its parameters

7 minutes.

**Files:**
- Modify (demo repo): `configuration/<lang>/Demo1-WatchConfig/` — add multi-key and all-keys endpoints
- Create (track repo): `dapr-configuration/2-component-and-parameters/{README.md,notes.md,assignment.md,tabs.md,scripts/setup.sh,tests/challenge.robot}`

**Interfaces:**
- Consumes: `configstore`, `config-watcher`, ports 5001/3500 from Task 3.
- Produces: `GET /config` (several keys via repeated `?key=` params) and `GET /config/all` (no keys ⇒ everything).

- [ ] **Step 1: Write the failing suite**

Per language: several keys returns both `feature-flag` and `max-retries`; all-keys returns both; a key that does not exist is absent from the response rather than erroring; the component's Redis metadata matches the state store's (the thing spec §3.2 says learners find surprising).

- [ ] **Step 2: Run the suite to verify it fails**

Expected: FAIL — `/config/all` returns 404.

- [ ] **Step 3: Add the two endpoints to the three demo apps**

- [ ] **Step 4: Run the suite to verify it passes**

- [ ] **Step 5: Write the assignment**

`configuration.redis` field by field, and what changes if you change each. Then one key, several keys, all keys — including that "all" is the empty key list, which reads as a bug until someone says it out loud.

- [ ] **Step 6: Write `README.md`, `notes.md`, `tabs.md`, `scripts/setup.sh`**

`notes.md` uses the "sandbox is being prepared" opener.

- [ ] **Step 7: Verify doc-sync passes**

- [ ] **Step 8: Commit** *(ask first)*

---

## Task 5: Challenge 3 — Subscribe and watch it change

8 minutes. **The aha moment.** The app prints a value; a `redis-cli SET` in the second terminal makes the running app log the new one.

**Files:**
- Modify (demo repo): `configuration/<lang>/Demo1-WatchConfig/` — add subscribe and unsubscribe
- Create (track repo): `dapr-configuration/3-subscribe-and-watch/{README.md,notes.md,assignment.md,tabs.md,scripts/setup.sh,scripts/check.sh,scripts/solve.sh,tests/challenge.robot}`

**Interfaces:**
- Consumes: the demo app and `configstore` from Tasks 3–4.
- Produces: `POST /subscribe` → `{"subscriptionId": "<id>"}`; `POST /unsubscribe/{id}`; a handler that logs `CONFIG UPDATED: <key>=<value>` on each change, which is the string the suite and the assignment's expected output both quote.

- [ ] **Step 1: Write the failing suite**

Per language:
- Subscribe, then `docker exec dapr_redis redis-cli SET feature-flag on`, then `Wait Until Log Contains` the app log for `CONFIG UPDATED: feature-flag=on`. **This is the aha, asserted.**
- Unsubscribe by ID, `SET feature-flag off`, and assert the log does **not** gain a second `CONFIG UPDATED` line within a bounded wait.

- [ ] **Step 2: Add the empty-first-callback test (Review Focus 6)**

Assert that the first callback after subscribing carries the subscription ID and **no** items — so the assignment cannot claim a value arrives immediately, and the suite cannot become flaky by asserting on it.

- [ ] **Step 3: Run the suite to verify it fails**

Expected: FAIL — `/subscribe` returns 404.

- [ ] **Step 4: Add subscribe/unsubscribe to the three demo apps**

Log exactly `CONFIG UPDATED: <key>=<value>` per change. The empty first callback is logged distinctly so the learner sees it rather than wondering.

- [ ] **Step 5: Run the suite to verify it passes**

- [ ] **Step 6: Write `check.sh` and `solve.sh`**

`check.sh` asserts the app log contains a `CONFIG UPDATED` line, with `fail-message "No config update received — did you SET the key in the second terminal while the app was subscribed?"`.

- [ ] **Step 7: Write the assignment**

Two terminals side by side: the app subscribed in one, `redis-cli` in the other. Call out the empty first callback before the learner hits it. Then unsubscribe and show the updates stop.

- [ ] **Step 8: Write `README.md`, `notes.md`, `tabs.md`, `scripts/setup.sh`**

- [ ] **Step 9: Verify doc-sync passes**

- [ ] **Step 10: Commit** *(ask first)*

---

## Task 6: Challenge 4 — Swap the provider

8 minutes. Redis → PostgreSQL, same subscribe call, same live update. Shape depends on Task 1's finding.

**Files:**
- Create (demo repo): `configuration/<lang>/resources/configstore-postgres.yaml`
- Create (track repo): `dapr-configuration/4-swap-the-provider/{README.md,notes.md,assignment.md,tabs.md,scripts/setup.sh,scripts/check.sh,scripts/solve.sh,tests/challenge.robot}`
- Modify (track repo): `dapr-configuration/_setup/sandbox-setup.sh` — Postgres readiness wait

**Interfaces:**
- Consumes: the demo app and the `configstore` component name from Task 3; Task 1's schema and trigger.
- Produces: `configstore-postgres.yaml` — type `configuration.postgresql`, **component name `configstore`**, pointing at the Task 2 Postgres.

- [ ] **Step 1: Write the failing suite**

Per language: the **unmodified** app returns `feature-flag` from Postgres, and — if Task 1 confirmed notifications — a `psql` `UPDATE` produces `CONFIG UPDATED: feature-flag=on` in the app log, exactly as Redis did. Assert the app source is unchanged from challenge 3, so "the code didn't change" is proved.

If Task 1 found notifications unworkable, the suite asserts the get-only behaviour and nothing about subscriptions.

- [ ] **Step 2: Add the Postgres readiness test (Review Focus 3)**

Assert Postgres accepts connections before any app starts, and that the readiness wait in `sandbox-setup.sh` exits non-zero on timeout.

- [ ] **Step 3: Run the suite to verify it fails**

Expected: FAIL — `configstore-postgres.yaml` does not exist.

- [ ] **Step 4: Add the Postgres readiness wait to `sandbox-setup.sh`**

Bounded `pg_isready` retry loop; non-zero exit with a clear message on timeout.

- [ ] **Step 5: Write `configstore-postgres.yaml`**

Per Interfaces, for all three languages.

- [ ] **Step 6: Run the suite to verify it passes**

- [ ] **Step 7: Write `check.sh` and `solve.sh`**

`check.sh` asserts the loaded `configstore` is `configuration.postgresql` and the app still answers.

- [ ] **Step 8: Write the assignment**

The swap, then the point: two different databases, one unchanged application. If Task 1 downgraded this to get-only, say so plainly here and explain why — spec §3.2.

- [ ] **Step 9: Write `README.md`, `notes.md`, `tabs.md`, `scripts/setup.sh`**

Close the track: `---`, recap, Discord `#university` pointer.

- [ ] **Step 10: Verify doc-sync passes**

- [ ] **Step 11: Commit** *(ask first)*

---

## Task 7: CI workflow and whole-track verification

**Files:**
- Create (track repo): `.github/workflows/test-dapr-configuration.yml`

**Interfaces:**
- Consumes: `ci/setup-dapr-configuration.sh`; all four suites.
- Produces: nothing downstream.

- [ ] **Step 1: Write the workflow**

Copy the shape from plan 1 Task 7 — `docsync` job looping all four challenges, `languages` matrix job with `fail-fast: false` over `[dotnet, java, python]`, explicit `~/.m2` cache, `rebot` merge, failure summary artifact. Schedule **07:00 UTC**; `pull_request` paths `dapr-configuration/**`, `tools/track-tester/**`, and the workflow file.

- [ ] **Step 2: Pre-warm Maven outside the timed run**

- [ ] **Step 3: Run the whole track locally**

Run: `(cd tools/track-tester && uv run robot --name "Dapr Configuration" ../../dapr-configuration/*/tests/challenge.robot)`
Expected: PASS, all languages, all four challenges.

- [ ] **Step 4: Verify the workflow on a branch**

- [ ] **Step 5: Confirm the time budget**

Expected: 28 minutes across the four assignments.

- [ ] **Step 6: Confirm the aha moment lands**

On a real Instruqt sandbox, complete challenge 3 in all three languages. The value must visibly change in the running app's output without a restart, fast enough that the learner connects the `SET` to the log line. If the delay is long enough to break that connection, say the expected delay in the assignment rather than letting the learner think it failed.

- [ ] **Step 7: Commit** *(ask first)*
