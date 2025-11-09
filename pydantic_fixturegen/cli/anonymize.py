"""CLI entrypoint for the deterministic anonymizer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

from pydantic_fixturegen.anonymize import AnonymizeConfig, build_config_from_rules
from pydantic_fixturegen.anonymize.pipeline import Anonymizer
from pydantic_fixturegen.cli.doctor import _execute_doctor
from pydantic_fixturegen.cli.gen._common import JSON_ERRORS_OPTION, render_cli_error
from pydantic_fixturegen.core.errors import EmitError
from pydantic_fixturegen.logging import Logger, get_logger

app = typer.Typer(
    invoke_without_command=True,
    subcommand_metavar="",
    help="Anonymize JSON payloads deterministically according to rule files.",
)

INPUT_ARGUMENT = typer.Argument(
    ...,
    help="Path to a JSON/JSONL file or directory containing payloads to anonymize.",
)

OUTPUT_OPTION = typer.Option(
    None,
    "--out",
    "-o",
    help="Destination file or directory for anonymized payloads (positional shortcut available).",
)

OUTPUT_ARGUMENT = typer.Argument(
    None,
    help="Optional destination when you prefer positional syntax instead of --out.",
)

RULES_OPTION = typer.Option(
    ...,
    "--rules",
    "-r",
    help="Path to a TOML/YAML/JSON rule file describing anonymization strategies.",
)

PROFILE_OPTION = typer.Option(
    None,
    "--profile",
    help="Apply a built-in privacy profile (pii-safe, realistic, edge, adversarial).",
)

SALT_OPTION = typer.Option(
    None,
    "--salt",
    help="Override the salt used for deterministic pseudonyms.",
)

ENTITY_OPTION = typer.Option(
    None,
    "--entity-field",
    help="Dotted path used to derive stable entity identifiers (e.g. 'user.id').",
)

REPORT_OPTION = typer.Option(
    None,
    "--report",
    help="Optional JSON file capturing anonymization summary and diff samples.",
)

BUDGET_REQUIRED_OPTION = typer.Option(
    None,
    "--max-required-misses",
    min=0,
    help="Override the allowed number of required rule misses (default from profile/rules).",
)

BUDGET_FAILURE_OPTION = typer.Option(
    None,
    "--max-rule-failures",
    min=0,
    help="Override maximum rule execution failures (default from profile/rules).",
)

DOCTOR_TARGET_OPTION = typer.Option(
    None,
    "--doctor-target",
    help="Optional module path analysed via pfg doctor after anonymization.",
)

DOCTOR_INCLUDE_OPTION = typer.Option(
    None,
    "--doctor-include",
    help="Include filter passed to the doctor analysis when --doctor-target is supplied.",
)

DOCTOR_EXCLUDE_OPTION = typer.Option(
    None,
    "--doctor-exclude",
    help="Exclude filter passed to the doctor analysis when --doctor-target is supplied.",
)

DOCTOR_TIMEOUT_OPTION = typer.Option(
    5.0,
    "--doctor-timeout",
    min=0.1,
    help="Timeout in seconds for doctor safe-import discovery.",
)

DOCTOR_MEMORY_OPTION = typer.Option(
    256,
    "--doctor-memory-mb",
    min=32,
    help="Memory limit in MB for doctor safe-import discovery.",
)


@dataclass
class FileMeta:
    path: Path
    format: str
    single_object: bool


@app.callback(invoke_without_command=True)
def anonymize(  # noqa: PLR0913
    input_path: Path = INPUT_ARGUMENT,
    output_argument: Path | None = OUTPUT_ARGUMENT,
    output: Path | None = OUTPUT_OPTION,
    rules: Path = RULES_OPTION,
    profile: str | None = PROFILE_OPTION,
    salt: str | None = SALT_OPTION,
    entity_field: str | None = ENTITY_OPTION,
    report: Path | None = REPORT_OPTION,
    max_required_misses: int | None = BUDGET_REQUIRED_OPTION,
    max_rule_failures: int | None = BUDGET_FAILURE_OPTION,
    doctor_target: Path | None = DOCTOR_TARGET_OPTION,
    doctor_include: str | None = DOCTOR_INCLUDE_OPTION,
    doctor_exclude: str | None = DOCTOR_EXCLUDE_OPTION,
    doctor_timeout: float = DOCTOR_TIMEOUT_OPTION,
    doctor_memory_mb: int = DOCTOR_MEMORY_OPTION,
    json_errors: bool = JSON_ERRORS_OPTION,
) -> None:
    logger = get_logger()
    try:
        destination = output or output_argument
        if destination is None:
            raise EmitError("Provide --out/--output or a positional destination path.")
        budget_overrides: dict[str, int | None] = {}
        if max_required_misses is not None:
            budget_overrides["max_required_rule_misses"] = max_required_misses
        if max_rule_failures is not None:
            budget_overrides["max_rule_failures"] = max_rule_failures

        config = build_config_from_rules(
            rules_path=rules,
            profile=profile,
            override_salt=salt,
            entity_field=entity_field,
            budget_overrides=budget_overrides or None,
        )
        files = _collect_input_files(input_path)
        aggregated = _run_anonymization(
            files=files,
            input_root=input_path,
            output=destination,
            config_path=rules,
            config=config,
            doctor_target=doctor_target,
            doctor_include=doctor_include,
            doctor_exclude=doctor_exclude,
            doctor_timeout=doctor_timeout,
            doctor_memory=doctor_memory_mb,
            logger=logger,
        )
    except EmitError as exc:
        render_cli_error(exc, json_errors=json_errors)
        return
    except Exception as exc:  # pragma: no cover - unexpected
        render_cli_error(EmitError(str(exc)), json_errors=json_errors)
        return

    typer.echo(
        "Anonymized "
        f"{aggregated['records_processed']} records across {aggregated['files_processed']} file(s)."
    )
    if report is not None:
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(aggregated, indent=2), encoding="utf-8")
        typer.echo(f"Wrote anonymization report to {report}")


def _collect_input_files(input_path: Path) -> list[Path]:
    if not input_path.exists():
        raise EmitError(f"Input path '{input_path}' does not exist.")
    if input_path.is_file():
        return [input_path]
    candidates = [
        path
        for path in input_path.rglob("*")
        if path.is_file() and path.suffix.lower() in {".json", ".jsonl", ".ndjson"}
    ]
    if not candidates:
        raise EmitError(f"No JSON/JSONL files discovered under '{input_path}'.")
    return sorted(candidates)


def _run_anonymization(
    *,
    files: list[Path],
    input_root: Path,
    output: Path,
    config_path: Path,
    config: AnonymizeConfig,
    doctor_target: Path | None,
    doctor_include: str | None,
    doctor_exclude: str | None,
    doctor_timeout: float,
    doctor_memory: int,
    logger: Logger,
) -> dict[str, Any]:
    output_is_dir = output.is_dir() or (
        not output.exists() and (len(files) > 1 or input_root.is_dir())
    )
    if output_is_dir:
        output.mkdir(parents=True, exist_ok=True)
    totals: dict[str, Any] = {
        "files_processed": 0,
        "records_processed": 0,
        "fields_anonymized": 0,
        "strategies": {},
        "rules": {},
        "rule_failures": {},
        "required_rule_misses": 0,
        "diffs": [],
        "profile": config.profile,
        "config_path": str(config_path),
    }
    doctor_summary: dict[str, Any] | None = None

    for file_path in files:
        records, meta = _read_records(file_path)
        anonymizer = Anonymizer(config, logger=logger)
        anonymized, report = anonymizer.anonymize_records(records)
        totals["files_processed"] += 1
        totals["records_processed"] += report.records_processed
        totals["fields_anonymized"] += report.fields_anonymized
        _merge_counts(totals["strategies"], report.strategy_counts)
        _merge_counts(totals["rules"], report.rule_matches)
        _merge_counts(totals["rule_failures"], report.rule_failures)
        totals["required_rule_misses"] += report.required_rule_misses
        if len(totals["diffs"]) < 50:
            totals["diffs"].extend(
                {
                    "path": diff.path,
                    "before": diff.before,
                    "after": diff.after,
                    "strategy": diff.strategy,
                    "record_index": diff.record_index,
                    "source": str(file_path),
                }
                for diff in report.diffs
            )
        out_path = _resolve_output_path(
            input_path=file_path,
            input_root=input_root,
            output=output,
            output_is_dir=output_is_dir,
            meta=meta,
        )
        _write_records(anonymized, meta, out_path)

    if doctor_target is not None:
        doctor_summary = _doctor_gap_summary(
            doctor_target,
            include=doctor_include,
            exclude=doctor_exclude,
            timeout=doctor_timeout,
            memory_limit_mb=doctor_memory,
        )
        totals["doctor_summary"] = doctor_summary

    return totals


def _merge_counts(target: dict[str, int], incoming: dict[str, int]) -> None:
    for key, value in incoming.items():
        target[key] = target.get(key, 0) + value


def _resolve_output_path(
    *,
    input_path: Path,
    input_root: Path,
    output: Path,
    output_is_dir: bool,
    meta: FileMeta,
) -> Path:
    if not output_is_dir:
        return output
    relative = Path(input_path.name) if input_root.is_file() else input_path.relative_to(input_root)
    destination = output / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def _read_records(path: Path) -> tuple[list[dict[str, Any]], FileMeta]:
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix in {".jsonl", ".ndjson"}:
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
        return records, FileMeta(path=path, format="jsonl", single_object=False)
    data = json.loads(text)
    if isinstance(data, list):
        return data, FileMeta(path=path, format="json", single_object=False)
    if isinstance(data, dict):
        return [data], FileMeta(path=path, format="json", single_object=True)
    raise EmitError(f"Unsupported JSON structure in '{path}'. Expected object or array.")


def _write_records(records: list[dict[str, Any]], meta: FileMeta, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if meta.format == "jsonl":
        with destination.open("w", encoding="utf-8") as fh:
            for record in records:
                fh.write(json.dumps(record))
                fh.write("\n")
        return
    payload: Any = records[0] if meta.single_object and records else records
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _doctor_gap_summary(
    path: Path,
    *,
    include: str | None,
    exclude: str | None,
    timeout: float,
    memory_limit_mb: int,
) -> dict[str, Any]:
    summary = _execute_doctor(
        target=str(path),
        include=include,
        exclude=exclude,
        ast_mode=False,
        hybrid_mode=False,
        timeout=timeout,
        memory_limit_mb=memory_limit_mb,
        render=False,
    )
    return {
        "total_error_fields": summary.total_error_fields,
        "total_warning_fields": summary.total_warning_fields,
        "gaps": [
            {
                "severity": entry.severity,
                "type": entry.type_name,
                "reason": entry.reason,
                "remediation": entry.remediation,
                "occurrences": entry.occurrences,
                "fields": entry.fields,
            }
            for entry in summary.summaries
        ],
    }


__all__ = ["app"]
