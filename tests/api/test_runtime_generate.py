from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic_fixturegen.api import _runtime as runtime_mod
from pydantic_fixturegen.api.models import FixturesGenerationResult, JsonGenerationResult
from pydantic_fixturegen.cli.gen import _common as cli_common
from pydantic_fixturegen.core.errors import DiscoveryError, EmitError
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
        indent=None,
        use_orjson=None,
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
            include=None,
            exclude=None,
            freeze_seeds=False,
            freeze_seeds_file=None,
            preset=None,
            profile=None,
        )

    assert "config" in excinfo.value.details


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
