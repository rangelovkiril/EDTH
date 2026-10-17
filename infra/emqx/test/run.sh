#!/bin/sh
# Local check of emqx.crd.yaml: EMQX + Postgres in podman, then e2e.py. Needs podman, python with
# pyyaml and paho-mqtt (set PYTHON to override), ports 1883/18083 free.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
emqx_dir=$(dirname "$here")
sql=$(dirname "$emqx_dir")/sql/001_init.sql
PYTHON=${PYTHON:-python}
EMQX_IMAGE=${EMQX_IMAGE:-docker.io/emqx/emqx:6.3.2}
work=$(mktemp -d)
trap 'podman rm -f emqx-test pg-test >/dev/null 2>&1; podman network rm edth-test >/dev/null 2>&1; rm -rf "$work"' EXIT

mkdir "$work/secrets"
printf 'user_id,password,is_superuser\nrpi-1,pw1,false\nrpi-2,pw2,false\nviewer,pwv,false\n' > "$work/secrets/users.csv"
printf 'pgpass' > "$work/secrets/pg_password"
chmod -R a+rX "$work"

"$PYTHON" "$here/crd_to_conf.py" "$emqx_dir/emqx.crd.yaml" \
  --set connectors.pgsql.edth_pg.server=pg-test:5432 \
  --set connectors.pgsql.edth_pg.username=postgres \
  --set 'connectors.pgsql.edth_pg.ssl={"enable":false}' \
  --set 'listeners.tcp.default={"enable":true,"bind":"0.0.0.0:1883"}' \
  --set 'listeners.ssl.default={"enable":false}' > "$work/emqx.conf"

podman network create edth-test >/dev/null
podman run -d --name pg-test --network edth-test -e POSTGRES_PASSWORD=pgpass -e POSTGRES_DB=edth \
  docker.io/library/postgres:16 >/dev/null
until podman exec pg-test pg_isready -U postgres -d edth >/dev/null 2>&1; do sleep 1; done
sleep 2
podman exec -i pg-test psql -U postgres -d edth -q -v ON_ERROR_STOP=1 < "$sql"

podman run -d --name emqx-test --network edth-test -p 1883:1883 -p 18083:18083 \
  -v "$work/secrets:/opt/emqx/etc/secrets:ro,Z" \
  -v "$emqx_dir/acl.conf:/opt/emqx/etc/acl/acl.conf:ro,Z" \
  -v "$work/emqx.conf:/opt/emqx/etc/emqx.conf:ro,Z" "$EMQX_IMAGE" >/dev/null
i=0
until curl -sf -m3 localhost:18083/status >/dev/null; do
  i=$((i + 1)); [ "$i" -gt 60 ] && { podman logs emqx-test | tail -20; exit 1; }
  sleep 2
done
sleep 5
"$PYTHON" "$here/e2e.py"
