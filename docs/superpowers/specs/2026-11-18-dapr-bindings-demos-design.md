# Design: Dapr bindings demos (`bindings/`)

**Date:** 2026-11-18
**Status:** Approved 2026-11-19
**Scope:** Demo source code in this repo only. The Instruqt track content (`assignment.md`,
Robot suites, setup scripts in `dapr-university-instruqt`) is built separately, later.

Decisions are marked as follows. Anything not marked was decided by the user in the
brainstorming session. *(My call)* marks a choice the designer made that the user has not
reviewed. The builder may revisit those but should say so.

---

## 1. Intent and why

After the track, a learner understands **what Dapr bindings are** and has used both directions:

- **Input binding (cron):** Dapr calls the app on a schedule. The app has no timer of its own.
- **Output binding (PostgreSQL):** the app asks Dapr to run SQL against Postgres. It uses
  `exec` for INSERT and DELETE and `query` for SELECT, so it can store, query and clean up data.

One demo puts the **State Management API and the Bindings API** side by side against the
same Postgres database, so the difference between the two is concrete.

The PostgreSQL binding only works as an output binding (verified in the 2026-10-20 handoff,
§3). That's why cron supplies the input side. This matches that handoff's recommendation (b).

### Theme

The track has a sci-fi theme modelled on the Star Trek world. It uses **only fictional names**
and no Star Trek trademarks: no "Enterprise", "Starfleet", "USS", real characters or real
places. Generic genre words such as *starship*, *stardate*, *warp core*, *plasma*,
*subspace*, *beacon* and *engineering* are fine.

The story: the starship's **engineering** console logs warp-core readings on a schedule, and
pings a **subspace beacon** automatically to establish communications.

Fictional names *(my call)*:

| Thing | Name |
|---|---|
| Starship | *ISV Meridian* (appears in log lines only) |
| Beacon | `relay-theta-9` (the beacon ID it reports) |

---

## 2. Goals, non-goals, anti-goals

### Goals

1. A new top-level `bindings/` folder with `dotnet/`, `python/` and `java/` (Spring Boot)
   subfolders, laid out like `pubsub/` and `secrets/`.
2. **Four demos per language**, one per challenge (§3).
3. **Dapr 1.19** runtime, CLI and SDKs, the same versions as `pubsub/` (§6).
4. The three languages behave identically: same app IDs, ports, routes, request and response
   JSON (including key order), SQL, table names and log lines (§5).
5. `bindings/README.md` explains how to run every demo locally, including starting Postgres.
6. Smoke-test scripts in `tests/bindings/`, shaped like `tests/pubsub/` (`lib.sh`,
   `smoke-demoN.sh`, `run-all.sh`, `start-postgres.sh`).

### Non-goals

- Track content (`assignment.md`, `notes.md`, Instruqt setup scripts, Robot suites).
- Any binding other than cron and PostgreSQL. No Kafka, HTTP or blob bindings.
- The State Query API (alpha). Demo 3 compares tables and access patterns. It does not
  claim the State API "cannot query".
- JavaScript or Go.
- Using Postgres credentials from a secret store. The secrets track covers that. The
  component holds a local-only connection string, with a comment saying so *(my call)*.

### Anti-goals (a failure even if everything runs)

- **Languages that drift apart.** The same rule as pubsub.
- **SDK sugar hiding the binding.** The input binding is a plain HTTP `POST /<binding-name>`
  endpoint with no Dapr attribute or decorator, so the learner sees that the binding's
  *name is the route*. The output binding uses the SDK's thin `InvokeBinding` call, which
  maps one-to-one onto the HTTP API (binding name, operation, data, metadata).
- **Demos where nothing visible happens.** Every tick produces a log line, and every
  endpoint returns something the learner can read. Rows can be checked with `psql`.
- **SQL built by string concatenation.** All values go in through the binding's `params`
  metadata (`$1`, `$2`, …). This is a teaching repo, and people copy it.
- **Real Star Trek names** anywhere in code, logs, YAML or README.

---

## 3. The four demos

Apps *(my call for IDs and ports)*:

| App ID | Role | App port | Dapr HTTP port |
|---|---|---|---|
| `engineering` | Engineering console. Receives cron triggers and calls the Postgres binding. | 5201 | 3520 |
| `subspace-beacon` | Relay station that answers pings (Demo 4 only) | 5202 | 3521 |

These ports stay clear of secrets (5001+, 3500+) and pubsub (5101+, 3510+).

Components *(my call for names)*:

| Name | Type | Direction | Used in |
|---|---|---|---|
| `warp-core-scan` | `bindings.cron`, `@every 10s` | input | 1, 2, 3 |
| `purge-old-readings` | `bindings.cron`, `@every 30s` | input | 2 |
| `beacon-ping` | `bindings.cron`, `@every 5s` | input | 4 |
| `ship-db` | `bindings.postgresql` | output | 2, 3, 4 |
| `statestore` | `state.postgresql` (v1) | (state store) | 3 |

Every binding component sets `metadata.direction` (`input` or `output`) explicitly, so the
learner sees which direction each one runs and Dapr doesn't probe the app for output-only
bindings.

**Clean start.** In Demos 2, 3 and 4, `engineering` clears its own table on startup with one
`exec` through `ship-db`, before the first cron tick is handled. Demos 2 and 3 clear
`warp_core_readings`, and Demo 4 clears `comms_log`. It logs
`engineering cleared <table> for a fresh run`. All demos and languages share one Postgres
container, so without this, rows from earlier runs would leak into `GET /readings` and
make Demo 4 report `ESTABLISHED` before the first ping (decided by the user, 2026-11-18).
If the clear fails because Postgres is down, the app logs the error and keeps running.
Demo 3's `state` table isn't cleared: its keys are overwritten each run.

Warp-core reading payload, identical in every language *(my call)*:

```json
{ "readingId": "wc-0007", "stardate": 78412.6, "coreTempK": 912, "plasmaFlow": 0.87 }
```

- `readingId` is a per-process counter, `wc-0001`, `wc-0002` and so on.
- `stardate` is a made-up but monotonically increasing number derived from the current
  time (formula is the builder's choice, the same in every language).
- `coreTempK` is a random integer between 850 and 950. `plasmaFlow` is a random number
  between 0.70 and 1.00, rounded to two decimals.

### 3.1 Demo 1: cron trigger (`Demo1-CronTrigger` / `demo1-cron-trigger`)

- `engineering` only. Components: `warp-core-scan` (cron, `@every 10s`).
- The app exposes `POST /warp-core-scan`. The route matches the component name, and Dapr
  calls it on every tick. The handler creates a reading, logs
  `engineering warp-core scan wc-0001 stardate=78412.6 coreTempK=912 plasmaFlow=0.87`,
  and returns `200`.
- No Postgres in this demo.
- README and comments point out:
  - the schedule lives in YAML (change `@every 10s` to `@every 3s` and restart, with no code change)
  - the binding's name is the route
  - a non-2xx response is logged by the sidecar as an error, and a cron tick is not
    redelivered *(the builder verifies this before stating it, see §7 risk 3)*

### 3.2 Demo 2: Postgres output (`Demo2-PostgresOutput` / `demo2-postgres-output`)

Components: `warp-core-scan`, `purge-old-readings`, `ship-db`.

- **Store:** each `warp-core-scan` tick INSERTs the reading through `ship-db` (`exec`) and logs
  `engineering stored reading wc-0001 in warp_core_readings`.
- **Query:** `GET /readings?minTemp=900` runs a parameterized SELECT (`query`) and returns
  the matching rows, newest first, at most 20, as
  `[{ "readingId": …, "stardate": …, "coreTempK": …, "plasmaFlow": …, "recordedAt": … }]`.
  If `minTemp` is missing it defaults to 0. If it isn't an integer, the endpoint returns
  `400 {"error": "INVALID_MIN_TEMP"}`.
- **Clean up:** each `purge-old-readings` tick runs
  `DELETE FROM warp_core_readings WHERE recorded_at < now() - interval '1 minute'` (`exec`)
  and logs `engineering purged <n> old readings`. `<n>` is the rows-affected count that the
  binding returns in its response metadata *(see §7 risk 2)*.
- The learner can watch rows come and go with `psql`.

### 3.3 Demo 3: State store vs binding (`Demo3-StateVsBinding` / `demo3-state-vs-binding`)

Components: `warp-core-scan`, `ship-db`, `statestore` (`state.postgresql`, the same
Postgres database).

- Each tick writes the same reading **twice** and logs both:
  - State API: key `reading-<readingId>`, with the reading JSON as the value.
    Log: `engineering saved reading wc-0001 to statestore (key=reading-wc-0001)`.
  - Binding: INSERT into `warp_core_readings`, as in Demo 2.
- Two read endpoints, one per API:
  - `GET /state/{readingId}` reads one reading by key through the State API.
  - `GET /readings?minTemp=900` runs the same SQL query as Demo 2.
- The lesson, carried by the README and code comments:
  - **State API:** Dapr owns the table (`state`: key, JSON value, etag, timestamps) and
    gives you get, set and delete by key, plus concurrency (ETags), TTL and transactions.
    It's portable across 30+ stores.
  - **Binding:** you own the schema and write the SQL. You can filter, sort and delete in
    bulk, but your code is now tied to Postgres. Swapping the component won't work.
- The learner opens `psql` and runs `\d state` and `\d warp_core_readings` to see both tables.

### 3.4 Demo 4: Subspace beacon (`Demo4-SubspaceBeacon` / `demo4-subspace-beacon`)

Apps: `engineering` and `subspace-beacon`. Components: `beacon-ping`, `ship-db`.

- `subspace-beacon` exposes `GET /ping` and returns
  `{ "beaconId": "relay-theta-9", "signalStrength": 45, "message": "…", "stardate": … }`.
  `signalStrength` walks through a fixed sequence (`12, 27, 45, 63, 81, 94`), then stays
  at 94. The story then plays out the same way in every run and language: a weak signal
  that firms up *(my call)*. Restarting the beacon restarts the sequence.
  `message` is `"static"` below 40, `"signal acquired"` from 40 to 79, and
  `"channel open"` from 80 up.
- On each `beacon-ping` tick, `engineering` does three things:
  1. Calls `subspace-beacon`'s `ping` method through **service invocation** (SDK
     `InvokeMethod` to app ID `subspace-beacon`).
  2. INSERTs the response into `comms_log` through `ship-db`.
  3. Logs `engineering pinged relay-theta-9 signalStrength=45 message="signal acquired"`.
- If the beacon is unreachable, it logs `engineering beacon unreachable` and stores nothing.
  The handler still returns `200`, so the sidecar doesn't log a binding error on every tick
  while the beacon starts up *(my call)*.
- `GET /comms/status` queries the last 3 rows of `comms_log` and returns:
  - `{"status": "ESTABLISHED", "lastSignalStrength": 94}` if all 3 have signal ≥ 40
  - `{"status": "SEARCHING", "lastSignalStrength": <n or null>}` otherwise
- This demo connects everything: input binding → service invocation → output binding.

---

## 4. Layout

Same naming conventions as `pubsub/`: PascalCase in .NET, kebab-case in Python and Java.

```
bindings/
  README.md
  sql/init.sql                     creates warp_core_readings and comms_log (shared by all languages)
  dotnet/ | python/ | java/
    resources/
      ship-db.yaml                 bindings.postgresql, direction: output
    Demo1-CronTrigger/
      dapr.yaml
      resources/warp-core-scan.yaml
      Engineering/
    Demo2-PostgresOutput/
      dapr.yaml                    resourcesPaths: [../resources, ./resources]
      resources/warp-core-scan.yaml, purge-old-readings.yaml
      Engineering/
    Demo3-StateVsBinding/
      resources/warp-core-scan.yaml, statestore.yaml
      Engineering/
    Demo4-SubspaceBeacon/
      resources/beacon-ping.yaml
      Engineering/  SubspaceBeacon/   (engineering/ subspace-beacon/ in Python and Java)
tests/bindings/
  lib.sh  run-all.sh  start-postgres.sh  smoke-demo1.sh … smoke-demo4.sh
```

- Demo 1's `dapr.yaml` loads only `./resources`, so no Postgres component is loaded and
  Postgres doesn't need to be running *(my call)*.
- Each demo keeps its own copy of the `engineering` app, so one folder shows everything.
  Duplication is fine in teaching code (the same rule as pubsub).
- Every demo runs with `dapr run -f .` from inside its folder.
- `.gitignore` gets `bindings/**/target/` and `bindings/**/.dapr/`.

### Postgres

- Docker container, pinned to an exact `postgres` image tag at build time. Bound to
  `127.0.0.1:5432` with user, password and database all set to `dapr` *(my call)*.
  `bindings/sql/init.sql` is mounted into `/docker-entrypoint-initdb.d/`, so the tables
  exist on first start. The README has a "Start Postgres" block that is safe to run
  twice and waits until `pg_isready` answers, like the RabbitMQ block in `pubsub/README.md`.
  `tests/bindings/start-postgres.sh` does the same.
- Schema *(my call)*:

  ```sql
  CREATE TABLE IF NOT EXISTS warp_core_readings (
    reading_id   TEXT PRIMARY KEY,
    stardate     NUMERIC(8,1) NOT NULL,
    core_temp_k  INTEGER NOT NULL,
    plasma_flow  NUMERIC(3,2) NOT NULL,
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
  );
  CREATE TABLE IF NOT EXISTS comms_log (
    id               SERIAL PRIMARY KEY,
    beacon_id        TEXT NOT NULL,
    signal_strength  INTEGER NOT NULL,
    message          TEXT NOT NULL,
    stardate         NUMERIC(8,1) NOT NULL,
    pinged_at        TIMESTAMPTZ NOT NULL DEFAULT now()
  );
  ```

- `readingId` restarts at `wc-0001` on every app start. That doesn't collide with the
  primary key, because the app clears `warp_core_readings` on startup (§3, clean start).
  The INSERT stays plain.
- The `state` table for Demo 3 is created by the state store component itself.

---

## 5. Cross-language parity rules

The same rules as `pubsub/` design §5:

- The same app IDs, ports, routes, JSON bodies (including key order), log lines, SQL text
  and table names.
- Failures are shown, not swallowed. A binding call that fails returns `500` with
  `{"error": "BINDING_FAILED"}` from an HTTP endpoint, and a log line from a cron handler.
- Code comments explain the Dapr concept on the line where it happens.
- Stack: .NET 10 minimal API; Python 3.12 FastAPI with `uv`; Java 17 with Spring Boot 4.0.8
  and Maven.
- Output binding calls: .NET `DaprClient.InvokeBindingAsync`, Python
  `DaprClient.invoke_binding`, Java `DaprClient.invokeBinding`. Parameters go in the
  `params` metadata key as a JSON array string. Query results are mapped to the §3 JSON
  shapes by the app, not passed through raw.
- Service invocation (Demo 4): .NET `DaprClient.InvokeMethodAsync`, Python
  `DaprClient.invoke_method`, Java `DaprClient.invokeMethod`.

---

## 6. Versions

Pin exact versions at build time, matching `pubsub/` §6: Dapr runtime and CLI 1.19.1,
.NET `Dapr.Client` / `Dapr.AspNetCore` 1.19.1, Python `dapr` 1.19.0, Java `io.dapr:dapr-sdk`
1.19.0. Postgres image: the latest stable major version at build time, pinned to an exact tag.

---

## 7. Risks: verify these before writing the demo that depends on them

1. **`query` result shape.** Check what the 1.19 PostgreSQL binding returns for `query`:
   an array of arrays or an array of objects, and how `NUMERIC` and `TIMESTAMPTZ` are
   encoded. The apps map rows to the §3 JSON either way, but the README should show the raw
   shape once so learners know it.
2. **Rows-affected for `exec`.** Confirm that the binding reports rows affected in its
   response metadata, and under which key. If it doesn't, Demo 2 logs
   `engineering purged old readings` without a count, the same in all languages, and the
   user should hear about it.
3. **Cron behaviour on failure.** Confirm what the sidecar logs when the handler returns
   non-2xx, and that the tick isn't retried. State it in the README only after verifying it.
4. **`params` metadata.** Confirm that parameterized `exec` and `query` with `$1`-style
   placeholders work through all three SDKs in 1.19.
5. **`state.postgresql` v1 vs v2.** v1 stores the value as JSONB in a `state` table, which
   is readable in `psql`. Confirm v1 is still supported in 1.19 and use it. If only v2 is
   supported, check whether its table is still readable enough for Demo 3's comparison.
   If it isn't, raise this with the user.
6. **Input-binding route probing.** Dapr may send `OPTIONS /<binding-name>` at startup to
   check whether the app handles the route. Confirm the minimal-API / FastAPI / Spring
   endpoints are detected without extra code.

If any of these fails in a way that changes what the learner sees, stop and raise it with
the user. Don't quietly change the lesson.

---

## 8. What is left to the builder

- The stardate formula, project names and exact log wording for anything not quoted above.
- How the startup clear is ordered relative to the first cron tick in each framework, as
  long as no tick is stored before the clear finishes.
- Whether Java uses `JdbcTemplate`-free plain SDK calls (it should: there's no JDBC driver
  in the apps, since the binding does the database work).

### Definition of done

- All four demos run with `dapr run -f .` in all three languages, with matching output.
- `tests/bindings/run-all.sh` passes for `dotnet`, `python` and `java`.
- Every §7 risk has a written outcome (in the plan or under `docs/superpowers/notes/`).
- `bindings/README.md` covers prerequisites, starting Postgres, running each demo, and the
  `psql` commands the learner uses.
- `.gitignore` is updated.
