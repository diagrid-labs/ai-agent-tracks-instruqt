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

Outcome: not yet verified.

## 5. `resourcesPaths` list in multi-app run (§3.6)

Outcome: works. With `common.resourcesPaths: [../resources, ./resources]` in a multi-app `dapr.yaml`, Dapr CLI 1.19.1 / runtime 1.19.1 loads both folders: the shared `pubsub` component and the Demo 1 `shipping-orders` subscription. `shipping` received its orders in .NET, Python and Java, so no fallback (copying `pubsub.yaml` into each demo) is needed.

## 6. Metadata endpoint subscription types (Demos 1 and 2)

Outcome (Demo 1): as designed. `GET /v1.0/metadata` on `shipping` (:3511) lists the `orders` subscription with `type` `DECLARATIVE`; on `invoicing` (:3512) it is `PROGRAMMATIC`. Same in .NET, Python and Java. Demo 2: `warehouse` (:3511) lists the `orders` subscription with `type` `STREAMING` in .NET, Python and Java. `/v1.0/healthz` on the `warehouse` sidecar returns 204 although it has no `appPort`, so no `healthz/outbound` fallback is needed.
