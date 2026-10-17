-- Applied once to the Exoscale DBaaS Postgres database used by EMQX and Grafana.
-- Idempotent: safe to re-run.

CREATE TABLE IF NOT EXISTS detections (
  ts          timestamptz      NOT NULL,                 -- node capture time (payload.t)
  ingest_ts   timestamptz      NOT NULL DEFAULT now(),   -- when the broker stored it
  node        text             NOT NULL,
  az          double precision NOT NULL,
  el          double precision NOT NULL,
  conf        double precision NOT NULL,
  frame       bigint           NOT NULL,
  latency_ms  double precision               -- broker time minus node time; also a clock-sanity signal
);
CREATE INDEX IF NOT EXISTS detections_ts_idx ON detections (ts DESC);
CREATE INDEX IF NOT EXISTS detections_node_ts_idx ON detections (node, ts DESC);

CREATE TABLE IF NOT EXISTS detections_rejected (
  ingest_ts   timestamptz NOT NULL DEFAULT now(),
  node        text        NOT NULL,
  reason      text        NOT NULL                       -- low_conf | range | node_mismatch
);
CREATE INDEX IF NOT EXISTS detections_rejected_ts_idx ON detections_rejected (ingest_ts DESC);

CREATE TABLE IF NOT EXISTS node_status (
  ts               timestamptz      NOT NULL,            -- node time (payload.t)
  ingest_ts        timestamptz      NOT NULL DEFAULT now(),
  node             text             NOT NULL,
  fps              double precision,
  temp_c           double precision,
  clock_offset_ms  double precision
);
CREATE INDEX IF NOT EXISTS node_status_node_ts_idx ON node_status (node, ts DESC);

-- Read-only role for Grafana.
-- CREATE ROLE grafana LOGIN PASSWORD '...';  -- create via the DBaaS console, not in git
-- GRANT SELECT ON detections, detections_rejected, node_status TO grafana;
