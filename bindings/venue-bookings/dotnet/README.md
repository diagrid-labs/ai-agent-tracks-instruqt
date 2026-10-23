# Venue Bookings in .NET

An ASP.NET Core app targeting .NET 10. The solution contains separate app and test projects.

From the repository root:

```bash
cd bindings/venue-bookings/dotnet
dotnet build
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
dapr run --app-id venue-bookings --resources-path ../resources -- dotnet run --project src/VenueBookings
```

In another terminal, save and read a booking:

```bash
curl -X POST http://localhost:8006/bookings -H "Content-Type: application/json" -d '{"venue":"Grand Ballroom","event_date":"2026-03-15"}'
curl http://localhost:8006/bookings
```

The app configures snake_case JSON for both endpoints. The save response is `{"status":"saved","rows_affected":"1"}`. A returned booking contains `id`, `venue` and `event_date`. Its date stays `2026-03-15` because the SELECT casts it to text.

## Tests

```bash
dotnet test
```

Running this command from `dotnet/` discovers the solution and runs the test project. The tests mock Dapr and check operations, SQL parameters and parsing of query results, including `[]`.

A binding failure returns HTTP 503 with a hint to check Dapr and Postgres. Stop the app with Ctrl+C. See the [shared README](../README.md) for cleanup.
