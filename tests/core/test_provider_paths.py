from __future__ import annotations

import random

import pytest
from pydantic_fixturegen.core.config import PathConfig
from pydantic_fixturegen.core.providers import paths as paths_mod
from pydantic_fixturegen.core.schema import FieldConstraints, FieldSummary


def _summary(
    *,
    fmt: str | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
) -> FieldSummary:
    return FieldSummary(
        type="string",
        constraints=FieldConstraints(min_length=min_length, max_length=max_length),
        format=fmt,
    )


def test_generate_path_posix_file() -> None:
    rng = random.Random(1234)
    summary = _summary(fmt="file")
    config = PathConfig(default_os="posix")

    result = paths_mod.generate_path(summary, random_generator=rng, path_config=config)

    assert result.startswith("/")
    assert "." in result


def test_generate_path_windows_via_model_target() -> None:
    class SampleModel:
        ...

    rng = random.Random(4321)
    summary = _summary(fmt="directory")
    config = PathConfig(
        default_os="posix",
        model_targets=((f"{SampleModel.__module__}.{SampleModel.__qualname__}", "windows"),),
    )

    result = paths_mod.generate_path(
        summary,
        random_generator=rng,
        path_config=config,
        model_type=SampleModel,
    )

    assert ":\\" in result
    assert result.endswith("\\") is False


def test_generate_path_requires_random_generator() -> None:
    with pytest.raises(RuntimeError):
        paths_mod.generate_path(_summary(), random_generator=None)  # type: ignore[arg-type]


def test_apply_length_constraints_file_padding() -> None:
    constraints = FieldConstraints(min_length=25)
    adjusted = paths_mod._apply_length_constraints("/tmp/out.json", constraints, "file")

    assert len(adjusted) >= 25
    assert adjusted.count("_") >= 1


def test_apply_length_constraints_directory_padding() -> None:
    constraints = FieldConstraints(min_length=18)
    adjusted = paths_mod._apply_length_constraints("/tmp", constraints, "directory")

    assert len(adjusted) >= 18
    assert adjusted.startswith("/tmp")


def test_apply_length_constraints_truncates_max_length() -> None:
    constraints = FieldConstraints(max_length=10)
    shortened = paths_mod._apply_length_constraints("/usr/local/bin/script.py", constraints, "file")

    assert len(shortened) <= 10
    assert shortened.endswith("/") is False
    assert shortened.endswith("\\") is False


def test_split_extension_handles_missing_extension() -> None:
    stem, ext = paths_mod._split_extension("/tmp/data")
    assert stem == "/tmp/data" and ext == ""

    stem, ext = paths_mod._split_extension("/tmp/file.txt")
    assert stem == "/tmp/file" and ext == ".txt"


def test_determine_kind_defaults_to_file() -> None:
    summary = _summary(fmt=None)
    assert paths_mod._determine_kind(summary) == "file"

    directory_summary = _summary(fmt="directory")
    assert paths_mod._determine_kind(directory_summary) == "directory"
