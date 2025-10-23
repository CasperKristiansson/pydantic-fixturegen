from __future__ import annotations

from pathlib import Path

from pydantic_fixturegen.core.introspect import discover


def _write_source(tmp_path: Path, name: str, content: str) -> Path:
    module_path = tmp_path / f"{name}.py"
    module_path.write_text(content, encoding="utf-8")
    return module_path


def test_ast_mode_returns_models(tmp_path: Path) -> None:
    module_path = _write_source(
        tmp_path,
        "inventory",
        """
from pydantic import BaseModel

class Item(BaseModel):
    sku: str

class _Internal(BaseModel):
    flag: bool
""",
    )

    result = discover([module_path], method="ast", public_only=False)

    names = {model.name for model in result.models}

    assert names == {"Item", "_Internal"}
    assert all(model.discovery == "ast" for model in result.models)
    assert result.errors == []


def test_import_mode_respects_public_only(tmp_path: Path) -> None:
    module_path = _write_source(
        tmp_path,
        "accounts",
        """
from pydantic import BaseModel

class Account(BaseModel):
    id: int

class _HiddenAccount(BaseModel):
    id: int
""",
    )

    result = discover([module_path], method="import", public_only=True)

    assert [model.name for model in result.models] == ["Account"]
    assert all(model.discovery == "import" for model in result.models)


def test_hybrid_mode_deduplicates(tmp_path: Path) -> None:
    module_path = _write_source(
        tmp_path,
        "customers",
        """
from pydantic import BaseModel

class Customer(BaseModel):
    id: int
""",
    )

    result = discover([module_path], method="hybrid", public_only=False)

    assert len(result.models) == 1
    model = result.models[0]
    assert model.name == "Customer"
    assert model.discovery == "import"


def test_include_exclude_patterns(tmp_path: Path) -> None:
    first = _write_source(
        tmp_path,
        "one",
        """
from pydantic import BaseModel

class Alpha(BaseModel):
    x: int

class Beta(BaseModel):
    x: int
""",
    )

    result = discover(
        [first],
        method="ast",
        include=["one.Al*"],
        exclude=["*.Beta"],
    )

    assert [model.name for model in result.models] == ["Alpha"]
