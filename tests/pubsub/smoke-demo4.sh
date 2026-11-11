#!/usr/bin/env bash
# Smoke test for Demo 4 (bulk publish and bulk subscribe).
# Usage: smoke-demo4.sh dotnet|python|java
source "$(dirname "$0")/lib.sh" "$@"

DEMO="$ROOT/pubsub/$LANG_ARG/Demo4-Bulk"
RUN="$(run_id)"

# json_norm round-trips JSON through python3 (key order preserved) so spacing never matters.
json_norm() {
  python3 -c 'import json,sys; print(json.dumps(json.loads(sys.stdin.read())))'
}

# batch_lines: prints shipping's batch lines that contain this run's ids.
batch_lines() {
  local log
  log="$(app_log Shipping shipping)"
  [ -n "$log" ] || return 0
  grep -F "shipping received batch of" "$log" | grep -F -- "$RUN-" || true
}

# distinct_ids: this run's distinct order ids across all batch lines, one per line.
distinct_ids() {
  batch_lines | grep -oE "$RUN-[0-9]+" | sort -u
}

assert_ports_free 5101 5102 3510 3511

start_demo "$DEMO" 5101 5102 3510 3511
wait_for_sidecar 3510
wait_for_sidecar 3511

# Regression guard: scopes must sit beside spec, so order-api loads no subscription.
subs="$(curl -s http://localhost:3510/v1.0/metadata | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("subscriptions") or []))')"
assert_eq "0" "$subs" "order-api sidecar lists no subscriptions (scopes is outside spec)"

# 1. One call publishes 25 orders.
resp="$(post_json "http://localhost:5101/orders/bulk?count=25&prefix=$RUN" "")"
assert_eq "200" "${resp%% *}" "POST /orders/bulk returns 200"
assert_eq '{"sent": 25, "failed": 0}' "$(echo "${resp#* }" | json_norm)" \
  "POST /orders/bulk reports 25 sent, 0 failed"

# 2. Shipping receives all 25, in batches.
i=0
while [ "$i" -lt 30 ] && [ "$(distinct_ids | wc -l | tr -d ' ')" -lt 25 ]; do
  sleep 1
  i=$((i + 1))
done
got="$(distinct_ids | wc -l | tr -d ' ')"
[ "$got" -eq 25 ] || die "shipping saw $got distinct order ids of 25 after 30s"
expected="$(for n in $(seq 1 25); do echo "$RUN-$n"; done | sort)"
assert_eq "$expected" "$(distinct_ids)" "shipping received $RUN-1 to $RUN-25"

# 3. They arrived grouped: some batch has more than one order, and fewer than 25 batches.
lines="$(batch_lines)"
nlines="$(echo "$lines" | wc -l | tr -d ' ')"
sizes="$(echo "$lines" | sed -E 's/.*received batch of ([0-9]+) orders.*/\1/' | tr '\n' ' ')"
echo "batch sizes: $sizes"
biggest="$(echo "$lines" | sed -E 's/.*received batch of ([0-9]+) orders.*/\1/' | sort -n | tail -n 1)"
[ "$biggest" -gt 1 ] || die "no batch had more than one order (sizes: $sizes)"
[ "$nlines" -lt 25 ] || die "expected fewer than 25 batches, got $nlines (sizes: $sizes)"
echo "PASS: 25 orders arrived in $nlines batches (largest $biggest)"

# 4. Shipping answers per entry: a readable entry is SUCCESS, an unreadable one is DROP.
# This posts a hand-made bulk body straight to the app, no sidecar involved.
resp="$(post_json http://localhost:5102/orders/bulk \
  "{\"entries\":[{\"entryId\":\"e1\",\"event\":{\"data\":{\"orderId\":\"$RUN-good\",\"item\":\"coffee-beans\",\"quantity\":1,\"priority\":\"standard\"},\"specversion\":\"1.0\"},\"contentType\":\"application/cloudevents+json\"},{\"entryId\":\"e2\",\"event\":{\"nothing\":\"here\"},\"contentType\":\"application/cloudevents+json\"}],\"topic\":\"orders\"}")"
assert_eq "200" "${resp%% *}" "hand-made bulk body returns 200"
assert_eq '{"statuses": [{"entryId": "e1", "status": "SUCCESS"}, {"entryId": "e2", "status": "DROP"}]}' \
  "$(echo "${resp#* }" | json_norm)" "good entry is SUCCESS, unreadable entry is DROP, in entry order"
wait_for_log Shipping shipping "shipping dropped unreadable entry e2"
echo "PASS: shipping logged the dropped entry"

# A body that is not a bulk envelope at all is a failed delivery.
resp="$(post_json http://localhost:5102/orders/bulk "this is not json")"
assert_eq "400" "${resp%% *}" "non-JSON bulk body returns 400"
assert_eq '{"error": "INVALID_BULK_REQUEST"}' "$(echo "${resp#* }" | json_norm)" \
  "non-JSON bulk body is INVALID_BULK_REQUEST"

# 5. count must be 1..100.
for q in "count=0&prefix=x" "count=101&prefix=x" "prefix=x"; do
  resp="$(post_json "http://localhost:5101/orders/bulk?$q" "")"
  assert_eq "400" "${resp%% *}" "POST /orders/bulk?$q returns 400"
  assert_eq '{"error": "INVALID_COUNT"}' "$(echo "${resp#* }" | json_norm)" \
    "POST /orders/bulk?$q body is INVALID_COUNT"
done

echo "Demo 4 ($LANG_ARG): all assertions passed"
