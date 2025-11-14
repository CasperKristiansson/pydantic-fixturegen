from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import typer
from pydantic_fixturegen.cli.gen import _common as gen_common
from pydantic_fixturegen.core.errors import DiscoveryError


class LoggerStub:
    def __init__(self) -> None:
        self.warns: list[dict[str, Any]] = []
        self.debugs: list[dict[str, Any]] = []

    def warn(self, message: str, **kwargs: Any) -> None:  # noqa: D401 - stub
        self.warns.append({"message": message, **kwargs})

    def debug(self, message: str, **kwargs: Any) -> None:  # noqa: D401 - stub
        self.debugs.append({"message": message, **kwargs})


def test_expand_target_paths_handles_files_and_directories(tmp_path: Path) -> None:
    module_file = tmp_path / "models.py"
    module_file.write_text("class User:\n    pass\n", encoding="utf-8")

    file_result = gen_common.expand_target_paths(module_file)
    assert file_result == [module_file]

    dir_result = gen_common.expand_target_paths(tmp_path)
    assert module_file in dir_result

    with pytest.raises(DiscoveryError):
        gen_common.expand_target_paths(tmp_path / "missing.py")

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(DiscoveryError):
        gen_common.expand_target_paths(empty_dir)


def test_parse_relation_links_and_locales() -> None:
    relations = gen_common.parse_relation_links(
        ["Model.User.id=Account.user_id", " Other.field = Target.value "]
    )
    assert relations["Model.User.id"] == "Account.user_id"
    assert relations["Other.field"] == "Target.value"

    with pytest.raises(typer.BadParameter):
        gen_common.parse_relation_links(["invalid-entry"])

    locales = gen_common.parse_locale_entries(["models.*=sv_SE"])
    assert locales == {"models.*": "sv_SE"}

    with pytest.raises(typer.BadParameter):
        gen_common.parse_locale_entries(["missing_locale"])


def test_parse_override_entries_validates_payloads() -> None:
    payload = json.dumps({"value": 1})
    overrides = gen_common.parse_override_entries([f"models.User.id={payload}"])
    assert overrides["models.User"]["id"]["value"] == 1

    with pytest.raises(typer.BadParameter):
        gen_common.parse_override_entries(["models.User=id"])

    with pytest.raises(typer.BadParameter):
        gen_common.parse_override_entries(['modelsUserField={"value": 1}'])

    with pytest.raises(typer.BadParameter):
        gen_common.parse_override_entries(["models.User.id={not-json}"])


def test_evaluate_type_expression_with_module(tmp_path: Path) -> None:
    module_path = tmp_path / "helpers.py"
    module_path.write_text(
        "from pydantic import BaseModel\nclass Helper(BaseModel):\n    name: str\n",
        encoding="utf-8",
    )
    result = gen_common.evaluate_type_expression("list[Helper]", module_path=module_path)
    assert getattr(result, "__origin__", None) is list
    helper_type = result.__args__[0]
    assert helper_type.__name__ == "Helper"

    with pytest.raises(ValueError):
        gen_common.evaluate_type_expression("UnknownType")


def test_emit_constraint_summary_warns_and_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    logger = LoggerStub()
    captured: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(
        gen_common.typer,
        "secho",
        lambda *args, **kwargs: captured.append(("secho", args, kwargs)),
    )
    monkeypatch.setattr(
        gen_common.typer,
        "echo",
        lambda *args, **kwargs: captured.append(("echo", args, kwargs)),
    )

    failure_report = {
        "models": [
            {
                "model": "models.User",
                "attempts": 2,
                "successes": 1,
                "fields": [
                    {
                        "name": "email",
                        "attempts": 1,
                        "successes": 0,
                        "failures": [
                            {
                                "message": "invalid",
                                "location": ["email"],
                                "value": "bad@example.com",
                            }
                        ],
                    }
                ],
            }
        ]
    }
    gen_common.emit_constraint_summary(
        failure_report,
        logger=logger,
        json_mode=False,
        heading="Report",
    )
    assert logger.warns
    assert any(entry[0] == "secho" for entry in captured)

    success_report = {
        "models": [
            {
                "model": "models.User",
                "attempts": 1,
                "successes": 1,
                "fields": [{"name": "email", "attempts": 1, "successes": 1}],
            }
        ]
    }
    gen_common.emit_constraint_summary(success_report, logger=logger, json_mode=False)
    assert logger.debugs
