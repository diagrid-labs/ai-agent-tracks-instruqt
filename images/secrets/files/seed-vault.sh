#!/usr/bin/env bash
# Seed HashiCorp Vault with the track's secrets, from inside the workstation.
#
# Usage: seed-vault.sh [SECRETS_JSON]        default: /work/secrets/secrets.json
# Env:   VAULT_ADDR   default http://vault:8200
#        VAULT_TOKEN  default root           (dev mode)
#
# The lab's setup step calls this. It talks to Vault's HTTP API rather than
# `docker exec ... vault kv put`, because the v2 workstation has no Docker and no vault binary.
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

# Parse AND write in one checked process.
#
# This used to be a shell `while read` loop fed by python3 through process substitution. Two bugs
# lived there, both silent, both exit 0: a parse error left Vault empty while the script reported
# success, because process substitution hides the producer's exit status from `set -e`; and any
# value containing a newline was truncated at the newline, with its tail written as a secret of
# its own. A line-delimited format simply cannot carry these values, so there is no delimiter to
# fix - the loop had to go.
#
# python3 is already required here to read the JSON, and it is in the base image for the Python
# demos, so doing the HTTP from the same process costs nothing and makes every failure loud.
python3 - "$SECRETS_JSON" "$VAULT_ADDR" "$VAULT_TOKEN" <<'PY'
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

secrets_path, vault_addr, vault_token = sys.argv[1:4]

try:
    with open(secrets_path, encoding="utf-8") as fh:
        secrets = json.load(fh)
except (OSError, ValueError) as exc:
    sys.exit(f"ERROR: could not read {secrets_path} as JSON: {exc}")

if not isinstance(secrets, dict):
    sys.exit(
        f"ERROR: {secrets_path} must be a JSON object of name/value pairs, "
        f"got {type(secrets).__name__}."
    )
if not secrets:
    sys.exit(f"ERROR: {secrets_path} contains no secrets.")

for name, value in secrets.items():
    # Vault stores strings; a non-string in the template is a template bug, not something to
    # silently coerce into a Python repr.
    if not isinstance(value, str):
        sys.exit(f"ERROR: secret {name!r} must be a string, got {type(value).__name__}.")

    # Writing the same key again overwrites it, so re-running this script is a no-op rather than
    # a duplicate - which is what makes a relaunched lab safe.
    request = urllib.request.Request(
        # quote() so a name with a space or slash is a bad-request we can read, not a mangled URL.
        f"{vault_addr}/v1/secret/data/dapr/{urllib.parse.quote(name, safe='')}",
        data=json.dumps({"data": {name: value}}).encode("utf-8"),
        headers={"X-Vault-Token": vault_token, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(request, timeout=30).close()
    except urllib.error.URLError as exc:
        sys.exit(f"ERROR: could not write secret/dapr/{name} to {vault_addr}: {exc}")

print(f"Seeded {len(secrets)} secret(s) into {vault_addr} under secret/dapr/")
PY
