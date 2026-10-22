#!/usr/bin/env bash
# The image/lab contract (design §8): what the Instruqt lab is allowed to assume the image gives it.
#
# Usage: contract.sh [image-tag]      default: $IMAGE_BASE
# Task 6 reuses this against the image PULLED from Docker Hub, which is the only run that proves
# what Instruqt will actually stream.
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
# shellcheck source=lib.sh
. ./lib.sh

IMAGE="${1:-$IMAGE_BASE}"
CONTAINER="contract-test-$$"

echo "== image/lab contract: $IMAGE =="

cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# Start the image the way Instruqt does: its own ENTRYPOINT, then terminals exec into it.
# Bypassing the entrypoint with --entrypoint would test an image nobody runs.
if ! docker run -d --name "$CONTAINER" "$IMAGE" sleep infinity >/dev/null 2>&1; then
    fail "could not start $IMAGE (is it built? run the Task 2 build first)"
fi

# The entrypoint waits for the control plane before exec'ing the command, so a container that is
# still 'created' after 60s never got there.
for _ in $(seq 1 60); do
    [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" = "true" ] && break
    sleep 1
done
if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" != "true" ]; then
    echo "--- container logs ---" >&2
    docker logs "$CONTAINER" 2>&1 | tail -20 >&2
    fail "container did not reach Running within 60s"
fi

# in_container <shell-flags> <script>   runs inside the image under test
dex()  { docker exec "$CONTAINER" sh -c "$1" 2>&1; }
dexl() { docker exec "$CONTAINER" sh -lc "$1" 2>&1; }

# --- 1. every tool resolves in BOTH a login and a non-login shell (Review Focus 1) -------------
# Instruqt check scripts run as `sh -c`, which sources neither /etc/profile nor a user rc file.
# A tool that only resolves in a login shell is a check script that fails for no visible reason.
for tool in dapr dotnet java mvn python3 uv node npm git; do
    check_ok "non-login shell resolves $tool" -- docker exec "$CONTAINER" sh -c "command -v $tool"
    check_ok "login shell resolves $tool"     -- docker exec "$CONTAINER" sh -lc "command -v $tool"
done

# --- 2. the cache variables are set in the shells the learner actually gets --------------------
check_eq "NUGET_PACKAGES in a non-login shell"   "/opt/caches/nuget" "$(dex 'echo $NUGET_PACKAGES')"
check_eq "UV_CACHE_DIR in a non-login shell"     "/opt/caches/uv"    "$(dex 'echo $UV_CACHE_DIR')"
check_eq "npm_config_cache in a non-login shell" "/opt/caches/npm"   "$(dex 'echo $npm_config_cache')"

# The same three via /etc/profile.d, with the image ENV stripped: this is the fallback that
# catches a shell which did not inherit the container environment.
check_eq "NUGET_PACKAGES via /etc/profile.d (env stripped)" "/opt/caches/nuget" \
    "$(docker exec "$CONTAINER" env -i /bin/sh -lc 'echo $NUGET_PACKAGES' 2>&1)"
check_eq "UV_CACHE_DIR via /etc/profile.d (env stripped)"   "/opt/caches/uv" \
    "$(docker exec "$CONTAINER" env -i /bin/sh -lc 'echo $UV_CACHE_DIR' 2>&1)"

# /etc/environment is read by PAM, not by sh, so it cannot be exercised through docker exec.
# Assert its contents instead - the honest level of proof available here.
check_ok "/etc/environment carries NUGET_PACKAGES" -- \
    docker exec "$CONTAINER" grep -q '^NUGET_PACKAGES=/opt/caches/nuget$' /etc/environment
check_ok "/etc/environment carries UV_CACHE_DIR" -- \
    docker exec "$CONTAINER" grep -q '^UV_CACHE_DIR=/opt/caches/uv$' /etc/environment

# Maven has no environment variable (design §7.4), so the global settings.xml is the mechanism.
check_ok "/etc/maven/settings.xml points at /opt/caches/m2" -- \
    docker exec "$CONTAINER" grep -q '<localRepository>/opt/caches/m2</localRepository>' /etc/maven/settings.xml
# ...and Maven itself agrees. This one reaches the network to fetch the help plugin; Task 3's
# offline `mvn -o` build is the stronger behavioural proof, but this is the one that fails loudly
# if the settings file is in the wrong place for this Maven version.
check_eq "mvn resolves localRepository to the shared cache" "/opt/caches/m2" \
    "$(dex 'mvn -q help:evaluate -Dexpression=settings.localRepository -DforceStdout 2>/dev/null | tail -1')"

# --- 3. the cache root exists and is world-readable --------------------------------------------
# Readable by every user, so switching the workstation to `run_as` later cannot silently
# orphan the warm caches (design §9.5).
for cache in nuget uv m2 npm; do
    check_ok "/opt/caches/$cache exists and is world-readable" -- \
        docker exec "$CONTAINER" sh -c "test -d /opt/caches/$cache && test -r /opt/caches/$cache"
done

# --- 4. the installed Dapr CLI matches versions.env exactly (Review Focus 6) --------------------
check_eq "Dapr CLI matches versions.env" "$DAPR_CLI_VERSION" \
    "$(dex 'dapr -v' | awk '/CLI version/ {print $NF}')"

# --- 5. no Docker client, so nothing can quietly depend on a daemon (design §7.1, §8) -----------
check_ok "no docker client in the image" -- \
    docker exec "$CONTAINER" sh -c '! command -v docker'

# --- 6. the Dapr runtime and all three slim binaries (Task 1: SLIM+LOCAL) -----------------------
check_eq "Dapr runtime matches versions.env" "$DAPR_RUNTIME_VERSION" \
    "$(dex 'dapr -v' | awk '/Runtime version/ {print $NF}')"
for bin in daprd placement scheduler; do
    check_ok "slim binary $bin is installed and executable" -- \
        docker exec "$CONTAINER" sh -c "test -x /root/.dapr/bin/$bin"
done

# --- 6b. no CRLF in the shipped scripts ---------------------------------------------------------
# core.autocrlf=true (the Windows default) rewrites these on checkout, and a CRLF shebang fails
# inside the image with "/usr/bin/env: 'bash\r': No such file or directory" - i.e. the workstation
# does not start at all. .gitattributes pins eol=lf; this proves it held all the way into the image.
CR="$(printf '\r')"
check_ok "entrypoint script has no CRLF line endings" -- \
    docker exec "$CONTAINER" sh -c "! grep -q '$CR' /usr/local/bin/start-control-plane.sh"
check_ok "profile.d cache script has no CRLF line endings" -- \
    docker exec "$CONTAINER" sh -c "! grep -q '$CR' /etc/profile.d/dapr-track-caches.sh"

# --- 7. the entrypoint actually brought the control plane up (Task 1, §9.1) ---------------------
# A TCP connect, not a health endpoint: both services speak gRPC, and "the port is listening" is
# what daprd needs. Readiness proper (healthz 204) is asserted in Task 4 with a sidecar running.
for port_name in "50005 placement" "50006 scheduler"; do
    set -- $port_name
    check_ok "control plane: $2 is listening on $1" -- \
        docker exec "$CONTAINER" bash -c "exec 3<>/dev/tcp/127.0.0.1/$1"
done
# Both must survive: placement and scheduler default to the same healthz/metrics ports, so a
# naive entrypoint starts both and silently loses the second (Task 1).
for proc in placement scheduler; do
    check_ok "control plane: $proc process is alive" -- \
        docker exec "$CONTAINER" pgrep -f "/root/.dapr/bin/$proc"
done

summary "contract.sh"
