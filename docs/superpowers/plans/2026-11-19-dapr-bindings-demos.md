# Dapr Bindings Demos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `bindings/`: four Dapr bindings demos (cron input, PostgreSQL output, state store vs binding, subspace beacon) in .NET, Python and Java that behave identically, plus a smoke-test harness that proves each one.

**Architecture:** Each language folder has a shared `ship-db` PostgreSQL output binding in `resources/` and four `DemoN-*` folders, each with its own `dapr.yaml`, its own cron components in `./resources`, and its own copy of the `engineering` app (plus `subspace-beacon` in Demo 4). Postgres runs in one Docker container whose tables are created by `bindings/sql/init.sql`. A bash smoke script per demo starts the demo, drives it with `curl` and `psql`, asserts on app logs and responses, and stops it. That script is the failing test written before each demo.

**Tech Stack:** Dapr 1.19.1 runtime and CLI; .NET 10 minimal APIs; Python 3.12 + FastAPI + uv; Java 17 + Spring Boot 4.0.8 + Maven; PostgreSQL in Docker; bash + curl + python3 for the smoke tests.

**Spec:** `docs/superpowers/specs/2026-11-18-dapr-bindings-demos-design.md`

## Global Constraints

- Dapr runtime and CLI **1.19.1** (already installed on this machine). .NET `Dapr.Client` / `Dapr.AspNetCore` **1.19.1**, `net10.0`. Python `dapr==1.19.0`, `fastapi`, `uvicorn`. Java `io.dapr:dapr-sdk` **1.19.0**, Java 17, `spring-boot-starter-parent` **4.0.8**, `spring-boot-starter-webmvc`. The same as `pubsub/`.
- Do not change anything under `pubsub/`, `secrets/` or `dapr-101/`.
- No Star Trek trademarks anywhere (no "Enterprise", "Starfleet", "USS", real characters or places). Ship: *ISV Meridian*. Beacon: `relay-theta-9`.
- Folder names: .NET PascalCase (`Demo1-CronTrigger/Engineering`, `Demo4-SubspaceBeacon/SubspaceBeacon`). Python and Java kebab-case (`demo1-cron-trigger/engineering`, `demo4-subspace-beacon/subspace-beacon`). Demo folders: `Demo1-CronTrigger`/`demo1-cron-trigger`, `Demo2-PostgresOutput`/`demo2-postgres-output`, `Demo3-StateVsBinding`/`demo3-state-vs-binding`, `Demo4-SubspaceBeacon`/`demo4-subspace-beacon`.
- Ports, identical in every language: `engineering` app **5201**, Dapr HTTP **3520**. `subspace-beacon` app **5202**, Dapr HTTP **3521**.
- Components: `warp-core-scan` (`bindings.cron`, `schedule: "@every 10s"`, `direction: input`), `purge-old-readings` (`bindings.cron`, `@every 30s`, input), `beacon-ping` (`bindings.cron`, `@every 5s`, input), `ship-db` (`bindings.postgresql`, `direction: output`, `connectionString: "host=localhost port=5432 user=dapr password=dapr dbname=dapr sslmode=disable"` with a comment that this is a local-only credential and that the secrets track shows how to use `secretKeyRef`), `statestore` (`state.postgresql`, `version: v1`, same connection string).
- `dapr.yaml`: Demo 1 `resourcesPaths: [./resources]`. Demos 2–4 `resourcesPaths: [../resources, ./resources]`. Commands as in pubsub: .NET `["dotnet", "run", "--urls", "http://localhost:<port>"]`; Python `["uv", "run", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "<port>"]`; Java `["mvn", "-q", "spring-boot:run"]` with `server.port` in `application.properties`.
- Input bindings are plain HTTP `POST /<binding-name>` endpoints with no Dapr attribute or decorator. Output binding: .NET `DaprClient.InvokeBindingAsync(BindingRequest)`, Python `DaprClient.invoke_binding`, Java `DaprClient.invokeBinding(InvokeBindingRequest, TypeRef)`. All SQL values go through `metadata.params` (a JSON array string, `$1`, `$2`…). No string-concatenated SQL.
- Service invocation (Demo 4): .NET `DaprClient.InvokeMethodAsync<T>(HttpMethod.Get, "subspace-beacon", "ping")`, Python `DaprClient.invoke_method("subspace-beacon", "ping", http_verb="GET")`, Java `DaprClient.invokeMethod("subspace-beacon", "ping", null, HttpExtension.GET, TypeRef)`.
- Comments in code explain the Dapr concept at the line where it happens, in the voice of `pubsub/*/Demo1-Subscriptions`.
- Responses keep JSON keys in the order given in this plan. **One parity exception** *(my call, plan-level)*: JSON numbers are compared by value, not text. .NET serializes `85728.0` as `85728`, and Python and Java keep `.0`. Log lines format numbers with fixed decimals (`stardate` 1, `plasmaFlow` 2), so log lines are text-identical.

## Shared contracts (all languages)

**Reading** (`WarpCoreReading`): `{"readingId": str, "stardate": number, "coreTempK": int, "plasmaFlow": number}`.
- `readingId` = `wc-` + 4-digit zero-padded per-process counter, starting at `wc-0001`.
- `stardate` = `round(78000.0 + (unixSeconds - 1767225600) / 3600.0, 1)` (1767225600 is 2026-01-01T00:00:00Z).
- `coreTempK` = random int in 850..950 inclusive. `plasmaFlow` = random in 0.70..1.00, rounded to 2 decimals.

**SQL** (exact text, the same in every language; the apps cast in SQL so the binding never returns NUMERIC or TIMESTAMPTZ values the apps have to decode):

| Name | Operation | SQL | params |
|---|---|---|---|
| `CLEAR_READINGS` | exec | `DELETE FROM warp_core_readings` | none |
| `INSERT_READING` | exec | `INSERT INTO warp_core_readings (reading_id, stardate, core_temp_k, plasma_flow) VALUES ($1, $2, $3, $4)` | `[readingId, stardate, coreTempK, plasmaFlow]` |
| `SELECT_READINGS` | query | `SELECT reading_id, stardate::float8, core_temp_k, plasma_flow::float8, to_char(recorded_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') FROM warp_core_readings WHERE core_temp_k >= $1 ORDER BY recorded_at DESC, reading_id DESC LIMIT 20` | `[minTemp]` |
| `PURGE_READINGS` | exec | `DELETE FROM warp_core_readings WHERE recorded_at < now() - interval '1 minute'` | none |
| `CLEAR_COMMS` | exec | `DELETE FROM comms_log` | none |
| `INSERT_PING` | exec | `INSERT INTO comms_log (beacon_id, signal_strength, message, stardate) VALUES ($1, $2, $3, $4)` | `[beaconId, signalStrength, message, stardate]` |
| `LAST_PINGS` | query | `SELECT signal_strength FROM comms_log ORDER BY id DESC LIMIT 3` | none |

Rows from `query` are mapped by **column position** unless Task 2 records that the binding returns objects (then by column name; Task 2 says which, and every later task uses that).

**Startup gate.** In Demos 2–4, `engineering` clears its table once at startup, after the sidecar is up: .NET `await daprClient.WaitForSidecarAsync()` in a hosted/background task, Python a background thread that creates the `DaprClient` (which waits for the sidecar), Java `client.waitForSidecar(60000).block()` in an `ApplicationReadyEvent` listener. Every cron handler and every GET endpoint waits on the gate before touching the database. After the gate opens, whether or not the clear succeeded, it logs `engineering cleared <table> for a fresh run` on success, or `engineering could not clear <table>: <error>` (WARNING) on failure, and the app keeps running.

**Log lines** (exact text; the smoke tests grep them; `<…>` fields as named):

| Demo | App | Line |
|---|---|---|
| 1–3 | engineering | `engineering warp-core scan <readingId> stardate=<stardate:0.0> coreTempK=<int> plasmaFlow=<0.00>` |
| 2–4 | engineering | `engineering cleared <table> for a fresh run` |
| 2, 3 | engineering | `engineering stored reading <readingId> in warp_core_readings` |
| 2 | engineering | `engineering purged <n> old readings` (or `engineering purged old readings` if Task 2 risk 2 says no count; see Task 2) |
| 3 | engineering | `engineering saved reading <readingId> to statestore (key=reading-<readingId>)` |
| 4 | engineering | `engineering pinged relay-theta-9 signalStrength=<n> message="<message>"` |
| 4 | engineering | `engineering beacon unreachable` (WARNING) |
| 2–4 | engineering | `engineering binding call failed: <error>` (WARNING) |
| 4 | subspace-beacon | `subspace-beacon answered ping signalStrength=<n>` |

**HTTP contracts:**

| App | Endpoint | Demo | Response |
|---|---|---|---|
| engineering | `POST /warp-core-scan` | 1–3 | `200`, empty body (Demo 2/3: `500` with `{"error": "BINDING_FAILED"}` if the INSERT fails) |
| engineering | `POST /purge-old-readings` | 2 | `200`, empty body |
| engineering | `GET /readings?minTemp=<int>` | 2, 3 | `200 [ {"readingId", "stardate", "coreTempK", "plasmaFlow", "recordedAt"} … ]`. `minTemp` missing → 0. Present but not matching `^-?[0-9]{1,6}$` (including empty, `9.5`, ` 900`, `abc`) → `400 {"error": "INVALID_MIN_TEMP"}`. Binding failure → `500 {"error": "BINDING_FAILED"}` |
| engineering | `GET /state/{readingId}` | 3 | `200 <Reading>` or `404 {"error": "NOT_FOUND"}` |
| engineering | `POST /beacon-ping` | 4 | `200`, empty body, always (including when the beacon is unreachable) |
| engineering | `GET /comms/status` | 4 | `200 {"status": "ESTABLISHED"\|"SEARCHING", "lastSignalStrength": int\|null}` |
| subspace-beacon | `GET /ping` | 4 | `200 {"beaconId": "relay-theta-9", "signalStrength": n, "message": m, "stardate": s}` |

Beacon sequence: `12, 27, 45, 63, 81, 94`, then `94` forever. It is a per-process counter. `message`: `<40` → `"static"`, `40..79` → `"signal acquired"`, `>=80` → `"channel open"`. Status: `ESTABLISHED` iff `LAST_PINGS` returns 3 rows, all `>= 40`. `lastSignalStrength` is the newest row or `null` when there are none.

## Review Focus

1. **Rows from an earlier run or another language.** Expected: every run starts empty, `GET /comms/status` says `SEARCHING` with `null` before the first ping. Pinned by the startup gate, and asserted in Task 4 (empty `GET /readings` right after the clear log line) and Task 6 (`SEARCHING`/`null` before the first ping log).
2. **A cron tick that arrives before the startup clear is done.** Expected: the tick waits and its reading survives the clear. Pinned in Task 4: `wc-0001` is in `GET /readings` once it has been logged as stored.
3. **Odd `minTemp` values (`abc`, empty, `9.5`, `99999999`, `-5`).** Expected: `400 INVALID_MIN_TEMP` for the first four; `-5` is valid and returns every row. Pinned in Task 4.
4. **Postgres not running when a Demo 2–4 smoke test starts.** Expected: the script stops before `dapr run` with `Postgres is not running; start it with tests/bindings/start-postgres.sh`. Pinned by `require_postgres` in Task 1, called by smoke scripts 2–4.
5. **A leaked process from an earlier run holding 5201/3520.** Expected: the test fails at once naming the port. Pinned by `assert_ports_free` (copied from pubsub) at the top of every smoke script.

## File Structure

```
bindings/
  README.md                                      (Task 7)
  sql/init.sql                                   tables from spec §4 (Task 1)
  <lang>/resources/ship-db.yaml                  (Task 1)
  dotnet/Demo1-CronTrigger/        dapr.yaml, resources/warp-core-scan.yaml, Engineering/
  dotnet/Demo2-PostgresOutput/     dapr.yaml, resources/{warp-core-scan,purge-old-readings}.yaml, Engineering/
  dotnet/Demo3-StateVsBinding/     dapr.yaml, resources/{warp-core-scan,statestore}.yaml, Engineering/
  dotnet/Demo4-SubspaceBeacon/     dapr.yaml, resources/beacon-ping.yaml, Engineering/, SubspaceBeacon/
  {python,java}/demo1-cron-trigger/ … same, kebab-case app folders (engineering/, subspace-beacon/)
tests/bindings/
  lib.sh  run-all.sh  start-postgres.sh  smoke-demo1.sh … smoke-demo4.sh
docs/superpowers/notes/2026-11-19-bindings-risk-outcomes.md     spec §7 outcomes
.gitignore                                       add bindings/**/target/ and bindings/**/.dapr/
```

Project files per app: .NET `<App>/<App>.csproj` + `Program.cs`; Python `<app-id>/pyproject.toml` + `app.py`; Java `<app-id>/pom.xml` + `src/main/java/io/diagrid/university/bindings/<app>/…` + `src/main/resources/application.properties` (`server.port`, `spring.application.name`).

---

### Task 1: Postgres, shared component and smoke-test harness

**Files:**
- Create: `bindings/sql/init.sql`, `bindings/{dotnet,python,java}/resources/ship-db.yaml`
- Create: `tests/bindings/lib.sh`, `tests/bindings/run-all.sh`, `tests/bindings/start-postgres.sh`
- Create: `docs/superpowers/notes/2026-11-19-bindings-risk-outcomes.md` (headings for spec §7 risks 1–6, each "not yet verified")
- Modify: `.gitignore` (two `bindings/**` lines next to the pubsub ones)

**Interfaces:**
- Produces `lib.sh`: a copy of `tests/pubsub/lib.sh` with `demo_dir 1..4` and `app_dir engineering|subspace-beacon` (→ `Engineering`/`SubspaceBeacon` in .NET) changed for bindings, plus:
  - `require_postgres` — fails with `Postgres is not running; start it with tests/bindings/start-postgres.sh` unless `docker exec bindings-postgres pg_isready -U dapr -d dapr` succeeds
  - `psql_q <sql>` — runs `docker exec bindings-postgres psql -U dapr -d dapr -tAc "<sql>"` and prints the trimmed result
  - `get_json <url>` — prints `<status> <body>`, like `post_json`
- Produces `start-postgres.sh`: `docker rm -f bindings-postgres`, then `docker run -d --name bindings-postgres -p 127.0.0.1:5432:5432 -e POSTGRES_USER=dapr -e POSTGRES_PASSWORD=dapr -e POSTGRES_DB=dapr -v "$ROOT/bindings/sql:/docker-entrypoint-initdb.d:ro" postgres:<exact tag>`, then waits up to 60 s for `pg_isready` **and** for `SELECT 1 FROM comms_log` to succeed (the init script runs after the first ready). Pin the tag to the newest stable `postgres:<major>.<minor>` on Docker Hub today.
- Produces `run-all.sh`: the pubsub one with demos `1 2 3 4`.

- [ ] **Step 1: Write `init.sql`** with the two `CREATE TABLE IF NOT EXISTS` statements from spec §4, verbatim.
- [ ] **Step 2: Write `start-postgres.sh` and run it.** Expected: `Postgres is ready after <n>s`. Then `docker exec bindings-postgres psql -U dapr -d dapr -tAc '\dt'` lists `comms_log` and `warp_core_readings`.
- [ ] **Step 3: Write `lib.sh` and self-test it.** `bash -c 'source tests/bindings/lib.sh python; require_postgres; psql_q "SELECT count(*) FROM comms_log"'` prints `0`. `docker stop bindings-postgres; bash -c 'source tests/bindings/lib.sh python; require_postgres'` exits non-zero with the message above. Run `start-postgres.sh` again.
- [ ] **Step 4: Write `run-all.sh`, the three `ship-db.yaml` files, the risk note and the `.gitignore` lines.**
- [ ] **Step 5: Commit** `test(bindings): add Postgres setup, ship-db component and smoke harness`.

---

### Task 2: Verify spec §7 risks against a bare sidecar

No app code. Use a sidecar-only run: `dapr run --app-id probe --dapr-http-port 3599 --resources-path bindings/python/resources` (the same pattern as `dapr-101/state-management`'s sidecar-only template), and call `POST http://localhost:3599/v1.0/bindings/ship-db` with `curl`.

**Files:**
- Modify: `docs/superpowers/notes/2026-11-19-bindings-risk-outcomes.md`

**Interfaces:**
- Produces, for Tasks 3–6 (written in the risk note under clear headings):
  - **Row shape** of `query`: arrays or objects, and the raw JSON for one `SELECT_READINGS` row
  - **Rows-affected key** in the `exec` response metadata (for example `rows-affected`) and whether **each** SDK exposes response metadata: .NET `BindingResponse.Metadata`, Python `BindingResponse.binding_metadata`, Java (check whether `invokeBinding` gives access to metadata at all)
  - **Params format** that works: `metadata.params` as a JSON array string, with string and number elements

- [ ] **Step 1: Risk 1 (row shape) and risk 4 (params).** INSERT a row with `INSERT_READING` and params `["wc-9999", 78000.5, 901, 0.88]`, then run `SELECT_READINGS` with `[900]`. Record the exact response body.
- [ ] **Step 2: Risk 2 (rows affected).** Run `CLEAR_READINGS` and record the response metadata. Then read the 1.19.0 Java SDK source for `invokeBinding` and record whether response metadata reaches the caller. **If any SDK can't read the count, stop and ask the user** (spec §7 risk 2). Offer two options: log without a count in all languages, or purge with `DELETE … RETURNING reading_id` through `query` and count the rows.
- [ ] **Step 3: Risk 5 (state store v1).** Add a temporary `statestore.yaml` (`state.postgresql`, `version: v1`) to a scratch folder, run the sidecar with both folders, `POST /v1.0/state/statestore` one item, and record `\d state` output and `SELECT key, value FROM state`. If v1 isn't loadable in 1.19.1, stop and ask the user.
- [ ] **Step 4: Commit** the risk note: `docs(bindings): record Postgres binding and state store probe results`.

Risks 3 and 6 are checked in Task 3, where an app exists.

---

### Task 3: Demo 1 — cron trigger

**Files:**
- Create: `tests/bindings/smoke-demo1.sh`
- Create per language: `Demo1-CronTrigger/{dapr.yaml, resources/warp-core-scan.yaml, Engineering/…}` (kebab-case in Python and Java)

**Interfaces:**
- Consumes: `lib.sh` (Task 1).
- Produces: `WarpCoreReading` and its factory (`createReading()` / `create_reading()`: counter, stardate, random values per Shared contracts), and the `POST /warp-core-scan` handler skeleton. Tasks 4 and 5 copy the `engineering` app from here.

- [ ] **Step 1: Write `smoke-demo1.sh`.** Assertions, in order:
  1. `assert_ports_free 5201 3520`. No `require_postgres`.
  2. `start_demo` with ports `5201 3520`; `wait_for_sidecar 3520`.
  3. `wait_for_log engineering engineering "engineering warp-core scan wc-0001 stardate="` (timeout 60).
  4. `wait_for_log … "engineering warp-core scan wc-0002 "` within 25 s of step 3. That proves the schedule repeats.
  5. The `wc-0001` line matches the regex `^.*engineering warp-core scan wc-0001 stardate=[0-9]+\.[0-9] coreTempK=(8[5-9][0-9]|9[0-4][0-9]|950) plasmaFlow=(0\.[7-9][0-9]|1\.00)$`.
  6. `GET :3520/v1.0/metadata` lists a component named `warp-core-scan` of type `bindings.cron`, and no component named `ship-db`.
- [ ] **Step 2: Run** `bash tests/bindings/smoke-demo1.sh dotnet`. Expected: FAIL (the demo folder doesn't exist).
- [ ] **Step 3: Build the .NET demo.** The component YAML carries comments: the name is the route; change `@every 10s` to `@every 3s`, restart, no code change.
- [ ] **Step 4: Run** `smoke-demo1.sh dotnet` → PASS. Risk 6: if the sidecar never calls the endpoint, check the daprd log for the `OPTIONS /warp-core-scan` probe and record the outcome.
- [ ] **Step 5: Risk 3.** Temporarily make the .NET handler return `500` and watch 3 ticks. Record what daprd logs and that the next tick is still on schedule, with no retry. Revert.
- [ ] **Step 6: Build Python, run `smoke-demo1.sh python` → PASS. Build Java, run `smoke-demo1.sh java` → PASS.**
- [ ] **Step 7: Record the outcomes for risks 3 and 6 and commit** `feat(bindings): add Demo1 cron input binding`.

---

### Task 4: Demo 2 — Postgres output (store, query, clean up)

**Files:**
- Create: `tests/bindings/smoke-demo2.sh`
- Create per language: `Demo2-PostgresOutput/{dapr.yaml, resources/{warp-core-scan,purge-old-readings}.yaml, Engineering/…}`

**Interfaces:**
- Consumes: the Task 3 `engineering` app; the row shape, rows-affected key and params format from Task 2's note.
- Produces: `ship-db` helper functions in `engineering`, reused by Tasks 5 and 6:
  - .NET `Task<BindingResponse> ExecAsync(string sql, params object[] args)` and `Task<JsonElement> QueryAsync(string sql, params object[] args)`
  - Python `exec_sql(sql: str, *args) -> BindingResponse` and `query_sql(sql: str, *args) -> list`
  - Java `Mono<?> exec(String sql, Object... args)` and `List<List<Object>> query(String sql, Object... args)` (or a list of maps if Task 2 found objects)
  - The startup gate (Shared contracts) and `GET /readings`.

- [ ] **Step 1: Write `smoke-demo2.sh`.** Assertions, in order:
  1. `require_postgres`; `assert_ports_free 5201 3520`.
  2. Seed leftovers: `psql_q "INSERT INTO warp_core_readings (reading_id, stardate, core_temp_k, plasma_flow) VALUES ('stale-1', 1.0, 900, 0.80)"`.
  3. `start_demo`, `wait_for_sidecar 3520`, `wait_for_log … "engineering cleared warp_core_readings for a fresh run"`.
  4. `psql_q "SELECT count(*) FROM warp_core_readings WHERE reading_id = 'stale-1'"` = `0` (Review Focus 1).
  5. `wait_for_log … "engineering stored reading wc-0001 in warp_core_readings"`. Then `get_json "http://localhost:5201/readings?minTemp=-5"` → `200`, a JSON array containing an object with `readingId == "wc-0001"`, keys exactly `readingId, stardate, coreTempK, plasmaFlow, recordedAt` in that order, and `recordedAt` matching `^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$` (Review Focus 2).
  6. `minTemp=951` → `200 []`. `minTemp=` (empty), `minTemp=abc`, `minTemp=9.5` and `minTemp=99999999` → `400 {"error": "INVALID_MIN_TEMP"}` (Review Focus 3).
  7. Purge: `psql_q "INSERT … VALUES ('old-1', 1.0, 900, 0.80)"` then `psql_q "UPDATE warp_core_readings SET recorded_at = now() - interval '2 minutes' WHERE reading_id = 'old-1'"`. Then `wait_for_log … "engineering purged "` (timeout 45), and `old-1` is gone from the table. The newest `purged` line has `n >= 1` (skip the count check if Task 2 chose the no-count fallback).
- [ ] **Step 2: Run `smoke-demo2.sh dotnet`** → FAIL.
- [ ] **Step 3: Build the .NET demo** to the Shared contracts. `warp-core-scan` now creates the reading, logs the scan line, runs `INSERT_READING` and logs the stored line. `purge-old-readings` runs `PURGE_READINGS`.
- [ ] **Step 4: Run `smoke-demo2.sh dotnet`** → PASS.
- [ ] **Step 5: Python → PASS, Java → PASS** with the same script.
- [ ] **Step 6: Commit** `feat(bindings): add Demo2 Postgres output binding`.

---

### Task 5: Demo 3 — state store vs binding

**Files:**
- Create: `tests/bindings/smoke-demo3.sh`
- Create per language: `Demo3-StateVsBinding/{dapr.yaml, resources/{warp-core-scan,statestore}.yaml, Engineering/…}`

**Interfaces:**
- Consumes: the Task 4 `engineering` app (copy it, then drop the purge endpoint and its component).
- Produces: nothing for later tasks.

State calls: .NET `SaveStateAsync("statestore", key, reading)` / `GetStateAsync<WarpCoreReading?>`; Python `save_state` / `get_state` (an empty `data` means not found); Java `saveState` / `getState(…, WarpCoreReading.class)` (a null value means not found). Key = `reading-<readingId>`.

- [ ] **Step 1: Write `smoke-demo3.sh`:**
  1. `require_postgres`; ports free; start; `wait_for_sidecar 3520`.
  2. `wait_for_log … "engineering saved reading wc-0001 to statestore (key=reading-wc-0001)"` and `"engineering stored reading wc-0001 in warp_core_readings"`.
  3. `get_json :5201/state/wc-0001` → `200`, `readingId == "wc-0001"`, keys `readingId, stardate, coreTempK, plasmaFlow`. Its `coreTempK` equals the `coreTempK` of `wc-0001` in `get_json :5201/readings?minTemp=-5`.
  4. `get_json :5201/state/wc-nope` → `404 {"error": "NOT_FOUND"}`.
  5. `psql_q "SELECT count(*) FROM state WHERE key = 'engineering||reading-wc-0001'"` = `1` (Dapr prefixes keys with the app ID; if Task 2 recorded a different prefix, use that).
- [ ] **Step 2: Run for dotnet** → FAIL. **Step 3: Build .NET** → PASS.
- [ ] **Step 4: Python → PASS, Java → PASS.**
- [ ] **Step 5: Commit** `feat(bindings): add Demo3 state store vs binding`.

---

### Task 6: Demo 4 — subspace beacon

**Files:**
- Create: `tests/bindings/smoke-demo4.sh`
- Create per language: `Demo4-SubspaceBeacon/{dapr.yaml, resources/beacon-ping.yaml, Engineering/…, SubspaceBeacon/…}`

**Interfaces:**
- Consumes: the Task 4 `ship-db` helpers and startup gate (the table is `comms_log`).
- Produces: nothing for later tasks.

- [ ] **Step 1: Write `smoke-demo4.sh`:**
  1. `require_postgres`; `assert_ports_free 5201 5202 3520 3521`.
  2. Seed leftovers: three `comms_log` rows with signal `94`.
  3. Start; wait for sidecars 3520 and 3521; `wait_for_log engineering … "engineering cleared comms_log for a fresh run"`.
  4. Before the first `pinged` log line appears: `GET :5201/comms/status` → `{"status": "SEARCHING", "lastSignalStrength": null}`. If a ping has already been logged by the time of the call, accept `SEARCHING` with `12` instead (Review Focus 1).
  5. `wait_for_log … 'engineering pinged relay-theta-9 signalStrength=27 message="static"'` → status `SEARCHING`, `lastSignalStrength` `27`.
  6. `wait_for_log … 'signalStrength=81 message="channel open"'` (timeout 60) → status `ESTABLISHED`, `lastSignalStrength` `81`.
  7. `wait_for_log subspace-beacon … "subspace-beacon answered ping signalStrength=45"`.
  8. `psql_q "SELECT string_agg(signal_strength::text, ',' ORDER BY id) FROM comms_log"` starts with `12,27,45,63,81`.
- [ ] **Step 2: Run for dotnet** → FAIL. **Step 3: Build .NET** → PASS.
- [ ] **Step 4: Check the unreachable case by hand once (.NET only).** Comment `subspace-beacon` out of `dapr.yaml`, run, and confirm `engineering beacon unreachable` is logged as a WARNING on each tick, nothing is stored, and the sidecar logs no binding error. Revert.
- [ ] **Step 5: Python → PASS, Java → PASS.**
- [ ] **Step 6: Commit** `feat(bindings): add Demo4 subspace beacon`.

---

### Task 7: README and full run

**Files:**
- Create: `bindings/README.md`

- [ ] **Step 1: Write the README**, shaped like `pubsub/README.md`:
  - Prerequisites (Dapr 1.19.1, Docker, `lsof`, the language runtimes).
  - Ports table.
  - A "Start Postgres" block (the same commands as `start-postgres.sh`, safe to run twice).
  - A demos table (challenge, .NET folder, Python/Java folder, what it shows).
  - Per demo: the run command, the `curl` calls, and the expected output.
  - The `psql` commands learners use: `docker exec -it bindings-postgres psql -U dapr -d dapr`, `\d state`, `\d warp_core_readings`, `SELECT * FROM comms_log;`.
  - The raw `query` row shape from Task 2.
  - A "State store vs binding" comparison (spec §3.3 bullets).
  - What the sidecar does when the cron handler fails (risk 3 outcome).
- [ ] **Step 2: Full run:** `bash tests/bindings/start-postgres.sh && bash tests/bindings/run-all.sh`. Expected: 12 × `PASS`.
- [ ] **Step 3: Check the theme:** `grep -rniE 'enterprise|starfleet|\buss\b|kirk|picard|spock|vulcan|klingon|romulan' bindings tests/bindings` → no matches.
- [ ] **Step 4: Commit** `docs(bindings): add README for the bindings demos`.
