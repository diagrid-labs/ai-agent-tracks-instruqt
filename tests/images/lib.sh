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
export IMAGE_BASE IMAGE_SECRETS REPO_ROOT

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
