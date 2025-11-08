"""Builders for FastAPI smoke test suites."""

from __future__ import annotations

import textwrap
from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import BaseModel

from ..core.generate import GenerationConfig, InstanceGenerator
from ..core.seed import SeedManager
from .loader import FastAPIRouteSpec, import_fastapi_app, iter_route_specs


def _slugify(path: str, method: str) -> str:
    safe = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    return f"{method.lower()}_{safe or 'root'}"


def _model_import_path(model: type[BaseModel]) -> tuple[str, str]:
    return model.__module__, model.__qualname__


@dataclass(slots=True)
class RouteTestCase:
    spec: FastAPIRouteSpec
    request_payload: dict[str, object] | None
    response_payload: dict[str, object] | None

    @property
    def test_name(self) -> str:
        return f"test_{_slugify(self.spec.path, self.spec.method)}"


class FastAPISmokeSuite:
    """Render pytest smoke tests that exercise FastAPI routes."""

    def __init__(
        self,
        *,
        target: str,
        seed: int | None = None,
        dependency_overrides: list[str] | None = None,
    ) -> None:
        self.target = target
        self.seed = seed
        self.dependency_overrides = dependency_overrides or []
        normalized_seed = SeedManager(seed=seed).normalized_seed if seed is not None else None
        self._generator = InstanceGenerator(config=GenerationConfig(seed=normalized_seed))

    def build(self) -> str:
        app = import_fastapi_app(self.target)
        test_cases: list[RouteTestCase] = []
        imports: set[tuple[str, str]] = set()
        for spec in iter_route_specs(app):
            request_payload = self._sample_payload(spec.request_model)
            response_payload = self._sample_payload(spec.response_model)
            if spec.request_model:
                imports.add(_model_import_path(spec.request_model))
            if spec.response_model:
                imports.add(_model_import_path(spec.response_model))
            test_cases.append(
                RouteTestCase(
                    spec=spec,
                    request_payload=request_payload,
                    response_payload=response_payload,
                )
            )

        return self._render_suite(test_cases, sorted(imports))

    def _sample_payload(self, model: type[BaseModel] | None) -> dict[str, object] | None:
        if model is None:
            return None
        instance = self._generator.generate_one(model)
        if instance is None:
            return None
        return instance.model_dump(mode="json")

    def _render_suite(
        self,
        cases: Iterable[RouteTestCase],
        imports: list[tuple[str, str]],
    ) -> str:
        module, attr = self.target.split(":", 1)
        lines: list[str] = [
            '"""Auto-generated FastAPI smoke tests."""',
            "from __future__ import annotations",
            "",
            "from importlib import import_module",
            "from fastapi.testclient import TestClient",
        ]
        for mod, cls in imports:
            lines.append(f"from {mod} import {cls}")
        lines.append("")
        lines.append(f"_module = import_module(\"{module}\")")
        lines.append(f"app = getattr(_module, \"{attr}\")")
        if self.dependency_overrides:
            lines.append("_DEPENDENCY_OVERRIDES = [")
            for entry in self.dependency_overrides:
                lines.append(f"    \"{entry}\",")
            lines.append("]")
            lines.extend(
                [
                    "for mapping in _DEPENDENCY_OVERRIDES:",
                    "    original_path, override_path = mapping.split(\"=\", 1)",
                    "    original_mod, original_attr = original_path.rsplit(\".\", 1)",
                    "    override_mod, override_attr = override_path.rsplit(\".\", 1)",
                    "    original_obj = getattr(import_module(original_mod), original_attr)",
                    "    override_obj = getattr(import_module(override_mod), override_attr)",
                    "    app.dependency_overrides[original_obj] = override_obj",
                ]
            )
        lines.append("client = TestClient(app)")
        lines.append("")

        for case in cases:
            lines.extend(self._render_test(case))

        return "\n".join(lines) + "\n"

    def _render_test(self, case: RouteTestCase) -> list[str]:
        lines: list[str] = []
        lines.append(f"def {case.test_name}() -> None:")
        if case.request_payload is not None:
            lines.append(
                textwrap.indent(
                    "payload = " + repr(case.request_payload),
                    "    ",
                )
            )
        lines.append("    response = client.request(")
        lines.append(f'        "{case.spec.method}",')
        lines.append(f'        "{case.spec.path}",')
        if case.request_payload is not None:
            lines.append("        json=payload,")
        lines.append("    )")
        lines.append("    assert 200 <= response.status_code < 400")
        if case.response_payload is not None and case.spec.response_model is not None:
            module, cls = _model_import_path(case.spec.response_model)
            lines.append("    data = response.json()")
            lines.append(f"    {cls}.model_validate(data)")
        else:
            lines.append("    response.json()")
        lines.append("")
        return lines


__all__ = ["FastAPISmokeSuite"]
