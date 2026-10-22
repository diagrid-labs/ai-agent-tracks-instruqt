# diagrid/university-secrets - the dapr-secrets track's thin layer over the shared base.
#
# It adds no tools. Its entire job is to leave the package caches warm, so a learner's first
# `dapr run` is seconds rather than a full cold restore - "caches that silently miss" is a named
# anti-goal of the design, and a cold cache costs minutes of a 30-minute track.
#
# Build (context is the repo's secrets/ folder, NOT the repo root):
#   docker build --platform=linux/amd64 -f images/secrets/Dockerfile \
#     --build-arg BASE_TAG=dev -t diagrid/university-secrets:dev secrets
ARG BASE_TAG=dev
FROM diagrid/university-base:${BASE_TAG}

# The demo code is NOT baked in: it is cloned at lab start so a demo fix reaches learners without
# an image rebuild (design decision 5). A COPY would leave the sources in a committed layer even
# if a later RUN deleted them, so the context is bind-mounted for the duration of this RUN only -
# it is never part of the image. Everything below happens in one layer, so only the cache deltas
# survive.
#
# A warm failure FAILS the build (design §9.3). The VM checklist this replaces only warned,
# because a human was watching the output scroll past; in CI a red build is visible and a cold
# cache is not.
RUN --mount=type=bind,source=.,target=/mnt/demos \
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
