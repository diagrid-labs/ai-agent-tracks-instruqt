#!/usr/bin/env bash
# Smoke test for Demo 2 (streaming subscription).
# Usage: smoke-demo2.sh dotnet|python|java
source "$(dirname "$0")/lib.sh" "$@"

DEMO="$(demo_dir 2)"
WAREHOUSE="$(app_dir warehouse)"
RUN="$(run_id)"

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

assert_ports_free 5101 3510 3511

start_demo "$DEMO" 5101 3510 3511
wait_for_sidecar 3510
# warehouse has no appPort; see docs/superpowers/notes/2026-11-11-pubsub-risk-outcomes.md if /v1.0/healthz never returns 204.
wait_for_sidecar 3511

# The stream is open once the metadata lists a STREAMING subscription. Waiting for it
# means the order below cannot be published before the subscriber is listening.
i=0
until [ "$(sub_type 3511)" = "STREAMING" ]; do
  i=$((i + 1))
  if [ "$i" -ge 60 ]; then
    demo_log_tail
    die "warehouse subscription never became STREAMING (last type: $(sub_type 3511))"
  fi
  sleep 1
done
echo "PASS: warehouse subscription is STREAMING"

resp="$(post_json http://localhost:5101/orders \
  "{\"orderId\":\"$RUN-1\",\"item\":\"coffee-beans\",\"quantity\":2,\"priority\":\"standard\"}")"
assert_eq "200" "${resp%% *}" "POST /orders returns 200"
assert_eq "{\"orderId\": \"$RUN-1\", \"topic\": \"orders\"}" "$(echo "${resp#* }" | json_norm)" \
  "POST /orders body names the order and topic"

wait_for_log "$WAREHOUSE" warehouse "warehouse received order $RUN-1"
echo "PASS: warehouse received the order over the stream"

# A message the warehouse cannot read: published straight through order-api's sidecar as
# text/plain, so Dapr wraps the text "not an order" in a CloudEvent. The warehouse drops it
# and acknowledges it, and the stream stays open for the next order.
before="$(count_log "$WAREHOUSE" warehouse "warehouse dropped unreadable event")"
status="$(curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:3510/v1.0/publish/pubsub/orders \
  -H 'Content-Type: text/plain' -d 'not an order')"
assert_eq "204" "$status" "publishing an unreadable message through the sidecar returns 204"
i=0
while [ "$i" -lt 30 ] && [ "$(count_log "$WAREHOUSE" warehouse "warehouse dropped unreadable event")" -le "$before" ]; do
  sleep 1
  i=$((i + 1))
done
[ "$(count_log "$WAREHOUSE" warehouse "warehouse dropped unreadable event")" -gt "$before" ] \
  || die "'warehouse dropped unreadable event' not logged after 30s"
echo "PASS: warehouse dropped the unreadable message"

resp="$(post_json http://localhost:5101/orders \
  "{\"orderId\":\"$RUN-2\",\"item\":\"coffee-beans\",\"quantity\":1,\"priority\":\"standard\"}")"
assert_eq "200" "${resp%% *}" "POST /orders after the unreadable message returns 200"
wait_for_log "$WAREHOUSE" warehouse "warehouse received order $RUN-2"
echo "PASS: the stream survived the unreadable message"
# Only the Java warehouse logs "warehouse stream ended" (its Flux reports the end of the stream
# to the app; the .NET and Python SDKs handle it internally), so this check is meaningful for
# Java only and trivially true for the others.
assert_eq "0" "$(count_log "$WAREHOUSE" warehouse "warehouse stream ended")" "the stream did not end"

echo "Demo 2 ($LANG_ARG): all assertions passed"
