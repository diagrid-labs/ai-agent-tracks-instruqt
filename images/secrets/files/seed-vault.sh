#!/usr/bin/env bash
# Seed HashiCorp Vault with the track's secrets, from inside the workstation.
#
# Usage: seed-vault.sh [SECRETS_JSON]        default: /work/secrets/secrets.json
# Env:   VAULT_ADDR   default http://vault:8200
#        VAULT_TOKEN  default root           (dev mode)
#
# The lab's setup step calls this. It talks to Vault's HTTP API with curl rather than
# `docker exec ... vault kv put`, because the v2 workstation has no Docker and no vault binary -
# and because the track already teaches with curl, so nothing new is introduced to the learner.
#
# Secrets are written to secret/dapr/<name> - KV v2 with the "dapr" prefix - which is what the
# Dapr Vault secret store reads by default. That default is precisely why
# secretstore-vault.yaml sets neither vaultKVPrefix nor the engine path.
set -euo pipefail

SECRETS_JSON="${1:-/work/secrets/secrets.json}"
VAULT_ADDR="${VAULT_ADDR:-http://vault:8200}"
VAULT_TOKEN="${VAULT_TOKEN:-root}"
READY_TIMEOUT="${READY_TIMEOUT:-30}"

if [ ! -f "$SECRETS_JSON" ]; then
    echo "ERROR: $SECRETS_JSON not found. The lab setup copies it from secrets.example.json," >&2
    echo "which is the single owner of the secret values." >&2
    exit 1
fi

# The lab starts Vault in parallel with the workstation, so this script can easily run before
# Vault has unsealed. Poll rather than sleep: a fixed sleep is either too short on a slow start
# or wasted time on a fast one. /v1/sys/health answers 200 only once Vault is initialised,
# unsealed and active.
ready=false
for _ in $(seq 1 "$READY_TIMEOUT"); do
    if curl -sf -o /dev/null "$VAULT_ADDR/v1/sys/health"; then
        ready=true
        break
    fi
    sleep 1
done
if [ "$ready" != true ]; then
    echo "ERROR: Vault at $VAULT_ADDR did not become ready within ${READY_TIMEOUT} seconds." >&2
    exit 1
fi

# Read name/value pairs from the JSON. python3 rather than jq: it is already in the image for the
# Python demos, and this keeps the base image one package smaller.
# A tab separator survives values containing spaces, which `read name value` would otherwise trim.
count=0
while IFS="$(printf '\t')" read -r name value; do
    [ -n "$name" ] || continue
    # Writing the same key again overwrites it, so re-running this script is a no-op rather than
    # a duplicate - which is what makes a relaunched lab safe.
    printf '%s' "$value" \
        | python3 -c 'import json,sys; print(json.dumps({"data": {sys.argv[1]: sys.stdin.read()}}))' "$name" \
        | curl -sf -o /dev/null -X POST \
            -H "X-Vault-Token: $VAULT_TOKEN" \
            -H "Content-Type: application/json" \
            --data-binary @- \
            "$VAULT_ADDR/v1/secret/data/dapr/$name" \
        || { echo "ERROR: could not write secret/dapr/$name to $VAULT_ADDR" >&2; exit 1; }
    count=$((count + 1))
done < <(python3 -c '
import json, sys
with open(sys.argv[1]) as fh:
    for k, v in json.load(fh).items():
        print(f"{k}\t{v}")
' "$SECRETS_JSON")

echo "Seeded $count secret(s) into $VAULT_ADDR under secret/dapr/"
