-- Tables for the Dapr bindings demos. Postgres runs this file once, on the first start of
-- the container (see tests/bindings/start-postgres.sh).
CREATE TABLE IF NOT EXISTS warp_core_readings (
  reading_id   TEXT PRIMARY KEY,
  stardate     NUMERIC(8,1) NOT NULL,
  core_temp_k  INTEGER NOT NULL,
  plasma_flow  NUMERIC(3,2) NOT NULL,
  recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS comms_log (
  id               SERIAL PRIMARY KEY,
  beacon_id        TEXT NOT NULL,
  signal_strength  INTEGER NOT NULL,
  message          TEXT NOT NULL,
  stardate         NUMERIC(8,1) NOT NULL,
  pinged_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
