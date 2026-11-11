#!/usr/bin/env bash
# Shared helpers for the pub/sub smoke tests. Source it from a smoke script:
#
#   source "$(dirname "$0")/lib.sh" "$@"
#
# Usage: start_demo <demo-dir> [port...] passes the demo's ports (app + Dapr HTTP) so
# stop_demo can verify they are free afterwards and kill leftovers.
#
# Works with bash 3.2 (macOS) and Linux. Every helper that fails prints a message to
# stderr and exits non-zero.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

LANG_ARG="${1:-}"
case "$LANG_ARG" in
  dotnet|python|java) ;;
  *) echo "usage: $(basename "$0") dotnet|python|java" >&2; exit 2 ;;
esac

DEMO_DIR=""
DEMO_PID=""
DEMO_PORTS=""

die() {
  echo "FAIL: $*" >&2
  exit 1
}

# Prints a prefix that is unique per run, so order ids from an earlier run (still
# sitting in Redis) never match this run's assertions.
run_id() {
  echo "r$(date +%s)"
}

port_in_use() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
  else
    nc -z localhost "$1" >/dev/null 2>&1
  fi
}

assert_ports_free() {
  local p
  for p in "$@"; do
    if port_in_use "$p"; then
      die "port $p is already in use"
    fi
  done
}

# Resolves an app dir: absolute paths stay as they are, relative ones are relative to
# the demo dir given to start_demo.
resolve_dir() {
  case "$1" in
    /*) echo "$1" ;;
    *) echo "${DEMO_DIR:-.}/$1" ;;
  esac
}

# start_demo <demo-dir> [port...]
# The optional ports (app and Dapr HTTP ports of the demo) are remembered so stop_demo
# can wait for them to close and kill whatever still holds them.
start_demo() {
  [ -d "$1" ] || die "demo dir $1 does not exist"
  DEMO_DIR="$(cd "$1" && pwd)"
  shift
  DEMO_PORTS="$*"
  mkdir -p "$DEMO_DIR/.dapr"
  cd "$DEMO_DIR" || die "cannot cd to $DEMO_DIR"
  dapr run -f . >"$DEMO_DIR/.dapr/smoke-run.log" 2>&1 &
  DEMO_PID=$!
  trap "stop_demo '$DEMO_DIR'" EXIT
}

# Kills a process and all its descendants.
kill_tree() {
  local pid="$1" child
  for child in $(pgrep -P "$pid" 2>/dev/null); do
    kill_tree "$child"
  done
  kill "$1" >/dev/null 2>&1
}

ports_busy() {
  local p busy=""
  for p in $DEMO_PORTS; do
    port_in_use "$p" && busy="$busy $p"
  done
  echo "${busy# }"
}

# Stops the demo and makes sure its ports are free: dapr stop, then wait up to 15 s,
# then kill the process tree and whatever still listens on the demo's ports.
stop_demo() {
  local dir="${1:-$DEMO_DIR}" i=0 busy p pid
  trap - EXIT
  [ -n "$dir" ] && (cd "$dir" && dapr stop -f . >/dev/null 2>&1)
  if [ -n "$DEMO_PID" ]; then
    kill_tree "$DEMO_PID"
    wait "$DEMO_PID" >/dev/null 2>&1
    DEMO_PID=""
  fi
  while [ "$i" -lt 15 ] && [ -n "$(ports_busy)" ]; do
    sleep 1
    i=$((i + 1))
  done
  busy="$(ports_busy)"
  if [ -n "$busy" ]; then
    for p in $busy; do
      for pid in $(lsof -t -nP -iTCP:"$p" -sTCP:LISTEN 2>/dev/null); do
        kill_tree "$pid"
      done
    done
    sleep 2
    busy="$(ports_busy)"
    for p in $busy; do
      for pid in $(lsof -t -nP -iTCP:"$p" -sTCP:LISTEN 2>/dev/null); do
        kill -9 "$pid" >/dev/null 2>&1
      done
    done
    sleep 1
    busy="$(ports_busy)"
    [ -n "$busy" ] && echo "WARNING: port(s) $busy still in use after stop_demo; kill the leaked process manually" >&2
  fi
  return 0
}

demo_log_tail() {
  if [ -n "$DEMO_DIR" ] && [ -f "$DEMO_DIR/.dapr/smoke-run.log" ]; then
    echo "---- last 40 lines of $DEMO_DIR/.dapr/smoke-run.log ----" >&2
    tail -n 40 "$DEMO_DIR/.dapr/smoke-run.log" >&2
  fi
}

# Fails fast if `dapr run` dies; on any failure shows the tail of smoke-run.log.
wait_for_sidecar() {
  local port="$1" timeout="${2:-180}" i=0 status
  while [ "$i" -lt "$timeout" ]; do
    status="$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$port/v1.0/healthz" 2>/dev/null)"
    [ "$status" = "204" ] && return 0
    if [ -n "$DEMO_PID" ] && ! kill -0 "$DEMO_PID" 2>/dev/null; then
      demo_log_tail
      die "dapr run exited before the sidecar on port $port became healthy"
    fi
    # `dapr run` stays alive when only the app fails to start, so also look for its message.
    if grep -q "The App process exited" "$DEMO_DIR/.dapr/smoke-run.log" 2>/dev/null; then
      demo_log_tail
      die "the app process exited before the sidecar on port $port became healthy"
    fi
    sleep 1
    i=$((i + 1))
  done
  demo_log_tail
  die "Dapr sidecar on port $port not healthy after ${timeout}s"
}

# Prints the newest app log (not the daprd log) of an app.
app_log() {
  local dir
  dir="$(resolve_dir "$1")"
  # shellcheck disable=SC2012
  ls -t "$dir"/.dapr/logs/"$2"_app_*.log 2>/dev/null | head -n 1
}

wait_for_log() {
  local dir="$1" app="$2" needle="$3" timeout="${4:-60}" i=0 log
  while [ "$i" -lt "$timeout" ]; do
    log="$(app_log "$dir" "$app")"
    if [ -n "$log" ] && grep -qF -- "$needle" "$log"; then
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  die "'$needle' not found in $app log after ${timeout}s"
}

count_log() {
  local log
  log="$(app_log "$1" "$2")"
  if [ -z "$log" ]; then
    echo 0
    return 0
  fi
  grep -cF -- "$3" "$log"
  return 0
}

# Prints "<status> <body>".
post_json() {
  local out status body
  out="$(curl -s --max-time 30 -w '\n%{http_code}' -X POST -H 'Content-Type: application/json' -d "$2" "$1")" \
    || die "POST $1 failed"
  status="$(echo "$out" | tail -n 1)"
  body="$(echo "$out" | sed '$d')"
  echo "$status $body"
}

assert_eq() {
  [ "$1" = "$2" ] || die "$3 (expected '$1', got '$2')"
  echo "PASS: $3"
}
