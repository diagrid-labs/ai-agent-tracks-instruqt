# Dapr Jobs Track Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `dapr-jobs` Instruqt track — four challenges, three languages, drift-tested — whose aha moment is killing the app, restarting it, and watching the job fire anyway while an in-process timer stays dead.

**Architecture:** One demo app per language in `ai-agent-tracks-instruqt/jobs/<language>/`, exposing both a Dapr job and an in-process timer so challenge 3 can kill the process and show the two outcomes side by side. **This track has no component YAML** — the Scheduler is a control-plane service `dapr init` already started — so act 2 covers API parameters only and act 3 is replaced by the durability demo. Track content in `dapr-university-instruqt/dapr-jobs/`.

**Tech Stack:** Dapr 1.18.x self-hosted (Jobs API stable since 1.18); ASP.NET Core minimal API (.NET 10), FastAPI (Python 3.12), Spring Boot (Java 17); Robot Framework 7.x via `uv`.

**Spec:** `docs/superpowers/specs/2026-10-20-dapr-building-block-tracks-design.md`

Plan 4 of 5. **The shared contract artifacts are defined in plan 1 (`2026-10-20-dapr-secrets-track.md`, Task 2).** Read it before Task 2 here.

## Global Constraints

Plan 1's Global Constraints apply in full. Track-specific values:

- **Track slug:** `dapr-jobs`. **Demo code:** `jobs/<language>/`.
- **Challenge slugs:** `1-what-is-the-jobs-api`, `2-scheduling-parameters`, `3-kill-it-and-watch-it-survive`, `4-managing-jobs`.
- **Time budget:** 5 + 8 + 8 + 7 = 28 minutes; `## Time limit (minutes)` 30, `### Extra time` 10.
- **CI schedule:** daily at **07:30 UTC**.
- **No component YAML and no `resources/` directory for the Jobs API itself.** If a challenge appears to need one, the design has drifted — stop and re-read spec §3.4.
- **Use the stable Jobs API**, not the deprecated alpha RPCs. `ScheduleJob`, `GetJob`, `DeleteJob`, `OnJobEvent`.
- **Delivery is at-least-once.** Every handler in every language must be idempotent, and the assignment must say why.
- **Git:** no `git add` / `commit` / `push` without the user explicitly asking in the current conversation. Ask before every commit step.

## Review Focus

Plan 1's five classes apply, with this track's specifics:

1. **Learner jumps to challenge 3.** Each `scripts/setup.sh` builds the demo itself. → Tasks 3–6.
2. **Sandbox relaunched mid-track.** Jobs persist in the Scheduler across app restarts — that is the point — so a relaunch can leave jobs from a previous session firing into a new one. `sandbox-setup.sh` must delete any job this track creates before the learner starts. → Task 2.
3. **A job name already exists.** Creating a job with an existing name fails unless `overwrite` is true, and a learner who re-runs challenge 1's command hits exactly that. → Task 3.
4. **A previous challenge's app still holds port 5001.** → Task 3.
5. **Learner switches language between challenges.** → Tasks 4–6.

Plus two specific to this track:

6. **A repeating job from an earlier challenge is still firing** during a later one, so the learner sees triggers they did not schedule and cannot tell which challenge they came from. Every job name is challenge-scoped, and every challenge's teardown deletes its own jobs. → Tasks 4–6.
7. **The job fires later than the learner expects.** Jobs are guaranteed never to fire *before* due time, with no promise about how soon after. An assignment implying "exactly on the second" will read as broken. → Task 4.

---

## Task 1: Verify the Python and Java job-trigger mechanics (blocking spike)

Spec §3.4 and §7.5: the trigger callback is documented only for .NET and Go. .NET registers `MapDaprScheduledJobHandler`, an HTTP endpoint at `/job/<job-name>`; Go uses a gRPC `AddJobEventHandler`. Python and Java are unknown, and a track that cannot receive a trigger in two of its three languages has no challenges at all.

Throwaway. Deliverable is a findings file.

**Files:**
- Create: `docs/superpowers/notes/2026-10-20-jobs-sdk-callback-findings.md`

**Interfaces:**
- Consumes: nothing.
- Produces: per language, the exact scheduling call signature and the exact handler registration, plus whether the app must run with `--app-protocol grpc`.

- [ ] **Step 1: Read the upstream quickstarts**

`dapr/quickstarts/jobs/python/sdk` and `dapr/quickstarts/jobs/java/sdk`, plus `jobs/csharp` for the .NET baseline. Record for each: how the job is scheduled, how the trigger is received, and what `dapr run` flags the app needs.

- [ ] **Step 2: Confirm the Python method names**

Spec §3.4 warns third-party examples still show `schedule_job_alpha1`. Check the installed `dapr` 1.18.3 package for the current names and record whether the stable names exist or the alpha ones are still the only option.

- [ ] **Step 3: Run one job end to end in each language on WSL2**

Schedule a job that fires in 10 seconds, receive the trigger, log it. Record the verbatim log line each SDK produces — challenge 1's expected-output block quotes it.

- [ ] **Step 4: Record whether an HTTP app can receive triggers in all three**

If Python or Java requires a gRPC app server while .NET uses HTTP, the three `<details>` blocks differ structurally, not just in syntax. Record it now so the assignment is written once rather than rewritten.

- [ ] **Step 5: Write the findings**

If a language cannot receive a trigger with its current SDK, stop and raise it before writing anything — the track cannot ship in three languages as specified.

- [ ] **Step 6: Commit the findings file** *(ask first)*

---

## Task 2: Scaffold and shared contract artifacts

**Files:**
- Create (demo repo): `jobs/README.md`
- Create (track repo): `dapr-jobs/README.md`, `dapr-jobs/website-description.md`, `dapr-jobs/_setup/sandbox-setup.sh`
- Create (track repo): `tools/track-tester/variables/dapr_jobs.py`, `tools/track-tester/ci/setup-dapr-jobs.sh`

**Interfaces:**
- Consumes: plan 1 Task 2's patterns; Task 1's findings.
- Produces:
  - `TRACKS_SRC_DIR`, `JOBS_BASE` (`<TRACKS_SRC_DIR>/jobs`), `DEMO` (`Demo1-Jobs`).
  - `JOB_NAMES` — the challenge-scoped job names (`ch1-greeting`, `ch2-report`, `ch3-heartbeat`, `ch4-cleanup`), so teardown can delete exactly what each challenge created (Review Focus 6).
  - Sandbox contract: repo cloned, `dapr init` complete with the Scheduler container running, any pre-existing track jobs deleted, demo pre-built for all three languages.

- [ ] **Step 1: Write the variables file**

`variables/dapr_jobs.py`, same shape as `dapr_secrets.py`, plus `JOB_NAMES` and the per-language trigger log lines Task 1 recorded.

- [ ] **Step 2: Write the track README**

All required sections. Teaser leads with durability, since that is what the track is for.

- [ ] **Step 3: Write `_setup/sandbox-setup.sh`**

Clone the demo repo; `docker login`; `dapr init` with the containers check — **including `dapr_scheduler`**, which this track depends on and the existing check already covers; `agent variable set` the pinned versions; delete any job in `JOB_NAMES` left from a previous launch (Review Focus 2); pre-build the demo for all three languages.

- [ ] **Step 4: Write `ci/setup-dapr-jobs.sh`**

Per plan 1 Task 2 step 4. No store provisioning needed — the Scheduler is built in, which is worth a comment in the script so a future reader does not go looking for the missing component.

- [ ] **Step 5: Verify it provisions a working sandbox**

Run: `bash tools/track-tester/ci/setup-dapr-jobs.sh`
Expected: exits 0; `docker ps` shows `dapr_scheduler` among the Dapr containers; `~/ai-agent-tracks-instruqt/jobs` exists.

- [ ] **Step 6: Verify it is idempotent and clears stale jobs**

Schedule a job named `ch3-heartbeat`, then re-run the script.
Expected: exits 0, and the job is gone.

- [ ] **Step 7: Write `jobs/README.md` in the demo repo**

- [ ] **Step 8: Commit** *(ask first)*

---

## Task 3: Challenge 1 — What the Jobs API is for

5 minutes. Schedule a one-shot job, watch it trigger. The contrast with `Timer` / `BackgroundService` / `@Scheduled` is stated here and proved in challenge 3.

**Files:**
- Create (demo repo): `jobs/<lang>/Demo1-Jobs/` ×3
- Create (track repo): `dapr-jobs/1-what-is-the-jobs-api/{README.md,notes.md,assignment.md,tabs.md,scripts/setup.sh,tests/challenge.robot}`

**Interfaces:**
- Consumes: `JOBS_BASE`, `DEMO`, `JOB_NAMES` from Task 2.
- Produces:
  - App: id `job-runner`, app port **5001**, Dapr HTTP **3500**. If Task 1 found Python or Java needs gRPC, the port contract is per language and recorded here.
  - `POST /jobs/{name}` schedules a job; the handler logs `JOB FIRED: <name> at <timestamp>`, the string the suite and assignment both quote.
  - `GET /fired` returns the list of job names fired so far, so assertions do not depend on log scraping alone.

- [ ] **Step 1: Write the failing Robot suite**

One case per language, tagged `dotnet`/`python`/`java`, importing `dapr.resource` and `variables/dapr_jobs.py`, `Suite Teardown    Terminate All Processes    kill=True`. Schedule `ch1-greeting` with a 10-second due time, then `Wait Until Log Contains` the app log for `JOB FIRED: ch1-greeting`, and assert `GET /fired` contains it. Case teardown deletes the job (Review Focus 6).

- [ ] **Step 2: Add the duplicate-name test (Review Focus 3)**

Schedule `ch1-greeting` twice without `overwrite`; assert the second attempt fails with a message naming the conflict, and that scheduling it again **with** `overwrite: true` succeeds. A learner re-running the command hits this, so the assignment must cover it.

- [ ] **Step 3: Add the port-collision test (Review Focus 4)**

- [ ] **Step 4: Run the suite to verify it fails**

Run: `(cd tools/track-tester && uv run robot ../../dapr-jobs/1-what-is-the-jobs-api/tests/challenge.robot)`
Expected: FAIL — the demo directories do not exist.

- [ ] **Step 5: Write the three demo apps**

Scheduling and handler registration exactly as Task 1 recorded per language. Handlers are idempotent — a job that fires twice must not double-count in `/fired`, because delivery is at-least-once.

- [ ] **Step 6: Run the suite to verify it passes**

- [ ] **Step 7: Write the assignment**

Schedule, wait, see it fire. Then why not an in-process timer — stated here, proved in challenge 3. Note that the Scheduler is already running and there is nothing to configure, because a learner who has done the other tracks will go looking for a component file.

- [ ] **Step 8: Write `README.md`, `notes.md`, `tabs.md`, `scripts/setup.sh`**

`notes.md` uses the full intro opener. `setup.sh` builds all three languages.

- [ ] **Step 9: Verify doc-sync passes**

- [ ] **Step 10: Commit** *(ask first)*

---

## Task 4: Challenge 2 — The scheduling parameters

8 minutes. The act-2 challenge: `schedule`, `dueTime`, `repeats`, `ttl`, `data`, `overwrite`.

**Files:**
- Modify (demo repo): `jobs/<lang>/Demo1-Jobs/` — accept the full parameter set
- Create (track repo): `dapr-jobs/2-scheduling-parameters/{README.md,notes.md,assignment.md,tabs.md,scripts/setup.sh,tests/challenge.robot}`

**Interfaces:**
- Consumes: the `job-runner` app and `POST /jobs/{name}` from Task 3.
- Produces: `POST /jobs/{name}` additionally accepting `schedule`, `dueTime`, `repeats`, `ttl`, `data` and `overwrite`; the handler logs the job's `data` payload alongside the fired line.

- [ ] **Step 1: Write the failing suite**

Per language:
- `@every 2s` with `repeats: 3` fires exactly three times and no more within a bounded wait.
- `data` round-trips — what was scheduled is what the handler receives.
- `ttl` expires a job that has not fired, and it never arrives.
- `dueTime` in the future does not fire early. Assert "no trigger before due time", never "a trigger at exactly due time" (Review Focus 7).

- [ ] **Step 2: Run the suite to verify it fails**

Expected: FAIL — the parameters are not accepted.

- [ ] **Step 3: Add the parameters to the three demo apps**

- [ ] **Step 4: Run the suite to verify it passes**

- [ ] **Step 5: Write the assignment**

Each parameter with what changes if you change it. Two things stated plainly because they bite later: a job never fires *before* due time but may fire after, with no stated bound; and delivery is at-least-once, so handlers must be idempotent.

- [ ] **Step 6: Write `README.md`, `notes.md`, `tabs.md`, `scripts/setup.sh`**

`notes.md` uses the "sandbox is being prepared" opener. Challenge teardown deletes `ch2-report`.

- [ ] **Step 7: Verify doc-sync passes**

- [ ] **Step 8: Commit** *(ask first)*

---

## Task 5: Challenge 3 — Kill it and watch it survive

8 minutes. **The aha moment.** A repeating job and an in-process timer, side by side. Ctrl-C the app. Restart. The timer is gone; the job fires.

**Files:**
- Modify (demo repo): `jobs/<lang>/Demo1-Jobs/` — add the in-process timer
- Create (track repo): `dapr-jobs/3-kill-it-and-watch-it-survive/{README.md,notes.md,assignment.md,tabs.md,scripts/setup.sh,scripts/check.sh,scripts/solve.sh,tests/challenge.robot}`

**Interfaces:**
- Consumes: the demo app and `JOB_NAMES` from Tasks 3–4.
- Produces: `POST /timer` starting an in-process repeating timer logging `TIMER FIRED: <timestamp>`; `GET /fired` unchanged. The two log prefixes — `JOB FIRED:` and `TIMER FIRED:` — are what the learner compares, and what the suite asserts on.

- [ ] **Step 1: Write the failing suite**

Per language, the aha asserted end to end:
1. Start the app; schedule `ch3-heartbeat` with `@every 5s`; start the in-process timer.
2. Wait until both `JOB FIRED:` and `TIMER FIRED:` appear.
3. `Stop Process With SIGINT    app` — the real Ctrl-C, not a kill.
4. Restart the app into a **fresh log file**.
5. Assert `JOB FIRED: ch3-heartbeat` appears in the new log within a bounded wait.
6. Assert `TIMER FIRED:` **never** appears in the new log.

Step 6 is the half people forget. Without it the test passes on an app that restarted its own timer, and the comparison the challenge is built on silently stops being true.

- [ ] **Step 2: Run the suite to verify it fails**

Expected: FAIL — `/timer` returns 404.

- [ ] **Step 3: Add the in-process timer to the three demo apps**

Each language's idiomatic in-process scheduler — `PeriodicTimer` / `asyncio` task / `@Scheduled` — deliberately **not** restarted on boot, because its dying is the lesson.

- [ ] **Step 4: Run the suite to verify it passes**

- [ ] **Step 5: Write `check.sh` and `solve.sh`**

`check.sh` asserts the current app log contains `JOB FIRED: ch3-heartbeat` and no `TIMER FIRED:`, with `fail-message "The job hasn't fired since the restart yet — give it a few seconds, or check that you scheduled ch3-heartbeat before stopping the app."`

- [ ] **Step 6: Write the assignment**

Build the contrast deliberately: both running, both firing, then the kill. Tell the learner what to expect before the restart so the moment lands as confirmation rather than confusion. Explain where the job lived while the app was down — the Scheduler, the same control-plane service that holds actor reminders.

- [ ] **Step 7: Write `README.md`, `notes.md`, `tabs.md`, `scripts/setup.sh`**

- [ ] **Step 8: Verify doc-sync passes**

- [ ] **Step 9: Commit** *(ask first)*

---

## Task 6: Challenge 4 — Managing jobs, and when not to use them

7 minutes. Get, delete, overwrite, TTL cleanup — then the comparison people actually ask for.

**Files:**
- Modify (demo repo): `jobs/<lang>/Demo1-Jobs/` — add get and delete endpoints
- Create (track repo): `dapr-jobs/4-managing-jobs/{README.md,notes.md,assignment.md,tabs.md,scripts/setup.sh,scripts/check.sh,scripts/solve.sh,tests/challenge.robot}`

**Interfaces:**
- Consumes: the demo app and `JOB_NAMES` from Tasks 3–5.
- Produces: `GET /jobs/{name}` returning the job's schedule and remaining repeats; `DELETE /jobs/{name}`.

- [ ] **Step 1: Write the failing suite**

Per language:
- Schedule `ch4-cleanup`, `GET` it, and assert the returned schedule matches what was sent.
- `DELETE` it, then `GET` again and assert it is gone.
- Assert a deleted job does not fire afterwards within a bounded wait — the assertion that proves delete means stop, not just "removed from the listing".
- Overwrite an existing job with a new schedule and assert the `GET` reflects the new one.

- [ ] **Step 2: Run the suite to verify it fails**

Expected: FAIL — `GET /jobs/{name}` returns 404.

- [ ] **Step 3: Add get and delete to the three demo apps**

- [ ] **Step 4: Run the suite to verify it passes**

- [ ] **Step 5: Write `check.sh` and `solve.sh`**

- [ ] **Step 6: Write the assignment**

Management first, then the comparison table — Jobs versus Workflow versus actor reminders versus the cron binding — with one line each on when to reach for which. This is the question the track exists to answer for people who already know Dapr, so it earns real space rather than a closing aside.

Close the track: `---`, recap, Discord `#university` pointer.

- [ ] **Step 7: Write `README.md`, `notes.md`, `tabs.md`, `scripts/setup.sh`**

- [ ] **Step 8: Verify doc-sync passes**

- [ ] **Step 9: Commit** *(ask first)*

---

## Task 7: CI workflow and whole-track verification

**Files:**
- Create (track repo): `.github/workflows/test-dapr-jobs.yml`

**Interfaces:**
- Consumes: `ci/setup-dapr-jobs.sh`; all four suites.
- Produces: nothing downstream.

- [ ] **Step 1: Write the workflow**

Copy the shape from plan 1 Task 7. Schedule **07:30 UTC**; `pull_request` paths `dapr-jobs/**`, `tools/track-tester/**`, and the workflow file.

- [ ] **Step 2: Pre-warm Maven outside the timed run**

- [ ] **Step 3: Account for the waiting in the timeouts**

This is the slowest of the five tracks to test: every assertion waits for wall-clock time to pass. Set per-suite timeouts from the longest `@every` plus the restart in challenge 3, with headroom — a timeout tuned to a fast local run will flake on a loaded CI runner, and a flaky durability test teaches the maintainer to ignore it.

- [ ] **Step 4: Run the whole track locally**

Run: `(cd tools/track-tester && uv run robot --name "Dapr Jobs" ../../dapr-jobs/*/tests/challenge.robot)`
Expected: PASS, all languages, all four challenges.

- [ ] **Step 5: Verify the workflow on a branch, twice**

Two consecutive runs, for the same reason as the Conversation track: timing-dependent suites need more than one pass before they are trusted.

- [ ] **Step 6: Confirm the time budget**

Expected: 28 minutes across the four assignments. Check it against real waiting — challenges 2 and 3 spend learner time watching for triggers, and a `@every 5s` job with three repeats is fifteen seconds of someone sitting still.

- [ ] **Step 7: Confirm the aha moment lands**

On a real Instruqt sandbox, complete challenge 3 in all three languages. The job must fire after the restart within a few seconds, and the timer must stay dead. If the post-restart delay is long, state it in the assignment rather than letting the learner conclude it failed.

- [ ] **Step 8: Commit** *(ask first)*
