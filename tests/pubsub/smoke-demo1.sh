#!/usr/bin/env bash
# Smoke test for Demo 1 (declarative vs programmatic subscriptions).
# Usage: smoke-demo1.sh dotnet|python|java
source "$(dirname "$0")/lib.sh" "$@"

DEMO="$(demo_dir 1)"
INVOICING="$(app_dir invoicing)"
SHIPPING="$(app_dir shipping)"
RUN="$(run_id)"

# json_norm round-trips JSON through python3 (key order preserved) so spacing never matters.
json_norm() {
  python3 -c 'import json,sys; print(json.dumps(json.loads(sys.stdin.read())))'
}

# sub_type <dapr-http-port>: prints the type of the subscription on topic "orders".
sub_type() {
  curl -s "http://localhost:$1/v1.0/metadata" | python3 -c '
import json, sys
meta = json.load(sys.stdin)
print(next((s.get("type", "") for s in meta.get("subscriptions", []) if s.get("topic") == "orders"), "NONE"))'
}

assert_ports_free 5101 5102 5103 3510 3511 3512

start_demo "$DEMO" 5101 5102 5103 3510 3511 3512
wait_for_sidecar 3510
wait_for_sidecar 3511
wait_for_sidecar 3512

# Regression guard: scopes must sit beside spec, so order-api loads no subscription.
subs="$(curl -s http://localhost:3510/v1.0/metadata | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("subscriptions") or []))')"
assert_eq "0" "$subs" "order-api sidecar lists no subscriptions (scopes is outside spec)"

# 1. A valid order is published to the orders topic.
resp="$(post_json http://localhost:5101/orders \
  "{\"orderId\":\"$RUN-1\",\"item\":\"coffee-beans\",\"quantity\":2,\"priority\":\"standard\"}")"
assert_eq "200" "${resp%% *}" "POST /orders returns 200"
assert_eq "{\"orderId\": \"$RUN-1\", \"topic\": \"orders\"}" "$(echo "${resp#* }" | json_norm)" \
  "POST /orders body names the order and topic"

# 2. Both subscribers receive it: shipping declaratively, invoicing from code.
wait_for_log "$SHIPPING" shipping "shipping received order $RUN-1"
echo "PASS: shipping received the order"
wait_for_log "$INVOICING" invoicing "invoicing received order $RUN-1"
echo "PASS: invoicing received the order"

# 3. The metadata endpoint tells the two kinds of subscription apart.
assert_eq "DECLARATIVE" "$(sub_type 3511)" "shipping subscription is DECLARATIVE"
assert_eq "PROGRAMMATIC" "$(sub_type 3512)" "invoicing subscription is PROGRAMMATIC"

# 4. A malformed order is refused and nothing is published.
resp="$(post_json http://localhost:5101/orders "{\"orderId\":\"$RUN-2\"}")"
assert_eq "400" "${resp%% *}" "malformed order returns 400"
assert_eq '{"error": "INVALID_ORDER"}' "$(echo "${resp#* }" | json_norm)" "malformed order body is INVALID_ORDER"
resp="$(post_json http://localhost:5101/orders \
  "{\"orderId\":\"$RUN-3\",\"item\":\"coffee-beans\",\"quantity\":\"2\",\"priority\":\"standard\"}")"
assert_eq "400" "${resp%% *}" "string quantity returns 400"
assert_eq '{"error": "INVALID_ORDER"}' "$(echo "${resp#* }" | json_norm)" "string quantity body is INVALID_ORDER"
resp="$(post_json http://localhost:5101/orders \
  "{\"orderId\":\"$RUN-6\",\"item\":\"coffee-beans\",\"quantity\":2147483648,\"priority\":\"standard\"}")"
assert_eq "400" "${resp%% *}" "quantity above the 32-bit int range returns 400"
assert_eq '{"error": "INVALID_ORDER"}' "$(echo "${resp#* }" | json_norm)" "quantity above int range is INVALID_ORDER"
resp="$(post_json http://localhost:5101/orders "not json")"
assert_eq "400" "${resp%% *}" "non-JSON body returns 400"
assert_eq '{"error": "INVALID_ORDER"}' "$(echo "${resp#* }" | json_norm)" "non-JSON body is INVALID_ORDER"
resp="$(post_json http://localhost:5101/orders \
  "{\"orderId\":\"$RUN-4\",\"item\":\"coffee-beans\",\"quantity\":2,\"priority\":\"standard\"} x")"
assert_eq "400" "${resp%% *}" "order followed by trailing content returns 400"
assert_eq '{"error": "INVALID_ORDER"}' "$(echo "${resp#* }" | json_norm)" "trailing content body is INVALID_ORDER"
sleep 3
assert_eq "0" "$(count_log "$SHIPPING" shipping "$RUN-2")" "shipping never saw the malformed order"
assert_eq "0" "$(count_log "$SHIPPING" shipping "$RUN-3")" "shipping never saw the string-quantity order"
assert_eq "0" "$(count_log "$SHIPPING" shipping "$RUN-4")" "shipping never saw the trailing-content order"
assert_eq "0" "$(count_log "$SHIPPING" shipping "$RUN-6")" "shipping never saw the out-of-range quantity order"

# 5. Shipping drops an event it cannot read: 200 DROP, so Dapr does not redeliver it.
# These post straight to the app, no sidecar involved.
before="$(count_log "$SHIPPING" shipping "shipping dropped unreadable event")"
resp="$(post_json http://localhost:5102/orders "not json")"
assert_eq "200" "${resp%% *}" "non-JSON event returns 200"
assert_eq '{"status": "DROP"}' "$(echo "${resp#* }" | json_norm)" "non-JSON event is DROP"
resp="$(post_json http://localhost:5102/orders "[]")"
assert_eq "200" "${resp%% *}" "non-object event returns 200"
assert_eq '{"status": "DROP"}' "$(echo "${resp#* }" | json_norm)" "non-object event is DROP"
resp="$(post_json http://localhost:5102/orders "null")"
assert_eq "200" "${resp%% *}" "a JSON null event returns 200"
assert_eq '{"status": "DROP"}' "$(echo "${resp#* }" | json_norm)" "a JSON null event is DROP"
# Shipping reads the body with the CloudEvents SDK, so an order in "data" is not enough: it is
# not a CloudEvent without the required attributes (here none of them are present).
resp="$(post_json http://localhost:5102/orders "{\"data\":{\"orderId\":\"$RUN-5\"}}")"
assert_eq "200" "${resp%% *}" "object that is not a CloudEvent returns 200"
assert_eq '{"status": "DROP"}' "$(echo "${resp#* }" | json_norm)" "object that is not a CloudEvent is DROP"
# A complete CloudEvent followed by more content is not one JSON value, so it is unreadable too.
resp="$(post_json http://localhost:5102/orders \
  "{\"specversion\":\"1.0\",\"id\":\"$RUN-7\",\"source\":\"smoke-test\",\"type\":\"com.dapr.event.sent\",\"datacontenttype\":\"application/json\",\"data\":{\"orderId\":\"$RUN-7\"}} x")"
assert_eq "200" "${resp%% *}" "CloudEvent followed by trailing content returns 200"
assert_eq '{"status": "DROP"}' "$(echo "${resp#* }" | json_norm)" "CloudEvent followed by trailing content is DROP"
i=0
while [ "$i" -lt 30 ] && [ "$(count_log "$SHIPPING" shipping "shipping dropped unreadable event")" -lt $((before + 5)) ]; do
  sleep 1
  i=$((i + 1))
done
after="$(count_log "$SHIPPING" shipping "shipping dropped unreadable event")"
[ "$after" -ge $((before + 5)) ] || die "expected 5 more 'shipping dropped unreadable event' lines, got $((after - before))"
assert_eq "0" "$(count_log "$SHIPPING" shipping "shipping received order $RUN-5")" "shipping did not accept the non-CloudEvent order"
assert_eq "0" "$(count_log "$SHIPPING" shipping "shipping received order $RUN-7")" "shipping did not accept the trailing-content event"
echo "PASS: shipping logged the five dropped events"
assert_last_log_is_warning "$SHIPPING" shipping "shipping dropped unreadable event" \
  "'shipping dropped unreadable event' is logged at warning level"

echo "Demo 1 ($LANG_ARG): all assertions passed"
