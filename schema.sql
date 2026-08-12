-- Throughline schema. Idempotent: safe to run on every boot.
--
-- The shape here follows from one requirement in the product spec: the
-- north-star metric is "divergence rate per field, per jurisdiction, over time,
-- and it should fall." That is a time-series question, not a relational one.
-- Storing only a current snapshot would answer "how wrong is the record today"
-- and permanently destroy the ability to answer "is it getting better", which
-- is the question an agency actually has to answer to a court or a funder.
--
-- So every reconciliation run appends observations rather than overwriting, and
-- the rate is derived. This mirrors the claim store's append-only design: we
-- never collapse history, because that collapse is the failure we exist to
-- detect.

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ---------------------------------------------------------------------------
-- Runs. One row per reconciliation.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS runs (
    run_id            text PRIMARY KEY,
    started_at        timestamptz NOT NULL,
    finished_at       timestamptz,
    healthy           boolean NOT NULL DEFAULT false,
    entities_resolved integer NOT NULL DEFAULT 0,
    claims            integer NOT NULL DEFAULT 0,
    divergences_total integer NOT NULL DEFAULT 0,
    divergence_rate   double precision NOT NULL DEFAULT 0,
    elapsed_ms        integer NOT NULL DEFAULT 0,
    coverage          jsonb,
    sources           jsonb,
    adjudication      jsonb
);

-- ---------------------------------------------------------------------------
-- The hypertable. One row per divergence, per run.
--
-- Partitioned on observed_at because every query we serve is time-scoped:
-- "the rate this week", "this field over the last month", "did it fall after
-- the agency refreshed". Chunking on that axis is what makes those cheap.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS divergence_observations (
    observed_at   timestamptz NOT NULL,
    run_id        text NOT NULL,
    divergence_id text NOT NULL,
    entity_key    text NOT NULL,
    subject       text NOT NULL,
    field         text NOT NULL,
    kind          text NOT NULL,
    severity      text NOT NULL,
    confidence    double precision NOT NULL,
    source        text,
    adjudicated   boolean NOT NULL DEFAULT false,
    detail        text
);

SELECT create_hypertable(
    'divergence_observations', 'observed_at',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_obs_kind_time
    ON divergence_observations (kind, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_obs_severity_time
    ON divergence_observations (severity, observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_obs_run
    ON divergence_observations (run_id, observed_at DESC);

-- ---------------------------------------------------------------------------
-- Claims, kept for provenance. A divergence is only defensible if the raw
-- record behind it can still be produced on demand.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS claim_observations (
    fetched_at  timestamptz NOT NULL,
    run_id      text NOT NULL,
    claim_id    text NOT NULL,
    entity_key  text NOT NULL,
    subject     text NOT NULL,
    field       text NOT NULL,
    value       text,
    source      text NOT NULL,
    source_url  text NOT NULL,
    observed_at timestamptz,
    sha256      text NOT NULL,
    raw         jsonb
);

SELECT create_hypertable(
    'claim_observations', 'fetched_at',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_claim_id ON claim_observations (claim_id, fetched_at DESC);

-- ---------------------------------------------------------------------------
-- Continuous aggregate: the north-star metric, pre-computed.
--
-- This is the reason we are on TimescaleDB rather than plain Postgres. The
-- dashboard chart reads pre-materialised buckets instead of scanning every
-- observation ever recorded, so the chart stays fast as history grows — which
-- for a longitudinal benchmark is the entire point, since the dataset only
-- ever gets longer and the benchmark is worthless if it is not longitudinal.
-- ---------------------------------------------------------------------------
CREATE MATERIALIZED VIEW IF NOT EXISTS divergence_rate_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', observed_at) AS bucket,
    kind,
    severity,
    count(*)                    AS observations,
    count(DISTINCT entity_key)  AS entities_affected,
    avg(confidence)             AS mean_confidence
FROM divergence_observations
GROUP BY bucket, kind, severity
WITH NO DATA;

-- Refresh recent buckets automatically. start_offset NULL so the very first
-- backfill covers all existing history rather than only the recent window.
SELECT add_continuous_aggregate_policy(
    'divergence_rate_hourly',
    start_offset      => NULL,
    end_offset        => INTERVAL '1 minute',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists     => TRUE
);

-- ---------------------------------------------------------------------------
-- Compression. Observations are append-only and never updated after their
-- chunk closes, which is precisely the access pattern columnar compression is
-- for. Segmenting by kind keeps same-kind rows adjacent.
-- ---------------------------------------------------------------------------
ALTER TABLE divergence_observations SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'kind, severity',
    timescaledb.compress_orderby   = 'observed_at DESC'
);

SELECT add_compression_policy(
    'divergence_observations', INTERVAL '7 days', if_not_exists => TRUE
);
