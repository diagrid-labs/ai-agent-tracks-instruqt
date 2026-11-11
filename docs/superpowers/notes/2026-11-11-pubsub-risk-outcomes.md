# Pub/sub deep-dive demos: risk outcomes

Outcomes for the risks in §7 of the design (`docs/superpowers/specs/2026-11-11-dapr-pubsub-deep-dive-demos-design.md`). Each task appends its result under the matching heading.

Toolchain: Dapr CLI 1.19.1, runtime 1.19.1. The Java SDK 1.19.0 is built against Spring Boot 4.0.8.

## 1. Java streaming ack timing (Demo 2)

Outcome: the happy path works. `DaprPreviewClient.subscribeToTopic("pubsub", "orders", TypeRef.get(Order.class))` delivers each order as a typed `Order`, and the stream acknowledges it itself, so the Java `warehouse` logs `warehouse received order <id>`. Ack timing (when the SDK acks relative to the handler finishing, and what a handler failure does) is not exercised; the demo always reports success. Gotcha: the Flux alone does not keep the JVM alive with `spring.main.web-application-type=none` (the app exited right after startup, "Exited App successfully"), so `OrderStream` blocks the main thread on a `CountDownLatch` that `@PreDestroy` releases on SIGTERM.

## 2. Bulk receive batching with Redis (Demo 4)

Outcome: not yet verified.

## 3. `rawPayload` on the subscriber side in each language (Demo 3)

Outcome: not yet verified.

## 4. Dead-letter trigger (Demo 5)

Outcome: not yet verified.

## 5. `resourcesPaths` list in multi-app run (§3.6)

Outcome: works. With `common.resourcesPaths: [../resources, ./resources]` in a multi-app `dapr.yaml`, Dapr CLI 1.19.1 / runtime 1.19.1 loads both folders: the shared `pubsub` component and the Demo 1 `shipping-orders` subscription. `shipping` received its orders in .NET, Python and Java, so no fallback (copying `pubsub.yaml` into each demo) is needed.

## 6. Metadata endpoint subscription types (Demos 1 and 2)

Outcome (Demo 1): as designed. `GET /v1.0/metadata` on `shipping` (:3511) lists the `orders` subscription with `type` `DECLARATIVE`; on `invoicing` (:3512) it is `PROGRAMMATIC`. Same in .NET, Python and Java. Demo 2: `warehouse` (:3511) lists the `orders` subscription with `type` `STREAMING` in .NET, Python and Java. `/v1.0/healthz` on the `warehouse` sidecar returns 204 although it has no `appPort`, so no `healthz/outbound` fallback is needed.
