# Dapr Pub/Sub Deep-Dive Demos Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `pubsub/` with six Dapr pub/sub demos in .NET, Python and Java that behave identically, plus a smoke-test harness that proves each one.

**Architecture:** Each language folder has a shared Redis `pubsub` component in `resources/` and six `DemoN-*` folders. Each demo is run with `dapr run -f .` and loads `../resources` plus its own `./resources` (subscriptions, resiliency). Demo 6 has no code: it points at the Demo 5 apps with a RabbitMQ `pubsub` component. A bash smoke script per demo starts it, drives it with `curl`, asserts on the app logs, and stops it. That script is the failing test written before each demo.

**Tech Stack:** Dapr 1.19.1 runtime and CLI; .NET 10 minimal APIs; Python 3.12 + FastAPI + uv; Java 17 + Spring Boot 4 + Maven; Redis (from `dapr init`); RabbitMQ in Docker; bash + curl + python3 for the smoke tests.

**Spec:** `docs/superpowers/specs/2026-11-11-dapr-pubsub-deep-dive-demos-design.md`

## Global Constraints

- Dapr runtime **1.19.1**, CLI **1.19.1** (`dapr init --runtime-version 1.19.1`; this machine has runtime 1.19.0, so upgrade it in Task 1).
- .NET: `Dapr.Client`, `Dapr.AspNetCore`, `Dapr.Messaging` **1.19.1**, `net10.0`.
- Python: `dapr[fastapi]==1.19.0`. **Not** `dapr-ext-fastapi`: from 1.19 the FastAPI extension ships as an extra of `dapr` (the standalone package stops at 1.18.3). Import stays `from dapr.ext.fastapi import DaprApp`. This corrects spec §6.
- Java: `io.dapr:dapr-sdk` and `io.dapr:dapr-sdk-springboot` **1.19.0**, Java 17, `spring-boot-starter-parent` **4.0.x** (the 1.19 Java SDK is built against Spring Boot 4.0.8; the secrets demos' 3.4.5 is not used here). Verify in Task 1.
- Do not change anything under `secrets/`.
- Do not copy code from `diagrid-labs/dapr-pub-sub-deep-dive`.
- Component name `pubsub`. Topics `orders`, `orders-raw`, `orders-dead`.
- App folder names are identical in every language: `OrderApi`, `Shipping`, `Invoicing`, `Warehouse`.
- Ports, identical in every language: `order-api` app **5101**, Dapr HTTP **3510**; the second app **5102**, Dapr HTTP **3511**; the third app **5103**, Dapr HTTP **3512**. `warehouse` has no app port, Dapr HTTP **3511**.
- Every `dapr.yaml` (Demos 1–5) uses `common.resourcesPaths: [../resources, ./resources]`.
- Payload `Order`: `{"orderId": str, "item": str, "quantity": int, "priority": "standard"|"express"}`, keys in that order.
- Comments in code explain the Dapr concept at the line where it happens, in the voice of `secrets/*/Demo1-ReadSecret`.
- Subscriber handlers are written against the HTTP contract (read the raw JSON body), except where a task says to use an SDK surface (Demo 1 `invoicing`, Demo 2 `warehouse`, publishers).

## Shared contracts (all languages)

**Publisher `order-api`, port 5101.** Same in every demo that has the endpoint:

| Endpoint | Demos | Behaviour | Response |
|---|---|---|---|
| `POST /orders` (body: `Order`) | 1, 2, 3, 5 | Publish to `orders` | `200 {"orderId": "<id>", "topic": "orders"}` |
| `POST /orders/raw` (body: `Order`) | 3 | Publish to `orders-raw` with publish metadata `rawPayload: "true"` | `200 {"orderId": "<id>", "topic": "orders-raw"}` |
| `POST /orders/bulk?count=N&prefix=P` | 4 | Build N orders `P-1`…`P-N` (`item` `coffee-beans`, `quantity` 1, `priority` `standard`) and bulk-publish them to `orders` in one call | `200 {"sent": N, "failed": <failed entries count>}` |

- Body missing any `Order` field, a field of the wrong JSON type, not JSON, not an object, or a valid JSON value followed by more non-whitespace content (`{...} x`): `400 {"error": "INVALID_ORDER"}`, nothing published.
- `count`: surrounding whitespace is stripped, then it must be ASCII digits only (`^[0-9]+$`) and 1..100. Missing, empty, `+5`, `1_0`, `1.5`, `abc`, `0` or `101`: `400 {"error": "INVALID_COUNT"}`. ` 5` is a valid 5.
- Published orders are serialized as compact JSON (no spaces) in every language.
- Dapr rejects the publish: `500 {"orderId": "<id>", "error": "<gRPC status name>"}`. Each language reads the gRPC status from the exception: .NET converts the `RpcException`'s `StatusCode` with a regex (`NotFound` → `NOT_FOUND`), Python uses `code().name`, and Java walks the `DaprException`'s cause chain to the `StatusRuntimeException` and uses `getStatus().getCode().name()`, with `INTERNAL` if there is none.
- Publisher logs `order-api published <orderId> to <topic>` per order (bulk: `order-api bulk published <N> orders to orders, <F> failed`).

**Subscriber log lines** (the smoke tests grep these; exact text, `<id>` is `data.orderId`):

| Demo | App | Line |
|---|---|---|
| 1 | shipping | `shipping received order <id>` |
| 1 | invoicing | `invoicing received order <id>` |
| 2 | warehouse | `warehouse received order <id>` |
| 3 | shipping | `shipping received with envelope: <raw request body>` and `shipping received raw: <raw request body>` |
| 4 | shipping | `shipping received batch of <n> orders: <id>,<id>,...` |
| 5/6 | shipping | `shipping express order <id>`, `shipping standard order <id>`, `shipping rejected order <id>`, `shipping dead-lettered order <id>` |
| 1, 5/6 | shipping | `shipping dropped unreadable event` |
| 4 | shipping | `shipping dropped unreadable entry <entryId>` |
| 2 | warehouse | `warehouse dropped unreadable event` |

Log levels: `shipping dropped unreadable event`, `shipping dropped unreadable entry <id>`, `shipping rejected order <id>` and `warehouse dropped unreadable event` are WARNING; every other line is INFO.

HTTP subscriber handlers (declarative, and Demo 1 `invoicing`) return `200 {"status": "SUCCESS"}`; the Demo 5 rejection returns `500 {"status": "RETRY"}`. A declarative handler that cannot read an event (empty body, not JSON, root not an object, no string `data.orderId`) returns `200 {"status": "DROP"}` and logs `shipping dropped unreadable event` (Demos 1 and 5; Demo 4 drops per entry). Dapr retries any non-2xx except 404, and an unreadable event never parses on a redelivery. Demo 1 `invoicing` leaves unreadable events to its SDK. Demo 2 `warehouse` logs `warehouse dropped unreadable event` for a message whose data is not an object with a string `orderId`, and still acknowledges it as success.

## Review Focus

1. **A leaked process from an earlier run still holds 5101 or 3510.** Expected: the smoke test fails at once saying which port is busy, not later with a confusing error. Pinned by `assert_ports_free` in Task 1, called first by every smoke script.
2. **Messages left in Redis from an earlier run** (consumer groups replay pending and undelivered messages on restart). Expected: a rerun still passes and isn't confused by old orders. Pinned by every smoke script using a run-unique order id prefix (`run_id` in Task 1) and asserting only on its own ids.
3. **A malformed order posted to the publisher.** Expected: `400 INVALID_ORDER` and nothing published. Pinned in Task 2's smoke test.
4. **Bulk count out of range or not plain digits (0, 101, missing, `+5`, `1_0`, `1.5`, `abc`).** Expected: `400 INVALID_COUNT`; ` 5` is accepted. Pinned in Task 5's smoke test.
5. **Demo 6 started without RabbitMQ running.** Expected: the smoke test stops before `dapr run` with "RabbitMQ is not running; start it first (see pubsub/README.md)". Pinned in Task 7's smoke test.

## File Structure

```
tests/pubsub/
  lib.sh                    shared helpers (Task 1)
  smoke-demo1.sh … smoke-demo6.sh   one per demo, arg: dotnet|python|java
  run-all.sh                every demo × every language
  start-rabbitmq.sh         start + wait for the RabbitMQ container (Task 7)
pubsub/
  README.md                 (Task 8)
  <lang>/resources/pubsub.yaml       Redis, name pubsub (Task 1)
  <lang>/Demo1-Subscriptions/        dapr.yaml, resources/, OrderApi/, Shipping/, Invoicing/
  <lang>/Demo2-Streaming/            dapr.yaml, OrderApi/, Warehouse/   (no resources/ folder)
  <lang>/Demo3-CloudEvents/          dapr.yaml, resources/, OrderApi/, Shipping/
  <lang>/Demo4-Bulk/                 dapr.yaml, resources/, OrderApi/, Shipping/
  <lang>/Demo5-RoutingDeadLetter/    dapr.yaml, resources/, OrderApi/, Shipping/
  <lang>/Demo6-SwapProvider/         dapr.yaml, resources/pubsub.yaml (RabbitMQ)
docs/superpowers/notes/2026-11-11-pubsub-risk-outcomes.md   spec §7 outcomes, appended per task
.gitignore                  add pubsub/**/target/ and pubsub/**/.dapr/
```

Project files per app: .NET `<App>/<App>.csproj` + `Program.cs`; Python `<App>/pyproject.toml` + `app.py`; Java `<App>/pom.xml` + `src/main/java/io/diagrid/university/pubsub/<app>/…` + `src/main/resources/application.properties` (`server.port`, `spring.application.name`).

`dapr.yaml` commands follow secrets: .NET `["dotnet", "run", "--urls", "http://localhost:<port>"]`; Python `["uv", "run", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "<port>"]`; Java `["mvn", "-q", "spring-boot:run"]`.

Demo 2 has no subscription files, so its `dapr.yaml` uses `resourcesPaths: [../resources]` only. This is the one exception to the global `resourcesPaths` rule.

---

### Task 1: Toolchain, shared component and smoke-test harness

**Files:**
- Create: `tests/pubsub/lib.sh`, `tests/pubsub/run-all.sh`
- Create: `pubsub/dotnet/resources/pubsub.yaml`, `pubsub/python/resources/pubsub.yaml`, `pubsub/java/resources/pubsub.yaml`
- Create: `docs/superpowers/notes/2026-11-11-pubsub-risk-outcomes.md`
- Modify: `.gitignore` (add the two `pubsub/**` lines next to the secrets entries)

**Interfaces:**
- Produces (`lib.sh`, sourced by every smoke script; all functions exit non-zero with a message on failure):
  - `ROOT` — repo root; `LANG_ARG` — validated first arg (`dotnet|python|java`, else usage error)
  - `run_id` — prints a run-unique prefix like `r1731340000`
  - `assert_ports_free <port>...` — fails "port <p> is already in use" if anything listens
  - `start_demo <demo-dir>` — `cd` there, `dapr run -f .` in the background, output to `<demo-dir>/.dapr/smoke-run.log`; registers `stop_demo` on `EXIT`
  - `stop_demo <demo-dir>` — `dapr stop -f .` from that folder, then kills the background job
  - `wait_for_sidecar <dapr-http-port> [timeout=180]` — polls `GET /v1.0/healthz` until 204
  - `app_log <app-dir> <app-id>` — prints the newest `<app-dir>/.dapr/logs/<app-id>_app_*.log`
  - `wait_for_log <app-dir> <app-id> <fixed-string> [timeout=60]` — waits until the app log contains the string
  - `count_log <app-dir> <app-id> <fixed-string>` — prints the number of matching lines
  - `post_json <url> <json>` — prints `<status> <body>`
  - `assert_eq <expected> <actual> <message>`
- Produces: `pubsub/<lang>/resources/pubsub.yaml`: `type: pubsub.redis`, `version: v1`, `redisHost: localhost:6379`, `redisPassword: ""`, `metadata.name: pubsub`, with a comment that this is the only file Demo 6 replaces.

- [ ] **Step 1: Pin and check the toolchain**

Run: `dapr uninstall && dapr init --runtime-version 1.19.1 && dapr --version`
Expected: `CLI version: 1.19.1`, `Runtime version: 1.19.1`.

Run: `curl -s https://repo1.maven.org/maven2/io/dapr/dapr-sdk-springboot/1.19.0/dapr-sdk-springboot-1.19.0.pom | grep -A1 spring-boot` and check which Spring Boot line the SDK expects. If it is not 4.0.x, use the line it does expect and update Global Constraints in this plan.

- [ ] **Step 2: Write `lib.sh` and a self-test**

Self-test: `bash -c 'source tests/pubsub/lib.sh python; assert_ports_free 5101 3510; run_id'` prints an id; `python3 -m http.server 5101 & sleep 1; bash -c 'source tests/pubsub/lib.sh python; assert_ports_free 5101'` exits non-zero with `port 5101 is already in use`; kill the server.

- [ ] **Step 3: Write `run-all.sh`**

Loops `for demo in 1 2 3 4 5 6; for lang in dotnet python java`, runs `tests/pubsub/smoke-demo$demo.sh $lang`, skips a missing script with `SKIP`, prints a `PASS`/`FAIL` table and exits non-zero if any failed. Accepts optional `--demo N` / `--lang L` filters.

- [ ] **Step 4: Create the three `resources/pubsub.yaml` files, the risk-outcomes note (headings for spec §7 risks 1–6, outcome "not yet verified"), and the `.gitignore` lines**

- [ ] **Step 5: Commit**

```bash
git add tests/pubsub pubsub/*/resources/pubsub.yaml docs/superpowers/notes/2026-11-11-pubsub-risk-outcomes.md .gitignore
git commit -m "test: add pub/sub smoke harness and shared Redis component"
```

---

### Task 2: Demo 1 — declarative vs programmatic

**Files:**
- Create: `tests/pubsub/smoke-demo1.sh`
- Create per language: `pubsub/<lang>/Demo1-Subscriptions/{dapr.yaml, resources/subscription-shipping.yaml, OrderApi/…, Shipping/…, Invoicing/…}`

**Interfaces:**
- Consumes: Task 1 `lib.sh`, `resources/pubsub.yaml`.
- Produces: the `OrderApi` publisher (`POST /orders`, per Shared contracts). Tasks 3 and 6 copy it unchanged into their demo folders. Task 4 copies it and adds `/orders/raw`. Task 5 copies it and adds `/orders/bulk`.

Apps: `order-api` 5101/3510, `shipping` 5102/3511, `invoicing` 5103/3512.

`subscription-shipping.yaml`: `apiVersion: dapr.io/v2alpha1`, `kind: Subscription`, name `shipping-orders`, `pubsubname: pubsub`, `topic: orders`, `routes.default: /orders`, `scopes: [shipping]`.

`invoicing` subscribes from code to `pubsub`/`orders` on route `/orders`:
- .NET: `app.UseCloudEvents()`, `app.MapSubscribeHandler()`, `app.MapPost("/orders", …).WithTopic("pubsub", "orders")` (`Dapr.AspNetCore`).
- Python: `DaprApp(app).subscribe(pubsub="pubsub", topic="orders", route="/orders")`.
- Java: `@Topic(name = "orders", pubsubName = "pubsub")` on `@PostMapping("/orders")`, handler takes `CloudEvent<Order>` (`dapr-sdk-springboot`).

- [ ] **Step 1: Write `smoke-demo1.sh`**

Assertions, in order:
1. `assert_ports_free 5101 5102 5103 3510 3511 3512`
2. `start_demo`; `wait_for_sidecar` for 3510, 3511, 3512
3. `post_json http://localhost:5101/orders '{"orderId":"<run_id>-1","item":"coffee-beans","quantity":2,"priority":"standard"}'` → status `200`, body `{"orderId":"<run_id>-1","topic":"orders"}` (compare after `python3 -c` JSON round-trip, key order preserved)
4. `wait_for_log Shipping shipping "shipping received order <run_id>-1"` and `wait_for_log Invoicing invoicing "invoicing received order <run_id>-1"`
5. `GET http://localhost:3511/v1.0/metadata` → `subscriptions[]` has an entry with `topic == "orders"` and `type == "DECLARATIVE"`; `GET :3512/v1.0/metadata` → `type == "PROGRAMMATIC"` (Review Focus + spec §7 risk 6)
6. `post_json …/orders '{"orderId":"<run_id>-2"}'` → status `400`, body `{"error":"INVALID_ORDER"}`; after 3 s, `count_log Shipping shipping "<run_id>-2"` is `0` (Review Focus 3)

- [ ] **Step 2: Run it and see it fail**

Run: `bash tests/pubsub/smoke-demo1.sh dotnet`
Expected: FAIL (demo folder does not exist).

- [ ] **Step 3: Build the .NET demo** to the contracts above. Use `dapr-skills:create-pubsub-dotnet` as a reference for idiomatic 1.19 usage only (spec §7a).

- [ ] **Step 4: Run `bash tests/pubsub/smoke-demo1.sh dotnet`** → PASS. This is also the risk 5 check: `shipping` only gets its subscription if the CLI loaded both entries of `resourcesPaths` (component from `../resources`, subscription from `./resources`). If the CLI rejects the list, switch to the fallback for every demo: copy `pubsub.yaml` into each demo's `resources/` and use a single `resourcesPath: ./resources` (Demo 6 then copies the Demo 5 subscription and resiliency files, with a comment that they are identical copies, spec §3.6). Record the outcome under risk 5. If metadata reports different type names, record the real values under risk 6, stop, and report to the user (spec §7).

- [ ] **Step 5: Build the Python demo** (reference: `dapr-skills:create-pubsub-python`). **Run** `bash tests/pubsub/smoke-demo1.sh python` → PASS.

- [ ] **Step 6: Build the Java demo.** **Run** `bash tests/pubsub/smoke-demo1.sh java` → PASS.

- [ ] **Step 7: Record the risk 5 and risk 6 outcomes** in the risk note.

- [ ] **Step 8: Commit**

```bash
git add tests/pubsub/smoke-demo1.sh pubsub/*/Demo1-Subscriptions docs/superpowers/notes/2026-11-11-pubsub-risk-outcomes.md
git commit -m "feat: add pub/sub Demo1 declarative vs programmatic subscriptions"
```

---

### Task 3: Demo 2 — streaming subscription

**Files:**
- Create: `tests/pubsub/smoke-demo2.sh`
- Create per language: `pubsub/<lang>/Demo2-Streaming/{dapr.yaml, OrderApi/…, Warehouse/…}`

**Interfaces:**
- Consumes: Task 2 `OrderApi` (copied unchanged).

Apps: `order-api` 5101/3510; `warehouse` Dapr HTTP 3511, **no `appPort`** in `dapr.yaml`. No `Subscription` files; `resourcesPaths: [../resources]`.

`warehouse` streams `pubsub`/`orders`, logs the line, always reports success:
- .NET: `Dapr.Messaging`; `builder.Services.AddDaprPubSubClient()`; a `BackgroundService` calls `DaprPublishSubscribeClient.SubscribeAsync("pubsub", "orders", new DaprSubscriptionOptions(new MessageHandlingPolicy(TimeSpan.FromSeconds(10), TopicResponseAction.Retry)), handler)` and the handler returns `TopicResponseAction.Success`. Reference: `dotnet-sdk/examples/Messaging/02-Streaming` at `v1.19.1`. Generic host (`Host.CreateApplicationBuilder`), no web server.
- Python: `DaprClient().subscribe_with_handler(pubsub_name="pubsub", topic="orders", handler_fn=…)` returning `TopicEventResponse("success")`; a plain `python app.py` process kept alive until SIGTERM. `dapr.yaml` command `["uv", "run", "python", "app.py"]`.
- Java: `DaprPreviewClient.subscribeToTopic("pubsub", "orders", TypeRef.get(Order.class))` → `Flux<Order>`, subscribe and log; Spring Boot with `spring.main.web-application-type=none`, kept alive by the subscription.

- [ ] **Step 1: Write `smoke-demo2.sh`**

1. `assert_ports_free 5101 3510 3511`
2. `start_demo`; `wait_for_sidecar 3510`, `wait_for_sidecar 3511`
3. Wait until `GET :3511/v1.0/metadata` lists a subscription to `orders` with `type == "STREAMING"` (timeout 60 s; this is also how the test knows the stream is open before publishing)
4. `POST /orders` with id `<run_id>-1` → `200`
5. `wait_for_log Warehouse warehouse "warehouse received order <run_id>-1"`

- [ ] **Step 2: Run it** for `dotnet`; expect FAIL.
- [ ] **Step 3: Build .NET; run → PASS.**
- [ ] **Step 4: Build Python; run → PASS.**
- [ ] **Step 5: Build Java; run → PASS.** Record risk 1's outcome (Java happy path works; ack timing not exercised) in the risk note.
- [ ] **Step 6: Commit** — `git add tests/pubsub/smoke-demo2.sh pubsub/*/Demo2-Streaming docs/superpowers/notes/…` ; message `feat: add pub/sub Demo2 streaming subscription`.

---

### Task 4: Demo 3 — CloudEvents with and without

**Files:**
- Create: `tests/pubsub/smoke-demo3.sh`
- Create per language: `pubsub/<lang>/Demo3-CloudEvents/{dapr.yaml, resources/subscription-orders.yaml, resources/subscription-orders-raw.yaml, OrderApi/…, Shipping/…}`

**Interfaces:**
- Consumes: Task 2 `OrderApi`, plus a new `POST /orders/raw` (Shared contracts).

Apps: `order-api` 5101/3510, `shipping` 5102/3511.

- `subscription-orders.yaml`: topic `orders`, `routes.default: /orders`, `scopes: [shipping]`.
- `subscription-orders-raw.yaml`: topic `orders-raw`, `routes.default: /orders-raw`, `scopes: [shipping]`, **no `rawPayload` metadata** (user decision after risk 3, see spec §3.3), with a comment explaining what subscription-side `rawPayload` would do instead (wrap raw messages from non-Dapr producers into a CloudEvent with `data_base64`).
- `/orders/raw` publishes with metadata `rawPayload: "true"`:
  - .NET `PublishEventAsync("pubsub", "orders-raw", order, new Dictionary<string,string>{{"rawPayload","true"}})`
  - Python `publish_event(..., publish_metadata={"rawPayload": "true"}, data_content_type="application/json")`
  - Java `publishEvent("pubsub", "orders-raw", order, Map.of("rawPayload", "true"))`
- `shipping` reads the raw request body as a string and logs it as is on one line. No CloudEvents middleware on these routes (.NET: no `UseCloudEvents()`).

- [ ] **Step 1: Write `smoke-demo3.sh`**

1. Ports free (5101 5102 3510 3511); start; wait for both sidecars
2. `POST /orders` id `<run_id>-1` → `200 {"orderId":"<run_id>-1","topic":"orders"}`
3. Wait for log `shipping received with envelope: `; take the line containing `<run_id>-1`; parse the JSON after the prefix with `python3`; assert keys `id`, `source`, `type`, `specversion`, `datacontenttype`, `traceparent` exist, `specversion == "1.0"`, `data.orderId == "<run_id>-1"`
4. `POST /orders/raw` id `<run_id>-2` → `200 {"orderId":"<run_id>-2","topic":"orders-raw"}`
5. Wait for log `shipping received raw: `; parse the JSON on the `<run_id>-2` line; assert it equals the posted order exactly (`{"orderId","item","quantity","priority"}`) and has **no** `specversion` key

- [ ] **Step 2: Run** for `dotnet` → FAIL.
- [ ] **Step 3: Build .NET → PASS.** If the raw body arrives wrapped, base64-encoded or rejected, record it under risk 3, stop and report.
- [ ] **Step 4: Build Python → PASS.**
- [ ] **Step 5: Build Java → PASS.** Record risk 3's outcome.
- [ ] **Step 6: Commit** — message `feat: add pub/sub Demo3 CloudEvents with and without rawPayload`.

---

### Task 5: Demo 4 — bulk publish and bulk receive

**Files:**
- Create: `tests/pubsub/smoke-demo4.sh`
- Create per language: `pubsub/<lang>/Demo4-Bulk/{dapr.yaml, resources/subscription-bulk.yaml, OrderApi/…, Shipping/…}`

**Interfaces:**
- Consumes: Task 2 `OrderApi`, plus a new `POST /orders/bulk?count=N&prefix=P` (Shared contracts).

Apps: `order-api` 5101/3510, `shipping` 5102/3511.

- Bulk publish, one call, no per-entry metadata:
  - .NET `DaprClient.BulkPublishEventAsync("pubsub", "orders", orders)` → `FailedEntries.Count`
  - Python `DaprClient.publish_events(pubsub_name="pubsub", topic_name="orders", data=[json.dumps(o) for o in orders], data_content_type="application/json")` → `len(failed_entries)`
  - Java `DaprClient.publishEvents("pubsub", "orders", "application/json", orders)` → `getFailedEntries().size()`
- `subscription-bulk.yaml`: topic `orders`, `routes.default: /orders/bulk`, `bulkSubscribe: { enabled: true, maxMessagesCount: 10, maxAwaitDurationMs: 1000 }`, `scopes: [shipping]`.
- `shipping` `POST /orders/bulk` reads `entries[]`; for each entry, takes the order from `entries[i].event` (a CloudEvent object whose `data` is the order; handle the case where `event` is a JSON string by parsing it); logs one batch line; responds `200 {"statuses": [{"entryId": "<entryId>", "status": "SUCCESS"}, ...]}` in entry order.

- [ ] **Step 1: Write `smoke-demo4.sh`**

1. Ports free; start; wait for sidecars
2. `POST /orders/bulk?count=25&prefix=<run_id>` → `200 {"sent":25,"failed":0}`
3. Wait (timeout 30 s) until the `shipping received batch of` lines that contain `<run_id>-` together list 25 distinct ids `<run_id>-1`…`<run_id>-25`
4. Among those lines: at least one has `n > 1`, and the number of lines is less than 25 (spec §3.4; risk 2)
5. `POST /orders/bulk?count=0&prefix=x`, `count=101`, no `count`, `count=%2B5`, `count=1_0`, `count=1.5` and `count=abc` → each `400 {"error":"INVALID_COUNT"}`; `count=%205` → `200 {"sent":5,"failed":0}` (Review Focus 4)

- [ ] **Step 2: Run** for `dotnet` → FAIL.
- [ ] **Step 3: Build .NET → PASS.** If assertion 4 fails (one entry per batch), record it under risk 2, stop and report to the user before changing anything (spec §7).
- [ ] **Step 4: Build Python → PASS.**
- [ ] **Step 5: Build Java → PASS.** Record risk 2's outcome.
- [ ] **Step 6: Commit** — message `feat: add pub/sub Demo4 bulk publish and bulk subscribe`.

---

### Task 6: Demo 5 — routing and dead-lettering

**Files:**
- Create: `tests/pubsub/smoke-demo5.sh`
- Create per language: `pubsub/<lang>/Demo5-RoutingDeadLetter/{dapr.yaml, resources/subscription-orders.yaml, resources/subscription-dead-letter.yaml, resources/resiliency.yaml, OrderApi/…, Shipping/…}`

**Interfaces:**
- Consumes: Task 2 `OrderApi` (copied unchanged).
- Produces: the apps and `resources/` that Task 7 runs against RabbitMQ unchanged. Nothing in this folder may name Redis.

Apps: `order-api` 5101/3510, `shipping` 5102/3511.

- `subscription-orders.yaml`: topic `orders`; `routes.rules: [{match: 'event.data.priority == "express"', path: /orders/express}]`; `routes.default: /orders/standard`; `deadLetterTopic: orders-dead`; `scopes: [shipping]`.
- `subscription-dead-letter.yaml`: topic `orders-dead`, `routes.default: /orders/dead`, `scopes: [shipping]`.
- `resiliency.yaml`: `apiVersion: dapr.io/v1alpha1`, `kind: Resiliency`, name `pubsub-retries`; policy `retries.orderRetries: {policy: constant, duration: 1s, maxRetries: 3}`; `targets.components.pubsub.inbound.retry: orderRetries`; `scopes: [shipping]`.
- `shipping` handlers: express and standard log their line and return `200 SUCCESS`, except when `data.item == "poison"`: log `shipping rejected order <id>` and return `500 {"status":"RETRY"}`. `/orders/dead` logs `shipping dead-lettered order <id>` and returns `200 SUCCESS`.

- [ ] **Step 1: Write `smoke-demo5.sh`**

1. Ports free; start; wait for sidecars
2. POST three orders: `<run_id>-1` standard, `<run_id>-2` express, `<run_id>-3` item `poison` standard → each `200`
3. `wait_for_log … "shipping standard order <run_id>-1"`, `"shipping express order <run_id>-2"`; `count_log … "shipping express order <run_id>-1"` is `0` and `"shipping standard order <run_id>-2"` is `0`
4. `wait_for_log … "shipping dead-lettered order <run_id>-3"` (timeout 60 s)
5. `count_log … "shipping rejected order <run_id>-3"` equals `4` (first try + 3 retries; risk 4). If the runtime gives a different count, record the real number in the risk note and assert that instead, as long as it is > 1 and the message is dead-lettered.

- [ ] **Step 2: Run** for `dotnet` → FAIL.
- [ ] **Step 3: Build .NET → PASS.** If the poison order is never dead-lettered, record under risk 4, stop and report.
- [ ] **Step 4: Build Python → PASS.**
- [ ] **Step 5: Build Java → PASS.** Record risk 4's outcome for Redis.
- [ ] **Step 6: Commit** — message `feat: add pub/sub Demo5 routing and dead-lettering`.

---

### Task 7: Demo 6 — swap Redis for RabbitMQ

**Files:**
- Create: `tests/pubsub/start-rabbitmq.sh`, `tests/pubsub/smoke-demo6.sh`
- Create per language: `pubsub/<lang>/Demo6-SwapProvider/{dapr.yaml, resources/pubsub.yaml}`

**Interfaces:**
- Consumes: Task 6's apps and `resources/`, unchanged.

- `start-rabbitmq.sh`: `docker rm -f rabbitmq`; `docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:<exact 4.x management tag>` (pick the newest `4.x.y-management` tag on Docker Hub and pin it); wait up to 60 s for `docker exec rabbitmq rabbitmq-diagnostics -q ping`. Safe to run twice. The README in Task 8 shows the same commands.
- `resources/pubsub.yaml`: `type: pubsub.rabbitmq`, `version: v1`, `metadata.name: pubsub`; `connectionString: amqp://guest:guest@localhost:5672`, `durable: "true"`, `deletedWhenUnused: "false"`, `autoAck: "false"`, `requeueInFailure: "false"`, `deliveryMode: "2"`. Do **not** set `enableDeadLetter` (spec §3.6). Comment: same name as the Redis component, the only file that differs.
- `dapr.yaml`: apps `order-api` and `shipping` with `appDirPath: ../Demo5-RoutingDeadLetter/OrderApi` and `../Demo5-RoutingDeadLetter/Shipping`, same ports and commands as Demo 5; `common.resourcesPaths: [./resources, ../Demo5-RoutingDeadLetter/resources]`. Comments mirror `secrets/*/Demo3-SwapProvider/dapr.yaml`.

- [ ] **Step 1: Write `smoke-demo6.sh`**

1. If `docker exec rabbitmq rabbitmq-diagnostics -q ping` fails: print `RabbitMQ is not running; start it first (see pubsub/README.md)` and exit 1 (Review Focus 5)
2. Ports free; start; wait for sidecars
3. `GET :3511/v1.0/metadata` → component `pubsub` has `type == "pubsub.rabbitmq"`
4. Same assertions 2–5 as `smoke-demo5.sh`, with log paths under `pubsub/<lang>/Demo5-RoutingDeadLetter/Shipping` (that is where `dapr run` writes logs for the reused app)
5. `curl -s -u guest:guest http://localhost:15672/api/exchanges` lists exchanges named `orders` and `orders-dead`
6. `git diff --quiet HEAD -- pubsub/<lang>/Demo5-RoutingDeadLetter` (nothing in Demo 5 changed; spec anti-goal)

- [ ] **Step 2: Run** `bash tests/pubsub/start-rabbitmq.sh && bash tests/pubsub/smoke-demo6.sh dotnet` → FAIL.
- [ ] **Step 3: Create the .NET `Demo6-SwapProvider`; run → PASS.** If routing, retry or dead-lettering behaves differently from Redis, record under risk 4, stop and report.
- [ ] **Step 4: Python → PASS. Java → PASS.** Then stop RabbitMQ (`docker rm -f rabbitmq`) and run `smoke-demo6.sh python` → it exits 1 with the "RabbitMQ is not running" message.
- [ ] **Step 5: Commit** — message `feat: add pub/sub Demo6 swapping Redis for RabbitMQ`.

---

### Task 8: README, skill review and full run

**Files:**
- Create: `pubsub/README.md`
- Modify: `docs/superpowers/notes/2026-11-11-pubsub-risk-outcomes.md`
- Modify: any demo file a kept review finding changes

- [ ] **Step 1: Write `pubsub/README.md`**, following `secrets/README.md`'s structure:
  - Intro: the six demos, for the Dapr University pub/sub deep-dive.
  - Prerequisites: Dapr CLI/runtime 1.19.1 (`dapr init --runtime-version 1.19.1`), Docker, .NET 10 SDK / Python 3.12 + uv / Java 17 + Maven.
  - "Start RabbitMQ (challenge 6 only)": the commands from `start-rabbitmq.sh`, plus the management UI URL `http://localhost:15672` (guest/guest).
  - A demos table: folder, challenge, what it shows (from spec §3).
  - Per demo: `cd pubsub/<lang>/DemoN-… && dapr run -f .`, the `curl` commands the smoke test uses, and the expected output (the log lines from Shared contracts, and a real envelope sample for Demo 3).
  - Running the smoke tests: `bash tests/pubsub/run-all.sh [--demo N] [--lang L]`.

- [ ] **Step 2: Run the review skills** `dapr-skills:review-pubsub-components`, `dapr-skills:review-pubsub-publishing` and `dapr-skills:review-pubsub-subscriptions` over each .NET and Python demo. Fix real findings in all three languages (Java too, so parity holds). Note findings that conflict with a deliberate teaching choice (raw-body logging in Demo 3, the `poison` order in Demo 5, the guest/guest RabbitMQ credentials, an empty Redis password) in the risk note under "Review findings kept on purpose", with one line each on why.

- [ ] **Step 3: Full run**

Run: `bash tests/pubsub/start-rabbitmq.sh && bash tests/pubsub/run-all.sh`
Expected: 18 `PASS`, 0 `FAIL`, 0 `SKIP`. Then run `bash tests/pubsub/run-all.sh --demo 5` a second time, straight after, and expect 3 `PASS` (Review Focus 2: leftovers from the first run don't break a rerun).

- [ ] **Step 4: Check the risk note** has a written outcome for every risk 1–6. No "not yet verified" left.

- [ ] **Step 5: Commit**

```bash
git add pubsub/README.md docs/superpowers/notes/2026-11-11-pubsub-risk-outcomes.md pubsub
git commit -m "docs: add pub/sub demos README and review outcomes"
```
