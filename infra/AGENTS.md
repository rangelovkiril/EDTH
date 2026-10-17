# infra — deployment and server-side configuration

Everything server-side is declarative and lives here; no custom backend.

| Path | What |
|------|------|
| `rpi/` | Podman quadlet, env example, forced-command deploy script for the Pis |
| `emqx/` | EMQX Operator CRD, rules, Postgres sink, authn/ACL (see its `AGENTS.md`) |
| `grafana/` | Provisioned datasource and dashboard |
| `sql/` | Postgres schema |

Secrets never go in git: commit `*.example`, keep the real file gitignored.
