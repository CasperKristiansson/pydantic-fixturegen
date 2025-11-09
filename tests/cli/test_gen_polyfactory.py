from __future__ import annotations

import builtins
import importlib
import sys
from pathlib import Path
from types import ModuleType

import pydantic_fixturegen.cli.gen.polyfactory as poly_cli
import pytest
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.core.errors import DiscoveryError
from pydantic_fixturegen.core.introspect import IntrospectedModel, IntrospectionResult
from tests._cli import create_cli_runner

runner = create_cli_runner()


def _suppress_polyfactory_cli_exit(monkeypatch):
    original = poly_cli.render_cli_error
    captured: list[Exception] = []

    def patched(error: Exception, *, json_errors: bool, exit_app: bool = True) -> None:
        captured.append(error)
        original(error, json_errors=json_errors, exit_app=False)

    monkeypatch.setattr(poly_cli, "render_cli_error", patched)
    return captured


def test_gen_polyfactory_exports_factories(tmp_path: Path) -> None:
    pytest.importorskip("polyfactory")

    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class User(BaseModel):
    name: str
""",
        encoding="utf-8",
    )

    output_path = tmp_path / "factories.py"
    result = runner.invoke(
        cli_app,
        [
            "gen",
            "polyfactory",
            str(module_path),
            "--out",
            str(output_path),
            "--seed",
            "7",
        ],
    )

    assert result.exit_code == 0, result.stdout

    sys.path.insert(0, str(tmp_path))
    try:
        module = importlib.import_module("factories")
        assert hasattr(module, "UserFactory")
        factory = module.UserFactory
        instance = factory.build()
        assert instance.name
        module.seed_factories(13)
        second = factory.build()
        assert second.name
    finally:
        sys.path.pop(0)
        if "factories" in sys.modules:
            del sys.modules["factories"]


def test_gen_polyfactory_requires_dependency(monkeypatch, tmp_path: Path) -> None:
    captured = _suppress_polyfactory_cli_exit(monkeypatch)
    module_path = tmp_path / "models.py"
    module_path.write_text(
        "from pydantic import BaseModel\n"
        "class Item(BaseModel):\n"
        "    value: int\n",
        encoding="utf-8",
    )

    original_import = builtins.__import__

    def fake_import(name: str, *args, **kwargs):
        if name == "polyfactory":
            raise ModuleNotFoundError("polyfactory missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "polyfactory",
            str(module_path),
        ],
    )

    assert result.exit_code == 1
    assert "Polyfactory is not installed" in str(captured[0])


def test_gen_polyfactory_handles_missing_target(monkeypatch, tmp_path: Path) -> None:
    captured = _suppress_polyfactory_cli_exit(monkeypatch)
    monkeypatch.setitem(sys.modules, "polyfactory", ModuleType("polyfactory"))
    target = tmp_path / "missing.py"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "polyfactory",
            str(target),
        ],
    )

    assert result.exit_code == 0
    assert "does not exist" in str(captured[0])


def test_gen_polyfactory_supports_stdout(monkeypatch, tmp_path: Path) -> None:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        "from pydantic import BaseModel\n"
        "class Item(BaseModel):\n"
        "    value: int\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(sys.modules, "polyfactory", ModuleType("polyfactory"))

    calls: dict[str, object] = {}

    def fake_build_module_source(**kwargs):
        calls.update(kwargs)
        return "generated module"

    monkeypatch.setattr(poly_cli, "_build_module_source", fake_build_module_source)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "polyfactory",
            str(module_path),
            "--stdout",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "generated module" in result.stdout
    assert calls["target"] == module_path


def test_gen_polyfactory_handles_build_errors(monkeypatch, tmp_path: Path) -> None:
    captured = _suppress_polyfactory_cli_exit(monkeypatch)
    module_path = tmp_path / "models.py"
    module_path.write_text(
        "from pydantic import BaseModel\n"
        "class Item(BaseModel):\n"
        "    value: int\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(sys.modules, "polyfactory", ModuleType("polyfactory"))
    monkeypatch.setattr(
        poly_cli,
        "_build_module_source",
        lambda **_: (_ for _ in ()).throw(DiscoveryError("boom")),
    )

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "polyfactory",
            str(module_path),
        ],
    )

    assert result.exit_code == 0
    assert "boom" in str(captured[0])


def test_gen_polyfactory_watch_mode_invokes_runner(monkeypatch, tmp_path: Path) -> None:
    module_path = tmp_path / "models.py"
    module_path.write_text(
        "from pydantic import BaseModel\n"
        "class Item(BaseModel):\n"
        "    value: int\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(sys.modules, "polyfactory", ModuleType("polyfactory"))
    monkeypatch.setattr(poly_cli, "_build_module_source", lambda **_: "module text")
    monkeypatch.setattr(
        poly_cli,
        "gather_default_watch_paths",
        lambda target_path, output=None, extra=None: ["models.py"],
    )

    calls: dict[str, object] = {}

    def fake_watch(callback, paths, debounce):
        calls["paths"] = paths
        calls["debounce"] = debounce
        callback()

    monkeypatch.setattr(poly_cli, "run_with_watch", fake_watch)

    out_path = tmp_path / "watch_factories.py"
    result = runner.invoke(
        cli_app,
        [
            "gen",
            "polyfactory",
            str(module_path),
            "--out",
            str(out_path),
            "--watch",
        ],
    )

    assert result.exit_code == 0
    assert calls["paths"] == ["models.py"]


def test_build_module_source_propagates_discovery_errors(monkeypatch, tmp_path: Path) -> None:
    module_path = tmp_path / "models.py"
    module_path.write_text("# empty module\n")
    monkeypatch.setattr(poly_cli.cli_common, "clear_module_cache", lambda: None)
    monkeypatch.setattr(
        poly_cli.cli_common,
        "discover_models",
        lambda *args, **kwargs: IntrospectionResult(models=[], warnings=[], errors=["boom"]),
    )

    with pytest.raises(DiscoveryError):
        poly_cli._build_module_source(
            target=module_path,
            include=None,
            exclude=None,
            seed=None,
            max_depth=None,
            cycle_policy=None,
            rng_mode=None,
        )


def test_build_module_source_includes_config_options(monkeypatch, tmp_path: Path) -> None:
    module_path = tmp_path / "models.py"
    module_path.write_text("# empty module\n")
    models = [
        IntrospectedModel(
            module="pkg.models",
            name="Sample",
            qualname="pkg.models.Sample",
            locator="pkg/models.py",
            lineno=1,
            discovery="import",
            is_public=True,
        )
    ]
    monkeypatch.setattr(poly_cli.cli_common, "clear_module_cache", lambda: None)
    monkeypatch.setattr(
        poly_cli.cli_common,
        "discover_models",
        lambda *args, **kwargs: IntrospectionResult(models=models, warnings=[], errors=[]),
    )

    source = poly_cli._build_module_source(
        target=module_path,
        include=["pkg.*"],
        exclude=None,
        seed=5,
        max_depth=3,
        cycle_policy="stub",
        rng_mode="legacy",
    )

    assert "seed=5" in source
    assert "max_depth=3" in source
    assert 'cycle_policy="stub"' in source
    assert 'rng_mode="legacy"' in source
    assert "class SampleFactory" in source


def test_build_module_source_requires_models(monkeypatch, tmp_path: Path) -> None:
    module_path = tmp_path / "models.py"
    module_path.write_text("# empty module\n")
    monkeypatch.setattr(poly_cli.cli_common, "clear_module_cache", lambda: None)
    monkeypatch.setattr(
        poly_cli.cli_common,
        "discover_models",
        lambda *args, **kwargs: IntrospectionResult(models=[], warnings=[], errors=[]),
    )

    with pytest.raises(DiscoveryError, match="No models discovered."):
        poly_cli._build_module_source(
            target=module_path,
            include=None,
            exclude=None,
            seed=None,
            max_depth=None,
            cycle_policy=None,
            rng_mode=None,
        )
