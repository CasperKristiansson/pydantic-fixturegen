"""Runtime helpers for wiring Polyfactory delegates into the generator."""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import suppress
from typing import Any, cast

from pydantic import BaseModel

from ..core.generate import InstanceGenerator, ModelDelegate
from ..logging import Logger
from .discovery import PolyfactoryBinding


def attach_polyfactory_bindings(
    generator: InstanceGenerator,
    bindings: Iterable[PolyfactoryBinding],
    *,
    logger: Logger | None = None,
) -> None:
    """Register discovered Polyfactory factories as model delegates."""

    registered = 0
    for binding in bindings:
        delegate = _build_delegate(binding)
        generator.register_delegate(binding.model, delegate)
        registered += 1

    if registered and logger is not None:
        logger.info(
            "Polyfactory delegation enabled",
            event="polyfactory_delegation_enabled",
            count=registered,
        )


def _build_delegate(binding: PolyfactoryBinding) -> ModelDelegate:
    model_label = _model_label(binding.model)
    factory_label = binding.label
    factory_cls = cast("type[Any]", binding.factory)

    def _delegate(
        generator: InstanceGenerator,
        model_type: type[BaseModel],
        path_label: str,
    ) -> BaseModel | None:
        seed = generator.seed_manager.derive_child_seed(
            "polyfactory",
            factory_label,
            path_label,
        )
        faker = generator.seed_manager.faker_for(
            "polyfactory",
            factory_label,
            path_label,
        )
        with suppress(Exception):  # pragma: no cover - attribute may be read-only
            factory_cls.__faker__ = faker
        try:
            factory_cls.seed_random(seed)
        except Exception as exc:  # pragma: no cover - defensive
            raise RuntimeError(f"Failed to seed {factory_label}: {exc}") from exc

        try:
            instance = factory_cls.build()
        except Exception as exc:
            raise RuntimeError(f"Polyfactory build failed for {factory_label}: {exc}") from exc

        if not isinstance(instance, model_type):
            if isinstance(instance, BaseModel) and isinstance(model_type, type) and issubclass(
                model_type, BaseModel
            ):
                try:
                    instance = model_type.model_validate(instance.model_dump())
                except Exception as exc:  # pragma: no cover - defensive
                    raise RuntimeError(
                        "Polyfactory factory returned incompatible type for "
                        f"{model_label}: {type(instance).__qualname__}"
                    ) from exc
            else:
                raise RuntimeError(
                    "Polyfactory factory returned unexpected type for "
                    f"{model_label}: {type(instance).__qualname__}"
                )
        return instance

    return _delegate


def _model_label(model: type[BaseModel]) -> str:
    module = getattr(model, "__module__", "")
    qualname = getattr(model, "__qualname__", getattr(model, "__name__", ""))
    return f"{module}.{qualname}" if module else qualname


__all__ = ["attach_polyfactory_bindings"]
