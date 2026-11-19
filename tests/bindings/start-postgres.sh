#!/usr/bin/env bash
# Starts PostgreSQL for the bindings demos and waits until the tables exist. Safe to run
# twice: it replaces the container named `bindings-postgres` and touches nothing else.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

docker rm -f bindings-postgres >/dev/null 2>&1 || true
# Bound to 127.0.0.1 only, so the demo credentials are not exposed. The init script in
# bindings/sql creates the tables on first start.
docker run -d --name bindings-postgres -p 127.0.0.1:5432:5432 \
  -e POSTGRES_USER=dapr -e POSTGRES_PASSWORD=dapr -e POSTGRES_DB=dapr \
  -v "$ROOT/bindings/sql:/docker-entrypoint-initdb.d:ro" \
  postgres:18.7 >/dev/null

# The init script runs after the first "ready", so wait for the table, not just pg_isready.
for i in $(seq 1 60); do
  if docker exec bindings-postgres pg_isready -U dapr -d dapr >/dev/null 2>&1 &&
     docker exec bindings-postgres psql -U dapr -d dapr -tAc 'SELECT 1 FROM comms_log' >/dev/null 2>&1; then
    echo "Postgres is ready after ${i}s"
    exit 0
  fi
  sleep 1
done
echo "Postgres did not become ready within 60s" >&2
exit 1
