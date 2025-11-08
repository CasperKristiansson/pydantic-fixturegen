from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic_fixturegen.api import _runtime as runtime_mod
from pydantic_fixturegen.api.models import FixturesGenerationResult, JsonGenerationResult
from pydantic_fixturegen.cli.gen import _common as cli_common
from pydantic_fixturegen.core.errors import DiscoveryError, EmitError, MappingError
from pydantic_fixturegen.core.io_utils import WriteResult
from pydantic_fixturegen.core.path_template import OutputTemplate
from pydantic_fixturegen.core.seed_freeze import FREEZE_FILE_BASENAME


class FakeLogger:
    def __init__(self) -> None:
        self.debug_calls: list[tuple[str, dict[str, object]]] = []
        self.info_calls: list[tuple[str, dict[str, object]]] = []
        self.warn_calls: list[tuple[str, dict[str, object]]] = []
        self.config = type("Config", (), {"json": False})()

    def debug(self, message: str, **kwargs: object) -> None:
        self.debug_calls.append((message, kwargs))

    def info(self, message: str, **kwargs: object) -> None:
        self.info_calls.append((message, kwargs))

    def warn(self, message: str, **kwargs: object) -> None:
        self.warn_calls.append((message, kwargs))


def _write_module(tmp_path: Path, source: str) -> Path:
    module = tmp_path / "models.py"
    module.write_text(source, encoding="utf-8")
    return module


def _write_linked_module(tmp_path: Path) -> Path:
    return _write_module(
        tmp_path,
        """
from pydantic import BaseModel


class User(BaseModel):
    id: int
    name: str


class Order(BaseModel):
    order_id: int
    user_id: int | None = None
""",
    )


def test_generate_json_artifacts_freeze_messages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(
        tmp_path,
        """
from pydantic import BaseModel


class Product(BaseModel):
    name: str
    price: float
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    freeze_file = tmp_path / FREEZE_FILE_BASENAME
    freeze_file.write_text("{not-json", encoding="utf-8")

    logger = FakeLogger()
    monkeypatch.setattr(runtime_mod, "get_logger", lambda: logger)

    def fake_emit_json_samples(samples, **kwargs):  # type: ignore[no-untyped-def]
        output_path = Path(kwargs["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("[]\n", encoding="utf-8")
        return [output_path]

    monkeypatch.setattr(runtime_mod, "emit_json_samples", fake_emit_json_samples)

    result = runtime_mod.generate_json_artifacts(
        target=module_path,
        output_template=OutputTemplate(str(tmp_path / "products.json")),
        count=1,
        jsonl=False,
        indent=0,
        use_orjson=False,
        shard_size=None,
        include=None,
        exclude=None,
        seed=None,
        now=None,
        freeze_seeds=True,
        freeze_seeds_file=freeze_file,
        preset=None,
    )

    assert isinstance(result, JsonGenerationResult)
    assert logger.warn_calls and logger.warn_calls[0][1]["event"] == "seed_freeze_invalid"


def test_generate_json_artifacts_updates_stale_freeze_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = _write_module(
        tmp_path,
        """
from pydantic import BaseModel


class Order(BaseModel):
    order_id: str
    total: float
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    freeze_file = tmp_path / FREEZE_FILE_BASENAME
    freeze_payload = {
        "version": 1,
        "models": {
            "models.Order": {"seed": 99, "model_digest": "stale-digest"},
        },
    }
    freeze_file.write_text(json.dumps(freeze_payload), encoding="utf-8")

    logger = FakeLogger()
    monkeypatch.setattr(runtime_mod, "get_logger", lambda: logger)

    def fake_emit_json_samples(samples, **kwargs):  # type: ignore[no-untyped-def]
        output_path = Path(kwargs["output_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("[]\n", encoding="utf-8")
        return [output_path]

    monkeypatch.setattr(runtime_mod, "emit_json_samples", fake_emit_json_samples)

    runtime_mod.generate_json_artifacts(
        target=module_path,
        output_template=OutputTemplate(str(tmp_path / "orders.json")),
        count=1,
        jsonl=False,
        indent=0,
        use_orjson=True,
        shard_size=None,
        include=None,
        exclude=None,
        seed=None,
        now="2024-01-01T00:00:00Z",
        freeze_seeds=True,
        freeze_seeds_file=freeze_file,
        preset=None,
    )

    assert any(call[1]["event"] == "seed_freeze_stale" for call in logger.warn_calls)
    refreshed = json.loads(freeze_file.read_text(encoding="utf-8"))
    assert "models.Order" in refreshed["models"]
    assert isinstance(refreshed["models"]["models.Order"]["seed"], int)


def test_generate_json_artifacts_multiple_models_error(tmp_path: Path) -> None:
    module_path = _write_module(
        tmp_path,
        """
from pydantic import BaseModel


class First(BaseModel):
    value: int


class Second(BaseModel):
    value: int
""",
    )

    with pytest.raises(DiscoveryError):
        runtime_mod.generate_json_artifacts(
            target=module_path,
            output_template=OutputTemplate(str(tmp_path / "out.json")),
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
        )


def test_generate_json_artifacts_requires_target_without_type(tmp_path: Path) -> None:
    with pytest.raises(DiscoveryError, match="Target path must be provided"):
        runtime_mod.generate_json_artifacts(
            target=None,
            output_template=OutputTemplate(str(tmp_path / "values.json")),
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
        )


def test_generate_json_artifacts_type_adapter_rejects_freeze(tmp_path: Path) -> None:
    with pytest.raises(DiscoveryError, match="Seed freezing is not supported"):
        runtime_mod.generate_json_artifacts(
            target=None,
            output_template=OutputTemplate(str(tmp_path / "values.json")),
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=True,
            freeze_seeds_file=None,
            preset=None,
            type_annotation=list[int],
        )


def test_generate_json_artifacts_type_adapter_rejects_relations(tmp_path: Path) -> None:
    with pytest.raises(DiscoveryError, match="Relation links cannot be combined"):
        runtime_mod.generate_json_artifacts(
            target=None,
            output_template=OutputTemplate(str(tmp_path / "values.json")),
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            type_annotation=list[int],
            relations={"User.id": "Order.user_id"},
        )


def test_generate_json_artifacts_type_adapter_rejects_related(tmp_path: Path) -> None:
    with pytest.raises(DiscoveryError, match="Related model generation is unavailable"):
        runtime_mod.generate_json_artifacts(
            target=None,
            output_template=OutputTemplate(str(tmp_path / "values.json")),
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            type_annotation=list[int],
            with_related=["models.User"],
        )


def test_generate_json_artifacts_attaches_error_details(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module_path = _write_module(
        tmp_path,
        """
from pydantic import BaseModel


class Product(BaseModel):
    name: str
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    def fake_emit_json_samples(samples, **kwargs):  # type: ignore[no-untyped-def]
        raise EmitError("emit failed")

    monkeypatch.setattr(runtime_mod, "emit_json_samples", fake_emit_json_samples)

    with pytest.raises(EmitError) as excinfo:
        runtime_mod.generate_json_artifacts(
            target=module_path,
            output_template=OutputTemplate(str(tmp_path / "products.json")),
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
        )

    details = excinfo.value.details
    assert "config" in details and "base_output" in details


def test_generate_json_artifacts_includes_validator_failure_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = _write_module(
        tmp_path,
        """
from pydantic import BaseModel, model_validator


class Broken(BaseModel):
    value: int

    @model_validator(mode="after")
    def always_fail(self):
        raise ValueError("nope")
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(MappingError) as excinfo:
        runtime_mod.generate_json_artifacts(
            target=module_path,
            output_template=OutputTemplate(str(tmp_path / "broken.json")),
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            respect_validators=True,
        )

    details = excinfo.value.details
    assert "validator_failure" in details
    assert details["validator_failure"]["message"].startswith("1 validation error for Broken")
    assert "constraint_summary" in details


def test_generate_json_artifacts_with_related_bundle(tmp_path: Path) -> None:
    module_path = _write_linked_module(tmp_path)
    output_template = OutputTemplate(str(tmp_path / "bundle.json"))

    result = runtime_mod.generate_json_artifacts(
        target=module_path,
        output_template=output_template,
        count=1,
        jsonl=False,
        indent=None,
        use_orjson=None,
        shard_size=None,
        include=["models.Order"],
        exclude=None,
        seed=None,
        now=None,
        freeze_seeds=False,
        freeze_seeds_file=None,
        preset=None,
        relations={"models.Order.user_id": "models.User.id"},
        with_related=["models.User", "models.User"],
        respect_validators=True,
        validator_max_retries=1,
    )

    assert result.paths
    payload = json.loads(result.paths[0].read_text(encoding="utf-8"))
    assert payload and "Order" in payload[0] and "User" in payload[0]
    assert payload[0]["Order"]["user_id"] == payload[0]["User"]["id"]


def test_generate_json_artifacts_all_related_consumes_primary(tmp_path: Path) -> None:
    module_path = _write_module(
        tmp_path,
        """
from pydantic import BaseModel


class User(BaseModel):
    name: str
""",
    )
    with pytest.raises(DiscoveryError, match="No primary model discovered"):
        runtime_mod.generate_json_artifacts(
            target=module_path,
            output_template=OutputTemplate(str(tmp_path / "bundle.json")),
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=["models.User"],
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            relations=None,
            with_related=["models.User"],
        )


def test_generate_json_artifacts_related_model_missing(tmp_path: Path) -> None:
    module_path = _write_linked_module(tmp_path)
    output_template = OutputTemplate(str(tmp_path / "missing.json"))

    with pytest.raises(DiscoveryError, match="Related model 'models.Missing' not found."):
        runtime_mod.generate_json_artifacts(
            target=module_path,
            output_template=output_template,
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=["models.Order"],
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            relations={"models.Order.user_id": "models.User.id"},
            with_related=["models.Missing"],
        )


def test_generate_json_artifacts_multiple_models_without_include(tmp_path: Path) -> None:
    module_path = _write_linked_module(tmp_path)
    output_template = OutputTemplate(str(tmp_path / "multi.json"))

    with pytest.raises(DiscoveryError, match="Multiple models discovered"):
        runtime_mod.generate_json_artifacts(
            target=module_path,
            output_template=output_template,
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
        )


def test_generate_json_artifacts_with_type_adapter(tmp_path: Path) -> None:
    output_template = OutputTemplate(str(tmp_path / "adapter.json"))

    result = runtime_mod.generate_json_artifacts(
        target=None,
        output_template=output_template,
        count=2,
        jsonl=False,
        indent=None,
        use_orjson=None,
        shard_size=None,
        include=None,
        exclude=None,
        seed=99,
        now=None,
        freeze_seeds=False,
        freeze_seeds_file=None,
        preset=None,
        type_annotation=list[int],
        type_label="list[int]",
    )

    assert isinstance(result, JsonGenerationResult)
    assert result.model is None
    assert result.paths
    data = json.loads(result.paths[0].read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 2
    for entry in data:
        assert isinstance(entry, list)
        assert all(isinstance(item, int) for item in entry)


def test_generate_json_artifacts_related_generation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = _write_linked_module(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    class FailingRelated:
        constraint_report = None
        validator_failure_details = None

        def generate_one(self, model_cls):
            if model_cls.__name__ == "User":
                return None
            return type("Fake", (), {"model_dump": lambda self: {"order_id": 1, "user_id": 1}})()

    monkeypatch.setattr(runtime_mod, "_build_instance_generator", lambda *_, **__: FailingRelated())

    def fake_emit_json_samples(sample_factory, **kwargs):  # type: ignore[no-untyped-def]
        sample_factory()
        return []

    monkeypatch.setattr(runtime_mod, "emit_json_samples", fake_emit_json_samples)

    with pytest.raises(MappingError) as excinfo:
        runtime_mod.generate_json_artifacts(
            target=module_path,
            output_template=OutputTemplate(str(tmp_path / "bundle.json")),
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=["models.Order"],
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            relations={"models.Order.user_id": "models.User.id"},
            with_related=["models.User"],
        )

    assert "User" in str(excinfo.value)


def test_generate_json_artifacts_main_generation_failure_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = _write_module(
        tmp_path,
        """
from pydantic import BaseModel


class Only(BaseModel):
    value: int
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    class Report:
        def summary(self) -> dict[str, object]:
            return {"models": [{"model": "Only", "fields": []}]}

    class MainFailureGenerator:
        def __init__(self) -> None:
            self.constraint_report = Report()
            self.validator_failure_details = {"message": "boom"}

        def generate_one(self, model_cls):
            return None

    monkeypatch.setattr(
        runtime_mod,
        "_build_instance_generator",
        lambda *_, **__: MainFailureGenerator(),
    )

    def fake_emit_json_samples(sample_factory, **kwargs):  # type: ignore[no-untyped-def]
        sample_factory()
        return []

    monkeypatch.setattr(runtime_mod, "emit_json_samples", fake_emit_json_samples)

    with pytest.raises(MappingError) as excinfo:
        runtime_mod.generate_json_artifacts(
            target=module_path,
            output_template=OutputTemplate(str(tmp_path / "only.json")),
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=["models.Only"],
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            relations=None,
            with_related=None,
        )

    assert excinfo.value.details["validator_failure"]["message"] == "boom"
    assert "constraint_summary" in excinfo.value.details


def test_generate_json_artifacts_type_adapter_plugin_delegate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runtime_mod, "emit_artifact", lambda name, ctx: name == "json")
    result = runtime_mod.generate_json_artifacts(
        target=None,
        output_template=OutputTemplate(str(tmp_path / "values.json")),
        count=1,
        jsonl=False,
        indent=None,
        use_orjson=None,
        shard_size=None,
        include=None,
        exclude=None,
        seed=None,
        now=None,
        freeze_seeds=False,
        freeze_seeds_file=None,
        preset=None,
        type_annotation=list[int],
        type_label="numbers",
    )
    assert result.delegated is True
    assert result.type_label == "numbers"


def test_generate_json_artifacts_type_adapter_generator_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class AdapterFailure:
        constraint_report = None
        validator_failure_details = None

        def generate_one(self, model_cls):
            return None

    monkeypatch.setattr(runtime_mod, "_build_instance_generator", lambda *_, **__: AdapterFailure())

    def fake_emit_json_samples(sample_factory, **kwargs):  # type: ignore[no-untyped-def]
        sample_factory()
        return []

    monkeypatch.setattr(runtime_mod, "emit_json_samples", fake_emit_json_samples)

    with pytest.raises(MappingError) as excinfo:
        runtime_mod.generate_json_artifacts(
            target=None,
            output_template=OutputTemplate(str(tmp_path / "values.json")),
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            type_annotation=list[int],
        )

    assert "type_adapter" in excinfo.value.details


def test_generate_json_artifacts_type_adapter_validation_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BadValueGenerator:
        constraint_report = None
        validator_failure_details = None

        def generate_one(self, model_cls):
            return type("Fake", (), {"value": "bad"})()

    monkeypatch.setattr(
        runtime_mod,
        "_build_instance_generator",
        lambda *_, **__: BadValueGenerator(),
    )

    def fake_emit_json_samples(sample_factory, **kwargs):  # type: ignore[no-untyped-def]
        sample_factory()
        return []

    monkeypatch.setattr(runtime_mod, "emit_json_samples", fake_emit_json_samples)

    with pytest.raises(MappingError) as excinfo:
        runtime_mod.generate_json_artifacts(
            target=None,
            output_template=OutputTemplate(str(tmp_path / "values.json")),
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            type_annotation=list[int],
        )

    assert "TypeAdapter validation failed" in str(excinfo.value)


def test_generate_json_artifacts_type_adapter_emit_runtime_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class SimpleGenerator:
        constraint_report = None
        validator_failure_details = None

        def generate_one(self, model_cls):
            return type("Fake", (), {"value": [1]})()

    monkeypatch.setattr(
        runtime_mod,
        "_build_instance_generator",
        lambda *_, **__: SimpleGenerator(),
    )

    def raise_runtime(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("boom")

    monkeypatch.setattr(runtime_mod, "emit_json_samples", raise_runtime)

    with pytest.raises(EmitError) as excinfo:
        runtime_mod.generate_json_artifacts(
            target=None,
            output_template=OutputTemplate(str(tmp_path / "values.json")),
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            type_annotation=list[int],
        )

    assert "config" in excinfo.value.details


def test_generate_json_artifacts_type_adapter_emit_mapping_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class SimpleGenerator:
        constraint_report = None
        validator_failure_details = None

        def generate_one(self, model_cls):
            return type("Fake", (), {"value": [1]})()

    monkeypatch.setattr(
        runtime_mod,
        "_build_instance_generator",
        lambda *_, **__: SimpleGenerator(),
    )

    def raise_mapping(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise MappingError("failed")

    monkeypatch.setattr(runtime_mod, "emit_json_samples", raise_mapping)

    with pytest.raises(MappingError) as excinfo:
        runtime_mod.generate_json_artifacts(
            target=None,
            output_template=OutputTemplate(str(tmp_path / "values.json")),
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            type_annotation=list[int],
        )

    assert "config" in excinfo.value.details


def test_generate_fixtures_artifacts_delegates_to_plugin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(
        tmp_path,
        """
from pydantic import BaseModel


class Item(BaseModel):
    name: str
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    monkeypatch.setattr(runtime_mod, "emit_artifact", lambda name, ctx: name == "fixtures")

    result = runtime_mod.generate_fixtures_artifacts(
        target=module_path,
        output_template=OutputTemplate(str(tmp_path / "conftest.py")),
        style="functions",
        scope="function",
        cases=1,
        return_type="model",
        seed=None,
        now=None,
        p_none=None,
        include=None,
        exclude=None,
        freeze_seeds=False,
        freeze_seeds_file=None,
        preset=None,
        profile=None,
    )

    assert isinstance(result, FixturesGenerationResult)
    assert result.delegated is True


def test_generate_fixtures_artifacts_attach_error_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(
        tmp_path,
        """
from pydantic import BaseModel


class Item(BaseModel):
    name: str
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    monkeypatch.setattr(runtime_mod, "emit_artifact", lambda name, ctx: False)

    def raise_emit_error(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise EmitError("emit failed")

    monkeypatch.setattr(runtime_mod, "emit_pytest_fixtures", raise_emit_error)

    with pytest.raises(EmitError) as excinfo:
        runtime_mod.generate_fixtures_artifacts(
            target=module_path,
            output_template=OutputTemplate(str(tmp_path / "conftest.py")),
            style="functions",
            scope="function",
            cases=1,
            return_type="model",
            seed=None,
            now=None,
            p_none=None,
            include=("models.Sample",),
            exclude=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            profile=None,
        )

    assert "config" in excinfo.value.details


def test_generate_fixtures_artifacts_reports_validator_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = _write_module(
        tmp_path,
        """
from pydantic import BaseModel, model_validator


class Broken(BaseModel):
    value: int

    @model_validator(mode="after")
    def always_fail(self):
        raise ValueError("nope")
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(EmitError) as excinfo:
        runtime_mod.generate_fixtures_artifacts(
            target=module_path,
            output_template=OutputTemplate(str(tmp_path / "conftest.py")),
            style="functions",
            scope="function",
            cases=1,
            return_type="model",
            seed=None,
            now=None,
            p_none=None,
            include=None,
            exclude=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            respect_validators=True,
        )

    assert "validator_failure" in excinfo.value.details


def test_generate_fixtures_artifacts_warns_on_invalid_freeze_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(
        tmp_path,
        """
from pydantic import BaseModel


class Sample(BaseModel):
    value: int
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    freeze_file = tmp_path / FREEZE_FILE_BASENAME
    freeze_file.write_text("{bad-json", encoding="utf-8")
    logger = FakeLogger()
    monkeypatch.setattr(runtime_mod, "get_logger", lambda: logger)

    def fake_emit_pytest_fixtures(*args, **kwargs):  # type: ignore[no-untyped-def]
        target = Path(kwargs["output_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# fixtures", encoding="utf-8")
        return WriteResult(path=target, wrote=True, skipped=False, reason=None, metadata={})

    monkeypatch.setattr(runtime_mod, "emit_pytest_fixtures", fake_emit_pytest_fixtures)

    runtime_mod.generate_fixtures_artifacts(
        target=module_path,
        output_template=OutputTemplate(str(tmp_path / "conftest.py")),
        style="functions",
        scope="function",
        cases=1,
        return_type="model",
        seed=None,
        now=None,
        p_none=0.5,
        include=None,
        exclude=None,
        freeze_seeds=True,
        freeze_seeds_file=freeze_file,
        preset="boundary",
        profile=None,
    )

    assert logger.warn_calls and logger.warn_calls[0][1]["event"] == "seed_freeze_invalid"


def test_generate_fixtures_artifacts_collects_constraint_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(
        tmp_path,
        """
from pydantic import BaseModel


class Sample(BaseModel):
    value: int
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    def fake_emit_pytest_fixtures(*args, **kwargs):  # type: ignore[no-untyped-def]
        target = Path(kwargs["output_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# fixtures", encoding="utf-8")
        return WriteResult(
            path=target,
            wrote=True,
            skipped=False,
            reason=None,
            metadata={"constraints": {"models": 1}},
        )

    monkeypatch.setattr(runtime_mod, "emit_pytest_fixtures", fake_emit_pytest_fixtures)

    result = runtime_mod.generate_fixtures_artifacts(
        target=module_path,
        output_template=OutputTemplate(str(tmp_path / "conftest.py")),
        style="functions",
        scope="function",
        cases=1,
        return_type="model",
        seed=None,
        now=None,
        p_none=None,
        include=None,
        exclude=("models.Ignore",),
        freeze_seeds=False,
        freeze_seeds_file=None,
        preset=None,
        profile=None,
    )

    assert result.constraint_summary == {"models": 1}


def test_generate_fixtures_artifacts_with_related_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_linked_module(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    def fake_emit_pytest_fixtures(*args, **kwargs):  # type: ignore[no-untyped-def]
        target = Path(kwargs["output_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# fixtures", encoding="utf-8")
        return WriteResult(path=target, wrote=True, skipped=False, reason=None, metadata=None)

    monkeypatch.setattr(runtime_mod, "emit_pytest_fixtures", fake_emit_pytest_fixtures)

    result = runtime_mod.generate_fixtures_artifacts(
        target=module_path,
        output_template=OutputTemplate(str(tmp_path / "conftest.py")),
        style="functions",
        scope="function",
        cases=1,
        return_type="model",
        seed=None,
        now=None,
        p_none=None,
        include=("models.Order",),
        exclude=None,
        freeze_seeds=False,
        freeze_seeds_file=None,
        preset=None,
        profile=None,
        respect_validators=None,
        validator_max_retries=2,
        relations={"models.Order.user_id": "models.User.id"},
        with_related=("User", "models.User"),
    )

    assert any(entry.endswith(".User") for entry in result.config.include)


def test_generate_fixtures_artifacts_unknown_related(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(
        tmp_path,
        """
from pydantic import BaseModel


class Sample(BaseModel):
    value: int
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    with pytest.raises(DiscoveryError, match="Related model 'Missing' not found"):
        runtime_mod.generate_fixtures_artifacts(
            target=module_path,
            output_template=OutputTemplate(str(tmp_path / "conftest.py")),
            style="functions",
            scope="function",
            cases=1,
            return_type="model",
            seed=None,
            now=None,
            p_none=None,
            include=None,
            exclude=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            profile=None,
            with_related=("Missing",),
        )


def test_generate_fixtures_artifacts_discovery_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(
        tmp_path,
        """
from pydantic import BaseModel


class Sample(BaseModel):
    value: int
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    class Dummy:
        errors = ["fixtures-broken"]
        warnings: list[str] = []
        models: list[Any] = []

    monkeypatch.setattr(cli_common, "discover_models", lambda *args, **kwargs: Dummy())

    with pytest.raises(DiscoveryError, match="fixtures-broken"):
        runtime_mod.generate_fixtures_artifacts(
            target=module_path,
            output_template=OutputTemplate(str(tmp_path / "conftest.py")),
            style="functions",
            scope="function",
            cases=1,
            return_type="model",
            seed=None,
            now=None,
            p_none=None,
            include=None,
            exclude=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            profile=None,
        )


def test_generate_fixtures_artifacts_no_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(
        tmp_path,
        """
class Empty:
    pass
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    class Dummy:
        errors: list[str] = []
        warnings: list[str] = []
        models: list[Any] = []

    monkeypatch.setattr(cli_common, "discover_models", lambda *args, **kwargs: Dummy())

    with pytest.raises(DiscoveryError, match="No models discovered"):
        runtime_mod.generate_fixtures_artifacts(
            target=module_path,
            output_template=OutputTemplate(str(tmp_path / "conftest.py")),
            style="functions",
            scope="function",
            cases=1,
            return_type="model",
            seed=None,
            now=None,
            p_none=None,
            include=None,
            exclude=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            profile=None,
        )


def test_generate_json_artifacts_discovery_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(
        tmp_path,
        """
from pydantic import BaseModel


class Sample(BaseModel):
    value: int
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    class Dummy:
        errors = ["broken"]
        warnings: list[str] = []
        models: list[Any] = []

    monkeypatch.setattr(cli_common, "discover_models", lambda *args, **kwargs: Dummy())

    with pytest.raises(DiscoveryError, match="broken"):
        runtime_mod.generate_json_artifacts(
            target=module_path,
            output_template=OutputTemplate(str(tmp_path / "out.json")),
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
        )


def test_generate_json_artifacts_no_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = _write_module(
        tmp_path,
        """
class NotModel:
    pass
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    class Dummy:
        errors: list[str] = []
        warnings: list[str] = []
        models: list[Any] = []

    monkeypatch.setattr(cli_common, "discover_models", lambda *args, **kwargs: Dummy())

    with pytest.raises(DiscoveryError, match="No models discovered"):
        runtime_mod.generate_json_artifacts(
            target=module_path,
            output_template=OutputTemplate(str(tmp_path / "empty.json")),
            count=1,
            jsonl=False,
            indent=None,
            use_orjson=None,
            shard_size=None,
            include=None,
            exclude=None,
            seed=None,
            now=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
        )


def test_generate_schema_artifacts_requires_file(tmp_path: Path) -> None:
    folder = tmp_path / "pkg"
    folder.mkdir()

    with pytest.raises(DiscoveryError, match="must be a Python module file"):
        runtime_mod.generate_schema_artifacts(
            target=folder,
            output_template=OutputTemplate(str(tmp_path / "schema.json")),
            indent=None,
            include=None,
            exclude=None,
            profile=None,
        )


def test_generate_schema_artifacts_discovery_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(
        tmp_path,
        """
from pydantic import BaseModel


class Demo(BaseModel):
    value: int
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    class Dummy:
        errors = ["schema-broken"]
        warnings: list[str] = []
        models: list[Any] = []

    monkeypatch.setattr(cli_common, "discover_models", lambda *args, **kwargs: Dummy())

    with pytest.raises(DiscoveryError, match="schema-broken"):
        runtime_mod.generate_schema_artifacts(
            target=module_path,
            output_template=OutputTemplate(str(tmp_path / "schema.json")),
            indent=None,
            include=None,
            exclude=None,
            profile=None,
        )


def test_generate_schema_artifacts_no_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module_path = _write_module(
        tmp_path,
        """
class Empty:
    pass
""",
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    class Dummy:
        errors: list[str] = []
        warnings: list[str] = []
        models: list[Any] = []

    monkeypatch.setattr(cli_common, "discover_models", lambda *args, **kwargs: Dummy())

    with pytest.raises(DiscoveryError, match="No models discovered"):
        runtime_mod.generate_schema_artifacts(
            target=module_path,
            output_template=OutputTemplate(str(tmp_path / "schema.json")),
            indent=None,
            include=None,
            exclude=None,
            profile=None,
        )
