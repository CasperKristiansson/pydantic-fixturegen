from __future__ import annotations

from pathlib import Path

from pydantic_fixturegen.core.ast_discover import discover_models


def _write_source(tmp_path: Path, name: str, content: str) -> Path:
    module_path = tmp_path / f"{name}.py"
    module_path.write_text(content, encoding="utf-8")
    return module_path


def test_ast_discovers_pydantic_models(tmp_path: Path) -> None:
    source = """
from pydantic import BaseModel

class User(BaseModel):
    id: int

class _Hidden(BaseModel):
    value: str
"""

    path = _write_source(tmp_path, "models", source)

    result = discover_models([path], infer_module=True)

    names = {model.name for model in result.models}

    assert "User" in names
    assert "_Hidden" in names
    assert all(model.module == "models" for model in result.models)


def test_public_only_respects_all(tmp_path: Path) -> None:
    source = """
from pydantic import BaseModel

__all__ = ["PublicModel"]

class PublicModel(BaseModel):
    id: int

class PrivateModel(BaseModel):
    id: int
"""

    path = _write_source(tmp_path, "shapes", source)

    result = discover_models([path], infer_module=True, public_only=True)

    assert [model.name for model in result.models] == ["PublicModel"]


def test_alias_and_attribute_bases(tmp_path: Path) -> None:
    source = """
import pydantic as pd
from pydantic import BaseModel as BM
from pydantic.v1 import RootModel

class ViaAlias(pd.BaseModel):
    value: str

class ViaFrom(BM):
    value: int

class ViaRoot(RootModel):
    root: list[int]
"""

    path = _write_source(tmp_path, "alias_models", source)

    result = discover_models([path], infer_module=True)

    names = {model.name for model in result.models}

    assert names == {"ViaAlias", "ViaFrom", "ViaRoot"}


def test_missing_file_yields_warning(tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"

    result = discover_models([missing], infer_module=True)

    assert result.models == []
    assert result.warnings


def test_unknown_bases_ignored(tmp_path: Path) -> None:
    source = """
class Foo:
    pass

class Bar(Foo):
    pass
"""

    path = _write_source(tmp_path, "plain", source)

    result = discover_models([path], infer_module=True)

    assert result.models == []


def test_handles_invalid_source(tmp_path: Path) -> None:
    path = tmp_path / "bad.py"
    path.write_text("not python >>>", encoding="utf-8")

    result = discover_models([path], infer_module=True)

    assert result.models == []
    assert result.warnings
