#!/usr/bin/env bash
# Shared helpers for the pub/sub smoke tests. Source it from a smoke script:
#
#   source "$(dirname "$0")/lib.sh" "$@"
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

start_demo() {
  [ -d "$1" ] || die "demo dir $1 does not exist"
  DEMO_DIR="$(cd "$1" && pwd)"
  mkdir -p "$DEMO_DIR/.dapr"
  cd "$DEMO_DIR" || die "cannot cd to $DEMO_DIR"
  dapr run -f . >"$DEMO_DIR/.dapr/smoke-run.log" 2>&1 &
  DEMO_PID=$!
  trap "stop_demo '$DEMO_DIR'" EXIT
}

stop_demo() {
  local dir="${1:-$DEMO_DIR}"
  trap - EXIT
  [ -n "$dir" ] && (cd "$dir" && dapr stop -f . >/dev/null 2>&1)
  if [ -n "$DEMO_PID" ]; then
    kill "$DEMO_PID" >/dev/null 2>&1
    wait "$DEMO_PID" >/dev/null 2>&1
    DEMO_PID=""
  fi
  return 0
}

wait_for_sidecar() {
  local port="$1" timeout="${2:-180}" i=0 status
  while [ "$i" -lt "$timeout" ]; do
    status="$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:$port/v1.0/healthz" 2>/dev/null)"
    [ "$status" = "204" ] && return 0
    sleep 1
    i=$((i + 1))
  done
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
  out="$(curl -s -w '\n%{http_code}' -X POST -H 'Content-Type: application/json' -d "$2" "$1")" \
    || die "POST $1 failed"
  status="$(echo "$out" | tail -n 1)"
  body="$(echo "$out" | sed '$d')"
  echo "$status $body"
}

assert_eq() {
  [ "$1" = "$2" ] || die "$3 (expected '$1', got '$2')"
  echo "PASS: $3"
}
