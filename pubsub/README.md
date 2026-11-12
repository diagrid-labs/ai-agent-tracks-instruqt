# Dapr Pub/sub demos

Demo apps for the Dapr University pub/sub deep-dive track, in .NET, Python and Java. They go further than the first pub/sub lesson: the three subscription types, CloudEvents with and without `rawPayload`, bulk publish and bulk receive, routing and dead-lettering, and swapping Redis for RabbitMQ without touching application code.

In Instruqt the sandbox setup script prepares everything below for you. Use this guide to run the demos on your own machine.

## Prerequisites

- [Dapr CLI](https://docs.dapr.io/getting-started/install-dapr-cli/) 1.19.1 and a completed `dapr init --runtime-version 1.19.1` (Docker required, it starts Redis)
- Docker, for the RabbitMQ container used in challenge 6
- `lsof`, which the smoke-test scripts use to stop the demo apps
- The runtime for the language you want to run: .NET SDK 10, Python 3.12 with [uv](https://docs.astral.sh/uv/), or Java 17 with Maven (the Java demos use Spring Boot 4.0.8)

The shell commands below assume a POSIX shell (Git Bash, WSL, macOS or Linux) with `python3` available. The track itself runs on a Linux sandbox.

Every demo uses the same app IDs and ports in every language, so run one demo at a time:

| App | App port | Dapr HTTP port |
|---|---|---|
| `order-api` (publisher) | 5101 | 3510 |
| `shipping`, `warehouse` (first subscriber) | 5102 (`warehouse` has none) | 3511 |
| `invoicing` (Demo 1 only) | 5103 | 3512 |

## Start RabbitMQ (challenge 6 only)

```bash
# Removing any existing container first makes this block safe to run again.
docker rm -f rabbitmq >/dev/null 2>&1 || true
# 5672 is AMQP (what Dapr connects to), 15672 is the management UI and API.
docker run -d --name rabbitmq -p 127.0.0.1:5672:5672 -p 127.0.0.1:15672:15672 rabbitmq:4.4.0-management
# Wait up to 60 seconds for the broker to answer. Ping as the rabbitmq user: a root
# `docker exec` creates a root-owned .erlang.cookie before the broker starts, and the
# broker then crashes.
for _ in $(seq 1 60); do
  docker exec -u rabbitmq rabbitmq rabbitmq-diagnostics -q ping >/dev/null 2>&1 && break
  sleep 1
done
```

The management UI is at <http://localhost:15672> (user `guest`, password `guest`). The ports are bound to localhost only, so the default guest/guest credentials are fine for a demo.

`bash tests/pubsub/start-rabbitmq.sh` does the same and prints when the broker is ready. Stop it afterwards with `docker rm -f rabbitmq`.

## The demos

The pub/sub component is named `pubsub` and the topics are `orders`, `orders-raw` and `orders-dead`. The Redis component lives once per language in `<lang>/resources/pubsub.yaml`. Each demo adds its own `Subscription` and resiliency files in `DemoN-*/resources/`, and its `dapr.yaml` loads both folders with `resourcesPaths`.

| Folder | Challenge | What it shows |
|---|---|---|
| `Demo1-Subscriptions` | 1 | Two subscribers on the same topic: `shipping` is wired by a `Subscription` YAML (declarative), `invoicing` from code (programmatic). Both receive every order, and the sidecar metadata endpoint lists one as `DECLARATIVE` and one as `PROGRAMMATIC`. |
| `Demo2-Streaming` | 2 | `warehouse` has no app port and no endpoints. It opens a stream to its sidecar and pulls orders. The metadata endpoint lists it as `STREAMING`. |
| `Demo3-CloudEvents` | 3 | The same kind of order published twice: normally (the subscriber logs the whole CloudEvent envelope) and with `rawPayload` (the subscriber logs only the bare order). |
| `Demo4-Bulk` | 4 | One bulk publish of N orders, and a `bulkSubscribe` subscription that receives them in batches and answers per entry. |
| `Demo5-RoutingDeadLetter` | 5 | `express` and `standard` orders reach different handlers through `routes.rules`. A `poison` order is retried by a resiliency policy and then dead-lettered to `orders-dead`. |
| `Demo6-SwapProvider` | 6 | The unchanged Demo 5 apps and `Subscription` files run against a `pubsub.rabbitmq` component with the same name. The RabbitMQ management UI shows what Dapr created. |

Every demo runs the same way. Replace `dotnet` with `python` or `java`, and `Demo1-Subscriptions` with the demo you want:

```bash
cd pubsub/dotnet/Demo1-Subscriptions
dapr run -f .
```

Stop it with Ctrl+C. Run the `curl` commands in a second terminal.

All publisher endpoints answer `400 {"error": "INVALID_ORDER"}` for a body that is not a single JSON object with `orderId`, `item`, `quantity` and `priority` of the right types (anything after the object, such as `{...} x`, counts as invalid too), and publish nothing. If Dapr rejects a publish, they answer `500` with the gRPC status name in `error`. Published orders are compact JSON in every language.

The log lines about messages that are dropped or rejected (`shipping dropped unreadable event`, `shipping dropped unreadable entry <entryId>`, `shipping rejected order <orderId>`, `warehouse dropped unreadable event`) are warnings; every other line is info.

### Demo 1: declarative vs programmatic

```bash
curl -s -X POST http://localhost:5101/orders -H 'Content-Type: application/json' \
  -d '{"orderId":"o-1001","item":"coffee-beans","quantity":2,"priority":"standard"}'
```

Response: `{"orderId":"o-1001","topic":"orders"}`. Both subscribers log the order:

```text
shipping received order o-1001
invoicing received order o-1001
```

Compare how each subscription is registered:

```bash
curl -s http://localhost:3511/v1.0/metadata | python3 -m json.tool   # shipping: "type": "DECLARATIVE"
curl -s http://localhost:3512/v1.0/metadata | python3 -m json.tool   # invoicing: "type": "PROGRAMMATIC"
```

`shipping` has no Dapr code at all. Its subscription is `resources/subscription-shipping.yaml`.

Both subscribers answer `200 {"status": "SUCCESS"}`. `shipping` answers `200 {"status": "DROP"}` for an event it cannot read (not JSON, not an object, or no string `data.orderId`) and logs `shipping dropped unreadable event`. Dapr redelivers on any non-2xx answer except 404, and an unreadable event will not parse any better the next time, so it is dropped instead. How `invoicing` treats an unreadable event is left to its SDK.

```bash
curl -s -X POST http://localhost:5102/orders -H 'Content-Type: application/json' -d 'not json'
```

Note that `scopes` sits beside `spec` in every `Subscription` file, not inside it. Inside `spec` it is ignored, and then every sidecar loads the subscription, including the publisher's.

### Demo 2: streaming

```bash
curl -s -X POST http://localhost:5101/orders -H 'Content-Type: application/json' \
  -d '{"orderId":"o-2001","item":"coffee-beans","quantity":1,"priority":"standard"}'
```

`warehouse` logs:

```text
warehouse received order o-2001
```

```bash
curl -s http://localhost:3511/v1.0/metadata | python3 -m json.tool   # warehouse: "type": "STREAMING"
```

There is no `Subscription` file and no `appPort`: the app calls the sidecar, not the other way round. Streaming subscriptions are an alpha API in Dapr 1.19. The handler always acknowledges the message, so this demo does not show retry or drop. A message it cannot read (not a JSON object with a string `orderId`) is logged as `warehouse dropped unreadable event` and still acknowledged.

### Demo 3: CloudEvents

```bash
# A normal publish: Dapr wraps the order in a CloudEvent
curl -s -X POST http://localhost:5101/orders -H 'Content-Type: application/json' \
  -d '{"orderId":"o-3001","item":"coffee-beans","quantity":2,"priority":"standard"}'
# A raw publish: the publisher sets the rawPayload metadata, so there is no envelope
curl -s -X POST http://localhost:5101/orders/raw -H 'Content-Type: application/json' \
  -d '{"orderId":"o-3002","item":"coffee-beans","quantity":3,"priority":"express"}'
```

`shipping` logs the request body exactly as Dapr sent it. The normal publish arrives as a CloudEvent envelope, with the order in `data` (wrapped here for reading, the log has it on one line; the exact fields and their order vary a little between SDKs):

```text
shipping received with envelope: {"data":{"item":"coffee-beans","orderId":"o-3001","priority":"standard","quantity":2},"datacontenttype":"application/json","id":"6ce4e90a-c8aa-49bd-83ad-2c9f121cda9e","pubsubname":"pubsub","source":"order-api","specversion":"1.0","time":"2026-11-11T23:17:46+01:00","topic":"orders","traceid":"00-eff559eb42be353e9621e35a4ebd2a54-00779deeb981362a-00","traceparent":"00-eff559eb42be353e9621e35a4ebd2a54-00779deeb981362a-00","tracestate":"","type":"com.dapr.event.sent"}
```

The raw publish arrives as the bare order:

```text
shipping received raw: {"orderId":"o-3002","item":"coffee-beans","quantity":3,"priority":"express"}
```

Raw publishing drops what the envelope carries: the event `id`, `source`, `type`, `specversion` and the trace context. It is worth it when the other side is not a Dapr app, for example a consumer that expects plain JSON.

The `rawPayload` metadata is set by the **publisher** only. The `orders-raw` subscription does not carry it. On a subscription, `rawPayload: "true"` does the opposite job: it is for consuming raw messages from non-Dapr producers, and Dapr then wraps each one in a CloudEvent with the bytes in `data_base64` and `datacontenttype` `application/octet-stream`. For example, with `rawPayload: "true"` on the `orders-raw` subscription, `shipping` would receive this instead of the bare order:

```text
{"data_base64":"eyJvcmRlcklkIjoicjE3OTQ0MzQ0MDgtMiIsIml0ZW0iOiJjb2ZmZWUtYmVhbnMiLCJxdWFudGl0eSI6MywicHJpb3JpdHkiOiJleHByZXNzIn0=","datacontenttype":"application/octet-stream","id":"a669a99e-24ea-45cc-b899-6b135c894d94","pubsubname":"pubsub","source":"Dapr","specversion":"1.0","topic":"orders-raw","traceid":"00-caa4258d9bd9f5f50e9ed3ed5d35ac78-e716131c626765f8-00","tracestate":"","type":"com.dapr.event.sent"}
```

### Demo 4: bulk publish and bulk receive

```bash
# One call publishes 25 orders named bulk-1 to bulk-25
curl -s -X POST 'http://localhost:5101/orders/bulk?count=25&prefix=bulk'
```

Response: `{"sent":25,"failed":0}`. `count` must be a whole number from 1 to 100 written in plain digits (surrounding spaces are ignored, `+5`, `1.5` and `1_0` are not accepted), otherwise the answer is `400 {"error": "INVALID_COUNT"}`. The subscription uses `bulkSubscribe` with `maxMessagesCount: 10` and `maxAwaitDurationMs: 1000`, so `shipping` receives the 25 orders in batches. With Redis the batches were 10, 10 and 5, in every language (the order inside a batch is not the publish order):

```text
shipping received batch of 10 orders: bulk-23,bulk-1,bulk-20,...
shipping received batch of 10 orders: ...
shipping received batch of 5 orders: ...
```

The handler answers with a status per entry, so Dapr only redelivers the entries that did not succeed. An entry it cannot read gets `DROP` and the log line `shipping dropped unreadable entry <entryId>`. You can see this by posting a hand-made bulk body to the app:

```bash
curl -s -X POST http://localhost:5102/orders/bulk -H 'Content-Type: application/json' \
  -d '{"entries":[{"entryId":"e1","event":{"data":{"orderId":"o-4001","item":"coffee-beans","quantity":1,"priority":"standard"},"specversion":"1.0"},"contentType":"application/cloudevents+json"},{"entryId":"e2","event":{"nothing":"here"},"contentType":"application/cloudevents+json"}],"topic":"orders"}'
```

Response: `{"statuses":[{"entryId":"e1","status":"SUCCESS"},{"entryId":"e2","status":"DROP"}]}`.

### Demo 5: routing and dead-lettering

```bash
for o in \
  '{"orderId":"o-5001","item":"coffee-beans","quantity":1,"priority":"standard"}' \
  '{"orderId":"o-5002","item":"coffee-beans","quantity":1,"priority":"express"}' \
  '{"orderId":"o-5003","item":"poison","quantity":1,"priority":"standard"}'; do
  curl -s -X POST http://localhost:5101/orders -H 'Content-Type: application/json' -d "$o"
done
```

`shipping` logs the routing, then the retries of the poison order, then its arrival on `orders-dead`:

```text
shipping standard order o-5001
shipping express order o-5002
shipping rejected order o-5003
shipping rejected order o-5003
shipping rejected order o-5003
shipping rejected order o-5003
shipping dead-lettered order o-5003
```

The poison order is delivered 4 times: the first try plus the 3 retries of `resources/resiliency.yaml` (constant, 1 second apart). Then Dapr republishes it to `orders-dead`, which `shipping` subscribes to like any other topic. The handler answers `500 {"status": "RETRY"}` for it. A `DROP` response would skip the retries, so the demo uses the retry path. The good orders are never dead-lettered.

### Demo 6: swap the provider

Start RabbitMQ first (see above). The folder has no app code: its `dapr.yaml` runs the Demo 5 apps, and its `resources/pubsub.yaml` is a `pubsub.rabbitmq` component with the same name, `pubsub`, as the Redis one. The Demo 5 `Subscription` and resiliency files are loaded unchanged.

```bash
cd pubsub/dotnet/Demo6-SwapProvider
dapr run -f .
```

Send the same three orders as in Demo 5. The output is the same, including the 4 deliveries of the poison order and its arrival on `orders-dead`. Now open <http://localhost:15672> (guest/guest). Under Exchanges you find `orders` and `orders-dead` (the topic names), and under Queues the durable `shipping-orders` and `shipping-orders-dead` (`<app-id>-<topic>`), which Dapr created. The component keeps Dapr's own `deadLetterTopic` as the dead-letter mechanism, so RabbitMQ's dead-letter feature stays off.

## Running the smoke tests

`tests/pubsub/` has one script per demo and language. Each starts the demo, drives it with the requests above and checks the log lines and responses:

```bash
bash tests/pubsub/run-all.sh                       # every demo in every language
bash tests/pubsub/run-all.sh --demo 5              # one demo, all languages
bash tests/pubsub/run-all.sh --demo 3 --lang java  # one demo, one language
```

Demo 6 needs RabbitMQ: run `bash tests/pubsub/start-rabbitmq.sh` first. Each script checks that the ports its own demo uses are free before it starts, and uses order IDs unique to the run, so leftover messages in Redis from an earlier run do not matter.
