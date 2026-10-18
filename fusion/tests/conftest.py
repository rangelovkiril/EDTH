import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

SCHEMAS = Path(__file__).resolve().parents[2] / "docs"


@pytest.fixture(scope="session")
def validate():
    validators = {
        name: Draft202012Validator(json.loads((SCHEMAS / f"{name}.schema.json").read_text()))
        for name in ("fix", "track")
    }

    def check(name, payload):
        validators[name].validate(json.loads(json.dumps(payload)))

    return check
