import argparse
import json
from pathlib import Path

import uvicorn

from .app import create_app


def main(argv=None):
    parser = argparse.ArgumentParser(description="EDTH local USB camera observation bench")
    parser.add_argument("--config", type=Path, help="JSON config; omit for synthetic demo")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Config/data directory")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    config = json.loads((args.root / args.config).read_text()) if args.config else {"mode": "demo"}
    uvicorn.run(create_app(config, args.root), host=args.host, port=args.port, log_level="info")
