# Venue Bookings (Java) — Dapr Bindings API Demo

A small Spring Boot app that saves and queries venue bookings through a single Dapr **output binding** to PostgreSQL. Built for the Dapr University "Using the Dapr Bindings API with PostgreSQL" track.

## What this demonstrates

- **The Bindings API, not the State Store API.** The app never talks to Postgres directly. It calls `POST /v1.0/bindings/postgres-binding` with a SQL statement, and Dapr's `bindings.postgresql` component runs it.
- **One binding, two operations.** Postgres only has an output binding in Dapr (there's no such thing as a Postgres input binding: nothing about a database can reach into your app and trigger it). Saving and querying both go through `postgres-binding`, just with a different `operation`: `exec` for the INSERT, `query` for the SELECT.

## Endpoints

| Method | Path | Binding operation | What it does |
|---|---|---|---|
| `POST` | `/bookings` | `exec` | Inserts a row: `{"venue": "...", "eventDate": "YYYY-MM-DD"}` |
| `GET` | `/bookings` | `query` | Returns every row as `{"bookings": [...]}` |

> [!NOTE]
> Unlike the Python and .NET versions, this one can't report `rows_affected` on save. The Java Dapr SDK's `invokeBinding` doesn't expose response metadata alongside the payload, only the .NET and Python SDKs do that.

## Setup

```bash
cd bindings/venue-bookings/java
mvn clean install
```

## Run

Requires the Dapr CLI (`dapr init`) and a local Postgres container reachable at `localhost:5432` (see `init.sql` for the schema it expects, and `resources/postgres-binding.yaml` for the connection string).

```bash
dapr run --app-id venue-bookings --resources-path ./resources -- mvn spring-boot:run
```

Save a booking:

```bash
curl -X POST http://localhost:8006/bookings -H "Content-Type: application/json" -d '{"venue": "Grand Ballroom", "eventDate": "2026-03-15"}'
```

Read them back:

```bash
curl http://localhost:8006/bookings
```

## Tests

```bash
mvn test
```

Unit tests mock `DaprClient` (via Mockito), so they don't need a running sidecar or database. They assert that each method calls the binding with the right operation and SQL.

## Resources

- `resources/postgres-binding.yaml` — the one Dapr component both endpoints use, `type: bindings.postgresql`.
- `init.sql` — creates the `bookings` table. Mount it into the Postgres container's `/docker-entrypoint-initdb.d/` so it runs on first boot.

## Files

- `BookingsController.java` — the two endpoints.
- `BookingsService.java` — the binding calls: one method per operation.
- `init.sql` — schema for the `bookings` table.
