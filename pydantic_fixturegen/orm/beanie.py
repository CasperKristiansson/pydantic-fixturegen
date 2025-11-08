"""Beanie (MongoDB) seeding helpers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, cast

from beanie import Document, init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from pydantic_fixturegen.api._runtime import ModelArtifactPlan

from ..logging import Logger, get_logger


@dataclass(slots=True)
class BeanieSeedResult:
    inserted: int
    cleanup: bool
    dry_run: bool


class BeanieSeeder:
    """Insert generated payloads into a MongoDB database via Beanie."""

    def __init__(
        self,
        plan: ModelArtifactPlan,
        client_factory: Callable[[], AsyncIOMotorClient[Any]],
        *,
        database_name: str,
        logger: Logger | None = None,
    ) -> None:
        self.plan = plan
        self._client_factory = client_factory
        self._database_name = database_name
        self.logger = logger or get_logger()

    def seed(
        self,
        count: int,
        *,
        batch_size: int = 50,
        cleanup: bool = False,
        dry_run: bool = False,
    ) -> BeanieSeedResult:
        asyncio.run(
            self._seed_async(
                count=count,
                batch_size=batch_size,
                cleanup=cleanup,
                dry_run=dry_run,
            )
        )
        return BeanieSeedResult(inserted=count, cleanup=cleanup, dry_run=dry_run)

    async def _seed_async(
        self,
        *,
        count: int,
        batch_size: int,
        cleanup: bool,
        dry_run: bool,
    ) -> None:
        client = self._client_factory()
        try:
            document_models: list[type[Document]] = [
                cast(type[Document], self.plan.model_cls),
                *[cast(type[Document], cls) for cls in self.plan.related_models],
            ]
            await init_beanie(
                database=cast(Any, client[self._database_name]),
                document_models=document_models,
            )
            inserted_docs: list[Document] = []
            produced = 0
            while produced < count:
                chunk = min(batch_size, count - produced)
                for _ in range(chunk):
                    for model_cls, payload in _expand_sample(self.plan, self.plan.sample_factory()):
                        doc = model_cls(**_clean_payload(payload))
                        if dry_run:
                            continue
                        await doc.insert()
                        inserted_docs.append(doc)
                produced += chunk
            if cleanup and not dry_run:
                for doc in reversed(inserted_docs):
                    await doc.delete()
        finally:
            client.close()
        self.logger.info(
            "Seeded Beanie documents",
            event="beanie_seed_complete",
            count=count,
            cleanup=cleanup,
            dry_run=dry_run,
        )


def _expand_sample(
    plan: ModelArtifactPlan,
    sample: Any,
) -> Iterable[tuple[type[Any], dict[str, Any]]]:
    if isinstance(sample, dict):
        expected_keys = {plan.model_cls.__name__, *[cls.__name__ for cls in plan.related_models]}
        if expected_keys.issubset(sample.keys()):
            ordered: list[tuple[type[Any], dict[str, Any]]] = []
            for related_cls in plan.related_models:
                payload = sample.get(related_cls.__name__)
                if isinstance(payload, dict):
                    ordered.append((related_cls, payload))
            primary_payload = sample.get(plan.model_cls.__name__)
            if isinstance(primary_payload, dict):
                ordered.append((plan.model_cls, primary_payload))
                return ordered
    if not isinstance(sample, dict):
        raise RuntimeError("Seeder expected payload dictionary")
    return [(plan.model_cls, sample)]


def _clean_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "__cycles__"}
