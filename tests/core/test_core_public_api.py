from __future__ import annotations

import pydantic_fixturegen.core as core


def test_core_exports_selected_symbols() -> None:
    exported = set(core.__all__)

    expected = {
        "AppConfig",
        "load_config",
        "create_default_registry",
        "generate_string",
        "SeedManager",
        "Strategy",
    }

    assert expected <= exported
    registry = core.create_default_registry()
    assert registry.__class__.__name__ == "ProviderRegistry"
