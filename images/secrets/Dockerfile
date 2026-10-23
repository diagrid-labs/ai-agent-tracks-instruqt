# diagrid/university-secrets - the dapr-secrets track's thin layer over the shared base.
#
# It adds no tools. Its job is to leave the package caches warm, so a learner's first `dapr run`
# is seconds rather than a full cold restore - "caches that silently miss" is a named anti-goal
# of the design - and to carry the one script the lab's setup step needs.
#
# Build. The context is this directory; the demo sources come in as the named context `demos`,
# so the image's own files and the code it warms against stay separate:
#   docker build --platform=linux/amd64 -f images/secrets/Dockerfile \
#     --build-context demos=secrets --build-arg BASE_TAG=dev \
#     -t diagrid/university-secrets:dev images/secrets
ARG BASE_TAG=dev
FROM diagrid/university-base:${BASE_TAG}

# The demo code is NOT baked in: it is cloned at lab start so a demo fix reaches learners without
# an image rebuild (design decision 5). A COPY would leave the sources in a committed layer even
# if a later RUN deleted them, so the demos are bind-mounted for the duration of this RUN only.
# Everything below happens in one layer, so only the cache deltas survive.
#
# Warming against the build's own sources rather than a `git clone` of main is deliberate: a
# clone would warm the dependency set of a different commit, so a PR that adds a dependency would
# publish an image whose cache misses it.
#
# A warm failure FAILS the build (design §9.3). The VM checklist this replaces only warned,
# because a human was watching the output scroll past; in CI a red build is visible and a cold
# cache is not.
RUN --mount=type=bind,from=demos,target=/mnt/demos \
    set -eux; \
    cp -r /mnt/demos /opt/prewarm; \
    for demo in Demo1-ReadSecret Demo2-Scoping/AppA Demo2-Scoping/AppB; do \
        ( cd "/opt/prewarm/dotnet/$demo" && dotnet build ); \
        ( cd "/opt/prewarm/python/$demo" && uv sync ); \
        ( cd "/opt/prewarm/java/$demo"   && mvn -q -DskipTests package ); \
    done; \
    rm -rf /opt/prewarm; \
    chmod -R a+rX /opt/caches; \
    du -sh /opt/caches/nuget /opt/caches/uv /opt/caches/m2
# Demo3-SwapProvider is deliberately absent: it holds no application code of its own, it runs
# Demo1-ReadSecret against a different secret store. Warming Demo1 covers it.

# Last, so that editing it does not invalidate the warm-cache layer above.
# The lab's setup step calls this to seed Vault over its HTTP API. It lives in the image rather
# than in the lab's HCL so this repo's tests can exercise it, and rather than in the Vault
# container's entrypoint so it is not a property of a stock upstream image.
COPY files/seed-vault.sh /usr/local/bin/seed-vault.sh
RUN chmod 0755 /usr/local/bin/seed-vault.sh
