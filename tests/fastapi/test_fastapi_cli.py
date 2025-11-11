from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from fastapi.testclient import TestClient  # type: ignore
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli.fastapi import (
    _import_object,
    _resolve_dependency_overrides,
    fastapi_serve,
)
from pydantic_fixturegen.core.errors import DiscoveryError
from pydantic_fixturegen.fastapi_support import build_mock_app
from tests._cli import create_cli_runner

runner = create_cli_runner()


def _write_app(tmp_path: Path) -> Path:
    module_path = tmp_path / "my_app.py"
    module_path.write_text(
        """
from fastapi import FastAPI
from pydantic import BaseModel


app = FastAPI()


class Item(BaseModel):
    id: int
    name: str


@app.get("/items", response_model=list[Item])
def list_items():
    return [Item(id=1, name="foo")]


@app.post("/items", response_model=Item)
def create_item(item: Item):
    return item
""",
        encoding="utf-8",
    )
    return module_path


def test_fastapi_smoke_generates_pytest_module(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_app(tmp_path)
    monkeypatch.syspath_prepend(tmp_path)
    output = tmp_path / "test_smoke.py"

    result = runner.invoke(
        cli_app,
        [
            "fastapi",
            "smoke",
            "my_app:app",
            "--out",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    content = output.read_text(encoding="utf-8")
    assert "client = TestClient(app)" in content
    assert "def test_get_items" in content


def test_fastapi_mock_server_builds_app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_app(tmp_path)
    monkeypatch.syspath_prepend(tmp_path)
    app = build_mock_app(target="my_app:app", seed=1)
    client = TestClient(app)

    response = client.get("/items")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_resolve_dependency_overrides_imports_functions(monkeypatch: pytest.MonkeyPatch) -> None:
    module_name = "tests.fastapi.sample_overrides"
    module = ModuleType(module_name)

    def original() -> str:
        return "original"

    def override() -> str:
        return "override"

    module.original = original
    module.override = override
    monkeypatch.setitem(sys.modules, module_name, module)

    overrides = _resolve_dependency_overrides([f"{module_name}.original={module_name}.override"])
    assert overrides == [(original, override)]
    assert _import_object(f"{module_name}:original") is original


def test_resolve_dependency_overrides_rejects_invalid_entries() -> None:
    with pytest.raises(DiscoveryError):
        _resolve_dependency_overrides(["not-a-pair"])


def test_fastapi_serve_invokes_uvicorn_with_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    module_name = "tests.fastapi.mock_deps"
    module = ModuleType(module_name)

    def original() -> str:
        return "orig"

    def override() -> str:
        return "over"

    module.original = original
    module.override = override
    monkeypatch.setitem(sys.modules, module_name, module)

    build_calls: dict[str, object] = {}

    def fake_build_mock_app(**kwargs: object) -> object:
        build_calls["kwargs"] = kwargs
        return SimpleNamespace()

    monkeypatch.setattr("pydantic_fixturegen.cli.fastapi.build_mock_app", fake_build_mock_app)

    class DummyLogger:
        def __init__(self) -> None:
            self.records: list[tuple[str, dict[str, object]]] = []

        def info(self, message: str, **extra: object) -> None:
            self.records.append((message, extra))

    dummy_logger = DummyLogger()
    monkeypatch.setattr("pydantic_fixturegen.cli.fastapi.get_logger", lambda: dummy_logger)

    def fake_run(app: object, host: str, port: int) -> None:
        build_calls["run"] = (app, host, port)

    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=fake_run))

    fastapi_serve(
        target="demo:app",
        host="0.0.0.0",
        port=9001,
        seed=42,
        dependency_override=[f"{module_name}.original={module_name}.override"],
    )

    assert build_calls["kwargs"]["seed"] == 42
    overrides = build_calls["kwargs"]["dependency_overrides"]
    assert overrides == [(original, override)]
    assert build_calls["run"][1:] == ("0.0.0.0", 9001)
    assert dummy_logger.records and dummy_logger.records[0][0] == "Starting FastAPI mock server"


def test_import_object_raises_for_missing_attribute(monkeypatch: pytest.MonkeyPatch) -> None:
    module_name = "tests.fastapi.empty_module"
    module = ModuleType(module_name)
    monkeypatch.setitem(sys.modules, module_name, module)

    with pytest.raises(DiscoveryError):
        _import_object(f"{module_name}.missing_attr")
