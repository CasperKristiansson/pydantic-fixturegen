from __future__ import annotations

import random

import pytest
from pydantic_fixturegen.core.config import PathConfig
from pydantic_fixturegen.core.providers import paths
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary


def _summary(
    format: str | None = None,
    *,
    min_length: int | None = None,
    max_length: int | None = None,
) -> FieldSummary:
    constraints = FieldConstraints(min_length=min_length, max_length=max_length)
    return FieldSummary(type="path", constraints=constraints, format=format)


class ScenarioRandom(random.Random):
    def choice(self, seq):  # type: ignore[override]
        if isinstance(seq, tuple) and all(getattr(item, "root", None) == "/" for item in seq):
            from pathlib import PurePosixPath

            return PurePosixPath("/home")
        if seq == ("users", "applications", "volumes"):
            return "users"
        return super().choice(seq)

    def randint(self, a: int, b: int) -> int:  # noqa: D401
        return a


class MacBranchRandom(random.Random):
    def __init__(self, branch: str) -> None:
        super().__init__(0)
        self.branch = branch

    def choice(self, seq):  # type: ignore[override]
        if seq == ("users", "applications", "volumes"):
            return self.branch
        return super().choice(seq)


class WindowsBranchRandom(random.Random):
    def choice(self, seq):  # type: ignore[override]
        if seq == ("Users", "ProgramData", "Projects"):
            return "Projects"
        return super().choice(seq)


def test_generate_path_requires_random_generator() -> None:
    summary = _summary()
    with pytest.raises(RuntimeError):
        paths.generate_path(summary)


def test_generate_path_directory_min_length_padding() -> None:
    summary = _summary(format="directory", min_length=80)
    rng = ScenarioRandom()
    result = paths.generate_path(
        summary,
        random_generator=rng,
        path_config=PathConfig(default_os="posix"),
    )
    assert len(result) >= 80
    assert result.startswith("/home/")


def test_generate_path_mac_file_branch_and_truncation() -> None:
    summary = _summary(format="file", max_length=20)
    rng = ScenarioRandom()
    result = paths.generate_path(
        summary,
        random_generator=rng,
        path_config=PathConfig(default_os="mac"),
    )
    assert result.startswith("/Users/")
    assert len(result) <= 20


def test_generate_path_mac_applications_branch() -> None:
    summary = _summary(format="file")
    rng = MacBranchRandom("applications")
    result = paths.generate_path(
        summary,
        random_generator=rng,
        path_config=PathConfig(default_os="mac"),
    )
    assert "/Applications/" in result
    assert ".app/Contents/Resources" in result


def test_generate_path_mac_volumes_directory() -> None:
    summary = _summary(format="directory")
    rng = MacBranchRandom("volumes")
    result = paths.generate_path(
        summary,
        random_generator=rng,
        path_config=PathConfig(default_os="mac"),
    )
    assert result.startswith("/Volumes/")
    assert "." not in result.split("/")[-1]


def test_generate_path_extends_file_names_when_short() -> None:
    summary = _summary(format="file", min_length=120)
    rng = ScenarioRandom()
    result = paths.generate_path(
        summary,
        random_generator=rng,
        path_config=PathConfig(default_os="windows"),
    )
    assert len(result) >= 120
    assert "x" in result


def test_generate_path_windows_projects_branch() -> None:
    summary = _summary(format="directory")
    rng = WindowsBranchRandom()
    result = paths.generate_path(
        summary,
        random_generator=rng,
        path_config=PathConfig(default_os="windows"),
    )
    assert result.split("\\")[1] not in {"Users", "ProgramData"}
