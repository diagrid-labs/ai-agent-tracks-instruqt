# Design: a shared container image for the Dapr University tracks on Instruqt v2

**Date:** 2026-10-21
**Status:** Design — approved to hand off, not yet built
**Image and demo code:** `diagrid-labs/ai-agent-tracks-instruqt`
**Lab definition and instructions:** `diagrid-labs/dapr-university-instruqt`
**Replaces:** the hand-pasted `_setup/image-*-install.sh` checklists in `dapr-university-instruqt`

---

## 1. Intent

Instruqt's v2 "labs" take a **Docker image** as the learner's compute, and those labs load
noticeably faster than the VM-backed sandboxes the Dapr University tracks use today. We want the
new Dapr tracks on that faster path.

Today each track carries a file like `dapr-secrets/_setup/image-dapr-secrets-install.sh`. Despite
the `.sh` extension it is **not a script anything runs** — it is a checklist of commands a human
pastes, in order, into a build VM's terminal to produce a custom VM image. That is slow to
produce, impossible to review by running it, and drifts silently from what the tracks need.

This design replaces that with one image, built by CI, that several Dapr tracks share.

### Why now

- v2 labs are the target platform for the new tracks, and they want an image, not a VM.
- Faster lab start is a direct learner benefit: these are 30-minute tracks, and minutes spent
  waiting for a sandbox are minutes not spent learning.
- The manual image build is a maintenance tax that nobody enjoys paying, and a rebuild is needed
  every time the Dapr CLI, .NET, or a demo's dependencies move.

---

## 2. Goals

1. **One shared base image** carrying the four language toolchains, the Dapr CLI, git, and warm
   package caches, usable by every Dapr track.
2. **A thin per-track layer** on top of that base for anything track-specific — principally the
   warmed dependency caches for that track's demo apps.
3. **Built and published by a GitHub Actions workflow** in `ai-agent-tracks-instruqt`, not by
   hand. A version bump should be a PR, not a terminal session.
4. **dapr-secrets runs on it end to end**, as the first track to migrate, with the same learning
   content it has now.
5. **The demo code is still cloned at lab start**, so demo changes reach learners without an
   image rebuild.

## 3. Non-goals

- Migrating the other tracks in this piece of work. The base image should *fit* them; moving
  them is separate.
- Changing what any track teaches. The Secrets API, the scoping lesson and the Vault swap stay
  exactly as they are conceptually.
- Maintaining the VM path. dapr-secrets is not published yet, so there is no live VM track to
  keep running alongside the lab — the checklist and the VM image it describes are simply
  retired. The other tracks keep their VM setup until each one is migrated on its own.
- Building for anything but `linux/amd64` (see constraints).

## 4. Anti-goals

Things that would make this a failure even if it technically worked:

- **A privileged container running Docker-in-Docker.** It is possible on this platform, but it
  reintroduces the daemon-boot and image-pull cost we are trying to remove, and the whole point
  of the move is speed.
- **An image so specific to dapr-secrets that the next track needs its own base.**
- **Caches that silently miss**, leaving a learner to sit through a cold NuGet or Maven restore
  while the image proudly reports that it warmed them.
- **A lab that only the author can rebuild**, i.e. CI that needs a secret or a step that lives in
  someone's head.

---

## 5. Constraints

Verified against the Instruqt docs on 2026-10-21:

| Constraint | Source |
| --- | --- |
| `container` resources are declared in `sandbox.hcl` and accept `image`, `entrypoint`, `command`, `environment`, `volume`, `port`, `network`, `capabilities`, `resources`, `run_as`, `health_check`, and `privileged` (default `false`) | [Container reference](https://docs.labs.instruqt.com/reference/sandbox/compute/container/) |
| `docker_host()` returns the environment's Docker endpoint (`tcp://docker:2375` or `unix:///var/run/docker.sock`) and is passed to a container as `DOCKER_HOST` | [Lab environment functions](https://docs.labs.instruqt.com/reference/functions/lab-environment/) |
| **Linux x86/amd64 images only.** Build with `--platform=linux/amd64` on Apple Silicon | [Custom container images](https://docs.instruqt.com/sandboxes/hosts/custom-container-images) |
| **Image streaming** — the fast-load path — works only for public Docker Hub and Google Artifact Registry. **GHCR, Quay and ECR are not eligible**, nor are V2 schema 1 manifests | [Custom container images](https://docs.instruqt.com/sandboxes/hosts/custom-container-images) |
| Instruqt v2 labs docs describe themselves as beta | docs.labs.instruqt.com |

Other constraints from the existing material:

- The Dapr versions are pinned in exactly one place today —
  `dapr-secrets/_setup/sandbox-setup.sh` holds `DAPR_CLI_VERSION 1.18.2` and
  `DAPR_RUNTIME_VERSION 1.18.7`, and `tools/track-tester/ci/setup-dapr-secrets.sh` parses them
  out of that file with `awk`. Whatever replaces the setup script must keep a single owner for
  those two numbers, or the CI drift guard loses its anchor.
- The demo apps live in `ai-agent-tracks-instruqt` under `secrets/{dotnet,python,java}/` as
  `Demo1-ReadSecret`, `Demo2-Scoping/AppA`, `Demo2-Scoping/AppB` and `Demo3-SwapProvider`
  (the last has no application code of its own — it runs Demo1 against a different store).
- `secrets.example.json` in that repo is the single owner of the secret values; both the sandbox
  setup and CI copy it to `secrets.json`.

---

## 6. Decisions already made

These were settled in the brainstorming conversation and are **not** open for the builder to
revisit. Where a decision was mine rather than Marc's, it says so.

| # | Decision | Whose |
| --- | --- | --- |
| 1 | Docker image for Instruqt v2 labs, replacing the custom VM image | Marc's |
| 2 | The track text and the demo code may both be adjusted to fit the new topology | Marc's |
| 3 | Four toolchains in the base: .NET, Python, Java, JavaScript/npm | Marc's |
| 4 | A GitHub Actions workflow builds and publishes the image | Marc's |
| 5 | The demo repo is still cloned at lab start, not baked into the image | Marc's |
| 6 | One shared base image plus a thin per-track layer | Marc's |
| 7 | **No DinD, no privileged workstation.** Supporting services are declared `container` resources alongside the workstation | mine |
| 8 | **Docker Hub** as the registry | mine — `sandbox-setup.sh` already does `docker login` with `DockerUSER`/`DockerPAT`, and Docker Hub is streaming-eligible where GHCR is not |
| 9 | Component URLs move from `localhost` to the service's container name | mine — follows from 7 |
| 10 | Node 24 via NodeSource | mine — matches `dapr-workflow/_setup/image-dapr-workflow-install.sh` |
| 11 | **The two repos keep their existing split**: `dapr-university-instruqt` holds the instructions (lab definition, pages, tasks, scripts); `ai-agent-tracks-instruqt` holds the demo code, the Dockerfiles and the build workflow | Marc's |
| 12 | **Docker Hub `diagrid/university-base`**, with the images **public**. The `diagrid` organization does not exist yet — see §7.5.1 | Marc's |
| 13 | **The image pins the Dapr CLI.** A new Dapr version means a new image | Marc's |
| 14 | **The lab reuses the existing `dapr-secrets` track URL and slugs.** That track is not live yet, so there are no learners to protect during the migration | Marc's |

---

## 7. The shape of it

### 7.0 Where things live

The two repos keep the split they have today, which means this work is a coordinated change
across both rather than one PR in one place:

| Repo | Owns |
| --- | --- |
| `ai-agent-tracks-instruqt` | the demo apps under `secrets/{dotnet,python,java}/`, their component YAML, `secrets.example.json`, **and now the Dockerfiles plus the build workflow**. The image lives here because the per-track layer warms caches by building this repo's demos |
| `dapr-university-instruqt` | the instructions: the lab definition (`*.hcl`), the page Markdown that today is `assignment.md`, the task check/solve/setup scripts, and the `track-tester` drift suites |

The coupling between them is one string: **the image tag the lab pins**. Publishing a new image
does not change a lab until someone edits that tag, which is what makes rebuilds safe.

A builder should expect to open two PRs — image first, lab second — and should not try to move
either repo's existing responsibilities while doing it.

### 7.1 Images

```
diagrid/university-base:<tag>             the four toolchains + Dapr CLI + git + empty warm caches
  └── diagrid/university-secrets:<tag>    + warmed caches for the secrets demos
  └── diagrid/university-<next>:<tag>     + warmed caches for that track's demos
```

The base contains, at the versions the tracks assume today:

| Tool | Version | Why |
| --- | --- | --- |
| .NET SDK | 10.0, from **Ubuntu's own noble feed** | the demos target `net10.0`. Do **not** add the Microsoft apt repo — it no longer carries .NET for Ubuntu and mixing it in causes a `/usr/bin/dnx` file conflict; do **not** add `ppa:dotnet/backports` either, which on noble carries 9/7/6 |
| JDK + Maven | OpenJDK 17, distro Maven | Spring Boot 3.4.5 demos with `<java.version>17</java.version>` |
| Python | 3.12 (distro default) + `uv` in `/usr/local/bin` | demos require >=3.12 and start via `uv run python app.py`, launched by the Dapr CLI, so `uv` must be on the default PATH of every terminal — not only in a shell that sourced a profile |
| Node | 24 (NodeSource) + npm | the fourth language |
| Dapr CLI | **pinned** (1.18.2 today). A new Dapr version means a new image — see §9.6 for where the number lives and what it does to the drift signal | every challenge runs `dapr run -f .` |
| git, curl, wget, unzip, ca-certificates | distro | the demo repo clone and the install scripts |

**No Docker Engine in the image.** That is the biggest single change from the VM, and it is what
makes the image small and the lab fast.

### 7.2 The lab topology

```
sandbox.hcl
├── container "workstation"   the image above; the learner's terminal(s)
├── container "redis"         redis:7            — challenge 2's state store
└── container "vault"         hashicorp/vault:1.20 dev mode — challenge 4
```

Supporting services become declared containers rather than things a setup script starts with
`dapr init` and `docker run`. They start in parallel with the workstation and are already warm
when the learner's terminal opens.

**Size the workstation explicitly** (mine). The `resources` block takes `cpu` in millicores
(100–8000), `memory` in MB (128–32768) and `disk`, and a container that silently inherits a small
default will make a Maven or MSBuild run slow or OOM — which would invert the whole point of the
warm caches. Declare it, start generous (an MSBuild and a Spring Boot build want real memory),
and tune down with the §10 measurements rather than guessing upward later.

### 7.3 What this changes in the track

| Today | After |
| --- | --- |
| `dapr init` in `sandbox-setup.sh` brings up placement, scheduler and Redis | Redis is a declared container; the Dapr control plane is handled per §9.1 |
| Vault component: `value: http://localhost:8200` | `value: http://vault:8200` |
| Challenge 4: `docker exec -e VAULT_ADDR=… vault vault kv put secret/dapr/shipping-token …` | a `curl` against Vault's HTTP API from the workstation (mine — the track already teaches with `curl`, and it removes the last need for a Docker CLI in the learner's hands) |
| Challenge 2 prose: "The Redis container that `dapr init` started has no password" | reworded for a Redis that the lab started (see §9.2) |
| `sandbox-setup.sh` clones the repo, writes `secrets.json`, starts and seeds Vault, pre-builds Demo1 | a lab setup step still clones and writes `secrets.json`; Vault seeding moves to the Vault container's own startup or a setup step against `http://vault:8200` |

### 7.4 Caches

The image warms package caches at **build** time; the demo code arrives at **launch** time. That
combination works as long as the caches live where every user and shell can find them and the
demos' dependency sets don't move underneath them.

```
/opt/caches/nuget   NUGET_PACKAGES
/opt/caches/uv      UV_CACHE_DIR
/opt/caches/m2      Maven has no env var — point the global settings.xml at it
/opt/caches/npm     npm_config_cache
```

Export the env vars in the image (`ENV`), and *also* write them to `/etc/profile.d/` and
`/etc/environment` if the lab may open shells that don't inherit the image's environment. Maven
reads the global `settings.xml` (`/etc/maven/settings.xml` on Debian/Ubuntu), which needs no env
var and is therefore the most robust of the four.

A cache that misses is a slow lab, not a broken one — but it is also the main thing this image is
*for*, so §10 asks for it to be measured rather than assumed.

### 7.5 Build and publish

#### 7.5.1 One-time: create the Docker Hub organization

The `diagrid` Docker Hub organization does not exist yet. Before the first build can publish:

1. Sign in to Docker Hub with an account that should own the org, go to
   **Organizations → Create Organization**, and claim the namespace `diagrid`. If that namespace
   is already taken by someone else — it is a short, common word, so check early — agree a
   fallback before the image names are baked into any lab config.
2. Create the repositories `university-base` and `university-secrets`, both with visibility
   **Public**. Public is not cosmetic here: Instruqt's image streaming only applies to public
   Docker Hub (or Artifact Registry) repos, and streaming is the fast-load path this whole design
   is built on. A private repo still works, just slowly.
3. Create an **organization access token** (Account Settings → Personal access tokens, or the
   org's own token page) with **Read & Write** scope. Note the token value once — it is not
   shown again.
4. Add it to `ai-agent-tracks-instruqt` under **Settings → Secrets and variables → Actions** as
   `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`. Keep these distinct from the `DockerUSER` /
   `DockerPAT` values the Instruqt sandbox uses: the sandbox only needs **pull**, CI needs
   **push**, and a pull-only token in CI produces exactly the "only the author can rebuild"
   failure this design lists as an anti-goal.
5. Invite whoever else should be able to rebuild. A one-person org reproduces the same anti-goal
   by a different route.

#### 7.5.2 The workflow

A workflow in `ai-agent-tracks-instruqt`:

- builds `track-base` and each `track-<name>` layer for `linux/amd64`;
- pushes to Docker Hub using the existing `DockerUSER` / `DockerPAT` credentials;
- tags with both an immutable tag (date + short SHA, e.g. `2026-10-21-a1b2c3d`) and a floating
  `latest`. **Labs pin the immutable tag**, so a rebuild never changes a running track underneath
  a learner; moving a track to a new image is a deliberate one-line change;
- runs on a schedule as well as on push, so an upstream bump surfaces as a red build rather than
  as a broken lab.

### 7.6 What the lab definition looks like in v2

Verified from the labs docs, because the builder review rightly pointed out that this design
described the image in detail and the thing consuming it barely at all. A v2 lab is **a directory
of HCL files** plus the Markdown, scripts and assets they reference, and every v1 lifecycle piece
this track uses has a v2 equivalent:

| v1 (today) | v2 equivalent |
| --- | --- |
| `assignment.md` per challenge | a **page** pointing at a Markdown file; its `activities` map binds ids to `task`/`quiz` resources, and those ids appear as tags in the Markdown |
| `scripts/setup.sh` | a `setup` block inside a task's `condition` — runs when the condition becomes active |
| `scripts/check.sh` | one or more `check` blocks per `condition`; **all** conditions must pass for the task to complete |
| `scripts/solve.sh` | a `solve` block — runs only when the learner skips the condition |
| (no equivalent) | a `cleanup` block, after the condition finishes |
| `tabs.md` with `host:` | `tabs.hcl` with `terminal` and `editor` resources; `target` references a container |
| Instruqt's `fail-message` helper | **`failure_message` is a fixed string in the HCL.** A check script cannot emit its own message — its output is captured for debugging only |

Two consequences the builder should plan around:

- **Scripts choose where they run.** `config.target` can be set on the task, the condition or an
  individual script (most specific wins) and points at a container, a VM, or nothing — in which
  case the script runs on the sandbox host rather than inside the workstation. Every check that
  inspects the learner's files or curls a running app must target the workstation container.
- **One check per failure cause.** Because `failure_message` is static, today's `check.sh` files
  that branch and emit different messages become several `check` blocks, one per cause. That is a
  mechanical rewrite, but it is a rewrite, and the messages are learner-visible.

The **editor tab survives**: an `editor` resource takes `workspace` blocks with a `directory` and
an optional `target` referencing a container, so challenges 2 and 3 can keep having the learner
edit YAML in place. The directory needs permissions the tab's user can write.

There is a reference implementation to copy from at
[github.com/instruqt/lab-examples](https://github.com/instruqt/lab-examples) — it includes a
`task` example with check and solve scripts and a `container-terminal` example. `instruqt lab
validate` checks locally that referenced script files exist before a push.

---

## 8. The image/lab contract

What the lab may assume the image provides. A builder should treat this as the acceptance
criteria for the base image:

| Guarantee | Check |
| --- | --- |
| `dapr`, `dotnet`, `java`, `mvn`, `python3`, `uv`, `node`, `npm`, `git` all resolve on the default PATH of a non-login shell | `sh -lc 'command -v …'` and `sh -c 'command -v …'` both succeed |
| The four cache env vars are set in any shell the learner gets | `env` in a fresh terminal |
| `/opt/caches` is world-readable and populated | `du -sh /opt/caches/*` is non-trivial |
| No Docker daemon is required for the track to work | nothing in the lab passes `privileged = true` |
| Vault is reachable at `http://vault:8200`, Redis at `redis:6379` | from the workstation container |

---

## 9. Left to the builder

These are real decisions, not oversights. Each needs a spike or a judgement call that the
conversation couldn't settle.

### 9.1 How `daprd` gets a placement and scheduler service — **the main open question**

Without `dapr init`'s containers, `dapr run -f .` still needs the Dapr runtime, and depending on
what the demos use, a placement service (actors) and a scheduler (jobs, workflow). The secrets
demos appear to use neither, but "appears to" is not good enough to build on.

Two candidate paths, in order of preference:

1. **Slim mode.** `dapr init --slim` during the image build installs `daprd`, placement and
   scheduler as **binaries** with no containers at all. If the secrets demos genuinely need
   neither service, this is the smallest, fastest answer, and `dapr run -f .` works unchanged.
   Verify: does `daprd` start cleanly and serve the Secrets and State APIs with no placement or
   scheduler running, or does it fail rather than warn?
2. **Declared control-plane containers.** Run `daprio/dapr:<runtime>` as placement and scheduler
   containers in `sandbox.hcl` and point the apps at them (`--placement-host-address`,
   `--scheduler-host-address`, or the equivalent fields in each demo's `dapr.yaml`). More moving
   parts, but no reliance on what daprd tolerates.

Pick by spike, and write down which it was and why — the next track inherits it.

### 9.2 Whether `dapr init` stays in the track's vocabulary

Challenge 2's prose leans on "the Redis container that `dapr init` started". If the lab starts
Redis, that sentence is simply false and must be reworded. More broadly: decide whether the new
tracks still *teach* `dapr init` as the local-dev story (it remains what a learner does on their
own laptop) or whether the lab quietly provides the infrastructure. Keep that choice consistent
across the tracks that share this image.

### 9.3 The per-track layer's mechanics

How the per-track Dockerfile takes the base (`ARG BASE_TAG`), which demos it warms, and whether a
warm failure fails the build or merely warns. Today's checklist warns; in CI, failing is probably
right, since a red build is visible and a cold cache is not.

### 9.4 Whether the drift tests move onto the image

`tools/track-tester/ci/setup-*.sh` currently reproduces the sandbox in CI by hand. Running the
Robot suites *inside* the published image would make CI test what learners actually get, and
would delete those scripts. Attractive, out of scope here, and worth costing separately.

### 9.5 Smaller calls

- Whether the workstation runs as root or via `run_as` with a named user. Root is simplest and
  matches today's assumptions; a named user is tidier, needs the caches to be group-readable, and
  must be able to write the directory the editor tab exposes.
- Whether Vault seeding lives in the Vault container's entrypoint, a lab setup step, or a small
  script in the image.
- Image size budget. Four SDKs is multiple gigabytes; streaming makes that cheaper than it looks,
  but measure before assuming (§10).
- Whether the per-challenge `setup.sh` pre-builds survive. Today every challenge's setup builds
  Demo1 in all three languages before the learner sees the page (challenge 3 does two apps). With
  warm caches these should be seconds rather than minutes — but if they aren't, they are the
  first thing to cut, because the lab now starts the services in parallel anyway.

### 9.6 Where the pinned Dapr version lives, now that the image pins it

**Decided (Marc): the image pins the Dapr CLI, and a new Dapr version means a new image.** What
is left to the builder is where the number lives and what happens to the drift signal. The
current arrangement is deliberate and slightly subtle, so it must not be changed by accident:

- `sandbox-setup.sh` sets `DAPR_CLI_VERSION 1.18.2` and `DAPR_RUNTIME_VERSION 1.18.7` as
  `agent variable set` lines, and `ci/setup-dapr-secrets.sh` `awk`s the versions out of that file
  — so the numbers live in exactly one place.
- Both the image checklist and the CI setup nonetheless install the CLI **unpinned**, on purpose:
  the drift suites then assert what a learner actually gets, and challenge 3's denial-wording
  constants (`DENIED_*` / `MISSING_*`) turn red precisely when a Dapr release changes the
  undocumented wording. That red is the signal, not a bug.

When `sandbox-setup.sh` goes away, both halves need a new home, and if §9.1 lands on slim mode
the runtime version becomes a property of the image too.

**My proposal, for the builder to confirm:**

- The versions move to a single file in `ai-agent-tracks-instruqt` next to the Dockerfiles — a
  `versions.env` with `DAPR_CLI_VERSION` and `DAPR_RUNTIME_VERSION`, read as build args by the
  image build and parsed by `ci/setup-dapr-secrets.sh` the same way it `awk`s them today. One
  owner, same as now, just a different address.
- **Keep the drift signal by splitting CI in two.** The main leg installs the *pinned* versions,
  so it tests what a learner actually gets. A second scheduled leg installs the CLI **unpinned**
  — the canary. When Dapr changes the undocumented denial wording, the canary goes red while the
  main leg stays green, which is the early warning to update the `DENIED_*` / `MISSING_*`
  constants, the assignment, and the image pin together.

That keeps both properties that are currently fused into one unpinned install: fidelity to the
learner's environment, and advance notice of upstream wording changes. If the builder finds the
second leg is not worth its cost, say so explicitly rather than letting the canary lapse.

### 9.7 Moving the demo components to service names, and keeping the drift CI green

Decision 9 changes `secretstore-vault.yaml` (`http://localhost:8200`) and
`statestore-with-secretref.yaml` (`localhost:6379`) in all three languages.

**The dapr-secrets track is not live yet (decision 14), so there are no learners to protect.**
Change the components on `main` in one PR — no migration branch, no duplicated component files.
That is the whole of the content side.

The one thing that does break is CI: `ci/setup-dapr-secrets.sh` runs on a GitHub runner where
Vault and Redis really are on `localhost`, so a component that says `http://vault:8200` will not
resolve there. **My call:** add host aliases in that setup script —

```bash
echo "127.0.0.1 vault redis" | sudo tee -a /etc/hosts
```

— so the same component files work unchanged in CI and in the lab. It is one line, it keeps the
suites asserting the files learners actually use, and it avoids a second set of CI-only
components that could drift. The drift CI is expected to stay green through the migration, not
be switched off for it.

### 9.8 Does the workstation's state survive between tasks?

The docs describe a lab's sandbox as one environment that the pages and tasks run inside, which
implies containers are not recreated per task — but they do not say so outright, and this track
leans on it hard: challenge 2 has the learner edit a YAML file and revert it, challenge 3 edits
`dapr.yaml` and expects a long-running `dapr run -f .` to still be serving ports 5002/5003 when
the check runs, and challenge 4 curls a running app on 5001 and its sidecar on 3500.

**Verify this in the very first spike.** If containers are recreated per task, or a long-running
foreground process doesn't survive a page change, the four challenges need restructuring rather
than rewording, and the estimate for this work changes materially.

---

## 10. How we'll know it worked

1. **Lab start time** from "start lab" to a usable terminal, compared against the current VM
   track. This is the whole reason for the work — measure it, write the number down.
2. **First `dapr run` time** for each of the four languages, cold lab. If a warmed cache isn't
   saving minutes, it isn't earning its place in the image.
3. **dapr-secrets completes end to end** on the new lab, all four challenges, in all three
   languages it currently supports.
4. **A version bump is a PR.** Changing the Dapr CLI version touches one file and produces a new
   image with no terminal session involved.

---

## 11. Risks

| Risk | Mitigation |
| --- | --- |
| v2 labs are beta; the container resource or the task/tab schema may change | pin the lab to an immutable image tag; confirm the Instruqt org actually has labs-beta access before the work starts, since everything here depends on it |
| The demos' dependencies move and the baked caches go stale | caches degrade to slow, not broken; the scheduled rebuild re-warms them |
| Four toolchains make a large image | streaming mitigates; measure (§10) and consider dropping a language from the base if one track never needs it |
| A single shared base couples the tracks — one bump affects all | immutable tags mean each track adopts a new base when it chooses |
| Docker Hub rate limits or credential rot in CI | the same `DockerUSER`/`DockerPAT` the sandbox already uses; verify they're organization credentials, not personal |

---

## 12. Source material

- `dapr-university-instruqt/dapr-secrets/_setup/image-dapr-secrets-install.sh` — the checklist
  this replaces. Its comments record several hard-won facts worth carrying over: the .NET feed
  trap, why `uv` must land in `/usr/local/bin`, and why the caches cannot live in `$HOME`.
- `dapr-university-instruqt/dapr-secrets/_setup/sandbox-setup.sh` — what the lab setup must still
  do: clone, write `secrets.json` from `secrets.example.json`, start and seed Vault.
- `dapr-university-instruqt/tools/track-tester/ci/setup-dapr-secrets.sh` — the CI reproduction,
  and the `awk` parse that makes the pinned versions single-sourced.
- `dapr-university-instruqt/ai-agents-deepagents/_setup/image-definition.sh` — the `/usr/bin/dnx`
  conflict note.
- `dapr-university-instruqt/dapr-secrets/*/assignment.md` — challenges 2 and 4 are the ones whose
  text this topology change touches.
