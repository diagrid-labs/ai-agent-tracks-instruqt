# Design: Dapr pub/sub deep-dive demos (`pubsub/`)

**Date:** 2026-11-11
**Status:** Approved 2026-11-11; implemented on feat/pubsub-deep-dive-demos
**Scope:** demo source code in this repo only. The learner-facing track content
(`assignment.md`, Robot suites, setup scripts in `dapr-university-instruqt`) is a later
session.

Decisions are marked as follows. Anything not marked was decided by the user in the
brainstorming session. *(My call)* marks a choice the designer made that the user has not
reviewed; the builder may revisit those but should say so.

---

## 1. Intent and why

Learners arrive from **Dapr 101**, challenge `5-pubsub-api`. There they ran `checkout`
and `order-processor` against the default Redis `pubsub.yaml`, published ten orders and
received them on an `/orders` endpoint. Subscriptions were shown only in passing (.NET and
Java `Topic` attributes, Python `/dapr/subscribe` or `DaprApp`), and CloudEvents got one
line about `UseCloudEvents()`.

This deep-dive starts where 101 stops. It covers what 101 skipped, in depth, in three
languages:

1. Switching the Redis component to RabbitMQ
2. The three subscription types (declarative, programmatic, streaming)
3. CloudEvents, with and without (`rawPayload`)
4. Bulk publishing, and bulk receiving
5. Routing and dead-lettering

The user did not name a specific problem the track must prevent. The goal is to cover all
five topics well.

### Relationship to existing material

- `diagrid-labs/dapr-pub-sub-deep-dive` (the user's conference-talk repo) has .NET-only
  demos on the same topics (`Demo1-Declarative` … `Demo8-Outbox`).
- `dapr-university-instruqt` has an unmerged `dapr-pubsub` track (branch
  `worktree-dapr-pubsub`, 5 challenges, 30 min, .NET only) built on those demos.
- `docs/superpowers/specs/2026-10-20-dapr-building-block-tracks-design.md` §8 planned to
  migrate those demos into `pubsub/dotnet/` and port them.

**The user chose to build fresh demos to this design instead of porting.** Do not copy
code from `dapr-pub-sub-deep-dive`. Reading it for ideas is fine. The §5.1 folder contract
of the building-block spec still applies (see §4 below).

---

## 2. Goals, non-goals, anti-goals

### Goals

1. A new top-level `pubsub/` folder with `dotnet/`, `python/` and `java/` (Spring Boot)
   subfolders, laid out like `secrets/`.
2. Six demos per language, one per challenge, numbered to match (§3).
3. The track they serve is **6 challenges, about 45 minutes**, roughly 7–8 minutes each.
4. **Declarative subscriptions are the default.** Programmatic appears only as the
   comparison in Demo 1. Streaming appears only in Demo 2. Everything else, including
   routing, dead-lettering, `rawPayload` on the subscriber side and bulk receiving, is
   configured in `Subscription` YAML.
5. **Dapr 1.19** runtime, CLI and SDKs throughout (§6).
6. The three languages behave identically: same app IDs, ports, routes, request and
   response JSON (including key order), and log lines (§5).
7. A `pubsub/README.md` that tells someone how to run every demo on their own machine,
   like `secrets/README.md`.

### Non-goals

- Track content: `assignment.md`, `notes.md`, `tabs.md`, Instruqt setup scripts, Robot
  drift suites, CI workflows. Next session.
- Container images for the sandbox (the `feat/dapr-secrets-container-image` branch work).
- Outbox pattern, Azure Service Bus, Kafka, or any broker other than Redis and RabbitMQ.
- JavaScript or Go.
- Per-event options on bulk publish (per-entry metadata or content type). .NET's
  `DaprClient.BulkPublishEventAsync` cannot set them, so using them would break parity.
- Retrofitting the three-act structure from the building-block spec. This is a deep-dive.

### Anti-goals (a failure even if everything runs)

- **Languages that drift apart.** If one language needs a note saying "in Java this works
  differently", the demo is wrong, unless the difference is the point and is called out
  in the design (only §7 risk 1 qualifies, and it is kept out of the demos).
- **Teaching SDK sugar instead of Dapr.** The YAML and the HTTP contract with the sidecar
  are the subject. An SDK helper that hides the thing being taught is the wrong choice.
- **Demos where nothing visible happens.** Every demo must give the learner something to
  see that proves the point: a log line, a response body, a RabbitMQ queue.
- **Fixing the RabbitMQ swap with code changes.** If Demo 6 needs any change to app code or
  `Subscription` files, the swap lesson has failed and the design must be revisited.

---

## 3. The six demos

Shared scenario across all demos *(my call)*: an order domain, continuing the
`order-api` naming from the secrets track. A publisher app publishes `Order` events;
subscriber apps receive them.

`Order` payload, identical in every language *(my call)*:

```json
{ "orderId": "o-1001", "item": "coffee-beans", "quantity": 2, "priority": "standard" }
```

`priority` is `standard` or `express` (used by routing in Demo 5). An order whose `item` is
`"poison"` is one the subscriber refuses (used by dead-lettering in Demo 5).

| Ch | Folder | Topic | What the learner sees |
|---|---|---|---|
| 1 | `Demo1-Subscriptions` | Declarative vs programmatic | Two subscriber apps on the same topic, one wired by a `Subscription` YAML and one from code. Both receive every order. The sidecar metadata endpoint (`GET /v1.0/metadata`) lists one subscription as `DECLARATIVE` and one as `PROGRAMMATIC`. |
| 2 | `Demo2-Streaming` | Streaming subscriptions | A subscriber with **no app port and no endpoints** that opens a stream to its sidecar and pulls orders. The metadata endpoint lists it as `STREAMING`. |
| 3 | `Demo3-CloudEvents` | CloudEvents with and without | The same order published twice: once normally (the subscriber logs the full envelope: `id`, `source`, `type`, `specversion`, `datacontenttype`, `traceparent`, `data`), and once with `rawPayload` (the subscriber logs only the bare order JSON). |
| 4 | `Demo4-Bulk` | Bulk publish and bulk receive | One bulk publish of N orders, with per-entry results. A subscriber with `bulkSubscribe` enabled receives them in batches and returns a status per entry; it logs each batch's size. |
| 5 | `Demo5-RoutingDeadLetter` | Routing and dead-lettering | `express` and `standard` orders land on different handlers through `routes.rules`. A `poison` order fails, is retried per a resiliency policy, then lands on the dead-letter topic, where a separate handler logs it. |
| 6 | `Demo6-SwapProvider` | Redis → RabbitMQ | The unchanged Demo 5 apps and `Subscription` files run against a `pubsub.rabbitmq` component with the same name. Same output. The RabbitMQ management UI shows the exchanges and queues Dapr created, including the dead-letter topic's. |

### 3.1 Demo 1: declarative vs programmatic

- Apps *(my call for IDs and ports)*: `order-api` (publisher, port 5101), `shipping`
  (declarative subscriber, 5102), `invoicing` (programmatic subscriber, 5103). See §5 for
  the port range.
- `shipping`'s wiring is `Demo1-Subscriptions/resources/subscription-shipping.yaml`
  (`dapr.io/v2alpha1`, `scopes: [shipping]`). Its code is a plain HTTP POST endpoint with
  no Dapr attributes.
- `invoicing` exposes its subscription from code:
  - .NET: `Dapr.AspNetCore` `[Topic]` or `.WithTopic(...)` plus `MapSubscribeHandler()`.
  - Python: `dapr-ext-fastapi` `DaprApp.subscribe(...)`.
  - Java: `dapr-sdk-springboot` `@Topic`.
- Both subscribers handle the order the same way: log a fixed line and return
  `200 {"status": "SUCCESS"}`. The comparison is the wiring, not the handler.
- `shipping` answers any event it cannot read with `200 {"status": "DROP"}` and a warning
  `shipping dropped unreadable event`, as Demo 5 does: Dapr retries any non-2xx except 404,
  and an unreadable event never parses on a redelivery. `invoicing` leaves unreadable events
  to its SDK.

### 3.2 Demo 2: streaming

- Apps: `order-api` (publisher) and `warehouse` (streaming subscriber, no `appPort` in
  `dapr.yaml`) *(my call for the name)*.
- SDK surfaces in 1.19 (all on the runtime's `SubscribeTopicEventsAlpha1`, so alpha):
  - .NET: the **`Dapr.Messaging`** NuGet package, `DaprPublishSubscribeClient.SubscribeAsync`.
  - Python: `DaprClient.subscribe_with_handler` (or `subscribe` plus a pull loop; builder's
    choice, same in effect).
  - Java: **`DaprPreviewClient.subscribeToTopic`**, which returns a `Flux<T>`. Do not use
    the deprecated `subscribeToEvents`.
- **The handler always succeeds.** It does not show retry or drop. This keeps the Java
  ack-timing question (§7 risk 1) out of the demo. A message it cannot read is logged as a
  warning, `warehouse dropped unreadable event`, and still acknowledged; the handler never
  throws.
- No `Subscription` YAML in this demo, and `warehouse` must not also be targeted by a
  declarative subscription.

### 3.3 Demo 3: CloudEvents

- The publisher exposes two endpoints *(my call)*: one publishes normally to `orders`, one
  publishes with publish metadata `rawPayload: "true"` to `orders-raw`.
- The subscriber has two declarative subscriptions, one per topic. **Neither carries
  `rawPayload`.** *(Decided by the user on 2026-11-11 after risk 3 was verified: in Dapr
  1.19.1, `rawPayload: "true"` on a subscription does not pass the bare payload through;
  it wraps an incoming raw message into a CloudEvent with `data_base64` and
  `datacontenttype: application/octet-stream`. Publishing with `rawPayload` and
  subscribing without it is what delivers the bare order JSON.)* A comment in
  `subscription-orders-raw.yaml`, and the README, explain that subscription-side
  `rawPayload` is for consuming raw messages from non-Dapr producers, which Dapr then
  wraps in a CloudEvent.
- The subscriber endpoints log exactly what arrived on the wire (the raw request body), so
  the learner sees the envelope in one case and only the order in the other. Do not let
  middleware unwrap the envelope before logging (for example .NET `UseCloudEvents()`): the
  point is to see it.
- After the raw envelope line, `/orders` reads the same body with the open CloudEvents SDK
  and logs `shipping parsed CloudEvent id=<id> type=<type> source=<source>` (decided by the
  user on 2026-11-12). A body the SDK cannot read gets no parsed line; the raw line already
  shows what arrived. `/orders-raw` gets no parsed line: the bare order is not a CloudEvent.
- The learner should come away knowing what `rawPayload` loses (type, source, id, trace
  context) and when it is worth it (talking to non-Dapr producers or consumers).

### 3.4 Demo 4: bulk publish and bulk receive

- Publisher endpoint takes a count and calls the SDK's bulk publish once:
  - .NET: `DaprClient.BulkPublishEventAsync`
  - Python: `DaprClient.publish_events`
  - Java: `DaprClient.publishEvents` (stable in 1.19; not the deprecated
    `DaprPreviewClient` versions)
  It returns how many entries were sent and how many failed, from the SDK's failed-entries
  result. `count` is stripped of surrounding whitespace and must then be ASCII digits only
  and 1..100; anything else is `400 {"error": "INVALID_COUNT"}`.
- Subscriber is **declarative with `bulkSubscribe`** (decided by the user):

  ```yaml
  bulkSubscribe:
    enabled: true
    maxMessagesCount: <builder picks>
    maxAwaitDurationMs: <builder picks>
  ```

  Its handler receives the bulk envelope (`entries[]`), logs the batch size, and answers
  per entry: `SUCCESS` for an entry it can read, `DROP` for one it cannot (Dapr redelivers
  only the entries that are not `SUCCESS`). It reads each entry's `event` with the open
  CloudEvents SDK, an open standard's library rather than a Dapr helper (decided by the user
  on 2026-11-12). Apart from that, the handler is written against the HTTP contract, not a
  Dapr SDK helper, in all three languages. Python has no Dapr SDK helper for it, so .NET and
  Java match Python instead of the other way round.
- Pick `maxMessagesCount` and `maxAwaitDurationMs` so a learner publishing e.g. 25 orders
  visibly sees more than one batch, and fewer batches than orders.

### 3.5 Demo 5: routing and dead-lettering

- One `Subscription` for `orders`:
  - `routes.rules`: `event.data.priority == "express"` → the express handler.
  - `routes.default` → the standard handler.
  - `deadLetterTopic: orders-dead`.
- A second `Subscription` for `orders-dead` → a dead-letter handler that logs the order.
- A `resiliency.yaml` with an inbound retry policy on the pub/sub component (a small,
  fixed number of retries with a short constant interval, so the learner watches the
  retries go by in well under a minute).
- Either handler returns an error status for an order whose `item` is `"poison"`. After the
  retries run out, the message goes to `orders-dead`. Use the retry-exhaustion path, not a
  `DROP` response (see §7 risk 4).
- Publisher sends a mixed set on request: some `standard`, some `express`, one `poison`
  *(my call)*. Built as three separate `POST /orders` calls instead of a "mixed set on
  request", so OrderApi stays identical to Demo 1.

### 3.6 Demo 6: swap the provider

Follows `secrets/*/Demo3-SwapProvider` and §5.1 of the building-block spec: the folder has
no app code. Its `dapr.yaml` points `appDirPath` back at the Demo 5 apps. Its `resources/`
holds a `pubsub.rabbitmq` component with `metadata.name: pubsub`, the same name as the
Redis one.

To keep "only the broker component differs" literally true *(my call)*:

- The Redis `pubsub` component lives once per language in `<lang>/resources/pubsub.yaml`
  (like `secrets/<lang>/resources/`).
- Each demo's own `Subscription` and resiliency files live in `DemoN-*/resources/`.
- Demos 1–5 load both folders with `resourcesPaths: [../resources, ./resources]`.
- Demo 6 loads `resourcesPaths: [./resources, ../Demo5-RoutingDeadLetter/resources]`.
  Its `./resources` holds only `pubsub.yaml` (RabbitMQ). No `Subscription` file is copied.

If the 1.19 CLI's multi-app run does not accept `resourcesPaths` as a list, fall back to
copying the Demo 5 subscription and resiliency files into `Demo6-SwapProvider/resources/`,
and say in a comment that they are identical copies (§7 risk 5).

RabbitMQ runs as a Docker container *(my call)*: the `rabbitmq` image with the
management plugin, ports 5672 and 15672, pinned to an exact tag at build time. The README
gets a "Start RabbitMQ (challenge 6 only)" block like the Vault one in
`secrets/README.md`, safe to run twice and waiting until the broker answers.

Do not enable the RabbitMQ component's own dead-letter feature. The dead-letter topic in
this track is Dapr's `deadLetterTopic`, and it must behave the same on both brokers.

---

## 4. Layout

> **Update 2026-11-12:** folder names are now idiomatic per language. .NET keeps PascalCase
> (`Demo1-Subscriptions/OrderApi`, as drawn below). Python and Java use kebab-case for both
> demo and app folders: `demo1-subscriptions/order-api`, `shipping`, `invoicing`,
> `warehouse`, `demo2-streaming`, `demo3-cloud-events`, `demo4-bulk`,
> `demo5-routing-dead-letter`, `demo6-swap-provider`. Instruqt assignments carry
> language-specific paths. App IDs, ports, routes and log lines are unchanged.

```
pubsub/
  README.md                       how to run every demo locally (like secrets/README.md)
  dotnet/ | python/ | java/
    resources/
      pubsub.yaml                 Redis, metadata.name: pubsub
    Demo1-Subscriptions/
      dapr.yaml
      resources/subscription-shipping.yaml
      OrderApi/  Shipping/  Invoicing/      (.NET; order-api/ shipping/ invoicing/ in Python, Java)
    Demo2-Streaming/
    Demo3-CloudEvents/
    Demo4-Bulk/
    Demo5-RoutingDeadLetter/
      resources/subscription-orders.yaml, subscription-dead-letter.yaml, resiliency.yaml
    Demo6-SwapProvider/
      dapr.yaml                   points at the Demo 5 apps (../Demo5-RoutingDeadLetter in .NET,
                                  ../demo5-routing-dead-letter in Python, Java)
      resources/pubsub.yaml       RabbitMQ, metadata.name: pubsub
```

- Component name `pubsub`; topics `orders`, `orders-raw`, `orders-dead` *(my call)*.
- Each demo has its own copy of the publisher app *(my call)*, so a learner reading one
  demo folder sees everything in it. Duplication across demos is accepted; this is teaching
  code.
- Run every demo with `dapr run -f .` from inside its folder, like the secrets demos.
- `.gitignore` gets `pubsub/**/target/` and `pubsub/**/.dapr/`, mirroring the secrets
  entries.

---

## 5. Cross-language parity rules

Copied from how `secrets/` already works:

- Same app IDs, app ports and Dapr HTTP ports in every language's `dapr.yaml`.
- Ports stay clear of the secrets demos, which use app ports 5001–5003 and Dapr HTTP ports
  3500–3502 *(my call)*. Pub/sub apps use **5101 and up**, their sidecars' Dapr HTTP
  ports **3510 and up**. Demo 6 reuses Demo 5's ports, since it runs the same apps.
- Same HTTP routes, request bodies and response bodies, including JSON key order.
- Same log line text for the things the learner is told to look for.
- Failures are shown, not swallowed: a publish that Dapr rejects returns an error status
  and the error name in the response body.
- App code comments explain the Dapr concept at the line where it happens, in the same
  voice as the secrets demos.
- Stack per language matches secrets: .NET 10 minimal API; Python 3.12 FastAPI with `uv`;
  Java 17 Spring Boot with Maven.

---

## 6. Versions

Checked on 2026-11-11. Re-check and pin exact versions when building.

| Component | Version | Note |
|---|---|---|
| Dapr runtime | 1.19.1 (2026-10-31) | |
| Dapr CLI | 1.19.1 (2026-10-22) | |
| .NET `Dapr.Client`, `Dapr.AspNetCore`, `Dapr.Messaging` | 1.19.1 | `Dapr.Messaging` only in Demo 2 |
| Python `dapr[fastapi]` | 1.19.0 | The FastAPI extension moved into the `dapr` package in 1.19; `dapr-ext-fastapi` is no longer a separate dependency |
| Java `io.dapr:dapr-sdk`, `dapr-sdk-springboot` | 1.19.0 | Spring Boot 4.0.8 |
| .NET `CloudNative.CloudEvents`, `CloudNative.CloudEvents.SystemTextJson` | 2.9.0 | `shipping` in Demos 1, 3, 4, 5 (added 2026-11-12) |
| Python `cloudevents` | 2.2.0 | `shipping` in Demos 1, 3, 4, 5 (added 2026-11-12) |
| Java `io.cloudevents:cloudevents-core`, `cloudevents-json-jackson` | 5.1.0 | `shipping` in Demos 1, 3, 4, 5 (added 2026-11-12); brings Jackson 2 beside Spring Boot's Jackson 3 |

The secrets demos stay on 1.18. Don't upgrade them as part of this work.

---

## 7. Risks: verify these before writing the demo that depends on them

Findings so far came from reading the `v1.19.0` SDK source, not from running anything.

1. **Java streaming ack timing (Demo 2).** In `EventSubscriberStreamObserver`, Java acks
   success when the event is emitted to the `Flux`. The ack may be sent before the
   learner's handler finishes. A handler exception may or may not become a retry. .NET and
   Python return an explicit status. The demo sidesteps this by always succeeding.
   Confirm the happy path works and leave the rest alone.
2. **Bulk receive batching with Redis (Demo 4).** Confirm that batches really arrive
   with more than one entry in 1.19. If Redis delivers one entry per batch, the demo shows
   nothing, and the user must hear about it before the demo is rewritten. Bulk receive is
   not part of the RabbitMQ swap: Demo 6 reruns the Demo 5 apps, which do not use
   `bulkSubscribe`. *(My call; an earlier draft wrongly listed Demo 6 here.)*
3. **`rawPayload` on the subscriber side in each language (Demo 3).** Confirm the raw
   body reaches the handler untouched in all three stacks, and that nothing in the
   framework rejects a non-CloudEvent body.
4. **Dead-letter trigger (Demo 5).** Confirm that retry exhaustion under the resiliency
   policy sends the message to `deadLetterTopic` on both Redis and RabbitMQ. Do not rely
   on a `DROP` response forwarding to the dead-letter topic unless verified.
5. **`resourcesPaths` list in multi-app run (§3.6).** Confirm the 1.19 CLI honours it in
   `common`. Fallback is described in §3.6.
6. **Metadata endpoint subscription types (Demos 1 and 2).** Confirm `GET /v1.0/metadata`
   reports `DECLARATIVE`, `PROGRAMMATIC` and `STREAMING` as described, in all three
   languages.

If any of these fails in a way that changes what the learner sees, stop and raise it with
the user. Don't quietly change the lesson.

---

## 7a. Tooling: the `dapr-skills` plugin

The user pointed out that the installed `dapr-skills` plugin has skills for pub/sub apps.
Use them as follows:

- **`dapr-skills:create-pubsub-dotnet` and `dapr-skills:create-pubsub-python`**: use these
  as a reference for idiomatic 1.19 SDK usage, component and `Subscription` YAML, and the
  three subscription types in .NET and Python. They scaffold their own project layout and
  ask what the app publishes, so the output must be fitted to the §4 layout, §3 scenario and
  §5 parity rules. This design wins wherever the two disagree. *(My call on how to use them.)*
- **No Java pub/sub skill exists.** Java demos are written to match the .NET and Python
  ones, using the Java SDK and Spring Boot directly.
- **`dapr-skills:review-pubsub-components`, `review-pubsub-publishing` and
  `review-pubsub-subscriptions`**: run these over each finished demo in .NET and Python as
  part of the definition of done. Review findings that conflict with a deliberate teaching
  choice in this design (for example logging the raw request body in Demo 3, or the
  `poison` order in Demo 5) are noted and kept, not "fixed".

---

## 8. What is left to the builder

- App folder and project names inside each demo, per language convention.
- Exact ports within the §5 ranges, as long as they are the same in every language.
- `maxMessagesCount` / `maxAwaitDurationMs`, retry count and interval.
- Python streaming: `subscribe_with_handler` or `subscribe` plus a loop.
- How each demo is checked before it is called done. There are no unit tests in the
  secrets demos and none are required here *(my call)*. Each demo must be run in all three
  languages, and the README must record the command and the expected output the learner
  should see.

### Definition of done

- All six demos run with `dapr run -f .` in all three languages against Redis, and Demo 6
  against RabbitMQ, with matching output across languages.
- Every risk in §7 has a written outcome (in the plan or a note under
  `docs/superpowers/notes/`).
- `pubsub/README.md` covers prerequisites, starting RabbitMQ, and running each demo.
- `.gitignore` updated.
