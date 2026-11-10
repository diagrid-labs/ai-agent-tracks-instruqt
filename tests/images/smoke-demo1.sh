#!/usr/bin/env bash
# Demo1-ReadSecret in the v2 lab topology, in all three languages.
#
# This is the test that proves the image is fit for the lab rather than merely well-formed:
# the workstation is a container with no Docker, Redis is its own container reached by service
# name, the demo code arrives at run time, and the sidecar has to reach READY - not merely
# "Running" - before any of it counts.
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
# shellcheck source=lib.sh
. ./lib.sh

echo "== Demo1-ReadSecret in the lab topology: $IMAGE_SECRETS =="

trap stop_topology EXIT

start_topology
prepare_workspace

for lang in dotnet python java; do
    stop_dapr
    docker exec -d "$WS" sh -c "cd /work/secrets/$lang/Demo1-ReadSecret && dapr run -f . > /tmp/$lang.log 2>&1"

    if ! wait_for_url "http://localhost:5001/secret/orderdb-password" 180; then
        echo "--- dapr run output ($lang) ---" >&2
        docker exec "$WS" sh -c "tail -30 /tmp/$lang.log" >&2 2>/dev/null || true
        echo "--- daprd log ($lang) ---" >&2
        docker exec "$WS" sh -c "D=/work/secrets/$lang/Demo1-ReadSecret/.dapr/logs; tail -30 \$D/*daprd*.log" >&2 2>/dev/null || true
        fail "$lang: Demo1 never served a secret (the state store component points at a host the workstation cannot reach, or the app did not start)"
    fi

    # The §9.1 regression guard. A sidecar with no control plane prints "Status: Running" and
    # serves secrets quite happily, but answers 500 ERR_HEALTH_NOT_READY here forever - so this
    # is the one assertion that would catch the control plane silently failing to start.
    check_eq "$lang: sidecar is READY (204, not 200 - Dapr answers No Content)" "204" \
        "$(docker exec "$WS" curl -s -o /dev/null -w '%{http_code}' http://localhost:3500/v1.0/healthz 2>&1)"

    # Through the app: the demo's own endpoint, which is what the learner curls.
    check_eq "$lang: app reads the secret through the Secrets API" \
        '{"name":"orderdb-password","value":"s3cr3t-pa55w0rd"}' \
        "$(docker exec "$WS" curl -sf http://localhost:5001/secret/orderdb-password 2>&1)"

    # Through the sidecar directly: proves the component, not just the app's own wiring.
    sidecar_secret="$(docker exec "$WS" curl -sf http://localhost:3500/v1.0/secrets/secretstore/payments-api-key 2>&1)"
    case "$sidecar_secret" in
        *pk-test-7f3a9*) pass "$lang: sidecar serves the secret store directly" ;;
        *) fail "$lang: sidecar did not serve payments-api-key
       actual: $sidecar_secret" ;;
    esac

    # The state store is the component that reaches Redis by service name, so a successful write
    # is what proves the localhost -> redis:6379 move actually landed.
    check_ok "$lang: state store reaches redis by service name" -- \
        docker exec "$WS" curl -sf -X POST -H 'Content-Type: application/json' \
            -d '[{"key":"smoke","value":"ok"}]' \
            http://localhost:3500/v1.0/state/statestore
done

stop_dapr
summary "smoke-demo1.sh"
