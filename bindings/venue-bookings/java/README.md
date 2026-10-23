# Venue Bookings in Java

A Spring Boot 4 app using Java 21. The committed Maven Wrapper downloads the required Maven version. On Windows, use `mvnw.cmd` in place of `bash ./mvnw`.

From the repository root:

```bash
cd bindings/venue-bookings/java
bash ./mvnw clean verify
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
dapr run --app-id venue-bookings --resources-path ../resources -- bash ./mvnw spring-boot:run
```

On Windows, use `dapr run --app-id venue-bookings --resources-path ../resources -- mvnw.cmd spring-boot:run`.

In another terminal, save and read a booking:

```bash
curl -X POST http://localhost:8006/bookings -H "Content-Type: application/json" -d '{"venue":"Grand Ballroom","eventDate":"2026-03-15"}'
curl http://localhost:8006/bookings
```

Java uses camelCase JSON for request and response records. The save response is `{"status":"saved"}`. The Dapr Java SDK only returns the binding payload, so it cannot expose the `rows-affected` metadata available in Python and .NET. A returned booking contains `id`, `venue` and `eventDate`. Its date stays `2026-03-15` because the SELECT casts it to text.

## Tests

```bash
bash ./mvnw test
```

Tests mock Dapr and check SQL operations and query responses, including an empty array. Spring supplies the configured Jackson mapper through constructor injection. Binding failures return HTTP 503 with a hint to check Dapr and Postgres.

Stop the app with Ctrl+C. See the [shared README](../README.md) for cleanup.
