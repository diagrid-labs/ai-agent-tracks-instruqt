#!/usr/bin/env bash
# The per-track layer's warm caches (design §7.4, anti-goal §4).
#
# Usage: caches-secrets.sh [image-tag]     default: $IMAGE_SECRETS
#
# "Caches that silently miss" is a named anti-goal: a cold cache costs a learner minutes of a
# 30-minute track while the image reports success. The only honest proof that a cache HIT is a
# build that cannot reach the network, so the three language builds below run with
# --network none. Check 4 is the other half: a dependency the cache does not have must still
# build, slowly, rather than fail.
set -uo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"
# shellcheck source=lib.sh
. ./lib.sh

IMAGE="${1:-$IMAGE_SECRETS}"

echo "== warm caches: $IMAGE =="

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    fail "image $IMAGE does not exist (build the Task 3 layer first)"
fi

# The control-plane entrypoint is irrelevant to a build test and costs an etcd start per
# container, so these runs go straight to a shell. contract.sh is what covers the entrypoint.
run_in_image() {
    docker run --rm --entrypoint sh "$@"
}

# --- 1. the caches are populated, not merely present (design §8) --------------------------------
# An empty but existing cache directory is exactly the silent miss this suite exists to catch.
for cache in nuget uv m2; do
    size_mb="$(run_in_image "$IMAGE" -c "du -sm /opt/caches/$cache 2>/dev/null | cut -f1")"
    if [ -z "$size_mb" ] || [ "$size_mb" -lt 10 ]; then
        fail "/opt/caches/$cache holds ${size_mb:-0} MB; expected >= 10 MB of warmed packages"
    fi
    pass "/opt/caches/$cache is warm (${size_mb} MB)"
done

# --- 2. the demo code is NOT baked in (design decision 5) ---------------------------------------
# The demos are cloned at lab start so a demo fix reaches learners without an image rebuild.
# The layer clones only to warm the caches, and must delete the checkout in the same layer.
check_ok "the prewarm checkout is not in the published image" -- \
    run_in_image "$IMAGE" -c '! test -d /opt/prewarm'

# --- 3. OFFLINE builds — the real proof of a cache hit (Review Focus 2) -------------------------
# The repo is copied in, not built in place: these write bin/, obj/, target/ and .venv/, and the
# mount is read-only precisely so a test cannot scribble on the working tree.
offline_build() {
    local label="$1" dir="$2" cmd="$3" out
    if out="$(docker run --rm --network none --entrypoint sh \
        -v "$REPO_ROOT_HOST:/src:ro" "$IMAGE" -c "
            set -e
            cp -r /src/secrets /work
            rm -rf /work/*/*/bin /work/*/*/obj /work/*/*/*/bin /work/*/*/*/obj
            cd /work/$dir
            $cmd
        " 2>&1)"; then
        pass "offline build: $label"
    else
        fail "offline build: $label
       dir:     $dir
       command: $cmd
       output:  $(printf '%s' "$out" | tail -15)"
    fi
}

offline_build ".NET (dotnet build, no network)"   "dotnet/Demo1-ReadSecret" "dotnet build"
offline_build "Python (uv sync, no network)"      "python/Demo1-ReadSecret" "uv sync --offline"
offline_build "Java (mvn -o package, no network)" "java/Demo1-ReadSecret"   "mvn -o -q -DskipTests package"

# --- 4. a dependency the cache does NOT have still builds (Review Focus 3) ----------------------
# Demos gain packages after an image is built. That must degrade to slow, not broken - an
# offline-only suite would call this a failure and the image would look stricter than it is.
if out="$(docker run --rm --entrypoint sh -v "$REPO_ROOT_HOST:/src:ro" "$IMAGE" -c '
        set -e
        cp -r /src/secrets /work
        rm -rf /work/*/*/bin /work/*/*/obj
        cd /work/dotnet/Demo1-ReadSecret
        sed -i "s#</Project>#  <ItemGroup><PackageReference Include=\"Newtonsoft.Json\" Version=\"13.0.3\" /></ItemGroup>\n</Project>#" Demo1-ReadSecret.csproj
        grep -q Newtonsoft Demo1-ReadSecret.csproj
        dotnet build
    ' 2>&1)"; then
    pass "a package the cache lacks is fetched, not fatal (networked build)"
else
    fail "a cache miss broke the build instead of merely slowing it
       output: $(printf '%s' "$out" | tail -15)"
fi

summary "caches-secrets.sh"
