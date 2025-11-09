from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from pydantic import BaseModel
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli.gen import examples as examples_module
from pydantic_fixturegen.core.errors import DiscoveryError
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


def test_gen_examples_skips_non_model_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec_path = tmp_path / "spec.yaml"
    out_path = tmp_path / "out.yaml"
    spec_path.write_text(yaml.safe_dump(OPENAPI_SPEC), encoding="utf-8")

    class DummyIngester:
        def ingest_openapi(self, *args: object, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(path=tmp_path / "generated.py")

    monkeypatch.setattr(examples_module, "SchemaIngester", DummyIngester)
    monkeypatch.setattr(
        examples_module,
        "_load_module_from_path",
        lambda path: SimpleNamespace(User=object()),
    )

    class DummyGenerator:
        def __init__(self, config: object) -> None:
            self.config = config

        def generate_one(self, model: type[BaseModel]) -> None:
            return None

    monkeypatch.setattr(examples_module, "InstanceGenerator", DummyGenerator)

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
    assert "example" not in updated["components"]["schemas"]["User"]


def test_gen_examples_skips_when_generator_returns_none(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec_path = tmp_path / "spec.yaml"
    out_path = tmp_path / "out.yaml"
    spec_path.write_text(yaml.safe_dump(OPENAPI_SPEC), encoding="utf-8")

    class DummyModel(BaseModel):
        id: int

    class DummyIngester:
        def ingest_openapi(self, *args: object, **kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(path=tmp_path / "generated.py")

    monkeypatch.setattr(examples_module, "SchemaIngester", DummyIngester)
    monkeypatch.setattr(
        examples_module,
        "_load_module_from_path",
        lambda path: SimpleNamespace(User=DummyModel),
    )

    class DummyGenerator:
        def __init__(self, config: object) -> None:
            self.config = config

        def generate_one(self, model: type[BaseModel]) -> None:
            return None

    monkeypatch.setattr(examples_module, "InstanceGenerator", DummyGenerator)

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
    assert "example" not in updated["components"]["schemas"]["User"]


def test_load_module_from_path_raises_for_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        examples_module.import_util,
        "spec_from_file_location",
        lambda *args, **kwargs: None,
    )
    try:
        with pytest.raises(DiscoveryError):
            examples_module._load_module_from_path(missing)
    finally:
        monkeypatch.undo()
