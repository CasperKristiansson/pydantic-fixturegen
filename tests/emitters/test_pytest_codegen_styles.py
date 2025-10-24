from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from pydantic_fixturegen.emitters.pytest_codegen import PytestEmitConfig, emit_pytest_fixtures


class Item(BaseModel):
    code: str = Field(min_length=3)
    quantity: int


class Order(BaseModel):
    number: str
    item: Item


def test_factory_style_emits_callable_fixture(tmp_path: Path) -> None:
    output = tmp_path / "factory.py"
    result = emit_pytest_fixtures(
        [Order],
        output_path=output,
        config=PytestEmitConfig(seed=5, style="factory", scope="module"),
    )

    assert result.wrote is True
    text = output.read_text(encoding="utf-8")
    assert "from typing import Any, Callable" in text or "from typing import Callable, Any" in text
    assert "@pytest.fixture(scope=\"module\")" in text
    assert "def order_factory(" in text
    assert "def builder(" in text
    assert "return builder" in text


def test_class_style_emits_factory_class(tmp_path: Path) -> None:
    output = tmp_path / "class_style.py"
    result = emit_pytest_fixtures(
        [Order],
        output_path=output,
        config=PytestEmitConfig(seed=8, style="class", scope="session"),
    )

    assert result.wrote is True
    text = output.read_text(encoding="utf-8")
    assert "class OrderFactory" in text
    assert "def build(self, **overrides: Any)" in text
    assert "@pytest.fixture(scope=\"session\")" in text
    assert "return OrderFactory(base_data)" in text


def test_class_style_dict_return(tmp_path: Path) -> None:
    output = tmp_path / "class_dict.py"
    result = emit_pytest_fixtures(
        [Order],
        output_path=output,
        config=PytestEmitConfig(seed=13, style="class", return_type="dict"),
    )

    assert result.wrote is True
    text = output.read_text(encoding="utf-8")
    assert "return dict(data)" in text
    assert "return OrderFactory(base_data)" in text
