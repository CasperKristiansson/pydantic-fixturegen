from __future__ import annotations

from pathlib import Path

import pytest

try:  # pragma: no cover - optional dependency
    from fastapi.testclient import TestClient  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    pytest.skip("fastapi is not installed", allow_module_level=True)

from pydantic_fixturegen.cli import app as cli_app
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
