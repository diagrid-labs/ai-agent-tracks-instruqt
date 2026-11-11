#!/usr/bin/env bash
# Starts RabbitMQ for Demo 6 and waits until it answers. Safe to run twice: it replaces
# the container named `rabbitmq` and touches nothing else.
set -euo pipefail

docker rm -f rabbitmq >/dev/null 2>&1 || true
# 5672 is AMQP (what Dapr connects to), 15672 is the management UI and API (guest/guest).
docker run -d --name rabbitmq -p 5672:5672 -p 15672:15672 rabbitmq:4.4.0-management >/dev/null

# Ping as the rabbitmq user: a root `docker exec` creates a root-owned .erlang.cookie before
# the broker starts, and the broker then crashes with eacces.
for i in $(seq 1 60); do
  if docker exec -u rabbitmq rabbitmq rabbitmq-diagnostics -q ping >/dev/null 2>&1; then
    echo "RabbitMQ is ready after ${i}s"
    exit 0
  fi
  sleep 1
done
echo "RabbitMQ did not become ready within 60s" >&2
exit 1
