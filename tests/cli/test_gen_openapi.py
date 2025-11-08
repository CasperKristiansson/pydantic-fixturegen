from __future__ import annotations

import json
from pathlib import Path

from pydantic_fixturegen.cli import app as cli_app
from tests._cli import create_cli_runner

runner = create_cli_runner()

OPENAPI_SPEC = """
openapi: 3.0.0
info:
  title: Example
  version: 1.0.0
paths:
  /users:
    get:
      responses:
        "200":
          description: OK
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/UserList"
  /orders:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/Order"
      responses:
        "201":
          description: Created
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Order"
components:
  schemas:
    UserList:
      type: object
      properties:
        items:
          type: array
          items:
            $ref: "#/components/schemas/User"
    User:
      type: object
      properties:
        id:
          type: integer
        email:
          type: string
    Order:
      type: object
      required: ["id"]
      properties:
        id:
          type: integer
        total:
          type: number
"""


def test_gen_openapi_emits_per_schema(tmp_path: Path) -> None:
    spec_path = tmp_path / "openapi.yaml"
    spec_path.write_text(OPENAPI_SPEC, encoding="utf-8")
    output_template = tmp_path / "{model}.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "openapi",
            str(spec_path),
            "--route",
            "GET /users",
            "--route",
            "POST /orders",
            "--out",
            str(output_template),
        ],
    )

    assert result.exit_code == 0, result.output
    user_list = json.loads((tmp_path / "UserList.json").read_text(encoding="utf-8"))
    assert isinstance(user_list, list) and user_list
    assert "items" in user_list[0]
    order = json.loads((tmp_path / "Order.json").read_text(encoding="utf-8"))
    assert isinstance(order, list) and order
    assert "id" in order[0]


def test_gen_openapi_requires_model_placeholder(tmp_path: Path) -> None:
    spec_path = tmp_path / "openapi.yaml"
    spec_path.write_text(OPENAPI_SPEC, encoding="utf-8")
    output_path = tmp_path / "samples.json"

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "openapi",
            str(spec_path),
            "--out",
            str(output_path),
        ],
    )

    assert result.exit_code != 0
    assert "must include '{model}'" in result.stderr
