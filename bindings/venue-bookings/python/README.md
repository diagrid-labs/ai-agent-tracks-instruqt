# Venue Bookings in Python

A FastAPI app with one Dapr client shared for the app's lifetime. Python 3.11+ and uv are required.

From the repository root:

```bash
cd bindings/venue-bookings/python
uv sync --frozen
```

## Start PostgreSQL

Install Docker and the Dapr CLI, then run `dapr init`. From this language folder, start the shared training database:

```bash
docker run -d --name dapr_postgres -p 5432:5432 \
  -e POSTGRES_PASSWORD=dapr123 -e POSTGRES_DB=venuedb \
  --mount "type=bind,source=$(cd .. && pwd)/init.sql,target=/docker-entrypoint-initdb.d/init.sql,readonly" \
  postgres:16
```

In PowerShell, use the same command on one line with `source=${PWD}/../init.sql`. If the container is already running from another language's walkthrough, keep using it.

Wait for this command to print `1`:

```bash
docker exec dapr_postgres psql -U postgres -d venuedb -tAc 'SELECT count(*) FROM information_schema.tables WHERE table_name = $$bookings$$;'
```

The shared component connects to `localhost:5432` with user `postgres`, password `dapr123` and database `venuedb`. The shared `init.sql` creates the `bookings` table at first boot.


## Run

```bash
uv run dapr run --app-id venue-bookings --resources-path ../resources -- python app.py
```

In another terminal, save and read a booking:

```bash
curl -X POST http://localhost:8006/bookings -H "Content-Type: application/json" -d '{"venue":"Grand Ballroom","event_date":"2026-03-15"}'
curl http://localhost:8006/bookings
```

Responses use snake_case. The save response is `{"status":"saved","rows_affected":"1"}`. A returned booking contains `id`, `venue` and `event_date`. Its date stays `2026-03-15` because the SELECT casts the database date to text.

## Test and lint

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Unit tests mock Dapr. They check the HTTP contract, SQL parameters, plain-date responses, an empty result array and reuse of the client. A binding failure returns HTTP 503 with a hint to check Dapr and Postgres.

Stop the app with Ctrl+C. See the [shared README](../README.md) for cleanup.
