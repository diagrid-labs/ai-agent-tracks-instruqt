-- Mount this file at /docker-entrypoint-initdb.d/init.sql when creating Postgres.
-- Postgres runs it once when initializing an empty data directory.
CREATE TABLE IF NOT EXISTS bookings (
    id SERIAL PRIMARY KEY,
    venue TEXT NOT NULL,
    event_date DATE NOT NULL
);
