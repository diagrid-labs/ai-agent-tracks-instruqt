# Dapr Actors Track Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `dapr-actors` Instruqt track — four challenges, three languages, drift-tested — whose aha moment is 100 concurrent increments landing on exactly 100 through an actor, and losing updates when the same 100 hit the state store directly.

**Architecture:** One demo app per language in `ai-agent-tracks-instruqt/actors/<language>/`: a counter actor plus a deliberately naive read-modify-write path against the same state store, so challenge 2 can run both and compare. .NET uses **`Dapr.Actors.Next`**, not the legacy `Dapr.Actors`. Track content in `dapr-university-instruqt/dapr-actors/`.

**Tech Stack:** Dapr runtime 1.19+ (see Task 1); `Dapr.Actors.Next` (.NET 10), `dapr` actor SDK (Python 3.12), `io.dapr:dapr-sdk` actors (Java 17, Spring Boot); Redis and PostgreSQL actor state stores; Robot Framework 7.x via `uv`.

**Spec:** `docs/superpowers/specs/2026-10-20-dapr-building-block-tracks-design.md`

Plan 5 of 5, and the one with a gate in front of it. **The shared contract artifacts are defined in plan 1 (`2026-10-20-dapr-secrets-track.md`, Task 2).** Read it before Task 2 here.

This is the most from-scratch of the five: a prerelease .NET package, no Next-specific quickstart, and **no upstream Python or Java actor quickstart at all** — `dapr/quickstarts/actors` is C# only. Budget accordingly; the other four tracks had upstream references to adapt and this one does not.

## Global Constraints

Plan 1's Global Constraints apply in full. Track-specific values:

- **Track slug:** `dapr-actors`. **Demo code:** `actors/<language>/`.
- **Challenge slugs:** `1-what-are-actors`, `2-one-hundred-at-once`, `3-state-timers-and-reminders`, `4-swap-the-state-store`.
- **Time budget:** 6 + 8 + 8 + 6 = 28 minutes; `## Time limit (minutes)` 30, `### Extra time` 10.
- **CI schedule:** daily at **07:45 UTC**.
- **.NET uses `Dapr.Actors.Next`.** Not `Dapr.Actors`, which receives security fixes only. Next is not API-compatible with it, requires Dapr runtime 1.18.0+, and delivers callbacks over app-initiated `SubscribeActorEvents` gRPC streams rather than inbound HTTP — which changes how the app is hosted and how the suite probes readiness.
- **The actor state store must set `actorStateStore: "true"`.** Only stores supporting both transactional operations and ETag qualify; Redis and PostgreSQL both do.
- **Git:** no `git add` / `commit` / `push` without the user explicitly asking in the current conversation. Ask before every commit step.

## Review Focus

Plan 1's five classes apply, with this track's specifics:

1. **Learner jumps to challenge 3.** Each `scripts/setup.sh` builds the demo itself. → Tasks 3–6.
2. **Sandbox relaunched mid-track.** Actor state persists in Redis across relaunches, so a counter from a previous session starts at a non-zero value and challenge 2's "exactly 100" reads as broken. `sandbox-setup.sh` must clear this track's actor state. → Task 2.
3. **The placement service is not ready when the app starts.** Actors need `dapr_placement`; without it the app starts but actor invocation hangs rather than erroring clearly. → Task 2 and Task 3.
4. **A previous challenge's app still holds port 5001.** → Task 3.
5. **Learner switches language between challenges.** → Tasks 4–6.

Plus two specific to this track:

6. **Challenge 2's comparison is non-deterministic.** The lost-update path may, by luck, produce exactly 100 on a fast machine with little contention. An assignment promising "you will see fewer than 100" will be wrong some of the time, and a suite asserting `< 100` will flake. The demo must make contention reliable, and the assertion must be `actor == 100` plus `direct != actor` across enough runs to be certain. → Task 4.
7. **Reminders fire after a restart** — that is the lesson of challenge 3 — which means a reminder from an earlier run can fire during a later challenge. Reminders are challenge-scoped and deleted in teardown. → Tasks 5–6.

---

## Task 1: Dapr 1.19 GA gate (blocking)

Spec §7.1: `Dapr.Actors.Next` exists on NuGet only as `1.19.0-preview.1` through `1.19.0-rc.3`. There is no stable release. **The spec's default is to wait.**

This task is a decision, not a build. It has a checkable result and it gates everything below it.

**Files:**
- Create: `docs/superpowers/notes/2026-10-20-actors-next-ga-check.md`

**Interfaces:**
- Consumes: nothing.
- Produces: a go/no-go, and if go, the exact package and runtime versions Tasks 2–7 pin.

- [ ] **Step 1: Check whether Dapr 1.19 has shipped**

```bash
curl -s "https://api.github.com/repos/dapr/dapr/releases/latest" | python -c "import sys,json;d=json.load(sys.stdin);print(d['tag_name'], d['published_at'])"
curl -s "https://api.nuget.org/v3-flatcontainer/dapr.actors.next/index.json" | python -c "import sys,json;v=json.load(sys.stdin)['versions'];print([x for x in v if '-' not in x][-3:] or 'NO STABLE RELEASE')"
```

- [ ] **Step 2: Decide**

- **A stable `Dapr.Actors.Next` exists** and the runtime is 1.19+ → record the versions and proceed to Task 2.
- **Still prerelease** → **stop.** Record the check and park the track. Do not build against an RC on a public university track without an explicit decision from the track owner; spec §7.1 states this is a judgement about what the university's name is attached to, not a technical call. Re-run this task when 1.19 ships.

- [ ] **Step 3: Write the check note**

Record what was found, the date, and the decision. If parked, note what re-triggers it so a later reader does not have to reconstruct the reasoning.

- [ ] **Step 4: Commit the note** *(ask first)*

---

## Task 2: Scaffold and shared contract artifacts

**Files:**
- Create (demo repo): `actors/README.md`
- Create (track repo): `dapr-actors/README.md`, `dapr-actors/website-description.md`, `dapr-actors/_setup/sandbox-setup.sh`
- Create (track repo): `tools/track-tester/variables/dapr_actors.py`, `tools/track-tester/ci/setup-dapr-actors.sh`

**Interfaces:**
- Consumes: plan 1 Task 2's patterns; Task 1's pinned versions.
- Produces:
  - `TRACKS_SRC_DIR`, `ACTORS_BASE` (`<TRACKS_SRC_DIR>/actors`), `DEMO` (`Demo1-Counter`).
  - `ACTOR_TYPE` (`CounterActor`), `ACTOR_ID` (`counter-1`), `CONCURRENT_CALLS` (`100`).
  - Sandbox contract: repo cloned, `dapr init` complete with `dapr_placement` running, prior actor state cleared, Postgres running with `actorStateStore` enabled, demo pre-built for all three languages.

- [ ] **Step 1: Write the variables file**

`variables/dapr_actors.py`, same shape as `dapr_secrets.py`, plus `ACTOR_TYPE`, `ACTOR_ID` and `CONCURRENT_CALLS`. `CONCURRENT_CALLS` lives here so the assignment, the suite and the demo cannot disagree about what "100" is.

- [ ] **Step 2: Write the track README**

All required sections. Teaser leads with turn-based concurrency, since the number on screen is the whole pitch.

- [ ] **Step 3: Write `_setup/sandbox-setup.sh`**

Clone the demo repo; `docker login`; `dapr init` with the containers check including **`dapr_placement`** (Review Focus 3); `agent variable set` the pinned versions; clear prior actor state with `docker exec dapr_redis redis-cli` scoped to this track's actor keys (Review Focus 2); start Postgres with the actor state store schema; pre-build the demo for all three languages.

**Do not** clear the whole Redis keyspace — the Dapr containers are shared and a blanket `FLUSHALL` breaks anything else the sandbox holds.

- [ ] **Step 4: Write `ci/setup-dapr-actors.sh`**

Per plan 1 Task 2 step 4, with Postgres provisioning. Pin the .NET package feed to include prerelease only if Task 1 concluded "go" on an RC.

- [ ] **Step 5: Verify it provisions a working sandbox**

Run: `bash tools/track-tester/ci/setup-dapr-actors.sh`
Expected: exits 0; `docker ps` shows `dapr_placement` and Postgres; `~/ai-agent-tracks-instruqt/actors` exists.

- [ ] **Step 6: Verify it clears prior actor state**

Set a counter to 50, re-run the script, read it back.
Expected: the counter is absent or zero, and unrelated Redis keys are untouched.

- [ ] **Step 7: Write `actors/README.md` in the demo repo**

Note prominently that the Python and Java demos have no upstream equivalent, so a future maintainer does not go looking for one.

- [ ] **Step 8: Commit** *(ask first)*

---

## Task 3: Challenge 1 — What actors are for

6 minutes — a minute longer than the other tracks' openers, because actors need identity, activation and placement explained before anything is invoked.

**Files:**
- Create (demo repo): `actors/<lang>/Demo1-Counter/` ×3, `actors/<lang>/resources/statestore-redis.yaml`
- Create (track repo): `dapr-actors/1-what-are-actors/{README.md,notes.md,assignment.md,tabs.md,scripts/setup.sh,tests/challenge.robot}`

**Interfaces:**
- Consumes: `ACTORS_BASE`, `DEMO`, `ACTOR_TYPE`, `ACTOR_ID` from Task 2.
- Produces:
  - Component name **`statestore`**, type `state.redis`, with `actorStateStore: "true"`. Fixed for the whole track; challenge 4 swaps the file behind it.
  - App: id `counter-app`, app port **5001**, Dapr HTTP **3500**.
  - Actor `CounterActor` with `Increment()` and `GetCount()`.
  - `POST /counter/{id}/increment` and `GET /counter/{id}` as the HTTP surface over the actor.

- [ ] **Step 1: Write the failing Robot suite**

One case per language, tagged `dotnet`/`python`/`java`, importing `dapr.resource` and `variables/dapr_actors.py`, `Suite Teardown    Terminate All Processes    kill=True`. Increment `counter-1` three times, assert `GET /counter/counter-1` returns 3, and assert a second actor id starts at zero — proving identity, not a global.

**.NET readiness note:** Next's callbacks arrive over app-initiated gRPC streams, so the HTTP readiness probe used by the other tracks may report ready before the actor stream is established. Probe actor readiness by invoking the actor and retrying, not by curling the app port.

- [ ] **Step 2: Add the placement-readiness test (Review Focus 3)**

Assert `dapr_placement` is running before the app starts, so a missing placement service fails here with a clear message instead of hanging an actor call later.

- [ ] **Step 3: Add the port-collision test (Review Focus 4)**

- [ ] **Step 4: Run the suite to verify it fails**

Run: `(cd tools/track-tester && uv run robot ../../dapr-actors/1-what-are-actors/tests/challenge.robot)`
Expected: FAIL — the demo directories do not exist.

- [ ] **Step 5: Write the three demo apps**

.NET with `Dapr.Actors.Next` — DI registration, options and source generators, per its docs; **not** the legacy reflection-based registration. Python and Java with their SDKs' actor support, written from scratch.

- [ ] **Step 6: Write `statestore-redis.yaml`**

Per Interfaces, including `actorStateStore: "true"`, in each language's `resources/`.

- [ ] **Step 7: Run the suite to verify it passes**

- [ ] **Step 8: Write the assignment**

Identity, activation, placement — then invoke. Close with when an actor is the **wrong** tool, which matters more here than in the other tracks because actors are the building block people most often reach for by mistake.

- [ ] **Step 9: Write `README.md`, `notes.md`, `tabs.md`, `scripts/setup.sh`**

`notes.md` uses the full intro opener. `setup.sh` builds all three languages.

- [ ] **Step 10: Verify doc-sync passes**

- [ ] **Step 11: Commit** *(ask first)*

---

## Task 4: Challenge 2 — 100 at once

8 minutes. **The aha moment, and it lands at challenge 2** — earliest of the five tracks, as spec §4 requires.

**Files:**
- Modify (demo repo): `actors/<lang>/Demo1-Counter/` — add the direct-state-store path and the concurrent driver
- Create (track repo): `dapr-actors/2-one-hundred-at-once/{README.md,notes.md,assignment.md,tabs.md,scripts/setup.sh,scripts/check.sh,scripts/solve.sh,tests/challenge.robot}`

**Interfaces:**
- Consumes: `CounterActor`, the HTTP surface, and `CONCURRENT_CALLS` from Tasks 2–3.
- Produces:
  - `POST /counter/{id}/increment-direct` — a deliberately naive read-modify-write straight against `statestore`, no ETag, no transaction.
  - `POST /race/{id}?mode=actor|direct` — fires `CONCURRENT_CALLS` concurrent increments and returns `{"mode": "...", "expected": 100, "actual": n}`.

- [ ] **Step 1: Write the failing suite**

Per language:
- `mode=actor` returns `actual == 100`, exactly, every time.
- `mode=direct` returns `actual != 100`.
- Run the direct case **five times** and assert at least four lose updates (Review Focus 6). A single run can get lucky; a flaky assertion here destroys trust in the one challenge the whole track exists for.
- Assert the two modes write to the same state store, so nobody can dismiss the comparison as apples and oranges.

- [ ] **Step 2: Run the suite to verify it fails**

Expected: FAIL — `/race/{id}` returns 404.

- [ ] **Step 3: Add the direct path and the driver to the three demo apps**

The direct path must make contention **reliable**, not incidental: read, a small deliberate delay, then write. Without the delay a fast machine serializes the calls by accident and the lesson evaporates. The delay is the honest part of the demo — it stands in for the real work a real handler does between read and write — and the assignment says so rather than hiding it.

- [ ] **Step 4: Run the suite to verify it passes**

- [ ] **Step 5: Verify the direct path's flakiness is bounded**

Run the suite's direct case 20 times.
Expected: lost updates in at least 18. If it is less reliable than that, increase the delay or the concurrency until it is — then update `CONCURRENT_CALLS` in the variables file so assignment, suite and demo stay in agreement.

- [ ] **Step 6: Write `check.sh` and `solve.sh`**

`check.sh` asserts an actor run returned exactly 100, with `fail-message "The actor run didn't total 100 — is the counter cleared? Try GET /counter/counter-1 first."`

- [ ] **Step 7: Write the assignment**

Actor first — 100 calls, 100. Then direct — 100 calls, fewer. Give the learner the number to expect before they run it, so the result confirms rather than confuses. Then the explanation: turn-based concurrency means one call at a time per actor, and that is a guarantee, not a lock you wrote.

- [ ] **Step 8: Write `README.md`, `notes.md`, `tabs.md`, `scripts/setup.sh`**

- [ ] **Step 9: Verify doc-sync passes**

- [ ] **Step 10: Commit** *(ask first)*

---

## Task 5: Challenge 3 — State, timers and reminders

8 minutes. Actor state persistence, and the difference that matters: a reminder survives a restart because the Scheduler holds it; a timer does not.

**Files:**
- Modify (demo repo): `actors/<lang>/Demo1-Counter/` — add timer and reminder registration
- Create (track repo): `dapr-actors/3-state-timers-and-reminders/{README.md,notes.md,assignment.md,tabs.md,scripts/setup.sh,scripts/check.sh,scripts/solve.sh,tests/challenge.robot}`

**Interfaces:**
- Consumes: `CounterActor` from Tasks 3–4.
- Produces: `POST /counter/{id}/timer` and `POST /counter/{id}/reminder`, both registering against the actor; handlers logging `ACTOR TIMER FIRED: <id>` and `ACTOR REMINDER FIRED: <id>`; `DELETE /counter/{id}/reminder`.

- [ ] **Step 1: Write the failing suite**

Per language:
- Increment, stop the app, restart, and assert the count survived — actor state is persisted, not in memory.
- Register both a timer and a reminder; wait for both to fire.
- `Stop Process With SIGINT`, restart into a fresh log, and assert `ACTOR REMINDER FIRED:` appears while `ACTOR TIMER FIRED:` does not. Same shape as the Jobs track's durability test, and the same omission to avoid: assert the timer's **absence**, or the test passes on an app that re-registered it.
- Case teardown deletes the reminder (Review Focus 7).

- [ ] **Step 2: Run the suite to verify it fails**

Expected: FAIL — `/timer` and `/reminder` return 404.

- [ ] **Step 3: Add timer and reminder registration to the three demo apps**

- [ ] **Step 4: Run the suite to verify it passes**

- [ ] **Step 5: Write `check.sh` and `solve.sh`**

- [ ] **Step 6: Write the assignment**

State first, then the timer/reminder distinction with the restart as proof. Say where reminders live — the Scheduler, the same service the Jobs track used — because the two tracks reinforce each other and a learner who did Jobs will recognise it.

- [ ] **Step 7: Write `README.md`, `notes.md`, `tabs.md`, `scripts/setup.sh`**

- [ ] **Step 8: Verify doc-sync passes**

- [ ] **Step 9: Commit** *(ask first)*

---

## Task 6: Challenge 4 — Swap the actor state store

6 minutes. Redis → PostgreSQL, same actor code.

**Files:**
- Create (demo repo): `actors/<lang>/resources/statestore-postgres.yaml`
- Create (track repo): `dapr-actors/4-swap-the-state-store/{README.md,notes.md,assignment.md,tabs.md,scripts/setup.sh,scripts/check.sh,scripts/solve.sh,tests/challenge.robot}`
- Modify (track repo): `dapr-actors/_setup/sandbox-setup.sh` — Postgres readiness wait

**Interfaces:**
- Consumes: `CounterActor` and the `statestore` component name from Task 3.
- Produces: `statestore-postgres.yaml` — type `state.postgresql`, **component name `statestore`**, with `actorStateStore: "true"`, pointing at the Task 2 Postgres.

- [ ] **Step 1: Write the failing suite**

Per language: the **unmodified** actor app increments and reads back correctly against Postgres, and a `mode=actor` race still returns exactly 100 — the guarantee is a property of the actor runtime, not of Redis. Assert the app source is unchanged from challenge 2.

- [ ] **Step 2: Add the negative test for `actorStateStore`**

With `actorStateStore` absent or `"false"`, assert actor invocation fails with a message naming the missing capability. This is the field the challenge is about; proving what happens without it is what makes it more than a line of YAML to copy.

- [ ] **Step 3: Add the Postgres readiness test (Review Focus 3)**

- [ ] **Step 4: Run the suite to verify it fails**

Expected: FAIL — `statestore-postgres.yaml` does not exist.

- [ ] **Step 5: Add the Postgres readiness wait to `sandbox-setup.sh`**

Bounded `pg_isready` retry; non-zero exit with a clear message on timeout.

- [ ] **Step 6: Write `statestore-postgres.yaml`**

Per Interfaces, for all three languages.

- [ ] **Step 7: Run the suite to verify it passes**

- [ ] **Step 8: Write `check.sh` and `solve.sh`**

`check.sh` asserts the loaded `statestore` is `state.postgresql` with `actorStateStore` true and the actor still answers.

- [ ] **Step 9: Write the assignment**

The swap, then `actorStateStore: "true"` and why not every store qualifies — transactional operations and ETag, which is a concrete answer to a question the docs leave abstract.

Close the track: `---`, recap, Discord `#university` pointer.

- [ ] **Step 10: Verify doc-sync passes**

- [ ] **Step 11: Commit** *(ask first)*

---

## Task 7: CI workflow and whole-track verification

**Files:**
- Create (track repo): `.github/workflows/test-dapr-actors.yml`

**Interfaces:**
- Consumes: `ci/setup-dapr-actors.sh`; all four suites.
- Produces: nothing downstream.

- [ ] **Step 1: Write the workflow**

Copy the shape from plan 1 Task 7. Schedule **07:45 UTC**; `pull_request` paths `dapr-actors/**`, `tools/track-tester/**`, and the workflow file. `setup-dotnet` pins the version Task 1 recorded.

- [ ] **Step 2: Pre-warm Maven outside the timed run**

- [ ] **Step 3: Run the whole track locally**

Run: `(cd tools/track-tester && uv run robot --name "Dapr Actors" ../../dapr-actors/*/tests/challenge.robot)`
Expected: PASS, all languages, all four challenges.

- [ ] **Step 4: Verify the workflow on a branch, three times**

Three consecutive runs, not two. Challenge 2 asserts on a race and challenge 3 on a restart; this is the most timing-sensitive track of the five, and the cost of a flaky aha moment is that the maintainer stops believing the suite.

- [ ] **Step 5: Confirm the time budget**

Expected: 28 minutes across the four assignments.

- [ ] **Step 6: Confirm the aha moment lands**

On a real Instruqt sandbox, complete challenge 2 in all three languages. The actor run must total exactly 100 and the direct run must visibly lose updates, on the sandbox's CPU budget rather than a developer laptop's. If the sandbox serializes the direct path by being slow, raise the concurrency or the delay until contention is reliable there — the sandbox is the environment that counts.

- [ ] **Step 7: If the track shipped on a prerelease package, record the re-pin obligation**

If Task 1 concluded "go" on an RC, note in the track's `notes.md` and in this plan what must be re-pinned when 1.19 goes GA, and who owns doing it. A prerelease pin with no owner becomes a silent liability.

- [ ] **Step 8: Commit** *(ask first)*
