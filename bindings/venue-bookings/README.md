# Venue Bookings — Dapr Bindings API Demo

A small FastAPI app that saves and queries venue bookings through a single Dapr **output binding** to PostgreSQL. Built for the Dapr University "Using the Dapr Bindings API with PostgreSQL" track.

## What this demonstrates

- **The Bindings API, not the State Store API.** The app never talks to Postgres directly. It calls `POST /v1.0/bindings/postgres-binding` with a SQL statement, and Dapr's `bindings.postgresql` component runs it.
- **One binding, two operations.** Postgres only has an output binding in Dapr (there's no such thing as a Postgres input binding: nothing about a database can reach into your app and trigger it). Saving and querying both go through `postgres-binding`, just with a different `operation`: `exec` for the INSERT, `query` for the SELECT.

## Endpoints

| Method | Path | Binding operation | What it does |
|---|---|---|---|
| `POST` | `/bookings` | `exec` | Inserts a row: `{"venue": "...", "event_date": "YYYY-MM-DD"}` |
| `GET` | `/bookings` | `query` | Returns every row as `{"bookings": [...]}` |

## Setup

```bash
cd bindings/venue-bookings
uv sync
```

## Run

Requires the Dapr CLI (`dapr init`) and a local Postgres container reachable at `localhost:5432` (see `init.sql` for the schema it expects, and `resources/postgres-binding.yaml` for the connection string).

```bash
uv run dapr run --app-id venue-bookings --resources-path ./resources -- python app.py
```

Save a booking:

```bash
curl -X POST http://localhost:8006/bookings \
  -H "Content-Type: application/json" \
  -d '{"venue": "Grand Ballroom", "event_date": "2026-03-15"}'
```

Read them back:

```bash
curl http://localhost:8006/bookings
```

## Tests

```bash
uv run pytest
```

Unit tests mock `DaprClient`, so they don't need a running sidecar or database. They assert that each endpoint calls the binding with the right operation and SQL.

## Resources

- `resources/postgres-binding.yaml` — the one Dapr component both endpoints use, `type: bindings.postgresql`.
- `init.sql` — creates the `bookings` table. Mount it into the Postgres container's `/docker-entrypoint-initdb.d/` so it runs on first boot.

## Files

- `app.py` — the whole app: two endpoints, one binding, two operations.
- `init.sql` — schema for the `bookings` table.
