# Dapr Secrets Track Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the `dapr-secrets` Instruqt track — four challenges, three languages, drift-tested — whose aha moment is an application being refused a secret by scoping.

**Architecture:** Demo apps live in `ai-agent-tracks-instruqt/secrets/<language>/` and are cloned onto the sandbox at launch; learner-facing content lives in `dapr-university-instruqt/dapr-secrets/`. Two demos carry all four challenges: `Demo1-ReadSecret` (one app, used by challenges 1, 2 and 4 — challenge 4 swaps only its component YAML, which is the whole point) and `Demo2-Scoping` (two apps, used by challenge 3). Each challenge's Robot suite is written before its demo and assignment exist, and the suite failing for the right reason is the gate to writing them.

**Tech Stack:** Dapr 1.18.x self-hosted; ASP.NET Core minimal API (.NET 10), FastAPI (Python 3.12), Spring Boot (Java 17); Robot Framework 7.x via `uv`; HashiCorp Vault in Docker; GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-20-dapr-building-block-tracks-design.md`

This is plan 1 of 5. It carries the **shared contract artifacts** (§5 of the spec) that plans 2–5 reuse: the `variables/` pattern, the `ci/setup-*.sh` pattern, the CI workflow shape, and the `<details>` language convention. Plans 2–5 reference Task 2 of this plan rather than restating it.

## Global Constraints

- **Two repos.** Demo code: `C:\dev\diagrid-labs\ai-agent-tracks-instruqt`, under `secrets/<language>/`. Track content: `C:\dev\diagrid-labs\dapr-university-instruqt`, under `dapr-secrets/`. Never mix them.
- **Three languages in every runnable challenge**: .NET, Python, Java (Spring Boot). No challenge ships with fewer.
- **`<summary>` text must be exactly `.NET`, `Python`, `Java`** — the doc-sync checker maps those strings to the `dotnet`/`python`/`java` tags.
- **Every runnable command is ` ```bash,run `; every expected-output block is ` ```text,nocopy `.** Every `bash,run` command must appear in the neighbouring Robot suite or in its `# doc-sync coverage` comment block.
- **Config lives in `README.md` files.** Never create `track.yml`, `config.yml`, or extensionless `setup`/`check`/`solve` files.
- **Track README requires all of:** `# Name`, `## Url`, `## Teaser` (with the `Languages: … Duration: …` line), `## Time limit (minutes)`, `## Description`, `### Time out idle users (minutes)`, `### Extra time (minutes)`.
- **Time budget:** 4 challenges summing to 28 minutes; `## Time limit (minutes)` is `30`, `### Extra time` is `10`, `### Time out idle users` is `10`.
- **Versions, pinned:** Dapr runtime `1.18.7`, Dapr CLI `1.18.2`, `Dapr.Client` `1.18.10`, Python `dapr` `1.18.3`, Java `io.dapr:dapr-sdk` `1.18.1`. Re-verify before Task 2 and update this list if they have moved.
- **VM image:** the shared "AI Agents Workflow" Instruqt sandbox. No `image-*.sh` in `_setup/` — only `sandbox-setup.sh`.
- **Run `robot`, `rebot` and `pytest` from inside `tools/track-tester/`** via `uv run`; suite paths are relative to that directory.
- **Never simplify `Stop Process With SIGINT`** to a single-PID kill.
- **Git:** the user's standing instruction is that no `git add` / `git commit` / `git push` runs unless they explicitly ask for it in the current conversation. The commit steps below are written as the plan's natural boundaries; **ask before running any of them**.

## Review Focus

Five things the spec implies, that a learner will hit, and that no task's happy-path suite would catch:

1. **A learner jumps straight to challenge 3** (Instruqt's Progress button allows it, and the track README advertises it). Each challenge's `scripts/setup.sh` must provision everything that challenge needs without assuming an earlier one ran. → pinned in Tasks 3–6, step "setup.sh is self-sufficient".
2. **The sandbox is relaunched mid-track** (up to 5 starts per track). `sandbox-setup.sh` must be idempotent: re-running it must not duplicate the Vault seed or corrupt `secrets.json`. → pinned in Task 2.
3. **Vault is not ready when the sidecar starts.** The component fails at init and the learner sees a sidecar error, not a secret. The setup must wait for Vault's readiness, not just start the container. → pinned in Task 6.
4. **A previous challenge's app is still running** because the learner never pressed Ctrl-C, squatting port 5001. The next `dapr run` fails with a bind error the assignment never mentions. → pinned in Task 3.
5. **A learner switches language between challenges** (challenge 1 in Python, challenge 2 in .NET). Each `setup.sh` must build all three languages, not only the one the previous challenge used. → pinned in Tasks 4–6.

---

## Task 1: Verify the scope-denial behaviour (blocking spike)

Spec §3.1 and §7.3: what an app receives when scoping denies it a secret is undocumented, and it is this track's entire aha moment. Nothing else in this plan may start until this is known, because challenge 3's assignment, its expected-output block and its Robot assertion all quote it.

Throwaway work. No demo apps, no assignment — the deliverable is a findings file.

**Files:**
- Create: `docs/superpowers/notes/2026-10-20-secret-scope-denial-findings.md` (in `ai-agent-tracks-instruqt`)

**Interfaces:**
- Consumes: nothing.
- Produces: the exact denial response (HTTP status, response body, and the SDK exception type and message per language) that Tasks 5's assignment and suite assert on.

- [ ] **Step 1: Stand up the environment**

On WSL2 with Docker (spec §7a). Install the Dapr CLI and run `dapr init`. Confirm with `dapr --version` that the runtime is `1.18.x`.

- [ ] **Step 2: Create the minimal scoping setup**

A `secrets.json` with two secrets, a `secretstore` component of type `secretstores.local.file`, and a Dapr `Configuration` resource scoping `app-b` with `defaultAccess: deny` and `allowedSecrets: ["payments-api-key"]`.

- [ ] **Step 3: Record the raw HTTP response**

Run the sidecar as `app-b` with that configuration, then:

```bash
curl -i http://localhost:3500/v1.0/secrets/secretstore/orderdb-password
```

Record the **exact** status code and response body.

- [ ] **Step 4: Record the SDK-level behaviour in all three languages**

For each of .NET (`DaprClient.GetSecretAsync`), Python (`DaprClient.get_secret`) and Java (`DaprClient.getSecret`), call for the denied secret and record the exception type and message, or the returned value if no exception is raised.

- [ ] **Step 5: Compare against a genuinely missing secret**

Repeat step 3 for a secret name that does not exist in `secrets.json` at all. Record whether the two are distinguishable. **This is the finding that decides the challenge:** if a denied secret is indistinguishable from a missing one, the aha moment does not land.

- [ ] **Step 6: Write the findings file and stop**

Record the status code, body, and the three SDK behaviours, plus the step-5 comparison. Then:

- If denial is **visibly distinct** → proceed to Task 2.
- If denial is **indistinguishable from not-found** → stop and raise it with the track owner before any further work. Do not design around it; spec §3.1 is explicit that this is the track's reason to exist.

- [ ] **Step 7: Commit the findings file** *(ask first — see Global Constraints)*

```bash
git add docs/superpowers/notes/2026-10-20-secret-scope-denial-findings.md
git commit -m "docs: record secret scope-denial behaviour findings"
```

---

## Task 2: Shared contract artifacts and track scaffold

Everything plans 2–5 copy. Deliberately one task: the scaffold is not independently reviewable in pieces, and a reviewer either accepts the contract or rejects it.

**Files:**
- Create (`ai-agent-tracks-instruqt`): `secrets/README.md`
- Create (`dapr-university-instruqt`): `dapr-secrets/README.md`, `dapr-secrets/website-description.md`, `dapr-secrets/_setup/sandbox-setup.sh`
- Create (`dapr-university-instruqt`): `tools/track-tester/variables/dapr_secrets.py`, `tools/track-tester/ci/setup-dapr-secrets.sh`

**Interfaces:**
- Consumes: Task 1's findings file (for the teaser's honesty about what the track shows).
- Produces:
  - `TRACKS_SRC_DIR` — the cloned demo repo root, resolving to `$TRACKS_SRC_DIR` or `~/ai-agent-tracks-instruqt`.
  - `SECRETS_BASE` — `os.path.join(TRACKS_SRC_DIR, "secrets")`.
  - `DEMO1`, `DEMO2` — `Demo1-ReadSecret`, `Demo2-Scoping`.
  - The sandbox contract every later task relies on: the repo cloned to `~/ai-agent-tracks-instruqt`, `secrets.json` written, Vault running and seeded, `dapr init` complete.

- [ ] **Step 1: Write the variables file**

Create `tools/track-tester/variables/dapr_secrets.py` following `variables/dapr_101.py`:

```python
TRACKS_SRC_DIR = os.environ.get("TRACKS_SRC_DIR") or os.path.expanduser("~/ai-agent-tracks-instruqt")
SECRETS_BASE = os.path.join(TRACKS_SRC_DIR, "secrets")
DEMO1 = "Demo1-ReadSecret"
DEMO2 = "Demo2-Scoping"
DENIED_STATUS = "<from Task 1>"
DENIED_BODY = "<from Task 1>"
```

`DENIED_STATUS` and `DENIED_BODY` carry Task 1's findings so challenge 3's suite and every later reference use one source of truth.

- [ ] **Step 2: Write the track README**

`dapr-secrets/README.md` with every required section (Global Constraints). Teaser names the three languages and 30 minutes. Description lists the four learning outcomes, matching spec §3.1's challenge table.

- [ ] **Step 3: Write `_setup/sandbox-setup.sh`**

Clone `https://github.com/diagrid-labs/ai-agent-tracks-instruqt.git`; `docker login -u ${DockerUSER} -p ${DockerPAT}`; `dapr init` with the running-containers check the other tracks use; `agent variable set DAPR_CLI_VERSION 1.18.2` and `DAPR_RUNTIME_VERSION 1.18.7`; write `secrets.json`; start Vault in dev mode and seed it; pre-build `Demo1-ReadSecret` for all three languages.

**Idempotency (Review Focus 2):** writing `secrets.json` must truncate rather than append, and the Vault container start must tolerate one already running (`docker rm -f` first, or `--restart` guard). Re-running the whole script must leave the same state.

- [ ] **Step 4: Write `ci/setup-dapr-secrets.sh`**

Follow `ci/setup-dapr-101.sh`: `set -euo pipefail`, parse the pinned versions out of `sandbox-setup.sh` with `awk '/DAPR_CLI_VERSION/ {print $NF}'` so the version lives in one place, clone the demo repo to `$TRACKS_SRC_DIR`, install `uv`, install the Dapr CLI unpinned and `dapr init`, start and seed Vault. Export `TRACKS_SRC_DIR` to `$GITHUB_ENV`.

- [ ] **Step 5: Verify the script provisions a working sandbox**

Run: `bash tools/track-tester/ci/setup-dapr-secrets.sh`
Expected: exits 0; `docker ps` shows `dapr_redis`, `dapr_placement`, `dapr_scheduler` and the Vault container; `~/ai-agent-tracks-instruqt/secrets` exists.

- [ ] **Step 6: Verify it is idempotent**

Run it a second time.
Expected: exits 0, same `docker ps` set, `secrets.json` byte-identical to the first run.

- [ ] **Step 7: Write `secrets/README.md` in the demo repo**

How to run the demos locally outside Instruqt: prerequisites, `dapr run` command per language, the two demo folders and which challenges use them.

- [ ] **Step 8: Commit** *(ask first)*

```bash
git commit -m "feat: scaffold dapr-secrets track and shared contract artifacts"
```

---

## Task 3: Challenge 1 — What the Secrets API is for

5 minutes. One app reads one secret from the local file store. Plants the hook spec §3.1 requires: both apps succeed today, and by the end the learner makes the second one fail on purpose.

**Files:**
- Create (demo repo): `secrets/dotnet/Demo1-ReadSecret/`, `secrets/python/Demo1-ReadSecret/`, `secrets/java/Demo1-ReadSecret/`, and `secrets/<lang>/resources/secretstore-local.yaml` for each language
- Create (track repo): `dapr-secrets/1-what-is-the-secrets-api/{README.md,notes.md,assignment.md,tabs.md,scripts/setup.sh,tests/challenge.robot}`

**Interfaces:**
- Consumes: `SECRETS_BASE`, `DEMO1` from Task 2.
- Produces:
  - Component name **`secretstore`**, type `secretstores.local.file`, `secretsFile: secrets.json`. The name is fixed for the whole track — challenge 4 swaps the file behind this same name, which is what makes "application code doesn't change" true.
  - Secrets: `orderdb-password` = `s3cr3t-pa55w0rd`, `payments-api-key` = `pk-test-7f3a9`.
  - App: id `order-api`, app port **5001**, Dapr HTTP port **3500**, endpoint `GET /secret/{name}` returning `{"name": "<name>", "value": "<value>"}`.

- [ ] **Step 1: Write the failing Robot suite**

`dapr-secrets/1-what-is-the-secrets-api/tests/challenge.robot`, one test case per language tagged `dotnet` / `python` / `java`, importing `../../../tools/track-tester/resources/dapr.resource` and `../../../tools/track-tester/variables/dapr_secrets.py`, with `Suite Teardown    Terminate All Processes    kill=True`.

Each case: start the app with `dapr run`, wait until it responds on port 5001, then

```robot
Assert Command Output Contains
...    curl -s http://localhost:5001/secret/orderdb-password    s3cr3t-pa55w0rd
```

and a case-level `[Teardown]    Stop Process With SIGINT    app`.

- [ ] **Step 2: Add the port-collision test (Review Focus 4)**

A test case `Port 5001 Is Free Before The App Starts` asserting nothing is listening on 5001 before launch, so a leaked process from a previous run fails loudly here rather than confusingly inside the next challenge.

- [ ] **Step 3: Run the suite to verify it fails**

Run: `(cd tools/track-tester && uv run robot ../../dapr-secrets/1-what-is-the-secrets-api/tests/challenge.robot)`
Expected: FAIL — the demo directories do not exist.

- [ ] **Step 4: Write the three demo apps**

`GET /secret/{name}` in each language, reading via the SDK (`DaprClient.GetSecretAsync` / `get_secret` / `getSecret`) against store `secretstore`. Minimal: one endpoint, no persistence, no extra dependencies. Each app folder also gets the `dapr.yaml` multi-app file its `dapr run -f .` uses.

- [ ] **Step 5: Write the component and secrets files**

`secretstore-local.yaml` per language as specified in Interfaces, plus the `secrets.json` shape Task 2's `sandbox-setup.sh` writes.

- [ ] **Step 6: Run the suite to verify it passes**

Run: as step 3.
Expected: PASS, 4 tests (3 languages + the port check).

- [ ] **Step 7: Write the assignment**

`assignment.md`: intro naming the 5-minute length; numbered `## 1.` … steps; per-language steps in `<details>` blocks with `<summary><b>.NET</b></summary>` etc.; every command ` ```bash,run `; expected output ` ```text,nocopy `. Close with the hook — two apps, both read the secret today — then `---` and a one-line lead-in to challenge 2.

- [ ] **Step 8: Write `README.md`, `notes.md`, `tabs.md`, `scripts/setup.sh`**

`README.md` with `# Name` / `## Url` (`dapr-secrets-what-is-the-secrets-api`) / `### Description`. `notes.md` uses the **full intro** opener (challenge 1 convention; see `dapr-101/1-what-is-dapr/notes.md`). `tabs.md` with a code editor and two terminals rooted at `ai-agent-tracks-instruqt/secrets`. `setup.sh` builds `Demo1-ReadSecret` for **all three languages** — self-sufficient, per Review Focus 1 and 5.

- [ ] **Step 9: Verify doc-sync passes**

Run:
```bash
(cd tools/track-tester && uv run python docsync/check_doc_sync.py \
  ../../dapr-secrets/1-what-is-the-secrets-api/assignment.md \
  ../../dapr-secrets/1-what-is-the-secrets-api/tests/challenge.robot)
```
Expected: exits 0.

- [ ] **Step 10: Commit** *(ask first)*

---

## Task 4: Challenge 2 — The component and its parameters

8 minutes. The act-2 challenge the spec says existing tracks skip: the component YAML line by line, then the API's own shape.

**Files:**
- Modify (demo repo): `secrets/<lang>/Demo1-ReadSecret/` — add the bulk endpoint; add `secrets/<lang>/resources/statestore-with-secretref.yaml`
- Create (track repo): `dapr-secrets/2-component-and-parameters/{README.md,notes.md,assignment.md,tabs.md,scripts/setup.sh,tests/challenge.robot}`

**Interfaces:**
- Consumes: `secretstore` component, `order-api` app, ports 5001/3500 from Task 3.
- Produces: `GET /secrets` (bulk, returning all accessible secrets); a `statestore` component whose `redisPassword` uses `secretKeyRef` against `secretstore` with `auth.secretStore: secretstore`.

- [ ] **Step 1: Write the failing suite**

Per language, assert:
- `GET /secrets` returns both `orderdb-password` and `payments-api-key`.
- The raw bulk HTTP API returns both: `curl -s http://localhost:3500/v1.0/secrets/secretstore/bulk`.
- `multiValued` behaviour: with a nested secret in `secrets.json`, the flattened key uses the configured `nestedSeparator`.
- The sidecar starts cleanly with the `secretKeyRef` state store component present — proving the indirection resolves rather than just parsing.

- [ ] **Step 2: Run the suite to verify it fails**

Expected: FAIL — `/secrets` returns 404.

- [ ] **Step 3: Add the bulk endpoint to the three demo apps**

`GET /secrets` → `GetBulkSecretAsync` / `get_bulk_secret` / `getBulkSecret`.

- [ ] **Step 4: Add the `secretKeyRef` state store component**

`statestore-with-secretref.yaml` per Interfaces. This is the challenge's teaching artifact: a component getting its password from the secret store instead of having it inline.

- [ ] **Step 5: Run the suite to verify it passes**

- [ ] **Step 6: Write the assignment**

Walk `secretstore-local.yaml` field by field — `secretsFile`, `nestedSeparator`, `multiValued` — each with what changes if you change it. Then the API: single, bulk, and `secretKeyRef`. Per-language `<details>` throughout.

- [ ] **Step 7: Write `README.md`, `notes.md`, `tabs.md`, `scripts/setup.sh`**

`notes.md` uses the **"sandbox for this challenge is being prepared"** opener (challenges 2+ convention). `setup.sh` builds all three languages (Review Focus 5).

- [ ] **Step 8: Verify doc-sync passes**

- [ ] **Step 9: Commit** *(ask first)*

---

## Task 5: Challenge 3 — Scoping, the app gets told no

8 minutes. **The aha moment.** App A reads the secret; App B asks for the same secret and is refused. Everything asserted here comes from Task 1's findings.

**Files:**
- Create (demo repo): `secrets/<lang>/Demo2-Scoping/AppA/`, `secrets/<lang>/Demo2-Scoping/AppB/`, `secrets/<lang>/resources/config-app-b.yaml`
- Create (track repo): `dapr-secrets/3-secret-scoping/{README.md,notes.md,assignment.md,tabs.md,scripts/setup.sh,scripts/check.sh,scripts/solve.sh,tests/challenge.robot}`

**Interfaces:**
- Consumes: `DENIED_STATUS`, `DENIED_BODY` from Task 2's variables file; the `secretstore` component.
- Produces: apps `app-a` (port 5002, Dapr HTTP 3501) and `app-b` (port 5003, Dapr HTTP 3502), both exposing `GET /secret/{name}`; `config-app-b.yaml`, a `Configuration` resource with `defaultAccess: deny` and `allowedSecrets: ["payments-api-key"]` for store `secretstore`.

- [ ] **Step 1: Write the failing suite**

Per language, four assertions:
- `app-a` reads `orderdb-password` and gets `s3cr3t-pa55w0rd`.
- `app-b` reads `payments-api-key` (its one allowed secret) and succeeds.
- `app-b` reads `orderdb-password` and is **refused**, asserting `${DENIED_STATUS}` and `${DENIED_BODY}`.
- `app-b` reads a secret that does not exist at all, asserting the response **differs** from the denial. This is Task 1 step 5 turned into a permanent regression test: if a future Dapr release collapses the two, this fails and the aha moment's loss is caught, not shipped.

- [ ] **Step 2: Run the suite to verify it fails**

Expected: FAIL — `Demo2-Scoping` does not exist.

- [ ] **Step 3: Write App A and App B in three languages**

Same single endpoint as Demo1. The two apps are deliberately identical in code — only the sidecar configuration differs, which is the point.

- [ ] **Step 4: Write `config-app-b.yaml`**

Per Interfaces. Apply to `app-b` only, via `--config` on its `dapr run`.

- [ ] **Step 5: Run the suite to verify it passes**

- [ ] **Step 6: Write `check.sh` and `solve.sh`**

`check.sh` confirms `config-app-b.yaml` is in place and that `app-b` is refused, with `fail-message "App B can still read orderdb-password — is the Configuration resource applied with --config?"`. `solve.sh` runs the exact commands that complete the challenge.

- [ ] **Step 7: Write the assignment**

Build to the refusal: run App A, succeed; run App B without scoping, succeed; apply the Configuration resource; run App B again, refused. The expected-output block quotes Task 1's exact response. Then the inverse — `defaultAccess: allow` with `deniedSecrets` — so both directions are seen.

- [ ] **Step 8: Write `README.md`, `notes.md`, `tabs.md`, `scripts/setup.sh`**

`setup.sh` builds `Demo2-Scoping` in all three languages and does not assume challenges 1–2 ran (Review Focus 1).

- [ ] **Step 9: Verify doc-sync passes**

- [ ] **Step 10: Commit** *(ask first)*

---

## Task 6: Challenge 4 — Swap the provider

7 minutes. Same application code, local file → HashiCorp Vault, different YAML behind the same component name.

**Files:**
- Create (demo repo): `secrets/<lang>/resources/secretstore-vault.yaml`
- Create (track repo): `dapr-secrets/4-swap-the-provider/{README.md,notes.md,assignment.md,tabs.md,scripts/setup.sh,scripts/check.sh,scripts/solve.sh,tests/challenge.robot}`
- Modify (track repo): `dapr-secrets/_setup/sandbox-setup.sh` — Vault readiness wait

**Interfaces:**
- Consumes: `Demo1-ReadSecret` and the `secretstore` component name from Task 3.
- Produces: `secretstore-vault.yaml` — type `secretstores.hashicorp.vault`, **component name `secretstore`**, pointing at the dev-mode Vault from Task 2.

- [ ] **Step 1: Write the failing suite**

Per language, assert that the **unmodified** `Demo1-ReadSecret` app returns `s3cr3t-pa55w0rd` from `GET /secret/orderdb-password` while running against the Vault component — no application rebuild, no code change. Add an assertion that the app binary or source is byte-identical to what challenge 1 used, so "the code didn't change" is proved rather than asserted in prose.

- [ ] **Step 2: Add the Vault readiness test (Review Focus 3)**

A test case asserting Vault answers its health endpoint before any app starts, and that `sandbox-setup.sh`'s wait loop (step 4) returns non-zero if Vault never becomes ready — so the learner gets a clear failure instead of an opaque sidecar error.

- [ ] **Step 3: Run the suite to verify it fails**

Expected: FAIL — `secretstore-vault.yaml` does not exist.

- [ ] **Step 4: Add the Vault readiness wait to `sandbox-setup.sh`**

Poll Vault's health endpoint with a bounded retry after starting the container; exit non-zero with a clear message on timeout.

- [ ] **Step 5: Write `secretstore-vault.yaml`**

Per Interfaces, for all three languages' `resources/` directories.

- [ ] **Step 6: Measure the Vault container's cost on the sandbox**

Time the sandbox launch with Vault included, and check memory against what the shared image has to spare alongside the Dapr containers and three language runtimes.

Spec §3.1 permits a fallback: if Vault is too expensive, swap to the **local environment variables** store (`secretstores.local.env`) instead — also Stable, no container, and application code still does not change. Prefer Vault; take the fallback only on a measurement, and if taken, rewrite step 1's suite and the assignment for the env-var store rather than leaving Vault half-described.

- [ ] **Step 7: Run the suite to verify it passes**

- [ ] **Step 8: Write `check.sh` and `solve.sh`**

`check.sh` asserts the active `secretstore` component is of type `secretstores.hashicorp.vault` and the app still answers, with `fail-message "The app isn't reading from Vault yet — is secretstore-vault.yaml the component Dapr loaded?"`.

- [ ] **Step 9: Write the assignment**

The swap, then the point: the app was never rebuilt. Close the track — `---`, a recap of the four challenges, and a pointer to the Dapr Discord `#university` channel as the other tracks do.

- [ ] **Step 10: Write `README.md`, `notes.md`, `tabs.md`, `scripts/setup.sh`**

- [ ] **Step 11: Verify doc-sync passes**

- [ ] **Step 12: Commit** *(ask first)*

---

## Task 7: CI workflow and whole-track verification

The spec's definition of done: a track without a green CI workflow is not done.

**Files:**
- Create (track repo): `.github/workflows/test-dapr-secrets.yml`

**Interfaces:**
- Consumes: `ci/setup-dapr-secrets.sh` from Task 2; all four suites.
- Produces: nothing downstream. Plans 2–5 copy this file's shape.

- [ ] **Step 1: Write the workflow**

Follow `.github/workflows/test-dapr-workflow.yml`. Daily `schedule` at **06:45 UTC** (staggered after the existing three at 06:00/06:15/06:30), `workflow_dispatch`, and `pull_request` on `dapr-secrets/**`, `tools/track-tester/**`, and the workflow file itself. Two jobs:

- `docsync` — loops all four challenges, collecting failures rather than stopping at the first (the `if !` guard pattern), writes `results/failed-docsync.txt`, uploads it.
- `languages` — `fail-fast: false`, matrix `[dotnet, java, python]`, with `setup-dotnet` (10.0.x), `setup-java` (temurin 17) and `setup-uv`; caches `~/.m2` explicitly keyed on the demo repo's poms, since the clone lands outside the workspace; runs `ci/setup-dapr-secrets.sh`, then every challenge suite filtered by `--include ${{ matrix.lang }}`, continuing past failures and merging results with `rebot`.

- [ ] **Step 2: Pre-warm Maven outside the timed run**

The Java leg resolves dependencies before the first suite starts, as the `dapr-workflow` Java leg does, so a cold `~/.m2` does not eat the readiness timeout.

- [ ] **Step 3: Run the whole track locally**

Run: `(cd tools/track-tester && uv run robot --name "Dapr Secrets" ../../dapr-secrets/*/tests/challenge.robot)`
Expected: PASS, all languages, all four challenges.

- [ ] **Step 4: Verify the workflow on a branch**

Trigger via `workflow_dispatch` and confirm the `docsync` job and all three language legs pass.

- [ ] **Step 5: Confirm the time budget**

Walk the four assignments and total the stated durations.
Expected: 28 minutes, matching the track README's `## Time limit (minutes)` of 30.

- [ ] **Step 6: Confirm the aha moment lands**

Launch the track on a real Instruqt sandbox and complete challenge 3 in all three languages. The refusal must be visible and unambiguous to a reader who has not seen Task 1's findings. WSL2 proved the mechanism; this proves it survives the environment. If they disagree, the sandbox wins.

- [ ] **Step 7: Commit** *(ask first)*

---

## Notes for plans 2–5

Reusable from this plan without change: the `variables/dapr_<block>.py` shape, `ci/setup-<track>.sh`, the workflow's two-job structure, the `<details>` convention, the challenge-file set, and the Review Focus items — all five recur in every track, because they are properties of Instruqt and the harness, not of secrets.

Track-specific per plan: the demo apps, the component types, the provider swap target, and the schedule offset (Configuration 07:00, Conversation 07:15, Jobs 07:30, Actors 07:45 UTC).
