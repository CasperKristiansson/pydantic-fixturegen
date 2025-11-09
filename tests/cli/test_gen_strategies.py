from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli.gen import strategies as strategies_module
from pydantic_fixturegen.core.errors import DiscoveryError
from tests._cli import create_cli_runner

pytest.importorskip("hypothesis")
from hypothesis.errors import NonInteractiveExampleWarning

MODULE_SOURCE = """
from pydantic import BaseModel, Field


class User(BaseModel):
    email: str
    age: int = Field(ge=1)


class Order(BaseModel):
    total: float
"""


def _write_module(tmp_path: Path) -> Path:
    module_path = tmp_path / "models.py"
    module_path.write_text(MODULE_SOURCE, encoding="utf-8")
    return module_path


def _suppress_strategies_cli_exit(monkeypatch: pytest.MonkeyPatch) -> list[Exception]:
    original_render = strategies_module.render_cli_error
    captured: list[Exception] = []

    def patched(error: Exception, *, json_errors: bool, exit_app: bool = True) -> None:
        captured.append(error)
        original_render(error, json_errors=json_errors, exit_app=False)

    monkeypatch.setattr(strategies_module, "render_cli_error", patched)
    return captured


def test_gen_strategies_writes_module(tmp_path: Path) -> None:
    module_path = _write_module(tmp_path)
    output_path = tmp_path / "strategies.py"
    runner = create_cli_runner()

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "strategies",
            str(module_path),
            "--out",
            str(output_path),
            "--include",
            "models.User",
            "--seed",
            "7",
            "--strategy-profile",
            "edge",
        ],
    )

    assert result.exit_code == 0, result.output
    content = output_path.read_text(encoding="utf-8")
    assert "strategy_for" in content

    import sys

    sys.modules.pop("models", None)
    sys.path.insert(0, str(tmp_path))
    try:
        module_globals = runpy.run_path(output_path)
    finally:
        sys.path.remove(str(tmp_path))
    strategy = module_globals.get("models_user_strategy")
    assert strategy is not None
    with pytest.warns(NonInteractiveExampleWarning):
        example = strategy.example()
    assert example.email


def test_gen_strategies_rejects_invalid_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(tmp_path)
    runner = create_cli_runner()

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "strategies",
            str(module_path),
            "--strategy-profile",
            "unknown",
        ],
    )

    assert result.exit_code != 0
    assert result.exception is not None
    assert "strategy-profile" in str(result.exception).lower()


def test_gen_strategies_errors_when_target_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = create_cli_runner()
    missing = tmp_path / "missing.py"
    errors = _suppress_strategies_cli_exit(monkeypatch)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "strategies",
            str(missing),
        ],
    )

    assert result.exit_code == 0
    assert errors and "does not exist" in str(errors[0]).lower()


def test_gen_strategies_errors_when_no_models_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(tmp_path)
    runner = create_cli_runner()
    errors = _suppress_strategies_cli_exit(monkeypatch)
    result = runner.invoke(
        cli_app,
        [
            "gen",
            "strategies",
            str(module_path),
            "--include",
            "models.Missing",
        ],
    )

    assert result.exit_code == 0
    assert errors and "no models discovered" in str(errors[0]).lower()


def test_gen_strategies_watch_mode_invokes_runner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(tmp_path)
    output_path = tmp_path / "strategies.py"
    runner = create_cli_runner()
    monkeypatch.setattr(strategies_module, "_build_source", lambda **kwargs: "content")
    monkeypatch.setattr(
        strategies_module,
        "gather_default_watch_paths",
        lambda target, output: [target],
    )
    invoked: dict[str, object] = {}

    def fake_watch(callback: callable, watch_paths: list[Path], debounce: float) -> None:
        invoked["paths"] = watch_paths
        callback()

    monkeypatch.setattr(strategies_module, "run_with_watch", fake_watch)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "strategies",
            str(module_path),
            "--out",
            str(output_path),
            "--watch",
            "--watch-debounce",
            "0.1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert invoked["paths"] == [module_path]


def test_gen_strategies_stdout_outputs_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(tmp_path)
    runner = create_cli_runner()
    monkeypatch.setattr(strategies_module, "_build_source", lambda **kwargs: "module-text")

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "strategies",
            str(module_path),
            "--stdout",
        ],
    )

    assert result.exit_code == 0
    assert "module-text" in result.output


def test_gen_strategies_handles_build_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(tmp_path)
    runner = create_cli_runner()
    errors = _suppress_strategies_cli_exit(monkeypatch)
    monkeypatch.setattr(
        strategies_module,
        "_build_source",
        lambda **kwargs: (_ for _ in ()).throw(DiscoveryError("build failed")),
    )

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "strategies",
            str(module_path),
        ],
    )

    assert result.exit_code == 0
    assert errors and "build failed" in str(errors[0])


def test_build_source_raises_when_discovery_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(tmp_path)
    discovery = SimpleNamespace(errors=["missing"], models=[])
    monkeypatch.setattr(
        strategies_module.cli_common,
        "discover_models",
        lambda *args, **kwargs: discovery,
    )

    with pytest.raises(DiscoveryError):
        strategies_module._build_source(
            target=module_path,
            include=None,
            exclude=None,
            seed=None,
            strategy_profile="typical",
            max_depth=None,
            cycle_policy=None,
            rng_mode=None,
        )


def test_build_source_includes_config_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(tmp_path)
    model = SimpleNamespace(module="models", name="User")
    discovery = SimpleNamespace(errors=[], models=[model])
    monkeypatch.setattr(
        strategies_module.cli_common,
        "discover_models",
        lambda *args, **kwargs: discovery,
    )

    source = strategies_module._build_source(
        target=module_path,
        include=None,
        exclude=None,
        seed=42,
        strategy_profile="typical",
        max_depth=5,
        cycle_policy="reuse",
        rng_mode="portable",
    )

    assert "seed=42" in source
    assert "max_depth=5" in source
