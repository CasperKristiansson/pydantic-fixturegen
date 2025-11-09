from __future__ import annotations

import json
from pathlib import Path

from pydantic_fixturegen.cli import app as cli_app
from tests._cli import create_cli_runner


def test_anonymize_cli_generates_output(tmp_path: Path) -> None:
    payload = [
        {"id": 1, "email": "one@example.com", "ssn": "111-22-3333"},
        {"id": 2, "email": "two@example.com", "ssn": "222-33-4444"},
    ]
    data_path = tmp_path / "payload.json"
    data_path.write_text(json.dumps(payload), encoding="utf-8")

    rules_path = tmp_path / "rules.toml"
    rules_path.write_text(
        """
[anonymize]
salt = "demo"

  [[anonymize.rules]]
  pattern = "*.email"
  strategy = "faker"
  provider = "email"
  required = true

  [[anonymize.rules]]
  pattern = "*.ssn"
  strategy = "hash"
  hash_algorithm = "sha1"
  required = true
""",
        encoding="utf-8",
    )

    module_path = tmp_path / "models.py"
    module_path.write_text(
        """
from pydantic import BaseModel


class Sample(BaseModel):
    email: str
    ssn: str
""",
        encoding="utf-8",
    )

    out_path = tmp_path / "out.json"
    report_path = tmp_path / "report.json"
    runner = create_cli_runner()
    result = runner.invoke(
        cli_app,
        [
            "anonymize",
            "--rules",
            str(rules_path),
            "--report",
            str(report_path),
            "--doctor-target",
            str(module_path),
            str(data_path),
            str(out_path),
        ],
    )
    if result.exit_code != 0:  # pragma: no cover - diagnostic aid
        print(result.stdout)
    assert result.exit_code == 0

    anonymized = json.loads(out_path.read_text(encoding="utf-8"))
    assert anonymized[0]["email"] != "one@example.com"
    hashed_value = anonymized[0]["ssn"]
    assert hashed_value != "111-22-3333"
    assert len(hashed_value) == 40  # sha1 hex

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["records_processed"] == 2
    assert report["files_processed"] == 1
    assert report["strategies"]["faker"] >= 2
    assert report["doctor_summary"]["total_error_fields"] >= 0


def test_anonymize_cli_requires_output(tmp_path: Path) -> None:
    data_path = tmp_path / "payload.json"
    data_path.write_text("[]", encoding="utf-8")
    rules_path = tmp_path / "rules.toml"
    rules_path.write_text(
        """
[anonymize]

  [[anonymize.rules]]
  pattern = "*.id"
  strategy = "hash"
""",
        encoding="utf-8",
    )
    runner = create_cli_runner()
    result = runner.invoke(
        cli_app,
        [
            "anonymize",
            str(data_path),
            "--rules",
            str(rules_path),
        ],
    )
    assert result.exit_code != 0


def test_anonymize_cli_directory_output_and_budgets(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "first.json").write_text(
        json.dumps([{"email": "one@example.com", "token": "abc"}]),
        encoding="utf-8",
    )
    nested = input_dir / "nested"
    nested.mkdir()
    (nested / "second.json").write_text(
        json.dumps([{"email": "two@example.com", "token": "def"}]),
        encoding="utf-8",
    )

    rules_path = tmp_path / "rules.toml"
    rules_path.write_text(
        """
[anonymize]
salt = "demo"

  [[anonymize.rules]]
  pattern = "*.email"
  strategy = "faker"
  provider = "email"

  [[anonymize.rules]]
  pattern = "*.token"
  strategy = "mask"
  mask_char = "#"
""",
        encoding="utf-8",
    )

    output_dir = tmp_path / "out"
    doctor_module = tmp_path / "models.py"
    doctor_module.write_text(
        """
from pydantic import BaseModel


class Entry(BaseModel):
    email: str
    token: str
""",
        encoding="utf-8",
    )

    runner = create_cli_runner()
    result = runner.invoke(
        cli_app,
        [
            "anonymize",
            "--rules",
            str(rules_path),
            "--entity-field",
            "email",
            "--max-required-misses",
            "1",
            "--max-rule-failures",
            "1",
            "--doctor-target",
            str(doctor_module),
            str(input_dir),
            str(output_dir),
        ],
    )
    if result.exit_code != 0:  # pragma: no cover - diagnostic
        print(result.stdout)
    assert result.exit_code == 0

    first_out = output_dir / "first.json"
    assert first_out.exists()
    payload = json.loads(first_out.read_text(encoding="utf-8"))
    assert payload[0]["token"] == "###"
