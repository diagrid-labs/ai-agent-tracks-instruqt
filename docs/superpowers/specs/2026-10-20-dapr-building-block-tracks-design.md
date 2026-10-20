# Design: Five Dapr building block tracks for Dapr University

**Date:** 2026-10-20
**Status:** Design — awaiting approval. Nothing is built until this is approved.
**Supersedes:** `2026-10-20-dapr-building-block-tracks-handoff.md` (brainstorming notes; kept for provenance)
**Next step after approval:** a plan (`superpowers:writing-plans`), then build in the order in §3.

---

## 1. Intent and why

Dapr University has nine tracks. Between them they cover state management, service
invocation, pub/sub, workflow, and the agent frameworks. Eight Dapr building block
APIs have no track at all: Actors, Jobs, Secrets, Configuration, Distributed Lock,
Cryptography, Conversation, and Bindings.

Five of those are what people actually ask about in Discord and on customer calls.
This design covers those five.

The questions people bring are consistent, and they are narrower than "teach me this
API":

> *"Getting started with these APIs, what do the parameters mean, how to switch from
> one provider to another."*

Those three questions are the spine of every track here. The second one is the gap in
the existing material: `dapr-101` shows `curl` commands but only glances at a component
file at the very end of challenge 3. "What does this metadata field actually do" has
never had a challenge of its own. That is where these tracks earn their thirty minutes.

### The anti-goal, in the user's words

> *"no quick realization of the value, no aha moment"*

A track that is technically correct but reads like the docs out loud is a **failure**,
even if every challenge passes and every test is green. Each track is therefore built
around one moment the learner *feels*, named in §3, and that moment is the thing to
protect when a challenge runs long and something has to be cut.

---

## 2. Goals, non-goals, anti-goals

### Goals

1. Five new self-paced Instruqt tracks, one per building block: **Secrets,
   Configuration, Conversation, Jobs, Actors**.
2. Each track: **3–4 challenges**, ~5–10 minutes each, **under 30 minutes total**.
3. Each track in **three languages — .NET, Python, Java (Spring Boot)** — with the
   learner choosing per challenge via `<details>` blocks.
4. Each track answers all three recurring questions (§4, the three-act structure).
5. Each track delivers its **aha moment** (§3), and delivers it early.
6. Demo source code lives in **`diagrid-labs/ai-agent-tracks-instruqt`** under
   `<building-block>/<language>/`, cloned onto the sandbox at launch.
7. Learner-facing track content lives in **`diagrid-labs/dapr-university-instruqt`**,
   one new top-level folder per track, following the house layout exactly.
8. **Drift tests ship with the tracks**, not after: a `tests/challenge.robot` suite for
   every runnable challenge, wired into `tools/track-tester/`, plus a per-track CI
   workflow. A track without them is not done.

### Non-goals

- **Catalyst.** All five are core open-source Dapr tracks. No Catalyst, no Diagrid
  account, no sign-up.
- **Kubernetes.** Self-hosted Dapr on a single sandbox VM, as every existing track does.
- **The remaining building blocks.** Distributed Lock, Cryptography, and Bindings are
  out of scope here. Bindings has its own proposal and its own known blocker (the
  PostgreSQL binding is output-only — see the handoff, §3).
- **Production guidance.** These teach the API, not how to run it at scale.
- **JavaScript/Go.** Three languages, matching the Bindings proposal, so authoring
  effort stays consistent.

### Anti-goals (failure even if it all works)

- A track whose value only arrives in the last challenge, or not at all.
- A challenge that is reading with a Run button at the bottom.
- A provider swap the learner has to take on faith because the second provider isn't
  actually on the VM.
- Three languages where two are obviously second-class — a Python learner hitting a
  ".NET only" note in the middle of a challenge.

---

## 3. The five tracks

Build order, as decided:

| # | Track | Slug | Challenges | Aha moment |
|---|---|---|---|---|
| 1 | Secrets | `dapr-secrets` | 4 | An app asks for a secret and is told **no**. |
| 2 | Configuration | `dapr-configuration` | 4 | Change a value in the store; the running app logs the new one with no restart. |
| 3 | Conversation | `dapr-conversation` | 4 | Same code, swap the provider, one YAML field. |
| 4 | Jobs | `dapr-jobs` | 4 | Kill the app, restart it, the job still fires. |
| 5 | Actors | `dapr-actors` | 4 | 100 concurrent increments produce exactly 100. The same 100 against the state store lose updates. |

Secrets goes first because it is the simplest to provision and proves the shared
contract (§5) end to end. Actors goes last for a reason beyond preference — see the
`Dapr.Actors.Next` constraint in §7.

---

### 3.1 Secrets — `dapr-secrets`

**Goal:** show that the Secrets API is not just "a place to put passwords" — it is an
access-controlled indirection that other components can pull from, and that can refuse.

**Aha:** scoping. App A reads the secret. App B asks for the same secret and is refused.
Removing a password from source code is worthy but inert; watching an app get told *no*
is what sticks.

| Ch | Title | ~min | Act | Content |
|---|---|---|---|---|
| 1 | What the Secrets API is for | 5 | 1 | Why a secret store beats a config file or an env var. Run an app that reads one secret from the **local file** store. Plant the hook: two apps, both succeed today — by the end of this track you will make the second one fail on purpose. |
| 2 | The component and its parameters | 8 | 2 | `secretstores.local.file` line by line: `secretsFile`, `nestedSeparator`, `multiValued`. Then the API: `GET /v1.0/secrets/<store>/<key>`, the bulk endpoint, and `secretKeyRef` — another component pulling its password from this store instead of having it inline. |
| 3 | Scoping — the app gets told no | 8 | 2 | Add a `Configuration` resource with a `secrets.scopes` section. `defaultAccess: deny` plus `allowedSecrets`, then `defaultAccess: allow` plus `deniedSecrets`. App A reads; App B is refused. **The aha.** |
| 4 | Swap the provider | 7 | 3 | Local file to **HashiCorp Vault** in a container. Same application code, same `GET`, different YAML. |

**Setup:** `secrets.json` for the local file store; a Vault container (dev mode) started
in `_setup/sandbox-setup.sh` and seeded with the same secret; two app IDs so the scoping
challenge has an App A and an App B.

**Verified:** local file, local environment variables, and HashiCorp Vault are all
**Stable** secret stores (local file and env vars since 1.9, Vault since 1.10). Scoping
fields are `storeName`, `defaultAccess` (`allow` or `deny`), `allowedSecrets`,
`deniedSecrets`; the lists override `defaultAccess`, and a non-empty `allowedSecrets`
means only those keys are reachable.

**Must be verified before the assignment is written:** the docs do **not** state what an
app actually receives when it asks for a secret it is not allowed to read — status code,
body, or SDK exception, and whether it differs per language. The whole aha moment is
that visible refusal, so this has to be confirmed empirically on a sandbox VM in all
three languages before challenge 3 promises anything specific (see §7a for where that
verification runs). If the refusal turns out to be invisible or indistinguishable from
"not found", stop and raise it with the track owner rather than papering over it: this is
the track's reason to exist, and a track built on an aha moment that does not land is the
anti-goal in §2 with a passing test suite attached.

**Lighter fallback for challenge 4** if the Vault container proves costly on the VM:
local file to the **local environment variables** store. Both Stable, no container, and
it still makes the point that application code does not change. Weaker demo, cheaper
setup — the builder's call once the VM is measured, but prefer Vault.

---

### 3.2 Configuration — `dapr-configuration`

**Goal:** separate "configuration" from "state" in the learner's head, and show the
thing the State API cannot do — push notification of change.

**Aha:** the app is running and printing a value. Change that value in the store from the
other terminal, and the running app logs the new one immediately, with no restart. Live
feature-flag flipping; the most visually satisfying of the five.

| Ch | Title | ~min | Act | Content |
|---|---|---|---|---|
| 1 | What the Configuration API is for | 5 | 1 | Read-only, app-config semantics, change notification. How it differs from the State API and from a `.env` file. `GET` one key from the **Redis** configuration store. |
| 2 | The component and its parameters | 7 | 2 | `configuration.redis` metadata (it shares the Redis state store's metadata). Get one key, several keys, all keys. The subscribe call and its key list. |
| 3 | Subscribe and watch it change | 8 | 2 | Subscribe, then `redis-cli SET` from the second terminal and watch the app log it. Note that the first callback carries no items, only the subscription ID — learners trip on this. Then unsubscribe by subscription ID and show updates stop. **The aha.** |
| 4 | Swap the provider | 8 | 3 | Redis to the **PostgreSQL** configuration store. Same subscribe call, same live update. |

**Verified:** Redis and PostgreSQL configuration stores are both **Stable** (both since
1.11). Kubernetes ConfigMap and Azure App Configuration are Alpha and are not used here.
The how-to has examples in .NET, Java, and Python — all three target languages.

**Must be verified before challenge 4 is written:** the PostgreSQL configuration store
needs a configuration table and, for change notification, database-side triggers that
`NOTIFY` on update. That is materially more setup than Redis, and the live-update aha has
to survive the swap or the challenge is pointless. Confirm the exact table schema and
trigger from the component reference, bake them into `_setup/sandbox-setup.sh`, and prove
an update propagates before writing the assignment. If notifications cannot be made to
work inside the time budget, downgrade challenge 4 to a get-only swap and say so plainly
in the assignment rather than implying the subscription works.

---

### 3.3 Conversation — `dapr-conversation`

**Goal:** show why you would call an LLM through Dapr instead of through the vendor's own
SDK — pluggability first, then the parts almost nobody knows are there.

**Aha:** the same application code against a different provider, with one YAML field
changing. Echo for tests, then a real LLM.

**Two providers, not three.** The brainstorming notes called for three — echo, a real
LLM, then another vendor. This design ships two. A third vendor needs either a second
API key (another Instruqt secret, more spend, another thing to break) or an Ollama model
pulled into the VM image, which is gigabytes against a sandbox budget that §5.5 is
already working to protect. The swap lands with two; the third adds cost, not insight.
*(Builder's call, recorded here as mine — the decision to use the built-in
`OPENAI_API_KEY` implies a single real provider.)*

| Ch | Title | ~min | Act | Content |
|---|---|---|---|---|
| 1 | What the Conversation API is for | 5 | 1 | One call against the **echo** component — no key, no spend, deterministic. Why route an LLM call through a sidecar at all. |
| 2 | The component and the request parameters | 8 | 2 | Component metadata versus per-request parameters, which learners conflate. `responseCacheTTL` is **component metadata** (in-memory, per sidecar); `promptCacheRetention` is a **per-request parameter**. Also `temperature`, `responseFormat` (JSON Schema for structured output), and the usage fields `promptTokens`, `completionTokens`, `totalTokens`. |
| 3 | Swap to a real LLM | 7 | 3 | Echo to `conversation.openai`, one YAML field plus a `secretKeyRef`. Same application code. **The aha.** |
| 4 | PII obfuscation and caching | 8 | 2 | Send a prompt containing an email address and a phone number, watch them scrubbed. Then call twice and watch the response cache and the token counts. The "I didn't know it did that" challenge. |

**The key:** the track uses the **built-in `OPENAI_API_KEY` Instruqt sandbox secret**,
following the proven `dapr-agents/_setup/sandbox-setup.sh` pattern — the key is written
into a `secrets.json` read by a local file secret store, and the conversation component
pulls it with `secretKeyRef`. The learner never supplies or sees a key. This is a
deliberate departure from the track-creation skill's default ("the learner sets their own
key in challenge 1"), decided because it removes the single biggest drop-off point in an
otherwise key-free set of tracks.

**Verified:** local **echo** is the only *Stable* conversation component (since 1.15), so
challenge 1 works with no credentials at all.

**CI calls the real model.** Challenges 3 and 4 run against OpenAI in CI, daily, across
all three languages. That needs an `OPENAI_API_KEY` **repository secret** in
`dapr-university-instruqt` — the first workflow in that repo to reference a secret at
all — and it costs money on a schedule. Two consequences for the builder: the
`secrets.json` provisioning in `_setup/sandbox-setup.sh` has to be reproduced in
`tools/track-tester/ci/setup-dapr-conversation.sh`, and the assertions must tolerate
non-deterministic output. Assert on *shape* — a non-empty completion, a scrubbed field
that no longer contains the email address, `totalTokens` greater than zero — never on
model wording, or the suite will fail on days nothing is wrong.

**Known risk, accepted:** the Conversation API itself is **alpha**, and every provider
component except echo is alpha. These assignments **will** drift. The Robot suites are
the mitigation, and the maintenance cost is real and ongoing. The exact config field name
for PII obfuscation is **not yet confirmed** and must be read off the component reference
before challenge 4 is written.

---

### 3.4 Jobs — `dapr-jobs`

**Goal:** show that scheduling belongs outside the process, and that the Scheduler is
already there.

**Aha:** schedule a job, kill the app, restart it — the job still fires. Side by side with
an in-process timer that died with the process.

**This track has no act 3.** The Scheduler is built into Dapr; there is no provider to
swap and no component YAML to write. Act 3 is replaced by the durability demo, and act 2
covers API parameters only. This is the one structural exception in the five, and it is
deliberate.

| Ch | Title | ~min | Act | Content |
|---|---|---|---|---|
| 1 | What the Jobs API is for | 5 | 1 | Schedule a one-shot job, watch it trigger. Why not `Timer` / `BackgroundService` / `@Scheduled`. Note that the Scheduler is a control-plane service `dapr init` already started — no component to configure. |
| 2 | The scheduling parameters | 8 | 2 | `schedule` (cron and `@every`), `dueTime`, `repeats`, `ttl`, `data`, and `overwrite`. Jobs never fire *before* their due time, with no promise about how soon after. Delivery is **at-least-once** — say so, because it changes how handlers are written. |
| 3 | Kill it and watch it survive | 8 | — | A repeating job alongside an in-process timer. Ctrl-C the app. Restart it. The timer is gone; the job fires. **The aha.** |
| 4 | Managing jobs, and when not to use them | 7 | 2 | Get, delete, and overwrite a job; TTL cleanup. Then the comparison people actually ask for: Jobs versus Workflow versus actor reminders versus the cron binding. |

**Verified:** the Jobs API is **stable** as of runtime 1.18, with `ScheduleJob`, `GetJob`,
`DeleteJob`, and the `OnJobEvent` callback; the alpha RPCs are deprecated but still work,
and updated SDKs fall back to them against older sidecars. `dapr/quickstarts/jobs` has
**csharp, java, python** (plus go and javascript), so all three target languages have
working upstream references.

**Must be verified before the assignments are written:** the trigger callback differs by
language. .NET registers `MapDaprScheduledJobHandler` (an HTTP endpoint at
`/job/<job-name>`); Go uses a gRPC `AddJobEventHandler`. The Python and Java callback
mechanics are not documented on the how-to page and must be read from
`dapr/quickstarts/jobs/python/sdk` and `dapr/quickstarts/jobs/java/sdk`. Confirm the
Python SDK's method names — third-party examples still show `schedule_job_alpha1`, and
the assignment should use whatever the current SDK exposes, not the alpha names.

---

### 3.5 Actors — `dapr-actors`

**Goal:** make turn-based concurrency concrete, instead of a sentence in the docs.

**Aha:** fire 100 concurrent increments at one actor; the count is exactly 100. Do the
same against a state store directly; watch updates get lost. The guarantee becomes a
number on screen that is wrong one way and right the other.

| Ch | Title | ~min | Act | Content |
|---|---|---|---|---|
| 1 | What actors are for | 6 | 1 | Invoke a method on one actor. Identity, activation, placement. When an actor is the wrong tool. |
| 2 | 100 at once | 8 | — | Fire 100 concurrent increments at one actor; the result is exactly 100. The same 100 against the state store directly lose updates. **The aha, early, as the handoff requires.** |
| 3 | State, timers and reminders | 8 | 2 | Actor state persistence. Timer versus reminder, and the difference that matters: a reminder survives a restart because the Scheduler holds it. |
| 4 | Swap the actor state store | 6 | 3 | Redis to **PostgreSQL**, same actor code. Covers the `actorStateStore: true` metadata flag and why not every store qualifies. |

**Verified:** Redis and PostgreSQL state stores are both **Stable** and both support
actors; a store qualifies only if it supports transactional operations *and* ETag.
Actors are supported in the .NET, Java, and Python SDKs.

**.NET uses `Dapr.Actors.Next`** — not the original `Dapr.Actors` package. `Dapr.Actors`
has stopped feature work and now receives security fixes only; all new actor development
is in Next, which removes reflection from the actor path and aligns with the SDK's DI,
options, and source-generator patterns. It is not API-compatible with the old package,
callbacks arrive over app-initiated `SubscribeActorEvents` gRPC streams rather than
inbound HTTP, and it ships an in-memory test runtime (`Dapr.Actors.Next.Testing`). See
§7 for the version constraint this creates.

**Note for the builder:** `dapr/quickstarts/actors` has **csharp only**. Unlike the other
four tracks, there is no upstream Python or Java reference to adapt — those demos are
written from scratch against the SDK docs.

---

## 4. The three-act structure

Every track follows the same spine, because the three recurring questions map onto a
3–4 challenge track almost exactly:

- **Act 1 — one challenge, ~5 min.** What this API is for, when you reach for it, and
  the smallest possible working call. Matches the house style: every existing track opens
  with a concept challenge (`1-what-is-dapr`, `1-durable-execution`,
  `1-what-is-dapr-agents`).
- **Act 2 — one or two challenges, ~8 min each.** The component YAML line by line and the
  API's own parameters. **This is the part the existing tracks skip**, and the direct
  answer to "what do the parameters mean".
- **Act 3 — one challenge, ~6–8 min.** Swap the provider without touching application
  code. Same app, different YAML, still works. The Dapr value proposition made literal —
  the thing a blog post cannot deliver but a VM can.

The aha moment is placed wherever it lands hardest, not at a fixed act. In Actors it is
challenge 2; in Conversation it is the act-3 swap itself; in Secrets and Configuration it
is challenge 3. Where it falls later than challenge 2, challenge 1 plants the hook
explicitly (see Secrets ch1).

**Jobs is the documented exception** — no provider to swap, so act 3 becomes the
durability demo and act 2 covers parameters only.

---

## 5. The shared contract

This section is the part the pub/sub migration (§8) also adopts. It is written once here
so all six tracks end up consistent.

### 5.1 Demo source code — `ai-agent-tracks-instruqt`

```
<building-block>/            secrets | configuration | conversation | jobs | actors | pubsub
  <language>/                dotnet | python | java
    README.md                how to run these demos locally, outside Instruqt
    Demo1-<slug>/            one folder per demo, numbered to match the challenge that uses it
    Demo2-<slug>/
    resources/               Dapr component YAML shared by the demos in this language folder
```

- Folder naming follows the existing `Demo<N>-<Slug>` convention in
  `dapr-pub-sub-deep-dive`, so the two repos read the same way. *(Builder's call,
  recorded here as mine — the user specified `<building-block>/<language>` and nothing
  below it.)*
- Component YAML lives beside the code it configures, because the YAML *is* the subject
  matter in act 2 and the learner opens it in the editor tab.
- Where a challenge swaps providers, both component files ship, named for their provider
  (`statestore-redis.yaml`, `statestore-postgres.yaml`).
- Real secrets are never committed. The Conversation track's `secrets.json` is generated
  at sandbox launch from the Instruqt sandbox secret and is git-ignored.

### 5.2 Track content — `dapr-university-instruqt`

One new top-level folder per track, exactly per the repo's
`creating-dapr-university-tracks` skill:

```
<track-slug>/
  README.md                  track config (Name, Url, Teaser, Time limit, Description,
                             Time out idle users, Extra time) — all sections required
  website-description.md     marketing copy for the Dapr University site
  _setup/
    sandbox-setup.sh         runs at every launch: clone source, docker login, dapr init,
                             provision stores, agent variable set
                             (no image script — these tracks reuse a shared sandbox, §5.6)
  <n>-<challenge-slug>/
    README.md                challenge config (Name, Url, Description)
    notes.md                 boot text (ch1 full intro; ch2+ the "sandbox is being
                             prepared" opener)
    assignment.md            learner-facing instructions
    tabs.md                  editor + terminal tabs
    scripts/setup.sh         per-challenge build/restore so the first run is fast
    scripts/check.sh         with fail-message, where there is a verifiable end state
    scripts/solve.sh         paired with every check.sh
    tests/challenge.robot    drift suite (see 5.4)
```

Do **not** create `track.yml`, `config.yml`, or extensionless lifecycle files. Config
lives in `README.md` files in this repo.

### 5.3 Three languages in one assignment

Per-language steps go in collapsible blocks, which is also what the doc-sync checker keys
off for language tagging:

```markdown
<details>
   <summary><b>.NET</b></summary>
...
</details>
```

Annotations are load-bearing: `bash,run` for every runnable command, `text,nocopy` for
expected output, `yaml,copy` for files the learner pastes. The doc-sync checker requires
every runnable `bash,run` block to appear in the neighbouring Robot suite.

Language naming in `<summary>` must be `.NET`, `Python`, `Java` — the checker maps those
strings to the `dotnet` / `python` / `java` tags.

### 5.4 Drift tests — in scope, not follow-on

For each track:

1. `<track>/<n>-<slug>/tests/challenge.robot` — one test case per language, tagged
   `dotnet` / `python` / `java`, importing the shared resources by relative path back into
   `tools/track-tester/`.
2. `tools/track-tester/variables/dapr_<block>.py` — resolves the demo source directory,
   following the existing pattern:
   `TRACKS_SRC_DIR = os.environ.get("TRACKS_SRC_DIR") or os.path.expanduser("~/ai-agent-tracks-instruqt")`.
   These tracks read from `ai-agent-tracks-instruqt`, not from `dapr/quickstarts`, so this
   is a new variables file rather than a reuse of `dapr_101.py`.
3. `tools/track-tester/ci/setup-<track>.sh` — reproduces the sandbox in CI.
4. `.github/workflows/test-<track>.yml` — daily schedule, `workflow_dispatch`, and PRs
   touching the track or the harness; a doc-sync job plus a per-language matrix
   (dotnet, python, java); each leg runs every challenge even if an earlier one fails,
   and failures feed the shared `drift-report` issue.

Existing harness rules that are **not** to be re-litigated: run `robot` from inside
`tools/track-tester/`; keep the `# doc-sync coverage` comment block accurate for commands
performed via `cwd=` or `bash -c`; never simplify `Stop Process With SIGINT` to a
single-PID kill.

Two things to know before writing the first workflow. These five tracks roughly triple
the repo's daily CI footprint — five new workflows, each a doc-sync job plus three
language legs across four challenges, several of them starting Vault, Postgres, or Redis
containers. And `test-dapr-conversation.yml` will be the first workflow in the repo to
use a secret (§3.3); every existing one is credential-free.

### 5.5 Sandbox provisioning

`_setup/sandbox-setup.sh` for every track:

```bash
git clone https://github.com/diagrid-labs/ai-agent-tracks-instruqt.git
docker login -u ${DockerUSER} -p ${DockerPAT}
dapr init                        # plus the running-containers check the other tracks use
agent variable set DAPR_CLI_VERSION <pinned>
agent variable set DAPR_RUNTIME_VERSION <pinned>
# track-specific: seed stores, start Vault/Postgres, pre-build the first demo
```

Pre-building the first demo in `sandbox-setup.sh` and later demos in each challenge's
`scripts/setup.sh` is the `dapr-pubsub` pattern and it matters: it keeps the learner's
first `dapr run` from stalling on a package restore. With three languages that means a
NuGet restore, a `uv sync`, and a Maven resolve — a cold `~/.m2` is the slowest of the
three and should be warmed at image-build time where possible.

### 5.6 The VM image — reuse, don't build

All five tracks run on the existing **"AI Agents Workflow" Instruqt sandbox**. It already
has Python and .NET 10; the track owner is adding **Java** to it, after which it is the
base for all five. No track in this set defines its own image.

This resolves what was the design's one open question. It also means the five
`_setup/image-<slug>-install.sh` scripts the house layout allows for are **not needed** —
the tracks reference the shared sandbox instead, and `_setup/` holds only
`sandbox-setup.sh`. That is a deliberate departure from `dapr-101`, which carries its own
image script.

**Prerequisite, owned by the track owner, not the builder:** Java 17 and Maven in the
sandbox. Track 1 (Secrets) needs it on day one, because every challenge ships in all
three languages from the start. Until it lands, the Java leg of every track is blocked —
Python and .NET work can proceed.

**One request while that update is being made:** pre-warm the Maven cache (`~/.m2`) in the
image with the Dapr Java SDK and Spring Boot dependencies. A cold `~/.m2` is the slowest
of the three restores by a wide margin — the `dapr-workflow` CI legs already have to
pre-warm Maven *outside* the timed run to stay inside a 300-second readiness timeout. If
the cache can be baked in, every Java challenge across the five tracks starts in seconds;
if it cannot, Maven resolution moves into `sandbox-setup.sh` and costs launch time on
every single launch of every Java-using track.

For reference, the repo's own image layer is inconsistent — four different script names
across the tracks and two tracks with no image script at all — and `reference.md` points
at a canonical image workflow, `.github/workflows/build-dapr-workflow-aspire-image.yml`,
that does not exist. Reusing the shared sandbox sidesteps all of that; don't take those
scripts as a pattern to follow.

---

## 6. Versions

Verified on 2026-10-20. Re-verify at build time and pin exactly in each track's setup
script — "latest" is not pinned in an assignment, it is checked and written down.

| Component | Verified latest | Note |
|---|---|---|
| Dapr runtime | **1.18.7** (2026-10-09) | 1.19 in RC |
| Dapr CLI | **1.18.2** (2026-08-21) | |
| .NET `Dapr.Client` | **1.18.10** stable | 1.19.0-rc.3 prerelease available |
| .NET `Dapr.Actors.Next` | **1.19.0-rc.3** — *prerelease only* | no stable release exists; see §7 |
| Python `dapr` | **1.18.3** (2026-07-15) | |
| Java `io.dapr:dapr-sdk` | **1.18.1** stable | 1.19.0-rc-2 is the latest including RCs; Java 17 minimum since Dapr 1.18 |

---

## 7. Constraints and risks

**1. `Dapr.Actors.Next` has no stable release.** The only versions on NuGet are
`1.19.0-preview.1` through `1.19.0-rc.3`. It requires Dapr runtime **1.18.0 or later** and
is expected to go stable alongside the 1.19 runtime and SDK. The Actors track is therefore
pinned to a prerelease package until 1.19 ships. This is why Actors is built last. When
the builder reaches it, one of three applies: 1.19 is GA and it is a non-issue; 1.19 is
still RC and the track pins the RC explicitly in both the project file and
`sandbox-setup.sh`; or the schedule has slipped far enough that the track waits.

**The default is to wait.** If 1.19 is still RC when track 5 comes up, Actors parks until
GA rather than shipping learners on a public university track onto a prerelease package
that will need re-pinning the moment it changes. Track 5 is also the most from-scratch of
the five — prerelease package, no Next-specific quickstart, and no upstream Python or
Java actor reference — so it is the worst one to start speculatively. Override that
default only on an explicit decision; it is a judgement about what the university's name
should be attached to, not a technical call. *(Builder's call, recorded here as mine —
the design previously left this open with no criterion.)*

**2. The Conversation API is alpha**, and every provider component except echo is alpha.
These assignments will drift more than the others. Accepted, with the Robot suites as the
mitigation and the maintenance cost priced in.

**3. The secret-scope refusal is undocumented.** What an app sees when it is denied a
secret is not in the docs and is the entire aha moment of track 1. Verify empirically in
all three languages before writing challenge 3. (§3.1)

**4. The PostgreSQL configuration store's change notification needs database-side
triggers.** Verify before committing to Configuration challenge 4. (§3.2)

**5. Jobs callback mechanics differ per language** and are documented only for .NET and
Go. Read Python and Java from the upstream quickstarts. (§3.4)

**6. No upstream Python or Java actor quickstart exists.** Those demos are written from
scratch. (§3.5)

**7. Three languages multiply everything.** Five tracks times four challenges times three
languages is roughly sixty assignment variants and fifteen demo apps, plus Robot suites
and CI. The build order exists so that track 1 proves the whole contract — layout, setup
scripts, `<details>` structure, Robot suite, CI workflow — before that shape is copied
four more times. Expect track 1 to take disproportionately long and the rest to speed up.

**All five are planned at equal depth, with no review gate after track 1.** The build
order still matters — Secrets is built first and the contract is proved there — but the
plan does not stop and wait for a sign-off before tracks 2 through 5 are planned out. The
risk this accepts is explicit: if building Secrets changes the shared contract in §5,
parts of the other four plans get rewritten. Mitigate it by keeping the contract
artifacts (the `variables/` file, the `ci/setup-*.sh` script, the CI workflow, the
`<details>` conventions) as named deliverables of track 1, so what changes is visible in
one place rather than smeared across four plans.

---

## 7a. Where the verification work happens

The three blocking findings in §7.3–§7.5, plus any spike the builder needs, run on
**WSL2 with Docker, locally**. The `tools/track-tester/ci/setup-*.sh` scripts are the
pattern to follow: they already reproduce a track's sandbox on Ubuntu, which is what CI
does and what WSL2 can do.

What this buys and what it does not: WSL2 is close to the CI runner, and good enough to
answer all three questions — a scope-denied secret returns the same thing to a Python
client whether the kernel is in a sandbox VM or WSL. It is **not** the Instruqt VM, so it
cannot answer questions about image contents, launch time, or the sandbox's resource
budget. Those are the ones that bite at upload time, which is why §5.6 asks the builder
to settle the image question with whoever owns Instruqt rather than infer it from a
local run.

The "aha moment lands on a real sandbox VM" item in the definition of done therefore
stays as written: WSL2 proves the mechanism, and the first real sandbox launch of each
track confirms it survives the environment. If the two disagree, the sandbox wins.

---

## 8. Follow-on: the pub/sub migration

Out of scope as a track design — `dapr-pubsub` is already designed and written — but it
adopts the contract in §5. Recorded here so it is not lost:

- Move the demo code from `diagrid-labs/dapr-pub-sub-deep-dive` into
  `ai-agent-tracks-instruqt/pubsub/dotnet/`, and update
  `dapr-pubsub/_setup/sandbox-setup.sh` and every `tabs.md` path accordingly.
- Port the demos to `pubsub/python/` and `pubsub/java/`.
- Wrap the per-language steps in the existing assignments in `<details>` blocks.
- Add `python` and `java` test cases to the five existing `challenge.robot` suites and
  extend the CI matrix.

Two things to know before starting it: `dapr-pubsub` currently lives on an unmerged branch
in a `.claude/worktrees/dapr-pubsub` worktree, and it is a five-challenge deep-dive track,
not a getting-started track — it does not follow the three-act spine in §4 and should not
be retrofitted to it.

---

## 9. What is left to the builder

Decided here: the five tracks, their order, their challenge breakdowns and timings, the
aha moment each one protects, the three-act spine, the languages, both repo layouts, the
provider swap targets, the key-handling pattern, the testing obligation (including a
live-LLM CI leg for Conversation), the version constraints, where verification runs
(§7a), that images are reused rather than built (§5.6), and that all five are planned at
equal depth with no gate after track 1.

**One dependency outside the builder's control:** Java 17 and Maven being added to the
"AI Agents Workflow" sandbox (§5.6). Python and .NET work can start before it lands; the
Java leg of every track is blocked until it does.

Left to the builder:

- The demo app's domain and story per track — the name, the scenario, what the actor or
  the job or the secret actually *is*. Keep it small enough to read in the editor tab in
  under a minute.
- Exact file, class, and app-ID names.
- The assignment prose itself.
- Which challenges get `check.sh` / `solve.sh`. Pure-reading steps need neither;
  `dapr-workflow` ships with none at all and relies on drift tests. Every `check.sh` needs
  a matching `solve.sh` and a `fail-message` with an actionable hint.
- Whether any challenge needs a diagram in `images/`.
- The fallback calls flagged in §3.1 and §3.2, once the VM is measured.

### Definition of done, per track

- [ ] Track `README.md` with every required section, including `### Time out idle users`
      and `### Extra time`
- [ ] 3–4 challenges, under 30 minutes total, each with `README.md`, `notes.md`,
      `assignment.md`
- [ ] All three languages present in every runnable challenge, in `<details>` blocks
- [ ] Demo code in `ai-agent-tracks-instruqt/<building-block>/<language>/`, cloned by
      `sandbox-setup.sh`
- [ ] Every runnable command tagged `,run`; every output block tagged `,nocopy`
- [ ] `tests/challenge.robot` per runnable challenge, per language, passing
- [ ] `ci/setup-<track>.sh` and `.github/workflows/test-<track>.yml`, green
- [ ] doc-sync passes
- [ ] The aha moment lands, on a real sandbox VM, in all three languages
