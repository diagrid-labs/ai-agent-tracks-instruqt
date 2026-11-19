#!/usr/bin/env bash
# Smoke test for bindings Demo 1 (cron input binding). Needs no Postgres.
# Usage: smoke-demo1.sh dotnet|python|java
source "$(dirname "$0")/lib.sh" "$@"

assert_ports_free 5201 3520

start_demo "$(demo_dir 1)" 5201 3520
wait_for_sidecar 3520

ENG="$(app_dir engineering)"

# The first tick can take a while: Java compiles on first run, and the cron binding waits one
# full interval (10 s) before it fires.
wait_for_log "$ENG" engineering "engineering warp-core scan wc-0001 stardate=" 180
T0=$(date +%s)
# A second reading proves the schedule repeats.
wait_for_log "$ENG" engineering "engineering warp-core scan wc-0002 " 25
echo "PASS: second scan arrived $(( $(date +%s) - T0 ))s after the first"

LINE="$(grep -hF "engineering warp-core scan wc-0001 " "$(app_log "$ENG" engineering)" | head -n 1)"
echo "$LINE" | grep -Eq '^.*engineering warp-core scan wc-0001 stardate=[0-9]+\.[0-9] coreTempK=(8[5-9][0-9]|9[0-4][0-9]|950) plasmaFlow=(0\.[7-9][0-9]|1\.00)$' \
  || die "wc-0001 log line has the wrong format: $LINE"
echo "PASS: wc-0001 log line format"

RESULT="$(get_json "http://localhost:3520/v1.0/metadata")"
STATUS="${RESULT%% *}"
assert_eq "200" "$STATUS" "metadata endpoint answers"
echo "${RESULT#* }" | python3 -c '
import json, sys
comps = json.load(sys.stdin)["components"]
by_name = {c["name"]: c["type"] for c in comps}
assert by_name.get("warp-core-scan") == "bindings.cron", by_name
assert "ship-db" not in by_name, by_name
' || die "metadata should list warp-core-scan (bindings.cron) and no ship-db"
echo "PASS: metadata lists warp-core-scan (bindings.cron) and no ship-db"

echo "Demo 1 ($LANG_ARG) smoke test passed"
