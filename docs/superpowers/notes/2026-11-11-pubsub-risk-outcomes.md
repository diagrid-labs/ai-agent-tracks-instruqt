# Pub/sub deep-dive demos: risk outcomes

Outcomes for the risks in §7 of the design (`docs/superpowers/specs/2026-11-11-dapr-pubsub-deep-dive-demos-design.md`). Each task appends its result under the matching heading.

Toolchain: Dapr CLI 1.19.1, runtime 1.19.1. The Java SDK 1.19.0 is built against Spring Boot 4.0.8.

## 1. Java streaming ack timing (Demo 2)

Outcome: the happy path works in all three languages, and a message the warehouse cannot read is dropped and acknowledged without ending the stream (`smoke-demo2.sh` publishes `not an order` as `text/plain` through order-api's sidecar, asserts `warehouse dropped unreadable event`, then asserts the next order still arrives).

Java: `DaprPreviewClient.subscribeToTopic("pubsub", "orders", TypeRef.BYTE_ARRAY)` hands each message's data to a `Flux<byte[]>`, and the SDK answers Dapr SUCCESS for every message it emits, so the demo always acknowledges. The warehouse reads the raw bytes and parses them itself with its Jackson 3 `JsonMapper`. It does not use `TypeRef.get(Order.class)`: an undeserializable payload with a typed `TypeRef` is answered DROP by the SDK and ends the Flux with an error, which closes the stream (the SDK does not reopen it). If the `onNext` callback threw, Reactor would cancel the Flux, with the same result, so it never throws. With `spring.main.web-application-type=none`, the Flux alone does not keep the JVM alive (the stream's threads are daemon threads; the app exited right after startup, "Exited App successfully"); `spring.main.keep-alive=true` keeps it running until SIGTERM, and `@PreDestroy` disposes the subscription. (An earlier version blocked the main thread on a `CountDownLatch`; `keep-alive` replaced it.)

Java shutdown: on `dapr stop` or Ctrl+C the sidecar usually gets its signal first. daprd logs `Unsubscribed from pubsub 'pubsub' topic 'orders'` and ends the stream with gRPC `UNKNOWN: stream closed` (the app logged it 14 ms after daprd's `Received signal 'terminated'`), before the app's own shutdown starts, so the app cannot dispose the subscription first. The warehouse recognises that case (`Status.fromThrowable(error)`: code `UNKNOWN`, description `stream closed`) and logs INFO `warehouse stream closed by the sidecar`, with no stack trace. Any other error still logs ERROR `warehouse stream ended` with the exception: killing the warehouse's daprd with `kill -9` mid-run gives `UNAVAILABLE: Network closed for unknown reason` and the ERROR line. A sidecar stopped gracefully on its own, while the app keeps running, is also logged as `closed by the sidecar`.

.NET (`Dapr.Messaging` 1.19.1): a handler that throws ends the whole streaming subscription, so `HandleAsync` never throws and always returns `TopicResponseAction.Success`. The `MessageHandlingPolicy` timeout and default action are applied by the SDK, not by Dapr. A normal stop logs nothing beyond `Application is shutting down...`.

Python (`dapr` 1.19.0, `subscribe_with_handler`): a handler that raises gets no answer sent for that message, and the SDK closes the stream and opens a new one; there is no handler timeout. So `receive_order` never raises and always returns success. On a normal stop the SDK itself logs WARNING `Subscription stream error: stream closed Status Code: StatusCode.UNKNOWN — reconnecting` (the sidecar ended the stream first), retries health checks against the stopped sidecar (`Health check on http://127.0.0.1:3511/v1.0/healthz/outbound failed`), and then WARNING `Subscription handler thread still running 5s after close`. There is no error and no stack trace; all of it comes from inside `subscribe_with_handler`, which catches the stream error and reconnects before the app sees it, so the app cannot recognise the shutdown case the way the Java warehouse does without dropping that SDK surface.

## 2. Bulk receive batching with Redis (Demo 4)

Outcome: works as designed. With `bulkSubscribe` (`maxMessagesCount: 10`, `maxAwaitDurationMs: 1000`) and one bulk publish of 25 orders, Redis delivers real batches in .NET, Python and Java: `shipping` logged batch sizes 10, 10, 5 in every language (3 requests for 25 orders). Dapr 1.19.1 POSTs to the subscription route `{"entries":[{"entryId","event","metadata":null,"contentType":"application/cloudevents+json"}, ...],"id","metadata":{"pubsubName":"pubsub"},"pubsubname","topic","type":"com.dapr.event.sent.bulk"}`. `entries[i].event` is a CloudEvent **object** (order in `event.data`), not a string, for orders published by the .NET, Python and Java SDKs; the handlers still accept a string `event` (parsed with the CloudEvents SDK like an object). Order inside a batch is not the publish order (for example 23, 1, 20, ...). The Java `shipping` app uses `spring-boot-starter-webmvc`, which in Spring Boot 4 brings Jackson 3 (`tools.jackson.databind`, `isString()`/`asString()`). Jackson 2 (`com.fasterxml`) is on the classpath of the apps that use the Dapr SDK and, through `cloudevents-json-jackson`, of the `shipping` apps (§7).

## 3. `rawPayload` on the subscriber side in each language (Demo 3)

Outcome: **publishing** with `rawPayload: "true"` works (the .NET SDK sends the order bytes as is, no base64 on the publish side). The problem is the **subscription** metadata `rawPayload: "true"` from the brief: with it, Dapr 1.19.1 delivers the raw message to the app wrapped in a CloudEvent with `data_base64`, not the bare order. Real body `shipping` received on `/orders-raw`:

```
{"data_base64":"eyJvcmRlcklkIjoicjE3OTQ0MzQ0MDgtMiIsIml0ZW0iOiJjb2ZmZWUtYmVhbnMiLCJxdWFudGl0eSI6MywicHJpb3JpdHkiOiJleHByZXNzIn0=","datacontenttype":"application/octet-stream","id":"a669a99e-24ea-45cc-b899-6b135c894d94","pubsubname":"pubsub","source":"Dapr","specversion":"1.0","topic":"orders-raw","traceid":"00-caa4258d9bd9f5f50e9ed3ed5d35ac78-e716131c626765f8-00","tracestate":"","type":"com.dapr.event.sent"}
```

Without `metadata.rawPayload` on the subscription (publisher still sets `rawPayload`), the same message arrives as the bare order JSON, `{"orderId":...,"item":...,"quantity":3,"priority":"express"}`, no `specversion`; the smoke test passes. So subscriber-side `rawPayload` means "wrap raw bytes for me" rather than "pass them through". A normal `/orders` delivery includes `traceparent` (and `traceid`, `tracestate`, `pubsubname`, `topic`, `time`), so that assertion holds.

Decision (user): publish-side `rawPayload` only; the `orders-raw` subscription has no `rawPayload` metadata. Verified in .NET, Python and Java: publish-side `rawPayload` delivers the bare order JSON (no `specversion`, no base64) to `shipping`. In Java, `@RequestBody String` accepts both `application/cloudevents+json` (envelope route) and `application/json`; both smoke assertions pass.

## 4. Dead-letter trigger (Demo 5)

Outcome: works as designed with Redis. With `resiliency.yaml` (`constant`, `1s`, `maxRetries: 3`, target `components.pubsub.inbound`, scoped to `shipping`), the poison order (`item: "poison"`, `500 {"status":"RETRY"}`) was delivered **4 times** (first try + 3 retries) in .NET, Python and Java, then dead-lettered: daprd logged `retriable error returned from app ... status code returned: 500` and `Error processing operation component[pubsub] input. Retrying in 1s` between attempts, about 1 s apart, and `shipping` received it once on `/orders/dead` roughly 3 s after the first attempt. The count stayed at 4 after a 3 s settle wait, so Redis' own redelivery (`redeliverInterval`/`processingTimeout`, defaults not changed) added no attempts. The dead-lettered message reaches `/orders/dead` as a CloudEvent (`application/cloudevents+json`) with the original order in `data`, so `data.orderId` works as on the other routes.

Gotcha found while building this: `scopes` on a `Subscription` belongs beside `spec`, not inside it. Inside `spec` it is ignored, so the `order-api` sidecar also subscribed; `order-api` answers 404 on `/orders/standard`, Dapr treats a 404 as a drop and, with `deadLetterTopic` set, dead-lettered every good order too. Demo 5's files use top-level `scopes`. This was fixed in all demos in 699ff51. It was not harmless in Demos 1, 3 and 4: `order-api`'s own `POST /orders` answered the CloudEvent with 400 `INVALID_ORDER`. `smoke-demo1`, `smoke-demo3`, `smoke-demo4`, `smoke-demo5` and `smoke-demo6` now guard against it with the order-api zero-subscriptions check.

## 5. `resourcesPaths` list in multi-app run (§3.6)

Outcome: works. With `common.resourcesPaths: [../resources, ./resources]` in a multi-app `dapr.yaml`, Dapr CLI 1.19.1 / runtime 1.19.1 loads both folders: the shared `pubsub` component and the Demo 1 `shipping-orders` subscription. `shipping` received its orders in .NET, Python and Java, so no fallback (copying `pubsub.yaml` into each demo) is needed.

## 6. Metadata endpoint subscription types (Demos 1 and 2)

Outcome (Demo 1): as designed. `GET /v1.0/metadata` on `shipping` (:3511) lists the `orders` subscription with `type` `DECLARATIVE`; on `invoicing` (:3512) it is `PROGRAMMATIC`. Same in .NET, Python and Java. Demo 2: `warehouse` (:3511) lists the `orders` subscription with `type` `STREAMING` in .NET, Python and Java. `/v1.0/healthz` on the `warehouse` sidecar returns 204 although it has no `appPort`, so no `healthz/outbound` fallback is needed.

## 4b. Dead-letter trigger on RabbitMQ (Demo 6)

Outcome: same behaviour as Redis. Demo 5's unchanged apps and `resources/` run against `pubsub.rabbitmq` (`autoAck: "false"`, `requeueInFailure: "false"`, no `enableDeadLetter`). Routing by priority works, the poison order was delivered **4 times** (first try + 3 retries from `resiliency.yaml`) and then dead-lettered once to `/orders/dead`, in .NET, Python and Java; the good orders were never dead-lettered. The count stayed at 4 after a 3 s settle wait, so RabbitMQ did not requeue it. Dapr created exchanges `orders` and `orders-dead` (the topic names) and durable queues `shipping-orders` and `shipping-orders-dead` (`<app-id>-<topic>`), checked through the management API at :15672.

Gotcha in `tests/pubsub/start-rabbitmq.sh`: pinging with a plain `docker exec` runs as root and creates a root-owned `/var/lib/rabbitmq/.erlang.cookie` before the broker starts, so the broker crashes with `eacces` (container exits, "did not become ready"). The script and the smoke test ping with `docker exec -u rabbitmq`. Pinned image: `rabbitmq:4.4.0-management`.

## 7. CloudEvents SDK in the `shipping` apps (Demos 1, 3, 4, 5)

Decision (user, 2026-11-12): the declarative `shipping` handlers read Dapr's envelope with the open CloudEvents SDK instead of picking `data` out of the JSON by hand, to show that Dapr delivers a standard CloudEvent any CloudEvents library can read. Packages: .NET `CloudNative.CloudEvents` + `CloudNative.CloudEvents.SystemTextJson` 2.9.0, Python `cloudevents` 2.2.0, Java `io.cloudevents:cloudevents-core` + `cloudevents-json-jackson` 5.1.0. All three parse the body in structured mode (the whole event is the JSON body), whatever the request's content type, so they accept and reject the same inputs. `invoicing` (Demo 1) and `warehouse` (Demo 2) stay on their Dapr SDK surfaces.

Java Jackson 2 gate (approved only if it has no downside), checked on Demo 1 `shipping`:
- Dependency tree: Spring Boot 4.0.8 manages Jackson 2 (`jackson-2-bom.version` 2.21.5), which is exactly the 2.21.5 that `cloudevents-json-jackson` 5.1.0 asks for. One `com.fasterxml.jackson.core:jackson-annotations:2.21`, shared by Jackson 3.1.5 and Jackson 2.21.5. No overrides, no duplicates.
- Spring MVC message converters, listed at startup from `RequestMappingHandlerAdapter` before and after the change: identical, with one JSON converter, `org.springframework.http.converter.json.JacksonJsonHttpMessageConverter` (Jackson 3); no `MappingJackson2HttpMessageConverter`. Response bytes for SUCCESS/DROP unchanged (`{"status":"SUCCESS"}`).
- The 5.1.0 jars are Java 17 bytecode (class major 61); compiles with `release 17`, runs on Spring Boot 4.0.8, and parses Dapr's envelope including the `topic`, `pubsubname`, `traceid`, `traceparent` and `tracestate` extensions.
- Startup log: no new lines or warnings (normalized diff shows only PID and path); startup time unchanged (0.741 s vs 0.742 s).

Contract changes: Demo 3 `shipping` logs `shipping parsed CloudEvent id=<id> type=<type> source=<source>` after the envelope line on `/orders` (`smoke-demo3.sh` asserts it). A body that is JSON but not a CloudEvent (for example `{"data":{"orderId":"x"}}`, no `id`, `source`, `type` or `specversion`) is now `200 DROP` in Demos 1 and 5 and a per-entry DROP in Demo 4 (`smoke-demo1.sh` asserts it; the hand-made Demo 4 entry `e1` became a complete CloudEvent).

SDK differences that the demos do not hit (Dapr always sends a complete 1.0 event): Python 2.2.0 accepts an event without `id` (it generates one) where .NET and Java reject it, and .NET rejects `specversion` `0.3` where Python and Java accept it. Python raises different exceptions for bad JSON (`ValueError`), a non-object body (`AttributeError`), a wrong attribute type (`TypeError`) and a missing or invalid attribute (`CloudEventValidationError`); .NET throws `JsonException` or `ArgumentException`; Java throws `EventDeserializationException` for all of them.

## Review findings kept on purpose

The `dapr-skills` review skills (`review-pubsub-components`, `review-pubsub-publishing`, `review-pubsub-subscriptions`) were applied by hand to all six .NET and Python demos. No finding needed a code change (Java mirrors the .NET and Python code, so nothing to carry over). These findings were left as they are:

- DPS-SUB-010 (Demo 3, publisher sends `rawPayload` and the `orders-raw` subscription lacks it): the checklist advice is wrong for Dapr 1.19.1. Subscription-side `rawPayload` wraps the message in a CloudEvent with `data_base64` (risk 3); publish-side only is the user's decision.
- DPS-PUB-012 (Demo 3, `rawPayload: "true"` on publish): the point of the demo is to show what raw publishing drops.
- Raw-body logging in Demo 3 `shipping` (no `UseCloudEvents()`): the learner has to see the envelope as it arrives. The CloudEvents SDK parses the same body only after the raw line is logged, on `/orders` only.
- The `poison` order and `500 {"status":"RETRY"}` in Demo 5 and 6: the retry-exhaustion path to the dead-letter topic is the lesson.
- DPS-CFG-001 (info, RabbitMQ `guest:guest` connection string) and an empty `redisPassword`: both are localhost-only demo brokers. Using `secretKeyRef` would hide the one file Demo 6 swaps.
- DPS-CFG-004 (info, no component `scopes`) and DPS-CFG-007 (info, no `maxLenApprox`/`streamTTL`): extra component metadata would make the Redis-to-RabbitMQ diff harder to read. The `Subscription` files are scoped.
- DPS-SUB-006 (idempotency): no handler has a side effect beyond logging.
- Demo 3 `shipping` logs whatever arrives and always answers SUCCESS (DPS-SUB-008 style): the subject is the envelope. Demos 1, 4 and 5 show the DROP path for unreadable input.
- Demo 2 streaming handlers always acknowledge, also a message they cannot read (logged as `warehouse dropped unreadable event`): spec §3.2 keeps retry and ack timing out of the demo (risk 1).
- DPS-PUB-007 on bulk publish is satisfied (`FailedEntries` is read); no per-entry metadata is set because .NET `BulkPublishEventAsync` cannot (spec §2).
- DPS-PUB-011 (info, Python sync `publish_event` inside `async def`) and DPS-PUB-002 (Python `except grpc.RpcError` does not catch `TimeoutError` when no sidecar runs): the routes are `async` to read the request body, and a missing sidecar still ends as a 500, not a swallowed failure.
- DPS-PUB-009 (info, topic literals repeated): each demo folder reads on its own (spec §4), the same reason `OrderApi` is duplicated per demo.
