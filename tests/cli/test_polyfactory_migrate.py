from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pydantic_fixturegen.cli.polyfactory as poly_cli
import pytest
import typer
from pydantic import BaseModel
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.core.errors import DiscoveryError
from pydantic_fixturegen.polyfactory_support.discovery import (
    POLYFACTORY_MODEL_FACTORY,
    POLYFACTORY_UNAVAILABLE_REASON,
    PolyfactoryBinding,
)
from pydantic_fixturegen.polyfactory_support.migration import FactoryReport, FieldReport
from tests._cli import create_cli_runner

try:  # pragma: no cover - optional dependency used in an integration test below
    import polyfactory  # type: ignore  # noqa: F401
except Exception:  # pragma: no cover - allow the module to import so other tests run
    polyfactory = None

runner = create_cli_runner()


def test_polyfactory_migrate_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if polyfactory is None:
        pytest.skip("polyfactory unavailable")
    module_path = tmp_path / "models_poly.py"
    module_path.write_text(
        """
from pydantic import BaseModel
from polyfactory.factories.pydantic_factory import ModelFactory
from polyfactory.fields import Use, Ignore


def slugify(prefix: str) -> str:
    return f"{prefix}-slug"


class Model(BaseModel):
    slug: str
    alias: str | None = None


class ModelFactoryShim(ModelFactory[Model]):
    __model__ = Model
    __check_model__ = False
    slug = Use(slugify, "fixture")
    alias = Ignore()
""",
        encoding="utf-8",
    )

    overrides_path = tmp_path / "overrides.toml"
    if POLYFACTORY_MODEL_FACTORY is None and POLYFACTORY_UNAVAILABLE_REASON:
        pytest.skip(POLYFACTORY_UNAVAILABLE_REASON)
    result = runner.invoke(
        cli_app,
        [
            "polyfactory",
            "migrate",
            str(module_path),
            "--format",
            "json",
            "--overrides-out",
            str(overrides_path),
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload and payload[0]["fields"]
    override_text = overrides_path.read_text(encoding="utf-8")
    assert "polyfactory_support.migration_helpers" in override_text
    assert "slug" in override_text


def _mock_discovery(
    monkeypatch: pytest.MonkeyPatch,
    model_cls: type[BaseModel],
    *,
    models: list[SimpleNamespace] | None = None,
    errors: list[str] | None = None,
) -> None:
    if models is None:
        models = [SimpleNamespace(module="demo.models", qualname=model_cls.__qualname__)]
    discovery = SimpleNamespace(models=models, errors=errors or [])
    monkeypatch.setattr(poly_cli.cli_common, "discover_models", lambda *_, **__: discovery)
    monkeypatch.setattr(poly_cli.cli_common, "load_model_class", lambda *_: model_cls)


def _binding_for(model_cls: type[BaseModel]) -> PolyfactoryBinding:
    factory = type("DemoFactory", (), {"__module__": "demo.factories"})
    return PolyfactoryBinding(model=model_cls, factory=factory, source="demo.factories.DemoFactory")


class _GeneratorStub:
    def __init__(self, strategies: dict[str, object] | None = None) -> None:
        self.requested: list[type[BaseModel]] = []
        self._strategies = strategies or {}

    def _get_model_strategies(self, model: type[BaseModel]) -> dict[str, object]:
        self.requested.append(model)
        return dict(self._strategies)


def _capture_cli_errors(monkeypatch: pytest.MonkeyPatch) -> list[Exception]:
    captured: list[Exception] = []
    original = poly_cli.render_cli_error

    def patched(error: Exception, *, json_errors: bool, exit_app: bool = True) -> None:
        captured.append(error)
        original(error, json_errors=json_errors, exit_app=False)

    monkeypatch.setattr(poly_cli, "render_cli_error", patched)
    return captured


def _call_migrate(
    *,
    target: Path,
    format: str = "table",
    overrides_out: Path | None = None,
    json_errors: bool = False,
) -> None:
    poly_cli.migrate(
        target=target,
        include=None,
        exclude=None,
        factory_module=None,
        format=format,
        overrides_out=overrides_out,
        json_errors=json_errors,
    )


def test_polyfactory_migrate_requires_dependency(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _capture_cli_errors(monkeypatch)
    target = tmp_path / "models.py"
    target.write_text("from pydantic import BaseModel\n", encoding="utf-8")
    monkeypatch.setattr(poly_cli, "POLYFACTORY_MODEL_FACTORY", None, raising=False)
    monkeypatch.setattr(
        poly_cli,
        "POLYFACTORY_UNAVAILABLE_REASON",
        "polyfactory missing",
        raising=False,
    )

    _call_migrate(target=target)

    assert any("polyfactory missing" in str(error) for error in captured)


def test_polyfactory_migrate_requires_existing_target(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _capture_cli_errors(monkeypatch)
    monkeypatch.setattr(poly_cli, "POLYFACTORY_MODEL_FACTORY", object(), raising=False)
    monkeypatch.setattr(poly_cli, "POLYFACTORY_UNAVAILABLE_REASON", None, raising=False)
    missing = tmp_path / "missing.py"

    _call_migrate(target=missing)

    assert any("does not exist" in str(error) for error in captured)


def test_polyfactory_migrate_reports_discovery_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _capture_cli_errors(monkeypatch)
    monkeypatch.setattr(poly_cli, "POLYFACTORY_MODEL_FACTORY", object(), raising=False)
    monkeypatch.setattr(poly_cli, "POLYFACTORY_UNAVAILABLE_REASON", None, raising=False)
    target = tmp_path / "models.py"
    target.write_text("from pydantic import BaseModel\n", encoding="utf-8")

    discovery = SimpleNamespace(models=[], errors=["boom"])
    monkeypatch.setattr(poly_cli.cli_common, "discover_models", lambda *_, **__: discovery)

    _call_migrate(target=target)

    assert any("boom" in str(error) for error in captured)


def test_polyfactory_migrate_requires_models(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _capture_cli_errors(monkeypatch)
    monkeypatch.setattr(poly_cli, "POLYFACTORY_MODEL_FACTORY", object(), raising=False)
    monkeypatch.setattr(poly_cli, "POLYFACTORY_UNAVAILABLE_REASON", None, raising=False)
    target = tmp_path / "models.py"
    target.write_text("from pydantic import BaseModel\n", encoding="utf-8")

    discovery = SimpleNamespace(models=[], errors=[])
    monkeypatch.setattr(poly_cli.cli_common, "discover_models", lambda *_, **__: discovery)

    _call_migrate(target=target)

    assert any("No models discovered" in str(error) for error in captured)


def test_polyfactory_migrate_handles_load_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _capture_cli_errors(monkeypatch)
    monkeypatch.setattr(poly_cli, "POLYFACTORY_MODEL_FACTORY", object(), raising=False)
    monkeypatch.setattr(poly_cli, "POLYFACTORY_UNAVAILABLE_REASON", None, raising=False)

    class DemoModel(BaseModel):
        value: int

    target = tmp_path / "models.py"
    target.write_text("from pydantic import BaseModel\n", encoding="utf-8")

    _mock_discovery(monkeypatch, DemoModel)

    def fail_loader(*_, **__) -> type[BaseModel]:
        raise RuntimeError("loader blew up")

    monkeypatch.setattr(poly_cli.cli_common, "load_model_class", fail_loader)

    _call_migrate(target=target)

    assert any("loader blew up" in str(error) for error in captured)


def test_polyfactory_migrate_validates_format(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class DemoModel(BaseModel):
        value: int

    target = tmp_path / "models.py"
    target.write_text("from pydantic import BaseModel\n", encoding="utf-8")

    monkeypatch.setattr(poly_cli, "POLYFACTORY_MODEL_FACTORY", object(), raising=False)
    monkeypatch.setattr(poly_cli, "POLYFACTORY_UNAVAILABLE_REASON", None, raising=False)
    _mock_discovery(monkeypatch, DemoModel)

    with pytest.raises(typer.BadParameter):
        _call_migrate(target=target, format="yaml")


def test_polyfactory_migrate_requires_bindings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _capture_cli_errors(monkeypatch)

    class DemoModel(BaseModel):
        value: int

    target = tmp_path / "models.py"
    target.write_text("from pydantic import BaseModel\n", encoding="utf-8")

    monkeypatch.setattr(poly_cli, "POLYFACTORY_MODEL_FACTORY", object(), raising=False)
    monkeypatch.setattr(poly_cli, "POLYFACTORY_UNAVAILABLE_REASON", None, raising=False)
    _mock_discovery(monkeypatch, DemoModel)
    monkeypatch.setattr(poly_cli, "_discover_bindings", lambda *_, **__: [])

    _call_migrate(target=target)

    assert any("No Polyfactory factories" in str(error) for error in captured)


def test_polyfactory_migrate_handles_generator_errors(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured = _capture_cli_errors(monkeypatch)

    class DemoModel(BaseModel):
        value: int

    target = tmp_path / "models.py"
    target.write_text("from pydantic import BaseModel\n", encoding="utf-8")

    monkeypatch.setattr(poly_cli, "POLYFACTORY_MODEL_FACTORY", object(), raising=False)
    monkeypatch.setattr(poly_cli, "POLYFACTORY_UNAVAILABLE_REASON", None, raising=False)
    _mock_discovery(monkeypatch, DemoModel)
    binding = _binding_for(DemoModel)
    monkeypatch.setattr(poly_cli, "_discover_bindings", lambda *_, **__: [binding])
    monkeypatch.setattr(poly_cli, "_build_relation_model_map", lambda _: {})

    def raise_pfg(*_, **__):
        raise DiscoveryError("generator failed")

    monkeypatch.setattr(poly_cli, "_build_instance_generator", raise_pfg)

    _call_migrate(target=target)

    assert any("generator failed" in str(error) for error in captured)


def test_polyfactory_migrate_stubbed_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class DemoModel(BaseModel):
        value: int

    target = tmp_path / "models.py"
    target.write_text("from pydantic import BaseModel\n", encoding="utf-8")

    monkeypatch.setattr(poly_cli, "POLYFACTORY_MODEL_FACTORY", object(), raising=False)
    monkeypatch.setattr(poly_cli, "POLYFACTORY_UNAVAILABLE_REASON", None, raising=False)
    _mock_discovery(monkeypatch, DemoModel)
    binding = _binding_for(DemoModel)
    monkeypatch.setattr(poly_cli, "_discover_bindings", lambda *_, **__: [binding])
    monkeypatch.setattr(poly_cli, "_build_relation_model_map", lambda models: {"models": models})

    fake_generator = _GeneratorStub({"value": object()})
    monkeypatch.setattr(poly_cli, "_build_instance_generator", lambda *_, **__: fake_generator)

    field = FieldReport(
        name="value",
        kind="Use",
        detail="Use(callable)",
        fixturegen_provider="provider:value",
        translation={"value": "constant"},
        message=None,
    )
    report = FactoryReport(
        model=DemoModel,
        factory=binding.factory,
        source=binding.source,
        fields=[field],
    )
    monkeypatch.setattr(poly_cli, "analyze_binding", lambda *_, **__: report)

    overrides_path = tmp_path / "overrides.toml"
    result = runner.invoke(
        cli_app,
        [
            "polyfactory",
            "migrate",
            str(target),
            "--format",
            "json",
            "--overrides-out",
            str(overrides_path),
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload[0]["fields"][0]["name"] == "value"
    override_text = overrides_path.read_text(encoding="utf-8")
    assert "[tool.pydantic_fixturegen.overrides" in override_text
    assert fake_generator.requested == [DemoModel]


def test_polyfactory_migrate_table_logs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class DemoModel(BaseModel):
        slug: str
        alias: str | None = None

    target = tmp_path / "models.py"
    target.write_text("from pydantic import BaseModel\n", encoding="utf-8")

    monkeypatch.setattr(poly_cli, "POLYFACTORY_MODEL_FACTORY", object(), raising=False)
    monkeypatch.setattr(poly_cli, "POLYFACTORY_UNAVAILABLE_REASON", None, raising=False)
    _mock_discovery(monkeypatch, DemoModel)
    binding = _binding_for(DemoModel)
    monkeypatch.setattr(poly_cli, "_discover_bindings", lambda *_, **__: [binding])
    monkeypatch.setattr(poly_cli, "_build_relation_model_map", lambda models: {"models": models})
    generator = _GeneratorStub()
    monkeypatch.setattr(poly_cli, "_build_instance_generator", lambda *_, **__: generator)

    field_translated = FieldReport(
        name="slug",
        kind="Use",
        detail="Use(callable)",
        fixturegen_provider="provider:slug",
        translation={"value": "slug"},
        message=None,
    )
    field_manual = FieldReport(
        name="alias",
        kind="Ignore",
        detail="Ignore()",
        fixturegen_provider=None,
        translation=None,
        message="manual intervention required",
    )
    report = FactoryReport(
        model=DemoModel,
        factory=binding.factory,
        source=binding.source,
        fields=[field_translated, field_manual],
    )
    monkeypatch.setattr(poly_cli, "analyze_binding", lambda *_, **__: report)

    class _Logger:
        def __init__(self) -> None:
            self.messages: list[tuple[str, dict[str, object]]] = []

        def info(self, message: str, **context: object) -> None:
            self.messages.append((message, context))

        def warn(self, *args, **kwargs) -> None:  # pragma: no cover - API parity stub
            self.messages.append(("warn", {"args": args, "kwargs": kwargs}))

    logger = _Logger()
    monkeypatch.setattr(poly_cli, "get_logger", lambda: logger)

    overrides_path = tmp_path / "table_overrides.toml"
    result = runner.invoke(
        cli_app,
        [
            "polyfactory",
            "migrate",
            str(target),
            "--overrides-out",
            str(overrides_path),
        ],
    )

    assert result.exit_code == 0, result.stdout
    text = result.stdout
    assert "Model:" in text and "Override" in text
    assert "Note: manual" in text
    assert overrides_path.exists()
    assert any(msg[0] == "Polyfactory overrides written" for msg in logger.messages)
