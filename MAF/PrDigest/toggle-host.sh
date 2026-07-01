#!/usr/bin/env bash
# Toggle between "localhost" and "0.0.0.0" in launchSettings.json.
#
# Usage:
#   ./toggle-host.sh to-any    # replace localhost -> 0.0.0.0
#   ./toggle-host.sh to-local  # replace 0.0.0.0 -> localhost

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_FILE="$SCRIPT_DIR/PrDigest.AppHost/Properties/launchSettings.json"

usage() {
  echo "Usage: $0 {to-any|to-local}" >&2
  echo "  to-any    Replace 'localhost' with '0.0.0.0'" >&2
  echo "  to-local  Replace '0.0.0.0' with 'localhost'" >&2
  exit 1
}

if [[ $# -ne 1 ]]; then
  usage
fi

if [[ ! -f "$TARGET_FILE" ]]; then
  echo "Error: file not found: $TARGET_FILE" >&2
  exit 1
fi

case "$1" in
  to-any)
    sed -i 's/localhost/0.0.0.0/g' "$TARGET_FILE"
    echo "Replaced 'localhost' with '0.0.0.0' in $TARGET_FILE"
    ;;
  to-local)
    sed -i 's/0\.0\.0\.0/localhost/g' "$TARGET_FILE"
    echo "Replaced '0.0.0.0' with 'localhost' in $TARGET_FILE"
    ;;
  *)
    usage
    ;;
esac
