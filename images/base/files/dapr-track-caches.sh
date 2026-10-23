# Shared package caches for the Dapr University tracks.
#
# These are also set as image ENV, which is what a `docker exec` terminal inherits. This file is
# the fallback for a login shell that did not inherit the container environment; /etc/environment
# is the third, for PAM sessions that source neither. The caches live outside any one user's home
# because the image build and the learner's terminal are not guaranteed to run as the same user.
#
# Note this does not by itself make the image `run_as`-ready: the Dapr runtime is in /root/.dapr
# and /root is 0700, so a named user would need the Dapr install moved too.
export NUGET_PACKAGES=/opt/caches/nuget
export UV_CACHE_DIR=/opt/caches/uv
export npm_config_cache=/opt/caches/npm
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_NOLOGO=1
