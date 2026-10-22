#!/usr/bin/env bash
# Start the Dapr control plane inside this container, then hand over to the container's command.
#
# Why this exists (design §9.1, settled by the Task 1 spike):
# `dapr init --slim` installs daprd, placement and scheduler as binaries but starts none of them,
# while `dapr run` passes --placement-host-address localhost:50005 and
# --scheduler-host-address localhost:50006 regardless of whether the app uses actors, jobs or
# workflow. With nothing listening there the sidecar serves its APIs but never becomes ready:
# GET /v1.0/healthz answers 500 ERR_HEALTH_NOT_READY forever.
#
# Starting the two binaries here - rather than declaring control-plane containers in the lab -
# keeps the ports on the defaults `dapr run` already assumes, so no demo's dapr.yaml ever needs
# --placement-host-address or --scheduler-host-address. That matters for every track, not just
# this one.
set -uo pipefail

DAPR_BIN="${DAPR_BIN:-/root/.dapr/bin}"
PLACEMENT_PORT="${PLACEMENT_PORT:-50005}"
SCHEDULER_PORT="${SCHEDULER_PORT:-50006}"
SCHEDULER_DATA_DIR="${SCHEDULER_DATA_DIR:-/var/lib/dapr-scheduler}"
LOG_DIR="${DAPR_CONTROL_PLANE_LOG_DIR:-/var/log}"

# Waits for a TCP listener. bash's /dev/tcp is used rather than ss or nc so the image needs no
# extra package for its own startup check.
wait_for_port() {
    local port="$1" name="$2" i
    for ((i = 0; i < 60; i++)); do
        if (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
            exec 3>&- 3<&-
            return 0
        fi
        sleep 0.5
    done
    return 1
}

mkdir -p "$SCHEDULER_DATA_DIR" "$LOG_DIR"

"$DAPR_BIN/placement" >"$LOG_DIR/placement.log" 2>&1 &

# The scheduler must be moved off 8080/9090: placement and scheduler BOTH default to those for
# healthz and metrics, so the second one to start otherwise dies with
# "listen tcp :8080: bind: address already in use" and the sidecar never becomes ready.
# --etcd-data-dir is explicit because its default is ./data, relative to the working directory,
# and it grows to ~123 MB - unset, a scheduler started from a demo folder writes that into the
# learner's checkout.
"$DAPR_BIN/scheduler" \
    --port "$SCHEDULER_PORT" \
    --healthz-port 8081 \
    --metrics-port 9091 \
    --etcd-data-dir "$SCHEDULER_DATA_DIR" \
    >"$LOG_DIR/scheduler.log" 2>&1 &

control_plane_ok=true
for svc in "placement:$PLACEMENT_PORT" "scheduler:$SCHEDULER_PORT"; do
    name="${svc%%:*}"
    port="${svc##*:}"
    if ! wait_for_port "$port" "$name"; then
        control_plane_ok=false
        echo "start-control-plane: $name did not listen on $port within 30s." >&2
        echo "start-control-plane: last lines of $LOG_DIR/$name.log --" >&2
        tail -20 "$LOG_DIR/$name.log" >&2 2>/dev/null || true
    fi
done

# Degrade, do not die. A sidecar without the control plane still serves the Secrets and State
# APIs (Task 1) - only /v1.0/healthz fails - so killing the workstation here would turn a
# degraded lab into a dead one. The contract test asserts the ports, which is what catches this.
if [ "$control_plane_ok" != true ]; then
    echo "start-control-plane: continuing without a healthy control plane; dapr run will work" >&2
    echo "start-control-plane: but /v1.0/healthz will answer 500 ERR_HEALTH_NOT_READY." >&2
fi

if [ "$#" -eq 0 ]; then
    exec sleep infinity
fi
exec "$@"
