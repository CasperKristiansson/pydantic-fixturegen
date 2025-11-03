from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path

import pytest
from pydantic_fixturegen.cli import app as cli_app
from pydantic_fixturegen.cli import watch as watch_mod
from pydantic_fixturegen.core.errors import WatchError
from typer.testing import CliRunner

runner = CliRunner()


def _write_model(tmp_path: Path) -> Path:
    module = tmp_path / "models.py"
    module.write_text(
        """
from pydantic import BaseModel


class Item(BaseModel):
    value: int
""",
        encoding="utf-8",
    )
    return module


def test_watch_requires_watchfiles(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = _write_model(tmp_path)
    out = tmp_path / "out.json"

    def fake_import() -> None:
        raise WatchError("watchfiles missing")

    monkeypatch.setattr(watch_mod, "_import_watch_backend", fake_import)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module),
            "--out",
            str(out),
            "--watch",
        ],
    )

    assert result.exit_code == 60
    assert "watchfiles" in result.stdout or "watchfiles" in result.stderr


def test_watch_triggers_rebuild(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = _write_model(tmp_path)
    out = tmp_path / "out.json"

    run_calls: list[int] = []

    def fake_run(run_once, watch_paths: Iterable[Path], debounce: float) -> None:  # type: ignore[override]
        assert any(module.parent.resolve() == path.resolve() for path in watch_paths)
        run_once()
        run_calls.append(1)
        run_once()
        run_calls.append(1)

    monkeypatch.setattr("pydantic_fixturegen.cli.gen.json.run_with_watch", fake_run)

    result = runner.invoke(
        cli_app,
        [
            "gen",
            "json",
            str(module),
            "--out",
            str(out),
            "--watch",
        ],
    )

    assert result.exit_code == 0
    assert out.is_file()
    assert len(run_calls) == 2


def test_gather_default_watch_paths(tmp_path: Path) -> None:
    module = _write_model(tmp_path)
    config = tmp_path / "pyproject.toml"
    config.write_text("[project]\nname='demo'\n", encoding="utf-8")
    output = tmp_path / "generated" / "out.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("{}", encoding="utf-8")
    extra = tmp_path / "additional.cfg"
    extra.write_text("", encoding="utf-8")

    paths = watch_mod.gather_default_watch_paths(module, output=output, extra=[extra])

    resolved = {path.resolve() for path in paths}
    assert module.resolve() in resolved
    assert module.parent.resolve() in resolved
    assert (Path.cwd() / "pyproject.toml").resolve() in resolved
    assert output.parent.resolve() in resolved


def test_run_with_watch_executes_multiple_times(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _write_model(tmp_path)

    def fake_backend(*paths: Path, debounce: float):  # type: ignore[override]
        yield {(0, paths[0])}
        yield {(0, paths[0])}

    monkeypatch.setattr(watch_mod, "_import_watch_backend", lambda: fake_backend)

    run_calls: list[int] = []

    watch_mod.run_with_watch(lambda: run_calls.append(1), [module], debounce=0.1)

    # initial call + one per change event
    assert len(run_calls) == 3


def test_gather_watch_paths_handles_missing_target(tmp_path: Path) -> None:
    missing = tmp_path / "missing.py"
    paths = watch_mod.gather_default_watch_paths(missing)
    resolved = {path.resolve() for path in paths}
    assert missing.parent.resolve() in resolved


def test_gather_watch_paths_handles_missing_extra(tmp_path: Path) -> None:
    module = _write_model(tmp_path)
    missing_extra = tmp_path / "missing" / "config.cfg"

    paths = watch_mod.gather_default_watch_paths(module, extra=[missing_extra])

    resolved = {path.resolve() for path in paths}
    assert module.parent.resolve() in resolved


def test_gather_watch_paths_no_valid_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _write_model(tmp_path)
    monkeypatch.setattr(watch_mod, "_normalize_watch_paths", lambda _paths: [])

    with pytest.raises(WatchError):
        watch_mod.gather_default_watch_paths(module)


def test_run_with_watch_requires_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = _write_model(tmp_path)

    def empty_backend(*_args: object, **_kwargs: object):
        return iter(())

    monkeypatch.setattr(watch_mod, "_import_watch_backend", lambda: empty_backend)
    monkeypatch.setattr(watch_mod, "_normalize_watch_paths", lambda _paths: [])

    with pytest.raises(WatchError):
        watch_mod.run_with_watch(lambda: None, [module], debounce=0.1)


def test_run_with_watch_handles_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _write_model(tmp_path)

    def interrupting_backend(*paths: Path, debounce: float):  # type: ignore[override]
        yield {(0, paths[0])}
        raise KeyboardInterrupt

    events: list[int] = []

    monkeypatch.setattr(watch_mod, "_import_watch_backend", lambda: interrupting_backend)
    monkeypatch.setattr(watch_mod, "_normalize_watch_paths", watch_mod._normalize_watch_paths)

    watch_mod.run_with_watch(lambda: events.append(1), [module], debounce=0.1)

    # initial run + iteration before interrupt
    assert len(events) == 2


def test_normalize_watch_paths_skips_missing(tmp_path: Path) -> None:
    missing = tmp_path / "missing" / "file.py"
    normalized = watch_mod._normalize_watch_paths([missing])
    assert normalized == []


def test_import_watch_backend_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "watchfiles", raising=False)

    original_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "watchfiles":
            raise ModuleNotFoundError("watchfiles not installed")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    with pytest.raises(WatchError):
        watch_mod._import_watch_backend()


def test_import_watch_backend_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class StubWatch:
        def __call__(self, *paths: Path, debounce: float):  # type: ignore[override]
            yield {(0, Path("."))}

    class StubModule:
        watch = StubWatch()

    monkeypatch.setitem(sys.modules, "watchfiles", StubModule())

    backend = watch_mod._import_watch_backend()
    iterator = backend(Path("."), debounce=0.1)
    first = next(iterator)
    assert isinstance(first, set)
