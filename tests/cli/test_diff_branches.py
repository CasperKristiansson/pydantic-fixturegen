from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from typer.testing import CliRunner

import pydantic_fixturegen.cli as cli_package
import pydantic_fixturegen.cli.diff as diff_module


runner = CliRunner()


def _write_simple_module(path: Path) -> None:
    path.write_text(
        "from pydantic import BaseModel\n\n"
        "class Model(BaseModel):\n"
        "    value: int\n",
        encoding="utf-8",
    )


def _stub_config() -> SimpleNamespace:
    return SimpleNamespace(
        include=[],
        exclude=[],
        seed=None,
        p_none=None,
        json=SimpleNamespace(indent=None, orjson=False),
        enum_policy="name",
        union_policy="smart",
        emitters=SimpleNamespace(pytest=SimpleNamespace(style="function", scope="function")),
    )


def _json_options(path: Path) -> diff_module.JsonDiffOptions:
    return diff_module.JsonDiffOptions(
        out=path,
        count=1,
        jsonl=False,
        indent=None,
        use_orjson=None,
        shard_size=None,
    )


def _fixtures_options(path: Path | None) -> diff_module.FixturesDiffOptions:
    return diff_module.FixturesDiffOptions(
        out=path,
        style=None,
        scope=None,
        cases=1,
        return_type=None,
    )


def _schema_options(path: Path | None) -> diff_module.SchemaDiffOptions:
    return diff_module.SchemaDiffOptions(out=path, indent=None)


def test_diff_requires_artifact_path(tmp_path: Path) -> None:
    module_path = tmp_path / "models.py"
    _write_simple_module(module_path)

    result = runner.invoke(cli_package.app, ["diff", str(module_path)])

    assert result.exit_code == 10
    assert "Provide at least one artifact path to diff." in result.stdout


def test_diff_rejects_missing_target(tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"
    json_out = tmp_path / "artifacts.json"

    result = runner.invoke(cli_package.app, ["diff", "--json-out", str(json_out), str(missing)])

    assert result.exit_code == 10
    assert "does not exist" in result.stdout


def test_diff_rejects_directory_target(tmp_path: Path) -> None:
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    json_out = tmp_path / "artifacts.json"

    result = runner.invoke(cli_package.app, ["diff", "--json-out", str(json_out), str(package_dir)])

    assert result.exit_code == 10
    assert "Target must be a Python module file" in result.stdout


def test_execute_diff_surfaces_discovery_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = tmp_path / "models.py"
    _write_simple_module(module_path)

    monkeypatch.setattr(diff_module, "load_config", lambda root: _stub_config())
    monkeypatch.setattr(diff_module, "load_entrypoint_plugins", lambda: None)
    monkeypatch.setattr(
        diff_module,
        "discover_models",
        lambda *args, **kwargs: SimpleNamespace(errors=["boom"], warnings=[], models=[]),
    )

    with pytest.raises(diff_module.DiscoveryError):
        diff_module._execute_diff(
            target=str(module_path),
            include=None,
            exclude=None,
            ast_mode=False,
            hybrid_mode=False,
            timeout=1.0,
            memory_limit_mb=128,
            seed_override=None,
            p_none_override=None,
            json_options=_json_options(tmp_path / "data.json"),
            fixtures_options=_fixtures_options(None),
            schema_options=_schema_options(None),
        )


def test_execute_diff_reports_warnings_and_missing_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module_path = tmp_path / "models.py"
    _write_simple_module(module_path)

    monkeypatch.setattr(diff_module, "load_config", lambda root: _stub_config())
    monkeypatch.setattr(diff_module, "load_entrypoint_plugins", lambda: None)
    monkeypatch.setattr(
        diff_module,
        "discover_models",
        lambda *args, **kwargs: SimpleNamespace(
            errors=[],
            warnings=["  caution  "],
            models=[],
        ),
    )

    with pytest.raises(diff_module.DiscoveryError):
        diff_module._execute_diff(
            target=str(module_path),
            include=None,
            exclude=None,
            ast_mode=False,
            hybrid_mode=False,
            timeout=1.0,
            memory_limit_mb=128,
            seed_override=None,
            p_none_override=None,
            json_options=_json_options(tmp_path / "data.json"),
            fixtures_options=_fixtures_options(None),
            schema_options=_schema_options(None),
        )

    err = capsys.readouterr().err
    assert "warning: caution" in err


def test_execute_diff_wraps_load_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = tmp_path / "models.py"
    _write_simple_module(module_path)

    discovery_model = SimpleNamespace(module="pkg", locator=str(module_path), name="Model")

    monkeypatch.setattr(diff_module, "load_config", lambda root: _stub_config())
    monkeypatch.setattr(diff_module, "load_entrypoint_plugins", lambda: None)
    monkeypatch.setattr(
        diff_module,
        "discover_models",
        lambda *args, **kwargs: SimpleNamespace(errors=[], warnings=[], models=[discovery_model]),
    )
    monkeypatch.setattr(diff_module, "load_model_class", lambda model: (_ for _ in ()).throw(RuntimeError("load failed")))

    with pytest.raises(diff_module.DiscoveryError) as exc_info:
        diff_module._execute_diff(
            target=str(module_path),
            include=None,
            exclude=None,
            ast_mode=False,
            hybrid_mode=False,
            timeout=1.0,
            memory_limit_mb=128,
            seed_override=None,
            p_none_override=None,
            json_options=_json_options(tmp_path / "data.json"),
            fixtures_options=_fixtures_options(None),
            schema_options=_schema_options(None),
        )

    assert "load failed" in str(exc_info.value)


class AlphaModel(BaseModel):
    value: int = 1


class BetaModel(BaseModel):
    value: int = 2


def test_diff_json_requires_models() -> None:
    with pytest.raises(diff_module.DiscoveryError):
        diff_module._diff_json_artifact(
            model_classes=[],
            app_config_seed=None,
            app_config_indent=None,
            app_config_orjson=False,
            app_config_enum="name",
            app_config_union="smart",
            app_config_p_none=0.0,
            options=_json_options(Path("unused.json")),
        )


def test_diff_json_rejects_multiple_models(tmp_path: Path) -> None:
    with pytest.raises(diff_module.DiscoveryError) as exc_info:
        diff_module._diff_json_artifact(
            model_classes=[AlphaModel, BetaModel],
            app_config_seed=None,
            app_config_indent=None,
            app_config_orjson=False,
            app_config_enum="name",
            app_config_union="smart",
            app_config_p_none=0.0,
            options=_json_options(tmp_path / "artifact.json"),
        )

    assert "Multiple models discovered" in str(exc_info.value)


def test_diff_json_requires_output(tmp_path: Path) -> None:
    options = diff_module.JsonDiffOptions(
        out=None,
        count=1,
        jsonl=False,
        indent=None,
        use_orjson=None,
        shard_size=None,
    )

    with pytest.raises(diff_module.DiscoveryError):
        diff_module._diff_json_artifact(
            model_classes=[AlphaModel],
            app_config_seed=None,
            app_config_indent=None,
            app_config_orjson=False,
            app_config_enum="name",
            app_config_union="smart",
            app_config_p_none=0.0,
            options=options,
        )


def test_diff_json_handles_mapping_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_path = tmp_path / "artifact.json"

    monkeypatch.setattr(
        diff_module,
        "_build_instance_generator",
        lambda **kwargs: SimpleNamespace(generate_one=lambda model: None),
    )

    def fake_emit_json_samples(factory, output_path, **kwargs):
        factory()
        return [output_path]

    monkeypatch.setattr(diff_module, "emit_json_samples", fake_emit_json_samples)

    with pytest.raises(diff_module.MappingError):
        diff_module._diff_json_artifact(
            model_classes=[AlphaModel],
            app_config_seed=None,
            app_config_indent=None,
            app_config_orjson=False,
            app_config_enum="name",
            app_config_union="smart",
            app_config_p_none=0.0,
            options=_json_options(output_path),
        )


def test_diff_json_detects_directory_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "artifacts" / "alpha.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.mkdir()

    def fake_emit_json_samples(factory, output_path, **kwargs):
        generated = output_path if output_path.suffix else output_path.with_suffix(".json")
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_text("{}", encoding="utf-8")
        return [generated]

    monkeypatch.setattr(diff_module, "_build_instance_generator", lambda **kwargs: SimpleNamespace(generate_one=lambda model: AlphaModel()))
    monkeypatch.setattr(diff_module, "emit_json_samples", fake_emit_json_samples)

    report = diff_module._diff_json_artifact(
        model_classes=[AlphaModel],
        app_config_seed=None,
        app_config_indent=None,
        app_config_orjson=False,
        app_config_enum="name",
        app_config_union="smart",
        app_config_p_none=0.0,
        options=_json_options(output_path),
    )

    assert "JSON artifact path is a directory" in report.messages[0]


def test_diff_json_ignores_extra_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "artifacts" / "alpha.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("{}", encoding="utf-8")

    extra_dir = output_path.parent / "alpha-001.json"
    extra_dir.mkdir()

    def fake_emit_json_samples(factory, output_path, **kwargs):
        generated = output_path if output_path.suffix else output_path.with_suffix(".json")
        generated.parent.mkdir(parents=True, exist_ok=True)
        generated.write_text("{}", encoding="utf-8")
        return [generated]

    monkeypatch.setattr(diff_module, "_build_instance_generator", lambda **kwargs: SimpleNamespace(generate_one=lambda model: AlphaModel()))
    monkeypatch.setattr(diff_module, "emit_json_samples", fake_emit_json_samples)

    report = diff_module._diff_json_artifact(
        model_classes=[AlphaModel],
        app_config_seed=None,
        app_config_indent=None,
        app_config_orjson=False,
        app_config_enum="name",
        app_config_union="smart",
        app_config_p_none=0.0,
        options=_json_options(output_path),
    )

    assert report.messages == []
    assert report.summary == "JSON artifacts match (1 file(s))."


def test_diff_fixtures_require_output() -> None:
    with pytest.raises(diff_module.DiscoveryError):
        diff_module._diff_fixtures_artifact(
            model_classes=[AlphaModel],
            app_config_seed=None,
            app_config_p_none=None,
            app_config_style="function",
            app_config_scope="function",
            options=_fixtures_options(None),
        )


def test_diff_fixtures_emit_artifact_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "fixtures" / "test_models.py"

    def fake_emit_artifact(name, context):
        context.output.parent.mkdir(parents=True, exist_ok=True)
        context.output.write_text("# stub", encoding="utf-8")
        return True

    monkeypatch.setattr(diff_module, "emit_artifact", fake_emit_artifact)

    report = diff_module._diff_fixtures_artifact(
        model_classes=[AlphaModel],
        app_config_seed=None,
        app_config_p_none=None,
        app_config_style="function",
        app_config_scope="function",
        options=_fixtures_options(output_path),
    )

    assert report.summary == "Fixtures artifact matches."


def test_diff_fixtures_emit_artifact_without_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "fixtures" / "test_models.py"

    monkeypatch.setattr(diff_module, "emit_artifact", lambda name, context: True)

    with pytest.raises(diff_module.EmitError):
        diff_module._diff_fixtures_artifact(
            model_classes=[AlphaModel],
            app_config_seed=None,
            app_config_p_none=None,
            app_config_style="function",
            app_config_scope="function",
            options=_fixtures_options(output_path),
        )


def test_diff_fixtures_detect_directory_target(tmp_path: Path) -> None:
    output_path = tmp_path / "fixtures" / "test_models.py"
    output_path.mkdir(parents=True, exist_ok=True)

    with pytest.raises(diff_module.EmitError):
        diff_module._diff_fixtures_artifact(
            model_classes=[AlphaModel],
            app_config_seed=None,
            app_config_p_none=None,
            app_config_style="function",
            app_config_scope="function",
            options=_fixtures_options(output_path),
        )


def test_diff_schema_requires_output() -> None:
    with pytest.raises(diff_module.DiscoveryError):
        diff_module._diff_schema_artifact(
            model_classes=[AlphaModel],
            app_config_indent=None,
            options=_schema_options(None),
        )


def test_diff_schema_emit_plugin_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "schema" / "model.json"

    def fake_emit_artifact(name, context):
        context.output.parent.mkdir(parents=True, exist_ok=True)
        context.output.write_text("{}", encoding="utf-8")
        return True

    monkeypatch.setattr(diff_module, "emit_artifact", fake_emit_artifact)

    report = diff_module._diff_schema_artifact(
        model_classes=[AlphaModel],
        app_config_indent=None,
        options=_schema_options(output_path),
    )

    assert report.summary == "Schema artifact matches."


def test_diff_schema_emit_artifact_without_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "schema" / "model.json"

    monkeypatch.setattr(diff_module, "emit_artifact", lambda name, context: True)

    with pytest.raises(diff_module.EmitError):
        diff_module._diff_schema_artifact(
            model_classes=[AlphaModel],
            app_config_indent=None,
            options=_schema_options(output_path),
        )


def test_diff_schema_handles_multiple_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_path = tmp_path / "schema" / "models.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("{}", encoding="utf-8")

    def fake_emit_artifact(name, context):
        return False

    def fake_emit_models_schema(models, output_path, **kwargs):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("{}", encoding="utf-8")
        return output_path

    monkeypatch.setattr(diff_module, "emit_artifact", fake_emit_artifact)
    monkeypatch.setattr(diff_module, "emit_models_schema", fake_emit_models_schema)
    monkeypatch.setattr(
        diff_module,
        "emit_model_schema",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("should not be called")),
    )

    report = diff_module._diff_schema_artifact(
        model_classes=[AlphaModel, BetaModel],
        app_config_indent=None,
        options=_schema_options(output_path),
    )

    assert report.summary == "Schema artifact matches."


def test_diff_schema_detects_directory_target(tmp_path: Path) -> None:
    output_path = tmp_path / "schema" / "model.json"
    output_path.mkdir(parents=True, exist_ok=True)

    with pytest.raises(diff_module.EmitError):
        diff_module._diff_schema_artifact(
            model_classes=[AlphaModel],
            app_config_indent=None,
            options=_schema_options(output_path),
        )


def test_resolve_method_variants() -> None:
    with pytest.raises(diff_module.DiscoveryError):
        diff_module._resolve_method(ast_mode=True, hybrid_mode=True)

    assert diff_module._resolve_method(ast_mode=False, hybrid_mode=True) == "hybrid"
    assert diff_module._resolve_method(ast_mode=True, hybrid_mode=False) == "ast"
    assert diff_module._resolve_method(ast_mode=False, hybrid_mode=False) == "import"


def test_render_reports_handles_cases(capsys: pytest.CaptureFixture[str]) -> None:
    diff_module._render_reports([], show_diff=False)
    output = capsys.readouterr()
    assert "No artifacts were compared" in output.out or output.err

    matching = diff_module.DiffReport(
        kind="json",
        target=Path("out.json"),
        checked_paths=[],
        messages=[],
        diff_outputs=[],
        summary="All good",
    )
    changed = diff_module.DiffReport(
        kind="fixtures",
        target=Path("fixtures.py"),
        checked_paths=[],
        messages=["Problem"],
        diff_outputs=[("fixtures.py", "")],
        summary=None,
    )

    diff_module._render_reports([matching, changed], show_diff=True)
    output = capsys.readouterr()
    assert "All good" in output.out
    assert "FIXTURES differences detected" in output.out
    assert "Problem" in output.out
