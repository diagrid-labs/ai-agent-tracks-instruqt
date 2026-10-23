# diagrid/university-base - the shared workstation image for the Dapr University tracks.
#
# Four language toolchains, the pinned Dapr CLI and runtime, and empty warm-cache directories
# that each per-track layer fills. Replaces the hand-pasted VM image checklist that used to live
# in dapr-university-instruqt/<track>/_setup/image-*-install.sh.
#
# Build (linux/amd64 only - Instruqt runs nothing else):
#   set -a; . images/versions.env; set +a
#   docker build --platform=linux/amd64 \
#     --build-arg DAPR_CLI_VERSION --build-arg DAPR_RUNTIME_VERSION \
#     -t diagrid/university-base:dev images/base
#
# NO DOCKER ENGINE IN THIS IMAGE. That is the point of the move off the VM: the lab declares
# Redis and Vault as their own containers, so the workstation needs no daemon and no privilege.
FROM ubuntu:24.04

ARG DAPR_CLI_VERSION
ARG DAPR_RUNTIME_VERSION

ENV DEBIAN_FRONTEND=noninteractive \
    DOTNET_CLI_TELEMETRY_OPTOUT=1 \
    DOTNET_NOLOGO=1

# An unpinned image is worse than no pin, because CI would assert a version nothing enforces.
RUN test -n "$DAPR_CLI_VERSION" && test -n "$DAPR_RUNTIME_VERSION" \
 || { echo "build args DAPR_CLI_VERSION and DAPR_RUNTIME_VERSION are required (see images/versions.env)" >&2; exit 1; }

# --- toolchains ------------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl wget git unzip \
 && rm -rf /var/lib/apt/lists/*

# .NET SDK 10 from Ubuntu's OWN noble feed. Do NOT add the Microsoft apt repo - it no longer
# carries .NET for Ubuntu and mixing it in collides with /usr/bin/dnx, which the distro package
# owns. Do NOT add ppa:dotnet/backports either: on noble it carries 9/7/6, not 10.
RUN apt-get update && apt-get install -y --no-install-recommends dotnet-sdk-10.0 \
 && rm -rf /var/lib/apt/lists/*

# Spring Boot 3.4.5 demos declare <java.version>17</java.version>.
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jdk maven \
 && rm -rf /var/lib/apt/lists/*

# 3.12 is the noble default; the demos require >=3.12 and run through uv.
RUN apt-get update && apt-get install -y --no-install-recommends python3 \
 && rm -rf /var/lib/apt/lists/*

# uv into /usr/local/bin, NOT $HOME/.local/bin: the Dapr CLI starts the Python demos with
# command: ["uv", "run", "python", "app.py"], so uv must resolve on the default PATH of every
# shell, not only one that sourced a profile.
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh \
 && uv --version

# Node 24, the fourth language.
RUN curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

# --- Dapr ---------------------------------------------------------------------------------------
# Pinned, unlike the VM checklist this replaces: a new Dapr version is now a new image, which is
# what makes a version bump a PR instead of a terminal session.
RUN wget -q https://raw.githubusercontent.com/dapr/cli/master/install/install.sh -O - \
    | /bin/bash -s "$DAPR_CLI_VERSION"

# Slim: installs daprd, placement and scheduler as binaries, with no containers and no daemon.
# It starts none of them - see start-control-plane.sh, which is this image's ENTRYPOINT.
RUN dapr init --slim --runtime-version "$DAPR_RUNTIME_VERSION"

# --- shared package caches (design §7.4) --------------------------------------------------------
# Three mechanisms, because three kinds of shell reach them: ENV for anything that inherits the
# container environment, /etc/profile.d for login shells that do not, and /etc/environment for
# PAM sessions that source neither. Maven has no variable at all, hence the global settings.xml.
ENV NUGET_PACKAGES=/opt/caches/nuget \
    UV_CACHE_DIR=/opt/caches/uv \
    npm_config_cache=/opt/caches/npm

COPY files/dapr-track-caches.sh /etc/profile.d/dapr-track-caches.sh
COPY files/maven-settings.xml /etc/maven/settings.xml
COPY files/start-control-plane.sh /usr/local/bin/start-control-plane.sh

RUN mkdir -p /opt/caches/nuget /opt/caches/uv /opt/caches/m2 /opt/caches/npm /var/lib/dapr-scheduler \
 && chmod -R a+rX /opt/caches \
 && chmod 0644 /etc/profile.d/dapr-track-caches.sh /etc/maven/settings.xml \
 && chmod 0755 /usr/local/bin/start-control-plane.sh \
 && printf '%s\n' \
      'NUGET_PACKAGES=/opt/caches/nuget' \
      'UV_CACHE_DIR=/opt/caches/uv' \
      'npm_config_cache=/opt/caches/npm' \
      'DOTNET_CLI_TELEMETRY_OPTOUT=1' \
      'DOTNET_NOLOGO=1' >> /etc/environment \
 && apt-get clean

# The control plane comes up before the learner's terminal does, then the container's own command
# takes over. exec "$@" is load-bearing: Instruqt uses this container as a terminal target.
ENTRYPOINT ["/usr/local/bin/start-control-plane.sh"]
CMD ["sleep", "infinity"]
