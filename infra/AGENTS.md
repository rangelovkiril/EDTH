# infra — deployment and server-side configuration

Everything server-side is declarative and lives here; no custom backend.

| Path | What |
|------|------|
| `rpi/` | Podman quadlet, env example, forced-command deploy script for the Pis |
| `emqx/` | EMQX Operator CRD, rules, Postgres sink, authn/ACL (see its `AGENTS.md`) |
| `grafana/` | Provisioned datasource and dashboard |
| `sql/` | Postgres schema |

Secrets never go in git: commit `*.example`, keep the real file gitignored.

## Grafana

`grafana/datasource.yaml` and `dashboards.yaml` are Grafana provisioning files; `edth.json` is
the dashboard. Give Grafana `PG_HOST`, `PG_PORT`, `PG_USER`, `PG_DATABASE`, `PG_PASSWORD` in its
environment (read-only role). The datasource uses `sslmode: require`; switch to `verify-full`
with the DBaaS CA for stricter checking. Panels: connected nodes (status < 15 s old), accepted and
rejected detections, p95 latency, FPS, clock offset, temperature, latest detections.

Broker-level metrics (connected clients, message rates, rule/sink counters) are in the EMQX
Dashboard; node metrics are not. A true connected-clients series would need the EMQX Prometheus
endpoint and a scraper, which this demo does not include.
