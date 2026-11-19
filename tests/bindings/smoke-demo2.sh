#!/usr/bin/env bash
# Smoke test for bindings Demo 2 (cron input + PostgreSQL output binding). Needs the bindings
# Postgres (tests/bindings/start-postgres.sh).
# Usage: smoke-demo2.sh dotnet|python|java
source "$(dirname "$0")/lib.sh" "$@"

require_postgres
assert_ports_free 5201 3520

# A leftover row from an earlier run. The app must clear the table at startup.
psql_q "INSERT INTO warp_core_readings (reading_id, stardate, core_temp_k, plasma_flow) VALUES ('stale-1', 1.0, 900, 0.80) ON CONFLICT DO NOTHING" >/dev/null

start_demo "$(demo_dir 2)" 5201 3520
wait_for_sidecar 3520

ENG="$(app_dir engineering)"

wait_for_log "$ENG" engineering "engineering cleared warp_core_readings for a fresh run" 180
assert_eq "0" "$(psql_q "SELECT count(*) FROM warp_core_readings WHERE reading_id = 'stale-1'")" \
  "stale row is gone after the startup clear"

# The first tick waits for the startup gate, so wc-0001 must survive the clear.
wait_for_log "$ENG" engineering "engineering stored reading wc-0001 in warp_core_readings" 60

RESULT="$(get_json "http://localhost:5201/readings?minTemp=-5")"
assert_eq "200" "${RESULT%% *}" "GET /readings?minTemp=-5 answers 200"
echo "${RESULT#* }" | python3 -c '
import json, re, sys
rows = json.load(sys.stdin, object_pairs_hook=lambda p: p)  # keep key order as a list of pairs
assert isinstance(rows, list) and rows, rows
row = next((r for r in rows if dict(r)["readingId"] == "wc-0001"), None)
assert row is not None, rows
assert [k for k, _ in row] == ["readingId", "stardate", "coreTempK", "plasmaFlow", "recordedAt"], row
r = dict(row)
assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", r["recordedAt"]), r
assert isinstance(r["coreTempK"], int) and 850 <= r["coreTempK"] <= 950, r
assert 0.70 <= r["plasmaFlow"] <= 1.00 and r["stardate"] > 78000, r
' || die "wc-0001 is missing from GET /readings or has the wrong shape: ${RESULT#* }"
echo "PASS: wc-0001 is returned with the five keys in order and an ISO recordedAt"

RESULT="$(get_json "http://localhost:5201/readings?minTemp=951")"
assert_eq "200 []" "$RESULT" "minTemp=951 returns an empty array"

for bad in "" abc 9.5 99999999; do
  RESULT="$(get_json "http://localhost:5201/readings?minTemp=$bad")"
  assert_eq "400" "${RESULT%% *}" "minTemp='$bad' answers 400"
  echo "${RESULT#* }" | python3 -c '
import json, sys
assert json.load(sys.stdin) == {"error": "INVALID_MIN_TEMP"}
' || die "minTemp='$bad' should answer {\"error\": \"INVALID_MIN_TEMP\"}: ${RESULT#* }"
done
echo "PASS: invalid minTemp values answer INVALID_MIN_TEMP"

# Purge: a row older than one minute disappears at the next 30 s tick.
psql_q "INSERT INTO warp_core_readings (reading_id, stardate, core_temp_k, plasma_flow) VALUES ('old-1', 1.0, 900, 0.80)" >/dev/null
psql_q "UPDATE warp_core_readings SET recorded_at = now() - interval '2 minutes' WHERE reading_id = 'old-1'" >/dev/null
# A purge line from an earlier tick does not count, so wait for a new one.
PURGES_BEFORE="$(count_log "$ENG" engineering "engineering purged old readings")"
i=0
while [ "$(count_log "$ENG" engineering "engineering purged old readings")" -le "$PURGES_BEFORE" ]; do
  i=$((i + 1))
  [ "$i" -le 45 ] || die "no new 'engineering purged old readings' line after 45s"
  sleep 1
done
assert_eq "0" "$(psql_q "SELECT count(*) FROM warp_core_readings WHERE reading_id = 'old-1'")" \
  "old-1 was purged"

echo "Demo 2 ($LANG_ARG) smoke test passed"
