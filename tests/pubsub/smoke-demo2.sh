#!/usr/bin/env bash
# Smoke test for Demo 2 (streaming subscription).
# Usage: smoke-demo2.sh dotnet|python|java
source "$(dirname "$0")/lib.sh" "$@"

DEMO="$ROOT/pubsub/$LANG_ARG/Demo2-Streaming"
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

wait_for_log Warehouse warehouse "warehouse received order $RUN-1"
echo "PASS: warehouse received the order over the stream"

echo "Demo 2 ($LANG_ARG): all assertions passed"
