#!/usr/bin/env bash
# Smoke test for bindings Demo 4 (cron input binding -> service invocation -> Postgres output
# binding). Needs the bindings Postgres (tests/bindings/start-postgres.sh).
# Usage: smoke-demo4.sh dotnet|python|java
source "$(dirname "$0")/lib.sh" "$@"

require_postgres
assert_ports_free 5201 5202 3520 3521

# Leftovers from an earlier run: engineering must clear them at startup.
psql_q "INSERT INTO comms_log (beacon_id, signal_strength, message, stardate) VALUES
  ('relay-theta-9', 94, 'channel open', 78000.0), ('relay-theta-9', 94, 'channel open', 78000.0),
  ('relay-theta-9', 94, 'channel open', 78000.0)" >/dev/null

start_demo "$(demo_dir 4)" 5201 5202 3520 3521
wait_for_sidecar 3520
wait_for_sidecar 3521

ENG="$(app_dir engineering)"
BEACON="$(app_dir subspace-beacon)"

wait_for_log "$ENG" engineering "engineering cleared comms_log for a fresh run" 180

# status_is <expected status> <expected lastSignalStrength or null; a|b for alternatives> <label>
status_is() {
  local result
  result="$(get_json "http://localhost:5201/comms/status")"
  assert_eq "200" "${result%% *}" "GET /comms/status answers 200"
  echo "${result#* }" | python3 -c '
import json, sys
pairs = json.load(sys.stdin, object_pairs_hook=lambda p: p)
assert [k for k, _ in pairs] == ["status", "lastSignalStrength"], pairs
r = dict(pairs)
assert r["status"] == sys.argv[1], r
assert json.dumps(r["lastSignalStrength"]) in sys.argv[2].split("|"), r
' "$1" "$2" || die "$3: wrong status: ${result#* }"
  echo "PASS: $3"
}

# Before the first tick the table is empty, but a ping may already have slipped in (signal 12),
# between the log check and the status call. Accept either.
status_is SEARCHING "null|12" "before the second ping: SEARCHING with null or 12"

# The cron binding fires every 5 s; the first tick comes one interval after the sidecar starts.
wait_for_log "$ENG" engineering 'engineering pinged relay-theta-9 signalStrength=27 message="static"' 120
status_is SEARCHING 27 "signal 27 is still SEARCHING"

wait_for_log "$ENG" engineering 'signalStrength=81 message="channel open"' 60
# The next tick may already have stored 94, so accept 81 or 94.
status_is ESTABLISHED "81|94" "signal 81 after 45, 63 is ESTABLISHED"

wait_for_log "$BEACON" subspace-beacon "subspace-beacon answered ping signalStrength=45" 10

assert_eq "12,27,45,63,81" "$(psql_q "SELECT string_agg(signal_strength::text, ',' ORDER BY id) FROM comms_log" | cut -d, -f1-5)" \
  "comms_log starts with 12,27,45,63,81 (leftovers cleared)"

echo "Demo 4 ($LANG_ARG) smoke test passed"
