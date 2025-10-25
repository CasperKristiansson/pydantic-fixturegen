"""CLI command for diffing regenerated artifacts against existing output."""

from __future__ import annotations

import difflib
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import typer
from pydantic import BaseModel

from pydantic_fixturegen.core.config import load_config
from pydantic_fixturegen.core.errors import (
    DiffError,
    DiscoveryError,
    EmitError,
    MappingError,
    PFGError,
)
from pydantic_fixturegen.core.generate import GenerationConfig, InstanceGenerator
from pydantic_fixturegen.core.seed import SeedManager
from pydantic_fixturegen.emitters.json_out import emit_json_samples
from pydantic_fixturegen.emitters.pytest_codegen import PytestEmitConfig, emit_pytest_fixtures
from pydantic_fixturegen.emitters.schema_out import emit_model_schema, emit_models_schema
from pydantic_fixturegen.plugins.hookspecs import EmitterContext
from pydantic_fixturegen.plugins.loader import emit_artifact, load_entrypoint_plugins

from .gen._common import (
    JSON_ERRORS_OPTION,
    DiscoveryMethod,
    clear_module_cache,
    discover_models,
    load_model_class,
    render_cli_error,
    split_patterns,
)
from .gen.fixtures import (
    DEFAULT_RETURN,
    ReturnLiteral,
    StyleLiteral,
    _coerce_return_type,
    _coerce_scope,
    _coerce_style,
)

PATH_ARGUMENT = typer.Argument(
    ...,
    help="Python module file containing Pydantic models to diff against artifacts.",
)

INCLUDE_OPTION = typer.Option(
    None,
    "--include",
    "-i",
    help="Comma-separated glob pattern(s) of fully-qualified model names to include.",
)

EXCLUDE_OPTION = typer.Option(
    None,
    "--exclude",
    "-e",
    help="Comma-separated glob pattern(s) of fully-qualified model names to exclude.",
)

AST_OPTION = typer.Option(False, "--ast", help="Use AST discovery only (no imports executed).")

HYBRID_OPTION = typer.Option(False, "--hybrid", help="Combine AST and safe import discovery.")

TIMEOUT_OPTION = typer.Option(
    5.0,
    "--timeout",
    min=0.1,
    help="Timeout in seconds for safe import execution.",
)

MEMORY_LIMIT_OPTION = typer.Option(
    256,
    "--memory-limit-mb",
    min=1,
    help="Memory limit in megabytes for safe import subprocess.",
)

SEED_OPTION = typer.Option(
    None,
    "--seed",
    help="Seed override for regenerated artifacts.",
)

PNONE_OPTION = typer.Option(
    None,
    "--p-none",
    min=0.0,
    max=1.0,
    help="Override probability of None for optional fields.",
)

JSON_OUT_OPTION = typer.Option(
    None,
    "--json-out",
    help="Existing JSON/JSONL artifact path to compare.",
)

JSON_COUNT_OPTION = typer.Option(
    1,
    "--json-count",
    min=1,
    help="Number of JSON samples to regenerate for comparison.",
)

JSON_JSONL_OPTION = typer.Option(
    False,
    "--json-jsonl/--no-json-jsonl",
    help="Treat JSON artifact as newline-delimited JSON.",
)

JSON_INDENT_OPTION = typer.Option(
    None,
    "--json-indent",
    min=0,
    help="Indentation override for JSON output.",
)

JSON_ORJSON_OPTION = typer.Option(
    None,
    "--json-orjson/--json-std",
    help="Toggle orjson serialization for JSON diff generation.",
)

JSON_SHARD_OPTION = typer.Option(
    None,
    "--json-shard-size",
    min=1,
    help="Shard size used when the JSON artifact was generated.",
)

FIXTURES_OUT_OPTION = typer.Option(
    None,
    "--fixtures-out",
    help="Existing pytest fixtures module path to compare.",
)

FIXTURES_STYLE_OPTION = typer.Option(
    None,
    "--fixtures-style",
    help="Fixture style override (functions, factory, class).",
)

FIXTURES_SCOPE_OPTION = typer.Option(
    None,
    "--fixtures-scope",
    help="Fixture scope override (function, module, session).",
)

FIXTURES_CASES_OPTION = typer.Option(
    1,
    "--fixtures-cases",
    min=1,
    help="Number of parametrised cases per fixture.",
)

FIXTURES_RETURN_OPTION = typer.Option(
    None,
    "--fixtures-return-type",
    help="Return type override for fixtures (model or dict).",
)

SCHEMA_OUT_OPTION = typer.Option(
    None,
    "--schema-out",
    help="Existing JSON schema file path to compare.",
)

SCHEMA_INDENT_OPTION = typer.Option(
    None,
    "--schema-indent",
    min=0,
    help="Indentation override for schema JSON output.",
)

SHOW_DIFF_OPTION = typer.Option(
    False,
    "--show-diff/--no-show-diff",
    help="Show unified diffs when differences are detected.",
)


app = typer.Typer(invoke_without_command=True, subcommand_metavar="")


@dataclass(slots=True)
class DiffReport:
    kind: str
    target: Path
    checked_paths: list[Path]
    messages: list[str]
    diff_outputs: list[tuple[str, str]]
    summary: str | None

    @property
    def changed(self) -> bool:
        return bool(self.messages)


def diff(  # noqa: PLR0913 - CLI mirrors documented parameters
    ctx: typer.Context,
    path: str = PATH_ARGUMENT,
    include: str | None = INCLUDE_OPTION,
    exclude: str | None = EXCLUDE_OPTION,
    ast_mode: bool = AST_OPTION,
    hybrid_mode: bool = HYBRID_OPTION,
    timeout: float = TIMEOUT_OPTION,
    memory_limit_mb: int = MEMORY_LIMIT_OPTION,
    seed: int | None = SEED_OPTION,
    p_none: float | None = PNONE_OPTION,
    json_out: Path | None = JSON_OUT_OPTION,
    json_count: int = JSON_COUNT_OPTION,
    json_jsonl: bool = JSON_JSONL_OPTION,
    json_indent: int | None = JSON_INDENT_OPTION,
    json_orjson: bool | None = JSON_ORJSON_OPTION,
    json_shard_size: int | None = JSON_SHARD_OPTION,
    fixtures_out: Path | None = FIXTURES_OUT_OPTION,
    fixtures_style: str | None = FIXTURES_STYLE_OPTION,
    fixtures_scope: str | None = FIXTURES_SCOPE_OPTION,
    fixtures_cases: int = FIXTURES_CASES_OPTION,
    fixtures_return_type: str | None = FIXTURES_RETURN_OPTION,
    schema_out: Path | None = SCHEMA_OUT_OPTION,
    schema_indent: int | None = SCHEMA_INDENT_OPTION,
    show_diff: bool = SHOW_DIFF_OPTION,
    json_errors: bool = JSON_ERRORS_OPTION,
) -> None:
    _ = ctx
    try:
        reports = _execute_diff(
            target=path,
            include=include,
            exclude=exclude,
            ast_mode=ast_mode,
            hybrid_mode=hybrid_mode,
            timeout=timeout,
            memory_limit_mb=memory_limit_mb,
            seed_override=seed,
            p_none_override=p_none,
            json_options=JsonDiffOptions(
                out=json_out,
                count=json_count,
                jsonl=json_jsonl,
                indent=json_indent,
                use_orjson=json_orjson,
                shard_size=json_shard_size,
            ),
            fixtures_options=FixturesDiffOptions(
                out=fixtures_out,
                style=fixtures_style,
                scope=fixtures_scope,
                cases=fixtures_cases,
                return_type=fixtures_return_type,
            ),
            schema_options=SchemaDiffOptions(
                out=schema_out,
                indent=schema_indent,
            ),
        )
    except PFGError as exc:
        render_cli_error(exc, json_errors=json_errors)
        return

    changed = any(report.changed for report in reports)

    if json_errors and changed:
        payload = {
            "artifacts": [
                {
                    "kind": report.kind,
                    "target": str(report.target),
                    "checked": [str(path) for path in report.checked_paths],
                    "messages": report.messages,
                    "diffs": [
                        {"path": path, "diff": diff_text} for path, diff_text in report.diff_outputs
                    ],
                }
                for report in reports
                if report.kind and (report.changed or report.messages or report.checked_paths)
            ]
        }
        render_cli_error(DiffError("Artifacts differ.", details=payload), json_errors=True)
        return

    _render_reports(reports, show_diff)

    if changed:
        raise typer.Exit(code=1)


app.callback(invoke_without_command=True)(diff)


@dataclass(slots=True)
class JsonDiffOptions:
    out: Path | None
    count: int
    jsonl: bool
    indent: int | None
    use_orjson: bool | None
    shard_size: int | None


@dataclass(slots=True)
class FixturesDiffOptions:
    out: Path | None
    style: str | None
    scope: str | None
    cases: int
    return_type: str | None


@dataclass(slots=True)
class SchemaDiffOptions:
    out: Path | None
    indent: int | None


def _execute_diff(
    *,
    target: str,
    include: str | None,
    exclude: str | None,
    ast_mode: bool,
    hybrid_mode: bool,
    timeout: float,
    memory_limit_mb: int,
    seed_override: int | None,
    p_none_override: float | None,
    json_options: JsonDiffOptions,
    fixtures_options: FixturesDiffOptions,
    schema_options: SchemaDiffOptions,
) -> list[DiffReport]:
    if not any((json_options.out, fixtures_options.out, schema_options.out)):
        raise DiscoveryError("Provide at least one artifact path to diff.")

    target_path = Path(target)
    if not target_path.exists():
        raise DiscoveryError(f"Target path '{target}' does not exist.", details={"path": target})
    if not target_path.is_file():
        raise DiscoveryError("Target must be a Python module file.", details={"path": target})

    clear_module_cache()
    load_entrypoint_plugins()

    app_config = load_config(root=Path.cwd())

    include_patterns = split_patterns(include) if include is not None else list(app_config.include)
    exclude_patterns = split_patterns(exclude) if exclude is not None else list(app_config.exclude)

    method = _resolve_method(ast_mode, hybrid_mode)
    discovery = discover_models(
        target_path,
        include=include_patterns,
        exclude=exclude_patterns,
        method=method,
        timeout=timeout,
        memory_limit_mb=memory_limit_mb,
    )

    if discovery.errors:
        raise DiscoveryError("; ".join(discovery.errors))

    for warning in discovery.warnings:
        if warning.strip():
            typer.secho(f"warning: {warning.strip()}", err=True, fg=typer.colors.YELLOW)

    if not discovery.models:
        raise DiscoveryError("No models discovered.")

    try:
        model_classes = [load_model_class(model) for model in discovery.models]
    except RuntimeError as exc:
        raise DiscoveryError(str(exc)) from exc

    seed_value = seed_override if seed_override is not None else app_config.seed
    p_none_value = p_none_override if p_none_override is not None else app_config.p_none

    reports: list[DiffReport] = []

    if json_options.out is not None:
        reports.append(
            _diff_json_artifact(
                model_classes=model_classes,
                app_config_seed=seed_value,
                app_config_indent=app_config.json.indent,
                app_config_orjson=app_config.json.orjson,
                app_config_enum=app_config.enum_policy,
                app_config_union=app_config.union_policy,
                app_config_p_none=p_none_value,
                options=json_options,
            )
        )

    if fixtures_options.out is not None:
        reports.append(
            _diff_fixtures_artifact(
                model_classes=model_classes,
                app_config_seed=seed_value,
                app_config_p_none=p_none_value,
                app_config_style=app_config.emitters.pytest.style,
                app_config_scope=app_config.emitters.pytest.scope,
                options=fixtures_options,
            )
        )

    if schema_options.out is not None:
        reports.append(
            _diff_schema_artifact(
                model_classes=model_classes,
                app_config_indent=app_config.json.indent,
                options=schema_options,
            )
        )

    return reports


def _diff_json_artifact(
    *,
    model_classes: list[type[BaseModel]],
    app_config_seed: int | str | None,
    app_config_indent: int | None,
    app_config_orjson: bool,
    app_config_enum: str,
    app_config_union: str,
    app_config_p_none: float | None,
    options: JsonDiffOptions,
) -> DiffReport:
    if not model_classes:
        raise DiscoveryError("No models available for JSON diff.")
    if len(model_classes) > 1:
        names = ", ".join(model.__name__ for model in model_classes)
        raise DiscoveryError(
            "Multiple models discovered. Use --include/--exclude to narrow selection for JSON"
            " diffs.",
            details={"models": names},
        )

    if options.out is None:
        raise DiscoveryError("JSON diff requires --json-out.")

    target_model = model_classes[0]
    output_path = Path(options.out)

    with tempfile.TemporaryDirectory() as tmp_dir:
        temp_base = Path(tmp_dir) / "json" / output_path.name
        temp_base.parent.mkdir(parents=True, exist_ok=True)

        generator = _build_instance_generator(
            seed_value=app_config_seed,
            union_policy=app_config_union,
            enum_policy=app_config_enum,
            p_none=app_config_p_none,
        )

        def sample_factory() -> BaseModel:
            instance = generator.generate_one(target_model)
            if instance is None:
                raise MappingError(
                    f"Failed to generate instance for {target_model.__name__}.",
                    details={"model": target_model.__name__},
                )
            return instance

        indent_value = options.indent if options.indent is not None else app_config_indent
        use_orjson_value = (
            options.use_orjson if options.use_orjson is not None else app_config_orjson
        )

        try:
            generated_paths = emit_json_samples(
                sample_factory,
                output_path=temp_base,
                count=options.count,
                jsonl=options.jsonl,
                indent=indent_value,
                shard_size=options.shard_size,
                use_orjson=use_orjson_value,
                ensure_ascii=False,
            )
        except RuntimeError as exc:
            raise EmitError(str(exc)) from exc

        generated_paths = sorted(generated_paths, key=lambda p: p.name)
        actual_parent = output_path.parent if output_path.parent != Path("") else Path(".")

        checked_paths: list[Path] = []
        messages: list[str] = []
        diff_outputs: list[tuple[str, str]] = []

        for generated_path in generated_paths:
            actual_path = actual_parent / generated_path.name
            checked_paths.append(actual_path)
            if not actual_path.exists():
                messages.append(f"Missing JSON artifact: {actual_path}")
                continue
            if actual_path.is_dir():
                messages.append(f"JSON artifact path is a directory: {actual_path}")
                continue

            actual_text = actual_path.read_text(encoding="utf-8")
            generated_text = generated_path.read_text(encoding="utf-8")
            if actual_text != generated_text:
                messages.append(f"JSON artifact differs: {actual_path}")
                diff_outputs.append(
                    (
                        str(actual_path),
                        _build_unified_diff(
                            actual_text,
                            generated_text,
                            str(actual_path),
                            f"{actual_path} (generated)",
                        ),
                    )
                )

        expected_names = {path.name for path in generated_paths}
        suffix = ".jsonl" if options.jsonl else ".json"
        stem = output_path.stem if output_path.suffix else output_path.name
        pattern = f"{stem}*{suffix}"
        extra_candidates = [p for p in actual_parent.glob(pattern) if p.name not in expected_names]

        for extra in sorted(extra_candidates, key=lambda p: p.name):
            if extra.is_file():
                messages.append(f"Unexpected extra JSON artifact: {extra}")

    summary = None
    if not messages:
        summary = f"JSON artifacts match ({len(checked_paths)} file(s))."

    return DiffReport(
        kind="json",
        target=output_path,
        checked_paths=checked_paths,
        messages=messages,
        diff_outputs=diff_outputs,
        summary=summary,
    )


def _diff_fixtures_artifact(
    *,
    model_classes: list[type[BaseModel]],
    app_config_seed: int | str | None,
    app_config_p_none: float | None,
    app_config_style: str,
    app_config_scope: str,
    options: FixturesDiffOptions,
) -> DiffReport:
    if options.out is None:
        raise DiscoveryError("Fixtures diff requires --fixtures-out.")

    output_path = Path(options.out)
    style_value = _coerce_style(options.style)
    scope_value = _coerce_scope(options.scope)
    return_type_value = _coerce_return_type(options.return_type)

    seed_normalized: int | None = None
    if app_config_seed is not None:
        seed_normalized = SeedManager(seed=app_config_seed).normalized_seed

    style_default = cast(StyleLiteral, app_config_style)
    style_final: StyleLiteral = style_value or style_default
    scope_final = scope_value or app_config_scope
    return_type_default: ReturnLiteral = DEFAULT_RETURN
    return_type_final: ReturnLiteral = return_type_value or return_type_default

    with tempfile.TemporaryDirectory() as tmp_dir:
        temp_out = Path(tmp_dir) / "fixtures" / output_path.name
        temp_out.parent.mkdir(parents=True, exist_ok=True)

        pytest_config = PytestEmitConfig(
            scope=scope_final,
            style=style_final,
            return_type=return_type_final,
            cases=options.cases,
            seed=seed_normalized,
            optional_p_none=app_config_p_none,
        )

        context = EmitterContext(
            models=tuple(model_classes),
            output=temp_out,
            parameters={
                "style": style_final,
                "scope": scope_final,
                "cases": options.cases,
                "return_type": return_type_final,
            },
        )

        generated_path: Path
        if emit_artifact("fixtures", context):
            generated_path = temp_out
        else:
            try:
                result = emit_pytest_fixtures(
                    model_classes,
                    output_path=temp_out,
                    config=pytest_config,
                )
            except Exception as exc:  # pragma: no cover - defensive
                raise EmitError(str(exc)) from exc
            generated_path = result.path

        if not generated_path.exists() or generated_path.is_dir():
            raise EmitError("Fixture emitter did not produce a file to diff.")

        generated_text = generated_path.read_text(encoding="utf-8")

    actual_path = output_path
    checked_paths = [actual_path]
    messages: list[str] = []
    diff_outputs: list[tuple[str, str]] = []

    if not actual_path.exists():
        messages.append(f"Missing fixtures module: {actual_path}")
    elif actual_path.is_dir():
        messages.append(f"Fixtures path is a directory: {actual_path}")
    else:
        actual_text = actual_path.read_text(encoding="utf-8")
        if actual_text != generated_text:
            messages.append(f"Fixtures module differs: {actual_path}")
            diff_outputs.append(
                (
                    str(actual_path),
                    _build_unified_diff(
                        actual_text,
                        generated_text,
                        str(actual_path),
                        f"{actual_path} (generated)",
                    ),
                )
            )

    summary = None
    if not messages:
        summary = "Fixtures artifact matches."

    return DiffReport(
        kind="fixtures",
        target=output_path,
        checked_paths=checked_paths,
        messages=messages,
        diff_outputs=diff_outputs,
        summary=summary,
    )


def _diff_schema_artifact(
    *,
    model_classes: list[type[BaseModel]],
    app_config_indent: int | None,
    options: SchemaDiffOptions,
) -> DiffReport:
    if options.out is None:
        raise DiscoveryError("Schema diff requires --schema-out.")

    output_path = Path(options.out)

    indent_value = options.indent if options.indent is not None else app_config_indent

    with tempfile.TemporaryDirectory() as tmp_dir:
        temp_out = Path(tmp_dir) / "schema" / output_path.name
        temp_out.parent.mkdir(parents=True, exist_ok=True)

        context = EmitterContext(
            models=tuple(model_classes),
            output=temp_out,
            parameters={"indent": indent_value},
        )

        if emit_artifact("schema", context):
            generated_path = temp_out
        else:
            try:
                if len(model_classes) == 1:
                    generated_path = emit_model_schema(
                        model_classes[0],
                        output_path=temp_out,
                        indent=indent_value,
                        ensure_ascii=False,
                    )
                else:
                    generated_path = emit_models_schema(
                        model_classes,
                        output_path=temp_out,
                        indent=indent_value,
                        ensure_ascii=False,
                    )
            except Exception as exc:  # pragma: no cover - defensive
                raise EmitError(str(exc)) from exc

        if not generated_path.exists() or generated_path.is_dir():
            raise EmitError("Schema emitter did not produce a file to diff.")

        generated_text = generated_path.read_text(encoding="utf-8")

    actual_path = output_path
    checked_paths = [actual_path]
    messages: list[str] = []
    diff_outputs: list[tuple[str, str]] = []

    if not actual_path.exists():
        messages.append(f"Missing schema artifact: {actual_path}")
    elif actual_path.is_dir():
        messages.append(f"Schema path is a directory: {actual_path}")
    else:
        actual_text = actual_path.read_text(encoding="utf-8")
        if actual_text != generated_text:
            messages.append(f"Schema artifact differs: {actual_path}")
            diff_outputs.append(
                (
                    str(actual_path),
                    _build_unified_diff(
                        actual_text,
                        generated_text,
                        str(actual_path),
                        f"{actual_path} (generated)",
                    ),
                )
            )

    summary = None
    if not messages:
        summary = "Schema artifact matches."

    return DiffReport(
        kind="schema",
        target=output_path,
        checked_paths=checked_paths,
        messages=messages,
        diff_outputs=diff_outputs,
        summary=summary,
    )


def _build_instance_generator(
    *,
    seed_value: int | str | None,
    union_policy: str,
    enum_policy: str,
    p_none: float | None,
) -> InstanceGenerator:
    normalized_seed: int | None = None
    if seed_value is not None:
        normalized_seed = SeedManager(seed=seed_value).normalized_seed

    p_none_value = p_none if p_none is not None else 0.0

    gen_config = GenerationConfig(
        seed=normalized_seed,
        enum_policy=enum_policy,
        union_policy=union_policy,
        default_p_none=p_none_value,
        optional_p_none=p_none_value,
    )
    return InstanceGenerator(config=gen_config)


def _resolve_method(ast_mode: bool, hybrid_mode: bool) -> DiscoveryMethod:
    if ast_mode and hybrid_mode:
        raise DiscoveryError("Choose only one of --ast or --hybrid.")
    if hybrid_mode:
        return "hybrid"
    if ast_mode:
        return "ast"
    return "import"


def _render_reports(reports: Iterable[DiffReport], show_diff: bool) -> None:
    reports = list(reports)
    if not reports:
        typer.secho("No artifacts were compared.", fg=typer.colors.YELLOW)
        return

    any_changes = False
    for report in reports:
        if report.changed:
            any_changes = True
            typer.secho(f"{report.kind.upper()} differences detected:", fg=typer.colors.YELLOW)
            for message in report.messages:
                typer.echo(f"  - {message}")
            if show_diff:
                for _path, diff_text in report.diff_outputs:
                    if diff_text:
                        typer.echo(diff_text.rstrip())
                        typer.echo()
        else:
            if report.summary:
                typer.echo(report.summary)

    if not any_changes:
        typer.secho("All compared artifacts match.", fg=typer.colors.GREEN)


def _build_unified_diff(
    original: str,
    regenerated: str,
    original_label: str,
    regenerated_label: str,
) -> str:
    diff = difflib.unified_diff(
        original.splitlines(keepends=True),
        regenerated.splitlines(keepends=True),
        fromfile=original_label,
        tofile=regenerated_label,
    )
    return "".join(diff)


__all__ = ["app"]
