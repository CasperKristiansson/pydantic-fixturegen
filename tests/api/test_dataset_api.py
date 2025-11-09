from __future__ import annotations

from pathlib import Path

import pydantic_fixturegen.api as api_mod


def test_generate_dataset_wraps_output_template(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_generate_dataset_artifacts(**kwargs):
        captured.update(kwargs)
        return "ok"

    monkeypatch.setattr(api_mod, "generate_dataset_artifacts", fake_generate_dataset_artifacts)

    freeze_file = tmp_path / "seeds.json"
    out_path = tmp_path / "export.csv"

    result = api_mod.generate_dataset(
        target="models.User",
        out=out_path,
        include=["models.*"],
        freeze_seeds=True,
        freeze_seeds_file=freeze_file,
        relations={"models.Order.user_id": "models.User.id"},
        max_depth=3,
        cycle_policy="stub",
        rng_mode="legacy",
    )

    assert result == "ok"
    assert captured["output_template"].raw.endswith("export.csv")
    assert captured["freeze_seeds_file"] == freeze_file
    assert captured["include"] == ("models.*",)
    assert captured["freeze_seeds"] is True
    assert captured["relations"] == {"models.Order.user_id": "models.User.id"}
    assert captured["max_depth"] == 3
    assert captured["cycle_policy"] == "stub"
    assert captured["rng_mode"] == "legacy"
