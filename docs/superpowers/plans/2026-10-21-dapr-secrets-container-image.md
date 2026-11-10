# Dapr Secrets Container Image Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and publish `diagrid/university-base` and `diagrid/university-secrets` — a CI-built container image that the Instruqt v2 `dapr-secrets` lab can run on — and prove it carries the four toolchains, the pinned Dapr CLI and runtime, and warm package caches.

**Architecture:** A two-layer Dockerfile set under `images/` in `ai-agent-tracks-instruqt`. `images/base/Dockerfile` installs the four toolchains, the pinned Dapr CLI, and `dapr init --slim` (subject to Task 1), with package caches in `/opt/caches`. `images/secrets/Dockerfile` takes `ARG BASE_TAG` and warms those caches by building the secrets demos once. The demo code is **not** baked in — it is cloned at lab start — so the layer clones, builds, and throws the checkout away, keeping only the caches. Tests are shell scripts under `tests/images/` that run assertions *inside* a container, because the thing under test is an image, not a library.

**Tech Stack:** Ubuntu 24.04; .NET SDK 10 (Ubuntu noble feed), OpenJDK 17 + Maven, Python 3.12 + `uv`, Node 24 (NodeSource); Dapr CLI 1.18.2 / runtime 1.18.7; Docker Buildx `linux/amd64`; GitHub Actions; Docker Hub.

**Spec:** `docs/superpowers/specs/2026-10-21-dapr-tracks-container-image-design.md`

**Scope:** This plan is the **image half** of the spec (§7.0's first repo). It stops at a published, verified image plus the one content change the image's own smoke test needs. The lab definition in `dapr-university-instruqt` — `sandbox.hcl`, pages, tasks, tabs, the §7.6 v1→v2 rewrite — is a separate plan. See **Deferred** at the end for what is knowingly left out and what must be verified before that plan can be estimated.

## Global Constraints

- **Repo:** everything in this plan lives in `C:\dev\diagrid-labs\ai-agent-tracks-instruqt`, except Task 7's single line in `C:\dev\diagrid-labs\dapr-university-instruqt`. Never mix the two repos' responsibilities (spec §7.0).
- **Platform `linux/amd64` only.** Every `docker build` in this plan passes `--platform=linux/amd64` (spec §5).
- **Image names:** `diagrid/university-base` and `diagrid/university-secrets`. Spec §7.5.2 says "`track-base`/`track-<name>`"; decision 12 in §6 says `university-*`, and decisions win. Use `university-*`.
- **Push credentials:** `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` (spec §7.5.1 step 4). Spec §7.5.2's "use the existing `DockerUSER`/`DockerPAT`" is superseded: those are the sandbox's pull-only credentials, and reusing them in CI reproduces the "only the author can rebuild" anti-goal (§4).
- **Versions, pinned, in exactly one file:** `images/versions.env` owns `DAPR_CLI_VERSION=1.18.2` and `DAPR_RUNTIME_VERSION=1.18.7`. Until the lab migrates, `dapr-university-instruqt/dapr-secrets/_setup/sandbox-setup.sh` still carries the same two numbers for its own CI's `awk` parse — a temporary twin, guarded by Task 2's version check and flagged in Deferred.
- **No Docker Engine in the image, no `privileged`, no DinD** (spec §4, §7.1). Nothing in the image or its tests assumes a Docker daemon is reachable from the workstation container.
- **The workstation runs as root** (spec §9.5, decided here): it matches what today's scripts assume, and the editor tab needs write access to the clone directory. Caches are still made world-readable so a later `run_as` switch does not silently break them.
- **Caches live at** `/opt/caches/{nuget,uv,m2,npm}`, never in `$HOME` (spec §7.4, and the source checklist's comment: the build user and the lab user are not guaranteed to be the same).
- **Demo code is cloned at lab start, never baked in** (spec decision 5). The per-track layer may clone to warm caches, but must delete the checkout.
- **Git:** the user's standing instruction is that no `git add` / `git commit` / `git push` runs unless they explicitly ask for it in the current conversation. The commit steps below mark the plan's natural boundaries; **ask before running any of them.**

## Review Focus

Failure modes the spec implies that a task's happy path would not catch. Each is pinned to a task below.

1. **A non-login, non-interactive shell.** Instruqt check scripts run as `sh -c '…'`, which sources neither `/etc/profile.d` nor a user rc file. If the cache variables only live there, every check runs against a cold cache while the image reports success. → pinned in Task 2, which asserts both `sh -lc` and `sh -c`.
2. **A cache that silently misses.** The spec's named anti-goal. A warm cache is only proven by a build that *cannot* reach the network. → pinned in Task 3, which builds each demo with `--network none`.
3. **A dependency the cache does not have.** Once a demo gains a package after the image was built, the cache must degrade to slow, not broken. An offline-only test would call that a failure. → pinned in Task 3, which also runs one networked build of a demo with an added package.
4. **Vault or Redis not ready when the sidecar starts.** The lab starts the containers in parallel with the workstation, so a component can load before the service answers and the learner sees a sidecar error rather than a secret. → pinned in Task 5's readiness wait, and in Task 4's smoke harness.
5. **The seed re-run.** A relaunched lab, or a learner re-running a setup step, must leave Vault with the same contents — not doubled, not half-written. → pinned in Task 5.
6. **`versions.env` drifting from the installed CLI.** A Dockerfile that installs unpinned while `versions.env` claims a pin is worse than no pin, because CI would assert against a number nothing enforces. → pinned in Task 2's version check.
7. **A sidecar that says `Running` but is not `ready`.** With no scheduler listening, `daprd` 1.18.7 prints `dapr initialized. Status: Running` while `/v1.0/healthz` returns 500 — so any test that greps the CLI's output, rather than asking the sidecar, passes on a broken lab. → pinned in Task 2's port check and Task 4's `healthz` assertion, both of which ask the sidecar.

---

## Prerequisites (human, blocking Task 6 only)

Tasks 1–5 and 7 need none of this; do it in parallel with them so it is not the critical path.

- [ ] **Claim the Docker Hub namespace.** Spec §7.5.1 step 1. `diagrid` is a short, common word — check availability **first**, and if it is taken, agree the fallback name with Marc before it is baked into Task 6's workflow.
- [ ] **Create `university-base` and `university-secrets`, both Public.** Public is load-bearing: Instruqt's image streaming — the fast path this whole design exists for — covers only public Docker Hub and Artifact Registry (spec §5).
- [ ] **Create an organization access token with Read & Write**, and add it to `ai-agent-tracks-instruqt` → Settings → Secrets and variables → Actions as `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`.
- [ ] **Invite at least one other person who can rebuild.** A one-person org is the "only the author can rebuild" anti-goal by another route (spec §7.5.1 step 5).
- [ ] **Confirm the Instruqt organization has v2 labs-beta access** (spec §11). Everything downstream of this plan depends on it.

---

## Task 1: Spike — the Dapr control plane in a Docker-less workstation (blocking)

Spec §9.1, the design's main open question. The answer changes Task 2's Dockerfile and the lab plan's `sandbox.hcl`, and every later track inherits it. Nothing else starts until it is settled.

**The spec's framing is out of date, and the research is already done.** Spec §9.1 asks whether `daprd` *fails* or merely *warns* with no placement or scheduler. At the version this track pins, it does neither — it sits in a third state the spec did not consider:

- `dapr init --slim` installs **three binaries** — `daprd`, `placement` and `scheduler` — into `$HOME/.dapr/bin`. It **starts none of them**.
- `dapr run` nonetheless passes `--scheduler-host-address localhost:50006`. With nothing listening there, `daprd` logs connection-refused about once a second, prints `dapr initialized. Status: Running`, and then `GET /v1.0/healthz` returns **HTTP 500** with `dapr is not ready: [scheduler-watch-hosts internal-placement-service]`.
- Reported on **daprd 1.18.7** — exactly this track's pin — and it affects apps that use no workflows, jobs or actor reminders. "The secrets demos need neither service" therefore does **not** make the problem go away. ([dapr/dapr#10821](https://github.com/dapr/dapr/issues/10821), open; its proposed fix improves the error message, not the behavior.)

So spec §9.1's option 1 ("slim mode, and `dapr run -f .` works unchanged") is **false as written**, and this task's job is to confirm that locally and then implement the option the spec did not list:

| | Approach | Cost |
| --- | --- | --- |
| **A (preferred)** | `dapr init --slim` in the image, and the workstation's entrypoint **starts the `placement` and `scheduler` binaries locally** | No Docker, no extra containers. They land on the default `localhost:50005` / `:50006` that `dapr run` already expects, so **every demo's `dapr.yaml` stays exactly as it is** |
| **B (fallback)** | Spec §9.1 option 2: declared `placement` and `scheduler` containers in `sandbox.hcl` | Forces `--placement-host-address` / `--scheduler-host-address` into learner-visible `dapr.yaml` files in every track, and reintroduces two image pulls at lab start |

Take A unless step 2 shows it does not work. Throwaway work: a scratch Dockerfile, deleted at the end. The deliverable is the findings note.

**Files:**
- Create: `docs/superpowers/notes/2026-10-21-dapr-control-plane-spike.md`
- Scratch (not committed): a Dockerfile under the session scratchpad directory

**Interfaces:**
- Consumes: nothing.
- Produces: the decision `SLIM+LOCAL` (A) or `CONTAINERS` (B), which Task 2 step 3 reads, plus the confirmed listen addresses. If `CONTAINERS`, the note records the exact `dapr.yaml` fields the lab plan must add to every demo.

- [ ] **Step 1: Build a scratch image with the Dapr runtime installed in slim mode**

In the scratchpad directory, a Dockerfile `FROM ubuntu:24.04` that installs `ca-certificates curl wget git dotnet-sdk-10.0`, installs the Dapr CLI pinned to 1.18.2, then runs slim init:

```dockerfile
RUN wget -q https://raw.githubusercontent.com/dapr/cli/master/install/install.sh -O - | /bin/bash -s 1.18.2
RUN dapr init --slim --runtime-version 1.18.7
```

Build with `docker build --platform=linux/amd64`. Two things to confirm and write down while here: that `/root/.dapr/bin/` really contains `daprd`, `placement` **and** `scheduler` (the CLI README says three, some third-party write-ups claim only two), and that `dotnet-sdk-10.0` resolves from Ubuntu's noble feed — if it does not, stop, because that invalidates Task 2 (spec §7.1's .NET feed trap).

- [ ] **Step 2: Reproduce the not-ready state, then fix it with local binaries**

Start `redis:7` on a user-defined docker network as `redis`. Run the scratch image on the same network with the repo mounted, copy `secrets/secrets.example.json` to `secrets/secrets.json`, point `statestore-with-secretref.yaml` at `redis:6379` by hand (the committed file still says `localhost` until Task 4), and from `secrets/dotnet/Demo1-ReadSecret` run `dapr run -f .`.

First **without** the control plane, capturing `curl -s -o /dev/null -w '%{http_code}' http://localhost:3500/v1.0/healthz` and the body. Expected, per the issue: `500`, naming `scheduler-watch-hosts` and `internal-placement-service`.

Then kill it, start both binaries in the background —

```bash
/root/.dapr/bin/placement &
/root/.dapr/bin/scheduler &
```

— and run `dapr run -f .` again. Confirm `healthz` now returns **200**, and confirm the default ports the two actually bind (expected `50005` placement, `50006` scheduler; `ss -ltnp` to be sure, since the spike, not memory, is what Task 2 encodes).

- [ ] **Step 3: Record what the Secrets API does in both states**

Capture verbatim into the note, for each of the two states above: whether `curl http://localhost:5001/secret/orderdb-password` answers `{"name":"orderdb-password","value":"s3cr3t-pa55w0rd"}`, whether the state store component loads, and whether `dapr run -f .` itself blocks waiting for the sidecar to become healthy. That last one decides how bad the unfixed state is for a learner: a not-ready sidecar that still serves secrets is a slow lab, one that never starts the app is a broken one.

- [ ] **Step 4: Check the scheduler's data directory**

`dapr init` gives the scheduler a volume because, in its own words, "without this flag, scheduler data is not persisted and not resilient to restarts." A locally started `scheduler` binary writes somewhere by default — find out where, and note whether it needs an explicit `--etcd-data-dir` under `/var/lib` to avoid writing into a path the lab does not expect. The secrets track stores no jobs, so this is a note for the tracks that will.

- [ ] **Step 5: Write the decision**

The note states `SLIM+LOCAL` or `CONTAINERS`, one paragraph of why, the captured evidence from steps 2–4, and the confirmed ports. Spec §9.1: "write down which it was and why — the next track inherits it." Add a line correcting §9.1's option 1, so the next reader does not re-derive this.

- [ ] **Step 5: Delete the scratch Dockerfile and commit the note** *(ask before any git command)*

```bash
git add docs/superpowers/notes/2026-10-21-dapr-control-plane-spike.md
git commit -m "docs: record the Dapr control-plane decision for the container image"
```

---

## Task 2: The base image

Spec §7.1 and §8. The four toolchains, the pinned Dapr CLI, the cache layout, and the contract the lab is allowed to assume.

**Files:**
- Create: `images/versions.env`
- Create: `images/base/Dockerfile`
- Create: `images/base/files/dapr-track-caches.sh`
- Create: `images/base/files/maven-settings.xml`
- Create: `images/base/files/start-control-plane.sh` (only if Task 1 decided `SLIM+LOCAL`)
- Create: `tests/images/lib.sh`
- Create: `tests/images/contract.sh`

**Interfaces:**
- Consumes: Task 1's `SLIM+LOCAL`/`CONTAINERS` decision and the confirmed placement/scheduler ports.
- Produces:
  - `images/versions.env`, shell-sourceable, `KEY=VALUE` one per line, keys `DAPR_CLI_VERSION` and `DAPR_RUNTIME_VERSION`. Task 3 and Task 6 source it; the other repo's `awk '/DAPR_CLI_VERSION/ {print $NF}'` idiom must keep working, so no inline comments on those two lines.
  - `tests/images/lib.sh`, sourced by every later test, exporting `IMAGE_BASE` (default `diagrid/university-base:dev`), `IMAGE_SECRETS` (default `diagrid/university-secrets:dev`), `REPO_ROOT`, and a `fail()` that prints and exits 1.
  - `tests/images/contract.sh <image>` — the §8 contract assertions against any image tag, reused in Task 6 against the image pulled from Docker Hub.

- [ ] **Step 1: Write the failing contract test**

`tests/images/contract.sh` takes an image tag as `$1`, defaults to `$IMAGE_BASE`, and asserts each of these as its own named check with a distinct failure message:

```bash
# 1. every tool resolves in BOTH a login and a non-login shell (Review Focus 1)
for tool in dapr dotnet java mvn python3 uv node npm git; do
  docker run --rm "$IMAGE" sh -lc "command -v $tool"   # login shell
  docker run --rm "$IMAGE" sh -c  "command -v $tool"   # non-login shell
done

# 2. the four cache variables are set in a non-login shell
docker run --rm "$IMAGE" sh -c 'echo "$NUGET_PACKAGES"'    # == /opt/caches/nuget
docker run --rm "$IMAGE" sh -c 'echo "$UV_CACHE_DIR"'      # == /opt/caches/uv
docker run --rm "$IMAGE" sh -c 'echo "$npm_config_cache"'  # == /opt/caches/npm
docker run --rm "$IMAGE" sh -c \
  'mvn help:evaluate -Dexpression=settings.localRepository -q -DforceStdout'
  # == /opt/caches/m2 — Maven has no env var, so this proves the global settings.xml (spec §7.4)

# 3. the cache root exists and is world-readable
docker run --rm "$IMAGE" sh -c 'test -r /opt/caches/nuget && test -r /opt/caches/m2'

# 4. the installed Dapr CLI matches versions.env exactly (Review Focus 6)
docker run --rm "$IMAGE" sh -c 'dapr -v' | awk '/CLI version/ {print $NF}'   # == DAPR_CLI_VERSION

# 5. no Docker client, so nothing can quietly depend on a daemon (spec §7.1, §8)
docker run --rm "$IMAGE" sh -c '! command -v docker'
```

If Task 1 decided `SLIM+LOCAL`, add two more checks — this is the §9.1 fix, and it is the one thing in the image that a learner would experience as "Dapr is broken":

```bash
# 6. the runtime matches versions.env, and all three slim binaries are present
docker run --rm "$IMAGE" sh -c 'dapr -v' | awk '/Runtime version/ {print $NF}'  # == DAPR_RUNTIME_VERSION
docker run --rm "$IMAGE" sh -c 'test -x /root/.dapr/bin/daprd \
  && test -x /root/.dapr/bin/placement && test -x /root/.dapr/bin/scheduler'

# 7. the entrypoint actually brings the control plane up: run the image detached, then
#    poll until both ports accept a TCP connection, failing after 30s
#      placement 50005, scheduler 50006   (ports as confirmed by Task 1, not from memory)
```

Check 7 is a TCP connect, not a health endpoint: both services speak gRPC, and "the port is listening" is what `daprd` needs. Sidecar readiness — the real proof — is asserted in Task 4, where a sidecar is actually running.

**Ports and flags confirmed by Task 1, not assumed:** placement on **50005**, scheduler on **50006**, which is what `dapr run` already passes. The scheduler must also take `--healthz-port 8081 --metrics-port 9091`, because placement and scheduler both default to 8080/9090 and the second to start otherwise dies with `bind: address already in use`; and `--etcd-data-dir /var/lib/dapr-scheduler`, because its default is `./data` relative to the working directory and grows to ~123 MB inside whatever folder the learner ran from.

- [ ] **Step 2: Run it to verify it fails**

Run: `bash tests/images/contract.sh`
Expected: FAIL with `Unable to find image 'diagrid/university-base:dev'`.

- [ ] **Step 3: Write `images/versions.env` and `images/base/Dockerfile`**

`versions.env`:

```
DAPR_CLI_VERSION=1.18.2
DAPR_RUNTIME_VERSION=1.18.7
```

`Dockerfile`, `FROM ubuntu:24.04`, with `ARG DAPR_CLI_VERSION` and `ARG DAPR_RUNTIME_VERSION`, installing in this order and carrying forward the hard-won facts the source checklist records (spec §12):

| What | How | The trap |
| --- | --- | --- |
| apt basics | `ca-certificates curl wget git unzip` | — |
| .NET SDK 10 | `apt-get install -y dotnet-sdk-10.0` | **Do not** add the Microsoft apt repo (`/usr/bin/dnx` file conflict) and **do not** add `ppa:dotnet/backports` (carries 9/7/6 on noble) |
| JDK + Maven | `openjdk-17-jdk maven` | — |
| Python | `python3`, then `uv` via `UV_INSTALL_DIR=/usr/local/bin` | `uv` must be on the **default** PATH: the Dapr CLI launches `uv run python app.py`, not a shell that sourced a profile |
| Node 24 | NodeSource setup script, then `nodejs` | — |
| Dapr CLI | `install.sh … \| /bin/bash -s "$DAPR_CLI_VERSION"` | pinned, unlike the checklist it replaces (spec decision 13) |
| Dapr runtime | `dapr init --slim --runtime-version "$DAPR_RUNTIME_VERSION"` | installs `daprd`, `placement` and `scheduler` as binaries and **starts none of them** — hence the entrypoint below. Omit this row entirely if Task 1 said `CONTAINERS` |

If Task 1 decided `SLIM+LOCAL`, add `files/start-control-plane.sh` at `/usr/local/bin`, and make it the image's `ENTRYPOINT`:

- it starts `/root/.dapr/bin/placement` and `/root/.dapr/bin/scheduler` in the background, redirecting each to its own log under `/var/log/`, so a learner reporting "Dapr won't start" leaves evidence behind;
- it waits until both ports accept a connection before handing over, so a terminal that opens quickly cannot race the control plane;
- it then `exec "$@"`, so Instruqt's `command` (or a plain shell) still decides what the container runs. An entrypoint that swallowed `$@` would make the workstation unusable as a terminal target.

This is what keeps every demo's `dapr.yaml` unchanged: the binaries bind the same `localhost:50005` / `:50006` that `dapr run` already assumes, so no `--placement-host-address` or `--scheduler-host-address` ever reaches a learner-visible file.

Then the cache layout, belt and braces across all three mechanisms (spec §7.4):

- `ENV NUGET_PACKAGES=/opt/caches/nuget UV_CACHE_DIR=/opt/caches/uv npm_config_cache=/opt/caches/npm DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1`
- `COPY files/dapr-track-caches.sh /etc/profile.d/` with the same exports, for login shells
- the same `KEY=VALUE` lines appended to `/etc/environment`, for PAM sessions that source neither
- `COPY files/maven-settings.xml /etc/maven/settings.xml`, a `<settings>` document whose only content is `<localRepository>/opt/caches/m2</localRepository>`
- `RUN mkdir -p /opt/caches/nuget /opt/caches/uv /opt/caches/m2 /opt/caches/npm && chmod -R a+rX /opt/caches`

Finish with `apt-get clean && rm -rf /var/lib/apt/lists/*`.

- [ ] **Step 4: Build and run the test to verify it passes**

```bash
set -a; . images/versions.env; set +a
docker build --platform=linux/amd64 \
  --build-arg DAPR_CLI_VERSION --build-arg DAPR_RUNTIME_VERSION \
  -t diagrid/university-base:dev images/base
bash tests/images/contract.sh
```
Expected: every check PASS.

- [ ] **Step 5: Record the image size**

`docker image ls diagrid/university-base:dev --format '{{.Size}}'`. Write the number into Task 1's note under a new "Measurements" heading — spec §9.5 and §10 both ask for it measured rather than assumed.

- [ ] **Step 6: Commit** *(ask first)*

```bash
git add images/versions.env images/base tests/images
git commit -m "feat: add the university-base container image for the Dapr tracks"
```

---

## Task 3: The secrets layer and its warm caches

Spec §7.1, §7.4, §9.3. The thin per-track layer, and the proof that its caches actually hit — the spec's named anti-goal.

**Files:**
- Create: `images/secrets/Dockerfile`
- Create: `tests/images/caches-secrets.sh`

**Interfaces:**
- Consumes: `tests/images/lib.sh` and the base image from Task 2.
- Produces: `diagrid/university-secrets:<tag>`, built with `--build-arg BASE_TAG=<base tag>`. Task 6 passes the immutable base tag; local builds pass `dev`.

- [ ] **Step 1: Write the failing cache test**

`tests/images/caches-secrets.sh`, asserting:

```bash
# 1. the caches are populated, not merely present (spec §8)
#    each of /opt/caches/{nuget,uv,m2} is over 10 MB   (du -sm)

# 2. the demo code is NOT baked in (spec decision 5)
docker run --rm "$IMAGE_SECRETS" sh -c '! test -d /opt/prewarm'

# 3. an OFFLINE build of each language succeeds — the only real proof of a cache hit
#    (Review Focus 2). Repo copied in, then with --network none:
#      dotnet build                    in secrets/dotnet/Demo1-ReadSecret
#      uv sync --offline               in secrets/python/Demo1-ReadSecret
#      mvn -o -q -DskipTests package   in secrets/java/Demo1-ReadSecret

# 4. a NETWORKED build of a demo with one added dependency still succeeds (Review Focus 3):
#    a cache miss must be slow, not fatal
```

For checks 3 and 4, copy the repo into the container rather than mounting it read-only — the builds write `bin/`, `obj/`, `target/` and `.venv/`. Run as `docker run --rm -v "$REPO_ROOT:/src:ro" … sh -c 'cp -r /src/secrets /work && cd /work/…'`.

- [ ] **Step 2: Run it to verify it fails**

Run: `bash tests/images/caches-secrets.sh`
Expected: FAIL — `diagrid/university-secrets:dev` does not exist.

- [ ] **Step 3: Write `images/secrets/Dockerfile`**

`ARG BASE_TAG` then `FROM diagrid/university-base:${BASE_TAG}`. One `RUN` that clones `https://github.com/diagrid-labs/ai-agent-tracks-instruqt.git --depth 1` into `/opt/prewarm`, builds `Demo1-ReadSecret`, `Demo2-Scoping/AppA` and `Demo2-Scoping/AppB` in each of `dotnet`, `python` and `java`, then `rm -rf /opt/prewarm` and `chmod -R a+rX /opt/caches` **in the same layer**, so the checkout never reaches the published image. `Demo3-SwapProvider` is skipped deliberately: it has no application code of its own, it runs Demo1 against another store.

Per-language warm commands, matching what the lab will actually run: `dotnet build`, `uv sync`, `mvn -q -DskipTests package`.

**A warm failure fails the build** (spec §9.3, decided here): no `|| echo WARNING`. The checklist this replaces warned because a human was reading the output; in CI a red build is visible and a cold cache is not.

- [ ] **Step 4: Build and run the test to verify it passes**

```bash
docker build --platform=linux/amd64 --build-arg BASE_TAG=dev \
  -t diagrid/university-secrets:dev images/secrets
bash tests/images/caches-secrets.sh
```
Expected: every check PASS, including the three offline builds.

- [ ] **Step 5: Record the warm build times**

Time one build per language in a fresh container against the warm cache, and append to the Measurements heading. Spec §10 item 2: if a warmed cache is not saving minutes, it has not earned its place in the image.

- [ ] **Step 6: Commit** *(ask first)*

```bash
git add images/secrets tests/images/caches-secrets.sh
git commit -m "feat: add the university-secrets layer with warmed demo caches"
```

---

## Task 4: The lab topology, and components that name services

Spec §7.2, §7.3 and §9.7. Decision 9 moves the component URLs off `localhost`; this task makes that change and proves it by running Demo1 the way the lab will — workstation container, Redis container, one network, code cloned at run time.

**Files:**
- Modify: `secrets/dotnet/resources/statestore-with-secretref.yaml:10`
- Modify: `secrets/python/resources/statestore-with-secretref.yaml:10`
- Modify: `secrets/java/resources/statestore-with-secretref.yaml:10`
- Modify: `secrets/dotnet/Demo3-SwapProvider/resources/statestore-with-secretref.yaml:10`
- Modify: `secrets/python/Demo3-SwapProvider/resources/statestore-with-secretref.yaml:10`
- Modify: `secrets/java/Demo3-SwapProvider/resources/statestore-with-secretref.yaml:10`
- Modify: `tests/images/lib.sh`
- Create: `tests/images/smoke-demo1.sh`

**Interfaces:**
- Consumes: `tests/images/lib.sh`, `diagrid/university-secrets:dev`.
- Produces: `lib.sh` gains `start_topology()` and `stop_topology()` — create a network `dapr-lab`; start `redis:7` as `redis` and `hashicorp/vault:1.20` in dev mode as `vault` (root token `root`, listening on `0.0.0.0:8200`); start the workstation named `ws` from `$IMAGE_SECRETS` on that network with the repo mounted at `/src`; and tear all of it down. Task 5 reuses both.

- [ ] **Step 1: Write the failing smoke test**

`tests/images/smoke-demo1.sh`, for each of `dotnet`, `python`, `java`:

```bash
start_topology
# what the lab's setup step will do: clone (here: copy from /src), write secrets.json
docker exec ws sh -c 'cp -r /src/secrets /work && cp /work/secrets/secrets.example.json /work/secrets/secrets.json'
docker exec -d ws sh -c "cd /work/secrets/$LANG/Demo1-ReadSecret && dapr run -f ."
# the sidecar reaches READY, not merely "Running" — the §9.1 regression guard (Task 1)
docker exec ws sh -c 'curl -s -o /dev/null -w "%{http_code}" http://localhost:3500/v1.0/healthz'
#   == 204 (Task 1: a ready sidecar answers 204 No Content, NOT 200 — asserting 200 fails on a
#   healthy sidecar). A 500 here is ERR_HEALTH_NOT_READY, whose body names the missing part
# then assert through the app and through the sidecar
docker exec ws sh -c 'curl -sf http://localhost:5001/secret/orderdb-password'
#   == {"name":"orderdb-password","value":"s3cr3t-pa55w0rd"}
docker exec ws sh -c 'curl -sf http://localhost:3500/v1.0/secrets/secretstore/payments-api-key'
#   contains pk-test-7f3a9
stop_topology
```

The readiness wait polls the endpoint rather than sleeping a fixed time (Review Focus 4). No `privileged`, no Docker socket in the workstation — if the test needs either, the design has been broken (spec §8).

- [ ] **Step 2: Run it to verify it fails**

Run: `bash tests/images/smoke-demo1.sh`
Expected: FAIL — the sidecar cannot load `statestore`; the component points at `localhost:6379` and nothing listens there inside the workstation container.

- [ ] **Step 3: Change `redisHost` to the service name in all six component files**

`value: localhost:6379` → `value: redis:6379`. Six files, one line each, no other edits. The neighbouring comments explain `secretKeyRef`, not the host, so they stay as they are.

- [ ] **Step 4: Run the test to verify it passes**

Run: `bash tests/images/smoke-demo1.sh`
Expected: PASS for all three languages.

- [ ] **Step 5: Commit** *(ask first)*

```bash
git add secrets tests/images
git commit -m "feat: point the state store at the redis service name for the v2 lab topology"
```

---

## Task 5: Vault — seeding in the image, and the provider swap

Spec §7.3, §9.5 and §9.7. Challenge 4's `docker exec … vault kv put` cannot survive into a lab with no Docker in the learner's hands, and the Vault component's address moves with it.

**Decided here (spec §9.5 leaves it open):** seeding lives in a **script in the image**, `/usr/local/bin/seed-vault.sh`, which the lab's setup step calls. Not the Vault container's entrypoint — that would make the seed a property of a stock upstream image and invisible to this repo's tests. Not inline in the lab HCL — the lab plan would then own logic this repo can test.

**Files:**
- Create: `images/secrets/files/seed-vault.sh`
- Modify: `images/secrets/Dockerfile` (COPY it to `/usr/local/bin`, `chmod 0755`)
- Modify: `secrets/dotnet/Demo3-SwapProvider/resources/secretstore-vault.yaml:12`
- Modify: `secrets/python/Demo3-SwapProvider/resources/secretstore-vault.yaml:12`
- Modify: `secrets/java/Demo3-SwapProvider/resources/secretstore-vault.yaml:12`
- Create: `tests/images/smoke-demo3.sh`

**Interfaces:**
- Consumes: `start_topology()` / `stop_topology()` from Task 4.
- Produces: `seed-vault.sh [SECRETS_JSON]` — defaults to `/work/secrets/secrets.json`, reads `VAULT_ADDR` (default `http://vault:8200`) and `VAULT_TOKEN` (default `root`), waits for Vault, and writes every name/value to `secret/dapr/<name>` over Vault's **HTTP API with `curl`** — no `docker exec`, no `vault` binary in the workstation (spec §7.3). The lab's setup step calls exactly this.

- [ ] **Step 1: Write the failing smoke test**

`tests/images/smoke-demo3.sh`, for each language:

```bash
start_topology                       # vault is up but unseeded
docker exec ws sh -c 'cp -r /src/secrets /work && cp /work/secrets/secrets.example.json /work/secrets/secrets.json'
docker exec ws seed-vault.sh
docker exec ws seed-vault.sh         # idempotence: a second run must be a no-op (Review Focus 5)
docker exec -d ws sh -c "cd /work/secrets/$LANG/Demo3-SwapProvider && dapr run -f ."
docker exec ws sh -c 'curl -sf http://localhost:5001/secret/orderdb-password'
#   == {"name":"orderdb-password","value":"s3cr3t-pa55w0rd"} — same answer as Task 4, now from Vault
docker exec ws sh -c 'curl -sf http://localhost:5001/secrets'
#   == exactly the two names in secrets.example.json, proving the seed wrote both
stop_topology
```

The equality with Task 4's answer is the point of the demo: the same unchanged app, a different store behind the same component name.

Add one readiness check of its own (Review Focus 4): run `seed-vault.sh` against a Vault container started in the same second, and assert it still succeeds rather than racing.

- [ ] **Step 2: Run it to verify it fails**

Run: `bash tests/images/smoke-demo3.sh`
Expected: FAIL — `seed-vault.sh: not found`.

- [ ] **Step 3: Write `seed-vault.sh` and change `vaultAddr`**

The script: `set -eu`; poll `GET $VAULT_ADDR/v1/sys/health` until it answers or 30 seconds pass, failing loudly on timeout in the same wording style as the script it replaces; then, for each name/value read out of the JSON with `python3 -c`, `curl -sf -X POST -H "X-Vault-Token: $VAULT_TOKEN" -d '{"data":{"<name>":"<value>"}}' "$VAULT_ADDR/v1/secret/data/dapr/<name>"`. KV v2, prefix `dapr` — matching the component's defaults, which is why `secretstore-vault.yaml` sets neither.

A `kv put` is last-writer-wins, so a re-run is inherently idempotent; the test pins it so a later rewrite cannot quietly lose that.

Then `value: http://localhost:8200` → `value: http://vault:8200` in the three `secretstore-vault.yaml` files. The comment above `vaultToken` about dev mode stays as it is.

- [ ] **Step 4: Run the test to verify it passes**

Run: `bash tests/images/smoke-demo3.sh`
Expected: PASS for all three languages, both seed runs, and the race check.

- [ ] **Step 5: Run the whole suite**

Run: `bash tests/images/contract.sh && bash tests/images/caches-secrets.sh && bash tests/images/smoke-demo1.sh && bash tests/images/smoke-demo3.sh`
Expected: all PASS. That is the §8 contract in full, and spec §10 item 3 for every part of it that does not need the lab itself.

- [ ] **Step 6: Commit** *(ask first)*

```bash
git add images secrets tests/images
git commit -m "feat: seed Vault over its HTTP API and point the component at the vault service"
```

---

## Task 6: Build and publish from CI

Spec §7.5.2 and §10 item 4 — a version bump must be a PR, not a terminal session. Needs the Prerequisites section done.

**Files:**
- Create: `.github/workflows/images.yml`

**Interfaces:**
- Consumes: `images/versions.env`, both Dockerfiles, `tests/images/contract.sh`, `tests/images/caches-secrets.sh`.
- Produces: `diagrid/university-base:<DATE>-<SHA7>` and `diagrid/university-secrets:<DATE>-<SHA7>`, plus `:latest` on both. **Labs pin the immutable tag** — the lab plan's `sandbox.hcl` takes it from the workflow summary, so a rebuild never changes a running track underneath a learner.

- [ ] **Step 1: Write the workflow**

One job, `runs-on: ubuntu-latest`:

1. checkout; `set -a; . images/versions.env; set +a` into `$GITHUB_ENV`; compute `TAG=$(date +%Y-%m-%d)-${GITHUB_SHA::7}`
2. `docker/setup-buildx-action`, then `docker/login-action` with `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`
3. build base for `linux/amd64` with both version build args, tagged `$TAG` and `latest`
4. build the secrets layer with `--build-arg BASE_TAG=$TAG`, same two tags
5. **run `tests/images/contract.sh` and `tests/images/caches-secrets.sh` against the freshly built images before pushing** — CI owning this is the whole point: a cold cache fails red here instead of silently in a lab
6. push both images, both tags
7. write the two immutable tags into `$GITHUB_STEP_SUMMARY`, so adopting a new image in the lab repo is a copy-paste of one string

Triggers: `push` on `main` limited to `paths: [images/**, secrets/**, .github/workflows/images.yml]`; `workflow_dispatch`; and `schedule` weekly, so an upstream bump surfaces as a red build rather than as a broken lab (spec §7.5.2).

- [ ] **Step 2: Lint it**

Run: `actionlint .github/workflows/images.yml`
Expected: no findings. (If `actionlint` is not installed: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:latest`.)

- [ ] **Step 3: Run it on a branch**

Push the branch and trigger via `workflow_dispatch`.
Expected: green, with both immutable tags in the run summary.

- [ ] **Step 4: Verify the published image, not the local one**

```bash
docker pull diagrid/university-secrets:<TAG>
IMAGE_BASE=diagrid/university-base:<TAG> bash tests/images/contract.sh
IMAGE_SECRETS=diagrid/university-secrets:<TAG> bash tests/images/caches-secrets.sh
```
Expected: PASS. A test that only ever ran against a locally built image proves nothing about what Instruqt will pull.

- [ ] **Step 5: Prove the version bump is a one-file change**

Change `DAPR_CLI_VERSION` in `images/versions.env` to a neighbouring patch release, confirm the workflow produces a new image whose `contract.sh` version check passes against the new number, then revert. Spec §10 item 4, demonstrated rather than asserted.

- [ ] **Step 6: Commit** *(ask first)*

```bash
git add .github/workflows/images.yml
git commit -m "ci: build and publish the Dapr University track images"
```

---

## Task 7: Keep the existing drift CI green

Spec §9.7. Tasks 4 and 5 changed component files that `dapr-university-instruqt`'s Robot suites run against on a GitHub runner, where Vault and Redis really are on `localhost`. One line keeps the same component files working in both places; without it, that repo's CI goes red the moment this plan's PR merges.

**Files:**
- Modify: `C:\dev\diagrid-labs\dapr-university-instruqt\tools\track-tester\ci\setup-dapr-secrets.sh` (in section 5, before the Vault container is started)

**Interfaces:**
- Consumes: the service names `vault` and `redis` fixed by Tasks 4 and 5.
- Produces: nothing other code reads.

- [ ] **Step 1: Watch the drift suites fail**

With this plan's component changes in place, run the dapr-secrets suites as that repo's `tools/track-tester` README describes.
Expected: FAIL — the Vault secret store cannot resolve host `vault`.

- [ ] **Step 2: Add the host aliases**

```bash
echo "127.0.0.1 vault redis" | sudo tee -a /etc/hosts
```

with a comment saying why: the lab reaches these services by container name, CI reaches them on loopback, and the alias means one set of component files serves both — no CI-only copies to drift (spec §9.7).

- [ ] **Step 3: Run the suites to verify they pass**

Expected: PASS, including challenge 3's `DENIED_*` / `MISSING_*` assertions, which nothing in this plan may touch.

- [ ] **Step 4: Commit in `dapr-university-instruqt`** *(ask first — separate repo, separate PR)*

```bash
git add tools/track-tester/ci/setup-dapr-secrets.sh
git commit -m "ci: alias vault and redis to loopback so lab component files work in CI"
```

---

## Deferred

Knowingly out of scope here, each with the reason and what it is waiting on.

| Item | Spec | Why not now |
| --- | --- | --- |
| The v2 lab definition — `sandbox.hcl`, pages, tasks, tabs, the `check.sh`-to-`check`-block rewrite | §7.2, §7.6 | Different repo, different plan. It consumes this plan's image tag and `seed-vault.sh`, and nothing else |
| **Does workstation state survive between tasks?** | §9.8 | **Blocking for the lab plan, not for this one.** Challenges 2–4 all assume a long-running `dapr run` survives a page change. Verify it in the lab plan's first spike; if it does not, those four challenges need restructuring and that plan's estimate changes materially |
| Retiring `sandbox-setup.sh` and moving the `awk` version parse onto `images/versions.env` | §9.6 | The lab still runs that script until it migrates. Until then the two files are a deliberate twin, both reading 1.18.2 / 1.18.7. Task 2's version check catches the image drifting from `versions.env`; nothing catches the twin drifting, so move the parse in the lab plan's first PR |
| The unpinned **canary** CI leg | §9.6 | Lives in the other repo's test CI, alongside the leg it shadows. The spec's proposal stands — a second scheduled leg that installs the CLI unpinned, so a change to Dapr's undocumented denial wording turns one leg red while the learner-facing leg stays green |
| Challenge 2's prose about "the Redis container that `dapr init` started", and whether the tracks still teach `dapr init` | §9.2 | Learner-facing text, lives in the lab repo. The answer must be consistent across every track sharing this image, so decide it once, in the lab plan |
| Sizing the workstation's `resources` block — `cpu` in millicores, `memory` in MB, `disk` | §7.2 | A `container` field, so it lives in `sandbox.hcl`. Start generous: an MSBuild and a Spring Boot build want real memory, and a container that silently inherits a small default would be slow or OOM, inverting the whole point of the warm caches. Tune down with Task 3's measurements rather than guessing upward later |
| Whether the per-challenge `setup.sh` pre-builds survive | §9.5 | Only measurable against a real lab. Task 3's warm build timings are the input to that call |
| Migrating the other tracks onto the base image | §3 | Explicit non-goal. The base must *fit* them, which is why all four toolchains are in it from the start |
| Running the Robot suites inside the published image | §9.4 | Attractive, out of scope, worth costing separately once the image is published and stable |
| Lab start time vs the current VM track | §10 item 1 | The headline number, and it cannot be measured without a lab. First measurement in the lab plan |
