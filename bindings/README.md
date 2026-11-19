# Dapr Bindings demos

Demo apps for the Dapr University bindings track, in .NET, Python and Java. The story: the starship's **engineering** console logs warp-core readings on a schedule and pings a **subspace beacon** to establish communications. Along the way you use both directions of a Dapr binding:

- **Input binding (cron):** Dapr calls your app on a schedule. The app has no timer of its own.
- **Output binding (PostgreSQL):** your app asks Dapr to run SQL against Postgres. It uses `exec` for INSERT and DELETE and `query` for SELECT.

The PostgreSQL binding only works as an output binding, which is why cron supplies the input side.

In Instruqt the sandbox setup script prepares everything below for you. Use this guide to run the demos on your own machine.

## Prerequisites

- [Dapr CLI](https://docs.dapr.io/getting-started/install-dapr-cli/) 1.19.1 and a completed `dapr init --runtime-version 1.19.1` (Docker required)
- Docker, for the PostgreSQL container (Demos 2 to 4)
- `lsof`, which the smoke-test scripts use to stop the demo apps
- The runtime for the language you want to run: .NET SDK 10, Python 3.12 with [uv](https://docs.astral.sh/uv/), or Java 17 with Maven (the Java demos use Spring Boot 4.0.8)

The shell commands below assume a POSIX shell (Git Bash, WSL, macOS or Linux) with `python3` available. The track itself runs on a Linux sandbox.

Every demo uses the same app IDs and ports in every language, so run one demo at a time:

| App | App port | Dapr HTTP port |
|---|---|---|
| `engineering` | 5201 | 3520 |
| `subspace-beacon` (Demo 4 only) | 5202 | 3521 |

## Start Postgres (Demos 2 to 4)

Demo 1 needs no database. For the others:

```bash
# Removing any existing container first makes this block safe to run again.
docker rm -f bindings-postgres >/dev/null 2>&1 || true
# Bound to 127.0.0.1 only, so the demo credentials are not exposed. The init script in
# bindings/sql creates the tables on first start. Run this from the repository root.
docker run -d --name bindings-postgres -p 127.0.0.1:5432:5432 \
  -e POSTGRES_USER=dapr -e POSTGRES_PASSWORD=dapr -e POSTGRES_DB=dapr \
  -v "$PWD/bindings/sql:/docker-entrypoint-initdb.d:ro" \
  postgres:18.7
# The init script runs after the first "ready", so wait for the table, not just pg_isready.
for _ in $(seq 1 60); do
  docker exec bindings-postgres psql -U dapr -d dapr -tAc 'SELECT 1 FROM comms_log' >/dev/null 2>&1 && break
  sleep 1
done
```

`bash tests/bindings/start-postgres.sh` does the same and prints when the database is ready. Stop it afterwards with `docker rm -f bindings-postgres`.

Open a SQL shell with:

```bash
docker exec -it bindings-postgres psql -U dapr -d dapr
```

The user, password and database are all `dapr`. The two tables the demos use are defined in `bindings/sql/init.sql`.

## The demos

The apps never mention PostgreSQL. They call a component by name: `ship-db`, defined once per language in `<lang>/resources/ship-db.yaml`. Each demo adds its own cron components (and in Demo 3 a state store) in its own `resources/` folder, and its `dapr.yaml` loads both folders with `resourcesPaths`. Every binding component sets `metadata.direction` (`input` or `output`) explicitly, so you can see which way it runs.

| Challenge | .NET folder | Python and Java folder | What it shows |
|---|---|---|---|
| 1 | `Demo1-CronTrigger` | `demo1-cron-trigger` | A `bindings.cron` component calls `POST /warp-core-scan` every 10 seconds. The schedule is in YAML and the binding's name is the route. No Postgres. |
| 2 | `Demo2-PostgresOutput` | `demo2-postgres-output` | The output binding in both directions: each tick stores a reading with `exec`, `GET /readings` reads them with `query`, and a second cron binding purges old rows. |
| 3 | `Demo3-StateVsBinding` | `demo3-state-vs-binding` | Each reading is saved twice into the same database: through the State API and through the binding. Two tables to compare in `psql`. |
| 4 | `Demo4-SubspaceBeacon` | `demo4-subspace-beacon` | Input binding, service invocation and output binding in one flow: a cron tick makes `engineering` call `subspace-beacon` and log the answer in Postgres. |

Folder names follow each language's conventions: .NET uses PascalCase (`Demo1-CronTrigger/Engineering`), Python and Java use kebab-case (`demo1-cron-trigger/engineering`). Apps are called `engineering` and `subspace-beacon` in Python and Java, and `Engineering` and `SubspaceBeacon` in .NET.

Every demo runs the same way. Pick the folder for your language and the demo you want, for example Demo 1:

```bash
cd bindings/dotnet/Demo1-CronTrigger   # Python: bindings/python/demo1-cron-trigger, Java: bindings/java/demo1-cron-trigger
dapr run -f .
```

Stop it with Ctrl+C. Run the `curl` commands in a second terminal. The first run of a Java demo is slow while Maven downloads dependencies.

Demos 2, 3 and 4 clear their own table at startup (`warp_core_readings` in Demos 2 and 3, `comms_log` in Demo 4) with one `exec` through `ship-db`, and log `engineering cleared <table> for a fresh run`. All demos and languages share one Postgres container, so without this, rows from earlier runs would leak into your results. If Postgres is down the app logs the error and keeps running. The `state` table in Demo 3 is not cleared: its keys are simply overwritten.

A warp-core reading looks the same in every language:

```json
{ "readingId": "wc-0007", "stardate": 78412.6, "coreTempK": 912, "plasmaFlow": 0.87 }
```

`readingId` is a per-process counter (`wc-0001`, `wc-0002`, ...), `coreTempK` is a random integer from 850 to 950, and `plasmaFlow` a random number from 0.70 to 1.00. The values and stardates in the expected output below come from a real run and will differ in yours.

### Demo 1: cron trigger

No Postgres needed. Run the demo and wait. Ten seconds after the app starts, and then every ten seconds, `engineering` logs:

```text
engineering warp-core scan wc-0001 stardate=85737.4 coreTempK=911 plasmaFlow=0.76
engineering warp-core scan wc-0002 stardate=85737.4 coreTempK=902 plasmaFlow=0.95
```

There is no timer in the app. `resources/warp-core-scan.yaml` is a `bindings.cron` component with `schedule: "@every 10s"`, and the sidecar sends an empty `POST /warp-core-scan` to the app on every tick. Three things to try:

- **The route is the component name.** The component is called `warp-core-scan`, so the app serves `POST /warp-core-scan`. There is no Dapr attribute, decorator or SDK call in any of the three languages. The sidecar sends no `OPTIONS` probe first; the first request is the first tick.
- **The schedule lives in YAML.** Change `@every 10s` to `@every 3s`, restart, and the scans come faster with no code change.
- **A failing handler is not retried.** If the handler answers `500`, Dapr does not redeliver that tick and does not move the schedule: the next tick arrives on time. At its default log level the sidecar logs nothing about it either, so the failure only shows in the app's own log.

### Demo 2: PostgreSQL output binding

Start Postgres first. Every 10 seconds `engineering` creates a reading and stores it with an `exec` through `ship-db`:

```text
engineering cleared warp_core_readings for a fresh run
engineering warp-core scan wc-0001 stardate=85737.4 coreTempK=911 plasmaFlow=0.76
engineering stored reading wc-0001 in warp_core_readings
engineering warp-core scan wc-0002 stardate=85737.4 coreTempK=902 plasmaFlow=0.95
engineering stored reading wc-0002 in warp_core_readings
```

Read the readings back. This is the `query` operation, with the SQL in the app:

```bash
curl -s "http://localhost:5201/readings?minTemp=900"
```

```json
[{"readingId":"wc-0004","stardate":85737.4,"coreTempK":922,"plasmaFlow":0.92,"recordedAt":"2026-11-19T09:25:49Z"},{"readingId":"wc-0003","stardate":85737.4,"coreTempK":919,"plasmaFlow":0.94,"recordedAt":"2026-11-19T09:25:39Z"},{"readingId":"wc-0001","stardate":85737.4,"coreTempK":911,"plasmaFlow":0.76,"recordedAt":"2026-11-19T09:25:19Z"}]
```

The rows are the newest first, at most 20. Only readings with `coreTempK` of at least `minTemp` are returned, so the list can be empty early on. `minTemp` defaults to 0, and a value that is not an integer answers `400 {"error": "INVALID_MIN_TEMP"}`.

A second cron component, `purge-old-readings` (`@every 30s`), runs `DELETE FROM warp_core_readings WHERE recorded_at < now() - interval '1 minute'` with `exec` and logs:

```text
engineering purged old readings
```

The line has no row count. The `exec` response does carry a `rows-affected` value in its metadata, and the .NET and Python SDKs expose it, but the Java SDK does not, so every language logs the same line.

Watch rows come and go in `psql`:

```bash
docker exec -it bindings-postgres psql -U dapr -d dapr
```

```sql
SELECT * FROM warp_core_readings;
```

```text
 reading_id | stardate | core_temp_k | plasma_flow |          recorded_at
------------+----------+-------------+-------------+-------------------------------
 wc-0001    |  85737.4 |         911 |        0.76 | 2026-11-19 09:25:19.779282+00
 wc-0002    |  85737.4 |         902 |        0.95 | 2026-11-19 09:25:29.733568+00
 wc-0003    |  85737.4 |         919 |        0.94 | 2026-11-19 09:25:39.772748+00
```

Run it again after a minute and the oldest rows are gone.

**What a `query` returns.** The binding answers `query` with an array of arrays: one inner array per row, with the values in `SELECT` order and no column names. The apps map the values by position. For one reading:

```json
[["wc-9999",78000.5,901,0.88,"2026-11-19T07:44:40Z"]]
```

The SQL casts `stardate` and `plasma_flow` to `float8` and formats `recorded_at` as text, so every value is a plain JSON string or number. The SQL and its values travel as request metadata: `metadata.sql` holds the statement with `$1`-style placeholders, and `metadata.params` holds the values as a JSON array encoded as a string, for example `"[900]"`.

### Demo 3: State store vs binding

Start Postgres first. Each tick writes the same reading twice and logs both:

```text
engineering cleared warp_core_readings for a fresh run
engineering warp-core scan wc-0001 stardate=85737.4 coreTempK=875 plasmaFlow=0.87
engineering saved reading wc-0001 to statestore (key=reading-wc-0001)
engineering stored reading wc-0001 in warp_core_readings
```

Read it back through each API:

```bash
curl -s http://localhost:5201/state/wc-0001          # State API: get by key
curl -s "http://localhost:5201/readings?minTemp=900" # Binding: your own SQL
```

```json
{"readingId":"wc-0001","stardate":85737.4,"coreTempK":875,"plasmaFlow":0.87}
```

`/state/<readingId>` answers `404 {"error": "NOT_FOUND"}` for a reading that was never saved. `/readings` works as in Demo 2 (it returns `[]` here, because 875 is below 900).

Now compare the two tables in `psql`:

```sql
\d state
\d warp_core_readings
SELECT key, value FROM state LIMIT 2;
```

```text
                                      Table "public.state"
   Column   |           Type           | Collation | Nullable |             Default
------------+--------------------------+-----------+----------+----------------------------------
 key        | text                     |           | not null |
 value      | jsonb                    |           | not null |
 isbinary   | boolean                  |           | not null |
 insertdate | timestamp with time zone |           | not null | now()
 updatedate | timestamp with time zone |           |          |
 expiredate | timestamp with time zone |           |          |
 row_id     | bigint                   |           | not null | generated by default as identity
```

```text
             key              |                                        value
------------------------------+-------------------------------------------------------------------------------------
 engineering||reading-wc-0001 | {"stardate": 85737.4, "coreTempK": 875, "readingId": "wc-0001", "plasmaFlow": 0.87}
```

Dapr created the `state` table and prefixes every key with the app ID (`engineering||`). `warp_core_readings` is yours: you chose its columns in `bindings/sql/init.sql`. The component is `state.postgresql` (version `v1`) pointing at the same database as `ship-db`.

#### State store vs binding

| | State API (`statestore`) | Binding (`ship-db`) |
|---|---|---|
| Who owns the table | Dapr: `state` with key, JSON value and timestamps (the ETag is Postgres's hidden `xmin` column, so `\d state` does not list it) | You: your own schema |
| What you write | A key and a value | SQL |
| What you can do | Get, set and delete by key, plus ETags (concurrency), TTL and transactions | Filter, sort and bulk-delete with any SQL |
| Portability | Works the same across 30+ stores: swap the component, keep the code | Tied to Postgres: swapping the component will not work |

Use the State API when you want key-value storage that stays portable. Use the binding when you want the full power of SQL and accept the tie to Postgres. "All readings above 900 K" is a one-line `WHERE` with the binding, and not something the State API does by key. The State API reads by key (one or in bulk). Filtering on values needs the alpha State Query API, which this track does not use.

### Demo 4: Subspace beacon

Start Postgres first. This demo runs two apps, so `dapr run -f .` starts two sidecars. `subspace-beacon` is a plain HTTP app with no Dapr SDK. It answers `GET /ping`, with a signal that firms up on each call: 12, 27, 45, 63, 81, 94, and then 94 from there on. Restarting the beacon restarts the sequence.

```bash
curl -s http://localhost:5202/ping
```

```json
{"beaconId":"relay-theta-9","signalStrength":94,"message":"channel open","stardate":85737.5}
```

`message` is `static` below 40, `signal acquired` from 40 to 79, and `channel open` from 80. (Calling the beacon yourself, as above, advances its sequence too.)

Every 5 seconds the `beacon-ping` cron component (scoped to `engineering` with `scopes`, so the beacon's sidecar does not load it) calls `engineering`, which does three things:

1. Calls `subspace-beacon` through service invocation, by app ID: .NET `DaprClient.CreateInvokeHttpClient("subspace-beacon")`, Python `invoke_method`, Java a Spring `RestClient` that calls its own sidecar with a `dapr-app-id: subspace-beacon` header. There is no host or port of the beacon in the code.
2. Inserts the answer into `comms_log` through `ship-db`.
3. Logs it:

```text
engineering cleared comms_log for a fresh run
engineering pinged relay-theta-9 signalStrength=12 message="static"
engineering pinged relay-theta-9 signalStrength=27 message="static"
engineering pinged relay-theta-9 signalStrength=45 message="signal acquired"
engineering pinged relay-theta-9 signalStrength=63 message="signal acquired"
engineering pinged relay-theta-9 signalStrength=81 message="channel open"
engineering pinged relay-theta-9 signalStrength=94 message="channel open"
```

If the beacon is unreachable, for example while it is still starting, `engineering` logs `engineering beacon unreachable`, stores nothing and still answers `200`. An unreachable beacon is expected while it starts, and a `500` would change nothing because cron ticks are never retried.

Ask `engineering` how communications are going:

```bash
curl -s http://localhost:5201/comms/status
```

Right after startup:

```json
{"status":"SEARCHING","lastSignalStrength":12}
```

About 30 seconds later, once the last three pings all have a signal of 40 or more:

```json
{"status":"ESTABLISHED","lastSignalStrength":94}
```

With no pings stored yet, `lastSignalStrength` is `null`. The pings are in Postgres:

```sql
SELECT * FROM comms_log;
```

```text
 id |   beacon_id   | signal_strength |     message     | stardate |           pinged_at
----+---------------+-----------------+-----------------+----------+-------------------------------
 25 | relay-theta-9 |              12 | static          |  85737.4 | 2026-11-19 09:26:50.091192+00
 26 | relay-theta-9 |              27 | static          |  85737.4 | 2026-11-19 09:26:55.014208+00
 27 | relay-theta-9 |              45 | signal acquired |  85737.4 | 2026-11-19 09:27:00.028696+00
```

The `id` keeps counting up across runs (the startup clear deletes rows but does not reset the sequence), so yours may start lower or higher.

## Resilience note: when the cron handler fails

A cron tick is fire-and-forget. If your handler answers non-2xx, the sidecar does not retry that tick, the schedule does not shift, and daprd logs nothing at the default level. This was checked by making the Demo 1 handler return `500`: the app saw exactly one request per tick and no extras. That is why the Postgres handlers in Demos 2 to 4 log their own errors (`engineering binding call failed: ...`), and why Demo 4 logs an unreachable beacon and answers `200`: a `500` would change nothing.

## Smoke tests

`tests/bindings` holds one script per demo. They start the demo, check the logs, endpoints and Postgres rows, and stop it again:

```bash
bash tests/bindings/start-postgres.sh
bash tests/bindings/run-all.sh                  # all 12 combinations, Java is slow
bash tests/bindings/run-all.sh --demo 2 --lang python
```
