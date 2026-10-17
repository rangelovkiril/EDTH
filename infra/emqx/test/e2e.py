"""Publish good/bad detections to a local EMQX and assert routing, ACL and Postgres rows.

Needs paho-mqtt, plus `podman exec pg-test psql` for the database checks (see run.sh).
"""

import json
import subprocess
import sys
import time

import paho.mqtt.client as mqtt

V2 = mqtt.CallbackAPIVersion.VERSION2
failures = []


def check(name, ok, detail=""):
    print(("ok   " if ok else "FAIL ") + name + (f"  {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def client(user, password, cid=None):
    c = mqtt.Client(V2, client_id=cid or user)
    c.username_pw_set(user, password)
    c.connect("localhost", 1883)
    c.loop_start()
    return c


def psql(query):
    out = subprocess.check_output(
        ["podman", "exec", "pg-test", "psql", "-U", "postgres", "-d", "edth", "-tAc", query]
    )
    return out.decode().strip()


got = []
viewer = client("viewer", "pwv")
viewer.on_message = lambda c, u, m: got.append((m.topic, json.loads(m.payload)))
viewer.subscribe("detections/#")
n1 = client("rpi-1", "pw1")
time.sleep(1)

now = time.time()
good = {"node": "rpi-1", "t": now, "az": 123.456, "el": 12.3, "conf": 0.82, "frame": 7}
det = "nodes/rpi-1/detections"
for payload in (
    good,
    {**good, "conf": 0.3},
    {**good, "az": 400},
    {k: v for k, v in good.items() if k != "el"},
    {**good, "node": "rpi-2"},
):
    n1.publish(det, json.dumps(payload))
n1.publish("nodes/rpi-2/detections", json.dumps({**good, "node": "rpi-2"}))  # spoof: ACL denies
n1.publish("nodes/rpi-1/status", json.dumps({"node": "rpi-1", "t": now, "fps": 29.7}))
n1.publish(
    "nodes/rpi-1/status", json.dumps({"node": "rpi-1", "t": now, "fps": 30.0, "temp_c": 51.5})
)
viewer.publish(det, json.dumps(good))  # viewer may not publish
time.sleep(2.5)

clean = [p for t, p in got if t == "detections/clean/rpi-1"]
rejected = [p for t, p in got if t == "detections/rejected/rpi-1"]
check("one clean detection", len(clean) == 1, str(clean))
check(
    "clean has latency_ms and ingest_ms", clean and {"latency_ms", "ingest_ms"} <= clean[0].keys()
)
check(
    "reasons",
    sorted(p["reason"] for p in rejected) == ["low_conf", "node_mismatch", "range", "range"],
    str([p["reason"] for p in rejected]),
)
check("nothing for rpi-2 (spoof denied)", not any(t.endswith("rpi-2") for t, _ in got))
check("pg detections == 1", psql("select count(*) from detections") == "1")
check("pg rejected == 4", psql("select count(*) from detections_rejected") == "4")
check("pg status == 2", psql("select count(*) from node_status") == "2")
check(
    "pg absent status field is NULL",
    psql("select count(*) from node_status where temp_c is null") == "1",
)

bad = []
c = mqtt.Client(V2, client_id="rpi-1x")
c.username_pw_set("rpi-1", "wrong")
c.on_connect = lambda c, u, f, r, p: bad.append(r.is_failure)
c.connect("localhost", 1883)
c.loop_start()
time.sleep(1.5)
check("wrong password rejected", bad == [True], str(bad))

sys.exit(1 if failures else 0)
