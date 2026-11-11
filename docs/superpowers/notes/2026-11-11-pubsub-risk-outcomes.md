# Pub/sub deep-dive demos: risk outcomes

Outcomes for the risks in §7 of the design (`docs/superpowers/specs/2026-11-11-dapr-pubsub-deep-dive-demos-design.md`). Each task appends its result under the matching heading.

Toolchain: Dapr CLI 1.19.1, runtime 1.19.1. The Java SDK 1.19.0 is built against Spring Boot 4.0.8.

## 1. Java streaming ack timing (Demo 2)

Outcome: the happy path works. `DaprPreviewClient.subscribeToTopic("pubsub", "orders", TypeRef.get(Order.class))` delivers each order as a typed `Order`, and the stream acknowledges it itself, so the Java `warehouse` logs `warehouse received order <id>`. Ack timing (when the SDK acks relative to the handler finishing, and what a handler failure does) is not exercised; the demo always reports success. Gotcha: the Flux alone does not keep the JVM alive with `spring.main.web-application-type=none` (the app exited right after startup, "Exited App successfully"), so `OrderStream` blocks the main thread on a `CountDownLatch` that `@PreDestroy` releases on SIGTERM.

## 2. Bulk receive batching with Redis (Demo 4)

Outcome: works as designed. With `bulkSubscribe` (`maxMessagesCount: 10`, `maxAwaitDurationMs: 1000`) and one bulk publish of 25 orders, Redis delivers real batches in .NET, Python and Java: `shipping` logged batch sizes 10, 10, 5 in every language (3 requests for 25 orders). Dapr 1.19.1 POSTs to the subscription route `{"entries":[{"entryId","event","metadata":null,"contentType":"application/cloudevents+json"}, ...],"id","metadata":{"pubsubName":"pubsub"},"pubsubname","topic","type":"com.dapr.event.sent.bulk"}`. `entries[i].event` is a CloudEvent **object** (order in `event.data`), not a string, for orders published by the .NET, Python and Java SDKs; the handlers still parse a string `event` defensively. Order inside a batch is not the publish order (for example 23, 1, 20, ...). The Java `shipping` app has only `spring-boot-starter-web`, which in Spring Boot 4 brings Jackson 3 (`tools.jackson.databind`, `isString()`/`asString()`); the `com.fasterxml` package is only on the classpath of apps that use the Dapr SDK.

## 3. `rawPayload` on the subscriber side in each language (Demo 3)

Outcome: **publishing** with `rawPayload: "true"` works (the .NET SDK sends the order bytes as is, no base64 on the publish side). The problem is the **subscription** metadata `rawPayload: "true"` from the brief: with it, Dapr 1.19.1 delivers the raw message to the app wrapped in a CloudEvent with `data_base64`, not the bare order. Real body `shipping` received on `/orders-raw`:

```
{"data_base64":"eyJvcmRlcklkIjoicjE3OTQ0MzQ0MDgtMiIsIml0ZW0iOiJjb2ZmZWUtYmVhbnMiLCJxdWFudGl0eSI6MywicHJpb3JpdHkiOiJleHByZXNzIn0=","datacontenttype":"application/octet-stream","id":"a669a99e-24ea-45cc-b899-6b135c894d94","pubsubname":"pubsub","source":"Dapr","specversion":"1.0","topic":"orders-raw","traceid":"00-caa4258d9bd9f5f50e9ed3ed5d35ac78-e716131c626765f8-00","tracestate":"","type":"com.dapr.event.sent"}
```

Without `metadata.rawPayload` on the subscription (publisher still sets `rawPayload`), the same message arrives as the bare order JSON, `{"orderId":...,"item":...,"quantity":3,"priority":"express"}`, no `specversion`; the smoke test passes. So subscriber-side `rawPayload` means "wrap raw bytes for me" rather than "pass them through". A normal `/orders` delivery includes `traceparent` (and `traceid`, `tracestate`, `pubsubname`, `topic`, `time`), so that assertion holds.

Decision (user): publish-side `rawPayload` only; the `orders-raw` subscription has no `rawPayload` metadata. Verified in .NET, Python and Java: publish-side `rawPayload` delivers the bare order JSON (no `specversion`, no base64) to `shipping`. In Java, `@RequestBody String` accepts both `application/cloudevents+json` (envelope route) and `application/json`; both smoke assertions pass.

## 4. Dead-letter trigger (Demo 5)

Outcome: works as designed with Redis. With `resiliency.yaml` (`constant`, `1s`, `maxRetries: 3`, target `components.pubsub.inbound`, scoped to `shipping`), the poison order (`item: "poison"`, `500 {"status":"RETRY"}`) was delivered **4 times** (first try + 3 retries) in .NET, Python and Java, then dead-lettered: daprd logged `retriable error returned from app ... status code returned: 500` and `Error processing operation component[pubsub] input. Retrying in 1s` between attempts, about 1 s apart, and `shipping` received it once on `/orders/dead` roughly 3 s after the first attempt. The count stayed at 4 after a 3 s settle wait, so Redis' own redelivery (`redeliverInterval`/`processingTimeout`, defaults not changed) added no attempts. The dead-lettered message reaches `/orders/dead` as a CloudEvent (`application/cloudevents+json`) with the original order in `data`, so `data.orderId` works as on the other routes.

Gotcha found while building this: `scopes` on a `Subscription` belongs beside `spec`, not inside it. Inside `spec` it is ignored, so the `order-api` sidecar also subscribed; `order-api` answers 404 on `/orders/standard`, Dapr treats a 404 as a drop and, with `deadLetterTopic` set, dead-lettered every good order too. Demo 5's files use top-level `scopes`. The Demo 1, 3 and 4 subscription files still have `scopes` inside `spec` (harmless there because `order-api` drops the messages without a dead-letter topic, but the scope is not applied).

## 5. `resourcesPaths` list in multi-app run (§3.6)

Outcome: works. With `common.resourcesPaths: [../resources, ./resources]` in a multi-app `dapr.yaml`, Dapr CLI 1.19.1 / runtime 1.19.1 loads both folders: the shared `pubsub` component and the Demo 1 `shipping-orders` subscription. `shipping` received its orders in .NET, Python and Java, so no fallback (copying `pubsub.yaml` into each demo) is needed.

## 6. Metadata endpoint subscription types (Demos 1 and 2)

Outcome (Demo 1): as designed. `GET /v1.0/metadata` on `shipping` (:3511) lists the `orders` subscription with `type` `DECLARATIVE`; on `invoicing` (:3512) it is `PROGRAMMATIC`. Same in .NET, Python and Java. Demo 2: `warehouse` (:3511) lists the `orders` subscription with `type` `STREAMING` in .NET, Python and Java. `/v1.0/healthz` on the `warehouse` sidecar returns 204 although it has no `appPort`, so no `healthz/outbound` fallback is needed.

## 4b. Dead-letter trigger on RabbitMQ (Demo 6)

Outcome: same behaviour as Redis. Demo 5's unchanged apps and `resources/` run against `pubsub.rabbitmq` (`autoAck: "false"`, `requeueInFailure: "false"`, no `enableDeadLetter`). Routing by priority works, the poison order was delivered **4 times** (first try + 3 retries from `resiliency.yaml`) and then dead-lettered once to `/orders/dead`, in .NET, Python and Java; the good orders were never dead-lettered. The count stayed at 4 after a 3 s settle wait, so RabbitMQ did not requeue it. Dapr created exchanges `orders` and `orders-dead` (the topic names) and durable queues `shipping-orders` and `shipping-orders-dead` (`<app-id>-<topic>`), checked through the management API at :15672.

Gotcha in `tests/pubsub/start-rabbitmq.sh`: pinging with a plain `docker exec` runs as root and creates a root-owned `/var/lib/rabbitmq/.erlang.cookie` before the broker starts, so the broker crashes with `eacces` (container exits, "did not become ready"). The script and the smoke test ping with `docker exec -u rabbitmq`. Pinned image: `rabbitmq:4.4.0-management`.

## Review findings kept on purpose

The `dapr-skills` review skills (`review-pubsub-components`, `review-pubsub-publishing`, `review-pubsub-subscriptions`) were applied by hand to all six .NET and Python demos. No finding needed a code change (Java mirrors the .NET and Python code, so nothing to carry over). These findings were left as they are:

- DPS-SUB-010 (Demo 3, publisher sends `rawPayload` and the `orders-raw` subscription lacks it): the checklist advice is wrong for Dapr 1.19.1. Subscription-side `rawPayload` wraps the message in a CloudEvent with `data_base64` (risk 3); publish-side only is the user's decision.
- DPS-PUB-012 (Demo 3, `rawPayload: "true"` on publish): the point of the demo is to show what raw publishing drops.
- Raw-body logging in Demo 3 `shipping` (no `UseCloudEvents()`, no parsing): the learner has to see the envelope as it arrives.
- The `poison` order and `500 {"status":"RETRY"}` in Demo 5 and 6: the retry-exhaustion path to the dead-letter topic is the lesson.
- DPS-CFG-001 (info, RabbitMQ `guest:guest` connection string) and an empty `redisPassword`: both are localhost-only demo brokers. Using `secretKeyRef` would hide the one file Demo 6 swaps.
- DPS-CFG-004 (info, no component `scopes`) and DPS-CFG-007 (info, no `maxLenApprox`/`streamTTL`): extra component metadata would make the Redis-to-RabbitMQ diff harder to read. The `Subscription` files are scoped.
- DPS-SUB-006 (idempotency): no handler has a side effect beyond logging.
- Demo 1 and 3 `shipping` handlers read the body without validation (DPS-SUB-008 style): the subject is the wiring, and Dapr always sends a CloudEvent. Demos 4 and 5 show the DROP path for unreadable input.
- Demo 2 streaming handlers always succeed and do not guard against malformed JSON: spec §3.2 keeps retry and ack timing out of the demo (risk 1).
- DPS-PUB-007 on bulk publish is satisfied (`FailedEntries` is read); no per-entry metadata is set because .NET `BulkPublishEventAsync` cannot (spec §2).
- DPS-PUB-011 (info, Python sync `publish_event` inside `async def`) and DPS-PUB-002 (Python `except grpc.RpcError` does not catch `TimeoutError` when no sidecar runs): the routes are `async` to read the request body, and a missing sidecar still ends as a 500, not a swallowed failure.
- DPS-PUB-009 (info, topic literals repeated): each demo folder reads on its own (spec §4), the same reason `OrderApi` is duplicated per demo.
