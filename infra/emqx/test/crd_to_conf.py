"""Extract spec.config.roots from emqx.crd.yaml as an emqx.conf (JSON is valid HOCON).

Used by the local test harness only. Optional substitutions make it runnable on one machine:
  crd_to_conf.py emqx.crd.yaml --set connectors.pgsql.edth_pg.server=pg-test:5432 ...
"""

import argparse
import json

import yaml


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("crd")
    ap.add_argument("--set", action="append", default=[], metavar="PATH=JSON")
    args = ap.parse_args()
    roots = yaml.safe_load(open(args.crd))["spec"]["config"]["roots"]
    for item in args.set:
        path, _, raw = item.partition("=")
        try:
            value = json.loads(raw)
        except ValueError:
            value = raw
        node = roots
        *parents, leaf = path.split(".")
        for key in parents:
            node = node[key]
        node[leaf] = value
    roots["node"] = {"name": "emqx@127.0.0.1", "cookie": "testcookie", "data_dir": "data"}
    roots["cluster"] = {"name": "emqxcl", "discovery_strategy": "manual"}
    print(json.dumps(roots, indent=2))


if __name__ == "__main__":
    main()
