# Venue Bookings with Dapr Bindings

Save and query venue bookings through the Dapr PostgreSQL output binding. Choose Python, .NET or Java. Each app uses the same database schema and component file.

## Layout

```text
venue-bookings/
  init.sql
  resources/postgres-binding.yaml
  python/
  dotnet/
    VenueBookings.sln
    src/VenueBookings/
    tests/VenueBookings.Tests/
  java/
    mvnw
    mvnw.cmd
    .mvn/wrapper/
    src/main/
    src/test/
```

`exec` runs the parameterized INSERT. `query` runs the SELECT through that same output binding. The query selects `event_date::text` so dates come back as `YYYY-MM-DD`.

## Choose a language

| Sample | Requirements | Request and response fields |
| --- | --- | --- |
| [Python](python/README.md) | Python 3.11+ and uv | `event_date`, `rows_affected` |
| [.NET](dotnet/README.md) | .NET 10 SDK | `event_date`, `rows_affected` |
| [Java](java/README.md) | JDK 21; Maven Wrapper included | `eventDate`; save returns only `status` |

Python and .NET use snake_case JSON. Java uses camelCase. The Java SDK does not expose binding response metadata, so the Java save response does not include an affected-row count.

All apps expose `POST /bookings` and `GET /bookings` on port 8006. Run one app at a time. A row saved through one language can be read through either of the others.

## Start PostgreSQL

Install Docker and the Dapr CLI, then run `dapr init`. From this folder, run:

```bash
docker run -d --name dapr_postgres -p 5432:5432 \
  -e POSTGRES_PASSWORD=dapr123 -e POSTGRES_DB=venuedb \
  --mount "type=bind,source=$(pwd)/init.sql,target=/docker-entrypoint-initdb.d/init.sql,readonly" \
  postgres:16
```

Wait for this command to print `1` before starting an app:

```bash
docker exec dapr_postgres psql -U postgres -d venuedb -tAc 'SELECT count(*) FROM information_schema.tables WHERE table_name = $$bookings$$;'
```

In PowerShell, run the container command on one line and use `${PWD}/init.sql` for the source path. The credentials in the component are for this local training database.

The SQL file runs only when Postgres initializes an empty data directory. To inspect saved rows:

```bash
docker exec dapr_postgres psql -U postgres -d venuedb -c 'SELECT * FROM bookings;'
```

Each language README has its build, run and test commands. Those commands point to the shared component using `--resources-path ../resources`.

## Cleanup

Stop the app with Ctrl+C. Remove the training container when finished:

```bash
docker rm -fv dapr_postgres
```
