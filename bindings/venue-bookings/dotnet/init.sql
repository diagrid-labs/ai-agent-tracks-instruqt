-- Runs automatically the first time the Postgres container starts
-- (mounted into /docker-entrypoint-initdb.d/ by sandbox-setup.sh).
CREATE TABLE IF NOT EXISTS bookings (
    id SERIAL PRIMARY KEY,
    venue TEXT NOT NULL,
    event_date DATE NOT NULL
);
