#!/usr/bin/env bash
# Smoke test for Demo 3 (CloudEvents with and without rawPayload).
# Usage: smoke-demo3.sh dotnet|python|java
source "$(dirname "$0")/lib.sh" "$@"

DEMO="$ROOT/pubsub/$LANG_ARG/Demo3-CloudEvents"
RUN="$(run_id)"

# json_norm round-trips JSON through python3 (key order preserved) so spacing never matters.
json_norm() {
  python3 -c 'import json,sys; print(json.dumps(json.loads(sys.stdin.read())))'
}

# log_json <prefix> <order-id>: prints the JSON after <prefix> on shipping's log line for that order.
log_json() {
  local log line
  log="$(app_log Shipping shipping)"
  line="$(grep -F -- "$1" "$log" | grep -F -- "$2" | head -n 1)"
  [ -n "$line" ] || die "no '$1' line for $2 in the shipping log"
  echo "${line#*"$1"}"
}

assert_ports_free 5101 5102 3510 3511

start_demo "$DEMO" 5101 5102 3510 3511
wait_for_sidecar 3510
wait_for_sidecar 3511

# 1. A normal publish: Dapr wraps the order in a CloudEvent.
resp="$(post_json http://localhost:5101/orders \
  "{\"orderId\":\"$RUN-1\",\"item\":\"coffee-beans\",\"quantity\":2,\"priority\":\"standard\"}")"
assert_eq "200" "${resp%% *}" "POST /orders returns 200"
assert_eq "{\"orderId\": \"$RUN-1\", \"topic\": \"orders\"}" "$(echo "${resp#* }" | json_norm)" \
  "POST /orders body names the order and topic"

# 2. Shipping sees the whole envelope, not just the order.
wait_for_log Shipping shipping "shipping received with envelope: "
wait_for_log Shipping shipping "$RUN-1"
envelope="$(log_json "shipping received with envelope: " "$RUN-1")"
echo "$envelope" | python3 -c '
import json, sys
run = sys.argv[1]
e = json.loads(sys.stdin.read())
for key in ("id", "source", "type", "specversion", "datacontenttype", "traceparent", "data"):
    assert key in e, "envelope is missing " + key
assert e["specversion"] == "1.0", e["specversion"]
assert e["data"]["orderId"] == run + "-1", e["data"]
' "$RUN" || die "envelope assertions failed: $envelope"
echo "PASS: shipping received a CloudEvent envelope with the order in data"

# 3. A raw publish: no envelope at all.
resp="$(post_json http://localhost:5101/orders/raw \
  "{\"orderId\":\"$RUN-2\",\"item\":\"coffee-beans\",\"quantity\":3,\"priority\":\"express\"}")"
assert_eq "200" "${resp%% *}" "POST /orders/raw returns 200"
assert_eq "{\"orderId\": \"$RUN-2\", \"topic\": \"orders-raw\"}" "$(echo "${resp#* }" | json_norm)" \
  "POST /orders/raw body names the order and topic"

wait_for_log Shipping shipping "shipping received raw: "
wait_for_log Shipping shipping "$RUN-2"
raw="$(log_json "shipping received raw: " "$RUN-2")"
assert_eq "{\"orderId\": \"$RUN-2\", \"item\": \"coffee-beans\", \"quantity\": 3, \"priority\": \"express\"}" \
  "$(echo "$raw" | json_norm)" "raw body is exactly the posted order"
echo "$raw" | python3 -c '
import json, sys
assert "specversion" not in json.loads(sys.stdin.read())' || die "raw body has a specversion key: $raw"
echo "PASS: raw body has no CloudEvent envelope"

echo "Demo 3 ($LANG_ARG): all assertions passed"
