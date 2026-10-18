import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

SCHEMAS = Path(__file__).resolve().parents[2] / "docs"


@pytest.fixture(scope="session")
def validate():
    validators = {
        name: Draft202012Validator(json.loads((SCHEMAS / f"{name}.schema.json").read_text()))
        for name in ("detection", "status", "fix", "ray")
    }

    def check(name, payload):
        # Round-trip through JSON so we validate exactly what goes on the wire.
        validators[name].validate(json.loads(json.dumps(payload)))

    return check
