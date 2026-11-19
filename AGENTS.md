# AGENTS.md

Guidance for coding agents working in this repository.

## What this repo is

This repo holds the sample code for the Dapr University tracks that run on Instruqt. It contains only the demo apps, their Dapr resources, READMEs and smoke tests. The Instruqt assignments, challenge text and sandbox setup scripts live in another repo. Don't add them here.

Learners read this code, so clarity matters more than cleverness. Every demo must be easy to follow, must run with one command, and must behave the same in every language it ships in.

## Layout

| Folder | What it holds |
|---|---|
| `dapr-101/` | The introductory track: service invocation and pub/sub per language, plus a sidecar-only state management lab |
| `secrets/`, `pubsub/`, `bindings/` | Building-block deep-dive tracks, each in .NET, Python and Java |
| `deepagents/`, `langgraph/`, `MAF/` | AI agent tracks: one app per framework, made durable with Dapr Workflow |
| `tests/<track>/` | Smoke tests for the building-block tracks (`run-all.sh`, `smoke-demoN.sh`, `lib.sh`, and a script that starts the track's container) |
| `docs/superpowers/` | Design specs, implementation plans and research notes per track |
| `data/` | Pre-baked GitHub issue and PR snapshots used by the agent tracks |

**`pubsub/` and `bindings/` are the reference tracks.** They are the most recent and most consistent. When you add a track or a demo, copy their structure, naming and idioms. Don't copy the older tracks: `secrets/` still targets Dapr 1.18. Don't upgrade an older track unless you're asked to.

## Structure of a building-block track

```text
<track>/
  README.md                    # prerequisites, ports, how to run each demo, what to look at
  sql/ or other shared files   # only when the track needs them (bindings/sql/init.sql)
  dotnet/
    resources/                 # components shared by every .NET demo of this track
    Demo1-CronTrigger/
      dapr.yaml                # multi-app run file
      resources/               # components and subscriptions for this demo only
      Engineering/             # one folder per app
  python/
    resources/
    demo1-cron-trigger/
      dapr.yaml
      resources/
      engineering/
  java/
    resources/
    demo1-cron-trigger/
      dapr.yaml
      resources/
      engineering/
```

- **Folder names follow each language's conventions.** .NET uses PascalCase (`Demo1-CronTrigger/Engineering`). Python and Java use kebab-case (`demo1-cron-trigger/engineering`), and their app folder names are the app IDs.
- **The languages match.** The same demo in each language has the same app IDs, app ports, Dapr HTTP ports, component names, endpoints, JSON contract (keys, key order, error bodies) and log lines. The README is written once for all three languages, and the smoke tests assert on these values.
- **Ports.** Each track has its own range, and one demo runs at a time. Pub/sub apps use 5101–5103 with Dapr HTTP ports 3510–3512. Bindings apps use 5201–5202 with 3520–3521. A new track takes the next block (53xx and 353x).
- **Components.** Components shared by every demo in a language go in `<lang>/resources/`. A demo's own components and subscriptions go in `<demo>/resources/`. Apps only use a component's name, such as `pubsub` or `ship-db`, and never the technology behind it. That keeps the swap-the-provider demos honest.
- **A theme.** Each track tells a small story with fictional names, for example orders in pub/sub and a starship's engineering deck in bindings. Keep the names fictional. Don't use trademarked characters or ships.
- **Order of work.** A new track starts with a spec in `docs/superpowers/specs/` and a plan in `docs/superpowers/plans/`. The README and smoke tests are part of the track, not extras.

## Multi-app run files (`dapr.yaml`)

Every demo has a `dapr.yaml` in its demo folder, and runs with `dapr run -f .` from that folder.

```yaml
version: 1
common:
  resourcesPaths:
    - ../resources   # shared by this language's demos
    - ./resources    # this demo's own
apps:
  - appID: engineering
    appDirPath: ./engineering
    appPort: 5201
    daprHTTPPort: 3520
    command: ["uv", "run", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "5201"]
```

- **Don't set `appLogDestination` or `daprdLogDestination`.** By default the app and sidecar logs are written to `<appDirPath>/.dapr/logs`, and the app log is also printed to the console. The Dapr Dev Dashboard and the smoke tests both read those log files. `.dapr/` is git-ignored per track.
- Set `daprHTTPPort` explicitly, because the README's `curl` commands and the smoke tests use it.
- An app that only calls its sidecar, such as a streaming subscriber or a one-shot agent, has no `appPort`.
- The command per language: .NET `["dotnet", "run", "--urls", "http://localhost:<port>"]`, Python `["uv", "run", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "<port>"]` (or `["uv", "run", "python", "<script>.py"]` for a script), Java `["mvn", "-q", "spring-boot:run"]` with `server.port` set in `application.properties`.
- `MAF/PrDigest` is a .NET Aspire app, and its AppHost starts the sidecars, so it has no `dapr.yaml`. `langgraph/supply_chain_auditor/supply-chain-auditor-langgraph.yaml` is a Diagrid Catalyst file for `diagrid dev run`. The local Dapr run file next to it is `dapr.yaml`.

## Versions

- **Dapr:** CLI and runtime 1.19.1.
- **.NET:** SDK 10, with `net10.0` minimal APIs. Packages `Dapr.Client` / `Dapr.AspNetCore` / `Dapr.Messaging` 1.19.1.
- **Python:** 3.12+ with [uv]. Each app has its own `pyproject.toml` and `uv.lock`. Pin the Dapr SDK exactly: `dapr==1.19.0`.
- **Java:** 17 with Maven and Spring Boot 4.0.8. Use the `spring-boot-starter-webmvc` starter, plus `spring-boot-starter-restclient` when the app uses a `RestClient`. Jackson 3 (`tools.jackson.*`), `io.dapr:dapr-sdk` 1.19.0, and the package `io.diagrid.university.<track>.<app>`.
- **Other packages:** pin exact versions, such as `cloudevents==2.2.0` and `CloudNative.CloudEvents` 2.9.0.

[uv]: https://docs.astral.sh/uv/

## Idiomatic code per language

Write each language the way a developer of that language would, not as a translation of another language. The behaviour must match across languages; the shape of the code doesn't have to. Use the current SDK APIs: the obsolete and deprecated invoke APIs were replaced on purpose (see `bindings/` Demo 4).

### .NET

- Use minimal APIs in `Program.cs`, with the domain types in their own files (`ShipDb.cs`, `WarpCoreReading.cs`).
- Register one `DaprClient` as a singleton: `builder.Services.AddSingleton(new DaprClientBuilder().Build())`. Register helpers such as `ShipDb` with DI, and inject them into the handlers.
- Return `TypedResults` (`TypedResults.Ok(...)`, `TypedResults.Json(..., statusCode: 500)`) from typed handler lambdas.
- Do startup work in an `IHostedService`.
- Log with `ILogger<T>` and message templates.
- Use records for contracts, and `System.Text.Json` with camelCase.
- Call other apps through `DaprClient.CreateInvokeHttpClient("<app-id>")`.

### Python (`pubsub/python` and `bindings/python` are the examples)

- Use FastAPI under uvicorn, with async endpoints.
- Use the async Dapr client, `dapr.aio.clients.DaprClient`. Open it once in a `lifespan` context manager with `async with DaprClient() as client:`, and do startup work there, before `yield`, so no request can race it. Store it on `app.state`.
- Hand the client and helpers to endpoints through `Depends`, with `Annotated` aliases such as `ShipDbDep = Annotated[ShipDb, Depends(get_ship_db)]`. Don't use globals.
- Use Pydantic models for contracts, with snake_case fields and camelCase JSON (`ConfigDict(alias_generator=to_camel, validate_by_name=True)`). Set `response_model=` on endpoints. A `TypedDict` is fine for a plain JSON body you match with `match`.
- **Errors:** register one `@app.exception_handler(grpc.RpcError)` that turns any failed Dapr call into the track's error body, so endpoints only describe the happy path.
  - Catch `grpc.RpcError`, not `DaprGrpcError`. The async client's `invoke_binding` raises a raw `grpc.aio.AioRpcError`.
  - `save_state` can also raise `DaprInternalError`.
- Log with `logging.getLogger("<app-id>")` and `%`-style arguments.
- Use type hints everywhere and `collections.abc` types.

### Java (`pubsub/java` and `bindings/java` are the examples)

- Use Spring Boot with `@RestController` classes, constructor injection, and package-private classes where possible.
- Declare one `DaprClient` `@Bean` in the `*Application` class. It is `AutoCloseable`, so Spring closes it.
- Use records for request and response bodies. Their component order is the JSON key order.
- Controllers return concrete types such as `List<ReadingRow>` or `void` for a cron trigger. They don't return `ResponseEntity` and don't use try/catch for API errors.
- Map exceptions to responses in one `@RestControllerAdvice` class (`ApiErrors`): use `@ExceptionHandler` with `@ResponseStatus` for `DaprException` and the domain exceptions.
- Block on the SDK's Mono with `.block()` inside controllers. This keeps the servlet stack simple to read.
- For startup work, use an `@EventListener(ApplicationReadyEvent.class)` that waits for the sidecar first with `daprClient.waitForSidecar(...)`.
- Inject configuration such as the Dapr HTTP port with `@Value("${DAPR_HTTP_PORT:3520}")`.
- Log with SLF4J.

### All languages

- **No Dapr code where Dapr doesn't need it.** An input binding target or a declarative subscriber is a plain HTTP endpoint, and a CloudEvent is read with the open CloudEvents SDK. Point this out in a comment, because it is part of the lesson.
- **Comments explain the Dapr concept on the line where it happens:** what the sidecar does, why the status code matters, what the component name stands for. Write for a learner. Don't narrate obvious code.
- **Fail visibly:**
  - Return the agreed error body, such as `{"error": "BINDING_FAILED"}` or `{"error": "INVALID_ORDER"}`, with a fitting status.
  - Log the warning line the README documents.
  - Choose status codes on purpose. Dapr retries on non-2xx, so a cron tick or an unreadable message answers 200 or `DROP` when a retry can't help.
- **Validate input the same way everywhere** (same rules, same limits). Use parameter placeholders such as `$1` in SQL, never string concatenation.
- **Stateful demos start clean.** An app that writes to a store clears its own data on startup, so earlier runs, or other languages, don't leak in.

## Verifying changes

- Start the track's backing service if it has one: `bash tests/bindings/start-postgres.sh` or `bash tests/pubsub/start-rabbitmq.sh`.
- Run the smoke tests:
  - All demos: `bash tests/<track>/run-all.sh`
  - One demo or language: `bash tests/<track>/run-all.sh --demo 2 --lang python`
- Run the tests for every language you touched. A change to a shared contract (ports, log lines, JSON, error bodies) touches all three.
- The smoke tests start each demo with `dapr run -f`, so they also exercise the run file.
- Failure paths aren't covered by the smoke tests. Check them by hand, for example by stopping the backing container, and note the result in the PR.
- The agent tracks have their own READMEs, `RUNBOOK.md` and tests, and need an OpenAI key.

## Conventions for docs and commits

- **Each track README** covers prerequisites, a port table, a demo table, then one section per demo with the exact `curl` commands, expected output and log lines.
- **Commit messages:** Conventional Commits scoped to the track, such as `feat(bindings): ...`, `fix(pubsub): ...` or `docs(bindings): ...`.
- **Secrets:** never commit them. Templates are `*.example.json`, and the real files are git-ignored. The local connection strings in demo components are marked as local-only in a comment.
