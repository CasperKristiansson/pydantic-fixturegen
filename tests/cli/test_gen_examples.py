from __future__ import annotations

from pathlib import Path

import yaml
from pydantic_fixturegen.cli import app as cli_app
from tests._cli import create_cli_runner

runner = create_cli_runner()


OPENAPI_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Example", "version": "1.0.0"},
    "paths": {
        "/users": {
            "get": {
                "responses": {
                    "200": {
                        "description": "ok",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/User"}
                            }
                        },
                    }
                }
            }
        }
    },
    "components": {
        "schemas": {
            "User": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                },
            }
        }
    },
}


def test_gen_examples_injects_payloads(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.yaml"
    out_path = tmp_path / "out.yaml"
    spec_path.write_text(yaml.safe_dump(OPENAPI_SPEC), encoding="utf-8")

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "examples",
            str(spec_path),
            "--out",
            str(out_path),
        ],
    )

    assert result.exit_code == 0, result.output
    updated = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    example = updated["components"]["schemas"]["User"].get("example")
    assert example
    assert set(example.keys()) >= {"id", "name"}
