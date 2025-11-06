"""CLI command to explain strategies for models and fields."""

from __future__ import annotations

import dataclasses
import decimal
import enum
import json
import types
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Union, get_args, get_origin, get_type_hints

import typer
from pydantic import BaseModel

from pydantic_fixturegen.core.errors import DiscoveryError, PFGError
from pydantic_fixturegen.core.providers import create_default_registry
from pydantic_fixturegen.core.schema import FieldSummary, summarize_model_fields
from pydantic_fixturegen.core.strategies import StrategyBuilder, StrategyResult, UnionStrategy
from pydantic_fixturegen.plugins.loader import get_plugin_manager

from ._common import (
    JSON_ERRORS_OPTION,
    clear_module_cache,
    discover_models,
    load_model_class,
    render_cli_error,
    split_patterns,
)

PATH_ARGUMENT = typer.Argument(..., help="Path to a Python module containing Pydantic models.")

INCLUDE_OPTION = typer.Option(
    None,
    "--include",
    "-i",
    help="Comma-separated pattern(s) of fully-qualified model names to include.",
)

EXCLUDE_OPTION = typer.Option(
    None,
    "--exclude",
    "-e",
    help="Comma-separated pattern(s) of fully-qualified model names to exclude.",
)

JSON_OUTPUT_OPTION = typer.Option(
    False,
    "--json",
    help="Emit a structured JSON description of strategies instead of formatted text.",
)

TREE_OPTION = typer.Option(
    False,
    "--tree",
    help="Render an ASCII tree illustrating strategy composition.",
)

MAX_DEPTH_OPTION = typer.Option(
    None,
    "--max-depth",
    min=0,
    help="Limit nested strategy expansion depth (0 shows only top-level strategies).",
)


@dataclass(slots=True)
class TreeNode:
    label: str
    children: list[TreeNode]


app = typer.Typer(invoke_without_command=True, subcommand_metavar="")


def explain(  # noqa: D401 - Typer callback
    ctx: typer.Context,
    path: str = PATH_ARGUMENT,
    include: str | None = INCLUDE_OPTION,
    exclude: str | None = EXCLUDE_OPTION,
    json_output: bool = JSON_OUTPUT_OPTION,
    tree_mode: bool = TREE_OPTION,
    max_depth: int | None = MAX_DEPTH_OPTION,
    json_errors: bool = JSON_ERRORS_OPTION,
) -> None:
    _ = ctx  # unused
    if json_output and tree_mode:
        render_cli_error(
            DiscoveryError("--json and --tree cannot be combined."),
            json_errors=json_errors,
        )
        return

    try:
        data = _execute_explain(
            target=path,
            include=include,
            exclude=exclude,
            max_depth=max_depth,
            emit_warnings=not json_output,
        )
    except PFGError as exc:
        render_cli_error(exc, json_errors=json_errors)
        return
    except ValueError as exc:
        render_cli_error(DiscoveryError(str(exc)), json_errors=json_errors)
        return

    if json_output:
        payload = {"warnings": data["warnings"], "models": data["models"]}
        typer.echo(json.dumps(payload, indent=2, default=str))
        return

    if not data["models"]:
        # Warnings and "No models discovered." already emitted when requested.
        return

    if tree_mode:
        _render_tree(data["models"])
    else:
        _render_text_reports(data["models"])


app.callback(invoke_without_command=True)(explain)


def _execute_explain(
    *,
    target: str,
    include: str | None,
    exclude: str | None,
    max_depth: int | None = None,
    emit_warnings: bool = True,
) -> dict[str, Any]:
    path = Path(target)
    if not path.exists():
        raise ValueError(f"Target path '{target}' does not exist.")
    if not path.is_file():
        raise ValueError("Target must be a Python module file.")

    clear_module_cache()

    discovery = discover_models(
        path,
        include=split_patterns(include),
        exclude=split_patterns(exclude),
    )

    if discovery.errors:
        raise ValueError("; ".join(discovery.errors))

    warnings = [warning.strip() for warning in discovery.warnings if warning.strip()]
    if emit_warnings:
        for warning in warnings:
            typer.secho(f"warning: {warning}", err=True, fg=typer.colors.YELLOW)

    if not discovery.models:
        if emit_warnings:
            typer.echo("No models discovered.")
        return {"warnings": warnings, "models": []}

    registry = create_default_registry(load_plugins=True)
    builder = StrategyBuilder(registry, plugin_manager=get_plugin_manager())
    depth_budget = None if max_depth is None else max_depth

    reports: list[dict[str, Any]] = []
    for model_info in discovery.models:
        model_cls = load_model_class(model_info)
        report = _collect_model_report(
            model_cls,
            builder=builder,
            max_depth=depth_budget,
            visited=set(),
        )
        reports.append(report)

    return {"warnings": warnings, "models": reports}


def _collect_model_report(
    model_cls: type[BaseModel],
    *,
    builder: StrategyBuilder,
    max_depth: int | None,
    visited: set[type[Any]],
) -> dict[str, Any]:
    qualname = _describe_type(model_cls)
    report: dict[str, Any] = {
        "kind": "model",
        "name": model_cls.__name__,
        "module": model_cls.__module__,
        "qualname": qualname,
        "fields": [],
    }

    if model_cls in visited:
        report["cycle"] = True
        return report

    visited.add(model_cls)
    summaries = summarize_model_fields(model_cls)

    for field_name, field in model_cls.model_fields.items():
        summary = summaries[field_name]
        field_report: dict[str, Any] = {
            "name": field_name,
            "summary": _summary_to_payload(summary),
        }
        try:
            strategy = builder.build_field_strategy(
                model_cls,
                field_name,
                field.annotation,
                summary,
            )
        except ValueError as exc:
            field_report["error"] = str(exc)
        else:
            field_report["strategy"] = _strategy_to_payload(
                strategy,
                builder=builder,
                remaining_depth=max_depth,
                visited=visited,
            )
        report["fields"].append(field_report)

    visited.remove(model_cls)
    return report


def _strategy_to_payload(
    strategy: StrategyResult,
    *,
    builder: StrategyBuilder,
    remaining_depth: int | None,
    visited: set[type[Any]],
) -> dict[str, Any]:
    if isinstance(strategy, UnionStrategy):
        payload: dict[str, Any] = {
            "kind": "union",
            "field": strategy.field_name,
            "policy": strategy.policy,
            "options": [],
        }
        if remaining_depth is not None and remaining_depth <= 0:
            payload["truncated"] = True
            return payload

        next_depth = None if remaining_depth is None else remaining_depth - 1
        for index, choice in enumerate(strategy.choices, start=1):
            option_summary = _summary_to_payload(choice.summary)
            option_payload: dict[str, Any] = {
                "index": index,
                "summary": option_summary,
                "annotation": _describe_annotation(choice.annotation),
                "strategy": _strategy_to_payload(
                    choice,
                    builder=builder,
                    remaining_depth=next_depth,
                    visited=visited,
                ),
            }
            payload["options"].append(option_payload)
        return payload

    provider_payload: dict[str, Any] = {
        "kind": "provider",
        "field": strategy.field_name,
        "provider": strategy.provider_name,
        "p_none": strategy.p_none,
        "summary_type": strategy.summary.type,
        "annotation": _describe_annotation(strategy.annotation),
    }
    if strategy.enum_values is not None:
        provider_payload["enum_values"] = _safe_json(strategy.enum_values)
    if strategy.enum_policy:
        provider_payload["enum_policy"] = strategy.enum_policy
    if strategy.provider_kwargs:
        provider_payload["provider_kwargs"] = _safe_json(strategy.provider_kwargs)

    if remaining_depth is not None and remaining_depth <= 0:
        provider_payload["truncated"] = True
        return provider_payload

    next_depth = None if remaining_depth is None else remaining_depth - 1
    summary_type = strategy.summary.type
    annotation = strategy.annotation
    if (
        summary_type == "model"
        and isinstance(annotation, type)
        and issubclass(annotation, BaseModel)
    ):
        provider_payload["nested_model"] = _collect_model_report(
            annotation,
            builder=builder,
            max_depth=next_depth,
            visited=visited,
        )
    elif summary_type == "dataclass" and isinstance(annotation, type):
        provider_payload["nested_model"] = _collect_dataclass_report(
            annotation,
            builder=builder,
            max_depth=next_depth,
            visited=visited,
        )
    return provider_payload


def _collect_dataclass_report(
    cls: type[Any],
    *,
    builder: StrategyBuilder,
    max_depth: int | None,
    visited: set[type[Any]],
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "kind": "dataclass",
        "qualname": _describe_type(cls),
        "fields": [],
    }

    if cls in visited:
        report["cycle"] = True
        return report

    if not dataclasses.is_dataclass(cls):
        report["unsupported"] = True
        return report

    try:
        dc_fields = dataclasses.fields(cls)
    except TypeError:
        report["unsupported"] = True
        return report

    try:
        type_hints = get_type_hints(cls, include_extras=True)
    except (NameError, TypeError):  # pragma: no cover - defensive
        type_hints = {}

    visited.add(cls)
    for field in dc_fields:
        resolved_type = type_hints.get(field.name, field.type)
        annotation_desc = _describe_annotation(resolved_type)
        summary: dict[str, Any] = {
            "type": annotation_desc or "unknown",
            "annotation": annotation_desc,
            "origin": "dataclass",
        }
        if field.default is not dataclasses.MISSING:
            summary["default"] = _safe_json(field.default)
        else:
            default_factory = getattr(field, "default_factory", dataclasses.MISSING)
            if default_factory is not dataclasses.MISSING:
                summary["default_factory"] = _describe_callable(default_factory)

        field_entry: dict[str, Any] = {
            "name": field.name,
            "summary": summary,
        }

        if max_depth is not None and max_depth <= 0:
            field_entry["truncated"] = True
        else:
            next_depth = None if max_depth is None else max_depth - 1
            nested_type = _resolve_runtime_type(resolved_type)
            if isinstance(nested_type, type) and nested_type not in visited:
                if _is_subclass(nested_type, BaseModel):
                    field_entry["nested"] = _collect_model_report(
                        nested_type,
                        builder=builder,
                        max_depth=next_depth,
                        visited=visited,
                    )
                elif dataclasses.is_dataclass(nested_type):
                    field_entry["nested"] = _collect_dataclass_report(
                        nested_type,
                        builder=builder,
                        max_depth=next_depth,
                        visited=visited,
                    )

        report["fields"].append(field_entry)

    visited.remove(cls)
    return report


def _summary_to_payload(summary: FieldSummary) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": summary.type,
        "is_optional": summary.is_optional,
    }
    if summary.format:
        payload["format"] = summary.format
    if summary.item_type:
        payload["item_type"] = summary.item_type
    if summary.enum_values is not None:
        payload["enum_values"] = _safe_json(summary.enum_values)
    annotation_desc = _describe_annotation(summary.annotation)
    if annotation_desc is not None:
        payload["annotation"] = annotation_desc
    item_annotation_desc = _describe_annotation(summary.item_annotation)
    if item_annotation_desc is not None:
        payload["item_annotation"] = item_annotation_desc
    constraints = _constraints_to_dict(summary)
    if constraints:
        payload["constraints"] = constraints
    return payload


def _constraints_to_dict(summary: FieldSummary) -> dict[str, Any]:
    if not summary.constraints.has_constraints():
        return {}
    constraints = summary.constraints
    data: dict[str, Any] = {}
    for key in (
        "ge",
        "le",
        "gt",
        "lt",
        "multiple_of",
        "min_length",
        "max_length",
        "pattern",
        "max_digits",
        "decimal_places",
    ):
        value = getattr(constraints, key)
        if value is not None:
            data[key] = _safe_json(value)
    return data


def _resolve_runtime_type(annotation: Any) -> type[Any] | None:
    if isinstance(annotation, types.GenericAlias):
        return None
    if isinstance(annotation, type):
        return annotation

    origin = get_origin(annotation)
    if origin is None:
        return None

    if origin in {list, set, tuple, dict}:
        return None

    if origin is Annotated:
        args = get_args(annotation)
        if args:
            return _resolve_runtime_type(args[0])

    if origin in {Union, types.UnionType}:
        args = tuple(arg for arg in get_args(annotation) if arg is not type(None))  # noqa: E721
        if len(args) == 1:
            return _resolve_runtime_type(args[0])
        return None

    return None


def _describe_callable(factory: Any) -> str:
    name = getattr(factory, "__qualname__", getattr(factory, "__name__", None))
    module = getattr(factory, "__module__", None)
    if name and module:
        return f"{module}.{name}"
    if name:
        return str(name)
    return repr(factory)


def _safe_json(value: Any) -> Any:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, enum.Enum):
        raw = value.value
        if isinstance(raw, str | int | float | bool):
            return raw
        return str(raw)
    if isinstance(value, decimal.Decimal):
        try:
            return float(value)
        except (OverflowError, ValueError):
            return str(value)
    if isinstance(value, Mapping):
        return {str(key): _safe_json(val) for key, val in value.items()}
    if isinstance(value, list | tuple | set):
        return [_safe_json(item) for item in value]
    return str(value)


def _describe_annotation(annotation: Any) -> str | None:
    if annotation is None:
        return None
    if isinstance(annotation, type):
        return _describe_type(annotation)
    return repr(annotation)


def _describe_type(tp: type[Any]) -> str:
    return f"{tp.__module__}.{tp.__qualname__}"


def _is_subclass(candidate: type[Any], parent: type[Any]) -> bool:
    try:
        return issubclass(candidate, parent)
    except TypeError:
        return False


def _render_text_reports(models: list[dict[str, Any]]) -> None:
    for model in models:
        typer.echo(f"Model: {model['qualname']}")
        fields = model.get("fields", [])
        if not fields:
            typer.echo("  (no fields)")
            typer.echo("")
            continue
        for field in fields:
            _render_field_text(field, indent="  ")
        typer.echo("")


def _render_field_text(field: dict[str, Any], *, indent: str) -> None:
    summary = field.get("summary", {})
    typer.echo(f"{indent}Field: {field['name']}")
    typer.echo(f"{indent}  Type: {summary.get('type')}")
    if summary.get("format"):
        typer.echo(f"{indent}  Format: {summary['format']}")
    if summary.get("is_optional"):
        typer.echo(f"{indent}  Optional: True")
    if summary.get("constraints"):
        typer.echo(f"{indent}  Constraints: {summary['constraints']}")
    if "default" in summary:
        typer.echo(f"{indent}  Default: {summary['default']}")
    if "default_factory" in summary:
        typer.echo(f"{indent}  Default factory: {summary['default_factory']}")

    if field.get("error"):
        typer.echo(f"{indent}  Issue: {field['error']}")
        return

    if field.get("truncated"):
        typer.echo(f"{indent}  ... (max depth reached)")
        return

    nested = field.get("nested")
    if nested:
        _render_nested_model_text(nested, indent=indent + "  ")
        return

    strategy = field.get("strategy")
    if strategy:
        _render_strategy_text(strategy, indent=indent + "  ")


def _render_strategy_text(strategy: dict[str, Any], *, indent: str) -> None:
    if strategy["kind"] == "union":
        typer.echo(f"{indent}Union policy: {strategy['policy']}")
        if strategy.get("truncated"):
            typer.echo(f"{indent}  ... (max depth reached)")
            return
        for option in strategy.get("options", []):
            option_summary = option.get("summary", {})
            typer.echo(f"{indent}  Option {option['index']} -> type: {option_summary.get('type')}")
            nested = option.get("strategy")
            if nested:
                _render_strategy_text(nested, indent=indent + "    ")
        return

    provider = strategy.get("provider") or "unknown"
    typer.echo(f"{indent}Provider: {provider}")
    if strategy.get("p_none") is not None:
        typer.echo(f"{indent}p_none: {strategy['p_none']}")
    if strategy.get("enum_values") is not None:
        typer.echo(f"{indent}Enum values: {strategy['enum_values']}")
    if strategy.get("enum_policy"):
        typer.echo(f"{indent}Enum policy: {strategy['enum_policy']}")
    if strategy.get("provider_kwargs"):
        typer.echo(f"{indent}Provider kwargs: {strategy['provider_kwargs']}")
    if strategy.get("truncated"):
        typer.echo(f"{indent}... (max depth reached)")
        return

    nested = strategy.get("nested_model")
    if nested:
        _render_nested_model_text(nested, indent=indent)


def _render_nested_model_text(model: dict[str, Any], *, indent: str) -> None:
    qualname = model.get("qualname", "<unknown>")
    if model.get("cycle"):
        typer.echo(f"{indent}Nested model: {qualname} (cycle detected)")
        return
    if model.get("unsupported"):
        typer.echo(f"{indent}Nested model: {qualname} (not expanded)")
        return

    typer.echo(f"{indent}Nested model: {qualname}")
    for nested_field in model.get("fields", []):
        _render_field_text(nested_field, indent=indent + "  ")


def _render_tree(models: list[dict[str, Any]]) -> None:
    nodes = [_model_to_tree(model) for model in models]
    for index, node in enumerate(nodes):
        typer.echo(node.label)
        _render_tree_children(node.children, prefix="")
        if index != len(nodes) - 1:
            typer.echo("")


def _model_to_tree(model: dict[str, Any]) -> TreeNode:
    fields = model.get("fields", [])
    if not fields:
        children = [TreeNode("(no fields)", [])]
    else:
        children = [_field_to_tree(field) for field in fields]
    return TreeNode(f"Model {model['qualname']}", children)


def _field_to_tree(field: dict[str, Any]) -> TreeNode:
    summary = field.get("summary", {})
    label = f"field {field['name']} [type={summary.get('type')}]"

    if field.get("error"):
        return TreeNode(label, [TreeNode(f"error: {field['error']}", [])])

    strategy = field.get("strategy")
    children = []
    if strategy:
        children.append(_strategy_to_tree_node(strategy))
    nested = field.get("nested")
    if nested:
        children.append(_nested_model_to_tree(nested))
    if field.get("truncated"):
        children.append(TreeNode("... (max depth reached)", []))
    return TreeNode(label, children)


def _strategy_to_tree_node(strategy: dict[str, Any]) -> TreeNode:
    if strategy["kind"] == "union":
        label = f"union policy={strategy['policy']}"
        if strategy.get("truncated"):
            option_nodes = [TreeNode("... (max depth reached)", [])]
        else:
            option_nodes = []
            for option in strategy.get("options", []):
                summary = option.get("summary", {})
                option_label = f"option {option['index']} [type={summary.get('type')}]"
                option_strategy = option.get("strategy")
                option_children = []
                if option_strategy:
                    option_children.append(_strategy_to_tree_node(option_strategy))
                option_nodes.append(TreeNode(option_label, option_children))
        return TreeNode(label, option_nodes)

    provider = strategy.get("provider") or "<unknown>"
    p_none = strategy.get("p_none")
    label = f"provider {provider}"
    if p_none is not None:
        label += f" (p_none={p_none})"

    children = []
    if strategy.get("enum_values") is not None:
        children.append(TreeNode(f"enum_values={strategy['enum_values']}", []))
    if strategy.get("enum_policy"):
        children.append(TreeNode(f"enum_policy={strategy['enum_policy']}", []))
    if strategy.get("provider_kwargs"):
        children.append(TreeNode(f"provider_kwargs={strategy['provider_kwargs']}", []))
    if strategy.get("truncated"):
        children.append(TreeNode("... (max depth reached)", []))
    else:
        nested = strategy.get("nested_model")
        if nested:
            children.append(_nested_model_to_tree(nested))
    return TreeNode(label, children)


def _nested_model_to_tree(model: dict[str, Any]) -> TreeNode:
    qualname = model.get("qualname", "<unknown>")
    if model.get("cycle"):
        return TreeNode(f"nested {qualname} (cycle detected)", [])
    if model.get("unsupported"):
        return TreeNode(f"nested {qualname} (not expanded)", [])
    fields = model.get("fields", [])
    children = [_field_to_tree(field) for field in fields] or [TreeNode("(no fields)", [])]
    return TreeNode(f"nested {qualname}", children)


def _render_tree_children(children: list[TreeNode], *, prefix: str) -> None:
    for index, child in enumerate(children):
        is_last = index == len(children) - 1
        branch = "`-- " if is_last else "|-- "
        typer.echo(f"{prefix}{branch}{child.label}")
        next_prefix = f"{prefix}{'    ' if is_last else '|   '}"
        _render_tree_children(child.children, prefix=next_prefix)


__all__ = ["app"]
