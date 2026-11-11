#!/usr/bin/env bash
# Smoke test for Demo 5 (routing and dead-lettering).
# Usage: smoke-demo5.sh dotnet|python|java
source "$(dirname "$0")/lib.sh" "$@"

DEMO="$ROOT/pubsub/$LANG_ARG/Demo5-RoutingDeadLetter"
RUN="$(run_id)"

assert_ports_free 5101 5102 3510 3511

start_demo "$DEMO" 5101 5102 3510 3511
wait_for_sidecar 3510
wait_for_sidecar 3511

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
wait_for_log Shipping shipping "shipping standard order $RUN-1"
wait_for_log Shipping shipping "shipping express order $RUN-2"
assert_eq "0" "$(count_log Shipping shipping "shipping express order $RUN-1")" \
  "standard order $RUN-1 never reached the express handler"
assert_eq "0" "$(count_log Shipping shipping "shipping standard order $RUN-2")" \
  "express order $RUN-2 never reached the standard handler"

# 3. Dead-lettering: the poison order is retried, then arrives on orders-dead.
wait_for_log Shipping shipping "shipping dead-lettered order $RUN-3" 60
echo "PASS: poison order $RUN-3 was dead-lettered"

# Good orders are never dead-lettered.
assert_eq "0" "$(count_log Shipping shipping "shipping dead-lettered order $RUN-1")" \
  "standard order $RUN-1 was not dead-lettered"
assert_eq "0" "$(count_log Shipping shipping "shipping dead-lettered order $RUN-2")" \
  "express order $RUN-2 was not dead-lettered"

# 4. Retries: first delivery plus 3 retries from resiliency.yaml. Wait a little so late
# redeliveries would show up in the count.
sleep 3
assert_eq "4" "$(count_log Shipping shipping "shipping rejected order $RUN-3")" \
  "poison order $RUN-3 was delivered 4 times (first try + 3 retries)"

echo "Demo 5 ($LANG_ARG): all assertions passed"
