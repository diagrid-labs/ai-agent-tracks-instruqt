#!/usr/bin/env bash
# Smoke test for bindings Demo 3 (State API and PostgreSQL output binding, same database).
# Needs the bindings Postgres (tests/bindings/start-postgres.sh).
# Usage: smoke-demo3.sh dotnet|python|java
source "$(dirname "$0")/lib.sh" "$@"

require_postgres
assert_ports_free 5201 3520

start_demo "$(demo_dir 3)" 5201 3520
wait_for_sidecar 3520

ENG="$(app_dir engineering)"

# The state table only exists after the first save, so wait for the save before querying it.
wait_for_log "$ENG" engineering "engineering saved reading wc-0001 to statestore (key=reading-wc-0001)" 180
wait_for_log "$ENG" engineering "engineering stored reading wc-0001 in warp_core_readings" 60

RESULT="$(get_json "http://localhost:5201/state/wc-0001")"
assert_eq "200" "${RESULT%% *}" "GET /state/wc-0001 answers 200"
STATE_TEMP="$(echo "${RESULT#* }" | python3 -c '
import json, sys
pairs = json.load(sys.stdin, object_pairs_hook=lambda p: p)
assert [k for k, _ in pairs] == ["readingId", "stardate", "coreTempK", "plasmaFlow"], pairs
r = dict(pairs)
assert r["readingId"] == "wc-0001", r
print(r["coreTempK"])
')" || die "GET /state/wc-0001 has the wrong shape: ${RESULT#* }"
echo "PASS: /state/wc-0001 returns the reading with the four keys in order"

# The same reading, read through the binding, must carry the same temperature.
RESULT="$(get_json "http://localhost:5201/readings?minTemp=-5")"
assert_eq "200" "${RESULT%% *}" "GET /readings?minTemp=-5 answers 200"
SQL_TEMP="$(echo "${RESULT#* }" | python3 -c '
import json, sys
row = next((r for r in json.load(sys.stdin) if r["readingId"] == "wc-0001"), None)
assert row is not None
print(row["coreTempK"])
')" || die "wc-0001 is missing from GET /readings: ${RESULT#* }"
assert_eq "$SQL_TEMP" "$STATE_TEMP" "state store and binding agree on coreTempK"

RESULT="$(get_json "http://localhost:5201/state/wc-nope")"
assert_eq "404" "${RESULT%% *}" "GET /state/wc-nope answers 404"
echo "${RESULT#* }" | python3 -c '
import json, sys
assert json.load(sys.stdin) == {"error": "NOT_FOUND"}
' || die "wc-nope should answer {\"error\": \"NOT_FOUND\"}: ${RESULT#* }"
echo "PASS: unknown reading answers NOT_FOUND"

# Dapr prefixes state keys with the app ID.
assert_eq "1" "$(psql_q "SELECT count(*) FROM state WHERE key = 'engineering||reading-wc-0001'")" \
  "state table holds engineering||reading-wc-0001"
# The value is a real JSON object (readable in psql), not a base64 string.
assert_eq "object" "$(psql_q "SELECT jsonb_typeof(value) FROM state WHERE key = 'engineering||reading-wc-0001'")" \
  "state value is a JSON object"

echo "Demo 3 ($LANG_ARG) smoke test passed"
