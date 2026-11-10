#!/usr/bin/env bash
# Demo3-SwapProvider: the same unchanged app, now reading from HashiCorp Vault.
#
# This is the track's payoff - the app is not copied and not changed, only the component YAML
# behind the name `secretstore` is - so the assertion that matters is that Demo3 returns exactly
# what Demo1 returned in smoke-demo1.sh.
#
# It also covers the two things the lab's setup step will depend on: seeding Vault over its HTTP
# API from inside the workstation (no docker exec, no vault binary - §7.3), and that seeding
# being safe to run twice.
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
# shellcheck source=lib.sh
. ./lib.sh

echo "== Demo3-SwapProvider against Vault: $IMAGE_SECRETS =="

trap stop_topology EXIT

# --- the readiness race (Review Focus 4) --------------------------------------------------------
# The lab starts Vault in parallel with the workstation, so the seed can run while Vault is still
# coming up. start_topology returns as soon as the workstation is Running, which is well before
# Vault has unsealed - seeding immediately is therefore the realistic case, not a contrived one.
start_topology
prepare_workspace
check_ok "seed-vault.sh waits for a Vault that is still starting" -- \
    docker exec "$WS" seed-vault.sh

# --- idempotence (Review Focus 5) ---------------------------------------------------------------
# A relaunched lab, or a learner re-running the setup step, must leave Vault with the same
# contents - not doubled, not half-written.
check_ok "seed-vault.sh is safe to run a second time" -- \
    docker exec "$WS" seed-vault.sh

# --- the seed must FAIL loudly rather than leave Vault empty -------------------------------------
# The lab's setup step reads this script's exit status. A seed that returns 0 having written
# nothing is the worst outcome available: setup "succeeds", Vault is empty, and the learner
# discovers it at challenge 4 as an opaque secret-not-found.
seed_must_fail() {
    local label="$1" content="$2"
    docker exec -i "$WS" sh -c "cat > /tmp/bad.json" <<<"$content"
    if docker exec "$WS" seed-vault.sh /tmp/bad.json >/dev/null 2>&1; then
        fail "$label: seed-vault.sh exited 0 when it wrote nothing"
    fi
    pass "$label"
}
seed_must_fail "malformed JSON is a hard failure" '{ this is not json'
seed_must_fail "an empty object is a hard failure" '{}'
seed_must_fail "a JSON array is a hard failure" '["a","b"]'

# A value containing a newline must round-trip intact and must NOT fabricate extra secrets - a
# line-delimited producer truncates the value and turns its tail into a key of its own.
docker exec -i "$WS" sh -c 'cat > /tmp/multi.json' <<<'{"multiline":"line1\nline2","plain":"ok"}'
check_ok "a value containing a newline seeds without error" -- \
    docker exec "$WS" seed-vault.sh /tmp/multi.json
check_eq "a newline in a value round-trips intact" "line1
line2" \
    "$(docker exec "$WS" sh -c 'curl -sf -H "X-Vault-Token: root" http://vault:8200/v1/secret/data/dapr/multiline | python3 -c "import json,sys; print(json.load(sys.stdin)[\"data\"][\"data\"][\"multiline\"])"' 2>&1)"
check_ok "a newline in a value fabricates no phantom secret" -- \
    docker exec "$WS" sh -c '! curl -sf -o /dev/null -H "X-Vault-Token: root" http://vault:8200/v1/secret/data/dapr/line2'

# The checks above left test keys in Vault. Remove them (KV v2: deleting the metadata drops
# every version) and re-seed, so the bulk assertion below sees exactly the template's contents.
for test_key in multiline plain; do
    docker exec "$WS" curl -sf -o /dev/null -X DELETE -H "X-Vault-Token: root" \
        "http://vault:8200/v1/secret/metadata/dapr/$test_key" 2>/dev/null || true
done
check_ok "re-seeding the real template after the robustness checks" -- \
    docker exec "$WS" seed-vault.sh

expected_bulk='{"orderdb-password":"s3cr3t-pa55w0rd","payments-api-key":"pk-test-7f3a9"}'

for lang in dotnet python java; do
    stop_dapr
    docker exec -d "$WS" sh -c "cd /work/secrets/$lang/Demo3-SwapProvider && dapr run -f . > /tmp/d3-$lang.log 2>&1"

    if ! wait_for_url "http://localhost:5001/secret/orderdb-password" 180; then
        echo "--- dapr run output ($lang) ---" >&2
        docker exec "$WS" sh -c "tail -30 /tmp/d3-$lang.log" >&2 2>/dev/null || true
        echo "--- daprd log ($lang) ---" >&2
        docker exec "$WS" sh -c "D=/work/secrets/$lang/Demo3-SwapProvider/.dapr/logs; tail -30 \$D/*daprd*.log" >&2 2>/dev/null || true
        fail "$lang: Demo3 never served a secret from Vault (component address, seed, or app start)"
    fi

    check_eq "$lang: sidecar is READY against the Vault store" "204" \
        "$(docker exec "$WS" curl -s -o /dev/null -w '%{http_code}' http://localhost:3500/v1.0/healthz 2>&1)"

    # The whole point of the demo: byte-identical to Demo1's answer in smoke-demo1.sh.
    check_eq "$lang: Vault returns what the file store returned - same app, swapped provider" \
        '{"name":"orderdb-password","value":"s3cr3t-pa55w0rd"}' \
        "$(docker exec "$WS" curl -sf http://localhost:5001/secret/orderdb-password 2>&1)"

    # Bulk: proves the seed wrote BOTH names, not just the one the single-secret check reads.
    check_eq "$lang: both seeded secrets are readable from Vault" "$expected_bulk" \
        "$(docker exec "$WS" curl -sf http://localhost:5001/secrets 2>&1)"
done

stop_dapr
summary "smoke-demo3.sh"
