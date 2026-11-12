#!/usr/bin/env bash
# Smoke test for Demo 6 (Demo 5's apps on RabbitMQ instead of Redis).
# Usage: smoke-demo6.sh dotnet|python|java
source "$(dirname "$0")/lib.sh" "$@"

DEMO="$(demo_dir 6)"
# Demo 6 runs Demo 5's apps, so their logs are in Demo 5's app folders.
DEMO5="$(demo_dir 5)"
SHIPPING="$DEMO5/$(app_dir shipping)"
RUN="$(run_id)"

if ! docker exec -u rabbitmq rabbitmq rabbitmq-diagnostics -q ping >/dev/null 2>&1; then
  echo "RabbitMQ is not running; start it first (see pubsub/README.md)" >&2
  exit 1
fi

assert_ports_free 5101 5102 3510 3511

start_demo "$DEMO" 5101 5102 3510 3511
wait_for_sidecar 3510
wait_for_sidecar 3511

# The component is named pubsub, but now it is RabbitMQ.
ptype="$(curl -s http://localhost:3511/v1.0/metadata | python3 -c 'import json,sys; print(next((c["type"] for c in json.load(sys.stdin)["components"] if c["name"]=="pubsub"), ""))')"
assert_eq "pubsub.rabbitmq" "$ptype" "component pubsub is of type pubsub.rabbitmq"

# Regression guard: scopes must sit beside spec, so order-api loads no subscription.
subs="$(curl -s http://localhost:3510/v1.0/metadata | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("subscriptions") or []))')"
assert_eq "0" "$subs" "order-api sidecar lists no subscriptions (scopes is outside spec)"

# 1. Three orders: a standard one, an express one, and a poison one that shipping rejects.
resp="$(post_json http://localhost:5101/orders \
  "{\"orderId\":\"$RUN-1\",\"item\":\"coffee-beans\",\"quantity\":1,\"priority\":\"standard\"}")"
assert_eq "200" "${resp%% *}" "POST $RUN-1 (standard) returns 200"
resp="$(post_json http://localhost:5101/orders \
  "{\"orderId\":\"$RUN-2\",\"item\":\"coffee-beans\",\"quantity\":1,\"priority\":\"express\"}")"
assert_eq "200" "${resp%% *}" "POST $RUN-2 (express) returns 200"
resp="$(post_json http://localhost:5101/orders \
  "{\"orderId\":\"$RUN-3\",\"item\":\"poison\",\"quantity\":1,\"priority\":\"standard\"}")"
assert_eq "200" "${resp%% *}" "POST $RUN-3 (poison) returns 200"

# 2. Routing: each order reaches the handler its priority selects, and only that one.
wait_for_log "$SHIPPING" shipping "shipping standard order $RUN-1"
wait_for_log "$SHIPPING" shipping "shipping express order $RUN-2"
assert_eq "0" "$(count_log "$SHIPPING" shipping "shipping express order $RUN-1")" \
  "standard order $RUN-1 never reached the express handler"
assert_eq "0" "$(count_log "$SHIPPING" shipping "shipping standard order $RUN-2")" \
  "express order $RUN-2 never reached the standard handler"

# 3. Dead-lettering: the poison order is retried, then arrives on orders-dead.
wait_for_log "$SHIPPING" shipping "shipping dead-lettered order $RUN-3" 60
echo "PASS: poison order $RUN-3 was dead-lettered"

# Good orders are never dead-lettered.
assert_eq "0" "$(count_log "$SHIPPING" shipping "shipping dead-lettered order $RUN-1")" \
  "standard order $RUN-1 was not dead-lettered"
assert_eq "0" "$(count_log "$SHIPPING" shipping "shipping dead-lettered order $RUN-2")" \
  "express order $RUN-2 was not dead-lettered"

# 4. Retries: first delivery plus 3 retries from resiliency.yaml. Wait a little so late
# redeliveries would show up in the count.
sleep 3
assert_eq "4" "$(count_log "$SHIPPING" shipping "shipping rejected order $RUN-3")" \
  "poison order $RUN-3 was delivered 4 times (first try + 3 retries)"

# 5. RabbitMQ created the exchanges for the topics.
exchanges="$(curl -s -u guest:guest http://localhost:15672/api/exchanges | python3 -c 'import json,sys; print(" ".join(e["name"] for e in json.load(sys.stdin)))')"
for ex in orders orders-dead; do
  case " $exchanges " in
    *" $ex "*) echo "PASS: RabbitMQ has exchange $ex" ;;
    *) die "RabbitMQ has no exchange $ex (found: $exchanges)" ;;
  esac
done

# 6. Anti-goal: swapping the broker changed nothing in Demo 5.
git -C "$ROOT" diff --quiet HEAD -- "$DEMO5" \
  || die "files under ${DEMO5#$ROOT/} changed"
echo "PASS: Demo 5 is unchanged"

echo "Demo 6 ($LANG_ARG): all assertions passed"
