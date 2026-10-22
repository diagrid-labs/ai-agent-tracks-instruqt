# Spike: the Dapr control plane in a Docker-less workstation

**Date:** 2026-10-21
**Task:** Task 1 of `docs/superpowers/plans/2026-10-21-dapr-secrets-container-image.md`
**Question:** Spec §9.1 — how do `placement` and `scheduler` reach `daprd` when the workstation is a container with no Docker?

## Decision: `SLIM+LOCAL`

`dapr init --slim` in the image, and the workstation's entrypoint starts the `placement` and
`scheduler` **binaries** locally. No Docker, no extra declared containers, and — because the two
bind the same default ports `dapr run` already assumes — **no demo's `dapr.yaml` changes in any
track.**

Spec §9.1's option 2 (declared control-plane containers) is rejected: it would force
`--placement-host-address` / `--scheduler-host-address` into learner-visible `dapr.yaml` files
across every track, and add two image pulls to lab start.

### Correction to spec §9.1

Option 1 in the spec reads "if the secrets demos genuinely need neither service … `dapr run -f .`
works unchanged." **That is false at 1.18.7.** `dapr run` passes `--scheduler-host-address
localhost:50006` and `--placement-host-address localhost:50005` whether or not the app uses
actors, jobs or workflow, so the sidecar never reaches ready with nothing listening there. The
spec's "fails or warns?" framing has a third answer, below.

## Evidence

Scratch image: `ubuntu:24.04` + `dotnet-sdk-10.0` (noble feed) + Dapr CLI 1.18.2 pinned +
`dapr init --slim --runtime-version 1.18.7`. Demo1-ReadSecret (.NET), `redis:7` as `redis` on a
user-defined network, `statestore-with-secretref.yaml` pointed at `redis:6379` by hand.

### Confirmations from the build

- **Slim installs three binaries**, settling the contradiction between the CLI README and
  third-party write-ups: `daprd` (230 MB), `placement` (45 MB), `scheduler` (59 MB) in
  `/root/.dapr/bin`. It starts none of them.
- `dotnet-sdk-10.0` resolves from Ubuntu's own noble feed → `10.0.113`. `/usr/bin/dnx` is a
  symlink owned by that package, which is exactly why adding the Microsoft apt repo causes the
  file conflict spec §7.1 warns about.

### State A — no control plane running

| Probe | Result |
| --- | --- |
| `dapr run -f .` | **Does not block.** The app starts and serves normally |
| `GET /v1.0/healthz` | **HTTP 500** `{"errorCode":"ERR_HEALTH_NOT_READY","message":"dapr is not ready: [scheduler-watch-hosts internal-placement-service]"}` |
| `GET /v1.0/healthz/outbound` | 204 — outbound is healthy, which is why the APIs still work |
| `GET /secret/orderdb-password` (app) | **200** `{"name":"orderdb-password","value":"s3cr3t-pa55w0rd"}` |
| `GET /v1.0/secrets/secretstore/payments-api-key` (sidecar) | **200** `{"payments-api-key":"pk-test-7f3a9"}` |
| Learner's console | **Clean.** 27 lines, 0 errors — `dapr run -f .` sends daprd output to `.dapr/logs/`, not the terminal |
| `.dapr/logs/*daprd*.log` | **1281 lines, ~5 errors/sec**, `Failed to connect to scheduler host … connection refused` |

So the secrets track *would* function untreated — the Secrets API, the local file store and the
Redis state store all work. What breaks is readiness: anything that gates on the standard
`/v1.0/healthz` endpoint sees a 500 forever.

### State B — `placement` and `scheduler` started locally

| Probe | Result |
| --- | --- |
| `GET /v1.0/healthz` | **HTTP 204** — ready |
| `GET /secret/orderdb-password` | 200, same value as state A |
| `GET /secrets` (bulk) | `{"orderdb-password":"s3cr3t-pa55w0rd","payments-api-key":"pk-test-7f3a9"}` |
| Components | `Component loaded: secretstore (secretstores.local.file/v1)`, `Component loaded: statestore (state.redis/v1)` |
| `.dapr/logs/*daprd*.log` | **77 lines, 0 connection-refused** |

## What Task 2's entrypoint must get right

Three findings that are not obvious and that a naive entrypoint gets wrong:

1. **`healthz` returns `204`, not `200`.** Assert `2xx`, or `204` exactly — a test written against
   `200` fails on a healthy sidecar.
2. **Placement and scheduler both default to healthz `8080` and metrics `9090`**, so starting them
   side by side kills the second one:
   `level=fatal msg="Fatal error running scheduler: listen tcp :8080: bind: address already in use"`.
   The scheduler must be given `--healthz-port 8081 --metrics-port 9091` (placement keeps the
   defaults; either could move, but the scheduler is the one started second).
3. **`scheduler --etcd-data-dir` defaults to `./data`, relative to the working directory**, and
   grows to **123 MB**. Unset, a scheduler started from a demo folder writes 123 MB of etcd data
   into the learner's checkout. Set it explicitly — `/var/lib/dapr-scheduler` was used here.

### Confirmed ports

| Service | gRPC | healthz | metrics |
| --- | --- | --- | --- |
| `placement` | **50005** (default) | 8080 (default) | 9090 (default) |
| `scheduler` | **50006** (default) | 8081 (**override**) | 9091 (**override**) |

Both gRPC ports are what `dapr run` already passes, which is the whole reason no `dapr.yaml`
changes.

### Cost

`placement` 51 MB RSS, `scheduler` 90 MB RSS — about **141 MB** of the workstation's memory
budget, plus 123 MB of disk for the scheduler's etcd data. Input to the §7.2 `resources` sizing
that the lab plan owns.

## Measurements

Recorded as spec §9.5 and §10 ask, rather than assumed. Appended as each task produces a number.

| Measurement | Value | From |
| --- | --- | --- |
| `diagrid/university-base` uncompressed | **1.94 GB** (2.08 GB on-disk with metadata) | Task 2 |
| Control plane ready after container start | **816 ms** | Task 2 |
| `placement` / `scheduler` resident memory | 51 MB / 90 MB (~141 MB) | Task 1 |
| Scheduler etcd data directory | 123 MB | Task 1 |

Four SDKs in under 2 GB is within the range spec §11 anticipated; Instruqt's image streaming is
what makes it cheap to start, which is why the Docker Hub repos must be public (§7.5.1).

## For the tracks that follow

The secrets track stores no jobs, so the scheduler's data directory only has to be *somewhere
harmless* here. The jobs and workflow tracks will actually write to it, and `dapr init` gives the
scheduler a Docker volume precisely because "without this flag, scheduler data is not persisted
and not resilient to restarts." If a future track needs jobs to survive a workstation restart,
that data directory needs to be a declared volume, not a path inside the container's writable
layer.
