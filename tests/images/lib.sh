#!/usr/bin/env bash
# Shared helpers for the container image tests.
#
# The thing under test is an image, not a library, so every assertion runs inside a container.
# Sourced by contract.sh, caches-secrets.sh, smoke-demo1.sh and smoke-demo3.sh.

# Git Bash (MSYS) rewrites arguments that look like absolute paths, turning /root/.dapr/bin/placement
# into C:/Program Files/Git/root/... before docker ever sees it. Harmless and unused on Linux/CI.
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL='*'

IMAGE_BASE="${IMAGE_BASE:-diagrid/university-base:dev}"
IMAGE_SECRETS="${IMAGE_SECRETS:-diagrid/university-secrets:dev}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# `docker -v` needs a path the Docker daemon understands. Under Git Bash that is C:/dev/... ,
# not the /c/dev/... that pwd reports; on Linux and in CI the two are the same string.
if command -v cygpath >/dev/null 2>&1; then
    REPO_ROOT_HOST="$(cygpath -m "$REPO_ROOT")"
else
    REPO_ROOT_HOST="$REPO_ROOT"
fi

export IMAGE_BASE IMAGE_SECRETS REPO_ROOT REPO_ROOT_HOST

# The versions the image claims to carry. One owner: images/versions.env.
if [ -f "$REPO_ROOT/images/versions.env" ]; then
    # shellcheck disable=SC1091
    set -a; . "$REPO_ROOT/images/versions.env"; set +a
fi

CHECKS_RUN=0

fail() {
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

pass() {
    CHECKS_RUN=$((CHECKS_RUN + 1))
    printf 'ok %2d  %s\n' "$CHECKS_RUN" "$*"
}

# check_eq <label> <expected> <actual>
check_eq() {
    if [ "$2" = "$3" ]; then
        pass "$1"
    else
        fail "$1
       expected: [$2]
       actual:   [$3]"
    fi
}

# check_ok <label> -- <command...>   passes when the command exits 0
check_ok() {
    local label="$1"; shift
    [ "$1" = "--" ] && shift
    local out
    if out="$("$@" 2>&1)"; then
        pass "$label"
    else
        fail "$label
       command: $*
       output:  ${out:-<empty>}"
    fi
}

summary() {
    printf '\n%s: %d checks passed\n' "${1:-suite}" "$CHECKS_RUN"
}

# --- the lab topology ---------------------------------------------------------------------------
# A local stand-in for what sandbox.hcl will declare: the workstation plus Redis and Vault as
# their OWN containers, reached by service name over one network. No Docker socket and no
# privilege in the workstation - if a test ever needs either, the design has been broken (§8).
LAB_NETWORK="${LAB_NETWORK:-dapr-lab}"
WS="${WS:-ws}"

stop_topology() {
    docker rm -f "$WS" lab-redis lab-vault >/dev/null 2>&1 || true
    docker network rm "$LAB_NETWORK" >/dev/null 2>&1 || true
}

start_topology() {
    stop_topology
    docker network create "$LAB_NETWORK" >/dev/null || fail "could not create network $LAB_NETWORK"

    docker run -d --name lab-redis --network "$LAB_NETWORK" --network-alias redis \
        redis:7 >/dev/null || fail "could not start redis"

    # Dev mode: in-memory, root token "root". Same shape as the sandbox setup it replaces.
    docker run -d --name lab-vault --network "$LAB_NETWORK" --network-alias vault \
        --cap-add=IPC_LOCK \
        -e VAULT_DEV_ROOT_TOKEN_ID=root -e VAULT_DEV_LISTEN_ADDRESS=0.0.0.0:8200 \
        hashicorp/vault:1.20 >/dev/null || fail "could not start vault"

    # The workstation runs its real ENTRYPOINT, so the control plane is up before any dapr run.
    docker run -d --name "$WS" --network "$LAB_NETWORK" -v "$REPO_ROOT_HOST:/src:ro" \
        "$IMAGE_SECRETS" sleep infinity >/dev/null || fail "could not start the workstation"

    local i
    for i in $(seq 1 60); do
        [ "$(docker inspect -f '{{.State.Running}}' "$WS" 2>/dev/null)" = "true" ] && return 0
        sleep 1
    done
    fail "workstation did not reach Running within 60s"
}

# Everything the lab's setup step does before a learner sees the page: clone the demo repo (here,
# copy it from the read-only mount) and write secrets.json from the committed template, which is
# the single owner of the secret values.
prepare_workspace() {
    docker exec "$WS" sh -c '
        rm -rf /work && mkdir -p /work
        cp -r /src/secrets /work/secrets
        rm -rf /work/secrets/*/*/bin /work/secrets/*/*/obj /work/secrets/*/*/*/bin /work/secrets/*/*/*/obj
        cp /work/secrets/secrets.example.json /work/secrets/secrets.json
    ' || fail "could not prepare the workspace in the workstation"
}

stop_dapr() {
    docker exec "$WS" sh -c 'pkill -f "dapr run" ; pkill -f daprd ; pkill -f "dotnet run" ; pkill -f spring-boot ; pkill -f uvicorn' >/dev/null 2>&1 || true
    sleep 3
}

# Polls rather than sleeping a fixed time: the lab starts these containers in parallel, so a
# component can load before the service behind it answers (Review Focus 4).
wait_for_url() {
    local url="$1" timeout="${2:-120}" i
    for ((i = 0; i < timeout; i++)); do
        if docker exec "$WS" curl -sf -o /dev/null "$url" 2>/dev/null; then
            return 0
        fi
        sleep 1
    done
    return 1
}
