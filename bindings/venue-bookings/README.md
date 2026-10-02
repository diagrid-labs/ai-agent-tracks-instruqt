# Venue Bookings — Dapr Bindings API Demo

A small app, in three languages, that saves and queries venue bookings through a single Dapr **output binding** to PostgreSQL. Built for the Dapr University "Using the Dapr Bindings API with PostgreSQL" track.

## What this demonstrates

- **The Bindings API, not the State Store API.** The app never talks to Postgres directly. It calls `POST /v1.0/bindings/postgres-binding` with a SQL statement, and Dapr's `bindings.postgresql` component runs it.
- **One binding, two operations.** Postgres only has an output binding in Dapr (there's no such thing as a Postgres input binding: nothing about a database can reach into your app and trigger it). Saving and querying both go through `postgres-binding`, just with a different `operation`: `exec` for the INSERT, `query` for the SELECT.

## Languages

Each language is a self-contained, independently runnable app with its own dependency file, `resources/postgres-binding.yaml`, and `init.sql`:

| Folder | Stack | Notes |
|---|---|---|
| [`python/`](python/) | FastAPI + `dapr` SDK | Reports `rows_affected` on save (from the binding's response metadata). |
| [`dotnet/`](dotnet/) | ASP.NET Core minimal API + `Dapr.AspNetCore` (brings in `Dapr.Client`) | Reports `rows_affected` on save. |
| [`java/`](java/) | Spring Boot + `io.dapr:dapr-sdk` | Can't report `rows_affected`: the Java SDK's `invokeBinding` doesn't expose response metadata the way Python and .NET do. See that folder's README. |

## Endpoints (same shape in every language)

| Method | Path | Binding operation | What it does |
|---|---|---|---|
| `POST` | `/bookings` | `exec` | Inserts a row: `{"venue": "...", "event_date"/"eventDate": "YYYY-MM-DD"}` |
| `GET` | `/bookings` | `query` | Returns every row as `{"bookings": [...]}` |

Each language's own README has exact setup, run, and test commands.

## Resources

Every language folder carries its own copy of:
- `resources/postgres-binding.yaml` — the one Dapr component both endpoints use, `type: bindings.postgresql`.
- `init.sql` — creates the `bookings` table. Mount it into the Postgres container's `/docker-entrypoint-initdb.d/` so it runs on first boot.
