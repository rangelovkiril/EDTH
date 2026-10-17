# infra/emqx — broker configuration

Declarative EMQX for the demo: validation, routing and storage with no custom backend.
Contract: [`../../docs/contract.md`](../../docs/contract.md).

## Files

| File | What |
|------|------|
| `emqx.crd.yaml` | `EMQX` custom resource (Operator 3.x, `apps.emqx.io/v3beta1`). **Single source of truth**: `spec.config.roots` holds listeners, authn/authz, Postgres connector/actions and rules |
| `acl.conf` | File ACL, shipped as ConfigMap `edth-emqx-acl` by `kustomization.yaml` |
| `certificate.yaml` | cert-manager Certificate for the TLS listener |
| `secrets.example.yaml` | Shape of Secret `edth-emqx-secrets`; the real `secrets.yaml` is gitignored |
| `test/` | Local check against a throwaway EMQX + Postgres in podman |

Postgres schema: `../sql/001_init.sql`.

## Rules

| Rule | Input | Does |
|------|-------|------|
| `det_accept` | `nodes/+/detections` | `conf >= 0.5`, range checks, `payload.node` = topic id → Postgres `detections` + `detections/clean/{id}` (adds `ingest_ms`, `latency_ms`) |
| `det_reject` | `nodes/+/detections` | complement, with `reason` = `node_mismatch` \| `range` \| `low_conf` → Postgres `detections_rejected` + `detections/rejected/{id}` |
| `status_sink` | `nodes/+/status` | → Postgres `node_status` |

Access: nodes authenticate with username = `NODE_ID`; the ACL lets a client publish only under
`nodes/<its clientid>/`. User `viewer` may subscribe to `detections/#` and `nodes/#`.

## Apply

```sh
kubectl apply -f secrets.yaml          # from secrets.example.yaml
kubectl apply -k .                     # EMQX CR, ACL ConfigMap, Certificate
```

Edit before applying: the Postgres host/database/user in `emqx.crd.yaml` (EMQX does not
expand `${ENV}` in config, so these are literals), and `dnsNames`/issuer in `certificate.yaml`.

## Local check

```sh
PYTHON=/path/to/python-with-paho-and-pyyaml ./test/run.sh
```

Extracts `spec.config.roots`, runs it on EMQX 6.3.2 with Postgres, and asserts accepted/rejected
routing, the ACL, bad passwords and the Postgres rows.

## Things that bit us (verified on EMQX 6.3.2)

- Config values cannot reference environment variables. Secrets use `file://` references.
- The bootstrap CSV header must be `user_id,password,is_superuser` for `bootstrap_type: plain`.
- JSON `null` reaches Postgres as the string `"null"` and fails the insert; hence the contract
  omits unavailable `status` fields instead of sending `null`.
- The `file` authz source takes `path` only, not inline rules.
- 6.x ships under the EMQX Community License: **one node** is free; a cluster needs a licence key
  (`license_key` in the Secret, `replicas: 1` otherwise).
- Operator 2.x used `apps.emqx.io/v2beta1` with a HOCON string; 3.x uses `v3beta1` with YAML.
