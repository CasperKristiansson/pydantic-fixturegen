from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_fixturegen.core import safe_import as safe_import_mod


def test_module_basename_for_init(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    init = pkg / "__init__.py"
    init.write_text("", encoding="utf-8")
    assert safe_import_mod._module_basename(init) == "pkg"


def test_resolve_module_name_for_package_init(tmp_path: Path) -> None:
    pkg = tmp_path / "pkg"
    sub = pkg / "sub"
    sub.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (sub / "__init__.py").write_text("", encoding="utf-8")
    name = safe_import_mod._resolve_module_name(sub / "__init__.py", tmp_path, 0)
    assert name == "pkg.sub"


def test_build_pythonpath_entries_skips_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_path = tmp_path / "module.py"
    module_path.write_text("", encoding="utf-8")
    missing = tmp_path / "missing"
    monkeypatch.setattr(safe_import_mod, "_candidate_python_paths", lambda *_: [missing])
    entries = safe_import_mod._build_pythonpath_entries(tmp_path, [module_path])
    assert entries == [tmp_path]


def test_safe_import_models_handles_empty_path_list() -> None:
    result = safe_import_mod.safe_import_models([])
    assert result.success is True
    assert result.models == []


def test_safe_import_models_handles_no_output(monkeypatch: pytest.MonkeyPatch) -> None:
    completed = SimpleNamespace(stdout="", stderr="err", returncode=2)
    monkeypatch.setattr(safe_import_mod.subprocess, "run", lambda *args, **kwargs: completed)
    result = safe_import_mod.safe_import_models([Path(__file__)])
    assert result.success is False
    assert "no output" in result.error.lower()


def test_safe_import_models_handles_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    completed = SimpleNamespace(stdout="{", stderr="err", returncode=0)
    monkeypatch.setattr(safe_import_mod.subprocess, "run", lambda *args, **kwargs: completed)
    result = safe_import_mod.safe_import_models([Path(__file__)])
    assert result.success is False
    assert "decode" in result.error.lower()


def test_build_env_filters_protected_keys(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    extra = {"CUSTOM": "1", "PYTHONPATH": "evil"}
    env = safe_import_mod._build_env(tmp_path, extra, [])
    assert env["CUSTOM"] == "1"
    assert env["PYTHONPATH"] != "evil"
